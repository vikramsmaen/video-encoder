import os
import time
import logging
import threading
from pathlib import Path
from typing import Set

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("r2_uploader.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

R2_ENDPOINT_URL = os.getenv('R2_ENDPOINT_URL')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.getenv('R2_BUCKET_NAME')
WATCH_DIRECTORY = os.getenv('WATCH_DIRECTORY')

class R2Uploader:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto'  # R2 requires region to be 'auto' or similar
        )
        self.bucket_name = R2_BUCKET_NAME
        self.upload_queue = set()
        self.upload_lock = threading.Lock()

    def upload_file(self, file_path: str):
        """Uploads a single file to R2."""
        try:
            # Calculate object key (relative path from watch directory)
            # If file path is outside watch directory (shouldn't happen with watcher), handle gracefully
            abs_file_path = os.path.abspath(file_path)
            abs_watch_dir = os.path.abspath(WATCH_DIRECTORY)
            
            if not abs_file_path.startswith(abs_watch_dir):
                logger.warning(f"File {file_path} is outside watch directory {WATCH_DIRECTORY}")
                return

            relative_path = os.path.relpath(abs_file_path, abs_watch_dir)
            # Normalize path separators for S3 (forward slashes)
            object_key = relative_path.replace(os.path.sep, '/')

            logger.info(f"Uploading {object_key}...")
            
            # Check if file is stable (size not changing)
            if not self._wait_for_file_stability(file_path):
                 logger.error(f"File {file_path} is unstable or inaccessible used by another process.")
                 return

            self.s3_client.upload_file(file_path, self.bucket_name, object_key)
            logger.info(f"Successfully uploaded: {object_key}")

        except ClientError as e:
            logger.error(f"Failed to upload {file_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error uploading {file_path}: {e}")

    def _wait_for_file_stability(self, file_path: str, timeout: int = 10) -> bool:
        """Waits for file size to stop changing, indicating write complete."""
        start_time = time.time()
        last_size = -1
        
        while time.time() - start_time < timeout:
            try:
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    return True
                last_size = current_size
                time.sleep(1)
            except OSError:
                time.sleep(1)
        
        return False

class WatcherHandler(FileSystemEventHandler):
    def __init__(self, uploader: R2Uploader):
        self.uploader = uploader

    def on_created(self, event):
        if event.is_directory:
            return
        self.uploader.upload_file(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self.uploader.upload_file(event.src_path)

def main():
    if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, WATCH_DIRECTORY]):
        logger.error("Missing configuration. Please check your .env file.")
        return

    if not os.path.exists(WATCH_DIRECTORY):
        logger.error(f"Watch directory does not exist: {WATCH_DIRECTORY}")
        return

    uploader = R2Uploader()
    event_handler = WatcherHandler(uploader)
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIRECTORY, recursive=True)
    
    logger.info(f"Starting R2 Uploader on: {WATCH_DIRECTORY}")
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
