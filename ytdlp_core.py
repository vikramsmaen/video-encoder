"""
yt-dlp Core Wrapper
Simple wrapper around yt-dlp for video downloading.
"""

import yt_dlp
import os
from datetime import datetime


class YTDLPCore:
    """Core wrapper for yt-dlp video downloading."""
    
    def __init__(self):
        self.callbacks = []
        
    def set_callback(self, callback):
        """Register a callback for events."""
        self.callbacks.append(callback)
    
    def _emit(self, event, data):
        """Emit an event to all registered callbacks."""
        for cb in self.callbacks:
            try:
                cb(event, data)
            except Exception as e:
                print(f"Callback error: {e}")
    
    def extract_formats(self, url):
        """
        Extract available formats from a URL.
        Returns list of format dicts with: id, resolution, filesize, ext, etc.
        """
        try:
            self._emit('log', f"🔍 Analyzing: {url}")
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    self._emit('error', "Could not extract video information")
                    return None
                
                # Get title
                title = info.get('title', 'video')
                self._emit('log', f"📹 Found: {title}")
                
                # Get formats
                formats = info.get('formats', [])
                if not formats:
                    self._emit('error', "No formats found")
                    return None
                
                # Process formats into simplified list
                processed_formats = []
                for fmt in formats:
                    # Skip audio-only or formats without video
                    if fmt.get('vcodec') == 'none':
                        continue
                    
                    format_info = {
                        'id': fmt.get('format_id', ''),
                        'ext': fmt.get('ext', 'mp4'),
                        'resolution': fmt.get('resolution', 'unknown'),
                        'width': fmt.get('width', 0),
                        'height': fmt.get('height', 0),
                        'filesize': fmt.get('filesize', 0),
                        'filesize_approx': fmt.get('filesize_approx', 0),
                        'vcodec': fmt.get('vcodec', 'unknown'),
                        'acodec': fmt.get('acodec', 'none'),
                        'fps': fmt.get('fps', 0),
                        'tbr': fmt.get('tbr', 0),  # total bitrate
                        'format_note': fmt.get('format_note', ''),
                    }
                    processed_formats.append(format_info)
                
                # Sort by resolution (height) descending - handle None values
                processed_formats.sort(key=lambda x: x['height'] or 0, reverse=True)
                
                self._emit('log', f"✅ Found {len(processed_formats)} video formats")
                self._emit('formats_extracted', {
                    'title': title,
                    'formats': processed_formats,
                    'url': url
                })
                
                return {
                    'title': title,
                    'formats': processed_formats,
                    'url': url
                }
                
        except Exception as e:
            self._emit('error', f"Failed to analyze URL: {str(e)}")
            return None
    
    def download_video(self, url, format_id, output_dir, filename):
        """
        Download video in specified format.
        
        Args:
            url: Video URL
            format_id: Format ID to download (or 'best')
            output_dir: Output directory
            filename: Output filename (without extension)
        """
        try:
            # Create output directory
            os.makedirs(output_dir, exist_ok=True)
            
            # Build output path
            output_template = os.path.join(output_dir, f"{filename}.%(ext)s")
            
            self._emit('log', f"⬇️ Starting download...")
            self._emit('download_started', None)
            
            # Progress hook
            def progress_hook(d):
                if d['status'] == 'downloading':
                    # Extract progress info
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)
                    
                    if total > 0:
                        percent = (downloaded / total) * 100
                        speed_mb = (speed / 1024 / 1024) if speed else 0
                        
                        self._emit('progress', {
                            'percent': percent,
                            'downloaded': downloaded,
                            'total': total,
                            'speed': speed_mb,
                            'eta': eta
                        })
                
                elif d['status'] == 'finished':
                    self._emit('log', "🔧 Processing (merging/converting)...")
                
                elif d['status'] == 'error':
                    self._emit('error', "Download error occurred")
            
            # yt-dlp options
            ydl_opts = {
                'format': format_id if format_id != 'best' else 'bestvideo+bestaudio/best',
                'outtmpl': output_template,
                'progress_hooks': [progress_hook],
                'merge_output_format': 'mp4',  # Merge to MP4
                'postprocessor_args': ['-c:v', 'copy', '-c:a', 'aac'],  # Fast re-encode audio if needed
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find the downloaded file
            output_file = None
            for ext in ['mp4', 'mkv', 'webm', 'flv']:
                potential_file = os.path.join(output_dir, f"{filename}.{ext}")
                if os.path.exists(potential_file):
                    output_file = potential_file
                    break
            
            if output_file:
                self._emit('log', f"✅ Downloaded: {os.path.basename(output_file)}")
                self._emit('download_complete', output_file)
            else:
                self._emit('error', "Download completed but file not found")
                
        except Exception as e:
            self._emit('error', f"Download failed: {str(e)}")


if __name__ == "__main__":
    # Quick test
    def callback(event, data):
        print(f"[{event}] {data}")
    
    core = YTDLPCore()
    core.set_callback(callback)
    
    # Test with a URL
    test_url = input("Enter video URL: ")
    result = core.extract_formats(test_url)
    
    if result:
        print(f"\nTitle: {result['title']}")
        print(f"\nAvailable formats:")
        for i, fmt in enumerate(result['formats'][:10]):  # Show first 10
            size_mb = (fmt['filesize'] or fmt['filesize_approx']) / (1024*1024) if (fmt['filesize'] or fmt['filesize_approx']) else 0
            print(f"{i+1}. {fmt['resolution']} - {fmt['ext']} - {size_mb:.1f}MB - {fmt['format_note']}")
