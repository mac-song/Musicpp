import sqlite3
import os
import json
import threading
from typing import List, Dict

from src.utils.constants import CONFIG_DIR
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MetadataDB:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._db_path = os.path.join(CONFIG_DIR, "metadata_cache.db")
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._local = threading.local()
        self._init_db()
        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self._db_path)
        return self._local.connection

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metadata (
                path TEXT PRIMARY KEY,
                folder TEXT,
                metadata TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_metadata_folder
            ON metadata(folder)
        ''')
        conn.commit()

    def save_metadata(self, folder: str, metadata_list: List[Dict]):
        if not metadata_list:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        folder = os.path.normpath(folder)
        try:
            for metadata in metadata_list:
                path = os.path.normpath(metadata.get("path", ""))
                if not path:
                    continue
                metadata_json = json.dumps(metadata, ensure_ascii=False)
                cursor.execute('''
                    INSERT OR REPLACE INTO metadata
                    (path, folder, metadata, last_updated)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (path, folder, metadata_json))
            conn.commit()
            logger.info(f"Saved {len(metadata_list)} metadata records (folder: {folder})")
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")
            conn.rollback()

    def load_metadata(self, folder: str) -> List[Dict]:
        folder = os.path.normpath(folder)
        conn = self._get_connection()
        cursor = conn.cursor()
        results = []
        try:
            cursor.execute('''
                SELECT metadata FROM metadata
                WHERE folder = ?
                ORDER BY path
            ''', (folder,))
            rows = cursor.fetchall()
            for row in rows:
                try:
                    results.append(json.loads(row[0]))
                except (json.JSONDecodeError, TypeError):
                    continue
            if results:
                logger.info(f"Loaded {len(results)} metadata records from cache (folder: {folder})")
        except Exception as e:
            logger.error(f"Error loading metadata from cache: {e}")
        return results

    def is_cache_valid(self, folder: str) -> bool:
        folder = os.path.normpath(folder)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT path, metadata FROM metadata WHERE folder = ?', (folder,))
            rows = cursor.fetchall()
            if not rows:
                return False
            for row in rows:
                try:
                    cached = json.loads(row[1])
                    cached_path = cached.get("path", "")
                    if not os.path.exists(cached_path):
                        return False
                except (json.JSONDecodeError, TypeError):
                    return False
            return True
        except Exception:
            return False

    def delete_stale_metadata(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT path FROM metadata')
            deleted = 0
            for (path,) in cursor.fetchall():
                if not os.path.exists(path):
                    cursor.execute('DELETE FROM metadata WHERE path = ?', (path,))
                    deleted += 1
            conn.commit()
            if deleted > 0:
                logger.info(f"Cleaned {deleted} stale metadata records")
        except Exception as e:
            logger.error(f"Error cleaning stale metadata: {e}")
            conn.rollback()

    def invalidate_folder(self, folder: str):
        folder = os.path.normpath(folder)
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM metadata WHERE folder = ?', (folder,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error invalidating folder cache: {e}")
            conn.rollback()

    def _cleanup(self) -> None:
        if hasattr(self._local, "connection") and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None
