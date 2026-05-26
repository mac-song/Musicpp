from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MusicPluginInterface(ABC):
    meta: Dict[str, Any] = {
        "id": "",
        "name": "",
        "version": "",
        "author": "",
        "description": "",
        "homepage": "",
        "config_schema": {}
    }

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @property
    def name(self) -> str:
        return self.meta.get("name", "")

    @property
    def version(self) -> str:
        return self.meta.get("version", "")

    @property
    def author(self) -> str:
        return self.meta.get("author", "")

    @property
    def plugin_id(self) -> str:
        return self.meta.get("id", "")

    @property
    def can_search(self) -> bool:
        return True

    @property
    def can_play(self) -> bool:
        return True

    @property
    def can_download(self) -> bool:
        return True

    @property
    def can_get_url(self) -> bool:
        return True

    @abstractmethod
    def search(self, keyword: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """
        Return: {"total": int, "list": [{"id": str, "pluginId": str, "title": str, "artist": str, "album": str, "duration": int, "cover": str, "qualities": [{"level": str, "bitrate": int, "size": int}], "sources": [str]}]}
        """
        pass

    @abstractmethod
    def get_song_url(self, song_id: str, quality: str = "320k") -> Dict[str, Any]:
        """
        Return: {"url": str, "headers": dict, "expires": int}
        """
        pass

    def get_download_url(self, song_id: str, quality: str = "320k") -> Dict[str, Any]:
        return self.get_song_url(song_id, quality)

    @abstractmethod
    def get_lyric(self, song_id: str) -> Dict[str, Optional[str]]:
        """
        Return: {"lrc": str, "tlyric": str}
        """
        pass

    def get_playlist(self, playlist_id: str) -> Dict[str, Any]:
        raise NotImplementedError("该插件不支持歌单功能")

    def get_qualities(self, song_id: str) -> List[str]:
        return ["128k", "320k"]

    def to_standard_format(self, raw_data: Dict) -> Dict[str, Any]:
        return {
            "id": str(raw_data.get("id", "")),
            "pluginId": self.plugin_id,
            "title": raw_data.get("title", ""),
            "artist": raw_data.get("artist", ""),
            "album": raw_data.get("album", ""),
            "duration": raw_data.get("duration", 0),
            "cover": raw_data.get("cover", ""),
            "qualities": raw_data.get("qualities", []),
            "sources": [self.plugin_id],
        }
