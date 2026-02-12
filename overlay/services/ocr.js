const { createWorker } = require('tesseract.js');

class OCRService {
  constructor(languages = 'eng+spa') {
    this.worker = null;
    this.languages = languages;
    this.initializing = false;
  }

  async initWorker() {
    if (this.worker) return;
    if (this.initializing) {
      // Wait for ongoing init
      while (this.initializing) {
        await new Promise(r => setTimeout(r, 100));
      }
      return;
    }

    this.initializing = true;
    try {
      this.worker = await createWorker(this.languages);
    } finally {
      this.initializing = false;
    }
  }

  /**
   * Capture the screen and run OCR on it
   */
  async captureAndRecognize() {
    await this.initWorker();

    const screenshot = require('screenshot-desktop');

    // Capture the full screen as a PNG buffer
    const imgBuffer = await screenshot({ format: 'png' });

    // Run OCR on the captured image
    const { data: { text } } = await this.worker.recognize(imgBuffer);

    return text.trim();
  }

  /**
   * Run OCR on a provided image buffer
   */
  async recognizeBuffer(buffer) {
    await this.initWorker();
    const { data: { text } } = await this.worker.recognize(buffer);
    return text.trim();
  }

  async cleanup() {
    if (this.worker) {
      await this.worker.terminate();
      this.worker = null;
    }
  }
}

module.exports = { OCRService };
