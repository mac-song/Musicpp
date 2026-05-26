from PySide6.QtWidgets import (
    QDialog, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QProgressBar,
)
from PySide6.QtCore import Qt, Signal


class ThemedDialog(QDialog):
    def __init__(self, parent=None, title="", width=420, height=0):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setModal(True)
        self._drag_pos = None
        self._title_text = title
        self._fixed_width = width
        self._fixed_height = height
        self._result_code = 0

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._title_bar = QWidget()
        self._title_bar.setObjectName("ThemedDialogTitleBar")
        self._title_bar.setFixedHeight(32)
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(8, 0, 0, 0)
        title_layout.setSpacing(0)

        self._title_label = QLabel(self._title_text)
        self._title_label.setObjectName("ThemedDialogTitleLabel")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()

        self._btn_close = QPushButton()
        self._btn_close.setObjectName("ThemedDialogCloseButton")
        self._btn_close.setFixedSize(40, 32)
        self._btn_close.clicked.connect(self.reject)
        title_layout.addWidget(self._btn_close)

        main_layout.addWidget(self._title_bar)

        self._body = QWidget()
        self._body.setObjectName("ThemedDialogBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(20, 16, 20, 20)
        self._body_layout.setSpacing(12)

        main_layout.addWidget(self._body)

        if self._fixed_width:
            self.setFixedWidth(self._fixed_width)
        if self._fixed_height:
            self.setFixedHeight(self._fixed_height + 32)

        self._title_bar.mousePressEvent = self._on_title_press
        self._title_bar.mouseMoveEvent = self._on_title_move
        self._title_bar.mouseReleaseEvent = self._on_title_release

    def _apply_style(self):
        from src.infrastructure.theme_engine import ThemeEngine
        from src.utils.svg_icons import get_icon
        c = ThemeEngine().get_current_colors()

        bg = c.get("window_bg", "#1a1a2e")
        border = c.get("border", "#333355")
        text = c.get("text_primary", "#e0e0e0")
        text_sec = c.get("text_secondary", "#a0a0b0")
        btn_hover = c.get("button_bg_hover", "rgba(255,255,255,40)")
        btn_pressed = c.get("button_bg_pressed", "rgba(255,255,255,60)")
        danger = c.get("danger", "#e05050")
        accent = c.get("accent", "#32c864")
        btn_bg = c.get("button_bg", "rgba(255,255,255,20)")
        btn_text = c.get("button_text", "#dddddd")

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg};
            }}
            #ThemedDialogTitleBar {{
                background-color: {bg};
                border-bottom: 1px solid {border};
            }}
            #ThemedDialogTitleLabel {{
                color: {text};
                font: bold 12px 'Microsoft YaHei';
                padding-left: 4px;
                background: transparent;
                border: none;
            }}
            #ThemedDialogCloseButton {{
                background-color: transparent;
                color: {text_sec};
                border: none;
                font-size: 16px;
            }}
            #ThemedDialogCloseButton:hover {{
                background-color: {danger};
                color: white;
            }}
            #ThemedDialogCloseButton:pressed {{
                background-color: {danger};
                color: white;
            }}
            #ThemedDialogBody {{
                background-color: {bg};
            }}
            QLabel {{
                color: {text};
                background: transparent;
                border: none;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {btn_text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 20px;
                min-height: 22px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                border-color: {accent};
            }}
            QPushButton:pressed {{
                background-color: {btn_pressed};
            }}
            QPushButton#ThemedDialogAcceptButton {{
                background-color: {accent};
                color: #ffffff;
                border-color: {accent};
                font-weight: bold;
            }}
            QPushButton#ThemedDialogAcceptButton:hover {{
                background-color: {c.get("accent_hover", "#3de878")};
            }}
            QPushButton#ThemedDialogDestructiveButton {{
                background-color: {danger};
                color: #ffffff;
                border-color: {danger};
                font-weight: bold;
            }}
            QPushButton#ThemedDialogDestructiveButton:hover {{
                background-color: #c04040;
            }}
            QRadioButton {{
                color: {text};
                background: transparent;
                border: none;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
                border: 2px solid {border};
                border-radius: 8px;
                background: transparent;
            }}
            QRadioButton::indicator:checked {{
                border-color: {accent};
                background-color: {accent};
            }}
            QCheckBox {{
                color: {text};
                background: transparent;
                border: none;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 2px solid {border};
                border-radius: 3px;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                border-color: {accent};
                background-color: {accent};
            }}
            QLineEdit {{
                background-color: {c.get("surface", "#16213e")};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 10px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
            QLineEdit:focus {{
                border-color: {accent};
            }}
            QComboBox {{
                background-color: {c.get("surface", "#16213e")};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 10px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
            QComboBox:hover {{
                border-color: {accent};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c.get("surface", "#16213e")};
                color: {text};
                border: 1px solid {border};
                selection-background-color: {accent};
                selection-color: white;
            }}
            QTableWidget {{
                background-color: {c.get("surface", "#16213e")};
                color: {text};
                border: 1px solid {border};
                gridline-color: {border};
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
            }}
            QTableWidget::item:selected {{
                background-color: {accent};
                color: white;
            }}
            QHeaderView::section {{
                background-color: {c.get("surface_alt", "#222240")};
                color: {text_sec};
                border: none;
                border-bottom: 1px solid {border};
                padding: 6px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QScrollArea {{
                background-color: {bg};
                border: none;
            }}
            QProgressBar {{
                background-color: {c.get("surface", "#16213e")};
                border: 1px solid {border};
                border-radius: 4px;
                text-align: center;
                color: {text};
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                min-height: 18px;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 3px;
            }}
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: rgba(255,255,255,40);
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: rgba(255,255,255,60);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 8px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background-color: rgba(255,255,255,40);
                border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: rgba(255,255,255,60);
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            QDialogButtonBox {{
                background: transparent;
                border: none;
            }}
            QDialogButtonBox QPushButton {{
                background-color: {btn_bg};
                color: {btn_text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 20px;
                min-height: 22px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background-color: {btn_hover};
                border-color: {accent};
            }}
        """)

        icon_color = c.get("text_primary", "#cccccc")
        self._btn_close.setIcon(get_icon("x", icon_color, 16))

    def body_layout(self):
        return self._body_layout

    def _on_title_press(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def _on_title_move(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def _on_title_release(self, event):
        self._drag_pos = None

    def exec(self):
        if self.parent():
            top = self.parent().window() if hasattr(self.parent(), 'window') else self.parent()
            parent_geo = top.geometry()
            x = parent_geo.center().x() - self.width() // 2
            y = parent_geo.center().y() - self.height() // 2
            self.move(x, y)
        return super().exec()


class ThemedMessageBox(ThemedDialog):
    accepted = Signal()

    def __init__(self, parent=None, icon_type="info", title="", message="",
                 buttons=None, default_button=None):
        super().__init__(parent, title)
        self._icon_type = icon_type
        self._message = message
        self._buttons = buttons or [("ok", "OK")]
        self._default_button = default_button
        self._clicked_button = None
        self._build_content()

    def _build_content(self):
        icon_colors = {
            "info": ("ℹ", "#5090d0"),
            "warning": ("⚠", "#e0a830"),
            "question": ("❓", "#5090d0"),
            "error": ("✕", "#e05050"),
        }
        icon_char, icon_color = icon_colors.get(self._icon_type, ("ℹ", "#5090d0"))

        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        icon_label = QLabel(icon_char)
        icon_label.setObjectName("ThemedMessageBoxIcon")
        icon_label.setFixedSize(36, 36)
        icon_label.setAlignment(Qt.AlignCenter)
        from src.infrastructure.theme_engine import ThemeEngine
        c = ThemeEngine().get_current_colors()
        icon_label.setStyleSheet(f"""
            #ThemedMessageBoxIcon {{
                color: {icon_color};
                font-size: 24px;
                font-weight: bold;
                background: transparent;
                border: none;
            }}
        """)
        content_layout.addWidget(icon_label, 0, Qt.AlignTop)

        msg_label = QLabel(self._message)
        msg_label.setWordWrap(True)
        msg_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg_label.setStyleSheet("font-size: 13px; line-height: 1.5;")
        content_layout.addWidget(msg_label, 1)

        self._body_layout.addLayout(content_layout)
        self._body_layout.addSpacing(8)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        for btn_id, btn_text in self._buttons:
            btn = QPushButton(btn_text)
            if btn_id in ("yes", "ok", "accept"):
                btn.setObjectName("ThemedDialogAcceptButton")
            elif btn_id in ("destructive",):
                btn.setObjectName("ThemedDialogDestructiveButton")

            btn.clicked.connect(lambda checked=False, bid=btn_id: self._on_button_clicked(bid))

            if self._default_button and btn_id == self._default_button:
                btn.setDefault(True)
                btn.setFocus()

            btn_layout.addWidget(btn)

        self._body_layout.addLayout(btn_layout)

        self.adjustSize()
        if self.width() < 360:
            self.setFixedWidth(360)

    def _on_button_clicked(self, btn_id):
        self._clicked_button = btn_id
        if btn_id in ("yes", "ok", "accept"):
            self._result_code = 1
            self.accept()
        elif btn_id in ("no", "cancel", "reject"):
            self._result_code = 0
            self.reject()
        else:
            self._result_code = 0
            self.reject()

    @staticmethod
    def information(parent, title, message, buttons=None, default_button=None):
        dlg = ThemedMessageBox(parent, "info", title, message, buttons, default_button)
        dlg.exec()
        return dlg._result_code

    @staticmethod
    def warning(parent, title, message, buttons=None, default_button=None):
        dlg = ThemedMessageBox(parent, "warning", title, message, buttons, default_button)
        dlg.exec()
        return dlg._result_code

    @staticmethod
    def question(parent, title, message, buttons=None, default_button=None):
        dlg = ThemedMessageBox(parent, "question", title, message, buttons, default_button)
        dlg.exec()
        return dlg._result_code

    @staticmethod
    def critical(parent, title, message, buttons=None, default_button=None):
        dlg = ThemedMessageBox(parent, "error", title, message, buttons, default_button)
        dlg.exec()
        return dlg._result_code


class ThemedInputDialog(ThemedDialog):
    def __init__(self, parent=None, title="", label="", text="", mode="text",
                 items=None, editable=True, width=380):
        super().__init__(parent, title, width=width)
        self._input_value = None
        self._mode = mode
        self._build_input(label, text, items, editable)

    def _build_input(self, label_text, default_text, items, editable):
        label = QLabel(label_text)
        label.setWordWrap(True)
        self._body_layout.addWidget(label)

        if self._mode == "item" and items:
            self._combo = QComboBox()
            self._combo.addItems(items)
            self._combo.setEditable(editable)
            if default_text and default_text in items:
                self._combo.setCurrentIndex(items.index(default_text))
            self._body_layout.addWidget(self._combo)
        else:
            self._line_edit = QLineEdit()
            self._line_edit.setText(default_text)
            self._line_edit.selectAll()
            self._body_layout.addWidget(self._line_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_ok = QPushButton("OK")
        btn_ok.setObjectName("ThemedDialogAcceptButton")
        btn_ok.clicked.connect(self._on_accept)
        btn_ok.setDefault(True)
        btn_layout.addWidget(btn_ok)

        self._body_layout.addLayout(btn_layout)

        self.adjustSize()

    def _on_accept(self):
        if self._mode == "item" and hasattr(self, '_combo'):
            self._input_value = self._combo.currentText()
        elif hasattr(self, '_line_edit'):
            self._input_value = self._line_edit.text()
        self._result_code = 1
        self.accept()

    def get_value(self):
        return self._input_value

    @staticmethod
    def getText(parent, title, label, text="", width=380):
        dlg = ThemedInputDialog(parent, title, label, text, mode="text", width=width)
        if dlg.exec() == QDialog.Accepted:
            return dlg.get_value(), True
        return "", False

    @staticmethod
    def getItem(parent, title, label, items, current=0, editable=True, width=380):
        default = items[current] if 0 <= current < len(items) else ""
        dlg = ThemedInputDialog(parent, title, label, default, mode="item",
                                items=items, editable=editable, width=width)
        if dlg.exec() == QDialog.Accepted:
            return dlg.get_value(), True
        return "", False


class ThemedProgressDialog(ThemedDialog):
    def __init__(self, parent=None, title="", label_text="", minimum=0, maximum=100,
                 cancel_button_text=None, width=380):
        super().__init__(parent, title, width=width)
        self._canceled = False
        self._build_progress(label_text, minimum, maximum, cancel_button_text)

    def _build_progress(self, label_text, minimum, maximum, cancel_button_text):
        self._progress_label = QLabel(label_text)
        self._progress_label.setWordWrap(True)
        self._body_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(minimum, maximum)
        self._progress_bar.setValue(minimum)
        self._body_layout.addWidget(self._progress_bar)

        if cancel_button_text:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            self._btn_cancel = QPushButton(cancel_button_text)
            self._btn_cancel.clicked.connect(self._on_cancel)
            btn_layout.addWidget(self._btn_cancel)
            self._body_layout.addLayout(btn_layout)
        else:
            self._btn_cancel = None

        self.adjustSize()

    def _on_cancel(self):
        self._canceled = True
        self.reject()

    def was_canceled(self):
        return self._canceled

    def set_minimum_duration(self, ms):
        pass

    def set_value(self, value):
        self._progress_bar.setValue(value)

    def set_label(self, text):
        self._progress_label.setText(text)


