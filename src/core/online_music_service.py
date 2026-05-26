import json
import os
import time
import threading
from typing import Dict, List, Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config")


class OnlineMusicService:
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
        self._data_path = os.path.join(DATA_DIR, "online_music.json")
        self._save_lock = threading.Lock()
        self._playlist = []
        self._favorites = []
        self._history = []
        self._user_playlists = {}
        self._load()
        self._initialized = True

    def _load(self):
        if not os.path.exists(self._data_path):
            return
        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._playlist = data.get("playlist", [])
            self._favorites = data.get("favorites", [])
            self._history = data.get("history", [])
            self._user_playlists = data.get("user_playlists", {})
        except Exception as e:
            logger.error(f"Load online music data failed: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._data_path), exist_ok=True)
            data = {
                "playlist": self._playlist,
                "favorites": self._favorites,
                "history": self._history,
                "user_playlists": self._user_playlists,
            }
            with open(self._data_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Save online music data failed: {e}")

    def _song_key(self, song: dict) -> str:
        return song.get("id") or song.get("hash") or song.get("songmid") or ""

    @staticmethod
    def _normalize_song(song: dict) -> dict:
        title = song.get("title") or song.get("name", "")
        artist = song.get("artist") or song.get("singer", "")
        album = song.get("album") or song.get("albumName", "")
        song_id = song.get("id") or song.get("hash") or song.get("songmid") or ""
        return {
            "id": song_id,
            "title": title,
            "artist": artist,
            "album": album,
            "duration": song.get("duration", 0),
            "pluginId": song.get("pluginId", ""),
            "source": song.get("source", ""),
            "cover": song.get("cover") or song.get("img", ""),
            "hash": song.get("hash", ""),
            "hash_320": song.get("hash_320") or song.get("320hash", ""),
            "hash_sq": song.get("hash_sq") or song.get("sqhash", ""),
        }

    @staticmethod
    def _normalize_import_song(song: dict) -> dict:
        normalized = OnlineMusicService._normalize_song(song)
        if song.get("match_status"):
            normalized["match_status"] = song["match_status"]
        if song.get("_play_url") or song.get("play_url"):
            normalized["_play_url"] = song.get("_play_url") or song.get("play_url", "")
        if song.get("quality"):
            normalized["quality"] = song["quality"]
        if song.get("qualities"):
            normalized["qualities"] = song["qualities"]
        return normalized

    # ---- Playlist ----
    def get_playlist(self) -> List[dict]:
        return list(self._playlist)

    def add_to_playlist(self, song: dict) -> bool:
        normalized = self._normalize_song(song)
        key = self._song_key(normalized)
        for item in self._playlist:
            if self._song_key(item) == key and key:
                return False
        self._playlist.append(normalized)
        with self._save_lock:
            self._save()
        return True

    def add_songs_to_playlist(self, songs: List[dict]) -> int:
        count = 0
        for song in songs:
            if self.add_to_playlist(song):
                count += 1
        return count

    def remove_from_playlist(self, indices: List[int]) -> int:
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self._playlist):
                self._playlist.pop(i)
        with self._save_lock:
            self._save()
        return len(indices)

    def clear_playlist(self):
        self._playlist.clear()
        with self._save_lock:
            self._save()

    # ---- Favorites ----
    def get_favorites(self) -> List[dict]:
        return list(self._favorites)

    def add_to_favorites(self, song: dict) -> bool:
        normalized = self._normalize_song(song)
        key = self._song_key(normalized)
        for item in self._favorites:
            if self._song_key(item) == key and key:
                return False
        self._favorites.append(normalized)
        with self._save_lock:
            self._save()
        return True

    def remove_from_favorites(self, indices: List[int]) -> int:
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self._favorites):
                self._favorites.pop(i)
        with self._save_lock:
            self._save()
        return len(indices)

    def is_in_favorites(self, song: dict) -> bool:
        key = self._song_key(song)
        if not key:
            return False
        return any(self._song_key(item) == key for item in self._favorites)

    # ---- History ----
    def get_history(self) -> List[dict]:
        return list(self._history)

    def add_to_history(self, song: dict):
        normalized = self._normalize_song(song)
        normalized["play_time"] = time.strftime("%Y-%m-%d %H:%M")
        key = self._song_key(normalized)
        self._history = [h for h in self._history if self._song_key(h) != key or not key]
        self._history.insert(0, normalized)
        if len(self._history) > 200:
            self._history = self._history[:200]
        with self._save_lock:
            self._save()

    def clear_history(self):
        self._history.clear()
        with self._save_lock:
            self._save()

    def export_history(self) -> str:
        if not self._history:
            return ""
        lines = []
        for song in self._history:
            title = song.get("title", "")
            artist = song.get("artist", "")
            play_time = song.get("play_time", "")
            lines.append(f"{play_time}  {artist} - {title}")
        return "\n".join(lines)

    # ---- User Playlists ----
    def get_user_playlists(self) -> Dict[str, List[dict]]:
        return dict(self._user_playlists)

    def create_playlist(self, name: str) -> bool:
        if name in self._user_playlists:
            return False
        self._user_playlists[name] = []
        with self._save_lock:
            self._save()
        return True

    def delete_playlist(self, name: str) -> bool:
        if name not in self._user_playlists:
            return False
        del self._user_playlists[name]
        with self._save_lock:
            self._save()
        return True

    def rename_playlist(self, old_name: str, new_name: str) -> bool:
        if old_name not in self._user_playlists or new_name in self._user_playlists:
            return False
        self._user_playlists[new_name] = self._user_playlists.pop(old_name)
        with self._save_lock:
            self._save()
        return True

    def get_playlist_songs(self, name: str) -> List[dict]:
        return list(self._user_playlists.get(name, []))

    def add_to_user_playlist(self, name: str, song: dict) -> bool:
        if name not in self._user_playlists:
            return False
        normalized = self._normalize_song(song)
        normalized["add_time"] = time.strftime("%Y-%m-%d %H:%M")
        key = self._song_key(normalized)
        for item in self._user_playlists[name]:
            if self._song_key(item) == key and key:
                return False
        self._user_playlists[name].append(normalized)
        with self._save_lock:
            self._save()
        return True

    def remove_from_user_playlist(self, name: str, indices: List[int]) -> int:
        if name not in self._user_playlists:
            return 0
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self._user_playlists[name]):
                self._user_playlists[name].pop(i)
        with self._save_lock:
            self._save()
        return len(indices)

    def get_playlist_names(self) -> List[str]:
        return list(self._user_playlists.keys())

    def import_songs_to_playlist(self, name: str, songs: List[dict]) -> int:
        if name not in self._user_playlists:
            self._user_playlists[name] = []
        count = 0
        for song in songs:
            normalized = self._normalize_import_song(song)
            normalized["add_time"] = time.strftime("%Y-%m-%d %H:%M")
            key = self._song_key(normalized)
            dup = any(self._song_key(item) == key and key for item in self._user_playlists[name])
            if not dup:
                self._user_playlists[name].append(normalized)
                count += 1
        if count > 0:
            with self._save_lock:
                self._save()
        return count

    def update_user_playlist_song(self, name: str, index: int, song: dict) -> bool:
        if name not in self._user_playlists:
            return False
        if index < 0 or index >= len(self._user_playlists[name]):
            return False
        normalized = self._normalize_import_song(song)
        if song.get("add_time"):
            normalized["add_time"] = song["add_time"]
        else:
            normalized["add_time"] = time.strftime("%Y-%m-%d %H:%M")
        self._user_playlists[name][index] = normalized
        with self._save_lock:
            self._save()
        return True

    def get_playlist_for_export(self, name: str) -> List[dict]:
        songs = self._user_playlists.get(name, [])
        return [dict(s) for s in songs]
