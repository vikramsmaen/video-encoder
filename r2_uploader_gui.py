import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
from dotenv import load_dotenv
from queue import Empty
import queue
from datetime import datetime

from r2_uploader_core import R2Core, UploadStatus

load_dotenv()


class R2UploaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("R2 Smart Uploader")
        self.root.geometry("1000x650")
        self.root.minsize(800, 550)

        # Colors
        self.colors = {
            'bg': '#0f0f1a',
            'bg_card': '#1a1a2e',
            'fg': '#ffffff',
            'fg_dim': '#9ca3af',
            'accent': '#f97316',
            'success': '#22c55e',
            'warning': '#eab308',
            'error': '#ef4444',
        }
        self._configure_styles()
        self.root.configure(bg=self.colors['bg'])

        # State
        self.watched_folders = set()
        self.queue_map = {}
        self.msg_queue = queue.Queue()

        # Core
        self.core = R2Core(
            os.getenv("R2_ENDPOINT_URL", ""),
            os.getenv("R2_ACCESS_KEY_ID", ""),
            os.getenv("R2_SECRET_ACCESS_KEY", ""),
            os.getenv("R2_BUCKET_NAME", "")
        )
        self.core.set_callback(self._on_event)

        self._build_ui()
        
        try:
            self.core.start()
        except Exception as e:
            self.log(f"Error: {e}")

        self.root.after(100, self._process_messages)
        self.root.after(500, self._update_stats)

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TButton', background=self.colors['accent'], foreground='white', padding=6)
        style.map('TButton', background=[('active', '#fb923c')])
        
        style.configure('Treeview', background='#1a1a2e', foreground='#fff', fieldbackground='#1a1a2e', rowheight=26)
        style.configure('Treeview.Heading', background='#252540', foreground='#fff', font=('Segoe UI', 9, 'bold'))
        style.map('Treeview', background=[('selected', '#f97316')])
        
        style.configure('TNotebook', background=self.colors['bg'])
        style.configure('TNotebook.Tab', background='#252540', foreground='#fff', padding=[10, 4])
        style.map('TNotebook.Tab', background=[('selected', '#f97316')])

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        # Header
        header = ttk.Frame(main)
        header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(header, text="☁️ R2 Uploader", font=('Segoe UI', 16, 'bold'), foreground=self.colors['accent']).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side=tk.RIGHT)
        self.btn_pause = ttk.Button(btn_frame, text="⏸ Pause", command=self._toggle_pause, width=10)
        self.btn_pause.pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="⏹ Stop", command=self.core.stop, width=8).pack(side=tk.LEFT)
        
        self.status_lbl = ttk.Label(header, text="● Ready", foreground=self.colors['success'])
        self.status_lbl.pack(side=tk.RIGHT, padx=15)

        # Stats Row
        stats = ttk.Frame(main)
        stats.pack(fill=tk.X, pady=(0, 10))
        
        self.stat_labels = {}
        for key, title in [('progress', 'Progress'), ('speed', 'Speed'), ('eta', 'ETA')]:
            f = tk.Frame(stats, bg=self.colors['bg_card'], padx=15, pady=8)
            f.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=3)
            tk.Label(f, text=title, font=('Segoe UI', 9), fg=self.colors['fg_dim'], bg=self.colors['bg_card']).pack(anchor='w')
            lbl = tk.Label(f, text="--", font=('Segoe UI', 18, 'bold'), fg=self.colors['fg'], bg=self.colors['bg_card'])
            lbl.pack(anchor='w')
            self.stat_labels[key] = lbl

        # Content
        content = ttk.Frame(main)
        content.pack(fill=tk.BOTH, expand=True)

        # Left: Watch folders
        left = ttk.Frame(content, width=220)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)
        
        ttk.Label(left, text="📂 Watch Folders", font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        
        self.watch_list = tk.Listbox(left, bg='#1a1a2e', fg='#fff', bd=0, highlightthickness=0, font=('Segoe UI', 9))
        self.watch_list.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        btn_row = ttk.Frame(left)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="+ Add", command=self._add_folder, width=8).pack(side=tk.LEFT, expand=True, padx=(0, 2))
        ttk.Button(btn_row, text="- Remove", command=self._remove_folder, width=8).pack(side=tk.LEFT, expand=True)

        # Right: Tabs
        right = ttk.Frame(content)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.nb = ttk.Notebook(right)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Queue Tab
        queue_tab = ttk.Frame(self.nb)
        self.nb.add(queue_tab, text="📋 Queue")
        
        toolbar = ttk.Frame(queue_tab)
        toolbar.pack(fill=tk.X, pady=5)
        ttk.Button(toolbar, text="🗑️ Clear Done", command=self._clear_done).pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="🔄 Reset", command=self._reset).pack(side=tk.RIGHT, padx=5)
        
        self.tree = ttk.Treeview(queue_tab, columns=('status', 'file', 'type'), show='headings', selectmode='none')
        self.tree.heading('status', text='Status')
        self.tree.heading('file', text='File')
        self.tree.heading('type', text='Type')
        self.tree.column('status', width=120)
        self.tree.column('file', width=300)
        self.tree.column('type', width=80)
        
        self.tree.tag_configure('completed', foreground=self.colors['success'])
        self.tree.tag_configure('skipped', foreground=self.colors['warning'])
        self.tree.tag_configure('failed', foreground=self.colors['error'])
        self.tree.tag_configure('uploading', foreground=self.colors['accent'])
        
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Log Tab
        log_tab = ttk.Frame(self.nb)
        self.nb.add(log_tab, text="📝 Log")
        
        self.log_text = tk.Text(log_tab, bg='#1a1a2e', fg='#fff', font=('Consolas', 9), state='disabled', wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # R2 Browser Tab
        r2_tab = ttk.Frame(self.nb)
        self.nb.add(r2_tab, text="☁️ R2 Browser")
        
        r2_toolbar = ttk.Frame(r2_tab)
        r2_toolbar.pack(fill=tk.X, pady=5)
        ttk.Button(r2_toolbar, text="🔍 Check R2", command=self._check_r2).pack(side=tk.LEFT, padx=(0, 5))

        self.r2_status = ttk.Label(r2_toolbar, text="Click to scan R2 bucket", foreground=self.colors['fg_dim'])
        self.r2_status.pack(side=tk.LEFT, padx=10)
        
        # R2 info display
        self.r2_info = tk.Text(r2_tab, bg='#1a1a2e', fg='#fff', font=('Consolas', 10), state='disabled', wrap=tk.WORD)
        self.r2_info.pack(fill=tk.BOTH, expand=True)

    def _update_stats(self):
        try:
            s = self.core.get_stats()
            
            # Progress
            done = s.get('done', 0)
            total = s.get('total', 0)
            self.stat_labels['progress'].config(text=f"{done} / {total}")
            
            # Speed
            if s.get('is_paused'):
                self.stat_labels['speed'].config(text="Paused", fg=self.colors['warning'])
            else:
                speed_mb = s.get('speed', 0) / (1024 * 1024)
                self.stat_labels['speed'].config(text=f"{speed_mb:.1f} MB/s", fg=self.colors['success'] if speed_mb > 1 else self.colors['fg'])
            
            # ETA
            eta = s.get('eta', 0)
            if eta > 60:
                self.stat_labels['eta'].config(text=f"{int(eta // 60)}m {int(eta % 60)}s")
            elif eta > 0:
                self.stat_labels['eta'].config(text=f"{int(eta)}s")
            else:
                self.stat_labels['eta'].config(text="--")
                
        except:
            pass
        
        self.root.after(500, self._update_stats)

    def _on_event(self, event_type, data):
        self.msg_queue.put((event_type, data))

    def _process_messages(self):
        try:
            for _ in range(50):
                event_type, data = self.msg_queue.get_nowait()
                self._handle_event(event_type, data)
        except Empty:
            pass
        self.root.after(100, self._process_messages)

    def _handle_event(self, event_type, data):
        if event_type == "log":
            self.log(data)
        elif event_type == "watch_added":
            self.watch_list.insert(tk.END, data)
            self.watched_folders.add(data)
        elif event_type == "watch_removed":
            self.watch_list.delete(0, tk.END)
            for f in self.watched_folders - {data}:
                self.watch_list.insert(tk.END, f)
            self.watched_folders.discard(data)
        elif event_type == "status_change":
            color = self.colors['success'] if data == "Running" else self.colors['warning']
            self.status_lbl.config(text=f"● {data}", foreground=color)
            if data == "Paused":
                self.btn_pause.config(text="▶ Resume")
            else:
                self.btn_pause.config(text="⏸ Pause")
        elif event_type == "queue_added":
            filename = os.path.basename(data['file_path'])
            ftype = "Video" if filename.endswith('master.m3u8') else "Segment"
            item_id = self.tree.insert('', 0, values=("Pending", filename, ftype))
            self.queue_map[data['id']] = item_id
        elif event_type == "upload_progress":
            item_id = self.queue_map.get(data['id'])
            if item_id and self.tree.exists(item_id):
                status = data['status']
                tag = ''
                if 'Completed' in str(status):
                    tag = 'completed'
                elif 'Skipped' in str(status):
                    tag = 'skipped'
                elif 'Failed' in str(status):
                    tag = 'failed'
                elif 'Uploading' in str(status):
                    tag = 'uploading'
                
                vals = list(self.tree.item(item_id, 'values'))
                vals[0] = status
                self.tree.item(item_id, values=vals, tags=(tag,))

    def _toggle_pause(self):
        if self.core.is_paused:
            self.core.resume()
        else:
            self.core.pause()

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def _clear_done(self):
        for item in self.tree.get_children():
            tags = self.tree.item(item, 'tags')
            if tags and (tags[0] in ['completed', 'skipped']):
                self.tree.delete(item)

    def _reset(self):
        self.core.reset_stats()
        self.tree.delete(*self.tree.get_children())
        self.queue_map.clear()

    def _add_folder(self):
        path = filedialog.askdirectory(title="Select Folder")
        if path:
            parent = os.path.dirname(path)
            self.core.add_watch_folder(path, parent)

    def _remove_folder(self):
        sel = self.watch_list.curselection()
        if sel:
            path = self.watch_list.get(sel[0])
            self.core.remove_watch_folder(path)

    def _check_r2(self):
        """Check R2 bucket and show file counts."""
        self.r2_status.config(text="Scanning R2...", foreground=self.colors['warning'])
        self.root.update()
        
        threading.Thread(target=self._do_check_r2, daemon=True).start()


    
    def _do_check_r2(self):
        """Background R2 scan."""
        try:
            s3 = self.core.s3_client
            bucket = self.core.bucket_name
            
            # Count all files and group by top-level folder
            total_count = 0
            total_size = 0
            folders = {}
            
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    size = obj.get('Size', 0)
                    total_count += 1
                    total_size += size
                    
                    # Get top-level folder
                    parts = key.split('/')
                    folder = parts[0] if len(parts) > 1 else "(root)"
                    if folder not in folders:
                        folders[folder] = {'count': 0, 'size': 0}
                    folders[folder]['count'] += 1
                    folders[folder]['size'] += size
            
            # Format results
            result = f"═══════════════════════════════════════\n"
            result += f"  R2 BUCKET: {bucket}\n"
            result += f"═══════════════════════════════════════\n\n"
            result += f"  TOTAL FILES: {total_count:,}\n"
            result += f"  TOTAL SIZE:  {total_size / (1024*1024*1024):.2f} GB\n\n"
            result += f"───────────────────────────────────────\n"
            result += f"  FOLDERS:\n"
            result += f"───────────────────────────────────────\n\n"
            
            for folder, data in sorted(folders.items(), key=lambda x: -x[1]['count']):
                size_mb = data['size'] / (1024 * 1024)
                result += f"  📁 {folder}\n"
                result += f"     Files: {data['count']:,}  |  Size: {size_mb:.1f} MB\n\n"
            
            # Update UI on main thread
            self.root.after(0, lambda: self._show_r2_results(result, total_count))
            
        except Exception as e:
            self.root.after(0, lambda: self._show_r2_results(f"Error: {e}", 0))
    
    def _show_r2_results(self, text, count):
        """Display R2 results."""
        self.r2_status.config(text=f"Found {count:,} files in R2", foreground=self.colors['success'])
        self.r2_info.config(state='normal')
        self.r2_info.delete(1.0, tk.END)
        self.r2_info.insert(tk.END, text)
        self.r2_info.config(state='disabled')

    def _sync_all_to_convex(self):
        """Sync all videos in R2 to Convex."""
        self.r2_status.config(text="Finding videos in R2...", foreground=self.colors['warning'])
        self.root.update()
        threading.Thread(target=self._do_sync_to_convex, daemon=True).start()
    
    def _do_sync_to_convex(self):
        """Background sync to Convex."""
        try:
            s3 = self.core.s3_client
            bucket = self.core.bucket_name
            
            # Find all master.m3u8 files (one per video)
            videos = []
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get('Contents', []):
                    if obj['Key'].endswith('master.m3u8'):
                        videos.append(obj['Key'])
            
            self.root.after(0, lambda: self.r2_status.config(
                text=f"Syncing {len(videos)} videos to Convex...", 
                foreground=self.colors['warning']
            ))
            
            synced = 0
            failed = 0
            
            for key in videos:
                result = self.core.trigger_convex_webhook(key)
                if result:
                    synced += 1
                else:
                    failed += 1
            
            msg = f"✅ Synced {synced} videos"
            if failed > 0:
                msg += f" (❌ {failed} failed)"
            
            self.root.after(0, lambda: self.r2_status.config(text=msg, foreground=self.colors['success']))
            self.root.after(0, lambda: self.log(msg))
            
        except Exception as e:
            self.root.after(0, lambda: self.r2_status.config(text=f"Error: {e}", foreground=self.colors['error']))


if __name__ == "__main__":
    root = tk.Tk()
    app = R2UploaderApp(root)
    root.mainloop()
