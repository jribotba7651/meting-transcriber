"""
Meeting Notes Assistant - Main Entry Point
Transcribe uploaded audio/video files or live system audio using Whisper.
Live audio is processed in real-time and immediately discarded — zero audio persistence.
"""

import os
import sys
import json
import logging
import subprocess
import atexit

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audio_capture import AudioCapture
from transcriber import Transcriber
from ui import TranscriberUI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    # Default configuration
    default_config = {
        "whisper_model": "base",
        "language": "auto",
        "device": "auto",
        "window_opacity": 0.95,
        "always_on_top": True,
        "buffer_duration": 10
    }

    # Try to load config file
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Merge with defaults
                default_config.update(config)
                logger.info("Configuration loaded from config.json")
        except Exception as e:
            logger.warning(f"Error loading config.json: {e}. Using defaults.")

    return default_config


def save_config(config):
    """Save configuration to config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("Configuration saved")
    except Exception as e:
        logger.error(f"Error saving config: {e}")


def main():
    """Main application entry point"""
    logger.info("=" * 60)
    logger.info("Meeting Notes Assistant")
    logger.info("=" * 60)

    # Load configuration
    config = load_config()

    # Initialize audio capture (stream-only, zero persistence, decoupled transcription)
    logger.info("Initializing audio capture (stream-only mode, decoupled transcription)...")
    audio_capture = AudioCapture(
        accumulate_seconds=config.get('buffer_duration', 10),
        overlap_seconds=config.get('overlap_seconds', 2)
    )

    # Initialize transcriber
    logger.info("Initializing transcriber...")
    transcriber = Transcriber(
        model_size=config['whisper_model'],
        device=config['device'],
        language=config['language']
    )

    # --- AI Assistant disabled for now (uncomment to re-enable) ---
    # # Start local LLM server (Ollama-compatible API on localhost:11434)
    llm_server = None
    # try:
    #     from local_llm_server import start_server
    #     llm_server = start_server(port=11434)
    # except Exception as e:
    #     logger.warning(f"Could not start local LLM server: {e}")
    #     logger.warning("AI Assistant will show 'Disconnected' until Ollama or local LLM is available.")

    # # Launch AI Overlay (Electron) as a child process
    overlay_process = None
    # overlay_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'overlay')
    # npx_path = os.path.join(overlay_dir, 'node_modules', '.bin', 'electron.cmd')
    #
    # if os.path.exists(npx_path):
    #     try:
    #         logger.info("Launching AI Overlay...")
    #         overlay_process = subprocess.Popen(
    #             [npx_path, '.'],
    #             cwd=overlay_dir,
    #             stdout=subprocess.DEVNULL,
    #             stderr=subprocess.DEVNULL,
    #             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    #         )
    #         logger.info(f"AI Overlay started (PID: {overlay_process.pid})")
    #     except Exception as e:
    #         logger.warning(f"Could not launch AI Overlay: {e}")
    # else:
    #     logger.warning("AI Overlay not found. Run 'npm install' in the overlay/ folder.")

    def cleanup_overlay():
        """Terminate overlay when main app exits"""
        if overlay_process and overlay_process.poll() is None:
            logger.info("Shutting down AI Overlay...")
            overlay_process.terminate()
            try:
                overlay_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                overlay_process.kill()

    atexit.register(cleanup_overlay)

    # Create and run UI
    logger.info("Starting UI...")
    app = TranscriberUI(audio_capture, transcriber, config)

    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
    finally:
        cleanup_overlay()
        if llm_server:
            from local_llm_server import stop_server
            stop_server(llm_server)
        audio_capture.cleanup()
        logger.info("Goodbye!")


if __name__ == "__main__":
    main()
