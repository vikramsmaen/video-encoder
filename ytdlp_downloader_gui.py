"""
Universal Video Downloader GUI
Using yt-dlp backend for reliable downloading from any site.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import queue
import threading
from ytdlp_core import YTDLPCore


class VideoDownloaderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🎬 Universal Video Downloader")
        self.root.geometry("900x650")
        self.root.minsize(800, 600)

        # Dark Theme Colors
        self.colors = {
            'bg': '#0f0f1a',
            'bg_secondary': '#1a1a2e',
            'bg_tertiary': '#252542',
            'fg': '#ffffff',
            'fg_secondary': '#9ca3af',
            'accent': '#8b5cf6',
            'success': '#22c55e',
            'error': '#ef4444',
        }

        self.core = YTDLPCore()
        self.core.set_callback(self._on_core_event)
        self.msg_queue = queue.Queue()
        
        self.current_info = None  # Stores {title, formats, url}
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "Videos"))

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
                       padding=(16, 10), font=('Segoe UI', 10, 'bold'))
        style.map('TButton', background=[('active', '#a78bfa'), ('disabled', self.colors['bg_tertiary'])])
        
        style.configure('Primary.TButton', background=self.colors['success'])
        style.map('Primary.TButton', background=[('active', '#16a34a')])
        
        style.configure('Treeview', background=self.colors['bg_secondary'], foreground=self.colors['fg'], 
                       fieldbackground=self.colors['bg_secondary'], rowheight=32, font=('Segoe UI', 10))
        style.configure('Treeview.Heading', background=self.colors['bg_tertiary'], foreground=self.colors['fg'],
                       font=('Segoe UI', 10, 'bold'), padding=8)
        style.map('Treeview', background=[('selected', self.colors['accent'])])
        
        style.configure('TLabelframe', background=self.colors['bg'])
        style.configure('TLabelframe.Label', background=self.colors['bg'], foreground=self.colors['accent'], 
                       font=('Segoe UI', 11, 'bold'))

    def _build_ui(self):
        self.root.configure(bg=self.colors['bg'])
        
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        title_lbl = ttk.Label(main_frame, text="🎬 Universal Video Downloader", 
                             font=('Segoe UI', 20, 'bold'))
        title_lbl.pack(anchor=tk.W, pady=(0, 5))
        
        subtitle_lbl = ttk.Label(main_frame, text="Powered by yt-dlp • Supports 1000+ sites", 
                                foreground=self.colors['fg_secondary'], font=('Segoe UI', 9))
        subtitle_lbl.pack(anchor=tk.W, pady=(0, 20))

        # URL Input
        url_group = ttk.LabelFrame(main_frame, text="📍 Video URL", padding=15)
        url_group.pack(fill=tk.X, pady=(0, 15))

        url_frame = ttk.Frame(url_group)
        url_frame.pack(fill=tk.X)
        
        self.url_entry = ttk.Entry(url_frame, font=('Segoe UI', 11))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.url_entry.bind('<Return>', lambda e: self._analyze())
        
        self.btn_analyze = ttk.Button(url_frame, text="🔍 Analyze", command=self._analyze)
        self.btn_analyze.pack(side=tk.RIGHT)

        # Formats Section
        format_group = ttk.LabelFrame(main_frame, text="📹 Available Formats", padding=15)
        format_group.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        instr_label = ttk.Label(format_group, text="💡 Enter a video URL and click Analyze to see available formats",
                               foreground=self.colors['fg_secondary'])
        instr_label.pack(anchor=tk.W, pady=(0, 10))

        tree_frame = ttk.Frame(format_group)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        cols = ('resolution', 'ext', 'filesize', 'codec', 'note')
        self.tree_formats = ttk.Treeview(tree_frame, columns=cols, show='headings', height=8, selectmode='browse')
        self.tree_formats.heading('resolution', text='Resolution')
        self.tree_formats.heading('ext', text='Format')
        self.tree_formats.heading('filesize', text='Size')
        self.tree_formats.heading('codec', text='Video Codec')
        self.tree_formats.heading('note', text='Note')
        
        self.tree_formats.column('resolution', width=100)
        self.tree_formats.column('ext', width=80)
        self.tree_formats.column('filesize', width=100)
        self.tree_formats.column('codec', width=120)
        self.tree_formats.column('note', width=200)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_formats.yview)
        self.tree_formats.configure(yscrollcommand=scrollbar.set)
        
        self.tree_formats.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Download Options
        options_group = ttk.LabelFrame(main_frame, text="⚙️ Download Options", padding=15)
        options_group.pack(fill=tk.X, pady=(0, 15))

        # Output dir
        dir_frame = ttk.Frame(options_group)
        dir_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(dir_frame, text="Save to:").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(dir_frame, text="📁 Browse", command=self._browse_output).pack(side=tk.RIGHT)

        # Filename
        name_frame = ttk.Frame(options_group)
        name_frame.pack(fill=tk.X)
        
        ttk.Label(name_frame, text="Filename:").pack(side=tk.LEFT, padx=(0, 10))
        self.name_entry = ttk.Entry(name_frame, width=40)
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.name_entry.insert(0, "video")

        # Download Button
        self.btn_download = ttk.Button(main_frame, text="🚀 Download Selected Format", 
                                       command=self._start_download, style='Primary.TButton', state='disabled')
        self.btn_download.pack(fill=tk.X, pady=(0, 15))

        # Progress
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.progress_label = ttk.Label(progress_frame, text="", foreground=self.colors['fg_secondary'])
        self.progress_label.pack(anchor=tk.W)

        # Log
        log_group = ttk.LabelFrame(main_frame, text="📋 Activity Log", padding=10)
        log_group.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_group, height=6, bg=self.colors['bg_secondary'], 
                               fg=self.colors['fg'], font=('Consolas', 9),
                               state='disabled', wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _analyze(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a video URL")
            return
        
        self.btn_analyze.config(state='disabled')
        self.btn_download.config(state='disabled')
        
        # Clear tree
        for item in self.tree_formats.get_children():
            self.tree_formats.delete(item)
        
        threading.Thread(target=self.core.extract_formats, args=(url,), daemon=True).start()

    def _start_download(self):
        selection = self.tree_formats.selection()
        if not selection or not self.current_info:
            messagebox.showwarning("Selection Error", "Please select a format to download")
            return
        
        # Get selected format ID
        item = selection[0]
        values = self.tree_formats.item(item, 'values')
        format_idx = int(self.tree_formats.index(item))
        selected_format = self.current_info['formats'][format_idx]
        format_id = selected_format['id']
        
        filename = self.name_entry.get().strip()
        if not filename:
            filename = "video"
        
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_', '-')).rstrip()
        
        out_dir = self.output_dir.get()
        url = self.current_info['url']
        
        self.btn_download.config(state='disabled')
        self.progress_var.set(0)
        self.progress_label.config(text="Starting download...")
        
        threading.Thread(target=self.core.download_video, 
                        args=(url, format_id, out_dir, filename), daemon=True).start()

    def _browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_dir.set(d)

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
            messagebox.showerror("Error", data)
            self.btn_analyze.config(state='normal')
            self.btn_download.config(state='normal')
        elif event == "formats_extracted":
            self.current_info = data
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, data['title'][:50])  # Use title as default filename
            
            # Populate formats tree
            for fmt in data['formats']:
                size = fmt['filesize'] or fmt['filesize_approx']
                size_str = f"{size / (1024*1024):.1f} MB" if size else "Unknown"
                
                self.tree_formats.insert('', tk.END, values=(
                    fmt['resolution'],
                    fmt['ext'],
                    size_str,
                    fmt['vcodec'],
                    fmt['format_note']
                ))
            
            self.btn_analyze.config(state='normal')
            self.btn_download.config(state='normal')
            self._log(f"✅ Ready to download")
            
        elif event == "download_started":
            self.progress_var.set(0)
            
        elif event == "progress":
            percent = data['percent']
            speed = data['speed']
            self.progress_var.set(percent)
            self.progress_label.config(text=f"Downloading: {percent:.1f}% @ {speed:.1f} MB/s")
            
        elif event == "download_complete":
            self.progress_var.set(100)
            self.progress_label.config(text="Download complete!")
            messagebox.showinfo("Success", f"Video downloaded to:\n{data}")
            self.btn_download.config(state='normal')

    def _log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"> {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')


def main():
    root = tk.Tk()
    app = VideoDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
