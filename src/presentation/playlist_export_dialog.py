import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QLabel, QComboBox, QFileDialog, QRadioButton,
    QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView,
)

from src.business.i18n_service import I18n
from src.presentation.themed_dialog import ThemedDialog, ThemedMessageBox
from src.core.online_music_service import OnlineMusicService
from src.infrastructure.playlist_parser import save_playlist_with_meta
from src.utils.logger import setup_logger, log_msgbox

logger = setup_logger(__name__)

FONT = "Microsoft YaHei"


class PlaylistExportDialog(ThemedDialog):
    def __init__(self, playlist_name: str, parent=None):
        super().__init__(parent, title=I18n.t("playlist.export.dlg_title"))
        self._online_svc = OnlineMusicService()
        self._playlist_name = playlist_name
        self._songs = self._online_svc.get_playlist_for_export(playlist_name)
        self._init_ui()

    def _init_ui(self):
        self.setMinimumSize(560, 440)
        self.resize(640, 500)

        layout = self.body_layout()
        layout.setSpacing(8)

        info_label = QLabel(I18n.tf("playlist.export.label_info", name=self._playlist_name, count=len(self._songs)))
        layout.addWidget(info_label)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([I18n.t("playlist.export.col_title"), I18n.t("playlist.export.col_artist"), I18n.t("playlist.export.col_quality"), I18n.t("playlist.export.col_match_status")])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().hide()

        for song in self._songs:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(song.get("title", "")))
            self._table.setItem(row, 1, QTableWidgetItem(song.get("artist", "")))
            self._table.setItem(row, 2, QTableWidgetItem(song.get("quality", "")))
            status = song.get("match_status", "")
            if status == "matched":
                status_text = I18n.t("playlist.export.status_matched")
            elif status == "unmatched":
                status_text = I18n.t("playlist.export.status_not_matched")
            else:
                status_text = ""
            self._table.setItem(row, 3, QTableWidgetItem(status_text))

        layout.addWidget(self._table, 1)

        format_group = QVBoxLayout()
        format_label = QLabel(I18n.t("playlist.export.label_format"))
        format_group.addWidget(format_label)

        format_row = QHBoxLayout()
        self._rb_m3u = QRadioButton("M3U/M3U8")
        self._rb_json = QRadioButton(I18n.t("playlist.export.rb_json_full"))
        self._rb_csv = QRadioButton("CSV")
        self._rb_txt = QRadioButton(I18n.t("playlist.export.rb_txt"))
        self._rb_m3u.setChecked(True)

        bg = QButtonGroup(self)
        bg.addButton(self._rb_m3u)
        bg.addButton(self._rb_json)
        bg.addButton(self._rb_csv)
        bg.addButton(self._rb_txt)

        format_row.addWidget(self._rb_m3u)
        format_row.addWidget(self._rb_json)
        format_row.addWidget(self._rb_csv)
        format_row.addWidget(self._rb_txt)
        format_row.addStretch()
        format_group.addLayout(format_row)
        layout.addLayout(format_group)

        hint_label = QLabel(I18n.t("playlist.export.hint"))
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_export = QPushButton(I18n.t("playlist.export.btn_export"))
        btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(btn_export)
        btn_cancel = QPushButton(I18n.t("common.cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _get_selected_format(self) -> str:
        if self._rb_json.isChecked():
            return "json"
        if self._rb_csv.isChecked():
            return "csv"
        if self._rb_txt.isChecked():
            return "txt"
        return "m3u"

    def _get_file_filter(self, fmt: str) -> tuple:
        filters = {
            "m3u": (I18n.t("playlist.export.filter_m3u"), ".m3u"),
            "json": (I18n.t("playlist.export.filter_json"), ".json"),
            "csv": (I18n.t("playlist.export.filter_csv"), ".csv"),
            "txt": (I18n.t("playlist.export.filter_txt"), ".txt"),
        }
        return filters.get(fmt, filters["m3u"])

    def _on_export(self):
        if not self._songs:
            log_msgbox("info", I18n.t("common.info"), I18n.t("playlist.export.msg_empty"))
            ThemedMessageBox.information(self, I18n.t("common.info"), I18n.t("playlist.export.msg_empty"))
            return

        fmt = self._get_selected_format()
        file_filter, default_ext = self._get_file_filter(fmt)

        default_name = f"{self._playlist_name}{default_ext}"
        file_path, _ = QFileDialog.getSaveFileName(
            self, I18n.t("playlist.export.dlg_save_title"), default_name, file_filter
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        if not ext:
            file_path += default_ext

        success = save_playlist_with_meta(file_path, self._songs)
        if success:
            log_msgbox("info", I18n.t("playlist.export.msg_export_done"), I18n.tf("playlist.export.msg_export_done_detail", path=file_path, count=len(self._songs)))
            ThemedMessageBox.information(
                self, I18n.t("playlist.export.msg_export_done"),
                I18n.tf("playlist.export.msg_export_done_detail", path=file_path, count=len(self._songs))
            )
            self.accept()
        else:
            log_msgbox("warning", I18n.t("playlist.export.msg_export_fail"), I18n.t("playlist.export.msg_export_fail_detail"))
            ThemedMessageBox.warning(self, I18n.t("playlist.export.msg_export_fail"), I18n.t("playlist.export.msg_export_fail_detail"))
