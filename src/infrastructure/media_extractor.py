import json
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from src.infrastructure.subtitle_parser import Chapter, SubtitleLine, SubtitleParser
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SubtitleInfo:
    lang: str
    name: str
    is_auto: bool


@dataclass
class ExtractOptions:
    subtitle_lang: str = "en"
    subtitle_lang_secondary: str = ""
    prefer_manual_sub: bool = True
    extract_audio: bool = True
    extract_subtitle: bool = True
    audio_format: str = "m4a"
    output_dir: str = ""


@dataclass
class ExtractResult:
    success: bool
    title: str = ""
    audio_path: str = ""
    subtitle_path: str = ""
    subtitle_path_secondary: str = ""
    chapters: List[Chapter] = field(default_factory=list)
    subtitle_lines: List[SubtitleLine] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""


def _get_ffmpeg_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    plugin_ffmpeg = os.path.join(project_root, "plugins", "ffmpeg", "ffmpeg.exe")
    if os.path.exists(plugin_ffmpeg):
        return plugin_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, Exception):
        pass
    import shutil
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    return "ffmpeg"


def _get_ffprobe_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    plugin_ffprobe = os.path.join(project_root, "plugins", "ffmpeg", "ffprobe.exe")
    if os.path.exists(plugin_ffprobe):
        return plugin_ffprobe
    import shutil
    sys_ffprobe = shutil.which("ffprobe")
    if sys_ffprobe:
        return sys_ffprobe
    return ""


