"""
Audio Capture Module
Handles WASAPI loopback audio capture using PyAudioWPatch
"""

import pyaudiowpatch as pyaudio
import numpy as np
import threading
import queue
import logging
from scipy import signal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioCapture:
    def __init__(self, sample_rate=16000, chunk_size=1024, buffer_duration=30):
        """
        Initialize audio capture

        Args:
            sample_rate: Target sample rate in Hz (16kHz is optimal for Whisper)
            chunk_size: Audio chunk size
            buffer_duration: Duration of audio buffer in seconds
        """
        self.target_sample_rate = sample_rate  # Rate for output (16kHz)
        self.native_sample_rate = None  # Rate of capture device (detected)
        self.channels = None  # Number of channels (detected)
        self.chunk_size = chunk_size
        self.buffer_duration = buffer_duration

        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.is_recording = False

        self.audio_queue = queue.Queue()
        self.buffer = []
        self.buffer_max_size = None  # Will be set when native rate is detected

        self.record_thread = None

    def get_loopback_devices(self):
        """Get list of available loopback devices"""
        devices = []
        try:
            # Get default WASAPI info
            wasapi_info = self.audio.get_host_api_info_by_type(pyaudio.paWASAPI)

            # Iterate through devices
            for i in range(self.audio.get_device_count()):
                device_info = self.audio.get_device_info_by_index(i)

                # Check if it's a loopback device
                if (device_info.get('hostApi') == wasapi_info.get('index') and
                    device_info.get('maxInputChannels') > 0 and
                    'loopback' in device_info.get('name', '').lower()):

                    devices.append({
                        'index': i,
                        'name': device_info.get('name'),
                        'channels': device_info.get('maxInputChannels')
                    })

            # If no loopback devices found, try to get default output as loopback
            if not devices:
                default_speakers = self.audio.get_default_output_device_info()
                loopback = self.audio.get_device_info_by_index(
                    default_speakers["index"]
                )

                if loopback.get('isLoopbackDevice'):
                    devices.append({
                        'index': loopback['index'],
                        'name': loopback.get('name'),
                        'channels': loopback.get('maxInputChannels')
                    })

        except Exception as e:
            logger.error(f"Error getting loopback devices: {e}")

        return devices

    def start_recording(self, device_index=None):
        """Start recording audio"""
        if self.is_recording:
            logger.warning("Already recording")
            return False

        try:
            # Get WASAPI loopback device
            if device_index is None:
                print("[DEBUG AUDIO] No device specified, getting default WASAPI loopback...")
                try:
                    # Use PyAudioWPatch's built-in method to get default loopback
                    device_info = self.audio.get_default_wasapi_loopback()
                    device_index = device_info['index']
                    print(f"[DEBUG AUDIO] Got default loopback: {device_info['name']}")
                    print(f"[DEBUG AUDIO] Device index: {device_index}")

                except Exception as e:
                    logger.error(f"Could not find default loopback device: {e}")
                    print(f"[DEBUG AUDIO] ERROR finding loopback: {e}")
                    return False
            else:
                print(f"[DEBUG AUDIO] Using specified device index: {device_index}")
                device_info = self.audio.get_device_info_by_index(device_index)

            # Detect native sample rate and channels
            self.native_sample_rate = int(device_info.get('defaultSampleRate', 48000))
            max_channels = device_info.get('maxInputChannels', 2)

            # For loopback, use the native channel count (usually stereo)
            self.channels = max_channels if max_channels > 0 else 2

            logger.info(f"Device native sample rate: {self.native_sample_rate} Hz")
            logger.info(f"Will resample to target rate: {self.target_sample_rate} Hz")
            print(f"[DEBUG AUDIO] Device info:")
            print(f"  - Name: {device_info.get('name')}")
            print(f"  - Index: {device_index}")
            print(f"  - Sample rate: {self.native_sample_rate} Hz")
            print(f"  - Max input channels: {max_channels}")
            print(f"  - Is loopback: {device_info.get('isLoopbackDevice', False)}")
            print(f"  - Host API: {device_info.get('hostApi')}")

            # Set buffer max size based on native rate and channels
            # Account for stereo when calculating buffer size
            self.buffer_max_size = int(self.native_sample_rate * self.buffer_duration)

            print(f"[DEBUG AUDIO] Opening stream with {self.channels} channel(s)")

            # Open stream with native parameters for WASAPI loopback
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.native_sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback
            )

            print(f"[DEBUG AUDIO] Stream opened successfully")

            self.is_recording = True
            self.stream.start_stream()

            print(f"[DEBUG AUDIO] Stream started, is_active: {self.stream.is_active()}")

            # Start processing thread
            self.record_thread = threading.Thread(target=self._process_audio, daemon=True)
            self.record_thread.start()

            logger.info(f"Started recording from device {device_index}")
            return True

        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            print(f"[DEBUG AUDIO] EXCEPTION in start_recording: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream"""
        print(f"[DEBUG AUDIO] Callback called: frame_count={frame_count}, status={status}")

        if status:
            logger.warning(f"Audio callback status: {status}")
            print(f"[DEBUG AUDIO] WARNING: Status flag present: {status}")

        # Add audio data to queue
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        print(f"[DEBUG AUDIO] Received {len(audio_data)} samples, max={np.max(np.abs(audio_data))}")

        # Convert stereo to mono if needed
        if self.channels == 2:
            # Reshape to (frames, channels) and average across channels
            audio_data = audio_data.reshape(-1, 2)
            audio_data = audio_data.mean(axis=1).astype(np.int16)
            print(f"[DEBUG AUDIO] Converted stereo to mono: {len(audio_data)} samples")

        self.audio_queue.put(audio_data)

        return (in_data, pyaudio.paContinue)

    def _process_audio(self):
        """Process audio from queue and maintain buffer"""
        print("[DEBUG AUDIO] Processing thread started")
        chunk_count = 0

        while self.is_recording:
            try:
                # Get audio chunk from queue
                audio_chunk = self.audio_queue.get(timeout=1)
                chunk_count += 1

                # Add to buffer
                self.buffer.extend(audio_chunk)

                if chunk_count % 10 == 0:  # Print every 10 chunks to avoid spam
                    print(f"[DEBUG AUDIO] Processed {chunk_count} chunks, buffer size: {len(self.buffer)} samples")

                # Trim buffer if too large
                if len(self.buffer) > self.buffer_max_size:
                    self.buffer = self.buffer[-self.buffer_max_size:]
                    print(f"[DEBUG AUDIO] Buffer trimmed to {len(self.buffer)} samples")

            except queue.Empty:
                if chunk_count == 0:
                    print("[DEBUG AUDIO] No audio chunks received yet (queue empty)")
                continue
            except Exception as e:
                logger.error(f"Error processing audio: {e}")
                print(f"[DEBUG AUDIO] ERROR: {e}")

    def get_audio_buffer(self):
        """Get current audio buffer as numpy array (resampled to target rate)"""
        print(f"[DEBUG AUDIO] get_audio_buffer called, buffer length: {len(self.buffer) if self.buffer else 0}")

        if not self.buffer:
            print("[DEBUG AUDIO] Buffer is empty, returning None")
            return None

        # Convert to float32 and normalize
        audio_array = np.array(self.buffer, dtype=np.float32)
        audio_array = audio_array / 32768.0  # Normalize int16 to float32

        print(f"[DEBUG AUDIO] Buffer before resampling: {len(audio_array)} samples")

        # Resample if native rate differs from target rate
        if self.native_sample_rate and self.native_sample_rate != self.target_sample_rate:
            # Calculate number of samples after resampling
            num_samples = int(len(audio_array) * self.target_sample_rate / self.native_sample_rate)

            # Resample using scipy
            audio_array = signal.resample(audio_array, num_samples)

            print(f"[DEBUG AUDIO] Resampled from {self.native_sample_rate} Hz to {self.target_sample_rate} Hz: {len(audio_array)} samples")
            logger.debug(f"Resampled from {self.native_sample_rate} Hz to {self.target_sample_rate} Hz")

        return audio_array

    def clear_buffer(self):
        """Clear the audio buffer"""
        self.buffer = []

    def stop_recording(self):
        """Stop recording audio"""
        if not self.is_recording:
            return

        self.is_recording = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.record_thread:
            self.record_thread.join(timeout=2)

        logger.info("Stopped recording")

    def cleanup(self):
        """Cleanup audio resources"""
        self.stop_recording()
        self.audio.terminate()


if __name__ == "__main__":
    # Test the audio capture
    print("Testing Audio Capture...")

    capture = AudioCapture()

    # List devices
    devices = capture.get_loopback_devices()
    print(f"\nFound {len(devices)} loopback device(s):")
    for dev in devices:
        print(f"  [{dev['index']}] {dev['name']} ({dev['channels']} channels)")

    if devices:
        print(f"\nStarting 5-second test recording...")
        capture.start_recording(devices[0]['index'])

        import time
        time.sleep(5)

        audio = capture.get_audio_buffer()
        print(f"Captured {len(audio) if audio is not None else 0} samples")

        capture.stop_recording()

    capture.cleanup()
    print("Test complete!")
