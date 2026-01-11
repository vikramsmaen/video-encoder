"""
Universal Media Scanner Core
Uses Playwright to intercept all network requests and detect media files.
"""

import re
import threading
from urllib.parse import urlparse, urljoin
from collections import defaultdict
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class MediaItem:
    """Represents a detected media item."""
    
    def __init__(self, url, media_type, resolution=None, size=None, content_type=None):
        self.url = url
        self.media_type = media_type  # 'm3u8', 'mp4', 'webm', 'ts_segment', 'ts_group'
        self.resolution = resolution
        self.size = size
        self.content_type = content_type
        self.segments = []  # For ts_group type
        self.is_selected = False
        self.timestamp = datetime.now()
    
    def __repr__(self):
        if self.media_type == 'ts_group':
            return f"<MediaItem ts_group: {len(self.segments)} segments>"
        return f"<MediaItem {self.media_type}: {self.url[:60]}...>"


class SegmentGrouper:
    """Groups .ts segments by their URL pattern."""
    
    def __init__(self):
        self.segment_patterns = defaultdict(list)
        
    def add_segment(self, url):
        """Add a segment URL and return its group key."""
        # Extract the base pattern by replacing segment numbers
        # Examples:
        # seg-17-v1-a1.ts -> seg-{}-v1-a1.ts
        # segment_0001.ts -> segment_{}.ts
        # chunk-00017.ts -> chunk-{}.ts
        
        pattern_key = self._extract_pattern(url)
        self.segment_patterns[pattern_key].append(url)
        return pattern_key
    
    def _extract_pattern(self, url):
        """Extract pattern key from segment URL."""
        parsed = urlparse(url)
        path = parsed.path
        
        # Replace numbers in the filename with placeholder
        # Find the last component (filename)
        parts = path.rsplit('/', 1)
        if len(parts) == 2:
            base_path, filename = parts
        else:
            base_path, filename = '', parts[0]
        
        # Replace numeric sequences in filename
        pattern_filename = re.sub(r'\d+', '{}', filename)
        
        # Combine base URL (without query) with pattern filename
        base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
        return f"{base_url}/{pattern_filename}"
    
    def get_groups(self):
        """Return all segment groups with 2+ segments."""
        return {k: sorted(v, key=self._extract_segment_number) 
                for k, v in self.segment_patterns.items() 
                if len(v) >= 2}
    
    def _extract_segment_number(self, url):
        """Extract the segment number for sorting."""
        # Find numbers in the URL path
        matches = re.findall(r'(\d+)', urlparse(url).path)
        if matches:
            # Return the last number (usually the segment index)
            return int(matches[-1])
        return 0


