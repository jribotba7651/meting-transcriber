# Meeting Transcriber

Real-time meeting transcription application for Windows using OpenAI Whisper.

## Features

- **Real-time audio capture** using WASAPI loopback (captures system audio output)
- **Local transcription** using Faster-Whisper (no API keys required)
- **Multiple model sizes** (tiny, base, small, medium, large)
- **GPU acceleration** support (CUDA) with automatic CPU fallback
- **Always-on-top window** for easy monitoring during meetings
- **Timestamped transcription** with export to text file
- **Configurable buffer duration** for optimal performance
- **No administrator privileges required**

## System Requirements

- Windows 10/11
- Python 3.11 or later
- 4GB RAM minimum (8GB+ recommended for larger models)
- CUDA-compatible GPU (optional, for faster transcription)

## Architecture

```
meeting-transcriber/
├── main.py              # Application entry point
├── audio_capture.py     # WASAPI loopback audio capture
├── transcriber.py       # Whisper-based transcription
├── ui.py                # Tkinter GUI
├── config.json          # User configuration
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── build_instructions.md # Instructions to create .exe
```

## Configuration

Edit `config.json` to customize:

```json
{
  "whisper_model": "base",      // tiny, base, small, medium, large
  "language": "auto",            // auto, en, es, fr, de, etc.
  "device": "auto",              // auto, cpu, cuda
  "buffer_duration": 30,         // seconds of audio to buffer before transcribing
  "window_opacity": 0.95,        // 0.0 (transparent) to 1.0 (opaque)
  "always_on_top": true          // keep window on top
}
```

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

### Running from Python

1. Install dependencies (see Installation section below)
2. Download Whisper models (see Model Download section)
3. Run: `python main.py`

### Using the Application

1. **Select Audio Device**: Choose your system's loopback device (usually your speakers/headphones)
2. **Choose Model**: Select Whisper model size based on your needs
3. **Set Language**: Choose language or leave on "auto" for detection
4. **Start Recording**: Click "Start Recording" button
5. **Monitor Transcription**: Text appears in real-time with timestamps
6. **Save**: Click "Save" to export transcription to .txt file

## Installation Instructions

⚠️ **DO NOT run these commands yet!** Check with your security team first.

### Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `faster-whisper` - Optimized Whisper implementation
- `PyAudioWPatch` - WASAPI loopback audio capture for Windows
- `numpy` - Array processing
- `pyinstaller` - For creating standalone .exe

### Step 2: Install CUDA (Optional, for GPU acceleration)

If you have an NVIDIA GPU and want faster transcription:

1. Install [CUDA Toolkit 11.8](https://developer.nvidia.com/cuda-11-8-0-download-archive)
2. Install cuDNN 8.x for CUDA 11.x

### Step 3: Download Whisper Models

Models are automatically downloaded on first use, but you can pre-download:

```python
from faster_whisper import WhisperModel

# This will download the model to cache
model = WhisperModel("base", device="cpu", compute_type="int8")
```

Default cache location:
- Windows: `C:\Users\<username>\.cache\huggingface\hub`

## Building Standalone Executable

See `build_instructions.md` for detailed steps to create a portable .exe file.

## Troubleshooting

### No loopback devices found

**Solution**: Windows audio devices must support loopback. Try:
1. Right-click speaker icon → Sounds → Recording tab
2. Right-click empty space → Show Disabled Devices
3. Enable "Stereo Mix" if available

### Audio not capturing

**Possible causes**:
- Application doesn't have permission to access audio
- Wrong device selected
- Audio driver issues

**Solution**: Restart application, try different device, update audio drivers

### Transcription is slow

**Solutions**:
- Use smaller model (tiny or base)
- Increase buffer_duration to transcribe less frequently
- Use GPU if available
- Close other applications

### Model download fails

**Solution**: Pre-download models manually and place in cache directory.

## Security Notes

- **No network access required** after initial model download
- **All processing is local** - no data sent to external servers
- **No administrator privileges** needed
- **Safe for corporate environments** - uses standard Windows audio APIs

## License

This is a personal/internal tool. Whisper models are by OpenAI.

## Support

For issues, check logs in console output or contact the developer.
