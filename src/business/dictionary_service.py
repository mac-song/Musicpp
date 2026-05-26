import threading
from collections import OrderedDict
from typing import Callable, Optional

from src.infrastructure.ecdict_provider import DictEntry, ECDictProvider, is_ecdict_available
from src.infrastructure.online_dict_provider import OnlineDictProvider
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class DictionaryService:
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
        self._ecdict = ECDictProvider()
        self._cache = OrderedDict()
        self._cache_max = 500
        self._online_enabled = True
        self._word_lookup_enabled = True
        self._initialized = True

    def set_word_lookup_enabled(self, enabled: bool):
        self._word_lookup_enabled = enabled

    def is_word_lookup_enabled(self) -> bool:
        return self._word_lookup_enabled

    def lookup(self, word: str) -> Optional[DictEntry]:
        if not word or not word.strip():
            return None

        word = word.strip().lower()

        cached = self._get_cache(word)
        if cached is not None:
            return cached

        entry = self._ecdict.lookup(word)
        if entry:
            self._put_cache(word, entry)
            return entry

        if self._online_enabled:
            online = OnlineDictProvider.lookup_any(word)
            if online:
                entry = DictEntry(
                    word=online.get("word", word),
                    phonetic=online.get("phonetic", ""),
                    translation=online.get("translation", ""),
                    definition=online.get("definition", ""),
                    pos=online.get("pos", ""),
                    source=online.get("source", "online"),
                )
                self._put_cache(word, entry)
                return entry

        self._put_cache(word, None)
        return None

    def lookup_offline_then_online(self, word: str, callback: Callable[[str, Optional[DictEntry], bool], None]):
        offline_result = self._ecdict.lookup(word)
        if offline_result:
            self._put_cache(word.strip().lower(), offline_result)
            try:
                callback(word, offline_result, False)
            except Exception:
                pass
            return

        if self._online_enabled:
            def _online_worker():
                online = OnlineDictProvider.lookup_any(word)
                if online:
                    entry = DictEntry(
                        word=online.get("word", word),
                        phonetic=online.get("phonetic", ""),
                        translation=online.get("translation", ""),
                        definition=online.get("definition", ""),
                        pos=online.get("pos", ""),
                        source=online.get("source", "online"),
                    )
                    self._put_cache(word.strip().lower(), entry)
                    try:
                        callback(word, entry, True)
                    except Exception:
                        pass
                else:
                    self._put_cache(word.strip().lower(), None)
                    try:
                        callback(word, None, True)
                    except Exception:
                        pass

            t = threading.Thread(target=_online_worker, daemon=True)
            t.start()
        else:
            self._put_cache(word.strip().lower(), None)
            try:
                callback(word, None, False)
            except Exception:
                pass

    def _get_cache(self, word: str) -> Optional[DictEntry]:
        if word in self._cache:
            self._cache.move_to_end(word)
            return self._cache[word]
        return None

    def _put_cache(self, word: str, entry: Optional[DictEntry]):
        self._cache[word] = entry
        self._cache.move_to_end(word)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)
