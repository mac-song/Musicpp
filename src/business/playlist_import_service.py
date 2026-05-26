import re
import threading
import time
from typing import Callable, Dict, List, Optional

from src.plugins.plugin_manager import PluginManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class PlaylistImportService:
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
        self._initialized = True

    def _get_plugin_manager(self) -> PluginManager:
        return PluginManager()

    def get_available_plugins(self) -> Dict[str, str]:
        pm = self._get_plugin_manager()
        plugins = pm.get_all_plugins()
        return {pid: plugin.name for pid, plugin in plugins.items()}

    def match_song(self, title: str, artist: str = "", plugin_id: str = "") -> Optional[dict]:
        keyword = f"{artist} {title}".strip() if artist else title
        if not keyword:
            logger.warning("match_song: keyword is empty, skip")
            return None

        try:
            pm = self._get_plugin_manager()
            if plugin_id:
                plugin = pm.get_plugin(plugin_id)
                if not plugin:
                    logger.warning(f"match_song: plugin '{plugin_id}' not found or not enabled")
                    return None
                plugins = {plugin_id: plugin}
            else:
                plugins = pm.get_all_plugins()

            if not plugins:
                logger.warning(f"match_song: no enabled plugins available for '{keyword}'")
                return None

            logger.info(f"match_song: searching '{keyword}' in plugin(s): {list(plugins.keys())}")

            best_match = None

            for pid, plugin in plugins.items():
                try:
                    result = plugin.search(keyword, page=1, limit=5)
                    candidates = []
                    if isinstance(result, dict):
                        candidates = result.get("list", [])
                    elif isinstance(result, list):
                        candidates = result

                    logger.info(f"match_song: plugin '{pid}' returned {len(candidates)} candidate(s) for '{keyword}'")

                    for candidate in candidates:
                        matched, reason = self._is_match(candidate, title, artist)
                        if matched:
                            logger.info(
                                f"match_song: candidate matched - "
                                f"title='{candidate.get('title', '')}' "
                                f"artist='{candidate.get('artist', '')}' "
                                f"from plugin '{pid}'"
                            )
                            best_match = self._build_matched_song(candidate, pid)
                            break
                        else:
                            logger.debug(
                                f"match_song: candidate NOT matched - "
                                f"cand_title='{_normalize(candidate.get('title', candidate.get('name', '')))}' "
                                f"tgt_title='{_normalize(title)}' "
                                f"cand_artist='{_normalize(candidate.get('artist', candidate.get('singer', '')))}' "
                                f"tgt_artist='{_normalize(artist)}' "
                                f"reason={reason}"
                            )
                except Exception as e:
                    logger.warning(f"match_song: plugin '{pid}' search failed for '{keyword}': {e}")
                    continue

            if not best_match and artist and artist.strip():
                logger.info(f"match_song: no match with 'artist title', fallback to title-only search '{title}'")
                for pid, plugin in plugins.items():
                    try:
                        result = plugin.search(title, page=1, limit=5)
                        candidates = []
                        if isinstance(result, dict):
                            candidates = result.get("list", [])
                        elif isinstance(result, list):
                            candidates = result

                        logger.info(f"match_song: fallback plugin '{pid}' returned {len(candidates)} candidate(s) for '{title}'")

                        for candidate in candidates:
                            matched, reason = self._is_match(candidate, title, artist)
                            if matched:
                                logger.info(
                                    f"match_song: fallback candidate matched - "
                                    f"title='{candidate.get('title', '')}' "
                                    f"artist='{candidate.get('artist', '')}' "
                                    f"from plugin '{pid}'"
                                )
                                best_match = self._build_matched_song(candidate, pid)
                                break
                    except Exception as e:
                        logger.warning(f"match_song: fallback plugin '{pid}' search failed for '{title}': {e}")
                        continue

            if best_match:
                logger.info(f"match_song: matched '{keyword}' -> '{best_match.get('title', '')}' from '{best_match.get('pluginId', '')}'")
            else:
                logger.warning(f"match_song: no match found for '{keyword}' (title={title!r}, artist={artist!r})")

            return best_match

        except Exception as e:
            logger.error(f"match_song: failed for '{keyword}': {e}")
            return None

    def match_songs_batch(
        self,
        songs: List[dict],
        plugin_id: str = "",
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> List[dict]:
        total = len(songs)
        results = []
        matched_count = 0

        logger.info(f"match_songs_batch: starting batch match for {total} song(s), plugin='{plugin_id or 'all'}'")

        for i, song in enumerate(songs):
            if cancel_check and cancel_check():
                logger.info("match_songs_batch: cancelled by user")
                break

            title = song.get("title", "")
            artist = song.get("artist", "")

            if progress_callback:
                progress_callback(i, total, f"{artist} - {title}" if artist else title)

            matched = self.match_song(title, artist, plugin_id=plugin_id)

            if matched:
                matched["match_status"] = "matched"
                results.append(matched)
                matched_count += 1
            else:
                song["match_status"] = "unmatched"
                results.append(song)

            time.sleep(0.3)

        logger.info(f"match_songs_batch: done - {matched_count}/{total} matched")

        if progress_callback:
            progress_callback(total, total, "")

        return results

    def get_play_url(self, song: dict, quality: str = "") -> Optional[str]:
        plugin_id = song.get("pluginId", "")
        song_id = song.get("id") or song.get("hash") or song.get("songmid", "")

        if not plugin_id or not song_id:
            return None

        pm = self._get_plugin_manager()
        plugin = pm.get_plugin(plugin_id)
        if not plugin:
            return None

        try:
            url_info = plugin.get_song_url(song_id, quality or "320k")
            if not url_info:
                return None

            url = url_info if isinstance(url_info, str) else url_info.get("url", "")
            is_local = url_info.get("is_local", False) if isinstance(url_info, dict) else False

            if url and (url.startswith("http") or is_local):
                song["_play_url"] = url
                song["_is_local"] = is_local
                headers = url_info.get("headers", {}) if isinstance(url_info, dict) else {}
                if headers:
                    song["headers"] = headers
                return url

        except Exception as e:
            logger.warning(f"Get play URL failed for {song_id}: {e}")

        return None

    def get_play_urls_batch(
        self,
        songs: List[dict],
        count: int = 3,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[dict]:
        fetched = 0
        for i, song in enumerate(songs):
            if song.get("match_status") != "matched":
                continue
            if song.get("_play_url"):
                fetched += 1
                continue

            if fetched >= count:
                break

            url = self.get_play_url(song)
            if url:
                fetched += 1

            if progress_callback:
                progress_callback(i, len(songs))

            time.sleep(0.2)

        return songs

    def rematch_song(self, song: dict, plugin_id: str = "") -> Optional[dict]:
        title = song.get("title", "")
        artist = song.get("artist", "")
        matched = self.match_song(title, artist, plugin_id=plugin_id)
        if matched:
            matched["match_status"] = "matched"
            return matched
        song["match_status"] = "unmatched"
        return song

    def _is_match(self, candidate: dict, target_title: str, target_artist: str) -> tuple:
        cand_title = _normalize(candidate.get("title", candidate.get("name", "")))
        tgt_title = _normalize(target_title)
        if not tgt_title or not cand_title:
            return False, f"empty title: cand={cand_title!r} tgt={tgt_title!r}"
        
        # 更宽松的标题匹配：只要目标标题是候选标题的子串即可匹配
        title_matched = tgt_title in cand_title
        if not title_matched:
            return False, f"title mismatch: cand={cand_title!r} tgt={tgt_title!r}"

        if not target_artist:
            return True, ""
        
        cand_artist = _normalize(candidate.get("artist", candidate.get("singer", "")))
        tgt_artist = _normalize(target_artist)
        
        if tgt_artist and cand_artist:
            # 歌手匹配也宽松：子串匹配
            if tgt_artist not in cand_artist and cand_artist not in tgt_artist:
                # 如果标题完全一致，就算歌手不一样也接受
                if tgt_title == cand_title:
                    logger.debug(f"Title exact match, accept even artist mismatch: {target_title}")
                    return True, ""
                else:
                    return False, f"artist mismatch: cand={cand_artist!r} tgt={tgt_artist!r}"

        return True, ""

    def _build_matched_song(self, candidate: dict, plugin_id: str) -> dict:
        song_id = candidate.get("id") or candidate.get("hash") or candidate.get("songmid", "")
        return {
            "id": str(song_id),
            "title": candidate.get("title", candidate.get("name", "")),
            "artist": candidate.get("artist", candidate.get("singer", "")),
            "album": candidate.get("album", candidate.get("albumName", "")),
            "duration": candidate.get("duration", 0),
            "pluginId": plugin_id,
            "source": candidate.get("source", plugin_id),
            "cover": candidate.get("cover", candidate.get("img", "")),
            "hash": candidate.get("hash", ""),
            "hash_320": candidate.get("hash_320", candidate.get("320hash", "")),
            "hash_sq": candidate.get("hash_sq", candidate.get("sqhash", "")),
            "qualities": candidate.get("qualities", []),
        }


def _normalize(text: str) -> str:
    text = re.sub(r'[\s\W]+', '', text).lower().strip()
    return text
