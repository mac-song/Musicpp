import json
import os
import copy
from typing import Dict, Optional

from src.utils.constants import CONFIG_DIR
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

THEMES_DIR = os.path.join(CONFIG_DIR, "themes")

_THEME_SCHEMA = {
    "name": "",
    "is_dark": True,
    "colors": {
        "window_bg": "#1a1a2e",
        "surface": "#16213e",
        "surface_alt": "#0f3460",
        "border": "#333355",
        "text_primary": "#e0e0e0",
        "text_secondary": "#a0a0b0",
        "text_muted": "#8a8aa0",
        "accent": "#32c864",
        "accent_hover": "#3de878",
        "accent_pressed": "#28a850",
        "danger": "#e05050",
        "warning": "#e0a830",
        "info": "#5090d0",
        "success": "#32c864",
        "button_bg": "rgba(255,255,255,20)",
        "button_bg_hover": "rgba(255,255,255,40)",
        "button_bg_pressed": "rgba(255,255,255,60)",
        "button_text": "#dddddd",
        "input_bg": "#1e1e3a",
        "input_border": "#444466",
        "input_focus_border": "#32c864",
        "slider_groove": "#333355",
        "slider_handle": "#32c864",
        "table_row_alt": "rgba(255,255,255,8)",
        "table_row_selected": "rgba(50,200,100,40)",
        "table_row_selected_text": "#32c864",
        "scrollbar_bg": "#1a1a2e",
        "scrollbar_handle": "#444466",
        "group_box_border": "#333355",
        "tab_bg": "#16213e",
        "tab_active_bg": "#1a1a2e",
        "lyric_active": "#32c864",
        "lyric_inactive": "#a0a0b0",
        "vu_green": "#32c864",
        "vu_yellow": "#e0a830",
        "vu_red": "#e05050",
        "dir_color": "#6ab4ff",
        "cover_placeholder_bg": "#2a2a4a",
        "cover_placeholder_border": "#555577",
    },
}

