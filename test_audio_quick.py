"""Test all loopback devices for 3 seconds each"""
import pyaudiowpatch as pyaudio
import numpy as np
import time

pa = pyaudio.PyAudio()
wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)

# Find ALL loopback devices
devices = []
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info.get('hostApi') == wasapi.get('index') and info.get('maxInputChannels') > 0:
        if info.get('isLoopbackDevice') or 'loopback' in info.get('name', '').lower():
            devices.append(info)

print(f"Found {len(devices)} loopback device(s)")

# Also try the default WASAPI loopback
try:
    default_lb = pa.get_default_wasapi_loopback()
    print(f"\nDefault WASAPI loopback: {default_lb['name']}")
except Exception as e:
    print(f"\nNo default WASAPI loopback: {e}")

# Test each device
for dev in devices:
    name = dev['name']
    rate = int(dev['defaultSampleRate'])
    ch = dev['maxInputChannels']
    idx = dev['index']
    
    print(f"\n--- Testing: {name} (idx={idx}, {rate}Hz, {ch}ch) ---")
    
    chunks = []
    
    def make_cb(chunk_list):
        def cb(data, fc, ti, st):
            chunk_list.append(np.frombuffer(data, dtype=np.int16))
            return (data, pyaudio.paContinue)
        return cb
    
    try:
        s = pa.open(
            format=pyaudio.paInt16,
            channels=ch,
            rate=rate,
            input=True,
            input_device_index=idx,
            frames_per_buffer=1024,
            stream_callback=make_cb(chunks)
        )
        s.start_stream()
        time.sleep(3)
        s.stop_stream()
        s.close()
        
        if chunks:
            all_audio = np.concatenate(chunks).astype(np.float32) / 32768.0
            if ch >= 2:
                all_audio = all_audio.reshape(-1, ch).mean(axis=1)
            rms = np.sqrt(np.mean(all_audio ** 2))
            mx = np.max(np.abs(all_audio))
            print(f"  Callbacks: {len(chunks)}")
            print(f"  Samples: {len(all_audio)} ({len(all_audio)/rate:.1f}s)")
            print(f"  RMS: {rms:.8f}  Max: {mx:.8f}")
            if rms < 1e-6:
                print(f"  Status: SILENT (no system audio on this device)")
            elif rms < 1e-4:
                print(f"  Status: VERY QUIET (old threshold would skip!)")
            else:
                print(f"  Status: ACTIVE")
        else:
            print(f"  Callbacks: 0 - NO DATA!")
            print(f"  Status: DEVICE NOT PRODUCING AUDIO")
    except Exception as e:
        print(f"  ERROR: {e}")

pa.terminate()
print(f"\nDone!")
