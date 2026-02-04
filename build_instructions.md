# Build Instructions - Creating Portable Executable

This guide explains how to manually create a standalone Windows executable (.exe) for the Meeting Transcriber.

⚠️ **IMPORTANT**: These instructions are for you to follow manually. Do NOT execute automatically.

## Prerequisites

1. All Python dependencies installed (`pip install -r requirements.txt`)
2. Whisper models downloaded and cached
3. PyInstaller installed (`pip install pyinstaller`)

## Step-by-Step Build Process

### Step 1: Pre-download Whisper Models

Before building, ensure all models you want to include are cached:

```python
# Run this Python code to download models
from faster_whisper import WhisperModel

models = ["tiny", "base", "small"]  # Choose which models to include

for model_name in models:
    print(f"Downloading {model_name}...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    print(f"{model_name} downloaded!")
```

Models will be cached in:
```
C:\Users\<username>\.cache\huggingface\hub
```

### Step 2: Create PyInstaller Spec File

Create a file named `meeting-transcriber.spec` in the project directory:

```python
# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect faster_whisper data files
datas = collect_data_files('faster_whisper')

# Add config.json
datas += [('config.json', '.')]

# Collect all whisper-related modules
hiddenimports = collect_submodules('faster_whisper')
hiddenimports += collect_submodules('ctranslate2')
hiddenimports += ['numpy', 'tkinter', 'pyaudiowpatch']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MeetingTranscriber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Set to False to hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MeetingTranscriber',
)
```

### Step 3: Build the Executable

Open Command Prompt in the project directory and run:

```bash
pyinstaller meeting-transcriber.spec
```

This will:
1. Analyze dependencies
2. Collect all required files
3. Create the executable
4. Place output in `dist/MeetingTranscriber/`

**Build time**: 2-5 minutes depending on your system.

### Step 4: Copy Whisper Model Cache (Optional)

To make the executable truly portable with pre-installed models:

1. Create `models` folder in `dist/MeetingTranscriber/`
2. Copy cached models from:
   ```
   C:\Users\<username>\.cache\huggingface\hub
   ```
   to:
   ```
   dist/MeetingTranscriber/models/
   ```

3. Modify `config.json` in the dist folder to point to local models (advanced)

### Step 5: Test the Executable

1. Navigate to `dist/MeetingTranscriber/`
2. Double-click `MeetingTranscriber.exe`
3. Test all functionality:
   - Device detection
   - Recording
   - Transcription
   - Saving files

### Step 6: Package for Distribution

Create a distributable package:

1. Compress the entire `dist/MeetingTranscriber/` folder to ZIP
2. Name it: `MeetingTranscriber_v1.0_portable.zip`

Contents should include:
```
MeetingTranscriber/
├── MeetingTranscriber.exe
├── config.json
├── models/ (if included)
├── _internal/ (PyInstaller dependencies)
└── ... (other DLLs and dependencies)
```

## Build Options

### Console vs Windowed

In the spec file, change:
```python
console=True   # Shows console window (useful for debugging)
console=False  # Hides console window (cleaner for end users)
```

### Single File vs Folder

For a single .exe file (slower startup):
```bash
pyinstaller --onefile main.py
```

For a folder distribution (faster startup, recommended):
```bash
pyinstaller meeting-transcriber.spec
```

### Adding an Icon

1. Create or download a `.ico` file
2. In spec file, set:
   ```python
   icon='path/to/icon.ico'
   ```

## Troubleshooting Build Issues

### Error: "Module not found"

**Solution**: Add to `hiddenimports` in spec file:
```python
hiddenimports += ['missing_module_name']
```

### Error: "DLL not found"

**Solution**: Ensure all system dependencies are installed (Visual C++ Redistributable)

### Executable won't start

**Solution**:
1. Build with `console=True` to see error messages
2. Check dependencies are correctly packaged
3. Test on a clean Windows machine

### Large file size

**Solutions**:
- Use `--exclude-module` to remove unused packages
- Don't include all Whisper models
- Use UPX compression (already enabled)

## Size Estimates

Approximate sizes of built executable:

| Configuration | Size |
|--------------|------|
| Base (no models) | ~150-250 MB |
| + Base model | ~250-350 MB |
| + Small model | ~500-600 MB |
| + Medium model | ~1.5-2 GB |

## Distribution Checklist

Before distributing:

- [ ] Tested on clean Windows 10/11 machine
- [ ] All features working (record, transcribe, save)
- [ ] Config.json has sensible defaults
- [ ] README.txt included with instructions
- [ ] License information included
- [ ] Version number documented
- [ ] Compressed to ZIP for easy distribution

## Advanced: Custom Model Paths

To use custom model paths instead of default cache:

1. Modify `transcriber.py`:
   ```python
   self.model = WhisperModel(
       self.model_size,
       device=self.device,
       compute_type=compute_type,
       download_root="./models"  # Use local models folder
   )
   ```

2. Copy models to `dist/MeetingTranscriber/models/`

## Security Considerations

✅ **Safe practices**:
- Building locally on your own machine
- Using official PyPI packages
- No code obfuscation needed
- Include source code for transparency

❌ **Avoid**:
- Running build scripts from untrusted sources
- Including credentials or API keys
- Auto-updating from remote servers

## Alternative: Python Distribution

Instead of .exe, you can distribute as Python app:

1. Create `install.bat`:
   ```batch
   @echo off
   pip install -r requirements.txt
   echo Installation complete!
   pause
   ```

2. Create `run.bat`:
   ```batch
   @echo off
   python main.py
   pause
   ```

3. Distribute as ZIP with Python code + batch files

Users need Python installed, but no build step required.

## Support

If build fails, provide:
1. Python version (`python --version`)
2. PyInstaller version (`pyinstaller --version`)
3. Full error message
4. Operating system version
