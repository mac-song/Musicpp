from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QMenu, QLabel, QAbstractItemView, QStackedWidget,
    QFileDialog, QComboBox, QTextEdit,
    QGroupBox
)
from PySide6.QtGui import QColor, QFont

from src.presentation.themed_dialog import ThemedMessageBox, ThemedInputDialog
from src.core.online_music_service import OnlineMusicService
from src.utils.logger import setup_logger, log_msgbox
from src.business.i18n_service import I18n
from src.utils.svg_icons import get_icon

logger = setup_logger(__name__)

FONT = "Microsoft YaHei"
FONT_SM = QFont(FONT, 9)
FONT_MD = QFont(FONT, 10)


class PluginTestWorker(QThread):
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, plugin, test_type, keyword):
        super().__init__()
        self.plugin = plugin
        self.test_type = test_type
        self.keyword = keyword

    def run(self):
        try:
            if self.test_type == "search":
                self.progress.emit(f"Searching: {self.keyword}")
                result = self.plugin.search(self.keyword, page=1, limit=3)
                self.finished.emit(f"Search result: {result}")
            elif self.test_type == "url":
                self.progress.emit(f"Getting URL: {self.keyword}")
                result = self.plugin.get_song_url(self.keyword, "320k")
                self.finished.emit(f"URL result: {result}")
            elif self.test_type == "lyric":
                self.progress.emit(f"Getting lyrics: {self.keyword}")
                result = self.plugin.get_lyric(self.keyword)
                self.finished.emit(f"Lyrics result: {result}")
        except Exception as e:
            self.error.emit(str(e))


