import csv
import io
import json
import os
import re
from typing import List, Optional

from src.utils.constants import SUPPORTED_AUDIO_FORMATS, PLAYLIST_FORMATS
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def parse_playlist(file_path: str) -> List[str]:
    paths = []
    playlist_dir = os.path.dirname(os.path.abspath(file_path))

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read playlist {file_path}: {e}")
            return []

    ext_inf = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            parts = line[8:].split(",", 1)
            if len(parts) == 2:
                try:
                    duration = int(parts[0].strip())
                except ValueError:
                    duration = -1
                title = parts[1].strip()
                ext_inf = {"title": title, "duration": duration}
            continue
        if line.startswith("#"):
            continue

        entry = line
        if not _is_url(entry):
            if not os.path.isabs(entry):
                entry = os.path.join(playlist_dir, entry)
            entry = os.path.normpath(entry)

        if _is_url(entry) or os.path.isfile(entry):
            paths.append(entry)
        else:
            ext = os.path.splitext(entry)[1].lower()
            if ext in SUPPORTED_AUDIO_FORMATS:
                logger.debug(f"Playlist entry not found, skipping: {entry}")

    return paths


def parse_playlist_with_meta(file_path: str) -> List[dict]:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".json":
        return _parse_json(file_path)
    if ext == ".csv":
        return _parse_csv(file_path)
    if ext in (".txt",):
        return _parse_text(file_path)
    return _parse_m3u_with_meta(file_path)


