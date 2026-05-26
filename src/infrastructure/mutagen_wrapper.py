import os
import re
from typing import Dict, Optional, Tuple

from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.apev2 import APEv2
from mutagen.oggvorbis import OggVorbis
from mutagen.wavpack import WavPack
from mutagen.wave import WAVE
from mutagen.m4a import M4A
from mutagen.id3 import TextFrame

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

_GARBAGE_MARKERS = {
    "kuwo", "kugou", "qqmusic", "qmc", "ncm", "kgm", "vpr",
    "kgma", "tkm", "bak", "tm", "joox", "migu",
}


def _is_suspicious_metadata(title: str, artist: str) -> bool:
    if not title:
        return True
    t = title.strip().lower()
    if t in _GARBAGE_MARKERS:
        return True
    if artist and t == artist.strip().lower() and len(t) <= 6:
        return True
    if len(t) <= 2 and not any("\u4e00" <= c <= "\u9fff" for c in t):
        return True
    return False


def _extract_from_filename(file_path: str) -> Tuple[str, str]:
    basename = os.path.splitext(os.path.basename(file_path))[0]
    basename = re.sub(r"^\d+[\.\s\-—–]+", "", basename).strip()
    for sep in (" - ", "—", "–", "-"):
        if sep in basename:
            parts = basename.split(sep, 1)
            left = parts[0].strip()
            right = parts[1].strip()
            if not left or not right:
                continue
            if any("\u4e00" <= c <= "\u9fff" for c in right) or any(c.isalpha() for c in right):
                return left, right
            return basename, ""
    return basename, ""


def _fix_misencoded_tag(text: str) -> str:
    try:
        raw = text.encode("latin-1")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    for encoding in ("gbk", "gb2312", "gb18030", "big5", "utf-8"):
        try:
            decoded = raw.decode(encoding)
            if decoded != text:
                return decoded
        except (UnicodeDecodeError, LookupError):
            continue
    return text


def _decode_tag(value):
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        value = value[0]
    if isinstance(value, bytes):
        for encoding in ("utf-8", "gbk", "gb2312", "big5", "utf-16", "utf-16-le", "latin-1"):
            try:
                return value.decode(encoding).strip()
            except (UnicodeDecodeError, AttributeError):
                continue
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, TextFrame):
        encoding = getattr(value, "encoding", None)
        text = str(value.text[0]) if value.text else ""
        if encoding is not None and int(encoding) == 0 and text:
            text = _fix_misencoded_tag(text)
        return text.strip()
    return str(value).strip()


class MutagenWrapper:
    @staticmethod
    def read_metadata(file_path: str) -> Dict[str, any]:
        metadata = {
            "title": "",
            "artist": "",
            "album": "",
            "duration": 0,
            "bitrate": 0,
            "format": "",
            "cover_path": None,
            "path": file_path,
        }

        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                return metadata

            ext = os.path.splitext(file_path)[1].lower()
            metadata["format"] = ext[1:] if ext else ""

            audio = None

            if ext == ".mp3":
                audio = MP3(file_path)
            elif ext == ".flac":
                audio = FLAC(file_path)
            elif ext == ".ape":
                audio = APEv2(file_path)
            elif ext == ".ogg":
                audio = OggVorbis(file_path)
            elif ext == ".wv":
                audio = WavPack(file_path)
            elif ext == ".wav":
                audio = WAVE(file_path)
            elif ext in [".m4a", ".aac"]:
                audio = M4A(file_path)

            if audio is None:
                logger.warning(f"Unsupported format: {ext}")
                metadata["title"] = os.path.splitext(os.path.basename(file_path))[0]
                metadata["artist"] = "Unknown Artist"
                return metadata

            if hasattr(audio, "info"):
                metadata["duration"] = int(audio.info.length)
                metadata["bitrate"] = getattr(audio.info, "bitrate", 0)

            if hasattr(audio, "tags") and audio.tags:
                tags = audio.tags

                title = ""
                artist = ""
                album = ""

                if hasattr(tags, "get"):
                    for key in ["TIT2", "TITLE", "\u6807\u9898"]:
                        val = tags.get(key)
                        if val:
                            title = _decode_tag(val)
                            if title:
                                break

                    for key in ["TPE1", "ARTIST", "\u827a\u672f\u5bb6", "\u6b4c\u624b"]:
                        val = tags.get(key)
                        if val:
                            artist = _decode_tag(val)
                            if artist:
                                break

                    for key in ["TALB", "ALBUM", "\u4e13\u8f91"]:
                        val = tags.get(key)
                        if val:
                            album = _decode_tag(val)
                            if album:
                                break

                metadata["title"] = title if title else os.path.splitext(os.path.basename(file_path))[0]
                metadata["artist"] = artist if artist else "Unknown Artist"
                metadata["album"] = album

                if _is_suspicious_metadata(metadata["title"], metadata["artist"]):
                    fn_title, fn_artist = _extract_from_filename(file_path)
                    if fn_title:
                        logger.info(f"Suspicious metadata '{metadata['title']}'/'{metadata['artist']}', using filename: '{fn_title}'/'{fn_artist}'")
                        metadata["title"] = fn_title
                        metadata["artist"] = fn_artist if fn_artist else "Unknown Artist"
                        metadata["album"] = ""

            if not metadata["title"]:
                metadata["title"] = os.path.splitext(os.path.basename(file_path))[0]

            return metadata

        except Exception as e:
            logger.error(f"Error reading metadata from {file_path}: {e}")
            metadata["title"] = os.path.splitext(os.path.basename(file_path))[0]
            metadata["artist"] = "Unknown Artist"
            return metadata

