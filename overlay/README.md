# Local AI Assistant Overlay

A transparent, always-on-top desktop overlay that connects to **Ollama** for 100% local AI assistance. No data leaves your machine.

## Features

- **Transparent overlay** - Frameless, always-on-top window that floats over your apps
- **Invisible to screen sharing** - Content protection enabled (platform-dependent)
- **Local AI via Ollama** - Chat with any model you have installed locally
- **Streaming responses** - See AI responses as they generate in real-time
- **Clipboard monitoring** - Auto-captures copied text as context for your questions
- **Screenshot + OCR** - Capture your screen and extract text with Tesseract.js
- **Global hotkeys** - Control the overlay without switching windows
- **Adjustable opacity** - Cycle through transparency levels
- **Click-through mode** - Make the overlay non-interactive while keeping it visible

## Prerequisites

1. **Node.js** (v18+): https://nodejs.org
2. **Ollama** running locally: https://ollama.ai
   ```bash
   # Install Ollama, then pull a model:
   ollama pull llama3.2
   ```

## Setup

```bash
cd overlay
npm install
npm start
```

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Shift+Space` | Show/Hide overlay |
| `Ctrl+Shift+O` | Screenshot + OCR (captures screen text) |
| `Ctrl+Shift+A` | Send clipboard content to AI context |

## UI Controls

- **Eye icon** - Toggle click-through mode
- **Circle icon** - Cycle opacity (95% → 70% → 40% → 20%)
- **Minus icon** - Hide overlay
- **X icon** - Quit application
- **Model badge** - Click to switch Ollama models
- **Clipboard button** - Toggle automatic clipboard monitoring
- **OCR button** - Manual screenshot + OCR capture
- **Clear button** - Clear chat history

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
│  │    (context + user question)         │   │
│  └──────────────┬───────────────────────┘   │
│                 │                           │
│                 ▼                           │
│  ┌──────────────────────────────────────┐   │
│  │     Ollama API (localhost:11434)     │   │
│  │     Streaming HTTP responses        │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

1. **Overlay Window** - Electron creates a transparent, frameless, always-on-top window
2. **Input Methods** - You can type questions, copy text (clipboard), or screenshot (OCR)
3. **AI Processing** - All queries go to your local Ollama instance
4. **Streaming** - Responses stream in real-time to the overlay

## Configuration

Edit `main.js` to change:
- Window dimensions and position
- Default model name
- Hotkey bindings
- Content protection settings

## Troubleshooting

**"AI: OFF" in status bar**
- Make sure Ollama is running: `ollama serve`
- Check that you have at least one model: `ollama list`

**OCR not working**
- First OCR call downloads the Tesseract language data (~15MB)
- Screenshot capture requires screen recording permissions on macOS

**Overlay hidden and can't find it**
- Use `Ctrl+Shift+Space` to toggle visibility
- Use the system tray icon → "Reset Position"
