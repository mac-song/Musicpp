import collections
import random
import threading
from typing import Callable, List, Optional

from src.core.audio_service import AudioService
from src.core.event_bus import EventBus
from src.utils.constants import (
    EVENT_PLAYBACK_STATE_CHANGED,
    EVENT_TRACK_CHANGED,
    PLAY_MODE_LOOP_ALL,
    PLAY_MODE_LOOP_SINGLE,
    PLAY_MODE_RANDOM,
    PLAY_MODE_SEQUENCE,
    PLAYBACK_STOPPED,
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

CONTEXT_LOCAL = "local"
CONTEXT_ONLINE = "online"


class PlaybackManager:
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
        self._audio_service = AudioService()
        self._event_bus = EventBus()

        self._local_playlist = []
        self._local_index = -1
        self._local_history = collections.deque(maxlen=100)

        self._online_playlist = []
        self._online_index = -1
        self._online_history = collections.deque(maxlen=100)

        self._context = CONTEXT_LOCAL
        self._play_mode = PLAY_MODE_SEQUENCE
        self._position_callbacks = []
        self._track_end_callback = None
        self._online_url_callback = None
        self._initialized = True

        self._audio_service.register_position_callback(self._on_position_changed)

    @property
    def _playlist(self):
        return self._local_playlist if self._context == CONTEXT_LOCAL else self._online_playlist

    @property
    def _current_index(self):
        return self._local_index if self._context == CONTEXT_LOCAL else self._online_index

    @_current_index.setter
    def _current_index(self, val):
        if self._context == CONTEXT_LOCAL:
            self._local_index = val
        else:
            self._online_index = val

    @property
    def _history(self):
        return self._local_history if self._context == CONTEXT_LOCAL else self._online_history

    def _switch_context(self, ctx: str):
        if ctx == self._context:
            return
        self._context = ctx

    def get_context(self) -> str:
        return self._context

    def set_playlist(self, songs: List[dict]) -> None:
        self._local_playlist = songs.copy()
        if self._local_index >= len(self._local_playlist):
            self._local_index = -1

    def add_to_playlist(self, song: dict) -> None:
        self._local_playlist.append(song)

    def remove_from_playlist(self, index: int) -> bool:
        if 0 <= index < len(self._local_playlist):
            self._local_playlist.pop(index)
            if index < self._local_index:
                self._local_index -= 1
            elif index == self._local_index:
                self.stop()
                self._local_index = -1
            return True
        return False

    def clear_playlist(self) -> None:
        self.stop()
        self._local_playlist.clear()
        self._local_index = -1

    def play_at(self, index: int) -> bool:
        playlist = self._playlist
        if not playlist or index < 0 or index >= len(playlist):
            return False

        self._current_index = index
        song = playlist[index]
        file_path = song.get("path", "")

        if file_path:
            is_url = file_path.startswith(("http://", "https://", "ftp://"))
            if is_url:
                song_info = self._build_song_info(song)
                auth_header = song.get("_auth_header", "")
                headers = {"Authorization": auth_header} if auth_header else None
                if self._audio_service.load_url(file_path, headers, song_info):
                    self._history.append(index)
                    return self._audio_service.play()
                return False
            if self._audio_service.load_audio(file_path):
                self._history.append(index)
                return self._audio_service.play()
            return False
        else:
            url = song.get("_play_url", "")
            if not url and self._online_url_callback:
                try:
                    url = self._online_url_callback(song)
                    if url:
                        song["_play_url"] = url
                except Exception as e:
                    logger.error(f"Online URL callback error: {e}")
                    return False
            if url:
                song_info = self._build_song_info(song)
                if song.get("_is_local") or url.startswith(("C:", "D:", "E:", "/", "\\")):
                    if self._audio_service.load_audio(url, song_info):
                        self._history.append(index)
                        return self._audio_service.play()
                else:
                    headers = song.get("headers", {})
                    if self._audio_service.load_url(url, headers if headers else None, song_info):
                        self._history.append(index)
                        return self._audio_service.play()
            return False

    def play_local_at(self, index: int) -> bool:
        self._switch_context(CONTEXT_LOCAL)
        return self.play_at(index)

    def play_online(self, song_data: dict, url: str) -> bool:
        self._switch_context(CONTEXT_ONLINE)
        song_data["_play_url"] = url
        self._online_playlist.clear()
        self._online_playlist.append(song_data)
        self._online_history.clear()
        self._online_index = 0

        song_info = self._build_song_info(song_data)
        if song_data.get("_is_local") or url.startswith(("C:", "D:", "E:", "/", "\\")):
            if self._audio_service.load_audio(url, song_info):
                return self._audio_service.play()
        else:
            headers = song_data.get("headers", {})
            if self._audio_service.load_url(url, headers if headers else None, song_info):
                return self._audio_service.play()
        return False

    @staticmethod
    def _build_song_info(song: dict) -> dict:
        return {
            "id": song.get("id", ""),
            "pluginId": song.get("pluginId", ""),
            "title": song.get("title", song.get("name", "")),
            "artist": song.get("artist", song.get("singer", "")),
            "album": song.get("album", song.get("albumName", "")),
            "source": song.get("source", song.get("pluginId", "")),
            "cover": song.get("cover", ""),
        }

    def set_online_playlist_and_play(self, songs: list, index: int = 0) -> bool:
        self._switch_context(CONTEXT_ONLINE)
        self._online_playlist = songs.copy()
        self._online_history.clear()
        return self.play_at(index)

    def play(self) -> bool:
        if self._audio_service.is_paused():
            return self._audio_service.play()

        if self._current_index >= 0 and self._current_index < len(self._playlist):
            return self._audio_service.play()

        if self._playlist:
            return self.play_at(0)

        return False

    def pause(self) -> bool:
        return self._audio_service.pause()

    def stop(self) -> bool:
        return self._audio_service.stop()

    def next_track(self) -> bool:
        playlist = self._playlist
        if not playlist:
            return False

        if self._play_mode == PLAY_MODE_LOOP_SINGLE:
            return self.play_at(self._current_index)

        if self._play_mode == PLAY_MODE_RANDOM:
            if len(playlist) > 1:
                next_index = random.randint(0, len(playlist) - 1)
                while next_index == self._current_index:
                    next_index = random.randint(0, len(playlist) - 1)
                return self.play_at(next_index)
            else:
                return self.play_at(0)

        next_index = self._current_index + 1
        if next_index >= len(playlist):
            if self._play_mode == PLAY_MODE_LOOP_ALL:
                next_index = 0
            else:
                self.stop()
                return False

        return self.play_at(next_index)

    def previous_track(self) -> bool:
        playlist = self._playlist
        if not playlist:
            return False

        if self._play_mode == PLAY_MODE_LOOP_SINGLE:
            return self.play_at(self._current_index)

        history = self._history
        if len(history) > 1:
            history.pop()
            prev_index = history[-1]
            return self.play_at(prev_index)

        prev_index = self._current_index - 1
        if prev_index < 0:
            if self._play_mode == PLAY_MODE_LOOP_ALL:
                prev_index = len(playlist) - 1
            else:
                prev_index = 0

        return self.play_at(prev_index)

    def seek(self, position: float) -> bool:
        return self._audio_service.seek(position)

    def set_volume(self, volume: int) -> bool:
        return self._audio_service.set_volume(volume)

    def get_volume(self) -> int:
        return self._audio_service.get_volume()

    def set_play_mode(self, mode: int) -> None:
        self._play_mode = mode

    def get_play_mode(self) -> int:
        return self._play_mode

    def get_current_track(self) -> Optional[dict]:
        playlist = self._playlist
        idx = self._current_index
        if 0 <= idx < len(playlist):
            return playlist[idx]
        return None

    def get_current_index(self) -> int:
        return self._current_index

    def get_playlist(self) -> List[dict]:
        return self._playlist.copy()

    def get_online_playlist(self) -> List[dict]:
        return self._online_playlist.copy()

    def get_position(self) -> float:
        return self._audio_service.get_position()

    def get_duration(self) -> float:
        return self._audio_service.get_duration()

    def is_playing(self) -> bool:
        return self._audio_service.is_playing()

    def is_paused(self) -> bool:
        return self._audio_service.is_paused()

    def register_position_callback(self, callback: Callable) -> None:
        if callback not in self._position_callbacks:
            self._position_callbacks.append(callback)

    def _on_position_changed(self, position: float) -> None:
        for callback in self._position_callbacks:
            try:
                callback(position)
            except Exception as e:
                logger.error(f"Position callback error: {e}")

        duration = self.get_duration()
        if duration > 0 and position >= duration - 0.5:
            self._on_track_end()

    def _on_track_end(self) -> None:
        if self._track_end_callback:
            try:
                self._track_end_callback()
            except Exception as e:
                logger.error(f"Track end callback error: {e}")
        else:
            self.next_track()

    def set_track_end_callback(self, callback: Callable) -> None:
        self._track_end_callback = callback

    def set_online_url_callback(self, callback: Callable) -> None:
        self._online_url_callback = callback

