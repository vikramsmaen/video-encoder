import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os

class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Toolkit Launcher")
        self.root.geometry("600x550")
        
        # Colors
        self.colors = {
            'bg': '#0f0f1a',
            'bg_card': '#1a1a2e',
            'fg': '#ffffff',
            'accent': '#f97316',
            'accent_hover': '#fb923c',
            'dim': '#9ca3af'
        }
        
        self.root.configure(bg=self.colors['bg'])
        
        # Style
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TFrame', background=self.colors['bg'])
        
        # Header
        header = tk.Frame(self.root, bg=self.colors['bg'])
        header.pack(fill=tk.X, pady=30)
        
        tk.Label(header, text="🎬 Video Toolkit", font=('Segoe UI', 24, 'bold'), 
                 fg=self.colors['accent'], bg=self.colors['bg']).pack()
        tk.Label(header, text="All-in-one Dashboard", font=('Segoe UI', 10), 
                 fg=self.colors['dim'], bg=self.colors['bg']).pack(pady=(5,0))

        # App Grid
        grid_frame = tk.Frame(self.root, bg=self.colors['bg'])
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=20)
        
        # Apps to launch
        self.apps = [
            ("🎥 Video Encoder", "video_encoder.py", "Encode videos to HLS"),
            ("🎨 Thumbnail Maker", "thumbnail_maker.py", "Create thumbnails & clips manually"),
            ("🏭 Bulk Sprite Gen", "bulk_sprite_maker.py", "Generate sprites for whole folders"),
            ("☁️ R2 Uploader", "r2_uploader_gui.py", "Upload assets to Cloudflare R2"),
            ("⬇️ HLS Downloader", "hls_downloader_gui.py", "Download HLS streams")
        ]
        
        for i, (name, script, desc) in enumerate(self.apps):
            self._create_card(grid_frame, name, script, desc)

    def _create_card(self, parent, name, script, desc):
        card = tk.Frame(parent, bg=self.colors['bg_card'], padx=15, pady=15)
        card.pack(fill=tk.X, pady=8)
        
        # Left: Info
        info = tk.Frame(card, bg=self.colors['bg_card'])
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(info, text=name, font=('Segoe UI', 12, 'bold'), fg=self.colors['fg'], bg=self.colors['bg_card']).pack(anchor='w')
        tk.Label(info, text=desc, font=('Segoe UI', 9), fg=self.colors['dim'], bg=self.colors['bg_card']).pack(anchor='w')
        
        # Right: Button
        btn = tk.Button(card, text="Launch 🚀", bg=self.colors['accent'], fg='white', 
                        font=('Segoe UI', 10, 'bold'), relief='flat', padx=15, pady=5,
                        activebackground=self.colors['accent_hover'], activeforeground='white',
                        cursor='hand2',
                        command=lambda s=script: self._launch(s))
        btn.pack(side=tk.RIGHT)

    def _launch(self, script_name):
        try:
            # Launch detached process
            if sys.platform == 'win32':
                subprocess.Popen([sys.executable, script_name], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen([sys.executable, script_name])
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch {script_name}:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LauncherApp(root)
    root.mainloop()
