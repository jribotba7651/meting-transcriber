"""
Audio Capture Module — Multi-Device Stream-Only Processing
Captures WASAPI loopback audio from ALL output devices simultaneously for real-time transcription.
This ensures audio is captured regardless of which device (headphones, speakers, monitor) is active.
Audio is NEVER saved to disk. Audio buffers are discarded immediately after transcription.
No .wav, .mp3, or temp files are created at any time.
"""

import pyaudiowpatch as pyaudio
import numpy as np
import threading
import queue
import time
import logging
from scipy import signal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeviceStream:
    """Manages a single loopback device stream with blocking reads in a dedicated thread.

    Uses blocking reads instead of callbacks because pyaudiowpatch callbacks
    produce 0 data on some WASAPI loopback configurations (confirmed on
    Windows 11 with Realtek drivers).
    """

    def __init__(self, device_index, device_name, channels, native_rate, audio_queue, pa_instance, chunk_size):
        self.device_index = device_index
        self.device_name = device_name
        self.channels = channels
        self.native_rate = native_rate
        self.audio_queue = audio_queue
        self.pa = pa_instance
        self.chunk_size = chunk_size
        self.stream = None
        self._running = False
        self._read_thread = None

    def start(self):
        """Open the PyAudio stream and start a blocking-read thread."""
        try:
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.native_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.chunk_size,
            )
            self.stream.start_stream()
            self._running = True
            self._read_thread = threading.Thread(
                target=self._read_loop, daemon=True,
                name=f"audio-read-{self.device_name}"
            )
            self._read_thread.start()
            logger.info(f"  ✓ Opened: {self.device_name} ({self.native_rate} Hz, {self.channels}ch)")
            return True
        except Exception as e:
            logger.warning(f"  ✗ Could not open {self.device_name}: {e}")
            return False

    def _read_loop(self):
        """Blocking read loop — reads audio and queues it for processing."""
        frames_per_read = self.native_rate // 10  # read ~100ms at a time
        while self._running and self.stream and self.stream.is_active():
            try:
                in_data = self.stream.read(frames_per_read, exception_on_overflow=False)
                audio_data = np.frombuffer(in_data, dtype=np.int16)
                audio_float = audio_data.astype(np.float32) / 32768.0

                if self.channels >= 2:
                    audio_float = audio_float.reshape(-1, self.channels).mean(axis=1)

                self.audio_queue.put((audio_float, self.native_rate))
            except OSError:
                # Stream closed or device disconnected
                break
            except Exception as e:
                if self._running:
                    logger.warning(f"Read error [{self.device_name}]: {e}")

    def stop(self):
        """Stop the read thread and close the stream."""
        self._running = False
        if self._read_thread:
            self._read_thread.join(timeout=3)
            self._read_thread = None
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class AudioCapture:
    def __init__(self, sample_rate=16000, chunk_size=1024, accumulate_seconds=10, overlap_seconds=2):
        """
        Initialize multi-device audio capture with zero-persistence pipeline.

        Captures from ALL available WASAPI loopback devices simultaneously and
        merges the audio streams. This ensures audio is captured regardless of
        which output device (headphones, speakers, monitor) is currently active.

        Args:
            sample_rate: Target sample rate in Hz (16kHz for Whisper)
            chunk_size: Audio chunk size for PyAudio stream
            accumulate_seconds: Seconds of audio to accumulate before sending to transcription
            overlap_seconds: Seconds of overlap between chunks to avoid cutting words
        """
        self.target_sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.accumulate_seconds = accumulate_seconds
        self.overlap_seconds = overlap_seconds

        self.audio = pyaudio.PyAudio()
        self.device_streams = []  # List of DeviceStream objects
        self.is_recording = False

        # Raw audio from all devices lands here (tagged with native_rate)
        self.audio_queue = queue.Queue()
        # Resampled + mixed audio ready for Whisper
        self.transcription_queue = queue.Queue(maxsize=5)

        self.record_thread = None
        self.transcription_thread = None
        self.transcribe_callback = None
        self.dropped_chunks = 0
        self.active_device_names = []
        self.buffer_progress = 0.0  # 0.0 to 1.0 — how full the accumulation buffer is
        self.callbacks_received = 0  # total audio callbacks from all devices
        self.no_audio_warned = False  # True after first "no audio" warning

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
                            'defaultSampleRate': int(device_info.get('defaultSampleRate', 48000)),
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
                        'defaultSampleRate': int(default_loopback.get('defaultSampleRate', 48000)),
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
                            'defaultSampleRate': int(loopback.get('defaultSampleRate', 48000)),
                            'isLoopback': True
                        })
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error getting loopback devices: {e}")

        logger.info(f"Found {len(devices)} loopback device(s): {[d['name'] for d in devices]}")
        return devices

    def _open_all_devices(self):
        """Open ALL available loopback devices simultaneously. Returns number opened."""
        devices = self.get_loopback_devices()

        if not devices:
            logger.error("No loopback devices available")
            return 0

        opened = 0
        logger.info(f"Opening {len(devices)} loopback device(s) for simultaneous capture...")

        for dev in devices:
            ds = DeviceStream(
                device_index=dev['index'],
                device_name=dev['name'],
                channels=dev['channels'],
                native_rate=dev['defaultSampleRate'],
                audio_queue=self.audio_queue,
                pa_instance=self.audio,
                chunk_size=self.chunk_size
            )
            if ds.start():
                self.device_streams.append(ds)
                self.active_device_names.append(dev['name'])
                opened += 1

        logger.info(f"Successfully opened {opened}/{len(devices)} loopback device(s)")
        return opened

    def _open_single_device(self, device_index):
        """Open a single specific loopback device. Returns True on success."""
        try:
            device_info = self.audio.get_device_info_by_index(device_index)
            native_rate = int(device_info.get('defaultSampleRate', 48000))
            channels = device_info.get('maxInputChannels', 2)
            if channels <= 0:
                channels = 2
            name = device_info.get('name', 'Unknown')

            ds = DeviceStream(
                device_index=device_index,
                device_name=name,
                channels=channels,
                native_rate=native_rate,
                audio_queue=self.audio_queue,
                pa_instance=self.audio,
                chunk_size=self.chunk_size
            )
            if ds.start():
                self.device_streams.append(ds)
                self.active_device_names.append(name)
                return True
            return False
        except Exception as e:
            logger.warning(f"Could not open device {device_index}: {e}")
            return False

    def start_recording(self, device_index=None, transcribe_callback=None):
        """
        Start capturing audio for real-time transcription.

        If device_index is 'auto' or None: opens ALL loopback devices simultaneously
        and merges their audio. This captures system audio regardless of which output
        device (headphones, speakers, monitor) is active — like Cluely.

        If device_index is a specific int: opens only that device.

        Args:
            device_index: 'auto'/None for all-device capture, or specific device index
            transcribe_callback: Function(numpy_float32_16khz) called with each audio chunk.
                                 Audio is discarded immediately after this callback returns.
        """
        if self.is_recording:
            logger.warning("Already recording")
            return False

        self.transcribe_callback = transcribe_callback
        self.active_device_names = []
        self.device_streams = []

        auto_mode = (device_index is None or device_index == 'auto')

        if auto_mode:
            opened = self._open_all_devices()
            if opened == 0:
                logger.error("Could not open any loopback device")
                return False
        else:
            if not self._open_single_device(device_index):
                return False

        self.is_recording = True
        self.dropped_chunks = 0

        self.record_thread = threading.Thread(target=self._process_audio, daemon=True)
        self.record_thread.start()

        self.transcription_thread = threading.Thread(target=self._transcription_worker, daemon=True)
        self.transcription_thread.start()

        device_str = ', '.join(self.active_device_names) if self.active_device_names else 'None'
        logger.info(f"Live transcription started — capturing from: {device_str}")
        logger.info("Zero audio persistence, decoupled transcription, multi-device merge")
        return True

    def _process_audio(self):
        """
        Processing thread — reads audio chunks from all devices, resamples to 16kHz,
        accumulates and sends to transcription queue.

        Audio from different devices at different sample rates is resampled to a
        common rate (target_sample_rate) before accumulation. Chunks from multiple
        devices are simply concatenated in arrival order — since only one device
        typically has audio at any time, this works well. If multiple devices have
        audio simultaneously, they'll be interleaved which is fine for Whisper.

        NEVER blocks on transcription. Audio capture continues uninterrupted.
        No audio is ever written to disk. No persistent buffer is maintained.
        """
        logger.info("Audio processing thread started (multi-device, stream-only, zero persistence)")

        accumulator = []
        accumulated_samples = 0
        samples_threshold = self.target_sample_rate * self.accumulate_seconds
        overlap_samples = int(self.target_sample_rate * self.overlap_seconds)
        last_level_log = time.time()  # periodic audio level logging

        while self.is_recording:
            try:
                audio_float, native_rate = self.audio_queue.get(timeout=1)

                # Resample to target rate if needed
                if native_rate != self.target_sample_rate:
                    ratio = native_rate / self.target_sample_rate
                    int_ratio = round(ratio)
                    # Use fast integer decimation for exact ratios (e.g. 48000→16000 = 3:1)
                    if int_ratio > 1 and abs(ratio - int_ratio) < 0.01 and len(audio_float) > 100:
                        audio_float = signal.decimate(audio_float, int_ratio, zero_phase=True)
                    else:
                        # Fallback to polyphase resample for non-integer ratios
                        num_samples = int(len(audio_float) * self.target_sample_rate / native_rate)
                        if num_samples > 0:
                            audio_float = signal.resample_poly(
                                audio_float,
                                self.target_sample_rate,
                                native_rate
                            )

                accumulator.append(audio_float)
                accumulated_samples += len(audio_float)

                # Log audio level every 3 seconds so user can see capture is working
                now = time.time()
                if now - last_level_log >= 3.0:
                    rms_now = np.sqrt(np.mean(audio_float ** 2))
                    pct = int(100 * accumulated_samples / samples_threshold)
                    logger.info(f"Audio level: RMS={rms_now:.6f} | Buffer: {pct}% ({accumulated_samples}/{samples_threshold} samples)")
                    last_level_log = now

                # Update buffer progress for UI feedback
                self.buffer_progress = min(1.0, accumulated_samples / samples_threshold)

                # When we have enough audio, queue for transcription
                if accumulated_samples >= samples_threshold:
                    full_audio = np.concatenate(accumulator)

                    # Skip pure silence — avoids Whisper hallucinations on empty audio
                    rms_energy = np.sqrt(np.mean(full_audio ** 2))
                    if rms_energy < 1e-6:  # Very conservative threshold — only skip near-zero silence
                        logger.info(f"Skipping silent chunk (RMS={rms_energy:.8f})")
                        # Keep overlap but don't send to Whisper
                        if overlap_samples > 0 and len(full_audio) > overlap_samples:
                            accumulator = [full_audio[-overlap_samples:]]
                            accumulated_samples = overlap_samples
                        else:
                            accumulator = []
                            accumulated_samples = 0
                        continue

                    logger.info(f"Sending {len(full_audio)} samples ({len(full_audio)/16000:.1f}s) to transcription (RMS={rms_energy:.6f})")

                    # Non-blocking put — if transcription is backed up, drop this chunk
                    try:
                        self.transcription_queue.put_nowait(full_audio)
                    except queue.Full:
                        self.dropped_chunks += 1
                        logger.warning(f"Transcription queue full — dropped chunk #{self.dropped_chunks}. "
                                       f"Whisper is falling behind. Consider using a smaller model.")

                    # Keep overlap to avoid cutting words at chunk boundaries
                    if overlap_samples > 0 and len(full_audio) > overlap_samples:
                        accumulator = [full_audio[-overlap_samples:]]
                        accumulated_samples = overlap_samples
                    else:
                        accumulator = []
                        accumulated_samples = 0

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in audio processing: {e}")

        # Flush remaining audio
        if accumulator:
            try:
                full_audio = np.concatenate(accumulator)
                self.transcription_queue.put(full_audio, timeout=5)
            except (queue.Full, Exception) as e:
                logger.warning(f"Could not flush remaining audio: {e}")

        logger.info("Audio processing thread stopped")

    def _transcription_worker(self):
        """
        Dedicated transcription thread — decoupled from audio capture.
        Reads resampled audio from transcription_queue, calls the callback, discards audio.
        This thread can take as long as needed without blocking audio capture.
        """
        logger.info("Transcription worker thread started")

        while self.is_recording or not self.transcription_queue.empty():
            try:
                audio_data = self.transcription_queue.get(timeout=2)

                if self.transcribe_callback:
                    self.transcribe_callback(audio_data)
                    logger.info(f"Transcription worker processed chunk ({len(audio_data)} samples, {len(audio_data)/16000:.1f}s)")

                # audio_data goes out of scope — garbage collected, zero persistence

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Transcription worker error: {e}")

        logger.info("Transcription worker thread stopped")

    def stop_recording(self):
        """Stop audio capture from all devices and let transcription worker finish pending chunks"""
        if not self.is_recording:
            return

        self.is_recording = False

        # Stop all device streams
        for ds in self.device_streams:
            ds.stop()
        self.device_streams = []

        # Wait for audio processing thread to flush remaining audio
        if self.record_thread:
            self.record_thread.join(timeout=5)
            self.record_thread = None

        # Wait for transcription worker to finish processing queued chunks
        if self.transcription_thread:
            logger.info(f"Waiting for transcription worker to finish ({self.transcription_queue.qsize()} chunks pending)...")
            self.transcription_thread.join(timeout=60)
            self.transcription_thread = None

        # Clear any remaining audio in raw queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        # Clear any unprocessed transcription chunks
        while not self.transcription_queue.empty():
            try:
                self.transcription_queue.get_nowait()
            except queue.Empty:
                break

        if self.dropped_chunks > 0:
            logger.warning(f"Session ended with {self.dropped_chunks} dropped audio chunks")

        self.transcribe_callback = None
        self.active_device_names = []
        logger.info("Live transcription capture stopped")

    def cleanup(self):
        """Cleanup audio resources"""
        self.stop_recording()
        if self.audio:
            self.audio.terminate()
