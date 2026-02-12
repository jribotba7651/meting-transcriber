const { clipboard } = require('electron');

class ClipboardMonitor {
  constructor(interval = 500) {
    this.interval = interval;
    this.lastText = '';
    this.timer = null;
    this.onChange = null;
  }

  /**
   * Start monitoring clipboard for changes
   * @param {Function} callback - Called with new text when clipboard changes
   */
  start(callback) {
    this.onChange = callback;
    this.lastText = clipboard.readText() || '';

    this.timer = setInterval(() => {
      try {
        const current = clipboard.readText() || '';
        if (current && current !== this.lastText) {
          this.lastText = current;
          if (this.onChange) {
            this.onChange(current);
          }
        }
      } catch (err) {
        // Clipboard read can fail intermittently, just skip
      }
    }, this.interval);
  }

  /**
   * Stop monitoring clipboard
   */
  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  /**
   * Get current clipboard text without triggering change event
   * @returns {string}
   */
  getCurrentText() {
    try {
      return clipboard.readText() || '';
    } catch (err) {
      return '';
    }
  }
}

module.exports = ClipboardMonitor;
