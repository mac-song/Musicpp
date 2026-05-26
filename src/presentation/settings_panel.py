import os
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QComboBox, QSpinBox, QCheckBox, QListWidget, QListWidgetItem,
    QStackedWidget, QFileDialog, QFormLayout, QGroupBox, QSlider,
    QColorDialog, QKeySequenceEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QDialogButtonBox,
    QScrollArea, QSizePolicy, QFrame, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QKeySequence, QPainter, QPen, QTextCharFormat
from PySide6.QtCore import QThread
from src.utils.svg_icons import get_icon
from src.plugins.whisper_plugin import WHISPER_MODELS, PIP_MIRRORS, HF_MIRRORS
from src.utils.logger import log_msgbox
from src.business.i18n_service import I18n
from src.presentation.themed_dialog import ThemedMessageBox, ThemedDialog


class WhisperInstallWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(bool)

    def __init__(self, mirror_url=""):
        super().__init__()
        self._mirror_url = mirror_url

    def run(self):
        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()
        ok = plugin.install(
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct),
            mirror_url=self._mirror_url,
        )
        self.finished.emit(ok)


class WhisperUninstallWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(bool)

    def run(self):
        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()
        ok = plugin.uninstall(
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct),
        )
        self.finished.emit(ok)


class WhisperDownloadModelWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(bool)

    def __init__(self, model_name, hf_mirror_url=""):
        super().__init__()
        self._model_name = model_name
        self._hf_mirror_url = hf_mirror_url

    def run(self):
        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()
        ok = plugin.download_model(
            self._model_name,
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct),
            hf_mirror_url=self._hf_mirror_url,
        )
        self.finished.emit(ok)


class DictDownloadWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(bool, str)

    ECDICT_MIRRORS = [
        (I18n.t("dict.mirror_ghfast"), "https://ghfast.top/https://github.com/skywind3000/ECDICT/releases/download/1.0.28/stardict.7z"),
        (I18n.t("dict.mirror_ghproxy"), "https://ghproxy.cn/https://github.com/skywind3000/ECDICT/releases/download/1.0.28/stardict.7z"),
        (I18n.t("dict.mirror_github"), "https://github.com/skywind3000/ECDICT/releases/download/1.0.28/stardict.7z"),
    ]

    def run(self):
        try:
            import os
            from src.infrastructure.ecdict_provider import _get_ecdict_dir, get_ecdict_db_path

            ecdict_dir = _get_ecdict_dir()
            db_path = get_ecdict_db_path()

            if os.path.isfile(db_path):
                try:
                    os.remove(db_path)
                except Exception:
                    pass

            import urllib.request

            tmp_7z = os.path.join(ecdict_dir, "stardict.7z")
            downloaded = False
            last_error = ""

            for mirror_name, url in self.ECDICT_MIRRORS:
                self.progress.emit(I18n.tf("dict.msg_trying_mirror", name=mirror_name), 5)
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

                    def _reporthook(block_num, block_size, total_size):
                        downloaded_bytes = block_num * block_size
                        if total_size > 0:
                            pct = min(int(downloaded_bytes / total_size * 80) + 5, 85)
                            mb = downloaded_bytes / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            self.progress.emit(I18n.tf("dict.msg_downloading", name=mirror_name, mb=mb, total_mb=total_mb), pct)

                    urllib.request.urlretrieve(url, tmp_7z, _reporthook)

                    if os.path.isfile(tmp_7z) and os.path.getsize(tmp_7z) > 100000:
                        downloaded = True
                        break
                    else:
                        if os.path.isfile(tmp_7z):
                            os.remove(tmp_7z)
                        last_error = I18n.tf("dict.msg_size_abnormal", name=mirror_name)
                except Exception as e:
                    last_error = f"{mirror_name}: {e}"
                    if os.path.isfile(tmp_7z):
                        try:
                            os.remove(tmp_7z)
                        except Exception:
                            pass
                    continue

            if not downloaded:
                self.finished.emit(False, I18n.tf("dict.msg_all_mirrors_failed", error=last_error))
                return

            self.progress.emit(I18n.t("dict.msg_extracting"), 88)

            try:
                import py7zr
                with py7zr.SevenZipFile(tmp_7z, 'r') as z:
                    z.extractall(path=ecdict_dir)
            except ImportError:
                import subprocess
                seven_zip = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "7z.exe")
                if not os.path.isfile(seven_zip):
                    seven_zip = "7z"
                result = subprocess.run(
                    [seven_zip, "x", tmp_7z, f"-o{ecdict_dir}", "-y"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode != 0:
                    self.finished.emit(False, I18n.tf("dict.msg_extract_fail", error=result.stderr[:200]))
                    return

            try:
                os.remove(tmp_7z)
            except Exception:
                pass

            extracted_db = os.path.join(ecdict_dir, "stardict.db")
            if os.path.isfile(extracted_db) and not os.path.isfile(db_path):
                os.rename(extracted_db, db_path)

            if not os.path.isfile(db_path):
                for f in os.listdir(ecdict_dir):
                    if f.endswith(".db"):
                        src = os.path.join(ecdict_dir, f)
                        if not os.path.isfile(db_path):
                            os.rename(src, db_path)
                        break

            if os.path.isfile(db_path):
                self.progress.emit(I18n.t("dict.msg_download_done"), 100)
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, I18n.t("dict.msg_db_not_found"))

        except Exception as e:
            self.finished.emit(False, str(e))


class ColorSwatchBar(QWidget):
    def __init__(self, keys: list, height: int = 28, parent=None):
        super().__init__(parent)
        self._keys = keys
        self._colors = {}
        self._hover_index = -1
        self._bar_height = height
        self.setFixedHeight(height)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def set_colors(self, colors: dict):
        self._colors = colors
        self.update()

    def paintEvent(self, event):
        if not self._keys:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        w = self.width()
        n = len(self._keys)
        sw = w / n
        for i, (key, tip) in enumerate(self._keys):
            color = self._colors.get(key, "#333")
            painter.fillRect(int(i * sw), 0, int(sw) + 1, self._bar_height, QColor(color))
            if i == self._hover_index:
                painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
                painter.drawRect(int(i * sw) + 1, 1, int(sw) - 2, self._bar_height - 2)
        painter.end()

    def mouseMoveEvent(self, event):
        n = len(self._keys)
        if n == 0:
            return
        sw = self.width() / n
        idx = int(event.x() / sw)
        if idx < 0:
            idx = 0
        if idx >= n:
            idx = n - 1
        if idx != self._hover_index:
            self._hover_index = idx
            key, tip = self._keys[idx]
            color = self._colors.get(key, "")
            self.setToolTip(f"{tip}: {color}")
            self.update()

    def leaveEvent(self, event):
        self._hover_index = -1
        self.update()


class SettingsPanel(QWidget):
    settings_changed = Signal(str, object)

    _NAV_KEYS = [
        "settings.nav.appearance", "settings.nav.theme", "settings.nav.shortcuts",
        "settings.nav.playback", "settings.nav.audio_plugins", "settings.nav.source_plugins",
        "settings.nav.lyric_plugins", "settings.nav.study", "settings.nav.webdav",
        "settings.nav.network", "settings.nav.logs", "settings.nav.about",
    ]

    _SHORTCUT_DEFS = [
        ("PlayPause", "settings.shortcuts.play_pause", "Ctrl+P"),
        ("Stop", "settings.shortcuts.stop", "Ctrl+S"),
        ("PrevTrack", "settings.shortcuts.prev_track", "Ctrl+Left"),
        ("NextTrack", "settings.shortcuts.next_track", "Ctrl+Right"),
        ("SeekBackward", "settings.shortcuts.seek_backward", "Left"),
        ("SeekForward", "settings.shortcuts.seek_forward", "Right"),
        ("VolumeUp", "settings.shortcuts.volume_up", "Up"),
        ("VolumeDown", "settings.shortcuts.volume_down", "Down"),
        ("ToggleLyric", "settings.shortcuts.toggle_lyric", "Ctrl+L"),
        ("ToggleSource", "settings.shortcuts.toggle_source", "Ctrl+T"),
        ("ToggleMini", "settings.shortcuts.toggle_mini", "Ctrl+M"),
        ("ToggleSettings", "settings.shortcuts.toggle_settings", "Ctrl+,"),
        ("OpenFile", "settings.shortcuts.open_file", "Ctrl+O"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        I18n.locale_changed.connect(self._on_locale_changed)

    def _init_ui(self):
        font = QFont("Microsoft YaHei", 9)
        self.setFont(font)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(160)
        self._nav_list.setFont(QFont("Microsoft YaHei", 10))
        self._nav_list.setSpacing(0)
        self._nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav_list.setCurrentRow(0)
        self._nav_list.currentItemChanged.connect(self._on_nav_changed)
        for key in self._NAV_KEYS:
            list_item = QListWidgetItem(I18n.t(key))
            list_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            list_item.setSizeHint(QSize(140, 32))
            list_item.setData(Qt.UserRole, key)
            self._nav_list.addItem(list_item)

        self._stacked = QStackedWidget()
        self._stacked.addWidget(self._wrap_scroll(self._build_appearance_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_theme_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_shortcuts_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_playback_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_audio_plugins_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_source_plugins_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_lyric_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_study_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_webdav_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_network_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_logs_page()))
        self._stacked.addWidget(self._wrap_scroll(self._build_about_page()))

        main_layout.addWidget(self._nav_list)
        main_layout.addWidget(self._stacked, 1)

    def _on_language_changed(self, index):
        locale = "zh_CN" if index == 0 else "en_US"
        from src.business.i18n_service import I18n
        I18n.set_locale(locale)
        from src.business.config_manager import ConfigManager
        ConfigManager().set("General", "Language", locale)
        self.settings_changed.emit("appearance/language", locale)

    def _on_locale_changed(self, locale):
        for i in range(self._nav_list.count()):
            item = self._nav_list.item(i)
            key = item.data(Qt.UserRole)
            if key:
                item.setText(I18n.t(key))

    def _on_nav_changed(self, current, previous):
        if current is None:
            return
        row = self._nav_list.row(current)
        if 0 <= row < self._stacked.count():
            self._stacked.setCurrentIndex(row)

    def _wrap_scroll(self, content_widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content_widget)
        return scroll

    # ── Lyric Page ──────────────────────────────────────────────

    def _build_lyric_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        source_group = QGroupBox(I18n.t("settings.lyric.group_sources"))
        source_layout = QHBoxLayout(source_group)
        source_layout.setSpacing(8)

        self._lyric_source_list = QListWidget()
        self._lyric_source_list.setDragDropMode(QListWidget.InternalMove)
        self._lyric_source_list.setMinimumHeight(80)
        source_items = [
            ("lrclib", I18n.t("settings.lyric.source_lrclib_name"), I18n.t("settings.lyric.source_lrclib_desc")),
            ("netease", I18n.t("settings.lyric.source_netease_name"), I18n.t("settings.lyric.source_netease_desc")),
            ("gequbao", I18n.t("settings.lyric.source_gequbao_name"), I18n.t("settings.lyric.source_gequbao_desc")),
        ]
        for source_id, name, desc in source_items:
            item = QListWidgetItem(f"{name}  —  {desc}")
            item.setData(Qt.UserRole, source_id)
            item.setCheckState(Qt.Checked)
            self._lyric_source_list.addItem(item)
        source_layout.addWidget(self._lyric_source_list, 1)

        src_btn_col = QVBoxLayout()
        src_btn_col.setSpacing(4)
        self._btn_source_up = QPushButton()
        self._btn_source_up.setIcon(get_icon("chevron-up", "#ccc", 14))
        self._btn_source_up.setToolTip(I18n.t("settings.lyric.btn_move_up"))
        self._btn_source_up.setFixedSize(28, 28)
        self._btn_source_up.clicked.connect(lambda: self._move_list_item(self._lyric_source_list, -1))
        self._btn_source_down = QPushButton()
        self._btn_source_down.setIcon(get_icon("chevron-down", "#ccc", 14))
        self._btn_source_down.setToolTip(I18n.t("settings.lyric.btn_move_down"))
        self._btn_source_down.setFixedSize(28, 28)
        self._btn_source_down.clicked.connect(lambda: self._move_list_item(self._lyric_source_list, 1))
        src_btn_col.addWidget(self._btn_source_up)
        src_btn_col.addWidget(self._btn_source_down)
        src_btn_col.addStretch()
        source_layout.addLayout(src_btn_col)

        layout.addWidget(source_group)

        auto_group = QGroupBox(I18n.t("settings.lyric.group_auto_sync"))
        auto_layout = QHBoxLayout(auto_group)
        auto_layout.setSpacing(20)

        self._chk_auto_download_play = QCheckBox(I18n.t("settings.lyric.auto_download_on_play"))
        self._chk_auto_download_play.setChecked(True)
        self._chk_auto_download_play.toggled.connect(
            lambda v: self.settings_changed.emit("lyric/auto_download_on_play", v)
        )
        auto_layout.addWidget(self._chk_auto_download_play)

        self._chk_overwrite_existing = QCheckBox(I18n.t("settings.lyric.overwrite_existing"))
        self._chk_overwrite_existing.setChecked(False)
        self._chk_overwrite_existing.toggled.connect(
            lambda v: self.settings_changed.emit("lyric/overwrite_existing", v)
        )
        auto_layout.addWidget(self._chk_overwrite_existing)

        layout.addWidget(auto_group)

        match_group = QGroupBox(I18n.t("settings.lyric.group_matching"))
        match_layout = QFormLayout(match_group)
        match_layout.setLabelAlignment(Qt.AlignRight)

        self._cmb_match_tolerance = QComboBox()
        self._cmb_match_tolerance.addItems([I18n.t("settings.lyric.tolerance_strict"), I18n.t("settings.lyric.tolerance_5s"), I18n.t("settings.lyric.tolerance_10s"), I18n.t("settings.lyric.tolerance_ignore")])
        self._cmb_match_tolerance.setCurrentIndex(0)
        self._cmb_match_tolerance.currentIndexChanged.connect(
            lambda i: self.settings_changed.emit("lyric/match_tolerance", i)
        )
        match_layout.addRow(I18n.t("settings.lyric.duration_tolerance"), self._cmb_match_tolerance)

        layout.addWidget(match_group)

        display_group = QGroupBox(I18n.t("settings.lyric.group_display"))
        display_layout = QFormLayout(display_group)
        display_layout.setLabelAlignment(Qt.AlignRight)

        self._spn_lyric_font_size = QSpinBox()
        self._spn_lyric_font_size.setRange(10, 32)
        self._spn_lyric_font_size.setValue(16)
        self._spn_lyric_font_size.valueChanged.connect(
            lambda v: self.settings_changed.emit("lyric/font_size", v)
        )
        display_layout.addRow(I18n.t("settings.lyric.font_size"), self._spn_lyric_font_size)

        color_row = QHBoxLayout()
        color_row.setSpacing(16)

        active_col = QHBoxLayout()
        active_col.setSpacing(4)
        active_lbl = QLabel(I18n.t("settings.lyric.color_active"))
        self._btn_active_color = QPushButton()
        self._btn_active_color.setFixedSize(40, 24)
        from src.infrastructure.theme_engine import ThemeEngine
        _tc = ThemeEngine().get_current_colors()
        self._active_color = QColor(_tc.get("lyric_active", "#32c864"))
        self._btn_active_color.setStyleSheet(f"background-color: {self._active_color.name()}; border: 1px solid #555;")
        self._btn_active_color.clicked.connect(lambda: self._pick_color("_active_color", "_btn_active_color", "lyric/active_color"))
        active_col.addStretch()
        active_col.addWidget(active_lbl)
        active_col.addWidget(self._btn_active_color)
        active_col.addStretch()
        color_row.addLayout(active_col, 1)

        inactive_col = QHBoxLayout()
        inactive_col.setSpacing(4)
        inactive_lbl = QLabel(I18n.t("settings.lyric.color_inactive"))
        self._btn_inactive_color = QPushButton()
        self._btn_inactive_color.setFixedSize(40, 24)
        self._inactive_color = QColor(_tc.get("lyric_inactive", "#a0a0b0"))
        self._btn_inactive_color.setStyleSheet(f"background-color: {self._inactive_color.name()}; border: 1px solid #555;")
        self._btn_inactive_color.clicked.connect(lambda: self._pick_color("_inactive_color", "_btn_inactive_color", "lyric/inactive_color"))
        inactive_col.addStretch()
        inactive_col.addWidget(inactive_lbl)
        inactive_col.addWidget(self._btn_inactive_color)
        inactive_col.addStretch()
        color_row.addLayout(inactive_col, 1)

        display_layout.addRow(I18n.t("settings.lyric.line_color"), color_row)

        layout.addWidget(display_group)
        layout.addStretch()

        return page

    def load_from_config(self, config):
        self._spn_lyric_font_size.blockSignals(True)
        self._spn_lyric_font_size.setValue(config.get("Lyric", "FontSize", 16))
        self._spn_lyric_font_size.blockSignals(False)

        self._chk_auto_download_play.blockSignals(True)
        self._chk_auto_download_play.setChecked(config.get("Lyric", "AutoDownloadOnPlay", True))
        self._chk_auto_download_play.blockSignals(False)

        self._chk_overwrite_existing.blockSignals(True)
        self._chk_overwrite_existing.setChecked(config.get("Lyric", "OverwriteExisting", False))
        self._chk_overwrite_existing.blockSignals(False)

        self._cmb_match_tolerance.blockSignals(True)
        self._cmb_match_tolerance.setCurrentIndex(config.get("Lyric", "MatchTolerance", 0))
        self._cmb_match_tolerance.blockSignals(False)

        active_color = config.get("Lyric", "ActiveColor", "#32c864")
        self._active_color = QColor(active_color)
        self._btn_active_color.setStyleSheet(f"background-color: {self._active_color.name()}; border: 1px solid #555;")

        inactive_color = config.get("Lyric", "InactiveColor", "#a0a0a0")
        self._inactive_color = QColor(inactive_color)
        self._btn_inactive_color.setStyleSheet(f"background-color: {self._inactive_color.name()}; border: 1px solid #555;")

        self._cmb_default_play_mode.blockSignals(True)
        self._cmb_default_play_mode.setCurrentIndex(config.get("Playback", "DefaultPlayMode", 0))
        self._cmb_default_play_mode.blockSignals(False)

        self._chk_auto_play.blockSignals(True)
        self._chk_auto_play.setChecked(config.get("Playback", "AutoPlay", False))
        self._chk_auto_play.blockSignals(False)

        self._chk_resume_position.blockSignals(True)
        self._chk_resume_position.setChecked(config.get("Playback", "ResumePosition", True))
        self._chk_resume_position.blockSignals(False)

        self._spn_rewind_step.blockSignals(True)
        self._spn_rewind_step.setValue(config.get("Playback", "RewindStep", 15))
        self._spn_rewind_step.blockSignals(False)

        self._spn_forward_step.blockSignals(True)
        self._spn_forward_step.setValue(config.get("Playback", "ForwardStep", 15))
        self._spn_forward_step.blockSignals(False)

        self._spn_resume_offset.blockSignals(True)
        self._spn_resume_offset.setValue(config.get("Playback", "ResumeOffset", 500))
        self._spn_resume_offset.blockSignals(False)

        self._sld_default_volume.blockSignals(True)
        vol = config.get("Playback", "DefaultVolume", 80)
        self._sld_default_volume.setValue(vol)
        self._lbl_default_volume.setText(str(vol))
        self._sld_default_volume.blockSignals(False)

        self._chk_wheel_volume.blockSignals(True)
        self._chk_wheel_volume.setChecked(config.get("Playback", "WheelVolume", True))
        self._chk_wheel_volume.blockSignals(False)

        self._chk_exit_on_list_end.blockSignals(True)
        self._chk_exit_on_list_end.setChecked(config.get("Playback", "ExitOnListEnd", False))
        self._chk_exit_on_list_end.blockSignals(False)

        self._chk_exit_after_track.blockSignals(True)
        self._chk_exit_after_track.setChecked(config.get("Playback", "ExitAfterTrack", False))
        self._chk_exit_after_track.blockSignals(False)

        self._cmb_theme.blockSignals(True)
        theme_name = config.get("Appearance", "ThemeName", "Midnight Blue")
        idx = self._cmb_theme.findText(theme_name)
        if idx >= 0:
            self._cmb_theme.setCurrentIndex(idx)
        self._update_theme_preview(theme_name)
        self._update_theme_buttons(theme_name)
        self._cmb_theme.blockSignals(False)

        self._cmb_language.blockSignals(True)
        from src.business.i18n_service import I18n
        current_locale = I18n.locale
        self._cmb_language.setCurrentIndex(0 if current_locale == "zh_CN" else 1)
        self._cmb_language.blockSignals(False)

        self._chk_always_on_top.blockSignals(True)
        self._chk_always_on_top.setChecked(config.get("Appearance", "AlwaysOnTop", True))
        self._chk_always_on_top.blockSignals(False)

        self._chk_minimize_tray.blockSignals(True)
        self._chk_minimize_tray.setChecked(config.get("Appearance", "MinimizeToTray", False))
        self._chk_minimize_tray.blockSignals(False)

        self._chk_show_grid.blockSignals(True)
        self._chk_show_grid.setChecked(config.get("Appearance", "ShowGrid", False))
        self._chk_show_grid.blockSignals(False)

        self._chk_natural_sort.blockSignals(True)
        self._chk_natural_sort.setChecked(config.get("Appearance", "NaturalSort", True))
        self._chk_natural_sort.blockSignals(False)

        self._chk_show_cover.blockSignals(True)
        self._chk_show_cover.setChecked(config.get("Appearance", "ShowCover", True))
        self._chk_show_cover.blockSignals(False)

        self._cmb_proxy_type.blockSignals(True)
        self._cmb_proxy_type.setCurrentIndex(config.get("Network", "ProxyType", 0))
        self._cmb_proxy_type.blockSignals(False)

        self._txt_proxy_addr.blockSignals(True)
        self._txt_proxy_addr.setText(config.get("Network", "ProxyAddr", "127.0.0.1"))
        self._txt_proxy_addr.blockSignals(False)

        self._spn_proxy_port.blockSignals(True)
        self._spn_proxy_port.setValue(config.get("Network", "ProxyPort", 7890))
        self._spn_proxy_port.blockSignals(False)

        self._spn_timeout.blockSignals(True)
        self._spn_timeout.setValue(config.get("Network", "Timeout", 30))
        self._spn_timeout.blockSignals(False)

        self._spn_retry.blockSignals(True)
        self._spn_retry.setValue(config.get("Network", "Retry", 3))
        self._spn_retry.blockSignals(False)

        self._spn_mini_font_size.blockSignals(True)
        self._spn_mini_font_size.setValue(config.get("Mini", "FontSize", 22))
        self._spn_mini_font_size.blockSignals(False)

        self._sld_mini_ctrl_opacity.blockSignals(True)
        ctrl_opacity = config.get("Mini", "CtrlBgOpacity", 80)
        self._sld_mini_ctrl_opacity.setValue(ctrl_opacity)
        self._lbl_mini_ctrl_opacity.setText(str(ctrl_opacity))
        self._sld_mini_ctrl_opacity.blockSignals(False)

        self._spn_mini_lyric_width.blockSignals(True)
        self._spn_mini_lyric_width.setValue(config.get("Mini", "LyricWidth", 0))
        self._spn_mini_lyric_width.blockSignals(False)

        self._spn_mini_lyric_height.blockSignals(True)
        self._spn_mini_lyric_height.setValue(config.get("Mini", "LyricHeight", 0))
        self._spn_mini_lyric_height.blockSignals(False)

        self._chk_mini_lyric_on_top.blockSignals(True)
        self._chk_mini_lyric_on_top.setChecked(config.get("Mini", "LyricAlwaysOnTop", True))
        self._chk_mini_lyric_on_top.blockSignals(False)

        mini_theme_name = config.get("Appearance", "MiniThemeName", "")
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        engine.set_mini_theme_name(mini_theme_name)
        self._cmb_mini_theme.blockSignals(True)
        if mini_theme_name:
            names = engine.get_theme_names()
            if mini_theme_name in names:
                idx = names.index(mini_theme_name) + 1
                self._cmb_mini_theme.setCurrentIndex(idx)
            else:
                self._cmb_mini_theme.setCurrentIndex(0)
        else:
            self._cmb_mini_theme.setCurrentIndex(0)
        self._cmb_mini_theme.blockSignals(False)
        self._update_mini_theme_preview(mini_theme_name)

        self.load_shortcuts_from_config(config)

        self._study_repeat_count.blockSignals(True)
        self._study_repeat_count.setValue(config.get("Study", "RepeatCount", 3))
        self._study_repeat_count.blockSignals(False)

        self._study_repeat_pause.blockSignals(True)
        self._study_repeat_pause.setValue(config.get("Study", "RepeatPauseSec", 3))
        self._study_repeat_pause.blockSignals(False)

        self._study_auto_next.blockSignals(True)
        self._study_auto_next.setChecked(config.get("Study", "AutoNextSentence", True))
        self._study_auto_next.blockSignals(False)

        self._chk_study_enabled.blockSignals(True)
        self._chk_study_enabled.setChecked(config.get("Study", "Enabled", True))
        self._chk_study_enabled.blockSignals(False)

        self._study_default_lang.blockSignals(True)
        lang = config.get("Study", "DefaultSubtitleLang", "en")
        idx = self._study_default_lang.findText(lang)
        if idx >= 0:
            self._study_default_lang.setCurrentIndex(idx)
        self._study_default_lang.blockSignals(False)

        self._study_default_lang_secondary.blockSignals(True)
        lang2 = config.get("Study", "DefaultSubtitleLangSecondary", "")
        if lang2:
            idx2 = self._study_default_lang_secondary.findText(lang2)
            if idx2 >= 0:
                self._study_default_lang_secondary.setCurrentIndex(idx2)
        self._study_default_lang_secondary.blockSignals(False)

        self._study_auto_split_gap.blockSignals(True)
        self._study_auto_split_gap.setValue(config.get("Study", "AutoSplitGap", 2000))
        self._study_auto_split_gap.blockSignals(False)

        self._chk_shadowing.blockSignals(True)
        self._chk_shadowing.setChecked(config.get("Study", "ShadowingEnabled", False))
        self._chk_shadowing.blockSignals(False)

        self._spn_shadowing_extra.blockSignals(True)
        self._spn_shadowing_extra.setValue(config.get("Study", "ShadowingExtraSec", 3))
        self._spn_shadowing_extra.blockSignals(False)

        self._spn_autoseg_threshold.blockSignals(True)
        self._spn_autoseg_threshold.setValue(config.get("Study", "AutoSegSilenceThreshold", 0))
        self._spn_autoseg_threshold.blockSignals(False)

        self._spn_autoseg_min_silence.blockSignals(True)
        self._spn_autoseg_min_silence.setValue(config.get("Study", "AutoSegMinSilenceMs", 300))
        self._spn_autoseg_min_silence.blockSignals(False)

        self._spn_autoseg_min_segment.blockSignals(True)
        self._spn_autoseg_min_segment.setValue(config.get("Study", "AutoSegMinSegmentMs", 800))
        self._spn_autoseg_min_segment.blockSignals(False)

        mat_dir = config.get("Study", "MaterialsDir", "")
        if mat_dir:
            self._study_materials_dir.setText(mat_dir)

        sessdata = config.get("Study", "BilibiliSESSDATA", "")
        if sessdata:
            self._bilibili_sessdata.setText(sessdata)

        self._spn_log_retain_months.blockSignals(True)
        self._spn_log_retain_months.setValue(config.get("Logs", "RetainMonths", 3))
        self._spn_log_retain_months.blockSignals(False)

    def _pick_color(self, attr_name, btn_attr_name, signal_key):
        current = getattr(self, attr_name, QColor(255, 255, 255))
        color = QColorDialog.getColor(current, self, "Select Color")
        if color.isValid():
            setattr(self, attr_name, color)
            btn = getattr(self, btn_attr_name)
            btn.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #555;")
            self.settings_changed.emit(signal_key, color.name())

    def _move_list_item(self, list_widget: QListWidget, direction: int):
        current_row = list_widget.currentRow()
        if current_row < 0:
            return
        new_row = current_row + direction
        if new_row < 0 or new_row >= list_widget.count():
            return
        item = list_widget.takeItem(current_row)
        list_widget.insertItem(new_row, item)
        list_widget.setCurrentRow(new_row)

    def get_lyric_sources(self) -> list:
        sources = []
        for i in range(self._lyric_source_list.count()):
            item = self._lyric_source_list.item(i)
            if item.checkState() == Qt.Checked:
                sources.append(item.data(Qt.UserRole))
        return sources if sources else ["lrclib", "netease"]

    # ── Playback Page ───────────────────────────────────────────

    def _build_playback_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        mode_group = QGroupBox(I18n.t("settings.playback.group_play_mode"))
        mode_layout = QFormLayout(mode_group)
        mode_layout.setLabelAlignment(Qt.AlignRight)

        self._cmb_default_play_mode = QComboBox()
        self._cmb_default_play_mode.addItems([I18n.t("settings.playback.mode_sequence"), I18n.t("settings.playback.mode_loop_all"), I18n.t("settings.playback.mode_loop_single"), I18n.t("settings.playback.mode_random")])
        self._cmb_default_play_mode.currentIndexChanged.connect(
            lambda i: self.settings_changed.emit("playback/default_play_mode", i)
        )
        mode_layout.addRow(I18n.t("settings.playback.default_play_mode"), self._cmb_default_play_mode)

        self._chk_auto_play = QCheckBox(I18n.t("settings.playback.auto_play"))
        self._chk_auto_play.setChecked(False)
        self._chk_auto_play.toggled.connect(
            lambda v: self.settings_changed.emit("playback/auto_play", v)
        )
        mode_layout.addRow("", self._chk_auto_play)

        self._chk_resume_position = QCheckBox(I18n.t("settings.playback.resume_position"))
        self._chk_resume_position.setChecked(True)
        self._chk_resume_position.toggled.connect(
            lambda v: self.settings_changed.emit("playback/resume_position", v)
        )
        mode_layout.addRow("", self._chk_resume_position)

        layout.addWidget(mode_group)

        skip_group = QGroupBox(I18n.t("settings.playback.group_skip"))
        skip_layout = QFormLayout(skip_group)
        skip_layout.setLabelAlignment(Qt.AlignRight)

        self._spn_rewind_step = QSpinBox()
        self._spn_rewind_step.setRange(5, 60)
        self._spn_rewind_step.setValue(15)
        self._spn_rewind_step.setSuffix(I18n.t("settings.playback.suffix_sec"))
        self._spn_rewind_step.valueChanged.connect(
            lambda v: self.settings_changed.emit("playback/rewind_step", v)
        )
        skip_layout.addRow(I18n.t("settings.playback.rewind_step"), self._spn_rewind_step)

        self._spn_forward_step = QSpinBox()
        self._spn_forward_step.setRange(5, 60)
        self._spn_forward_step.setValue(15)
        self._spn_forward_step.setSuffix(I18n.t("settings.playback.suffix_sec"))
        self._spn_forward_step.valueChanged.connect(
            lambda v: self.settings_changed.emit("playback/forward_step", v)
        )
        skip_layout.addRow(I18n.t("settings.playback.forward_step"), self._spn_forward_step)

        self._spn_resume_offset = QSpinBox()
        self._spn_resume_offset.setRange(0, 2000)
        self._spn_resume_offset.setValue(500)
        self._spn_resume_offset.setSuffix(I18n.t("settings.playback.suffix_ms"))
        self._spn_resume_offset.valueChanged.connect(
            lambda v: self.settings_changed.emit("playback/resume_offset", v)
        )
        skip_layout.addRow(I18n.t("settings.playback.resume_offset"), self._spn_resume_offset)

        layout.addWidget(skip_group)

        volume_group = QGroupBox(I18n.t("settings.playback.group_volume"))
        volume_layout = QVBoxLayout(volume_group)
        volume_layout.setSpacing(8)

        vol_row = QHBoxLayout()
        vol_lbl = QLabel(I18n.t("settings.playback.default_volume"))
        vol_lbl.setFixedWidth(100)
        self._sld_default_volume = QSlider(Qt.Horizontal)
        self._sld_default_volume.setRange(0, 100)
        self._sld_default_volume.setValue(80)
        self._lbl_default_volume = QLabel("80")
        self._lbl_default_volume.setFixedWidth(30)
        self._sld_default_volume.valueChanged.connect(self._on_volume_slider_changed)
        vol_row.addWidget(vol_lbl)
        vol_row.addWidget(self._sld_default_volume, 1)
        vol_row.addWidget(self._lbl_default_volume)
        volume_layout.addLayout(vol_row)

        self._chk_wheel_volume = QCheckBox(I18n.t("settings.playback.wheel_volume"))
        self._chk_wheel_volume.setChecked(True)
        self._chk_wheel_volume.toggled.connect(
            lambda v: self.settings_changed.emit("playback/wheel_volume", v)
        )
        volume_layout.addWidget(self._chk_wheel_volume)

        layout.addWidget(volume_group)

        exit_group = QGroupBox(I18n.t("settings.playback.group_exit"))
        exit_layout = QHBoxLayout(exit_group)
        exit_layout.setSpacing(20)

        self._chk_exit_on_list_end = QCheckBox(I18n.t("settings.playback.exit_on_list_end"))
        self._chk_exit_on_list_end.setChecked(False)
        self._chk_exit_on_list_end.toggled.connect(
            lambda v: self.settings_changed.emit("playback/exit_on_list_end", v)
        )
        exit_layout.addWidget(self._chk_exit_on_list_end)

        self._chk_exit_after_track = QCheckBox(I18n.t("settings.playback.exit_after_track"))
        self._chk_exit_after_track.setChecked(False)
        self._chk_exit_after_track.toggled.connect(
            lambda v: self.settings_changed.emit("playback/exit_after_track", v)
        )
        exit_layout.addWidget(self._chk_exit_after_track)

        layout.addWidget(exit_group)
        layout.addStretch()

        return page

    def _on_volume_slider_changed(self, value):
        self._lbl_default_volume.setText(str(value))
        self.settings_changed.emit("playback/default_volume", value)

    # ── Appearance Page ─────────────────────────────────────────

    def _build_appearance_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lang_group = QGroupBox(I18n.t("settings.appearance.group_language"))
        lang_layout = QFormLayout(lang_group)
        lang_layout.setLabelAlignment(Qt.AlignRight)
        self._cmb_language = QComboBox()
        self._cmb_language.addItems([I18n.t("settings.appearance.lang_chinese"), I18n.t("settings.appearance.lang_english")])
        self._cmb_language.setCurrentIndex(0)
        self._cmb_language.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addRow(I18n.t("settings.appearance.language"), self._cmb_language)
        layout.addWidget(lang_group)

        window_group = QGroupBox(I18n.t("settings.appearance.group_window"))
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(10)
        self._chk_always_on_top = QCheckBox(I18n.t("settings.appearance.always_on_top"))
        self._chk_always_on_top.setChecked(True)
        self._chk_always_on_top.toggled.connect(
            lambda v: self.settings_changed.emit("appearance/always_on_top", v)
        )
        window_layout.addWidget(self._chk_always_on_top)
        self._chk_minimize_tray = QCheckBox(I18n.t("settings.appearance.minimize_to_tray"))
        self._chk_minimize_tray.setChecked(False)
        self._chk_minimize_tray.toggled.connect(
            lambda v: self.settings_changed.emit("appearance/minimize_to_tray", v)
        )
        window_layout.addWidget(self._chk_minimize_tray)
        layout.addWidget(window_group)

        list_group = QGroupBox(I18n.t("settings.appearance.group_file_list"))
        list_layout = QVBoxLayout(list_group)
        list_layout.setSpacing(10)
        self._chk_show_grid = QCheckBox(I18n.t("settings.appearance.show_grid"))
        self._chk_show_grid.setChecked(False)
        self._chk_show_grid.toggled.connect(
            lambda v: self.settings_changed.emit("appearance/show_grid", v)
        )
        list_layout.addWidget(self._chk_show_grid)
        self._chk_natural_sort = QCheckBox(I18n.t("settings.appearance.natural_sort"))
        self._chk_natural_sort.setChecked(True)
        self._chk_natural_sort.toggled.connect(
            lambda v: self.settings_changed.emit("appearance/natural_sort", v)
        )
        list_layout.addWidget(self._chk_natural_sort)
        layout.addWidget(list_group)

        cover_group = QGroupBox(I18n.t("settings.appearance.group_cover_art"))
        cover_layout = QVBoxLayout(cover_group)
        cover_layout.setSpacing(10)
        self._chk_show_cover = QCheckBox(I18n.t("settings.appearance.show_cover"))
        self._chk_show_cover.setChecked(True)
        self._chk_show_cover.toggled.connect(
            lambda v: self.settings_changed.emit("appearance/show_cover", v)
        )
        cover_layout.addWidget(self._chk_show_cover)
        layout.addWidget(cover_group)

        layout.addStretch()
        return page

    # ── Theme Page ──────────────────────────────────────────────

    def _build_theme_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        select_group = QGroupBox(I18n.t("settings.theme.group_select"))
        select_layout = QVBoxLayout(select_group)
        select_layout.setSpacing(8)

        combo_row = QHBoxLayout()
        combo_row.setSpacing(8)
        lbl_theme = QLabel(I18n.t("settings.theme.label"))
        lbl_theme.setFixedWidth(60)
        self._cmb_theme = QComboBox()
        self._cmb_theme.currentIndexChanged.connect(self._on_theme_combo_changed)
        combo_row.addWidget(lbl_theme)
        combo_row.addWidget(self._cmb_theme, 1)
        select_layout.addLayout(combo_row)

        self._theme_preview_keys = [
            ("window_bg", "Window BG"), ("surface", "Surface"), ("surface_alt", "Surface Alt"),
            ("border", "Border"), ("text_primary", "Text"), ("text_secondary", "Text 2nd"),
            ("accent", "Accent"), ("accent_hover", "Accent Hover"), ("danger", "Danger"),
            ("warning", "Warning"), ("success", "Success"), ("info", "Info"),
        ]
        self._theme_swatch = ColorSwatchBar(self._theme_preview_keys, height=28)
        select_layout.addWidget(self._theme_swatch)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._btn_edit_theme = QPushButton()
        self._btn_edit_theme.setIcon(get_icon("edit-3", "#ccc", 14))
        self._btn_edit_theme.setToolTip(I18n.t("settings.theme.btn_edit"))
        self._btn_edit_theme.setFixedSize(28, 28)
        self._btn_edit_theme.clicked.connect(self._on_edit_theme)
        self._btn_duplicate_theme = QPushButton()
        self._btn_duplicate_theme.setIcon(get_icon("copy", "#ccc", 14))
        self._btn_duplicate_theme.setToolTip(I18n.t("settings.theme.btn_duplicate"))
        self._btn_duplicate_theme.setFixedSize(28, 28)
        self._btn_duplicate_theme.clicked.connect(self._on_duplicate_theme)
        self._btn_delete_theme = QPushButton()
        self._btn_delete_theme.setIcon(get_icon("trash-2", "#ccc", 14))
        self._btn_delete_theme.setToolTip(I18n.t("settings.theme.btn_delete"))
        self._btn_delete_theme.setFixedSize(28, 28)
        self._btn_delete_theme.clicked.connect(self._on_delete_theme)
        self._btn_import_theme = QPushButton()
        self._btn_import_theme.setIcon(get_icon("upload", "#ccc", 14))
        self._btn_import_theme.setToolTip(I18n.t("settings.theme.btn_import"))
        self._btn_import_theme.setFixedSize(28, 28)
        self._btn_import_theme.clicked.connect(self._on_import_theme)
        self._btn_export_theme = QPushButton()
        self._btn_export_theme.setIcon(get_icon("download", "#ccc", 14))
        self._btn_export_theme.setToolTip(I18n.t("settings.theme.btn_export"))
        self._btn_export_theme.setFixedSize(28, 28)
        self._btn_export_theme.clicked.connect(self._on_export_theme)
        for b in [self._btn_edit_theme, self._btn_duplicate_theme, self._btn_delete_theme,
                   self._btn_import_theme, self._btn_export_theme]:
            btn_row.addWidget(b)
        select_layout.addLayout(btn_row)

        layout.addWidget(select_group)

        info_label = QLabel(I18n.t("settings.theme.info_text"))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info_label)

        mini_group = QGroupBox(I18n.t("settings.theme.group_mini_mode"))
        mini_layout = QVBoxLayout(mini_group)
        mini_layout.setSpacing(8)

        mini_theme_row = QHBoxLayout()
        mini_theme_row.setSpacing(8)
        lbl_mini_theme = QLabel(I18n.t("settings.theme.mini_theme"))
        lbl_mini_theme.setFixedWidth(80)
        self._cmb_mini_theme = QComboBox()
        self._cmb_mini_theme.currentIndexChanged.connect(self._on_mini_theme_combo_changed)
        mini_theme_row.addWidget(lbl_mini_theme)
        mini_theme_row.addWidget(self._cmb_mini_theme, 1)
        mini_layout.addLayout(mini_theme_row)

        self._mini_theme_preview_keys = [
            ("window_bg", "Window BG"), ("surface", "Surface"), ("surface_alt", "Surface Alt"),
            ("border", "Border"), ("text_primary", "Text"), ("accent", "Accent"),
            ("accent_hover", "Accent Hover"), ("danger", "Danger"), ("warning", "Warning"),
            ("success", "Success"), ("lyric_active", "Lyric Active"), ("lyric_inactive", "Lyric Inactive"),
        ]
        self._mini_theme_swatch = ColorSwatchBar(self._mini_theme_preview_keys, height=28)
        mini_layout.addWidget(self._mini_theme_swatch)

        mini_ctrl_layout = QFormLayout()
        mini_ctrl_layout.setLabelAlignment(Qt.AlignRight)
        mini_ctrl_layout.setSpacing(6)

        ctrl_opacity_row = QHBoxLayout()
        self._sld_mini_ctrl_opacity = QSlider(Qt.Horizontal)
        self._sld_mini_ctrl_opacity.setRange(10, 100)
        self._sld_mini_ctrl_opacity.setValue(80)
        self._lbl_mini_ctrl_opacity = QLabel("80")
        self._lbl_mini_ctrl_opacity.setFixedWidth(30)
        self._sld_mini_ctrl_opacity.valueChanged.connect(self._on_mini_ctrl_opacity_changed)
        ctrl_opacity_row.addWidget(self._sld_mini_ctrl_opacity, 1)
        ctrl_opacity_row.addWidget(self._lbl_mini_ctrl_opacity)
        mini_ctrl_layout.addRow(I18n.t("settings.theme.ctrl_opacity"), ctrl_opacity_row)

        self._spn_mini_font_size = QSpinBox()
        self._spn_mini_font_size.setRange(8, 48)
        self._spn_mini_font_size.setValue(22)
        self._spn_mini_font_size.valueChanged.connect(
            lambda v: self.settings_changed.emit("mini/font_size", v)
        )
        mini_ctrl_layout.addRow(I18n.t("settings.theme.font_size"), self._spn_mini_font_size)

        size_row = QHBoxLayout()
        self._spn_mini_lyric_width = QSpinBox()
        self._spn_mini_lyric_width.setRange(0, 2000)
        self._spn_mini_lyric_width.setValue(0)
        self._spn_mini_lyric_width.setSuffix(I18n.t("settings.theme.suffix_px"))
        self._spn_mini_lyric_width.setSpecialValueText(I18n.t("settings.theme.auto"))
        self._spn_mini_lyric_width.valueChanged.connect(
            lambda v: self.settings_changed.emit("mini/lyric_width", v)
        )
        self._spn_mini_lyric_height = QSpinBox()
        self._spn_mini_lyric_height.setRange(0, 500)
        self._spn_mini_lyric_height.setValue(0)
        self._spn_mini_lyric_height.setSuffix(I18n.t("settings.theme.suffix_px"))
        self._spn_mini_lyric_height.setSpecialValueText(I18n.t("settings.theme.auto"))
        self._spn_mini_lyric_height.valueChanged.connect(
            lambda v: self.settings_changed.emit("mini/lyric_height", v)
        )
        size_row.addWidget(self._spn_mini_lyric_width)
        size_row.addWidget(QLabel("×"))
        size_row.addWidget(self._spn_mini_lyric_height)
        size_row.addStretch()
        mini_ctrl_layout.addRow(I18n.t("settings.theme.size_wh"), size_row)

        self._chk_mini_lyric_on_top = QCheckBox(I18n.t("settings.theme.always_on_top"))
        self._chk_mini_lyric_on_top.setChecked(True)
        self._chk_mini_lyric_on_top.toggled.connect(
            lambda v: self.settings_changed.emit("mini/lyric_always_on_top", v)
        )
        mini_ctrl_layout.addRow("", self._chk_mini_lyric_on_top)

        mini_layout.addLayout(mini_ctrl_layout)
        layout.addWidget(mini_group)

        layout.addStretch()

        self._refresh_theme_combo()
        self._refresh_mini_theme_combo()

        return page

    def _refresh_theme_combo(self):
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        names = engine.get_theme_names()
        current = engine.get_current_name()
        self._cmb_theme.blockSignals(True)
        self._cmb_theme.clear()
        for name in names:
            self._cmb_theme.addItem(name)
        idx = names.index(current) if current in names else 0
        self._cmb_theme.setCurrentIndex(idx)
        self._cmb_theme.blockSignals(False)
        self._update_theme_preview(current)
        self._update_theme_buttons(current)

    def _on_theme_combo_changed(self, index):
        name = self._cmb_theme.itemText(index)
        self.settings_changed.emit("appearance/theme_name", name)
        self._update_theme_preview(name)
        self._update_theme_buttons(name)
        mini_theme = self._cmb_mini_theme.currentText() if hasattr(self, '_cmb_mini_theme') else ""
        if mini_theme == "Same as Main" or not mini_theme:
            self._update_mini_theme_preview("")

    def _update_theme_preview(self, name):
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        theme = engine.get_theme(name)
        if not theme:
            return
        self._theme_swatch.set_colors(theme.get("colors", {}))
    def _update_theme_buttons(self, name):
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        is_builtin = name in engine.get_builtin_names()
        self._btn_delete_theme.setEnabled(not is_builtin)

    def _refresh_mini_theme_combo(self):
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        names = engine.get_theme_names()
        current_mini = engine.get_mini_theme_name()
        self._cmb_mini_theme.blockSignals(True)
        self._cmb_mini_theme.clear()
        self._cmb_mini_theme.addItem(I18n.t("settings.theme.same_as_main"))
        for name in names:
            self._cmb_mini_theme.addItem(name)
        if current_mini and current_mini in names:
            idx = names.index(current_mini) + 1
            self._cmb_mini_theme.setCurrentIndex(idx)
        else:
            self._cmb_mini_theme.setCurrentIndex(0)
        self._cmb_mini_theme.blockSignals(False)
        self._update_mini_theme_preview(current_mini)

    def _on_mini_theme_combo_changed(self, index):
        if index == 0:
            theme_name = ""
        else:
            theme_name = self._cmb_mini_theme.itemText(index)
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        engine.set_mini_theme_name(theme_name)
        self.settings_changed.emit("appearance/mini_theme_name", theme_name)
        self._update_mini_theme_preview(theme_name)

    def _update_mini_theme_preview(self, name):
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        if name:
            theme = engine.get_theme(name)
        else:
            theme = engine.get_current_theme()
        if not theme:
            return
        self._mini_theme_swatch.set_colors(theme.get("colors", {}))

    def _on_edit_theme(self):
        name = self._cmb_theme.currentText()
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        theme = engine.get_theme(name)
        if not theme:
            return
        dialog = ThemeEditDialog(theme, self)
        if dialog.exec() == ThemeEditDialog.Accepted:
            edited = dialog.get_theme_data()
            engine.save_theme(edited)
            if edited["name"] != name:
                self._refresh_theme_combo()
                idx = self._cmb_theme.findText(edited["name"])
                if idx >= 0:
                    self._cmb_theme.setCurrentIndex(idx)
            self.settings_changed.emit("appearance/theme_name", edited["name"])

    def _on_duplicate_theme(self):
        name = self._cmb_theme.currentText()
        from src.presentation.themed_dialog import ThemedInputDialog
        new_name, ok = ThemedInputDialog.getText(self, I18n.t("settings.theme.duplicate_title"), I18n.t("settings.theme.duplicate_label"), text=f"{name} (Copy)")
        if ok and new_name and new_name.strip():
            from src.infrastructure.theme_engine import ThemeEngine
            engine = ThemeEngine()
            if engine.duplicate_theme(name, new_name.strip()):
                self._refresh_theme_combo()
                idx = self._cmb_theme.findText(new_name.strip())
                if idx >= 0:
                    self._cmb_theme.setCurrentIndex(idx)

    def _on_delete_theme(self):
        name = self._cmb_theme.currentText()
        from src.infrastructure.theme_engine import ThemeEngine
        engine = ThemeEngine()
        if name in engine.get_builtin_names():
            return
        log_msgbox("question", I18n.t("settings.theme.delete_title"), I18n.tf("settings.theme.delete_msg", name=name))
        reply = ThemedMessageBox.question(self, I18n.t("settings.theme.delete_title"), I18n.tf("settings.theme.delete_msg", name=name),
                                          buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no")
        if reply == 1:
            engine.delete_theme(name)
            self._refresh_theme_combo()
            self.settings_changed.emit("appearance/theme_name", engine.get_current_name())

    def _on_import_theme(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, I18n.t("settings.theme.import_title"), "", I18n.t("settings.theme.import_filter"))
        if path:
            from src.infrastructure.theme_engine import ThemeEngine
            engine = ThemeEngine()
            if engine.import_theme(path):
                self._refresh_theme_combo()
                log_msgbox("info", I18n.t("settings.theme.import_success_title"), I18n.t("settings.theme.import_success_msg"))
                ThemedMessageBox.information(self, I18n.t("settings.theme.import_success_title"), I18n.t("settings.theme.import_success_msg"))
            else:
                log_msgbox("warning", I18n.t("settings.theme.import_fail_title"), I18n.t("settings.theme.import_fail_msg"))
                ThemedMessageBox.warning(self, I18n.t("settings.theme.import_fail_title"), I18n.t("settings.theme.import_fail_msg"))

    def _on_export_theme(self):
        name = self._cmb_theme.currentText()
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, I18n.t("settings.theme.export_title"), f"{name}.json", I18n.t("settings.theme.import_filter"))
        if path:
            from src.infrastructure.theme_engine import ThemeEngine
            engine = ThemeEngine()
            if not engine.export_theme(name, path):
                log_msgbox("warning", I18n.t("settings.theme.export_fail_title"), I18n.t("settings.theme.export_fail_msg"))
                ThemedMessageBox.warning(self, I18n.t("settings.theme.export_fail_title"), I18n.t("settings.theme.export_fail_msg"))
        layout.addStretch()

        return page

    def _on_mini_ctrl_opacity_changed(self, value):
        self._lbl_mini_ctrl_opacity.setText(str(value))
        self.settings_changed.emit("mini/ctrl_bg_opacity", value)

    # ── Source Plugins Page ─────────────────────────────────────

    def _build_source_plugins_page(self):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._btn_install_source_plugin = QPushButton(I18n.t("settings.source_plugin.install"))
        self._btn_install_source_plugin.setFont(QFont("Microsoft YaHei", 9))
        self._btn_install_source_plugin.clicked.connect(self._on_install_source_plugin)
        toolbar.addWidget(self._btn_install_source_plugin)
        self._btn_batch_import_plugins = QPushButton(I18n.t("settings.source_plugin.batch_import"))
        self._btn_batch_import_plugins.setFont(QFont("Microsoft YaHei", 9))
        self._btn_batch_import_plugins.clicked.connect(self._on_batch_import_plugins)
        toolbar.addWidget(self._btn_batch_import_plugins)
        toolbar.addStretch()
        self._btn_refresh_source_plugins = QPushButton()
        self._btn_refresh_source_plugins.setIcon(get_icon("refresh-cw", "#ccc", 14))
        self._btn_refresh_source_plugins.setToolTip(I18n.t("settings.source_plugin.refresh"))
        self._btn_refresh_source_plugins.setFixedSize(28, 28)
        self._btn_refresh_source_plugins.clicked.connect(self._on_refresh_source_plugins)
        toolbar.addWidget(self._btn_refresh_source_plugins)
        layout.addLayout(toolbar)

        self._source_plugin_table = QTableWidget()
        self._source_plugin_table.setColumnCount(6)
        self._source_plugin_table.setHorizontalHeaderLabels([I18n.t("settings.source_plugin.col_name"), I18n.t("settings.source_plugin.col_search"), I18n.t("settings.source_plugin.col_play"), I18n.t("settings.source_plugin.col_download"), I18n.t("settings.source_plugin.col_status"), I18n.t("settings.source_plugin.col_action")])
        self._source_plugin_table.verticalHeader().setVisible(False)
        header = self._source_plugin_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._source_plugin_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._source_plugin_table.setSelectionMode(QTableWidget.SingleSelection)
        self._source_plugin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._source_plugin_table.setFont(QFont("Microsoft YaHei", 9))
        self._source_plugin_table.verticalHeader().setDefaultSectionSize(26)
        layout.addWidget(self._source_plugin_table, 1)

        test_group = QGroupBox(I18n.t("settings.source_plugin.group_test"))
        test_group.setFont(QFont("Microsoft YaHei", 10))
        test_layout = QVBoxLayout(test_group)

        test_toolbar = QHBoxLayout()
        test_toolbar.addWidget(QLabel(I18n.t("settings.source_plugin.test_label")))
        self._cmb_source_test_type = QComboBox()
        self._cmb_source_test_type.addItems([I18n.t("settings.source_plugin.test_search"), I18n.t("settings.source_plugin.test_url"), I18n.t("settings.source_plugin.test_lyric")])
        self._cmb_source_test_type.setFont(QFont("Microsoft YaHei", 9))
        test_toolbar.addWidget(self._cmb_source_test_type)

        self._txt_source_test_keyword = QLineEdit()
        self._txt_source_test_keyword.setPlaceholderText(I18n.t("settings.source_plugin.test_placeholder"))
        self._txt_source_test_keyword.setFont(QFont("Microsoft YaHei", 9))
        test_toolbar.addWidget(self._txt_source_test_keyword, 1)

        self._btn_run_source_test = QPushButton()
        self._btn_run_source_test.setIcon(get_icon("zap", "#ccc", 14))
        self._btn_run_source_test.setToolTip(I18n.t("settings.source_plugin.run_test"))
        self._btn_run_source_test.setFixedSize(28, 28)
        self._btn_run_source_test.clicked.connect(self._on_run_source_test)
        test_toolbar.addWidget(self._btn_run_source_test)
        test_layout.addLayout(test_toolbar)

        from PySide6.QtWidgets import QTextEdit
        self._source_test_output = QTextEdit()
        self._source_test_output.setReadOnly(True)
        self._source_test_output.setFont(QFont("Microsoft YaHei", 9))
        self._source_test_output.setPlaceholderText(I18n.t("settings.source_plugin.test_result_placeholder"))
        self._source_test_output.setMaximumHeight(150)
        test_layout.addWidget(self._source_test_output)

        layout.addWidget(test_group)

        self._source_plugins_data = []
        self._source_plugin_instances = {}
        self._current_source_test_plugin = None
        self._source_test_worker = None

        return page

    source_plugin_install_requested = Signal(str)
    source_plugin_enable_requested = Signal(str, bool)
    source_plugin_delete_requested = Signal(str)

    def _on_install_source_plugin(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("settings.source_plugin.select_file"), "", I18n.t("settings.source_plugin.file_filter")
        )
        if file_path:
            self.source_plugin_install_requested.emit(file_path)

    def _on_batch_import_plugins(self):
        folder = QFileDialog.getExistingDirectory(self, I18n.t("settings.source_plugin.select_export_folder"))
        if not folder:
            return
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        results = pm.import_from_export_folder(folder)

        lines = []
        type_names = {
            "source": "音源插件",
            "decoder": "音频解码插件",
            "transcription": "转录插件",
            "tool": "工具",
            "dictionary": "字典数据",
            "alist": "AList服务",
            "whisper": "Whisper语音识别",
        }
        for ptype, info in results.items():
            if info["success"] == 0 and info["failed"] == 0:
                continue
            lines.append(f"【{type_names.get(ptype, ptype)}】")
            for detail in info["details"]:
                lines.append(f"  {detail}")
            if info["failed"] > 0:
                lines.append(f"  成功: {info['success']}, 失败: {info['failed']}")
            else:
                lines.append(f"  全部成功 ({info['success']}个)")

        if not lines:
            ThemedMessageBox.information(self, I18n.t("common.info"), I18n.t("settings.source_plugin.no_plugins_found"))
            return

        ThemedMessageBox.information(self, I18n.t("settings.source_plugin.batch_import_result"), "\n".join(lines))
        self._on_refresh_source_plugins()

    def _on_refresh_source_plugins(self):
        from src.core.event_bus import EventBus
        EventBus().publish("__refresh_plugins__", None)

    def set_source_plugins(self, plugins, instances=None):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()

        self._source_plugins_data = plugins
        if instances:
            self._source_plugin_instances = instances
        self._source_plugin_table.setRowCount(0)
        for plugin in plugins:
            row = self._source_plugin_table.rowCount()
            self._source_plugin_table.insertRow(row)

            plugin_id = plugin.get("id", "")
            name = plugin.get("name", "")
            source_name = plugin.get("source_name", "")
            display_name = f"{name} ({source_name})" if source_name else name

            can_search = plugin.get("can_search", True)
            can_play = plugin.get("can_play", True)
            can_download = plugin.get("can_download", True)
            status = plugin.get("status", "enabled")
            is_enabled = status == "enabled"

            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.UserRole, plugin_id)
            self._source_plugin_table.setItem(row, 0, name_item)

            self._source_plugin_table.setItem(row, 1, QTableWidgetItem("✓" if can_search else "✗"))
            self._source_plugin_table.setItem(row, 2, QTableWidgetItem("✓" if can_play else "✗"))
            self._source_plugin_table.setItem(row, 3, QTableWidgetItem("✓" if can_download else "✗"))

            status_item = QTableWidgetItem(I18n.t("settings.source_plugin.status_enabled") if is_enabled else I18n.t("settings.source_plugin.status_disabled"))
            status_item.setForeground(QColor(tc.get("success", "#32c864")) if is_enabled else QColor(tc.get("danger", "#e05050")))
            self._source_plugin_table.setItem(row, 4, status_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 0, 4, 0)
            action_layout.setSpacing(6)

            link_color = tc.get("accent", "#32c864")
            danger_color = tc.get("danger", "#e05050")
            muted_color = tc.get("text_muted", "#666680")

            link_style = (
                f"QPushButton {{ color: {link_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: {tc.get('accent_hover', '#3de878')}; }}"
            )
            danger_link_style = (
                f"QPushButton {{ color: {danger_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: #ff6666; }}"
            )
            disabled_link_style = (
                f"QPushButton {{ color: {muted_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; }}"
            )

            btn_toggle = QPushButton(I18n.t("settings.source_plugin.btn_disable") if is_enabled else I18n.t("settings.source_plugin.btn_enable"))
            btn_toggle.setStyleSheet(link_style)
            btn_toggle.setCursor(Qt.PointingHandCursor)
            btn_toggle.setFixedHeight(20)
            btn_toggle.clicked.connect(
                lambda checked, pid=plugin_id, en=is_enabled: self._on_source_plugin_toggle(pid, en)
            )
            action_layout.addWidget(btn_toggle)

            btn_test = QPushButton(I18n.t("settings.source_plugin.btn_test"))
            btn_test.setStyleSheet(link_style)
            btn_test.setCursor(Qt.PointingHandCursor)
            btn_test.setFixedHeight(20)
            btn_test.clicked.connect(
                lambda checked, pid=plugin_id: self._on_source_plugin_test(pid)
            )
            action_layout.addWidget(btn_test)

            if is_enabled:
                btn_delete = QPushButton(I18n.t("settings.source_plugin.btn_delete"))
                btn_delete.setStyleSheet(disabled_link_style)
                btn_delete.setCursor(Qt.ForbiddenCursor)
                btn_delete.setFixedHeight(20)
                btn_delete.setToolTip(I18n.t("settings.source_plugin.disable_first"))
            else:
                btn_delete = QPushButton(I18n.t("settings.source_plugin.btn_delete"))
                btn_delete.setStyleSheet(danger_link_style)
                btn_delete.setCursor(Qt.PointingHandCursor)
                btn_delete.setFixedHeight(20)
                btn_delete.clicked.connect(
                    lambda checked, pid=plugin_id: self._on_source_plugin_delete(pid)
                )
            action_layout.addWidget(btn_delete)

            self._source_plugin_table.setCellWidget(row, 5, action_widget)

    def _on_source_plugin_toggle(self, plugin_id, currently_enabled):
        new_enabled = not currently_enabled
        self.source_plugin_enable_requested.emit(plugin_id, new_enabled)

    def _on_source_plugin_test(self, plugin_id):
        if plugin_id in self._source_plugin_instances:
            self._current_source_test_plugin = self._source_plugin_instances[plugin_id]
            self._source_test_output.append(I18n.tf("settings.source_plugin.plugin_selected", plugin_id=plugin_id))

    def _on_source_plugin_delete(self, plugin_id):
        plugin_info = None
        for p in self._source_plugins_data:
            if p.get("id") == plugin_id:
                plugin_info = p
                break
        if not plugin_info:
            return
        name = plugin_info.get("name", plugin_id)
        source = plugin_info.get("source_name", "")
        display = f"{name} ({source})" if source else name
        log_msgbox("warning", I18n.t("settings.source_plugin.confirm_delete_title"), I18n.tf("settings.source_plugin.confirm_delete_msg", display=display))
        reply = ThemedMessageBox.warning(
            self, I18n.t("settings.source_plugin.confirm_delete_title"),
            I18n.tf("settings.source_plugin.confirm_delete_msg", display=display),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no",
        )
        if reply == 1:
            self.source_plugin_delete_requested.emit(plugin_id)

    def _on_run_source_test(self):
        if not self._current_source_test_plugin:
            self._source_test_output.append(I18n.t("settings.source_plugin.select_plugin_first"))
            return
        test_type = self._cmb_source_test_type.currentIndex()
        keyword = self._txt_source_test_keyword.text().strip()
        if not keyword:
            keyword = I18n.t("settings.source_plugin.default_keyword")
        test_names = [I18n.t("settings.source_plugin.test_search"), I18n.t("settings.source_plugin.test_url"), I18n.t("settings.source_plugin.test_lyric")]
        self._source_test_output.append(I18n.tf("settings.source_plugin.test_starting", test_name=test_names[test_type]))
        self._btn_run_source_test.setEnabled(False)

        from PySide6.QtCore import QThread
        if self._source_test_worker and self._source_test_worker.isRunning():
            self._source_test_worker.terminate()
            self._source_test_worker.wait()

        class _TestWorker(QThread):
            progress = Signal(str)
            finished = Signal(str)
            error = Signal(str)

            def __init__(self, plugin, t_type, kw):
                super().__init__()
                self.plugin = plugin
                self.t_type = t_type
                self.kw = kw

            def run(self):
                try:
                    if self.t_type == 0:
                        self.progress.emit(I18n.tf("settings.source_plugin.msg_searching", kw=self.kw))
                        result = self.plugin.search(self.kw, page=1, limit=3)
                        self.finished.emit(I18n.tf("settings.source_plugin.msg_search_result", result=result))
                    elif self.t_type == 1:
                        self.progress.emit(I18n.tf("settings.source_plugin.msg_getting_url", kw=self.kw))
                        result = self.plugin.get_song_url(self.kw, "320k")
                        self.finished.emit(I18n.tf("settings.source_plugin.msg_url_result", result=result))
                    elif self.t_type == 2:
                        self.progress.emit(I18n.tf("settings.source_plugin.msg_getting_lyric", kw=self.kw))
                        result = self.plugin.get_lyric(self.kw)
                        self.finished.emit(I18n.tf("settings.source_plugin.msg_lyric_result", result=result))
                except Exception as e:
                    self.error.emit(str(e))

        self._source_test_worker = _TestWorker(
            self._current_source_test_plugin, test_type, keyword
        )
        self._source_test_worker.progress.connect(lambda msg: self._source_test_output.append(msg))
        self._source_test_worker.finished.connect(self._on_source_test_finished)
        self._source_test_worker.error.connect(self._on_source_test_error)
        self._source_test_worker.start()

    def _on_source_test_finished(self, result):
        self._source_test_output.append(result)
        self._btn_run_source_test.setEnabled(True)

    def _on_source_test_error(self, error):
        self._source_test_output.append(I18n.tf("settings.source_plugin.test_error", error=error))
        self._btn_run_source_test.setEnabled(True)

    # ── Audio Plugins Page ──────────────────────────────────────

    def _build_audio_plugins_page(self):
        from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        installed_group = QGroupBox(I18n.t("settings.audio_plugin.group_installed"))
        installed_group.setFont(QFont("Microsoft YaHei", 10))
        il = QVBoxLayout(installed_group)

        self._installed_table = QTableWidget()
        self._installed_table.setColumnCount(4)
        self._installed_table.setHorizontalHeaderLabels([I18n.t("settings.audio_plugin.col_name"), I18n.t("settings.audio_plugin.col_formats"), I18n.t("settings.audio_plugin.col_status"), I18n.t("settings.audio_plugin.col_action")])
        self._installed_table.verticalHeader().setVisible(False)
        self._installed_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._installed_table.setSelectionMode(QTableWidget.SingleSelection)
        self._installed_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._installed_table.setFont(QFont("Microsoft YaHei", 9))
        self._installed_table.verticalHeader().setDefaultSectionSize(26)
        ih = self._installed_table.horizontalHeader()
        ih.setSectionResizeMode(0, QHeaderView.Stretch)
        ih.setSectionResizeMode(1, QHeaderView.Stretch)
        ih.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        ih.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        il.addWidget(self._installed_table)
        layout.addWidget(installed_group)

        available_group = QGroupBox(I18n.t("settings.audio_plugin.group_available"))
        available_group.setFont(QFont("Microsoft YaHei", 10))
        al = QVBoxLayout(available_group)

        self._available_table = QTableWidget()
        self._available_table.setColumnCount(4)
        self._available_table.setHorizontalHeaderLabels([I18n.t("settings.audio_plugin.col_name"), I18n.t("settings.audio_plugin.col_formats"), I18n.t("settings.audio_plugin.col_desc"), I18n.t("settings.audio_plugin.col_action")])
        self._available_table.verticalHeader().setVisible(False)
        self._available_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._available_table.setSelectionMode(QTableWidget.SingleSelection)
        self._available_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._available_table.setFont(QFont("Microsoft YaHei", 9))
        self._available_table.verticalHeader().setDefaultSectionSize(26)
        ah = self._available_table.horizontalHeader()
        ah.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        ah.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        ah.setSectionResizeMode(2, QHeaderView.Stretch)
        ah.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        al.addWidget(self._available_table)
        layout.addWidget(available_group)

        import_row = QHBoxLayout()
        self._btn_import_decoder = QPushButton(I18n.t("settings.audio_plugin.import_decoder"))
        self._btn_import_decoder.setFont(QFont("Microsoft YaHei", 9))
        self._btn_import_decoder.clicked.connect(self._on_import_decoder)
        import_row.addWidget(self._btn_import_decoder)
        import_row.addStretch()

        self._chk_auto_prompt = QCheckBox(I18n.t("settings.audio_plugin.auto_prompt"))
        self._chk_auto_prompt.setFont(QFont("Microsoft YaHei", 9))
        self._chk_auto_prompt.setChecked(True)
        import_row.addWidget(self._chk_auto_prompt)
        layout.addLayout(import_row)

        self._refresh_decoder_tables()
        return page

    def _refresh_decoder_tables(self):
        from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        dpm = DecoderPluginManager()

        self._installed_table.setRowCount(0)
        core_item = QTableWidgetItem("BASS Core")
        core_item.setData(Qt.UserRole, "bass_core")
        self._installed_table.insertRow(0)
        self._installed_table.setItem(0, 0, core_item)
        self._installed_table.setItem(0, 1, QTableWidgetItem("MP3, WAV, OGG"))
        status_item = QTableWidgetItem("✓")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor(tc.get("success", "#32c864")))
        self._installed_table.setItem(0, 2, status_item)
        self._installed_table.setItem(0, 3, QTableWidgetItem(I18n.t("settings.audio_plugin.builtin")))

        all_plugins = dpm.get_all_plugin_info()
        for info in all_plugins:
            if not info.get("installed") and not info.get("is_builtin"):
                continue
            if info.get("id") == "bass_core":
                continue
            row = self._installed_table.rowCount()
            self._installed_table.insertRow(row)
            name_item = QTableWidgetItem(info.get("name", info.get("id", "")))
            name_item.setData(Qt.UserRole, info.get("id", ""))
            self._installed_table.setItem(row, 0, name_item)
            self._installed_table.setItem(row, 1, QTableWidgetItem(", ".join(info.get("formats", []))))
            status_text = "✓" if info.get("loaded") else "⚠"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            if info.get("loaded"):
                status_item.setForeground(QColor(tc.get("success", "#32c864")))
                status_item.setToolTip(I18n.t("settings.audio_plugin.loaded"))
            else:
                status_item.setForeground(QColor(tc.get("warning", "#e0a030")))
                status_item.setToolTip(I18n.t("settings.audio_plugin.not_loaded"))
            self._installed_table.setItem(row, 2, status_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 0, 4, 0)
            action_layout.setSpacing(4)
            if not info.get("is_builtin", False):
                link_color = tc.get("danger", "#e05050")
                link_style = (
                    f"QPushButton {{ color: {link_color}; background: transparent; border: none; "
                    f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                    f"QPushButton:hover {{ color: #ff6666; }}"
                )
                btn_remove = QPushButton(I18n.t("settings.audio_plugin.uninstall"))
                btn_remove.setStyleSheet(link_style)
                btn_remove.setCursor(Qt.PointingHandCursor)
                btn_remove.setFixedHeight(20)
                pid = info.get("id", "")
                btn_remove.clicked.connect(lambda checked, p=pid: self._on_remove_decoder(p))
                action_layout.addWidget(btn_remove)
            else:
                action_layout.addWidget(QLabel(I18n.t("settings.audio_plugin.builtin")))
            self._installed_table.setCellWidget(row, 3, action_widget)

        self._available_table.setRowCount(0)
        for info in all_plugins:
            if info.get("installed") or info.get("is_builtin"):
                continue
            row = self._available_table.rowCount()
            self._available_table.insertRow(row)
            name_item = QTableWidgetItem(info.get("name", info.get("id", "")))
            name_item.setData(Qt.UserRole, info.get("id", ""))
            self._available_table.setItem(row, 0, name_item)
            self._available_table.setItem(row, 1, QTableWidgetItem(", ".join(info.get("formats", []))))
            self._available_table.setItem(row, 2, QTableWidgetItem(info.get("description", "")))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 0, 4, 0)
            link_color = tc.get("accent", "#32c864")
            link_style = (
                f"QPushButton {{ color: {link_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: {tc.get('accent_hover', '#3de878')}; }}"
            )
            btn_download = QPushButton(I18n.t("settings.audio_plugin.download"))
            btn_download.setStyleSheet(link_style)
            btn_download.setCursor(Qt.PointingHandCursor)
            btn_download.setFixedHeight(20)
            pid = info.get("id", "")
            btn_download.clicked.connect(lambda checked, p=pid: self._on_download_decoder(p))
            action_layout.addWidget(btn_download)
            self._available_table.setCellWidget(row, 3, action_widget)

    def _on_import_decoder(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("settings.audio_plugin.select_decoder_file"), "", I18n.t("settings.audio_plugin.decoder_file_filter")
        )
        if file_path:
            from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
            dpm = DecoderPluginManager()
            if dpm.import_plugin(file_path):
                self._refresh_decoder_tables()

    def _on_remove_decoder(self, plugin_id: str):
        log_msgbox("warning", I18n.t("settings.audio_plugin.confirm_uninstall_title"), I18n.t("settings.audio_plugin.confirm_uninstall_msg"))
        reply = ThemedMessageBox.warning(
            self, I18n.t("settings.audio_plugin.confirm_uninstall_title"),
            I18n.t("settings.audio_plugin.confirm_uninstall_msg"),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no",
        )
        if reply == 1:
            from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
            dpm = DecoderPluginManager()
            dpm.remove_plugin(plugin_id)
            self._refresh_decoder_tables()

    def _on_download_decoder(self, plugin_id: str):
        from src.infrastructure.decoder_plugin_manager import DecoderPluginManager
        dpm = DecoderPluginManager()
        info = None
        from src.utils.constants import BASS_PLUGIN_REGISTRY
        info = BASS_PLUGIN_REGISTRY.get(plugin_id)
        if not info:
            return
        log_msgbox("info", I18n.t("settings.audio_plugin.download_decoder_title"), I18n.tf("settings.audio_plugin.download_decoder_msg", name=info.get('name', plugin_id), formats=', '.join(info.get('formats', []))))
        reply = ThemedMessageBox.information(
            self, I18n.t("settings.audio_plugin.download_decoder_title"),
            I18n.tf("settings.audio_plugin.download_decoder_msg", name=info.get('name', plugin_id), formats=', '.join(info.get('formats', []))),
            buttons=[("ok", I18n.t("common.ok")), ("cancel", I18n.t("common.cancel"))], default_button="ok",
        )
        if reply == 1:
            if dpm.download_plugin(plugin_id):
                log_msgbox("info", I18n.t("settings.audio_plugin.download_complete_title"), I18n.tf("settings.audio_plugin.download_complete_msg", name=info.get('name', plugin_id)))
                ThemedMessageBox.information(self, I18n.t("settings.audio_plugin.download_complete_title"), I18n.tf("settings.audio_plugin.download_complete_msg", name=info.get('name', plugin_id)))
                self._refresh_decoder_tables()
            else:
                log_msgbox("warning", I18n.t("settings.audio_plugin.download_fail_title"), I18n.tf("settings.audio_plugin.download_fail_msg", name=info.get('name', plugin_id)))
                ThemedMessageBox.warning(self, I18n.t("settings.audio_plugin.download_fail_title"), I18n.tf("settings.audio_plugin.download_fail_msg", name=info.get('name', plugin_id)))

    # ── Logs Page ──────────────────────────────────────────────

    def _build_logs_page(self):
        from src.utils.logger import LOG_CATEGORIES, get_log_files, search_logs, delete_log_file, cleanup_old_logs, get_total_log_size, format_size

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        search_group = QGroupBox(I18n.t("settings.logs.group_search"))
        search_layout = QVBoxLayout(search_group)
        search_layout.setSpacing(8)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_row.addWidget(QLabel(I18n.t("settings.logs.keyword")))
        self._log_keyword = QLineEdit()
        self._log_keyword.setPlaceholderText(I18n.t("settings.logs.keyword_placeholder"))
        self._log_keyword.setFixedHeight(28)
        filter_row.addWidget(self._log_keyword, 1)

        filter_row.addWidget(QLabel(I18n.t("settings.logs.category")))
        self._log_category = QComboBox()
        self._log_category.setFixedWidth(120)
        self._log_category.setFixedHeight(28)
        for cat_id, cat_name in LOG_CATEGORIES:
            self._log_category.addItem(cat_name, cat_id)
        filter_row.addWidget(self._log_category)

        filter_row.addWidget(QLabel(I18n.t("settings.logs.level")))
        self._log_level = QComboBox()
        self._log_level.setFixedWidth(90)
        self._log_level.setFixedHeight(28)
        self._log_level.addItems([I18n.t("settings.logs.level_all"), "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        filter_row.addWidget(self._log_level)

        self._btn_log_search = QPushButton(I18n.t("settings.logs.search"))
        self._btn_log_search.setFixedHeight(28)
        self._btn_log_search.setFixedWidth(60)
        self._btn_log_search.clicked.connect(self._on_log_search)
        filter_row.addWidget(self._btn_log_search)

        search_layout.addLayout(filter_row)

        self._log_results = QTextEdit()
        self._log_results.setReadOnly(True)
        self._log_results.setFont(QFont("Consolas", 9))
        self._log_results.setMinimumHeight(200)
        self._log_results.setPlaceholderText(I18n.t("settings.logs.results_placeholder"))
        search_layout.addWidget(self._log_results, 1)

        result_row = QHBoxLayout()
        self._lbl_log_count = QLabel("")
        self._lbl_log_count.setStyleSheet("color: #888; font-size: 11px;")
        result_row.addWidget(self._lbl_log_count)
        result_row.addStretch()
        search_layout.addLayout(result_row)

        layout.addWidget(search_group, 1)

        files_group = QGroupBox(I18n.t("settings.logs.group_files"))
        files_layout = QVBoxLayout(files_group)
        files_layout.setSpacing(8)

        self._log_table = QTableWidget()
        self._log_table.setColumnCount(5)
        self._log_table.setHorizontalHeaderLabels([I18n.t("settings.logs.col_date"), I18n.t("settings.logs.col_filename"), I18n.t("settings.logs.col_size"), I18n.t("settings.logs.col_view"), I18n.t("settings.logs.col_delete")])
        self._log_table.verticalHeader().setVisible(False)
        self._log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._log_table.setSelectionMode(QTableWidget.SingleSelection)
        self._log_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._log_table.setFont(QFont("Microsoft YaHei", 9))
        self._log_table.verticalHeader().setDefaultSectionSize(28)
        self._log_table.setMaximumHeight(180)
        lh = self._log_table.horizontalHeader()
        lh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lh.setSectionResizeMode(1, QHeaderView.Stretch)
        lh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        lh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._log_table.doubleClicked.connect(self._on_log_table_double_clicked)
        files_layout.addWidget(self._log_table)

        self._lbl_log_total = QLabel("")
        self._lbl_log_total.setStyleSheet("color: #888; font-size: 11px;")
        files_layout.addWidget(self._lbl_log_total)

        layout.addWidget(files_group)

        cleanup_group = QGroupBox(I18n.t("settings.logs.group_cleanup"))
        cleanup_layout = QHBoxLayout(cleanup_group)
        cleanup_layout.setSpacing(8)

        cleanup_layout.addWidget(QLabel(I18n.t("settings.logs.auto_delete")))
        self._spn_log_retain_months = QSpinBox()
        self._spn_log_retain_months.setRange(1, 24)
        self._spn_log_retain_months.setValue(3)
        self._spn_log_retain_months.setSuffix(I18n.t("settings.logs.suffix_months"))
        self._spn_log_retain_months.valueChanged.connect(
            lambda v: self.settings_changed.emit("logs/retain_months", v)
        )
        cleanup_layout.addWidget(self._spn_log_retain_months)

        self._btn_log_cleanup = QPushButton(I18n.t("settings.logs.cleanup_now"))
        self._btn_log_cleanup.setFixedHeight(28)
        self._btn_log_cleanup.clicked.connect(self._on_log_cleanup)
        cleanup_layout.addWidget(self._btn_log_cleanup)

        self._btn_log_delete_all = QPushButton(I18n.t("settings.logs.delete_all"))
        self._btn_log_delete_all.setFixedHeight(28)
        self._btn_log_delete_all.clicked.connect(self._on_log_delete_all)
        cleanup_layout.addWidget(self._btn_log_delete_all)

        cleanup_layout.addStretch()
        layout.addWidget(cleanup_group)

        self._refresh_log_table()
        return page

    def _refresh_log_table(self):
        from src.utils.logger import get_log_files, get_total_log_size, format_size
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()

        files = get_log_files()
        self._log_table.setRowCount(len(files))

        for row, f in enumerate(files):
            date_item = QTableWidgetItem(f["date"])
            date_item.setData(Qt.UserRole, f["path"])
            self._log_table.setItem(row, 0, date_item)
            self._log_table.setItem(row, 1, QTableWidgetItem(f["name"]))
            self._log_table.setItem(row, 2, QTableWidgetItem(format_size(f["size"])))

            link_color = tc.get("accent", "#4a9eff")
            danger_color = tc.get("danger", "#e05050")
            link_style_view = (
                f"QPushButton {{ color: {link_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: #6ab8ff; }}"
            )
            link_style_del = (
                f"QPushButton {{ color: {danger_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: #ff6666; }}"
            )

            view_widget = QWidget()
            view_layout = QHBoxLayout(view_widget)
            view_layout.setContentsMargins(4, 0, 4, 0)
            btn_view = QPushButton(I18n.t("settings.logs.btn_view"))
            btn_view.setStyleSheet(link_style_view)
            btn_view.setCursor(Qt.PointingHandCursor)
            btn_view.setFixedHeight(20)
            btn_view.clicked.connect(lambda checked, p=f["path"]: self._on_view_log_file(p))
            view_layout.addWidget(btn_view)
            self._log_table.setCellWidget(row, 3, view_widget)

            del_widget = QWidget()
            del_layout = QHBoxLayout(del_widget)
            del_layout.setContentsMargins(4, 0, 4, 0)
            btn_del = QPushButton(I18n.t("settings.logs.btn_delete"))
            btn_del.setStyleSheet(link_style_del)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedHeight(20)
            btn_del.clicked.connect(lambda checked, p=f["path"]: self._on_delete_single_log(p))
            del_layout.addWidget(btn_del)
            self._log_table.setCellWidget(row, 4, del_widget)

        total_size = get_total_log_size()
        self._lbl_log_total.setText(I18n.tf("settings.logs.total_files", count=len(files), size=format_size(total_size)))

    def _on_log_search(self):
        from src.utils.logger import search_logs

        keyword = self._log_keyword.text().strip()
        category = self._log_category.currentData() or "all"
        level_text = self._log_level.currentText()
        level_filter = "all" if level_text == I18n.t("settings.logs.level_all") else level_text

        results = search_logs(
            keyword=keyword,
            category=category,
            level_filter=level_filter,
            max_lines=500,
        )

        self._log_results.clear()
        cursor = self._log_results.textCursor()

        level_colors = {
            "DEBUG": "#888888",
            "INFO": "#cccccc",
            "WARNING": "#f0ad4e",
            "ERROR": "#e05050",
            "CRITICAL": "#ff0000",
        }

        if not results:
            cursor.insertText(I18n.t("settings.logs.no_results"))
            self._lbl_log_count.setText("")
            return

        for i, r in enumerate(results):
            line_text = r.get("line", "")
            level = r.get("level", "")
            color = level_colors.get(level, "#cccccc")

            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            if level in ("ERROR", "CRITICAL"):
                fmt.setFontWeight(QFont.Bold)

            cursor.insertText(line_text, fmt)
            if i < len(results) - 1:
                cursor.insertText("\n")

        self._lbl_log_count.setText(I18n.tf("settings.logs.result_count", count=len(results)))

    def _on_view_log_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            log_msgbox("warning", I18n.t("settings.logs.view_log_title"), I18n.tf("settings.logs.cannot_read_log", error=e))
            ThemedMessageBox.warning(self, I18n.t("settings.logs.view_log_title"), I18n.tf("settings.logs.cannot_read_log", error=e))
            return

        dlg = ThemedDialog(self, title=I18n.tf("settings.logs.log_viewer_title", filename=os.path.basename(path)), width=800)
        dlg.resize(816, 600)

        dlg_layout = dlg.body_layout()

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(I18n.t("settings.logs.filter_label")))
        dlg_filter = QLineEdit()
        dlg_filter.setPlaceholderText(I18n.t("settings.logs.filter_placeholder"))
        dlg_filter.setFixedHeight(28)
        search_row.addWidget(dlg_filter, 1)
        dlg_level = QComboBox()
        dlg_level.setFixedWidth(90)
        dlg_level.setFixedHeight(28)
        dlg_level.addItems([I18n.t("settings.logs.level_all"), "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        search_row.addWidget(dlg_level)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Consolas", 9))
        dlg_layout.addLayout(search_row)
        dlg_layout.addWidget(text_edit)

        level_colors = {
            "DEBUG": "#888888",
            "INFO": "#cccccc",
            "WARNING": "#f0ad4e",
            "ERROR": "#e05050",
            "CRITICAL": "#ff0000",
        }

        def render_content():
            text_edit.clear()
            cursor = text_edit.textCursor()
            filter_text = dlg_filter.text().strip().lower()
            level_text = dlg_level.currentText()
            level_filter = "all" if level_text == I18n.t("settings.logs.level_all") else level_text

            for line in content.split("\n"):
                if filter_text and filter_text not in line.lower():
                    continue
                if level_filter != "all" and level_filter not in line:
                    continue

                line_level = ""
                for lv in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
                    if lv in line:
                        line_level = lv
                        break

                fmt = QTextCharFormat()
                color = level_colors.get(line_level, "#cccccc")
                fmt.setForeground(QColor(color))
                if line_level in ("ERROR", "CRITICAL"):
                    fmt.setFontWeight(QFont.Bold)
                cursor.insertText(line, fmt)
                cursor.insertText("\n")

        dlg_filter.textChanged.connect(render_content)
        dlg_level.currentTextChanged.connect(lambda: render_content())
        render_content()
        dlg.exec()

    def _on_log_table_double_clicked(self, index):
        item = self._log_table.item(index.row(), 0)
        if item:
            path = item.data(Qt.UserRole)
            if path:
                self._on_view_log_file(path)

    def _on_delete_single_log(self, path: str):
        from src.utils.logger import delete_log_file
        if delete_log_file(path):
            self._refresh_log_table()

    def _on_log_cleanup(self):
        from src.utils.logger import cleanup_old_logs
        months = self._spn_log_retain_months.value()
        deleted = cleanup_old_logs(months)
        self._refresh_log_table()
        if deleted > 0:
            self._lbl_log_total.setText(I18n.tf("settings.logs.cleaned_count", count=deleted))
        else:
            self._lbl_log_total.setText(I18n.t("settings.logs.no_expired"))

    def _on_log_delete_all(self):
        from src.utils.logger import get_log_files, delete_log_file
        log_msgbox("warning", I18n.t("settings.logs.delete_all_title"), I18n.t("settings.logs.delete_all_msg"))
        reply = ThemedMessageBox.warning(
            self, I18n.t("settings.logs.delete_all_title"),
            I18n.t("settings.logs.delete_all_msg"),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no",
        )
        if reply == 1:
            files = get_log_files()
            deleted = 0
            for f in files:
                if delete_log_file(f["path"]):
                    deleted += 1
            self._refresh_log_table()
            self._lbl_log_total.setText(I18n.tf("settings.logs.deleted_count", count=deleted))

    # ── Study Page ─────────────────────────────────────────────

    def _build_study_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        mode_group = QGroupBox(I18n.t("settings.study.group_mode"))
        mode_layout = QHBoxLayout(mode_group)
        mode_layout.setSpacing(16)

        self._chk_study_enabled = QCheckBox(I18n.t("settings.study.enable_mode"))
        self._chk_study_enabled.setChecked(True)
        self._chk_study_enabled.toggled.connect(
            lambda v: self.settings_changed.emit("study/enabled", v)
        )
        mode_layout.addWidget(self._chk_study_enabled)

        mode_hint = QLabel(I18n.t("settings.study.mode_hint"))
        mode_hint.setStyleSheet("color: #888; font-size: 11px;")
        mode_layout.addWidget(mode_hint)
        mode_layout.addStretch()

        layout.addWidget(mode_group)

        repeat_group = QGroupBox(I18n.t("settings.study.group_repeat"))
        repeat_layout = QHBoxLayout(repeat_group)
        repeat_layout.setSpacing(8)

        repeat_layout.addWidget(QLabel(I18n.t("settings.study.repeat_count")))
        self._study_repeat_count = QSpinBox()
        self._study_repeat_count.setRange(1, 20)
        self._study_repeat_count.setValue(3)
        repeat_layout.addWidget(self._study_repeat_count)
        repeat_layout.addSpacing(16)
        repeat_layout.addWidget(QLabel(I18n.t("settings.study.pause_gap")))
        self._study_repeat_pause = QSpinBox()
        self._study_repeat_pause.setRange(1, 30)
        self._study_repeat_pause.setValue(3)
        self._study_repeat_pause.setSuffix(I18n.t("settings.study.suffix_sec"))
        repeat_layout.addWidget(self._study_repeat_pause)
        repeat_layout.addSpacing(16)
        self._study_auto_next = QCheckBox(I18n.t("settings.study.auto_next"))
        self._study_auto_next.setChecked(True)
        repeat_layout.addWidget(self._study_auto_next)
        repeat_layout.addStretch()

        layout.addWidget(repeat_group)

        shadowing_group = QGroupBox(I18n.t("settings.study.group_shadowing"))
        shadowing_layout = QHBoxLayout(shadowing_group)
        shadowing_layout.setSpacing(8)

        self._chk_shadowing = QCheckBox(I18n.t("settings.study.enable_shadowing"))
        self._chk_shadowing.setChecked(False)
        shadowing_layout.addWidget(self._chk_shadowing)
        shadowing_layout.addSpacing(12)
        shadowing_layout.addWidget(QLabel(I18n.t("settings.study.extra_pause")))
        self._spn_shadowing_extra = QSpinBox()
        self._spn_shadowing_extra.setRange(0, 30)
        self._spn_shadowing_extra.setValue(3)
        self._spn_shadowing_extra.setSuffix(I18n.t("settings.study.suffix_sec"))
        shadowing_layout.addWidget(self._spn_shadowing_extra)
        shadowing_hint = QLabel(I18n.t("settings.study.shadowing_hint"))
        shadowing_hint.setStyleSheet("color: #888; font-size: 11px;")
        shadowing_layout.addWidget(shadowing_hint)
        shadowing_layout.addStretch()

        layout.addWidget(shadowing_group)

        autoseg_group = QGroupBox(I18n.t("settings.study.group_autoseg"))
        autoseg_layout = QHBoxLayout(autoseg_group)
        autoseg_layout.setSpacing(8)

        autoseg_layout.addWidget(QLabel(I18n.t("settings.study.energy_threshold")))
        self._spn_autoseg_threshold = QSpinBox()
        self._spn_autoseg_threshold.setRange(0, 20000)
        self._spn_autoseg_threshold.setValue(0)
        self._spn_autoseg_threshold.setSpecialValueText(I18n.t("settings.study.auto"))
        self._spn_autoseg_threshold.setSingleStep(500)
        self._spn_autoseg_threshold.setToolTip(I18n.t("settings.study.threshold_tooltip"))
        autoseg_layout.addWidget(self._spn_autoseg_threshold)
        autoseg_layout.addSpacing(8)
        autoseg_layout.addWidget(QLabel(I18n.t("settings.study.min_silence")))
        self._spn_autoseg_min_silence = QSpinBox()
        self._spn_autoseg_min_silence.setRange(100, 3000)
        self._spn_autoseg_min_silence.setValue(300)
        self._spn_autoseg_min_silence.setSuffix(I18n.t("settings.study.suffix_ms"))
        self._spn_autoseg_min_silence.setSingleStep(50)
        autoseg_layout.addWidget(self._spn_autoseg_min_silence)
        autoseg_layout.addSpacing(8)
        autoseg_layout.addWidget(QLabel(I18n.t("settings.study.min_segment")))
        self._spn_autoseg_min_segment = QSpinBox()
        self._spn_autoseg_min_segment.setRange(300, 5000)
        self._spn_autoseg_min_segment.setValue(800)
        self._spn_autoseg_min_segment.setSuffix(I18n.t("settings.study.suffix_ms"))
        self._spn_autoseg_min_segment.setSingleStep(100)
        autoseg_layout.addWidget(self._spn_autoseg_min_segment)
        autoseg_layout.addStretch()

        layout.addWidget(autoseg_group)

        subtitle_group = QGroupBox(I18n.t("settings.study.group_subtitle"))
        subtitle_layout = QHBoxLayout(subtitle_group)
        subtitle_layout.setSpacing(8)

        subtitle_layout.addWidget(QLabel(I18n.t("settings.study.default_lang")))
        self._study_default_lang = QComboBox()
        self._study_default_lang.addItems(["en", "zh-Hans", "ja", "ko", "fr", "de", "es"])
        self._study_default_lang.setCurrentText("en")
        subtitle_layout.addWidget(self._study_default_lang)
        subtitle_layout.addSpacing(16)
        subtitle_layout.addWidget(QLabel(I18n.t("settings.study.secondary_lang")))
        self._study_default_lang_secondary = QComboBox()
        self._study_default_lang_secondary.addItem(I18n.t("settings.study.none"))
        self._study_default_lang_secondary.addItems(["en", "zh-Hans", "ja", "ko", "fr", "de", "es"])
        subtitle_layout.addWidget(self._study_default_lang_secondary)
        subtitle_layout.addSpacing(16)
        subtitle_layout.addWidget(QLabel(I18n.t("settings.study.split_gap")))
        self._study_auto_split_gap = QSpinBox()
        self._study_auto_split_gap.setRange(500, 10000)
        self._study_auto_split_gap.setValue(2000)
        self._study_auto_split_gap.setSuffix(I18n.t("settings.study.suffix_ms"))
        self._study_auto_split_gap.setSingleStep(500)
        subtitle_layout.addWidget(self._study_auto_split_gap)
        subtitle_layout.addStretch()

        layout.addWidget(subtitle_group)

        ffmpeg_group = QGroupBox(I18n.t("settings.study.group_ffmpeg"))
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        ffmpeg_layout.setSpacing(8)

        self._ffmpeg_status_label = QLabel()
        self._ffmpeg_status_label.setWordWrap(True)
        self._refresh_ffmpeg_status()
        ffmpeg_layout.addWidget(self._ffmpeg_status_label)

        ffmpeg_btn_row = QHBoxLayout()
        ffmpeg_btn_row.setSpacing(8)

        self._btn_ffmpeg_browse = QPushButton(I18n.t("settings.study.select_ffmpeg"))
        self._btn_ffmpeg_browse.setFixedHeight(28)
        self._btn_ffmpeg_browse.clicked.connect(self._on_ffmpeg_browse)
        ffmpeg_btn_row.addWidget(self._btn_ffmpeg_browse)

        self._btn_ffprobe_browse = QPushButton(I18n.t("settings.study.select_ffprobe"))
        self._btn_ffprobe_browse.setFixedHeight(28)
        self._btn_ffprobe_browse.clicked.connect(self._on_ffprobe_browse)
        ffmpeg_btn_row.addWidget(self._btn_ffprobe_browse)

        self._btn_ffmpeg_download = QPushButton(I18n.t("settings.study.auto_download"))
        self._btn_ffmpeg_download.setFixedHeight(28)
        self._btn_ffmpeg_download.clicked.connect(self._on_ffmpeg_download)
        ffmpeg_btn_row.addWidget(self._btn_ffmpeg_download)

        self._btn_ffmpeg_clear = QPushButton(I18n.t("settings.study.clear"))
        self._btn_ffmpeg_clear.setFixedHeight(28)
        self._btn_ffmpeg_clear.setFixedWidth(60)
        self._btn_ffmpeg_clear.clicked.connect(self._on_ffmpeg_clear)
        ffmpeg_btn_row.addWidget(self._btn_ffmpeg_clear)

        ffmpeg_btn_row.addStretch()
        ffmpeg_layout.addLayout(ffmpeg_btn_row)

        layout.addWidget(ffmpeg_group)

        whisper_group = QGroupBox(I18n.t("settings.study.group_whisper"))
        whisper_layout = QVBoxLayout(whisper_group)
        whisper_layout.setSpacing(8)

        self._whisper_status_label = QLabel()
        self._whisper_status_label.setWordWrap(True)
        whisper_layout.addWidget(self._whisper_status_label)

        whisper_row1 = QHBoxLayout()
        whisper_row1.setSpacing(8)
        whisper_row1.addWidget(QLabel(I18n.t("settings.study.label_model")))
        self._whisper_model_combo = QComboBox()
        for m in WHISPER_MODELS:
            self._whisper_model_combo.addItem(f"{m['name']} ({m['params']}, {m['vram']}) - {m['desc']}", m['name'])
        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            saved_model = cm.get("Whisper", "Model", "base")
            for i in range(self._whisper_model_combo.count()):
                if self._whisper_model_combo.itemData(i) == saved_model:
                    self._whisper_model_combo.setCurrentIndex(i)
                    break
        except Exception:
            pass
        whisper_row1.addWidget(self._whisper_model_combo, 1)
        self._btn_whisper_download_model = QPushButton(I18n.t("settings.study.btn_download_model"))
        self._btn_whisper_download_model.setFixedHeight(28)
        self._btn_whisper_download_model.clicked.connect(self._on_whisper_download_model)
        whisper_row1.addWidget(self._btn_whisper_download_model)
        whisper_layout.addLayout(whisper_row1)

        whisper_row2 = QHBoxLayout()
        whisper_row2.setSpacing(8)
        whisper_row2.addWidget(QLabel(I18n.t("settings.study.label_device")))
        self._whisper_device_combo = QComboBox()
        self._whisper_device_combo.addItem(I18n.t("settings.study.device_auto"), "auto")
        self._whisper_device_combo.addItem("CPU", "cpu")
        self._whisper_device_combo.addItem("CUDA (GPU)", "cuda")
        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            saved_device = cm.get("Whisper", "Device", "auto")
            for i in range(self._whisper_device_combo.count()):
                if self._whisper_device_combo.itemData(i) == saved_device:
                    self._whisper_device_combo.setCurrentIndex(i)
                    break
        except Exception:
            pass
        whisper_row2.addWidget(self._whisper_device_combo)
        whisper_row2.addSpacing(16)
        whisper_row2.addWidget(QLabel(I18n.t("settings.study.label_whisper_lang")))
        self._whisper_lang_combo = QComboBox()
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_auto"), "")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_zh"), "zh")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_en"), "en")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_ja"), "ja")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_ko"), "ko")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_fr"), "fr")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_de"), "de")
        self._whisper_lang_combo.addItem(I18n.t("settings.study.whisper_lang_es"), "es")
        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            saved_lang = cm.get("Whisper", "Language", "")
            for i in range(self._whisper_lang_combo.count()):
                if self._whisper_lang_combo.itemData(i) == saved_lang:
                    self._whisper_lang_combo.setCurrentIndex(i)
                    break
        except Exception:
            pass
        whisper_row2.addWidget(self._whisper_lang_combo)
        whisper_row2.addStretch()
        whisper_layout.addLayout(whisper_row2)

        whisper_mirror_row = QHBoxLayout()
        whisper_mirror_row.setSpacing(8)
        whisper_mirror_row.addWidget(QLabel(I18n.t("settings.study.label_pip_mirror")))
        self._whisper_mirror_combo = QComboBox()
        for m in PIP_MIRRORS:
            self._whisper_mirror_combo.addItem(m["name"], m["url"])
        whisper_mirror_row.addWidget(self._whisper_mirror_combo, 1)
        whisper_layout.addLayout(whisper_mirror_row)

        whisper_hf_row = QHBoxLayout()
        whisper_hf_row.setSpacing(8)
        whisper_hf_row.addWidget(QLabel(I18n.t("settings.study.label_hf_mirror")))
        self._whisper_hf_combo = QComboBox()
        for m in HF_MIRRORS:
            self._whisper_hf_combo.addItem(m["name"], m["url"])
        self._whisper_hf_combo.currentIndexChanged.connect(self._on_whisper_hf_changed)
        whisper_hf_row.addWidget(self._whisper_hf_combo, 1)
        whisper_layout.addLayout(whisper_hf_row)

        self._whisper_log = QTextEdit()
        self._whisper_log.setReadOnly(True)
        self._whisper_log.setMaximumHeight(80)
        self._whisper_log.setPlaceholderText(I18n.t("settings.study.ph_whisper_log"))
        self._whisper_log.setVisible(False)
        whisper_layout.addWidget(self._whisper_log)

        whisper_btn_row = QHBoxLayout()
        whisper_btn_row.setSpacing(8)
        self._btn_whisper_install = QPushButton(I18n.t("settings.study.btn_whisper_install"))
        self._btn_whisper_install.setFixedHeight(28)
        self._btn_whisper_install.clicked.connect(self._on_whisper_install)
        whisper_btn_row.addWidget(self._btn_whisper_install)
        self._btn_whisper_uninstall = QPushButton(I18n.t("settings.study.btn_whisper_uninstall"))
        self._btn_whisper_uninstall.setFixedHeight(28)
        self._btn_whisper_uninstall.clicked.connect(self._on_whisper_uninstall)
        whisper_btn_row.addWidget(self._btn_whisper_uninstall)
        whisper_btn_row.addStretch()
        whisper_layout.addLayout(whisper_btn_row)

        self._refresh_whisper_status()

        layout.addWidget(whisper_group)

        dict_group = QGroupBox(I18n.t("settings.study.group_dict"))
        dict_layout = QVBoxLayout(dict_group)
        dict_layout.setSpacing(8)

        self._chk_dict_enabled = QCheckBox(I18n.t("settings.study.dict_enabled"))
        self._chk_dict_enabled.setChecked(True)
        self._chk_dict_enabled.toggled.connect(
            lambda v: self.settings_changed.emit("dictionary/word_lookup_enabled", v)
        )
        dict_layout.addWidget(self._chk_dict_enabled)

        self._dict_status_label = QLabel()
        self._dict_status_label.setWordWrap(True)
        dict_layout.addWidget(self._dict_status_label)

        dict_offline_row = QHBoxLayout()
        dict_offline_row.setSpacing(8)
        dict_offline_row.addWidget(QLabel(I18n.t("settings.study.label_offline_dict")))
        self._btn_dict_download = QPushButton(I18n.t("settings.study.btn_dict_download"))
        self._btn_dict_download.setFixedHeight(26)
        self._btn_dict_download.clicked.connect(self._on_dict_download)
        dict_offline_row.addWidget(self._btn_dict_download)
        dict_offline_row.addStretch()
        dict_layout.addLayout(dict_offline_row)

        self._chk_dict_online = QCheckBox(I18n.t("settings.study.dict_online"))
        self._chk_dict_online.setChecked(True)
        self._chk_dict_online.toggled.connect(
            lambda v: self.settings_changed.emit("dictionary/online_enabled", v)
        )
        dict_layout.addWidget(self._chk_dict_online)

        self._dict_log = QTextEdit()
        self._dict_log.setReadOnly(True)
        self._dict_log.setMaximumHeight(60)
        self._dict_log.setPlaceholderText(I18n.t("settings.study.ph_dict_log"))
        self._dict_log.setVisible(False)
        dict_layout.addWidget(self._dict_log)

        self._refresh_dict_status()

        layout.addWidget(dict_group)

        storage_group = QGroupBox(I18n.t("settings.study.group_storage"))
        storage_layout = QFormLayout(storage_group)
        storage_layout.setSpacing(8)

        self._study_materials_dir = QLineEdit()
        default_dir = os.path.join(os.path.expanduser("~"), "Music", "Music++", "StudyMaterials")
        self._study_materials_dir.setText(default_dir)
        self._study_materials_dir.setReadOnly(True)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self._study_materials_dir, 1)
        btn_browse = QPushButton(I18n.t("settings.study.btn_browse"))
        btn_browse.setFixedWidth(70)
        btn_browse.clicked.connect(self._on_study_dir_browse)
        dir_row.addWidget(btn_browse)
        storage_layout.addRow(I18n.t("settings.study.label_materials_dir"), dir_row)

        layout.addWidget(storage_group)

        bilibili_group = QGroupBox(I18n.t("settings.study.group_bilibili"))
        bilibili_layout = QVBoxLayout(bilibili_group)
        bilibili_layout.setSpacing(8)

        self._bilibili_sessdata = QLineEdit()
        self._bilibili_sessdata.setEchoMode(QLineEdit.Password)
        self._bilibili_sessdata.setPlaceholderText(I18n.t("settings.study.ph_bilibili_sessdata"))
        bilibili_layout.addWidget(self._bilibili_sessdata)

        bilibili_hint = QLabel(
            I18n.t("settings.study.bilibili_hint")
        )
        bilibili_hint.setStyleSheet("color: #888; font-size: 11px;")
        bilibili_hint.setWordWrap(True)
        bilibili_layout.addWidget(bilibili_hint)

        layout.addWidget(bilibili_group)

        self._bilibili_sessdata.textChanged.connect(
            lambda v: self.settings_changed.emit("study/bilibili_sessdata", v.strip())
        )

        self._study_repeat_count.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/repeat_count", v)
        )
        self._study_repeat_pause.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/repeat_pause_sec", v)
        )
        self._study_auto_next.toggled.connect(
            lambda v: self.settings_changed.emit("study/auto_next_sentence", v)
        )
        self._study_default_lang.currentTextChanged.connect(
            lambda v: self.settings_changed.emit("study/default_subtitle_lang", v)
        )
        self._study_default_lang_secondary.currentTextChanged.connect(
            lambda v: self.settings_changed.emit("study/default_subtitle_lang_secondary", v)
        )
        self._study_auto_split_gap.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/auto_split_gap", v)
        )

        self._chk_shadowing.toggled.connect(
            lambda v: self.settings_changed.emit("study/shadowing_enabled", v)
        )
        self._spn_shadowing_extra.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/shadowing_extra_sec", v)
        )
        self._spn_autoseg_threshold.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/autoseg_threshold", v)
        )
        self._spn_autoseg_min_silence.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/autoseg_min_silence", v)
        )
        self._spn_autoseg_min_segment.valueChanged.connect(
            lambda v: self.settings_changed.emit("study/autoseg_min_segment", v)
        )

        self._whisper_model_combo.currentIndexChanged.connect(
            lambda: self.settings_changed.emit("whisper/model", self._whisper_model_combo.currentData() or "base")
        )
        self._whisper_device_combo.currentIndexChanged.connect(
            lambda: self.settings_changed.emit("whisper/device", self._whisper_device_combo.currentData() or "auto")
        )
        self._whisper_lang_combo.currentIndexChanged.connect(
            lambda: self.settings_changed.emit("whisper/language", self._whisper_lang_combo.currentData() or "")
        )

        layout.addStretch()
        return page

    def _refresh_ffmpeg_status(self):
        from src.infrastructure.media_extractor import _get_ffmpeg_path, _get_ffprobe_path
        ffmpeg_path = _get_ffmpeg_path()
        ffprobe_path = _get_ffprobe_path()

        ffmpeg_ok = os.path.isfile(ffmpeg_path) if ffmpeg_path else False
        ffprobe_ok = os.path.isfile(ffprobe_path) if ffprobe_path else False

        parts = []
        if ffmpeg_ok:
            parts.append(I18n.t("settings.study.ffmpeg_installed"))
        else:
            parts.append(I18n.t("settings.study.ffmpeg_not_installed"))
        if ffprobe_ok:
            parts.append(I18n.t("settings.study.ffprobe_installed"))
        else:
            parts.append(I18n.t("settings.study.ffprobe_not_installed"))

        self._ffmpeg_status_label.setText("  |  ".join(parts))
        if ffmpeg_ok:
            self._ffmpeg_status_label.setStyleSheet("color: #32c864;")
        else:
            self._ffmpeg_status_label.setStyleSheet("color: #e0a030;")

    def _on_ffmpeg_browse(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("settings.study.dlg_select_ffmpeg"), "", I18n.t("settings.study.dlg_executable_filter")
        )
        if file_path and os.path.isfile(file_path):
            plugin_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "plugins", "ffmpeg"
            )
            os.makedirs(plugin_dir, exist_ok=True)
            import shutil
            dest = os.path.join(plugin_dir, "ffmpeg.exe")
            try:
                shutil.copy2(file_path, dest)
            except Exception:
                dest = file_path
            self.settings_changed.emit("study/ffmpeg_path", dest)
            self._refresh_ffmpeg_status()

    def _on_ffprobe_browse(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("settings.study.dlg_select_ffprobe"), "", I18n.t("settings.study.dlg_executable_filter")
        )
        if file_path and os.path.isfile(file_path):
            plugin_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "plugins", "ffmpeg"
            )
            os.makedirs(plugin_dir, exist_ok=True)
            import shutil
            dest = os.path.join(plugin_dir, "ffprobe.exe")
            try:
                shutil.copy2(file_path, dest)
            except Exception:
                dest = file_path
            self.settings_changed.emit("study/ffprobe_path", dest)
            self._refresh_ffmpeg_status()

    def _on_ffmpeg_download(self):
        from PySide6.QtCore import QThread, Signal as QSignal
        import urllib.request
        import zipfile
        import io

        log_msgbox("info", I18n.t("settings.study.msg_ffmpeg_download_title"), I18n.t("settings.study.msg_ffmpeg_download_text"))
        reply = ThemedMessageBox.information(
            self, I18n.t("settings.study.msg_ffmpeg_download_title"),
            I18n.t("settings.study.msg_ffmpeg_download_text"),
            buttons=[("ok", I18n.t("common.ok")), ("cancel", I18n.t("common.cancel"))], default_button="ok",
        )
        if reply != 1:
            return

        self._btn_ffmpeg_download.setEnabled(False)
        self._btn_ffmpeg_download.setText(I18n.t("settings.study.btn_downloading"))

        class _DownloadWorker(QThread):
            progress = QSignal(str)
            finished = QSignal(bool, str)

            def run(self):
                try:
                    plugin_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "plugins", "ffmpeg"
                    )
                    os.makedirs(plugin_dir, exist_ok=True)

                    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=300) as resp:
                        total = int(resp.headers.get("content-length", 0))
                        data = b""
                        downloaded = 0
                        while True:
                            chunk = resp.read(512 * 1024)
                            if not chunk:
                                break
                            data += chunk
                            downloaded += len(chunk)
                            if total > 0 and downloaded % (10 * 1024 * 1024) < 512 * 1024:
                                pct = downloaded * 100 // total
                                self.progress.emit(I18n.tf("settings.study.msg_download_progress", pct=pct))

                    self.progress.emit(I18n.t("settings.study.msg_extracting"))
                    extracted = []
                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                        for name in zf.namelist():
                            basename = os.path.basename(name)
                            if basename in ("ffmpeg.exe", "ffprobe.exe"):
                                with zf.open(name) as src:
                                    dest = os.path.join(plugin_dir, basename)
                                    with open(dest, "wb") as dst:
                                        dst.write(src.read())
                                extracted.append(basename)

                    if "ffmpeg.exe" in extracted:
                        self.finished.emit(True, I18n.tf("settings.study.msg_install_success", files=', '.join(extracted)))
                    else:
                        self.finished.emit(False, I18n.t("settings.study.msg_ffmpeg_not_found"))
                except Exception as e:
                    self.finished.emit(False, str(e))

        self._ffmpeg_download_worker = _DownloadWorker()
        self._ffmpeg_download_worker.progress.connect(
            lambda msg: self._ffmpeg_status_label.setText(msg)
        )
        self._ffmpeg_download_worker.finished.connect(self._on_ffmpeg_download_finished)
        self._ffmpeg_download_worker.start()

    def _on_ffmpeg_download_finished(self, success, message):
        self._btn_ffmpeg_download.setEnabled(True)
        self._btn_ffmpeg_download.setText(I18n.t("settings.study.btn_auto_downloading"))
        if success:
            log_msgbox("info", I18n.t("settings.study.msg_ffmpeg_install_title"), f"✓ {message}")
            ThemedMessageBox.information(self, I18n.t("settings.study.msg_ffmpeg_install_title"), f"✓ {message}")
            self.settings_changed.emit("study/ffmpeg_path", "plugin")
        else:
            log_msgbox("warning", I18n.t("settings.study.msg_ffmpeg_fail_title"), I18n.tf("settings.study.msg_ffmpeg_fail_text", message=message))
            ThemedMessageBox.warning(self, I18n.t("settings.study.msg_ffmpeg_fail_title"), I18n.tf("settings.study.msg_ffmpeg_fail_text", message=message))
        self._refresh_ffmpeg_status()

    def _on_ffmpeg_clear(self):
        log_msgbox("question", I18n.t("settings.study.msg_ffmpeg_clear_title"), I18n.t("settings.study.msg_ffmpeg_clear_text"))
        reply = ThemedMessageBox.question(
            self, I18n.t("settings.study.msg_ffmpeg_clear_title"),
            I18n.t("settings.study.msg_ffmpeg_clear_text"),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no",
        )
        if reply == 1:
            plugin_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "plugins", "ffmpeg"
            )
            import shutil
            if os.path.isdir(plugin_dir):
                shutil.rmtree(plugin_dir, True)
            self.settings_changed.emit("study/ffmpeg_path", "")
            self._refresh_ffmpeg_status()

    def _refresh_whisper_status(self):
        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()
        status = plugin.get_status()
        if status["installed"]:
            device_info = status["device"]
            if status["cuda_available"]:
                device_info += I18n.t("settings.study.whisper_cuda_available")
            model_info = I18n.tf("settings.study.whisper_model_loaded", model=status['current_model']) if status["model_loaded"] else ""
            self._whisper_status_label.setText(
                I18n.tf("settings.study.whisper_installed", version=status['version'], device_info=device_info, model_info=model_info)
            )
            self._whisper_status_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
            self._btn_whisper_install.setEnabled(False)
            self._btn_whisper_uninstall.setEnabled(True)
            self._btn_whisper_download_model.setEnabled(True)
        else:
            self._whisper_status_label.setText(
                I18n.t("settings.study.whisper_not_installed")
            )
            self._whisper_status_label.setStyleSheet("color: #FF9800; font-size: 12px;")
            self._btn_whisper_install.setEnabled(True)
            self._btn_whisper_uninstall.setEnabled(False)
            self._btn_whisper_download_model.setEnabled(False)

    def _on_whisper_install(self):
        mirror_url = self._whisper_mirror_combo.currentData() or ""
        mirror_name = self._whisper_mirror_combo.currentText()
        source_hint = f"\n{I18n.t('settings.study.whisper_mirror_source')}: {mirror_name}" if mirror_url else f"\n{I18n.t('settings.study.whisper_mirror_source')}: {I18n.t('settings.study.whisper_mirror_default')}"

        log_msgbox("info", I18n.t("settings.study.whisper_install_title"), I18n.tf("settings.study.whisper_install_text", source_hint=source_hint))
        reply = ThemedMessageBox.information(
            self, I18n.t("settings.study.whisper_install_title"),
            I18n.tf("settings.study.whisper_install_text", source_hint=source_hint),
            buttons=[("ok", I18n.t("common.ok")), ("cancel", I18n.t("common.cancel"))], default_button="ok",
        )
        if reply != 1:
            return

        self._whisper_log.clear()
        self._whisper_log.setVisible(True)
        self._btn_whisper_install.setEnabled(False)
        self._btn_whisper_uninstall.setEnabled(False)
        self._btn_whisper_download_model.setEnabled(False)
        self._whisper_status_label.setText(I18n.t("settings.study.whisper_installing"))
        self._whisper_status_label.setStyleSheet("color: #2196F3; font-size: 12px;")

        self._whisper_install_worker = WhisperInstallWorker(mirror_url=mirror_url)
        self._whisper_install_worker.progress.connect(self._on_whisper_log)
        self._whisper_install_worker.finished.connect(self._on_whisper_install_finished)
        self._whisper_install_worker.start()

    def _on_whisper_log(self, msg, pct):
        if pct >= 0:
            self._whisper_log.append(f"<span style='color:#aaa'>[{pct}%]</span> {msg}")
            self._whisper_status_label.setText(f"⏳ {msg} ({pct}%)")
        else:
            self._whisper_log.append(f"<span style='color:#f44336'>[{I18n.t('common.error')}]</span> {msg}")
            self._whisper_status_label.setText(f"❌ {msg}")
            self._whisper_status_label.setStyleSheet("color: #f44336; font-size: 12px;")

    def _on_whisper_install_finished(self, ok):
        if ok:
            self._whisper_log.append(f"<span style='color:#4CAF50'>{I18n.t('settings.study.whisper_install_success')}</span>")
            self._whisper_status_label.setText(I18n.t("settings.study.whisper_install_success"))
            self._whisper_status_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
            self._refresh_whisper_status()
            log_msgbox("info", I18n.t("settings.study.whisper_install_success_title"), I18n.t("settings.study.whisper_install_success_text"))
            ThemedMessageBox.information(
                self, I18n.t("settings.study.whisper_install_success_title"),
                I18n.t("settings.study.whisper_install_success_text"),
            )
        else:
            self._whisper_log.append(f"<span style='color:#f44336'>{I18n.t('settings.study.whisper_install_fail')}</span>")
            self._refresh_whisper_status()

    def _on_whisper_uninstall(self):
        log_msgbox("question", I18n.t("settings.study.whisper_uninstall_title"), I18n.t("settings.study.whisper_uninstall_text"))
        reply = ThemedMessageBox.question(
            self, I18n.t("settings.study.whisper_uninstall_title"),
            I18n.t("settings.study.whisper_uninstall_text"),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no",
        )
        if reply != 1:
            return

        self._whisper_log.clear()
        self._whisper_log.setVisible(True)
        self._btn_whisper_install.setEnabled(False)
        self._btn_whisper_uninstall.setEnabled(False)
        self._btn_whisper_download_model.setEnabled(False)
        self._whisper_status_label.setText(I18n.t("settings.study.whisper_uninstalling"))
        self._whisper_status_label.setStyleSheet("color: #2196F3; font-size: 12px;")

        self._whisper_uninstall_worker = WhisperUninstallWorker()
        self._whisper_uninstall_worker.progress.connect(self._on_whisper_log)
        self._whisper_uninstall_worker.finished.connect(self._on_whisper_uninstall_finished)
        self._whisper_uninstall_worker.start()

    def _on_whisper_uninstall_finished(self, ok):
        if ok:
            self._whisper_log.append(f"<span style='color:#4CAF50'>{I18n.t('settings.study.whisper_uninstall_success')}</span>")
        else:
            self._whisper_log.append(f"<span style='color:#f44336'>{I18n.t('settings.study.whisper_uninstall_fail')}</span>")
        self._refresh_whisper_status()

    def _on_whisper_download_model(self):
        model_name = self._whisper_model_combo.currentData()
        if not model_name:
            return

        hf_mirror_url = self._whisper_hf_combo.currentData() or ""
        hf_mirror_name = self._whisper_hf_combo.currentText()
        hf_hint = f"\n{I18n.t('settings.study.whisper_hf_mirror')}: {hf_mirror_name}" if hf_mirror_url else f"\n{I18n.t('settings.study.whisper_hf_mirror')}: {I18n.t('settings.study.whisper_hf_default')}"

        model_info = next((m for m in WHISPER_MODELS if m["name"] == model_name), None)
        size_hint = model_info["vram"] if model_info else ""

        log_msgbox("info", I18n.t("settings.study.whisper_download_model_title"), I18n.tf("settings.study.whisper_download_model_text", model_name=model_name, size_hint=size_hint, hf_hint=hf_hint))
        reply = ThemedMessageBox.information(
            self, I18n.t("settings.study.whisper_download_model_title"),
            I18n.tf("settings.study.whisper_download_model_text", model_name=model_name, size_hint=size_hint, hf_hint=hf_hint),
            buttons=[("ok", I18n.t("common.ok")), ("cancel", I18n.t("common.cancel"))], default_button="ok",
        )
        if reply != 1:
            return

        self._whisper_log.clear()
        self._whisper_log.setVisible(True)
        self._btn_whisper_install.setEnabled(False)
        self._btn_whisper_uninstall.setEnabled(False)
        self._btn_whisper_download_model.setEnabled(False)
        self._whisper_status_label.setText(I18n.tf("settings.study.whisper_downloading_model", name=model_name))
        self._whisper_status_label.setStyleSheet("color: #2196F3; font-size: 12px;")

        self._whisper_download_worker = WhisperDownloadModelWorker(model_name, hf_mirror_url=hf_mirror_url)
        self._whisper_download_worker.progress.connect(self._on_whisper_log)
        self._whisper_download_worker.finished.connect(self._on_whisper_download_finished)
        self._whisper_download_worker.start()

    def _on_whisper_download_finished(self, ok):
        if ok:
            self._whisper_log.append(f"<span style='color:#4CAF50'>{I18n.t('settings.study.whisper_model_download_success')}</span>")
        else:
            self._whisper_log.append(f"<span style='color:#f44336'>{I18n.t('settings.study.whisper_model_download_fail')}</span>")
        self._refresh_whisper_status()

    def _on_whisper_hf_changed(self):
        hf_url = self._whisper_hf_combo.currentData() or ""
        self.settings_changed.emit("whisper/hf_mirror", hf_url)

    def _on_study_dir_browse(self):
        from PySide6.QtWidgets import QFileDialog
        dir_path = QFileDialog.getExistingDirectory(self, "Select Study Materials Directory")
        if dir_path:
            self._study_materials_dir.setText(dir_path)

    def _refresh_dict_status(self):
        from src.infrastructure.ecdict_provider import is_ecdict_available
        if is_ecdict_available():
            self._dict_status_label.setText(I18n.t("settings.study.dict_ready"))
            self._dict_status_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
            self._btn_dict_download.setText(I18n.t("settings.study.btn_dict_redownload"))
        else:
            self._dict_status_label.setText(I18n.t("settings.study.dict_not_downloaded"))
            self._dict_status_label.setStyleSheet("color: #f44336; font-size: 12px;")
            self._btn_dict_download.setText(I18n.t("settings.study.btn_dict_download"))

    def _on_dict_download(self):
        log_msgbox("info", I18n.t("settings.study.dict_download_title"), I18n.t("settings.study.dict_download_text"))
        reply = ThemedMessageBox.information(
            self, I18n.t("settings.study.dict_download_title"),
            I18n.t("settings.study.dict_download_text"),
            buttons=[("ok", I18n.t("common.ok")), ("cancel", I18n.t("common.cancel"))], default_button="ok",
        )
        if reply != 1:
            return

        self._dict_log.clear()
        self._dict_log.setVisible(True)
        self._btn_dict_download.setEnabled(False)
        self._dict_status_label.setText(I18n.t("settings.study.dict_downloading"))
        self._dict_status_label.setStyleSheet("color: #2196F3; font-size: 12px;")

        self._dict_download_worker = DictDownloadWorker()
        self._dict_download_worker.progress.connect(self._on_dict_download_log)
        self._dict_download_worker.finished.connect(self._on_dict_download_finished)
        self._dict_download_worker.start()

    def _on_dict_download_log(self, msg, pct):
        if pct >= 0:
            self._dict_log.append(f"<span style='color:#aaa'>[{pct}%]</span> {msg}")
            self._dict_status_label.setText(f"⏳ {msg} ({pct}%)")
        else:
            self._dict_log.append(f"<span style='color:#f44336'>[{I18n.t('common.error')}]</span> {msg}")

    def _on_dict_download_finished(self, success, error_msg):
        if hasattr(self, '_dict_download_worker') and self._dict_download_worker:
            self._dict_download_worker.wait()
            self._dict_download_worker = None

        self._btn_dict_download.setEnabled(True)

        if success:
            self._dict_log.append(f"<span style='color:#4CAF50'>{I18n.t('settings.study.dict_download_success')}</span>")
        else:
            self._dict_log.append(f"<span style='color:#f44336'>{I18n.tf('settings.study.dict_download_fail', error=error_msg)}</span>")

        self._refresh_dict_status()

    # ── WebDAV Page ─────────────────────────────────────────────

    def _build_webdav_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(I18n.t("settings.webdav.label_accounts")))
        header_layout.addStretch()
        btn_add = QPushButton(I18n.t("settings.webdav.btn_add"))
        btn_add.setFixedHeight(28)
        btn_add.clicked.connect(self._on_webdav_add)
        header_layout.addWidget(btn_add)
        layout.addLayout(header_layout)

        self._webdav_table = QTableWidget()
        self._webdav_table.setColumnCount(5)
        self._webdav_table.setHorizontalHeaderLabels([I18n.t("settings.webdav.col_name"), I18n.t("settings.webdav.col_server"), I18n.t("settings.webdav.col_username"), I18n.t("settings.webdav.col_preset"), I18n.t("settings.webdav.col_action")])
        self._webdav_table.verticalHeader().setVisible(False)
        self._webdav_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._webdav_table.setSelectionMode(QTableWidget.SingleSelection)
        self._webdav_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._webdav_table.setFont(QFont("Microsoft YaHei", 9))
        self._webdav_table.verticalHeader().setDefaultSectionSize(28)
        wh = self._webdav_table.horizontalHeader()
        wh.setSectionResizeMode(0, QHeaderView.Stretch)
        wh.setSectionResizeMode(1, QHeaderView.Stretch)
        wh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        layout.addWidget(self._webdav_table)

        hint = QLabel(I18n.t("settings.webdav.hint"))
        hint.setStyleSheet("color: #888; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        presets_group = QGroupBox(I18n.t("settings.webdav.group_presets"))
        presets_group.setFont(QFont("Microsoft YaHei", 10))
        presets_inner = QVBoxLayout(presets_group)
        presets_inner.setSpacing(2)
        presets_inner.setContentsMargins(8, 8, 8, 8)
        preset_items = [
            (I18n.t("settings.webdav.preset_jianguoyun"), "https://dav.jianguoyun.com/dav/", I18n.t("settings.webdav.preset_jianguoyun_desc")),
            (I18n.t("settings.webdav.preset_alist"), "http://IP:5244/dav/", I18n.t("settings.webdav.preset_alist_desc")),
            (I18n.t("settings.webdav.preset_synology"), "http://IP:5005", I18n.t("settings.webdav.preset_synology_desc")),
            (I18n.t("settings.webdav.preset_qnap"), "http://IP:8080", I18n.t("settings.webdav.preset_qnap_desc")),
            (I18n.t("settings.webdav.preset_nextcloud"), I18n.t("settings.webdav.preset_nextcloud_url"), I18n.t("settings.webdav.preset_nextcloud_desc")),
            (I18n.t("settings.webdav.preset_infinicloud"), "https://tasgn.storage.infini-cloud.net/dav/", I18n.t("settings.webdav.preset_infinicloud_desc")),
        ]
        presets_content = QWidget()
        presets_vbox = QVBoxLayout(presets_content)
        presets_vbox.setContentsMargins(0, 0, 0, 0)
        presets_vbox.setSpacing(2)
        for label, addr, desc in preset_items:
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(f"<b>{label}</b>"))
            addr_label = QLabel(addr)
            addr_label.setStyleSheet("color: #6ab4ff; font-size: 11px;")
            addr_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row_layout.addWidget(addr_label)
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color: #999; font-size: 10px;")
            row_layout.addWidget(desc_label)
            row_layout.addStretch()
            presets_vbox.addLayout(row_layout)
        presets_scroll = QScrollArea()
        presets_scroll.setWidget(presets_content)
        presets_scroll.setWidgetResizable(True)
        presets_scroll.setFrameShape(QScrollArea.NoFrame)
        presets_scroll.setFixedHeight(26 * 3 + 8)
        presets_inner.addWidget(presets_scroll)
        layout.addWidget(presets_group)

        alist_group = QGroupBox(I18n.t("settings.webdav.group_alist_guide"))
        alist_group.setFont(QFont("Microsoft YaHei", 10))
        alist_inner = QVBoxLayout(alist_group)
        alist_inner.setSpacing(2)
        alist_inner.setContentsMargins(8, 8, 8, 8)
        alist_content = QWidget()
        alist_vbox = QVBoxLayout(alist_content)
        alist_vbox.setContentsMargins(0, 0, 0, 0)
        alist_vbox.setSpacing(6)
        alist_steps = [
            I18n.t("settings.webdav.alist_step1"),
            I18n.t("settings.webdav.alist_step2"),
        ]
        for step_html in alist_steps:
            step_label = QLabel(step_html)
            step_label.setWordWrap(True)
            step_label.setTextFormat(Qt.RichText)
            step_label.setStyleSheet("font-size: 11px; padding: 2px 0;")
            step_label.setOpenExternalLinks(True)
            alist_vbox.addWidget(step_label)
        alist_scroll = QScrollArea()
        alist_scroll.setWidget(alist_content)
        alist_scroll.setWidgetResizable(True)
        alist_scroll.setFrameShape(QScrollArea.NoFrame)
        alist_scroll.setFixedHeight(26 * 4 + 8)
        alist_inner.addWidget(alist_scroll)
        layout.addWidget(alist_group)

        layout.addStretch()

        self._refresh_webdav_table()
        return page

    def _refresh_webdav_table(self):
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        self._webdav_table.setRowCount(0)

        from src.business.webdav_account_manager import WebDAVAccountManager
        mgr = WebDAVAccountManager()
        accounts = mgr.get_all_accounts()

        for account in accounts:
            row = self._webdav_table.rowCount()
            self._webdav_table.insertRow(row)

            name_item = QTableWidgetItem(account.get("name", ""))
            name_item.setData(Qt.UserRole, account.get("id", ""))
            self._webdav_table.setItem(row, 0, name_item)
            self._webdav_table.setItem(row, 1, QTableWidgetItem(account.get("server_url", "")))
            self._webdav_table.setItem(row, 2, QTableWidgetItem(account.get("username", "")))

            preset = account.get("preset", "")
            self._webdav_table.setItem(row, 3, QTableWidgetItem(preset if preset else I18n.t("settings.webdav.preset_custom")))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 0, 4, 0)
            action_layout.setSpacing(6)

            link_color = tc.get("accent", "#32c864")
            link_style = (
                f"QPushButton {{ color: {link_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: {tc.get('accent_hover', '#3de878')}; }}"
            )
            danger_color = tc.get("danger", "#e05050")
            danger_style = (
                f"QPushButton {{ color: {danger_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: #ff6666; }}"
            )

            aid = account.get("id", "")

            btn_test = QPushButton(I18n.t("settings.webdav.btn_test"))
            btn_test.setStyleSheet(link_style)
            btn_test.setCursor(Qt.PointingHandCursor)
            btn_test.setFixedHeight(20)
            btn_test.clicked.connect(lambda checked, a=aid: self._on_webdav_test(a))
            action_layout.addWidget(btn_test)

            btn_edit = QPushButton(I18n.t("settings.webdav.btn_edit"))
            btn_edit.setStyleSheet(link_style)
            btn_edit.setCursor(Qt.PointingHandCursor)
            btn_edit.setFixedHeight(20)
            btn_edit.clicked.connect(lambda checked, a=aid: self._on_webdav_edit(a))
            action_layout.addWidget(btn_edit)

            btn_del = QPushButton(I18n.t("settings.webdav.btn_delete"))
            btn_del.setStyleSheet(danger_style)
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedHeight(20)
            btn_del.clicked.connect(lambda checked, a=aid: self._on_webdav_delete(a))
            action_layout.addWidget(btn_del)

            self._webdav_table.setCellWidget(row, 4, action_widget)

    def _on_webdav_add(self):
        dlg = WebDAVAccountDialog(self)
        if dlg.exec() == QDialog.Accepted:
            from src.business.webdav_account_manager import WebDAVAccountManager
            mgr = WebDAVAccountManager()
            mgr.add_account(dlg.get_data())
            self._refresh_webdav_table()

    def _on_webdav_edit(self, account_id: str):
        from src.business.webdav_account_manager import WebDAVAccountManager
        mgr = WebDAVAccountManager()
        account = mgr.get_account(account_id)
        if not account:
            return
        dlg = WebDAVAccountDialog(self, account)
        if dlg.exec() == QDialog.Accepted:
            mgr.update_account(account_id, dlg.get_data())
            self._refresh_webdav_table()

    def _on_webdav_delete(self, account_id: str):
        from src.business.webdav_account_manager import WebDAVAccountManager
        mgr = WebDAVAccountManager()
        account = mgr.get_account(account_id)
        if not account:
            return
        log_msgbox("warning", I18n.t("settings.webdav.msg_delete_title"), I18n.tf("settings.webdav.msg_delete_text", name=account.get('name', '')))
        reply = ThemedMessageBox.warning(
            self, I18n.t("settings.webdav.msg_delete_title"),
            I18n.tf("settings.webdav.msg_delete_text", name=account.get('name', '')),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no",
        )
        if reply == 1:
            mgr.delete_account(account_id)
            self._refresh_webdav_table()

    def _on_webdav_test(self, account_id: str):
        from src.business.webdav_account_manager import WebDAVAccountManager
        mgr = WebDAVAccountManager()
        ok, msg = mgr.test_connection(account_id)
        if ok:
            log_msgbox("info", I18n.t("settings.webdav.msg_test_title"), I18n.tf("settings.webdav.msg_test_success", msg=msg))
            ThemedMessageBox.information(self, I18n.t("settings.webdav.msg_test_title"), I18n.tf("settings.webdav.msg_test_success", msg=msg))
        else:
            log_msgbox("warning", I18n.t("settings.webdav.msg_test_title"), I18n.tf("settings.webdav.msg_test_fail", msg=msg))
            ThemedMessageBox.warning(self, I18n.t("settings.webdav.msg_test_title"), I18n.tf("settings.webdav.msg_test_fail", msg=msg))

    # ── Network Page ────────────────────────────────────────────

    def _build_network_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        proxy_group = QGroupBox(I18n.t("settings.network.group_proxy"))
        proxy_layout = QFormLayout(proxy_group)
        proxy_layout.setLabelAlignment(Qt.AlignRight)

        self._cmb_proxy_type = QComboBox()
        self._cmb_proxy_type.addItems([I18n.t("settings.network.proxy_none"), I18n.t("settings.network.proxy_http"), I18n.t("settings.network.proxy_socks5")])
        self._cmb_proxy_type.currentIndexChanged.connect(
            lambda i: self.settings_changed.emit("network/proxy_type", i)
        )
        proxy_layout.addRow(I18n.t("settings.network.proxy_type"), self._cmb_proxy_type)

        addr_row = QHBoxLayout()
        self._txt_proxy_addr = QLineEdit()
        self._txt_proxy_addr.setPlaceholderText("127.0.0.1")
        self._txt_proxy_addr.textChanged.connect(
            lambda v: self.settings_changed.emit("network/proxy_addr", v)
        )
        self._spn_proxy_port = QSpinBox()
        self._spn_proxy_port.setRange(1, 65535)
        self._spn_proxy_port.setValue(7890)
        self._spn_proxy_port.setFixedWidth(80)
        self._spn_proxy_port.valueChanged.connect(
            lambda v: self.settings_changed.emit("network/proxy_port", v)
        )
        addr_row.addWidget(self._txt_proxy_addr, 3)
        addr_row.addWidget(QLabel(":"))
        addr_row.addWidget(self._spn_proxy_port, 1)
        proxy_layout.addRow(I18n.t("settings.network.proxy_address"), addr_row)

        test_row = QHBoxLayout()
        self._btn_proxy_test = QPushButton(I18n.t("settings.network.proxy_test"))
        self._btn_proxy_test.setFixedHeight(28)
        self._btn_proxy_test.clicked.connect(self._on_proxy_test)
        test_row.addWidget(self._btn_proxy_test)
        self._lbl_proxy_test = QLabel("")
        self._lbl_proxy_test.setStyleSheet("font-size: 11px;")
        test_row.addWidget(self._lbl_proxy_test, 1)
        proxy_layout.addRow("", test_row)

        layout.addWidget(proxy_group)

        request_group = QGroupBox(I18n.t("settings.network.group_request"))
        request_layout = QFormLayout(request_group)
        request_layout.setLabelAlignment(Qt.AlignRight)

        self._spn_timeout = QSpinBox()
        self._spn_timeout.setRange(5, 60)
        self._spn_timeout.setValue(30)
        self._spn_timeout.setSuffix(I18n.t("settings.network.suffix_sec"))
        self._spn_timeout.valueChanged.connect(
            lambda v: self.settings_changed.emit("network/timeout", v)
        )
        request_layout.addRow(I18n.t("settings.network.timeout"), self._spn_timeout)

        self._spn_retry = QSpinBox()
        self._spn_retry.setRange(0, 5)
        self._spn_retry.setValue(3)
        self._spn_retry.setSuffix(I18n.t("settings.network.suffix_times"))
        self._spn_retry.valueChanged.connect(
            lambda v: self.settings_changed.emit("network/retry", v)
        )
        request_layout.addRow(I18n.t("settings.network.retry"), self._spn_retry)

        layout.addWidget(request_group)
        layout.addStretch()

        return page

    # ── Shortcuts Page ──────────────────────────────────────────

    def _build_shortcuts_page(self):
        from src.infrastructure.theme_engine import ThemeEngine
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        _sc_tc = ThemeEngine().get_current_colors()
        info_label = QLabel(I18n.t("settings.shortcut.info_text"))
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {_sc_tc.get('text_muted', '#888')}; font-size: 11px;")
        layout.addWidget(info_label)

        self._shortcut_table = QTableWidget()
        self._shortcut_table.setColumnCount(3)
        self._shortcut_table.setHorizontalHeaderLabels([I18n.t("settings.shortcut.col_action"), I18n.t("settings.shortcut.col_shortcut"), I18n.t("settings.shortcut.col_default")])
        self._shortcut_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._shortcut_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._shortcut_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._shortcut_table.verticalHeader().setVisible(False)
        self._shortcut_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._shortcut_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._shortcut_table.verticalHeader().setDefaultSectionSize(36)

        self._shortcut_edits = {}
        self._shortcut_defaults = {}

        for row_idx, (action_id, label_key, default_key) in enumerate(self._SHORTCUT_DEFS):
            self._shortcut_table.insertRow(row_idx)
            self._shortcut_defaults[action_id] = default_key

            name_item = QTableWidgetItem(I18n.t(label_key))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            name_item.setData(Qt.UserRole, action_id)
            self._shortcut_table.setItem(row_idx, 0, name_item)

            key_edit = QKeySequenceEdit(QKeySequence(default_key))
            key_edit.setFixedHeight(30)
            key_edit.keySequenceChanged.connect(
                lambda seq, aid=action_id: self._on_shortcut_changed(aid, seq)
            )
            self._shortcut_edits[action_id] = key_edit
            self._shortcut_table.setCellWidget(row_idx, 1, key_edit)

            default_item = QTableWidgetItem(default_key)
            default_item.setFlags(default_item.flags() & ~Qt.ItemIsEditable)
            default_item.setForeground(QColor(ThemeEngine().get_current_colors().get("text_muted", "#666680")))
            self._shortcut_table.setItem(row_idx, 2, default_item)

        layout.addWidget(self._shortcut_table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_reset_shortcuts = QPushButton(I18n.t("settings.shortcut.btn_reset"))
        self._btn_reset_shortcuts.clicked.connect(self._reset_shortcuts)
        btn_row.addWidget(self._btn_reset_shortcuts)
        layout.addLayout(btn_row)

        return page

    def _on_shortcut_changed(self, action_id, key_sequence):
        key_str = key_sequence.toString()
        self.settings_changed.emit(f"shortcuts/{action_id}", key_str)

    def _reset_shortcuts(self):
        for action_id, label_key, default_key in self._SHORTCUT_DEFS:
            edit = self._shortcut_edits.get(action_id)
            if edit:
                edit.blockSignals(True)
                edit.setKeySequence(QKeySequence(default_key))
                edit.blockSignals(False)
                self.settings_changed.emit(f"shortcuts/{action_id}", default_key)

    def load_shortcuts_from_config(self, config):
        for action_id, label_key, default_key in self._SHORTCUT_DEFS:
            saved = config.get("Shortcuts", action_id, default_key)
            edit = self._shortcut_edits.get(action_id)
            if edit:
                edit.blockSignals(True)
                edit.setKeySequence(QKeySequence(saved))
                edit.blockSignals(False)

    def _on_proxy_test(self):
        self._btn_proxy_test.setEnabled(False)
        self._lbl_proxy_test.setText(I18n.t("settings.network.proxy_testing"))
        threading.Thread(target=self._do_proxy_test, daemon=True).start()

    def _do_proxy_test(self):
        try:
            from src.core.network_service import NetworkService
            ns = NetworkService()
            ns.apply_proxy()
            result = ns.get("https://httpbin.org/ip", timeout=10)
            if result and "origin" in result:
                ip = result["origin"]
                msg = I18n.tf("settings.network.proxy_test_ok", ip=ip)
            else:
                msg = I18n.t("settings.network.proxy_test_ok_no_ip")
            color = "#32c864"
        except Exception as e:
            msg = I18n.tf("settings.network.proxy_test_fail", error=str(e)[:80])
            color = "#e74c3c"
        from PySide6.QtCore import QTimer
        def _update():
            self._lbl_proxy_test.setText(msg)
            self._lbl_proxy_test.setStyleSheet(f"color: {color}; font-size: 11px;")
            self._btn_proxy_test.setEnabled(True)
        QTimer.singleShot(0, _update)

    # ── About Page ──────────────────────────────────────────────

    def _build_about_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignTop)

        title_font = QFont("Microsoft YaHei", 18, QFont.Bold)
        section_font = QFont("Microsoft YaHei", 11, QFont.Bold)
        body_font = QFont("Microsoft YaHei", 10)
        small_font = QFont("Microsoft YaHei", 9)

        app_name = QLabel("Music++")
        app_name.setFont(title_font)
        app_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(app_name)

        version = QLabel(I18n.t("settings.about.version"))
        version.setFont(QFont("Microsoft YaHei", 10))
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #888;")
        layout.addWidget(version)

        layout.addSpacing(12)

        intro = QLabel(I18n.t("settings.about.intro"))
        intro.setFont(body_font)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        layout.addSpacing(8)

        def add_section(title_text):
            lbl = QLabel(title_text)
            lbl.setFont(section_font)
            layout.addWidget(lbl)

        def add_bullet(text, bold_prefix=""):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(16, 2, 0, 2)
            row_layout.setSpacing(0)
            indent = QLabel("• ")
            indent.setFont(body_font)
            indent.setFixedWidth(16)
            row_layout.addWidget(indent)
            if bold_prefix:
                content = QLabel()
                content.setFont(body_font)
                content.setWordWrap(True)
                content.setTextFormat(Qt.RichText)
                content.setText(f"<b>{bold_prefix}</b>{text}")
                row_layout.addWidget(content)
            else:
                content = QLabel(text)
                content.setFont(body_font)
                content.setWordWrap(True)
                row_layout.addWidget(content)
            layout.addWidget(row)

        add_section(I18n.t("settings.about.section_acknowledgments"))
        add_bullet(I18n.t("settings.about.ack_1by1"))
        add_bullet(I18n.t("settings.about.ack_platforms"))
        add_bullet(I18n.t("settings.about.ack_ai"))

        layout.addSpacing(8)
        add_section(I18n.t("settings.about.section_features"))
        add_bullet(I18n.t("settings.about.feature_1"))
        add_bullet(I18n.t("settings.about.feature_2"))
        add_bullet(I18n.t("settings.about.feature_3"))
        add_bullet(I18n.t("settings.about.feature_4"))
        add_bullet(I18n.t("settings.about.feature_5"))

        layout.addSpacing(8)
        add_section(I18n.t("settings.about.section_easter_egg"))
        egg = QLabel(I18n.t("settings.about.easter_egg"))
        egg.setFont(body_font)
        egg.setWordWrap(True)
        egg.setContentsMargins(16, 2, 0, 2)
        layout.addWidget(egg)

        layout.addSpacing(8)
        add_section(I18n.t("settings.about.section_legal"))
        legal = QLabel(I18n.t("settings.about.legal"))
        legal.setFont(small_font)
        legal.setWordWrap(True)
        legal.setStyleSheet("color: #888;")
        legal.setContentsMargins(16, 2, 0, 2)
        layout.addWidget(legal)

        layout.addSpacing(4)
        add_section(I18n.t("settings.about.section_disclaimer"))
        disclaimer = QLabel(I18n.t("settings.about.disclaimer"))
        disclaimer.setFont(small_font)
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #888;")
        disclaimer.setContentsMargins(16, 2, 0, 2)
        layout.addWidget(disclaimer)

        layout.addStretch()
        return page


