"""
Transcriber Module
Optimized audio transcription using OpenAI Whisper.
- Greedy decoding (beam_size=1) for ~2-3x faster inference
- Fixed language eliminates auto-detection overhead
- Silero VAD pre-filters silence to avoid hallucinations
- Reduced buffer (10s) for near-real-time display
"""

import os
import tempfile
import logging
from datetime import datetime
from threading import Thread, Lock
import numpy as np

try:
    import whisper
except ImportError:
    whisper = None

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


# --------------- Silero VAD helper ---------------
_vad_model = None

def _get_vad_model():
    """Lazy-load Silero VAD model (tiny, runs in <5ms)."""
    global _vad_model
    if _vad_model is None:
        try:
            import torch
            model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True,
                source='github',
            )
            _vad_model = model
            logger.info("Silero VAD model loaded")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD: {e}. Falling back to energy-based VAD.")
    return _vad_model


def _has_speech(audio_float32_16k, threshold=0.3):
    """Check if audio contains speech using Silero VAD or energy fallback.
    
    Args:
        audio_float32_16k: float32 numpy array at 16kHz
        threshold: VAD probability threshold (0.0-1.0)
    
    Returns:
        True if speech detected, False if silence/noise only
    """
    vad = _get_vad_model()
    if vad is not None:
        try:
            import torch
            # Silero VAD expects 512-sample windows at 16kHz
            # Check a few windows spread across the audio
            audio_tensor = torch.from_numpy(audio_float32_16k)
            window = 512
            step = max(window, len(audio_tensor) // 20)  # ~20 samples
            for start in range(0, len(audio_tensor) - window, step):
                chunk = audio_tensor[start:start + window]
                prob = vad(chunk, 16000).item()
                if prob > threshold:
                    return True
            return False
        except Exception as e:
            logger.debug(f"VAD error: {e}")

    # Energy-based fallback
    rms = np.sqrt(np.mean(audio_float32_16k ** 2))
    return rms > 0.005


class Transcriber:
    def __init__(self, model_size="base", device="auto", language="auto"):
        """
        Initialize transcriber with optimized settings.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (auto, cpu, cuda)
            language: Language code (en, es) or auto for auto-detect
        """
        self.model_size = model_size
        self.language = None if language == "auto" else language
        self.model = None
        self.device = self._determine_device(device)
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

    def load_model(self):
        """Load the Whisper model"""
        if whisper is None:
            raise ImportError("openai-whisper not installed.")
        try:
            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            self.model = whisper.load_model(self.model_size, device=self.device)
            logger.info(f"Model loaded successfully on {self.device}")
            return True
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False


    def transcribe_audio(self, audio_data):
        """
        Transcribe a numpy audio chunk (float32, 16kHz).
        Uses VAD to skip silence and greedy decoding for speed.

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

        # VAD check: skip silence to avoid Whisper hallucinations
        if not _has_speech(audio_data):
            logger.debug("No speech detected, skipping chunk")
            return []

        with self.transcription_lock:
            self.is_transcribing = True
            try:
                # Greedy decoding (beam_size=1) is ~2-3x faster than default beam=5
                decode_options = {
                    "beam_size": 1,
                    "best_of": 1,
                    "temperature": 0.0,
                    "no_speech_threshold": 0.6,
                    "compression_ratio_threshold": 2.4,
                }
                if self.language:
                    decode_options["language"] = self.language

                result = self.model.transcribe(
                    audio_data,
                    fp16=False,
                    **decode_options,
                )

                segments = []
                for seg in result.get("segments", []):
                    text = seg["text"].strip()
                    if text:
                        segments.append({
                            "start": seg["start"],
                            "end": seg["end"],
                            "text": text,
                        })

                return segments

            except Exception as e:
                logger.error(f"Transcription error: {e}")
                return []
            finally:
                self.is_transcribing = False

    def _extract_audio_ffmpeg(self, video_path, output_path):
        """Extract audio from video using ffmpeg directly.

        Returns True on success, False on failure.
        """
        import subprocess
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", video_path,
                    "-vn",          # no video
                    "-acodec", "pcm_s16le",
                    "-ar", "16000", # 16kHz for Whisper
                    "-ac", "1",     # mono
                    output_path,
                ],
                capture_output=True,
                timeout=300,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"ffmpeg extraction failed: {e}")
            return False

    def _extract_audio_moviepy(self, video_path, output_path):
        """Extract audio from video using MoviePy as fallback.

        Returns True on success, False on failure.
        """
        if VideoFileClip is None:
            return False
        try:
            video = VideoFileClip(video_path)
            video.audio.write_audiofile(output_path, verbose=False, logger=None)
            video.close()
            return True
        except Exception as e:
            logger.warning(f"MoviePy extraction failed: {e}")
            return False

    def transcribe_file(self, file_path, progress_callback=None):
        """
        Transcribe an audio or video file.

        Whisper uses ffmpeg internally so it can handle most video/audio
        formats directly.  If direct transcription fails for a video file,
        we fall back to explicit audio extraction (ffmpeg CLI, then MoviePy).

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

        try:
            audio_path = file_path
            temp_audio = None

            video_exts = ('.mp4', '.mkv', '.avi', '.webm', '.mov', '.wmv')
            is_video = file_path.lower().endswith(video_exts)

            if progress_callback:
                progress_callback("Transcribing... (this may take a while)")

            # Transcribe with optimized settings
            decode_options = {
                "beam_size": 1,
                "best_of": 1,
                "temperature": 0.0,
            }
            if self.language:
                decode_options["language"] = self.language

            # First attempt: pass the file directly to Whisper (works for
            # any format that ffmpeg can decode, including .mp4).
            result = None
            try:
                result = self.model.transcribe(
                    audio_path,
                    fp16=False,
                    verbose=False,
                    **decode_options,
                )
            except Exception as e:
                logger.warning(f"Direct transcription failed: {e}")

                # Fallback: extract audio explicitly for video files
                if is_video:
                    if progress_callback:
                        progress_callback("Extracting audio from video...")

                    temp_audio = os.path.join(
                        tempfile.gettempdir(), "meeting_audio_temp.wav"
                    )

                    extracted = self._extract_audio_ffmpeg(file_path, temp_audio)
                    if not extracted:
                        extracted = self._extract_audio_moviepy(file_path, temp_audio)

                    if not extracted:
                        if progress_callback:
                            progress_callback(
                                "Error: Could not extract audio. "
                                "Please install ffmpeg or moviepy."
                            )
                        return []

                    audio_path = temp_audio
                    result = self.model.transcribe(
                        audio_path,
                        fp16=False,
                        verbose=False,
                        **decode_options,
                    )
                else:
                    raise  # re-raise for non-video files

            segments = []
            for seg in result.get("segments", []):
                text = seg["text"].strip()
                if text:
                    segment = {
                        "start": seg["start"],
                        "end": seg["end"],
                        "text": text,
                    }
                    segments.append(segment)

                    # Stream segments to UI as they're processed
                    if progress_callback:
                        progress_callback(
                            f"__segment__{seg['start']:.2f}|{seg['end']:.2f}|{text}"
                        )

            # Cleanup temp file
            if temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except OSError:
                    pass

            if progress_callback:
                progress_callback(f"Done - {len(segments)} segments")

            return segments

        except Exception as e:
            logger.error(f"File transcription error: {e}")
            if progress_callback:
                progress_callback(f"Error: {e}")
            return []

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
