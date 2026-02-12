const http = require('http');
const { URL } = require('url');

class OllamaClient {
  constructor(baseUrl = 'http://localhost:11434') {
    this.baseUrl = baseUrl;
    this.currentRequest = null;
  }

  /**
   * Stream a chat response from Ollama
   * @param {string} model - Model name (e.g. 'llama3.2')
   * @param {Array} messages - Array of {role, content} messages
   * @param {Function} onToken - Called with each token string
   * @param {Function} onDone - Called when generation completes with {totalDuration, evalCount}
   * @param {Function} onError - Called on error with Error object
   */
  streamChat(model, messages, onToken, onDone, onError) {
    const url = new URL('/api/chat', this.baseUrl);
    const body = JSON.stringify({
      model,
      messages,
      stream: true
    });

    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body)
      },
      timeout: 120000
    };

    const req = http.request(options, (res) => {
      if (res.statusCode === 404) {
        onError(new Error(`Model '${model}' not found. Run: ollama pull ${model}`));
        return;
      }

      if (res.statusCode !== 200) {
        let errorBody = '';
        res.on('data', (chunk) => { errorBody += chunk; });
        res.on('end', () => {
          onError(new Error(`Ollama returned ${res.statusCode}: ${errorBody}`));
        });
        return;
      }

      res.setEncoding('utf8');
      let buffer = '';

      res.on('data', (chunk) => {
        buffer += chunk;
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.done) {
              onDone({
                totalDuration: data.total_duration,
                evalCount: data.eval_count
              });
            } else if (data.message && data.message.content) {
              onToken(data.message.content);
            }
          } catch (parseErr) {
            // Skip malformed JSON lines, continue streaming
            console.warn('Failed to parse Ollama stream line:', line);
          }
        }
      });

      res.on('end', () => {
        // Process any remaining buffer
        if (buffer.trim()) {
          try {
            const data = JSON.parse(buffer);
            if (data.done) {
              onDone({
                totalDuration: data.total_duration,
                evalCount: data.eval_count
              });
            } else if (data.message && data.message.content) {
              onToken(data.message.content);
            }
          } catch (e) {
            // ignore
          }
        }
      });

      res.on('error', (err) => onError(err));
    });

    req.on('error', (err) => {
      if (err.code === 'ECONNREFUSED') {
        onError(new Error('Cannot connect to Ollama. Make sure it is running on ' + this.baseUrl));
      } else {
        onError(err);
      }
    });

    req.on('timeout', () => {
      req.destroy();
      onError(new Error('Request to Ollama timed out after 120 seconds.'));
    });

    this.currentRequest = req;
    req.write(body);
    req.end();
  }

  /**
   * Abort the current in-flight request
   */
  abort() {
    if (this.currentRequest) {
      this.currentRequest.destroy();
      this.currentRequest = null;
    }
  }

  /**
   * Check if Ollama is running and return available models
   * @returns {Promise<{connected: boolean, models: string[], error: string|null}>}
   */
  async checkConnection() {
    return new Promise((resolve) => {
      const url = new URL('/api/tags', this.baseUrl);
      const req = http.get(url, { timeout: 5000 }, (res) => {
        let body = '';
        res.on('data', (chunk) => { body += chunk; });
        res.on('end', () => {
          try {
            const data = JSON.parse(body);
            const models = (data.models || []).map(m => m.name);
            resolve({ connected: true, models, error: null });
          } catch (e) {
            resolve({ connected: true, models: [], error: 'Could not parse model list' });
          }
        });
      });

      req.on('error', (err) => {
        if (err.code === 'ECONNREFUSED') {
          resolve({
            connected: false,
            models: [],
            error: 'Ollama is not running. Start it with `ollama serve` or download from ollama.com'
          });
        } else {
          resolve({ connected: false, models: [], error: err.message });
        }
      });

      req.on('timeout', () => {
        req.destroy();
        resolve({ connected: false, models: [], error: 'Connection timed out' });
      });
    });
  }
}

module.exports = OllamaClient;