_THEME_COLOR_LABEL_KEYS = {
    "window_bg": "settings.theme_edit.color_window_bg",
    "surface": "settings.theme_edit.color_surface",
    "surface_alt": "settings.theme_edit.color_surface_alt",
    "border": "settings.theme_edit.color_border",
    "text_primary": "settings.theme_edit.color_text_primary",
    "text_secondary": "settings.theme_edit.color_text_secondary",
    "text_muted": "settings.theme_edit.color_text_muted",
    "accent": "settings.theme_edit.color_accent",
    "accent_hover": "settings.theme_edit.color_accent_hover",
    "accent_pressed": "settings.theme_edit.color_accent_pressed",
    "danger": "settings.theme_edit.color_danger",
    "warning": "settings.theme_edit.color_warning",
    "info": "settings.theme_edit.color_info",
    "success": "settings.theme_edit.color_success",
    "button_bg": "settings.theme_edit.color_button_bg",
    "button_bg_hover": "settings.theme_edit.color_button_bg_hover",
    "button_bg_pressed": "settings.theme_edit.color_button_bg_pressed",
    "button_text": "settings.theme_edit.color_button_text",
    "input_bg": "settings.theme_edit.color_input_bg",
    "input_border": "settings.theme_edit.color_input_border",
    "input_focus_border": "settings.theme_edit.color_input_focus_border",
    "slider_groove": "settings.theme_edit.color_slider_groove",
    "slider_handle": "settings.theme_edit.color_slider_handle",
    "table_row_alt": "settings.theme_edit.color_table_row_alt",
    "table_row_selected": "settings.theme_edit.color_table_row_selected",
    "table_row_selected_text": "settings.theme_edit.color_table_row_selected_text",
    "scrollbar_bg": "settings.theme_edit.color_scrollbar_bg",
    "scrollbar_handle": "settings.theme_edit.color_scrollbar_handle",
    "group_box_border": "settings.theme_edit.color_group_box_border",
    "tab_bg": "settings.theme_edit.color_tab_bg",
    "tab_active_bg": "settings.theme_edit.color_tab_active_bg",
    "lyric_active": "settings.theme_edit.color_lyric_active",
    "lyric_inactive": "settings.theme_edit.color_lyric_inactive",
    "vu_green": "settings.theme_edit.color_vu_green",
    "vu_yellow": "settings.theme_edit.color_vu_yellow",
    "vu_red": "settings.theme_edit.color_vu_red",
    "dir_color": "settings.theme_edit.color_dir_color",
    "cover_placeholder_bg": "settings.theme_edit.color_cover_placeholder_bg",
    "cover_placeholder_border": "settings.theme_edit.color_cover_placeholder_border",
}