class OnlineMusicPanel(QWidget):
    search_requested = Signal(str, int, int)
    download_requested = Signal(dict, str)
    play_requested = Signal(dict)
    play_online_list_requested = Signal(list, int)
    play_with_mode_requested = Signal(dict, list, str)
    plugin_install_requested = Signal(str)
    plugin_enable_requested = Signal(str, bool)
    plugin_delete_requested = Signal(str)
    _chapters_ready = Signal(list)
    _chapters_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._svc = OnlineMusicService()
        self._search_results = []
        self._search_keyword = ""
        self._current_playlist_name = None
        self._plugins_data = []
        self._plugin_instances = {}
        self._current_test_plugin = None
        self._test_worker = None
        self._chapters_ready.connect(self._on_chapters_ready)
        self._chapters_failed.connect(self._on_chapters_failed)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_main_area(), 1)

    def _build_main_area(self) -> QWidget:
        widget = QWidget()
        hbox = QHBoxLayout(widget)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)

        self._menu_list = QListWidget()
        self._menu_list.setFont(FONT_SM)
        self._menu_list.setFixedWidth(110)
        self._menu_list.setCurrentRow(0)
        self._menu_list.currentRowChanged.connect(self._on_menu_changed)
        for label in [I18n.t("online.tab.search"), I18n.t("online.tab.playlist"), I18n.t("online.tab.favorites"), I18n.t("online.tab.history"), I18n.t("online.tab.my_lists")]:
            item = QListWidgetItem(label)
            item.setTextAlignment(Qt.AlignCenter)
            self._menu_list.addItem(item)
        hbox.addWidget(self._menu_list)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_search_panel())
        self._stack.addWidget(self._build_playlist_panel())
        self._stack.addWidget(self._build_favorites_panel())
        self._stack.addWidget(self._build_history_panel())
        self._stack.addWidget(self._build_user_playlist_panel())
        hbox.addWidget(self._stack, 1)

        return widget

    def _on_menu_changed(self, row):
        self._stack.setCurrentIndex(row)
        if row == 2:
            self._refresh_favorites()
        elif row == 3:
            self._refresh_history()
        elif row == 4:
            self._refresh_user_playlist_list()

    def auto_select_page(self):
        songs = self._svc.get_playlist()
        if songs:
            self._menu_list.setCurrentRow(1)
        else:
            self._menu_list.setCurrentRow(0)

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _fmt_duration(d) -> str:
        if isinstance(d, (int, float)) and d > 0:
            return f"{int(d) // 60}:{int(d) % 60:02d}"
        return ""

    @staticmethod
    def _song_display(song: dict) -> str:
        title = song.get("title") or song.get("name", "")
        artist = song.get("artist") or song.get("singer", "")
        album = song.get("album") or song.get("albumName", "")
        parts = [title]
        if artist:
            parts.append(artist)
        if album and album != title:
            parts.append(album)
        return " - ".join(parts)

    def _get_selected_songs(self, table: QTableWidget) -> list:
        songs = []
        for row in table.selectionModel().selectedRows():
            item = table.item(row.row(), 0)
            if item:
                data = item.data(Qt.UserRole)
                if data:
                    songs.append(data)
        return songs

    def _get_song_from_row(self, table: QTableWidget, row: int) -> dict:
        item = table.item(row, 0)
        return item.data(Qt.UserRole) if item else {}

    def _build_song_table(self, cols: list, widths: list) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(cols))
        _col_i18n = {
            "Song": I18n.t("online.header.song"),
            "Duration": I18n.t("online.header.duration"),
            "Source": I18n.t("online.header.source"),
            "Lyric": I18n.t("online.header.lyric"),
            "Played": I18n.t("online.header.played"),
            "Added": I18n.t("online.header.added"),
        }
        table.setHorizontalHeaderLabels([_col_i18n.get(c, c) for c in cols])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(cols)):
            table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.setFont(FONT_SM)
        table.verticalHeader().setDefaultSectionSize(26)
        table.verticalHeader().hide()
        return table

    def _fill_song_table(self, table: QTableWidget, songs: list, cols: list):
        table.setRowCount(0)
        for song in songs:
            row = table.rowCount()
            table.insertRow(row)
            display = self._song_display(song)
            title_item = QTableWidgetItem(display)
            title_item.setData(Qt.UserRole, song)
            table.setItem(row, 0, title_item)
            col_idx = 1
            if "Duration" in cols:
                table.setItem(row, col_idx, QTableWidgetItem(self._fmt_duration(song.get("duration", 0))))
                col_idx += 1
            if "Source" in cols:
                table.setItem(row, col_idx, QTableWidgetItem(song.get("source") or song.get("pluginId", "")))
                col_idx += 1
            if "Lyric" in cols:
                has_lyric = self._check_lyric_status(song)
                lyric_item = QTableWidgetItem("✓" if has_lyric else "✗")
                lyric_item.setTextAlignment(Qt.AlignCenter)
                from src.infrastructure.theme_engine import ThemeEngine
                _tc = ThemeEngine().get_current_colors()
                if has_lyric:
                    lyric_item.setForeground(QColor(_tc.get("success", "#32c864")))
                else:
                    lyric_item.setForeground(QColor(_tc.get("text_muted", "#666680")))
                table.setItem(row, col_idx, lyric_item)
                col_idx += 1
            if "Played" in cols:
                table.setItem(row, col_idx, QTableWidgetItem(song.get("play_time", "")))
                col_idx += 1
            if "Added" in cols:
                table.setItem(row, col_idx, QTableWidgetItem(song.get("add_time", "")))
                col_idx += 1

    def _check_lyric_status(self, song: dict) -> bool:
        from src.business.lyric_manager import LyricManager
        lm = LyricManager()
        title = song.get("title", "")
        artist = song.get("artist", "")
        if not title:
            return False
        return lm.has_lyric_in_db(title, artist)

    def _add_to_playlist_action(self, songs: list):
        count = self._svc.add_songs_to_playlist(songs)
        self._refresh_playlist()
        self._menu_list.setCurrentRow(1)
        return count

    def _expand_bilibili_chapters(self, song: dict):
        from src.plugins.plugin_manager import PluginManager
        pm = PluginManager()
        plugin = pm.get_plugin("bilibili")
        if not plugin:
            return
        import threading
        bvid = song.get("id", "")
        cover = song.get("cover", "")

        def _do_expand():
            try:
                chapters = plugin.get_chapters(bvid)
                if not chapters:
                    self._chapters_failed.emit(
                        I18n.t("online.msg.no_chapters")
                    )
                    return

                chapter_songs = []
                for ch in chapters:
                    ch_bvid = ch.get("bvid", bvid)
                    cs = {
                        "id": f"{bvid}_p{ch['index']}",
                        "pluginId": "bilibili",
                        "source": "bilibili",
                        "title": ch["title"],
                        "artist": ch.get("artist", ""),
                        "album": ch.get("album", ""),
                        "duration": ch.get("duration", 0),
                        "cover": cover,
                        "bvid": ch_bvid,
                        "cid": ch.get("cid", ""),
                        "chapter_index": ch["index"],
                        "is_chapter": True,
                    }
                    chapter_songs.append(cs)

                if chapter_songs:
                    first = chapter_songs[0]
                    url_info = plugin.get_chapter_url(bvid, first.get("cid", ""), 0)
                    if isinstance(url_info, dict):
                        first["_play_url"] = url_info.get("url", "")
                        first["_is_local"] = url_info.get("is_local", False)

                self._chapters_ready.emit(chapter_songs)
            except Exception as e:
                from src.utils.logger import setup_logger
                setup_logger(__name__).warning(f"Expand chapters failed: {e}")
                self._chapters_failed.emit(str(e))

        t = threading.Thread(target=_do_expand, daemon=True)
        t.start()

    def _on_chapters_ready(self, chapter_songs: list):
        self._svc.add_songs_to_playlist(chapter_songs)
        self._refresh_playlist()
        self._menu_list.setCurrentRow(1)

    def _match_lyric_for_song(self, song: dict):
        from src.presentation.lyric_select_dialog import LyricSelectDialog
        from src.business.lyric_manager import LyricManager
        from PySide6.QtWidgets import QApplication

        title = song.get("title", "")
        artist = song.get("artist", "")
        album = song.get("album", "")
        duration = song.get("duration", 0)

        if not title:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            lm = LyricManager()
            candidates = lm.search_lyric_candidates(title, artist, album, duration)
        except Exception as e:
            candidates = []
        QApplication.restoreOverrideCursor()

        if not candidates:
            log_msgbox("info", I18n.t("online.msg.lyric_match_title"), I18n.tf("online.msg.lyric_not_found", title=title, artist=artist))
            ThemedMessageBox.information(self, I18n.t("online.msg.lyric_match_title"), I18n.tf("online.msg.lyric_not_found", title=title, artist=artist))
            return

        dialog = LyricSelectDialog(f"{title} - {artist}", candidates, self)
        if dialog.exec() == LyricSelectDialog.Accepted:
            selected = dialog.get_selected()
            if selected:
                lm = LyricManager()
                lm.save_lyric_to_db(
                    selected["content"], title, artist, album, duration,
                    selected.get("source", "manual"), selected.get("translate", "")
                )
                self._refresh_current_table()

    def _on_chapters_failed(self, msg: str):
        logger.warning(f"Chapters expand failed: {msg}")

    def _add_to_favorites_action(self, songs: list):
        count = 0
        for s in songs:
            if self._svc.add_to_favorites(s):
                count += 1
        return count

    def _add_to_user_playlist_action(self, songs: list):
        names = self._svc.get_playlist_names()
        if not names:
            log_msgbox("info", I18n.t("online.dialog.add_to_list"), I18n.t("online.msg.no_playlists"))
            ThemedMessageBox.information(self, I18n.t("online.dialog.add_to_list"), I18n.t("online.msg.no_playlists"))
            return
        name, ok = ThemedInputDialog.getItem(self, I18n.t("online.dialog.add_to_list"), I18n.t("online.dialog.select_list"), names, 0, False)
        if ok and name:
            count = 0
            for s in songs:
                if self._svc.add_to_user_playlist(name, s):
                    count += 1
            if self._current_playlist_name == name:
                self._refresh_user_playlist_detail()

    def _show_play_mode_dialog(self, song: dict, all_songs: list):
        from src.presentation.themed_dialog import ThemedDialog
        from PySide6.QtWidgets import QRadioButton, QDialogButtonBox
        dialog = ThemedDialog(self, title=I18n.t("online.dialog.play_mode"), width=360)

        title = song.get("title") or song.get("name", "")
        artist = song.get("artist") or song.get("singer", "")
        label = QLabel(f"🎵 {title}" + (f" — {artist}" if artist else ""))
        label.setWordWrap(True)
        dialog.body_layout().addWidget(label)
        dialog.body_layout().addSpacing(8)

        modes = [
            ("replace", I18n.t("online.mode.replace")),
            ("prepend", I18n.t("online.mode.prepend")),
            ("append", I18n.t("online.mode.append")),
            ("insert_next", I18n.t("online.mode.insert_next")),
            ("play_now", I18n.t("online.mode.play_now")),
        ]
        radio_buttons = []
        for i, (mode_id, text) in enumerate(modes):
            rb = QRadioButton(text)
            rb.setFont(FONT_SM)
            if i == 0:
                rb.setChecked(True)
            dialog.body_layout().addWidget(rb)
            radio_buttons.append((rb, mode_id))

        dialog.body_layout().addSpacing(8)
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.setFont(FONT_SM)
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        dialog.body_layout().addWidget(btn_box)

        if dialog.exec() == ThemedDialog.Accepted:
            selected_mode = "replace"
            for rb, mode_id in radio_buttons:
                if rb.isChecked():
                    selected_mode = mode_id
                    break
            self.play_with_mode_requested.emit(song, all_songs, selected_mode)

    # ========================================================= SEARCH PANEL
    def _build_search_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        search_bar = QHBoxLayout()
        search_bar.setSpacing(6)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(I18n.t("online.search.placeholder"))
        self._search_input.setFont(FONT_MD)
        self._search_input.returnPressed.connect(self._on_search)
        search_bar.addWidget(self._search_input, 1)
        self._btn_search = QPushButton()
        self._btn_search.setIcon(get_icon("search", "#ccc", 14))
        self._btn_search.setToolTip(I18n.t("online.search.btn"))
        self._btn_search.setFixedSize(28, 28)
        self._btn_search.clicked.connect(self._on_search)
        search_bar.addWidget(self._btn_search)
        vbox.addLayout(search_bar)

        self._search_table = self._build_song_table(
            ["Song", "Duration", "Source", "Lyric"], [0, 60, 80, 40]
        )
        self._search_table.doubleClicked.connect(self._on_search_double_click)
        self._search_table.customContextMenuRequested.connect(self._on_search_context_menu)
        vbox.addWidget(self._search_table, 1)

        return widget

    def _on_search(self):
        keyword = self._search_input.text().strip()
        if keyword:
            self._search_keyword = keyword
            self.search_requested.emit(keyword, 1, 50)

    def _on_search_double_click(self, index):
        song = self._get_song_from_row(self._search_table, index.row())
        if song:
            self._show_play_mode_dialog(song, self._search_results)

    def _on_search_context_menu(self, pos):
        row = self._search_table.rowAt(pos.y())
        if row < 0:
            return
        if not self._search_table.selectionModel().isRowSelected(row, self._search_table.rootIndex()):
            self._search_table.selectRow(row)
        songs = self._get_selected_songs(self._search_table)
        if not songs:
            return
        song = songs[0]

        menu = QMenu(self)
        menu.setFont(FONT_SM)
        play_action = menu.addAction(I18n.t("online.action.play"))
        add_playlist_action = menu.addAction(I18n.t("online.action.add_to_playlist"))
        add_fav_action = menu.addAction(I18n.t("online.action.add_to_favorites"))
        add_user_pl_action = menu.addAction(I18n.t("online.action.add_to_list"))
        menu.addSeparator()
        download_action = menu.addAction(I18n.t("online.action.download"))
        match_lyric_action = menu.addAction(I18n.t("online.action.match_lyric"))
        expand_action = None
        if song.get("pluginId") == "bilibili":
            expand_action = menu.addAction(I18n.t("online.action.expand_chapters"))

        action = menu.exec(self._search_table.viewport().mapToGlobal(pos))
        if action == play_action:
            self._show_play_mode_dialog(song, self._search_results)
        elif action == add_playlist_action:
            self._add_to_playlist_action(songs)
        elif action == add_fav_action:
            self._add_to_favorites_action(songs)
        elif action == add_user_pl_action:
            self._add_to_user_playlist_action(songs)
        elif action == download_action:
            quality = song.get("quality", "")
            self.download_requested.emit(song, quality)
        elif action == match_lyric_action:
            self._match_lyric_for_song(song)
        elif action == expand_action:
            self._expand_bilibili_chapters(song)

    # ======================================================= PLAYLIST PANEL
    def _build_playlist_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addStretch()
        btn_clear = QPushButton()
        btn_clear.setIcon(get_icon("trash-2", "#ccc", 14))
        btn_clear.setToolTip("Clear")
        btn_clear.setFixedSize(28, 28)
        btn_clear.clicked.connect(self._on_clear_playlist)
        bar.addWidget(btn_clear)
        btn_remove = QPushButton()
        btn_remove.setIcon(get_icon("minus", "#ccc", 14))
        btn_remove.setToolTip("Remove")
        btn_remove.setFixedSize(28, 28)
        btn_remove.clicked.connect(self._on_remove_from_playlist)
        bar.addWidget(btn_remove)
        vbox.addLayout(bar)

        self._playlist_table = self._build_song_table(
            ["Song", "Duration", "Source", "Lyric"], [0, 60, 80, 40]
        )
        self._playlist_table.doubleClicked.connect(self._on_playlist_double_click)
        self._playlist_table.customContextMenuRequested.connect(self._on_playlist_context_menu)
        vbox.addWidget(self._playlist_table, 1)

        self._refresh_playlist()
        return widget

    def _refresh_playlist(self):
        songs = self._svc.get_playlist()
        self._fill_song_table(self._playlist_table, songs, ["Song", "Duration", "Source", "Lyric"])

    def _refresh_current_table(self):
        idx = self._menu_list.currentRow()
        if idx == 1:
            self._refresh_playlist()
        elif idx == 2:
            self._refresh_favorites()
        elif idx == 3:
            self._refresh_history()
        elif idx >= 4:
            self._refresh_user_playlist_detail()

    def _on_playlist_double_click(self, index):
        song = self._get_song_from_row(self._playlist_table, index.row())
        if song:
            self.play_online_list_requested.emit(self._svc.get_playlist(), index.row())

    def _on_playlist_context_menu(self, pos):
        row = self._playlist_table.rowAt(pos.y())
        if row < 0:
            return
        if not self._playlist_table.selectionModel().isRowSelected(row, self._playlist_table.rootIndex()):
            self._playlist_table.selectRow(row)
        songs = self._get_selected_songs(self._playlist_table)
        song = songs[0] if songs else {}

        menu = QMenu(self)
        menu.setFont(FONT_SM)
        play_action = menu.addAction(I18n.t("online.action.play"))
        add_fav_action = menu.addAction(I18n.t("online.action.add_to_favorites"))
        add_user_pl_action = menu.addAction(I18n.t("online.action.add_to_list"))
        menu.addSeparator()
        match_lyric_action = menu.addAction(I18n.t("online.action.match_lyric"))
        menu.addSeparator()
        remove_action = menu.addAction(I18n.t("online.action.remove_from_list"))

        action = menu.exec(self._playlist_table.viewport().mapToGlobal(pos))
        if action == play_action:
            self.play_online_list_requested.emit(self._svc.get_playlist(), row)
        elif action == add_fav_action:
            self._add_to_favorites_action(songs)
        elif action == add_user_pl_action:
            self._add_to_user_playlist_action(songs)
        elif action == match_lyric_action:
            self._match_lyric_for_song(song)
        elif action == remove_action:
            indices = [r.row() for r in self._playlist_table.selectionModel().selectedRows()]
            self._svc.remove_from_playlist(indices)
            self._refresh_playlist()

    def _on_clear_playlist(self):
        self._svc.clear_playlist()
        self._refresh_playlist()

    def _on_remove_from_playlist(self):
        indices = [r.row() for r in self._playlist_table.selectionModel().selectedRows()]
        if indices:
            self._svc.remove_from_playlist(indices)
            self._refresh_playlist()

    # ===================================================== FAVORITES PANEL
    def _build_favorites_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addStretch()
        btn_play_all = QPushButton()
        btn_play_all.setIcon(get_icon("play-circle", "#ccc", 14))
        btn_play_all.setToolTip("Play All")
        btn_play_all.setFixedSize(28, 28)
        btn_play_all.clicked.connect(self._on_play_all_favorites)
        bar.addWidget(btn_play_all)
        vbox.addLayout(bar)

        self._fav_table = self._build_song_table(
            ["Song", "Duration", "Source", "Lyric"], [0, 60, 80, 40]
        )
        self._fav_table.doubleClicked.connect(self._on_fav_double_click)
        self._fav_table.customContextMenuRequested.connect(self._on_fav_context_menu)
        vbox.addWidget(self._fav_table, 1)

        return widget

    def _refresh_favorites(self):
        songs = self._svc.get_favorites()
        self._fill_song_table(self._fav_table, songs, ["Song", "Duration", "Source", "Lyric"])

    def _on_fav_double_click(self, index):
        song = self._get_song_from_row(self._fav_table, index.row())
        if song:
            self.play_requested.emit(song)

    def _on_fav_context_menu(self, pos):
        row = self._fav_table.rowAt(pos.y())
        if row < 0:
            return
        if not self._fav_table.selectionModel().isRowSelected(row, self._fav_table.rootIndex()):
            self._fav_table.selectRow(row)
        songs = self._get_selected_songs(self._fav_table)
        song = songs[0] if songs else {}

        menu = QMenu(self)
        menu.setFont(FONT_SM)
        play_next_action = menu.addAction(I18n.t("online.action.play_next"))
        add_user_pl_action = menu.addAction(I18n.t("online.action.add_to_list"))
        menu.addSeparator()
        match_lyric_action = menu.addAction(I18n.t("online.action.match_lyric"))
        menu.addSeparator()
        remove_action = menu.addAction(I18n.t("online.action.remove_from_favorites"))

        action = menu.exec(self._fav_table.viewport().mapToGlobal(pos))
        if action == play_next_action:
            self.play_requested.emit(song)
        elif action == add_user_pl_action:
            self._add_to_user_playlist_action(songs)
        elif action == match_lyric_action:
            self._match_lyric_for_song(song)
        elif action == remove_action:
            indices = [r.row() for r in self._fav_table.selectionModel().selectedRows()]
            self._svc.remove_from_favorites(indices)
            self._refresh_favorites()

    def _on_play_all_favorites(self):
        songs = self._svc.get_favorites()
        if songs:
            self._svc.clear_playlist()
            self._svc.add_songs_to_playlist(songs)
            self._refresh_playlist()
            self.play_online_list_requested.emit(self._svc.get_playlist(), 0)

    # ======================================================= HISTORY PANEL
    def _build_history_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addStretch()
        btn_play_all = QPushButton()
        btn_play_all.setIcon(get_icon("play-circle", "#ccc", 14))
        btn_play_all.setToolTip("Play All")
        btn_play_all.setFixedSize(28, 28)
        btn_play_all.clicked.connect(self._on_play_all_history)
        bar.addWidget(btn_play_all)
        btn_export = QPushButton()
        btn_export.setIcon(get_icon("download", "#ccc", 14))
        btn_export.setToolTip("Export")
        btn_export.setFixedSize(28, 28)
        btn_export.clicked.connect(self._on_export_history)
        bar.addWidget(btn_export)
        btn_clear = QPushButton()
        btn_clear.setIcon(get_icon("trash-2", "#ccc", 14))
        btn_clear.setToolTip("Clear")
        btn_clear.setFixedSize(28, 28)
        btn_clear.clicked.connect(self._on_clear_history)
        bar.addWidget(btn_clear)
        vbox.addLayout(bar)

        self._history_table = self._build_song_table(
            ["Song", "Duration", "Source", "Lyric", "Played"], [0, 60, 80, 40, 130]
        )
        self._history_table.doubleClicked.connect(self._on_history_double_click)
        self._history_table.customContextMenuRequested.connect(self._on_history_context_menu)
        vbox.addWidget(self._history_table, 1)

        return widget

    def _refresh_history(self):
        songs = self._svc.get_history()
        self._fill_song_table(self._history_table, songs, ["Song", "Duration", "Source", "Lyric", "Played"])

    def _on_history_double_click(self, index):
        song = self._get_song_from_row(self._history_table, index.row())
        if song:
            self.play_requested.emit(song)

    def _on_history_context_menu(self, pos):
        row = self._history_table.rowAt(pos.y())
        if row < 0:
            return
        if not self._history_table.selectionModel().isRowSelected(row, self._history_table.rootIndex()):
            self._history_table.selectRow(row)
        songs = self._get_selected_songs(self._history_table)
        song = songs[0] if songs else {}

        menu = QMenu(self)
        menu.setFont(FONT_SM)
        add_fav_action = menu.addAction(I18n.t("online.action.add_to_favorites"))
        add_user_pl_action = menu.addAction(I18n.t("online.action.add_to_list"))
        add_playlist_action = menu.addAction(I18n.t("online.action.add_to_playlist"))
        menu.addSeparator()
        match_lyric_action = menu.addAction(I18n.t("online.action.match_lyric"))

        action = menu.exec(self._history_table.viewport().mapToGlobal(pos))
        if action == add_fav_action:
            self._add_to_favorites_action(songs)
        elif action == add_user_pl_action:
            self._add_to_user_playlist_action(songs)
        elif action == add_playlist_action:
            self._add_to_playlist_action(songs)
        elif action == match_lyric_action:
            self._match_lyric_for_song(song)

    def _on_play_all_history(self):
        songs = self._svc.get_history()
        if songs:
            self._svc.clear_playlist()
            self._svc.add_songs_to_playlist(songs)
            self._refresh_playlist()
            self.play_online_list_requested.emit(self._svc.get_playlist(), 0)

    def _on_export_history(self):
        text = self._svc.export_history()
        if not text:
            log_msgbox("info", "Info", "No history yet")
            ThemedMessageBox.information(self, "Info", "No history yet")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export History", "play_history.txt", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def _on_clear_history(self):
        self._svc.clear_history()
        self._refresh_history()

    # ================================================= USER PLAYLIST PANEL
    def _build_user_playlist_panel(self) -> QWidget:
        widget = QWidget()
        hbox = QHBoxLayout(widget)
        hbox.setContentsMargins(4, 4, 4, 4)
        hbox.setSpacing(4)

        left = QWidget()
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        btn_create = QPushButton()
        btn_create.setIcon(get_icon("folder-plus", "#ccc", 14))
        btn_create.setToolTip("New Playlist")
        btn_create.setFixedSize(28, 28)
        btn_create.clicked.connect(self._on_create_playlist)
        bar.addWidget(btn_create)
        btn_delete = QPushButton()
        btn_delete.setIcon(get_icon("folder-minus", "#ccc", 14))
        btn_delete.setToolTip("Delete Playlist")
        btn_delete.setFixedSize(28, 28)
        btn_delete.clicked.connect(self._on_delete_playlist)
        bar.addWidget(btn_delete)
        btn_import = QPushButton()
        btn_import.setIcon(get_icon("download", "#ccc", 14))
        btn_import.setToolTip("Import Playlist")
        btn_import.setFixedSize(28, 28)
        btn_import.clicked.connect(self._on_import_playlist)
        bar.addWidget(btn_import)
        btn_export = QPushButton()
        btn_export.setIcon(get_icon("upload", "#ccc", 14))
        btn_export.setToolTip("Export Playlist")
        btn_export.setFixedSize(28, 28)
        btn_export.clicked.connect(self._on_export_playlist)
        bar.addWidget(btn_export)
        left_vbox.addLayout(bar)

        self._user_pl_list = QListWidget()
        self._user_pl_list.setFont(FONT_SM)
        self._user_pl_list.setFixedWidth(120)
        self._user_pl_list.currentRowChanged.connect(self._on_user_pl_selected)
        self._user_pl_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._user_pl_list.customContextMenuRequested.connect(self._on_user_pl_list_context_menu)
        left_vbox.addWidget(self._user_pl_list, 1)
        hbox.addWidget(left)

        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(4)

        self._user_pl_bar = QHBoxLayout()
        self._user_pl_bar.setSpacing(6)
        self._user_pl_bar.addStretch()
        self._btn_play_all_pl = QPushButton()
        self._btn_play_all_pl.setIcon(get_icon("play-circle", "#ccc", 14))
        self._btn_play_all_pl.setToolTip("Play All")
        self._btn_play_all_pl.setFixedSize(28, 28)
        self._btn_play_all_pl.clicked.connect(self._on_play_all_user_pl)
        self._user_pl_bar.addWidget(self._btn_play_all_pl)
        right_vbox.addLayout(self._user_pl_bar)

        self._user_pl_table = self._build_song_table(
            ["Song", "Duration", "Source", "Lyric", "Added"], [0, 60, 80, 40, 130]
        )
        self._user_pl_table.doubleClicked.connect(self._on_user_pl_double_click)
        self._user_pl_table.customContextMenuRequested.connect(self._on_user_pl_context_menu)
        right_vbox.addWidget(self._user_pl_table, 1)
        hbox.addWidget(right, 1)

        return widget

    def _refresh_user_playlist_list(self):
        self._user_pl_list.clear()
        names = self._svc.get_playlist_names()
        for name in names:
            self._user_pl_list.addItem(name)
        if names:
            self._user_pl_list.setCurrentRow(0)
        else:
            self._current_playlist_name = None
            self._user_pl_table.setRowCount(0)

    def _on_user_pl_selected(self, row):
        if row < 0:
            return
        item = self._user_pl_list.item(row)
        if item:
            self._current_playlist_name = item.text()
            self._refresh_user_playlist_detail()

    def _refresh_user_playlist_detail(self):
        if not self._current_playlist_name:
            self._user_pl_table.setRowCount(0)
            return
        songs = self._svc.get_playlist_songs(self._current_playlist_name)
        self._fill_song_table(self._user_pl_table, songs, ["Song", "Duration", "Source", "Lyric", "Added"])

    def _on_user_pl_double_click(self, index):
        song = self._get_song_from_row(self._user_pl_table, index.row())
        if song:
            self.play_requested.emit(song)

    def _on_user_pl_context_menu(self, pos):
        row = self._user_pl_table.rowAt(pos.y())
        if row < 0:
            return
        if not self._user_pl_table.selectionModel().isRowSelected(row, self._user_pl_table.rootIndex()):
            self._user_pl_table.selectRow(row)
        songs = self._get_selected_songs(self._user_pl_table)
        song = songs[0] if songs else {}

        menu = QMenu(self)
        menu.setFont(FONT_SM)
        play_action = menu.addAction(I18n.t("online.action.play"))
        add_fav_action = menu.addAction(I18n.t("online.action.add_to_favorites"))
        add_playlist_action = menu.addAction(I18n.t("online.action.add_to_playlist"))
        menu.addSeparator()
        match_lyric_action = menu.addAction(I18n.t("online.action.match_lyric"))
        menu.addSeparator()
        rematch_action = menu.addAction(I18n.t("online.action.rematch"))
        get_url_action = menu.addAction(I18n.t("online.action.get_url"))
        menu.addSeparator()
        remove_action = menu.addAction(I18n.t("online.action.remove_song"))

        action = menu.exec(self._user_pl_table.viewport().mapToGlobal(pos))
        if action == play_action:
            self.play_requested.emit(song)
        elif action == add_fav_action:
            self._add_to_favorites_action(songs)
        elif action == add_playlist_action:
            self._add_to_playlist_action(songs)
        elif action == match_lyric_action:
            self._match_lyric_for_song(song)
        elif action == rematch_action:
            self._on_rematch_user_pl_song(row, song)
        elif action == get_url_action:
            self._on_get_url_user_pl_song(row, song)
        elif action == remove_action:
            indices = [r.row() for r in self._user_pl_table.selectionModel().selectedRows()]
            if self._current_playlist_name:
                self._svc.remove_from_user_playlist(self._current_playlist_name, indices)
                self._refresh_user_playlist_detail()

    def _on_user_pl_list_context_menu(self, pos):
        item = self._user_pl_list.itemAt(pos)
        if not item:
            return
        name = item.text()

        menu = QMenu(self)
        menu.setFont(FONT_SM)
        rename_action = menu.addAction(I18n.t("online.menu.rename"))
        delete_action = menu.addAction(I18n.t("online.menu.delete_playlist"))
        menu.addSeparator()
        import_action = menu.addAction(I18n.t("online.menu.import_songs"))
        export_action = menu.addAction(I18n.t("online.menu.export_playlist"))

        action = menu.exec(self._user_pl_list.viewport().mapToGlobal(pos))
        if action == rename_action:
            self._on_rename_playlist(name)
        elif action == delete_action:
            self._on_delete_playlist()
        elif action == import_action:
            self._on_import_playlist()
        elif action == export_action:
            self._on_export_playlist()

    def _on_rename_playlist(self, old_name: str):
        new_name, ok = ThemedInputDialog.getText(
            self, I18n.t("online.dlg.rename_playlist"), I18n.t("online.dlg.new_name"), text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if self._svc.rename_playlist(old_name, new_name):
            self._current_playlist_name = new_name
            self._refresh_user_playlist_list()
            names = self._svc.get_playlist_names()
            if new_name in names:
                self._user_pl_list.setCurrentRow(names.index(new_name))
        else:
            log_msgbox("warning", I18n.t("online.msg.rename_fail_title"), I18n.t("online.msg.rename_fail_body"))
            ThemedMessageBox.warning(self, I18n.t("online.msg.rename_fail_title"), I18n.t("online.msg.rename_fail_body"))

    def _on_create_playlist(self):
        name, ok = ThemedInputDialog.getText(self, "New Playlist", "Playlist name:")
        if ok and name.strip():
            if self._svc.create_playlist(name.strip()):
                self._refresh_user_playlist_list()
            else:
                log_msgbox("warning", "Info", "Playlist already exists")
                ThemedMessageBox.warning(self, "Info", "Playlist already exists")

    def _on_delete_playlist(self):
        item = self._user_pl_list.currentItem()
        if not item:
            return
        name = item.text()
        log_msgbox("question", I18n.t("common.confirm"), f'Delete playlist "{name}"?')
        ret = ThemedMessageBox.question(self, I18n.t("common.confirm"), f'Delete playlist "{name}"?', buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))], default_button="no")
        if ret == 1:
            self._svc.delete_playlist(name)
            self._current_playlist_name = None
            self._refresh_user_playlist_list()

    def _on_play_all_user_pl(self):
        if not self._current_playlist_name:
            return
        songs = self._svc.get_playlist_songs(self._current_playlist_name)
        if songs:
            self._svc.clear_playlist()
            self._svc.add_songs_to_playlist(songs)
            self._refresh_playlist()
            self.play_online_list_requested.emit(self._svc.get_playlist(), 0)

    # ====================================================== PLUGIN PANEL
    def _build_plugin_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.addStretch()
        self._btn_install_plugin = QPushButton()
        self._btn_install_plugin.setIcon(get_icon("file-plus", "#ccc", 14))
        self._btn_install_plugin.setToolTip("Install Plugin")
        self._btn_install_plugin.setFixedSize(28, 28)
        self._btn_install_plugin.clicked.connect(self._on_install_plugin)
        toolbar.addWidget(self._btn_install_plugin)
        self._btn_refresh_plugins = QPushButton()
        self._btn_refresh_plugins.setIcon(get_icon("refresh-cw", "#ccc", 14))
        self._btn_refresh_plugins.setToolTip("Refresh")
        self._btn_refresh_plugins.setFixedSize(28, 28)
        self._btn_refresh_plugins.clicked.connect(self._on_refresh_plugins)
        toolbar.addWidget(self._btn_refresh_plugins)
        vbox.addLayout(toolbar)

        self._plugin_table = QTableWidget()
        self._plugin_table.setColumnCount(7)
        self._plugin_table.setHorizontalHeaderLabels([I18n.t("online.header.name"), I18n.t("online.header.search"), I18n.t("online.header.play"), I18n.t("online.header.download"), I18n.t("online.header.url"), I18n.t("online.header.status"), I18n.t("online.header.actions")])
        self._plugin_table.verticalHeader().setVisible(False)
        header = self._plugin_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 7):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._plugin_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._plugin_table.setSelectionMode(QTableWidget.SingleSelection)
        self._plugin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._plugin_table.setFont(FONT_SM)
        self._plugin_table.verticalHeader().setDefaultSectionSize(26)
        self._plugin_table.setMaximumHeight(26 * 5 + self._plugin_table.horizontalHeader().height() + 4)
        self._plugin_table.itemClicked.connect(self._on_plugin_row_clicked)
        vbox.addWidget(self._plugin_table, 0)

        test_group = QGroupBox("Plugin Test")
        test_group.setFont(FONT_SM)
        test_layout = QVBoxLayout(test_group)

        test_toolbar = QHBoxLayout()
        test_toolbar.addWidget(QLabel("Test:"))
        self._cmb_test_type = QComboBox()
        self._cmb_test_type.addItems(["Search Test", "URL Test", "Lyric Test"])
        self._cmb_test_type.setFont(FONT_SM)
        test_toolbar.addWidget(self._cmb_test_type)

        self._txt_test_keyword = QLineEdit()
        self._txt_test_keyword.setPlaceholderText("Enter keyword or song ID")
        self._txt_test_keyword.setFont(FONT_SM)
        test_toolbar.addWidget(self._txt_test_keyword, 1)

        self._btn_run_test = QPushButton()
        self._btn_run_test.setIcon(get_icon("zap", "#ccc", 14))
        self._btn_run_test.setToolTip("Run Test")
        self._btn_run_test.setFixedSize(28, 28)
        self._btn_run_test.clicked.connect(self._on_run_test)
        test_toolbar.addWidget(self._btn_run_test)
        test_layout.addLayout(test_toolbar)

        self._test_output = QTextEdit()
        self._test_output.setReadOnly(True)
        self._test_output.setFont(FONT_SM)
        self._test_output.setPlaceholderText("Test results will appear here...")
        test_layout.addWidget(self._test_output)

        vbox.addWidget(test_group, 1)

        return widget

    def _on_plugin_row_clicked(self, item):
        row = item.row()
        plugin_id_item = self._plugin_table.item(row, 0)
        if plugin_id_item:
            plugin_id = plugin_id_item.data(Qt.UserRole)
            if plugin_id and plugin_id in self._plugin_instances:
                self._current_test_plugin = self._plugin_instances[plugin_id]
                self._safe_append(f"\nPlugin selected: {plugin_id}")

    def _on_run_test(self):
        if not self._current_test_plugin:
            self._safe_append("Please select a plugin to test first")
            return
        test_type = self._cmb_test_type.currentIndex()
        keyword = self._txt_test_keyword.text().strip()
        if not keyword:
            keyword = "Jay Chou"
        test_names = ["Search Test", "URL Test", "Lyric Test"]
        self._safe_append(f"\nStarting [{test_names[test_type]}]...")
        self._btn_run_test.setEnabled(False)
        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.terminate()
            self._test_worker.wait()
        self._test_worker = PluginTestWorker(
            self._current_test_plugin, ["search", "url", "lyric"][test_type], keyword
        )
        self._test_worker.progress.connect(lambda msg: self._safe_append(msg))
        self._test_worker.finished.connect(self._on_test_finished)
        self._test_worker.error.connect(self._on_test_error)
        self._test_worker.start()

    def _on_test_finished(self, result):
        self._safe_append(result)
        self._btn_run_test.setEnabled(True)

    def _on_test_error(self, error):
        self._safe_append(f"Error: {error}")
        self._btn_run_test.setEnabled(True)

    def _safe_append(self, text):
        try:
            if self._test_output is None:
                return
            self._test_output.append(text)
        except RuntimeError:
            pass

    def _on_install_plugin(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Plugin File", "", "Python Files (*.py);;JS Files (*.js)"
        )
        if file_path:
            self.plugin_install_requested.emit(file_path)

    def _on_refresh_plugins(self):
        from src.core.event_bus import EventBus
        EventBus().publish("__refresh_plugins__", None)

    def set_plugins(self, plugins, instances=None):
        self._plugins_data = plugins
        if instances:
            self._plugin_instances = instances
        self._plugin_table.setRowCount(0)
        for plugin in plugins:
            row = self._plugin_table.rowCount()
            self._plugin_table.insertRow(row)

            plugin_id = plugin.get("id", "")
            name = plugin.get("name", "")
            source_name = plugin.get("source_name", "")
            display_name = f"{name} ({source_name})" if source_name else name

            can_search = plugin.get("can_search", True)
            can_play = plugin.get("can_play", True)
            can_download = plugin.get("can_download", True)
            can_get_url = plugin.get("can_get_url", False)
            status = plugin.get("status", "enabled")
            is_enabled = status == "enabled"

            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.UserRole, plugin_id)
            self._plugin_table.setItem(row, 0, name_item)

            self._plugin_table.setItem(row, 1, QTableWidgetItem("✓" if can_search else "✗"))
            self._plugin_table.setItem(row, 2, QTableWidgetItem("✓" if can_play else "✗"))
            self._plugin_table.setItem(row, 3, QTableWidgetItem("✓" if can_download else "✗"))
            self._plugin_table.setItem(row, 4, QTableWidgetItem("✓" if can_get_url else "✗"))

            status_item = QTableWidgetItem("Enabled" if is_enabled else "Disabled")
            from src.infrastructure.theme_engine import ThemeEngine
            _tc = ThemeEngine().get_current_colors()
            status_item.setForeground(QColor(_tc.get("success", "#32c864")) if is_enabled else QColor(_tc.get("danger", "#e05050")))
            self._plugin_table.setItem(row, 5, status_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 0, 4, 0)
            action_layout.setSpacing(6)

            from src.infrastructure.theme_engine import ThemeEngine
            _link_tc = ThemeEngine().get_current_colors()
            link_color = _link_tc.get("accent", "#32c864")
            danger_color = _link_tc.get("danger", "#e05050")
            muted_color = _link_tc.get("text_muted", "#666680")

            link_style = (
                f"QPushButton {{ color: {link_color}; background: transparent; border: none; "
                f"padding: 0; margin: 0; font-size: 11px; text-decoration: underline; }}"
                f"QPushButton:hover {{ color: {_link_tc.get('accent_hover', '#3de878')}; }}"
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

            btn_toggle = QPushButton("Disable" if is_enabled else "Enable")
            btn_toggle.setStyleSheet(link_style)
            btn_toggle.setCursor(Qt.PointingHandCursor)
            btn_toggle.setFixedHeight(20)
            btn_toggle.clicked.connect(
                lambda checked, pid=plugin_id, en=is_enabled: self._on_plugin_toggle(pid, en)
            )
            action_layout.addWidget(btn_toggle)

            btn_test = QPushButton("Test")
            btn_test.setStyleSheet(link_style)
            btn_test.setCursor(Qt.PointingHandCursor)
            btn_test.setFixedHeight(20)
            btn_test.clicked.connect(
                lambda checked, pid=plugin_id: self._on_plugin_test(pid)
            )
            action_layout.addWidget(btn_test)

            if is_enabled:
                btn_delete = QPushButton("Delete")
                btn_delete.setStyleSheet(disabled_link_style)
                btn_delete.setCursor(Qt.ForbiddenCursor)
                btn_delete.setFixedHeight(20)
                btn_delete.setToolTip("Please disable the plugin first before deleting")
                btn_delete.clicked.connect(
                    lambda checked, pid=plugin_id: self._on_plugin_delete_hint(pid)
                )
            else:
                btn_delete = QPushButton("Delete")
                btn_delete.setStyleSheet(danger_link_style)
                btn_delete.setCursor(Qt.PointingHandCursor)
                btn_delete.setFixedHeight(20)
                btn_delete.clicked.connect(
                    lambda checked, pid=plugin_id: self._on_plugin_delete(pid)
                )
            action_layout.addWidget(btn_delete)

            self._plugin_table.setCellWidget(row, 6, action_widget)

    def _on_plugin_toggle(self, plugin_id, currently_enabled):
        new_enabled = not currently_enabled
        self.plugin_enable_requested.emit(plugin_id, new_enabled)

    def _on_plugin_test(self, plugin_id):
        if plugin_id in self._plugin_instances:
            self._current_test_plugin = self._plugin_instances[plugin_id]
            self._safe_append(f"\nPlugin selected: {plugin_id}")

    def _on_plugin_delete_hint(self, plugin_id):
        log_msgbox("info", I18n.t("online.msg.cannot_delete_title"),
                    I18n.t("online.msg.cannot_delete_body"))
        ThemedMessageBox.information(
            self, I18n.t("online.msg.cannot_delete_title"),
            I18n.t("online.msg.cannot_delete_body")
        )

    def _on_plugin_delete(self, plugin_id):
        plugin_info = None
        for p in self._plugins_data:
            if p.get("id") == plugin_id:
                plugin_info = p
                break
        if not plugin_info:
            return
        name = plugin_info.get("name", plugin_id)
        source = plugin_info.get("source_name", "")
        display = f"{name} ({source})" if source else name
        log_msgbox("warning", I18n.t("settings.source_plugin.msg_delete_title"),
                    I18n.tf("settings.source_plugin.msg_delete_text", display=display))
        reply = ThemedMessageBox.warning(
            self, I18n.t("settings.source_plugin.msg_delete_title"),
            I18n.tf("settings.source_plugin.msg_delete_text", display=display),
            buttons=[("yes", I18n.t("common.yes")), ("no", I18n.t("common.no"))],
            default_button="no",
        )
        if reply == 1:
            self.plugin_delete_requested.emit(plugin_id)

    # ====================================================== PUBLIC API
    def set_search_results(self, results: list):
        self._search_results = results
        self._fill_song_table(self._search_table, results, ["Song", "Duration", "Source", "Lyric"])

    def record_play_history(self, song: dict):
        self._svc.add_to_history(song)

    def highlight_current_song(self, song_id: str):
        self._highlight_in_table(self._playlist_table, song_id)
        self._highlight_in_table(self._search_table, song_id)

    def _highlight_in_table(self, table: QTableWidget, song_id: str):
        from src.infrastructure.theme_engine import ThemeEngine
        _tc = ThemeEngine().get_current_colors()
        active_bg = QColor(_tc.get("accent", "#32c864"))
        active_bg.setAlpha(40)
        active_fg = QColor(_tc.get("accent", "#32c864"))
        normal_fg = QColor(_tc.get("text_primary", "#e0e0e0"))
        matched = False
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if not item:
                continue
            data = item.data(Qt.UserRole)
            sid = ""
            if data:
                sid = data.get("id") or data.get("hash") or data.get("songmid") or ""
            is_current = (sid == song_id) and bool(song_id)
            if is_current:
                matched = True
            for col in range(table.columnCount()):
                cell = table.item(row, col)
                if cell:
                    font = cell.font()
                    font.setBold(is_current)
                    cell.setFont(font)
                    if is_current:
                        cell.setBackground(active_bg)
                        cell.setForeground(active_fg)
                    else:
                        cell.setBackground(QColor(0, 0, 0, 0))
                        cell.setForeground(normal_fg)
            if is_current:
                table.selectRow(row)
        logger.debug(f"highlight_in_table: song_id={song_id}, rows={table.rowCount()}, matched={matched}")

    # ========================================== IMPORT / EXPORT
    def _on_import_playlist(self):
        from src.presentation.playlist_import_dialog import PlaylistImportDialog
        dialog = PlaylistImportDialog(self)
        dialog.import_completed.connect(self._on_import_done)
        dialog.exec()

    def _on_import_done(self, playlist_name: str, count: int):
        self._refresh_user_playlist_list()
        names = self._svc.get_playlist_names()
        if playlist_name in names:
            idx = names.index(playlist_name)
            self._user_pl_list.setCurrentRow(idx)

    def _on_export_playlist(self):
        if not self._current_playlist_name:
            log_msgbox("info", I18n.t("common.info"), I18n.t("online.msg.select_playlist"))
            ThemedMessageBox.information(self, I18n.t("common.info"), I18n.t("online.msg.select_playlist"))
            return
        from src.presentation.playlist_export_dialog import PlaylistExportDialog
        dialog = PlaylistExportDialog(self._current_playlist_name, self)
        dialog.exec()

    def _on_rematch_user_pl_song(self, row: int, song: dict):
        if not self._current_playlist_name:
            return
        from src.business.playlist_import_service import PlaylistImportService
        from PySide6.QtWidgets import QApplication
        import_svc = PlaylistImportService()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = import_svc.rematch_song(song)
            if result and result.get("match_status") == "matched":
                self._svc.update_user_playlist_song(self._current_playlist_name, row, result)
                self._refresh_user_playlist_detail()
                log_msgbox("info", I18n.t("online.msg.rematch_title"), I18n.t("online.msg.rematch_success"))
                ThemedMessageBox.information(self, I18n.t("online.msg.rematch_title"), I18n.t("online.msg.rematch_success"))
            else:
                log_msgbox("info", I18n.t("online.msg.rematch_title"), I18n.t("online.msg.rematch_not_found"))
                ThemedMessageBox.information(self, I18n.t("online.msg.rematch_title"), I18n.t("online.msg.rematch_not_found"))
        except Exception as e:
            logger.error(f"Rematch failed: {e}")
            log_msgbox("warning", I18n.t("online.msg.rematch_title"), I18n.tf("online.msg.rematch_fail", error=e))
            ThemedMessageBox.warning(self, I18n.t("online.msg.rematch_title"), I18n.tf("online.msg.rematch_fail", error=e))
        finally:
            QApplication.restoreOverrideCursor()

    def _on_get_url_user_pl_song(self, row: int, song: dict):
        if not self._current_playlist_name:
            return
        if song.get("_play_url"):
            log_msgbox("info", I18n.t("online.msg.get_url_title"), I18n.t("online.msg.get_url_has_url"))
            ThemedMessageBox.information(self, I18n.t("online.msg.get_url_title"), I18n.t("online.msg.get_url_has_url"))
            return

        from src.business.playlist_import_service import PlaylistImportService
        from PySide6.QtWidgets import QApplication
        import_svc = PlaylistImportService()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            url = import_svc.get_play_url(song)
            if url:
                self._svc.update_user_playlist_song(self._current_playlist_name, row, song)
                self._refresh_user_playlist_detail()
                log_msgbox("info", I18n.t("online.msg.get_url_title"), I18n.t("online.msg.get_url_success"))
                ThemedMessageBox.information(self, I18n.t("online.msg.get_url_title"), I18n.t("online.msg.get_url_success"))
            else:
                log_msgbox("info", I18n.t("online.msg.get_url_title"), I18n.t("online.msg.get_url_not_found"))
                ThemedMessageBox.information(self, I18n.t("online.msg.get_url_title"), I18n.t("online.msg.get_url_not_found"))
        except Exception as e:
            logger.error(f"Get URL failed: {e}")
            log_msgbox("warning", I18n.t("online.msg.get_url_title"), I18n.tf("online.msg.get_url_fail", error=e))
            ThemedMessageBox.warning(self, I18n.t("online.msg.get_url_title"), I18n.tf("online.msg.get_url_fail", error=e))
        finally:
            QApplication.restoreOverrideCursor()
