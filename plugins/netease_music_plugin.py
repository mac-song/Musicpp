import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict

from yt_dlp import YoutubeDL

from src.plugins.plugin_interface import MusicPluginInterface
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class NetEaseMusicPlugin(MusicPluginInterface):
    meta = {
        "id": "netease_music",
        "name": "网易云音乐",
        "version": "1.0",
        "author": "Music++",
        "description": "搜索网易云音乐并提取音频流",
        "source_name": "网易云",
    }

    SEARCH_URL = "https://music.163.com/api/search/get/web"
    SONG_URL_TEMPLATE = "https://music.163.com/#/song?id={}"

    def __init__(self):
        self._url_cache = {}

    def search(self, keyword: str, page: int = 1, limit: int = 30) -> Dict[str, Any]:
        try:
            offset = (page - 1) * limit
            params = urllib.parse.urlencode({
                "s": keyword,
                "type": 1,
                "offset": offset,
                "limit": limit,
            })
            full_url = f"{self.SEARCH_URL}?{params}"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://music.163.com",
            }

            req = urllib.request.Request(full_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") != 200:
                return {"total": 0, "list": []}

            result = data.get("result", {})
            songs = result.get("songs", [])
            total = result.get("songCount", len(songs))

            results = []
            for song in songs:
                song_id = song.get("id", "")
                name = song.get("name", "")
                artists = ", ".join(a.get("name", "") for a in song.get("artists", []))
                album = song.get("album", {}).get("name", "")
                duration = song.get("duration", 0) // 1000
                cover_id = song.get("album", {}).get("id", "")
                cover = f"https://music.163.com/api/img/blur/{cover_id}" if cover_id else ""

                results.append({
                    "id": str(song_id),
                    "pluginId": "netease_music",
                    "source": "netease_music",
                    "title": name,
                    "artist": artists,
                    "album": album,
                    "duration": duration,
                    "cover": cover,
                    "qualities": [
                        {"type": "mp3", "size": 0},
                    ],
                    "sources": ["netease_music"],
                })

            return {"total": total, "list": results}

        except Exception as e:
            logger.error(f"NetEase Music search error: {e}")
            return {"total": 0, "list": []}

    def get_song_url(self, song_id: str, quality: str = "320k") -> Dict[str, Any]:
        if song_id in self._url_cache:
            return self._url_cache[song_id]

        try:
            song_url = self.SONG_URL_TEMPLATE.format(song_id)

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio/best",
                "noplaylist": True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(song_url, download=False)
                if info:
                    audio_url = info.get("url", "")
                    if audio_url and audio_url.startswith("http"):
                        result = {
                            "url": audio_url,
                            "headers": {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                                "Referer": "https://music.163.com",
                            },
                        }
                        self._url_cache[song_id] = result
                        return result

            return {"url": "", "error": "无法获取音频流"}
        except Exception as e:
            logger.error(f"NetEase Music get_song_url error: {e}")
            return {"url": "", "error": str(e)}

    def get_lyric(self, song_id: str) -> Dict[str, Any]:
        try:
            url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&tv=-1"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://music.163.com",
            }

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            lrc = data.get("lrc", {}).get("lyric", "")
            tlyric = data.get("tlyric", {}).get("lyric", "")
            return {"lrc": lrc, "tlyric": tlyric}

        except Exception as e:
            logger.error(f"NetEase Music get_lyric error: {e}")
            return {"lrc": "", "tlyric": ""}
