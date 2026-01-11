"""
Encoder Core Module
FFmpeg-based HLS encoding with multi-resolution output.
Optimized for lower resource usage while maintaining quality.
"""

import subprocess
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Callable, Dict
from enum import Enum


class EncodingStatus(Enum):
    PENDING = "pending"
    ENCODING = "encoding"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ResolutionConfig:
    """Configuration for a resolution variant."""
    name: str
    width: int
    height: int
    bitrate: int  # in kbps
    
    @property
    def bitrate_str(self) -> str:
        return f"{self.bitrate}k"


# Resolution ladder - from lowest to highest
RESOLUTION_LADDER = [
    ResolutionConfig("240p", 426, 240, 400),
    ResolutionConfig("360p", 640, 360, 800),
    ResolutionConfig("480p", 854, 480, 1400),
    ResolutionConfig("720p", 1280, 720, 2800),
    ResolutionConfig("1080p", 1920, 1080, 5000),
    ResolutionConfig("1440p", 2560, 1440, 8000),
    ResolutionConfig("4K", 3840, 2160, 15000),
]


@dataclass
class EncodingProgress:
    """Progress information for an encoding job."""
    current_time: float = 0.0
    total_duration: float = 0.0
    fps: float = 0.0
    bitrate: str = ""
    speed: str = ""
    
    @property
    def percent(self) -> float:
        if self.total_duration <= 0:
            return 0.0
        return min(100.0, (self.current_time / self.total_duration) * 100)
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Estimate remaining time in seconds."""
        if not self.speed or self.total_duration <= 0:
            return None
        try:
            speed_val = float(self.speed.replace('x', ''))
            if speed_val <= 0:
                return None
            remaining_time = self.total_duration - self.current_time
            return remaining_time / speed_val
        except ValueError:
            return None


@dataclass
class EncodingJob:
    """Represents a video encoding job."""
    input_path: str
    output_folder: str
    video_name: str
    output_dir: str  # Base output directory
    resolutions: List[ResolutionConfig]
    source_width: int
    source_height: int
    source_duration: float
    source_fps: float
    preset: str = "veryfast"
    status: EncodingStatus = EncodingStatus.PENDING
    progress: EncodingProgress = None
    error_message: str = ""
    
    def __post_init__(self):
        if self.progress is None:
            self.progress = EncodingProgress(total_duration=self.source_duration)
    
    @property
    def output_path(self) -> str:
        """Full output path for this job."""
        return os.path.join(self.output_dir, self.output_folder)
    
    @property
    def segments_path(self) -> str:
        """Path to segments directory (now flattened to output_path)."""
        return self.output_path


class HLSEncoder:
    """FFmpeg-based HLS encoder with progress tracking and GPU acceleration."""
    
    PRESETS = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
    NVENC_PRESETS = ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]  # p1=fastest, p7=slowest
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self._current_process: Optional[subprocess.Popen] = None
        self._cancelled = False
        self.gpu_encoder = self._detect_gpu_encoder()
    
    def _detect_gpu_encoder(self) -> Optional[str]:
        """Detect and TEST available GPU encoder (NVENC, QSV, AMF)."""
        encoders_to_test = [
            ("nvenc", "h264_nvenc"),
            ("qsv", "h264_qsv"),
            ("amf", "h264_amf"),
        ]
        
        for name, codec in encoders_to_test:
            try:
                # Actually TEST the encoder with a tiny encode
                result = subprocess.run(
                    [
                        self.ffmpeg_path, "-hide_banner", "-y",
                        "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1",
                        "-c:v", codec, "-f", "null", "-"
                    ],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                # If it succeeds (return code 0), this encoder works
                if result.returncode == 0:
                    return name
            except Exception:
                continue
        
        return None  # Fall back to CPU
    
    def get_encoder_info(self) -> str:
        """Get human-readable encoder info."""
        if self.gpu_encoder == "nvenc":
            return "NVIDIA NVENC (GPU)"
        elif self.gpu_encoder == "qsv":
            return "Intel QuickSync (GPU)"
        elif self.gpu_encoder == "amf":
            return "AMD AMF (GPU)"
        return "x264 (CPU)"
    
    def get_available_resolutions(self, source_width: int, source_height: int) -> List[ResolutionConfig]:
        """
        Get list of resolutions:
        1. ALWAYS include the Source resolution.
        2. Include all standard resolutions where height < source_height.
        """
        # Calculate appropriate bitrate for source if it's non-standard
        pixels = source_width * source_height
        if pixels < 150000:  # ~240p
             bitrate = 400
        elif pixels < 300000: # ~360p
             bitrate = 800
        elif pixels < 500000: # ~480p
             bitrate = 1400
        elif pixels < 1000000: # ~720p
             bitrate = 2800
        elif pixels < 2500000: # ~1080p
             bitrate = 5000
        elif pixels < 4000000: # ~1440p
             bitrate = 8000
        else: # 4K+
             bitrate = 15000

        source_res = ResolutionConfig(
            name="Source",
            width=source_width,
            height=source_height,
            bitrate=bitrate
        )

        available = [source_res]
        
        for res in RESOLUTION_LADDER:
            # Add standard resolutions strictly lower than source height
            if res.height < source_height:
                available.append(res)
        
        # Sort by height descending
        available.sort(key=lambda x: x.height, reverse=True)
        
        return available
    
    def create_encoding_job(
        self,
        input_path: str,
        output_folder: str,
        video_name: str,
        output_dir: str,
        source_width: int,
        source_height: int,
        source_duration: float,
        source_fps: float,
        selected_resolutions: Optional[List[str]] = None,
        preset: str = "veryfast"
    ) -> EncodingJob:
        """Create an encoding job with specified parameters."""
        
        # Get available resolutions
        available = self.get_available_resolutions(source_width, source_height)
        
        # Filter by selected if specified
        if selected_resolutions:
            resolutions = [r for r in available if r.name in selected_resolutions]
        else:
            resolutions = available
        
        return EncodingJob(
            input_path=input_path,
            output_folder=output_folder,
            video_name=video_name,
            output_dir=output_dir,
            resolutions=resolutions,
            source_width=source_width,
            source_height=source_height,
            source_duration=source_duration,
            source_fps=source_fps,
            preset=preset
        )
    
    def encode(
        self,
        job: EncodingJob,
        progress_callback: Optional[Callable[[EncodingProgress], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Execute HLS encoding for a job.
        
        Returns:
            True on success, False on failure.
        """
        self._cancelled = False
        job.status = EncodingStatus.ENCODING
        job.progress = EncodingProgress(total_duration=job.source_duration)
        
        # Create output directory
        try:
            os.makedirs(job.output_path, exist_ok=True)
        except OSError as e:
            job.status = EncodingStatus.FAILED
            job.error_message = f"Failed to create output directory: {e}"
            return False
        
        # Build FFmpeg command
        cmd = self._build_ffmpeg_command(job)
        
        if log_callback:
            log_callback(f"Starting encoding: {job.video_name}")
            log_callback(f"Output: {job.output_path}")
            log_callback(f"Resolutions: {', '.join(r.name for r in job.resolutions)}")
        
        # Run FFmpeg
        try:
            self._current_process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                encoding='utf-8',
                errors='replace',  # Handle encoding errors gracefully
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Parse progress from stderr
            stderr_lines = []
            for line in self._current_process.stderr:
                if self._cancelled:
                    self._current_process.terminate()
                    job.status = EncodingStatus.CANCELLED
                    return False
                
                # Capture last 20 lines for error debugging
                stderr_lines.append(line.strip())
                if len(stderr_lines) > 20:
                    stderr_lines.pop(0)
                
                # Parse progress
                progress = self._parse_progress(line, job.source_duration)
                if progress:
                    job.progress = progress
                    if progress_callback:
                        progress_callback(progress)
                
                # Log output - but avoid flooding log with frame details
                if log_callback and line.strip() and not line.startswith("frame="):
                    log_callback(line.strip())
            
            self._current_process.wait()
            
            if self._current_process.returncode != 0:
                job.status = EncodingStatus.FAILED
                
                # Construct detailed error message
                error_details = "\n".join(stderr_lines)
                job.error_message = f"FFmpeg exited with code {self._current_process.returncode}\n\nLast Output:\n{error_details}"
                return False
            
            # Verify output
            if not self._verify_output(job):
                job.status = EncodingStatus.FAILED
                job.error_message = "Output verification failed"
                return False
            
            job.status = EncodingStatus.COMPLETED
            job.progress.current_time = job.source_duration
            if progress_callback:
                progress_callback(job.progress)
            
            if log_callback:
                log_callback(f"Encoding completed: {job.video_name}")
            
            return True
            
        except FileNotFoundError:
            job.status = EncodingStatus.FAILED
            job.error_message = "FFmpeg not found. Please install FFmpeg."
            return False
        except Exception as e:
            job.status = EncodingStatus.FAILED
            job.error_message = str(e)
            return False
        finally:
            self._current_process = None
    
    def cancel(self):
        """Cancel current encoding."""
        self._cancelled = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass
    
    def _build_ffmpeg_command(self, job: EncodingJob) -> List[str]:
        """Build FFmpeg command for multi-resolution HLS encoding."""
        
        num_resolutions = len(job.resolutions)
        
        # Calculate GOP size (2 seconds of frames)
        gop_size = int(job.source_fps * 2)
        
        # Build filter complex for splitting video
        filter_parts = [f"[0:v]split={num_resolutions}"]
        filter_parts.extend([f"[v{i}]" for i in range(num_resolutions)])
        filter_complex = "".join(filter_parts) + ";"
        
        # Add scaling for each resolution
        for i, res in enumerate(job.resolutions):
            # Use scale with force_original_aspect_ratio to maintain aspect ratio
            # and pad if necessary, or use simpler scale
            filter_complex += f"[v{i}]scale={res.width}:{res.height}:force_original_aspect_ratio=decrease,pad={res.width}:{res.height}:(ow-iw)/2:(oh-ih)/2[v{res.name}];"
        
        # Remove trailing semicolon
        filter_complex = filter_complex.rstrip(";")
        
        cmd = [
            self.ffmpeg_path,
            "-i", job.input_path,
            "-filter_complex", filter_complex,
        ]
        
        # Map each resolution with its settings - use GPU if available
        video_encoder = "libx264"
        encoder_opts = []
        
        if self.gpu_encoder == "nvenc":
            video_encoder = "h264_nvenc"
            # Map preset to NVENC (ultrafast -> p1, veryslow -> p7)
            preset_map = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3", 
                         "faster": "p4", "fast": "p5", "medium": "p5", 
                         "slow": "p6", "slower": "p7", "veryslow": "p7"}
            nvenc_preset = preset_map.get(job.preset, "p3")
            encoder_opts = ["-preset", nvenc_preset, "-rc", "vbr", "-cq", "23"]
        elif self.gpu_encoder == "qsv":
            video_encoder = "h264_qsv"
            encoder_opts = ["-preset", "faster", "-global_quality", "23"]
        elif self.gpu_encoder == "amf":
            video_encoder = "h264_amf"
            encoder_opts = ["-quality", "speed", "-rc", "vbr_latency"]
        else:
            # CPU encoding with preset
            encoder_opts = ["-preset", job.preset, "-profile:v", "main", "-level", "4.0",
                          "-x264opts", "rc-lookahead=20"]
        
        for i, res in enumerate(job.resolutions):
            cmd.extend([
                "-map", f"[v{res.name}]",
                "-map", "0:a?",
                f"-c:v:{i}", video_encoder,
                f"-b:v:{i}", res.bitrate_str,
                f"-maxrate:v:{i}", f"{int(res.bitrate * 1.5)}k",
                f"-bufsize:v:{i}", f"{res.bitrate * 2}k",
                f"-c:a:{i}", "aac",
                f"-b:a:{i}", "128k",
                "-ac", "2",
            ])
        
        # Add encoder-specific options
        cmd.extend(encoder_opts)
        
        # Common encoding settings
        cmd.extend([
            "-g", str(gop_size),
            "-keyint_min", str(gop_size),
            "-sc_threshold", "0",
            "-threads", "0",
        ])
        
        # HLS settings
        cmd.extend([
            "-f", "hls",
            "-hls_time", "6",
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", os.path.join(job.output_path, "%v_%03d.ts"),
            "-master_pl_name", "master.m3u8",
        ])
        
        # Variable stream map with named streams - use resolution names for output filenames
        # Format: "v:0,a:0,name:240p v:1,a:1,name:360p ..."
        var_stream_map = " ".join([f"v:{i},a:{i},name:{res.name}" for i, res in enumerate(job.resolutions)])
        cmd.extend([
            "-var_stream_map", var_stream_map,
        ])
        
        # Output path pattern - %v will be replaced with the stream name (resolution)
        output_pattern = os.path.join(job.output_path, "%v.m3u8")
        cmd.append(output_pattern)
        
        return cmd
    
    def _parse_progress(self, line: str, total_duration: float) -> Optional[EncodingProgress]:
        """Parse FFmpeg progress output."""
        
        # Look for time=HH:MM:SS.ms
        time_match = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', line)
        if not time_match:
            return None
        
        hours, mins, secs, ms = map(int, time_match.groups())
        current_time = hours * 3600 + mins * 60 + secs + ms / 100
        
        progress = EncodingProgress(
            current_time=current_time,
            total_duration=total_duration
        )
        
        # Parse FPS
        fps_match = re.search(r'fps=\s*(\d+\.?\d*)', line)
        if fps_match:
            progress.fps = float(fps_match.group(1))
        
        # Parse bitrate
        bitrate_match = re.search(r'bitrate=\s*(\d+\.?\d*\w+/s)', line)
        if bitrate_match:
            progress.bitrate = bitrate_match.group(1)
        
        # Parse speed
        speed_match = re.search(r'speed=\s*(\d+\.?\d*x)', line)
        if speed_match:
            progress.speed = speed_match.group(1)
        
        return progress
    
    def _verify_output(self, job: EncodingJob) -> bool:
        """Verify that all expected output files were created."""
        
        # Check master playlist
        master_path = os.path.join(job.output_path, "master.m3u8")
        if not os.path.exists(master_path):
            return False
        
        # Check each resolution playlist
        for res in job.resolutions:
            playlist_path = os.path.join(job.output_path, f"{res.name}.m3u8")
            if not os.path.exists(playlist_path):
                return False
        
        # Check at least some segments exist
        segments = [f for f in os.listdir(job.segments_path) if f.endswith('.ts')]
        if not segments:
            return False
        
        return True


def get_presets() -> List[str]:
    """Get list of available encoding presets."""
    return HLSEncoder.PRESETS


def get_resolution_names() -> List[str]:
    """Get list of resolution names."""
    return [r.name for r in RESOLUTION_LADDER]


.0

