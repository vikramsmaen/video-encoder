import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import cv2
import threading
import time
from datetime import datetime
import glob

class BulkSpriteMaker:
    def __init__(self, root):
        self.root = root
        self.root.title("Bulk Sprite Generator")
        self.root.geometry("800x600")
        
        # Colors
        self.colors = {
            'bg': '#0f0f1a',
            'fg': '#ffffff',
            'accent': '#f97316',
            'success': '#22c55e',
            'warning': '#eab308', 
            'error': '#ef4444',
            'dim': '#9ca3af'
        }
        
        self.root.configure(bg=self.colors['bg'])
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._configure_styles()
        
        # State
        self.root_folder = tk.StringVar()
        self.is_running = False
        self.stop_event = threading.Event()
        self.log_queue = []
        
        self.setup_ui()
        
    def _configure_styles(self):
        self.style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        self.style.configure('TFrame', background=self.colors['bg'])
        self.style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'])
        self.style.configure('TButton', background=self.colors['accent'], foreground='white', padding=6)
        self.style.map('TButton', background=[('active', '#fb923c')])
        self.style.configure('Horizontal.TProgressbar', background=self.colors['accent'], troughcolor=self.colors['bg'])
        
    def setup_ui(self):
        main = ttk.Frame(self.root, padding=20)
        main.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = ttk.Label(main, text="🏭 Bulk Sprite Generator", font=('Segoe UI', 18, 'bold'), foreground=self.colors['accent'])
        title.pack(pady=(0, 20))
        
        # Folder Selection
        folder_frame = ttk.Frame(main)
        folder_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Label(folder_frame, text="Root Video Directory:", font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 5))
        
        input_frame = ttk.Frame(folder_frame)
        input_frame.pack(fill=tk.X)
        
        self.entry_path = tk.Entry(input_frame, textvariable=self.root_folder, bg='#1a1a2e', fg='white', insertbackground='white', font=('Consolas', 10))
        self.entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=5)
        
        ttk.Button(input_frame, text="📂 Browse", command=self.browse_folder).pack(side=tk.LEFT)
        
        # Actions
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.btn_start = ttk.Button(btn_frame, text="▶ Start Processing", command=self.start_processing)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 10))
        
        self.btn_stop = ttk.Button(btn_frame, text="⏹ Stop", command=self.stop_processing, state='disabled')
        self.btn_stop.pack(side=tk.LEFT)
        
        # Progress
        progress_frame = ttk.Frame(main)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.status_var, font=('Segoe UI', 9), foreground=self.colors['dim']).pack(anchor='w')
        
        self.progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(5, 0))
        
        # Log
        log_frame = ttk.Frame(main)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(log_frame, text="Activity Log:", font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 5))
        
        self.log_text = tk.Text(log_frame, bg='#1a1a2e', fg='#e2e8f0', font=('Consolas', 9), state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = scrollbar.set

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.root_folder.set(folder)
            
    def log(self, msg, color=None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state='normal')
        
        tag = None
        if color:
            tag = color
            self.log_text.tag_config(color, foreground=color)
            
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.root.update()

    def start_processing(self):
        folder = self.root_folder.get()
        if not folder or not os.path.exists(folder):
            messagebox.showerror("Error", "Please select a valid directory")
            return
            
        self.is_running = True
        self.stop_event.clear()
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.entry_path.config(state='disabled')
        
        threading.Thread(target=self._process_thread, args=(folder,), daemon=True).start()
        
    def stop_processing(self):
        if self.is_running:
            self.stop_event.set()
            self.log("Stopping... please wait for current task to finish.", self.colors['warning'])

    def _process_thread(self, root_folder):
        self.log(f"Scanning for master.m3u8 files in {root_folder}...")
        
        # Recursively find all master.m3u8 files
        targets = []
        for root, dirs, files in os.walk(root_folder):
            if 'master.m3u8' in files:
                targets.append(os.path.join(root, 'master.m3u8'))
        
        total = len(targets)
        self.log(f"Found {total} videos.", self.colors['accent'])
        
        processed = 0
        skipped = 0
        errors = 0
        
        for i, m3u8_path in enumerate(targets):
            if self.stop_event.is_set():
                break
                
            video_dir = os.path.dirname(m3u8_path)
            video_name = os.path.basename(video_dir)
            
            # Sanitized folder name for data
            # Logic: data_ + sanitized(video_name)
            # Replace spaces and dots with underscores to match R2 Uploader strict logic
            sanitized_name = video_name.replace(" ", "_").replace(".", "_")
            data_folder_name = f"data_{sanitized_name}"
            data_path = os.path.join(video_dir, data_folder_name)
            
            # --- CONSOLIDATION LOGIC ---
            # Check for ANY existing data folders (legacy names, non-sanitized, etc.)
            existing_data_folders = []
            try:
                for item in os.listdir(video_dir):
                    full_item = os.path.join(video_dir, item)
                    if os.path.isdir(full_item) and item.startswith("data_"):
                        existing_data_folders.append(item)
            except: pass

            # If we have existing data folders, we want to consolidate them into 'data_path'
            if existing_data_folders:
                # If the canonical path already exists, use it as base.
                # If not, rename the first available one to canonical.
                
                target_exists = data_folder_name in existing_data_folders
                
                if not target_exists:
                    # Rename the first found legacy folder to the new canonical name
                    first_legacy = existing_data_folders[0]
                    src = os.path.join(video_dir, first_legacy)
                    try:
                        self.log(f"Renaming {first_legacy} -> {data_folder_name}", self.colors['warning'])
                        os.rename(src, data_path)
                        # Update our list: we now have the target
                        existing_data_folders.remove(first_legacy)
                        target_exists = True
                    except Exception as e:
                        self.log(f"Rename failed: {e}", self.colors['error'])
                
                # Now, if there are ANY OTHER data folders (duplicates), move content and delete
                if target_exists:
                    for folder in existing_data_folders:
                        if folder == data_folder_name:
                            continue
                            
                        # Move contents to canonical
                        src_dir = os.path.join(video_dir, folder)
                        try:
                            self.log(f"Merging {folder} into {data_folder_name}...", self.colors['warning'])
                            for item in os.listdir(src_dir):
                                s = os.path.join(src_dir, item)
                                d = os.path.join(data_path, item)
                                if os.path.isfile(s):
                                    # Overwrite if exists
                                    if os.path.exists(d):
                                        os.remove(d)
                                    os.rename(s, d)
                            # Remove empty dir
                            os.rmdir(src_dir)
                        except Exception as e:
                            self.log(f"Merge error: {e}", self.colors['error'])

            # Proceed to generate sprites (Overwrite existing sprites if needed)
            try:
                self.log(f"Processing: {video_name}")
                os.makedirs(data_path, exist_ok=True)
                
                # Generate Sprites
                self._generate_sprites(m3u8_path, data_path)
                
                processed += 1
                self.log(f"✅ Generated sprites for {video_name}", self.colors['success'])
                
            except Exception as e:
                self.log(f"❌ Error {video_name}: {e}", self.colors['error'])
                errors += 1
                # Cleanup empty folder if failed?
                try: 
                    if os.path.exists(data_path) and not os.listdir(data_path):
                        os.rmdir(data_path)
                except: pass
            
            self._update_progress(i + 1, total, f"Processed {processed}/{total}")
        
        self.is_running = False
        self.root.after(0, self._reset_ui)
        self.log("------------------------------------------------")
        self.log(f"Job Complete. Processed: {processed}, Skipped: {skipped}, Errors: {errors}", self.colors['success'])

    def _update_progress(self, current, total, status_text):
        self.root.after(0, lambda: self._do_update_progress(current, total, status_text))
        
    def _do_update_progress(self, current, total, status_text):
        pct = (current / total) * 100
        self.status_var.set(f"{status_text} ({int(pct)}%)")
        self.progress['value'] = pct

    def _reset_ui(self):
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.entry_path.config(state='normal')
        self.status_var.set("Ready")
        self.progress['value'] = 0

    def _generate_sprites(self, video_path, output_folder):
        """Extract 10 evenly spaced frames."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("Could not open video file (cv2)")
            
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            # Fallback for m3u8 if OpenCV fails to read duration
            # Try to read matching .mp4 in the same folder?
            # Or assume a fixed number of frames? No.
            # Usually HLS m3u8 in OpenCV works if ffmpeg backend is active.
            # If 0, we can't seek percentages.
            cap.release()
            raise Exception("Could not determine frame count")
            
        # 10 frames from 5% to 95% to avoid black start/end
        # Or 0% to 90%? User said "10 images as per duration".
        # Let's do 10 evenly spaced points: 0, 10, ... 90%?
        # Or better: interval = duration / 10. timestamps: 0.5*interval, 1.5*interval...
        # Let's stick to 10 evenly spaced.
        
        indices = [int(total_frames * (i / 10)) for i in range(10)]
        
        count = 0
        for i, frame_idx in enumerate(indices):
            if self.stop_event.is_set():
                break
                
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                # Resize maintain aspect ratio, height 240px
                h, w = frame.shape[:2]
                target_h = 240
                target_w = int(w * (target_h / h))
                
                resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                
                # Save: sprite_1.jpg to sprite_10.jpg
                # Filename: sprite_{i+1}.jpg match (1-10) or (0-9)?
                # thumbnail_maker used `sprite_{i}.jpg`. User might prefer 1-based.
                # Let's match thumbnail_maker style if possible. 
                # thumbnail_maker logic: `save_path = ... / f"sprite_{i}.jpg"` (0-based loops usually). 
                # Wait, earlier 'r2_uploader' parsed `sprite_{index}`.
                # Let's use 1-based for humans, but 0-based is fine too. 
                # User request: "sprite_1.jpg to sprite_10.jpg" (implied in previous plan)
                # Let's use 1-based.
                
                out_name = f"sprite_{i+1}.jpg"
                out_path = os.path.join(output_folder, out_name)
                
                cv2.imwrite(out_path, resized, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                count += 1
            else:
                pass
                
        cap.release()
        
        if count == 0:
            raise Exception("No frames extracted")

if __name__ == "__main__":
    root = tk.Tk()
    app = BulkSpriteMaker(root)
    root.mainloop()
