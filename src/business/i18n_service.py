import threading
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.core.database_service import DatabaseService
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class I18nService(QObject):
    _instance = None
    _lock = threading.Lock()

    locale_changed = Signal(str)

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
        super().__init__()
        self._locale = "en_US"
        self._strings: dict[str, str] = {}
        self._initialized = True

    def init(self, locale: str = "en_US"):
        self._locale = locale
        self._ensure_db_table()
        self._load_from_db()
        if not self._strings:
            self._seed_to_db()
            self._load_from_db()
        logger.info(f"I18n initialized: locale={self._locale}, strings={len(self._strings)}")

    def t(self, key: str) -> str:
        return self._strings.get(key, key)

    def tf(self, key: str, **kwargs) -> str:
        template = self._strings.get(key, key)
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template

    def set_locale(self, locale: str):
        if locale == self._locale:
            return
        old = self._locale
        self._locale = locale
        self._strings.clear()
        self._load_from_db()
        if not self._strings:
            self._seed_to_db()
            self._load_from_db()
        logger.info(f"I18n locale changed: {old} -> {locale}, strings={len(self._strings)}")
        self.locale_changed.emit(locale)

    @property
    def locale(self) -> str:
        return self._locale

    def _ensure_db_table(self):
        db = DatabaseService()
        conn = db._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS i18n (
                locale TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (locale, key)
            )
        """)
        conn.commit()

    def _load_from_db(self):
        db = DatabaseService()
        conn = db._get_connection()
        rows = conn.execute(
            "SELECT key, value FROM i18n WHERE locale = ?",
            (self._locale,),
        ).fetchall()
        self._strings = {row[0]: row[1] for row in rows}

    def _seed_to_db(self):
        from src.business.i18n_data import LANG_PACKS
        pack = LANG_PACKS.get(self._locale, {})
        if not pack:
            return
        db = DatabaseService()
        conn = db._get_connection()
        conn.execute("DELETE FROM i18n WHERE locale = ?", (self._locale,))
        conn.executemany(
            "INSERT OR IGNORE INTO i18n (locale, key, value) VALUES (?, ?, ?)",
            [(self._locale, k, v) for k, v in pack.items()],
        )
        conn.commit()
        logger.info(f"I18n seeded {len(pack)} strings for locale={self._locale}")

    def refresh_from_code(self):
        from src.business.i18n_data import LANG_PACKS, LANG_VERSION
        db = DatabaseService()
        conn = db._get_connection()
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'i18n_version'"
        ).fetchone()
        if row and row[0] == str(LANG_VERSION):
            return
        for locale, pack in LANG_PACKS.items():
            for k, v in pack.items():
                conn.execute(
                    "INSERT OR IGNORE INTO i18n (locale, key, value) VALUES (?, ?, ?)",
                    (locale, k, v),
                )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value, type) VALUES (?, ?, ?)",
            ("i18n_version", str(LANG_VERSION), "string"),
        )
        conn.commit()
        self._strings.clear()
        self._load_from_db()
        logger.info(f"I18n refreshed to version {LANG_VERSION}")


I18n = I18nService()
