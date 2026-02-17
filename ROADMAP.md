# Roadmap & Development Backlog

> Last updated: 2025-02-17
> Status: **Dormant** — parked for future development

---

## Recent Fix (2025-02-17): Audio Capture Blocking Reads

### Problem
Live transcription started but captured zero audio. The WASAPI loopback device opened successfully but PyAudio **callbacks produced 0 data** (0 callbacks fired).

### Root Cause
`pyaudiowpatch 0.2.12.8` callback mode is broken on Windows 11 with Realtek WASAPI loopback drivers. The stream opens without error, `start_stream()` succeeds, but the callback function is never invoked.

### Diagnosis
```
Callback mode:  0 callbacks in 5 seconds  → BROKEN
Blocking read:  40 reads in 5 seconds     → WORKS (RMS up to 0.10)
```

### Fix Applied
Changed `DeviceStream` class in `audio_capture.py` from callback mode to **blocking reads in a dedicated thread**. Each device now gets its own `_read_loop()` thread that calls `stream.read()` in a loop and queues audio for processing.

**Before:** `stream_callback=self._callback` → 0 data
**After:** `threading.Thread(target=self._read_loop)` → audio flows correctly

### Files Changed
- `audio_capture.py` — `DeviceStream` class rewritten (lines 21-97)

---

## Backlog

### P1: Auto Device Detection (Seamless Audio Capture)

**Goal:** Audio capture "just works" regardless of headphones, speakers, Bluetooth — like Cluely.

**Current behavior:** Only detects loopback devices at startup. If user connects headphones mid-meeting, that device's loopback won't be captured.

**Desired behavior:** Periodically re-scan for new WASAPI loopback devices during recording and automatically start capturing from new ones.

**Implementation notes:**
- Add a device monitor thread in `AudioCapture` that rescans every 5-10 seconds
- Compare current device list with active `DeviceStream` instances
- Start new `DeviceStream` for newly detected devices
- Stop `DeviceStream` for devices that disappeared
- Windows only exposes loopback for the **active** output device, so switching output creates/destroys loopback devices

**Complexity:** Medium — ~100 lines, mostly in `audio_capture.py`

---

### P2: Local AI Vision for Screenshots

**Goal:** Send screenshots to a local multimodal model for analysis (code help, meeting content understanding, etc.) without sending data to the cloud.

**How it works:**
- Ollama supports multimodal models that accept images
- Screenshot → base64 → send to Ollama `/api/chat` with image parameter
- Model analyzes the image and returns text response

**Recommended models:**
| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `moondream` | ~1.7GB | Fast | Good for simple tasks |
| `llava` | ~4.7GB | Medium | Good general vision |
| `llava:13b` | ~8GB | Slower | Best quality |

**API call example:**
```python
import requests, base64

with open("screenshot.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

response = requests.post("http://localhost:11434/api/chat", json={
    "model": "llava",
    "messages": [{
        "role": "user",
        "content": "What's on this screen?",
        "images": [img_b64]
    }]
})
```

**Integration points:**
- Overlay already has screenshot + OCR (`overlay/services/ocrService.js`)
- Add a new service `overlay/services/visionService.js`
- Add UI toggle: OCR-only vs AI Vision analysis
- Keep `moondream` as default (smallest, fastest)

**Complexity:** Medium — ~150 lines across overlay services + UI

---

### P3: Cluely Feature Parity Analysis

| Feature | Our App | Cluely | Gap |
|---------|---------|--------|-----|
| Live transcription (Whisper) | ✅ Local | ✅ Cloud | We're better (private) |
| Zero audio persistence | ✅ | ✅ | Parity |
| Invisible overlay | ✅ Electron | ✅ Electron | Parity |
| Screenshot + OCR | ✅ Tesseract | ✅ Gemini Vision | Ours is local-only |
| AI Vision (screenshots) | ❌ | ✅ Gemini | **P2 above** |
| Chat with AI | ✅ Ollama | ✅ GPT/Claude | Ours is local-only |
| Auto device detection | ❌ | ✅ | **P1 above** |
| Clipboard monitoring | ✅ | ❌ | We have it, they don't |
| Global hotkeys | ✅ | ✅ | Parity |
| Solution/debug workflow | ❌ | ✅ | Nice-to-have |
| Queue screenshots (up to 5) | ❌ | ✅ | Nice-to-have |

**Key advantages we have over Cluely:**
- 100% local / zero network (Cluely sends to cloud)
- Zero audio persistence architecture with security audit
- Clipboard monitoring
- No API keys or subscriptions needed

**Key gaps:**
- P1: Auto device detection (seamless audio)
- P2: AI vision for screenshots (local multimodal)

---

### P4: Nice-to-Have Improvements

- [ ] Screenshot queue (capture multiple, analyze together)
- [ ] Debug workflow (take follow-up screenshots for iterative problem solving)
- [ ] Language auto-detection (currently hardcoded to `"en"` in config)
- [ ] Transcript search within UI
- [ ] Export to markdown format
- [ ] Overlay: show live transcription text in overlay window
- [ ] Package as single installer (Electron + Python bundled)

---

## Architecture Reference

```
System Audio (WASAPI loopback — blocking reads)
  ↓
DeviceStream._read_loop() — per-device thread, 100ms reads
  ↓
audio_queue — tagged with (audio_float32, native_rate)
  ↓
AudioCapture._process_audio() — resample to 16kHz, accumulate 10s
  ↓
transcription_queue — resampled audio chunks
  ↓
AudioCapture._transcription_worker() — calls callback, discards audio
  ↓
Transcriber.transcribe_audio() — Silero VAD + Whisper (greedy, beam=1)
  ↓
Text segments → UI + JSON file
  ↓
Audio numpy arrays garbage collected (zero persistence)
```

## Diagnostic Scripts

- `test_audio_quick.py` — Test all loopback devices for 3 seconds, show RMS levels
- `diagnose_pipeline.py` — End-to-end test: device → capture → resample → transcribe
- `diagnose5.py` — Plays system beep and captures from each device
