"""
End-to-end diagnostic for the transcription pipeline.
Tests each stage: device detection -> audio capture -> resampling -> transcription
"""
import sys
import time
import numpy as np
import pyaudiowpatch as pyaudio
import threading
import queue

print("=" * 60)
print("Meeting Transcriber - Pipeline Diagnostic")
print("=" * 60)

# Stage 1: Device detection
print("\n[STAGE 1] Detecting loopback devices...")
pa = pyaudio.PyAudio()
wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
devices = []
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if (info.get('hostApi') == wasapi_info.get('index') and
        info.get('maxInputChannels') > 0):
        name = info.get('name', '')
        if info.get('isLoopbackDevice', False) or 'loopback' in name.lower():
            devices.append(info)
            print(f"  [{i}] {name} ({int(info['defaultSampleRate'])} Hz, {info['maxInputChannels']}ch)")

if not devices:
    print("  ERROR: No loopback devices found!")
    sys.exit(1)
print(f"  Found {len(devices)} device(s)")

# Stage 2: Capture 5 seconds of audio from first device
print(f"\n[STAGE 2] Capturing 5 seconds from: {devices[0]['name']}")
print("  >>> PLAY SOME AUDIO NOW (YouTube, music, anything) <<<")

audio_chunks = []
dev = devices[0]
dev_idx = dev['index']
rate = int(dev['defaultSampleRate'])
channels = dev['maxInputChannels']

def callback(in_data, frame_count, time_info, status):
    audio_chunks.append(np.frombuffer(in_data, dtype=np.int16))
    return (in_data, pyaudio.paContinue)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=channels,
    rate=rate,
    input=True,
    input_device_index=dev_idx,
    frames_per_buffer=1024,
    stream_callback=callback
)
stream.start_stream()

for i in range(5):
    time.sleep(1)
    total_samples = sum(len(c) for c in audio_chunks)
    # Compute RMS on latest chunk
    if audio_chunks:
        latest = audio_chunks[-1].astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(latest ** 2))
    else:
        rms = 0
    print(f"  {i+1}s: {len(audio_chunks)} callbacks, {total_samples} samples, RMS={rms:.6f}")

stream.stop_stream()
stream.close()

if not audio_chunks:
    print("  ERROR: No audio captured!")
    pa.terminate()
    sys.exit(1)

# Stage 3: Process audio
print(f"\n[STAGE 3] Processing captured audio...")
raw = np.concatenate(audio_chunks)
print(f"  Raw samples: {len(raw)} ({len(raw)/rate:.1f}s at {rate} Hz)")

# Convert to float32 mono
audio_float = raw.astype(np.float32) / 32768.0
if channels >= 2:
    audio_float = audio_float.reshape(-1, channels).mean(axis=1)
print(f"  Mono float32: {len(audio_float)} samples")

# Overall RMS
rms = np.sqrt(np.mean(audio_float ** 2))
print(f"  RMS energy: {rms:.6f}")
print(f"  Silence threshold (1e-4): {'WOULD SKIP (silent)' if rms < 1e-4 else 'WOULD PROCESS (has audio)'}")
print(f"  Max amplitude: {np.max(np.abs(audio_float)):.6f}")

# Stage 4: Resample to 16kHz
print(f"\n[STAGE 4] Resampling {rate} Hz -> 16000 Hz...")
from scipy import signal

target_rate = 16000
ratio = rate / target_rate
int_ratio = round(ratio)
print(f"  Ratio: {ratio:.4f}, int_ratio: {int_ratio}")

try:
    if int_ratio > 1 and abs(ratio - int_ratio) < 0.01 and len(audio_float) > 100:
        resampled = signal.decimate(audio_float, int_ratio, zero_phase=True)
        print(f"  Used signal.decimate (fast integer path)")
    else:
        resampled = signal.resample_poly(audio_float, target_rate, rate)
        print(f"  Used signal.resample_poly (non-integer path)")
    print(f"  Resampled: {len(resampled)} samples ({len(resampled)/16000:.1f}s at 16kHz)")
    rms_resampled = np.sqrt(np.mean(resampled ** 2))
    print(f"  Resampled RMS: {rms_resampled:.6f}")
except Exception as e:
    print(f"  ERROR during resampling: {e}")
    import traceback; traceback.print_exc()
    pa.terminate()
    sys.exit(1)

# Stage 5: Test faster-whisper transcription
print(f"\n[STAGE 5] Testing faster-whisper transcription...")
try:
    from faster_whisper import WhisperModel
    print(f"  Loading model 'base' on cpu (int8)...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    print(f"  Model loaded. Transcribing {len(resampled)/16000:.1f}s of audio...")

    segments_gen, info = model.transcribe(
        resampled,
        language=None,  # auto-detect
        vad_filter=True,
        no_speech_threshold=0.6,
    )

    segments = list(segments_gen)
    detected_lang = info.language
    print(f"  Detected language: {detected_lang}")
    print(f"  Segments: {len(segments)}")

    if segments:
        for seg in segments:
            print(f"    [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text.strip()}")
    else:
        print(f"  WARNING: No segments produced!")
        print(f"  This could mean:")
        print(f"    - Audio was too quiet (RMS={rms_resampled:.6f})")
        print(f"    - no_speech_threshold filtered everything out")
        print(f"    - No intelligible speech in the audio")

        # Try again without no_speech_threshold
        print(f"\n  Retrying WITHOUT no_speech_threshold filter...")
        segments_gen2, info2 = model.transcribe(
            resampled,
            language=None,
            vad_filter=False,
        )
        segments2 = list(segments_gen2)
        print(f"  Segments (no filter): {len(segments2)}")
        for seg in segments2:
            print(f"    [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text.strip()}")

except Exception as e:
    print(f"  ERROR: {e}")
    import traceback; traceback.print_exc()

pa.terminate()
print(f"\n{'=' * 60}")
print("Diagnostic complete!")
print("=" * 60)
