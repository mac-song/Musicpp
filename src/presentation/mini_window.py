import sys
import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QFont, QFontMetrics

LYRIC_FONT_FAMILY = "Microsoft YaHei"
LYRIC_FONT_SIZE = 22
CTRL_HEIGHT = 24
MINI_CTRL_WIDTH = 420
MAX_SONG_INFO_LEN = 30

GWL_EXSTYLE = -20
WS_EX_WINDOWEDGE = 0x00000100
WS_EX_CLIENTEDGE = 0x00000200
DWMWA_NCRENDERING_ENABLED = 1
DWMWA_TRANSITIONS_FORCEDISABLED = 3
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_DONOTROUND = 1


def _disable_system_border(widget):
    if sys.platform != "win32":
        return
    hwnd = int(widget.winId())
    if not hwnd:
        return
    ex_style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ex_style &= ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE)
    ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_NCRENDERING_ENABLED,
        ctypes.byref(wintypes.BOOL(False)),
        ctypes.sizeof(wintypes.BOOL),
    )
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(wintypes.INT(DWMWCP_DONOTROUND)),
        ctypes.sizeof(wintypes.INT),
    )
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_TRANSITIONS_FORCEDISABLED,
        ctypes.byref(wintypes.BOOL(True)),
        ctypes.sizeof(wintypes.BOOL),
    )


def _truncate_song_info(text: str, max_len: int = MAX_SONG_INFO_LEN) -> str:
    if not text:
        return text
    if len(text) > max_len:
        return text[:max_len] + "......"
    return text


class LyricFloatingWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = QPoint()
        self._font_size = LYRIC_FONT_SIZE
        self._active_color = "#32c864"
        self._inactive_color = "#a0a0a0"
        self._always_on_top = True
        self._fixed_width = 0
        self._fixed_height = 0
        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setStyleSheet("""
            LyricFloatingWindow {
                background: transparent;
                border: none;
                outline: none;
            }
            QLabel {
                background: transparent;
                border: none;
                outline: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._lbl_active = QLabel("")
        self._lbl_active.setFont(QFont(LYRIC_FONT_FAMILY, self._font_size, QFont.Bold))
        self._lbl_active.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self._lbl_active.setStyleSheet(f"color: {self._active_color}; padding: 2px 0px;")
        layout.addWidget(self._lbl_active)

        self._lbl_inactive = QLabel("")
        self._lbl_inactive.setFont(QFont(LYRIC_FONT_FAMILY, self._font_size, QFont.Normal))
        self._lbl_inactive.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self._lbl_inactive.setStyleSheet(f"color: {self._inactive_color}; padding: 2px 0px;")
        layout.addWidget(self._lbl_inactive)

        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        _disable_system_border(self)

    def update_lyric(self, active_text, inactive_text):
        self._lbl_active.setText(active_text)
        self._lbl_inactive.setText(inactive_text if inactive_text else "")
        self._resize_to_content(active_text, inactive_text)

    def clear_lyric(self):
        self._lbl_active.setText("")
        self._lbl_inactive.setText("")

    def _resize_to_content(self, active_text="", inactive_text=""):
        if self._fixed_width > 0 and self._fixed_height > 0:
            self.setFixedSize(self._fixed_width, self._fixed_height)
            return
        font = QFont(LYRIC_FONT_FAMILY, self._font_size, QFont.Bold)
        fm = QFontMetrics(font)
        max_w = 0
        for t in [active_text, inactive_text]:
            if t:
                tw = fm.horizontalAdvance(t)
                if tw > max_w:
                    max_w = tw
        w = max(max_w + 10, 200)
        w = min(w, 1600)
        line_h = int(fm.height() * 1.5)
        h = line_h * 2 + 4 + 4
        self.setFixedSize(w, h)

    def set_font_size(self, size):
        self._font_size = size
        self._lbl_active.setFont(QFont(LYRIC_FONT_FAMILY, size, QFont.Bold))
        self._lbl_inactive.setFont(QFont(LYRIC_FONT_FAMILY, size, QFont.Normal))

    def set_lyric_colors(self, active_color: str, inactive_color: str):
        self._active_color = active_color
        self._inactive_color = inactive_color
        self._lbl_active.setStyleSheet(f"color: {active_color}; padding: 2px 0px;")
        self._lbl_inactive.setStyleSheet(f"color: {inactive_color}; padding: 2px 0px;")

    def set_always_on_top(self, on_top: bool):
        self._always_on_top = on_top
        if on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def set_fixed_size_from_settings(self, w: int, h: int):
        self._fixed_width = w
        self._fixed_height = h

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()


class MiniWindow(QWidget):
    prev_requested = Signal()
    play_requested = Signal()
    next_requested = Signal()
    restore_requested = Signal()
    hide_requested = Signal()
    lyric_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_pos = QPoint()
        self._is_playing = False
        self._has_lyric = False
        self._lyric_visible = False
        self._song_info = ""
        self._time_info = ""
        self._init_ui()
        self._lyric_window = LyricFloatingWindow()
        self._apply_style()
        self._update_icons()
        self._resize_to_fit()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self._container = QWidget(self)
        self._container.setObjectName("mini_container")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.addWidget(self._container)

        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(6, 2, 6, 2)
        self._container_layout.setSpacing(0)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)

        self._lbl_info = QLabel("Music++")
        self._lbl_info.setFont(QFont("Microsoft YaHei", 9, QFont.Normal))
        ctrl_row.addWidget(self._lbl_info)

        self._lbl_time = QLabel("")
        self._lbl_time.setFont(QFont("Microsoft YaHei", 9, QFont.Normal))
        ctrl_row.addWidget(self._lbl_time)

        ctrl_row.addStretch()

        self._btn_prev = QPushButton()
        self._btn_prev.setFixedSize(28, CTRL_HEIGHT)
        self._btn_prev.setToolTip("Previous")
        self._btn_prev.clicked.connect(self.prev_requested.emit)
        ctrl_row.addWidget(self._btn_prev)

        self._btn_play = QPushButton()
        self._btn_play.setFixedSize(28, CTRL_HEIGHT)
        self._btn_play.setToolTip("Play")
        self._btn_play.clicked.connect(self.play_requested.emit)
        ctrl_row.addWidget(self._btn_play)

        self._btn_next = QPushButton()
        self._btn_next.setFixedSize(28, CTRL_HEIGHT)
        self._btn_next.setToolTip("Next")
        self._btn_next.clicked.connect(self.next_requested.emit)
        ctrl_row.addWidget(self._btn_next)

        ctrl_row.addSpacing(6)

        self._btn_lyric = QPushButton()
        self._btn_lyric.setFixedSize(28, CTRL_HEIGHT)
        self._btn_lyric.setToolTip("Lyric")
        self._btn_lyric.setCheckable(True)
        self._btn_lyric.clicked.connect(self._toggle_lyric)
        ctrl_row.addWidget(self._btn_lyric)

        self._btn_restore = QPushButton()
        self._btn_restore.setFixedSize(28, CTRL_HEIGHT)
        self._btn_restore.setToolTip("Full Mode")
        self._btn_restore.clicked.connect(self.restore_requested.emit)
        ctrl_row.addWidget(self._btn_restore)

        self._btn_close = QPushButton()
        self._btn_close.setFixedSize(28, CTRL_HEIGHT)
        self._btn_close.setToolTip("Hide")
        self._btn_close.clicked.connect(self.hide_requested.emit)
        ctrl_row.addWidget(self._btn_close)

        self._container_layout.addLayout(ctrl_row)

    def showEvent(self, event):
        super().showEvent(event)
        _disable_system_border(self)

    def _apply_style(self):
        from src.infrastructure.theme_engine import ThemeEngine
        c = ThemeEngine().get_mini_colors()
        bg = c.get("surface", "#1a1a2e")
        accent = c.get("accent", "#32c864")
        text = c.get("text_primary", "#e0e0e0")
        btn_bg = c.get("button_bg", "rgba(255,255,255,20)")
        btn_bg_hover = c.get("button_bg_hover", "rgba(255,255,255,40)")
        btn_bg_pressed = c.get("button_bg_pressed", "rgba(255,255,255,60)")
        self._container.setStyleSheet(f"""
            QWidget#mini_container {{
                background-color: {bg};
                border: 1px solid rgba(255,255,255,30);
                border-radius: 8px;
                outline: none;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {text};
                border: none;
                border-radius: 3px;
                outline: none;
                font-size: 11px;
                padding: 1px 6px;
            }}
            QPushButton:hover {{
                background-color: {btn_bg_hover};
            }}
            QPushButton:pressed {{
                background-color: {btn_bg_pressed};
            }}
            QPushButton:checked {{
                background-color: {accent};
                color: {bg};
            }}
            QLabel {{
                color: {text};
                background: transparent;
                border: none;
                outline: none;
            }}
        """)
        lyric_active = c.get("lyric_active", "#32c864")
        lyric_inactive = c.get("lyric_inactive", "#a0a0b0")
        self._lyric_window.set_lyric_colors(lyric_active, lyric_inactive)

    def _toggle_lyric(self, checked):
        self._lyric_visible = checked
        self._btn_lyric.setToolTip("Lyric: ON" if checked else "Lyric")
        if checked:
            self._lyric_window.show()
            ctrl_geo = self.geometry()
            self._lyric_window.move(ctrl_geo.left(), ctrl_geo.top() - self._lyric_window.height() - 4)
        else:
            self._lyric_window.hide()
        self.lyric_toggled.emit(checked)

    def _update_icons(self):
        from src.utils.svg_icons import get_icon
        from src.infrastructure.theme_engine import ThemeEngine
        c = ThemeEngine().get_mini_colors()
        color = c.get("text_primary", "#ddd")
        sz = 14
        self._btn_prev.setIcon(get_icon("skip-back", color, sz))
        self._btn_play.setIcon(get_icon("play", color, sz))
        self._btn_next.setIcon(get_icon("skip-forward", color, sz))
        self._btn_lyric.setIcon(get_icon("text", color, sz))
        self._btn_restore.setIcon(get_icon("maximize-2", color, sz))
        self._btn_close.setIcon(get_icon("x", color, sz))

    def _resize_to_fit(self):
        self._container.adjustSize()
        content_w = self._container.sizeHint().width() + 12
        if self._song_info:
            w = max(content_w, MINI_CTRL_WIDTH)
        else:
            w = content_w
        self.setFixedSize(w + 8, CTRL_HEIGHT + 16)

    def update_song_info(self, song_info, time_info=""):
        self._song_info = _truncate_song_info(song_info) if song_info else ""
        self._time_info = time_info
        if self._song_info:
            self._lbl_info.setText(f"Music++ - {self._song_info}")
        else:
            self._lbl_info.setText("Music++")
        if time_info:
            self._lbl_time.setText(f" [{time_info}]")
        else:
            self._lbl_time.setText("")
        self._resize_to_fit()

    def update_lyric(self, active_text, inactive_text):
        if active_text:
            self._has_lyric = True
            self._lyric_window.update_lyric(active_text, inactive_text)
            if self._lyric_visible:
                self._lyric_window.show()
        else:
            self._lyric_window.clear_lyric()

    def clear_lyric(self):
        self._has_lyric = False
        self._lyric_window.clear_lyric()
        self._lyric_window.hide()
        self._btn_lyric.setChecked(False)
        self._btn_lyric.setToolTip("Lyric")
        self._lyric_visible = False

    def update_play_state(self, is_playing):
        self._is_playing = is_playing
        from src.utils.svg_icons import get_icon
        from src.infrastructure.theme_engine import ThemeEngine
        c = ThemeEngine().get_mini_colors()
        color = c.get("text_primary", "#ddd")
        icon = get_icon("pause" if is_playing else "play", color, 14)
        self._btn_play.setIcon(icon)
        self._btn_play.setToolTip("Pause" if is_playing else "Play")

    def update_repeat_state(self, active, start, end):
        pass

    def set_font_size(self, size):
        self._lyric_window.set_font_size(size)

    def set_lyric_colors(self, active_color: str, inactive_color: str):
        self._lyric_window.set_lyric_colors(active_color, inactive_color)

    def set_lyric_always_on_top(self, on_top: bool):
        self._lyric_window.set_always_on_top(on_top)

    def set_lyric_fixed_size(self, w: int, h: int):
        self._lyric_window.set_fixed_size_from_settings(w, h)

    def move_to_bottom_right(self):
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - self.width() - 20
            y = geo.bottom() - self.height() - 20
            self.move(x, y)

    def hideEvent(self, event):
        self._lyric_window.hide()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._lyric_window.close()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = QPoint()