def _theme_color_labels():
    return {k: I18n.t(v) for k, v in _THEME_COLOR_LABEL_KEYS.items()}

_THEME_COLOR_GROUP_KEYS = [
    ("settings.theme_edit.group_backgrounds", ["window_bg", "surface", "surface_alt", "cover_placeholder_bg"]),
    ("settings.theme_edit.group_borders", ["border", "group_box_border", "cover_placeholder_border", "input_border", "input_focus_border", "scrollbar_bg", "scrollbar_handle"]),
    ("settings.theme_edit.group_text", ["text_primary", "text_secondary", "text_muted", "button_text", "table_row_selected_text"]),
    ("settings.theme_edit.group_accent", ["accent", "accent_hover", "accent_pressed"]),
    ("settings.theme_edit.group_status", ["danger", "warning", "info", "success"]),
    ("settings.theme_edit.group_buttons", ["button_bg", "button_bg_hover", "button_bg_pressed"]),
    ("settings.theme_edit.group_inputs", ["input_bg", "slider_groove", "slider_handle"]),
    ("settings.theme_edit.group_table", ["table_row_alt", "table_row_selected"]),
    ("settings.theme_edit.group_tabs", ["tab_bg", "tab_active_bg"]),
    ("settings.theme_edit.group_lyrics", ["lyric_active", "lyric_inactive"]),
    ("settings.theme_edit.group_vu_meter", ["vu_green", "vu_yellow", "vu_red"]),
    ("settings.theme_edit.group_navigation", ["dir_color"]),
]

