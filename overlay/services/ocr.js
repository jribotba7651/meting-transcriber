const { createWorker } = require('tesseract.js');
const screenshot = require('screenshot-desktop');
const path = require('path');
const fs = require('fs');
const os = require('os');

// --- Local paths for air-gapped operation ---
const TESSDATA_PATH = path.join(__dirname, 'tessdata');
const WORKER_PATH = path.join(__dirname, '..', 'node_modules', 'tesseract.js', 'dist', 'worker.min.js');
const CORE_PATH = path.join(__dirname, '..', 'node_modules', 'tesseract.js-core');

class OCRService {
  constructor() {
    this.worker = null;
    this.isReady = false;
    this.isInitializing = false;
  }

  async initialize() {
    if (this.isReady || this.isInitializing) return;
    this.isInitializing = true;

    try {
      this.worker = await createWorker('eng+spa', {
        workerPath: WORKER_PATH,
        corePath: CORE_PATH,
        langPath: TESSDATA_PATH,
        gzip: false,
        cacheMethod: 'none',
        logging: false,
      });
      this.isReady = true;
      console.log('OCR worker initialized (local tessdata)');
    } catch (err) {
      console.error('Failed to initialize OCR worker:', err);
      this.isReady = false;
    } finally {
      this.isInitializing = false;
    }
  }

  /**
   * Capture screenshot using screenshot-desktop (native, reliable on Windows).
   * Saves to temp file and returns the path.
   */
  async captureScreen() {
    const tmpPath = path.join(os.tmpdir(), `ocr_capture_${Date.now()}.png`);
    try {
      await screenshot({ filename: tmpPath });
      const buffer = fs.readFileSync(tmpPath);
      // Clean up temp file
      try { fs.unlinkSync(tmpPath); } catch (e) { /* ignore */ }
      return buffer;
    } catch (err) {
      try { fs.unlinkSync(tmpPath); } catch (e) { /* ignore */ }
      throw new Error('Screenshot capture failed: ' + err.message);
    }
  }

  /**
   * Capture screenshot and extract text via OCR.
   * Hides overlay during capture so it doesn't appear in the screenshot.
   */
  async captureAndRecognize(overlayWindow = null) {
    if (!this.isReady) {
      console.log('OCR: Initializing worker on first use...');
      await this.initialize();
    }

    if (!this.worker) {
      throw new Error('OCR engine failed to initialize. Check tessdata files.');
    }

    // Hide overlay so it doesn't appear in screenshot
    if (overlayWindow && overlayWindow.isVisible()) {
      overlayWindow.hide();
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    let imgBuffer;
    try {
      imgBuffer = await this.captureScreen();
      console.log(`OCR: Screenshot captured (${imgBuffer.length} bytes)`);
    } catch (err) {
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
      console.log(`OCR: Extracted ${cleaned.length} characters`);
      if (!cleaned) {
        throw new Error('No text detected in screenshot.');
      }
      return cleaned;
    } catch (err) {
      if (err.message.includes('No text detected')) throw err;
      throw new Error('OCR recognition failed: ' + err.message);
    }
  }

  async terminate() {
    if (this.worker) {
      try { await this.worker.terminate(); } catch (e) { /* ignore */ }
      this.worker = null;
      this.isReady = false;
    }
  }
}

module.exports = OCRService;
