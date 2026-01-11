import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import queue
import threading
from hls_downloader_core import HLSDownloaderCore

class HLSDownloaderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HLS Video Downloader")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        # Dark Theme Colors
        self.colors = {
            'bg': '#1e1e2e',
            'bg_secondary': '#2d2d3f',
            'bg_tertiary': '#3d3d5a',
            'fg': '#ffffff',
            'fg_secondary': '#b4b4b4',
            'accent': '#7c3aed',  # Purple accent
            'success': '#22c55e',
            'error': '#ef4444',
            'border': '#4a4a6a'
        }

        self.core = HLSDownloaderCore()
        self.core.set_callback(self._on_core_event)
        self.msg_queue = queue.Queue()
        
        self.streams = []
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "HLS_Downloads"))
        self.merge_var = tk.BooleanVar(value=True)

        self._configure_styles()
        self._build_ui()
        self._process_messages()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TEntry', fieldbackground=self.colors['bg_secondary'], foreground=self.colors['fg'], insertcolor=self.colors['fg'])
        style.configure('TButton', background=self.colors['accent'], foreground=self.colors['fg'], padding=8)
        style.map('TButton', background=[('active', '#8b5cf6')])
        
        style.configure('Treeview', 
                        background=self.colors['bg_secondary'], 
                        foreground=self.colors['fg'], 
                        fieldbackground=self.colors['bg_secondary'],
                        rowheight=30)
        style.configure('Treeview.Heading', 
                        background=self.colors['bg_tertiary'], 
                        foreground=self.colors['fg'],
                        font=('Segoe UI', 10, 'bold'))
        style.map('Treeview', background=[('selected', self.colors['accent'])])
        
        style.configure('TLabelframe', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TLabelframe.Label', background=self.colors['bg'], foreground=self.colors['accent'], font=('Segoe UI', 10, 'bold'))

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_lbl = ttk.Label(main_frame, text="📥 HLS Downloader & Merger", font=('Segoe UI', 18, 'bold'))
        title_lbl.pack(anchor=tk.W, pady=(0, 20))

        # URL Input
        input_group = ttk.LabelFrame(main_frame, text="Video Source", padding=15)
        input_group.pack(fill=tk.X, pady=(0, 15))

        url_frame = ttk.Frame(input_group)
        url_frame.pack(fill=tk.X)
        
        ttk.Label(url_frame, text="m3u8 URL:").pack(side=tk.LEFT, padx=(0, 10))
        self.url_entry = ttk.Entry(url_frame, width=60)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.btn_analyze = ttk.Button(url_frame, text="🔍 Analyze", command=self._analyze_url)
        self.btn_analyze.pack(side=tk.RIGHT)

        # Resolution Selection
        res_group = ttk.LabelFrame(main_frame, text="Available Resolutions", padding=15)
        res_group.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        cols = ('res', 'bandwidth')
        self.tree_res = ttk.Treeview(res_group, columns=cols, show='headings', height=5, selectmode='extended')
        self.tree_res.heading('res', text='Resolution')
        self.tree_res.heading('bandwidth', text='Bitrate (bps)')
        self.tree_res.column('res', width=150)
        self.tree_res.column('bandwidth', width=200)
        
        sb = ttk.Scrollbar(res_group, orient=tk.VERTICAL, command=self.tree_res.yview)
        self.tree_res.configure(yscrollcommand=sb.set)
        self.tree_res.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Settings
        settings_group = ttk.LabelFrame(main_frame, text="Download Options", padding=15)
        settings_group.pack(fill=tk.X, pady=(0, 15))

        # Output Dir
        out_frame = ttk.Frame(settings_group)
        out_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(out_frame, text="Save to:").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Entry(out_frame, textvariable=self.output_dir, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(out_frame, text="Browse", command=self._browse_output).pack(side=tk.RIGHT)

        # Merge Checkbox
        options_frame = ttk.Frame(settings_group)
        options_frame.pack(fill=tk.X)
        ttk.Checkbutton(options_frame, text="Convert to MP4 (Merging)", variable=self.merge_var).pack(side=tk.LEFT)

        # Download Button
        self.btn_download = ttk.Button(main_frame, text="🚀 Start Download", command=self._start_download, state='disabled')
        self.btn_download.pack(fill=tk.X, pady=(0, 15))

        # Logs
        log_group = ttk.LabelFrame(main_frame, text="Activity Log", padding=10)
        log_group.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_group, height=6, bg=self.colors['bg_secondary'], fg=self.colors['fg'], 
                                font=('Consolas', 9), state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _analyze_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a Video Page URL or .m3u8 link.")
            return
        
        self.btn_analyze.config(state='disabled')
        self.btn_download.config(state='disabled')
        # Clear tree
        for item in self.tree_res.get_children():
            self.tree_res.delete(item)
            
        threading.Thread(target=self.core.analyze_url, args=(url,), daemon=True).start()

    def _start_download(self):
        selection = self.tree_res.selection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select at least one resolution (use Ctrl/Shift to select multiple).")
            return

        selected_streams = []
        for item in selection:
            idx = int(self.tree_res.index(item))
            selected_streams.append(self.streams[idx])
        
        url = self.url_entry.get().strip()
        # Derive name from URL or generic
        video_name = os.path.basename(url).split('?')[0].replace('.m3u8', '')
        if not video_name or len(video_name) < 3:
            video_name = "HLS_Video"

        out_path = self.output_dir.get()
        merge = self.merge_var.get()

        self.btn_download.config(state='disabled')
        self.core.start_download(selected_streams, out_path, video_name, merge)

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
            self._log(f"ERROR: {data}")
            messagebox.showerror("Error", data)
            self.btn_analyze.config(state='normal')
            self.btn_download.config(state='normal')
        elif event == "analysis_complete":
            self.streams = data
            for s in self.streams:
                self.tree_res.insert('', tk.END, values=(s['resolution'], s['bandwidth']))
            self.btn_analyze.config(state='normal')
            self.btn_download.config(state='normal')
            self._log(f"Analysis complete. Found {len(data)} streams.")
        elif event == "progress":
            self._log(f"Progress: {data}")
        elif event == "download_complete":
            self._log("Download Complete!")
            messagebox.showinfo("Success", f"Video has been saved to:\n{data}")
            self.btn_download.config(state='normal')

    def _log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"> {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

if __name__ == "__main__":
    root = tk.Tk()
    app = HLSDownloaderGUI(root)
    root.mainloop()
