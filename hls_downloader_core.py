import os
import subprocess
import m3u8
import requests
import re
import threading
from urllib.parse import urljoin, urlparse
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class HLSDownloaderCore:
    def __init__(self):
        self.callbacks = []
        self._stop_event = threading.Event()

    def set_callback(self, callback):
        self.callbacks.append(callback)

    def _emit(self, event, data):
        for cb in self.callbacks:
            cb(event, data)

    def analyze_url(self, url):
        """Parse master.m3u8 or resolve a page URL to find it."""
        try:
            url = url.strip()
            self._emit("log", f"Analyzing: {url}")
            
            # If it's a page URL, try to find an m3u8 inside
            if not url.lower().endswith('.m3u8') and not '.m3u8' in url.lower():
                url = self._resolve_page_url(url)
                if not url:
                    return None

            playlist = m3u8.load(url)
            
            streams = []
            if playlist.is_variant:
                for p in playlist.playlists:
                    res = p.stream_info.resolution or (0, 0)
                    streams.append({
                        "resolution": f"{res[1]}p" if res[1] else "Unknown",
                        "uri": urljoin(url, p.uri),
                        "bandwidth": p.stream_info.bandwidth
                    })
            else:
                # Single stream playlist
                streams.append({
                    "resolution": "Source",
                    "uri": url,
                    "bandwidth": "Unknown"
                })
            
            self._emit("analysis_complete", streams)
            return streams
        except Exception as e:
            self._emit("error", f"Analysis failed: {str(e)}")
            return None

    def _resolve_page_url(self, page_url):
        """Scans a web page for m3u8 master playlist links."""
        try:
            self._emit("log", "Scanning page (Attempting to bypass blocks)...")
            
            session = requests.Session()
            retry = Retry(connect=3, backoff_factor=0.5)
            adapter = HTTPAdapter(max_retries=retry)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Increased timeout to 20s and added session support
            response = session.get(page_url, headers=headers, timeout=20)
            response.raise_for_status()
            
            html = response.text
            
            # Common patterns for m3u8 in HTML/JS
            patterns = [
                r'https?://[^\s"\']+\.m3u8[^\s"\']*', # Standard absolute URLs
                r'/[^\s"\']+\.m3u8[^\s"\']*',          # Relative URLs
                r'video_hls\s*:\s*[\'"]([^\'"]+)[\'"]', # JS Variable (XVIDEOS style)
                r'[\'"]hls_url[\'"]\s*:\s*[\'"]([^\'"]+)[\'"]', # JSON/API style
            ]
            
            found_urls = []
            for pattern in patterns:
                matches = re.findall(pattern, html)
                for m in matches:
                    # re.findall with groups returns the group, others return the match
                    url_candidate = m if isinstance(m, str) else m[0]
                    # Clean up escaped slashes (common in JS)
                    url_candidate = url_candidate.replace('\\/', '/')
                    full_url = urljoin(page_url, url_candidate)
                    if full_url not in found_urls:
                        found_urls.append(full_url)
            
            if not found_urls:
                self._emit("error", "Could not find any HLS (.m3u8) links. The site might be blocking my scanner.")
                return None
            
            # Weighted selection to find the BEST master playlist
            # Higher weight = Better candidate
            scored_urls = []
            for u in found_urls:
                score = 0
                u_lower = u.lower()
                
                # 'master' is almost always the one we want
                if 'master' in u_lower:
                    score += 100
                
                # 'hls' is the target format
                if 'hls' in u_lower:
                    score += 50
                
                # 'low' is usually a subset we want to avoid if possible
                if 'low' in u_lower:
                    score -= 80
                
                # 'pc' or 'main' are good indicators on some sites
                if 'pc' in u_lower or 'main' in u_lower:
                    score += 30

                # Short generic 'hls.m3u8' is often the master
                if u_lower.endswith('hls.m3u8'):
                    score += 40

                scored_urls.append((score, u))
            
            # Sort by score descending
            scored_urls.sort(key=lambda x: x[0], reverse=True)
            best_url = scored_urls[0][1]
            
            self._emit("log", f"Selected Best Candidate (Score {scored_urls[0][0]}): {os.path.basename(urlparse(best_url).path)}")
            return best_url

        except requests.exceptions.Timeout:
            self._emit("error", "Connection timed out. The website might be blocking automated requests or your region is restricted.")
            return None
        except Exception as e:
            self._emit("error", f"Scanner failed: {str(e)}")
            return None

    def start_download(self, streams, output_dir, video_name, merge_to_mp4=False):
        """Start the download process for multiple streams in a separate thread."""
        thread = threading.Thread(
            target=self._download_worker,
            args=(streams, output_dir, video_name, merge_to_mp4),
            daemon=True
        )
        thread.start()

    def _download_worker(self, streams, output_dir, video_name, merge_to_mp4):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in video_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
            parent_dir = os.path.join(output_dir, f"{safe_name}_{timestamp}")
            os.makedirs(parent_dir, exist_ok=True)

            self._emit("log", f"Parent Directory: {parent_dir}")
            
            for i, stream in enumerate(streams):
                if self._stop_event.is_set():
                    break
                
                res_name = stream.get('resolution', f"Stream_{i}")
                m3u8_url = stream['uri']
                
                self._emit("log", f"[{i+1}/{len(streams)}] Downloading {res_name}...")
                
                # Create subfolder for this resolution
                res_dir = os.path.join(parent_dir, res_name)
                os.makedirs(res_dir, exist_ok=True)
                
                output_file = os.path.join(res_dir, "output.ts")
                if merge_to_mp4:
                    output_file = os.path.join(res_dir, f"{safe_name}_{res_name}.mp4")

                # Construct FFmpeg command
                cmd = [
                    "ffmpeg", "-y",
                    "-i", m3u8_url,
                    "-c", "copy"
                ]
                
                if merge_to_mp4:
                    cmd.extend(["-bsf:a", "aac_adtstoasc"])
                
                cmd.append(output_file)

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )

                for line in process.stdout:
                    if self._stop_event.is_set():
                        process.terminate()
                        self._emit("log", "Download cancelled by user")
                        return
                    if "time=" in line:
                        # Add resolution context to progress
                        self._emit("progress", f"[{res_name}] {line.strip()}")

                process.wait()

                if process.returncode == 0:
                    self._emit("log", f"Done: {res_name} -> {os.path.basename(output_file)}")
                else:
                    self._emit("log", f"Error: FFmpeg failed for {res_name} (Code {process.returncode})")

            if not self._stop_event.is_set():
                self._emit("log", "All tasks completed!")
                self._emit("download_complete", parent_dir)

        except Exception as e:
            self._emit("error", f"Download worker error: {str(e)}")

    def cancel(self):
        self._stop_event.set()
