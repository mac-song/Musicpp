import json
import os
import re
import subprocess
import tempfile
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict

from yt_dlp import YoutubeDL

from src.plugins.plugin_interface import MusicPluginInterface
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

_CACHE_DIR = os.path.join(tempfile.gettempdir(), "musicpp_online_cache")


def _get_ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, Exception):
        return "ffmpeg"


class BiliBiliPlugin(MusicPluginInterface):
    meta = {
        "id": "bilibili",
        "name": "B站音乐",
        "version": "2.2",
        "author": "Music++",
        "description": "搜索B站音乐视频并提取音频流，支持合集章节切分",
        "source_name": "B站",
    }

    SEARCH_API = "https://api.bilibili.com/x/web-interface/search/type"
    VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view"

    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    def __init__(self):
        self._search_cache = {}
        self._title_cache = {}
        self._url_cache = {}
        self._chapter_cache = {}
        self._buvid3 = str(uuid.uuid4())
        os.makedirs(_CACHE_DIR, exist_ok=True)

    def _make_headers(self, referer="https://search.bilibili.com") -> dict:
        return {
            "User-Agent": self._UA,
            "Referer": referer,
            "Origin": "https://search.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": f"buvid3={self._buvid3}",
        }

    def search(self, keyword: str, page: int = 1, limit: int = 30) -> Dict[str, Any]:
        try:
            params = urllib.parse.urlencode({
                "search_type": "video",
                "keyword": keyword,
                "page": page,
                "page_size": limit,
            })
            url = f"{self.SEARCH_API}?{params}"

            req = urllib.request.Request(url, headers=self._make_headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") != 0:
                logger.error(f"BiliBili search API error: {data.get('message', '')}")
                return {"total": 0, "list": []}

            results_raw = data.get("data", {}).get("result", [])
            total = data.get("data", {}).get("numResults", len(results_raw))

            results = []
            for item in results_raw:
                bvid = item.get("bvid", "")
                if not bvid:
                    continue
                if not bvid.startswith("BV"):
                    bvid = "BV" + bvid

                title = item.get("title", "")
                title = re.sub(r'<[^>]+>', '', title)
                author = item.get("author", "")
                duration_str = item.get("duration", "0:00")
                duration = self._parse_duration(duration_str)
                cover = item.get("pic", "")
                if cover and not cover.startswith("http"):
                    cover = "https:" + cover

                clean_title = self._clean_title(title)
                artist = self._extract_artist(title) if not author else author

                song = {
                    "id": bvid,
                    "pluginId": "bilibili",
                    "source": "bilibili",
                    "title": clean_title,
                    "artist": artist,
                    "album": "B站",
                    "duration": duration,
                    "cover": cover,
                    "qualities": [
                        {"type": "m4a", "size": 0},
                    ],
                    "sources": ["bilibili"],
                }
                results.append(song)
                self._search_cache[bvid] = f"https://www.bilibili.com/video/{bvid}"
                self._title_cache[bvid] = clean_title

            return {"total": total, "list": results}

        except Exception as e:
            logger.error(f"BiliBili search error: {e}")
            return {"total": 0, "list": []}

    def get_chapters(self, song_id: str) -> list:
        if song_id in self._chapter_cache:
            return self._chapter_cache[song_id]
        chapters = self._fetch_chapters(song_id)
        self._chapter_cache[song_id] = chapters
        return chapters

    def _fetch_chapters(self, bvid: str) -> list:
        try:
            params = urllib.parse.urlencode({"bvid": bvid})
            url = f"{self.VIDEO_INFO_API}?{params}"
            req = urllib.request.Request(url, headers=self._make_headers("https://www.bilibili.com"))
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("code") != 0:
                return []

            video_info = data.get("data", {})
            pages = video_info.get("pages", [])
            ugc_season = video_info.get("ugc_season", None)

            if len(pages) > 1:
                return self._parse_pages_chapters(video_info, pages)

            if ugc_season:
                return self._parse_ugc_season_chapters(video_info, ugc_season)

            return []
        except Exception as e:
            logger.warning(f"Failed to fetch chapters for {bvid}: {e}")
            return []

    def _parse_pages_chapters(self, video_info: dict, pages: list) -> list:
        uploader = ""
        owner = video_info.get("owner", {})
        if isinstance(owner, dict):
            uploader = owner.get("name", "")
        video_title = self._clean_title(video_info.get("title", ""))

        chapters = []
        for idx, page in enumerate(pages):
            cid = page.get("cid", "")
            part_title = page.get("part", "")
            duration = page.get("duration", 0)
            if not part_title:
                part_title = f"Part {idx + 1}"

            parsed = self._parse_chapter_title(part_title)
            artist = parsed["artist"] or uploader

            chapters.append({
                "index": idx,
                "cid": cid,
                "bvid": video_info.get("bvid", ""),
                "title": parsed["title"],
                "artist": artist,
                "album": video_title,
                "duration": duration,
                "chapter_type": "page",
            })
        return chapters

    def _parse_ugc_season_chapters(self, video_info: dict, ugc_season: dict) -> list:
        uploader = ""
        owner = video_info.get("owner", {})
        if isinstance(owner, dict):
            uploader = owner.get("name", "")
        season_title = ugc_season.get("title", "") or self._clean_title(video_info.get("title", ""))

        chapters = []
        idx = 0
        for section in ugc_season.get("sections", []):
            for ep in section.get("episodes", []):
                ep_bvid = ep.get("bvid", "")
                ep_cid = ep.get("cid", "")
                ep_title = ep.get("title", "")
                ep_arc = ep.get("arc", {})
                ep_duration = ep_arc.get("duration", 0)
                if isinstance(ep_duration, (int, float)) and ep_duration > 1000:
                    ep_duration = int(ep_duration)

                if not ep_title:
                    ep_title = f"Episode {idx + 1}"

                parsed = self._parse_chapter_title(ep_title)
                artist = parsed["artist"] or uploader

                chapters.append({
                    "index": idx,
                    "cid": str(ep_cid),
                    "bvid": ep_bvid,
                    "title": parsed["title"],
                    "artist": artist,
                    "album": season_title,
                    "duration": ep_duration,
                    "chapter_type": "ugc_season",
                })
                idx += 1
        return chapters

    def get_song_url(self, song_id: str, quality: str = "320k") -> Dict[str, Any]:
        if song_id in self._url_cache:
            return self._url_cache[song_id]

        chapter_match = re.match(r'^(BV[a-zA-Z0-9]+)_p(\d+)$', song_id)
        if not chapter_match:
            chapter_match = re.match(r'^([a-zA-Z0-9]+)_p(\d+)$', song_id)
        if chapter_match:
            bvid = chapter_match.group(1)
            if not bvid.startswith("BV"):
                bvid = "BV" + bvid
            chapter_index = int(chapter_match.group(2))
            return self.get_chapter_url(bvid, "", chapter_index)

        try:
            actual_id = song_id
            if not actual_id.startswith("BV"):
                actual_id = "BV" + actual_id
            url = self._search_cache.get(song_id, f"https://www.bilibili.com/video/{actual_id}")
            title = self._title_cache.get(song_id, song_id)
            safe_title = self._sanitize_filename(title)
            cache_file = os.path.join(_CACHE_DIR, f"{safe_title}.m4a")

            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
                result = {"url": cache_file, "is_local": True}
                self._url_cache[song_id] = result
                return result

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio/best",
                "noplaylist": True,
                "outtmpl": cache_file,
                "overwrites": True,
                "http_headers": {
                    "User-Agent": self._UA,
                    "Referer": "https://www.bilibili.com",
                },
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
                result = {"url": cache_file, "is_local": True}
                self._url_cache[song_id] = result
                return result

            return {"url": "", "error": "下载音频失败"}
        except Exception as e:
            logger.error(f"BiliBili get_song_url error: {e}")
            return {"url": "", "error": str(e)}

    def get_chapter_url(self, bvid: str, cid: str, chapter_index: int) -> Dict[str, Any]:
        cache_key = f"{bvid}_p{chapter_index}"
        if cache_key in self._url_cache:
            return self._url_cache[cache_key]

        try:
            chapters = self.get_chapters(bvid)
            chapter = None
            for ch in chapters:
                if ch["index"] == chapter_index:
                    chapter = ch
                    break
            if not chapter:
                return {"url": "", "error": "Chapter not found"}

            chapter_title = chapter["title"]
            safe_title = self._sanitize_filename(chapter_title)
            cache_file = os.path.join(_CACHE_DIR, f"{safe_title}.m4a")

            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000:
                result = {"url": cache_file, "is_local": True, "title": chapter["title"], "artist": chapter.get("artist", ""), "album": chapter.get("album", "")}
                self._url_cache[cache_key] = result
                return result

            chapter_type = chapter.get("chapter_type", "page")

            if chapter_type == "ugc_season":
                ep_bvid = chapter.get("bvid", bvid)
                download_url = f"https://www.bilibili.com/video/{ep_bvid}"
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "noplaylist": True,
                    "outtmpl": cache_file,
                    "overwrites": True,
                    "http_headers": {
                        "User-Agent": self._UA,
                        "Referer": "https://www.bilibili.com",
                    },
                }
            else:
                url = self._search_cache.get(bvid, f"https://www.bilibili.com/video/{bvid}")
                page_num = chapter_index + 1
                download_url = url
                ydl_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "format": "bestaudio/best",
                    "noplaylist": False,
                    "playlist_items": str(page_num),
                    "outtmpl": cache_file,
                    "overwrites": True,
                    "http_headers": {
                        "User-Agent": self._UA,
                        "Referer": "https://www.bilibili.com",
                    },
                }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([download_url])

            if os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000:
                result = {"url": cache_file, "is_local": True, "title": chapter["title"], "artist": chapter.get("artist", ""), "album": chapter.get("album", "")}
                self._url_cache[cache_key] = result
                return result

            return {"url": "", "error": "Chapter download failed"}

        except Exception as e:
            logger.error(f"BiliBili get_chapter_url error: {e}")
            return {"url": "", "error": str(e)}

    def _split_by_chapters(self, full_m4a: str, bvid: str, chapters: list) -> list:
        result_files = []
        for ch in chapters:
            safe_name = self._sanitize_filename(ch["title"])
            out_file = os.path.join(_CACHE_DIR, f"{safe_name}.m4a")
            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                result_files.append(out_file)
                continue

            start_time = 0
            for prev_ch in chapters:
                if prev_ch["index"] == ch["index"]:
                    break
                start_time += prev_ch.get("duration", 0)

            duration = ch.get("duration", 0)
            if duration <= 0:
                result_files.append("")
                continue

            try:
                cmd = [
                    _get_ffmpeg_path(), "-y", "-i", full_m4a,
                    "-ss", str(start_time),
                    "-t", str(duration),
                    "-c:a", "aac", "-b:a", "192k",
                    "-vn",
                    "-metadata", f"title={ch['title']}",
                    "-metadata", f"artist={ch.get('artist', '')}",
                    "-metadata", f"album={ch.get('album', '')}",
                    "-metadata", f"track={ch['index'] + 1}/{len(chapters)}",
                    out_file,
                ]
                subprocess.run(cmd, capture_output=True, timeout=120, check=True)
                if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                    result_files.append(out_file)
                else:
                    result_files.append("")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"ffmpeg split failed for chapter {ch['title']}: {e}")
                result_files.append("")

        return result_files

    def get_lyric(self, song_id: str) -> Dict[str, Any]:
        try:
            actual_id = song_id
            if not actual_id.startswith("BV"):
                actual_id = "BV" + actual_id
            url = f"https://www.bilibili.com/video/{actual_id}"

            sub_dir = os.path.join(_CACHE_DIR, "subs")
            os.makedirs(sub_dir, exist_ok=True)
            safe_id = re.sub(r'[\\/:*?"<>|]', '_', actual_id)
            out_base = os.path.join(sub_dir, safe_id)

            for existing in os.listdir(sub_dir):
                if existing.startswith(safe_id) and existing.endswith((".srt", ".vtt", ".ass")):
                    existing_path = os.path.join(sub_dir, existing)
                    lrc = self._convert_subtitle_to_lrc(existing_path)
                    if lrc:
                        return {"lrc": lrc, "tlyric": ""}

            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["zh", "zh-Hans", "zh-CN", "en", "ja"],
                "subtitlesformat": "srt",
                "outtmpl": out_base,
                "http_headers": {
                    "User-Agent": self._UA,
                    "Referer": "https://www.bilibili.com",
                },
            }

            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except Exception:
                pass

            for existing in os.listdir(sub_dir):
                if existing.startswith(safe_id) and existing.endswith((".srt", ".vtt", ".ass")):
                    existing_path = os.path.join(sub_dir, existing)
                    lrc = self._convert_subtitle_to_lrc(existing_path)
                    if lrc:
                        return {"lrc": lrc, "tlyric": ""}

            return {"lrc": "", "tlyric": ""}
        except Exception as e:
            logger.warning(f"BiliBili get_lyric error: {e}")
            return {"lrc": "", "tlyric": ""}

    @staticmethod
    def _convert_subtitle_to_lrc(subtitle_path: str) -> str:
        ext = os.path.splitext(subtitle_path)[1].lower()
        try:
            with open(subtitle_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            try:
                with open(subtitle_path, "r", encoding="gbk") as f:
                    content = f.read()
            except Exception:
                return ""

        if ext == ".srt":
            return BiliBiliPlugin._srt_to_lrc(content)
        elif ext == ".vtt":
            return BiliBiliPlugin._vtt_to_lrc(content)
        elif ext == ".ass":
            return BiliBiliPlugin._ass_to_lrc(content)
        return ""

    @staticmethod
    def _srt_to_lrc(content: str) -> str:
        import re as _re
        lines = []
        blocks = _re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            block_lines = block.strip().split('\n')
            if len(block_lines) < 3:
                continue
            time_match = _re.match(
                r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})',
                block_lines[1].strip()
            )
            if not time_match:
                continue
            m, s, ms = int(time_match.group(1)), int(time_match.group(2)), int(time_match.group(3))
            total_ms = m * 60000 + s * 1000 + ms
            minutes = total_ms // 60000
            seconds = (total_ms % 60000) // 1000
            centiseconds = (total_ms % 1000) // 10
            text = ' '.join(line.strip() for line in block_lines[2:] if line.strip())
            text = _re.sub(r'<[^>]+>', '', text)
            text = text.strip()
            if not text:
                continue
            lines.append(f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]{text}")
        return '\n'.join(lines)

    @staticmethod
    def _vtt_to_lrc(content: str) -> str:
        import re as _re
        lines = []
        time_pattern = _re.compile(
            r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})'
        )
        current_text = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                continue
            tm = time_pattern.match(line)
            if tm:
                if current_text:
                    text = ' '.join(current_text).strip()
                    text = _re.sub(r'<[^>]+>', '', text)
                    if text:
                        lines.append(text)
                    current_text = []
                m, s, ms = int(tm.group(1)), int(tm.group(2)), int(tm.group(3))
                total_ms = m * 60000 + s * 1000 + ms
                minutes = total_ms // 60000
                seconds = (total_ms % 60000) // 1000
                centiseconds = (total_ms % 1000) // 10
                current_text = [f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"]
                continue
            if line and current_text:
                current_text.append(line)
        if current_text:
            text = ' '.join(current_text).strip()
            text = _re.sub(r'<[^>]+>', '', text)
            if text and not text.endswith(']'):
                lines.append(text)
        return '\n'.join(lines)

    @staticmethod
    def _ass_to_lrc(content: str) -> str:
        import re as _re
        lines = []
        dialogue_pattern = _re.compile(
            r'Dialogue:\s*\d+,\s*(\d):(\d{2}):(\d{2})\.(\d{2}),\s*\d:\d{2}:\d{2}\.\d{2},([^,]*),([^,]*),([^,]*),([^,]*),(.*)'
        )
        for line in content.split('\n'):
            m = dialogue_pattern.match(line.strip())
            if not m:
                continue
            h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            total_ms = h * 3600000 + mi * 60000 + s * 1000 + cs * 10
            minutes = total_ms // 60000
            seconds = (total_ms % 60000) // 1000
            centiseconds = (total_ms % 1000) // 10
            text = m.group(9).strip()
            text = _re.sub(r'\{[^}]*\}', '', text)
            text = text.replace('\\N', ' ').replace('\\n', ' ')
            text = text.strip()
            if not text:
                continue
            lines.append(f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]{text}")
        return '\n'.join(lines)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        filename = re.sub(r'[\\/:*?"<>|]', '_', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        if not filename:
            filename = 'unknown'
        return filename

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

    @staticmethod
    def _parse_chapter_title(raw_title: str) -> dict:
        title = raw_title.strip()
        title = re.sub(r"分P\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"【[^】]*】", "", title)
        title = re.sub(r"\[[^\]]*\]", "", title)
        title = re.sub(r"[【】\[\]（）()]", " ", title)
        title = re.sub(r"^\d+[\.\s、]+", "", title)
        title = re.sub(r"\s+", " ", title).strip()

        song_title = title
        artist = ""
        album = ""

        m = re.match(r"^(.+?)\s*[-—–]\s*(.+)$", title)
        if m:
            left, right = m.group(1).strip(), m.group(2).strip()
            if re.match(r"^[\u4e00-\u9fff\u3400-\u4dbf]", left) and not re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", right):
                song_title = left
                artist = right
            elif re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", right):
                song_title = right
                artist = left
            else:
                song_title = right
                artist = left

        m2 = re.match(r"^(.+?)\s*[:：]\s*(.+)$", title)
        if m2 and not artist:
            artist = m2.group(1).strip()
            song_title = m2.group(2).strip()

        bm = re.search(r"《([^》]+)》", song_title)
        if bm:
            song_title = bm.group(1)

        if not song_title:
            song_title = raw_title.strip()

        return {"title": song_title, "artist": artist, "album": album}

    @staticmethod
    def _clean_title(title: str) -> str:
        title = re.sub(r"分P\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"【[^】]*】", "", title)
        title = re.sub(r"\[[^\]]*\]", "", title)
        title = re.sub(r"[【】\[\]（）()]", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title

    @staticmethod
    def _extract_artist(title: str) -> str:
        patterns = [
            r"[-—]\s*([^-—【\]]+?)\s*[-—]",
            r"[:：]\s*([^:：【\]]+?)\s*[:：]",
        ]
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                return match.group(1).strip()
        return ""
