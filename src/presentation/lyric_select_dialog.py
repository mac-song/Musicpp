from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QTextEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.business.i18n_service import I18n
from src.presentation.themed_dialog import ThemedDialog
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class LyricSelectDialog(ThemedDialog):
    def __init__(self, song_title: str, candidates: list, parent=None):
        super().__init__(parent, title=I18n.t("lyric_select.dlg_title"))
        self._candidates = candidates
        self._selected_index = -1
        self._init_ui(song_title)

    def _init_ui(self, song_title: str):
        self.setMinimumSize(700, 450)
        self.resize(800, 550)

        layout = self.body_layout()
        layout.setSpacing(8)

        info_label = QLabel(f"Found {len(self._candidates)} lyric candidates for: {song_title}")
        info_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #ddd;")
        layout.addWidget(info_label)

        hint_label = QLabel("Double-click a row or select and click OK to apply. Click Cancel to skip.")
        hint_label.setStyleSheet("font-size: 11px; color: #999;")
        layout.addWidget(hint_label)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["#", "Source", "Title", "Artist", "Duration"])
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setFixedHeight(26 * 5 + self._table.horizontalHeader().height() + 4)
        self._table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self._table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFont(QFont("Consolas", 10))
        self._preview.setStyleSheet(
            "QTextEdit { background: #1a1a2e; color: #ccc; border: 1px solid #333; border-radius: 4px; padding: 4px; }"
        )
        self._preview.setPlaceholderText("Select a row above to preview lyrics...")
        layout.addWidget(self._preview, stretch=1)

        self._table.selectionModel().currentRowChanged.connect(self._on_row_changed)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_ok = QPushButton("OK")
        self._btn_ok.setFixedWidth(80)
        self._btn_ok.setEnabled(False)
        self._btn_ok.clicked.connect(self._on_ok)
        btn_layout.addWidget(self._btn_ok)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setFixedWidth(80)
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        layout.addLayout(btn_layout)

        self._populate_table()

    def _populate_table(self):
        self._table.setRowCount(len(self._candidates))
        for i, cand in enumerate(self._candidates):
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 0, num_item)

            source_item = QTableWidgetItem(cand.get("source", ""))
            source_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 1, source_item)

            self._table.setItem(i, 2, QTableWidgetItem(cand.get("title", "")))
            self._table.setItem(i, 3, QTableWidgetItem(cand.get("artist", "")))

            dur = cand.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(i, 4, dur_item)

        if self._candidates:
            self._table.selectRow(0)
            self._btn_ok.setEnabled(True)

    def _on_row_changed(self, current, _previous):
        row = current.row() if current.isValid() else -1
        if 0 <= row < len(self._candidates):
            content = self._candidates[row].get("content", "")
            self._preview.setPlainText(content)
            self._btn_ok.setEnabled(True)
        else:
            self._preview.clear()
            self._btn_ok.setEnabled(False)

    def _on_double_click(self):
        self._on_ok()

    def _on_ok(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._candidates):
            self._selected_index = row
            self.accept()

    def get_selected(self) -> dict:
        if 0 <= self._selected_index < len(self._candidates):
            return self._candidates[self._selected_index]
        return None
