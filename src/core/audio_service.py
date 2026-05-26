import threading
from typing import Callable, Optional

from src.infrastructure.bass_engine import BASSEngine
from src.utils.constants import (
    EVENT_PLAYBACK_STATE_CHANGED,
    EVENT_TRACK_CHANGED,
    EVENT_PLAY_FAILED,
    PLAYBACK_PAUSED,
    PLAYBACK_PLAYING,
    PLAYBACK_STOPPED,
)
from src.utils.logger import setup_logger
from .event_bus import EventBus

logger = setup_logger(__name__)


class AudioService:
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
        self._engine = BASSEngine()
        self._event_bus = EventBus()
        self._current_file = ""
        self._position_timer = None
        self._position_callbacks = []
        self._callbacks_lock = threading.Lock()
        self._initialized = True

    def initialize(self) -> bool:
        result = self._engine.initialize()
        if result:
            self._start_position_timer()
        return result

    def load_audio(self, file_path: str, song_info: dict = None) -> bool:
        result = self._engine.load(file_path)
        if result:
            self._current_file = file_path
            event_data = {
                "file_path": file_path,
                "duration": self.get_duration()
            }
            if song_info:
                event_data["song_info"] = song_info
            self._event_bus.publish(EVENT_TRACK_CHANGED, event_data)
        else:
            self._event_bus.publish(EVENT_PLAY_FAILED, {
                "file_path": file_path,
                "song_info": song_info,
            })
        return result

    def load_url(self, url: str, headers: dict = None, song_info: dict = None) -> bool:
        result = self._engine.load_url(url, headers)
        if result:
            self._current_file = url
            event_data = {
                "file_path": url,
                "duration": self.get_duration()
            }
            if song_info:
                event_data["song_info"] = song_info
            self._event_bus.publish(EVENT_TRACK_CHANGED, event_data)
        return result

    def play(self) -> bool:
        result = self._engine.play()
        if result:
            self._event_bus.publish(EVENT_PLAYBACK_STATE_CHANGED, {
                "state": PLAYBACK_PLAYING,
                "file_path": self._current_file
            })
        return result

    def pause(self) -> bool:
        result = self._engine.pause()
        if result:
            self._event_bus.publish(EVENT_PLAYBACK_STATE_CHANGED, {
                "state": PLAYBACK_PAUSED,
                "file_path": self._current_file
            })
        return result

    def stop(self) -> bool:
        result = self._engine.stop()
        if result:
            self._event_bus.publish(EVENT_PLAYBACK_STATE_CHANGED, {
                "state": PLAYBACK_STOPPED,
                "file_path": ""
            })
            self._current_file = ""
        return result

    def unload(self) -> None:
        self._engine.stop()
        self._engine.unload()
        self._current_file = ""

    def seek(self, position: float) -> bool:
        return self._engine.seek(position)

    def set_volume(self, volume: int) -> bool:
        volume_float = max(0, min(100, volume)) / 100.0
        return self._engine.set_volume(volume_float)

    def set_speed(self, rate: float) -> bool:
        return self._engine.set_speed(rate)

    def get_volume(self) -> int:
        return int(self._engine.get_volume() * 100)

    def get_position(self) -> float:
        return self._engine.get_position()

    def get_duration(self) -> float:
        return self._engine.get_duration()

    def get_playback_state(self) -> int:
        if self._engine.is_playing():
            return PLAYBACK_PLAYING
        elif self._engine.is_paused():
            return PLAYBACK_PAUSED
        return PLAYBACK_STOPPED

    def is_playing(self) -> bool:
        return self._engine.is_playing()

    def is_paused(self) -> bool:
        return self._engine.is_paused()

    def register_position_callback(self, callback: Callable) -> None:
        with self._callbacks_lock:
            if callback not in self._position_callbacks:
                self._position_callbacks.append(callback)

    def _start_position_timer(self) -> None:
        self._timer_pause = threading.Event()
        self._timer_active = threading.Event()
        self._timer_active.set()

        def timer_loop():
            while self._initialized:
                self._timer_pause.wait(timeout=0.1)
                if not self._initialized:
                    break
                if self.is_playing() and self._position_callbacks:
                    position = self.get_position()
                    callbacks = list(self._position_callbacks)
                    for callback in callbacks:
                        try:
                            callback(position)
                        except Exception as e:
                            logger.error(f"Position callback error: {e}")

        self._position_timer = threading.Thread(target=timer_loop, daemon=True)
        self._position_timer.start()