def _theme_color_groups():
    return [(I18n.t(k), v) for k, v in _THEME_COLOR_GROUP_KEYS]


class ThemeEditDialog(ThemedDialog):
    def __init__(self, theme_data: dict, parent=None):
        super().__init__(parent, title=I18n.tf("settings.theme_edit.dlg_title", name=theme_data.get('name', '')))
        self._theme_data = theme_data.copy()
        self._colors = theme_data.get("colors", {}).copy()
        self._color_buttons = {}
        self._init_ui()

    def _init_ui(self):
        self.setMinimumSize(520, 600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = self.body_layout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(I18n.t("settings.theme_edit.label_name"))
        name_lbl.setFixedWidth(90)
        self._txt_name = QLineEdit(self._theme_data.get("name", ""))
        name_row.addWidget(name_lbl)
        name_row.addWidget(self._txt_name, 1)
        main_layout.addLayout(name_row)

        is_dark_row = QHBoxLayout()
        is_dark_row.setSpacing(8)
        is_dark_lbl = QLabel(I18n.t("settings.theme_edit.label_dark_mode"))
        is_dark_lbl.setFixedWidth(90)
        self._chk_is_dark = QCheckBox()
        self._chk_is_dark.setChecked(self._theme_data.get("is_dark", True))
        is_dark_row.addWidget(is_dark_lbl)
        is_dark_row.addWidget(self._chk_is_dark)
        is_dark_row.addStretch()
        main_layout.addLayout(is_dark_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(8)

        for group_name, keys in _theme_color_groups():
            group = QGroupBox(group_name)
            group_layout = QFormLayout(group)
            group_layout.setLabelAlignment(Qt.AlignRight)
            group_layout.setSpacing(4)

            for key in keys:
                color_val = self._colors.get(key, "#333333")
                row_widget = self._create_color_row(key, color_val)
                label_text = _theme_color_labels().get(key, key)
                group_layout.addRow(label_text, row_widget)

            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def _create_color_row(self, key: str, color_val: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        btn = QPushButton()
        btn.setFixedSize(36, 22)
        display_color = color_val
        if color_val.startswith("rgba"):
            parts = color_val.replace("rgba", "").strip("()").split(",")
            if len(parts) >= 3:
                display_color = f"rgb({parts[0].strip()},{parts[1].strip()},{parts[2].strip()})"
        btn.setStyleSheet(f"background-color: {display_color}; border: 1px solid #555; border-radius: 3px;")
        btn.clicked.connect(lambda checked=False, k=key: self._pick_color(k))
        layout.addWidget(btn)

        txt = QLineEdit(color_val)
        txt.setFixedWidth(140)
        txt.textChanged.connect(lambda val, k=key: self._on_color_text_changed(k, val, btn))
        layout.addWidget(txt, 1)

        self._color_buttons[key] = (btn, txt)
        return row

    def _pick_color(self, key: str):
        current = self._colors.get(key, "#333333")
        if current.startswith("rgba"):
            parts = current.replace("rgba", "").strip("()").split(",")
            r = int(parts[0].strip()) if len(parts) > 0 else 0
            g = int(parts[1].strip()) if len(parts) > 1 else 0
            b = int(parts[2].strip()) if len(parts) > 2 else 0
            current = f"#{r:02x}{g:02x}{b:02x}"
        color = QColorDialog.getColor(QColor(current), self, "Select Color")
        if color.isValid():
            hex_val = color.name()
            self._colors[key] = hex_val
            btn, txt = self._color_buttons[key]
            btn.setStyleSheet(f"background-color: {hex_val}; border: 1px solid #555; border-radius: 3px;")
            txt.blockSignals(True)
            txt.setText(hex_val)
            txt.blockSignals(False)

    def _on_color_text_changed(self, key: str, value: str, btn: QPushButton):
        self._colors[key] = value
        display = value
        if value.startswith("rgba"):
            parts = value.replace("rgba", "").strip("()").split(",")
            if len(parts) >= 3:
                display = f"rgb({parts[0].strip()},{parts[1].strip()},{parts[2].strip()})"
        btn.setStyleSheet(f"background-color: {display}; border: 1px solid #555; border-radius: 3px;")

    def get_theme_data(self) -> dict:
        self._theme_data["name"] = self._txt_name.text().strip()
        self._theme_data["is_dark"] = self._chk_is_dark.isChecked()
        self._theme_data["colors"] = self._colors.copy()
        return self._theme_data


class WebDAVAccountDialog(ThemedDialog):
    def __init__(self, parent=None, account: dict = None):
        super().__init__(parent, title=I18n.t("settings.webdav.dlg_edit_title") if account else I18n.t("settings.webdav.dlg_add_title"))
        self.setMinimumWidth(420)
        self.setFont(QFont("Microsoft YaHei", 9))

        layout = self.body_layout()
        layout.setSpacing(8)

        form = QFormLayout()
        form.setSpacing(6)

        self._txt_name = QLineEdit()
        self._txt_name.setPlaceholderText(I18n.t("settings.webdav.ph_name"))
        form.addRow(I18n.t("settings.webdav.label_name"), self._txt_name)

        self._cmb_preset = QComboBox()
        self._cmb_preset.setEditable(False)
        self._cmb_preset.addItem(I18n.t("settings.webdav.preset_custom"), "")
        self._cmb_preset.addItem(I18n.t("settings.webdav.preset_jianguoyun"), "jianguoyun")
        self._cmb_preset.addItem(I18n.t("settings.webdav.preset_alist_dialog"), "alist")
        self._cmb_preset.addItem(I18n.t("settings.webdav.preset_synology"), "synology")
        self._cmb_preset.addItem(I18n.t("settings.webdav.preset_qnap"), "qnap")
        self._cmb_preset.addItem("Nextcloud", "nextcloud")
        self._cmb_preset.addItem("InfiniCLOUD", "infinicloud")
        self._cmb_preset.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow(I18n.t("settings.webdav.label_preset"), self._cmb_preset)

        self._txt_url = QLineEdit()
        self._txt_url.setPlaceholderText("https://your-server.com/dav/")
        form.addRow(I18n.t("settings.webdav.label_server"), self._txt_url)

        self._txt_username = QLineEdit()
        form.addRow(I18n.t("settings.webdav.label_username"), self._txt_username)

        self._txt_password = QLineEdit()
        self._txt_password.setEchoMode(QLineEdit.Password)
        form.addRow(I18n.t("settings.webdav.label_password"), self._txt_password)

        self._txt_root = QLineEdit()
        self._txt_root.setText("/")
        form.addRow(I18n.t("settings.webdav.label_root"), self._txt_root)

        self._chk_verify_ssl = QCheckBox(I18n.t("settings.webdav.verify_ssl"))
        self._chk_verify_ssl.setChecked(False)
        form.addRow("", self._chk_verify_ssl)

        self._spin_timeout = QSpinBox()
        self._spin_timeout.setRange(5, 120)
        self._spin_timeout.setValue(30)
        self._spin_timeout.setSuffix(I18n.t("settings.webdav.suffix_sec"))
        form.addRow(I18n.t("settings.webdav.label_timeout"), self._spin_timeout)

        layout.addLayout(form)

        btn_test = QPushButton(I18n.t("settings.webdav.btn_test_connection"))
        btn_test.setFixedHeight(28)
        btn_test.clicked.connect(self._on_test)
        layout.addWidget(btn_test)

        self._lbl_test_result = QLabel("")
        self._lbl_test_result.setWordWrap(True)
        layout.addWidget(self._lbl_test_result)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if account:
            self._txt_name.setText(account.get("name", ""))
            self._txt_url.setText(account.get("server_url", ""))
            self._txt_username.setText(account.get("username", ""))
            self._txt_password.setText(account.get("password", ""))
            self._txt_root.setText(account.get("root_path", "/"))
            self._chk_verify_ssl.setChecked(bool(account.get("verify_ssl", 0)))
            self._spin_timeout.setValue(account.get("timeout", 30))
            preset = account.get("preset", "")
            idx = self._cmb_preset.findData(preset)
            if idx >= 0:
                self._cmb_preset.setCurrentIndex(idx)

    def _on_preset_changed(self, index):
        presets = {
            "jianguoyun": ("https://dav.jianguoyun.com/dav/", "/", True),
            "alist": ("http://IP:5244/dav/", "/", False),
            "synology": ("http://IP:5005", "/", False),
            "qnap": ("http://IP:8080", "/", False),
            "nextcloud": (I18n.t("settings.webdav.preset_nextcloud_url"), "/", True),
            "infinicloud": ("https://tasgn.storage.infini-cloud.net/dav/", "/", True),
        }
        key = self._cmb_preset.currentData()
        if key in presets:
            url, root, ssl = presets[key]
            if not self._txt_url.text() or self._txt_url.text() == self._txt_url.placeholderText():
                self._txt_url.setText(url)
            if self._txt_root.text() == "/":
                self._txt_root.setText(root)
            self._chk_verify_ssl.setChecked(ssl)
        if key == "alist":
            self._lbl_test_result.setText(
                I18n.t("settings.webdav.alist_hint")
            )
            self._lbl_test_result.setStyleSheet("color: #6ab4ff;")

    def _on_test(self):
        url = self._txt_url.text().strip()
        if not url:
            self._lbl_test_result.setText(I18n.t("settings.webdav.msg_fill_server"))
            self._lbl_test_result.setStyleSheet("color: #e05050;")
            return
        from src.infrastructure.webdav_client import WebDAVClient
        url = WebDAVClient.normalize_url(url)
        self._txt_url.setText(url)
        ok, msg = WebDAVClient.test_connection(
            server_url=url,
            username=self._txt_username.text().strip(),
            password=self._txt_password.text(),
            timeout=self._spin_timeout.value(),
            verify_ssl=self._chk_verify_ssl.isChecked(),
        )
        if ok:
            self._lbl_test_result.setText(f"✓ {msg}")
            self._lbl_test_result.setStyleSheet("color: #32c864;")
        else:
            self._lbl_test_result.setText(f"✗ {msg}")
            self._lbl_test_result.setStyleSheet("color: #e05050;")

    def _on_accept(self):
        if not self._txt_name.text().strip():
            self._txt_name.setFocus()
            return
        url = self._txt_url.text().strip()
        if not url:
            self._txt_url.setFocus()
            return
        from src.infrastructure.webdav_client import WebDAVClient
        normalized = WebDAVClient.normalize_url(url)
        if not normalized.startswith(("http://", "https://")):
            self._lbl_test_result.setText(I18n.t("settings.webdav.msg_invalid_url"))
            self._lbl_test_result.setStyleSheet("color: #e05050;")
            self._txt_url.setFocus()
            return
        self._txt_url.setText(normalized)
        self.accept()

    def get_data(self) -> dict:
        from src.infrastructure.webdav_client import WebDAVClient
        return {
            "name": self._txt_name.text().strip(),
            "server_url": WebDAVClient.normalize_url(self._txt_url.text().strip()),
            "username": self._txt_username.text().strip(),
            "password": self._txt_password.text(),
            "root_path": self._txt_root.text().strip() or "/",
            "verify_ssl": self._chk_verify_ssl.isChecked(),
            "timeout": self._spin_timeout.value(),
            "preset": self._cmb_preset.currentData() or "",
        }
