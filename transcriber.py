"""
Transcriber Module
Handles audio transcription using OpenAI Whisper
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


class Transcriber:
    def __init__(self, model_size="base", device="auto", language="auto"):
        """
        Initialize transcriber

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (auto, cpu, cuda)
            language: Language for transcription (auto for auto-detect, or language code)
        """
        self.model_size = model_size
        self.language = None if language == "auto" else language
        self.model = None
        self.device = self._determine_device(device)

        self.transcription_lock = Lock()
        self.is_transcribing = False

    def _determine_device(self, device_preference):
        """Determine which device to use"""
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
        else:
            return device_preference

    def load_model(self):
        """Load the Whisper model"""
        if whisper is None:
            raise ImportError("openai-whisper not installed. Please install it first.")

        try:
            logger.info(f"Loading Whisper model: {self.model_size}")
            self.model = whisper.load_model(self.model_size)
            logger.info("Model loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False

    def transcribe_audio(self, audio_data, callback=None):
        """
        Transcribe audio data

        Args:
            audio_data: numpy array of audio samples (float32, 16kHz)
            callback: Optional callback function to call with transcription results

        Returns:
            List of transcription segments
        """
        if self.model is None:
            logger.error("Model not loaded")
            return []

        if audio_data is None or len(audio_data) == 0:
            logger.warning("No audio data to transcribe")
            return []

        with self.transcription_lock:
            self.is_transcribing = True

        try:
            transcription = self.model.transcribe(
                audio_data,
                language=self.language,
                verbose=False
            )

            results = []
            for segment in transcription['segments']:
                result = {
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                }
                results.append(result)

                if callback:
                    callback(result)

            logger.info(f"Transcribed {len(results)} segments")
            return results

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return []

        finally:
            with self.transcription_lock:
                self.is_transcribing = False

    def transcribe_async(self, audio_data, callback):
        """
        Transcribe audio asynchronously

        Args:
            audio_data: numpy array of audio samples
            callback: Callback function to call with results
        """
        thread = Thread(
            target=self.transcribe_audio,
            args=(audio_data, callback),
            daemon=True
        )
        thread.start()

    def transcribe_file(self, file_path, progress_callback=None):
        """
        Transcribe an audio or video file.

        Args:
            file_path: Path to video/audio file
            progress_callback: Optional callback(status_text) for progress updates

        Returns:
            List of transcription segments
        """
        if self.model is None:
            logger.error("Model not loaded")
            return []

        if VideoFileClip is None:
            logger.error("moviepy not installed")
            return []

        video_exts = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.wmv'}
        audio_exts = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.wma'}
        ext = os.path.splitext(file_path)[1].lower()

        clip = None
        tmp_wav = None
        try:
            if progress_callback:
                progress_callback("Extracting audio...")

            # Extract audio to a temp wav file
            tmp_wav = tempfile.mktemp(suffix='.wav')
            logger.info(f"Extracting audio from: {file_path} (format: {ext})")

            if ext in video_exts:
                clip = VideoFileClip(file_path)
                if clip.audio is None:
                    logger.error("Video file has no audio track")
                    if progress_callback:
                        progress_callback("Error: Video has no audio track")
                    return []
                clip.audio.write_audiofile(tmp_wav, fps=16000, nbytes=2, codec='pcm_s16le')
            elif ext in audio_exts:
                clip = AudioFileClip(file_path)
                clip.write_audiofile(tmp_wav, fps=16000, nbytes=2, codec='pcm_s16le')
            else:
                logger.error(f"Unsupported file format: {ext}")
                if progress_callback:
                    progress_callback(f"Error: Unsupported format {ext}")
                return []

            logger.info(f"Audio extracted to temp file: {tmp_wav}")

            if progress_callback:
                progress_callback("Loading audio data...")

            # Read the wav file as numpy array
            import wave
            with wave.open(tmp_wav, 'rb') as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                raw_data = wf.readframes(n_frames)

            logger.info(f"WAV: channels={n_channels}, width={sampwidth}, rate={framerate}, frames={n_frames}")

            audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0

            # Convert to mono if stereo
            if n_channels > 1:
                audio_data = audio_data.reshape(-1, n_channels).mean(axis=1)

            if len(audio_data) == 0:
                logger.error("Extracted audio is empty")
                if progress_callback:
                    progress_callback("Error: No audio data extracted")
                return []

            total_duration = len(audio_data) / 16000
            logger.info(f"File audio: {len(audio_data)} samples ({total_duration:.1f}s)")

            # Transcribe in chunks of 120 seconds for better quality (more context)
            chunk_seconds = 120
            chunk_samples = chunk_seconds * 16000
            all_segments = []
            time_offset = 0.0

            total_chunks = max(1, int(np.ceil(len(audio_data) / chunk_samples)))

            for i in range(total_chunks):
                start_sample = i * chunk_samples
                end_sample = min((i + 1) * chunk_samples, len(audio_data))
                chunk = audio_data[start_sample:end_sample]

                chunk_start_sec = start_sample / 16000
                chunk_end_sec = end_sample / 16000

                if progress_callback:
                    progress_callback(
                        f"Transcribing chunk {i+1}/{total_chunks} "
                        f"({chunk_start_sec:.0f}s-{chunk_end_sec:.0f}s of {total_duration:.0f}s)"
                    )

                logger.info(f"Transcribing chunk {i+1}/{total_chunks}: {chunk_start_sec:.0f}s-{chunk_end_sec:.0f}s")

                segments = self.transcribe_audio(chunk)

                # Adjust timestamps to absolute position in the file
                for seg in segments:
                    seg['start'] += chunk_start_sec
                    seg['end'] += chunk_start_sec
                    all_segments.append(seg)

                    # Call segment_callback to show results immediately
                    if progress_callback:
                        progress_callback(f"__segment__{seg['start']}|{seg['end']}|{seg['text']}")

            if progress_callback:
                progress_callback(f"Done - {len(all_segments)} segments from {total_duration:.0f}s")

            return all_segments

        except Exception as e:
            logger.error(f"Error transcribing file: {e}", exc_info=True)
            if progress_callback:
                progress_callback(f"Error: {e}")
            return []

        finally:
            # Clean up
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

    def is_busy(self):
        """Check if transcriber is currently processing"""
        return self.is_transcribing

    @staticmethod
    def format_timestamp(seconds):
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def save_transcription(segments, filename):
        """
        Save transcription to file

        Args:
            segments: List of transcription segments
            filename: Output filename
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("CONFIDENTIAL — INTERNAL USE ONLY\n")
                f.write("=" * 80 + "\n")
                f.write(f"Meeting Transcription\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Classification: Internal/Confidential\n")
                f.write("=" * 80 + "\n\n")

                for seg in segments:
                    timestamp = Transcriber.format_timestamp(seg['start'])
                    f.write(f"[{timestamp}] {seg['text']}\n\n")

            logger.info(f"Transcription saved to {filename}")
            return True

        except Exception as e:
            logger.error(f"Error saving transcription: {e}")
            return False


if __name__ == "__main__":
    # Test the transcriber
    print("Testing Transcriber...")

    transcriber = Transcriber(model_size="tiny", device="cpu")

    if transcriber.load_model():
        print("Model loaded successfully!")

        # Create a test audio signal (1 second of silence)
        test_audio = np.zeros(16000, dtype=np.float32)

        print("Testing transcription...")
        results = transcriber.transcribe_audio(test_audio)
        print(f"Transcription results: {results}")
    else:
        print("Failed to load model")

    print("Test complete!")