BUILTIN_THEMES = [
    {
        "name": "Midnight Blue",
        "is_dark": True,
        "colors": {
            "window_bg": "#1a1a2e",
            "surface": "#16213e",
            "surface_alt": "#0f3460",
            "border": "#333355",
            "text_primary": "#e0e0e0",
            "text_secondary": "#a0a0b0",
            "text_muted": "#8a8aa0",
            "accent": "#32c864",
            "accent_hover": "#3de878",
            "accent_pressed": "#28a850",
            "danger": "#e05050",
            "warning": "#e0a830",
            "info": "#5090d0",
            "success": "#32c864",
            "button_bg": "rgba(255,255,255,20)",
            "button_bg_hover": "rgba(255,255,255,40)",
            "button_bg_pressed": "rgba(255,255,255,60)",
            "button_text": "#dddddd",
            "input_bg": "#1e1e3a",
            "input_border": "#444466",
            "input_focus_border": "#32c864",
            "slider_groove": "#333355",
            "slider_handle": "#32c864",
            "table_row_alt": "rgba(255,255,255,8)",
            "table_row_selected": "rgba(50,200,100,40)",
            "table_row_selected_text": "#32c864",
            "scrollbar_bg": "#1a1a2e",
            "scrollbar_handle": "#444466",
            "group_box_border": "#333355",
            "tab_bg": "#16213e",
            "tab_active_bg": "#1a1a2e",
            "lyric_active": "#32c864",
            "lyric_inactive": "#a0a0b0",
            "vu_green": "#32c864",
            "vu_yellow": "#e0a830",
            "vu_red": "#e05050",
            "dir_color": "#6ab4ff",
            "cover_placeholder_bg": "#2a2a4a",
            "cover_placeholder_border": "#555577",
        },
    },
    {
        "name": "Spotify Dark",
        "is_dark": True,
        "colors": {
            "window_bg": "#121212",
            "surface": "#181818",
            "surface_alt": "#282828",
            "border": "#3a3a3a",
            "text_primary": "#ffffff",
            "text_secondary": "#b3b3b3",
            "text_muted": "#8a8a8a",
            "accent": "#1db954",
            "accent_hover": "#1ed760",
            "accent_pressed": "#1aa34a",
            "danger": "#e91429",
            "warning": "#f59b23",
            "info": "#509bf5",
            "success": "#1db954",
            "button_bg": "rgba(255,255,255,10)",
            "button_bg_hover": "rgba(255,255,255,20)",
            "button_bg_pressed": "rgba(255,255,255,30)",
            "button_text": "#ffffff",
            "input_bg": "#2a2a2a",
            "input_border": "#3a3a3a",
            "input_focus_border": "#1db954",
            "slider_groove": "#3a3a3a",
            "slider_handle": "#1db954",
            "table_row_alt": "rgba(255,255,255,6)",
            "table_row_selected": "rgba(29,185,84,40)",
            "table_row_selected_text": "#1db954",
            "scrollbar_bg": "#121212",
            "scrollbar_handle": "#3a3a3a",
            "group_box_border": "#3a3a3a",
            "tab_bg": "#181818",
            "tab_active_bg": "#121212",
            "lyric_active": "#1db954",
            "lyric_inactive": "#b3b3b3",
            "vu_green": "#1db954",
            "vu_yellow": "#f59b23",
            "vu_red": "#e91429",
            "dir_color": "#509bf5",
            "cover_placeholder_bg": "#282828",
            "cover_placeholder_border": "#3a3a3a",
        },
    },
    {
        "name": "Dracula",
        "is_dark": True,
        "colors": {
            "window_bg": "#282a36",
            "surface": "#21222c",
            "surface_alt": "#343746",
            "border": "#44475a",
            "text_primary": "#f8f8f2",
            "text_secondary": "#bfc0c8",
            "text_muted": "#8b9cc7",
            "accent": "#bd93f9",
            "accent_hover": "#caa8fc",
            "accent_pressed": "#a87ee0",
            "danger": "#ff5555",
            "warning": "#f1fa8c",
            "info": "#8be9fd",
            "success": "#50fa7b",
            "button_bg": "rgba(255,255,255,10)",
            "button_bg_hover": "rgba(255,255,255,20)",
            "button_bg_pressed": "rgba(255,255,255,30)",
            "button_text": "#f8f8f2",
            "input_bg": "#21222c",
            "input_border": "#44475a",
            "input_focus_border": "#bd93f9",
            "slider_groove": "#44475a",
            "slider_handle": "#bd93f9",
            "table_row_alt": "rgba(255,255,255,6)",
            "table_row_selected": "rgba(189,147,249,40)",
            "table_row_selected_text": "#bd93f9",
            "scrollbar_bg": "#282a36",
            "scrollbar_handle": "#44475a",
            "group_box_border": "#44475a",
            "tab_bg": "#21222c",
            "tab_active_bg": "#282a36",
            "lyric_active": "#bd93f9",
            "lyric_inactive": "#bfc0c8",
            "vu_green": "#50fa7b",
            "vu_yellow": "#f1fa8c",
            "vu_red": "#ff5555",
            "dir_color": "#8be9fd",
            "cover_placeholder_bg": "#343746",
            "cover_placeholder_border": "#44475a",
        },
    },
    {
        "name": "Nord",
        "is_dark": True,
        "colors": {
            "window_bg": "#2e3440",
            "surface": "#3b4252",
            "surface_alt": "#434c5e",
            "border": "#4c566a",
            "text_primary": "#eceff4",
            "text_secondary": "#d8dee9",
            "text_muted": "#a5b0c3",
            "accent": "#88c0d0",
            "accent_hover": "#8fbcbb",
            "accent_pressed": "#81a1c1",
            "danger": "#bf616a",
            "warning": "#ebcb8b",
            "info": "#5e81ac",
            "success": "#a3be8c",
            "button_bg": "rgba(255,255,255,10)",
            "button_bg_hover": "rgba(255,255,255,20)",
            "button_bg_pressed": "rgba(255,255,255,30)",
            "button_text": "#eceff4",
            "input_bg": "#3b4252",
            "input_border": "#4c566a",
            "input_focus_border": "#88c0d0",
            "slider_groove": "#4c566a",
            "slider_handle": "#88c0d0",
            "table_row_alt": "rgba(255,255,255,6)",
            "table_row_selected": "rgba(136,192,208,40)",
            "table_row_selected_text": "#88c0d0",
            "scrollbar_bg": "#2e3440",
            "scrollbar_handle": "#4c566a",
            "group_box_border": "#4c566a",
            "tab_bg": "#3b4252",
            "tab_active_bg": "#2e3440",
            "lyric_active": "#88c0d0",
            "lyric_inactive": "#d8dee9",
            "vu_green": "#a3be8c",
            "vu_yellow": "#ebcb8b",
            "vu_red": "#bf616a",
            "dir_color": "#81a1c1",
            "cover_placeholder_bg": "#434c5e",
            "cover_placeholder_border": "#4c566a",
        },
    },
    {
        "name": "Rose Pine",
        "is_dark": True,
        "colors": {
            "window_bg": "#191724",
            "surface": "#1f1d2e",
            "surface_alt": "#26233a",
            "border": "#3b3654",
            "text_primary": "#e0def4",
            "text_secondary": "#908caa",
            "text_muted": "#9088a8",
            "accent": "#c4a7e7",
            "accent_hover": "#d4b8f0",
            "accent_pressed": "#b494d4",
            "danger": "#eb6f92",
            "warning": "#f6c177",
            "info": "#9ccfd8",
            "success": "#52b788",
            "button_bg": "rgba(255,255,255,10)",
            "button_bg_hover": "rgba(255,255,255,20)",
            "button_bg_pressed": "rgba(255,255,255,30)",
            "button_text": "#e0def4",
            "input_bg": "#1f1d2e",
            "input_border": "#3b3654",
            "input_focus_border": "#c4a7e7",
            "slider_groove": "#3b3654",
            "slider_handle": "#c4a7e7",
            "table_row_alt": "rgba(255,255,255,6)",
            "table_row_selected": "rgba(196,167,231,40)",
            "table_row_selected_text": "#c4a7e7",
            "scrollbar_bg": "#191724",
            "scrollbar_handle": "#3b3654",
            "group_box_border": "#3b3654",
            "tab_bg": "#1f1d2e",
            "tab_active_bg": "#191724",
            "lyric_active": "#c4a7e7",
            "lyric_inactive": "#908caa",
            "vu_green": "#31748f",
            "vu_yellow": "#f6c177",
            "vu_red": "#eb6f92",
            "dir_color": "#9ccfd8",
            "cover_placeholder_bg": "#26233a",
            "cover_placeholder_border": "#3b3654",
        },
    },
    {
        "name": "Catppuccin Mocha",
        "is_dark": True,
        "colors": {
            "window_bg": "#1e1e2e",
            "surface": "#181825",
            "surface_alt": "#313244",
            "border": "#45475a",
            "text_primary": "#cdd6f4",
            "text_secondary": "#a6adc8",
            "text_muted": "#8b8fa6",
            "accent": "#cba6f7",
            "accent_hover": "#d4b8f8",
            "accent_pressed": "#b48ef0",
            "danger": "#f38ba8",
            "warning": "#f9e2af",
            "info": "#89b4fa",
            "success": "#a6e3a1",
            "button_bg": "rgba(255,255,255,10)",
            "button_bg_hover": "rgba(255,255,255,20)",
            "button_bg_pressed": "rgba(255,255,255,30)",
            "button_text": "#cdd6f4",
            "input_bg": "#181825",
            "input_border": "#45475a",
            "input_focus_border": "#cba6f7",
            "slider_groove": "#45475a",
            "slider_handle": "#cba6f7",
            "table_row_alt": "rgba(255,255,255,6)",
            "table_row_selected": "rgba(203,166,247,40)",
            "table_row_selected_text": "#cba6f7",
            "scrollbar_bg": "#1e1e2e",
            "scrollbar_handle": "#45475a",
            "group_box_border": "#45475a",
            "tab_bg": "#181825",
            "tab_active_bg": "#1e1e2e",
            "lyric_active": "#cba6f7",
            "lyric_inactive": "#a6adc8",
            "vu_green": "#a6e3a1",
            "vu_yellow": "#f9e2af",
            "vu_red": "#f38ba8",
            "dir_color": "#89b4fa",
            "cover_placeholder_bg": "#313244",
            "cover_placeholder_border": "#45475a",
        },
    },
    {
        "name": "Daylight",
        "is_dark": False,
        "colors": {
            "window_bg": "#f5f5f5",
            "surface": "#ffffff",
            "surface_alt": "#e8e8e8",
            "border": "#d0d0d0",
            "text_primary": "#1a1a1a",
            "text_secondary": "#555555",
            "text_muted": "#6e6e6e",
            "accent": "#1a73e8",
            "accent_hover": "#4a90e8",
            "accent_pressed": "#1558b0",
            "danger": "#d93025",
            "warning": "#e8a317",
            "info": "#1a73e8",
            "success": "#1a7d34",
            "button_bg": "rgba(0,0,0,8)",
            "button_bg_hover": "rgba(0,0,0,15)",
            "button_bg_pressed": "rgba(0,0,0,22)",
            "button_text": "#1a1a1a",
            "input_bg": "#ffffff",
            "input_border": "#c0c0c0",
            "input_focus_border": "#1a73e8",
            "slider_groove": "#c0c0c0",
            "slider_handle": "#1a73e8",
            "table_row_alt": "rgba(0,0,0,4)",
            "table_row_selected": "rgba(26,115,232,40)",
            "table_row_selected_text": "#1a73e8",
            "scrollbar_bg": "#f5f5f5",
            "scrollbar_handle": "#c0c0c0",
            "group_box_border": "#d0d0d0",
            "tab_bg": "#e8e8e8",
            "tab_active_bg": "#f5f5f5",
            "lyric_active": "#1a73e8",
            "lyric_inactive": "#6e6e6e",
            "vu_green": "#1a7d34",
            "vu_yellow": "#e8a317",
            "vu_red": "#d93025",
            "dir_color": "#1a73e8",
            "cover_placeholder_bg": "#e0e0e0",
            "cover_placeholder_border": "#c0c0c0",
        },
    },
    {
        "name": "Solarized Light",
        "is_dark": False,
        "colors": {
            "window_bg": "#fdf6e3",
            "surface": "#eee8d5",
            "surface_alt": "#e0dac7",
            "border": "#d0c8a8",
            "text_primary": "#073642",
            "text_secondary": "#4e6369",
            "text_muted": "#51686e",
            "accent": "#155d90",
            "accent_hover": "#4aa3e0",
            "accent_pressed": "#104a75",
            "danger": "#dc322f",
            "warning": "#b58900",
            "info": "#155d90",
            "success": "#4a6300",
            "button_bg": "rgba(0,0,0,8)",
            "button_bg_hover": "rgba(0,0,0,15)",
            "button_bg_pressed": "rgba(0,0,0,22)",
            "button_text": "#073642",
            "input_bg": "#eee8d5",
            "input_border": "#d0c8a8",
            "input_focus_border": "#155d90",
            "slider_groove": "#d0c8a8",
            "slider_handle": "#155d90",
            "table_row_alt": "rgba(0,0,0,4)",
            "table_row_selected": "rgba(21,93,144,40)",
            "table_row_selected_text": "#155d90",
            "scrollbar_bg": "#fdf6e3",
            "scrollbar_handle": "#d0c8a8",
            "group_box_border": "#d0c8a8",
            "tab_bg": "#eee8d5",
            "tab_active_bg": "#fdf6e3",
            "lyric_active": "#155d90",
            "lyric_inactive": "#51686e",
            "vu_green": "#4a6300",
            "vu_yellow": "#b58900",
            "vu_red": "#dc322f",
            "dir_color": "#155d90",
            "cover_placeholder_bg": "#e0dac7",
            "cover_placeholder_border": "#d0c8a8",
        },
    },
]


class ThemeEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._current_theme_name = "Midnight Blue"
        self._mini_theme_name: Optional[str] = None
        self._themes: Dict[str, dict] = {}
        self._load_all_themes()
        self._initialized = True

    def _load_all_themes(self):
        for theme in BUILTIN_THEMES:
            self._themes[theme["name"]] = copy.deepcopy(theme)
        os.makedirs(THEMES_DIR, exist_ok=True)
        for fname in os.listdir(THEMES_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(THEMES_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if self._validate_theme(data):
                    self._themes[data["name"]] = data
            except Exception as e:
                logger.warning(f"Failed to load theme {fname}: {e}")

    def _validate_theme(self, data: dict) -> bool:
        if "name" not in data or "colors" not in data:
            return False
        if not isinstance(data["name"], str) or not data["name"].strip():
            return False
        if not isinstance(data["colors"], dict):
            return False
        return True

    def get_theme_names(self) -> list:
        return list(self._themes.keys())

    def get_builtin_names(self) -> list:
        return [t["name"] for t in BUILTIN_THEMES]

    def get_theme(self, name: str) -> Optional[dict]:
        return copy.deepcopy(self._themes.get(name))

    def get_current_theme(self) -> dict:
        return copy.deepcopy(self._themes.get(self._current_theme_name, BUILTIN_THEMES[0]))

    def get_current_colors(self) -> dict:
        theme = self.get_current_theme()
        return theme.get("colors", {})

    def get_mini_theme_name(self) -> str:
        return self._mini_theme_name or ""

    def set_mini_theme_name(self, name: str):
        if name and name not in self._themes:
            return
        self._mini_theme_name = name if name else None

    def get_mini_colors(self) -> dict:
        if self._mini_theme_name:
            theme = self._themes.get(self._mini_theme_name)
            if theme:
                return theme.get("colors", {})
        return self.get_current_colors()

    def get_current_name(self) -> str:
        return self._current_theme_name

    def set_current_theme(self, name: str) -> bool:
        if name not in self._themes:
            return False
        self._current_theme_name = name
        return True

    def save_theme(self, theme_data: dict) -> bool:
        if not self._validate_theme(theme_data):
            return False
        name = theme_data["name"]
        self._themes[name] = copy.deepcopy(theme_data)
        if name not in self.get_builtin_names():
            self._save_theme_to_file(theme_data)
        return True

    def _save_theme_to_file(self, theme_data: dict):
        os.makedirs(THEMES_DIR, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in theme_data["name"])
        fpath = os.path.join(THEMES_DIR, f"{safe_name}.json")
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(theme_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save theme: {e}")

    def delete_theme(self, name: str) -> bool:
        if name in self.get_builtin_names():
            return False
        if name not in self._themes:
            return False
        del self._themes[name]
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        fpath = os.path.join(THEMES_DIR, f"{safe_name}.json")
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except Exception:
                pass
        if self._current_theme_name == name:
            self._current_theme_name = BUILTIN_THEMES[0]["name"]
        return True

    def import_theme(self, file_path: str) -> bool:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not self._validate_theme(data):
                return False
            self.save_theme(data)
            return True
        except Exception as e:
            logger.error(f"Failed to import theme: {e}")
            return False

    def export_theme(self, name: str, file_path: str) -> bool:
        theme = self._themes.get(name)
        if not theme:
            return False
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(theme, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to export theme: {e}")
            return False

    def duplicate_theme(self, source_name: str, new_name: str) -> bool:
        source = self._themes.get(source_name)
        if not source:
            return False
        new_theme = copy.deepcopy(source)
        new_theme["name"] = new_name
        return self.save_theme(new_theme)

    def generate_qss(self) -> str:
        c = self.get_current_colors()
        is_dark = self.get_current_theme().get("is_dark", True)
        text_on_bg = "#ffffff" if is_dark else "#000000"

        qss = f"""
QWidget {{
    background-color: {c["window_bg"]};
    color: {c["text_primary"]};
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}}

QMainWindow {{
    background-color: {c["window_bg"]};
}}

QPushButton {{
    background-color: {c["button_bg"]};
    color: {c["button_text"]};
    border: 1px solid {c["border"]};
    border-radius: 4px;
    padding: 4px 12px;
    min-height: 20px;
}}
QPushButton:hover {{
    background-color: {c["button_bg_hover"]};
    border-color: {c["accent"]};
}}
QPushButton:pressed {{
    background-color: {c["button_bg_pressed"]};
}}
QPushButton:checked {{
    background-color: {c["accent"]};
    color: {text_on_bg};
    border-color: {c["accent"]};
}}
QPushButton:disabled {{
    color: {c["text_muted"]};
    background-color: {c["surface"]};
}}

QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background: {c["slider_groove"]};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c["slider_handle"]};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {c["accent"]};
    border-radius: 2px;
}}

QLabel {{
    color: {c["text_primary"]};
    background: transparent;
    border: none;
}}

QTreeWidget {{
    background-color: {c["surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 4px;
    outline: none;
}}
QTreeWidget::item {{
    padding: 3px 4px;
    border: none;
}}
QTreeWidget::item:selected {{
    background-color: {c["table_row_selected"]};
    color: {c["table_row_selected_text"]};
}}
QTreeWidget::item:hover {{
    background-color: {c["button_bg_hover"]};
}}

QTableWidget {{
    background-color: {c["surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 4px;
    gridline-color: {c["border"]};
    selection-background-color: {c["table_row_selected"]};
    selection-color: {c["table_row_selected_text"]};
}}
QTableWidget::item {{
    padding: 2px 6px;
}}
QTableWidget::item:alternate {{
    background-color: {c["table_row_alt"]};
}}
QHeaderView::section {{
    background-color: {c["surface_alt"]};
    color: {c["text_secondary"]};
    border: none;
    border-right: 1px solid {c["border"]};
    border-bottom: 1px solid {c["border"]};
    padding: 4px 8px;
    font-weight: bold;
}}

QListWidget {{
    background-color: {c["surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    border-radius: 4px;
    outline: none;
}}
QListWidget::item {{
    padding: 6px 10px;
    border: none;
}}
QListWidget::item:selected {{
    background-color: {c["table_row_selected"]};
    color: {c["table_row_selected_text"]};
}}
QListWidget::item:hover {{
    background-color: {c["button_bg_hover"]};
}}

QComboBox {{
    background-color: {c["input_bg"]};
    color: {c["text_primary"]};
    border: 1px solid {c["input_border"]};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
}}
QComboBox:hover {{
    border-color: {c["accent"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {c["surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["table_row_selected"]};
    selection-color: {c["table_row_selected_text"]};
}}

QSpinBox {{
    background-color: {c["input_bg"]};
    color: {c["text_primary"]};
    border: 1px solid {c["input_border"]};
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 20px;
}}
QSpinBox:hover {{
    border-color: {c["accent"]};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {c["surface_alt"]};
    border: none;
    width: 16px;
}}

QLineEdit {{
    background-color: {c["input_bg"]};
    color: {c["text_primary"]};
    border: 1px solid {c["input_border"]};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
}}
QLineEdit:hover {{
    border-color: {c["accent"]};
}}
QLineEdit:focus {{
    border-color: {c["input_focus_border"]};
}}

QCheckBox {{
    color: {c["text_primary"]};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c["input_border"]};
    border-radius: 3px;
    background-color: {c["input_bg"]};
}}
QCheckBox::indicator:checked {{
    background-color: {c["accent"]};
    border-color: {c["accent"]};
}}
QCheckBox::indicator:hover {{
    border-color: {c["accent"]};
}}
QRadioButton {{
    color: {c["text_primary"]};
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {c["text_secondary"]};
    border-radius: 7px;
    background-color: transparent;
}}
QRadioButton::indicator:checked {{
    background-color: {c["accent"]};
    border-color: {c["accent"]};
}}
QRadioButton::indicator:hover {{
    border-color: {c["accent"]};
}}

QGroupBox {{
    color: {c["text_secondary"]};
    border: 1px solid {c["group_box_border"]};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {c["accent"]};
}}

QSplitter::handle {{
    background-color: {c["border"]};
}}
QSplitter::handle:horizontal {{
    width: 2px;
}}
QSplitter::handle:vertical {{
    height: 2px;
}}

QScrollBar:vertical {{
    background: {c["scrollbar_bg"]};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {c["scrollbar_handle"]};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {c["scrollbar_bg"]};
    height: 8px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {c["scrollbar_handle"]};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QTextEdit {{
    background-color: {c["input_bg"]};
    color: {c["text_primary"]};
    border: 1px solid {c["input_border"]};
    border-radius: 4px;
    padding: 4px;
}}

QKeySequenceEdit {{
    background-color: {c["input_bg"]};
    color: {c["text_primary"]};
    border: 1px solid {c["input_border"]};
    border-radius: 4px;
    padding: 2px 6px;
}}

QStackedWidget {{
    background-color: {c["window_bg"]};
}}

QMenu {{
    background-color: {c["surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 24px;
    border-radius: 3px;
}}
QMenu::item:selected {{
    background-color: {c["table_row_selected"]};
    color: {c["table_row_selected_text"]};
}}
QMenu::separator {{
    height: 1px;
    background: {c["border"]};
    margin: 4px 8px;
}}

QTabWidget::pane {{
    border: 1px solid {c["border"]};
    background-color: {c["window_bg"]};
}}
QTabBar::tab {{
    background-color: {c["tab_bg"]};
    color: {c["text_secondary"]};
    padding: 6px 16px;
    border: 1px solid {c["border"]};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{
    background-color: {c["tab_active_bg"]};
    color: {c["accent"]};
}}

QToolTip {{
    background-color: {c["surface"]};
    color: {c["text_primary"]};
    border: 1px solid {c["border"]};
    padding: 4px;
}}
"""
        return qss
