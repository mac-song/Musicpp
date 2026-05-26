import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
    QFileDialog, QProgressBar, QComboBox,
    QAbstractItemView, QRadioButton, QButtonGroup, QWidget,
)
from PySide6.QtGui import QColor

from src.business.i18n_service import I18n
from src.presentation.themed_dialog import ThemedDialog, ThemedMessageBox
from src.business.playlist_import_service import PlaylistImportService
from src.core.online_music_service import OnlineMusicService
from src.infrastructure.playlist_parser import parse_playlist_with_meta
from src.utils.logger import setup_logger, log_msgbox

logger = setup_logger(__name__)

class PlaylistImportDialog(ThemedDialog):
    import_completed = Signal(str, int)
    _sig_progress = Signal(int, int, str)
    _sig_match_done = Signal(list)
    _sig_match_error = Signal(str)
    _sig_url_done = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, title=I18n.t("playlist.import.dlg_title"))
        self._import_svc = PlaylistImportService()
        self._online_svc = OnlineMusicService()
        self._parsed_songs = []
        self._matched_songs = []
        self._cancelled = False
        self._matching = False
        self._sig_progress.connect(self._on_match_progress)
        self._sig_match_done.connect(self._on_match_done)
        self._sig_match_error.connect(self._on_match_error)
        self._sig_url_done.connect(self._on_url_done)
        self._init_ui()

    def _init_ui(self):
        self.setMinimumSize(720, 520)
        self.resize(800, 600)

        layout = self.body_layout()
        layout.setSpacing(8)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self._file_input = QLineEdit()
        self._file_input.setReadOnly(True)
        self._file_input.setPlaceholderText(I18n.t("playlist.import.ph_file"))
        file_row.addWidget(self._file_input, 1)
        btn_browse = QPushButton(I18n.t("playlist.import.btn_browse"))
        btn_browse.clicked.connect(self._on_browse)
        file_row.addWidget(btn_browse)
        layout.addLayout(file_row)

        source_row = QHBoxLayout()
        source_row.setSpacing(6)
        source_row.addWidget(QLabel(I18n.t("playlist.import.label_match_source")))
        self._combo_source = QComboBox()
        self._combo_source.addItem(I18n.t("playlist.import.source_all"), "")
        plugins = self._import_svc.get_available_plugins()
        for pid, pname in plugins.items():
            self._combo_source.addItem(pname, pid)
        self._combo_source.setCurrentIndex(0)
        source_row.addWidget(self._combo_source, 1)
        layout.addLayout(source_row)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        self._lbl_count = QLabel(I18n.tf("playlist.import.label_parsed", count=0))
        self._lbl_matched = QLabel(I18n.tf("playlist.import.label_matched_count", count=0))
        self._lbl_unmatched = QLabel(I18n.tf("playlist.import.label_unmatched_count", count=0))
        info_row.addWidget(self._lbl_count)
        info_row.addWidget(self._lbl_matched)
        info_row.addWidget(self._lbl_unmatched)
        info_row.addStretch()
        layout.addLayout(info_row)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([I18n.t("playlist.import.col_title"), I18n.t("playlist.import.col_artist"), I18n.t("playlist.import.col_status"), I18n.t("playlist.import.col_action")])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        layout.addWidget(self._table, 1)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._btn_match = QPushButton(I18n.t("playlist.import.btn_start_match"))
        self._btn_match.setEnabled(False)
        self._btn_match.clicked.connect(self._on_start_match)
        btn_row.addWidget(self._btn_match)
        self._btn_cancel = QPushButton(I18n.t("playlist.import.btn_cancel_match"))
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel_match)
        btn_row.addWidget(self._btn_cancel)
        self._btn_import = QPushButton(I18n.t("playlist.import.btn_import_to"))
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(self._btn_import)
        self._btn_close = QPushButton(I18n.t("playlist.import.btn_close"))
        self._btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

    def _get_selected_plugin_id(self) -> str:
        data = self._combo_source.currentData()
        return data if data else ""

    def _on_browse(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("playlist.import.dlg_select_file"), "",
            "Playlist Files (*.m3u *.m3u8 *.json *.csv *.txt);;All Files (*)"
        )
        if not file_path:
            return

        self._file_input.setText(file_path)
        self._parsed_songs = parse_playlist_with_meta(file_path)
        self._matched_songs = list(self._parsed_songs)

        logger.info(f"Import: parsed {len(self._parsed_songs)} songs from {file_path}")
        for i, s in enumerate(self._parsed_songs[:5]):
            logger.info(f"  Song {i}: title={s.get('title', '')!r} artist={s.get('artist', '')!r}")
        if len(self._parsed_songs) > 5:
            logger.info(f"  ... and {len(self._parsed_songs) - 5} more")

        self._refresh_table()
        self._btn_match.setEnabled(len(self._parsed_songs) > 0)
        self._btn_import.setEnabled(False)

    def _refresh_table(self):
        self._table.setRowCount(0)
        matched_count = 0
        unmatched_count = 0

        for i, song in enumerate(self._matched_songs):
            row = self._table.rowCount()
            self._table.insertRow(row)

            title_item = QTableWidgetItem(song.get("title", ""))
            title_item.setData(Qt.UserRole, i)
            self._table.setItem(row, 0, title_item)

            self._table.setItem(row, 1, QTableWidgetItem(song.get("artist", "")))

            status = song.get("match_status", "unmatched")
            if status == "matched":
                matched_count += 1
                status_text = I18n.t("playlist.import.status_matched")
                status_color = QColor("#32c864")
            else:
                unmatched_count += 1
                status_text = I18n.t("playlist.import.status_not_matched")
                status_color = QColor("#e05050")

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(status_color)
            status_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2, status_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 0, 2, 0)
            action_layout.setSpacing(4)

            btn_rematch = QPushButton(I18n.t("playlist.import.btn_rematch"))
            btn_rematch.setFixedHeight(20)
            btn_rematch.setCursor(Qt.PointingHandCursor)
            btn_rematch.clicked.connect(lambda checked, idx=i: self._on_rematch(idx))
            action_layout.addWidget(btn_rematch)

            if status == "matched" and not song.get("_play_url"):
                btn_url = QPushButton(I18n.t("playlist.import.btn_get_url"))
                btn_url.setFixedHeight(20)
                btn_url.setCursor(Qt.PointingHandCursor)
                btn_url.clicked.connect(lambda checked, idx=i: self._on_get_url(idx))
                action_layout.addWidget(btn_url)

            self._table.setCellWidget(row, 3, action_widget)

        self._lbl_count.setText(I18n.tf("playlist.import.label_parsed", count=len(self._matched_songs)))
        self._lbl_matched.setText(I18n.tf("playlist.import.label_matched_count", count=matched_count))
        self._lbl_unmatched.setText(I18n.tf("playlist.import.label_unmatched_count", count=unmatched_count))

    def _on_start_match(self):
        if self._matching:
            return
        self._matching = True
        self._cancelled = False
        self._btn_match.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._btn_import.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setMaximum(len(self._matched_songs))
        self._progress.setValue(0)

        songs_snapshot = [dict(s) for s in self._matched_songs]
        plugin_id = self._get_selected_plugin_id()

        logger.info(f"Start match: {len(songs_snapshot)} songs, plugin_id={plugin_id!r}")
        self._status_label.setText(I18n.tf("playlist.import.msg_starting_match", count=len(songs_snapshot)))

        def _do_match():
            try:
                result = self._import_svc.match_songs_batch(
                    songs_snapshot,
                    plugin_id=plugin_id,
                    progress_callback=lambda c, t, n: self._sig_progress.emit(c, t, n),
                    cancel_check=lambda: self._cancelled,
                )
                self._matching = False
                self._sig_match_done.emit(result)
            except Exception as e:
                logger.error(f"Match thread crashed: {e}", exc_info=True)
                self._matching = False
                self._sig_match_error.emit(str(e))

        t = threading.Thread(target=_do_match, daemon=True)
        t.start()

    def _on_match_progress(self, current, total, song_name):
        if not self._cancelled:
            self._progress.setValue(current)
            self._status_label.setText(I18n.tf("playlist.import.msg_matching", current=current, total=total, name=song_name))

    def _on_match_done(self, result):
        self._matched_songs = result
        self._progress.setVisible(False)

        matched = sum(1 for s in result if s.get("match_status") == "matched")
        unmatched = len(result) - matched
        self._status_label.setText(I18n.tf("playlist.import.msg_match_complete", matched=matched, unmatched=unmatched))
        logger.info(f"Match done: {matched} matched, {unmatched} unmatched out of {len(result)}")

        self._btn_match.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._btn_import.setEnabled(matched > 0)
        self._refresh_table()

    def _on_match_error(self, error_msg):
        self._progress.setVisible(False)
        self._status_label.setText(I18n.tf("playlist.import.msg_match_error", error=error_msg))
        self._btn_match.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._refresh_table()

    def _on_cancel_match(self):
        self._cancelled = True
        self._status_label.setText(I18n.t("playlist.import.msg_cancelling"))

    def _on_rematch(self, idx):
        if idx < 0 or idx >= len(self._matched_songs):
            return
        song = self._matched_songs[idx]
        plugin_id = self._get_selected_plugin_id()
        self._status_label.setText(I18n.tf("playlist.import.msg_rematch_song", name=song.get('title', '')))

        logger.info(f"Rematch: title={song.get('title', '')!r} artist={song.get('artist', '')!r} plugin_id={plugin_id!r}")

        song_copy = dict(song)

        def _do():
            try:
                result = self._import_svc.rematch_song(song_copy, plugin_id=plugin_id)
                self._matched_songs[idx] = result
                self._sig_match_done.emit(self._matched_songs)
            except Exception as e:
                logger.error(f"Rematch failed: {e}", exc_info=True)
                self._sig_match_error.emit(str(e))

        t = threading.Thread(target=_do, daemon=True)
        t.start()

    def _on_get_url(self, idx):
        if idx < 0 or idx >= len(self._matched_songs):
            return
        song = self._matched_songs[idx]
        self._status_label.setText(I18n.tf("playlist.import.msg_getting_url", name=song.get('title', '')))

        def _do():
            try:
                self._import_svc.get_play_url(song)
                self._sig_url_done.emit()
            except Exception as e:
                logger.error(f"Get URL failed: {e}", exc_info=True)
                self._sig_url_done.emit()

        t = threading.Thread(target=_do, daemon=True)
        t.start()

    def _on_url_done(self):
        self._status_label.setText(I18n.t("playlist.import.msg_url_done"))
        self._refresh_table()

    def _on_table_context_menu(self, pos):
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction(I18n.t("playlist.import.action_rematch"), lambda: self._on_rematch(row))
        menu.addAction(I18n.t("playlist.import.action_get_url"), lambda: self._on_get_url(row))
        menu.addSeparator()
        menu.addAction(I18n.t("playlist.import.action_remove"), lambda: self._on_remove_song(row))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_remove_song(self, idx):
        if 0 <= idx < len(self._matched_songs):
            self._matched_songs.pop(idx)
            self._refresh_table()

    def _on_import(self):
        matched = [s for s in self._matched_songs if s.get("match_status") == "matched"]
        if not matched:
            log_msgbox("info", I18n.t("common.info"), I18n.t("playlist.import.msg_no_matched"))
            ThemedMessageBox.information(self, I18n.t("common.info"), I18n.t("playlist.import.msg_no_matched"))
            return

        names = self._online_svc.get_playlist_names()
        dialog = _ImportTargetDialog(names, self)
        if dialog.exec() != _ImportTargetDialog.Accepted:
            return

        target = dialog.get_target()
        if not target:
            return

        count = self._online_svc.import_songs_to_playlist(target, matched)

        self._status_label.setText(I18n.tf("playlist.import.msg_imported", count=count, target=target))
        self.import_completed.emit(target, count)

        def _fetch_urls():
            self._import_svc.get_play_urls_batch(matched, count=3)

        t = threading.Thread(target=_fetch_urls, daemon=True)
        t.start()

        log_msgbox("info", I18n.t("playlist.import.msg_import_done"), I18n.tf("playlist.import.msg_import_done_detail", count=count, target=target))
        ThemedMessageBox.information(
            self, I18n.t("playlist.import.msg_import_done"),
            I18n.tf("playlist.import.msg_import_done_detail", count=count, target=target)
        )


