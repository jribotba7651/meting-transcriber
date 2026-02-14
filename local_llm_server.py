"""
Local LLM Server - Ollama-compatible API using GPT4All
Runs on localhost:11434, same API format as Ollama so the overlay works without changes.
"""

import json
import threading
import logging
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from gpt4all import GPT4All

logger = logging.getLogger(__name__)

# Connection errors that occur when the client (Electron) aborts/closes the request.
# These are harmless and expected - the health check polls every 15s and may close early.
_CONNECTION_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)

# Global model instance
_model = None
_model_name = None
_model_lock = threading.Lock()
_generate_lock = threading.Lock()   # Serialize model.generate() calls (GPT4All is NOT thread-safe)
_model_ready = False  # True once model is fully loaded and ready to generate


def get_model():
    """Lazy-load the GPT4All model"""
    global _model, _model_name, _model_ready
    if _model is None:
        with _model_lock:
            if _model is None:
                # Use a small, fast model that works on CPU
                _model_name = "Phi-3-mini-4k-instruct.Q4_0.gguf"
                logger.info(f"Loading GPT4All model: {_model_name}")
                logger.info("First run will download ~2GB model file...")
                _model = GPT4All(_model_name, allow_download=True)
                _model_ready = True
                logger.info("Model loaded successfully")
    return _model


