"""
UI Module
Tkinter-based GUI for the Meeting Notes Assistant
Supports file upload transcription and live stream-only transcription.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import json
import os
from datetime import datetime
import threading
from threading import Lock
import time


class TranscriberUI:
    def __init__(self, audio_capture, transcriber, config):
        """
        Initialize UI

        Args:
            audio_capture: AudioCapture instance for live transcription
            transcriber: Transcriber instance
            config: Configuration dictionary
        """
        self.audio_capture = audio_capture
        self.transcriber = transcriber
        self.config = config

        self.root = tk.Tk()
        self.root.title("Meeting Notes Assistant")

        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)

        # State
        self.transcription_segments = []
        self.is_live_transcribing = False
        self.live_start_time = None
        self.live_elapsed_timer = None
        self.live_segment_offset = 0.0
        self._offset_lock = Lock()
        self._chunk_counter = 0  # monotonic chunk counter for correct offset

        # Shared transcript file for overlay integration
        self.live_transcript_dir = os.path.join(
            os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
            'meeting-transcriber'
        )
        self.live_transcript_path = os.path.join(self.live_transcript_dir, 'live_transcript.json')

        self._setup_ui()
        self._apply_config()

    def _setup_ui(self):
        """Setup the UI components"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

        # --- Control Frame ---
        control_frame = ttk.LabelFrame(main_frame, text="Settings", padding="5")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)

        # Model selection
        ttk.Label(control_frame, text="Model:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.model_var = tk.StringVar(value=self.config.get('whisper_model', 'base'))
        model_combo = ttk.Combobox(
            control_frame,
            textvariable=self.model_var,
            values=['tiny', 'base', 'small', 'medium', 'large'],
            state="readonly",
            width=15
        )
        model_combo.grid(row=0, column=1, sticky=tk.W)

        # Language selection
        ttk.Label(control_frame, text="Language:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.language_var = tk.StringVar(value=self.config.get('language', 'auto'))
        language_combo = ttk.Combobox(
            control_frame,
            textvariable=self.language_var,
            values=['auto', 'en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'pl', 'ru', 'ja', 'zh'],
            state="readonly",
            width=15
        )
        language_combo.grid(row=1, column=1, sticky=tk.W, pady=(5, 0))

        # Device selection
        ttk.Label(control_frame, text="Audio Device:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        device_frame = ttk.Frame(control_frame)
        device_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=(5, 0))

        self.device_var = tk.StringVar(value="(click Refresh)")
        self.device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.device_var,
            state="readonly",
            width=40
        )
        self.device_combo.pack(side=tk.LEFT)

        self.refresh_btn = ttk.Button(device_frame, text="Refresh", command=self._refresh_devices, width=8)
        self.refresh_btn.pack(side=tk.LEFT, padx=(5, 0))

        self.loopback_devices = []

        # --- Action Frame ---
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        action_frame.columnconfigure(2, weight=1)

        # Upload button
        self.upload_btn = ttk.Button(
            action_frame,
            text="\U0001f4c1 Upload Audio/Video",
            command=self._upload_video,
            width=22
        )
        self.upload_btn.grid(row=0, column=0, padx=(0, 5))

        # Live transcription button
        self.live_btn = ttk.Button(
            action_frame,
            text="\U0001f534 Start Live Transcription",
            command=self._toggle_live_transcription,
            width=28
        )
        self.live_btn.grid(row=0, column=1, padx=(0, 10))

        # --- Status Frame ---
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)

        # Status label
        self.status_var = tk.StringVar(value="Ready \u2014 Upload a file or start live transcription")
        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_label.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # --- Transcription Frame ---
        trans_frame = ttk.LabelFrame(main_frame, text="Transcription", padding="5")
        trans_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
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
        button_frame.grid(row=4, column=0, sticky=(tk.W, tk.E))

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
        self.root.geometry("750x650")
        self.root.minsize(550, 450)

    def _apply_config(self):
        """Apply configuration settings"""
        if self.config.get('always_on_top', True):
            self.root.attributes('-topmost', True)

        opacity = self.config.get('window_opacity', 0.95)
        self.root.attributes('-alpha', opacity)

    def _refresh_devices(self):
        """Refresh the list of loopback audio devices"""
        self.loopback_devices = self.audio_capture.get_loopback_devices()

        if self.loopback_devices:
            # "All Devices" captures from every output simultaneously — never misses audio
            device_names = [f'🔊 All Devices ({len(self.loopback_devices)} found)'] + [d['name'] for d in self.loopback_devices]
            self.device_combo['values'] = device_names
            self.device_combo.current(0)  # Default to all-device capture
        else:
            self.device_combo['values'] = ['No loopback devices found']
            self.device_var.set('No loopback devices found')

    def _get_selected_device_index(self):
        """Get the device index of the selected loopback device.
        Returns 'auto' for auto-detect mode, a device index for specific device,
        or None if no devices available."""
        if not self.loopback_devices:
            return None

        current_selection = self.device_combo.current()

        # Index 0 = "Auto-detect" option
        if current_selection == 0:
            return 'auto'

        # Offset by 1 for the actual device list (auto-detect is index 0)
        device_idx = current_selection - 1
        if 0 <= device_idx < len(self.loopback_devices):
            return self.loopback_devices[device_idx]['index']
        return None

    # --- Live Transcription ---

    def _toggle_live_transcription(self):
        """Toggle live transcription on/off"""
        if self.is_live_transcribing:
            self._stop_live_transcription()
        else:
            self._start_live_transcription()

    def _show_consent_dialog(self):
        """Show consent dialog before starting live transcription. Returns True if user consents."""
        return messagebox.askokcancel(
            "Live Transcription \u2014 Consent Required",
            "This will capture system audio for live transcription.\n\n"
            "\u2022 No audio is recorded or saved.\n"
            "\u2022 No audio files are created or stored at any time.\n"
            "\u2022 Audio is processed in real-time and immediately discarded from memory.\n"
            "\u2022 Only the text transcription is kept.\n\n"
            "Ensure all meeting participants are aware.\n\n"
            "Click OK to confirm and start.",
            icon='warning'
        )

    def _start_live_transcription(self):
        """Start live transcription with consent and zero audio persistence"""
        # Refresh devices if not done yet
        if not self.loopback_devices:
            self._refresh_devices()

        device_index = self._get_selected_device_index()
        if device_index is None:
            messagebox.showerror("Error", "No loopback audio device found.\n\n"
                                 "Click 'Refresh' next to Audio Device to detect devices.")
            return

        # Show consent dialog
        if not self._show_consent_dialog():
            return

        # Load model if not loaded
        if self.transcriber.model is None:
            self._update_status("Loading Whisper model...")
            self.root.update()

            model_size = self.model_var.get()
            language = self.language_var.get()
            self.transcriber.model_size = model_size
            self.transcriber.language = None if language == "auto" else language

            if not self.transcriber.load_model():
                messagebox.showerror("Error", "Failed to load Whisper model")
                self._update_status("Ready \u2014 Upload a file or start live transcription")
                return

        # Define transcription callback (called from transcription worker thread)
        def on_audio_chunk(audio_data):
            """Receive audio, transcribe, discard audio. Only text survives."""
            if not self.is_live_transcribing:
                return

            # Grab the offset for THIS chunk atomically before transcribing
            with self._offset_lock:
                chunk_offset = self.live_segment_offset
                self._chunk_counter += 1

            segments = self.transcriber.transcribe_audio(audio_data)

            # Calculate the actual net duration (exclude overlap to avoid duplicate timestamps)
            overlap_seconds = self.audio_capture.overlap_seconds
            if audio_data is not None:
                chunk_duration = len(audio_data) / 16000.0
                net_duration = max(0, chunk_duration - overlap_seconds)
            else:
                net_duration = 0

            for seg in segments:
                # Offset timestamps relative to session start
                seg['start'] += chunk_offset
                seg['end'] += chunk_offset
                self.root.after(0, self._add_transcription_segment, seg)

            # Update offset for next chunk (net duration only, overlap already counted)
            with self._offset_lock:
                self.live_segment_offset = chunk_offset + net_duration

        # Start capture
        self.is_live_transcribing = True
        self.live_start_time = time.time()
        self.live_segment_offset = 0.0
        self._chunk_counter = 0

        # Show header
        self.text_area.insert(tk.END, f"--- Live Transcription Started: {datetime.now().strftime('%H:%M:%S')} ---\n\n")
        self.text_area.see(tk.END)

        success = self.audio_capture.start_recording(
            device_index=device_index,
            transcribe_callback=on_audio_chunk
        )

        if not success:
            self.is_live_transcribing = False
            self.live_start_time = None
            messagebox.showerror("Error", "Failed to start audio capture.\n\n"
                                 "Try selecting a different audio device.")
            self._update_status("Ready \u2014 Upload a file or start live transcription")
            return

        # Update UI
        self.live_btn.config(text="\u23f9 Stop Live Transcription")
        self.upload_btn.config(state='disabled')
        self._update_live_status()

    def _update_live_status(self):
        """Update status bar with elapsed time during live transcription"""
        if not self.is_live_transcribing:
            return

        elapsed = time.time() - self.live_start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        device_count = len(self.audio_capture.active_device_names)
        status = f"\U0001f534 TRANSCRIBING LIVE \u2014 {minutes:02d}:{seconds:02d}  ({device_count} device(s))"

        # Show buffer progress when waiting for first chunk
        buffer_pct = int(self.audio_capture.buffer_progress * 100)
        if buffer_pct < 100:
            status += f"  | Buffering: {buffer_pct}%"

        # Show warning if audio chunks are being dropped
        dropped = self.audio_capture.dropped_chunks
        if dropped > 0:
            status += f"  \u26a0\ufe0f {dropped} chunk(s) dropped — Whisper falling behind"

        # Show pending queue size for visibility
        pending = self.audio_capture.transcription_queue.qsize()
        if pending > 0:
            status += f"  | Queue: {pending}"

        self._update_status(status)

        self.live_elapsed_timer = self.root.after(1000, self._update_live_status)

    def _stop_live_transcription(self):
        """Stop live transcription"""
        self.is_live_transcribing = False

        if self.live_elapsed_timer:
            self.root.after_cancel(self.live_elapsed_timer)
            self.live_elapsed_timer = None

        self.audio_capture.stop_recording()

        # Show footer
        elapsed = time.time() - self.live_start_time if self.live_start_time else 0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        self.text_area.insert(tk.END,
            f"\n--- Live Transcription Stopped: {datetime.now().strftime('%H:%M:%S')} "
            f"(duration: {minutes:02d}:{seconds:02d}) ---\n\n")
        self.text_area.see(tk.END)

        self.live_start_time = None
        self.live_segment_offset = 0.0

        # Mark transcript as inactive for overlay
        self._clear_live_transcript()

        # Re-enable UI
        self.live_btn.config(text="\U0001f534 Start Live Transcription")
        self.upload_btn.config(state='normal')
        self._update_status(f"Done \u2014 {len(self.transcription_segments)} segments transcribed")

    # --- File Upload Transcription ---

    def _add_transcription_segment(self, segment):
        """Add a transcription segment to the display"""
        self.transcription_segments.append(segment)

        timestamp = self.transcriber.format_timestamp(segment['start'])
        text = f"[{timestamp}] {segment['text']}\n\n"

        self.text_area.insert(tk.END, text)
        self.text_area.see(tk.END)

        # Export live transcript for overlay integration
        if self.is_live_transcribing:
            self._save_live_transcript()

    def _save_live_transcript(self):
        """Write live transcript to JSON for overlay integration"""
        try:
            os.makedirs(self.live_transcript_dir, exist_ok=True)

            data = {
                'timestamp': datetime.now().isoformat(),
                'segments': self.transcription_segments,
                'session_id': str(self.live_start_time) if self.live_start_time else None,
                'is_active': self.is_live_transcribing
            }

            # Write to temp file first, then rename for atomic write
            tmp_path = self.live_transcript_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self.live_transcript_path)
        except Exception as e:
            print(f"[Transcript export] Error: {e}")

    def _clear_live_transcript(self):
        """Mark live transcript as inactive"""
        try:
            if os.path.exists(self.live_transcript_path):
                data = {
                    'timestamp': datetime.now().isoformat(),
                    'segments': self.transcription_segments,
                    'session_id': None,
                    'is_active': False
                }
                with open(self.live_transcript_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[Transcript export] Error clearing: {e}")

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

    def _upload_video(self):
        """Upload and transcribe a video/audio file"""
        if self.is_live_transcribing:
            messagebox.showinfo("Info", "Stop live transcription before uploading a file.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Video or Audio File",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.avi *.webm *.mov *.wmv"),
                ("Audio files", "*.mp3 *.wav *.m4a *.ogg *.flac *.wma"),
                ("All files", "*.*")
            ]
        )

        if not file_path:
            return

        # Load model if not loaded
        if self.transcriber.model is None:
            self._update_status("Loading model...")
            self.root.update()

            model_size = self.model_var.get()
            language = self.language_var.get()
            self.transcriber.model_size = model_size
            self.transcriber.language = None if language == "auto" else language

            if not self.transcriber.load_model():
                messagebox.showerror("Error", "Failed to load Whisper model")
                self._update_status("Ready \u2014 Upload a file or start live transcription")
                return

        # Disable buttons during processing
        self.upload_btn.config(state='disabled')
        self.live_btn.config(state='disabled')

        # Show header
        filename = os.path.basename(file_path)
        self.text_area.insert(tk.END, f"--- Transcription: {filename} ---\n\n")
        self.text_area.see(tk.END)

        def process_file():
            error_msg = None

            def on_progress(status):
                nonlocal error_msg
                if status.startswith("Error:"):
                    error_msg = status
                    self.root.after(0, self._update_status, status)
                elif status.startswith("__segment__"):
                    parts = status[len("__segment__"):].split("|", 2)
                    if len(parts) == 3:
                        seg = {'start': float(parts[0]), 'end': float(parts[1]), 'text': parts[2]}
                        self.root.after(0, self._add_transcription_segment, seg)
                else:
                    self.root.after(0, self._update_status, status)

            segments = self.transcriber.transcribe_file(file_path, progress_callback=on_progress)

            def show_results():
                if segments:
                    self.text_area.insert(tk.END, f"\n--- End of {filename} ---\n\n")
                    self.text_area.see(tk.END)
                    self._update_status(f"Done - {len(segments)} segments from {filename}")
                elif error_msg:
                    messagebox.showerror("Transcription Error",
                                         f"Failed to transcribe {filename}:\n\n{error_msg}")
                    self._update_status("Ready \u2014 Upload a file or start live transcription")
                else:
                    messagebox.showwarning("Warning", "No transcription segments were generated.\n\n"
                                           "Check the terminal for more details.")
                    self._update_status("Ready \u2014 Upload a file or start live transcription")

                self.upload_btn.config(state='normal')
                self.live_btn.config(state='normal')

            self.root.after(0, show_results)

        thread = threading.Thread(target=process_file, daemon=True)
        thread.start()

    # --- Window Controls ---

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
        if self.is_live_transcribing:
            self.audio_capture.stop_recording()
        self.audio_capture.cleanup()
        self.root.destroy()
