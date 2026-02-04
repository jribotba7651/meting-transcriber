"""
UI Module
Tkinter-based GUI for the Meeting Transcriber
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import json
import os
from datetime import datetime
import threading
import time
import numpy as np


class TranscriberUI:
    def __init__(self, audio_capture, transcriber, config):
        """
        Initialize UI

        Args:
            audio_capture: AudioCapture instance
            transcriber: Transcriber instance
            config: Configuration dictionary
        """
        self.audio_capture = audio_capture
        self.transcriber = transcriber
        self.config = config

        self.root = tk.Tk()
        self.root.title("Meeting Transcriber")

        # State
        self.is_recording = False
        self.transcription_segments = []
        self.last_transcription_time = 0
        self.transcription_thread = None
        self.previous_buffer_tail = None  # Store last N seconds for overlap

        self._setup_ui()
        self._apply_config()
        self._populate_devices()

    def _setup_ui(self):
        """Setup the UI components"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # --- Control Frame ---
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding="5")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)

        # Device selection
        ttk.Label(control_frame, text="Audio Device:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(control_frame, textvariable=self.device_var, state="readonly")
        self.device_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))

        # Refresh devices button
        refresh_btn = ttk.Button(control_frame, text="↻", width=3, command=self._populate_devices)
        refresh_btn.grid(row=0, column=2)

        # Model selection
        ttk.Label(control_frame, text="Model:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.model_var = tk.StringVar(value=self.config.get('whisper_model', 'base'))
        model_combo = ttk.Combobox(
            control_frame,
            textvariable=self.model_var,
            values=['tiny', 'base', 'small', 'medium', 'large'],
            state="readonly",
            width=15
        )
        model_combo.grid(row=1, column=1, sticky=tk.W, pady=(5, 0))

        # Language selection
        ttk.Label(control_frame, text="Language:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.language_var = tk.StringVar(value=self.config.get('language', 'auto'))
        language_combo = ttk.Combobox(
            control_frame,
            textvariable=self.language_var,
            values=['auto', 'en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'pl', 'ru', 'ja', 'zh'],
            state="readonly",
            width=15
        )
        language_combo.grid(row=2, column=1, sticky=tk.W, pady=(5, 0))

        # --- Status Frame ---
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        status_frame.columnconfigure(1, weight=1)

        # Start/Stop button
        self.record_btn = ttk.Button(
            status_frame,
            text="▶ Start Recording",
            command=self._toggle_recording,
            width=20
        )
        self.record_btn.grid(row=0, column=0, padx=(0, 10))

        # Status label
        self.status_var = tk.StringVar(value="Idle")
        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_label.grid(row=0, column=1, sticky=(tk.W, tk.E))

        # --- Transcription Frame ---
        trans_frame = ttk.LabelFrame(main_frame, text="Transcription", padding="5")
        trans_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        trans_frame.columnconfigure(0, weight=1)
        trans_frame.rowconfigure(0, weight=1)

        # Transcription text area
        self.text_area = scrolledtext.ScrolledText(
            trans_frame,
            wrap=tk.WORD,
            width=80,
            height=20,
            font=("Consolas", 10)
        )
        self.text_area.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # --- Button Frame ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))

        # Clear button
        clear_btn = ttk.Button(button_frame, text="Clear", command=self._clear_transcription)
        clear_btn.pack(side=tk.LEFT, padx=(0, 5))

        # Save button
        save_btn = ttk.Button(button_frame, text="Save", command=self._save_transcription)
        save_btn.pack(side=tk.LEFT, padx=(0, 5))

        # Always on top checkbox
        self.always_on_top_var = tk.BooleanVar(value=self.config.get('always_on_top', True))
        always_on_top_cb = ttk.Checkbutton(
            button_frame,
            text="Always on Top",
            variable=self.always_on_top_var,
            command=self._toggle_always_on_top
        )
        always_on_top_cb.pack(side=tk.RIGHT)

        # Window size
        self.root.geometry("700x600")
        self.root.minsize(500, 400)

    def _apply_config(self):
        """Apply configuration settings"""
        # Always on top
        if self.config.get('always_on_top', True):
            self.root.attributes('-topmost', True)

        # Opacity
        opacity = self.config.get('window_opacity', 0.95)
        self.root.attributes('-alpha', opacity)

    def _populate_devices(self):
        """Populate audio device dropdown"""
        devices = self.audio_capture.get_loopback_devices()

        if not devices:
            self.device_combo['values'] = ["No loopback devices found"]
            self.device_combo.current(0)
            self.device_combo.state(['disabled'])
            messagebox.showwarning(
                "No Devices",
                "No loopback audio devices found.\n\n"
                "Please ensure your audio output device supports loopback capture."
            )
            return

        device_names = [f"[{d['index']}] {d['name']}" for d in devices]
        self.device_combo['values'] = device_names
        self.device_combo.current(0)
        self.device_combo.state(['!disabled'])

        # Store device mapping
        self.device_mapping = {name: d['index'] for name, d in zip(device_names, devices)}

    def _toggle_recording(self):
        """Toggle recording on/off"""
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        """Start recording"""
        print("[DEBUG] _start_recording called")

        # Use default WASAPI loopback (None = auto-detect)
        # This is more reliable than manually selecting from dropdown
        device_index = None
        print(f"[DEBUG] Using default WASAPI loopback (device_index=None)")

        # Load model if not loaded
        if self.transcriber.model is None:
            print("[DEBUG] Loading Whisper model...")
            self._update_status("Loading model...")
            self.root.update()

            model_size = self.model_var.get()
            language = self.language_var.get()

            self.transcriber.model_size = model_size
            self.transcriber.language = None if language == "auto" else language

            if not self.transcriber.load_model():
                messagebox.showerror("Error", "Failed to load Whisper model")
                self._update_status("Idle")
                return

            print("[DEBUG] Model loaded successfully")
        else:
            print("[DEBUG] Model already loaded")

        # Start audio capture
        print("[DEBUG] Starting audio capture...")
        if not self.audio_capture.start_recording(device_index):
            messagebox.showerror("Error", "Failed to start audio capture")
            self._update_status("Idle")
            return

        print("[DEBUG] Audio capture started successfully")

        # Update UI
        self.is_recording = True
        self.record_btn.config(text="⏹ Stop Recording")
        self.device_combo.state(['disabled'])
        self._update_status("Recording...")

        # Start transcription loop
        print("[DEBUG] Starting transcription thread...")
        self.transcription_thread = threading.Thread(target=self._transcription_loop, daemon=True)
        self.transcription_thread.start()
        print("[DEBUG] Transcription thread started")

    def _stop_recording(self):
        """Stop recording"""
        self.is_recording = False
        self.audio_capture.stop_recording()

        # Update UI
        self.record_btn.config(text="▶ Start Recording")
        self.device_combo.state(['!disabled'])
        self._update_status("Idle")

    def _transcription_loop(self):
        """Continuous transcription loop with double buffering and overlap"""
        buffer_duration = self.config.get('buffer_duration', 10)
        overlap_seconds = 5  # Keep last 5 seconds for continuity
        target_sample_rate = 16000  # Whisper's expected rate
        overlap_samples = overlap_seconds * target_sample_rate

        print(f"[DEBUG] Transcription loop started. Will transcribe every {buffer_duration} seconds")
        print(f"[DEBUG] Using {overlap_seconds}s overlap to avoid cutting words")

        while self.is_recording:
            current_time = time.time()

            # Transcribe every buffer_duration seconds
            if current_time - self.last_transcription_time >= buffer_duration:
                print(f"[DEBUG] {buffer_duration} seconds elapsed, getting audio buffer...")

                # STEP 1: Get current buffer (this is a copy)
                audio_buffer = self.audio_capture.get_audio_buffer()

                if audio_buffer is not None and len(audio_buffer) > 0:
                    print(f"[DEBUG] Audio buffer obtained: {len(audio_buffer)} samples ({len(audio_buffer)/target_sample_rate:.2f} seconds)")

                    # STEP 2: Clear buffer IMMEDIATELY so new audio can accumulate
                    self.audio_capture.clear_buffer()
                    print("[DEBUG] Audio buffer cleared - new audio can now accumulate during transcription")

                    # STEP 3: Add overlap from previous buffer if available
                    if self.previous_buffer_tail is not None:
                        print(f"[DEBUG] Adding {len(self.previous_buffer_tail)} overlap samples ({len(self.previous_buffer_tail)/target_sample_rate:.2f}s)")
                        # Prepend previous tail to current buffer
                        audio_buffer = np.concatenate([self.previous_buffer_tail, audio_buffer])
                        print(f"[DEBUG] Combined buffer: {len(audio_buffer)} samples ({len(audio_buffer)/target_sample_rate:.2f}s)")

                    # STEP 4: Save tail for next iteration
                    if len(audio_buffer) > overlap_samples:
                        self.previous_buffer_tail = audio_buffer[-overlap_samples:].copy()
                        print(f"[DEBUG] Saved {overlap_seconds}s tail for next overlap")
                    else:
                        self.previous_buffer_tail = audio_buffer.copy()
                        print(f"[DEBUG] Buffer shorter than overlap, saved entire buffer")

                    # STEP 5: Transcribe (this takes time, but buffer is accumulating new audio)
                    self._update_status("Transcribing...")
                    print("[DEBUG] Sending audio to transcriber...")

                    transcribe_start = time.time()
                    segments = self.transcriber.transcribe_audio(audio_buffer)
                    transcribe_time = time.time() - transcribe_start

                    print(f"[DEBUG] Transcription complete in {transcribe_time:.2f}s. Received {len(segments)} segments")

                    # STEP 6: Add to display (adjust timestamps if we had overlap)
                    overlap_time = overlap_seconds if self.previous_buffer_tail is not None else 0
                    for seg in segments:
                        # Adjust timestamp to account for overlap (skip displaying overlap part)
                        if seg['start'] >= overlap_time:
                            adjusted_seg = seg.copy()
                            adjusted_seg['start'] -= overlap_time
                            adjusted_seg['end'] -= overlap_time
                            print(f"[DEBUG] Segment: [{adjusted_seg['start']:.2f}s] {adjusted_seg['text']}")
                            self._add_transcription_segment(adjusted_seg)
                        else:
                            print(f"[DEBUG] Skipping overlap segment: [{seg['start']:.2f}s]")

                    self._update_status("Recording...")
                else:
                    print("[DEBUG] Audio buffer is None or empty")

                self.last_transcription_time = current_time

            time.sleep(1)

    def _add_transcription_segment(self, segment):
        """Add a transcription segment to the display"""
        self.transcription_segments.append(segment)

        timestamp = self.transcriber.format_timestamp(segment['start'])
        text = f"[{timestamp}] {segment['text']}\n\n"

        # Update text area
        self.text_area.insert(tk.END, text)
        self.text_area.see(tk.END)

    def _clear_transcription(self):
        """Clear the transcription"""
        if messagebox.askyesno("Confirm", "Clear all transcription?"):
            self.text_area.delete(1.0, tk.END)
            self.transcription_segments = []

    def _save_transcription(self):
        """Save transcription to file"""
        if not self.transcription_segments:
            messagebox.showinfo("Info", "No transcription to save")
            return

        # Ask for filename
        default_filename = f"transcription_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=default_filename
        )

        if filename:
            if self.transcriber.save_transcription(self.transcription_segments, filename):
                messagebox.showinfo("Success", f"Transcription saved to:\n{filename}")
            else:
                messagebox.showerror("Error", "Failed to save transcription")

    def _toggle_always_on_top(self):
        """Toggle always on top"""
        self.root.attributes('-topmost', self.always_on_top_var.get())

    def _update_status(self, status):
        """Update status label"""
        self.status_var.set(status)

    def run(self):
        """Start the UI main loop"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.mainloop()

    def _on_closing(self):
        """Handle window closing"""
        if self.is_recording:
            self._stop_recording()

        self.audio_capture.cleanup()
        self.root.destroy()
