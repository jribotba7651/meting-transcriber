"""
Component Testing Script
Test individual components before running the full application
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_audio_capture():
    """Test audio capture functionality"""
    print("\n" + "="*60)
    print("Testing Audio Capture")
    print("="*60)

    try:
        from audio_capture import AudioCapture

        capture = AudioCapture()

        # Test device detection
        devices = capture.get_loopback_devices()
        print(f"\n✓ Found {len(devices)} loopback device(s):")
        for dev in devices:
            print(f"  [{dev['index']}] {dev['name']} ({dev['channels']} channels)")

        if not devices:
            print("\n⚠ No loopback devices found!")
            print("  This might be normal if 'Stereo Mix' is disabled.")
            print("  You can enable it in Windows Sound settings.")

        capture.cleanup()
        return True

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("  Please install: pip install PyAudioWPatch")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def test_transcriber():
    """Test transcriber functionality"""
    print("\n" + "="*60)
    print("Testing Transcriber")
    print("="*60)

    try:
        from transcriber import Transcriber
        import numpy as np

        print("\nInitializing transcriber with 'tiny' model...")
        transcriber = Transcriber(model_size="tiny", device="cpu")

        print("Loading model (this may take a moment)...")
        if transcriber.load_model():
            print("✓ Model loaded successfully!")

            # Test with silent audio
            print("\nTesting transcription with silent audio...")
            test_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
            results = transcriber.transcribe_audio(test_audio)

            print(f"✓ Transcription completed: {len(results)} segment(s)")
            if results:
                for seg in results:
                    print(f"  [{seg['start']:.2f}s - {seg['end']:.2f}s]: {seg['text']}")
            else:
                print("  (No speech detected in silent audio - this is expected)")

            return True
        else:
            print("✗ Failed to load model")
            print("  The model will be downloaded on first use.")
            print("  Make sure you have internet connection.")
            return False

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("  Please install: pip install faster-whisper")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ui():
    """Test UI functionality (just import)"""
    print("\n" + "="*60)
    print("Testing UI")
    print("="*60)

    try:
        import tkinter as tk
        print("✓ Tkinter available")

        # Test tkinter works
        root = tk.Tk()
        root.withdraw()  # Hide window
        root.destroy()
        print("✓ Tkinter functional")

        from ui import TranscriberUI
        print("✓ UI module imports successfully")

        return True

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("  Tkinter should be included with Python")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def test_config():
    """Test configuration loading"""
    print("\n" + "="*60)
    print("Testing Configuration")
    print("="*60)

    try:
        import json

        config_path = os.path.join(os.path.dirname(__file__), 'config.json')

        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)

            print("✓ config.json loaded successfully:")
            for key, value in config.items():
                print(f"  {key}: {value}")

            return True
        else:
            print("⚠ config.json not found (will use defaults)")
            return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("MEETING TRANSCRIBER - COMPONENT TESTS")
    print("="*70)
    print("\nThis script tests each component individually.")
    print("Run this before using the full application.\n")

    results = {
        "Configuration": test_config(),
        "UI": test_ui(),
        "Audio Capture": test_audio_capture(),
        "Transcriber": test_transcriber(),
    }

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    for component, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {component}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✓ All tests passed! You can run the application with: python main.py")
    else:
        print("\n⚠ Some tests failed. Please fix the issues before running the application.")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()
