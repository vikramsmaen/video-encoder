"""
Bulk Video Downloader GUI
Download multiple videos with individual format selection.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import os
import queue
import threading
from ytdlp_core import YTDLPCore


class BulkDownloaderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🎬 Bulk Video Downloader")
        self.root.geometry("1100x750")
        self.root.minsize(1000, 700)

        # Dark Theme
        self.colors = {
            'bg': '#0f0f1a',
            'bg_secondary': '#1a1a2e',
            'bg_tertiary': '#252542',
            'fg': '#ffffff',
            'fg_secondary': '#9ca3af',
            'accent': '#8b5cf6',
            'success': '#22c55e',
            'warning': '#f59e0b',
            'error': '#ef4444',
        }

        self.core = YTDLPCore()
        self.core.set_callback(self._on_core_event)
        self.msg_queue = queue.Queue()
        
        self.video_queue = []  # List of {url, title, formats, selected_format_idx, status}
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "Videos"))
        self.currently_analyzing_idx = None
        self.currently_downloading = False

        self._configure_styles()
        self._build_ui()
        self._process_messages()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'], font=('Segoe UI', 10))
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TEntry', fieldbackground=self.colors['bg_secondary'], foreground=self.colors['fg'], 
                       insertcolor=self.colors['fg'], padding=8)
        style.configure('TButton', background=self.colors['accent'], foreground=self.colors['fg'], 
                       padding=(12, 8), font=('Segoe UI', 10, 'bold'))
        style.map('TButton', background=[('active', '#a78bfa'), ('disabled', self.colors['bg_tertiary'])])
        
        style.configure('Primary.TButton', background=self.colors['success'])
        style.map('Primary.TButton', background=[('active', '#16a34a')])
        
        style.configure('Treeview', background=self.colors['bg_secondary'], foreground=self.colors['fg'], 
                       fieldbackground=self.colors['bg_secondary'], rowheight=28, font=('Segoe UI', 9))
        style.configure('Treeview.Heading', background=self.colors['bg_tertiary'], foreground=self.colors['fg'],
                       font=('Segoe UI', 10, 'bold'), padding=6)
        style.map('Treeview', background=[('selected', self.colors['accent'])])
        
        style.configure('TLabelframe', background=self.colors['bg'])
        style.configure('TLabelframe.Label', background=self.colors['bg'], foreground=self.colors['accent'], 
                       font=('Segoe UI', 11, 'bold'))

    def _build_ui(self):
        self.root.configure(bg=self.colors['bg'])
        
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        title_lbl = ttk.Label(main_frame, text="🎬 Bulk Video Downloader", 
                             font=('Segoe UI', 18, 'bold'))
        title_lbl.pack(anchor=tk.W, pady=(0, 3))
        
        subtitle_lbl = ttk.Label(main_frame, text="Download up to 10 videos • Powered by yt-dlp", 
                                foreground=self.colors['fg_secondary'], font=('Segoe UI', 9))
        subtitle_lbl.pack(anchor=tk.W, pady=(0, 15))

        # URL Input
        url_group = ttk.LabelFrame(main_frame, text="📍 Video URLs (One per line, max 10)", padding=12)
        url_group.pack(fill=tk.X, pady=(0, 12))

        self.url_text = scrolledtext.ScrolledText(url_group, height=5, bg=self.colors['bg_secondary'],
                                                   fg=self.colors['fg'], font=('Consolas', 10),
                                                   insertbackground=self.colors['fg'], wrap=tk.WORD)
        self.url_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        btn_frame = ttk.Frame(url_group)
        btn_frame.pack(fill=tk.X)
        
        self.btn_add = ttk.Button(btn_frame, text="➕ Add to Queue", command=self._add_to_queue)
        self.btn_add.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(btn_frame, text="🗑️ Clear Queue", command=self._clear_queue).pack(side=tk.LEFT)

        # Video Queue
        queue_group = ttk.LabelFrame(main_frame, text="📋 Download Queue", padding=12)
        queue_group.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        tree_frame = ttk.Frame(queue_group)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        cols = ('#', 'title', 'resolution', 'status')
        self.tree_queue = ttk.Treeview(tree_frame, columns=cols, show='headings', height=10, selectmode='browse')
        self.tree_queue.heading('#', text='#')
        self.tree_queue.heading('title', text='Title')
        self.tree_queue.heading('resolution', text='Selected Resolution')
        self.tree_queue.heading('status', text='Status')
        
        self.tree_queue.column('#', width=40, anchor='center')
        self.tree_queue.column('title', width=400)
        self.tree_queue.column('resolution', width=150)
        self.tree_queue.column('status', width=200)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_queue.yview)
        self.tree_queue.configure(yscrollcommand=scrollbar.set)
        
        self.tree_queue.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree_queue.bind('<Double-1>', self._on_queue_double_click)

        # Control buttons
        control_frame = ttk.Frame(queue_group)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(control_frame, text="💡 Double-click a video to select resolution",
                 foreground=self.colors['fg_secondary'], font=('Segoe UI', 9)).pack(side=tk.LEFT)
        
        ttk.Button(control_frame, text="📁 Set Output Folder", 
                  command=self._browse_output).pack(side=tk.RIGHT, padx=(10, 0))
        
        self.output_label = ttk.Label(control_frame, text=f"→ {self.output_dir.get()}", 
                                      foreground=self.colors['fg_secondary'], font=('Segoe UI', 9))
        self.output_label.pack(side=tk.RIGHT)

        # Download Button
        self.btn_download_all = ttk.Button(main_frame, text="🚀 Download All Videos", 
                                          command=self._start_bulk_download, style='Primary.TButton',
                                          state='disabled')
        self.btn_download_all.pack(fill=tk.X, pady=(0, 12))

        # Progress
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 12))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 4))
        
        self.progress_label = ttk.Label(progress_frame, text="", foreground=self.colors['fg_secondary'])
        self.progress_label.pack(anchor=tk.W)

        # Log
        log_group = ttk.LabelFrame(main_frame, text="📋 Activity Log", padding=8)
        log_group.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_group, height=6, bg=self.colors['bg_secondary'], 
                               fg=self.colors['fg'], font=('Consolas', 9),
                               state='disabled', wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _add_to_queue(self):
        urls_text = self.url_text.get('1.0', tk.END).strip()
        if not urls_text:
            messagebox.showwarning("Input Error", "Please enter at least one URL")
            return
        
        urls = [u.strip() for u in urls_text.split('\n') if u.strip()]
        
        if len(self.video_queue) + len(urls) > 10:
            messagebox.showwarning("Queue Full", "Maximum 10 videos allowed in queue")
            return
        
        self.btn_add.config(state='disabled')
        self._log(f"📥 Adding {len(urls)} video(s) to queue...")
        
        # Add URLs to queue and start analyzing
        for url in urls:
            video_entry = {
                'url': url,
                'title': 'Analyzing...',
                'formats': None,
                'selected_format_idx': None,
                'status': 'Analyzing...'
            }
            self.video_queue.append(video_entry)
        
        self._refresh_queue_display()
        self._analyze_next_video()

    def _analyze_next_video(self):
        """Analyze the next video that needs analysis."""
        for idx, video in enumerate(self.video_queue):
            if video['formats'] is None and video['status'] == 'Analyzing...':
                self.currently_analyzing_idx = idx
                threading.Thread(target=self.core.extract_formats, args=(video['url'],), daemon=True).start()
                return
        
        # All analyzed
        self.currently_analyzing_idx = None
        self.btn_add.config(state='normal')
        self._log("✅ All videos analyzed. Double-click to select resolutions.")
        self._check_ready_to_download()

    def _on_queue_double_click(self, event):
        """Open format selection dialog for selected video."""
        selection = self.tree_queue.selection()
        if not selection:
            return
        
        idx = int(self.tree_queue.index(selection[0]))
        video = self.video_queue[idx]
        
        if not video['formats']:
            messagebox.showinfo("No Formats", "This video is still being analyzed or failed")
            return
        
        self._show_format_selector(idx)

    def _show_format_selector(self, video_idx):
        """Show dialog to select format for a specific video."""
        video = self.video_queue[video_idx]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Select Resolution - {video['title'][:50]}")
        dialog.geometry("700x500")
        dialog.configure(bg=self.colors['bg'])
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text=f"📹 {video['title']}", font=('Segoe UI', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))

        # Formats list
        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        cols = ('resolution', 'ext', 'filesize', 'codec')
        tree = ttk.Treeview(tree_frame, columns=cols, show='headings', height=12, selectmode='browse')
        tree.heading('resolution', text='Resolution')
        tree.heading('ext', text='Format')
        tree.heading('filesize', text='Size')
        tree.heading('codec', text='Video Codec')
        
        tree.column('resolution', width=120)
        tree.column('ext', width=80)
        tree.column('filesize', width=100)
        tree.column('codec', width=150)
        
        for fmt in video['formats']:
            size = fmt['filesize'] or fmt['filesize_approx']
            size_str = f"{size / (1024*1024):.1f} MB" if size else "Unknown"
            
            tree.insert('', tk.END, values=(
                fmt['resolution'],
                fmt['ext'],
                size_str,
                fmt['vcodec']
            ))
        
        # Select current if any
        if video['selected_format_idx'] is not None:
            tree.selection_set(tree.get_children()[video['selected_format_idx']])
            tree.see(tree.get_children()[video['selected_format_idx']])
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X)
        
        def on_confirm():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a format")
                return
            
            selected_idx = tree.index(selection[0])
            video['selected_format_idx'] = selected_idx
            video['status'] = 'Ready'
            self._refresh_queue_display()
            self._check_ready_to_download()
            dialog.destroy()
        
        ttk.Button(btn_frame, text="✓ Confirm", command=on_confirm, style='Primary.TButton').pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

    def _start_bulk_download(self):
        if self.currently_downloading:
            return
        
        self.currently_downloading = True
        self.btn_download_all.config(state='disabled')
        self._log(f"🚀 Starting bulk download of {len(self.video_queue)} videos...")
        
        threading.Thread(target=self._download_all_worker, daemon=True).start()

    def _download_all_worker(self):
        """Download all videos in queue."""
        total = len(self.video_queue)
        
        for idx, video in enumerate(self.video_queue):
            if video['status'] != 'Ready':
                continue
            
            self._update_video_status(idx, 'Downloading...')
            self._log(f"[{idx+1}/{total}] {video['title'][:50]}...")
            
            # Create safe filename
            safe_title = "".join(c for c in video['title'] if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
            filename = f"{idx+1}_{safe_title[:50]}"
            
            # Get selected format
            selected_format = video['formats'][video['selected_format_idx']]
            format_id = selected_format['id']
            
            # Download (synchronous in this thread)
            try:
                self.core.download_video(video['url'], format_id, self.output_dir.get(), filename)
                # Wait for completion signal
                while video['status'] == 'Downloading...':
                    import time
                    time.sleep(0.1)
            except Exception as e:
                self._update_video_status(idx, f'Failed: {str(e)[:30]}')
        
        self.currently_downloading = False
        self._log("🎉 Bulk download complete!")
        messagebox.showinfo("Complete", f"Downloaded {total} videos to:\n{self.output_dir.get()}")

    def _browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_dir.set(d)
            self.output_label.config(text=f"→ {d}")

    def _clear_queue(self):
        if messagebox.askyesno("Clear Queue", "Remove all videos from queue?"):
            self.video_queue.clear()
            self._refresh_queue_display()
            self.btn_download_all.config(state='disabled')

    def _refresh_queue_display(self):
        """Refresh the queue treeview."""
        for item in self.tree_queue.get_children():
            self.tree_queue.delete(item)
        
        for idx, video in enumerate(self.video_queue):
            resolution_text = "Not selected"
            if video['selected_format_idx'] is not None and video['formats']:
                fmt = video['formats'][video['selected_format_idx']]
                resolution_text = fmt['resolution']
            
            self.tree_queue.insert('', tk.END, values=(
                idx + 1,
                video['title'][:60],
                resolution_text,
                video['status']
            ))

    def _update_video_status(self, idx, status):
        """Update status of a specific video."""
        self.video_queue[idx]['status'] = status
        self._refresh_queue_display()

    def _check_ready_to_download(self):
        """Check if all videos are ready to download."""
        if not self.video_queue:
            self.btn_download_all.config(state='disabled')
            return
        
        all_ready = all(v['status'] == 'Ready' for v in self.video_queue)
        if all_ready:
            self.btn_download_all.config(state='normal')

    def _on_core_event(self, event, data):
        self.msg_queue.put((event, data))

    def _process_messages(self):
        try:
            while True:
                event, data = self.msg_queue.get_nowait()
                self._handle_event(event, data)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_messages)

    def _handle_event(self, event, data):
        if event == "log":
            self._log(data)
        elif event == "error":
            self._log(f"❌ {data}")
            if self.currently_analyzing_idx is not None:
                self._update_video_status(self.currently_analyzing_idx, 'Failed')
                self._analyze_next_video()
        elif event == "formats_extracted":
            if self.currently_analyzing_idx is not None:
                video = self.video_queue[self.currently_analyzing_idx]
                video['title'] = data['title']
                video['formats'] = data['formats']
                video['status'] = 'Needs resolution'
                self._refresh_queue_display()
                self._analyze_next_video()
        elif event == "download_started":
            pass
        elif event == "progress":
            percent = data['percent']
            speed = data['speed']
            self.progress_var.set(percent)
            self.progress_label.config(text=f"Downloading: {percent:.1f}% @ {speed:.1f} MB/s")
        elif event == "download_complete":
            # Find which video just completed and update its status
            for idx, video in enumerate(self.video_queue):
                if video['status'] == 'Downloading...':
                    self._update_video_status(idx, 'Downloaded')
                    break
            self.progress_var.set(0)

    def _log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"> {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')


def main():
    root = tk.Tk()
    app = BulkDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
