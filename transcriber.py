"""
Transcriber Module
Handles audio transcription using OpenAI Whisper
"""

import os
import logging
from datetime import datetime
from threading import Thread, Lock
import numpy as np

try:
    import whisper
except ImportError:
    whisper = None

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
            # Try CUDA first, fallback to CPU
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
            # Transcribe
            transcription = self.model.transcribe(
                audio_data,
                language=self.language,
                verbose=False
            )

            # Collect results
            results = []
            for segment in transcription['segments']:
                result = {
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                }
                results.append(result)

                # Call callback if provided
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
                f.write(f"Meeting Transcription\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
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
