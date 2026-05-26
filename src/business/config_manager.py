import configparser
import json
import os
import threading
from typing import Any, Dict, List, Optional

from src.core.database_service import DatabaseService
from src.core.event_bus import EventBus
from src.utils.constants import CONFIG_PATH, EVENT_CONFIG_UPDATED
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConfigManager:
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
        self._db = DatabaseService()
        self._event_bus = EventBus()
        self._config_path = CONFIG_PATH
        self._ini_parser = configparser.ConfigParser(interpolation=None, strict=False)
        self._ini_parser.optionxform = str
        self._defaults = self._get_default_config()
        self._initialized = True
        self._load_config()

    def _get_default_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            "General": {
                "Language": "zh-CN",
                "OnlineMode": False,
            },
            "Lyric": {
                "DefaultSource": "lrclib,netease",
                "SavePath": "{song_path}",
                "FontSize": 16,
                "ActiveColor": "#32c864",
                "InactiveColor": "#a0a0a0",
                "AutoDownloadOnPlay": True,
                "OverwriteExisting": False,
                "MatchTolerance": 0,
            },
            "Playback": {
                "DefaultPlayMode": 0,
                "AutoPlay": False,
                "ResumePosition": True,
                "RewindStep": 15,
                "ForwardStep": 15,
                "ResumeOffset": 500,
                "DefaultVolume": 80,
                "WheelVolume": True,
                "ExitOnListEnd": False,
                "ExitAfterTrack": False,
            },
            "Appearance": {
                "Theme": 0,
                "ThemeName": "Midnight Blue",
                "Language": 0,
                "AlwaysOnTop": True,
                "MinimizeToTray": False,
                "ShowGrid": False,
                "NaturalSort": True,
                "ShowCover": True,
            },
            "Network": {
                "ProxyType": 0,
                "ProxyAddr": "127.0.0.1",
                "ProxyPort": 7890,
                "Timeout": 30,
                "Retry": 3,
            },
            "Mini": {
                "FontSize": 22,
                "BgColor": "#1a1a2e",
                "BgOpacity": 80,
            },
            "OnlineMusic": {
                "DefaultPlugin": "netease,qq,kugou",
                "DefaultQuality": "320k",
                "DownloadPath": os.path.join(os.path.expanduser("~"), "Music"),
                "ConcurrentDownload": 3,
            },
            "Shortcuts": {
                "PlayPause": "Ctrl+P",
                "Stop": "Ctrl+S",
                "PrevTrack": "Ctrl+Left",
                "NextTrack": "Ctrl+Right",
                "SeekBackward": "Left",
                "SeekForward": "Right",
                "VolumeUp": "Up",
                "VolumeDown": "Down",
                "ToggleLyric": "Ctrl+L",
                "ToggleSource": "Ctrl+T",
                "ToggleMini": "Ctrl+M",
                "ToggleSettings": "Ctrl+,",
                "OpenFile": "Ctrl+O",
            },
        }

    def _load_config(self) -> None:
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)

        if os.path.exists(self._config_path):
            try:
                self._ini_parser.read(self._config_path, encoding="utf-8")
                self._migrate_key_case()
                logger.info(f"Loaded config from {self._config_path}")
            except Exception as e:
                logger.error(f"Error loading config: {e}")
                self._create_default_config()
        else:
            self._create_default_config()

        self._sync_to_database()

    def _migrate_key_case(self) -> None:
        snake_to_pascal = {
            "auto_download_on_play": "AutoDownloadOnPlay",
            "overwrite_existing": "OverwriteExisting",
            "match_tolerance": "MatchTolerance",
            "font_size": "FontSize",
            "active_color": "ActiveColor",
            "inactive_color": "InactiveColor",
            "default_play_mode": "DefaultPlayMode",
            "auto_play": "AutoPlay",
            "resume_position": "ResumePosition",
            "rewind_step": "RewindStep",
            "forward_step": "ForwardStep",
            "resume_offset": "ResumeOffset",
            "default_volume": "DefaultVolume",
            "wheel_volume": "WheelVolume",
            "exit_on_list_end": "ExitOnListEnd",
            "exit_after_track": "ExitAfterTrack",
            "theme": "Theme",
            "theme_name": "ThemeName",
            "language": "Language",
            "always_on_top": "AlwaysOnTop",
            "minimize_to_tray": "MinimizeToTray",
            "show_grid": "ShowGrid",
            "natural_sort": "NaturalSort",
            "show_cover": "ShowCover",
            "proxy_type": "ProxyType",
            "proxy_addr": "ProxyAddr",
            "proxy_port": "ProxyPort",
            "timeout": "Timeout",
            "retry": "Retry",
            "bg_color": "BgColor",
            "bg_opacity": "BgOpacity",
            "lastfolder": "LastFolder",
            "lastvolume": "LastVolume",
            "lastsong": "LastSong",
            "lastposition": "LastPosition",
        }
        for section, options in self._defaults.items():
            for dk in options:
                lk = dk.lower()
                if lk != dk:
                    snake_to_pascal[lk] = dk

        changed = False
        for section in self._ini_parser.sections():
            items = list(self._ini_parser.items(section))
            seen = {}
            for key, value in items:
                pascal_key = snake_to_pascal.get(key)
                if pascal_key and pascal_key != key:
                    if not self._ini_parser.has_option(section, pascal_key):
                        self._ini_parser.set(section, pascal_key, value)
                    self._ini_parser.remove_option(section, key)
                    key = pascal_key
                    changed = True
                if key in seen:
                    self._ini_parser.remove_option(section, key)
                    self._ini_parser.set(section, key, value)
                    changed = True
                seen[key] = value
        if changed:
            self._save_ini()

    def _create_default_config(self) -> None:
        for section, options in self._defaults.items():
            if not self._ini_parser.has_section(section):
                self._ini_parser.add_section(section)
            for key, value in options.items():
                self._ini_parser.set(section, key, str(value))

        self._save_ini()
        logger.info("Created default config")

    def _save_ini(self) -> None:
        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                self._ini_parser.write(f)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def _sync_to_database(self) -> None:
        for section in self._ini_parser.sections():
            for key, value in self._ini_parser.items(section):
                db_key = f"{section}.{key}"
                existing = self._db.fetchone(
                    "SELECT * FROM config WHERE key = ?",
                    (db_key,)
                )

                config_type = self._detect_type(value)

                if existing:
                    self._db.update(
                        "config",
                        {"value": value, "type": config_type},
                        "key = ?",
                        (db_key,)
                    )
                else:
                    self._db.insert("config", {
                        "key": db_key,
                        "value": value,
                        "type": config_type
                    })

        valid_keys = set()
        for section in self._ini_parser.sections():
            for key, _ in self._ini_parser.items(section):
                valid_keys.add(f"{section}.{key}")

        all_rows = self._db.fetchall("SELECT key FROM config", ())
        if all_rows:
            for row in all_rows:
                if row["key"] not in valid_keys:
                    self._db.delete("config", "key = ?", (row["key"],))

    def _detect_type(self, value: str) -> str:
        try:
            int(value)
            return "int"
        except ValueError:
            pass

        if value.lower() in ("true", "false", "1", "0", "yes", "no"):
            return "bool"

        try:
            json.loads(value)
            return "json"
        except ValueError:
            pass

        return "string"

    def _normalize_bool(self, value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def get(self, section: str, key: str, default: Any = None) -> Any:
        db_key = f"{section}.{key}"
        result = self._db.fetchone(
            "SELECT value, type FROM config WHERE key = ?",
            (db_key,)
        )

        if result:
            return self._convert_value(result["value"], result["type"])

        if self._ini_parser.has_option(section, key):
            value = self._ini_parser.get(section, key)
            return self._convert_value(value, self._detect_type(value))

        if section in self._defaults and key in self._defaults[section]:
            return self._defaults[section][key]

        return default

    def _convert_value(self, value: str, type_name: str) -> Any:
        if type_name == "int":
            return int(value)
        elif type_name == "bool":
            return value.lower() in ("true", "1", "yes")
        elif type_name == "json":
            return json.loads(value)
        return value

    def set(self, section: str, key: str, value: Any) -> bool:
        try:
            str_value = self._normalize_bool(value)
            type_name = self._detect_type(str_value)

            if not self._ini_parser.has_section(section):
                self._ini_parser.add_section(section)

            self._ini_parser.set(section, key, str_value)
            self._save_ini()

            db_key = f"{section}.{key}"
            existing = self._db.fetchone(
                "SELECT id FROM config WHERE key = ?",
                (db_key,)
            )

            if existing:
                self._db.update(
                    "config",
                    {"value": str_value, "type": type_name},
                    "key = ?",
                    (db_key,)
                )
            else:
                self._db.insert("config", {
                    "key": db_key,
                    "value": str_value,
                    "type": type_name
                })

            self._event_bus.publish(EVENT_CONFIG_UPDATED, {
                "section": section,
                "key": key,
                "value": value
            })

            return True

        except Exception as e:
            logger.error(f"Error setting config {section}.{key}: {e}")
            return False

