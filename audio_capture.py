"""
Audio Capture Module — Stream-Only Processing
Captures WASAPI loopback audio for real-time transcription.
Audio is NEVER saved to disk. Audio buffers are discarded immediately after transcription.
No .wav, .mp3, or temp files are created at any time.
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
    def __init__(self, sample_rate=16000, chunk_size=1024, accumulate_seconds=10):
        """
        Initialize audio capture with zero-persistence pipeline.

        Args:
            sample_rate: Target sample rate in Hz (16kHz for Whisper)
            chunk_size: Audio chunk size for PyAudio stream
            accumulate_seconds: Seconds of audio to accumulate before sending to transcription
        """
        self.target_sample_rate = sample_rate
        self.native_sample_rate = None
        self.channels = None
        self.chunk_size = chunk_size
        self.accumulate_seconds = accumulate_seconds

        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.is_recording = False

        self.audio_queue = queue.Queue()
        self.record_thread = None
        self.transcribe_callback = None

    def get_loopback_devices(self):
        """Get list of available loopback devices"""
        devices = []
        try:
            wasapi_info = self.audio.get_host_api_info_by_type(pyaudio.paWASAPI)

            for i in range(self.audio.get_device_count()):
                device_info = self.audio.get_device_info_by_index(i)

                if (device_info.get('hostApi') == wasapi_info.get('index') and
                    device_info.get('maxInputChannels') > 0):

                    name = device_info.get('name', '')
                    is_loopback = device_info.get('isLoopbackDevice', False)

                    if is_loopback or 'loopback' in name.lower():
                        devices.append({
                            'index': i,
                            'name': name,
                            'channels': device_info.get('maxInputChannels'),
                            'isLoopback': is_loopback
                        })

            try:
                default_loopback = self.audio.get_default_wasapi_loopback()
                default_idx = default_loopback['index']
                if not any(d['index'] == default_idx for d in devices):
                    devices.insert(0, {
                        'index': default_idx,
                        'name': default_loopback.get('name', 'Default Loopback'),
                        'channels': default_loopback.get('maxInputChannels', 2),
                        'isLoopback': True
                    })
            except Exception as e:
                logger.debug(f"Could not get default WASAPI loopback: {e}")

            if not devices:
                try:
                    default_speakers = self.audio.get_default_output_device_info()
                    loopback = self.audio.get_device_info_by_index(
                        default_speakers["index"]
                    )
                    if loopback.get('isLoopbackDevice'):
                        devices.append({
                            'index': loopback['index'],
                            'name': loopback.get('name'),
                            'channels': loopback.get('maxInputChannels'),
                            'isLoopback': True
                        })
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error getting loopback devices: {e}")

        logger.info(f"Found {len(devices)} loopback device(s): {[d['name'] for d in devices]}")
        return devices

    def start_recording(self, device_index=None, transcribe_callback=None):
        """
        Start capturing audio for real-time transcription.

        Args:
            device_index: WASAPI loopback device index (None for default)
            transcribe_callback: Function(numpy_float32_16khz) called with each audio chunk.
                                 Audio is discarded immediately after this callback returns.
        """
        if self.is_recording:
            logger.warning("Already recording")
            return False

        self.transcribe_callback = transcribe_callback

        try:
            if device_index is None:
                try:
                    device_info = self.audio.get_default_wasapi_loopback()
                    device_index = device_info['index']
                except Exception as e:
                    logger.error(f"Could not find default loopback device: {e}")
                    return False
            else:
                device_info = self.audio.get_device_info_by_index(device_index)

            self.native_sample_rate = int(device_info.get('defaultSampleRate', 48000))
            max_channels = device_info.get('maxInputChannels', 2)
            self.channels = max_channels if max_channels > 0 else 2

            logger.info(f"Capture device: {device_info.get('name')}")
            logger.info(f"Native sample rate: {self.native_sample_rate} Hz → target: {self.target_sample_rate} Hz")

            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.native_sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback
            )

            self.is_recording = True
            self.stream.start_stream()

            self.record_thread = threading.Thread(target=self._process_audio, daemon=True)
            self.record_thread.start()

            logger.info("Live transcription capture started (zero audio persistence)")
            return True

        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio stream callback — receives raw audio chunks"""
        if status:
            logger.warning(f"Audio callback status: {status}")

        audio_data = np.frombuffer(in_data, dtype=np.int16)

        # Convert stereo to mono
        if self.channels == 2:
            audio_data = audio_data.reshape(-1, 2).mean(axis=1).astype(np.int16)

        self.audio_queue.put(audio_data)
        return (in_data, pyaudio.paContinue)

    def _process_audio(self):
        """
        Processing thread — accumulates audio, sends to transcription, discards immediately.
        No audio is ever written to disk. No persistent buffer is maintained.
        """
        logger.info("Audio processing thread started (stream-only, zero persistence)")

        # Temporary accumulator — discarded after each transcription call
        accumulator = []
        accumulated_samples = 0
        samples_threshold = self.native_sample_rate * self.accumulate_seconds

        while self.is_recording:
            try:
                audio_chunk = self.audio_queue.get(timeout=1)

                accumulator.append(audio_chunk)
                accumulated_samples += len(audio_chunk)

                # When we have enough audio, process and discard
                if accumulated_samples >= samples_threshold:
                    self._transcribe_and_discard(accumulator)
                    # Discard all audio data immediately
                    accumulator = []
                    accumulated_samples = 0

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in audio processing: {e}")

        # Process any remaining audio before stopping
        if accumulator and self.transcribe_callback:
            self._transcribe_and_discard(accumulator)

        logger.info("Audio processing thread stopped")

    def _transcribe_and_discard(self, accumulator):
        """
        Resample accumulated audio, send to transcription callback, then discard.
        After this method returns, no reference to the audio data remains.
        """
        if not self.transcribe_callback:
            return

        try:
            # Concatenate accumulated chunks
            audio_array = np.concatenate(accumulator).astype(np.float32) / 32768.0

            # Resample to 16kHz if needed
            if self.native_sample_rate != self.target_sample_rate:
                num_samples = int(len(audio_array) * self.target_sample_rate / self.native_sample_rate)
                audio_array = signal.resample(audio_array, num_samples)

            # Send to transcription — this is the only output
            self.transcribe_callback(audio_array)

        except Exception as e:
            logger.error(f"Error in transcribe-and-discard: {e}")

        # audio_array goes out of scope here — garbage collected, zero persistence

    def stop_recording(self):
        """Stop audio capture"""
        if not self.is_recording:
            return

        self.is_recording = False

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

        if self.record_thread:
            self.record_thread.join(timeout=3)
            self.record_thread = None

        # Clear any remaining audio in queue — discard, don't process
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        self.transcribe_callback = None
        logger.info("Live transcription capture stopped")

    def cleanup(self):
        """Cleanup audio resources"""
        self.stop_recording()
        if self.audio:
            self.audio.terminate()
