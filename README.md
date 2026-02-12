# Meeting Notes Assistant

Local meeting notes tool for Windows using OpenAI Whisper. Transcribe uploaded files or capture live audio in real-time — all processing stays on your machine.

> **Zero audio persistence.** Live audio is processed by Whisper in real-time and immediately discarded from memory. No audio files are created or stored at any time. Only the text transcription is kept.

## Features

- **Live transcription** — Capture system audio in real-time via WASAPI loopback, with consent dialog
- **File upload transcription** — Upload MP4, MKV, AVI, MP3, WAV, M4A, and other formats
- **Zero audio persistence** — Live audio stream goes directly to Whisper and is immediately discarded
- **Consent dialog** — Users must acknowledge before starting live transcription
- **Local transcription** using Whisper (no API keys required)
- **Multiple model sizes** (tiny, base, small, medium, large)
- **GPU acceleration** support (CUDA) with automatic CPU fallback
- **Always-on-top window** for easy monitoring
- **Timestamped transcription** with export to text file
- **Classification headers** on saved transcription files
- **No network access** after initial model download

## AI Overlay (Local Assistant)

The `overlay/` directory contains an Electron-based AI assistant overlay:

- **Invisible to screen sharing** — protected from screen capture
- **Chat with local AI** via Ollama (no cloud APIs)
- **Screenshot + OCR** — capture on-screen text for notes
- **Clipboard monitoring** — auto-captures copied text as context
- **Global hotkeys** — Ctrl+Shift+Space to toggle, Ctrl+Shift+O for OCR

See `overlay/` for setup instructions.

## System Requirements

- Windows 10/11
- Python 3.11 or later
- 4GB RAM minimum (8GB+ recommended for larger models)
- CUDA-compatible GPU (optional, for faster transcription)

## Architecture

```
meeting-transcriber/
├── main.py              # Application entry point
├── audio_capture.py     # WASAPI loopback capture (stream-only, zero persistence)
├── transcriber.py       # Whisper-based transcription
├── ui.py                # Tkinter GUI (file upload + live transcription)
├── config.json          # User configuration
├── requirements.txt     # Python dependencies
├── security/            # Security audit documentation
├── overlay/             # Electron AI assistant overlay
│   ├── main.js          # Electron main process
│   ├── services/        # Ollama, OCR, clipboard services
│   └── renderer/        # Chat UI
└── README.md            # This file
```

## Configuration

Edit `config.json` to customize:

```json
{
  "whisper_model": "base",
  "language": "auto",
  "device": "auto",
  "window_opacity": 0.95,
  "always_on_top": true,
  "buffer_duration": 10
}
```

- `buffer_duration`: Seconds of audio to accumulate before each transcription pass (default: 10)

## Model Sizes

| Model  | Parameters | VRAM    | Speed | Accuracy |
|--------|-----------|---------|-------|----------|
| tiny   | 39M       | ~1GB    | Fast  | Low      |
| base   | 74M       | ~1GB    | Fast  | Good     |
| small  | 244M      | ~2GB    | Medium| Better   |
| medium | 769M      | ~5GB    | Slow  | Great    |
| large  | 1550M     | ~10GB   | Slower| Best     |

**Recommendation**: Start with `base` for good balance of speed and accuracy.

## Usage

### File Upload
1. Install dependencies: `pip install -r requirements.txt`
2. Run: `python main.py`
3. Click "Upload Audio/Video" and select a file
4. Wait for transcription to complete
5. Click "Save" to export to .txt file

### Live Transcription
1. Run: `python main.py`
2. Click "Refresh" next to Audio Device to detect loopback devices
3. Select your audio output device
4. Click "Start Live Transcription"
5. Read and accept the consent dialog
6. Transcription appears in real-time as audio plays
7. Click "Stop Live Transcription" when done
8. Click "Save" to export

## Security Notes

- **Zero audio persistence** — live audio is processed in real-time by Whisper and immediately discarded from memory. No audio files (`.wav`, `.mp3`, etc.) are ever created during live transcription
- **Consent required** — a consent dialog must be accepted before live transcription begins
- **No network access required** after initial model download
- **All processing is local** — no data sent to external servers
- **No administrator privileges** needed
- **Classification headers** — saved transcription files include "CONFIDENTIAL — INTERNAL USE ONLY" headers
- **Security audit** — see `security/` directory for full audit documentation

## License

This is a personal/internal tool. Whisper models are by OpenAI.
