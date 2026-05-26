from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)

from src.business.help_data import HELP_DATA
from src.business.i18n_service import I18n
from src.infrastructure.theme_engine import ThemeEngine
from src.utils.svg_icons import get_icon

FONT_YAHEI = "Microsoft YaHei"
FONT_SONG = "SimSun"

RELATED_HELP = {
    "study_library": ["study_controls"],
    "study_import": ["study_controls"],
    "study_subtitle": ["study_controls"],
    "study_segment": ["study_controls"],
    "main_settings": ["dev_architecture", "dev_source_plugin", "dev_decoder_plugin", "dev_transcription_plugin", "dev_theme"],
    "dev_architecture": ["dev_source_plugin", "dev_decoder_plugin", "dev_transcription_plugin", "dev_theme"],
    "dev_source_plugin": ["dev_architecture", "dev_decoder_plugin"],
    "dev_decoder_plugin": ["dev_architecture", "dev_source_plugin"],
    "dev_transcription_plugin": ["dev_architecture"],
    "dev_theme": ["dev_architecture"],
}


def _make_font(size_pt: int, bold: bool = False) -> QFont:
    family = FONT_YAHEI if size_pt >= 10 else FONT_SONG
    weight = QFont.Bold if bold else QFont.Normal
    return QFont(family, size_pt, weight)


