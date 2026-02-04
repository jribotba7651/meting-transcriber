"""
Meeting Transcriber - Main Entry Point
Real-time meeting transcription using Whisper
"""

import os
import sys
import json
import logging

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from audio_capture import AudioCapture
from transcriber import Transcriber
from ui import TranscriberUI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    # Default configuration
    default_config = {
        "whisper_model": "base",
        "language": "auto",
        "device": "auto",
        "buffer_duration": 30,
        "window_opacity": 0.95,
        "always_on_top": True
    }

    # Try to load config file
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Merge with defaults
                default_config.update(config)
                logger.info("Configuration loaded from config.json")
        except Exception as e:
            logger.warning(f"Error loading config.json: {e}. Using defaults.")

    return default_config


def save_config(config):
    """Save configuration to config.json"""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')

    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("Configuration saved")
    except Exception as e:
        logger.error(f"Error saving config: {e}")


def main():
    """Main application entry point"""
    logger.info("=" * 60)
    logger.info("Meeting Transcriber")
    logger.info("=" * 60)

    # Load configuration
    config = load_config()

    # Initialize components
    logger.info("Initializing audio capture...")
    audio_capture = AudioCapture(
        sample_rate=16000,
        chunk_size=1024,
        buffer_duration=config['buffer_duration']
    )

    logger.info("Initializing transcriber...")
    transcriber = Transcriber(
        model_size=config['whisper_model'],
        device=config['device'],
        language=config['language']
    )

    # Create and run UI
    logger.info("Starting UI...")
    app = TranscriberUI(audio_capture, transcriber, config)

    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
    finally:
        logger.info("Cleaning up...")
        audio_capture.cleanup()
        logger.info("Goodbye!")


if __name__ == "__main__":
    main()
