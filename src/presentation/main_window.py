import sys
import os
import string
import threading
import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QMenu, QFrame,
    QScrollArea,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QAbstractItemView, QStackedWidget,
    QSystemTrayIcon,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QEvent
from PySide6.QtGui import QMovie, QShortcut, QKeySequence, QPixmap, QPainter, QColor, QFont, QIcon

from src.business.config_manager import ConfigManager
from src.business.lyric_manager import LyricManager
from src.business.playback_manager import PlaybackManager, CONTEXT_LOCAL, CONTEXT_ONLINE
from src.core.audio_service import AudioService
from src.core.event_bus import EventBus
from src.core.metadata_service import MetadataService
from src.core.music_library_service import MusicLibraryService
from src.core.beets_service import BeetsService
from src.utils.metadata_db import MetadataDB
from src.presentation.online_music_panel import OnlineMusicPanel
from src.presentation.settings_panel import SettingsPanel
from src.presentation.lyric_panel import LyricPanel
from src.presentation.lyric_select_dialog import LyricSelectDialog
from src.presentation.mini_window import MiniWindow
from src.presentation.themed_dialog import ThemedMessageBox
from src.presentation.study_window import StudyWindow
from src.presentation.help_panel import HelpWindow
from src.core.search_service import SearchService
from src.core.download_service import DownloadService
from src.utils.constants import (
    DEFAULT_WINDOW_HEIGHT, DEFAULT_WINDOW_WIDTH,
    EVENT_LYRIC_LOADED, EVENT_PLAYBACK_STATE_CHANGED, EVENT_TRACK_CHANGED,
    EVENT_PLAY_FAILED,
    PLAY_MODE_LOOP_ALL, PLAY_MODE_LOOP_SINGLE, PLAY_MODE_RANDOM, PLAY_MODE_SEQUENCE,
    PLAYBACK_PAUSED, PLAYBACK_PLAYING, PLAYBACK_STOPPED,
    SUPPORTED_AUDIO_FORMATS,
    PLAYLIST_FORMATS,
)
from src.utils.logger import setup_logger, log_msgbox
from src.business.i18n_service import I18n

logger = setup_logger(__name__)

WINDOWS_BLACKLIST = {
    "$RECYCLE.BIN", "System Volume Information", "Windows",
    "Program Files", "Program Files (x86)", "ProgramData",
    "Recovery", "$WinREAgent", "Intel", "PerfLogs", "MSOCache",
    "Documents and Settings", "All Users", "Default User",
    "Public", "Default", "Default.migrated",
    "AppData", "Application Data", "Local Settings",
    "Cookies", "History", "NetHood", "PrintHood",
    "Recent", "SendTo", "Templates", "Start Menu",
    "NTUSER.DAT", "ntuser.dat.LOG1", "ntuser.dat.LOG2",
    "System32", "SysWOW64", "Boot", "EFI",
}

if sys.platform == "win32":
    WM_NCHITTEST = 0x0084
    HTCLIENT = 1
    HTCAPTION = 2
    HTTOP = 12
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTLEFT = 10
    HTRIGHT = 11
    HTBOTTOM = 15
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    BORDER_WIDTH = 5


def _is_valid_dir(entry):
    try:
        if not entry.is_dir(follow_symlinks=False):
            return False
        if entry.name.startswith('.'):
            return False
        if entry.name in WINDOWS_BLACKLIST:
            return False
        if entry.is_symlink():
            return False
        try:
            stat_info = entry.stat(follow_symlinks=False)
            if stat_info.st_file_attributes & 0x400:
                return False
        except OSError:
            return False
        return True
    except (OSError, PermissionError):
        return False


def _list_subdirs(path):
    result = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if _is_valid_dir(entry):
                    result.append((entry.name, entry.path))
    except (PermissionError, OSError):
        pass
    result.sort(key=lambda x: x[0].lower())
    return result


