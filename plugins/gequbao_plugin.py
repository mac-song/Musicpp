import html as html_lib
import json
import re
import urllib.parse
import urllib.request
import http.cookiejar
from typing import Any, Dict, Optional

from src.plugins.plugin_interface import MusicPluginInterface
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class GeQuBaoPlugin(MusicPluginInterface):
    meta = {
        "id": "gequbao",
        "name": "歌曲宝",
        "version": "1.0",
        "author": "Music++",
        "description": "搜索歌曲宝音乐资源并在线播放",
        "source_name": "歌曲宝",
    }

    _BASE_URL = "https://www.gequbao.com"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self._song_cache: Dict[str, Dict] = {}
        self._lrc_cache: Dict[str, str] = {}
        self._url_cache: Dict[str, Dict] = {}
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj)
        )

    def _make_headers(self, referer: str = "") -> dict:
        h = {
            "User-Agent": self._UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if referer:
            h["Referer"] = referer
        return h

    def _make_api_headers(self, referer: str = "") -> dict:
        return {
            "User-Agent": self._UA,
            "Referer": referer,
            "Origin": self._BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _fetch_page(self, url: str, headers: dict = None) -> Optional[str]:
        try:
            req = urllib.request.Request(url, headers=headers or self._make_headers())
            with self._opener.open(req, timeout=15) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            logger.error(f"Fetch page failed [{url}]: {e}")
            return None

    def _parse_app_data(self, page_html: str) -> Optional[Dict]:
        m = re.search(r"window\.appData\s*=\s*JSON\.parse\('(.*?)'\)", page_html)
        if not m:
            return None
        try:
            raw = m.group(1)
            decoded = raw.encode("utf-8").decode("unicode_escape")
            return json.loads(decoded)
        except Exception as e:
            logger.error(f"Parse appData failed: {e}")
            return None

    def _parse_lrc(self, page_html: str) -> str:
        m = re.search(r'id="content-lrc"[^>]*>(.*?)</div>', page_html, re.DOTALL)
        if not m:
            return ""
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        return text

    def _fetch_song_detail(self, page_id: str) -> Optional[Dict]:
        if page_id in self._song_cache:
            return self._song_cache[page_id]

        url = f"{self._BASE_URL}/music/{page_id}"
        page_html = self._fetch_page(url)
        if not page_html:
            return None

        app_data = self._parse_app_data(page_html)
        if not app_data:
            return None

        lrc_text = self._parse_lrc(page_html)
        if lrc_text:
            self._lrc_cache[page_id] = lrc_text

        cover = app_data.get("mp3_cover", "")
        if cover:
            cover = cover.replace("\\/", "/")

        detail = {
            "mp3_id": app_data.get("mp3_id"),
            "play_id": app_data.get("play_id", ""),
            "title": app_data.get("mp3_title", ""),
            "author": app_data.get("mp3_author", ""),
            "cover": cover,
            "duration": self._parse_duration(app_data.get("mp3_duration", "0:00")),
            "lrc_is_empty": app_data.get("lrc_is_empty", True),
            "mp3_type": app_data.get("mp3_type", 0),
        }
        self._song_cache[page_id] = detail
        return detail

    def _request_play_url(self, play_id: str, mp3_id) -> Optional[str]:
        api_url = f"{self._BASE_URL}/api/play-url"
        headers = self._make_api_headers(
            referer=f"{self._BASE_URL}/music/{mp3_id}"
        )
        params = {"id": play_id}
        post_data = urllib.parse.urlencode(params).encode("utf-8")
        try:
            req = urllib.request.Request(api_url, data=post_data, headers=headers)
            with self._opener.open(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("code") == 1:
                return data["data"]["url"]
            logger.warning(f"play-url API error: {data.get('msg', '')}")
        except Exception as e:
            logger.error(f"Request play-url failed: {e}")
        return None

    def search(self, keyword: str, page: int = 1, limit: int = 30) -> Dict[str, Any]:
        try:
            url = f"{self._BASE_URL}/s/{urllib.parse.quote(keyword)}"
            logger.info(f"GeQuBao search: url={url}")
            page_html = self._fetch_page(url)
            if not page_html:
                logger.warning(f"GeQuBao search: fetch_page returned None for '{keyword}'")
                return {"total": 0, "list": []}

            rows = re.findall(
                r'<a[^>]*href="/music/(\d+)"[^>]*title="([^"]+)"',
                page_html,
            )
            logger.info(f"GeQuBao search: found {len(rows)} raw results for '{keyword}'")
            seen = set()
            results = []
            for sid, title_text in rows:
                if sid in seen:
                    continue
                seen.add(sid)
                parts = title_text.split(" - ", 1)
                name = html_lib.unescape(parts[0].strip())
                author = html_lib.unescape(parts[1].strip()) if len(parts) > 1 else ""

                results.append({
                    "id": sid,
                    "pluginId": "gequbao",
                    "source": "gequbao",
                    "title": name,
                    "artist": author,
                    "album": "",
                    "duration": 0,
                    "cover": "",
                    "qualities": [{"type": "mp3", "size": 0}],
                    "sources": ["gequbao"],
                })
                if len(results) >= limit:
                    break

            logger.info(f"GeQuBao search: returning {len(results)} results for '{keyword}'")
            for idx, r in enumerate(results):
                logger.debug(f"  [{idx}] {r['title']} - {r['artist']} (id={r['id']})")
            return {"total": len(results), "list": results}

        except Exception as e:
            logger.error(f"GeQuBao search error: {e}")
            return {"total": 0, "list": []}

    def get_song_url(self, song_id: str, quality: str = "320k") -> Dict[str, Any]:
        if song_id in self._url_cache:
            return self._url_cache[song_id]

        try:
            detail = self._fetch_song_detail(song_id)
            if not detail:
                return {"url": "", "error": "无法获取歌曲详情"}

            play_id = detail.get("play_id", "")
            if not play_id:
                return {"url": "", "error": "无法获取play_id"}

            mp3_url = self._request_play_url(play_id, detail.get("mp3_id", song_id))
            if not mp3_url:
                self._song_cache.pop(song_id, None)
                detail = self._fetch_song_detail(song_id)
                if detail:
                    play_id = detail.get("play_id", "")
                    if play_id:
                        mp3_url = self._request_play_url(
                            play_id, detail.get("mp3_id", song_id)
                        )

            if not mp3_url:
                return {"url": "", "error": "获取播放链接失败"}

            result = {"url": mp3_url}
            self._url_cache[song_id] = result
            return result

        except Exception as e:
            logger.error(f"GeQuBao get_song_url error: {e}")
            return {"url": "", "error": str(e)}

    def get_lyric(self, song_id: str) -> Dict[str, Any]:
        try:
            if song_id in self._lrc_cache:
                return {"lrc": self._lrc_cache[song_id], "tlyric": ""}

            detail = self._fetch_song_detail(song_id)
            if not detail:
                return {"lrc": "", "tlyric": ""}

            lrc = self._lrc_cache.get(song_id, "")
            return {"lrc": lrc, "tlyric": ""}

        except Exception as e:
            logger.error(f"GeQuBao get_lyric error: {e}")
            return {"lrc": "", "tlyric": ""}

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        try:
            parts = duration_str.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except (ValueError, IndexError):
            pass
        return 0
