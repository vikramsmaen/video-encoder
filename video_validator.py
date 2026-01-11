"""
Video Validator Module
Handles video metadata extraction and validation using ffprobe.
"""

import subprocess
import json
import os
from dataclasses import dataclass
from typing import Optional, Tuple
from fractions import Fraction


@dataclass
class VideoInfo:
    """Data class containing video metadata."""
    filepath: str
    filename: str
    width: int
    height: int
    duration: float
    fps: float
    codec: str
    bitrate: Optional[int]
    audio_codec: Optional[str]
    audio_bitrate: Optional[int]
    filesize: int
    
    @property
    def resolution_label(self) -> str:
        """Get human-readable resolution label."""
        if self.height >= 2160:
            return "4K"
        elif self.height >= 1440:
            return "1440p"
        elif self.height >= 1080:
            return "1080p"
        elif self.height >= 720:
            return "720p"
        elif self.height >= 480:
            return "480p"
        elif self.height >= 360:
            return "360p"
        else:
            return "240p"
    
    @property
    def duration_formatted(self) -> str:
        """Get human-readable duration."""
        hours = int(self.duration // 3600)
        minutes = int((self.duration % 3600) // 60)
        seconds = int(self.duration % 60)
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    @property
    def filesize_formatted(self) -> str:
        """Get human-readable file size."""
        size = self.filesize
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class VideoValidator:
    """Validates and extracts metadata from video files."""
    
    SUPPORTED_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.wmv', '.flv', '.ts', '.mts'}
    
    def __init__(self, ffprobe_path: str = "ffprobe"):
        self.ffprobe_path = ffprobe_path
    
    def is_valid_extension(self, filepath: str) -> bool:
        """Check if file has a valid video extension."""
        ext = os.path.splitext(filepath)[1].lower()
        return ext in self.SUPPORTED_EXTENSIONS
    
    def get_video_info(self, filepath: str) -> Tuple[Optional[VideoInfo], Optional[str]]:
        """
        Extract video metadata using ffprobe.
        
        Returns:
            Tuple of (VideoInfo, None) on success or (None, error_message) on failure.
        """
        # Check file exists
        if not os.path.exists(filepath):
            return None, f"File not found: {filepath}"
        
        # Check extension
        if not self.is_valid_extension(filepath):
            return None, f"Unsupported file format: {os.path.splitext(filepath)[1]}"
        
        # Get file size
        try:
            filesize = os.path.getsize(filepath)
        except OSError as e:
            return None, f"Cannot read file: {e}"
        
        # Run ffprobe
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name,bit_rate,duration",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            filepath
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
        except FileNotFoundError:
            return None, "ffprobe not found. Please install FFmpeg and add it to PATH."
        except subprocess.TimeoutExpired:
            return None, "ffprobe timed out while analyzing video."
        except Exception as e:
            return None, f"ffprobe error: {e}"
        
        if result.returncode != 0:
            return None, f"ffprobe failed: {result.stderr}"
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None, "Failed to parse ffprobe output."
        
        # Extract video stream info
        streams = data.get("streams", [])
        if not streams:
            return None, "No video stream found in file."
        
        video_stream = streams[0]
        format_info = data.get("format", {})
        
        # Get dimensions
        width = video_stream.get("width")
        height = video_stream.get("height")
        if not width or not height:
            return None, "Could not determine video dimensions."
        
        # Get FPS
        fps_str = video_stream.get("r_frame_rate", "30/1")
        try:
            fps = float(Fraction(fps_str))
        except (ValueError, ZeroDivisionError):
            fps = 30.0
        
        # Get duration (try stream first, then format)
        duration = video_stream.get("duration")
        if duration is None:
            duration = format_info.get("duration")
        try:
            duration = float(duration) if duration else 0.0
        except ValueError:
            duration = 0.0
        
        # Get codec
        codec = video_stream.get("codec_name", "unknown")
        
        # Get bitrate (try stream first, then format)
        bitrate = video_stream.get("bit_rate")
        if bitrate is None:
            bitrate = format_info.get("bit_rate")
        try:
            bitrate = int(bitrate) if bitrate else None
        except ValueError:
            bitrate = None
        
        # Get audio info
        audio_codec, audio_bitrate = self._get_audio_info(filepath)
        
        return VideoInfo(
            filepath=filepath,
            filename=os.path.basename(filepath),
            width=width,
            height=height,
            duration=duration,
            fps=fps,
            codec=codec,
            bitrate=bitrate,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            filesize=filesize
        ), None
    
    def _get_audio_info(self, filepath: str) -> Tuple[Optional[str], Optional[int]]:
        """Extract audio stream info."""
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,bit_rate",
            "-of", "json",
            filepath
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get("streams", [])
                if streams:
                    audio_stream = streams[0]
                    codec = audio_stream.get("codec_name")
                    bitrate = audio_stream.get("bit_rate")
                    try:
                        bitrate = int(bitrate) if bitrate else None
                    except ValueError:
                        bitrate = None
                    return codec, bitrate
        except Exception:
            pass
        
        return None, None
    
    def validate_for_encoding(self, filepath: str) -> Tuple[Optional[VideoInfo], Optional[str]]:
        """
        Validate video is suitable for encoding.
        
        Returns:
            Tuple of (VideoInfo, None) on success or (None, error_message) on failure.
        """
        info, error = self.get_video_info(filepath)
        
        if error:
            return None, error
        
        # Check duration
        if info.duration < 1:
            return None, "Video duration too short (< 1 second)."
        
        # Check minimum resolution
        if info.width < 100 or info.height < 100:
            return None, f"Video resolution too small: {info.width}x{info.height}"
        
        return info, None


def get_supported_extensions() -> list:
    """Get list of supported video extensions for file dialogs."""
    return list(VideoValidator.SUPPORTED_EXTENSIONS)