class MediaScannerCore:
    """
    Core scanner that uses Playwright to:
    1. Open a browser with network interception
    2. Navigate to user-provided URLs
    3. Detect and collect media files in real-time
    """
    
    MEDIA_PATTERNS = {
        'm3u8': [
            r'\.m3u8(\?|$)',
            r'application/vnd\.apple\.mpegurl',
            r'application/x-mpegurl',
        ],
        'mp4': [
            r'\.mp4(\?|$)',
            r'video/mp4',
        ],
        'webm': [
            r'\.webm(\?|$)',
            r'video/webm',
        ],
        'ts_segment': [
            r'\.ts(\?|$)',
            r'video/mp2t',
            r'video/MP2T',
        ],
        'mkv': [
            r'\.mkv(\?|$)',
            r'video/x-matroska',
        ],
    }
    
    # URLs to ignore (ads, trackers, etc.)
    IGNORE_PATTERNS = [
        r'googlesyndication',
        r'doubleclick',
        r'analytics',
        r'facebook\.com',
        r'twitter\.com',
        r'adsense',
        r'adservice',
    ]
    
    def __init__(self):
        self.callbacks = []
        self.detected_media = []  # List of MediaItem
        self.segment_grouper = SegmentGrouper()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._browser_running = False
        
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
    
    def _should_ignore(self, url):
        """Check if URL should be ignored (ads, trackers)."""
        url_lower = url.lower()
        for pattern in self.IGNORE_PATTERNS:
            if re.search(pattern, url_lower):
                return True
        return False
    
    def _detect_media_type(self, url, content_type=None):
        """Detect media type from URL or content-type."""
        url_lower = url.lower()
        content_type_lower = (content_type or '').lower()
        
        for media_type, patterns in self.MEDIA_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower) or re.search(pattern, content_type_lower):
                    return media_type
        return None
    
    def _on_request(self, request):
        """Handle network requests - catch media URLs early."""
        try:
            url = request.url
            
            # Skip ignored URLs
            if self._should_ignore(url):
                return
            
            # Detect media type from URL alone
            media_type = self._detect_media_type(url, None)
            
            if media_type:
                # Log detection for debugging
                self._emit('log', f"🔍 Detected {media_type}: {url[:80]}...")
                
        except Exception as e:
            pass  # Don't spam logs with request errors
    
    def _on_response(self, response):
        """Handle network responses."""
        try:
            url = response.url
            
            # Skip ignored URLs
            if self._should_ignore(url):
                return
            
            # Get content type from headers
            content_type = response.headers.get('content-type', '')
            
            # Detect media type
            media_type = self._detect_media_type(url, content_type)
            
            if media_type:
                with self._lock:
                    self._handle_media_detection(url, media_type, content_type, response)
                    
        except Exception as e:
            self._emit('log', f"Response handler error: {e}")
    
    def _handle_media_detection(self, url, media_type, content_type, response):
        """Process a detected media item."""
        
        # Check for duplicate
        existing_urls = [m.url for m in self.detected_media if m.media_type != 'ts_group']
        if url in existing_urls:
            return
        
        if media_type == 'ts_segment':
            # Add to segment grouper
            group_key = self.segment_grouper.add_segment(url)
            
            # Get current groups
            groups = self.segment_grouper.get_groups()
            
            if group_key in groups:
                segments = groups[group_key]
                
                # Find or create a ts_group MediaItem
                existing_group = None
                for m in self.detected_media:
                    if m.media_type == 'ts_group' and m.url == group_key:
                        existing_group = m
                        break
                
                if existing_group:
                    existing_group.segments = segments
                    self._emit('media_updated', existing_group)
                else:
                    # Create new group
                    group_item = MediaItem(
                        url=group_key,
                        media_type='ts_group',
                        content_type='video/mp2t'
                    )
                    group_item.segments = segments
                    self.detected_media.append(group_item)
                    self._emit('media_detected', group_item)
                    self._emit('log', f"📦 Segment group detected: {len(segments)} segments")
        else:
            # Direct media file
            size = response.headers.get('content-length')
            
            # Try to extract resolution from URL
            resolution = None
            res_match = re.search(r'(\d{3,4})p', url)
            if res_match:
                resolution = res_match.group(1) + 'p'
            
            item = MediaItem(
                url=url,
                media_type=media_type,
                resolution=resolution,
                size=int(size) if size else None,
                content_type=content_type
            )
            
            self.detected_media.append(item)
            self._emit('media_detected', item)
            self._emit('log', f"📹 {media_type.upper()} detected: {resolution or 'unknown'} resolution")
    
    def start_browser(self, headless=False):
        """Start the Playwright browser with stealth settings."""
        if not PLAYWRIGHT_AVAILABLE:
            self._emit('error', "Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        
        try:
            self._emit('log', "Starting Chrome browser (with video codecs)...")
            
            self.playwright = sync_playwright().start()
            
            # Use the user's installed Chrome browser (has H.264/AAC codecs)
            # Falls back to chromium if Chrome is not installed
            try:
                self.browser = self.playwright.chromium.launch(
                    channel='chrome',  # Use installed Chrome for video codec support
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-automation',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-infobars',
                        '--autoplay-policy=no-user-gesture-required',
                        '--window-size=1280,720',
                    ]
                )
                self._emit('log', "Using installed Chrome browser")
            except Exception:
                # Fallback to Playwright's Chromium if Chrome not installed
                self._emit('log', "Chrome not found, using Chromium (may have codec issues)")
                self.browser = self.playwright.chromium.launch(
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-automation',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--autoplay-policy=no-user-gesture-required',
                        '--window-size=1280,720',
                    ]
                )
            
            # Create context with full permissions for media playback
            self.context = self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                permissions=['geolocation'],  # Grant permissions
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=True,  # Bypass Content Security Policy
            )
            
            self.page = self.context.new_page()
            
            # Apply anti-detection scripts before any page loads
            self.page.add_init_script("""
                // Overwrite the 'webdriver' property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Overwrite plugins to look like a real browser
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Overwrite languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Override permissions query
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Remove automation-related properties
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            """)
            
            # Set up network interception - use BOTH request and response
            # Some media loads via fetch/XHR and may not trigger response events
            self.page.on('request', self._on_request)
            self.page.on('response', self._on_response)
            
            self._browser_running = True
            self._emit('log', "Browser started. Network interception active.")
            self._emit('browser_ready', None)
            return True
            
        except Exception as e:
            self._emit('error', f"Failed to start browser: {e}")
            return False
    
    def navigate(self, url):
        """Navigate to a URL."""
        if not self.page:
            self._emit('error', "Browser not started")
            return False
        
        try:
            # Clear previous media
            with self._lock:
                self.detected_media.clear()
                self.segment_grouper = SegmentGrouper()
            
            self._emit('media_cleared', None)
            self._emit('log', f"Navigating to: {url}")
            
            self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            self._emit('log', "Page loaded. Play the video to detect media streams.")
            self._emit('navigation_complete', url)
            return True
            
        except Exception as e:
            self._emit('error', f"Navigation failed: {e}")
            return False
    
    def get_detected_media(self):
        """Return list of all detected media items."""
        with self._lock:
            return list(self.detected_media)
    
    def stop_browser(self):
        """Stop and cleanup the browser."""
        if not self._browser_running:
            return
        
        self._browser_running = False
        
        # Close in order, suppressing errors since browser may already be gone
        try:
            if self.page:
                try:
                    self.page.close()
                except:
                    pass
                self.page = None
        except:
            pass
        
        try:
            if self.context:
                try:
                    self.context.close()
                except:
                    pass
                self.context = None
        except:
            pass
        
        try:
            if self.browser:
                try:
                    self.browser.close()
                except:
                    pass
                self.browser = None
        except:
            pass
        
        try:
            if self.playwright:
                try:
                    self.playwright.stop()
                except:
                    pass
                self.playwright = None
        except:
            pass
        
        try:
            self._emit('log', "Browser stopped.")
            self._emit('browser_stopped', None)
        except:
            pass
    
    def download_media(self, media_item, output_dir, video_name, merge_to_mp4=True):
        """Download a media item in a separate thread."""
        thread = threading.Thread(
            target=self._download_worker,
            args=(media_item, output_dir, video_name, merge_to_mp4),
            daemon=True
        )
        thread.start()
    
    def _download_worker(self, media_item, output_dir, video_name, merge_to_mp4):
        """Worker thread for downloading media."""
        import subprocess
        import os
        import requests
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in video_name if c.isalnum() or c in (' ', '.', '_')).rstrip()
            if not safe_name:
                safe_name = "video"
            
            parent_dir = os.path.join(output_dir, f"{safe_name}_{timestamp}")
            os.makedirs(parent_dir, exist_ok=True)
            
            self._emit('log', f"📁 Output directory: {parent_dir}")
            
            if media_item.media_type == 'm3u8':
                self._download_m3u8(media_item, parent_dir, safe_name, merge_to_mp4)
            elif media_item.media_type == 'ts_group':
                self._download_ts_group(media_item, parent_dir, safe_name, merge_to_mp4)
            elif media_item.media_type in ('mp4', 'webm', 'mkv'):
                self._download_direct(media_item, parent_dir, safe_name)
            else:
                self._emit('error', f"Unknown media type: {media_item.media_type}")
                return
            
            self._emit('download_complete', parent_dir)
            
        except Exception as e:
            self._emit('error', f"Download failed: {e}")
    
    def _download_m3u8(self, media_item, parent_dir, video_name, merge_to_mp4):
        """Download m3u8 stream using FFmpeg."""
        import subprocess
        import os
        
        resolution = media_item.resolution or "source"
        output_ext = "mp4" if merge_to_mp4 else "ts"
        output_file = os.path.join(parent_dir, f"{video_name}_{resolution}.{output_ext}")
        
        self._emit('log', f"⬇️ Downloading m3u8 stream...")
        
        cmd = ["ffmpeg", "-y", "-i", media_item.url, "-c", "copy"]
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
                return
            if "time=" in line:
                self._emit('progress', line.strip())
        
        process.wait()
        
        if process.returncode == 0:
            self._emit('log', f"✅ Downloaded: {os.path.basename(output_file)}")
        else:
            self._emit('error', f"FFmpeg failed with code {process.returncode}")
    
    def _download_ts_group(self, media_item, parent_dir, video_name, merge_to_mp4):
        """Download and merge .ts segments."""
        import subprocess
        import os
        import requests
        
        segments = media_item.segments
        total = len(segments)
        
        self._emit('log', f"⬇️ Downloading {total} segments...")
        
        # Create temp directory for segments
        temp_dir = os.path.join(parent_dir, "temp_segments")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Download all segments
        segment_files = []
        session = requests.Session()
        
        for i, seg_url in enumerate(segments):
            if self._stop_event.is_set():
                return
            
            seg_file = os.path.join(temp_dir, f"seg_{i:05d}.ts")
            
            try:
                response = session.get(seg_url, timeout=30)
                response.raise_for_status()
                
                with open(seg_file, 'wb') as f:
                    f.write(response.content)
                
                segment_files.append(seg_file)
                
                if (i + 1) % 10 == 0 or i == total - 1:
                    self._emit('progress', f"Downloaded {i+1}/{total} segments")
                    
            except Exception as e:
                self._emit('log', f"⚠️ Failed segment {i}: {e}")
        
        if not segment_files:
            self._emit('error', "No segments downloaded")
            return
        
        # Create concat file
        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            for seg_file in segment_files:
                f.write(f"file '{seg_file}'\n")
        
        # Merge with FFmpeg
        self._emit('log', "🔧 Merging segments...")
        
        output_ext = "mp4" if merge_to_mp4 else "ts"
        output_file = os.path.join(parent_dir, f"{video_name}.{output_ext}")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
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
            if "time=" in line:
                self._emit('progress', f"Merging: {line.strip()}")
        
        process.wait()
        
        # Cleanup temp files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        if process.returncode == 0:
            self._emit('log', f"✅ Merged: {os.path.basename(output_file)}")
        else:
            self._emit('error', f"Merge failed with code {process.returncode}")
    
    def _download_direct(self, media_item, parent_dir, video_name):
        """Download a direct video file."""
        import os
        import requests
        
        ext = media_item.media_type
        resolution = media_item.resolution or ""
        output_file = os.path.join(parent_dir, f"{video_name}_{resolution}.{ext}" if resolution else f"{video_name}.{ext}")
        
        self._emit('log', f"⬇️ Downloading {ext.upper()} file...")
        
        try:
            response = requests.get(media_item.url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if self._stop_event.is_set():
                        return
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        if downloaded % (1024 * 1024) < 8192:  # Every ~1MB
                            self._emit('progress', f"Downloaded: {pct:.1f}%")
            
            self._emit('log', f"✅ Downloaded: {os.path.basename(output_file)}")
            
        except Exception as e:
            self._emit('error', f"Download failed: {e}")
    
    def cancel(self):
        """Cancel ongoing operations."""
        self._stop_event.set()


if __name__ == "__main__":
    # Quick test
    def callback(event, data):
        print(f"[{event}] {data}")
    
    scanner = MediaScannerCore()
    scanner.set_callback(callback)
    
    if scanner.start_browser(headless=False):
        scanner.navigate("https://example.com")
        input("Press Enter to stop...")
        scanner.stop_browser()