class MediaExtractor:

    def __init__(self):
        self._ffmpeg = _get_ffmpeg_path()
        self._ffprobe = _get_ffprobe_path()

    def get_available_subtitles(self, url: str) -> List[SubtitleInfo]:
        try:
            from yt_dlp import YoutubeDL
            ydl_opts = {
                "listsubtitles": True,
                "quiet": True,
                "no_warnings": True,
            }
            if self._ffmpeg:
                ydl_opts["ffmpeg_location"] = self._ffmpeg
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return []
                result = []
                manual_subs = info.get("subtitles", {})
                auto_subs = info.get("automatic_captions", {})
                for lang, subs in manual_subs.items():
                    name = subs[0].get("name", lang) if subs else lang
                    result.append(SubtitleInfo(lang=lang, name=name, is_auto=False))
                for lang, subs in auto_subs.items():
                    if lang not in manual_subs:
                        name = subs[0].get("name", f"{lang} (auto)") if subs else f"{lang} (auto)"
                        result.append(SubtitleInfo(lang=lang, name=name, is_auto=True))
                return result
        except Exception as e:
            logger.warning(f"MediaExtractor get_available_subtitles error: {e}")
            return []

    def get_chapters(self, url: str) -> List[Chapter]:
        try:
            from yt_dlp import YoutubeDL
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
            }
            if self._ffmpeg:
                ydl_opts["ffmpeg_location"] = self._ffmpeg
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return []
                raw_chapters = info.get("chapters") or []
                if not raw_chapters:
                    return []
                chapters = []
                for i, ch in enumerate(raw_chapters):
                    start_ms = int(ch.get("start_time", 0) * 1000)
                    end_ms = int(ch.get("end_time", 0) * 1000)
                    title = ch.get("title", f"Chapter {i + 1}")
                    chapters.append(Chapter(index=i, title=title, start_ms=start_ms, end_ms=end_ms))
                return chapters
        except Exception as e:
            logger.warning(f"MediaExtractor get_chapters error: {e}")
            return []

    def extract_from_url(
        self,
        url: str,
        options: ExtractOptions,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> ExtractResult:
        try:
            from yt_dlp import YoutubeDL

            output_dir = options.output_dir or tempfile.mkdtemp(prefix="study_")
            os.makedirs(output_dir, exist_ok=True)

            if progress_callback:
                progress_callback("获取视频信息...", 10)

            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "no_warnings": True,
                "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": options.audio_format,
                }],
            }

            if self._ffmpeg:
                ydl_opts["ffmpeg_location"] = self._ffmpeg

            if options.extract_subtitle:
                ydl_opts["writesubtitles"] = options.prefer_manual_sub
                ydl_opts["writeautomaticsub"] = True
                sublangs = [options.subtitle_lang]
                if options.subtitle_lang_secondary:
                    sublangs.append(options.subtitle_lang_secondary)
                ydl_opts["subtitleslangs"] = sublangs
                ydl_opts["subtitlesformat"] = "srt"

                try:
                    cookie_file = self._get_cookie_file()
                    if cookie_file:
                        ydl_opts["cookiefile"] = cookie_file
                        logger.info(f"extract_from_url: using cookie file: {cookie_file}")
                    else:
                        cookie_browser = self._get_cookie_browser()
                        if cookie_browser:
                            ydl_opts["cookiesfrombrowser"] = (cookie_browser,)
                            logger.info(f"extract_from_url: using cookies from browser: {cookie_browser}")
                except Exception as e:
                    logger.warning(f"extract_from_url: cookie setup failed: {e}")

            if progress_callback:
                progress_callback("下载音频和字幕...", 30)

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return ExtractResult(success=False, error="无法获取视频信息")

            title = info.get("title") or "Unknown"
            duration_ms = int((info.get("duration") or 0) * 1000)

            all_files = os.listdir(output_dir)
            logger.info(f"extract_from_url: downloaded files in {output_dir}: {all_files}")

            if progress_callback:
                progress_callback("处理文件...", 70)

            audio_path = self._find_audio_file(output_dir, title, options.audio_format)
            subtitle_path = self._find_subtitle_file(output_dir, title, options.subtitle_lang)
            logger.info(f"extract_from_url: audio_path='{audio_path}', subtitle_path='{subtitle_path}', lang='{options.subtitle_lang}'")

            if not subtitle_path and "bilibili.com" in url:
                logger.info("extract_from_url: no subtitle file found, trying Bilibili API fallback")
                bilibili_sub = self._extract_bilibili_subtitle(url, output_dir, options.subtitle_lang)
                if bilibili_sub:
                    subtitle_path = bilibili_sub
                    logger.info(f"extract_from_url: Bilibili API fallback found subtitle: {subtitle_path}")

            subtitle_path_secondary = ""
            if options.subtitle_lang_secondary:
                subtitle_path_secondary = self._find_subtitle_file(
                    output_dir, title, options.subtitle_lang_secondary
                )

            raw_chapters = info.get("chapters") or []
            chapters = []
            for i, ch in enumerate(raw_chapters):
                start_ms = int(ch.get("start_time", 0) * 1000)
                end_ms = int(ch.get("end_time", 0) * 1000)
                title_ch = ch.get("title", f"Chapter {i + 1}")
                chapters.append(Chapter(index=i, title=title_ch, start_ms=start_ms, end_ms=end_ms))

            subtitle_lines = []
            if subtitle_path and os.path.exists(subtitle_path):
                try:
                    with open(subtitle_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    fmt = SubtitleParser.detect_format(subtitle_path)
                    subtitle_lines = SubtitleParser.parse(content, fmt) or []

                    if subtitle_path_secondary and os.path.exists(subtitle_path_secondary):
                        with open(subtitle_path_secondary, "r", encoding="utf-8", errors="ignore") as f:
                            content2 = f.read()
                        fmt2 = SubtitleParser.detect_format(subtitle_path_secondary)
                        secondary_lines = SubtitleParser.parse(content2, fmt2) or []
                        subtitle_lines = SubtitleParser.merge_translations(subtitle_lines, secondary_lines) or subtitle_lines
                except Exception as e:
                    logger.warning(f"MediaExtractor subtitle parse error: {e}")

            if progress_callback:
                progress_callback("完成", 100)

            return ExtractResult(
                success=True,
                title=title,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                subtitle_path_secondary=subtitle_path_secondary,
                chapters=chapters,
                subtitle_lines=subtitle_lines,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"MediaExtractor extract_from_url error: {e}")
            return ExtractResult(success=False, error=str(e))

    def extract_from_file(
        self,
        file_path: str,
        options: ExtractOptions,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> ExtractResult:
        try:
            if not os.path.exists(file_path):
                return ExtractResult(success=False, error=f"文件不存在: {file_path}")

            output_dir = options.output_dir or os.path.dirname(file_path)
            os.makedirs(output_dir, exist_ok=True)

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            title = base_name

            if progress_callback:
                progress_callback("提取音频...", 20)

            audio_path = os.path.join(output_dir, f"{base_name}.{options.audio_format}")
            if not os.path.exists(audio_path) or os.path.getmtime(file_path) > os.path.getmtime(audio_path):
                cmd = [
                    self._ffmpeg, "-i", file_path,
                    "-vn", "-acodec", "copy",
                    "-y", audio_path,
                ]
                result = subprocess.run(cmd, capture_output=True, timeout=120)
                if result.returncode != 0:
                    cmd = [
                        self._ffmpeg, "-i", file_path,
                        "-vn", "-acodec", "aac", "-q:a", "2",
                        "-y", audio_path,
                    ]
                    result = subprocess.run(cmd, capture_output=True, timeout=120)
                    if result.returncode != 0:
                        return ExtractResult(success=False, error="音频提取失败")

            if progress_callback:
                progress_callback("提取字幕...", 50)

            subtitle_path = ""
            subtitle_lines = []

            local_sub = self._find_local_subtitle(file_path)
            if local_sub:
                subtitle_path = local_sub
            else:
                extracted_sub = os.path.join(output_dir, f"{base_name}.srt")
                cmd = [self._ffmpeg, "-i", file_path, "-map", "0:s:0", "-y", extracted_sub]
                sub_result = subprocess.run(cmd, capture_output=True, timeout=30)
                if sub_result.returncode == 0 and os.path.exists(extracted_sub):
                    subtitle_path = extracted_sub

            if subtitle_path and os.path.exists(subtitle_path):
                with open(subtitle_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                fmt = SubtitleParser.detect_format(subtitle_path)
                subtitle_lines = SubtitleParser.parse(content, fmt)

            duration_ms = 0
            if self._ffprobe:
                cmd = [self._ffprobe, "-i", file_path, "-show_entries", "format=duration",
                       "-of", "json", "-v", "quiet"]
                try:
                    probe = subprocess.run(cmd, capture_output=True, timeout=10)
                    if probe.returncode == 0:
                        probe_data = json.loads(probe.stdout.decode())
                        dur = float(probe_data.get("format", {}).get("duration", 0))
                        duration_ms = int(dur * 1000)
                except Exception:
                    pass
            if duration_ms == 0:
                cmd = [self._ffmpeg, "-i", file_path, "-f", "null", "-"]
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=30)
                    output = result.stderr.decode(errors="ignore")
                    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", output)
                    if m:
                        h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)[:3])
                        duration_ms = (h * 3600 + mi * 60 + s) * 1000 + ms
                except Exception:
                    pass

            if progress_callback:
                progress_callback("完成", 100)

            return ExtractResult(
                success=True,
                title=title,
                audio_path=audio_path,
                subtitle_path=subtitle_path,
                chapters=[],
                subtitle_lines=subtitle_lines,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.error(f"MediaExtractor extract_from_file error: {e}")
            return ExtractResult(success=False, error=str(e))

    def split_audio_by_chapter(
        self,
        audio_path: str,
        chapters: List[Chapter],
        output_dir: str,
    ) -> List[str]:
        if not chapters or not os.path.exists(audio_path):
            return [audio_path] if os.path.exists(audio_path) else []

        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        ext = os.path.splitext(audio_path)[1] or ".m4a"
        output_paths = []

        for ch in chapters:
            start_sec = ch.start_ms / 1000.0
            end_sec = ch.end_ms / 1000.0 if ch.end_ms > 0 else None
            safe_title = "".join(c for c in ch.title if c.isalnum() or c in " _-").strip()
            if not safe_title:
                safe_title = f"chapter_{ch.index + 1}"
            out_path = os.path.join(output_dir, f"{base_name}_{safe_title}{ext}")

            cmd = [self._ffmpeg, "-i", audio_path, "-ss", str(start_sec)]
            if end_sec:
                cmd.extend(["-to", str(end_sec)])
            cmd.extend(["-c", "copy", "-y", out_path])

            try:
                result = subprocess.run(cmd, capture_output=True, timeout=60)
                if result.returncode == 0 and os.path.exists(out_path):
                    output_paths.append(out_path)
                else:
                    output_paths.append(audio_path)
            except Exception:
                output_paths.append(audio_path)

        return output_paths

    def _find_audio_file(self, output_dir: str, title: str, fmt: str) -> str:
        for ext in [f".{fmt}", ".m4a", ".mp3", ".ogg", ".wav", ".webm"]:
            for f in os.listdir(output_dir):
                if f.endswith(ext):
                    return os.path.join(output_dir, f)
        return ""

    def _find_subtitle_file(self, output_dir: str, title: str, lang: str) -> str:
        if not os.path.isdir(output_dir):
            logger.warning(f"_find_subtitle_file: output_dir does not exist: {output_dir}")
            return ""
        all_files = os.listdir(output_dir)
        logger.info(f"_find_subtitle_file: searching in {output_dir}, lang={lang}, files={all_files}")
        for f in all_files:
            if lang in f and any(f.endswith(e) for e in [".srt", ".ass", ".vtt"]):
                result = os.path.join(output_dir, f)
                logger.info(f"_find_subtitle_file: found with lang match: {result}")
                return result
        for f in all_files:
            if any(f.endswith(e) for e in [".srt", ".ass", ".vtt", ".lrc"]):
                result = os.path.join(output_dir, f)
                logger.info(f"_find_subtitle_file: found without lang match: {result}")
                return result
        logger.warning(f"_find_subtitle_file: no subtitle file found in {output_dir}")
        return ""

    def _find_local_subtitle(self, file_path: str) -> str:
        base = os.path.splitext(file_path)[0]
        for ext in [".srt", ".ass", ".ssa", ".vtt", ".lrc", ".SRT", ".ASS", ".VTT", ".LRC"]:
            path = base + ext
            if os.path.exists(path):
                return path
        for ext in [".srt", ".ass", ".ssa", ".vtt", ".lrc"]:
            for suffix in [".en", ".zh", ".zh-CN", ".zh-Hans", ".chi", ".eng", ".chinese", ".english"]:
                path = base + suffix + ext
                if os.path.exists(path):
                    return path
        return ""

    def _get_cookie_browser(self) -> str:
        try:
            from src.business.config_manager import ConfigManager
            cfg = ConfigManager()
            browser = cfg.get("Study", "CookieBrowser", "")
            if browser:
                return browser
        except Exception:
            pass
        return ""

    def _get_bilibili_sessdata(self) -> str:
        try:
            from src.business.config_manager import ConfigManager
            cfg = ConfigManager()
            sessdata = cfg.get("Study", "BilibiliSESSDATA", "")
            if sessdata:
                from urllib.parse import quote, unquote
                decoded = unquote(sessdata)
                if decoded != sessdata:
                    sessdata = quote(decoded, safe="")
                return sessdata
        except Exception:
            pass
        return ""

    def _get_cookie_file(self) -> str:
        try:
            from src.business.config_manager import ConfigManager
            cfg = ConfigManager()
            cookie_file = cfg.get("Study", "CookieFile", "")
            if cookie_file and os.path.exists(cookie_file):
                return cookie_file
        except Exception:
            pass
        return ""

    def _extract_bilibili_subtitle(self, url: str, output_dir: str, lang: str) -> str:
        try:
            bvid_match = re.search(r'BV[\w]+', url)
            if not bvid_match:
                logger.warning("_extract_bilibili_subtitle: no BV ID found in URL")
                return ""
            bvid = bvid_match.group(0)

            page_match = re.search(r'[?&]p=(\d+)', url)
            page_num = int(page_match.group(1)) if page_match else 1

            sessdata = self._get_bilibili_sessdata()

            api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
            req = Request(api_url)
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            req.add_header("Referer", "https://www.bilibili.com")
            if sessdata:
                req.add_header("Cookie", f"SESSDATA={sessdata}")

            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            if data.get("code") != 0:
                logger.warning(f"_extract_bilibili_subtitle: view API error: {data.get('message', '')}")
                return ""

            video_info = data.get("data", {})
            pages = video_info.get("pages", [])
            if page_num > len(pages):
                page_num = 1
            cid = pages[page_num - 1].get("cid") if pages else 0
            if not cid:
                logger.warning("_extract_bilibili_subtitle: no cid found")
                return ""

            subtitle_api = f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}"
            req2 = Request(subtitle_api)
            req2.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            req2.add_header("Referer", "https://www.bilibili.com")
            if sessdata:
                req2.add_header("Cookie", f"SESSDATA={sessdata}")

            with urlopen(req2, timeout=10) as resp2:
                sub_data = json.loads(resp2.read().decode())

            if sub_data.get("code") != 0:
                logger.warning(f"_extract_bilibili_subtitle: player API error: {sub_data.get('message', '')}")
                return ""

            subtitle_info = sub_data.get("data", {}).get("subtitle", {})
            subtitles = subtitle_info.get("subtitles", [])

            if not subtitles:
                logger.info("_extract_bilibili_subtitle: no subtitles available (may require login)")
                return ""

            logger.info(f"_extract_bilibili_subtitle: {len(subtitles)} subtitles found: {[s.get('lan') for s in subtitles]}")

            best_sub = None
            best_body = []
            for sub in subtitles:
                sub_url = sub.get("subtitle_url", "")
                if not sub_url:
                    continue
                if sub_url.startswith("//"):
                    sub_url = "https:" + sub_url
                try:
                    req3 = Request(sub_url)
                    req3.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                    req3.add_header("Referer", "https://www.bilibili.com")
                    with urlopen(req3, timeout=10) as resp3:
                        sub_content = json.loads(resp3.read().decode())
                    body = sub_content.get("body", [])
                    valid_lines = [b for b in body if b.get("content", "").strip()]
                    logger.info(f"_extract_bilibili_subtitle: lang={sub.get('lan')}, total={len(body)}, valid={len(valid_lines)}")
                    if len(valid_lines) > len(best_body):
                        best_sub = sub
                        best_body = body
                except Exception as e:
                    logger.warning(f"_extract_bilibili_subtitle: failed to download lang={sub.get('lan')}: {e}")
                    continue

            if not best_sub or not best_body:
                logger.warning("_extract_bilibili_subtitle: all subtitles empty or download failed")
                return ""

            logger.info(f"_extract_bilibili_subtitle: selected lang={best_sub.get('lan')}, lines={len(best_body)}")

            srt_path = os.path.join(output_dir, f"bilibili_subtitle_{bvid}_p{page_num}.srt")
            srt_lines = []
            for idx, item in enumerate(body):
                start_ms = int(item.get("from", 0) * 1000)
                end_ms = int(item.get("to", 0) * 1000)
                text = item.get("content", "").strip()
                if not text:
                    continue
                start_h = start_ms // 3600000
                start_m = (start_ms % 3600000) // 60000
                start_s = (start_ms % 60000) // 1000
                start_ms_val = start_ms % 1000
                end_h = end_ms // 3600000
                end_m = (end_ms % 3600000) // 60000
                end_s = (end_ms % 60000) // 1000
                end_ms_val = end_ms % 1000
                srt_lines.append(str(idx + 1))
                srt_lines.append(
                    f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms_val:03d} --> "
                    f"{end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms_val:03d}"
                )
                srt_lines.append(text)
                srt_lines.append("")

            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines))

            logger.info(f"_extract_bilibili_subtitle: saved subtitle to {srt_path} ({len(body)} lines)")
            return srt_path

        except URLError as e:
            logger.warning(f"_extract_bilibili_subtitle: network error: {e}")
            return ""
        except Exception as e:
            logger.warning(f"_extract_bilibili_subtitle: error: {e}")
            return ""
