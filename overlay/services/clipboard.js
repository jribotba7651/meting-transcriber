const { clipboard } = require('electron');

class ClipboardService {
  constructor(onChange) {
    this.onChange = onChange;
    this.lastText = '';
    this.interval = null;
    this.pollMs = 500; // Check every 500ms
  }

  start() {
    if (this.interval) return;

    this.lastText = clipboard.readText();

    this.interval = setInterval(() => {
      const currentText = clipboard.readText();
      if (currentText && currentText !== this.lastText) {
        this.lastText = currentText;
        this.onChange(currentText);
      }
    }, this.pollMs);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }
}

module.exports = { ClipboardService };
