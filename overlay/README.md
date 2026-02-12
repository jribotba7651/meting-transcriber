# Local AI Assistant Overlay

A transparent, always-on-top desktop overlay that connects to **Ollama** for 100% local AI assistance. No data leaves your machine. Invisible to screen sharing.

## Features

- **Transparent overlay** - Frameless, always-on-top window that floats over your apps
- **Invisible to screen sharing** - Content protection enabled (`setContentProtection`)
- **Local AI via Ollama** - Chat with any model you have installed locally
- **Streaming responses** - See AI responses as they generate in real-time
- **Clipboard monitoring** - Auto-captures copied text as context for your questions
- **Screenshot + OCR** - Capture your screen and extract text with Tesseract.js
- **Global hotkeys** - Control the overlay without switching windows
- **Adjustable opacity** - Cycle through transparency levels (95% / 70% / 40% / 20%)
- **Click-through mode** - Make the overlay non-interactive while keeping it visible
- **Conversation persistence** - Chat history saved to disk, survives restarts
- **System prompt** - Configurable behavior instructions for the AI
- **Code copy buttons** - One-click copy for code blocks in AI responses
- **Markdown rendering** - Bold, italic, headers, lists, code blocks, links
- **Multi-model support** - Switch between installed Ollama models on the fly
- **Configurable** - JSON config file for all settings

## Prerequisites

1. **Node.js** (v18+): https://nodejs.org
2. **Ollama** running locally: https://ollama.ai

```bash
# Install Ollama, then pull a model:
ollama pull llama3.2

# Start Ollama if it's not running as a service:
ollama serve
```

## Setup

```bash
cd overlay
npm install
npm start
```

## Build Distributable

```bash
# Install build dependencies
npm install

# Build for your platform
npm run build:win     # Windows (.exe installer + portable)
npm run build:mac     # macOS (.dmg)
npm run build:linux   # Linux (.AppImage + .deb)
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+Space` | Show/Hide overlay |
| `Ctrl+Shift+O` | Screenshot + OCR (captures screen text) |
| `Ctrl+Shift+A` | Send clipboard content to AI context |

All shortcuts are configurable in `config.json`.

## UI Controls

| Control | Action |
|---|---|
| Eye icon | Toggle click-through mode |
| Circle icon | Cycle opacity (95% / 70% / 40% / 20%) |
| Minus icon | Hide overlay |
| X icon | Quit application |
| Model badge | Click to switch Ollama models |
| Clipboard btn | Toggle automatic clipboard monitoring |
| OCR btn | Manual screenshot + OCR capture |
| Clear btn | Clear chat history |

## Configuration

Edit `config.json` to customize:

```json
{
  "ollama": {
    "baseUrl": "http://localhost:11434",
    "defaultModel": "llama3.2",
    "requestTimeout": 120000
  },
  "window": {
    "width": 380,
    "height": 500,
    "opacity": 0.95,
    "position": "bottom-right",
    "margin": 20
  },
  "shortcuts": {
    "toggleOverlay": "CommandOrControl+Shift+Space",
    "screenshotOCR": "CommandOrControl+Shift+O",
    "clipboardAsk": "CommandOrControl+Shift+A"
  },
  "clipboard": {
    "pollIntervalMs": 500,
    "autoMonitor": false
  },
  "ocr": {
    "languages": "eng+spa"
  },
  "systemPrompt": "You are a helpful local AI assistant..."
}
```

### Window positions
`"position"` can be: `"bottom-right"`, `"bottom-left"`, `"top-right"`, `"top-left"`

### OCR languages
Uses Tesseract.js language codes. Common: `"eng"`, `"spa"`, `"fra"`, `"deu"`, `"por"`. Combine with `+`: `"eng+spa"`

## Architecture

```
overlay/
├── main.js              # Electron main process
├── preload.js           # Secure IPC bridge
├── config.json          # User configuration
├── package.json         # Dependencies & build config
├── renderer/
│   ├── index.html       # Overlay UI
│   ├── styles.css       # Dark theme styles
│   └── app.js           # Chat logic, markdown, persistence
└── services/
    ├── ai.js            # Ollama HTTP client (chat + streaming)
    ├── clipboard.js     # Clipboard polling monitor
    └── ocr.js           # Screenshot + Tesseract.js OCR
```

## How It Works

```
┌─────────────────────────────────────────────┐
│  Electron (Transparent Window)              │
│  ┌──────────────┐  ┌────────────────────┐   │
│  │ Clipboard    │  │ Screenshot + OCR   │   │
│  │ Monitor      │  │ (Tesseract.js)     │   │
│  └──────┬───────┘  └────────┬───────────┘   │
│         │                   │               │
│         ▼                   ▼               │
│  ┌──────────────────────────────────────┐   │
│  │         Chat Interface               │   │
│  │  (markdown, code blocks, copy btn)   │   │
│  └──────────────┬───────────────────────┘   │
│                 │                           │
│                 ▼                           │
│  ┌──────────────────────────────────────┐   │
│  │     Ollama API (localhost:11434)     │   │
│  │     Streaming HTTP responses        │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Troubleshooting

**"AI: OFF" in status bar**
- Make sure Ollama is running: `ollama serve`
- Check that you have at least one model: `ollama list`
- Verify the URL in config.json matches your Ollama instance

**OCR not working**
- First OCR call downloads Tesseract language data (~15MB)
- On macOS: grant Screen Recording permission in System Preferences
- On Linux: ensure `xdpyinfo` or similar screen capture tool is available

**Overlay hidden and can't find it**
- Use `Ctrl+Shift+Space` to toggle visibility
- Right-click the system tray icon and select "Reset Position"

**Streaming seems slow**
- Larger models are slower; try a smaller model like `llama3.2:1b`
- Check if GPU acceleration is enabled in Ollama

**Chat history lost**
- History is saved to your OS user data directory
- Windows: `%APPDATA%/local-ai-overlay/`
- macOS: `~/Library/Application Support/local-ai-overlay/`
- Linux: `~/.config/local-ai-overlay/`
