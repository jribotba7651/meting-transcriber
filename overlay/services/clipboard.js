const { clipboard } = require('electron');

class ClipboardService {
  constructor(onChange, pollMs = 500) {
    this.onChange = onChange;
    this.lastText = '';
    this.interval = null;
    this.pollMs = pollMs;
  }

  start() {
    if (this.interval) return;

    this.lastText = clipboard.readText();

    this.interval = setInterval(() => {
      try {
        const currentText = clipboard.readText();
        if (currentText && currentText !== this.lastText) {
          this.lastText = currentText;
          this.onChange(currentText);
        }
      } catch (e) {
        // Clipboard may be locked by another app, skip this poll
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
