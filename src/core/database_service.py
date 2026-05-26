import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from src.utils.constants import DB_PATH
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class DatabaseService:
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
        self._db_path = DB_PATH
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._local = threading.local()
        self._init_database()
        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self._db_path)
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection

    def _init_database(self) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS song (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                artist TEXT,
                album TEXT,
                duration INTEGER,
                path TEXT UNIQUE NOT NULL,
                format TEXT,
                bitrate INTEGER,
                cover_path TEXT,
                add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS playlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_default BOOLEAN DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS playlist_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                song_id INTEGER NOT NULL,
                sort INTEGER NOT NULL,
                add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES playlist(id) ON DELETE CASCADE,
                FOREIGN KEY (song_id) REFERENCES song(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, song_id)
            );

            CREATE TABLE IF NOT EXISTS lyric (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_key TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT,
                album TEXT,
                duration INTEGER,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                translate TEXT,
                is_synced BOOLEAN DEFAULT 0,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_ai_generated BOOLEAN DEFAULT 0,
                UNIQUE(song_key, source)
            );

            CREATE TABLE IF NOT EXISTS lyric_offset (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_key TEXT NOT NULL UNIQUE,
                offset_ms INTEGER NOT NULL DEFAULT 0,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS repeat_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_key TEXT NOT NULL UNIQUE,
                repeat_type INTEGER NOT NULL DEFAULT 0,
                start_sec REAL NOT NULL DEFAULT 0,
                end_sec REAL NOT NULL DEFAULT 0,
                step_sec INTEGER NOT NULL DEFAULT 3,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS download (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id INTEGER NOT NULL,
                plugin_id INTEGER NOT NULL,
                quality TEXT NOT NULL,
                path TEXT,
                progress INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (song_id) REFERENCES song(id) ON DELETE CASCADE,
                FOREIGN KEY (plugin_id) REFERENCES plugin(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS plugin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                path TEXT UNIQUE NOT NULL,
                version TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                type TEXT NOT NULL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS webdav_accounts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                server_url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                root_path TEXT DEFAULT '/',
                is_ssl BOOLEAN DEFAULT 1,
                verify_ssl BOOLEAN DEFAULT 0,
                timeout INTEGER DEFAULT 30,
                cache_ttl INTEGER DEFAULT 600,
                preset TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS study_materials (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                audio_path TEXT NOT NULL,
                subtitle_path TEXT DEFAULT '',
                subtitle_path_secondary TEXT DEFAULT '',
                chapters_json TEXT DEFAULT '[]',
                duration_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_played_at TEXT DEFAULT '',
                progress_ms INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS study_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id TEXT NOT NULL,
                chapter_index INTEGER DEFAULT -1,
                sentence_index INTEGER DEFAULT -1,
                played_at TEXT NOT NULL,
                duration_sec INTEGER DEFAULT 0,
                repeat_count INTEGER DEFAULT 0,
                FOREIGN KEY (material_id) REFERENCES study_materials(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorite (
                path TEXT PRIMARY KEY,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration INTEGER DEFAULT 0,
                format TEXT,
                add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_playlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_playlist_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration INTEGER DEFAULT 0,
                format TEXT,
                sort_order INTEGER DEFAULT 0,
                add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES user_playlist(id) ON DELETE CASCADE,
                UNIQUE(playlist_id, path)
            );

            CREATE TABLE IF NOT EXISTS play_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration INTEGER DEFAULT 0,
                format TEXT,
                play_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS genre_cache (
                path TEXT PRIMARY KEY,
                genre TEXT,
                source TEXT DEFAULT 'tag',
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self._migrate_lyric_table(conn)
        self._migrate_study_tables(conn)
        conn.commit()
        logger.info("Database initialized successfully")

    def _migrate_study_tables(self, conn) -> None:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(study_materials)")
        columns = {row[1] for row in cursor.fetchall()}
        if "total_sentences" not in columns:
            cursor.execute("ALTER TABLE study_materials ADD COLUMN total_sentences INTEGER DEFAULT 0")
        if "learned_sentences" not in columns:
            cursor.execute("ALTER TABLE study_materials ADD COLUMN learned_sentences INTEGER DEFAULT 0")

        cursor.execute("PRAGMA table_info(study_records)")
        columns = {row[1] for row in cursor.fetchall()}
        if "sentence_count" not in columns:
            cursor.execute("ALTER TABLE study_records ADD COLUMN sentence_count INTEGER DEFAULT 0")
        if "total_sentences" not in columns:
            cursor.execute("ALTER TABLE study_records ADD COLUMN total_sentences INTEGER DEFAULT 0")
        if "study_duration_sec" not in columns:
            cursor.execute("ALTER TABLE study_records ADD COLUMN study_duration_sec INTEGER DEFAULT 0")

    def _migrate_lyric_table(self, conn) -> None:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(lyric)")
        columns = {row[1] for row in cursor.fetchall()}
        if "song_key" not in columns:
            cursor.execute("DROP TABLE IF EXISTS lyric")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lyric (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    song_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT,
                    album TEXT,
                    duration INTEGER,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    translate TEXT,
                    is_synced BOOLEAN DEFAULT 0,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_ai_generated BOOLEAN DEFAULT 0,
                    UNIQUE(song_key, source)
                );
            """)
        elif "offset_ms" in columns:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lyric_offset (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    song_key TEXT NOT NULL UNIQUE,
                    offset_ms INTEGER NOT NULL DEFAULT 0,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("SELECT song_key, offset_ms FROM lyric WHERE offset_ms IS NOT NULL AND offset_ms != 0")
            for row in cursor.fetchall():
                try:
                    cursor.execute(
                        "INSERT OR REPLACE INTO lyric_offset (song_key, offset_ms) VALUES (?, ?)",
                        (row[0], row[1])
                    )
                except Exception:
                    pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lyric_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    song_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT,
                    album TEXT,
                    duration INTEGER,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    translate TEXT,
                    is_synced BOOLEAN DEFAULT 0,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_ai_generated BOOLEAN DEFAULT 0,
                    UNIQUE(song_key, source)
                );
            """)
            cursor.execute("INSERT OR IGNORE INTO lyric_new SELECT id, song_key, title, artist, album, duration, source, content, translate, is_synced, create_time, update_time, is_ai_generated FROM lyric")
            cursor.execute("DROP TABLE lyric")
            cursor.execute("ALTER TABLE lyric_new RENAME TO lyric")

    def execute(
        self,
        sql: str,
        parameters: Tuple = ()
    ) -> sqlite3.Cursor:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute(sql, parameters)
                conn.commit()
                return cursor
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise

    def fetchone(
        self,
        sql: str,
        parameters: Tuple = ()
    ) -> Optional[Dict[str, Any]]:
        cursor = self.execute(sql, parameters)
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetchall(
        self,
        sql: str,
        parameters: Tuple = ()
    ) -> List[Dict[str, Any]]:
        cursor = self.execute(sql, parameters)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def insert(
        self,
        table: str,
        data: Dict[str, Any]
    ) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        cursor = self.execute(sql, tuple(data.values()))
        return cursor.lastrowid

    def update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        where_params: Tuple = ()
    ) -> int:
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        cursor = self.execute(sql, tuple(data.values()) + where_params)
        return cursor.rowcount

    def delete(
        self,
        table: str,
        where: str,
        where_params: Tuple = ()
    ) -> int:
        sql = f"DELETE FROM {table} WHERE {where}"
        cursor = self.execute(sql, where_params)
        return cursor.rowcount

    def _cleanup(self) -> None:
        if hasattr(self._local, "connection") and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception:
                pass
            self._local.connection = None

