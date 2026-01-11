"""
Universal Video Downloader GUI
Tkinter-based control panel that works with Playwright browser for media detection.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import queue
import threading
from media_scanner_core import MediaScannerCore, PLAYWRIGHT_AVAILABLE


class UniversalDownloaderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🎬 Universal Video Downloader")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Dark Theme Colors
        self.colors = {
            'bg': '#0f0f1a',
            'bg_secondary': '#1a1a2e',
            'bg_tertiary': '#252542',
            'bg_hover': '#2d2d4a',
            'fg': '#ffffff',
            'fg_secondary': '#9ca3af',
            'fg_muted': '#6b7280',
            'accent': '#8b5cf6',
            'accent_hover': '#a78bfa',
            'success': '#22c55e',
            'warning': '#f59e0b',
            'error': '#ef4444',
            'border': '#374151'
        }

        self.core = MediaScannerCore()
        self.core.set_callback(self._on_core_event)
        self.msg_queue = queue.Queue()
        
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "VideoDownloads"))
        self.merge_var = tk.BooleanVar(value=True)
        self.browser_running = False
        self.media_items = {}  # item_id -> MediaItem

        self._configure_styles()
        self._build_ui()
        self._process_messages()
        
        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Handle window close - cleanup browser properly."""
        if self.browser_running:
            self._log("🛑 Closing browser...")
            try:
                self.core.stop_browser()
            except:
                pass
        self.root.destroy()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Base styles
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'], font=('Segoe UI', 10))
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TEntry', fieldbackground=self.colors['bg_secondary'], foreground=self.colors['fg'], 
                       insertcolor=self.colors['fg'], padding=8)
        
        # Buttons
        style.configure('TButton', background=self.colors['accent'], foreground=self.colors['fg'], 
                       padding=(16, 10), font=('Segoe UI', 10, 'bold'))
        style.map('TButton', 
                  background=[('active', self.colors['accent_hover']), ('disabled', self.colors['bg_tertiary'])],
                  foreground=[('disabled', self.colors['fg_muted'])])
        
        # Primary action button
        style.configure('Primary.TButton', background=self.colors['success'])
        style.map('Primary.TButton', background=[('active', '#16a34a'), ('disabled', self.colors['bg_tertiary'])])
        
        # Danger button
        style.configure('Danger.TButton', background=self.colors['error'])
        style.map('Danger.TButton', background=[('active', '#dc2626')])
        
        # Treeview
        style.configure('Treeview', 
                       background=self.colors['bg_secondary'], 
                       foreground=self.colors['fg'], 
                       fieldbackground=self.colors['bg_secondary'],
                       rowheight=36,
                       font=('Segoe UI', 10))
        style.configure('Treeview.Heading', 
                       background=self.colors['bg_tertiary'], 
                       foreground=self.colors['fg'],
                       font=('Segoe UI', 10, 'bold'),
                       padding=8)
        style.map('Treeview', 
                  background=[('selected', self.colors['accent'])],
                  foreground=[('selected', self.colors['fg'])])
        
        # LabelFrame
        style.configure('TLabelframe', background=self.colors['bg'])
        style.configure('TLabelframe.Label', background=self.colors['bg'], foreground=self.colors['accent'], 
                       font=('Segoe UI', 11, 'bold'))
        
        # Checkbutton
        style.configure('TCheckbutton', background=self.colors['bg'], foreground=self.colors['fg'])

    def _build_ui(self):
        # Configure root background
        self.root.configure(bg=self.colors['bg'])
        
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_lbl = ttk.Label(header_frame, text="🎬 Universal Video Downloader", 
                             font=('Segoe UI', 20, 'bold'))
        title_lbl.pack(side=tk.LEFT)
        
        subtitle_lbl = ttk.Label(header_frame, text="Intercepts media from any website", 
                                foreground=self.colors['fg_secondary'], font=('Segoe UI', 10))
        subtitle_lbl.pack(side=tk.LEFT, padx=(15, 0), pady=(8, 0))

        # URL Input Section
        url_group = ttk.LabelFrame(main_frame, text="📍 Target URL", padding=15)
        url_group.pack(fill=tk.X, pady=(0, 15))

        url_frame = ttk.Frame(url_group)
        url_frame.pack(fill=tk.X)
        
        self.url_entry = ttk.Entry(url_frame, font=('Segoe UI', 11))
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.url_entry.insert(0, "https://")
        self.url_entry.bind('<Return>', lambda e: self._navigate())
        
        self.btn_navigate = ttk.Button(url_frame, text="🌐 Open in Browser", command=self._navigate)
        self.btn_navigate.pack(side=tk.RIGHT)

        # Browser Status
        status_frame = ttk.Frame(url_group)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_label = ttk.Label(status_frame, text="⚪ Browser not running", 
                                      foreground=self.colors['fg_muted'])
        self.status_label.pack(side=tk.LEFT)
        
        self.btn_stop_browser = ttk.Button(status_frame, text="Stop Browser", 
                                           command=self._stop_browser, style='Danger.TButton')
        self.btn_stop_browser.pack(side=tk.RIGHT)
        self.btn_stop_browser.config(state='disabled')

        # Media Detection Section
        media_group = ttk.LabelFrame(main_frame, text="📹 Detected Media", padding=15)
        media_group.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # Instructions
        instr_label = ttk.Label(media_group, 
                               text="💡 Navigate to a page and play the video. Media streams will appear here automatically.",
                               foreground=self.colors['fg_secondary'], wraplength=800)
        instr_label.pack(anchor=tk.W, pady=(0, 10))

        # Media Treeview
        tree_frame = ttk.Frame(media_group)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        cols = ('type', 'resolution', 'details')
        self.tree_media = ttk.Treeview(tree_frame, columns=cols, show='headings', height=6, selectmode='extended')
        self.tree_media.heading('type', text='Type')
        self.tree_media.heading('resolution', text='Resolution')
        self.tree_media.heading('details', text='Details')
        self.tree_media.column('type', width=120, minwidth=100)
        self.tree_media.column('resolution', width=100, minwidth=80)
        self.tree_media.column('details', width=500, minwidth=300)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree_media.yview)
        self.tree_media.configure(yscrollcommand=scrollbar.set)
        
        self.tree_media.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Download Options Section
        options_group = ttk.LabelFrame(main_frame, text="⚙️ Download Options", padding=15)
        options_group.pack(fill=tk.X, pady=(0, 15))

        options_top = ttk.Frame(options_group)
        options_top.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(options_top, text="Save to:").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Entry(options_top, textvariable=self.output_dir, width=50, font=('Segoe UI', 10)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(options_top, text="📁 Browse", command=self._browse_output).pack(side=tk.RIGHT)

        options_bottom = ttk.Frame(options_group)
        options_bottom.pack(fill=tk.X)
        
        ttk.Checkbutton(options_bottom, text="Convert & merge to MP4", variable=self.merge_var).pack(side=tk.LEFT)

        # Video Name
        name_frame = ttk.Frame(options_group)
        name_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(name_frame, text="Video Name:").pack(side=tk.LEFT, padx=(0, 10))
        self.name_entry = ttk.Entry(name_frame, width=40, font=('Segoe UI', 10))
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.name_entry.insert(0, "downloaded_video")

        # Download Button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.btn_download = ttk.Button(btn_frame, text="🚀 Download Selected", 
                                       command=self._start_download, style='Primary.TButton')
        self.btn_download.pack(fill=tk.X)
        self.btn_download.config(state='disabled')

        # Log Section
        log_group = ttk.LabelFrame(main_frame, text="📋 Activity Log", padding=10)
        log_group.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_group, height=8, bg=self.colors['bg_secondary'], 
                               fg=self.colors['fg'], font=('Consolas', 9),
                               state='disabled', wrap=tk.WORD,
                               insertbackground=self.colors['fg'],
                               selectbackground=self.colors['accent'])
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Check Playwright availability on startup
        self._check_playwright()

    def _check_playwright(self):
        if not PLAYWRIGHT_AVAILABLE:
            self._log("⚠️ Playwright not installed!")
            self._log("Run these commands to install:")
            self._log("  pip install playwright")
            self._log("  playwright install chromium")
            messagebox.showwarning("Dependency Missing", 
                                  "Playwright is required but not installed.\n\n"
                                  "Run in terminal:\n"
                                  "pip install playwright\n"
                                  "playwright install chromium")

    def _navigate(self):
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("Input Error", "Please enter a valid URL.")
            return
        
        # Start browser if not running
        if not self.browser_running:
            self._log("🚀 Starting browser...")
            self.btn_navigate.config(state='disabled')
            
            def start_and_navigate():
                if self.core.start_browser(headless=False):
                    self.browser_running = True
                    self.core.navigate(url)
                    
            threading.Thread(target=start_and_navigate, daemon=True).start()
        else:
            threading.Thread(target=lambda: self.core.navigate(url), daemon=True).start()

    def _stop_browser(self):
        self._log("🛑 Stopping browser...")
        threading.Thread(target=self.core.stop_browser, daemon=True).start()

    def _browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_dir.set(d)

    def _start_download(self):
        selection = self.tree_media.selection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select at least one media item to download.")
            return
        
        video_name = self.name_entry.get().strip()
        if not video_name:
            video_name = "downloaded_video"
        
        out_dir = self.output_dir.get()
        merge = self.merge_var.get()
        
        self.btn_download.config(state='disabled')
        
        # Download each selected item
        for item_id in selection:
            if item_id in self.media_items:
                media_item = self.media_items[item_id]
                self.core.download_media(media_item, out_dir, video_name, merge)

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
            self._log(f"❌ ERROR: {data}")
            messagebox.showerror("Error", data)
            self.btn_navigate.config(state='normal')
            self.btn_download.config(state='normal')
        elif event == "browser_ready":
            self.browser_running = True
            self.status_label.config(text="🟢 Browser running", foreground=self.colors['success'])
            self.btn_navigate.config(state='normal')
            self.btn_stop_browser.config(state='normal')
        elif event == "browser_stopped":
            self.browser_running = False
            self.status_label.config(text="⚪ Browser not running", foreground=self.colors['fg_muted'])
            self.btn_navigate.config(state='normal')
            self.btn_stop_browser.config(state='disabled')
            self.btn_download.config(state='disabled')
        elif event == "navigation_complete":
            self.btn_navigate.config(state='normal')
            self._log(f"📍 Loaded: {data}")
        elif event == "media_cleared":
            # Clear the treeview
            for item in self.tree_media.get_children():
                self.tree_media.delete(item)
            self.media_items.clear()
            self.btn_download.config(state='disabled')
        elif event == "media_detected":
            self._add_media_to_tree(data)
            self.btn_download.config(state='normal')
        elif event == "media_updated":
            self._update_media_in_tree(data)
        elif event == "progress":
            # Update last log line or add new
            self._log(f"⏳ {data}")
        elif event == "download_complete":
            self._log(f"✅ Download complete! Saved to: {data}")
            messagebox.showinfo("Success", f"Video downloaded to:\n{data}")
            self.btn_download.config(state='normal')

    def _add_media_to_tree(self, media_item):
        """Add a media item to the treeview."""
        type_icons = {
            'm3u8': '📺 HLS Stream',
            'mp4': '🎬 MP4 Video',
            'webm': '🎬 WebM Video',
            'mkv': '🎬 MKV Video',
            'ts_group': '📦 Segments',
        }
        
        type_text = type_icons.get(media_item.media_type, media_item.media_type)
        resolution = media_item.resolution or 'Unknown'
        
        if media_item.media_type == 'ts_group':
            details = f"{len(media_item.segments)} segments"
        else:
            url_short = media_item.url[:80] + "..." if len(media_item.url) > 80 else media_item.url
            size_str = ""
            if media_item.size:
                size_mb = media_item.size / (1024 * 1024)
                size_str = f" ({size_mb:.1f} MB)"
            details = f"{url_short}{size_str}"
        
        item_id = self.tree_media.insert('', tk.END, values=(type_text, resolution, details))
        self.media_items[item_id] = media_item

    def _update_media_in_tree(self, media_item):
        """Update an existing segment group in the treeview."""
        for item_id, item in self.media_items.items():
            if item.media_type == 'ts_group' and item.url == media_item.url:
                details = f"{len(media_item.segments)} segments"
                self.tree_media.set(item_id, 'details', details)
                self.media_items[item_id] = media_item
                break

    def _log(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"> {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')


def main():
    root = tk.Tk()
    app = UniversalDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
