from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QSizePolicy,
)
from src.utils.svg_icons import get_icon

FONT_FAMILY = "Microsoft YaHei"
TITLE_FONT = QFont(FONT_FAMILY, 14, QFont.Bold)
LYRIC_ACTIVE_FONT = QFont(FONT_FAMILY, 16, QFont.Bold)
LYRIC_INACTIVE_FONT = QFont(FONT_FAMILY, 16, QFont.Normal)
OFFSET_BTN_FONT = QFont(FONT_FAMILY, 9)
OFFSET_LABEL_FONT = QFont(FONT_FAMILY, 9)


def _get_theme_colors():
    try:
        from src.infrastructure.theme_engine import ThemeEngine
        c = ThemeEngine().get_current_colors()
        return (
            QColor(c.get("lyric_active", "#32c864")),
            QColor(c.get("lyric_inactive", "#a0a0b0")),
            QColor(c.get("text_primary", "#e0e0e0")),
            QColor(c.get("text_secondary", "#a0a0b0")),
        )
    except Exception:
        return QColor(50, 200, 100), QColor(160, 160, 160), QColor(30, 30, 30), QColor(100, 100, 100)


class LyricPanel(QWidget):
    offset_adjusted = Signal(int)
    offset_reset = Signal()
    offset_save = Signal()
    line_clicked = Signal(int)
    lines_selected = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lyric_labels = []
        self._translation_labels = []
        self._current_index = -1
        self._stretch_item = None
        self._font_size = 16
        self._current_offset_ms = 0
        self._selected_start = -1
        self._selected_end = -1
        self._repeat_start_ms = -1
        self._translation_visible = False
        self._dictation_mode = False
        self._original_texts = []
        self._repeat_end_ms = -1
        self._scroll_freeze = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(0)

        _, _, title_color, subtitle_color = _get_theme_colors()

        self._lbl_title = QLabel("")
        self._lbl_title.setFont(TITLE_FONT)
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setStyleSheet(f"color: {title_color.name()}; background: transparent;")
        layout.addWidget(self._lbl_title)

        layout.addSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._lyric_container = QWidget()
        self._lyric_container.setStyleSheet("background: transparent; border: none;")
        self._lyric_layout = QVBoxLayout(self._lyric_container)
        self._lyric_layout.setContentsMargins(8, 10, 8, 10)
        self._lyric_layout.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._lyric_container)

        layout.addWidget(self._scroll, 1)

        self._offset_bar = self._build_offset_bar()
        self._offset_bar.setVisible(False)
        layout.addWidget(self._offset_bar)

        self.setStyleSheet("LyricPanel { background: transparent; border: none; }")

    def _build_offset_bar(self) -> QWidget:
        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(0, 2, 0, 2)
        hbox.setSpacing(4)
        hbox.setAlignment(Qt.AlignCenter)

        lbl_hint = QLabel("Offset:")
        lbl_hint.setFont(OFFSET_LABEL_FONT)
        lbl_hint.setStyleSheet("color: #999; background: transparent;")
        hbox.addWidget(lbl_hint)

        for text, delta in [("-2s", -2000), ("-1s", -1000), ("-0.5s", -500)]:
            btn = QPushButton(text)
            btn.setFont(OFFSET_BTN_FONT)
            btn.setMinimumWidth(btn.sizeHint().width() + 8)
            btn.clicked.connect(lambda _, d=delta: self._on_adjust(d))
            hbox.addWidget(btn)

        self._lbl_offset = QLabel("0.0s")
        self._lbl_offset.setFont(OFFSET_LABEL_FONT)
        self._lbl_offset.setAlignment(Qt.AlignCenter)
        self._lbl_offset.setMinimumWidth(45)
        self._lbl_offset.setStyleSheet("color: #ddd; font-weight: bold; background: transparent;")
        hbox.addWidget(self._lbl_offset)

        for text, delta in [("+0.5s", 500), ("+1s", 1000), ("+2s", 2000)]:
            btn = QPushButton(text)
            btn.setFont(OFFSET_BTN_FONT)
            btn.setMinimumWidth(btn.sizeHint().width() + 8)
            btn.clicked.connect(lambda _, d=delta: self._on_adjust(d))
            hbox.addWidget(btn)

        hbox.addSpacing(8)

        self._btn_reset = QPushButton()
        self._btn_reset.setIcon(get_icon("rotate-ccw", "#ccc", 14))
        self._btn_reset.setToolTip("Reset")
        self._btn_reset.setFixedSize(28, 28)
        self._btn_reset.clicked.connect(self._on_reset)
        hbox.addWidget(self._btn_reset)

        self._btn_save = QPushButton()
        self._btn_save.setIcon(get_icon("save", "#ccc", 14))
        self._btn_save.setToolTip("Save")
        self._btn_save.setFixedSize(28, 28)
        self._btn_save.clicked.connect(self._on_save)
        hbox.addWidget(self._btn_save)

        return bar

    def _on_adjust(self, delta_ms: int):
        self.offset_adjusted.emit(delta_ms)

    def _on_reset(self):
        self.offset_reset.emit()

    def _on_save(self):
        self.offset_save.emit()

    def update_offset_display(self, offset_ms: int):
        self._current_offset_ms = offset_ms
        sign = "+" if offset_ms > 0 else ""
        self._lbl_offset.setText(f"{sign}{offset_ms / 1000:.1f}s")
        has_offset = offset_ms != 0
        self._btn_reset.setEnabled(has_offset)
        self._btn_save.setEnabled(has_offset)

    def show_offset_bar(self):
        self._offset_bar.setVisible(True)

    def hide_offset_bar(self):
        self._offset_bar.setVisible(False)

    def set_song_info(self, title: str, artist: str = "", album: str = ""):
        if artist:
            self._lbl_title.setText(f"{title} — {artist}")
        else:
            self._lbl_title.setText(title if title else "Unknown")

    def _calc_line_height(self, font: QFont) -> int:
        fm = QFontMetrics(font)
        return int(fm.height() * 1.5)

    def _apply_active_style(self, lbl: QLabel, color: QColor):
        lbl.setStyleSheet(
            f"color: {color.name()}; background: transparent; border: none;"
        )

    def _apply_inactive_style(self, lbl: QLabel, color: QColor):
        lbl.setStyleSheet(
            f"color: {color.name()}; background: transparent; border: none;"
        )

    def set_lyric_lines(self, lines: list, translations: list = None):
        self._clear_lyric_labels()

        _, inactive_color, _, _ = _get_theme_colors()
        inactive_font = QFont(FONT_FAMILY, self._font_size, QFont.Normal)
        line_h = self._calc_line_height(inactive_font)
        fm = QFontMetrics(inactive_font)
        spacing = line_h - fm.height()
        self._lyric_layout.setSpacing(spacing)

        self._lyric_times = [line.time_ms for line in lines]
        self._original_texts = [line.text for line in lines]

        trans_font = QFont(FONT_FAMILY, max(self._font_size - 3, 9), QFont.Normal)
        trans_color = QColor(inactive_color)
        trans_color.setAlpha(180)

        if translations:
            self._translation_visible = True

        for i, line in enumerate(lines):
            lbl = QLabel(line.text)
            lbl.setFont(inactive_font)
            self._apply_inactive_style(lbl, inactive_color)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            lbl.setFixedHeight(line_h)
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.mousePressEvent = lambda event, idx=i: self._on_line_clicked(idx, event)
            self._lyric_layout.addWidget(lbl)
            self._lyric_labels.append(lbl)

            if self._translation_visible and translations and i < len(translations) and translations[i]:
                trans_lbl = QLabel(translations[i])
                trans_lbl.setFont(trans_font)
                trans_lbl.setStyleSheet(
                    f"color: {trans_color.name()}; background: transparent; border: none;"
                )
                trans_lbl.setAlignment(Qt.AlignCenter)
                trans_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                self._lyric_layout.addWidget(trans_lbl)
                self._translation_labels.append(trans_lbl)
            else:
                self._translation_labels.append(None)

        self._stretch_item = self._lyric_layout.addStretch()

    def set_translations(self, translations: list):
        if not self._lyric_labels:
            return
        self._translation_visible = bool(translations and any(translations))

        _, inactive_color, _, _ = _get_theme_colors()
        trans_font = QFont(FONT_FAMILY, max(self._font_size - 3, 9), QFont.Normal)
        trans_color = QColor(inactive_color)
        trans_color.setAlpha(180)

        for i, lbl in enumerate(self._lyric_labels):
            trans_text = translations[i] if i < len(translations) else ""
            existing_trans = self._translation_labels[i] if i < len(self._translation_labels) else None

            if trans_text and self._translation_visible:
                if existing_trans:
                    existing_trans.setText(trans_text)
                    existing_trans.setVisible(True)
                else:
                    trans_lbl = QLabel(trans_text)
                    trans_lbl.setFont(trans_font)
                    trans_lbl.setStyleSheet(
                        f"color: {trans_color.name()}; background: transparent; border: none;"
                    )
                    trans_lbl.setAlignment(Qt.AlignCenter)
                    trans_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                    idx_in_layout = self._lyric_layout.indexOf(lbl) + 1
                    self._lyric_layout.insertWidget(idx_in_layout, trans_lbl)
                    while len(self._translation_labels) <= i:
                        self._translation_labels.append(None)
                    self._translation_labels[i] = trans_lbl
            elif existing_trans:
                existing_trans.setVisible(False)

    def set_translation_visible(self, visible: bool):
        self._translation_visible = visible
        for trans_lbl in self._translation_labels:
            if trans_lbl:
                trans_lbl.setVisible(visible)

    def set_dictation_mode(self, enabled: bool):
        self._dictation_mode = enabled
        for i, lbl in enumerate(self._lyric_labels):
            if enabled:
                if i == self._current_index:
                    lbl.setText(self._original_texts[i] if i < len(self._original_texts) else lbl.text())
                else:
                    lbl.setText("·" * min(len(self._original_texts[i]) if i < len(self._original_texts) else 3, 20))
            else:
                if i < len(self._original_texts):
                    lbl.setText(self._original_texts[i])

    def _on_line_clicked(self, index: int, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ShiftModifier and self._selected_start >= 0:
                self._selected_end = index
                self._update_selection_highlight()
                start = min(self._selected_start, self._selected_end)
                end = max(self._selected_start, self._selected_end)
                self.lines_selected.emit(start, end)
            else:
                self._selected_start = index
                self._selected_end = index
                self._update_selection_highlight()
                self.line_clicked.emit(index)

    def highlight_line(self, index: int):
        if index == self._current_index:
            return
        if index < 0 or index >= len(self._lyric_labels):
            return

        active_color, inactive_color, _, _ = _get_theme_colors()
        active_font = QFont(FONT_FAMILY, self._font_size, QFont.Bold)
        inactive_font = QFont(FONT_FAMILY, self._font_size, QFont.Normal)
        active_line_h = self._calc_line_height(active_font)
        inactive_line_h = self._calc_line_height(inactive_font)

        if 0 <= self._current_index < len(self._lyric_labels):
            old = self._lyric_labels[self._current_index]
            old.setFont(inactive_font)
            self._apply_inactive_style(old, inactive_color)
            old.setFixedHeight(inactive_line_h)

        self._current_index = index
        lbl = self._lyric_labels[index]
        lbl.setFont(active_font)
        self._apply_active_style(lbl, active_color)
        lbl.setFixedHeight(active_line_h)

        if not self._scroll_freeze:
            QTimer.singleShot(50, lambda: self._scroll_to_line(index))

    def _scroll_to_line(self, index: int):
        if index < 0 or index >= len(self._lyric_labels):
            return
        lbl = self._lyric_labels[index]
        scroll_height = self._scroll.viewport().height()
        target_y = lbl.pos().y() - scroll_height // 3
        self._scroll.verticalScrollBar().setValue(max(0, target_y))

    def _update_selection_highlight(self):
        active_color, inactive_color, _, _ = _get_theme_colors()
        from src.infrastructure.theme_engine import ThemeEngine
        tc = ThemeEngine().get_current_colors()
        select_bg = QColor(tc.get("accent", "#32c864"))
        select_bg.setAlpha(35)
        repeat_bg = QColor(tc.get("table_row_selected", "rgba(50,200,100,40)"))

        sel_start = min(self._selected_start, self._selected_end) if self._selected_start >= 0 and self._selected_end >= 0 else -1
        sel_end = max(self._selected_start, self._selected_end) if self._selected_start >= 0 and self._selected_end >= 0 else -1

        inactive_font = QFont(FONT_FAMILY, self._font_size, QFont.Normal)
        inactive_line_h = self._calc_line_height(inactive_font)

        for i, lbl in enumerate(self._lyric_labels):
            if i == self._current_index:
                continue
            lbl.setFont(inactive_font)
            lbl.setFixedHeight(inactive_line_h)

            in_selection = sel_start >= 0 and sel_start <= i <= sel_end
            in_repeat_range = self._is_in_repeat_range(i)

            if in_selection:
                lbl.setStyleSheet(
                    f"color: {active_color.name()}; background-color: {select_bg.name(QColor.HexArgb)}; "
                    f"border: none; border-radius: 3px; padding: 0 4px;"
                )
            elif in_repeat_range:
                lbl.setStyleSheet(
                    f"color: {inactive_color.name()}; background-color: {repeat_bg.name(QColor.HexArgb)}; "
                    f"border: none; border-radius: 3px; padding: 0 4px;"
                )
            else:
                self._apply_inactive_style(lbl, inactive_color)

    def _is_in_repeat_range(self, line_index: int) -> bool:
        if self._repeat_start_ms < 0 or self._repeat_end_ms < 0:
            return False
        if not hasattr(self, '_lyric_times') or line_index >= len(self._lyric_times):
            return False
        line_start = self._lyric_times[line_index]
        line_end = self._lyric_times[line_index + 1] if line_index + 1 < len(self._lyric_times) else self._repeat_end_ms + 1
        return line_start < self._repeat_end_ms and line_end > self._repeat_start_ms

    def set_repeat_range(self, start_ms: int, end_ms: int):
        self._repeat_start_ms = start_ms
        self._repeat_end_ms = end_ms
        self._update_selection_highlight()

    def clear_repeat_range(self):
        self._repeat_start_ms = -1
        self._repeat_end_ms = -1
        self._update_selection_highlight()

    def set_scroll_freeze(self, freeze: bool):
        self._scroll_freeze = freeze
        if not freeze and 0 <= self._current_index < len(self._lyric_labels):
            QTimer.singleShot(50, lambda: self._scroll_to_line(self._current_index))

    def _clear_lyric_labels(self):
        if self._stretch_item is not None:
            self._lyric_layout.removeItem(self._stretch_item)
            self._stretch_item = None
        for lbl in self._lyric_labels:
            self._lyric_layout.removeWidget(lbl)
            lbl.deleteLater()
        self._lyric_labels.clear()
        for lbl in self._translation_labels:
            if lbl:
                self._lyric_layout.removeWidget(lbl)
                lbl.deleteLater()
        self._translation_labels.clear()
        self._current_index = -1
        self._selected_start = -1
        self._selected_end = -1
        self._repeat_start_ms = -1
        self._repeat_end_ms = -1
        self._original_texts = []

    def set_font_size(self, size: int):
        self._font_size = size
        active_font = QFont(FONT_FAMILY, size, QFont.Bold)
        inactive_font = QFont(FONT_FAMILY, size, QFont.Normal)
        active_line_h = self._calc_line_height(active_font)
        inactive_line_h = self._calc_line_height(inactive_font)
        for i, lbl in enumerate(self._lyric_labels):
            if i == self._current_index:
                lbl.setFont(active_font)
                lbl.setFixedHeight(active_line_h)
            else:
                lbl.setFont(inactive_font)
                lbl.setFixedHeight(inactive_line_h)

    def clear(self):
        self._lbl_title.setText("")
        self._clear_lyric_labels()
        self._current_offset_ms = 0
        self.update_offset_display(0)
        self._offset_bar.setVisible(False)