class HelpWindow(QWidget):
    def __init__(self, main_window: QWidget, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self._current_help_id = None
        self._syncing_position = False
        self._init_ui()
        self._setup_window_flags()

    def _setup_window_flags(self):
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

    def _init_ui(self):
        self.setFixedWidth(380)
        self.setMinimumHeight(200)
        self.setObjectName("HelpWindow")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("HelpWindowHeader")
        header.setFixedHeight(32)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 0, 0, 0)
        header_layout.setSpacing(0)

        self._lbl_title = QLabel("")
        self._lbl_title.setObjectName("HelpWindowTitle")
        self._lbl_title.setFont(_make_font(11, bold=True))
        header_layout.addWidget(self._lbl_title)

        header_layout.addStretch()

        self._btn_close = QPushButton()
        self._btn_close.setObjectName("HelpWindowCloseButton")
        self._btn_close.setFixedSize(40, 32)
        self._btn_close.setToolTip(I18n.t("help.close"))
        self._btn_close.clicked.connect(self._on_close)
        header_layout.addWidget(self._btn_close)

        layout.addWidget(header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._content_widget = QWidget()
        self._content_widget.setObjectName("HelpWindowContent")
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(16, 12, 16, 16)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()

        self._scroll.setWidget(self._content_widget)
        layout.addWidget(self._scroll, 1)

        self._apply_style()
        self._update_icons()

    def _apply_style(self):
        tc = ThemeEngine().get_current_colors()
        bg = tc.get("surface", "#1a1a2e")
        surface2 = tc.get("surface_alt", "#222240")
        text = tc.get("text_primary", "#e0e0e0")
        text2 = tc.get("text_secondary", "#a0a0b0")
        accent = tc.get("accent", "#32c864")
        border = tc.get("border", "#444444")

        self.setStyleSheet(f"""
            QWidget#HelpWindow {{
                background-color: {surface2};
                border: 1px solid {border};
                border-left: 2px solid {accent};
            }}
            QWidget#HelpWindowHeader {{
                background-color: {bg};
            }}
            QLabel#HelpWindowTitle {{
                color: {accent};
                background: transparent;
                border: none;
            }}
            QPushButton#HelpWindowCloseButton {{
                background: transparent;
                color: {text2};
                border: none;
                font-size: 14px;
            }}
            QPushButton#HelpWindowCloseButton:hover {{
                background-color: rgba(255,255,255,30);
                border-radius: 4px;
            }}
            QWidget#HelpWindowContent {{
                background-color: {surface2};
            }}
            QScrollArea {{
                background-color: {surface2};
                border: none;
            }}
        """)

        for i in range(self._content_layout.count()):
            item = self._content_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, QLabel):
                    obj = w.objectName()
                    if obj == "HelpSectionHeading":
                        w.setStyleSheet(
                            f"color: {accent}; background: transparent; border: none; font-weight: bold;"
                        )
                    elif obj == "HelpSectionContent":
                        w.setStyleSheet(
                            f"color: {text2}; background: transparent; border: none;"
                        )
                    elif obj == "HelpSectionSeparator":
                        w.setStyleSheet(
                            f"background-color: {border}; border: none; max-height: 1px;"
                        )
                elif isinstance(w, QPushButton) and w.objectName() == "HelpRelatedButton":
                    w.setStyleSheet(
                        f"QPushButton {{ color: {accent}; background: transparent; border: none; "
                        f"font-size: 10px; text-align: left; padding: 4px 0; }} "
                        f"QPushButton:hover {{ color: {tc.get('accent_hover', '#3de878')}; text-decoration: underline; }}"
                    )

    def _update_icons(self):
        tc = ThemeEngine().get_current_colors()
        color = tc.get("text_secondary", "#a0a0b0")
        self._btn_close.setIcon(get_icon("x", color, 16))

    def sync_position(self):
        if self._syncing_position:
            return
        self._syncing_position = True
        try:
            if self._main_window and self._main_window.isVisible():
                main_geo = self._main_window.geometry()
                main_screen = self._main_window.screen()
                if main_screen:
                    screen_geo = main_screen.availableGeometry()
                    x = main_geo.right()
                    y = main_geo.top()
                    h = main_geo.height()
                    if x + self.width() > screen_geo.right():
                        x = main_geo.left() - self.width()
                    if x < screen_geo.left():
                        x = screen_geo.left()
                    self.setGeometry(x, y, self.width(), h)
        finally:
            self._syncing_position = False

    def show_help(self, help_id: str):
        data = HELP_DATA.get(help_id)
        if not data:
            return

        self._current_help_id = help_id
        self._lbl_title.setText(f"📖 {data['title']}")

        self._clear_content()

        tc = ThemeEngine().get_current_colors()
        accent = tc.get("accent", "#32c864")
        text2 = tc.get("text_secondary", "#a0a0b0")
        border = tc.get("border", "#444444")
        surface2 = tc.get("surface_alt", "#222240")

        for i, section in enumerate(data["sections"]):
            if i > 0:
                sep = QFrame()
                sep.setObjectName("HelpSectionSeparator")
                sep.setFixedHeight(1)
                sep.setStyleSheet(f"background-color: {border}; border: none;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, sep)
                margin = QWidget()
                margin.setFixedHeight(8)
                margin.setStyleSheet(f"background-color: {surface2}; border: none;")
                self._content_layout.insertWidget(self._content_layout.count() - 1, margin)

            heading = QLabel(section["heading"])
            heading.setObjectName("HelpSectionHeading")
            heading.setFont(_make_font(10, bold=True))
            heading.setWordWrap(True)
            heading.setStyleSheet(f"color: {accent}; background: transparent; border: none; font-weight: bold;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, heading)

            content = QLabel(section["content"])
            content.setObjectName("HelpSectionContent")
            content.setFont(_make_font(9))
            content.setWordWrap(True)
            content.setTextInteractionFlags(Qt.TextSelectableByMouse)
            content.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, content)

            spacer = QWidget()
            spacer.setFixedHeight(4)
            spacer.setStyleSheet(f"background-color: {surface2}; border: none;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, spacer)

        related = RELATED_HELP.get(help_id, [])
        if related:
            sep = QFrame()
            sep.setObjectName("HelpSectionSeparator")
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background-color: {border}; border: none;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, sep)

            related_label = QLabel("相关帮助")
            related_label.setFont(_make_font(9, bold=True))
            related_label.setStyleSheet(f"color: {text2}; background: transparent; border: none;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, related_label)

            for rid in related:
                rdata = HELP_DATA.get(rid)
                if rdata:
                    btn = QPushButton(f"→ {rdata['title']}")
                    btn.setObjectName("HelpRelatedButton")
                    btn.setFont(_make_font(10))
                    btn.setCursor(Qt.PointingHandCursor)
                    btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                    btn.setStyleSheet(
                        f"QPushButton {{ color: {accent}; background: transparent; border: none; "
                        f"font-size: 10px; text-align: left; padding: 4px 0; }} "
                        f"QPushButton:hover {{ color: {tc.get('accent_hover', '#3de878')}; text-decoration: underline; }}"
                    )
                    btn.clicked.connect(lambda checked, h=rid: self.show_help(h))
                    self._content_layout.insertWidget(self._content_layout.count() - 1, btn)

        self.sync_position()
        self.show()
        self._scroll.verticalScrollBar().setValue(0)

    def _clear_content(self):
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_close(self):
        self._current_help_id = None
        self.hide()

    def closeEvent(self, event):
        event.ignore()
        self._current_help_id = None
        self.hide()

    def refresh_style(self):
        self._apply_style()
        self._update_icons()
        if self._current_help_id:
            help_id = self._current_help_id
            self._current_help_id = None
            self.show_help(help_id)

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate:
            pass
        return super().event(event)
