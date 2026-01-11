"""
Video Encoder GUI Application
A Python tkinter application for encoding videos to HLS format with adaptive quality streaming.
Supports batch processing, custom output folders, and multiple resolution variants.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import re
import queue
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime

from video_validator import VideoValidator, VideoInfo, get_supported_extensions
from encoder_core import (
    HLSEncoder, EncodingJob, EncodingStatus, EncodingProgress,
    get_presets, get_resolution_names, RESOLUTION_LADDER
)



@dataclass
class QueueItem:
    """Represents a video in the encoding queue."""
    video_info: VideoInfo
    output_folder: str
    video_name: str
    selected_resolutions: List[str]
    status: str = "Pending"
    progress: float = 0.0
    job: Optional[EncodingJob] = None
    error_message: str = ""  # Store error reason for failed videos


class VideoEncoderApp:
    """Main GUI Application for Video Encoding."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AQ Video Encoder - HLS Adaptive Quality")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Set dark theme colors
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
        
        # Style configuration
        self._configure_styles()
        
        # Core components
        self.validator = VideoValidator()
        self.encoder = HLSEncoder()
        self.encoding_queue: List[QueueItem] = []
        self.is_encoding = False
        self.current_job_index = -1
        
        # Output directory
        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Videos", "Encoded"))
        
        # Encoding settings
        self.preset_var = tk.StringVar(value="ultrafast")
        self.resolution_vars: Dict[str, tk.BooleanVar] = {}
        
        # Message queue for thread-safe UI updates
        self.message_queue = queue.Queue()
        
        # Build UI
        self._build_ui()
        
        # Start message processor
        self._process_messages()
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name to be safe for folders/URLs."""
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', name).lower()
        return re.sub(r'_+', '_', safe_name).strip('_')

    def _configure_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure('.', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TFrame', background=self.colors['bg'])
        style.configure('TLabel', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TButton', background=self.colors['accent'], foreground=self.colors['fg'], padding=10)
        style.map('TButton', background=[('active', self.colors['accent_hover'])])
        
        style.configure('TEntry', fieldbackground=self.colors['bg_secondary'], foreground=self.colors['fg'])
        style.configure('TCombobox', fieldbackground=self.colors['bg_secondary'], foreground=self.colors['fg'])
        
        style.configure('Treeview', 
                        background=self.colors['bg_secondary'], 
                        foreground=self.colors['fg'],
                        fieldbackground=self.colors['bg_secondary'],
                        rowheight=30)
        style.configure('Treeview.Heading', 
                        background=self.colors['bg_tertiary'], 
                        foreground=self.colors['fg'])
        style.map('Treeview', background=[('selected', self.colors['accent'])])
        
        style.configure('TCheckbutton', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TLabelframe', background=self.colors['bg'], foreground=self.colors['fg'])
        style.configure('TLabelframe.Label', background=self.colors['bg'], foreground=self.colors['fg'])
        
        # Custom styles
        style.configure('Header.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('SubHeader.TLabel', font=('Segoe UI', 12))
        style.configure('Accent.TButton', background=self.colors['accent'])
        style.configure('Success.TButton', background=self.colors['success'])
        style.configure('Danger.TButton', background=self.colors['error'])
        
        # Progress bar
        style.configure("green.Horizontal.TProgressbar", 
                        troughcolor=self.colors['bg_secondary'],
                        background=self.colors['success'])
    
    def _build_ui(self):
        """Build the main UI."""
        self.root.configure(bg=self.colors['bg'])
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        self._build_header(main_frame)
        
        # Content area with left and right panels
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Left panel - Settings and controls
        left_panel = ttk.Frame(content_frame, width=350)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel.pack_propagate(False)
        
        self._build_settings_panel(left_panel)
        
        # Right panel - Queue and logs
        right_panel = ttk.Frame(content_frame)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self._build_queue_panel(right_panel)
        self._build_log_panel(right_panel)
        
        # Status bar
        self._build_status_bar(main_frame)
    
    def _build_header(self, parent):
        """Build header section."""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = ttk.Label(header_frame, text="🎬 AQ Video Encoder", style='Header.TLabel')
        title_label.pack(side=tk.LEFT)
        
        subtitle_label = ttk.Label(header_frame, text="HLS Adaptive Quality Streaming", style='SubHeader.TLabel')
        subtitle_label.pack(side=tk.LEFT, padx=(15, 0), pady=(5, 0))
    
    def _build_settings_panel(self, parent):
        """Build settings panel."""
        
        # Output Directory
        output_frame = ttk.LabelFrame(parent, text="📁 Output Directory", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        output_entry = ttk.Entry(output_frame, textvariable=self.output_dir, width=35)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_btn = ttk.Button(output_frame, text="Browse", command=self._browse_output_dir, width=10)
        browse_btn.pack(side=tk.RIGHT)
        
        # Add Videos section
        add_frame = ttk.LabelFrame(parent, text="➕ Add Videos", padding=10)
        add_frame.pack(fill=tk.X, pady=(0, 10))
        
        add_files_btn = ttk.Button(add_frame, text="Add Video Files", command=self._add_video_files)
        add_files_btn.pack(fill=tk.X, pady=(0, 5))
        
        add_folder_btn = ttk.Button(add_frame, text="Add Folder (Batch)", command=self._add_video_folder)
        add_folder_btn.pack(fill=tk.X)
        
        # Resolution Selection
        res_frame = ttk.LabelFrame(parent, text="🎯 Target Resolutions", padding=10)
        res_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Create 2 columns for resolutions
        res_grid = ttk.Frame(res_frame)
        res_grid.pack(fill=tk.X)
        
        for i, res in enumerate(RESOLUTION_LADDER):
            var = tk.BooleanVar(value=True)
            self.resolution_vars[res.name] = var
            
            row = i // 2
            col = i % 2
            
            cb = ttk.Checkbutton(res_grid, text=f"{res.name} ({res.bitrate}k)", variable=var)
            cb.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
        
        # Add Source resolution option for small videos
        self.resolution_vars["Source"] = tk.BooleanVar(value=True)
        cb_source = ttk.Checkbutton(res_grid, text="Source (small videos)", variable=self.resolution_vars["Source"])
        cb_source.grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        # Filter buttons
        filter_frame = ttk.Frame(res_frame)
        filter_frame.pack(fill=tk.X, pady=(5, 0))
        
        filter_btn = ttk.Button(filter_frame, text="🔍 Filter Queue", command=self._filter_by_resolution)
        filter_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        select_all_btn = ttk.Button(filter_frame, text="All", command=lambda: self._toggle_all_resolutions(True), width=5)
        select_all_btn.pack(side=tk.LEFT, padx=2)
        
        select_none_btn = ttk.Button(filter_frame, text="None", command=lambda: self._toggle_all_resolutions(False), width=5)
        select_none_btn.pack(side=tk.LEFT, padx=2)
        
        # Encoding Preset
        preset_frame = ttk.LabelFrame(parent, text="⚡ Encoding Settings", padding=10)
        preset_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Show encoder type (GPU or CPU)
        encoder_info = self.encoder.get_encoder_info()
        encoder_color = self.colors['success'] if 'GPU' in encoder_info else self.colors['fg_secondary']
        encoder_label = ttk.Label(preset_frame, text=f"🎮 {encoder_info}", foreground=encoder_color, font=('Segoe UI', 10, 'bold'))
        encoder_label.pack(anchor=tk.W, pady=(0, 5))
        
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, 
                                    values=get_presets(), state='readonly', width=30)
        preset_combo.pack(fill=tk.X)
        
        preset_note = ttk.Label(preset_frame, text="ultrafast = Maximum speed (GPU makes this faster)", 
                               foreground=self.colors['fg_secondary'], font=('Segoe UI', 9))
        preset_note.pack(anchor=tk.W, pady=(5, 0))
        
        # Control buttons
        ctrl_frame = ttk.Frame(parent)
        ctrl_frame.pack(fill=tk.X, pady=10)
        
        self.start_btn = ttk.Button(ctrl_frame, text="▶ Start Encoding", command=self._start_encoding, style='Success.TButton')
        self.start_btn.pack(fill=tk.X, pady=(0, 5))
        
        self.cancel_btn = ttk.Button(ctrl_frame, text="⏹ Cancel", command=self._cancel_encoding, style='Danger.TButton', state=tk.DISABLED)
        self.cancel_btn.pack(fill=tk.X, pady=(0, 5))
        
        clear_btn = ttk.Button(ctrl_frame, text="🗑 Clear Queue", command=self._clear_queue)
        clear_btn.pack(fill=tk.X)
        
        # Tools section
        tools_frame = ttk.LabelFrame(parent, text="🛠️ Tools", padding=10)
        tools_frame.pack(fill=tk.X, pady=(10, 0))
        
        bulk_rename_btn = ttk.Button(tools_frame, text="📝 Bulk Rename...", command=self._show_bulk_rename_dialog)
        bulk_rename_btn.pack(fill=tk.X, pady=(0, 5))
        
        quick_clean_btn = ttk.Button(tools_frame, text="🧹 Quick Clean Names", command=self._quick_clean_names)
        quick_clean_btn.pack(fill=tk.X)
    
    def _build_queue_panel(self, parent):
        """Build queue panel."""
        queue_frame = ttk.LabelFrame(parent, text="📋 Encoding Queue", padding=10)
        queue_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Queue treeview
        columns = ('name', 'folder', 'resolution', 'duration', 'status', 'progress')
        self.queue_tree = ttk.Treeview(queue_frame, columns=columns, show='headings', height=10)
        
        self.queue_tree.heading('name', text='Video Name (click to edit)')
        self.queue_tree.heading('folder', text='Output Folder')
        self.queue_tree.heading('resolution', text='Source Res')
        self.queue_tree.heading('duration', text='Duration')
        self.queue_tree.heading('status', text='Status')
        self.queue_tree.heading('progress', text='Progress')
        
        self.queue_tree.column('name', width=250)
        self.queue_tree.column('folder', width=200)
        self.queue_tree.column('resolution', width=80)
        self.queue_tree.column('duration', width=70)
        self.queue_tree.column('status', width=80)
        self.queue_tree.column('progress', width=80)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scrollbar.set)
        
        self.queue_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Context menu and inline editing
        self.queue_tree.bind('<Button-3>', self._show_queue_context_menu)
        self.queue_tree.bind('<Double-1>', self._on_double_click_cell)
        
        # Store reference to queue_frame for cell editing overlay
        self.queue_tree_frame = queue_frame
        self._edit_entry = None  # Current edit entry widget
        
        # Overall progress
        progress_frame = ttk.Frame(queue_frame)
        progress_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.overall_progress = ttk.Progressbar(progress_frame, style="green.Horizontal.TProgressbar", length=400)
        self.overall_progress.pack(fill=tk.X)
        
        self.progress_label = ttk.Label(progress_frame, text="Ready", foreground=self.colors['fg_secondary'])
        self.progress_label.pack(anchor=tk.W, pady=(5, 0))
    
    def _build_log_panel(self, parent):
        """Build log panel."""
        log_frame = ttk.LabelFrame(parent, text="📜 Encoding Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Log text widget
        self.log_text = tk.Text(log_frame, height=8, bg=self.colors['bg_secondary'], 
                                fg=self.colors['fg'], insertbackground=self.colors['fg'],
                                font=('Consolas', 9), wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text.config(state=tk.DISABLED)
    
    def _build_status_bar(self, parent):
        """Build status bar."""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_label = ttk.Label(status_frame, text="Ready - Add videos to begin",
                                      foreground=self.colors['fg_secondary'])
        self.status_label.pack(side=tk.LEFT)
        
        self.eta_label = ttk.Label(status_frame, text="", foreground=self.colors['fg_secondary'])
        self.eta_label.pack(side=tk.RIGHT)
    
    def _browse_output_dir(self):
        """Browse for output directory."""
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)
    
    def _add_video_files(self):
        """Add individual video files."""
        extensions = get_supported_extensions()
        filetypes = [
            ("Video Files", " ".join([f"*{ext}" for ext in extensions])),
            ("All Files", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Select Video Files",
            filetypes=filetypes
        )
        
        if files:
            for filepath in files:
                self._add_video_to_queue(filepath)
    
    def _add_video_folder(self):
        """Add all videos from a folder."""
        folder = filedialog.askdirectory(title="Select Folder with Videos")
        if not folder:
            return
        
        extensions = get_supported_extensions()
        videos_found = []
        
        for filename in os.listdir(folder):
            ext = os.path.splitext(filename)[1].lower()
            if ext in extensions:
                videos_found.append(os.path.join(folder, filename))
        
        if not videos_found:
            messagebox.showinfo("No Videos", "No video files found in the selected folder.")
            return
        
        # Ask for common folder name prefix
        folder_name = os.path.basename(folder)
        prefix = self._ask_folder_name(f"Batch from: {folder_name}", folder_name)
        if prefix is None:
            return
        
        for i, filepath in enumerate(videos_found):
            video_name = os.path.splitext(os.path.basename(filepath))[0]
            
            # Sanitize video name for folder usage
            safe_video_name = re.sub(r'[^a-zA-Z0-9]', '_', video_name).lower()
            safe_video_name = re.sub(r'_+', '_', safe_video_name).strip('_')
            
            output_folder = f"{prefix}_{safe_video_name}" if prefix else safe_video_name
            self._add_video_to_queue(filepath, output_folder)
        
        self._log(f"Added {len(videos_found)} videos from folder: {folder}")
    
    def _add_video_to_queue(self, filepath: str, output_folder: str = None):
        """Add a single video to the encoding queue."""
        # Validate video
        info, error = self.validator.validate_for_encoding(filepath)
        
        if error:
            self._log(f"Error: {error}")
            messagebox.showerror("Validation Error", error)
            return
        
        # Ask for folder name if not provided
        if output_folder is None:
            default_name = os.path.splitext(info.filename)[0]
            # Sanitize default name: lowercase, replace spaces with underscores, remove special chars
            safe_name = re.sub(r'[^a-zA-Z0-9]', '_', default_name).lower()
            safe_name = re.sub(r'_+', '_', safe_name).strip('_')
            
            output_folder = self._ask_folder_name(f"Name for: {info.filename}", safe_name)
            if output_folder is None:
                return
        
        # Get selected resolutions
        selected = [name for name, var in self.resolution_vars.items() if var.get()]
        
        # Filter to available resolutions
        available = self.encoder.get_available_resolutions(info.width, info.height)
        available_names = [r.name for r in available]
        
        # NEW LOGIC: If 'Source' is selected, we fulfill the user's request to
        # encode "Original + All Below". So we just use all available names.
        if "Source" in selected:
            valid_resolutions = available_names
        else:
            # Otherwise, respect manual selection
            valid_resolutions = [r for r in selected if r in available_names]
        
        if not valid_resolutions:
            messagebox.showwarning("No Valid Resolutions", 
                                   f"No selected resolutions are available for {info.filename}\n"
                                   f"Source resolution: {info.width}x{info.height}")
            return
        
        # Create queue item
        video_name = os.path.splitext(info.filename)[0]
        item = QueueItem(
            video_info=info,
            output_folder=output_folder,
            video_name=video_name,
            selected_resolutions=valid_resolutions
        )
        
        self.encoding_queue.append(item)
        self._update_queue_display()
        self._log(f"Added: {info.filename} → {output_folder}/ ({', '.join(valid_resolutions)})")
        self._update_status(f"Queue: {len(self.encoding_queue)} video(s)")
    
    def _ask_folder_name(self, title: str, default: str) -> Optional[str]:
        """Ask user for output folder name."""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("400x150")
        dialog.configure(bg=self.colors['bg'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        result = [None]
        
        ttk.Label(dialog, text="Enter output folder name:").pack(pady=(20, 5))
        
        entry_var = tk.StringVar(value=default)
        entry = ttk.Entry(dialog, textvariable=entry_var, width=40)
        entry.pack(pady=5)
        entry.select_range(0, tk.END)
        entry.focus()
        
        def on_ok():
            result[0] = entry_var.get().strip()
            if not result[0]:
                result[0] = default
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())
        
        dialog.wait_window()
        return result[0]
    
    def _update_queue_display(self):
        """Update the queue treeview."""
        # Clear existing items
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        
        # Add queue items
        for i, item in enumerate(self.encoding_queue):
            info = item.video_info
            progress_str = f"{item.progress:.1f}%" if item.progress > 0 else "-"
            
            self.queue_tree.insert('', tk.END, iid=str(i), values=(
                item.video_name,
                item.output_folder,
                info.resolution_label,
                info.duration_formatted,
                item.status,
                progress_str
            ))
    
    def _show_queue_context_menu(self, event):
        """Show context menu for queue items."""
        item = self.queue_tree.identify_row(event.y)
        if not item:
            # Show general menu if clicking on empty area
            menu = tk.Menu(self.root, tearoff=0, bg=self.colors['bg_secondary'], fg=self.colors['fg'])
            menu.add_command(label="📝 Bulk Rename All...", command=self._show_bulk_rename_dialog)
            menu.add_command(label="🧹 Quick Clean All Names", command=self._quick_clean_names)
            menu.add_separator()
            menu.add_command(label="Select All", command=self._select_all_queue_items)
            menu.tk_popup(event.x_root, event.y_root)
            return
        
        self.queue_tree.selection_set(item)
        idx = int(item)
        queue_item = self.encoding_queue[idx]
        
        menu = tk.Menu(self.root, tearoff=0, bg=self.colors['bg_secondary'], fg=self.colors['fg'])
        
        # Show error details for failed items
        if queue_item.status == "Failed" and queue_item.error_message:
            menu.add_command(label="⚠️ View Error Details", command=lambda: self._show_error_details(idx))
            menu.add_command(label="🔄 Retry Encoding", command=lambda: self._retry_encoding(idx))
            menu.add_separator()
        
        # Single item actions
        menu.add_command(label="✏️ Edit Folder Name", command=lambda: self._edit_queue_item(None))
        menu.add_command(label="📋 Copy Video Name", command=lambda: self._copy_to_clipboard(queue_item.video_name))
        menu.add_separator()
        
        # Rename submenu
        rename_menu = tk.Menu(menu, tearoff=0, bg=self.colors['bg_secondary'], fg=self.colors['fg'])
        rename_menu.add_command(label="Add Prefix...", command=lambda: self._add_prefix_suffix(idx, "prefix"))
        rename_menu.add_command(label="Add Suffix...", command=lambda: self._add_prefix_suffix(idx, "suffix"))
        rename_menu.add_command(label="Use Video Filename", command=lambda: self._use_video_filename(idx))
        rename_menu.add_command(label="Clean Name", command=lambda: self._clean_single_name(idx))
        menu.add_cascade(label="🔄 Rename", menu=rename_menu)
        
        menu.add_separator()
        menu.add_command(label="🗑 Remove from Queue", command=lambda: self._remove_queue_item(idx))
        menu.add_separator()
        menu.add_command(label="📂 Open Source Location", 
                        command=lambda: os.startfile(os.path.dirname(queue_item.video_info.filepath)))
        
        menu.tk_popup(event.x_root, event.y_root)
    
    def _edit_queue_item(self, event):
        """Edit a queue item's folder name."""
        selection = self.queue_tree.selection()
        if not selection:
            return
        
        idx = int(selection[0])
        item = self.encoding_queue[idx]
        
        if item.status != "Pending":
            return
        
        new_name = self._ask_folder_name(f"Edit: {item.video_name}", item.output_folder)
        if new_name:
            item.output_folder = new_name
            self._update_queue_display()
    
    def _on_double_click_cell(self, event):
        """Handle double-click on a cell for inline editing."""
        # Identify the clicked row and column
        region = self.queue_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        
        column = self.queue_tree.identify_column(event.x)
        item_id = self.queue_tree.identify_row(event.y)
        
        if not item_id:
            return
        
        # Column #1 is 'name', #2 is 'folder'
        editable_columns = {'#1': 'name', '#2': 'folder'}
        if column not in editable_columns:
            return
        
        idx = int(item_id)
        if idx >= len(self.encoding_queue):
            return
        
        queue_item = self.encoding_queue[idx]
        if queue_item.status != "Pending":
            return
        
        col_name = editable_columns[column]
        
        # Get cell bounding box
        bbox = self.queue_tree.bbox(item_id, column)
        if not bbox:
            return
        
        x, y, width, height = bbox
        
        # Get current value
        if col_name == 'name':
            current_value = queue_item.video_name
        else:
            current_value = queue_item.output_folder
        
        # Create entry widget for inline editing
        self._create_cell_editor(item_id, column, col_name, current_value, x, y, width, height)
    
    def _create_cell_editor(self, item_id, column, col_name, current_value, x, y, width, height):
        """Create an inline entry widget for cell editing."""
        # Destroy existing edit widget
        if self._edit_entry:
            self._edit_entry.destroy()
            self._edit_entry = None
        
        # Create entry widget
        entry_var = tk.StringVar(value=current_value)
        entry = tk.Entry(self.queue_tree, textvariable=entry_var,
                        bg=self.colors['bg_secondary'], fg=self.colors['fg'],
                        insertbackground=self.colors['fg'],
                        font=('Segoe UI', 9), relief=tk.SOLID, bd=1)
        
        # Position the entry over the cell
        entry.place(x=x, y=y, width=width, height=height)
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        self._edit_entry = entry
        
        def save_edit():
            new_value = entry_var.get().strip()
            if new_value and new_value != current_value:
                idx = int(item_id)
                if idx < len(self.encoding_queue):
                    if col_name == 'name':
                        # Update video name (keep as is) and output folder (sanitized)
                        self.encoding_queue[idx].video_name = new_value
                        self.encoding_queue[idx].output_folder = self._sanitize_name(new_value)
                    else:
                        # Direct folder edit - strictly sanitize
                        self.encoding_queue[idx].output_folder = self._sanitize_name(new_value)
                    self._update_queue_display()
            cancel_edit()
        
        def cancel_edit():
            if self._edit_entry:
                self._edit_entry.destroy()
                self._edit_entry = None
        
        entry.bind('<Return>', lambda e: save_edit())
        entry.bind('<Escape>', lambda e: cancel_edit())
        entry.bind('<FocusOut>', lambda e: save_edit())
    
    def _remove_queue_item(self, idx: int):
        """Remove item from queue."""
        if self.encoding_queue[idx].status in ["Pending", "Completed", "Failed"]:
            del self.encoding_queue[idx]
            self._update_queue_display()
    
    def _clear_queue(self):
        """Clear the encoding queue."""
        if self.is_encoding:
            messagebox.showwarning("Cannot Clear", "Cannot clear queue while encoding is in progress.")
            return
        
        self.encoding_queue.clear()
        self._update_queue_display()
        self._log("Queue cleared")
        self._update_status("Queue cleared")
    
    def _show_error_details(self, idx: int):
        """Show error details for a failed video."""
        if idx >= len(self.encoding_queue):
            return
        
        item = self.encoding_queue[idx]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Error Details - {item.video_name}")
        dialog.geometry("500x300")
        dialog.configure(bg=self.colors['bg'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Header
        ttk.Label(dialog, text="⚠️ Encoding Failed", font=('Segoe UI', 14, 'bold'),
                 foreground=self.colors['error']).pack(pady=(15, 5))
        
        # Video info
        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Label(info_frame, text=f"Video: {item.video_name}").pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Source: {item.video_info.filepath}",
                 foreground=self.colors['fg_secondary']).pack(anchor=tk.W)
        ttk.Label(info_frame, text=f"Resolution: {item.video_info.width}x{item.video_info.height}",
                 foreground=self.colors['fg_secondary']).pack(anchor=tk.W)
        
        # Error message
        ttk.Label(dialog, text="Error Message:", font=('Segoe UI', 10, 'bold')).pack(anchor=tk.W, padx=20, pady=(10, 5))
        
        error_text = tk.Text(dialog, height=5, bg=self.colors['bg_secondary'],
                            fg=self.colors['error'], font=('Consolas', 10), wrap=tk.WORD)
        error_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))
        error_text.insert(tk.END, item.error_message or "No error details available")
        error_text.config(state=tk.DISABLED)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        
        ttk.Button(btn_frame, text="🔄 Retry", 
                  command=lambda: [dialog.destroy(), self._retry_encoding(idx)],
                  width=12).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)
    
    def _retry_encoding(self, idx: int):
        """Reset a failed video to pending for retry."""
        if idx >= len(self.encoding_queue):
            return
        
        item = self.encoding_queue[idx]
        if item.status in ["Failed", "Cancelled"]:
            item.status = "Pending"
            item.progress = 0.0
            item.error_message = ""
            item.job = None
            self._update_queue_display()
            self._log(f"Reset for retry: {item.video_name}")
    
    def _toggle_all_resolutions(self, state: bool):
        """Toggle all resolution checkboxes."""
        for var in self.resolution_vars.values():
            var.set(state)
    
    def _filter_by_resolution(self):
        """Filter queue to only keep videos with selected resolutions available."""
        if not self.encoding_queue:
            messagebox.showinfo("Empty Queue", "No videos in queue to filter.")
            return
        
        if self.is_encoding:
            messagebox.showwarning("Cannot Filter", "Cannot filter while encoding is in progress.")
            return
        
        selected = [name for name, var in self.resolution_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("No Selection", "Please select at least one target resolution.")
            return
        
        # Find videos to keep
        to_remove = []
        for i, item in enumerate(self.encoding_queue):
            if item.status != "Pending":
                continue
            
            # Get available resolutions for this video
            available = self.encoder.get_available_resolutions(
                item.video_info.width, 
                item.video_info.height
            )
            available_names = [r.name for r in available]
            
            # Check if any selected resolution is available
            has_valid = any(res in available_names for res in selected)
            
            if not has_valid:
                to_remove.append(i)
        
        if not to_remove:
            messagebox.showinfo("All Match", "All videos have the selected resolutions available.")
            return
        
        # Confirm removal
        if not messagebox.askyesno("Confirm Filter", 
                                   f"Remove {len(to_remove)} video(s) that don't have selected resolutions?"):
            return
        
        # Remove in reverse order to maintain indices
        for i in reversed(to_remove):
            removed_name = self.encoding_queue[i].video_name
            del self.encoding_queue[i]
            self._log(f"Filtered out: {removed_name}")
        
        self._update_queue_display()
        self._update_status(f"Removed {len(to_remove)} video(s), {len(self.encoding_queue)} remaining")
        messagebox.showinfo("Filtered", f"Removed {len(to_remove)} video(s) without selected resolutions.")
    
    def _start_encoding(self):
        """Start the encoding process."""
        if not self.encoding_queue:
            messagebox.showinfo("Empty Queue", "Add videos to the queue first.")
            return
        
        # Check output directory
        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showerror("Error", "Please select an output directory.")
            return
        
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Error", f"Cannot create output directory: {e}")
            return
        
        # Find first pending item
        pending = [i for i, item in enumerate(self.encoding_queue) if item.status == "Pending"]
        if not pending:
            messagebox.showinfo("Complete", "All videos have been processed.")
            return
        
        self.is_encoding = True
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        
        # Start encoding thread
        threading.Thread(target=self._encoding_thread, daemon=True).start()
    
    def _encoding_thread(self):
        """Encoding thread that processes the queue."""
        output_dir = self.output_dir.get()
        preset = self.preset_var.get()
        
        pending_items = [i for i, item in enumerate(self.encoding_queue) if item.status == "Pending"]
        total_items = len(pending_items)
        
        for count, idx in enumerate(pending_items):
            if not self.is_encoding:
                break
            
            item = self.encoding_queue[idx]
            self.current_job_index = idx
            
            # Update status
            item.status = "Encoding"
            self._queue_message('update_queue')
            self._queue_message('status', f"Encoding {count + 1}/{total_items}: {item.video_name}")
            self._queue_message('log', f"\n{'='*50}\nStarting: {item.video_name}\n{'='*50}")
            
            # Create encoding job
            job = self.encoder.create_encoding_job(
                input_path=item.video_info.filepath,
                output_folder=item.output_folder,
                video_name=item.video_name,
                output_dir=output_dir,
                source_width=item.video_info.width,
                source_height=item.video_info.height,
                source_duration=item.video_info.duration,
                source_fps=item.video_info.fps,
                selected_resolutions=item.selected_resolutions,
                preset=preset
            )
            item.job = job
            
            # Run encoding
            success = self.encoder.encode(
                job,
                progress_callback=lambda p: self._on_progress(idx, p),
                log_callback=lambda msg: self._queue_message('log', msg)
            )
            
            if success:
                item.status = "Completed"
                item.progress = 100.0
                item.error_message = ""
                self._queue_message('log', f"✓ Completed: {item.video_name}")
            else:
                if job.status == EncodingStatus.CANCELLED:
                    item.status = "Cancelled"
                    item.error_message = "Cancelled by user"
                else:
                    item.status = "Failed"
                    item.error_message = job.error_message or "Unknown error"
                    self._queue_message('log', f"✗ Failed: {item.video_name} - {item.error_message}")
            
            self._queue_message('update_queue')
        
        self._queue_message('encoding_complete')
    
    def _on_progress(self, idx: int, progress: EncodingProgress):
        """Handle progress updates from encoder."""
        if idx < len(self.encoding_queue):
            self.encoding_queue[idx].progress = progress.percent
        
        self._queue_message('progress', progress)
    
    def _queue_message(self, msg_type: str, data=None):
        """Queue a message for the UI thread."""
        self.message_queue.put((msg_type, data))
    
    def _process_messages(self):
        """Process messages from the encoding thread."""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()
                
                if msg_type == 'update_queue':
                    self._update_queue_display()
                elif msg_type == 'status':
                    self._update_status(data)
                elif msg_type == 'log':
                    self._log(data)
                elif msg_type == 'progress':
                    self._update_progress(data)
                elif msg_type == 'encoding_complete':
                    self._encoding_complete()
        except queue.Empty:
            pass
        
        self.root.after(100, self._process_messages)
    
    def _update_progress(self, progress: EncodingProgress):
        """Update progress display."""
        self.overall_progress['value'] = progress.percent
        
        eta_str = ""
        if progress.eta_seconds:
            mins = int(progress.eta_seconds // 60)
            secs = int(progress.eta_seconds % 60)
            eta_str = f"ETA: {mins}m {secs}s"
        
        speed_str = f" | Speed: {progress.speed}" if progress.speed else ""
        self.progress_label.config(text=f"{progress.percent:.1f}%{speed_str}")
        self.eta_label.config(text=eta_str)
        
        # Update queue display periodically
        if int(progress.percent) % 5 == 0:
            self._update_queue_display()
    
    def _cancel_encoding(self):
        """Cancel the current encoding."""
        if messagebox.askyesno("Cancel Encoding", "Are you sure you want to cancel?"):
            self.is_encoding = False
            self.encoder.cancel()
            self._log("Encoding cancelled by user")
    
    def _encoding_complete(self):
        """Handle encoding completion."""
        self.is_encoding = False
        self.current_job_index = -1
        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        
        completed = sum(1 for item in self.encoding_queue if item.status == "Completed")
        failed = sum(1 for item in self.encoding_queue if item.status == "Failed")
        
        self._update_status(f"Complete: {completed} succeeded, {failed} failed")
        self.progress_label.config(text="Complete")
        self.eta_label.config(text="")
        
        if failed == 0:
            self._log("\n✓ All videos encoded successfully!")
            messagebox.showinfo("Complete", f"Successfully encoded {completed} video(s)!")
        else:
            self._log(f"\n⚠ Encoding complete with {failed} failure(s)")
            messagebox.showwarning("Complete", f"Encoded {completed} video(s), {failed} failed.")
    
    def _log(self, message: str):
        """Add message to log."""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _update_status(self, message: str):
        """Update status bar."""
        self.status_label.config(text=message)
    
    # ============= NAMING UTILITIES =============
    
    def _clean_name(self, name: str) -> str:
        """Clean a name by removing/replacing problematic characters."""
        # Replace common separators with spaces
        name = re.sub(r'[_\-\.]+', ' ', name)
        # Remove special characters but keep spaces and alphanumeric
        name = re.sub(r'[^\w\s]', '', name)
        # Collapse multiple spaces
        name = re.sub(r'\s+', ' ', name)
        # Title case and strip
        return name.strip().title()
    
    def _quick_clean_names(self):
        """Quick clean all pending items' folder names."""
        if not self.encoding_queue:
            messagebox.showinfo("Empty Queue", "No videos in queue to rename.")
            return
        
        pending = [item for item in self.encoding_queue if item.status == "Pending"]
        if not pending:
            messagebox.showinfo("No Pending", "No pending items to rename.")
            return
        
        for item in pending:
            item.output_folder = self._clean_name(item.output_folder)
        
        self._update_queue_display()
        self._log(f"Cleaned names for {len(pending)} items")
        messagebox.showinfo("Done", f"Cleaned folder names for {len(pending)} item(s).")
    
    def _clean_single_name(self, idx: int):
        """Clean a single item's folder name."""
        if idx < len(self.encoding_queue):
            item = self.encoding_queue[idx]
            if item.status == "Pending":
                item.output_folder = self._clean_name(item.output_folder)
                self._update_queue_display()
    
    def _select_all_queue_items(self):
        """Select all items in queue."""
        for item_id in self.queue_tree.get_children():
            self.queue_tree.selection_add(item_id)
    
    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
    
    def _add_prefix_suffix(self, idx: int, mode: str):
        """Add prefix or suffix to a single item."""
        if idx >= len(self.encoding_queue):
            return
        
        item = self.encoding_queue[idx]
        if item.status != "Pending":
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Add {mode.title()}")
        dialog.geometry("350x120")
        dialog.configure(bg=self.colors['bg'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Enter {mode} for: {item.output_folder}").pack(pady=(15, 5))
        
        entry_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=entry_var, width=35)
        entry.pack(pady=5)
        entry.focus()
        
        def apply():
            value = entry_var.get().strip()
            if value:
                if mode == "prefix":
                    item.output_folder = f"{value}{item.output_folder}"
                else:
                    item.output_folder = f"{item.output_folder}{value}"
                self._update_queue_display()
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Apply", command=apply, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)
        
        entry.bind('<Return>', lambda e: apply())
        entry.bind('<Escape>', lambda e: dialog.destroy())
    
    def _use_video_filename(self, idx: int):
        """Set folder name to match video filename."""
        if idx < len(self.encoding_queue):
            item = self.encoding_queue[idx]
            if item.status == "Pending":
                item.output_folder = item.video_name
                self._update_queue_display()
    
    def _process_messages(self):
        """Process messages from the encoding thread."""
        try:
            while True:
                msg_type, data = self.message_queue.get_nowait()
                
                if msg_type == 'update_queue':
                    self._update_queue_display()
                elif msg_type == 'status':
                    self._update_status(data)
                elif msg_type == 'log':
                    self._log(data)
                elif msg_type == 'progress':
                    self._update_progress(data)
                elif msg_type == 'encoding_complete':
                    self._encoding_complete()
        except queue.Empty:
            pass
        
        self.root.after(100, self._process_messages)

    def _show_bulk_rename_dialog(self):
        """Show comprehensive bulk rename dialog."""
        if not self.encoding_queue:
            messagebox.showinfo("Empty Queue", "No videos in queue to rename.")
            return
        
        pending = [item for item in self.encoding_queue if item.status == "Pending"]
        if not pending:
            messagebox.showinfo("No Pending", "No pending items to rename.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Bulk Rename")
        dialog.geometry("500x550")
        dialog.configure(bg=self.colors['bg'])
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Variables
        prefix_var = tk.StringVar()
        suffix_var = tk.StringVar()
        find_var = tk.StringVar()
        replace_var = tk.StringVar()
        template_var = tk.StringVar(value="{name}")
        clean_var = tk.BooleanVar(value=False)
        numbering_var = tk.BooleanVar(value=False)
        start_num_var = tk.StringVar(value="1")
        
        # Header
        ttk.Label(dialog, text="📝 Bulk Rename", font=('Segoe UI', 14, 'bold')).pack(pady=(15, 5))
        ttk.Label(dialog, text=f"Renaming {len(pending)} pending item(s)", 
                 foreground=self.colors['fg_secondary']).pack(pady=(0, 10))
        
        # Notebook for tabs
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # Tab 1: Prefix/Suffix
        tab1 = ttk.Frame(notebook, padding=15)
        notebook.add(tab1, text="Prefix/Suffix")
        
        ttk.Label(tab1, text="Prefix (added before name):").pack(anchor=tk.W)
        ttk.Entry(tab1, textvariable=prefix_var, width=40).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(tab1, text="Suffix (added after name):").pack(anchor=tk.W)
        ttk.Entry(tab1, textvariable=suffix_var, width=40).pack(fill=tk.X, pady=(0, 10))
        
        # Tab 2: Find & Replace
        tab2 = ttk.Frame(notebook, padding=15)
        notebook.add(tab2, text="Find & Replace")
        
        ttk.Label(tab2, text="Find:").pack(anchor=tk.W)
        ttk.Entry(tab2, textvariable=find_var, width=40).pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(tab2, text="Replace with:").pack(anchor=tk.W)
        ttk.Entry(tab2, textvariable=replace_var, width=40).pack(fill=tk.X, pady=(0, 10))
        
        # Tab 3: Template
        tab3 = ttk.Frame(notebook, padding=15)
        notebook.add(tab3, text="Template")
        
        ttk.Label(tab3, text="Template pattern:").pack(anchor=tk.W)
        ttk.Entry(tab3, textvariable=template_var, width=40).pack(fill=tk.X, pady=(0, 5))
        
        template_help = """Available placeholders:
{name} = Original folder name
{video} = Video filename (no extension)
{num} = Sequence number
{res} = Video resolution (e.g., 1080p)

Example: "Series_{num}_{name}" """
        ttk.Label(tab3, text=template_help, foreground=self.colors['fg_secondary'],
                 font=('Consolas', 9), justify=tk.LEFT).pack(anchor=tk.W, pady=5)
        
        # Options frame
        options_frame = ttk.LabelFrame(dialog, text="Options", padding=10)
        options_frame.pack(fill=tk.X, padx=15, pady=10)
        
        ttk.Checkbutton(options_frame, text="🧹 Clean names (remove special chars, title case)", 
                       variable=clean_var).pack(anchor=tk.W)
        
        num_frame = ttk.Frame(options_frame)
        num_frame.pack(fill=tk.X, pady=5)
        ttk.Checkbutton(num_frame, text="Add sequential numbers, starting at:", 
                       variable=numbering_var).pack(side=tk.LEFT)
        ttk.Entry(num_frame, textvariable=start_num_var, width=5).pack(side=tk.LEFT, padx=5)
        
        # Preview frame
        preview_frame = ttk.LabelFrame(dialog, text="Preview", padding=10)
        preview_frame.pack(fill=tk.X, padx=15, pady=(0, 10))
        
        preview_text = tk.Text(preview_frame, height=3, bg=self.colors['bg_secondary'],
                              fg=self.colors['fg'], font=('Consolas', 9))
        preview_text.pack(fill=tk.X)
        
        def update_preview(*args):
            """Update preview with first item."""
            if not pending:
                return
            
            sample = pending[0]
            new_name = self._apply_rename_rules(
                sample.output_folder,
                sample.video_name,
                sample.video_info.resolution_label,
                0,
                prefix_var.get(),
                suffix_var.get(),
                find_var.get(),
                replace_var.get(),
                template_var.get(),
                clean_var.get(),
                numbering_var.get(),
                int(start_num_var.get() or "1")
            )
            
            preview_text.config(state=tk.NORMAL)
            preview_text.delete(1.0, tk.END)
            preview_text.insert(tk.END, f"Before: {sample.output_folder}\n")
            preview_text.insert(tk.END, f"After:  {new_name}")
            preview_text.config(state=tk.DISABLED)
        
        # Bind updates
        for var in [prefix_var, suffix_var, find_var, replace_var, template_var, start_num_var]:
            var.trace('w', update_preview)
        clean_var.trace('w', update_preview)
        numbering_var.trace('w', update_preview)
        
        update_preview()
        
        def apply_changes():
            try:
                start_num = int(start_num_var.get() or "1")
            except ValueError:
                start_num = 1
            
            for i, item in enumerate(pending):
                item.output_folder = self._apply_rename_rules(
                    item.output_folder,
                    item.video_name,
                    item.video_info.resolution_label,
                    i,
                    prefix_var.get(),
                    suffix_var.get(),
                    find_var.get(),
                    replace_var.get(),
                    template_var.get(),
                    clean_var.get(),
                    numbering_var.get(),
                    start_num
                )
            
            self._update_queue_display()
            self._log(f"Bulk renamed {len(pending)} items")
            dialog.destroy()
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        
        ttk.Button(btn_frame, text="Apply to All", command=apply_changes, 
                  style='Success.TButton', width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy, width=10).pack(side=tk.LEFT, padx=5)
    
    def _apply_rename_rules(
        self,
        current_name: str,
        video_name: str,
        resolution: str,
        index: int,
        prefix: str,
        suffix: str,
        find: str,
        replace: str,
        template: str,
        clean: bool,
        add_number: bool,
        start_num: int
    ) -> str:
        """Apply all rename rules to a name."""
        result = current_name
        
        # Apply template if not default
        if template and template != "{name}":
            result = template.replace("{name}", current_name)
            result = result.replace("{video}", video_name)
            result = result.replace("{res}", resolution)
            result = result.replace("{num}", str(start_num + index))
        
        # Find and replace
        if find:
            result = result.replace(find, replace)
        
        # Add prefix/suffix
        if prefix:
            result = prefix + result
        if suffix:
            result = result + suffix
        
        # Add numbering
        if add_number and "{num}" not in template:
            result = f"{start_num + index:02d}_{result}"
        
        # Clean
        if clean:
            result = self._clean_name(result)
        
        return result.strip() if result.strip() else current_name


def main():
    """Main entry point."""
    root = tk.Tk()
    app = VideoEncoderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
