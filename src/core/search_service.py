import re
import threading
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from src.plugins.plugin_manager import PluginManager
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class SearchService(QObject):
    search_completed = Signal(list)
    search_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plugin_manager = PluginManager()
        self._search_lock = threading.Lock()

    def search(self, keyword: str, page: int = 1, limit: int = 20, plugin_ids: list = None):
        if not keyword or not keyword.strip():
            self.search_error.emit("搜索关键词不能为空")
            return
        with self._search_lock:
            thread = threading.Thread(
                target=self._do_search,
                args=(keyword, page, limit, plugin_ids),
                daemon=True
            )
            thread.start()

    def _do_search(self, keyword, page, limit, plugin_ids):
        try:
            if plugin_ids:
                plugins = {
                    pid: self._plugin_manager.get_plugin(pid)
                    for pid in plugin_ids
                }
                plugins = {k: v for k, v in plugins.items() if v is not None}
            else:
                plugins = self._plugin_manager.get_all_plugins()

            if not plugins:
                self.search_error.emit("没有可用的搜索插件")
                return

            results_map = {}
            events = {}

            def _search_plugin(plugin_name, plugin_instance):
                try:
                    plugin_results = plugin_instance.search(keyword, page, limit)
                    if isinstance(plugin_results, dict):
                        results_map[plugin_name] = plugin_results.get("list", [])
                    elif isinstance(plugin_results, list):
                        results_map[plugin_name] = plugin_results
                    else:
                        results_map[plugin_name] = []
                except Exception as e:
                    logger.warning(f"Plugin {plugin_name} search failed: {e}")
                    results_map[plugin_name] = []
                events[plugin_name].set()

            for name, plugin in plugins.items():
                event = threading.Event()
                events[name] = event
                t = threading.Thread(
                    target=_search_plugin,
                    args=(name, plugin),
                    daemon=True
                )
                t.start()

            for name, event in events.items():
                event.wait(timeout=10)

            all_results = []
            for name, plugin in plugins.items():
                plugin_results = results_map.get(name, [])
                for result in plugin_results:
                    result["pluginId"] = name
                    result["source"] = name
                all_results.extend(plugin_results)

            logger.info(f"Raw results before processing: {len(all_results)} songs")
            if all_results:
                logger.info(f"  First result keys: {list(all_results[0].keys())}")
                logger.info(f"  First result: {all_results[0]}")

            for result in all_results:
                result_source = result.get("source")
                result_plugin_id = result.get("pluginId")
                if not result_plugin_id:
                    if result_source:
                        result["pluginId"] = str(result_source)
                    else:
                        result["pluginId"] = ""
                if "sources" not in result or not any(s for s in result.get("sources", []) if s):
                    sources_list = []
                    if result_source:
                        sources_list.append(str(result_source))
                    plugin_id = result.get("pluginId")
                    if plugin_id and str(plugin_id) not in sources_list:
                        sources_list.append(str(plugin_id))
                    if sources_list:
                        result["sources"] = sources_list

            aggregated = self._aggregate_results(all_results)

            logger.info(f"Search results: {len(aggregated)} songs")
            for i, r in enumerate(aggregated[:3]):
                logger.info(f"  Song {i}: title={r.get('title')}, sources={r.get('sources')}, source={r.get('source')}, pluginId={r.get('pluginId')}")

            for result in aggregated:
                if not result.get("pluginId"):
                    sources = result.get("sources", [])
                    valid_sources = [s for s in sources if s]
                    if valid_sources:
                        result["pluginId"] = valid_sources[0]
                    elif result.get("source"):
                        result["pluginId"] = result["source"]

            self.search_completed.emit(aggregated)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            self.search_error.emit(str(e))

    def _aggregate_results(self, results: list) -> list:
        if not results:
            return []

        logger.info(f"_aggregate_results called with {len(results)} songs")
        for i, r in enumerate(results[:3]):
            logger.info(f"  Input {i}: title={r.get('title')}, sources={r.get('sources')}, source={r.get('source')}, pluginId={r.get('pluginId')}")

        aggregated = []
        for song in results:
            merged = False
            for existing in aggregated:
                if self._is_duplicate(song, existing):
                    existing_sources = existing.get("sources", [])
                    new_sources = song.get("sources", [])
                    if existing.get("pluginId") and existing["pluginId"] not in existing_sources:
                        existing_sources.append(existing["pluginId"])
                    if song.get("pluginId") and song["pluginId"] not in new_sources:
                        new_sources.append(song["pluginId"])
                    merged_sources = list(dict.fromkeys(existing_sources + new_sources))
                    merged_sources = [s for s in merged_sources if s]
                    existing["sources"] = merged_sources

                    existing_qualities = existing.get("qualities", [])
                    new_qualities = song.get("qualities", [])
                    seen_levels = {q.get("level") for q in existing_qualities}
                    for q in new_qualities:
                        if q.get("level") not in seen_levels:
                            existing_qualities.append(q)
                            seen_levels.add(q.get("level"))
                    existing["qualities"] = existing_qualities

                    if not existing.get("cover") and song.get("cover"):
                        existing["cover"] = song["cover"]

                    merged = True
                    break

            if not merged:
                song_copy = dict(song)
                if "sources" not in song_copy or not any(song_copy.get("sources", [])):
                    plugin_id = song_copy.get("pluginId", "")
                    song_copy["sources"] = [plugin_id] if plugin_id else []
                if "qualities" not in song_copy:
                    song_copy["qualities"] = []
                aggregated.append(song_copy)

        logger.info(f"_aggregate_results output: {len(aggregated)} songs")
        for i, r in enumerate(aggregated[:3]):
            logger.info(f"  Output {i}: title={r.get('title')}, sources={r.get('sources')}, source={r.get('source')}, pluginId={r.get('pluginId')}")

        return aggregated

    def _is_duplicate(self, song1: dict, song2: dict) -> bool:
        title1 = self._normalize_title(song1.get("title", ""))
        title2 = self._normalize_title(song2.get("title", ""))

        if title1 != title2:
            return False

        artist1 = self._normalize_artist(song1.get("artist", ""))
        artist2 = self._normalize_artist(song2.get("artist", ""))

        if not (artist1 in artist2 or artist2 in artist1):
            return False

        duration1 = song1.get("duration", 0) or 0
        duration2 = song2.get("duration", 0) or 0

        if duration1 > 0 and duration2 > 0:
            if abs(duration1 - duration2) > 5:
                return False

        return True

    @staticmethod
    def _normalize_title(title: str) -> str:
        title = re.sub(r'[\s\W]+', '', title).lower()
        return title

    @staticmethod
    def _normalize_artist(artist: str) -> str:
        artist = re.sub(r'\s+', '', artist).lower()
        return artist
