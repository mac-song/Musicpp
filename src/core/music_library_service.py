import sqlite3
import threading
from typing import Any, Dict, List, Optional

from src.core.database_service import DatabaseService
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MusicLibraryService:
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
        self._db = DatabaseService()
        self._ensure_default_playlist()
        self._initialized = True

    def _ensure_default_playlist(self):
        try:
            row = self._db.fetchone("SELECT id FROM user_playlist WHERE id = 1")
            if not row:
                self._db.execute(
                    "INSERT INTO user_playlist (id, name) VALUES (1, ?)",
                    ("我喜欢的音乐",)
                )
        except Exception as e:
            logger.error(f"Ensure default playlist error: {e}")

    # ================================================================
    # Favorites
    # ================================================================

    def add_favorite(self, path: str, meta: Dict[str, Any] = None) -> bool:
        if not meta:
            meta = {}
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO favorite (path, title, artist, album, duration, format) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (path, meta.get("title", ""), meta.get("artist", ""),
                 meta.get("album", ""), meta.get("duration", 0), meta.get("format", ""))
            )
            logger.info(f"Added to favorites: {path}")
            return True
        except Exception as e:
            logger.error(f"Add favorite error: {e}")
            return False

    def remove_favorite(self, path: str) -> bool:
        try:
            self._db.delete("favorite", "path = ?", (path,))
            logger.info(f"Removed from favorites: {path}")
            return True
        except Exception as e:
            logger.error(f"Remove favorite error: {e}")
            return False

    def is_favorite(self, path: str) -> bool:
        row = self._db.fetchone("SELECT path FROM favorite WHERE path = ?", (path,))
        return row is not None

    def get_favorites(self) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT path, title, artist, album, duration, format, add_time "
            "FROM favorite ORDER BY add_time DESC"
        )
        return rows

    # ================================================================
    # Playlists
    # ================================================================

    def create_playlist(self, name: str) -> Optional[int]:
        try:
            cursor = self._db.execute(
                "INSERT INTO user_playlist (name) VALUES (?)", (name,)
            )
            playlist_id = cursor.lastrowid
            logger.info(f"Created playlist: {name} (id={playlist_id})")
            return playlist_id
        except Exception as e:
            logger.error(f"Create playlist error: {e}")
            return None

    def delete_playlist(self, playlist_id: int) -> bool:
        try:
            self._db.delete("user_playlist", "id = ?", (playlist_id,))
            logger.info(f"Deleted playlist id={playlist_id}")
            return True
        except Exception as e:
            logger.error(f"Delete playlist error: {e}")
            return False

    def rename_playlist(self, playlist_id: int, name: str) -> bool:
        try:
            self._db.update("user_playlist", {"name": name}, "id = ?", (playlist_id,))
            return True
        except Exception as e:
            logger.error(f"Rename playlist error: {e}")
            return False

    def get_playlists(self) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT p.id, p.name, p.create_time, "
            "(SELECT COUNT(*) FROM user_playlist_item WHERE playlist_id = p.id) AS track_count "
            "FROM user_playlist p ORDER BY p.id"
        )
        return rows

    def add_to_playlist(self, playlist_id: int, path: str, meta: Dict[str, Any] = None) -> bool:
        if not meta:
            meta = {}
        try:
            max_row = self._db.fetchone(
                "SELECT MAX(sort_order) AS max_sort FROM user_playlist_item WHERE playlist_id = ?",
                (playlist_id,)
            )
            sort_order = (max_row["max_sort"] or 0) + 1 if max_row else 1
            self._db.execute(
                "INSERT OR IGNORE INTO user_playlist_item "
                "(playlist_id, path, title, artist, album, duration, format, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (playlist_id, path, meta.get("title", ""), meta.get("artist", ""),
                 meta.get("album", ""), meta.get("duration", 0), meta.get("format", ""), sort_order)
            )
            logger.info(f"Added to playlist {playlist_id}: {path}")
            return True
        except Exception as e:
            logger.error(f"Add to playlist error: {e}")
            return False

    def remove_from_playlist(self, playlist_id: int, item_id: int) -> bool:
        try:
            self._db.delete(
                "user_playlist_item",
                "id = ? AND playlist_id = ?",
                (item_id, playlist_id)
            )
            return True
        except Exception as e:
            logger.error(f"Remove from playlist error: {e}")
            return False

    def get_playlist_items(self, playlist_id: int) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT id, path, title, artist, album, duration, format, sort_order, add_time "
            "FROM user_playlist_item WHERE playlist_id = ? ORDER BY sort_order",
            (playlist_id,)
        )
        return rows

    # ================================================================
    # Play History
    # ================================================================

    def add_play_history(self, path: str, meta: Dict[str, Any] = None) -> bool:
        if not meta:
            meta = {}
        try:
            self._db.execute(
                "INSERT INTO play_history (path, title, artist, album, duration, format, play_time) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (path, meta.get("title", ""), meta.get("artist", ""),
                 meta.get("album", ""), meta.get("duration", 0), meta.get("format", ""))
            )
            self._trim_history()
            return True
        except Exception as e:
            logger.error(f"Add play history error: {e}")
            return False

    def get_play_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT id, path, title, artist, album, duration, format, play_time "
            "FROM play_history ORDER BY play_time DESC LIMIT ?",
            (limit,)
        )
        return rows

    def clear_play_history(self) -> bool:
        try:
            self._db.execute("DELETE FROM play_history")
            return True
        except Exception as e:
            logger.error(f"Clear play history error: {e}")
            return False

    def _trim_history(self, max_records: int = 1000):
        try:
            self._db.execute(
                "DELETE FROM play_history WHERE id NOT IN "
                "(SELECT id FROM play_history ORDER BY play_time DESC LIMIT ?)",
                (max_records,)
            )
        except Exception as e:
            logger.error(f"Trim history error: {e}")

    # ================================================================
    # Genre Cache
    # ================================================================

    def get_genre(self, path: str) -> Optional[str]:
        row = self._db.fetchone("SELECT genre FROM genre_cache WHERE path = ?", (path,))
        return row["genre"] if row else None

    def set_genre(self, path: str, genre: str, source: str = "tag") -> bool:
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO genre_cache (path, genre, source, update_time) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (path, genre, source)
            )
            return True
        except Exception as e:
            logger.error(f"Set genre error: {e}")
            return False

    def get_genres(self) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT genre, COUNT(*) AS count FROM genre_cache "
            "WHERE genre IS NOT NULL AND genre != '' "
            "GROUP BY genre ORDER BY count DESC"
        )
        return rows

    def get_songs_by_genre(self, genre: str) -> List[Dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT g.path, g.genre, g.source "
            "FROM genre_cache g WHERE g.genre = ?",
            (genre,)
        )
        return rows
