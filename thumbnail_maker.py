import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import cv2
import PIL.Image, PIL.ImageTk
import threading
import time
import os
import shutil
import subprocess
from typing import List, Optional, Tuple

class ThumbnailMakerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AQ Video - Thumbnail & Preview Maker")
        self.root.geometry("1200x850")
        
        # Dark Theme Colors (matching Video Encoder)
        self.colors = {
            'bg': '#1e1e2e',
            'bg_secondary': '#2d2d3f',
            'bg_tertiary': '#3d3d5a',
            'fg': '#ffffff',
            'fg_secondary': '#b4b4b4',
            'accent': '#7c3aed',
            'accent_hover': '#8b5cf6',
            'success': '#22c55e',
            'warning': '#f59e0b',
            'error': '#ef4444',
            'border': '#4a4a6a'
        }
        
        self._configure_styles()
        
        # State
        self.video_path = ""
        self.cap = None
        self.total_frames = 0
        self.fps = 0
        self.duration = 0
        self.is_playing = False
        self.current_frame_idx = 0
        self.update_job = None
        
        # Thumbnail State
        self.thumbnails: List[Tuple[int, PIL.Image.Image]] = []  # (frame_idx, image)
        self.thumb_resolution = tk.StringVar(value="640") # Default width
        
        # Export Progress
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="")
        
        # Preview Clip State
        self.clip_start: Optional[int] = None
        self.clip_duration_sec = tk.IntVar(value=5) # Default 5s
        self.clips: List[Tuple[int, int]] = [] # List of (start_frame, end_frame)
        
        # Build UI
        self._build_ui()
        
        # Keyboard shortcuts
        self.root.bind('<space>', self._toggle_play)
        self.root.bind('<Left>', lambda e: self._seek_relative(-5))
        self.root.bind('<Right>', lambda e: self._seek_relative(5))

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TButton', background=self.colors['accent'], foreground=self.colors['fg'], padding=8)
        style.map('TButton', background=[('active', self.colors['accent_hover'])])
        style.configure('TScale', background=self.colors['bg'], troughcolor=self.colors['bg_secondary'])
        
        style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'))
        style.configure('SubHeader.TLabel', font=('Segoe UI', 12, 'bold'))
        
        style.configure('Success.TButton', background=self.colors['success'])
        style.configure('Danger.TButton', background=self.colors['error'])
        style.configure('Warning.TButton', background=self.colors['warning'])

    def _build_ui(self):
        self.root.configure(bg=self.colors['bg'])
        
        # Main Layout
        left_panel = ttk.Frame(self.root, width=850)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        right_panel = ttk.Frame(self.root, width=350)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        
        # === Left Panel: Video Player ===
        
        # Header / Load Button
        header = ttk.Frame(left_panel)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, text="📺 Video Player", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(header, text="📂 Load Video...", command=self._load_video).pack(side=tk.RIGHT)
        
        # Video Canvas
        self.canvas_frame = ttk.Frame(left_panel, style='TFrame')  # Container for aspect ratio
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind canvas resize to maintain aspect ratio logic if needed
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        
        # Controls Frame
        controls = ttk.Frame(left_panel)
        controls.pack(fill=tk.X, pady=(10, 0))
        
        # Timeline
        self.time_var = tk.DoubleVar()
        self.timeline = ttk.Scale(controls, from_=0, to=100, variable=self.time_var, command=self._on_seek)
        self.timeline.pack(fill=tk.X, pady=(0, 5))
        
        # Buttons & Time
        btn_box = ttk.Frame(controls)
        btn_box.pack(fill=tk.X)
        
        self.play_btn = ttk.Button(btn_box, text="▶ Play", command=self._toggle_play, width=10)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(btn_box, text="⏪ -5s", command=lambda: self._seek_relative(-5)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_box, text="⏩ +5s", command=lambda: self._seek_relative(5)).pack(side=tk.LEFT, padx=2)
        
        self.time_lbl = ttk.Label(btn_box, text="00:00 / 00:00", font=('Consolas', 10))
        self.time_lbl.pack(side=tk.RIGHT)
        
        # === Right Panel: Tools ===
        
        # Thumbnails Section
        thumb_frame = ttk.LabelFrame(right_panel, text="📸 Thumbnails (Max 5)", padding=10)
        thumb_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Settings Row
        t_settings = ttk.Frame(thumb_frame)
        t_settings.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(t_settings, text="Width:").pack(side=tk.LEFT)
        res_combo = ttk.Combobox(t_settings, textvariable=self.thumb_resolution, 
                                values=["320", "640", "1280", "1920", "Original"], width=8, state="readonly")
        res_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(thumb_frame, text="Capture Current Frame", command=self._capture_frame).pack(fill=tk.X, pady=(0, 10))
        
        # Thumbnail List (Canvas to show images)
        self.thumb_list_frame = tk.Frame(thumb_frame, bg=self.colors['bg_secondary'], height=250)
        self.thumb_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.thumb_list_frame.pack_propagate(False) # Fixed height
        
        # Scrollable container for thumbnails
        self.thumb_canvas = tk.Canvas(self.thumb_list_frame, bg=self.colors['bg_secondary'], highlightthickness=0)
        self.thumb_scrollbar = ttk.Scrollbar(self.thumb_list_frame, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_scroll_frame = ttk.Frame(self.thumb_canvas)
        
        self.thumb_scroll_frame.bind("<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")))
        self.thumb_canvas.create_window((0, 0), window=self.thumb_scroll_frame, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scrollbar.set)
        
        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Clip Preview Section
        clip_frame = ttk.LabelFrame(right_panel, text="🎬 Preview Clips", padding=10)
        clip_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(clip_frame, text="Select Start point & Duration:", foreground=self.colors['fg_secondary']).pack(anchor=tk.W)
        
        clip_controls = ttk.Frame(clip_frame)
        clip_controls.pack(fill=tk.X, pady=5)
        
        ttk.Button(clip_controls, text="Set Start ([)", command=self._set_clip_start, width=12).pack(side=tk.LEFT, padx=(0, 5))
        
        # Duration selection
        ttk.Radiobutton(clip_controls, text="5s", variable=self.clip_duration_sec, value=5).pack(side=tk.LEFT, padx=2)
        ttk.Radiobutton(clip_controls, text="10s", variable=self.clip_duration_sec, value=10).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(clip_controls, text="➕ Add", command=self._add_clip, width=8).pack(side=tk.LEFT, padx=(10, 0))
        
        self.clip_lbl = ttk.Label(clip_frame, text="Range: Not Set", font=('Consolas', 9))
        self.clip_lbl.pack(fill=tk.X, pady=5)
        
        # Clip List
        self.clip_listbox = tk.Listbox(clip_frame, height=4, bg=self.colors['bg_secondary'], fg=self.colors['fg'], borderwidth=0)
        self.clip_listbox.pack(fill=tk.X, pady=(0, 5))
        
        # Context menu for deleting clips
        self.clip_listbox.bind("<Delete>", self._remove_selected_clip)
        self.clip_listbox.bind("<BackSpace>", self._remove_selected_clip)
        
        # Unified Export Section
        export_frame = ttk.LabelFrame(right_panel, text="💾 Export", padding=10)
        export_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(export_frame, text="💾 Export All Data", command=self._export_all_data, style='Success.TButton').pack(fill=tk.X)
        
        # Progress Bar & Status
        self.progress_bar = ttk.Progressbar(export_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        
        self.status_lbl = ttk.Label(export_frame, textvariable=self.status_var, font=('Consolas', 8), foreground=self.colors['fg_secondary'], wraplength=300)
        self.status_lbl.pack(fill=tk.X, pady=(2, 0))


    # --- Video Logic ---
    
    def _get_data_folder(self):
        """Get or create the data folder for current video."""
        if not self.video_path: return None
        video_dir = os.path.dirname(self.video_path)
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        data_dir = os.path.join(video_dir, f"data_{video_name}")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir

    def _load_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mkv *.mov *.avi *.ts")])
        if not path:
            return
            
        self.video_path = path
        self.cap = cv2.VideoCapture(path)
        
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Could not open video file.")
            return
            
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.duration = self.total_frames / self.fps if self.fps > 0 else 0
        
        self.timeline.configure(to=self.total_frames)
        self.current_frame_idx = 0
        
        self._update_time_label()
        self._show_frame()
        self.root.title(f"AQ Video - {os.path.basename(path)}")
        
        # Reset state
        self.thumbnails.clear()
        self.clips.clear()
        self._media_player_reset_clip()
        self._refresh_thumb_list()
        self._refresh_clip_list()

    def _show_frame(self):
        if not self.cap:
            return
            
        ret, frame = self.cap.read()
        if ret:
            # Convert color
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = PIL.Image.fromarray(frame)
            
            # Resize logic (fit to canvas)
            c_width = self.canvas.winfo_width()
            c_height = self.canvas.winfo_height()
            
            if c_width > 1 and c_height > 1:
                # Calculate aspect ratio
                img_ratio = img.width / img.height
                canvas_ratio = c_width / c_height
                
                if canvas_ratio > img_ratio:
                    # Height matches
                    new_height = c_height
                    new_width = int(new_height * img_ratio)
                else:
                    # Width matches
                    new_width = c_width
                    new_height = int(new_width / img_ratio)
                    
                img = img.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)
            
            self.photo = PIL.ImageTk.PhotoImage(image=img)
            self.canvas.delete("all")
            # Center image
            x = c_width // 2
            y = c_height // 2
            self.canvas.create_image(x, y, image=self.photo, anchor=tk.CENTER)

    def _update_video_loop(self):
        """Loop for playing video."""
        if self.is_playing and self.cap:
            self.current_frame_idx += 1  # Simplified, ideally use time delta
            if self.current_frame_idx >= self.total_frames:
                self.is_playing = False
                self.play_btn.config(text="▶ Play")
                return

            # Seek only if we drifted significantly or for efficiency
            # Actually for smooth playback we grab next frame
            # But opencv seek is slow. so we just read next.
            # However we need to sync self.current_frame_idx with cap position
            
            # Reading next frame automatically advances
            self._show_frame()
            
            # Update slider
            self.time_var.set(self.current_frame_idx)
            self._update_time_label()
            
            # Schedule next frame (e.g., 30fps -> 33ms)
            delay = int(1000 / self.fps) if self.fps > 0 else 33
            self.update_job = self.root.after(delay, self._update_video_loop)

    def _toggle_play(self, event=None):
        if not self.cap: return
        
        if self.is_playing:
            self.is_playing = False
            self.play_btn.config(text="▶ Play")
            if self.update_job:
                self.root.after_cancel(self.update_job)
        else:
            self.is_playing = True
            self.play_btn.config(text="⏸ Pause")
            
            # Ensure cap is at current slider pos
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_idx)
            self._update_video_loop()

    def _on_seek(self, val):
        if not self.cap: return
        frame_idx = int(float(val))
        self.current_frame_idx = frame_idx
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        self._show_frame()
        self._update_time_label()

    def _seek_relative(self, seconds):
        if not self.cap: return
        frames_delta = int(seconds * self.fps)
        new_idx = max(0, min(self.total_frames - 1, self.current_frame_idx + frames_delta))
        self.time_var.set(new_idx)
        self._on_seek(new_idx)

    def _on_canvas_resize(self, event):
        # Debounce or just redraw current frame
        if self.cap and not self.is_playing:
            self._show_frame()

    def _update_time_label(self):
        cur_sec = self.current_frame_idx / self.fps if self.fps > 0 else 0
        total_sec = self.duration
        
        def fmt(s):
            m, s = divmod(int(s), 60)
            return f"{m:02d}:{s:02d}"
            
        self.time_lbl.config(text=f"{fmt(cur_sec)} / {fmt(total_sec)}")

    # --- Thumbnail Logic ---
    
    def _capture_frame(self):
        if not self.cap: return
        
        if len(self.thumbnails) >= 5:
            messagebox.showwarning("Limit Reached", "You can only select up to 5 thumbnails.")
            return
            
        # Get current frame logic (reuse show_frame logic largely but save PIL image)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame_idx)
        ret, frame = self.cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = PIL.Image.fromarray(frame_rgb)
            
            # Store original high-res image
            self.thumbnails.append((self.current_frame_idx, img))
            self.thumbnails.sort(key=lambda x: x[0]) # Sort by time
            self._refresh_thumb_list()
            
    def _refresh_thumb_list(self):
        # Clear
        for widget in self.thumb_scroll_frame.winfo_children():
            widget.destroy()
            
        for i, (idx, img) in enumerate(self.thumbnails):
            # Create a row
            row = ttk.Frame(self.thumb_scroll_frame)
            row.pack(fill=tk.X, pady=2, padx=5)
            
            # Thumbnail preview (small)
            thumb_prev = img.copy()
            thumb_prev.thumbnail((80, 45))
            photo = PIL.ImageTk.PhotoImage(thumb_prev)
            
            lbl = ttk.Label(row, image=photo)
            lbl.image = photo # Keep ref
            lbl.pack(side=tk.LEFT)
            
            # Info
            ts_sec = idx / self.fps if self.fps > 0 else 0
            txt = f"#{i+1} @ {ts_sec:.1f}s"
            ttk.Label(row, text=txt).pack(side=tk.LEFT, padx=10)
            
            # Delete btn
            btn = ttk.Button(row, text="❌", width=3, 
                           command=lambda idx=i: self._remove_thumb(idx))
            btn.pack(side=tk.RIGHT)

    def _remove_thumb(self, list_idx):
        if 0 <= list_idx < len(self.thumbnails):
            self.thumbnails.pop(list_idx)
            self._refresh_thumb_list()

    # --- Export Logic ---
        
    def _export_all_data(self):
        """Unified export: Manual Thumbs, 10 Progression Images, and Clips."""
        data_folder = self._get_data_folder()
        if not data_folder: 
            messagebox.showwarning("Error", "No video loaded.")
            return

        # Build summary for confirmation
        summary = []
        summary.append(f"• {len(self.thumbnails)} Manual Thumbnails")
        summary.append(f"• 10 Automated Progression Images (sprite_1-10.jpg)")
        summary.append(f"• {len(self.clips)} Video Clips")
        summary.append(f"\nLocation: {data_folder}")
        
        if not messagebox.askyesno("Export All Data", "Generate the following?\n\n" + "\n".join(summary)):
            return

        # Settings
        target_width = 320 
        res_val = self.thumb_resolution.get()
        if res_val.isdigit():
            target_width = int(res_val)
        elif res_val == "Original":
            target_width = 0

        # Run in thread
        def run_export():
            errors = []
            
            # Tasks: Thumbs + 10 Sprites + Clips
            total_tasks = len(self.thumbnails) + 10 + len(self.clips)
            completed_tasks = 0
            
            def update_progress(msg):
                nonlocal completed_tasks
                completed_tasks += 1
                percent = (completed_tasks / total_tasks) * 100 if total_tasks > 0 else 100
                self.progress_var.set(percent)
                self.status_var.set(msg)
            
            self.progress_var.set(0)
            self.status_var.set("Starting export...")
            
            ffmpeg_cmd = shutil.which("ffmpeg") or "ffmpeg"

            # 1. Manual Thumbnails
            for i, (_, img) in enumerate(self.thumbnails):
                try:
                    self.status_var.set(f"Saving thumb_{i+1}.jpg...")
                    if target_width > 0:
                        ratio = img.height / img.width
                        new_h = int(target_width * ratio)
                        resized = img.resize((target_width, new_h), PIL.Image.Resampling.LANCZOS)
                    else:
                        resized = img
                    
                    save_path = os.path.join(data_folder, f"thumb_{i+1}.jpg")
                    resized.save(save_path, "JPEG", quality=95)
                except Exception as e:
                    errors.append(f"Thumb {i+1}: {e}")
                update_progress(f"Saved thumb_{i+1}")

            # 2. Progression Images (Autogen 10)
            duration = self.duration
            timestamps = [duration * (i + 0.5) / 10 for i in range(10)]
            
            for i, ts in enumerate(timestamps):
                try:
                    self.status_var.set(f"Extracting sprite_{i+1}.jpg...")
                    out_path = os.path.join(data_folder, f"sprite_{i+1}.jpg")
                    cmd = [
                        ffmpeg_cmd, "-ss", str(ts), "-i", self.video_path,
                        "-vframes", "1", "-vf", f"scale={target_width if target_width > 0 else -1}:-1",
                        "-q:v", "2", "-y", out_path
                    ]
                    subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, check=True)
                except Exception as e:
                    errors.append(f"Sprite {i+1}: {e}")
                update_progress(f"Generated sprite_{i+1}")
                
            # 3. Clips
            for i, (start_frame, end_frame) in enumerate(self.clips):
                try:
                    self.status_var.set(f"Exporting preview_{i+1}.mp4...")
                    start_sec = start_frame / self.fps
                    dur = (end_frame - start_frame) / self.fps
                    output_path = os.path.join(data_folder, f"preview_{i+1}.mp4")
                    
                    cmd = [
                        ffmpeg_cmd, "-ss", str(start_sec), "-i", self.video_path,
                        "-t", str(dur), "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-y", output_path
                    ]
                    subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, check=True)
                except Exception as e:
                    errors.append(f"Clip {i+1}: {e}")
                update_progress(f"Exported preview_{i+1}")

            # Completion
            self.progress_var.set(100)
            self.status_var.set("Done.")
            
            msg = "Export Complete!"
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors)
                self.root.after(0, lambda: messagebox.showwarning("Finished with Errors", msg))
            else:
                self.root.after(0, lambda: messagebox.showinfo("Success", msg))
                
            self.root.after(3000, lambda: self.status_var.set(""))

        threading.Thread(target=run_export, daemon=True).start()

    # --- Clip Logic ---

    def _media_player_reset_clip(self):
        self.clip_start = None
        self.clip_lbl.config(text="Range: Not Set")

    def _set_clip_start(self):
        if not self.cap: return
        self.clip_start = self.current_frame_idx
        self._update_clip_label()
        
    def _set_clip_end(self):
        # Removed manual end setting
        pass 

    def _update_clip_label(self):
        s = self.clip_start if self.clip_start is not None else "?"
        dur = self.clip_duration_sec.get()
        
        # Convert to time
        if self.fps > 0:
            s_t = f"{s/self.fps:.1f}s" if isinstance(s, (int, float)) else "?"
        else:
            s_t = str(s)
            
        self.clip_lbl.config(text=f"Start: {s_t} (+{dur}s)")

    def _add_clip(self):
        if self.clip_start is None:
            messagebox.showwarning("Invalid", "Set start point first.")
            return
            
        dur_sec = self.clip_duration_sec.get()
        dur_frames = int(dur_sec * self.fps)
        
        start_frame = self.clip_start
        end_frame = min(self.total_frames, start_frame + dur_frames)
        
        if start_frame >= end_frame:
             messagebox.showwarning("Invalid", "Clip falls outside video duration.")
             return

        self.clips.append((start_frame, end_frame))
        self._refresh_clip_list()
        self._media_player_reset_clip()
        
    def _remove_selected_clip(self, event):
        sel = self.clip_listbox.curselection()
        if sel:
            idx = int(sel[0])
            self.clips.pop(idx)
            self._refresh_clip_list()
            
    def _refresh_clip_list(self):
        self.clip_listbox.delete(0, tk.END)
        for i, (s, e) in enumerate(self.clips):
            s_t = f"{s/self.fps:.1f}s" if self.fps > 0 else s
            e_t = f"{e/self.fps:.1f}s" if self.fps > 0 else e
            dur = (e - s) / self.fps if self.fps > 0 else 0
            self.clip_listbox.insert(tk.END, f"Clip {i+1}: {s_t} - {e_t} ({dur:.1f}s)")



if __name__ == "__main__":
    root = tk.Tk()
    app = ThumbnailMakerApp(root)
    root.mainloop()