class OllamaCompatHandler(BaseHTTPRequestHandler):
    """HTTP handler that mimics Ollama API endpoints"""

    def log_message(self, format, *args):
        """Suppress default HTTP logging"""
        pass

    def handle_one_request(self):
        """Override to catch connection errors at the top level."""
        try:
            super().handle_one_request()
        except _CONNECTION_ERRORS:
            pass
        except OSError as e:
            # Windows-specific socket errors (10053=abort, 10054=reset, 10057=not connected)
            if getattr(e, 'winerror', 0) in (10053, 10054, 10057):
                pass
            else:
                raise

    def handle(self):
        """Override to suppress connection errors during the full handle cycle."""
        try:
            super().handle()
        except _CONNECTION_ERRORS:
            pass

    def _send_json(self, data, status=200):
        try:
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
        except _CONNECTION_ERRORS:
            pass  # Client already disconnected

    def _send_ndjson_line(self, data):
        """Send a single newline-delimited JSON line"""
        try:
            self.wfile.write(json.dumps(data).encode() + b'\n')
            self.wfile.flush()
        except _CONNECTION_ERRORS:
            pass  # Client already disconnected

    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
        except _CONNECTION_ERRORS:
            pass

    def do_GET(self):
        if self.path == '/api/tags' or self.path == '/api/tags/':
            # List models endpoint — always respond 200 so overlay shows "Connected"
            if _model_ready:
                self._send_json({
                    'models': [{
                        'name': 'phi3-mini',
                        'model': 'phi3-mini',
                        'size': 2000000000,
                    }]
                })
            else:
                # Model still loading — return empty models but still 200
                self._send_json({
                    'models': [{
                        'name': 'phi3-mini (loading...)',
                        'model': 'phi3-mini',
                        'size': 2000000000,
                    }]
                })
        elif self.path == '/' or self.path == '/api/version':
            # Health check
            self._send_json({
                'status': 'ok',
                'version': 'gpt4all-compat',
                'model_ready': _model_ready
            })
        else:
            self._send_json({'error': 'not found'}, 404)

    def do_POST(self):
        if self.path == '/api/chat':
            self._handle_chat()
        elif self.path == '/api/generate':
            self._handle_generate()
        else:
            self._send_json({'error': 'not found'}, 404)

    def _handle_chat(self):
        """Handle /api/chat - streaming chat completion"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))
        except Exception as e:
            logger.error(f"Failed to read chat request body: {e}")
            self._send_json({'error': str(e)}, 400)
            return

        messages = body.get('messages', [])
        stream = body.get('stream', True)

        if not _model_ready:
            self._send_json({'error': 'Model is still loading, please wait...'}, 503)
            return

        # Build prompt from messages
        model = get_model()

        # Format messages for GPT4All chat
        system_prompt = ""
        chat_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_prompt = msg['content']
            else:
                chat_messages.append(msg)

        if not chat_messages:
            self._send_json({'error': 'No messages provided'}, 400)
            return

        # Send response headers for streaming
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        except _CONNECTION_ERRORS:
            return  # Client already gone

        try:
            if stream:
                # Streaming response
                with _generate_lock, model.chat_session(system_prompt=system_prompt if system_prompt else None):
                    # Replay previous conversation to build full context
                    # Both user AND assistant messages are needed for coherent memory
                    for msg in chat_messages[:-1]:
                        if msg['role'] == 'user':
                            # Generate response to build context (discard output)
                            model.generate(msg['content'], max_tokens=1)
                        elif msg['role'] == 'assistant':
                            # Inject assistant response into context via internal state
                            if hasattr(model, 'current_chat_session') and model.current_chat_session:
                                model.current_chat_session.append({
                                    'role': 'assistant',
                                    'content': msg['content']
                                })

                    # Generate response for last message
                    last_msg = chat_messages[-1]['content']

                    full_response = ""
                    for token in model.generate(last_msg, max_tokens=1024, streaming=True):
                        full_response += token
                        try:
                            self.wfile.write(json.dumps({
                                'model': 'phi3-mini',
                                'message': {'role': 'assistant', 'content': token},
                                'done': False
                            }).encode() + b'\n')
                            self.wfile.flush()
                        except _CONNECTION_ERRORS:
                            # Client disconnected mid-stream — stop generating
                            logger.info("Client disconnected during streaming, stopping generation")
                            return

                    # Send final done message
                    self._send_ndjson_line({
                        'model': 'phi3-mini',
                        'message': {'role': 'assistant', 'content': ''},
                        'done': True,
                        'total_duration': 0,
                        'eval_count': len(full_response.split())
                    })
            else:
                # Non-streaming
                with _generate_lock, model.chat_session(system_prompt=system_prompt if system_prompt else None):
                    # Replay context (same as streaming path)
                    for msg in chat_messages[:-1]:
                        if msg['role'] == 'user':
                            model.generate(msg['content'], max_tokens=1)
                        elif msg['role'] == 'assistant':
                            if hasattr(model, 'current_chat_session') and model.current_chat_session:
                                model.current_chat_session.append({
                                    'role': 'assistant',
                                    'content': msg['content']
                                })

                    last_msg = chat_messages[-1]['content']
                    response = model.generate(last_msg, max_tokens=1024)

                    self._send_ndjson_line({
                        'model': 'phi3-mini',
                        'message': {'role': 'assistant', 'content': response},
                        'done': True
                    })

        except _CONNECTION_ERRORS:
            logger.info("Client disconnected during chat")
        except Exception as e:
            logger.error(f"Chat error: {e}")
            try:
                self._send_ndjson_line({
                    'model': 'phi3-mini',
                    'message': {'role': 'assistant', 'content': f'Error: {str(e)}'},
                    'done': True
                })
            except _CONNECTION_ERRORS:
                pass

    def _handle_generate(self):
        """Handle /api/generate - simple text generation"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length))
        except Exception as e:
            self._send_json({'error': str(e)}, 400)
            return

        if not _model_ready:
            self._send_json({'error': 'Model is still loading, please wait...'}, 503)
            return

        prompt = body.get('prompt', '')
        model = get_model()

        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ndjson')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        except _CONNECTION_ERRORS:
            return

        try:
            response = model.generate(prompt, max_tokens=1024)
            self._send_ndjson_line({
                'model': 'phi3-mini',
                'response': response,
                'done': True
            })
        except _CONNECTION_ERRORS:
            pass
        except Exception as e:
            logger.error(f"Generate error: {e}")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in a separate thread so health checks
    don't block while a streaming chat response is in progress."""
    daemon_threads = True


def start_server(port=11434):
    """Start the Ollama-compatible local LLM server"""
    server = ThreadedHTTPServer(('127.0.0.1', port), OllamaCompatHandler)
    server.timeout = None
    logger.info(f"Local LLM server starting on http://127.0.0.1:{port}")

    # Pre-load model in background
    def preload():
        try:
            get_model()
        except Exception as e:
            logger.error(f"Failed to pre-load model: {e}")

    threading.Thread(target=preload, daemon=True).start()

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    logger.info("Local LLM server running")
    return server


def stop_server(server):
    """Stop the server"""
    if server:
        server.shutdown()
        logger.info("Local LLM server stopped")
