import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional

from src.utils.logger import setup_logger

logger = setup_logger(__name__)

ECDICT_DB_NAME = "ecdict.db"


@dataclass
class DictEntry:
    word: str = ""
    phonetic: str = ""
    definition: str = ""
    translation: str = ""
    pos: str = ""
    collins: int = 0
    oxford: int = 0
    tag: str = ""
    bnc: int = 0
    frq: int = 0
    exchange: str = ""
    source: str = "offline"


def _get_ecdict_dir() -> str:
    from src.utils.constants import CACHE_DIR
    d = os.path.join(CACHE_DIR, "ecdict")
    os.makedirs(d, exist_ok=True)
    return d


def get_ecdict_db_path() -> str:
    return os.path.join(_get_ecdict_dir(), ECDICT_DB_NAME)


def is_ecdict_available() -> bool:
    return os.path.isfile(get_ecdict_db_path())


class ECDictProvider:
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
        self._local = threading.local()
        self._lemma_cache = {}
        self._initialized = True

    def _get_conn(self) -> Optional[sqlite3.Connection]:
        conn = getattr(self._local, "connection", None)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except Exception:
                self._local.connection = None

        db_path = get_ecdict_db_path()
        if not os.path.isfile(db_path):
            return None

        try:
            self._local.connection = sqlite3.connect(db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            return self._local.connection
        except Exception as e:
            logger.error(f"ECDICT connect error: {e}")
            self._local.connection = None
            return None

    def lookup(self, word: str) -> Optional[DictEntry]:
        if not word or not word.strip():
            return None

        word = word.strip().lower()
        conn = self._get_conn()
        if conn is None:
            return None

        try:
            row = conn.execute(
                "SELECT * FROM stardict WHERE word = ? COLLATE NOCASE",
                (word,)
            ).fetchone()

            if row is None:
                row = conn.execute(
                    "SELECT * FROM stardict WHERE sw = ? COLLATE NOCASE LIMIT 1",
                    (word,)
                ).fetchone()

            if row is None:
                lemma = self._find_lemma(conn, word)
                if lemma and lemma != word:
                    row = conn.execute(
                        "SELECT * FROM stardict WHERE word = ? COLLATE NOCASE",
                        (lemma,)
                    ).fetchone()

            if row is None:
                return None

            return self._row_to_entry(row)

        except Exception as e:
            logger.error(f"ECDICT lookup error for '{word}': {e}")
            return None

    def _find_lemma(self, conn: sqlite3.Connection, word: str) -> Optional[str]:
        try:
            row = conn.execute(
                "SELECT word FROM stardict WHERE exchange LIKE ? LIMIT 1",
                (f"%{word}%",)
            ).fetchone()
            if row:
                return row["word"]
        except Exception:
            pass

        if word.endswith("ing"):
            for candidate in [word[:-3], word[:-3] + "e", word[:-4] if len(word) > 4 else ""]:
                if candidate and candidate != word:
                    r = conn.execute(
                        "SELECT word FROM stardict WHERE word = ? COLLATE NOCASE",
                        (candidate,)
                    ).fetchone()
                    if r:
                        return r["word"]
        elif word.endswith("ed"):
            for candidate in [word[:-2], word[:-1], word[:-2] + "e", word[:-3] if len(word) > 3 else ""]:
                if candidate and candidate != word:
                    r = conn.execute(
                        "SELECT word FROM stardict WHERE word = ? COLLATE NOCASE",
                        (candidate,)
                    ).fetchone()
                    if r:
                        return r["word"]
        elif word.endswith("es") and not word.endswith("ies"):
            candidate = word[:-2]
            if candidate and candidate != word:
                r = conn.execute(
                    "SELECT word FROM stardict WHERE word = ? COLLATE NOCASE",
                    (candidate,)
                ).fetchone()
                if r:
                    return r["word"]
        elif word.endswith("ies"):
            candidate = word[:-3] + "y"
            if candidate != word:
                r = conn.execute(
                    "SELECT word FROM stardict WHERE word = ? COLLATE NOCASE",
                    (candidate,)
                ).fetchone()
                if r:
                    return r["word"]
        elif word.endswith("s") and not word.endswith("ss"):
            candidate = word[:-1]
            if candidate and candidate != word:
                r = conn.execute(
                    "SELECT word FROM stardict WHERE word = ? COLLATE NOCASE",
                    (candidate,)
                ).fetchone()
                if r:
                    return r["word"]
        elif word.endswith("er") or word.endswith("est"):
            base = word[:-2] if word.endswith("er") else word[:-3]
            if base and base != word:
                r = conn.execute(
                    "SELECT word FROM stardict WHERE word = ? COLLATE NOCASE",
                    (base,)
                ).fetchone()
                if r:
                    return r["word"]

        return None

    def _row_to_entry(self, row) -> DictEntry:
        return DictEntry(
            word=row["word"] if "word" in row.keys() else "",
            phonetic=row["phonetic"] if "phonetic" in row.keys() else "",
            definition=row["definition"] if "definition" in row.keys() else "",
            translation=row["translation"] if "translation" in row.keys() else "",
            pos=row["pos"] if "pos" in row.keys() else "",
            collins=int(row["collins"] or 0) if "collins" in row.keys() else 0,
            oxford=int(row["oxford"] or 0) if "oxford" in row.keys() else 0,
            tag=row["tag"] if "tag" in row.keys() else "",
            bnc=int(row["bnc"] or 0) if "bnc" in row.keys() else 0,
            frq=int(row["frq"] or 0) if "frq" in row.keys() else 0,
            exchange=row["exchange"] if "exchange" in row.keys() else "",
            source="offline",
        )

    def close(self):
        conn = getattr(self._local, "connection", None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.connection = None
