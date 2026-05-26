from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout,
)

from src.business.i18n_service import I18n
from src.infrastructure.ecdict_provider import DictEntry
from src.infrastructure.theme_engine import ThemeEngine


FONT = "Microsoft YaHei"


class WordTooltip(QFrame):
    pin_requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self._entry = None
        self._word = ""
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)

        self._word_label = QLabel()
        self._word_label.setFont(QFont(FONT, 13, QFont.Bold))
        header.addWidget(self._word_label)

        self._phonetic_label = QLabel()
        self._phonetic_label.setFont(QFont(FONT, 10))
        header.addWidget(self._phonetic_label)

        header.addStretch()

        self._pin_btn = QPushButton("📌")
        self._pin_btn.setFixedSize(22, 22)
        self._pin_btn.setCursor(Qt.PointingHandCursor)
        self._pin_btn.setToolTip(I18n.t("word.tooltip.pin_detail"))
        self._pin_btn.clicked.connect(self._on_pin)
        self._pin_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 12px; }")
        header.addWidget(self._pin_btn)

        layout.addLayout(header)

        self._trans_label = QLabel()
        self._trans_label.setFont(QFont(FONT, 11))
        self._trans_label.setWordWrap(True)
        self._trans_label.setMaximumWidth(360)
        layout.addWidget(self._trans_label)

        self._tag_label = QLabel()
        self._tag_label.setFont(QFont(FONT, 9))
        layout.addWidget(self._tag_label)

        self._hint_label = QLabel(I18n.t("word.tooltip.hint"))
        self._hint_label.setFont(QFont(FONT, 8))
        layout.addWidget(self._hint_label)

        self._apply_style()

    def _apply_style(self):
        tc = ThemeEngine().get_current_colors()
        bg = tc.get("surface", "#16213e")
        border = tc.get("border", "#333355")
        text = tc.get("text_primary", "#e0e0e0")
        text2 = tc.get("text_secondary", "#a0a0b0")
        accent = tc.get("accent", "#32c864")

        self.setStyleSheet(f"""
            WordTooltip {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)
        self._word_label.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        self._phonetic_label.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
        self._trans_label.setStyleSheet(f"color: {text}; background: transparent; border: none;")
        self._tag_label.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
        self._hint_label.setStyleSheet(f"color: {tc.get('text_muted', '#8a8aa0')}; background: transparent; border: none;")

    def set_entry(self, word: str, entry: Optional[DictEntry]):
        self._word = word
        self._entry = entry
        self._apply_style()

        if entry is None:
            self._word_label.setText(word)
            self._phonetic_label.setText("")
            self._trans_label.setText(I18n.t("word.detail.not_found"))
            self._tag_label.setText("")
            self._hint_label.setVisible(False)
            return

        self._word_label.setText(entry.word)

        ph = entry.phonetic
        if ph and not ph.startswith("/"):
            ph = f"/{ph}/"
        self._phonetic_label.setText(ph)

        trans_text = entry.translation
        if not trans_text and entry.definition:
            trans_text = entry.definition
        if trans_text:
            lines = trans_text.split("\n")
            display_lines = lines[:6]
            if len(lines) > 6:
                display_lines.append("…")
            trans_text = "\n".join(display_lines)
        self._trans_label.setText(trans_text or I18n.t("word.detail.no_translation"))

        tags = []
        if entry.tag:
            tag_str = entry.tag.strip()
            if tag_str:
                tags.append(tag_str)
        if entry.collins:
            stars = "★" * min(entry.collins, 5)
            tags.append(I18n.tf("word.detail.collins_star", stars=stars))
        if entry.oxford:
            tags.append(I18n.t("word.detail.oxford_3000"))
        if entry.source == "offline":
            tags.append(I18n.t("word.detail.offline_label"))
        elif entry.source != "offline":
            tags.append(I18n.tf("word.detail.online_label", source=entry.source))

        self._tag_label.setText(" | ".join(tags) if tags else "")
        self._hint_label.setVisible(True)

    def _on_pin(self):
        if self._entry:
            self.pin_requested.emit(self._word, self._entry)

    def show_at(self, global_pos):
        self.adjustSize()
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = global_pos.x()
            y = global_pos.y() + 16
            if x + self.width() > geo.right():
                x = geo.right() - self.width() - 4
            if y + self.height() > geo.bottom():
                y = global_pos.y() - self.height() - 8
            if x < geo.left():
                x = geo.left() + 4
            if y < geo.top():
                y = geo.top() + 4
            self.move(x, y)
        self.show()


class WordDetailPanel(QFrame):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self._entry = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self._word_label = QLabel()
        self._word_label.setFont(QFont(FONT, 16, QFont.Bold))
        header.addWidget(self._word_label)

        self._phonetic_label = QLabel()
        self._phonetic_label.setFont(QFont(FONT, 12))
        header.addWidget(self._phonetic_label)

        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; color: #aaa; } QPushButton:hover { color: #fff; }")
        header.addWidget(close_btn)

        layout.addLayout(header)

        self._pos_label = QLabel()
        self._pos_label.setFont(QFont(FONT, 10))
        layout.addWidget(self._pos_label)

        self._trans_label = QLabel()
        self._trans_label.setFont(QFont(FONT, 12))
        self._trans_label.setWordWrap(True)
        self._trans_label.setMaximumWidth(420)
        layout.addWidget(self._trans_label)

        self._def_label = QLabel()
        self._def_label.setFont(QFont(FONT, 10))
        self._def_label.setWordWrap(True)
        self._def_label.setMaximumWidth(420)
        layout.addWidget(self._def_label)

        self._exchange_label = QLabel()
        self._exchange_label.setFont(QFont(FONT, 9))
        layout.addWidget(self._exchange_label)

        self._tag_label = QLabel()
        self._tag_label.setFont(QFont(FONT, 9))
        layout.addWidget(self._tag_label)

    def _apply_style(self):
        tc = ThemeEngine().get_current_colors()
        bg = tc.get("surface", "#16213e")
        border = tc.get("border", "#333355")
        text = tc.get("text_primary", "#e0e0e0")
        text2 = tc.get("text_secondary", "#a0a0b0")
        accent = tc.get("accent", "#32c864")

        self.setStyleSheet(f"""
            WordDetailPanel {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        self._word_label.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        self._phonetic_label.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
        self._pos_label.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        self._trans_label.setStyleSheet(f"color: {text}; background: transparent; border: none;")
        self._def_label.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
        self._exchange_label.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
        self._tag_label.setStyleSheet(f"color: {tc.get('text_muted', '#8a8aa0')}; background: transparent; border: none;")

    def set_entry(self, word: str, entry: Optional[DictEntry]):
        self._entry = entry
        self._apply_style()

        if entry is None:
            self._word_label.setText(word)
            self._phonetic_label.setText("")
            self._pos_label.setText("")
            self._trans_label.setText(I18n.t("word.detail.not_found"))
            self._def_label.setText("")
            self._exchange_label.setText("")
            self._tag_label.setText("")
            return

        self._word_label.setText(entry.word)

        ph = entry.phonetic
        if ph and not ph.startswith("/"):
            ph = f"/{ph}/"
        self._phonetic_label.setText(ph)

        self._pos_label.setText(I18n.tf("word.detail.pos_label", pos=entry.pos) if entry.pos else "")

        self._trans_label.setText(entry.translation or I18n.t("word.detail.no_chinese"))

        if entry.definition:
            self._def_label.setText(I18n.t("word.detail.en_definition_label") + "\n" + entry.definition)
            self._def_label.setVisible(True)
        else:
            self._def_label.setVisible(False)

        if entry.exchange:
            parts = []
            for item in entry.exchange.split("/"):
                if ":" in item:
                    prefix, val = item.split(":", 1)
                    labels = {
                        "p": I18n.t("word.detail.exchange_p"), "d": I18n.t("word.detail.exchange_d"), "i": I18n.t("word.detail.exchange_i"),
                        "3": I18n.t("word.detail.exchange_3"), "r": I18n.t("word.detail.exchange_r"), "t": I18n.t("word.detail.exchange_t"),
                        "s": I18n.t("word.detail.exchange_s"), "0": I18n.t("word.detail.exchange_0"), "1": I18n.t("word.detail.exchange_1"),
                    }
                    label = labels.get(prefix, prefix)
                    parts.append(f"{label}: {val}")
            if parts:
                self._exchange_label.setText(I18n.t("word.detail.exchange_label") + " | ".join(parts))
                self._exchange_label.setVisible(True)
            else:
                self._exchange_label.setVisible(False)
        else:
            self._exchange_label.setVisible(False)

        tags = []
        if entry.tag:
            tags.append(entry.tag)
        if entry.collins:
            tags.append(I18n.tf("word.detail.collins_star", stars='★' * min(entry.collins, 5)))
        if entry.oxford:
            tags.append(I18n.t("word.detail.oxford_3000"))
        if entry.bnc:
            tags.append(f"BNC #{entry.bnc}")
        if entry.frq:
            tags.append(I18n.tf("word.detail.contemporary", rank=entry.frq))
        self._tag_label.setText(" | ".join(tags) if tags else "")

    def show_at(self, global_pos):
        self.adjustSize()
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = global_pos.x()
            y = global_pos.y() + 16
            if x + self.width() > geo.right():
                x = geo.right() - self.width() - 4
            if y + self.height() > geo.bottom():
                y = global_pos.y() - self.height() - 8
            self.move(x, y)
        self.show()


def get_word_at_position(text: str, pos: int) -> str:
    if not text or pos < 0 or pos >= len(text):
        return ""
    if not text[pos].isalpha():
        return ""
    start = pos
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    end = pos
    while end < len(text) - 1 and text[end + 1].isalpha():
        end += 1
    word = text[start:end + 1]
    if len(word) < 2:
        return ""
    return word


