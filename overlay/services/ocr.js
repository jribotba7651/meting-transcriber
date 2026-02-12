const { createWorker } = require('tesseract.js');
const path = require('path');

class OCRService {
  constructor() {
    this.worker = null;
  }

  async initWorker() {
    if (this.worker) return;
    this.worker = await createWorker('eng+spa');
  }

  /**
   * Capture the screen and run OCR on it
   * Returns extracted text
   */
  async captureAndRecognize() {
    await this.initWorker();

    // Dynamic import for screenshot-desktop (ESM/CJS compatibility)
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
