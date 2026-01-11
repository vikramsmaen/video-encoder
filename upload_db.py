import sqlite3
import os
import threading
from datetime import datetime
from typing import Optional, Dict

class UploadDB:
    def __init__(self, db_path="r2_uploads.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # Videos table: Tracks the master folder status
            # Schema Migration: We'll add columns if they don't exist (simplest way for dev)
            try:
                cursor.execute("ALTER TABLE videos ADD COLUMN convex_status TEXT DEFAULT 'PENDING'")
            except sqlite3.OperationalError:
                pass # Column exists

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT UNIQUE,
                    r2_key_prefix TEXT,
                    status TEXT,
                    convex_status TEXT DEFAULT 'PENDING',
                    uploaded_files INTEGER DEFAULT 0,
                    total_files INTEGER DEFAULT 0,
                    last_updated TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()

    def _normalize_path(self, path: str) -> str:
        return os.path.normpath(path).lower()

    def get_video(self, source_path: str) -> Optional[Dict]:
        norm_path = self._normalize_path(source_path)
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE source_path = ?", (norm_path,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return dict(row)
            return None

    def add_or_update_video(self, source_path: str, r2_key: str, status: str = "PENDING", convex_status: str = "PENDING"):
        norm_path = self._normalize_path(source_path)
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # Upsert with convex_status
            cursor.execute("""
                INSERT INTO videos (source_path, r2_key_prefix, status, convex_status, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_path) DO UPDATE SET
                    status=excluded.status,
                    convex_status=excluded.convex_status,
                    last_updated=excluded.last_updated
            """, (norm_path, r2_key, status, convex_status, now))
            
            conn.commit()
            conn.close()

    def mark_completed(self, source_path: str, r2_key: str, convex_synced: bool = False):
        status = "COMPLETED" if convex_synced else "UPLOADED_PARTIAL"
        c_status = "SYNCED" if convex_synced else "FAILED"
        
        self.add_or_update_video(source_path, r2_key, status, c_status)

    def update_progress(self, source_path: str):
        # We could track individual files, but for performance we might just bump a counter
        # For now, we mainly care about Master Status
        pass

    def get_all_videos(self) -> list:
        """Get all videos from the database for display in UI."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, source_path, r2_key_prefix, status, convex_status, last_updated 
                FROM videos 
                ORDER BY last_updated DESC
            """)
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]

    def get_summary_stats(self) -> dict:
        """Get summary statistics for the UI."""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'COMPLETED'")
            completed = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'UPLOADED_PARTIAL'")
            partial = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM videos WHERE status = 'PENDING'")
            pending = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM videos")
            total = cursor.fetchone()[0]
            conn.close()
            return {
                'completed': completed,
                'partial': partial,
                'pending': pending,
                'total': total
            }

    def reset_video(self, source_path: str):
        """Reset a video's status to allow re-upload."""
        norm_path = self._normalize_path(source_path)
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM videos WHERE source_path = ?", (norm_path,))
            conn.commit()
            conn.close()