def _list_music_and_dirs(path):
    dirs = []
    files = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if _is_valid_dir(entry):
                        dirs.append((entry.name, entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in SUPPORTED_AUDIO_FORMATS or ext in PLAYLIST_FORMATS:
                            files.append((entry.name, entry.path))
                except (OSError, PermissionError):
                    continue
    except (PermissionError, OSError):
        pass
    dirs.sort(key=lambda x: x[0].lower())
    files.sort(key=lambda x: x[0].lower())
    return dirs, files


class VUMeter(QWidget):
    NUM_BARS = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 80)
        self.setMaximumHeight(90)
        self._levels = [0.0] * self.NUM_BARS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._decay)
        self._timer.start(50)

    def _get_theme_colors(self):
        try:
            from src.infrastructure.theme_engine import ThemeEngine
            c = ThemeEngine().get_current_colors()
            return QColor(c.get("vu_green", "#32c864")), QColor(c.get("vu_yellow", "#e0a830")), QColor(c.get("vu_red", "#e05050"))
        except Exception:
            return QColor(50, 200, 100), QColor(255, 200, 50), QColor(255, 50, 50)

    def set_levels(self, levels):
        for i in range(min(self.NUM_BARS, len(levels))):
            self._levels[i] = min(1.0, max(0.0, levels[i]))
        self.update()

    def _decay(self):
        for i in range(self.NUM_BARS):
            self._levels[i] *= 0.88
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        n = self.NUM_BARS
        gap = 2
        bar_w = max(6, (w - gap * (n + 1)) // n)
        total_w = n * bar_w + (n + 1) * gap
        start_x = (w - total_w) // 2
        top = 4
        bar_h = h - 10

        color_green, color_yellow, color_red = self._get_theme_colors()

        for i in range(n):
            x = start_x + gap + i * (bar_w + gap)

            level = self._levels[i]
            fill_h = int(bar_h * level)
            if fill_h > 0:
                segments = 20
                seg_h = bar_h / segments
                for s in range(int(segments * level)):
                    ratio = s / segments
                    if ratio > 0.8:
                        color = color_red
                    elif ratio > 0.6:
                        color = color_yellow
                    else:
                        color = color_green
                    y = top + bar_h - int((s + 1) * seg_h)
                    painter.fillRect(x, y, bar_w, max(1, int(seg_h) - 1), color)

        painter.end()


class MainWindow(QMainWindow):
    position_changed = Signal(float)
    file_list_loaded = Signal(str, list, list)
    _sig_track_changed = Signal(object)
    _sig_lyric_loaded = Signal(object)
    _sig_lyric_candidates = Signal(object, object)
    _sig_playback_state = Signal(object)
    _sig_online_url_ready = Signal(dict, dict)
    _sig_online_url_failed = Signal(str)
    _sig_play_failed = Signal(str)
    _sig_beets_progress = Signal(str, int)
    _sig_beets_done = Signal(bool)

    def __init__(self):
        super().__init__()
        self._playback_manager = PlaybackManager()
        self._lyric_manager = LyricManager()
        self._metadata_service = MetadataService()
        self._config_manager = ConfigManager()
        self._event_bus = EventBus()
        self._metadata_db = MetadataDB()
        self._music_library = MusicLibraryService()
        self._beets_service = BeetsService()
        self._search_service = SearchService(self)
        self._download_service = DownloadService(self)

        self._current_position = 0.0
        self._current_duration = 0.0
        self._is_seeking = False
        self._current_metadata = None
        self._current_folder = ""
        self._current_dir_type = ""
        self._current_dir_extra = ""
        self._file_list_version = 0
        self._mini_mode = False
        self._mini_window = None
        self._help_window = HelpWindow(self)
        self._tray_icon = None

        self._repeat_active = False
        self._repeat_start = 0.0
        self._repeat_end = 0.0
        self._repeat_seeking = False

        self._init_ui()
        self._init_event_handlers()
        self._init_shortcuts()
        self._init_timer()
        self._connect_online_signals()
        self._refresh_plugin_list()
        self._apply_theme(self._config_manager.get("Appearance", "ThemeName", "Midnight Blue"))

        self._sig_track_changed.connect(self._handle_track_changed, Qt.QueuedConnection)
        self._sig_lyric_loaded.connect(self._handle_lyric_loaded, Qt.QueuedConnection)
        self._sig_lyric_candidates.connect(self._handle_lyric_candidates, Qt.QueuedConnection)
        self._sig_online_url_ready.connect(self._handle_online_url_ready, Qt.QueuedConnection)
        self._sig_online_url_failed.connect(self._handle_online_url_failed, Qt.QueuedConnection)
        self._sig_playback_state.connect(self._handle_playback_state_changed, Qt.QueuedConnection)
        self._sig_play_failed.connect(self._handle_play_failed, Qt.QueuedConnection)

        self._sig_beets_progress.connect(self._on_beets_progress, Qt.QueuedConnection)
        self._sig_beets_done.connect(self._on_beets_done, Qt.QueuedConnection)

        self.file_list_loaded.connect(self._on_file_list_loaded)

        threading.Thread(target=self._metadata_db.delete_stale_metadata, daemon=True).start()

        self._start_alist_if_available()

    # ================================================================
    # UI
    # ================================================================

    def _init_ui(self):
        self.setWindowTitle("Music++")
        self.setMinimumSize(900, 600)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self._normal_geometry = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_custom_title_bar())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(4)

        body_layout.addWidget(self._build_top_panel())

        self._middle_stack = QStackedWidget()
        self._middle_stack.addWidget(self._build_middle_panel())
        self._online_music_panel = OnlineMusicPanel()
        self._middle_stack.addWidget(self._online_music_panel)
        self._lyric_panel = LyricPanel()
        self._lyric_panel.offset_adjusted.connect(self._on_lyric_offset_adjusted)
        self._lyric_panel.offset_reset.connect(self._on_lyric_offset_reset)
        self._lyric_panel.offset_save.connect(self._on_lyric_offset_save)
        self._lyric_panel.line_clicked.connect(self._on_lyric_line_clicked)
        self._lyric_panel.lines_selected.connect(self._on_lyric_lines_selected)
        self._middle_stack.addWidget(self._lyric_panel)
        self._settings_panel = SettingsPanel()
        self._middle_stack.addWidget(self._settings_panel)
        self._study_window = None
        self._study_mode_active = False
        self._lyric_panel_visible = False
        self._settings_panel_visible = False
        self._lyric_state = 0  # 0=OFF, 1=ON(lyric panel)
        self._pre_lyric_stack_index = 0
        self._pre_settings_stack_index = 0
        body_layout.addWidget(self._middle_stack, 1)

        self._bottom_panel = self._build_bottom_panel()
        body_layout.addWidget(self._bottom_panel)

        layout.addWidget(body, 1)

        from src.business.config_manager import ConfigManager
        online_mode = ConfigManager().get("General", "OnlineMode", False)
        if online_mode:
            self._btn_source.setChecked(True)
            self._btn_source.setToolTip(I18n.t("main.tooltip.source_online"))
            self._middle_stack.setCurrentIndex(1)
            from src.core.online_music_service import OnlineMusicService
            if OnlineMusicService().get_playlist():
                self._online_music_panel._menu_list.setCurrentRow(1)

        self._settings_panel.load_from_config(self._config_manager)

        study_enabled = self._config_manager.get("Study", "Enabled", True)
        self._btn_study.setVisible(study_enabled)

        retain_months = self._config_manager.get("Logs", "RetainMonths", 3)
        from src.utils.logger import cleanup_old_logs
        cleanup_old_logs(retain_months)

    def _build_custom_title_bar(self):
        self._title_bar = QWidget()
        self._title_bar.setObjectName("CustomTitleBar")
        self._title_bar.setFixedHeight(32)
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(8, 0, 0, 0)
        title_layout.setSpacing(0)

        self._title_label = QLabel(I18n.t("main.label.app_title"))
        self._title_label.setObjectName("TitleLabel")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()

        self._btn_help = QPushButton()
        self._btn_help.setObjectName("TitleBarButton")
        self._btn_help.setFixedSize(32, 32)
        self._btn_help.setToolTip(I18n.t("help.toggle"))
        self._btn_help.clicked.connect(self._toggle_help)
        title_layout.addWidget(self._btn_help)

        self._btn_minimize = QPushButton()
        self._btn_minimize.setObjectName("TitleBarButton")
        self._btn_minimize.setFixedSize(40, 32)
        self._btn_minimize.clicked.connect(self.showMinimized)
        title_layout.addWidget(self._btn_minimize)

        self._btn_maximize = QPushButton()
        self._btn_maximize.setObjectName("TitleBarButton")
        self._btn_maximize.setFixedSize(40, 32)
        self._btn_maximize.clicked.connect(self._toggle_maximize)
        title_layout.addWidget(self._btn_maximize)

        self._btn_close = QPushButton()
        self._btn_close.setObjectName("TitleBarCloseButton")
        self._btn_close.setFixedSize(40, 32)
        self._btn_close.clicked.connect(self.close)
        title_layout.addWidget(self._btn_close)

        self._title_bar_drag_pos = None
        self._title_bar.mousePressEvent = self._on_title_bar_press
        self._title_bar.mouseMoveEvent = self._on_title_bar_move
        self._title_bar.mouseReleaseEvent = self._on_title_bar_release
        self._title_bar.mouseDoubleClickEvent = self._on_title_bar_double_click

        return self._title_bar

    def _update_maximize_icon(self):
        from src.utils.svg_icons import get_icon
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        icon_color = tc.get("text_primary", "#cccccc")
        if self.isMaximized():
            self._btn_maximize.setIcon(get_icon("minimize-2", icon_color, 16))
        else:
            self._btn_maximize.setIcon(get_icon("maximize-2", icon_color, 16))

    def _toggle_maximize(self):
        if self.isMaximized():
            if hasattr(self, '_normal_geometry') and self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self.showNormal()
        else:
            self._normal_geometry = self.geometry()
            self.showMaximized()
        self._update_maximize_icon()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._update_maximize_icon()
            if not self.isMaximized() and hasattr(self, '_normal_geometry') and self._normal_geometry:
                self.setGeometry(self._normal_geometry)

    def _on_title_bar_press(self, event):
        if event.button() == Qt.LeftButton:
            child = self._title_bar.childAt(event.position().toPoint())
            if isinstance(child, QPushButton):
                return
            self._title_bar_drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_title_bar_move(self, event):
        if event.buttons() & Qt.LeftButton and self._title_bar_drag_pos:
            if self.isMaximized():
                if hasattr(self, '_normal_geometry') and self._normal_geometry:
                    self.setGeometry(self._normal_geometry)
                self.showNormal()
                self._update_maximize_icon()
                geo = self.frameGeometry()
                center_x = geo.center().x()
                self._title_bar_drag_pos = QPoint(center_x - geo.left(), self._title_bar_drag_pos.y())
            self.move(event.globalPosition().toPoint() - self._title_bar_drag_pos)
            event.accept()

    def _on_title_bar_release(self, event):
        self._title_bar_drag_pos = None
        event.accept()

    def _on_title_bar_double_click(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()

    def _build_top_panel(self):
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._btn_play = QPushButton(); self._btn_play.setFixedSize(32, 28)
        self._btn_play.setToolTip(I18n.t("main.tooltip.play"))
        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_pause = QPushButton(); self._btn_pause.setFixedSize(32, 28)
        self._btn_pause.setToolTip(I18n.t("main.tooltip.pause"))
        self._btn_pause.clicked.connect(self._pause)
        self._btn_backward = QPushButton(); self._btn_backward.setFixedSize(32, 28)
        self._btn_backward.setToolTip(I18n.t("main.tooltip.rewind"))
        self._btn_backward.clicked.connect(self._seek_backward)
        self._btn_forward = QPushButton(); self._btn_forward.setFixedSize(32, 28)
        self._btn_forward.setToolTip(I18n.t("main.tooltip.fast_forward"))
        self._btn_forward.clicked.connect(self._seek_forward)
        self._btn_prev = QPushButton(); self._btn_prev.setFixedSize(32, 28)
        self._btn_prev.setToolTip(I18n.t("main.tooltip.previous"))
        self._btn_prev.clicked.connect(self._previous_track)
        self._btn_next = QPushButton(); self._btn_next.setFixedSize(32, 28)
        self._btn_next.setToolTip(I18n.t("main.tooltip.next"))
        self._btn_next.clicked.connect(self._next_track)
        self._btn_mode = QPushButton(); self._btn_mode.setFixedSize(32, 28)
        self._btn_mode.setToolTip(I18n.t("main.tooltip.mode_sequence"))
        self._btn_mode.clicked.connect(self._cycle_play_mode)
        self._btn_lyric = QPushButton(); self._btn_lyric.setFixedSize(32, 28)
        self._btn_lyric.setToolTip(I18n.t("main.tooltip.lyric_off"))
        self._btn_lyric.clicked.connect(self._cycle_lyric_state)
        self._btn_repeat = QPushButton(); self._btn_repeat.setFixedSize(32, 28)
        self._btn_repeat.setToolTip(I18n.t("main.tooltip.repeat_off"))
        self._btn_repeat.setCheckable(True)
        self._btn_repeat.clicked.connect(self._on_repeat_toggle)
        self._btn_source = QPushButton(); self._btn_source.setFixedSize(32, 28)
        self._btn_source.setToolTip(I18n.t("main.tooltip.source_local"))
        self._btn_source.setCheckable(True); self._btn_source.clicked.connect(self._toggle_source_panel)
        self._btn_mini = QPushButton(); self._btn_mini.setFixedSize(32, 28)
        self._btn_mini.setToolTip(I18n.t("main.tooltip.mini_mode"))
        self._btn_mini.clicked.connect(self._toggle_mini_mode)
        self._btn_study = QPushButton(); self._btn_study.setFixedSize(32, 28)
        self._btn_study.setToolTip(I18n.t("main.tooltip.study"))
        self._btn_study.setCheckable(True)
        self._btn_study.clicked.connect(self._toggle_study_window)
        self._btn_settings = QPushButton(); self._btn_settings.setFixedSize(32, 28)
        self._btn_settings.setToolTip(I18n.t("main.tooltip.settings"))
        self._btn_settings.setCheckable(True)
        self._btn_settings.clicked.connect(self._toggle_settings_panel)

        for w in [self._btn_source, self._btn_play, self._btn_pause, self._btn_backward, self._btn_forward,
                   self._btn_prev, self._btn_next, self._btn_mode, self._btn_lyric, self._btn_repeat]:
            row1.addWidget(w)
        row1.addStretch()
        row1.addWidget(self._btn_mini)
        row1.addWidget(self._btn_study)
        row1.addWidget(self._btn_settings)
        vbox.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self._slider_progress = QSlider(Qt.Horizontal)
        self._slider_progress.setRange(0, 1000)
        self._slider_progress.sliderPressed.connect(lambda: setattr(self, '_is_seeking', True))
        self._slider_progress.sliderReleased.connect(self._on_seek_end)
        self._lbl_time = QLabel("00:00 / 00:00"); self._lbl_time.setFixedWidth(90)
        self._lbl_time.setAlignment(Qt.AlignCenter)
        self._slider_volume = QSlider(Qt.Horizontal)
        self._slider_volume.setRange(0, 100); self._slider_volume.setValue(80)
        self._slider_volume.setFixedWidth(100)
        self._slider_volume.valueChanged.connect(self._set_volume)
        self._lbl_volume = QLabel("80%"); self._lbl_volume.setFixedWidth(35)

        row2.addWidget(self._slider_progress, 1)
        row2.addWidget(self._lbl_time)
        row2.addWidget(QLabel(I18n.t("main.label.volume")))
        row2.addWidget(self._slider_volume)
        row2.addWidget(self._lbl_volume)
        vbox.addLayout(row2)

        return panel

    def _build_middle_panel(self):
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        # Left: directory tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(QLabel(I18n.t("main.label.directory")))
        self._dir_tree = QTreeWidget()
        self._dir_tree.setHeaderHidden(True)
        self._dir_tree.itemClicked.connect(self._on_dir_clicked)
        self._dir_tree.itemExpanded.connect(self._on_dir_expanded)
        self._dir_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._dir_tree.customContextMenuRequested.connect(self._on_dir_context_menu)
        self._populate_root_tree()
        left_layout.addWidget(self._dir_tree)
        splitter.addWidget(left)

        # Right: file list + lyric manage panel (stacked)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self._right_stack = QStackedWidget()

        # Page 0: playlist page (label + file table)
        playlist_page = QWidget()
        playlist_layout = QVBoxLayout(playlist_page)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.addWidget(QLabel(I18n.t("main.label.playlist")))
        self._file_table = QTableWidget()
        self._file_table.setColumnCount(5)
        self._file_table.setHorizontalHeaderLabels([I18n.t("main.header.name"), I18n.t("main.header.duration"), I18n.t("main.header.format"), I18n.t("main.header.lyric"), I18n.t("main.header.play_time")])
        self._file_table.verticalHeader().setVisible(False)
        self._file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._file_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._file_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self._file_table.setColumnWidth(4, 0)
        self._file_table._history_mode = False
        self._file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._file_table.setSelectionMode(QTableWidget.SingleSelection)
        self._file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._file_table.doubleClicked.connect(self._on_file_double_clicked)
        self._file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._file_table.customContextMenuRequested.connect(self._on_file_context_menu)
        playlist_layout.addWidget(self._file_table)
        self._right_stack.addWidget(playlist_page)

        right_layout.addWidget(self._right_stack)
        splitter.addWidget(right)

        splitter.setSizes([250, 550])
        return splitter

    def _build_bottom_panel(self):
        panel = QWidget()
        panel.setMinimumHeight(100)
        hbox = QHBoxLayout(panel)
        hbox.setContentsMargins(4, 4, 4, 4)
        hbox.setSpacing(8)

        self._lbl_cover = QLabel()
        self._lbl_cover.setFixedSize(90, 90)
        self._lbl_cover.setAlignment(Qt.AlignCenter)
        self._lbl_cover.setStyleSheet("background-color: #2a2a2a;")
        self._load_default_cover()
        hbox.addWidget(self._lbl_cover)

        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignCenter)

        song_font = QFont("Microsoft YaHei", 16, QFont.Bold)

        self._lbl_line1 = QLabel(I18n.t("main.label.no_track_playing"))
        self._lbl_line1.setFont(song_font)
        self._lbl_line1.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(self._lbl_line1)

        self._lbl_line2 = QLabel("")
        self._lbl_line2.setFont(song_font)
        self._lbl_line2.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(self._lbl_line2)

        self._lbl_line3 = QLabel("00:00 / 00:00")
        self._lbl_line3.setFont(song_font)
        self._lbl_line3.setAlignment(Qt.AlignCenter)
        self._lbl_line3.setStyleSheet("color: #aaa;")
        info_layout.addWidget(self._lbl_line3)

        hbox.addWidget(info, 1)

        self._vu_meter = VUMeter()
        hbox.addWidget(self._vu_meter)

        self._info_rotate_timer = QTimer(self)
        self._info_rotate_timer.timeout.connect(self._rotate_info)
        self._info_rotate_index = 0
        self._info_rotate_timer.start(4000)

        self._has_lyric = False
        self._current_lyric_index = -1
        self._current_song_id = ""
        self._lyric_active_color = "#32c864"
        self._lyric_inactive_color = "#999999"

        return panel

    def _load_default_cover(self):
        default_gif = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cover.gif")
        if os.path.exists(default_gif):
            if hasattr(self, '_cover_movie') and self._cover_movie:
                self._cover_movie.stop()
                self._cover_movie.deleteLater()
            self._lbl_cover.setPixmap(QPixmap())
            self._cover_movie = QMovie(default_gif)
            self._cover_movie.setCacheMode(QMovie.CacheAll)
            self._cover_movie.setScaledSize(self._lbl_cover.size())
            self._lbl_cover.setMovie(self._cover_movie)
            self._cover_movie.start()
        else:
            self._lbl_cover.setText(I18n.t("main.label.no_cover"))

    def _rotate_info(self):
        if self._has_lyric and not self._lyric_panel_visible:
            return
        if not self._current_metadata:
            return
        meta = self._current_metadata
        groups = []

        title = meta.get("title", "Unknown")
        artist = meta.get("artist", "")
        if artist and artist != "Unknown Artist":
            groups.append(f"{title} \u2014 {artist}")
        else:
            groups.append(title)

        codec_parts = []
        if meta.get("format"):
            codec_parts.append(meta["format"].upper())
        if meta.get("encoder"):
            codec_parts.append(meta["encoder"])
        source = meta.get("source", "")
        if source:
            codec_parts.append(f"Source: {source}")
        if codec_parts:
            groups.append("  ".join(codec_parts))

        br_parts = []
        if meta.get("bitrate"):
            br_parts.append(f"{meta['bitrate'] // 1000}kbps")
        channels = meta.get("channels", 0)
        if channels == 1:
            br_parts.append("Mono")
        elif channels == 2:
            br_parts.append("Stereo")
        elif channels > 2:
            br_parts.append(f"{channels}ch")
        if br_parts:
            groups.append("  ".join(br_parts))

        if not groups:
            return

        self._info_rotate_index = (self._info_rotate_index + 1) % len(groups)
        idx = self._info_rotate_index
        self._lbl_line1.setText(groups[idx])
        self._lbl_line2.setText(groups[(idx + 1) % len(groups)] if len(groups) > 1 else "")

    # ================================================================
    # Directory Tree
    # ================================================================

    def _populate_root_tree(self):
        my_music_root = QTreeWidgetItem(self._dir_tree, [I18n.t("main.tree.my_music")])
        my_music_root.setData(0, Qt.UserRole, {"type": "my_music_root"})
        my_music_root.setExpanded(True)

        fav_item = QTreeWidgetItem(my_music_root, [I18n.t("main.tree.favorites")])
        fav_item.setData(0, Qt.UserRole, {"type": "favorites"})

        playlist_root = QTreeWidgetItem(my_music_root, [I18n.t("main.tree.playlists")])
        playlist_root.setData(0, Qt.UserRole, {"type": "playlist_root"})
        self._populate_playlist_tree(playlist_root)

        genre_root = QTreeWidgetItem(my_music_root, [I18n.t("main.tree.genre")])
        genre_root.setData(0, Qt.UserRole, {"type": "genre_root"})
        self._populate_genre_tree(genre_root)

        history_item = QTreeWidgetItem(my_music_root, [I18n.t("main.tree.history")])
        history_item.setData(0, Qt.UserRole, {"type": "play_history"})

        drives_root = QTreeWidgetItem(self._dir_tree, [I18n.t("main.tree.local_drives")])
        drives_root.setData(0, Qt.UserRole, {"type": "root"})
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                item = QTreeWidgetItem(drives_root, [f"{letter}:"])
                item.setData(0, Qt.UserRole, {"type": "drive", "path": drive_path})
                QTreeWidgetItem(item, ["..."])

        cloud_root = QTreeWidgetItem(self._dir_tree, ["Cloud Storage"])
        cloud_root.setData(0, Qt.UserRole, {"type": "cloud_root"})
        self._populate_webdav_tree(cloud_root)

        self._dir_tree.expandItem(drives_root)

    def _populate_playlist_tree(self, playlist_root):
        playlist_root.takeChildren()
        playlists = self._music_library.get_playlists()
        for pl in playlists:
            name = pl.get("name", "")
            track_count = pl.get("track_count", 0)
            label = f"📂 {name}" if track_count == 0 else f"📂 {name} ({track_count})"
            pl_item = QTreeWidgetItem(playlist_root, [label])
            pl_item.setData(0, Qt.UserRole, {
                "type": "user_playlist",
                "playlist_id": pl["id"],
                "playlist_name": name,
            })

    def _populate_genre_tree(self, genre_root):
        genre_root.takeChildren()
        genres = self._music_library.get_genres()
        if not genres:
            empty = QTreeWidgetItem(genre_root, [I18n.t("main.tree.genre_empty")])
            empty.setData(0, Qt.UserRole, {"type": "genre_empty"})
        else:
            for g in genres:
                genre_name = g.get("genre", "Unknown")
                count = g.get("count", 0)
                g_item = QTreeWidgetItem(genre_root, [f"🎵 {genre_name} ({count})"])
                g_item.setData(0, Qt.UserRole, {
                    "type": "genre",
                    "genre": genre_name,
                })

    def _populate_webdav_tree(self, cloud_root):
        cloud_root.takeChildren()
        try:
            from src.business.webdav_account_manager import WebDAVAccountManager
            mgr = WebDAVAccountManager()
            accounts = mgr.get_all_accounts()
            for account in accounts:
                aid = account.get("id", "")
                name = account.get("name", "WebDAV")
                item = QTreeWidgetItem(cloud_root, [f"🌐 {name}"])
                item.setData(0, Qt.UserRole, {
                    "type": "webdav_root",
                    "account_id": aid,
                    "path": account.get("root_path", "/"),
                })
                QTreeWidgetItem(item, ["..."])
        except Exception as e:
            logger.warning(f"Failed to populate WebDAV tree: {e}")

    def _refresh_webdav_tree(self):
        for i in range(self._dir_tree.topLevelItemCount()):
            item = self._dir_tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "cloud_root":
                self._populate_webdav_tree(item)
                break

    def _refresh_playlist_tree(self):
        for i in range(self._dir_tree.topLevelItemCount()):
            item = self._dir_tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "my_music_root":
                for j in range(item.childCount()):
                    child = item.child(j)
                    cd = child.data(0, Qt.UserRole)
                    if cd and cd.get("type") == "playlist_root":
                        self._populate_playlist_tree(child)
                        break
                break

    def _on_dir_context_menu(self, pos):
        item = self._dir_tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        dtype = data.get("type", "")
        menu = QMenu(self)

        if dtype == "playlist_root":
            menu.addAction(I18n.t("main.action.create_playlist"), self._create_playlist_dialog)
            menu.exec(self._dir_tree.viewport().mapToGlobal(pos))
            return

        if dtype == "user_playlist":
            menu.addAction(I18n.t("main.action.create_playlist"), self._create_playlist_dialog)
            menu.addSeparator()
            menu.addAction(I18n.t("main.action.rename"), lambda: self._rename_playlist_dialog(data.get("playlist_id", 0), data.get("playlist_name", "")))
            menu.addAction(I18n.t("main.action.delete_playlist"), lambda: self._delete_playlist_confirm(data.get("playlist_id", 0), data.get("playlist_name", "")))
            menu.exec(self._dir_tree.viewport().mapToGlobal(pos))
            return

        if dtype == "play_history":
            menu.addAction(I18n.t("main.menu.clear_history"), self._clear_play_history_confirm)
            menu.exec(self._dir_tree.viewport().mapToGlobal(pos))
            return

        if dtype == "genre_root":
            menu.addAction(I18n.t("main.action.scan_genre"), self._scan_genre_dialog)
            menu.exec(self._dir_tree.viewport().mapToGlobal(pos))
            return

    def _create_playlist_dialog(self):
        from src.presentation.themed_dialog import ThemedInputDialog
        name, ok = ThemedInputDialog.getText(self, I18n.t("main.input.create_playlist_title"), I18n.t("main.input.create_playlist_label"))
        if ok and name.strip():
            self._music_library.create_playlist(name.strip())
            self._refresh_playlist_tree()

    def _rename_playlist_dialog(self, playlist_id: int, old_name: str):
        from src.presentation.themed_dialog import ThemedInputDialog
        name, ok = ThemedInputDialog.getText(self, I18n.t("main.dlg.rename_playlist"), I18n.t("main.dlg.new_name"), text=old_name)
        if ok and name.strip():
            self._music_library.rename_playlist(playlist_id, name.strip())
            self._refresh_playlist_tree()

    def _delete_playlist_confirm(self, playlist_id: int, name: str):
        log_msgbox("question", I18n.t("main.msg.delete_playlist_title"),
                   I18n.tf("main.msg.delete_playlist_body", name=name))
        reply = ThemedMessageBox.question(
            self, I18n.t("main.msg.delete_playlist_title"),
            I18n.tf("main.msg.delete_playlist_body", name=name),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no"
        )
        if reply == 1:
            self._music_library.delete_playlist(playlist_id)
            self._refresh_playlist_tree()
            self._file_table.setRowCount(0)

    def _clear_play_history_confirm(self):
        log_msgbox("question", I18n.t("main.msg.clear_history_title"), I18n.t("main.msg.clear_history_body"))
        reply = ThemedMessageBox.question(
            self, I18n.t("main.msg.clear_history_title"),
            I18n.t("main.msg.clear_history_body"),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no"
        )
        if reply == 1:
            self._music_library.clear_play_history()
            self._file_table.setRowCount(0)

    # ================================================================
    # My Music - File List Views
    # ================================================================

    def _set_history_mode(self, enabled: bool):
        self._file_table._history_mode = enabled
        if enabled:
            self._file_table.setColumnWidth(4, 130)
        else:
            self._file_table.setColumnWidth(4, 0)

    def _load_favorites_list(self):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._set_history_mode(False)
        self._file_table.setRowCount(0)

        favorites = self._music_library.get_favorites()
        playlist = []

        for fav in favorites:
            path = fav.get("path", "")
            if not path:
                continue
            title = fav.get("title", "") or os.path.splitext(os.path.basename(path))[0]
            artist = fav.get("artist", "") or ""
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title
            dur = fav.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            fmt = (fav.get("format") or "").upper()

            meta = {
                "path": path,
                "title": title,
                "artist": artist,
                "album": fav.get("album", ""),
                "duration": dur,
                "format": fmt.lower() if fmt else "",
            }

            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            name_item = QTableWidgetItem(f"⭐{display}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": path, "metadata": meta, "_favorite": True})
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            lyric_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)
            self._file_table.setItem(row, 4, QTableWidgetItem(""))

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)

        logger.info(f"Loaded favorites: {len(playlist)} tracks")

    def _load_playlist_overview(self):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._set_history_mode(False)
        self._file_table.setRowCount(0)

        playlists = self._music_library.get_playlists()
        for pl in playlists:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            name = pl.get("name", "")
            track_count = pl.get("track_count", 0)
            pl_item = QTableWidgetItem(f"📋 {name}")
            pl_item.setData(Qt.UserRole, {
                "type": "user_playlist",
                "playlist_id": pl["id"],
                "playlist_name": name,
            })
            pl_item.setForeground(QColor(tc.get("dir_color", "#6ab4ff")))
            self._file_table.setItem(row, 0, pl_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(str(track_count)))
            self._file_table.setItem(row, 2, QTableWidgetItem(""))
            self._file_table.setItem(row, 3, QTableWidgetItem(""))
            self._file_table.setItem(row, 4, QTableWidgetItem(""))

        logger.info(f"Loaded playlist overview: {len(playlists)} playlists")

    def _load_user_playlist(self, playlist_id: int):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._set_history_mode(False)
        self._file_table.setRowCount(0)

        items = self._music_library.get_playlist_items(playlist_id)
        playlist = []

        for item in items:
            path = item.get("path", "")
            if not path:
                continue
            title = item.get("title", "") or os.path.splitext(os.path.basename(path))[0]
            artist = item.get("artist", "") or ""
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title
            dur = item.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            fmt = (item.get("format") or "").upper()

            meta = {
                "path": path,
                "title": title,
                "artist": artist,
                "album": item.get("album", ""),
                "duration": dur,
                "format": fmt.lower() if fmt else "",
            }

            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
            name_item.setData(Qt.UserRole, {
                "type": "music",
                "path": path,
                "metadata": meta,
                "_playlist_item_id": item.get("id"),
                "_playlist_id": playlist_id,
            })
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            lyric_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)
            self._file_table.setItem(row, 4, QTableWidgetItem(""))

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)

        logger.info(f"Loaded playlist {playlist_id}: {len(playlist)} tracks")

    def _load_play_history(self):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._set_history_mode(True)
        self._file_table.setRowCount(0)

        history = self._music_library.get_play_history()
        playlist = []

        for rec in history:
            path = rec.get("path", "")
            if not path:
                continue
            title = rec.get("title", "") or os.path.splitext(os.path.basename(path))[0]
            artist = rec.get("artist", "") or ""
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title
            dur = rec.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            fmt = (rec.get("format") or "").upper()
            play_time = rec.get("play_time", "")

            meta = {
                "path": path,
                "title": title,
                "artist": artist,
                "album": rec.get("album", ""),
                "duration": dur,
                "format": fmt.lower() if fmt else "",
            }

            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": path, "metadata": meta})
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            lyric_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)
            time_item = QTableWidgetItem(play_time)
            time_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 4, time_item)

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)

        logger.info(f"Loaded play history: {len(playlist)} records")

    def _load_genre_overview(self):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._set_history_mode(False)
        self._file_table.setRowCount(0)

        beets_status = self._beets_service.get_status()
        if not beets_status.get("installed"):
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            hint_item = QTableWidgetItem(I18n.t("main.table.beets_not_installed"))
            hint_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 0, hint_item)
            for c in range(1, 5):
                self._file_table.setItem(row, c, QTableWidgetItem(""))
            return

        genres = self._music_library.get_genres()
        if not genres:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            hint_item = QTableWidgetItem(I18n.t("main.table.no_genre_data"))
            hint_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 0, hint_item)
            for c in range(1, 5):
                self._file_table.setItem(row, c, QTableWidgetItem(""))
            return

        for g in genres:
            genre_name = g.get("genre", "Unknown")
            count = g.get("count", 0)
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            g_item = QTableWidgetItem(f"🎵 {genre_name}")
            g_item.setData(Qt.UserRole, {"type": "genre", "genre": genre_name})
            g_item.setForeground(QColor(tc.get("dir_color", "#6ab4ff")))
            self._file_table.setItem(row, 0, g_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(str(count)))
            self._file_table.setItem(row, 2, QTableWidgetItem(""))
            self._file_table.setItem(row, 3, QTableWidgetItem(""))
            self._file_table.setItem(row, 4, QTableWidgetItem(""))

        logger.info(f"Loaded genre overview: {len(genres)} genres")

    def _load_genre_songs(self, genre: str):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._set_history_mode(False)
        self._file_table.setRowCount(0)

        songs = self._music_library.get_songs_by_genre(genre)
        playlist = []

        for song in songs:
            path = song.get("path", "")
            if not path or not os.path.exists(path):
                continue
            meta = self._metadata_service.read_metadata(path)
            title = meta.get("title", "") or os.path.splitext(os.path.basename(path))[0]
            artist = meta.get("artist", "") or ""
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title
            dur = meta.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            fmt = meta.get("format", "").upper()

            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": path, "metadata": meta})
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            lyric_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)
            self._file_table.setItem(row, 4, QTableWidgetItem(""))

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)

        logger.info(f"Loaded genre '{genre}': {len(playlist)} tracks")

    def _scan_genre_dialog(self):
        beets_status = self._beets_service.get_status()
        if not beets_status.get("installed"):
            log_msgbox("question", I18n.t("main.msg.install_beets_title"),
                       I18n.t("main.msg.install_beets_body"))
            reply = ThemedMessageBox.question(
                self, I18n.t("main.msg.install_beets_title"),
                I18n.t("main.msg.install_beets_body"),
                buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="yes"
            )
            if reply != 1:
                return
            pip_mirror = self._config_manager.get("Translation", "PIPMirror", "")
            success = self._beets_service.install(
                progress_callback=lambda msg, pct: logger.info(f"[Beets install] {msg} ({pct}%)"),
                mirror_url=pip_mirror,
            )
            if not success:
                log_msgbox("warning", I18n.t("main.msg.beets_install_failed_title"), I18n.t("main.msg.beets_install_failed_body"))
                ThemedMessageBox.warning(self, I18n.t("main.msg.beets_install_failed_title"), I18n.t("main.msg.beets_install_failed_body"))
                return

        folder = QFileDialog.getExistingDirectory(self, I18n.t("main.dialog.select_music_dir_for_scan"))
        if not folder:
            return

        from src.presentation.themed_dialog import ThemedProgressDialog
        self._beets_progress = ThemedProgressDialog(
            self, title=I18n.t("main.title.scan_genre"),
            label_text=I18n.t("main.progress.scanning_genre"),
            minimum=0, maximum=100
        )
        self._beets_progress.set_minimum_duration(0)
        self._beets_progress.set_value(0)
        self._beets_progress.show()

        def worker():
            success = self._beets_service.scan_directory(
                folder,
                progress_callback=lambda msg, pct: self._sig_beets_progress.emit(msg, pct),
            )
            self._sig_beets_done.emit(success)

        threading.Thread(target=worker, daemon=True).start()

    def _on_beets_progress(self, msg: str, pct: int):
        if hasattr(self, '_beets_progress') and self._beets_progress:
            self._beets_progress.set_label(msg)
            self._beets_progress.set_value(pct)

    def _on_beets_done(self, success: bool):
        if hasattr(self, '_beets_progress') and self._beets_progress:
            self._beets_progress.close()
            self._beets_progress = None

        if success:
            genre_root = self._find_genre_root()
            if genre_root:
                self._populate_genre_tree(genre_root)
            log_msgbox("info", I18n.t("main.msg.scan_complete_title"), I18n.t("main.msg.scan_complete_body"))
            ThemedMessageBox.information(self, I18n.t("main.msg.scan_complete_title"), I18n.t("main.msg.scan_complete_body"))
        else:
            log_msgbox("warning", I18n.t("main.msg.scan_failed_title"), I18n.t("main.msg.scan_failed_body"))
            ThemedMessageBox.warning(self, I18n.t("main.msg.scan_failed_title"), I18n.t("main.msg.scan_failed_body"))

    def _find_genre_root(self):
        for i in range(self._dir_tree.topLevelItemCount()):
            item = self._dir_tree.topLevelItem(i)
            data = item.data(0, Qt.UserRole)
            if data and data.get("type") == "my_music_root":
                for j in range(item.childCount()):
                    child = item.child(j)
                    cd = child.data(0, Qt.UserRole)
                    if cd and cd.get("type") == "genre_root":
                        return child
        return None

    def _on_dir_expanded(self, item):
        data = item.data(0, Qt.UserRole)
        if not data or data.get("type") == "root" or data.get("type") == "cloud_root":
            return
        if item.childCount() == 1 and item.child(0).text(0) == "...":
            dtype = data.get("type", "")
            if dtype.startswith("webdav"):
                self._populate_webdav_subtree(item)
            else:
                self._populate_tree_item(item)

    def _on_dir_clicked(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        dtype = data.get("type", "")

        if dtype == "my_music_root":
            return
        if dtype == "favorites":
            self._current_dir_type = "favorites"
            self._current_dir_extra = ""
            self._load_favorites_list()
            return
        if dtype == "playlist_root":
            self._current_dir_type = "playlist_root"
            self._current_dir_extra = ""
            self._load_playlist_overview()
            return
        if dtype == "user_playlist":
            self._current_dir_type = "user_playlist"
            self._current_dir_extra = str(data.get("playlist_id", 0))
            self._load_user_playlist(data.get("playlist_id", 0))
            return
        if dtype == "play_history":
            self._current_dir_type = "play_history"
            self._current_dir_extra = ""
            self._load_play_history()
            return
        if dtype == "genre_root":
            self._current_dir_type = "genre_root"
            self._current_dir_extra = ""
            self._load_genre_overview()
            return
        if dtype == "genre":
            self._current_dir_type = "genre"
            self._current_dir_extra = data.get("genre", "")
            self._load_genre_songs(data.get("genre", ""))
            return
        if dtype == "root" or dtype == "cloud_root":
            return

        path = data.get("path", "")

        if dtype.startswith("webdav"):
            if item.childCount() == 1 and item.child(0).text(0) == "...":
                self._populate_webdav_subtree(item)
            self._load_webdav_file_list(data.get("account_id", ""), path)
        else:
            if item.childCount() == 1 and item.child(0).text(0) == "...":
                self._populate_tree_item(item)
            self._current_folder = path
            self._current_dir_type = "folder"
            self._current_dir_extra = ""
            self._load_file_list_async(path)

    def _populate_tree_item(self, item):
        data = item.data(0, Qt.UserRole)
        path = data.get("path", "") if data else ""
        if not path:
            return

        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()

        item.takeChildren()
        subdirs = _list_subdirs(path)
        if not subdirs:
            empty = QTreeWidgetItem(item, ["(empty)"])
            empty.setForeground(0, QColor(tc.get("text_muted", "#666680")))
        else:
            for name, full_path in subdirs:
                child = QTreeWidgetItem(item, [name])
                child.setData(0, Qt.UserRole, {"type": "folder", "path": full_path})
                QTreeWidgetItem(child, ["..."])

    def _populate_webdav_subtree(self, item):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        account_id = data.get("account_id", "")
        path = data.get("path", "/")

        from src.infrastructure.theme_engine import ThemeEngine
        from src.infrastructure import webdav_cache
        tc = ThemeEngine().get_current_colors()

        try:
            from src.business.webdav_account_manager import WebDAVAccountManager
            from src.infrastructure.webdav_client import WebDAVClient
            mgr = WebDAVAccountManager()
            account = mgr.get_account(account_id)
            if not account:
                return

            cache_ttl = account.get("cache_ttl", 600)
            entries = webdav_cache.get(account_id, path, ttl=cache_ttl)
            if entries is None:
                entries = WebDAVClient.list_dir(
                    server_url=account["server_url"],
                    path=path,
                    username=account["username"],
                    password=account["password"],
                    timeout=account.get("timeout", 30),
                    verify_ssl=bool(account.get("verify_ssl", 0)),
                )
                if entries:
                    webdav_cache.put(account_id, path, entries)
        except Exception as e:
            logger.warning(f"WebDAV list_dir failed: {e}")
            entries = []

        item.takeChildren()
        dirs = [e for e in entries if e.is_dir]
        if not dirs:
            empty = QTreeWidgetItem(item, ["(empty)"])
            empty.setForeground(0, QColor(tc.get("text_muted", "#666680")))
        else:
            for entry in dirs:
                child = QTreeWidgetItem(item, [entry.name])
                child.setData(0, Qt.UserRole, {
                    "type": "webdav_dir",
                    "account_id": account_id,
                    "path": entry.path,
                })
                QTreeWidgetItem(child, ["..."])

    # ================================================================
    # File List (right panel)
    # ================================================================

    def _load_webdav_file_list(self, account_id: str, path: str, _retry: int = 0):
        from src.infrastructure.theme_engine import ThemeEngine
        from src.infrastructure import webdav_cache
        tc = ThemeEngine().get_current_colors()
        self._file_table.setRowCount(1)
        hint = QTableWidgetItem(I18n.t("main.table.loading"))
        hint.setForeground(QColor(tc.get("text_muted", "#666680")))
        self._file_table.setItem(0, 0, hint)
        for c in range(1, 5):
            self._file_table.setItem(0, c, QTableWidgetItem(""))

        try:
            from src.business.webdav_account_manager import WebDAVAccountManager
            from src.infrastructure.webdav_client import WebDAVClient
            mgr = WebDAVAccountManager()
            account = mgr.get_account(account_id)
            if not account:
                self._file_table.setRowCount(0)
                return

            cache_ttl = account.get("cache_ttl", 600)
            entries = webdav_cache.get(account_id, path, ttl=cache_ttl)
            if entries is None:
                entries = WebDAVClient.list_dir(
                    server_url=account["server_url"],
                    path=path,
                    username=account["username"],
                    password=account["password"],
                    timeout=account.get("timeout", 30),
                    verify_ssl=bool(account.get("verify_ssl", 0)),
                )
                if entries:
                    webdav_cache.put(account_id, path, entries)
        except Exception as e:
            logger.warning(f"WebDAV list_dir failed: {e}")
            entries = []

        if not entries and _retry < 1:
            import time
            time.sleep(0.5)
            return self._load_webdav_file_list(account_id, path, _retry=_retry + 1)

        self._file_table.setRowCount(0)

        if not entries:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            empty_item = QTableWidgetItem(I18n.t("main.table.webdav_error"))
            empty_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 0, empty_item)
            for c in range(1, 5):
                self._file_table.setItem(row, c, QTableWidgetItem(""))
            return

        playlist = []
        for entry in entries:
            if entry.is_dir:
                row = self._file_table.rowCount()
                self._file_table.insertRow(row)
                dir_item = QTableWidgetItem(f"\U0001F4C1 {entry.name}")
                dir_item.setData(Qt.UserRole, {
                    "type": "webdav_dir",
                    "account_id": account_id,
                    "path": entry.path,
                })
                dir_item.setForeground(QColor(tc.get("dir_color", "#6ab4ff")))
                self._file_table.setItem(row, 0, dir_item)
                for c in range(1, 5):
                    self._file_table.setItem(row, c, QTableWidgetItem(""))
                continue

            if not entry.is_audio and not entry.is_playlist:
                continue

            if entry.is_playlist:
                row = self._file_table.rowCount()
                self._file_table.insertRow(row)
                pl_item = QTableWidgetItem(f"\U0001F4CB {entry.name}")
                pl_item.setData(Qt.UserRole, {
                    "type": "webdav_playlist",
                    "account_id": account_id,
                    "path": entry.path,
                })
                pl_item.setForeground(QColor(tc.get("dir_color", "#6ab4ff")))
                self._file_table.setItem(row, 0, pl_item)
                self._file_table.setItem(row, 1, QTableWidgetItem(""))
                self._file_table.setItem(row, 2, QTableWidgetItem("M3U"))
                self._file_table.setItem(row, 3, QTableWidgetItem(""))
                continue

            file_url = WebDAVClient.get_file_url(account["server_url"], entry.path)
            auth_header = WebDAVClient.build_auth_header(account["username"], account["password"])

            cached = webdav_cache.get_download_url(account_id, entry.path)
            if cached:
                direct_url, is_direct = cached
            else:
                direct_url = None
                is_direct = False

                preset = account.get("preset", "")
                if preset == "alist" or "/dav" in account["server_url"].lower():
                    try:
                        from src.infrastructure.alist_client import AListClient
                        alist_base = account["server_url"].rstrip("/")
                        if alist_base.endswith("/dav"):
                            alist_base = alist_base[:-4]
                        token = AListClient.login(alist_base, account["username"], account["password"])
                        if token:
                            alist_url = AListClient.get_download_url(alist_base, entry.path, token)
                            if alist_url:
                                direct_url = alist_url
                                is_direct = True
                    except Exception as e:
                        logger.debug(f"AList API fallback to WebDAV: {e}")

                if not direct_url:
                    try:
                        direct_url, is_direct = WebDAVClient.get_download_url(
                            server_url=account["server_url"],
                            path=entry.path,
                            username=account["username"],
                            password=account["password"],
                            timeout=account.get("timeout", 30),
                            verify_ssl=bool(account.get("verify_ssl", 0)),
                        )
                    except Exception:
                        direct_url = file_url
                        is_direct = False

                if direct_url:
                    webdav_cache.put_download_url(account_id, entry.path, direct_url, is_direct)

            play_url = direct_url if is_direct else file_url
            play_auth = "" if is_direct else auth_header

            meta = {
                "path": play_url,
                "title": os.path.splitext(entry.name)[0],
                "duration": -1,
                "format": entry.ext.lstrip("."),
                "artist": "",
                "is_url": True,
                "_auth_header": play_auth,
                "_source": "webdav",
                "_account_id": account_id,
                "_original_url": file_url,
                "_is_direct_link": is_direct,
            }

            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            name_item = QTableWidgetItem(f"\U0001F310 {entry.name}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": file_url, "metadata": meta})
            self._file_table.setItem(row, 0, name_item)

            size_str = ""
            if entry.size > 0:
                if entry.size >= 1048576:
                    size_str = f"{entry.size / 1048576:.1f}MB"
                else:
                    size_str = f"{entry.size / 1024:.0f}KB"
            self._file_table.setItem(row, 1, QTableWidgetItem(size_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(entry.ext.lstrip(".").upper()))
            lyric_item = QTableWidgetItem("✓")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            _tc = ThemeEngine().get_current_colors()
            lyric_item.setForeground(QColor(_tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)

        logger.info(f"WebDAV file list: {len(playlist)} audio files in {path}")

    def _load_webdav_playlist(self, account_id: str, path: str):
        from src.infrastructure.theme_engine import ThemeEngine
        from src.business.webdav_account_manager import WebDAVAccountManager
        from src.infrastructure.webdav_client import WebDAVClient
        tc = ThemeEngine().get_current_colors()

        try:
            mgr = WebDAVAccountManager()
            account = mgr.get_account(account_id)
            if not account:
                return

            content = WebDAVClient.download_text(
                server_url=account["server_url"],
                path=path,
                username=account["username"],
                password=account["password"],
                timeout=account.get("timeout", 30),
                verify_ssl=bool(account.get("verify_ssl", 0)),
            )
        except Exception as e:
            logger.warning(f"WebDAV download playlist failed: {e}")
            content = None

        if not content:
            log_msgbox("info", I18n.t("main.msg.playlist_download_failed_title"), I18n.t("main.msg.playlist_download_failed_body"))
            ThemedMessageBox.information(self, I18n.t("main.msg.playlist_download_failed_title"), I18n.t("main.msg.playlist_download_failed_body"))
            return

        auth_header = WebDAVClient.build_auth_header(account["username"], account["password"])
        playlist_dir_path = os.path.dirname(path.rstrip("/"))

        entries = []
        ext_inf = {}
        for line in content.splitlines():
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

            entry_path = line
            is_url = entry_path.startswith(("http://", "https://", "ftp://"))

            if not is_url:
                if not entry_path.startswith("/"):
                    base_dir = playlist_dir_path
                    entry_path = base_dir.rstrip("/") + "/" + entry_path
                entry_path = os.path.normpath(entry_path).replace("\\", "/")

            file_url = entry_path if is_url else WebDAVClient.get_file_url(account["server_url"], entry_path)

            ext = os.path.splitext(entry_path)[1].lower()
            if ext not in SUPPORTED_AUDIO_FORMATS and not is_url:
                continue

            meta = {
                "path": file_url,
                "title": ext_inf.get("title", os.path.splitext(os.path.basename(entry_path))[0]),
                "duration": ext_inf.get("duration", -1),
                "format": ext.lstrip(".") if ext else "url",
                "artist": "",
                "is_url": True,
                "_auth_header": auth_header,
                "_source": "webdav",
                "_account_id": account_id,
            }
            entries.append(meta)
            ext_inf = {}

        self._file_table.setRowCount(0)
        playlist = []
        for meta in entries:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)

            title = meta.get("title", "Unknown")
            artist = meta.get("artist", "")
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title

            dur = meta.get("duration", -1)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur >= 0 else ""
            fmt = meta.get("format", "").upper()

            name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": meta["path"], "metadata": meta})
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            lyric_item.setForeground(QColor(tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)
            self._playback_manager.play_local_at(0)

        logger.info(f"Loaded WebDAV playlist: {path} ({len(playlist)} tracks)")

    def _load_file_list_async(self, folder):
        self._file_list_version += 1
        version = self._file_list_version

        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()

        self._file_table.setRowCount(1)
        hint = QTableWidgetItem("Loading...")
        hint.setForeground(QColor(tc.get("text_muted", "#666680")))
        self._file_table.setItem(0, 0, hint)
        for c in range(1, 5):
            self._file_table.setItem(0, c, QTableWidgetItem(""))

        def worker():
            dirs, files = _list_music_and_dirs(folder)
            if version != self._file_list_version:
                return

            music_metadata = []
            for name, fpath in files:
                try:
                    ext = os.path.splitext(fpath)[1].lower()
                    if ext in PLAYLIST_FORMATS:
                        from src.infrastructure.playlist_parser import parse_playlist_with_meta
                        entries = parse_playlist_with_meta(fpath)
                        if entries:
                            music_metadata.append({
                                "path": fpath,
                                "title": os.path.basename(fpath),
                                "duration": 0,
                                "format": "m3u",
                                "artist": "",
                                "is_playlist": True,
                                "track_count": len(entries),
                            })
                        else:
                            music_metadata.append({
                                "path": fpath,
                                "title": os.path.basename(fpath),
                                "duration": 0,
                                "format": "m3u",
                                "artist": "",
                                "is_playlist": True,
                                "track_count": 0,
                            })
                    else:
                        meta = self._metadata_service.read_metadata(fpath)
                        music_metadata.append(meta)
                except Exception:
                    music_metadata.append({"path": fpath, "title": name, "duration": 0, "format": "", "artist": ""})

            self.file_list_loaded.emit(folder, dirs, music_metadata)

        threading.Thread(target=worker, daemon=True).start()

    def _on_file_list_loaded(self, folder, dirs, music_metadata):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._file_table.setRowCount(0)

        for name, fpath in dirs:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            dir_item = QTableWidgetItem(f"\U0001F4C1 {name}")
            dir_item.setData(Qt.UserRole, {"type": "dir", "path": fpath})
            dir_item.setForeground(QColor(tc.get("dir_color", "#6ab4ff")))
            self._file_table.setItem(row, 0, dir_item)
            for c in range(1, 5):
                self._file_table.setItem(row, c, QTableWidgetItem(""))

        playlist = []
        for meta in music_metadata:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)

            song_path = meta.get("path", "")
            is_pl = meta.get("is_playlist", False)

            if is_pl:
                pl_item = QTableWidgetItem(f"\U0001F4CB {os.path.basename(song_path)}")
                pl_item.setData(Qt.UserRole, {"type": "playlist", "path": song_path})
                pl_item.setForeground(QColor(tc.get("dir_color", "#6ab4ff")))
                self._file_table.setItem(row, 0, pl_item)
                self._file_table.setItem(row, 1, QTableWidgetItem(""))
                self._file_table.setItem(row, 2, QTableWidgetItem("M3U"))
                self._file_table.setItem(row, 3, QTableWidgetItem(""))
                continue

            title = meta.get("title", "Unknown")
            artist = meta.get("artist", "")
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title

            dur = meta.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}"
            fmt = meta.get("format", "").upper()

            title = meta.get("title", "")
            artist = meta.get("artist", "")
            has_lyric = self._lyric_manager.has_local_lyric(song_path) or self._lyric_manager.has_lyric_in_db(title, artist)

            name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": song_path, "metadata": meta})
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓" if has_lyric else "✗")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            from src.infrastructure.theme_engine import ThemeEngine
            _tc = ThemeEngine().get_current_colors()
            if has_lyric:
                lyric_item.setForeground(QColor(_tc.get("success", "#32c864")))
            else:
                lyric_item.setForeground(QColor(_tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)

        logger.info(f"File list: {len(dirs)} dirs, {len(music_metadata)} songs in {folder}")

    def _on_file_double_clicked(self, index):
        item = self._file_table.item(index.row(), 0)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return

        dtype = data.get("type")
        if dtype == "dir":
            self._navigate_to_dir(data["path"])
        elif dtype == "webdav_dir":
            self._load_webdav_file_list(data["account_id"], data["path"])
        elif dtype == "playlist":
            self._load_playlist_file(data["path"])
        elif dtype == "webdav_playlist":
            self._load_webdav_playlist(data["account_id"], data["path"])
        elif dtype == "user_playlist":
            self._load_user_playlist(data.get("playlist_id", 0))
        elif dtype == "genre":
            self._load_genre_songs(data.get("genre", ""))
        elif dtype == "music":
            self._play_file_at_row(index.row())

    def _get_selected_file_data(self):
        rows = self._file_table.selectionModel().selectedRows()
        if not rows:
            return None, -1
        row = rows[0].row()
        item = self._file_table.item(row, 0)
        if not item:
            return None, -1
        data = item.data(Qt.UserRole)
        return data, row

    def _on_file_context_menu(self, pos):
        data, row = self._get_selected_file_data()
        if not data:
            return

        if data.get("type") == "playlist":
            menu = QMenu(self)
            menu.addAction(I18n.t("main.menu.load_playlist"), lambda: self._load_playlist_file(data["path"]))
            menu.addSeparator()
            pl_path = data["path"]
            if os.path.isfile(pl_path):
                menu.addAction(I18n.t("main.action.browse_file_location"), lambda: subprocess.Popen(f'explorer /select,"{pl_path}"'))
            menu.exec(self._file_table.viewport().mapToGlobal(pos))
            return

        if data.get("type") == "webdav_playlist":
            menu = QMenu(self)
            menu.addAction(I18n.t("main.action.load_playlist"), lambda: self._load_webdav_playlist(data["account_id"], data["path"]))
            menu.exec(self._file_table.viewport().mapToGlobal(pos))
            return

        if data.get("type") == "user_playlist":
            menu = QMenu(self)
            menu.addAction(I18n.t("main.action.open_playlist"), lambda: self._load_user_playlist(data.get("playlist_id", 0)))
            menu.exec(self._file_table.viewport().mapToGlobal(pos))
            return

        if data.get("type") == "genre":
            menu = QMenu(self)
            menu.addAction(I18n.t("main.menu.view_songs"), lambda: self._load_genre_songs(data.get("genre", "")))
            menu.exec(self._file_table.viewport().mapToGlobal(pos))
            return

        if data.get("type") == "webdav_dir":
            menu = QMenu(self)
            menu.addAction(I18n.t("main.action.open_directory"), lambda: self._load_webdav_file_list(data["account_id"], data["path"]))
            menu.exec(self._file_table.viewport().mapToGlobal(pos))
            return

        if data.get("type") != "music":
            return

        meta = data.get("metadata", {})
        is_webdav = meta.get("_source") == "webdav"
        file_path = meta.get("path", "")

        if not is_webdav and file_path:
            meta = self._metadata_service.read_metadata(file_path)

        menu = QMenu(self)

        title = meta.get("title", "Unknown")
        artist = meta.get("artist", "Unknown Artist")
        album = meta.get("album", "")
        track = meta.get("track", "")
        duration = meta.get("duration", 0)
        fmt = meta.get("format", "").upper()
        bitrate = meta.get("bitrate", 0)
        channels = meta.get("channels", 0)
        encoder = meta.get("encoder", "")
        sample_rate = meta.get("sample_rate", "")

        if is_webdav:
            meta_items = [I18n.tf("main.meta.title", value=title)]
            if artist and artist != "Unknown Artist":
                meta_items.append(I18n.tf("main.meta.artist", value=artist))
            meta_items.append(I18n.tf("main.meta.format", value=fmt))
            meta_items.append(I18n.t("main.meta.source_webdav"))
        else:
            meta_items = [I18n.tf("main.meta.title", value=title), I18n.tf("main.meta.artist", value=artist)]
            if album:
                meta_items.append(I18n.tf("main.meta.album", value=album))
            if track:
                meta_items.append(I18n.tf("main.meta.track", value=track))
            meta_items.append(I18n.tf("main.meta.duration", value=f"{int(duration) // 60}:{int(duration) % 60:02d}"))
            meta_items.append(I18n.tf("main.meta.format", value=fmt))
            if bitrate:
                meta_items.append(I18n.tf("main.meta.bitrate", value=bitrate // 1000))
            if channels:
                ch_str = "Mono" if channels == 1 else "Stereo" if channels == 2 else f"{channels}ch"
                meta_items.append(I18n.tf("main.meta.channels", value=ch_str))
            if encoder:
                meta_items.append(I18n.tf("main.meta.encoder", value=encoder))
            if sample_rate:
                meta_items.append(I18n.tf("main.meta.sample_rate", value=sample_rate))

        for text in meta_items:
            act = menu.addAction(text)
            act.setEnabled(False)

        menu.addSeparator()
        if not is_webdav:
            menu.addAction(I18n.t("main.menu.copy_to_dots"), self._ctx_copy_to)
            menu.addAction(I18n.t("main.action.delete"), self._ctx_delete)
            menu.addAction(I18n.t("main.menu.rename"), self._ctx_rename)
            menu.addAction(I18n.t("main.action.move_to"), self._ctx_move_to)
            menu.addSeparator()
            if self._music_library.is_favorite(file_path):
                menu.addAction(I18n.t("main.action.remove_from_favorites"), self._ctx_remove_from_favorites)
            else:
                menu.addAction(I18n.t("main.action.add_to_favorites"), self._ctx_add_to_favorites)
            add_to_pl_menu = menu.addMenu(I18n.t("main.menu.add_to_playlist"))
            playlists = self._music_library.get_playlists()
            for pl in playlists:
                pl_id = pl["id"]
                pl_name = pl.get("name", "")
                add_to_pl_menu.addAction(pl_name, lambda checked=False, pid=pl_id: self._ctx_add_to_playlist(pid))
            menu.addAction(I18n.t("main.action.browse_track_location"), self._ctx_browse_location)
            menu.addSeparator()
            menu.addAction(I18n.t("main.action.search_lyric"), self._ctx_search_lyric)

        item_data = data
        if item_data.get("_playlist_id"):
            menu.addSeparator()
            menu.addAction(I18n.t("main.action.remove_from_playlist"), self._ctx_remove_from_playlist)

        menu.addAction(I18n.t("main.menu.play"), self._ctx_play)
        menu.addAction(I18n.t("main.action.skip"), self._ctx_skip)
        menu.addAction(I18n.t("main.menu.next"), self._ctx_next)
        menu.addAction(I18n.t("main.action.select"), self._ctx_select)

        menu.exec(self._file_table.viewport().mapToGlobal(pos))

    def _ctx_copy_to(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        src = meta.get("path", "")
        if not src or not os.path.exists(src):
            return
        folder = QFileDialog.getExistingDirectory(self, I18n.t("main.dialog.copy_to"))
        if folder:
            import shutil
            try:
                shutil.copy2(src, folder)
                log_msgbox("info", I18n.t("main.msg.copy_complete_title"), I18n.tf("main.msg.copy_complete_body", folder=folder))
                ThemedMessageBox.information(self, I18n.t("main.msg.copy_complete_title"), I18n.tf("main.msg.copy_complete_body", folder=folder))
            except Exception as e:
                log_msgbox("warning", I18n.t("main.msg.copy_failed_title"), I18n.tf("main.msg.copy_failed_body", error=e))
                ThemedMessageBox.warning(self, I18n.t("main.msg.copy_failed_title"), I18n.tf("main.msg.copy_failed_body", error=e))

    def _ctx_delete(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        src = meta.get("path", "")
        if not src or not os.path.exists(src):
            return
        name = os.path.basename(src)
        log_msgbox("question", I18n.t("main.msg.confirm_delete_title"), I18n.tf("main.msg.confirm_delete_body", name=name))
        reply = ThemedMessageBox.question(self, I18n.t("main.msg.confirm_delete_title"), I18n.tf("main.msg.confirm_delete_body", name=name),
                                     buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no")
        if reply == 1:
            try:
                import send2trash
                send2trash.send2trash(src)
            except ImportError:
                os.remove(src)
            self._file_table.removeRow(row)

    def _ctx_rename(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        src = meta.get("path", "")
        if not src or not os.path.exists(src):
            return
        old_name = os.path.basename(src)
        from src.presentation.themed_dialog import ThemedInputDialog
        new_name, ok = ThemedInputDialog.getText(self, I18n.t("main.input.rename_file_title"), I18n.t("main.input.rename_file_label"), text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(src), new_name)
            try:
                os.rename(src, new_path)
                meta["path"] = new_path
                data["path"] = new_path
                item = self._file_table.item(row, 0)
                if item:
                    item.setData(Qt.UserRole, data)
                    display = new_name
                    title = meta.get("title", "Unknown")
                    artist = meta.get("artist", "")
                    if artist and artist != "Unknown Artist":
                        display = f"{artist} - {title}"
                    item.setText(f"\U0001F3B5 {display}")
            except Exception as e:
                log_msgbox("warning", I18n.t("main.msg.rename_failed_title"), I18n.tf("main.msg.rename_failed_body", error=e))
                ThemedMessageBox.warning(self, I18n.t("main.msg.rename_failed_title"), I18n.tf("main.msg.rename_failed_body", error=e))

    def _ctx_move_to(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        src = meta.get("path", "")
        if not src or not os.path.exists(src):
            return
        folder = QFileDialog.getExistingDirectory(self, I18n.t("main.dlg.move_to"))
        if folder:
            import shutil
            try:
                shutil.move(src, folder)
                self._file_table.removeRow(row)
                log_msgbox("info", I18n.t("main.msg.move_complete_title"), I18n.tf("main.msg.move_complete_body", folder=folder))
                ThemedMessageBox.information(self, I18n.t("main.msg.move_complete_title"), I18n.tf("main.msg.move_complete_body", folder=folder))
            except Exception as e:
                log_msgbox("warning", I18n.t("main.msg.move_failed_title"), I18n.tf("main.msg.move_failed_body", error=e))
                ThemedMessageBox.warning(self, I18n.t("main.msg.move_failed_title"), I18n.tf("main.msg.move_failed_body", error=e))

    def _ctx_add_to_favorites(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        file_path = meta.get("path", "")
        if file_path:
            self._music_library.add_favorite(file_path, meta)

    def _ctx_remove_from_favorites(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        file_path = meta.get("path", "")
        if file_path:
            self._music_library.remove_favorite(file_path)
            if data.get("_favorite"):
                self._file_table.removeRow(row)

    def _ctx_add_to_playlist(self, playlist_id: int):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        file_path = meta.get("path", "")
        if file_path:
            self._music_library.add_to_playlist(playlist_id, file_path, meta)
            self._refresh_playlist_tree()

    def _ctx_remove_from_playlist(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        playlist_id = data.get("_playlist_id")
        item_id = data.get("_playlist_item_id")
        if playlist_id and item_id:
            self._music_library.remove_from_playlist(playlist_id, item_id)
            self._file_table.removeRow(row)
            self._refresh_playlist_tree()

    def _ctx_browse_location(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        file_path = meta.get("path", "")
        if file_path and os.path.exists(file_path):
            import subprocess
            folder = os.path.dirname(file_path)
            subprocess.Popen(f'explorer /select,"{file_path}"')

    def _ctx_search_lyric(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        file_path = meta.get("path", "")
        if file_path:
            meta = self._metadata_service.read_metadata(file_path)
        self._show_lyric_select_dialog(meta)

    def _ctx_play(self):
        data, row = self._get_selected_file_data()
        if not data or data.get("type") != "music":
            return
        self._play_file_at_row(row)

    def _ctx_skip(self):
        self._next_track()

    def _ctx_next(self):
        self._next_track()

    def _ctx_select(self):
        data, row = self._get_selected_file_data()
        if not data:
            return
        self._file_table.selectRow(row)

    def _play_file_at_row(self, row):
        item = self._file_table.item(row, 0)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data or data.get("type") != "music":
            return
        meta = data.get("metadata", {})
        song_path = meta.get("path", "")
        if song_path:
            skip_count = 0
            for r in range(self._file_table.rowCount()):
                ri = self._file_table.item(r, 0)
                if ri:
                    rd = ri.data(Qt.UserRole)
                    if rd and rd.get("type") in ("dir", "playlist", "webdav_dir", "webdav_playlist", "user_playlist", "genre"):
                        skip_count += 1
                    if rd and rd.get("type") == "music":
                        break
            play_index = row - skip_count
            if play_index >= 0:
                self._playback_manager.play_local_at(play_index)

    def _navigate_to_dir(self, path):
        self._current_folder = path
        self._load_file_list_async(path)
        self._select_tree_item_by_path(path)

    def _load_playlist_file(self, file_path: str):
        from src.infrastructure.playlist_parser import parse_playlist_with_meta
        entries = parse_playlist_with_meta(file_path)
        if not entries:
            log_msgbox("info", I18n.t("main.msg.playlist_empty_title"), I18n.t("main.msg.playlist_empty_body"))
            ThemedMessageBox.information(self, I18n.t("main.msg.playlist_empty_title"), I18n.t("main.msg.playlist_empty_body"))
            return

        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._file_table.setRowCount(0)

        playlist = []
        for meta in entries:
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)

            song_path = meta.get("path", "")
            is_url = meta.get("is_url", False)
            title = meta.get("title", "Unknown")
            artist = meta.get("artist", "")
            display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title

            dur = meta.get("duration", -1)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur >= 0 else ""
            fmt = meta.get("format", "").upper()
            if is_url:
                fmt = "HLS" if song_path.lower().endswith(".m3u8") else "URL"

            if not is_url:
                has_lyric = self._lyric_manager.has_local_lyric(song_path) or self._lyric_manager.has_lyric_in_db(title, artist)
            else:
                has_lyric = False

            name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
            name_item.setData(Qt.UserRole, {"type": "music", "path": song_path, "metadata": meta})
            self._file_table.setItem(row, 0, name_item)
            self._file_table.setItem(row, 1, QTableWidgetItem(dur_str))
            self._file_table.setItem(row, 2, QTableWidgetItem(fmt))
            lyric_item = QTableWidgetItem("✓" if has_lyric else "✗")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            _tc = ThemeEngine().get_current_colors()
            if has_lyric:
                lyric_item.setForeground(QColor(_tc.get("success", "#32c864")))
            else:
                lyric_item.setForeground(QColor(_tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)

            playlist.append(meta)

        self._playback_manager.clear_playlist()
        if playlist:
            self._playback_manager.set_playlist(playlist)
            self._playback_manager.play_local_at(0)

        logger.info(f"Loaded playlist: {file_path} ({len(playlist)} tracks)")

    def _select_tree_item_by_path(self, target_path):
        target_path = os.path.normpath(target_path)
        drive = os.path.splitdrive(target_path)[0]
        if not drive:
            return
        drive_item = self._find_tree_item_by_data(self._dir_tree.invisibleRootItem(), "path", drive + "\\")
        if not drive_item:
            return
        parts = target_path[len(drive):].strip(os.sep).split(os.sep)
        current_item = drive_item
        current_path = drive + "\\"
        for part in parts:
            if not part:
                continue
            if current_item.childCount() == 1 and current_item.child(0).text(0) == "...":
                self._populate_tree_item(current_item)
            found = False
            for i in range(current_item.childCount()):
                child = current_item.child(i)
                data = child.data(0, Qt.UserRole)
                if data and os.path.normpath(data.get("path", "")) == os.path.normpath(os.path.join(current_path, part)):
                    current_item = child
                    current_path = os.path.join(current_path, part)
                    found = True
                    break
            if not found:
                break
        self._dir_tree.setCurrentItem(current_item)
        self._dir_tree.expandItem(current_item)
        parent = current_item.parent()
        while parent:
            self._dir_tree.expandItem(parent)
            parent = parent.parent()

    def _find_tree_item_by_data(self, parent, key, value):
        for i in range(parent.childCount()):
            child = parent.child(i)
            data = child.data(0, Qt.UserRole)
            if data and data.get(key) == value:
                return child
            if child.childCount() > 0:
                result = self._find_tree_item_by_data(child, key, value)
                if result:
                    return result
        return None

    def _select_tree_item_by_type(self, type_name):
        item = self._find_tree_item_by_data(self._dir_tree.invisibleRootItem(), "type", type_name)
        if item:
            self._dir_tree.setCurrentItem(item)
            parent = item.parent()
            while parent:
                self._dir_tree.expandItem(parent)
                parent = parent.parent()

    def _select_tree_item_by_type_and_extra(self, type_name, extra_key, extra_value):
        root = self._dir_tree.invisibleRootItem()
        item = self._find_tree_item_by_type_and_extra(root, type_name, extra_key, extra_value)
        if item:
            self._dir_tree.setCurrentItem(item)
            parent = item.parent()
            while parent:
                self._dir_tree.expandItem(parent)
                parent = parent.parent()

    def _find_tree_item_by_type_and_extra(self, parent, type_name, extra_key, extra_value):
        for i in range(parent.childCount()):
            child = parent.child(i)
            data = child.data(0, Qt.UserRole)
            if data and data.get("type") == type_name:
                ev = data.get(extra_key)
                if str(ev) == str(extra_value):
                    return child
            if child.childCount() > 0:
                result = self._find_tree_item_by_type_and_extra(child, type_name, extra_key, extra_value)
                if result:
                    return result
        return None

    # ================================================================
    # Menu / Shortcuts / Timer
    # ================================================================

    def _init_event_handlers(self):
        self._event_bus.subscribe(EVENT_PLAYBACK_STATE_CHANGED, self._on_playback_state_changed)
        self._event_bus.subscribe(EVENT_TRACK_CHANGED, self._on_track_changed)
        self._event_bus.subscribe(EVENT_LYRIC_LOADED, self._on_lyric_loaded)
        self._event_bus.subscribe(EVENT_PLAY_FAILED, self._on_play_failed)
        self.position_changed.connect(self._update_position)
        self._playback_manager.register_position_callback(self._on_position_update)

    def _init_shortcuts(self):
        self._shortcuts = {}
        self._shortcut_actions = {
            "PlayPause": self._pause,
            "Stop": self._stop,
            "PrevTrack": self._previous_track,
            "NextTrack": self._next_track,
            "SeekBackward": self._seek_backward,
            "SeekForward": self._seek_forward,
            "VolumeUp": lambda: self._adjust_volume(5),
            "VolumeDown": lambda: self._adjust_volume(-5),
            "ToggleLyric": self._cycle_lyric_state,
            "ToggleSource": lambda: self._btn_source.click(),
            "ToggleMini": self._toggle_mini_mode,
            "ToggleSettings": self._toggle_settings_panel,
            "OpenFile": self._add_files,
        }
        self._load_shortcuts()
        self._f1_shortcut = QShortcut(QKeySequence(Qt.Key_F1), self)
        self._f1_shortcut.setContext(Qt.ApplicationShortcut)
        self._f1_shortcut.activated.connect(self._toggle_help)

    def _load_shortcuts(self):
        for sid, old_sc in self._shortcuts.items():
            old_sc.setEnabled(False)
            old_sc.deleteLater()
        self._shortcuts.clear()

        for action_id, callback in self._shortcut_actions.items():
            key_str = self._config_manager.get("Shortcuts", action_id, "")
            if not key_str:
                continue
            key_seq = QKeySequence(key_str)
            if key_seq.isEmpty():
                continue
            sc = QShortcut(key_seq, self, callback)
            sc.setContext(Qt.ApplicationShortcut)
            self._shortcuts[action_id] = sc

    def _rebind_shortcut(self, action_id, key_str):
        old_sc = self._shortcuts.get(action_id)
        if old_sc:
            old_sc.setEnabled(False)
            old_sc.deleteLater()
            del self._shortcuts[action_id]

        key_seq = QKeySequence(key_str)
        if key_seq.isEmpty():
            return
        callback = self._shortcut_actions.get(action_id)
        if not callback:
            return
        sc = QShortcut(key_seq, self, callback)
        sc.setContext(Qt.ApplicationShortcut)
        self._shortcuts[action_id] = sc

    def _init_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_ui)

    def _connect_online_signals(self):
        self._online_music_panel.search_requested.connect(self._on_online_search)
        self._online_music_panel.download_requested.connect(self._on_online_download)
        self._online_music_panel.play_requested.connect(self._on_online_play)
        self._online_music_panel.play_online_list_requested.connect(self._on_online_play_list)
        self._online_music_panel.play_with_mode_requested.connect(self._on_online_play_with_mode)
        self._settings_panel.source_plugin_install_requested.connect(self._on_plugin_install)
        self._settings_panel.source_plugin_enable_requested.connect(self._on_plugin_enable)
        self._settings_panel.source_plugin_delete_requested.connect(self._on_plugin_delete)
        self._search_service.search_completed.connect(self._online_music_panel.set_search_results)
        self._search_service.search_error.connect(lambda e: logger.warning(f"Search error: {e}"))
        self._settings_panel.settings_changed.connect(self._on_settings_changed)
        self._playback_manager.set_online_url_callback(self._get_online_url)

    def _on_online_search(self, keyword, page, limit):
        self._search_service.search(keyword, page, limit)

    def _on_online_download(self, song_data, quality):
        task_id = self._download_service.add_task(song_data, quality)
        self._download_service.start_queue()

    def _on_online_play(self, song_data):
        plugin_id = song_data.get("pluginId", "")
        song_id = song_data.get("id") or song_data.get("songmid") or song_data.get("hash", "")
        if not plugin_id or not song_id:
            return
        self._show_download_hint(song_data.get("title", ""))
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        plugin = pm.get_plugin(plugin_id)
        if not plugin:
            self._hide_download_hint()
            return
        import threading
        ctx = {"song_data": song_data, "mode": "single"}
        t = threading.Thread(target=self._async_get_url, args=(plugin, song_id, ctx), daemon=True)
        t.start()

    def _on_online_play_list(self, songs: list, index: int):
        if not songs or index < 0 or index >= len(songs):
            return
        song_data = songs[index]
        plugin_id = song_data.get("pluginId", "")
        song_id = song_data.get("id") or song_data.get("songmid") or song_data.get("hash", "")
        if not plugin_id or not song_id:
            return

        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        plugin = pm.get_plugin(plugin_id)
        if not plugin:
            return

        self._show_download_hint(song_data.get("title", ""))
        import threading
        ctx = {"song_data": song_data, "songs": songs, "index": index, "mode": "play_list"}
        t = threading.Thread(target=self._async_get_url, args=(plugin, song_id, ctx), daemon=True)
        t.start()

    def _on_online_play_with_mode(self, song_data: dict, all_songs: list, mode: str):
        plugin_id = song_data.get("pluginId", "")
        song_id = song_data.get("id") or song_data.get("songmid") or song_data.get("hash", "")
        if not plugin_id or not song_id:
            return
        self._show_download_hint(song_data.get("title", ""))
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        plugin = pm.get_plugin(plugin_id)
        if not plugin:
            self._hide_download_hint()
            return
        import threading
        ctx = {"song_data": song_data, "all_songs": all_songs, "mode": mode}
        t = threading.Thread(target=self._async_get_url, args=(plugin, song_id, ctx), daemon=True)
        t.start()

    def _standardize_song(self, s: dict, song_id: str = "", url: str = "",
                          is_local: bool = False, headers: dict = None) -> dict:
        sid = s.get("id") or s.get("hash") or s.get("songmid") or ""
        std = {
            "id": sid,
            "pluginId": s.get("pluginId", ""),
            "title": s.get("title", s.get("name", I18n.t("main.meta.unknown"))),
            "artist": s.get("artist", s.get("singer", "")),
            "album": s.get("album", s.get("albumName", "")),
            "duration": s.get("duration", 0),
            "cover": s.get("cover", ""),
            "source": s.get("source", s.get("pluginId", "")),
            "headers": {},
        }
        if s.get("is_chapter"):
            std["is_chapter"] = True
            std["bvid"] = s.get("bvid", "")
            std["cid"] = s.get("cid", "")
            std["chapter_index"] = s.get("chapter_index", 0)
        if s.get("_play_url"):
            std["_play_url"] = s["_play_url"]
            std["_is_local"] = s.get("_is_local", False)
        if sid == song_id and url:
            std["_play_url"] = url
            std["headers"] = headers or {}
            std["_is_local"] = is_local
        return std

    def _svc_replace_playlist(self, all_songs: list, song_id: str, url: str,
                               is_local: bool, headers: dict):
        from src.core.online_music_service import OnlineMusicService
        svc = OnlineMusicService()
        svc.clear_playlist()
        for s in all_songs:
            svc.add_to_playlist(s)
        self._online_music_panel._refresh_playlist()

        standardized = [self._standardize_song(s, song_id, url, is_local, headers) for s in all_songs]
        target_idx = 0
        for i, s in enumerate(all_songs):
            sid = s.get("id") or s.get("hash") or s.get("songmid") or ""
            if sid == song_id:
                target_idx = i
                break
        self._playback_manager.set_online_playlist_and_play(standardized, target_idx)

    def _svc_prepend_playlist(self, all_songs: list, song_id: str, url: str,
                               is_local: bool, headers: dict):
        from src.core.online_music_service import OnlineMusicService
        svc = OnlineMusicService()
        existing = svc.get_playlist()
        svc.clear_playlist()
        for s in all_songs:
            svc.add_to_playlist(s)
        for s in existing:
            svc.add_to_playlist(s)
        self._online_music_panel._refresh_playlist()

        standardized = [self._standardize_song(s, song_id, url, is_local, headers) for s in all_songs]
        target_idx = 0
        for i, s in enumerate(all_songs):
            sid = s.get("id") or s.get("hash") or s.get("songmid") or ""
            if sid == song_id:
                target_idx = i
                break

        pm_playlist = self._playback_manager.get_online_playlist()
        new_playlist = standardized + pm_playlist
        self._playback_manager.set_online_playlist_and_play(new_playlist, target_idx)

    def _svc_append_playlist(self, all_songs: list, song_id: str, url: str,
                              is_local: bool, headers: dict):
        from src.core.online_music_service import OnlineMusicService
        svc = OnlineMusicService()
        for s in all_songs:
            svc.add_to_playlist(s)
        self._online_music_panel._refresh_playlist()

        standardized = [self._standardize_song(s, song_id, url, is_local, headers) for s in all_songs]
        pm_playlist = self._playback_manager.get_online_playlist()
        current_idx = self._playback_manager.get_current_index()
        new_playlist = pm_playlist + standardized
        self._playback_manager.set_online_playlist_and_play(new_playlist, current_idx if current_idx >= 0 else 0)

    def _svc_insert_next(self, song_data: dict, url: str, is_local: bool,
                          headers: dict, play_now: bool = False):
        from src.core.online_music_service import OnlineMusicService
        svc = OnlineMusicService()
        svc.add_to_playlist(song_data)
        self._online_music_panel._refresh_playlist()

        standard_song = self._standardize_song(song_data, song_data.get("id", ""), url, is_local, headers)
        pm_playlist = self._playback_manager.get_online_playlist()
        current_idx = self._playback_manager.get_current_index()

        insert_pos = current_idx + 1 if current_idx >= 0 else len(pm_playlist)
        pm_playlist.insert(insert_pos, standard_song)

        if play_now:
            self._playback_manager.set_online_playlist_and_play(pm_playlist, insert_pos)
        else:
            self._playback_manager._online_playlist = pm_playlist

    def _get_online_url(self, song: dict) -> str:
        plugin_id = song.get("pluginId", "")
        song_id = song.get("id") or song.get("hash") or song.get("songmid") or ""
        if not plugin_id or not song_id:
            return ""

        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        plugin = pm.get_plugin(plugin_id)
        if not plugin:
            return ""

        try:
            if song.get("is_chapter") and hasattr(plugin, "get_chapter_url"):
                bvid = song.get("bvid", song_id)
                cid = song.get("cid", "")
                chapter_index = song.get("chapter_index", 0)
                url_info = plugin.get_chapter_url(bvid, cid, chapter_index)
            else:
                url_info = plugin.get_song_url(song_id)
            if not url_info:
                return ""
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
            logger.warning(f"Get online URL failed: {e}")
        return ""

    def _async_get_url(self, plugin, song_id: str, ctx: dict):
        try:
            song_data = ctx.get("song_data", {})
            if song_data.get("is_chapter") and hasattr(plugin, "get_chapter_url"):
                bvid = song_data.get("bvid", song_id)
                cid = song_data.get("cid", "")
                chapter_index = song_data.get("chapter_index", 0)
                url_info = plugin.get_chapter_url(bvid, cid, chapter_index)
            else:
                url_info = plugin.get_song_url(song_id)
            if not url_info:
                self._sig_online_url_failed.emit("Failed to get audio URL")
                return
            url = url_info if isinstance(url_info, str) else url_info.get("url", "")
            is_local = url_info.get("is_local", False) if isinstance(url_info, dict) else False
            if not url or (not url.startswith("http") and not is_local):
                error = url_info.get("error", "Unknown error") if isinstance(url_info, dict) else "Unknown error"
                self._sig_online_url_failed.emit(error)
                return
            headers = url_info.get("headers", {}) if isinstance(url_info, dict) else {}
            ctx["url"] = url
            ctx["is_local"] = is_local
            ctx["headers"] = headers
            self._sig_online_url_ready.emit(url_info, ctx)
        except Exception as e:
            self._sig_online_url_failed.emit(str(e))

    def _handle_online_url_ready(self, url_info: dict, ctx: dict):
        self._hide_download_hint()
        url = ctx.get("url", "")
        is_local = ctx.get("is_local", False)
        headers = ctx.get("headers", {})
        song_data = ctx.get("song_data", {})
        mode = ctx.get("mode", "single")

        if isinstance(url_info, dict):
            for key in ("title", "artist", "album"):
                val = url_info.get(key, "")
                if val:
                    song_data[key] = val

        if mode == "single":
            song_id = song_data.get("id") or song_data.get("hash") or song_data.get("songmid", "")
            plugin_id = song_data.get("pluginId", "")
            from src.core.online_music_service import OnlineMusicService
            svc = OnlineMusicService()
            svc.add_to_playlist(song_data)
            self._online_music_panel._refresh_playlist()
            svc_playlist = svc.get_playlist()
            target_idx = len(svc_playlist) - 1
            standardized = []
            for s in svc_playlist:
                sid = s.get("id") or s.get("hash") or s.get("songmid") or ""
                std = {
                    "id": sid,
                    "pluginId": s.get("pluginId", ""),
                    "title": s.get("title", s.get("name", I18n.t("main.meta.unknown"))),
                    "artist": s.get("artist", s.get("singer", "")),
                    "album": s.get("album", s.get("albumName", "")),
                    "duration": s.get("duration", 0),
                    "cover": s.get("cover", ""),
                    "source": s.get("source", s.get("pluginId", "")),
                    "headers": {},
                }
                if s.get("is_chapter"):
                    std["is_chapter"] = True
                    std["bvid"] = s.get("bvid", "")
                    std["cid"] = s.get("cid", "")
                    std["chapter_index"] = s.get("chapter_index", 0)
                if s.get("_play_url"):
                    std["_play_url"] = s["_play_url"]
                    std["_is_local"] = s.get("_is_local", False)
                if sid == song_id:
                    std["_play_url"] = url
                    std["headers"] = headers
                    std["_is_local"] = is_local
                standardized.append(std)
            self._playback_manager.set_online_playlist_and_play(standardized, target_idx)
            self._online_music_panel.record_play_history(song_data)
        else:
            all_songs = ctx.get("all_songs", [])
            song_id = song_data.get("id") or song_data.get("hash") or song_data.get("songmid", "")
            if mode == "play_list":
                songs = ctx.get("songs", [])
                play_index = ctx.get("index", 0)
                standardized = [self._standardize_song(s) for s in songs]
                for i, s in enumerate(standardized):
                    sid = s.get("id", "")
                    if sid == song_id:
                        s["_play_url"] = url
                        s["headers"] = headers
                        s["_is_local"] = is_local
                        play_index = i
                        break
                self._playback_manager.set_online_playlist_and_play(standardized, play_index)
                from src.core.online_music_service import OnlineMusicService
                svc = OnlineMusicService()
                svc.clear_playlist()
                for s in songs:
                    svc.add_to_playlist(s)
                self._online_music_panel._refresh_playlist()
            elif mode == "replace":
                self._svc_replace_playlist(all_songs, song_id, url, is_local, headers)
            elif mode == "prepend":
                self._svc_prepend_playlist(all_songs, song_id, url, is_local, headers)
            elif mode == "append":
                self._svc_append_playlist(all_songs, song_id, url, is_local, headers)
            elif mode == "insert_next":
                self._svc_insert_next(song_data, url, is_local, headers, play_now=False)
            elif mode == "play_now":
                self._svc_insert_next(song_data, url, is_local, headers, play_now=True)
            self._online_music_panel.record_play_history(song_data)

    def _handle_online_url_failed(self, error_msg: str):
        self._hide_download_hint()
        log_msgbox("warning", I18n.t("main.msg.download_failed_title"), I18n.tf("main.msg.download_failed_body", error=error_msg))
        ThemedMessageBox.warning(self, I18n.t("main.msg.download_failed_title"), I18n.tf("main.msg.download_failed_body", error=error_msg))

    def _on_play_failed(self, data: dict):
        file_path = data.get("file_path", "")
        if file_path:
            self._sig_play_failed.emit(file_path)

    def _handle_play_failed(self, file_path: str):
        if self._study_mode_active:
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_AUDIO_FORMATS:
            return
        from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
        dpm = DecoderPluginManager()
        missing = dpm.find_missing_plugin(ext)
        if not missing:
            return
        auto_prompt = True
        if hasattr(self, '_settings_panel') and hasattr(self._settings_panel, '_chk_auto_prompt'):
            auto_prompt = self._settings_panel._chk_auto_prompt.isChecked()
        if not auto_prompt:
            return
        plugin_name = missing.get("name", ext)
        formats_str = ", ".join(missing.get("formats", [ext]))
        log_msgbox("question", I18n.t("main.msg.need_decoder_title"),
                   I18n.tf("main.msg.need_decoder_body", file_name=os.path.basename(file_path), ext=ext, plugin_name=plugin_name, formats=formats_str))
        reply = ThemedMessageBox.question(
            self, I18n.t("main.msg.need_decoder_title"),
            I18n.tf("main.msg.need_decoder_body", file_name=os.path.basename(file_path), ext=ext, plugin_name=plugin_name, formats=formats_str),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="yes"
        )
        if reply == 1:
            plugin_id = missing.get("id", "")
            if plugin_id:
                if dpm.download_plugin(plugin_id):
                    log_msgbox("info", I18n.t("main.msg.install_success_title"), I18n.tf("main.msg.install_success_body", name=plugin_name))
                    ThemedMessageBox.information(self, I18n.t("main.msg.install_success_title"), I18n.tf("main.msg.install_success_body", name=plugin_name))
                    if hasattr(self, '_settings_panel') and hasattr(self._settings_panel, '_refresh_decoder_tables'):
                        self._settings_panel._refresh_decoder_tables()
                    from src.core.audio_service import AudioService
                    if AudioService().load_audio(file_path):
                        AudioService().play()
                else:
                    log_msgbox("warning", I18n.t("main.msg.decoder_install_failed_title"),
                               I18n.tf("main.msg.decoder_install_failed_body", name=plugin_name))
                    ThemedMessageBox.warning(
                        self, I18n.t("main.msg.decoder_install_failed_title"),
                        I18n.tf("main.msg.decoder_install_failed_body", name=plugin_name)
                    )

    def _show_download_hint(self, title: str):
        self._lbl_line1.setText(I18n.t("main.label.downloading_audio"))
        self._lbl_line2.setText(title)
        self._lbl_line3.setText(I18n.t("main.label.please_wait"))

    def _hide_download_hint(self):
        if self._lbl_line1.text().startswith("⏳"):
            self._lbl_line1.setText(I18n.t("main.label.no_track_playing"))
            self._lbl_line2.setText("")
            self._lbl_line3.setText("00:00 / 00:00")

    def _on_plugin_install(self, path):
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        if pm.load_plugin(path):
            self._refresh_plugin_list()

    def _on_plugin_enable(self, plugin_id, enabled):
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        if enabled:
            pm.enable_plugin(plugin_id)
        else:
            pm.disable_plugin(plugin_id)
        self._refresh_plugin_list()

    def _on_plugin_delete(self, plugin_id):
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        pm.delete_plugin(plugin_id)
        self._refresh_plugin_list()

    def _refresh_plugin_list(self):
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        plugins = pm.get_all_plugin_info()
        instances = {pid: plugin for pid, plugin in pm._plugins.items()}
        self._settings_panel.set_source_plugins(plugins, instances)

    _SETTINGS_KEY_MAP = {
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
        "PlayPause": "PlayPause",
        "Stop": "Stop",
        "PrevTrack": "PrevTrack",
        "NextTrack": "NextTrack",
        "SeekBackward": "SeekBackward",
        "SeekForward": "SeekForward",
        "VolumeUp": "VolumeUp",
        "VolumeDown": "VolumeDown",
        "ToggleLyric": "ToggleLyric",
        "ToggleSource": "ToggleSource",
        "ToggleMini": "ToggleMini",
        "ToggleSettings": "ToggleSettings",
        "OpenFile": "OpenFile",
        "bilibili_sessdata": "BilibiliSESSDATA",
        "enabled": "Enabled",
        "retain_months": "RetainMonths",
        "shadowing_enabled": "ShadowingEnabled",
        "shadowing_extra_sec": "ShadowingExtraSec",
        "autoseg_threshold": "AutoSegSilenceThreshold",
        "autoseg_min_silence": "AutoSegMinSilenceMs",
        "autoseg_min_segment": "AutoSegMinSegmentMs",
        "model": "Model",
        "device": "Device",
        "language": "Language",
        "hf_mirror": "HFMirror",
        "engine": "Engine",
        "pip_mirror": "PIPMirror",
    }

    def _on_settings_changed(self, key, value):
        prefix_map = {
            "lyric/": "Lyric",
            "playback/": "Playback",
            "appearance/": "Appearance",
            "network/": "Network",
            "mini/": "Mini",
            "shortcuts/": "Shortcuts",
            "study/": "Study",
            "logs/": "Logs",
            "whisper/": "Whisper",
            "dictionary/": "Dictionary",
        }
        for prefix, section in prefix_map.items():
            if key.startswith(prefix):
                raw_key = key[len(prefix):]
                config_key = self._SETTINGS_KEY_MAP.get(raw_key, raw_key)
                self._config_manager.set(section, config_key, value)
                self._apply_settings_change(key, value)
                return
        self._config_manager.set("Settings", key, value)

    def _apply_settings_change(self, key, value):
        if key == "playback/default_play_mode":
            modes = [PLAY_MODE_SEQUENCE, PLAY_MODE_LOOP_ALL, PLAY_MODE_LOOP_SINGLE, PLAY_MODE_RANDOM]
            idx = int(value)
            if 0 <= idx < len(modes):
                self._playback_manager.set_play_mode(modes[idx])
                self._update_mode_icon()
        elif key == "playback/default_volume":
            vol = int(value)
            self._slider_volume.setValue(vol)
            self._playback_manager.set_volume(vol)
        elif key == "playback/rewind_step":
            step = int(value)
            self._btn_backward.setToolTip(I18n.tf("main.tooltip.rewind_step", step=step))
        elif key == "playback/forward_step":
            step = int(value)
            self._btn_forward.setToolTip(I18n.tf("main.tooltip.forward_step", step=step))
        elif key == "appearance/always_on_top":
            flags = self.windowFlags()
            flags = flags | Qt.FramelessWindowHint
            if value:
                flags = flags | Qt.WindowStaysOnTopHint
            else:
                flags = flags & ~Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.show()
            self.raise_()
            self.activateWindow()
        elif key == "appearance/show_grid":
            self._file_table.setShowGrid(bool(value))
        elif key == "lyric/font_size":
            self._lyric_panel.set_font_size(int(value))
        elif key == "lyric/active_color":
            self._lyric_active_color = str(value)
        elif key == "lyric/inactive_color":
            self._lyric_inactive_color = str(value)
        elif key == "mini/font_size":
            if self._mini_window:
                self._mini_window.set_font_size(int(value))
            self._config_manager.set("Mini", "FontSize", int(value))
        elif key == "mini/ctrl_bg_opacity":
            self._config_manager.set("Mini", "CtrlBgOpacity", int(value))
            if self._mini_window:
                self._mini_window._apply_style()
        elif key == "mini/lyric_width":
            if self._mini_window:
                h = self._config_manager.get("Mini", "LyricHeight", 0)
                self._mini_window.set_lyric_fixed_size(int(value), h)
            self._config_manager.set("Mini", "LyricWidth", int(value))
        elif key == "mini/lyric_height":
            if self._mini_window:
                w = self._config_manager.get("Mini", "LyricWidth", 0)
                self._mini_window.set_lyric_fixed_size(w, int(value))
            self._config_manager.set("Mini", "LyricHeight", int(value))
        elif key == "mini/lyric_always_on_top":
            if self._mini_window:
                self._mini_window.set_lyric_always_on_top(bool(value))
            self._config_manager.set("Mini", "LyricAlwaysOnTop", bool(value))
        elif key.startswith("shortcuts/"):
            action_id = key[len("shortcuts/"):]
            self._rebind_shortcut(action_id, str(value))
        elif key.startswith("network/proxy"):
            from src.core.network_service import NetworkService, apply_urllib_proxy
            NetworkService().apply_proxy()
            apply_urllib_proxy()
        elif key == "study/enabled":
            self._btn_study.setVisible(bool(value))
        elif key == "study/shadowing_enabled":
            if hasattr(self, '_study_window') and self._study_window:
                self._study_window._player.set_shadowing_mode(bool(value))
                self._study_window._btn_shadowing.setChecked(bool(value))
        elif key == "study/shadowing_extra_sec":
            if hasattr(self, '_study_window') and self._study_window:
                self._study_window._player._shadowing_extra_sec = int(value)
        elif key == "dictionary/word_lookup_enabled":
            from src.business.dictionary_service import DictionaryService
            DictionaryService().set_word_lookup_enabled(bool(value))
            if hasattr(self, '_study_window') and self._study_window:
                self._study_window._btn_dict_toggle.blockSignals(True)
                self._study_window._btn_dict_toggle.setChecked(bool(value))
                self._study_window._btn_dict_toggle.blockSignals(False)
        elif key == "appearance/theme_name":
            self._apply_theme(str(value))
        elif key == "appearance/mini_theme_name":
            from src.infrastructure.theme_engine import ThemeEngine
            engine = ThemeEngine()
            engine.set_mini_theme_name(str(value) if value else "")
            self._config_manager.set("Appearance", "MiniThemeName", str(value) if value else "")
            if self._mini_window:
                self._mini_window._apply_style()
                self._mini_window._update_icons()

    def _apply_theme(self, theme_name: str = ""):
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        if theme_name:
            engine.set_current_theme(theme_name)
            self._config_manager.set("Appearance", "ThemeName", engine.get_current_name())
        qss = engine.generate_qss()
        colors = engine.get_current_colors()

        title_bar_bg = colors.get("window_bg", "#1a1a2e")
        title_bar_text = colors.get("text_primary", "#e0e0e0")
        btn_hover = colors.get("button_bg_hover", "rgba(255,255,255,30)")
        btn_pressed = colors.get("button_bg_pressed", "rgba(255,255,255,50)")
        danger_color = colors.get("danger", "#e74c3c")
        border_color = colors.get("border", "#444444")

        title_bar_qss = f"""
        QWidget#CustomTitleBar {{
            background-color: {title_bar_bg};
        }}
        QLabel#TitleLabel {{
            color: {title_bar_text};
            font: bold 12px 'Microsoft YaHei';
            padding-left: 4px;
        }}
        QPushButton#TitleBarButton {{
            background-color: transparent;
            color: {title_bar_text};
            border: none;
            font-size: 14px;
        }}
        QPushButton#TitleBarButton:hover {{
            background-color: {btn_hover};
        }}
        QPushButton#TitleBarButton:pressed {{
            background-color: {btn_pressed};
        }}
        QPushButton#TitleBarCloseButton {{
            background-color: transparent;
            color: {title_bar_text};
            border: none;
            font-size: 16px;
        }}
        QPushButton#TitleBarCloseButton:hover {{
            background-color: {danger_color};
            color: white;
        }}
        QPushButton#TitleBarCloseButton:pressed {{
            background-color: {danger_color};
            color: white;
        }}
        """

        QApplication.instance().setStyleSheet(qss + title_bar_qss)

        self._lyric_active_color = colors.get("lyric_active", "#32c864")
        self._lyric_inactive_color = colors.get("lyric_inactive", "#a0a0a0")
        if self._mini_window:
            self._mini_window._apply_style()
            self._mini_window._update_icons()

        self._update_button_icons(colors)
        if hasattr(self, '_help_window'):
            self._help_window.refresh_style()

    def _update_button_icons(self, colors: dict = None):
        if colors is None:
            from src.infrastructure.theme_engine import ThemeEngine
            colors = ThemeEngine().get_current_colors()
        from src.utils.svg_icons import get_icon
        icon_color = colors.get("text_primary", "#cccccc")
        accent_color = colors.get("accent", "#32c864")
        sz = 18
        self._btn_play.setIcon(get_icon("play", icon_color, sz))
        self._btn_pause.setIcon(get_icon("pause", icon_color, sz))
        self._btn_prev.setIcon(get_icon("skip-back", icon_color, sz))
        self._btn_next.setIcon(get_icon("skip-forward", icon_color, sz))
        self._btn_backward.setIcon(get_icon("rewind", icon_color, sz))
        self._btn_forward.setIcon(get_icon("fast-forward", icon_color, sz))
        self._btn_source.setIcon(get_icon("hard-drive", icon_color, sz))
        self._btn_settings.setIcon(get_icon("settings", icon_color, sz))
        self._btn_study.setIcon(get_icon("book-open", icon_color, sz))
        self._btn_lyric.setIcon(get_icon("text", icon_color, sz))
        self._update_mode_icon(icon_color, sz)
        self._update_repeat_icon(icon_color, sz)
        self._update_mini_btn_icon()
        self._btn_minimize.setIcon(get_icon("minimize-2", icon_color, 16))
        self._btn_maximize.setIcon(get_icon("maximize-2", icon_color, 16))
        self._btn_close.setIcon(get_icon("x", icon_color, 16))
        self._btn_help.setIcon(get_icon("circle-help", icon_color, 16))

    def _update_mode_icon(self, color: str = None, sz: int = 18):
        from src.utils.svg_icons import get_icon
        from src.utils.constants import PLAY_MODE_SEQUENCE, PLAY_MODE_LOOP_ALL, PLAY_MODE_LOOP_SINGLE, PLAY_MODE_RANDOM
        if color is None:
            from src.infrastructure.theme_engine import ThemeEngine
            tc = ThemeEngine().get_current_colors()
            color = tc.get("text_primary", "#cccccc")
        mode = self._playback_manager.get_play_mode()
        if mode == PLAY_MODE_SEQUENCE:
            self._btn_mode.setIcon(get_icon("list-music", color, sz))
            self._btn_mode.setToolTip(I18n.t("main.tooltip.mode_sequence"))
        elif mode == PLAY_MODE_LOOP_ALL:
            self._btn_mode.setIcon(get_icon("repeat", color, sz))
            self._btn_mode.setToolTip(I18n.t("main.tooltip.mode_loop_all"))
        elif mode == PLAY_MODE_LOOP_SINGLE:
            self._btn_mode.setIcon(get_icon("repeat-1", color, sz))
            self._btn_mode.setToolTip(I18n.t("main.tooltip.mode_loop_single"))
        elif mode == PLAY_MODE_RANDOM:
            self._btn_mode.setIcon(get_icon("shuffle", color, sz))
            self._btn_mode.setToolTip(I18n.t("main.tooltip.mode_random"))

    def _update_repeat_icon(self, color: str = None, sz: int = 18):
        from src.utils.svg_icons import get_icon
        if color is None:
            from src.infrastructure.theme_engine import ThemeEngine
            tc = ThemeEngine().get_current_colors()
            color = tc.get("text_primary", "#cccccc")
        if self._repeat_active:
            start_str = self._fmt_time(self._repeat_start)
            end_str = self._fmt_time(self._repeat_end)
            self._btn_repeat.setIcon(get_icon("repeat-line", color, sz))
            self._btn_repeat.setToolTip(I18n.tf("main.tooltip.repeat_active", start=start_str, end=end_str))
        else:
            self._btn_repeat.setIcon(get_icon("repeat-off", color, sz))
            self._btn_repeat.setToolTip(I18n.t("main.tooltip.repeat_inactive"))

    # ================================================================
    # Playback Controls
    # ================================================================

    def _toggle_play(self):
        if self._playback_manager.is_paused() or self._playback_manager.is_playing():
            self._playback_manager.seek(0)
            self._playback_manager.play()
        else:
            is_online = self._btn_source.isChecked()
            target_ctx = CONTEXT_ONLINE if is_online else CONTEXT_LOCAL
            current_ctx = self._playback_manager.get_context()
            if target_ctx != current_ctx:
                self._playback_manager._switch_context(target_ctx)
            if is_online and not self._playback_manager.get_online_playlist():
                from src.core.online_music_service import OnlineMusicService
                svc_songs = OnlineMusicService().get_playlist()
                if svc_songs:
                    standardized = [self._standardize_song(s) for s in svc_songs]
                    self._playback_manager._online_playlist = standardized
            self._playback_manager.play()

    def _pause(self):
        if self._playback_manager.is_playing():
            self._playback_manager.pause()
        elif self._playback_manager.is_paused():
            self._playback_manager.play()

    def _stop(self):
        self._playback_manager.stop()

    def _seek_forward(self):
        pos = self._playback_manager.get_position()
        if self._repeat_active and self._repeat_end > 0:
            step = int(self._config_manager.get("Playback", "ForwardStep", 15))
            new_pos = min(pos + step, self._repeat_end)
            self._playback_manager.seek(new_pos)
        else:
            step = self._config_manager.get("Playback", "ForwardStep", 15)
            self._playback_manager.seek(pos + step)

    def _seek_backward(self):
        pos = self._playback_manager.get_position()
        if self._repeat_active and self._repeat_end > 0:
            step = int(self._config_manager.get("Playback", "RewindStep", 15))
            new_pos = max(pos - step, self._repeat_start)
            self._playback_manager.seek(new_pos)
        else:
            step = self._config_manager.get("Playback", "RewindStep", 15)
            self._playback_manager.seek(max(0, pos - step))

    def _next_track(self):
        self._playback_manager.next_track()

    def _previous_track(self):
        self._playback_manager.previous_track()

    def _on_seek_end(self):
        self._is_seeking = False
        if self._current_duration > 0:
            self._playback_manager.seek((self._slider_progress.value() / 1000.0) * self._current_duration)

    def _set_volume(self, value):
        self._playback_manager.set_volume(value)
        self._lbl_volume.setText(f"{value}%")

    def _adjust_volume(self, delta):
        self._slider_volume.setValue(max(0, min(100, self._slider_volume.value() + delta)))

    def wheelEvent(self, event):
        wheel_volume = self._config_manager.get("Playback", "WheelVolume", True)
        if wheel_volume:
            delta = event.angleDelta().y()
            if delta > 0:
                self._adjust_volume(5)
            elif delta < 0:
                self._adjust_volume(-5)
            event.accept()
        else:
            super().wheelEvent(event)

    def _cycle_play_mode(self):
        current = self._playback_manager.get_play_mode()
        modes = [(PLAY_MODE_SEQUENCE, "Sequence"), (PLAY_MODE_LOOP_ALL, "Loop All"),
                 (PLAY_MODE_LOOP_SINGLE, "Loop Single"), (PLAY_MODE_RANDOM, "Random")]
        for i, (mode, _) in enumerate(modes):
            if mode == current:
                next_mode = modes[(i + 1) % len(modes)]
                self._playback_manager.set_play_mode(next_mode[0])
                self._update_mode_icon()
                break

    def _handle_lyric_download_progress(self, data: dict):
        if data.get("done", 0) >= data.get("total", 0):
            self._refresh_lyric_column()

    def _refresh_lyric_column(self):
        for row in range(self._file_table.rowCount()):
            item = self._file_table.item(row, 0)
            if not item:
                continue
            data = item.data(Qt.UserRole)
            if not data or data.get("type") != "music":
                continue
            song_path = data.get("path", "")
            title = data.get("title", "")
            artist = data.get("artist", "")
            has_lyric = self._lyric_manager.has_local_lyric(song_path) or self._lyric_manager.has_lyric_in_db(title, artist)
            lyric_item = QTableWidgetItem("✓" if has_lyric else "✗")
            lyric_item.setTextAlignment(Qt.AlignCenter)
            from src.infrastructure.theme_engine import ThemeEngine
            _tc = ThemeEngine().get_current_colors()
            if has_lyric:
                lyric_item.setForeground(QColor(_tc.get("success", "#32c864")))
            else:
                lyric_item.setForeground(QColor(_tc.get("text_muted", "#666680")))
            self._file_table.setItem(row, 3, lyric_item)

    def _handle_lyric_download_finished(self):
        pass

    def _on_lyric_offset_adjusted(self, delta_ms: int):
        new_offset = self._lyric_manager.adjust_lyric_offset(delta_ms)
        self._lyric_panel.update_offset_display(new_offset)
        self._current_lyric_index = -1

    def _on_lyric_offset_reset(self):
        self._lyric_manager.reset_lyric_offset()
        self._lyric_panel.update_offset_display(0)
        self._current_lyric_index = -1

    def _on_lyric_offset_save(self):
        song_info = self._lyric_manager._current_song
        if not song_info:
            return
        title = song_info.get("title", "")
        artist = song_info.get("artist", "")
        offset = self._lyric_manager.get_lyric_offset()
        if offset == 0:
            self._lyric_manager.delete_lyric_offset_from_db(title, artist)
        else:
            self._lyric_manager.save_lyric_offset_to_db(title, artist)
        log_msgbox("info", I18n.t("main.msg.lyric_offset_title"), I18n.tf("main.msg.lyric_offset_body", offset=f"{offset / 1000:+.1f}"))
        ThemedMessageBox.information(self, I18n.t("main.msg.lyric_offset_title"), I18n.tf("main.msg.lyric_offset_body", offset=f"{offset / 1000:+.1f}"))

    def _on_repeat_toggle(self, checked):
        if checked:
            if self._has_lyric and self._current_lyric_index >= 0:
                self._start_repeat_lyric_line(self._current_lyric_index)
            elif self._current_duration > 0:
                pos = self._current_position
                self._repeat_start = max(0, pos - 5)
                self._repeat_end = min(self._current_duration, pos + 5)
                self._repeat_active = True
                self._lyric_panel.set_repeat_range(
                    int(self._repeat_start * 1000),
                    int(self._repeat_end * 1000),
                )
            else:
                self._btn_repeat.setChecked(False)
                return
            self._update_repeat_icon()
        else:
            self._stop_repeat()

    def _start_repeat_lyric_line(self, index: int):
        lyric_lines = self._lyric_manager.get_current_lyric()
        if not lyric_lines or index < 0 or index >= len(lyric_lines):
            self._btn_repeat.setChecked(False)
            return
        start_ms = lyric_lines[index].time_ms
        if index + 1 < len(lyric_lines):
            end_ms = lyric_lines[index + 1].time_ms
        else:
            end_ms = int(self._current_duration * 1000)
        self._repeat_start = start_ms / 1000.0
        self._repeat_end = end_ms / 1000.0
        if self._repeat_end - self._repeat_start < 1.0:
            self._repeat_end = self._repeat_start + 1.0
        self._repeat_active = True
        self._btn_repeat.setChecked(True)
        self._lyric_panel.set_repeat_range(start_ms, end_ms)
        self._playback_manager.seek(self._repeat_start)
        self._update_repeat_icon()
        if self._mini_window:
            self._mini_window.update_repeat_state(1, self._repeat_start, self._repeat_end)

    def _start_repeat_lyric_range(self, start_index: int, end_index: int):
        lyric_lines = self._lyric_manager.get_current_lyric()
        if not lyric_lines:
            self._btn_repeat.setChecked(False)
            return
        start_index = max(0, min(start_index, len(lyric_lines) - 1))
        end_index = max(0, min(end_index, len(lyric_lines) - 1))
        if start_index > end_index:
            start_index, end_index = end_index, start_index

        start_ms = lyric_lines[start_index].time_ms
        if end_index + 1 < len(lyric_lines):
            end_ms = lyric_lines[end_index + 1].time_ms
        else:
            end_ms = int(self._current_duration * 1000)

        self._repeat_start = start_ms / 1000.0
        self._repeat_end = end_ms / 1000.0
        if self._repeat_end - self._repeat_start < 1.0:
            self._repeat_end = self._repeat_start + 1.0
        self._repeat_active = True
        self._btn_repeat.setChecked(True)
        self._lyric_panel.set_repeat_range(start_ms, end_ms)
        self._playback_manager.seek(self._repeat_start)
        self._update_repeat_icon()
        if self._mini_window:
            self._mini_window.update_repeat_state(1, self._repeat_start, self._repeat_end)

    def _stop_repeat(self):
        self._save_repeat_cache()
        self._repeat_active = False
        self._repeat_start = 0.0
        self._repeat_end = 0.0
        self._repeat_seeking = False
        self._btn_repeat.setChecked(False)
        self._lyric_panel.clear_repeat_range()
        self._lyric_panel.set_scroll_freeze(False)
        self._update_repeat_icon()
        if self._mini_window:
            self._mini_window.update_repeat_state(0, 0.0, 0.0)

    def _on_lyric_line_clicked(self, index: int):
        if self._repeat_active:
            self._start_repeat_lyric_line(index)
        else:
            self._start_repeat_lyric_line(index)
            self._lyric_panel.set_scroll_freeze(True)

    def _on_lyric_lines_selected(self, start_index: int, end_index: int):
        self._start_repeat_lyric_range(start_index, end_index)
        self._lyric_panel.set_scroll_freeze(True)

    def _do_repeat_seek(self, target: float):
        self._playback_manager.seek(target)
        try:
            from src.infrastructure.bass_engine import BASSEngine
            engine = BASSEngine()
            if engine.has_stream():
                engine.fade_in(80)
        except Exception:
            pass
        self._repeat_seeking = False

    def _save_repeat_cache(self):
        if not self._repeat_active:
            return
        song_key = self._get_current_song_key()
        if not song_key:
            return
        try:
            from src.core.database_service import DatabaseService
            db = DatabaseService()
            conn = db._get_connection()
            conn.execute(
                "INSERT OR REPLACE INTO repeat_cache (song_key, repeat_type, start_sec, end_sec, step_sec, update_time) "
                "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                (song_key, 1, self._repeat_start, self._repeat_end, 0),
            )
            conn.commit()
        except Exception as e:
            logger.warning(f"Save repeat cache failed: {e}")

    def _load_repeat_cache(self):
        if not self._lyric_panel_visible:
            return
        song_key = self._get_current_song_key()
        if not song_key:
            return
        try:
            from src.core.database_service import DatabaseService
            db = DatabaseService()
            conn = db._get_connection()
            row = conn.execute(
                "SELECT repeat_type, start_sec, end_sec, step_sec FROM repeat_cache WHERE song_key = ?",
                (song_key,),
            ).fetchone()
            if row and row[0] > 0:
                self._repeat_active = True
                self._repeat_start = row[1]
                self._repeat_end = row[2]
                self._btn_repeat.setChecked(True)
                self._lyric_panel.set_repeat_range(
                    int(self._repeat_start * 1000),
                    int(self._repeat_end * 1000),
                )
                self._lyric_panel.set_scroll_freeze(True)
                self._update_repeat_icon()
        except Exception as e:
            logger.warning(f"Load repeat cache failed: {e}")

    def _get_current_song_key(self) -> str:
        if not self._current_metadata:
            return ""
        title = self._current_metadata.get("title", "").lower().strip()
        artist = self._current_metadata.get("artist", "").lower().strip()
        if not title:
            return ""
        return f"{title}||{artist}"

    def _cycle_lyric_state(self):
        self._lyric_state = (self._lyric_state + 1) % 2
        if self._lyric_state == 0:
            self._set_lyric_off()
        else:
            self._set_lyric_on()

    def _close_settings_if_open(self):
        if self._settings_panel_visible:
            self._settings_panel_visible = False
            self._btn_settings.setChecked(False)
        if self._study_window is not None and self._study_window.isVisible():
            self._study_window.close()
            self._study_window = None
            self._study_mode_active = False
            self._btn_study.setChecked(False)

    def _set_lyric_off(self):
        self._lyric_panel_visible = False
        self._btn_lyric.setToolTip(I18n.t("main.tooltip.lyric_off"))
        self._middle_stack.setCurrentIndex(self._pre_lyric_stack_index)
        if self._pre_lyric_stack_index == 0:
            self._right_stack.setCurrentIndex(0)
        if self._has_lyric:
            self._lbl_line1.setStyleSheet(f"color: {self._lyric_active_color};")
            self._lbl_line2.setStyleSheet(f"color: {self._lyric_inactive_color};")
            self._current_lyric_index = -1
        if self._repeat_active:
            self._stop_repeat()
        self._update_help_if_visible()

    def _set_lyric_on(self):
        self._close_settings_if_open()
        self._lyric_panel_visible = True
        self._btn_lyric.setToolTip(I18n.t("main.tooltip.lyric_on"))
        self._pre_lyric_stack_index = self._middle_stack.currentIndex()
        self._middle_stack.setCurrentIndex(2)
        if self._pre_lyric_stack_index == 0:
            self._right_stack.setCurrentIndex(0)
        if self._has_lyric:
            self._lyric_panel.show_offset_bar()
            self._lyric_panel.update_offset_display(self._lyric_manager.get_lyric_offset())
            self._lbl_line1.setStyleSheet("")
            self._lbl_line2.setStyleSheet("")
            self._info_rotate_index = -1
            self._rotate_info()
        self._update_help_if_visible()

    def _handle_lyric_candidates(self, song_info: dict, results: list):
        if not results:
            return
        title = song_info.get("title", "")
        artist = song_info.get("artist", "")
        album = song_info.get("album", "")
        duration = song_info.get("duration", 0)

        if len(results) == 1:
            best = results[0]
            self._lyric_manager.set_current_lyric(best["content"], song_info)
            self._lyric_manager.save_lyric_to_db(
                best["content"], title, artist, album, duration,
                best.get("source", "unknown"), best.get("translate", "")
            )
            song_path = song_info.get("path", "")
            if song_path and not self._lyric_manager.has_local_lyric(song_path):
                self._lyric_manager.save_lyric(best["content"], song_path)
            return

        dialog = LyricSelectDialog(f"{title} - {artist}", results, self)
        if dialog.exec() == LyricSelectDialog.Accepted:
            selected = dialog.get_selected()
            if selected:
                self._lyric_manager.set_current_lyric(selected["content"], song_info)
                self._lyric_manager.save_lyric_to_db(
                    selected["content"], title, artist, album, duration,
                    selected.get("source", "manual"), selected.get("translate", "")
                )
                song_path = song_info.get("path", "")
                if song_path and not self._lyric_manager.has_local_lyric(song_path):
                    self._lyric_manager.save_lyric(selected["content"], song_path)
        else:
            best = results[0]
            self._lyric_manager.set_current_lyric(best["content"], song_info)

    def _toggle_source_panel(self):
        online = self._btn_source.isChecked()
        if online:
            self._btn_source.setToolTip(I18n.t("main.tooltip.source_online"))
            target = 1
            self._online_music_panel.auto_select_page()
        else:
            self._btn_source.setToolTip(I18n.t("main.tooltip.source_local"))
            target = 0
        if self._settings_panel_visible:
            self._settings_panel_visible = False
            self._btn_settings.setChecked(False)
            self._bottom_panel.show()
        if self._study_window is not None and self._study_window.isVisible():
            self._study_window.close()
            self._study_window = None
            self._study_mode_active = False
            self._btn_study.setChecked(False)
            self._bottom_panel.show()
        if self._lyric_panel_visible:
            self._pre_lyric_stack_index = target
        else:
            self._middle_stack.setCurrentIndex(target)
        from src.business.config_manager import ConfigManager
        ConfigManager().set("General", "OnlineMode", online)
        self._update_help_if_visible()

    def _toggle_mini_mode(self):
        if self._mini_mode:
            self._exit_mini_mode()
        else:
            self._enter_mini_mode()
        self._update_mini_btn_icon()

    def _update_mini_btn_icon(self):
        from src.utils.svg_icons import get_icon
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        color = tc.get("text_primary", "#cccccc")
        if self._mini_mode:
            self._btn_mini.setIcon(get_icon("maximize-2", color, 18))
            self._btn_mini.setToolTip(I18n.t("main.tooltip.exit_mini_mode"))
        else:
            self._btn_mini.setIcon(get_icon("minimize-2", color, 18))
            self._btn_mini.setToolTip(I18n.t("main.tooltip.mini_mode"))

    def _enter_mini_mode(self):
        self._mini_mode = True
        self._save_state()

        if not self._mini_window:
            self._mini_window = MiniWindow()
            self._mini_window.prev_requested.connect(self._previous_track)
            self._mini_window.play_requested.connect(self._pause)
            self._mini_window.next_requested.connect(self._next_track)
            self._mini_window.restore_requested.connect(self._exit_mini_mode)
            self._mini_window.hide_requested.connect(self._hide_mini_window)
            self._mini_window.lyric_toggled.connect(self._on_mini_lyric_toggled)
            self._mini_window.set_font_size(
                self._config_manager.get("Mini", "FontSize", 22)
            )
            self._mini_window._apply_style()
            self._mini_window._update_icons()
            lw = self._config_manager.get("Mini", "LyricWidth", 0)
            lh = self._config_manager.get("Mini", "LyricHeight", 0)
            self._mini_window.set_lyric_fixed_size(lw, lh)
            on_top = self._config_manager.get("Mini", "LyricAlwaysOnTop", True)
            self._mini_window.set_lyric_always_on_top(on_top)
            self._mini_window.update_play_state(self._playback_manager.is_playing())
            if self._has_lyric:
                self._sync_lyric_to_mini()

        self._mini_window.move_to_bottom_right()
        self._mini_window.show()
        if hasattr(self, '_help_window'):
            self._help_window.hide()
        self.hide()

        self._create_tray_icon()

    def _exit_mini_mode(self):
        self._mini_mode = False
        if self._mini_window:
            self._mini_window.hide()
        if self._tray_icon:
            self._tray_icon.hide()
        self.show()
        self._update_mini_btn_icon()

    def _create_tray_icon(self):
        if self._tray_icon:
            self._tray_icon.show()
            return

        icon = self.windowIcon()
        if icon.isNull():
            icon = QIcon.fromTheme("media-playback-start")
        self._tray_icon = QSystemTrayIcon(icon, self)

        menu = QMenu()
        action_open = menu.addAction("Open Full Mode")
        action_open.triggered.connect(self._exit_mini_mode)
        action_hide = menu.addAction(I18n.t("main.action.hide_mini_window"))
        action_hide.triggered.connect(self._hide_mini_window)
        menu.addSeparator()
        action_exit = menu.addAction("Exit")
        action_exit.triggered.connect(self._tray_exit)
        self._tray_icon.setContextMenu(menu)

        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._exit_mini_mode()

    def _hide_mini_window(self):
        if self._mini_window:
            self._mini_window.hide()

    def _tray_exit(self):
        self._mini_mode = False
        if self._mini_window:
            self._mini_window.close()
        if self._tray_icon:
            self._tray_icon.hide()
        self.close()

    def _sync_lyric_to_mini(self):
        if not self._mini_window:
            return
        if not self._has_lyric:
            self._mini_window.update_lyric("No lyrics", "")
            return
        position_ms = int(self._current_position * 1000)
        idx, line = self._lyric_manager.get_current_line(position_ms)
        if line:
            active_text = line.text
            lyric_lines = self._lyric_manager.get_current_lyric()
            next_idx = idx + 1
            inactive_text = lyric_lines[next_idx].text if next_idx < len(lyric_lines) else ""
            self._mini_window.update_lyric(active_text, inactive_text)
        else:
            self._mini_window.update_lyric("", "")

    def _on_mini_lyric_toggled(self, checked):
        if checked:
            self._sync_lyric_to_mini()

    def _toggle_settings_panel(self):
        if self._settings_panel_visible:
            self._settings_panel_visible = False
            self._btn_settings.setChecked(False)
            self._middle_stack.setCurrentIndex(self._pre_settings_stack_index)
            if self._pre_settings_stack_index == 0:
                self._right_stack.setCurrentIndex(0)
            self._bottom_panel.show()
            self._update_help_if_visible()
        else:
            if self._lyric_panel_visible:
                self._lyric_state = 0
            self._lyric_panel_visible = False
            self._btn_lyric.setToolTip(I18n.t("main.tooltip.lyric_off"))
            if self._study_window is not None and self._study_window.isVisible():
                self._study_window.close()
                self._study_window = None
                self._study_mode_active = False
                self._btn_study.setChecked(False)
            self._settings_panel_visible = True
            self._btn_settings.setChecked(True)
            self._pre_settings_stack_index = self._middle_stack.currentIndex()
            self._middle_stack.setCurrentIndex(3)
            self._bottom_panel.hide()
            self._update_help_if_visible()

    def _toggle_study_window(self):
        if self._study_window is not None and self._study_window.isVisible():
            self._study_window.close()
            self._study_window = None
            self._study_mode_active = False
            self._btn_study.setChecked(False)
            self.show()
            return

        if self._playback_manager.is_playing():
            self._playback_manager.pause()

        help_was_visible = hasattr(self, '_help_window') and self._help_window.isVisible()
        if help_was_visible:
            self._help_window.hide()

        self._study_mode_active = True
        self._study_window = StudyWindow()
        self._study_window.closed.connect(self._on_study_window_closed)
        self._study_window.switch_to_full.connect(self._on_study_switch_full)

        main_geo = self.geometry()
        main_maximized = self.isMaximized()

        self.hide()

        if main_maximized:
            self._study_window.showMaximized()
        else:
            self._study_window.move(main_geo.topLeft())
            self._study_window.resize(main_geo.size())
            self._study_window.show()

        if help_was_visible:
            self._study_window._help_window.show_help("study_library")

        self._btn_study.setChecked(True)

    def _on_study_window_closed(self):
        self._btn_study.setChecked(False)
        study_help_visible = (self._study_window and
                              hasattr(self._study_window, '_help_window') and
                              self._study_window._help_window.isVisible())
        if study_help_visible:
            self._study_window._help_window.hide()
        self._study_window = None
        self._study_mode_active = False
        AudioService().unload()
        self._stop_repeat()
        self._slider_progress.setValue(0)
        self._lbl_time.setText("00:00 / 00:00")
        self.show()
        if study_help_visible:
            help_id = self._get_current_help_id()
            self._help_window.show_help(help_id)

    def _on_study_switch_full(self):
        study_help_visible = (self._study_window and
                              hasattr(self._study_window, '_help_window') and
                              self._study_window._help_window.isVisible())
        if study_help_visible:
            self._study_window._help_window.hide()
        if self._study_window:
            self._study_window.close()
        self._study_mode_active = False
        AudioService().unload()
        self._stop_repeat()
        self._slider_progress.setValue(0)
        self._lbl_time.setText("00:00 / 00:00")
        self.show()
        self._exit_mini_mode()
        if study_help_visible:
            help_id = self._get_current_help_id()
            self._help_window.show_help(help_id)

    def _toggle_help(self):
        if self._mini_mode:
            self._show_mini_help()
            return
        if self._study_mode_active and self._study_window and self._study_window.isVisible():
            self._study_window._toggle_help()
            return
        if self._help_window.isVisible():
            self._help_window.hide()
        else:
            help_id = self._get_current_help_id()
            self._help_window.show_help(help_id)

    def _show_mini_help(self):
        from src.business.help_data import HELP_DATA
        from src.presentation.themed_dialog import ThemedDialog
        data = HELP_DATA.get("mini_mode")
        if not data:
            return
        dlg = ThemedDialog(self, title=f"📖 {data['title']}", width=380)
        dlg.setMinimumHeight(400)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(16, 12, 16, 16)
        cl.setSpacing(4)
        tc = ThemeEngine().get_current_colors()
        accent = tc.get("accent", "#32c864")
        text2 = tc.get("text_secondary", "#a0a0b0")
        for i, section in enumerate(data["sections"]):
            if i > 0:
                sep = QFrame()
                sep.setFixedHeight(1)
                sep.setStyleSheet("background-color: rgba(255,255,255,15);")
                cl.addWidget(sep)
            h = QLabel(section["heading"])
            h.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            h.setWordWrap(True)
            h.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
            cl.addWidget(h)
            c = QLabel(section["content"])
            c.setFont(QFont("Microsoft YaHei", 9))
            c.setWordWrap(True)
            c.setTextInteractionFlags(Qt.TextSelectableByMouse)
            c.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
            cl.addWidget(c)
            sp = QWidget()
            sp.setFixedHeight(4)
            cl.addWidget(sp)
        cl.addStretch()
        scroll.setWidget(content)
        dlg.body_layout().addWidget(scroll)
        dlg.exec()

    def _get_current_help_id(self) -> str:
        if self._settings_panel_visible:
            return "main_settings"
        if self._lyric_panel_visible:
            return "main_lyric"
        idx = self._middle_stack.currentIndex()
        if idx == 1:
            return "main_online"
        return "main_local"

    def _update_help_if_visible(self):
        if hasattr(self, '_help_window') and self._help_window.isVisible():
            help_id = self._get_current_help_id()
            self._help_window.show_help(help_id)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, '_help_window') and self._help_window.isVisible():
            self._help_window.sync_position()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_help_window') and self._help_window.isVisible():
            self._help_window.sync_position()

    def keyPressEvent(self, event):
        from PySide6.QtGui import QKeyEvent
        if event.key() == Qt.Key_F1:
            self._toggle_help()
            event.accept()
            return
        super().keyPressEvent(event)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Music Files", "",
            "Audio & Playlist Files (*.mp3 *.wav *.flac *.ape *.ogg *.m4a *.aac *.wma *.m3u *.m3u8)")
        for f in files:
            self._add_single_file(f)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, I18n.t("main.dialog.select_music_folder"))
        if folder:
            self._current_folder = folder
            self._load_file_list_async(folder)

    def _add_single_file(self, file_path):
        from src.infrastructure.playlist_parser import is_playlist_file
        if is_playlist_file(file_path):
            self._load_playlist_file(file_path)
            return
        meta = self._metadata_service.read_metadata(file_path)
        row = self._file_table.rowCount()
        self._file_table.insertRow(row)
        title = meta.get("title", "Unknown")
        artist = meta.get("artist", "")
        display = f"{artist} - {title}" if (artist and artist != "Unknown Artist") else title
        dur = meta.get("duration", 0)
        name_item = QTableWidgetItem(f"\U0001F3B5 {display}")
        name_item.setData(Qt.UserRole, {"type": "music", "path": file_path, "metadata": meta})
        self._file_table.setItem(row, 0, name_item)
        self._file_table.setItem(row, 1, QTableWidgetItem(f"{dur // 60}:{dur % 60:02d}"))
        self._file_table.setItem(row, 2, QTableWidgetItem(meta.get("format", "").upper()))
        lyric_item = QTableWidgetItem("✓")
        lyric_item.setTextAlignment(Qt.AlignCenter)
        from src.infrastructure.theme_engine import ThemeEngine
        _tc = ThemeEngine().get_current_colors()
        lyric_item.setForeground(QColor(_tc.get("text_muted", "#666680")))
        self._file_table.setItem(row, 3, lyric_item)

    # ================================================================
    # Playback Events
    # ================================================================

    def _on_playback_state_changed(self, data):
        self._sig_playback_state.emit(data)

    def _handle_playback_state_changed(self, data):
        if self._study_mode_active:
            return
        state = data.get("state", PLAYBACK_STOPPED)
        if state == PLAYBACK_PLAYING:
            if not self._timer.isActive():
                self._timer.start(100)
            self._btn_pause.setToolTip(I18n.t("main.tooltip.pause"))
        elif state == PLAYBACK_PAUSED:
            self._btn_pause.setToolTip(I18n.t("main.tooltip.resume"))
        else:
            self._timer.stop()
            self._btn_pause.setToolTip(I18n.t("main.tooltip.pause"))
            self._slider_progress.setValue(0)
            self._lbl_time.setText("00:00 / 00:00")

    def _on_track_changed(self, data):
        self._sig_track_changed.emit(data)

    def _handle_track_changed(self, data):
        if self._study_mode_active:
            return
        file_path = data.get("file_path", "")
        duration = data.get("duration", 0)
        song_info = data.get("song_info", None)
        self._current_duration = duration
        self._current_song_id = ""

        self._stop_repeat()
        self._highlight_current_track(file_path)

        if song_info:
            self._current_song_id = song_info.get("id", "") or file_path
            self._current_metadata = {
                "title": song_info.get("title", ""),
                "artist": song_info.get("artist", ""),
                "album": song_info.get("album", ""),
                "source": song_info.get("source", ""),
                "duration": int(duration) if duration else 0,
                "path": file_path,
            }
            self._has_lyric = False
            self._current_lyric_index = -1
            self._lyric_panel.clear()
            self._lbl_line1.setStyleSheet("")
            self._lbl_line2.setStyleSheet("")
            self._info_rotate_index = -1
            self._rotate_info()
            self._load_cover_for_online(song_info)
            self._load_online_lyric(song_info)
            self._load_repeat_cache()
            if self._mini_window:
                self._mini_window.clear_lyric()
            online_song_id = song_info.get("id", "")
            if online_song_id:
                logger.info(f"Highlighting online song: id={online_song_id}")
                self._online_music_panel.highlight_current_song(online_song_id)
        elif file_path:
            self._current_song_id = file_path
            meta = self._metadata_service.read_metadata(file_path)
            self._current_metadata = meta
            self._has_lyric = False
            self._current_lyric_index = -1
            self._lyric_panel.clear()
            self._lbl_line1.setStyleSheet("")
            self._lbl_line2.setStyleSheet("")
            self._info_rotate_index = -1
            self._rotate_info()
            self._load_cover_image(file_path)
            self._load_local_lyric(meta)
            self._load_repeat_cache()
            if self._mini_window:
                self._mini_window.clear_lyric()
            is_local = not file_path.startswith(("http://", "https://", "ftp://"))
            if is_local:
                self._music_library.add_play_history(file_path, meta)

    def _highlight_current_track(self, file_path):
        from src.infrastructure.theme_engine import ThemeEngine
        colors = ThemeEngine().get_current_colors()
        accent_color = QColor(colors.get("table_row_selected_text", "#32c864"))
        text_color = QColor(colors.get("text_primary", "#e0e0e0"))

        for row in range(self._file_table.rowCount()):
            item = self._file_table.item(row, 0)
            if not item:
                continue
            data = item.data(Qt.UserRole)
            if not data or data.get("type") != "music":
                continue

            is_current = data.get("path") == file_path
            font = item.font()
            font.setBold(is_current)

            if is_current:
                item.setText(item.text().replace("\U0001F3B5 ", "\u25B6 ", 1))
                self._file_table.selectRow(row)
            else:
                text = item.text()
                if text.startswith("\u25B6 "):
                    item.setText("\U0001F3B5 " + text[2:])

            for col in range(self._file_table.columnCount()):
                cell = self._file_table.item(row, col)
                if cell:
                    cell.setFont(font)
                    if is_current:
                        cell.setForeground(accent_color)
                    else:
                        cell.setForeground(text_color)

    def _load_cover_image(self, file_path):
        import glob
        folder = os.path.dirname(file_path)
        covers = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.bmp"]:
            covers.extend(glob.glob(os.path.join(folder, ext)))
            covers.extend(glob.glob(os.path.join(folder, ext.upper())))
        for name in ["cover", "folder", "album", "front"]:
            for ext in ["jpg", "jpeg", "png"]:
                p = os.path.join(folder, f"{name}.{ext}")
                if os.path.exists(p):
                    covers.insert(0, p)
        if covers:
            px = QPixmap(covers[0])
            if not px.isNull():
                if hasattr(self, '_cover_movie') and self._cover_movie:
                    self._cover_movie.stop()
                    self._cover_movie.deleteLater()
                    self._cover_movie = None
                self._lbl_cover.setMovie(None)
                self._lbl_cover.setPixmap(px.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self._load_default_cover()

    def _load_local_lyric(self, meta):
        song_path = meta.get("path", "")
        title = meta.get("title", "")
        artist = meta.get("artist", "")
        logger.info(f"[LYRIC-DEBUG] _load_local_lyric called: path={song_path}, title={title}, artist={artist}")

        lyric = self._lyric_manager.load_local_lyric(song_path)
        logger.info(f"[LYRIC-DEBUG] load_local_lyric result: {'found' if lyric else 'NOT found'}, len={len(lyric) if lyric else 0}")
        if lyric:
            self._lyric_manager.set_current_lyric(lyric, meta)
            if not self._lyric_manager.has_lyric_in_db(title, artist):
                album = meta.get("album", "")
                duration = meta.get("duration", 0)
                self._lyric_manager.save_lyric_to_db(lyric, title, artist, album, duration, "local")
            return

        db_lyric = self._lyric_manager.load_lyric_from_db(title, artist)
        logger.info(f"[LYRIC-DEBUG] load_lyric_from_db result: {'found' if db_lyric else 'NOT found'}")
        if db_lyric:
            self._lyric_manager.set_current_lyric(db_lyric, meta)
            if song_path and not self._lyric_manager.has_local_lyric(song_path):
                self._lyric_manager.save_lyric(db_lyric, song_path)
            return

        logger.info(f"[LYRIC-DEBUG] starting online search for: {title} - {artist}")
        threading.Thread(
            target=self._search_lyric_silent,
            args=(meta,),
            daemon=True,
        ).start()

    def _load_cover_for_online(self, song_info: dict):
        cover_url = song_info.get("cover", "")
        if cover_url:
            threading.Thread(
                target=self._download_and_show_cover,
                args=(cover_url,),
                daemon=True,
            ).start()
        else:
            self._load_default_cover()

    def _should_skip_lyric_download(self, song_info: dict) -> bool:
        duration = song_info.get("duration", 0)
        if duration and duration > 600:
            return True
        is_chapter = song_info.get("is_chapter", False)
        plugin_id = song_info.get("source", song_info.get("pluginId", ""))
        if plugin_id == "bilibili" and not is_chapter:
            return True
        return False

    def _load_online_lyric(self, song_info: dict):
        threading.Thread(
            target=self._load_online_lyric_bg,
            args=(song_info,),
            daemon=True,
        ).start()

    def _load_online_lyric_bg(self, song_info: dict):
        title = song_info.get("title", "")
        artist = song_info.get("artist", "")

        db_lyric = self._lyric_manager.load_lyric_from_db(title, artist)
        if db_lyric:
            self._lyric_manager.set_current_lyric(db_lyric, song_info)
            return

        plugin_id = song_info.get("source", song_info.get("pluginId", ""))
        song_id = song_info.get("id", "")
        if plugin_id and song_id:
            try:
                from src.plugins.plugin_manager import PluginManager
                pm = PluginManager()
                plugin = pm.get_plugin(plugin_id)
                if plugin:
                    lrc_result = plugin.get_lyric(song_id)
                    lrc_text = lrc_result.get("lrc", "") if lrc_result else ""
                    if lrc_text:
                        self._lyric_manager.set_current_lyric(lrc_text, song_info)
                        album = song_info.get("album", "")
                        duration = song_info.get("duration", 0)
                        self._lyric_manager.save_lyric_to_db(lrc_text, title, artist, album, duration, plugin_id)
                        return
            except Exception as e:
                logger.warning(f"Plugin get_lyric failed: {e}")

        if not self._should_skip_lyric_download(song_info):
            self._search_lyric_silent(song_info)

    def _search_lyric_silent(self, song_info: dict):
        try:
            title = song_info.get("title", "")
            artist = song_info.get("artist", "")
            album = song_info.get("album", "")
            duration = song_info.get("duration", 0)
            results = self._lyric_manager.search_lyric_online(title, artist, album, duration)
            if results:
                best = results[0]
                self._lyric_manager.set_current_lyric(best["content"], song_info)
                self._lyric_manager.save_lyric_to_db(
                    best["content"], title, artist, album, duration,
                    best["source"], best.get("translate", "")
                )
                song_path = song_info.get("path", "")
                if song_path and not self._lyric_manager.has_local_lyric(song_path):
                    self._lyric_manager.save_lyric(best["content"], song_path)
        except Exception as e:
            logger.warning(f"Silent lyric search failed: {e}")

    def _show_lyric_select_dialog(self, song_info: dict):
        title = song_info.get("title", "")
        artist = song_info.get("artist", "")
        album = song_info.get("album", "")
        duration = song_info.get("duration", 0)

        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            candidates = self._lyric_manager.search_lyric_candidates(title, artist, album, duration)
        except Exception as e:
            logger.warning(f"Lyric candidate search failed: {e}")
            candidates = []
        QApplication.restoreOverrideCursor()

        if not candidates:
            log_msgbox("info", I18n.t("main.msg.lyric_not_found_title"), I18n.tf("main.msg.lyric_not_found_body", title=title, artist=artist))
            ThemedMessageBox.information(self, I18n.t("main.msg.lyric_not_found_title"), I18n.tf("main.msg.lyric_not_found_body", title=title, artist=artist))
            return

        dialog = LyricSelectDialog(f"{title} - {artist}", candidates, self)
        if dialog.exec() == LyricSelectDialog.Accepted:
            selected = dialog.get_selected()
            if selected:
                self._lyric_manager.set_current_lyric(selected["content"], song_info)
                self._lyric_manager.save_lyric_to_db(
                    selected["content"], title, artist, album, duration,
                    selected.get("source", "manual"), selected.get("translate", "")
                )
                song_path = song_info.get("path", "")
                if song_path and not self._lyric_manager.has_local_lyric(song_path):
                    self._lyric_manager.save_lyric(selected["content"], song_path)

    def _download_and_show_cover(self, url: str):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            px = QPixmap()
            px.loadFromData(data)
            if not px.isNull():
                from PySide6.QtCore import QMetaObject, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_set_cover_pixmap",
                    Qt.QueuedConnection,
                    Q_ARG(QPixmap, px.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)),
                )
                return
        except Exception as e:
            logger.warning(f"Failed to download cover: {e}")
        from PySide6.QtCore import QMetaObject
        QMetaObject.invokeMethod(self, "_load_default_cover", Qt.QueuedConnection)

    @Slot(QPixmap)
    def _set_cover_pixmap(self, px: QPixmap):
        if hasattr(self, '_cover_movie') and self._cover_movie:
            self._cover_movie.stop()
            self._cover_movie.deleteLater()
            self._cover_movie = None
        self._lbl_cover.setMovie(None)
        self._lbl_cover.setPixmap(px)

    def _on_lyric_loaded(self, data):
        self._sig_lyric_loaded.emit(data)

    def _handle_lyric_loaded(self, data):
        if self._study_mode_active:
            return
        if data.get("__lyric_download_progress__"):
            progress = data.get("data", {})
            self._handle_lyric_download_progress(progress)
            return

        song_info = data.get("song", {})
        loaded_id = ""
        if song_info:
            loaded_id = song_info.get("id", "") or song_info.get("path", "")
        if loaded_id and self._current_song_id and loaded_id != self._current_song_id:
            logger.debug(f"Ignoring stale lyric: loaded={loaded_id}, current={self._current_song_id}")
            return
        lyric_lines = data.get("lyric", [])
        logger.info(f"[LYRIC-DEBUG] _handle_lyric_loaded: lines={len(lyric_lines)}, loaded_id={loaded_id}, current_song_id={self._current_song_id}, panel_visible={self._lyric_panel_visible}")
        if lyric_lines:
            self._has_lyric = True
            self._current_lyric_index = -1
            title = song_info.get("title", "") if song_info else ""
            artist = song_info.get("artist", "") if song_info else ""
            album = song_info.get("album", "") if song_info else ""
            self._lyric_panel.set_song_info(title, artist, album)
            self._lyric_panel.set_lyric_lines(lyric_lines)
            self._lyric_panel.update_offset_display(self._lyric_manager.get_lyric_offset())
            self._refresh_lyric_column()
            if self._lyric_panel_visible:
                self._lyric_panel.show_offset_bar()
                self._lbl_line1.setStyleSheet("")
                self._lbl_line2.setStyleSheet("")
            else:
                self._lbl_line1.setText("")
                self._lbl_line1.setStyleSheet(f"color: {self._lyric_active_color};")
                self._lbl_line2.setText("")
                self._lbl_line2.setStyleSheet(f"color: {self._lyric_inactive_color};")
        else:
            self._has_lyric = False
            self._current_lyric_index = -1
            self._lyric_panel.clear()
            self._lbl_line1.setStyleSheet("")
            self._lbl_line2.setStyleSheet("")
            self._info_rotate_index = -1
            self._rotate_info()

    def _on_position_update(self, position):
        self.position_changed.emit(position)

    def _update_position(self, position):
        if self._study_mode_active:
            return
        self._current_position = position
        if not self._is_seeking and self._current_duration > 0:
            self._slider_progress.setValue(int((position / self._current_duration) * 1000))

    def _update_ui(self):
        if self._study_mode_active:
            return
        from datetime import datetime
        pos_str = self._fmt_time(self._current_position)
        dur_str = self._fmt_time(self._current_duration)
        now = datetime.now().strftime("%H:%M")
        self._lbl_line3.setText(f"{pos_str} / {dur_str}    {now}")

        if self._repeat_active and self._repeat_end > 0 and not self._repeat_seeking:
            if self._current_position >= self._repeat_end:
                self._repeat_seeking = True
                target = self._repeat_start
                try:
                    from src.infrastructure.bass_engine import BASSEngine
                    engine = BASSEngine()
                    if engine.has_stream():
                        engine.fade_out(80)
                        QTimer.singleShot(80, lambda t=target: self._do_repeat_seek(t))
                    else:
                        self._playback_manager.seek(target)
                        self._repeat_seeking = False
                except Exception:
                    self._playback_manager.seek(target)
                    self._repeat_seeking = False

        if self._mini_mode and self._mini_window:
            self._mini_window.update_play_state(self._playback_manager.is_playing())
            self._mini_window.update_song_info(self._get_current_song_info(), f"{pos_str}|{dur_str}")

        if self._has_lyric:
            position_ms = int(self._current_position * 1000)
            idx, line = self._lyric_manager.get_current_line(position_ms)
            if line and idx != self._current_lyric_index:
                self._current_lyric_index = idx
                self._lyric_panel.highlight_line(idx)
                if not self._lyric_panel_visible:
                    self._lbl_line1.setText(line.text)
                    self._lbl_line1.setStyleSheet(f"color: {self._lyric_active_color};")
                    lyric_lines = self._lyric_manager.get_current_lyric()
                    next_idx = idx + 1
                    inactive_text = lyric_lines[next_idx].text if next_idx < len(lyric_lines) else ""
                    self._lbl_line2.setText(inactive_text)
                    self._lbl_line2.setStyleSheet(f"color: {self._lyric_inactive_color};")
                if self._mini_mode and self._mini_window:
                    lyric_lines = self._lyric_manager.get_current_lyric()
                    next_idx = idx + 1
                    inactive_text = lyric_lines[next_idx].text if next_idx < len(lyric_lines) else ""
                    self._mini_window.update_lyric(line.text, inactive_text)

        if self._playback_manager.is_playing():
            import random
            self._vu_meter.set_levels([random.random() * 0.7 + 0.2 for _ in range(VUMeter.NUM_BARS)])
        else:
            self._vu_meter.set_levels([0] * VUMeter.NUM_BARS)

    def _get_current_song_info(self):
        track = self._playback_manager.get_current_track()
        if not track:
            return ""
        file_path = track.get("path", "")
        title = track.get("title", "")
        artist = track.get("artist", "")
        if title and artist:
            info = f"{title} - {artist}"
        elif title:
            info = title
        elif file_path:
            info = os.path.splitext(os.path.basename(file_path))[0]
        else:
            return ""
        if len(info) > 150:
            info = info[:150] + "..."
        return info

    def _fmt_time(self, sec):
        return f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"

    # ================================================================
    # State Persistence
    # ================================================================

    def _start_alist_if_available(self):
        try:
            from src.infrastructure.alist_service import AListService
            if AListService.is_available():
                threading.Thread(target=self._alist_start_worker, daemon=True).start()
        except Exception as e:
            logger.debug(f"AList auto-start check skipped: {e}")

    def _alist_start_worker(self):
        from src.infrastructure.alist_service import AListService
        if AListService.start():
            AListService.wait_ready(timeout=15)

    def _stop_alist(self):
        try:
            from src.infrastructure.alist_service import AListService
            AListService.stop()
        except Exception:
            pass

    def _save_state(self):
        try:
            if self._current_folder and os.path.isdir(self._current_folder):
                root_part = os.path.splitdrive(self._current_folder)[1]
                if root_part not in ("\\", "/", ""):
                    self._config_manager.set("State", "LastFolder", self._current_folder)
            self._config_manager.set("State", "LastDirType", self._current_dir_type or "folder")
            self._config_manager.set("State", "LastDirExtra", self._current_dir_extra or "")
            track = self._playback_manager.get_current_track()
            if track:
                sp = track.get("path", "")
                if sp and os.path.exists(sp):
                    self._config_manager.set("State", "LastSong", sp)
                    self._config_manager.set("State", "LastPosition", str(self._playback_manager.get_position()))
            self._config_manager.set("State", "LastVolume", str(self._playback_manager.get_volume()))
            logger.info("State saved")
        except Exception as e:
            logger.error(f"Save state error: {e}")

    def _restore_state(self):
        try:
            last_dir_type = self._config_manager.get("State", "LastDirType", "folder")
            last_dir_extra = self._config_manager.get("State", "LastDirExtra", "")
            self._current_dir_type = last_dir_type
            self._current_dir_extra = last_dir_extra

            if last_dir_type == "folder":
                last_folder = self._config_manager.get("State", "LastFolder", "")
                if last_folder and os.path.isdir(last_folder):
                    self._current_folder = last_folder
                    self._load_file_list_async(last_folder)
                    self._select_tree_item_by_path(last_folder)
            elif last_dir_type == "favorites":
                self._select_tree_item_by_type("favorites")
                self._load_favorites_list()
            elif last_dir_type == "play_history":
                self._select_tree_item_by_type("play_history")
                self._load_play_history()
            elif last_dir_type == "user_playlist" and last_dir_extra:
                pid = int(last_dir_extra)
                self._select_tree_item_by_type_and_extra("user_playlist", "playlist_id", pid)
                self._load_user_playlist(pid)
            elif last_dir_type == "genre" and last_dir_extra:
                self._select_tree_item_by_type_and_extra("genre", "genre", last_dir_extra)
                self._load_genre_songs(last_dir_extra)
            else:
                last_folder = self._config_manager.get("State", "LastFolder", "")
                if last_folder and os.path.isdir(last_folder):
                    self._current_folder = last_folder
                    self._load_file_list_async(last_folder)
                    self._select_tree_item_by_path(last_folder)
            vol = self._config_manager.get("State", "LastVolume", None)
            if vol is None:
                vol = self._config_manager.get("Playback", "DefaultVolume", 80)
            self._slider_volume.setValue(int(vol))
            self._playback_manager.set_volume(int(vol))

            default_mode = self._config_manager.get("Playback", "DefaultPlayMode", 0)
            modes = [PLAY_MODE_SEQUENCE, PLAY_MODE_LOOP_ALL, PLAY_MODE_LOOP_SINGLE, PLAY_MODE_RANDOM]
            mode_names = ["Sequence", "Loop All", "Loop Single", "Random"]
            if 0 <= default_mode < len(modes):
                self._playback_manager.set_play_mode(modes[default_mode])
                self._update_mode_icon()

            rewind_step = self._config_manager.get("Playback", "RewindStep", 15)
            self._btn_backward.setToolTip(I18n.tf("main.tooltip.rewind_step", step=rewind_step))
            forward_step = self._config_manager.get("Playback", "ForwardStep", 15)
            self._btn_forward.setToolTip(I18n.tf("main.tooltip.forward_step", step=forward_step))

            always_on_top = self._config_manager.get("Appearance", "AlwaysOnTop", True)
            if always_on_top:
                flags = self.windowFlags() | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                self.setWindowFlags(flags)
                self.show()
                self.raise_()
                self.activateWindow()

            show_grid = self._config_manager.get("Appearance", "ShowGrid", False)
            self._file_table.setShowGrid(show_grid)

            font_size = self._config_manager.get("Lyric", "FontSize", 16)
            self._lyric_panel.set_font_size(font_size)
            self._lyric_active_color = self._config_manager.get("Lyric", "ActiveColor", "#32c864")
            self._lyric_inactive_color = self._config_manager.get("Lyric", "InactiveColor", "#a0a0a0")

            theme_name = self._config_manager.get("Appearance", "ThemeName", "Midnight Blue")
            self._apply_theme(theme_name)

            self._load_shortcuts()

            logger.info("State restored")
        except Exception as e:
            logger.error(f"Restore state error: {e}")

    def nativeEvent(self, eventType, message):
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST:
                    from PySide6.QtGui import QCursor
                    cursor_pos = QCursor.pos()

                    if hasattr(self, '_btn_minimize'):
                        for btn in [self._btn_help, self._btn_minimize, self._btn_maximize, self._btn_close]:
                            local_pos = btn.mapFromGlobal(cursor_pos)
                            if btn.rect().contains(local_pos):
                                return super().nativeEvent(eventType, message)

                    if hasattr(self, '_title_bar'):
                        title_local = self._title_bar.mapFromGlobal(cursor_pos)
                        if self._title_bar.rect().contains(title_local):
                            return True, HTCAPTION

                    if not self.isMaximized():
                        rect = self.frameGeometry()
                        x = cursor_pos.x() - rect.left()
                        y = cursor_pos.y() - rect.top()
                        w = rect.width()
                        h = rect.height()
                        bw = BORDER_WIDTH

                        on_left = 0 <= x < bw
                        on_right = w - bw <= x < w
                        on_top = 0 <= y < bw
                        on_bottom = h - bw <= y < h

                        if on_top and on_left:
                            return True, HTTOPLEFT
                        elif on_top and on_right:
                            return True, HTTOPRIGHT
                        elif on_bottom and on_left:
                            return True, HTBOTTOMLEFT
                        elif on_bottom and on_right:
                            return True, HTBOTTOMRIGHT
                        elif on_left:
                            return True, HTLEFT
                        elif on_right:
                            return True, HTRIGHT
                        elif on_top:
                            return True, HTTOP
                        elif on_bottom:
                            return True, HTBOTTOM
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        minimize_to_tray = self._config_manager.get("Appearance", "MinimizeToTray", False)
        if minimize_to_tray and not self._mini_mode:
            event.ignore()
            if hasattr(self, '_help_window'):
                self._help_window.hide()
            self.hide()
            return
        self._save_state()
        self._playback_manager.stop()
        self._timer.stop()
        self._stop_alist()
        if hasattr(self, '_help_window'):
            self._help_window.deleteLater()
        if self._mini_window:
            self._mini_window.close()
        if self._tray_icon:
            self._tray_icon.hide()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Music++")
    app.setApplicationVersion("2.0.0")

    from src.business.config_manager import ConfigManager
    locale = ConfigManager().get("General", "Language", "en_US")
    if locale == "zh-CN":
        locale = "zh_CN"
    elif locale == "en-US" or locale == "en_US":
        locale = "en_US"

    from src.business.i18n_service import I18n
    I18n.init(locale)
    I18n.refresh_from_code()

    audio = AudioService()
    if not audio.initialize():
        log_msgbox("critical", I18n.t("main.msg.audio_init_failed_title"), I18n.t("main.msg.audio_init_failed_body"))
        ThemedMessageBox.critical(None, I18n.t("main.msg.audio_init_failed_title"), I18n.t("main.msg.audio_init_failed_body"))
        sys.exit(1)

    from src.core.network_service import apply_urllib_proxy
    apply_urllib_proxy()

    def cleanup():
        try:
            from src.core.database_service import DatabaseService
            from src.utils.metadata_db import MetadataDB
            from src.infrastructure.ecdict_provider import ECDictProvider
            from src.core.event_bus import EventBus

            DatabaseService()._cleanup()
            MetadataDB()._cleanup()
            ECDictProvider().close()

            bus = EventBus()
            if hasattr(bus, '_executor'):
                bus._executor.shutdown(wait=False)

            from src.core.network_service import NetworkService
            NetworkService()._session.close()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    app.aboutToQuit.connect(cleanup)

    window = MainWindow()
    window.show()
    QTimer.singleShot(500, window._restore_state)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
