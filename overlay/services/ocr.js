const { createWorker } = require('tesseract.js');
const screenshot = require('screenshot-desktop');
const path = require('path');

// ─── Local paths for air-gapped operation (F-OCR-001 fix) ───
// All Tesseract assets are bundled locally — zero CDN calls.
const TESSDATA_PATH = path.join(__dirname, 'tessdata');
const WORKER_PATH = path.join(__dirname, '..', 'node_modules', 'tesseract.js', 'dist', 'worker.min.js');
const CORE_PATH = path.join(__dirname, '..', 'node_modules', 'tesseract.js-core');

class OCRService {
  constructor() {
    this.worker = null;
    this.isReady = false;
    this.isInitializing = false;
  }

  /**
   * Pre-initialize the Tesseract worker for faster first OCR call.
   * All models loaded from local filesystem — no network access.
   */
  async initialize() {
    if (this.isReady || this.isInitializing) return;
    this.isInitializing = true;

    try {
      this.worker = await createWorker('eng+spa', {
        workerPath: WORKER_PATH,
        corePath: CORE_PATH,
        langPath: TESSDATA_PATH,
        gzip: false,           // Our .traineddata files are not gzipped
        cacheMethod: 'none',   // Don't cache — we already have local files
        logging: false,        // Suppress verbose logging
      });
      this.isReady = true;
      console.log('OCR worker initialized (local tessdata, no CDN)');
    } catch (err) {
      console.error('Failed to initialize OCR worker:', err);
      this.isReady = false;
    } finally {
      this.isInitializing = false;
    }
  }

  /**
   * Capture screenshot and extract text via OCR
   * @param {BrowserWindow} overlayWindow - The overlay window to hide during capture
   * @returns {Promise<string>} Extracted text
   */
  async captureAndRecognize(overlayWindow = null) {
    if (!this.isReady) {
      await this.initialize();
    }

    if (!this.worker) {
      throw new Error('OCR engine failed to initialize. Restart the app.');
    }

    // Hide overlay so it doesn't appear in screenshot
    if (overlayWindow && overlayWindow.isVisible()) {
      overlayWindow.hide();
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    let imgBuffer;
    try {
      imgBuffer = await screenshot({ format: 'png' });
    } catch (err) {
      // Re-show overlay before throwing
      if (overlayWindow) overlayWindow.show();
      throw new Error('Could not capture screen: ' + err.message);
    }

    // Re-show overlay
    if (overlayWindow) {
      overlayWindow.show();
    }

    try {
      const { data: { text } } = await this.worker.recognize(imgBuffer);
      const cleaned = text.trim();
      if (!cleaned) {
        throw new Error('No text detected in screenshot.');
      }
      return cleaned;
    } catch (err) {
      if (err.message.includes('No text detected')) throw err;
      throw new Error('OCR failed: ' + err.message);
    }
  }

  /**
   * Clean up the Tesseract worker
   */
  async terminate() {
    if (this.worker) {
      try {
        await this.worker.terminate();
      } catch (e) {
        // ignore termination errors
      }
      this.worker = null;
      this.isReady = false;
    }
  }
}

module.exports = OCRService;
