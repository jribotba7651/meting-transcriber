"""
UI Module
Tkinter-based GUI for the Meeting Notes Assistant
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import json
import os
from datetime import datetime
import threading
import time


class TranscriberUI:
    def __init__(self, transcriber, config):
        """
        Initialize UI

        Args:
            transcriber: Transcriber instance
            config: Configuration dictionary
        """
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
        main_frame.rowconfigure(2, weight=1)

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

        # --- Status Frame ---
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        status_frame.columnconfigure(1, weight=1)

        # Upload button (primary action)
        self.upload_btn = ttk.Button(
            status_frame,
            text="📁 Upload Audio/Video",
            command=self._upload_video,
            width=25
        )
        self.upload_btn.grid(row=0, column=0, padx=(0, 10))

        # Status label
        self.status_var = tk.StringVar(value="Ready — Upload a file to transcribe")
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

    def _upload_video(self):
        """Upload and transcribe a video/audio file"""
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
                self._update_status("Ready — Upload a file to transcribe")
                return

        # Disable button during processing
        self.upload_btn.config(state='disabled')

        # Show header immediately
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
                    # Real-time segment display: __segment__start|end|text
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
                elif not error_msg:
                    messagebox.showwarning("Warning", "No transcription segments were generated.\n\n"
                                           "Check the terminal for more details.")
                    self._update_status("Ready — Upload a file to transcribe")
                else:
                    self._update_status("Ready — Upload a file to transcribe")

                self.upload_btn.config(state='normal')

            self.root.after(0, show_results)

        thread = threading.Thread(target=process_file, daemon=True)
        thread.start()

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
        self.root.destroy()