def is_playlist_file(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext in PLAYLIST_FORMATS


def is_importable_file(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext in (".m3u", ".m3u8", ".json", ".csv", ".txt")


def _is_url(path: str) -> bool:
    return path.startswith(("http://", "https://", "ftp://"))


def _parse_m3u_with_meta(file_path: str) -> List[dict]:
    results = []
    playlist_dir = os.path.dirname(os.path.abspath(file_path))

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read playlist {file_path}: {e}")
            return []

    ext_inf = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            parts = line[8:].split(",", 1)
            if len(parts) == 2:
                try:
                    duration = int(parts[0].strip())
                except ValueError:
                    duration = -1
                title_artist = parts[1].strip()
                title, artist = _split_title_artist(title_artist)
                ext_inf = {"title": title, "artist": artist, "duration": duration}
            continue
        if line.startswith("#"):
            continue

        entry = line
        is_url = _is_url(entry)
        if not is_url:
            if not os.path.isabs(entry):
                entry = os.path.join(playlist_dir, entry)
            entry = os.path.normpath(entry)

        if is_url or os.path.isfile(entry):
            meta = {
                "path": entry,
                "title": ext_inf.get("title", os.path.splitext(os.path.basename(entry))[0]),
                "artist": ext_inf.get("artist", ""),
                "album": ext_inf.get("album", ""),
                "duration": ext_inf.get("duration", -1),
                "format": os.path.splitext(entry)[1].lstrip("."),
                "is_url": is_url,
            }
            results.append(meta)
            ext_inf = {}
        else:
            ext_inf = {}

    return results


def _parse_json(file_path: str) -> List[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse JSON playlist {file_path}: {e}")
        return []

    songs = data if isinstance(data, list) else data.get("songs", data.get("tracks", []))
    results = []
    for song in songs:
        meta = {
            "title": song.get("title", song.get("name", "")),
            "artist": song.get("artist", song.get("singer", "")),
            "album": song.get("album", song.get("albumName", "")),
            "duration": song.get("duration", -1),
            "path": song.get("path", song.get("url", song.get("_play_url", ""))),
            "format": song.get("format", ""),
            "is_url": _is_url(song.get("path", song.get("url", song.get("_play_url", "")))),
        }
        if song.get("pluginId"):
            meta["pluginId"] = song["pluginId"]
        if song.get("id"):
            meta["id"] = str(song["id"])
        if song.get("source"):
            meta["source"] = song["source"]
        if song.get("cover"):
            meta["cover"] = song["cover"]
        if meta["title"]:
            results.append(meta)
    return results


def _parse_csv(file_path: str) -> List[dict]:
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Failed to read CSV playlist {file_path}: {e}")
        return []

    sniffer_sample = content[:2048]
    try:
        dialect = csv.Sniffer().sniff(sniffer_sample)
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    results = []
    for row in reader:
        title = _csv_get(row, ["title", "Title", "TITLE", "name", "Name", "歌曲", "歌名"])
        artist = _csv_get(row, ["artist", "Artist", "ARTIST", "singer", "Singer", "歌手", "艺术家"])
        album = _csv_get(row, ["album", "Album", "ALBUM", "专辑"])
        duration_str = _csv_get(row, ["duration", "Duration", "DURATION", "时长"])
        path = _csv_get(row, ["path", "Path", "PATH", "url", "URL", "路径", "地址"])

        try:
            duration = int(float(duration_str)) if duration_str else -1
        except (ValueError, TypeError):
            duration = -1

        if title:
            meta = {
                "title": title.strip(),
                "artist": (artist or "").strip(),
                "album": (album or "").strip(),
                "duration": duration,
                "path": (path or "").strip(),
                "format": "",
                "is_url": _is_url(path) if path else False,
            }
            results.append(meta)
    return results


def _parse_text(file_path: str) -> List[dict]:
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Failed to read text playlist {file_path}: {e}")
        return []

    results = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        title, artist = _split_title_artist(line)
        meta = {
            "title": title,
            "artist": artist,
            "album": "",
            "duration": -1,
            "path": "",
            "format": "",
            "is_url": False,
        }
        if title:
            results.append(meta)
    return results


def _csv_get(row: dict, keys: list) -> str:
    for key in keys:
        if key in row and row[key]:
            return row[key]
    return ""


def _split_title_artist(text: str) -> tuple:
    text = text.strip()
    # 去掉开头的序号前缀，如 "1、", "2. ", "3 - " 等
    text = re.sub(r'^\d+[、.．\-–—\s]+', '', text).strip()
    for sep in [" - ", " — ", " – ", "-", "—", "–"]:
        if sep in text:
            parts = text.split(sep, 1)
            left = parts[0].strip()
            right = parts[1].strip()
            if _looks_like_artist(left):
                return right, left
            return left, right
    return text, ""


def _looks_like_artist(text: str) -> bool:
    if not text:
        return False
    text = text.strip()
    # 常见的英文歌手名模式
    artist_indicators = re.compile(
        r'^[A-Z][a-z]+(\s[A-Z][a-z]+)*$|'
        r'^[A-Z]{2,5}$'
    )
    return bool(artist_indicators.search(text))


def save_playlist(file_path: str, entries: List[str]) -> bool:
    try:
        playlist_dir = os.path.dirname(os.path.abspath(file_path))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for entry in entries:
                if _is_url(entry):
                    f.write(f"{entry}\n")
                else:
                    rel = os.path.relpath(entry, playlist_dir)
                    f.write(f"{rel}\n")
        return True
    except Exception as e:
        logger.error(f"Failed to save playlist {file_path}: {e}")
        return False


def save_playlist_with_meta(file_path: str, songs: List[dict]) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".json":
        return _save_json(file_path, songs)
    if ext == ".csv":
        return _save_csv(file_path, songs)
    if ext == ".txt":
        return _save_text(file_path, songs)
    return _save_m3u_with_meta(file_path, songs)


def _save_m3u_with_meta(file_path: str, songs: List[dict]) -> bool:
    try:
        playlist_dir = os.path.dirname(os.path.abspath(file_path))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for song in songs:
                title = song.get("title", "")
                artist = song.get("artist", "")
                duration = song.get("duration", -1)
                if isinstance(duration, (int, float)) and duration > 0:
                    dur_str = str(int(duration))
                else:
                    dur_str = "-1"
                display = f"{artist} - {title}" if artist else title
                f.write(f"#EXTINF:{dur_str},{display}\n")
                play_url = song.get("_play_url", song.get("play_url", ""))
                path = song.get("path", "")
                entry = play_url or path
                if entry and _is_url(entry):
                    f.write(f"{entry}\n")
                elif path and os.path.isfile(path):
                    rel = os.path.relpath(path, playlist_dir)
                    f.write(f"{rel}\n")
                else:
                    keyword = f"{artist} {title}".strip() if artist else title
                    f.write(f"# SEARCH: {keyword}\n")
        return True
    except Exception as e:
        logger.error(f"Failed to save M3U playlist {file_path}: {e}")
        return False


def _save_json(file_path: str, songs: List[dict]) -> bool:
    try:
        export_songs = []
        for song in songs:
            s = {
                "title": song.get("title", ""),
                "artist": song.get("artist", ""),
                "album": song.get("album", ""),
                "duration": song.get("duration", 0),
                "id": song.get("id", ""),
                "pluginId": song.get("pluginId", ""),
                "source": song.get("source", ""),
                "cover": song.get("cover", ""),
                "hash": song.get("hash", ""),
                "hash_320": song.get("hash_320", ""),
                "hash_sq": song.get("hash_sq", ""),
                "_play_url": song.get("_play_url", song.get("play_url", "")),
                "match_status": song.get("match_status", ""),
                "quality": song.get("quality", ""),
            }
            path = song.get("path", "")
            if path:
                s["path"] = path
            export_songs.append(s)
        data = {
            "version": 1,
            "songs": export_songs,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save JSON playlist {file_path}: {e}")
        return False


def _save_csv(file_path: str, songs: List[dict]) -> bool:
    try:
        with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Artist", "Album", "Duration", "Source", "URL"])
            for song in songs:
                title = song.get("title", "")
                artist = song.get("artist", "")
                album = song.get("album", "")
                duration = song.get("duration", 0)
                source = song.get("source", song.get("pluginId", ""))
                url = song.get("_play_url", song.get("play_url", song.get("path", "")))
                writer.writerow([title, artist, album, duration, source, url])
        return True
    except Exception as e:
        logger.error(f"Failed to save CSV playlist {file_path}: {e}")
        return False


def _save_text(file_path: str, songs: List[dict]) -> bool:
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for song in songs:
                title = song.get("title", "")
                artist = song.get("artist", "")
                if artist:
                    f.write(f"{artist} - {title}\n")
                else:
                    f.write(f"{title}\n")
        return True
    except Exception as e:
        logger.error(f"Failed to save text playlist {file_path}: {e}")
        return False
