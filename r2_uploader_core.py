import os
import time
import logging
import threading
from typing import Optional, Callable, Dict, Any
import queue
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.exceptions import ClientError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from watchdog.events import FileSystemEventHandler

from upload_db import UploadDB

logger = logging.getLogger("R2Core")

class UploadStatus:
    PENDING = "Pending"
    UPLOADING = "⬆️ Uploading"
    COMPLETED = "✅ Completed"
    FAILED = "❌ Failed"
    SKIPPED = "⏭️ Skipped"


class R2WatchHandler(FileSystemEventHandler):
    """Watches for new files and queues them."""
    def __init__(self, core, watch_root):
        self.core = core
        self.watch_root = watch_root

    def on_created(self, event):
        if not event.is_directory:
            self.core.queue_upload(event.src_path, self.watch_root)


class R2Core:
    def __init__(self, endpoint_url, access_key, secret_key, bucket_name):
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.s3_client = self._init_client()
        self.upload_queue = queue.Queue()
        self.watchers: Dict[str, Observer] = {}
        self.watch_roots: Dict[str, str] = {} # Map folder_path -> watch_root
        
        # Database
        self.db = UploadDB()
        
        # Callback for UI updates
        self.callback: Optional[Callable[[str, Any], None]] = None
        
        # Worker control
        self.is_running = False
        self.is_paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.worker_thread: Optional[threading.Thread] = None
        
        # Parallel uploads
        self.max_workers = 8
        self.executor: Optional[ThreadPoolExecutor] = None
        self.active_futures = set()

        # SIMPLE STATS
        self.stats = {
            'total': 0,       # Total files to process
            'uploaded': 0,    # Successfully uploaded
            'skipped': 0,     # Already in R2
            'failed': 0,      # Failed uploads
            'bytes_uploaded': 0,
            'start_time': 0,
        }
        self.stats_lock = threading.Lock()

    def _init_client(self):
        return boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name='auto'
        )

    def set_callback(self, callback_func):
        self.callback = callback_func

    def _emit(self, event_type, data):
        if self.callback:
            self.callback(event_type, data)

    def reset_stats(self):
        """Reset all stats."""
        with self.stats_lock:
            self.stats = {
                'total': 0, 'uploaded': 0, 'skipped': 0, 'failed': 0,
                'bytes_uploaded': 0, 'start_time': time.time(),
            }
        self._emit("stats_update", self.get_stats())

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
        self._emit("log", f"Started with {self.max_workers} parallel uploads")
        self._emit("status_change", "Running")

    def stop(self):
        self.is_running = False
        self.resume()
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        for observer in self.watchers.values():
            observer.stop()
            observer.join()
        self.watchers.clear()
        self._emit("log", "Stopped")
        self._emit("status_change", "Stopped")

    def pause(self):
        self.is_paused = True
        self.pause_event.clear()
        self._emit("log", "Paused")
        self._emit("status_change", "Paused")

    def resume(self):
        self.is_paused = False
        self.pause_event.set()
        self._emit("log", "Resumed")
        self._emit("status_change", "Running")

    def get_stats(self):
        with self.stats_lock:
            elapsed = time.time() - self.stats['start_time'] if self.stats['start_time'] > 0 else 0
            speed = self.stats['bytes_uploaded'] / elapsed if elapsed > 0 and not self.is_paused else 0
            done = self.stats['uploaded'] + self.stats['skipped']
            remaining = self.stats['total'] - done - self.stats['failed']
            eta = remaining * (elapsed / done) if done > 0 else 0
            
            return {
                **self.stats,
                'done': done,
                'speed': speed,
                'elapsed': elapsed,
                'eta': eta,
                'is_paused': self.is_paused,
            }

    # ========== SIMPLE UPLOAD FLOW ==========

    def add_watch_folder(self, path: str, relative_to: str = None):
        """Add a folder to watch and scan it."""
        if path in self.watchers:
            return
        if not os.path.exists(path):
            self._emit("error", f"Path not found: {path}")
            return

        watch_root = relative_to if relative_to else os.path.dirname(path)
        
        # Start watcher for new files
        handler = R2WatchHandler(self, watch_root)
        observer = Observer()
        observer.schedule(handler, path, recursive=True)
        observer.start()
        self.watchers[path] = observer
        self.watch_roots[path] = watch_root
        
        self._emit("watch_added", path)
        self._emit("log", f"Watching: {path}")
        
        # Scan existing files
        threading.Thread(target=self._scan_and_upload, args=(path, watch_root), daemon=True).start()

    def remove_watch_folder(self, path: str):
        if path in self.watchers:
            self.watchers[path].stop()
            self.watchers[path].join()
            del self.watchers[path]
            if path in self.watch_roots:
                del self.watch_roots[path]
            self._emit("watch_removed", path)
            self._emit("log", f"Removed: {path}")

    def _scan_and_upload(self, folder_path: str, watch_root: str):
        """
        SIMPLE FLOW:
        1. List all local files
        2. List all R2 files for prefix
        3. Compare and queue only missing files
        """
        folder_name = os.path.basename(folder_path)
        self._emit("log", f"Scanning {folder_name}...")
        
        # Reset stats for this scan
        self.reset_stats()
        self.stats['start_time'] = time.time()
        
        # 1. Get all local files
        local_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.startswith('.') or file.endswith('.tmp'):
                    continue
                full_path = os.path.join(root, file)
                try:
                    rel_path = os.path.relpath(full_path, watch_root)
                    r2_key = rel_path.replace(os.path.sep, '/')
                except ValueError:
                    r2_key = file
                
                # Sanitize: Replace spaces -> _, dots -> _ (preserve extension)
                # We apply this to the RELATIVE HEAD (dirs) and TAIL (filename) separately?
                # Simpler: Just handle the filename extension protection.
                
                # Split path to protect extension of the FILE
                # But we also want to sanitize directory names in the path if they have dots/spaces.
                # This is getting complex if we change directory structure R2 side.
                # Let's just sanitize the string, but protect the LAST dot.
                
                base, ext = os.path.splitext(r2_key)
                r2_key = base.replace(" ", "_").replace(".", "_") + ext

                local_files.append((full_path, r2_key))
        
        self._emit("log", f"Found {len(local_files)} local files")
        
        # 2. Get all R2 files for this prefix
        # We need to construct the prefix with the SAME sanitization logic
        # But watch out: If we sanitize the folder name, we change the prefix.
        # "Encoded/Movie.Name" -> "Encoded/Movie_Name/"
        
        rel_prefix = os.path.relpath(folder_path, watch_root).replace(os.path.sep, '/')
        # Sanitize the prefix part
        # We can't rely on splitext here easily for directories.
        # Just replace spaces/_/dots in the path segments?
        # Let's do simple replacement for now, assuming directories don't have extensions typically.
        r2_prefix = rel_prefix.replace(" ", "_").replace(".", "_") + "/"
        self._emit("log", f"R2 Prefix: {r2_prefix}")
        
        existing_keys = set()
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=r2_prefix):
                for obj in page.get('Contents', []):
                    existing_keys.add(obj['Key'])
        except ClientError as e:
            self._emit("log", f"R2 list error: {e}")
        
        self._emit("log", f"Found {len(existing_keys)} files already in R2")
        
        # DEBUG: Show sample keys for comparison
        if local_files and existing_keys:
            sample_local = local_files[0][1]
            sample_r2 = next(iter(existing_keys)) if existing_keys else "N/A"
            self._emit("log", f"Sample local key: {sample_local}")
            self._emit("log", f"Sample R2 key: {sample_r2}")
        
        # 3. Compare and queue
        to_upload = []
        skipped_count = 0
        
        for full_path, r2_key in local_files:
            if r2_key in existing_keys:
                skipped_count += 1
            else:
                to_upload.append((full_path, r2_key, watch_root))
        
        # Update stats
        with self.stats_lock:
            self.stats['total'] = len(local_files)
            self.stats['skipped'] = skipped_count
        
        self._emit("log", f"Skipping {skipped_count} (already in R2), uploading {len(to_upload)}")
        self._emit("stats_update", self.get_stats())
        
        # 4. Queue files for upload
        for full_path, r2_key, root in to_upload:
            self.queue_upload(full_path, root, r2_key)
            
        # 5. Check for 'data_*' asset folders (created by Thumbnail Maker)
        # We only check this if we are scanning a folder which might contain it.
        # But here 'folder_path' IS the video folder usually (e.g. D:\Encoded\MovieName).
        # So we look for subdirectories starting with 'data_'.
        try:
            for item in os.listdir(folder_path):
                sub_path = os.path.join(folder_path, item)
                if os.path.isdir(sub_path) and item.startswith("data_"):
                    self._emit("log", f"Found asset folder: {item}")
                    # Recursively scan/upload this asset folder
                    self._scan_and_upload(sub_path, watch_root)
        except Exception as e:
            self._emit("log", f"Asset scan error: {e}")

    def queue_upload(self, file_path: str, watch_root: str, r2_key: str = None):
        """Add a file to upload queue."""
        if file_path.endswith('.tmp') or os.path.basename(file_path).startswith('.'):
            return

        if r2_key is None:
            try:
                rel_path = os.path.relpath(file_path, watch_root)
                r2_key = rel_path.replace(os.path.sep, '/')
            except ValueError:
                r2_key = os.path.basename(file_path)
        
            except ValueError:
                r2_key = os.path.basename(file_path)
        
        # Sanitize: Replace spaces -> _, dots -> _ (preserve extension)
        base, ext = os.path.splitext(r2_key)
        r2_key = base.replace(" ", "_").replace(".", "_") + ext

        item = {
            'file_path': file_path,
            'watch_root': watch_root,
            'r2_key': r2_key,
            'id': f"{file_path}_{time.time()}",
        }
        
        self.upload_queue.put(item)
        self._emit("queue_added", item)

    def _process_queue(self):
        """Process upload queue with parallel workers."""
        while self.is_running:
            try:
                self.pause_event.wait()
                
                # Clean up done futures
                done = {f for f in self.active_futures if f.done()}
                self.active_futures -= done
                
                # Limit concurrency
                if len(self.active_futures) >= self.max_workers:
                    time.sleep(0.05)
                    continue
                
                item = self.upload_queue.get(timeout=0.5)
                future = self.executor.submit(self._do_upload, item)
                self.active_futures.add(future)
                self.upload_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Queue error: {e}")

    def _do_upload(self, item):
        """Upload a single file."""
        file_path = item['file_path']
        r2_key = item['r2_key']
        
        # Update UI: Uploading
        self._emit("upload_progress", {'id': item['id'], 'status': UploadStatus.UPLOADING, 'key': r2_key})
        
        # Check file exists
        if not os.path.exists(file_path):
            with self.stats_lock:
                self.stats['failed'] += 1
            self._emit("upload_progress", {'id': item['id'], 'status': UploadStatus.FAILED, 'error': 'File not found'})
            return
        
        try:
            file_size = os.path.getsize(file_path)
            
            # Upload to R2
            self.s3_client.upload_file(file_path, self.bucket_name, r2_key)
            
            # Success
            with self.stats_lock:
                self.stats['uploaded'] += 1
                self.stats['bytes_uploaded'] += file_size
            
            self._emit("upload_progress", {'id': item['id'], 'status': UploadStatus.COMPLETED})
            self._emit("stats_update", self.get_stats())
            
            # Mark in DB
            self.db.mark_completed(os.path.dirname(file_path), os.path.dirname(r2_key), convex_synced=True)
            
            if r2_key.endswith('master.m3u8'):
                self._emit("log", f"✅ Uploaded: {r2_key}")

        except Exception as e:
            with self.stats_lock:
                self.stats['failed'] += 1
            self._emit("upload_progress", {'id': item['id'], 'status': UploadStatus.FAILED, 'error': str(e)[:50]})
            self._emit("log", f"❌ Failed: {r2_key} - {e}")

    def _get_video_duration_from_r2(self, folder_key: str) -> float:
        """Parse video duration from HLS playlist in R2."""
        try:
            # Try to get a resolution playlist (e.g., 720p.m3u8)
            folder = os.path.dirname(folder_key)
            
            # List files in folder to find a playlist
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=folder + "/",
                MaxKeys=50
            )
            
            playlist_key = None
            for obj in response.get('Contents', []):
                key = obj['Key']
                if key.endswith('.m3u8') and not key.endswith('master.m3u8'):
                    playlist_key = key
                    break
            
            if not playlist_key:
                return 0.0
            
            # Download and parse playlist
            obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=playlist_key)
            content = obj['Body'].read().decode('utf-8')
            
            # Sum EXTINF durations
            import re
            durations = re.findall(r'#EXTINF:([\d.]+)', content)
            total = sum(float(d) for d in durations)
            return round(total, 2)
            
        except Exception as e:
            self._emit("log", f"Duration parse error: {e}")
            return 0.0



