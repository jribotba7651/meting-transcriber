const http = require('http');

class AIService {
  constructor(baseUrl = 'http://localhost:11434') {
    this.baseUrl = baseUrl;
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
          try {
            const parsed = JSON.parse(data);
            resolve(parsed.message?.content || 'No response');
          } catch (e) {
            reject(new Error(`Failed to parse Ollama response: ${data}`));
          }
        });
      });

      req.on('error', (e) => {
        reject(new Error(`Ollama connection failed. Is Ollama running? (${e.message})`));
      });

      req.setTimeout(120000, () => {
        req.destroy();
        reject(new Error('Ollama request timed out after 120s'));
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
      }, resolve);

      req.on('error', (e) => {
        reject(new Error(`Ollama connection failed. Is Ollama running? (${e.message})`));
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
          if (parsed.message?.content) {
            yield parsed.message.content;
          }
        } catch (e) {
          // Skip malformed JSON lines
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
    return new Promise((resolve, reject) => {
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
        resolve([]);  // Return empty list if Ollama isn't running
      });

      req.end();
    });
  }
}

module.exports = { AIService };
