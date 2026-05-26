import os
import re
import threading
from typing import Callable, Dict, List, Optional, Tuple

from src.core.database_service import DatabaseService
from src.core.event_bus import EventBus
from src.core.network_service import NetworkService
from src.utils.constants import (
    DEFAULT_LYRIC_SOURCES,
    EVENT_LYRIC_GENERATED,
    EVENT_LYRIC_LOADED,
)
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class LyricLine:
    def __init__(self, time_ms: int, text: str, translate: str = ""):
        self.time_ms = time_ms
        self.text = text
        self.translate = translate


class LyricManager:
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
        self._event_bus = EventBus()
        self._network = NetworkService()
        self._current_lyric = []
        self._current_song = None
        self._lyric_offset_ms = 0
        self._plugin_lyric_sources = {}
        self._initialized = True

    def parse_lrc(self, lrc_content: str) -> List[LyricLine]:
        lines = []
        pattern = re.compile(r"\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)")

        for line in lrc_content.split("\n"):
            match = pattern.match(line.strip())
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                milliseconds = int(match.group(3))
                if len(match.group(3)) == 2:
                    milliseconds *= 10
                text = match.group(4).strip()
                time_ms = minutes * 60000 + seconds * 1000 + milliseconds
                lines.append(LyricLine(time_ms, text))

        lines.sort(key=lambda x: x.time_ms)
        return lines

    def format_lrc(self, lines: List[LyricLine]) -> str:
        result = []
        for line in lines:
            minutes = line.time_ms // 60000
            seconds = (line.time_ms % 60000) // 1000
            milliseconds = line.time_ms % 1000
            result.append(f"[{minutes:02d}:{seconds:02d}.{milliseconds:03d}]{line.text}")
        return "\n".join(result)

    def get_current_line(self, position_ms: int) -> Tuple[int, Optional[LyricLine]]:
        if not self._current_lyric:
            return -1, None

        adjusted_ms = position_ms + self._lyric_offset_ms

        for i in range(len(self._current_lyric) - 1, -1, -1):
            if self._current_lyric[i].time_ms <= adjusted_ms:
                return i, self._current_lyric[i]

        return 0, self._current_lyric[0] if self._current_lyric else None

    def load_local_lyric(self, song_path: str) -> Optional[str]:
        base_path = os.path.splitext(song_path)[0]

        for ext in [".lrc", ".LRC"]:
            lyric_path = base_path + ext
            if os.path.exists(lyric_path):
                try:
                    with open(lyric_path, "r", encoding="utf-8") as f:
                        return f.read()
                except UnicodeDecodeError:
                    try:
                        with open(lyric_path, "r", encoding="gbk") as f:
                            return f.read()
                    except Exception:
                        pass

        return None

    def has_local_lyric(self, song_path: str) -> bool:
        if not song_path:
            return False
        base_path = os.path.splitext(song_path)[0]
        return os.path.exists(base_path + ".lrc") or os.path.exists(base_path + ".LRC")

    def _has_timestamp(self, content: str) -> bool:
        if not content:
            return False
        return bool(re.search(r"\[\d{2}:\d{2}", content))

    def search_lyric_online(
        self,
        title: str,
        artist: str = "",
        album: str = "",
        duration: int = 0,
        sources: Optional[List[str]] = None
    ) -> List[Dict]:
        sources = sources or DEFAULT_LYRIC_SOURCES
        results = []

        for source in sources:
            try:
                if source == "lrclib":
                    result = self._search_lrclib(title, artist, album, duration)
                elif source == "lrcapi":
                    result = self._search_lrcapi(title, artist)
                elif source == "netease":
                    result = self._search_netease(title, artist)
                elif source == "gequbao":
                    result = self._search_gequbao(title, artist)
                else:
                    continue

                if result:
                    results.append({
                        "source": source,
                        "content": result.get("content", ""),
                        "translate": result.get("translate", ""),
                        "title": result.get("title", title),
                        "artist": result.get("artist", artist),
                    })

            except Exception as e:
                logger.warning(f"Search {source} failed: {e}")

        results.sort(key=lambda x: (0 if self._has_timestamp(x.get("content", "")) else 1))
        return results

    def search_lyric_candidates(
        self,
        title: str,
        artist: str = "",
        album: str = "",
        duration: int = 0,
        sources: Optional[List[str]] = None
    ) -> List[Dict]:
        sources = sources or DEFAULT_LYRIC_SOURCES
        seen = set()
        candidates = []

        for source in sources:
            try:
                if source == "lrclib":
                    items = self._search_lrclib_candidates(title, artist)
                elif source == "netease":
                    items = self._netease_search_candidates(title, artist)
                elif source == "gequbao":
                    items = self._search_gequbao_candidates(title, artist)
                else:
                    continue

                for item in items:
                    key = (item.get("title", "").lower(), item.get("artist", "").lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append({
                        "source": source,
                        "content": item.get("content", ""),
                        "translate": item.get("translate", ""),
                        "title": item.get("title", title),
                        "artist": item.get("artist", artist),
                        "duration": item.get("duration", 0),
                    })

            except Exception as e:
                logger.warning(f"Search {source} candidates failed: {e}")

        candidates.sort(key=lambda x: (0 if self._has_timestamp(x.get("content", "")) else 1))
        return candidates

    def _search_lrclib(
        self,
        title: str,
        artist: str,
        album: str = "",
        duration: int = 0
    ) -> Optional[Dict]:
        if duration:
            result = self._search_lrclib_precise(title, artist, album, duration)
            if result:
                return result

        return self._search_lrclib_fuzzy(title, artist)

    def _search_lrclib_precise(
        self,
        title: str,
        artist: str,
        album: str,
        duration: int
    ) -> Optional[Dict]:
        url = "https://lrclib.net/api/get"
        params = {
            "track_name": title,
            "artist_name": artist,
        }
        if album:
            params["album_name"] = album
        if duration:
            params["duration"] = duration

        response = self._network.get(url, params=params, timeout=8)
        if not response or not isinstance(response, dict):
            return None

        content = response.get("syncedLyrics", "") or response.get("plainLyrics", "")
        if content:
            return {
                "content": content,
                "title": response.get("trackName", title),
                "artist": response.get("artistName", artist),
            }

        return None

    def _search_lrclib_fuzzy(self, title: str, artist: str) -> Optional[Dict]:
        url = "https://lrclib.net/api/search"
        query = f"{title} {artist}".strip()
        params = {"q": query, "limit": 10}

        response = self._network.get(url, params=params, timeout=8)
        if not response or not isinstance(response, list):
            return None

        title_lower = title.lower()
        artist_lower = artist.lower() if artist else ""

        synced_match = None
        plain_match = None

        for item in response:
            synced = item.get("syncedLyrics", "")
            plain = item.get("plainLyrics", "")
            if not synced and not plain:
                continue

            if title_lower and artist_lower:
                item_title = item.get("trackName", "").lower()
                item_artist = item.get("artistName", "").lower()
                if title_lower not in item_title and artist_lower not in item_artist:
                    continue

            result = {
                "content": synced or plain,
                "title": item.get("trackName", title),
                "artist": item.get("artistName", artist),
            }

            if synced and not synced_match:
                synced_match = result
            elif not plain_match:
                plain_match = result

            if synced_match:
                break

        if response and not synced_match and not plain_match:
            for item in response:
                synced = item.get("syncedLyrics", "")
                plain = item.get("plainLyrics", "")
                content = synced or plain
                if content:
                    return {
                        "content": content,
                        "title": item.get("trackName", title),
                        "artist": item.get("artistName", artist),
                    }

        return synced_match or plain_match

    def _search_lrclib_candidates(self, title: str, artist: str, limit: int = 10) -> List[Dict]:
        url = "https://lrclib.net/api/search"
        query = f"{title} {artist}".strip()
        params = {"q": query, "limit": limit}

        response = self._network.get(url, params=params, timeout=8)
        if not response or not isinstance(response, list):
            return []

        candidates = []
        for item in response:
            synced = item.get("syncedLyrics", "")
            plain = item.get("plainLyrics", "")
            content = synced or plain
            if not content:
                continue
            candidates.append({
                "content": content,
                "title": item.get("trackName", title),
                "artist": item.get("artistName", artist),
                "duration": item.get("duration", 0),
                "synced": bool(synced),
            })

        candidates.sort(key=lambda x: (0 if x.get("synced") else 1))
        return candidates

    def _search_lrcapi(self, title: str, artist: str) -> Optional[Dict]:
        return self._search_lrclib_fuzzy(title, artist)

    def _get_gequbao_plugin(self):
        try:
            from src.plugins.plugin_manager import PluginManager
            pm = PluginManager()
            return pm.get_plugin("gequbao")
        except Exception:
            return None

    def _search_gequbao(self, title: str, artist: str) -> Optional[Dict]:
        plugin = self._get_gequbao_plugin()
        if not plugin:
            return None
        try:
            keyword = f"{title} {artist}".strip()
            search_result = plugin.search(keyword, limit=5)
            songs = search_result.get("list", [])
            if not songs:
                return None

            title_lower = title.lower()
            artist_lower = artist.lower() if artist else ""
            matched_song = None

            for song in songs:
                song_title = song.get("title", "").lower()
                song_artist = song.get("artist", "").lower()
                if title_lower in song_title or (artist_lower and artist_lower in song_artist):
                    matched_song = song
                    break

            if not matched_song:
                matched_song = songs[0]

            song_id = matched_song.get("id", "")
            if not song_id:
                return None

            lrc_result = plugin.get_lyric(song_id)
            lrc_text = lrc_result.get("lrc", "") if lrc_result else ""
            if not lrc_text:
                return None

            return {
                "content": lrc_text,
                "title": matched_song.get("title", title),
                "artist": matched_song.get("artist", artist),
            }
        except Exception as e:
            logger.warning(f"Gequbao lyric search failed: {e}")
            return None

    def _search_gequbao_candidates(self, title: str, artist: str, limit: int = 5) -> List[Dict]:
        plugin = self._get_gequbao_plugin()
        if not plugin:
            return []
        try:
            keyword = f"{title} {artist}".strip()
            search_result = plugin.search(keyword, limit=limit)
            songs = search_result.get("list", [])
            if not songs:
                return []

            candidates = []
            for song in songs:
                song_id = song.get("id", "")
                if not song_id:
                    continue
                lrc_result = plugin.get_lyric(song_id)
                lrc_text = lrc_result.get("lrc", "") if lrc_result else ""
                if not lrc_text:
                    continue
                candidates.append({
                    "content": lrc_text,
                    "title": song.get("title", title),
                    "artist": song.get("artist", artist),
                    "duration": 0,
                })

            return candidates
        except Exception as e:
            logger.warning(f"Gequbao candidate search failed: {e}")
            return []

    def _search_netease(self, title: str, artist: str) -> Optional[Dict]:
        try:
            song_id = self._netease_search_song(title, artist)
            if not song_id:
                return None

            lyric_data = self._netease_get_lyric(song_id)
            if not lyric_data:
                return None

            lrc_content = lyric_data.get("lrc", {}).get("lyric", "")
            if not lrc_content:
                return None

            translate = lyric_data.get("tlyric", {}).get("lyric", "")

            return {
                "content": lrc_content,
                "translate": translate,
                "title": title,
                "artist": artist,
            }
        except Exception as e:
            logger.warning(f"Netease lyric search failed: {e}")
            return None

    def _netease_search_song(self, title: str, artist: str) -> Optional[str]:
        url = "https://music.163.com/api/search/get/web"
        keyword = f"{title} {artist}".strip()
        params = {
            "s": keyword,
            "type": 1,
            "offset": 0,
            "total": "true",
            "limit": 5,
        }
        headers = {
            "Referer": "https://music.163.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
        }

        response = self._network.get(url, params=params, headers=headers, timeout=8)
        if not response:
            return None

        songs = response.get("result", {}).get("songs", [])
        if not songs:
            return None

        title_lower = title.lower()
        artist_lower = artist.lower() if artist else ""

        for song in songs:
            song_name = song.get("name", "").lower()
            song_artists = [a.get("name", "").lower() for a in song.get("artists", [])]
            if title_lower in song_name:
                if not artist_lower or any(artist_lower in a for a in song_artists):
                    return str(song.get("id", ""))

        return str(songs[0].get("id", ""))

    def _netease_search_candidates(self, title: str, artist: str, limit: int = 5) -> List[Dict]:
        url = "https://music.163.com/api/search/get/web"
        keyword = f"{title} {artist}".strip()
        params = {
            "s": keyword,
            "type": 1,
            "offset": 0,
            "total": "true",
            "limit": limit,
        }
        headers = {
            "Referer": "https://music.163.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
        }

        response = self._network.get(url, params=params, headers=headers, timeout=8)
        if not response:
            return []

        songs = response.get("result", {}).get("songs", [])
        candidates = []

        for song in songs[:limit]:
            song_id = str(song.get("id", ""))
            song_name = song.get("name", "")
            song_artists = "/".join(a.get("name", "") for a in song.get("artists", []))
            duration_ms = song.get("duration", 0)

            lyric_data = self._netease_get_lyric(song_id)
            if not lyric_data:
                continue

            lrc_content = lyric_data.get("lrc", {}).get("lyric", "")
            if not lrc_content:
                continue

            translate = lyric_data.get("tlyric", {}).get("lyric", "")
            candidates.append({
                "content": lrc_content,
                "translate": translate,
                "title": song_name,
                "artist": song_artists,
                "duration": duration_ms // 1000 if duration_ms else 0,
            })

        return candidates

    def _netease_get_lyric(self, song_id: str) -> Optional[Dict]:
        url = "https://music.163.com/api/song/lyric"
        params = {
            "id": song_id,
            "lv": -1,
            "tv": -1,
        }
        headers = {
            "Referer": "https://music.163.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0",
        }

        response = self._network.get(url, params=params, headers=headers, timeout=8)
        return response

    def set_current_lyric(self, lrc_content: str, song_info: Optional[Dict] = None) -> None:
        self._current_lyric = self.parse_lrc(lrc_content)
        self._current_song = song_info
        self._lyric_offset_ms = 0
        if song_info:
            self._load_lyric_offset_from_db(
                song_info.get("title", ""), song_info.get("artist", "")
            )
        self._event_bus.publish(EVENT_LYRIC_LOADED, {
            "lyric": self._current_lyric,
            "song": song_info
        })

    def get_current_lyric(self) -> List[LyricLine]:
        return self._current_lyric

    def adjust_lyric_offset(self, delta_ms: int) -> int:
        self._lyric_offset_ms += delta_ms
        return self._lyric_offset_ms

    def get_lyric_offset(self) -> int:
        return self._lyric_offset_ms

    def reset_lyric_offset(self) -> None:
        self._lyric_offset_ms = 0

    def save_lyric_offset_to_db(self, title: str, artist: str = "") -> bool:
        try:
            song_key = self.make_song_key(title, artist)
            existing = self._db.fetchone(
                "SELECT id FROM lyric_offset WHERE song_key = ?",
                (song_key,)
            )
            if existing:
                self._db.update(
                    "lyric_offset",
                    {"offset_ms": self._lyric_offset_ms},
                    "song_key = ?",
                    (song_key,)
                )
            else:
                self._db.insert("lyric_offset", {
                    "song_key": song_key,
                    "offset_ms": self._lyric_offset_ms,
                })
            return True
        except Exception as e:
            logger.error(f"Error saving lyric offset to DB: {e}")
            return False

    def delete_lyric_offset_from_db(self, title: str, artist: str = "") -> bool:
        try:
            song_key = self.make_song_key(title, artist)
            self._db.delete("lyric_offset", "song_key = ?", (song_key,))
            return True
        except Exception as e:
            logger.error(f"Error deleting lyric offset from DB: {e}")
            return False

    def _load_lyric_offset_from_db(self, title: str, artist: str = "") -> None:
        try:
            song_key = self.make_song_key(title, artist)
            row = self._db.fetchone(
                "SELECT offset_ms FROM lyric_offset WHERE song_key = ?",
                (song_key,)
            )
            if row and row.get("offset_ms"):
                self._lyric_offset_ms = int(row["offset_ms"])
        except Exception:
            pass

    @staticmethod
    def make_song_key(title: str, artist: str = "") -> str:
        key = f"{title.strip().lower()}||{artist.strip().lower()}"
        return key

    def save_lyric_to_db(
        self,
        lrc_content: str,
        title: str,
        artist: str = "",
        album: str = "",
        duration: int = 0,
        source: str = "unknown",
        translate: str = "",
    ) -> bool:
        try:
            song_key = self.make_song_key(title, artist)
            is_synced = self._has_timestamp(lrc_content)
            existing = self._db.fetchone(
                "SELECT id FROM lyric WHERE song_key = ? AND source = ?",
                (song_key, source)
            )
            data = {
                "song_key": song_key,
                "title": title,
                "artist": artist,
                "album": album,
                "duration": duration,
                "source": source,
                "content": lrc_content,
                "translate": translate,
                "is_synced": 1 if is_synced else 0,
            }
            if existing:
                self._db.update("lyric", data, "id = ?", (existing["id"],))
            else:
                self._db.insert("lyric", data)
            return True
        except Exception as e:
            logger.error(f"Error saving lyric to DB: {e}")
            return False

    def load_lyric_from_db(
        self,
        title: str,
        artist: str = "",
    ) -> Optional[str]:
        try:
            song_key = self.make_song_key(title, artist)
            row = self._db.fetchone(
                "SELECT content FROM lyric WHERE song_key = ? AND is_synced = 1 ORDER BY update_time DESC LIMIT 1",
                (song_key,)
            )
            if row:
                return row["content"]
            row = self._db.fetchone(
                "SELECT content FROM lyric WHERE song_key = ? ORDER BY update_time DESC LIMIT 1",
                (song_key,)
            )
            if row:
                return row["content"]
            return None
        except Exception as e:
            logger.error(f"Error loading lyric from DB: {e}")
            return None

    def has_lyric_in_db(self, title: str, artist: str = "") -> bool:
        try:
            song_key = self.make_song_key(title, artist)
            row = self._db.fetchone(
                "SELECT id FROM lyric WHERE song_key = ? LIMIT 1",
                (song_key,)
            )
            return row is not None
        except Exception:
            return False

    def get_lyric_sources_from_db(self, title: str, artist: str = "") -> List[str]:
        try:
            song_key = self.make_song_key(title, artist)
            rows = self._db.fetchall(
                "SELECT source FROM lyric WHERE song_key = ?",
                (song_key,)
            )
            return [r["source"] for r in rows]
        except Exception:
            return []

    def save_lyric(
        self,
        lrc_content: str,
        song_path: str,
        save_path: Optional[str] = None
    ) -> bool:
        try:
            if save_path:
                target_path = save_path
            else:
                target_path = os.path.splitext(song_path)[0] + ".lrc"

            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(lrc_content)

            return True
        except Exception as e:
            logger.error(f"Error saving lyric: {e}")
            return False

    def auto_search_and_load(
        self,
        song_info: Dict,
        sources: Optional[List[str]] = None
    ) -> bool:
        song_path = song_info.get("path", "")
        title = song_info.get("title", "")
        artist = song_info.get("artist", "")
        album = song_info.get("album", "")
        duration = song_info.get("duration", 0)

        local_lyric = self.load_local_lyric(song_path)
        if local_lyric:
            self.set_current_lyric(local_lyric, song_info)
            if not self.has_lyric_in_db(title, artist):
                self.save_lyric_to_db(local_lyric, title, artist, album, duration, "local")
            return True

        db_lyric = self.load_lyric_from_db(title, artist)
        if db_lyric:
            self.set_current_lyric(db_lyric, song_info)
            if song_path and not self.has_local_lyric(song_path):
                self.save_lyric(db_lyric, song_path)
            return True

        results = self.search_lyric_online(title, artist, album, duration, sources)

        if results:
            best_result = results[0]
            self.set_current_lyric(best_result["content"], song_info)

            self.save_lyric_to_db(
                best_result["content"], title, artist, album, duration,
                best_result["source"], best_result.get("translate", "")
            )

            if song_path:
                self.save_lyric(best_result["content"], song_path)

            return True

        return False

    def search_and_save(
        self,
        song_info: Dict,
        sources: Optional[List[str]] = None,
        overwrite: bool = False
    ) -> Dict:
        song_path = song_info.get("path", "")
        title = song_info.get("title", "Unknown")
        artist = song_info.get("artist", "")
        album = song_info.get("album", "")
        duration = song_info.get("duration", 0)

        if not overwrite and self.has_lyric_in_db(title, artist):
            return {
                "status": "skipped",
                "path": song_path,
                "title": title,
                "artist": artist,
                "message": "Lyric already exists in database",
            }

        results = self.search_lyric_online(title, artist, album, duration, sources)

        if results:
            best = results[0]
            content = best["content"]

            self.save_lyric_to_db(
                content, title, artist, album, duration,
                best["source"], best.get("translate", "")
            )

            if song_path:
                self.save_lyric(content, song_path)

            return {
                "status": "success",
                "path": song_path,
                "title": title,
                "artist": artist,
                "source": best["source"],
                "message": f"Downloaded from {best['source']}",
            }

        return {
            "status": "not_found",
            "path": song_path,
            "title": title,
            "artist": artist,
            "message": "No lyric found from any source",
        }