class _ImportTargetDialog(ThemedDialog):
    def __init__(self, existing_names: list, parent=None):
        super().__init__(parent, title=I18n.t("playlist.import.dlg_target_title"))
        self._target = ""
        self._existing_names = existing_names
        self.setMinimumWidth(360)

        layout = self.body_layout()

        self._rb_new = QRadioButton(I18n.t("playlist.import.rb_new_playlist"))
        self._rb_existing = QRadioButton(I18n.t("playlist.import.rb_existing"))
        self._rb_new.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self._rb_new)
        bg.addButton(self._rb_existing)
        layout.addWidget(self._rb_new)

        self._new_name_input = QLineEdit()
        self._new_name_input.setPlaceholderText(I18n.t("playlist.import.ph_new_name"))
        layout.addWidget(self._new_name_input)

        layout.addWidget(self._rb_existing)

        self._combo = QComboBox()
        self._combo.setEnabled(False)
        for name in existing_names:
            self._combo.addItem(name)
        layout.addWidget(self._combo)

        self._rb_new.toggled.connect(lambda checked: self._new_name_input.setEnabled(checked))
        self._rb_existing.toggled.connect(lambda checked: self._combo.setEnabled(checked))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton(I18n.t("common.ok"))
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton(I18n.t("common.cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _on_ok(self):
        if self._rb_new.isChecked():
            name = self._new_name_input.text().strip()
            if not name:
                log_msgbox("warning", I18n.t("common.warning"), I18n.t("playlist.import.msg_enter_name"))
                ThemedMessageBox.warning(self, I18n.t("common.warning"), I18n.t("playlist.import.msg_enter_name"))
                return
            if name in self._existing_names:
                log_msgbox("warning", I18n.t("common.warning"), I18n.t("playlist.import.msg_name_exists"))
                ThemedMessageBox.warning(self, I18n.t("common.warning"), I18n.t("playlist.import.msg_name_exists"))
                return
            self._online_svc = OnlineMusicService()
            self._online_svc.create_playlist(name)
            self._target = name
        else:
            if self._combo.count() == 0:
                log_msgbox("warning", I18n.t("common.warning"), I18n.t("playlist.import.msg_no_playlists_avail"))
                ThemedMessageBox.warning(self, I18n.t("common.warning"), I18n.t("playlist.import.msg_no_playlists_avail"))
                return
            self._target = self._combo.currentText()
        self.accept()

    def get_target(self) -> str:
        return self._target
