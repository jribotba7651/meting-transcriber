"""
Transcriber Module
Optimized audio transcription using faster-whisper (CTranslate2).
- INT8 quantized inference for ~4x faster CPU performance
- Greedy decoding (beam_size=1) for additional speed
- Fixed language eliminates auto-detection overhead
- Built-in Silero VAD for file transcription
- Energy-based silence detection for live streaming
"""

import os
import tempfile
import logging
from datetime import datetime
from threading import Thread, Lock
import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    from moviepy import VideoFileClip, AudioFileClip
except ImportError:
    try:
        from moviepy.editor import VideoFileClip, AudioFileClip
    except ImportError:
        VideoFileClip = None
        AudioFileClip = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _is_silent(audio_float32_16k, threshold=0.005):
    """Quick energy-based silence check for live audio chunks.

    For file transcription, faster-whisper's built-in vad_filter
    handles silence filtering. This is only used for live streaming
    to skip completely silent chunks before calling transcribe().

    Args:
        audio_float32_16k: float32 numpy array at 16kHz
        threshold: RMS energy threshold

    Returns:
        True if audio is silent (below threshold)
    """
    rms = np.sqrt(np.mean(audio_float32_16k ** 2))
    return rms < threshold


class Transcriber:
    def __init__(self, model_size="base", device="auto", language="auto", compute_type="auto"):
        """
        Initialize transcriber with optimized settings.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (auto, cpu, cuda)
            language: Language code (en, es) or auto for auto-detect
            compute_type: CTranslate2 compute type (auto, int8, float16, float32)
        """
        self.model_size = model_size
        self.language = None if language == "auto" else language
        self.model = None
        self.device = self._determine_device(device)
        self.compute_type = self._determine_compute_type(compute_type, self.device)
        self.transcription_lock = Lock()
        self.is_transcribing = False

    def _determine_device(self, device_preference):
        if device_preference == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info("CUDA available, using GPU")
                    return "cuda"
            except ImportError:
                pass
            logger.info("Using CPU")
            return "cpu"
        return device_preference

    def _determine_compute_type(self, compute_type, device):
        """Select optimal compute type for the device."""
        if compute_type != "auto":
            return compute_type
        if device == "cuda":
            return "float16"
        return "int8"  # fastest on CPU

    def load_model(self):
        """Load the Whisper model using faster-whisper (CTranslate2)."""
        if WhisperModel is None:
            raise ImportError(
                "faster-whisper not installed. Run: pip install faster-whisper"
            )
        try:
            logger.info(
                f"Loading Whisper model: {self.model_size} on {self.device} "
                f"(compute_type={self.compute_type})"
            )
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info(f"Model loaded successfully on {self.device}")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False


    def transcribe_audio(self, audio_data):
        """
        Transcribe a numpy audio chunk (float32, 16kHz).
        Uses energy-based silence detection to skip empty chunks.

        Args:
            audio_data: numpy float32 array at 16kHz sample rate

        Returns:
            List of segment dicts with 'start', 'end', 'text' keys
        """
        if self.model is None or audio_data is None:
            return []

        # Convert to float32 if needed
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        # Energy-based silence check: skip empty chunks to save CPU
        if _is_silent(audio_data):
            logger.debug("No speech detected, skipping chunk")
            return []

        with self.transcription_lock:
            self.is_transcribing = True
            try:
                options = {
                    "beam_size": 1,
                    "temperature": 0.0,
                    "no_speech_threshold": 0.6,
                    "compression_ratio_threshold": 2.4,
                    "vad_filter": False,  # live chunks already pre-filtered
                }
                if self.language:
                    options["language"] = self.language

                segments_gen, info = self.model.transcribe(
                    audio_data, **options
                )

                segments = []
                for seg in segments_gen:
                    text = seg.text.strip()
                    if text:
                        segments.append({
                            "start": seg.start,
                            "end": seg.end,
                            "text": text,
                        })

                return segments

            except Exception as e:
                logger.error(f"Transcription error: {e}")
                return []
            finally:
                self.is_transcribing = False

    def transcribe_file(self, file_path, progress_callback=None):
        """
        Transcribe an audio or video file.

        Uses MoviePy (which bundles its own ffmpeg) to extract audio to a
        16 kHz PCM WAV, then reads it with the stdlib `wave` module and
        feeds numpy arrays to faster-whisper.

        Args:
            file_path: Path to audio/video file
            progress_callback: Optional callback for status updates.
                Receives strings like "Processing..." or "__segment__start|end|text"

        Returns:
            List of segment dicts with 'start', 'end', 'text' keys
        """
        if self.model is None:
            if progress_callback:
                progress_callback("Error: Model not loaded")
            return []

        video_exts = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.wmv'}
        audio_exts = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.wma'}
        ext = os.path.splitext(file_path)[1].lower()

        if VideoFileClip is None:
            if progress_callback:
                progress_callback(
                    "Error: moviepy is not installed. "
                    "Run:  pip install moviepy"
                )
            return []

        clip = None
        tmp_wav = None
        try:
            if progress_callback:
                progress_callback("Extracting audio...")

            tmp_wav = tempfile.mktemp(suffix='.wav')
            logger.info(f"Extracting audio from: {file_path} (format: {ext})")

            if ext in video_exts:
                clip = VideoFileClip(file_path)
                if clip.audio is None:
                    if progress_callback:
                        progress_callback("Error: Video has no audio track")
                    return []
                clip.audio.write_audiofile(
                    tmp_wav, fps=16000, nbytes=2, codec='pcm_s16le',
                )
            elif ext in audio_exts:
                clip = AudioFileClip(file_path)
                clip.write_audiofile(
                    tmp_wav, fps=16000, nbytes=2, codec='pcm_s16le',
                )
            else:
                if progress_callback:
                    progress_callback(f"Error: Unsupported format {ext}")
                return []

            logger.info(f"Audio extracted to temp file: {tmp_wav}")

            if progress_callback:
                progress_callback("Loading audio data...")

            # Read the WAV with stdlib — no ffmpeg needed
            import wave
            with wave.open(tmp_wav, 'rb') as wf:
                n_channels = wf.getnchannels()
                n_frames = wf.getnframes()
                framerate = wf.getframerate()
                raw_data = wf.readframes(n_frames)

            logger.info(
                f"WAV: channels={n_channels}, rate={framerate}, frames={n_frames}"
            )

            audio_data = (
                np.frombuffer(raw_data, dtype=np.int16)
                .astype(np.float32) / 32768.0
            )
            if n_channels > 1:
                audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)

            if len(audio_data) == 0:
                if progress_callback:
                    progress_callback("Error: No audio data extracted")
                return []

            total_duration = len(audio_data) / 16000.0
            logger.info(f"File audio: {len(audio_data)} samples ({total_duration:.1f}s)")

            # Transcribe in 120-second chunks for progress reporting
            chunk_seconds = 120
            chunk_samples = chunk_seconds * 16000
            all_segments = []
            total_chunks = max(1, int(np.ceil(len(audio_data) / chunk_samples)))

            for i in range(total_chunks):
                start_sample = i * chunk_samples
                end_sample = min((i + 1) * chunk_samples, len(audio_data))
                chunk = audio_data[start_sample:end_sample]

                chunk_start_sec = start_sample / 16000.0
                chunk_end_sec = end_sample / 16000.0

                if progress_callback:
                    progress_callback(
                        f"Transcribing chunk {i + 1}/{total_chunks} "
                        f"({chunk_start_sec:.0f}s\u2013{chunk_end_sec:.0f}s "
                        f"of {total_duration:.0f}s)"
                    )

                # Use faster-whisper with built-in VAD for file transcription
                options = {
                    "beam_size": 1,
                    "temperature": 0.0,
                    "no_speech_threshold": 0.6,
                    "compression_ratio_threshold": 2.4,
                    "vad_filter": True,  # built-in Silero VAD
                }
                if self.language:
                    options["language"] = self.language

                segments_gen, _info = self.model.transcribe(chunk, **options)

                for seg in segments_gen:
                    text = seg.text.strip()
                    if not text:
                        continue
                    segment_dict = {
                        "start": seg.start + chunk_start_sec,
                        "end": seg.end + chunk_start_sec,
                        "text": text,
                    }
                    all_segments.append(segment_dict)

                    if progress_callback:
                        progress_callback(
                            f"__segment__{segment_dict['start']:.2f}|"
                            f"{segment_dict['end']:.2f}|{segment_dict['text']}"
                        )

            if progress_callback:
                progress_callback(
                    f"Done - {len(all_segments)} segments from {total_duration:.0f}s"
                )

            return all_segments

        except Exception as e:
            logger.error(f"Error transcribing file: {e}", exc_info=True)
            if progress_callback:
                progress_callback(f"Error: {e}")
            return []

        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception:
                    pass
            if tmp_wav and os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass

    @staticmethod
    def format_timestamp(seconds):
        """Format seconds into MM:SS or HH:MM:SS string"""
        seconds = max(0, seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def save_transcription(self, segments, filename):
        """
        Save transcription segments to a text file.

        Args:
            segments: List of segment dicts
            filename: Output file path

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for seg in segments:
                    ts = self.format_timestamp(seg['start'])
                    f.write(f"[{ts}] {seg['text']}\n\n")
            logger.info(f"Transcription saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Error saving transcription: {e}")
            return False
