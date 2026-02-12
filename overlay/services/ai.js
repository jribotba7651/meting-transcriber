const http = require('http');

class AIService {
  constructor(baseUrl = 'http://localhost:11434', timeout = 120000) {
    this.baseUrl = baseUrl;
    this.timeout = timeout;
  }

  /**
   * Check if Ollama is reachable
   */
  async healthCheck() {
    return new Promise((resolve) => {
      const url = new URL('/', this.baseUrl);
      const req = http.request({
        hostname: url.hostname,
        port: url.port,
        path: '/',
        method: 'GET',
        timeout: 5000,
      }, (res) => {
        resolve({ ok: true, status: res.statusCode });
      });
      req.on('error', () => resolve({ ok: false, error: 'Connection refused' }));
      req.on('timeout', () => {
        req.destroy();
        resolve({ ok: false, error: 'Timeout' });
      });
      req.end();
    });
  }

  /**
   * Send a chat request to Ollama and get the full response
   */
  async chat(messages, model = 'llama3.2') {
    const body = JSON.stringify({
      model,
      messages,
      stream: false,
    });

    return new Promise((resolve, reject) => {
      const url = new URL('/api/chat', this.baseUrl);
      const req = http.request({
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      }, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          if (res.statusCode >= 400) {
            try {
              const parsed = JSON.parse(data);
              reject(new Error(parsed.error || `Ollama error (HTTP ${res.statusCode})`));
            } catch (e) {
              reject(new Error(`Ollama error (HTTP ${res.statusCode}): ${data.substring(0, 200)}`));
            }
            return;
          }
          try {
            const parsed = JSON.parse(data);
            resolve(parsed.message?.content || 'No response');
          } catch (e) {
            reject(new Error(`Failed to parse Ollama response: ${data.substring(0, 200)}`));
          }
        });
      });

      req.on('error', (e) => {
        if (e.code === 'ECONNREFUSED') {
          reject(new Error('Ollama is not running. Start it with: ollama serve'));
        } else {
          reject(new Error(`Ollama connection failed: ${e.message}`));
        }
      });

      req.setTimeout(this.timeout, () => {
        req.destroy();
        reject(new Error(`Ollama request timed out after ${this.timeout / 1000}s`));
      });

      req.write(body);
      req.end();
    });
  }

  /**
   * Stream a chat response from Ollama, yielding chunks as they arrive
   */
  async *chatStream(messages, model = 'llama3.2') {
    const body = JSON.stringify({
      model,
      messages,
      stream: true,
    });

    const response = await new Promise((resolve, reject) => {
      const url = new URL('/api/chat', this.baseUrl);
      const req = http.request({
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
        },
      }, (res) => {
        if (res.statusCode >= 400) {
          let data = '';
          res.on('data', (chunk) => { data += chunk; });
          res.on('end', () => {
            try {
              const parsed = JSON.parse(data);
              reject(new Error(parsed.error || `Ollama error (HTTP ${res.statusCode})`));
            } catch (e) {
              reject(new Error(`Ollama error (HTTP ${res.statusCode})`));
            }
          });
          return;
        }
        resolve(res);
      });

      req.on('error', (e) => {
        if (e.code === 'ECONNREFUSED') {
          reject(new Error('Ollama is not running. Start it with: ollama serve'));
        } else {
          reject(new Error(`Ollama connection failed: ${e.message}`));
        }
      });

      req.setTimeout(this.timeout, () => {
        req.destroy();
        reject(new Error(`Ollama request timed out after ${this.timeout / 1000}s`));
      });

      req.write(body);
      req.end();
    });

    let buffer = '';

    for await (const chunk of response) {
      buffer += chunk.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const parsed = JSON.parse(line);
          if (parsed.error) {
            throw new Error(parsed.error);
          }
          if (parsed.message?.content) {
            yield parsed.message.content;
          }
        } catch (e) {
          if (e.message && !e.message.includes('JSON')) {
            throw e;
          }
        }
      }
    }

    // Process remaining buffer
    if (buffer.trim()) {
      try {
        const parsed = JSON.parse(buffer);
        if (parsed.message?.content) {
          yield parsed.message.content;
        }
      } catch (e) {
        // Skip
      }
    }
  }

  /**
   * List available Ollama models
   */
  async listModels() {
    return new Promise((resolve) => {
      const url = new URL('/api/tags', this.baseUrl);
      const req = http.request({
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: 'GET',
      }, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          try {
            const parsed = JSON.parse(data);
            const models = (parsed.models || []).map(m => ({
              name: m.name,
              size: m.size,
              modified: m.modified_at,
            }));
            resolve(models);
          } catch (e) {
            resolve([]);
          }
        });
      });

      req.on('error', () => {
        resolve([]);
      });

      req.setTimeout(5000, () => {
        req.destroy();
        resolve([]);
      });

      req.end();
    });
  }
}

module.exports = { AIService };
