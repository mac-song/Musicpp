import os
import sys
import time
import ctypes
from ctypes import wintypes
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSettings, QPoint, QEvent
from PySide6.QtGui import QFont, QColor, QKeyEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QSlider, QProgressBar, QStackedWidget,
    QScrollArea, QFileDialog, QSizePolicy, QFrame,
    QGroupBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QApplication,
)

from src.presentation.themed_dialog import ThemedMessageBox
from src.presentation.help_panel import HelpWindow

from src.business.study_manager import StudyManager, StudyMaterial
from src.infrastructure.subtitle_parser import SubtitleLine, SubtitleParser
from src.infrastructure.theme_engine import ThemeEngine
from src.utils.logger import setup_logger, log_msgbox
from src.business.i18n_service import I18n
from src.utils.svg_icons import get_icon

logger = setup_logger(__name__)

FONT = "Microsoft YaHei"
PAGE_LIBRARY = 0
PAGE_IMPORT = 1
PAGE_SUBTITLE = 2
PAGE_SEGMENT = 3

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


class ImportWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(object)
    batch_finished = Signal(list)
    error = Signal(str)

    def __init__(self, mode, **kwargs):
        super().__init__()
        self._mode = mode
        self._kwargs = kwargs

    def run(self):
        try:
            mgr = StudyManager()
            if self._mode == "url":
                result = mgr.import_from_url(
                    self._kwargs["url"],
                    self._kwargs.get("lang", "en"),
                    self._kwargs.get("lang_secondary", ""),
                    lambda msg, pct: self.progress.emit(msg, pct),
                )
                if result:
                    self.finished.emit(result)
                else:
                    self.error.emit(I18n.t("study.msg.import_failed"))
            elif self._mode == "file":
                result = mgr.import_from_file(
                    self._kwargs["file_path"],
                    lambda msg, pct: self.progress.emit(msg, pct),
                    self._kwargs.get("subtitle_path", ""),
                )
                if result:
                    self.finished.emit(result)
                else:
                    self.error.emit(I18n.t("study.msg.import_failed"))
            elif self._mode == "folder":
                results = mgr.import_from_folder(
                    self._kwargs["folder_path"],
                    lambda msg, pct: self.progress.emit(msg, pct),
                )
                if results:
                    self.batch_finished.emit(results)
                else:
                    self.error.emit(I18n.t("study.msg.folder_empty"))
        except Exception as e:
            self.error.emit(str(e))


class SegmentWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, audio_path, threshold, min_silence, min_segment):
        super().__init__()
        self._audio_path = audio_path
        self._threshold = threshold
        self._min_silence = min_silence
        self._min_segment = min_segment

    def run(self):
        try:
            from src.infrastructure.audio_segmenter import AudioSegmenter
            segments = AudioSegmenter.detect_segments(
                self._audio_path,
                silence_threshold=self._threshold,
                min_silence_ms=self._min_silence,
                min_segment_ms=self._min_segment,
            )
            if segments:
                self.finished.emit(segments)
            else:
                self.error.emit(I18n.t("study.msg.auto_segment_failed"))
        except Exception as e:
            self.error.emit(str(e))


class WhisperWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(str, object)
    error = Signal(str, str)

    def __init__(self, material_id, audio_path, model_name, language, device, hf_mirror_url=""):
        super().__init__()
        self._material_id = material_id
        self._audio_path = audio_path
        self._model_name = model_name
        self._language = language
        self._device = device
        self._hf_mirror_url = hf_mirror_url

    def run(self):
        try:
            from src.business.study_manager import StudyManager
            mgr = StudyManager()
            result = mgr.run_whisper_transcription(
                self._material_id,
                self._audio_path,
                model_name=self._model_name,
                language=self._language,
                device=self._device,
                hf_mirror_url=self._hf_mirror_url,
                progress_callback=lambda msg, pct: self.progress.emit(msg, pct),
            )
            if result:
                self.finished.emit(self._material_id, result)
            else:
                self.error.emit(self._material_id, I18n.t("study.msg.whisper_transcribe_failed"))
        except Exception as e:
            self.error.emit(self._material_id, str(e))


class WordHoverLabel(QLabel):
    word_hovered = Signal(str, object)
    word_clicked = Signal(str, object)
    hover_left = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(350)
        self._hover_timer.timeout.connect(self._on_hover_timeout)
        self._current_word = ""
        self._tooltip = None
        self._detail_panel = None
        self.setMouseTracking(True)

    def _get_char_index_at(self, pos):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.font())
        text = self.text()
        if not text:
            return -1

        doc = self._get_layout()
        if doc is None:
            return -1

        rel_pos = pos
        for i in range(len(text)):
            char_rect = fm.boundingRect(text[:i + 1])
            if rel_pos.x() <= char_rect.width():
                return i
        return len(text) - 1 if text else -1

    def _get_layout(self):
        return self.text()

    def _get_word_at_pos(self, pos):
        text = self.text()
        if not text:
            return ""

        from PySide6.QtGui import QTextLayout
        from PySide6.QtCore import QPointF

        layout = QTextLayout(text, self.font())
        layout.setCacheEnabled(True)

        option = self._text_option()
        layout.setTextOption(option)

        layout.beginLayout()
        lines = []
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(self.width() - self.contentsMargins().left() - self.contentsMargins().right())
            lines.append(line)
        layout.endLayout()

        if not lines:
            return ""

        line_spacing = layout.lineCount()
        first_line_height = lines[0].height() if lines else 0
        line_height = first_line_height
        if line_height <= 0:
            line_height = 1

        target_line = None
        target_line_idx = -1
        y = pos.y()
        for i, ln in enumerate(lines):
            line_y = ln.y()
            line_bottom = line_y + ln.height()
            if line_y <= y <= line_bottom:
                target_line = ln
                target_line_idx = i
                break

        if target_line is None:
            if y < 0 and lines:
                target_line = lines[0]
                target_line_idx = 0
            elif y > 0 and lines:
                target_line = lines[-1]
                target_line_idx = len(lines) - 1
            else:
                return ""

        from_line_start = target_line.textStart()
        from_line_length = target_line.textLength()

        char_idx = -1
        for i in range(from_line_start, from_line_start + from_line_length):
            x_start = target_line.cursorToX(i - from_line_start)[0]
            x_end = target_line.cursorToX(i - from_line_start + 1)[0]
            if x_start <= pos.x() <= x_end:
                char_idx = i
                break

        if char_idx < 0:
            return ""

        from src.presentation.word_tooltip import get_word_at_position
        return get_word_at_position(text, char_idx)

    def _text_option(self):
        from PySide6.QtGui import QTextOption
        option = QTextOption()
        if self.alignment() & Qt.AlignCenter:
            option.setAlignment(Qt.AlignCenter)
        elif self.alignment() & Qt.AlignRight:
            option.setAlignment(Qt.AlignRight)
        else:
            option.setAlignment(Qt.AlignLeft)
        if self.wordWrap():
            option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        else:
            option.setWrapMode(QTextOption.NoWrap)
        return option

    def mouseMoveEvent(self, event):
        word = self._get_word_at_pos(event.position().toPoint() if hasattr(event, 'position') else event.pos())
        if word and word != self._current_word:
            self._current_word = word
            self._hover_timer.start()
            self.setCursor(Qt.PointingHandCursor)
        elif not word and self._current_word:
            self._current_word = ""
            self._hover_timer.stop()
            self._hide_tooltip()
            self.setCursor(Qt.PointingHandCursor)
            self.hover_left.emit()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._current_word = ""
        self._hover_timer.stop()
        self._hide_tooltip()
        self.hover_left.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._current_word:
            self._show_detail(self._current_word)
            return
        super().mousePressEvent(event)

    def _on_hover_timeout(self):
        if not self._current_word:
            return
        self._show_tooltip(self._current_word)

    def _show_tooltip(self, word):
        self._hide_tooltip()

        from src.business.dictionary_service import DictionaryService
        svc = DictionaryService()
        if not svc.is_word_lookup_enabled():
            return

        from src.presentation.word_tooltip import WordTooltip

        self._tooltip = WordTooltip()
        self._tooltip.pin_requested.connect(self._show_detail)

        entry = svc.lookup(word)
        self._tooltip.set_entry(word, entry)

        global_pos = self.cursor().pos()
        self._tooltip.show_at(global_pos)

        if entry is None or entry.source == "offline":
            svc.lookup_offline_then_online(word, self._on_online_result)

    def _on_online_result(self, word, entry, is_online):
        if self._tooltip and self._current_word == word.lower():
            if entry and (self._tooltip._entry is None or self._tooltip._entry.source == "offline"):
                self._tooltip.set_entry(word, entry)

    def _show_detail(self, word, entry=None):
        self._hide_tooltip()

        from src.business.dictionary_service import DictionaryService
        svc = DictionaryService()
        if not svc.is_word_lookup_enabled():
            return

        from src.presentation.word_tooltip import WordDetailPanel

        if entry is None:
            entry = svc.lookup(word)

        self._detail_panel = WordDetailPanel()
        self._detail_panel.set_entry(word, entry)

        global_pos = self.cursor().pos()
        self._detail_panel.show_at(global_pos)

    def _hide_tooltip(self):
        if self._tooltip:
            try:
                self._tooltip.hide()
                self._tooltip.deleteLater()
            except Exception:
                pass
            self._tooltip = None


class SubtitleLineWidget(QWidget):
    clicked = Signal(int)
    ctrl_clicked = Signal(int)
    shift_clicked = Signal(int)

    def __init__(self, line: SubtitleLine, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._line = line
        self._is_current = False
        self._is_played = False
        self._is_selected = False
        self._auto_wrap = True
        self.setCursor(Qt.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        from PySide6.QtGui import QFontMetrics

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignCenter)

        text_font = QFont(FONT, 16, QFont.Normal)
        fm = QFontMetrics(text_font)
        line_h = fm.height() + fm.descent() + 12

        self._text_label = WordHoverLabel(self._line.text)
        self._text_label.setFont(text_font)
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setWordWrap(True)
        self._text_label.setMinimumHeight(line_h)
        self._text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._text_label)

        trans_font = QFont(FONT, 13, QFont.Normal)
        trans_fm = QFontMetrics(trans_font)
        trans_h = trans_fm.height() + trans_fm.descent() + 8

        self._trans_label = QLabel(self._line.translation if self._line.translation else "")
        self._trans_label.setFont(trans_font)
        self._trans_label.setAlignment(Qt.AlignCenter)
        self._trans_label.setWordWrap(True)
        self._trans_label.setTextInteractionFlags(Qt.NoTextInteraction)
        self._trans_label.setMinimumHeight(trans_h)
        self._trans_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._trans_label.setVisible(bool(self._line.translation))
        layout.addWidget(self._trans_label)

        self._update_style()

    def set_current(self, current: bool):
        self._is_current = current
        self._update_style()

    def set_played(self, played: bool):
        self._is_played = played
        self._update_style()

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def set_translation_visible(self, visible: bool):
        self._trans_label.setVisible(visible and bool(self._line.translation))

    def set_auto_wrap(self, wrap: bool):
        self._auto_wrap = wrap
        self._text_label.setWordWrap(wrap)
        if not wrap:
            from PySide6.QtGui import QFontMetrics
            fm = QFontMetrics(self._text_label.font())
            self._text_label.setFixedHeight(fm.height() + fm.descent() + 12)

    def _update_style(self):
        tc = ThemeEngine().get_current_colors()
        if self._is_current:
            color = tc.get("lyric_active", "#32c864")
            self._text_label.setStyleSheet(
                f"color: {color}; font-weight: bold; background: transparent; border: none;"
            )
        elif self._is_selected:
            color = "#e0a030"
            self._text_label.setStyleSheet(
                f"color: {color}; background: rgba(224,160,48,30); border-radius: 3px; border: none;"
            )
        elif self._is_played:
            color = tc.get("lyric_inactive", "#a0a0b0")
            self._text_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        else:
            color = tc.get("lyric_inactive", "#a0a0b0")
            self._text_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")

        bg = "rgba(50,200,100,20)" if self._is_current else (
            "rgba(224,160,48,15)" if self._is_selected else "transparent"
        )
        self.setStyleSheet(f"SubtitleLineWidget {{ background: {bg}; border-radius: 4px; }}")
        self._trans_label.setStyleSheet(
            f"color: {tc.get('text_secondary', '#a0a0b0')}; background: transparent; border: none;"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ControlModifier:
                self.ctrl_clicked.emit(self._index)
            elif event.modifiers() & Qt.ShiftModifier:
                self.shift_clicked.emit(self._index)
            else:
                self.clicked.emit(self._index)
        super().mousePressEvent(event)


class StudyPlayer:
    STATE_STOPPED = "stopped"
    STATE_PLAYING = "playing"
    STATE_PAUSED = "paused"
    STATE_SHADOWING_WAIT = "shadowing_wait"

    def __init__(self):
        self._audio_service = None
        self._material = None
        self._subtitle_lines = []
        self._current_subtitle_index = -1
        self._state = self.STATE_STOPPED
        self._speed = 1.0
        self._position_ms = 0
        self._duration_ms = 0
        self._volume = 80

        self._repeat_mode = 0
        self._repeat_count = 3
        self._repeat_pause_sec = 3
        self._repeat_current = 0
        self._repeat_pausing = False
        self._repeat_range_start = -1
        self._repeat_range_end = -1
        self._repeat_timer = None
        self._auto_next = True

        self._shadowing_mode = False
        self._shadowing_extra_sec = 3
        self._shadowing_timer = None
        self._shadowing_current_sentence_start = -1
        self._shadowing_current_sentence_end = -1

        self._auto_segmented = False
        self._segment_worker = None

        self._position_timer = QTimer()
        self._position_timer.setInterval(100)
        self._position_timer.timeout.connect(self._on_position_tick)

        self._study_start_time = 0
        self._study_elapsed = 0

        self.on_position_changed = None
        self.on_subtitle_changed = None
        self.on_state_changed = None
        self.on_repeat_progress = None
        self.on_repeat_done = None
        self.on_material_finished = None
        self.on_shadowing_wait = None
        self.on_shadowing_resume = None
        self.on_auto_segment_done = None

    def _get_audio_service(self):
        if self._audio_service is None:
            from src.core.audio_service import AudioService
            self._audio_service = AudioService()
        return self._audio_service

    def load_material(self, material: StudyMaterial, subtitle_lines: list):
        self.stop()
        self._material = material
        self._subtitle_lines = subtitle_lines
        self._current_subtitle_index = -1
        self._position_ms = 0
        self._auto_segmented = False

        audio = self._get_audio_service()
        if audio.is_playing():
            audio.stop()

        ok = audio.load_audio(material.audio_path, {"title": material.title, "artist": "Study"})
        if ok:
            self._duration_ms = audio.get_duration() * 1000
            audio.set_volume(self._volume)
            if self._speed != 1.0:
                self._apply_speed(audio)

            if not subtitle_lines:
                from src.business.study_manager import StudyManager
                mgr = StudyManager()
                segments = mgr.load_segments(material.id)
                if segments:
                    self._subtitle_lines = segments
                    self._auto_segmented = True
                    logger.info(f"Loaded {len(segments)} segments from file for {material.id}")
                else:
                    self._try_auto_segment(material.audio_path)

        return ok

    def play(self):
        audio = self._get_audio_service()
        if audio.play():
            self._state = self.STATE_PLAYING
            self._position_timer.start()
            self._study_start_time = time.time()
            if self.on_state_changed:
                self.on_state_changed(self._state)

    def pause(self):
        audio = self._get_audio_service()
        audio.pause()
        self._state = self.STATE_PAUSED
        self._study_elapsed += time.time() - self._study_start_time
        if self.on_state_changed:
            self.on_state_changed(self._state)

    def stop(self):
        self._stop_repeat()
        self._position_timer.stop()
        audio = self._get_audio_service()
        audio.unload()
        self._state = self.STATE_STOPPED
        if self._material:
            self._study_elapsed += time.time() - self._study_start_time
        if self.on_state_changed:
            self.on_state_changed(self._state)

    def toggle_play(self):
        if self._state == self.STATE_PLAYING:
            self.pause()
        else:
            self.play()

    def seek_to_ms(self, ms):
        audio = self._get_audio_service()
        audio.seek(ms / 1000.0)
        self._position_ms = ms
        self._check_subtitle_change()

    def seek_to_subtitle(self, index):
        if 0 <= index < len(self._subtitle_lines):
            line = self._subtitle_lines[index]
            self.seek_to_ms(line.start_ms)

    def set_speed(self, rate):
        self._speed = rate
        audio = self._get_audio_service()
        self._apply_speed(audio)

    def _apply_speed(self, audio):
        try:
            audio.set_speed(self._speed)
        except AttributeError:
            pass

    def set_volume(self, vol):
        self._volume = vol
        audio = self._get_audio_service()
        audio.set_volume(vol)

    def get_position_ms(self):
        return self._position_ms

    def get_duration_ms(self):
        return self._duration_ms

    def get_state(self):
        return self._state

    def start_sentence_repeat(self, subtitle_index, repeat_count=None, pause_sec=None):
        self._stop_repeat()
        self._repeat_mode = 1
        self._repeat_count = repeat_count if repeat_count is not None else 999999
        self._repeat_pause_sec = pause_sec if pause_sec is not None else self._repeat_pause_sec
        self._repeat_current = 0
        self._repeat_range_start = subtitle_index
        self._repeat_range_end = subtitle_index
        self._current_subtitle_index = subtitle_index
        if self.on_subtitle_changed:
            self.on_subtitle_changed(subtitle_index)
        line = self._subtitle_lines[subtitle_index]
        self._position_ms = line.start_ms
        audio = self._get_audio_service()
        audio.seek(line.start_ms / 1000.0)
        if self._state != self.STATE_PLAYING:
            self.play()

    def start_range_repeat(self, start_index, end_index, repeat_count=None):
        self._stop_repeat()
        self._repeat_mode = 2
        self._repeat_count = repeat_count if repeat_count is not None else 999999
        self._repeat_current = 0
        self._repeat_range_start = start_index
        self._repeat_range_end = end_index
        self._current_subtitle_index = start_index
        if self.on_subtitle_changed:
            self.on_subtitle_changed(start_index)
        line = self._subtitle_lines[start_index]
        self._position_ms = line.start_ms
        audio = self._get_audio_service()
        audio.seek(line.start_ms / 1000.0)
        if self._state != self.STATE_PLAYING:
            self.play()

    def stop_repeat(self):
        self._stop_repeat()
        self._repeat_mode = 0

    def get_repeat_mode(self):
        return self._repeat_mode

    def _stop_repeat(self):
        if self._repeat_timer is not None:
            self._repeat_timer.stop()
            self._repeat_timer = None
        self._repeat_pausing = False
        self._repeat_current = 0

    def set_shadowing_mode(self, enabled: bool, extra_sec: int = 3):
        self._shadowing_mode = enabled
        self._shadowing_extra_sec = extra_sec
        if not enabled:
            self._cancel_shadowing_wait()

    def _cancel_shadowing_wait(self):
        if self._shadowing_timer is not None:
            self._shadowing_timer.stop()
            self._shadowing_timer = None
        if self._state == self.STATE_SHADOWING_WAIT:
            self._state = self.STATE_PAUSED
            if self.on_state_changed:
                self.on_state_changed(self._state)

    def _on_shadowing_sentence_end(self):
        if not self._subtitle_lines or self._current_subtitle_index < 0:
            return
        line = self._subtitle_lines[self._current_subtitle_index]
        sentence_duration_ms = line.end_ms - line.start_ms
        wait_ms = sentence_duration_ms + self._shadowing_extra_sec * 1000

        self._shadowing_current_sentence_start = line.start_ms
        self._shadowing_current_sentence_end = line.end_ms

        audio = self._get_audio_service()
        audio.pause()
        self._state = self.STATE_SHADOWING_WAIT
        self._position_timer.stop()
        if self.on_state_changed:
            self.on_state_changed(self._state)
        if self.on_shadowing_wait:
            self.on_shadowing_wait(self._current_subtitle_index, wait_ms)

        self._shadowing_timer = QTimer()
        self._shadowing_timer.setSingleShot(True)
        self._shadowing_timer.timeout.connect(self._on_shadowing_wait_done)
        self._shadowing_timer.start(wait_ms)

    def _on_shadowing_wait_done(self):
        self._shadowing_timer = None
        if self._state != self.STATE_SHADOWING_WAIT:
            return
        next_idx = self._current_subtitle_index + 1
        if next_idx < len(self._subtitle_lines):
            self._current_subtitle_index = next_idx
            if self.on_subtitle_changed:
                self.on_subtitle_changed(next_idx)
            line = self._subtitle_lines[next_idx]
            self._position_ms = line.start_ms
            audio = self._get_audio_service()
            audio.seek(line.start_ms / 1000.0)
            self._state = self.STATE_PLAYING
            self._position_timer.start()
            self._study_start_time = time.time()
            audio.play()
            if self.on_state_changed:
                self.on_state_changed(self._state)
            if self.on_shadowing_resume:
                self.on_shadowing_resume(next_idx)
        else:
            self._state = self.STATE_PAUSED
            if self.on_state_changed:
                self.on_state_changed(self._state)

    def _try_auto_segment(self, audio_path: str):
        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            threshold = int(cm.get("Study", "AutoSegSilenceThreshold", "0"))
            min_silence = int(cm.get("Study", "AutoSegMinSilenceMs", "300"))
            min_segment = int(cm.get("Study", "AutoSegMinSegmentMs", "800"))
        except Exception:
            threshold = 0
            min_silence = 300
            min_segment = 800

        self._segment_worker = SegmentWorker(
            audio_path, threshold, min_silence, min_segment
        )
        self._segment_worker.finished.connect(self._on_auto_segment_done)
        self._segment_worker.error.connect(self._on_auto_segment_error)
        self._segment_worker.start()

    def _on_auto_segment_done(self, segments):
        if self._segment_worker:
            self._segment_worker.wait()
            self._segment_worker = None
        self._subtitle_lines = segments
        self._auto_segmented = True
        logger.info(f"Auto-segmented: {len(segments)} segments")
        if self._material:
            from src.business.study_manager import StudyManager
            mgr = StudyManager()
            mgr.save_segments(self._material.id, segments)
        if self.on_auto_segment_done:
            self.on_auto_segment_done(segments)

    def _on_auto_segment_error(self, msg):
        if self._segment_worker:
            self._segment_worker.wait()
            self._segment_worker = None
        logger.warning(f"Auto-segment failed: {msg}")

    def is_auto_segmented(self) -> bool:
        return self._auto_segmented

    def _on_position_tick(self):
        audio = self._get_audio_service()
        pos_sec = audio.get_position()
        self._position_ms = int(pos_sec * 1000)

        if self.on_position_changed:
            self.on_position_changed(self._position_ms, self._duration_ms)

        self._check_subtitle_change()

        if self._repeat_mode > 0 and self._current_subtitle_index >= 0:
            self._check_repeat_boundary()

        if self._shadowing_mode and self._state == self.STATE_PLAYING and self._current_subtitle_index >= 0:
            self._check_shadowing_boundary()

        if self._material:
            mgr = StudyManager()
            mgr.update_progress(self._material.id, self._position_ms)

    def _check_subtitle_change(self):
        if not self._subtitle_lines:
            return
        new_index = -1
        for i, line in enumerate(self._subtitle_lines):
            if line.start_ms <= self._position_ms < line.end_ms:
                new_index = i
                break
        if new_index != self._current_subtitle_index:
            self._current_subtitle_index = new_index
            if self.on_subtitle_changed:
                self.on_subtitle_changed(new_index)

    def _check_repeat_boundary(self):
        if self._repeat_pausing:
            return
        idx = self._current_subtitle_index
        if idx < 0:
            return

        if self._repeat_mode == 1:
            end_ms = self._subtitle_lines[idx].end_ms
            if self._position_ms >= end_ms - 30:
                self._repeat_current += 1
                if self.on_repeat_progress:
                    self.on_repeat_progress(self._repeat_current, self._repeat_count)
                if self._repeat_current >= self._repeat_count:
                    self._repeat_current = 0
                    self._on_repeat_done()
                else:
                    self._pause_and_replay()

        elif self._repeat_mode == 2:
            if idx > self._repeat_range_end:
                self._repeat_current += 1
                if self.on_repeat_progress:
                    self.on_repeat_progress(self._repeat_current, self._repeat_count)
                if self._repeat_current >= self._repeat_count:
                    self._repeat_current = 0
                    self._on_repeat_done()
                else:
                    self._pause_and_replay()

    def _check_shadowing_boundary(self):
        if self._repeat_mode > 0:
            return
        idx = self._current_subtitle_index
        if idx < 0 or idx >= len(self._subtitle_lines):
            return
        line = self._subtitle_lines[idx]
        if self._position_ms >= line.end_ms - 30:
            self._on_shadowing_sentence_end()

    def _pause_and_replay(self):
        audio = self._get_audio_service()
        idx = self._current_subtitle_index
        if 0 <= idx < len(self._subtitle_lines):
            end_ms = self._subtitle_lines[idx].end_ms
            cur_sec = audio.get_position()
            end_sec = end_ms / 1000.0
            if cur_sec < end_sec:
                audio.seek(end_sec)
        audio.pause()
        self._state = self.STATE_PAUSED
        self._position_timer.stop()
        self._repeat_pausing = True
        if self._repeat_timer is not None:
            self._repeat_timer.stop()
        self._repeat_timer = QTimer()
        self._repeat_timer.setSingleShot(True)
        self._repeat_timer.timeout.connect(self._replay_after_pause)
        self._repeat_timer.start(self._repeat_pause_sec * 1000)

    def _replay_after_pause(self):
        self._repeat_pausing = False
        target = self._repeat_range_start
        if self._repeat_mode == 1:
            target = self._current_subtitle_index
        line = self._subtitle_lines[target]
        self._current_subtitle_index = target
        self._position_ms = line.start_ms
        audio = self._get_audio_service()
        audio.seek(line.start_ms / 1000.0)
        self._state = self.STATE_PLAYING
        self._position_timer.start()
        self._study_start_time = time.time()
        audio.play()
        if self.on_state_changed:
            self.on_state_changed(self._state)

    def _on_repeat_done(self):
        self._stop_repeat()
        self._repeat_mode = 0
        if self.on_repeat_done:
            self.on_repeat_done()
        if self._auto_next and self._current_subtitle_index + 1 < len(self._subtitle_lines):
            next_idx = self._current_subtitle_index + 1
            line = self._subtitle_lines[next_idx]
            self._current_subtitle_index = next_idx
            self._position_ms = line.start_ms
            if self.on_subtitle_changed:
                self.on_subtitle_changed(next_idx)
            audio = self._get_audio_service()
            audio.seek(line.start_ms / 1000.0)
            self._state = self.STATE_PLAYING
            self._position_timer.start()
            self._study_start_time = time.time()
            audio.play()
            if self.on_state_changed:
                self.on_state_changed(self._state)
        else:
            self.pause()


class StudyWindow(QWidget):
    closed = Signal()
    switch_to_full = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mgr = StudyManager()
        self._player = StudyPlayer()
        self._materials = []
        self._current_material_index = -1
        self._subtitle_widgets = []
        self._selected_subtitle_indices = set()
        self._import_worker = None

        self._player.on_position_changed = self._on_player_position
        self._player.on_subtitle_changed = self._on_player_subtitle
        self._player.on_state_changed = self._on_player_state
        self._player.on_repeat_progress = self._on_player_repeat_progress
        self._player.on_repeat_done = self._on_player_repeat_done
        self._player.on_shadowing_wait = self._on_player_shadowing_wait
        self._player.on_shadowing_resume = self._on_player_shadowing_resume
        self._player.on_auto_segment_done = self._on_player_auto_segment_done

        self._init_ui()
        self._help_window = HelpWindow(self)
        self._apply_style()

    def _init_ui(self):
        self.setWindowTitle(I18n.t("study.title"))
        self.setMinimumSize(600, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self._normal_geometry = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_custom_title_bar())
        main_layout.addWidget(self._build_control_bar())

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_library_page())
        self._stack.addWidget(self._build_import_page())
        self._stack.addWidget(self._build_subtitle_page())
        self._stack.addWidget(self._build_segment_page())
        main_layout.addWidget(self._stack, 1)

    def _build_custom_title_bar(self):
        self._title_bar = QWidget()
        self._title_bar.setObjectName("StudyTitleBar")
        self._title_bar.setFixedHeight(32)
        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(8, 0, 0, 0)
        title_layout.setSpacing(0)

        self._title_label = QLabel(I18n.t("study.title"))
        self._title_label.setObjectName("StudyTitleLabel")
        title_layout.addWidget(self._title_label)
        title_layout.addStretch()

        self._btn_title_help = QPushButton()
        self._btn_title_help.setObjectName("StudyTitleBarButton")
        self._btn_title_help.setFixedSize(32, 32)
        self._btn_title_help.setToolTip(I18n.t("help.toggle"))
        self._btn_title_help.clicked.connect(self._toggle_help)
        title_layout.addWidget(self._btn_title_help)

        self._btn_title_minimize = QPushButton()
        self._btn_title_minimize.setObjectName("StudyTitleBarButton")
        self._btn_title_minimize.setFixedSize(40, 32)
        self._btn_title_minimize.clicked.connect(self.showMinimized)
        title_layout.addWidget(self._btn_title_minimize)

        self._btn_title_maximize = QPushButton()
        self._btn_title_maximize.setObjectName("StudyTitleBarButton")
        self._btn_title_maximize.setFixedSize(40, 32)
        self._btn_title_maximize.clicked.connect(self._toggle_maximize)
        title_layout.addWidget(self._btn_title_maximize)

        self._btn_title_close = QPushButton()
        self._btn_title_close.setObjectName("StudyTitleBarCloseButton")
        self._btn_title_close.setFixedSize(40, 32)
        self._btn_title_close.clicked.connect(self.close)
        title_layout.addWidget(self._btn_title_close)

        self._title_bar_drag_pos = None
        self._title_bar.mousePressEvent = self._on_title_bar_press
        self._title_bar.mouseMoveEvent = self._on_title_bar_move
        self._title_bar.mouseReleaseEvent = self._on_title_bar_release
        self._title_bar.mouseDoubleClickEvent = self._on_title_bar_double_click

        return self._title_bar

    def _update_maximize_icon(self):
        tc = ThemeEngine().get_current_colors()
        icon_color = tc.get("text_primary", "#cccccc")
        if self.isMaximized():
            self._btn_title_maximize.setIcon(get_icon("minimize-2", icon_color, 16))
        else:
            self._btn_title_maximize.setIcon(get_icon("maximize-2", icon_color, 16))

    def _toggle_maximize(self):
        if self.isMaximized():
            if self._normal_geometry:
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
            if not self.isMaximized() and self._normal_geometry:
                self.setGeometry(self._normal_geometry)

    def _on_title_bar_press(self, event):
        if event.button() == Qt.LeftButton:
            self._title_bar_drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _on_title_bar_move(self, event):
        if event.buttons() & Qt.LeftButton and self._title_bar_drag_pos:
            if self.isMaximized():
                if self._normal_geometry:
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

    def nativeEvent(self, eventType, message):
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            try:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST:
                    from PySide6.QtGui import QCursor
                    cursor_pos = QCursor.pos()

                    for btn in [self._btn_title_help, self._btn_title_minimize, self._btn_title_maximize, self._btn_title_close]:
                        local_pos = btn.mapFromGlobal(cursor_pos)
                        if btn.rect().contains(local_pos):
                            return super().nativeEvent(eventType, message)

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

    def _build_control_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._btn_import = QPushButton()
        self._btn_import.setFixedSize(32, 28)
        self._btn_import.setToolTip(I18n.t("study.btn.import_material"))
        self._btn_import.clicked.connect(lambda: self._switch_page(PAGE_IMPORT))
        row1.addWidget(self._btn_import)

        self._btn_play = QPushButton()
        self._btn_play.setFixedSize(32, 28)
        self._btn_play.setToolTip(I18n.t("study.btn.play"))
        self._btn_play.clicked.connect(self._on_toggle_play)
        row1.addWidget(self._btn_play)

        self._btn_prev = QPushButton()
        self._btn_prev.setFixedSize(32, 28)
        self._btn_prev.setToolTip(I18n.t("study.btn.prev_material"))
        self._btn_prev.clicked.connect(self._on_prev_material)
        row1.addWidget(self._btn_prev)

        self._btn_next = QPushButton()
        self._btn_next.setFixedSize(32, 28)
        self._btn_next.setToolTip(I18n.t("study.btn.next_material"))
        self._btn_next.clicked.connect(self._on_next_material)
        row1.addWidget(self._btn_next)

        row1.addSpacing(8)

        self._btn_prev_sentence = QPushButton()
        self._btn_prev_sentence.setFixedSize(28, 28)
        self._btn_prev_sentence.setToolTip(I18n.t("study.btn.prev_sentence"))
        self._btn_prev_sentence.clicked.connect(self._on_prev_sentence)
        row1.addWidget(self._btn_prev_sentence)

        self._btn_next_sentence = QPushButton()
        self._btn_next_sentence.setFixedSize(28, 28)
        self._btn_next_sentence.setToolTip(I18n.t("study.btn.next_sentence"))
        self._btn_next_sentence.clicked.connect(self._on_next_sentence)
        row1.addWidget(self._btn_next_sentence)

        self._btn_repeat_current = QPushButton()
        self._btn_repeat_current.setFixedSize(28, 28)
        self._btn_repeat_current.setToolTip(I18n.t("study.btn.repeat_current"))
        self._btn_repeat_current.clicked.connect(self._on_repeat_current_sentence)
        row1.addWidget(self._btn_repeat_current)

        self._btn_back_5 = QPushButton()
        self._btn_back_5.setFixedSize(28, 28)
        self._btn_back_5.setToolTip(I18n.t("study.btn.back_5"))
        self._btn_back_5.clicked.connect(lambda: self._on_jump_sentences(-5))
        row1.addWidget(self._btn_back_5)

        self._btn_forward_5 = QPushButton()
        self._btn_forward_5.setFixedSize(28, 28)
        self._btn_forward_5.setToolTip(I18n.t("study.btn.forward_5"))
        self._btn_forward_5.clicked.connect(lambda: self._on_jump_sentences(5))
        row1.addWidget(self._btn_forward_5)

        self._btn_first_sentence = QPushButton()
        self._btn_first_sentence.setFixedSize(28, 28)
        self._btn_first_sentence.setToolTip(I18n.t("study.btn.first_sentence"))
        self._btn_first_sentence.clicked.connect(self._on_first_sentence)
        row1.addWidget(self._btn_first_sentence)

        self._btn_last_sentence = QPushButton()
        self._btn_last_sentence.setFixedSize(28, 28)
        self._btn_last_sentence.setToolTip(I18n.t("study.btn.last_sentence"))
        self._btn_last_sentence.clicked.connect(self._on_last_sentence)
        row1.addWidget(self._btn_last_sentence)

        self._btn_shadowing = QPushButton()
        self._btn_shadowing.setFixedSize(28, 28)
        self._btn_shadowing.setCheckable(True)
        self._btn_shadowing.setToolTip(I18n.t("study.btn.shadowing"))
        self._btn_shadowing.clicked.connect(self._on_toggle_shadowing)
        row1.addWidget(self._btn_shadowing)

        self._btn_subtitle_toggle = QPushButton()
        self._btn_subtitle_toggle.setFixedSize(28, 28)
        self._btn_subtitle_toggle.setCheckable(True)
        self._btn_subtitle_toggle.setToolTip(I18n.t("study.btn.subtitle"))
        self._btn_subtitle_toggle.clicked.connect(self._on_toggle_subtitle)
        row1.addWidget(self._btn_subtitle_toggle)

        self._combo_speed = QComboBox()
        self._combo_speed.setFixedWidth(58)
        self._combo_speed.setFixedHeight(28)
        self._combo_speed.addItems(["0.5x", "0.8x", "1.0x", "1.2x", "1.5x", "2.0x"])
        self._combo_speed.setCurrentIndex(2)
        self._combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        row1.addWidget(self._combo_speed)

        self._lbl_repeat_status = QLabel("")
        self._lbl_repeat_status.setFont(QFont(FONT, 9))
        self._lbl_repeat_status.setFixedHeight(28)
        row1.addWidget(self._lbl_repeat_status)

        row1.addStretch()

        self._btn_dict_toggle = QPushButton()
        self._btn_dict_toggle.setFixedSize(28, 28)
        self._btn_dict_toggle.setCheckable(True)
        self._btn_dict_toggle.setChecked(True)
        self._btn_dict_toggle.setToolTip(I18n.t("study.btn.dict_toggle"))
        self._btn_dict_toggle.clicked.connect(self._on_toggle_dict_lookup)
        row1.addWidget(self._btn_dict_toggle)

        self._btn_full = QPushButton()
        self._btn_full.setFixedSize(32, 28)
        self._btn_full.setToolTip(I18n.t("study.btn.full_mode"))
        self._btn_full.clicked.connect(self._on_full_mode)
        row1.addWidget(self._btn_full)

        bar_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self._slider_progress = QSlider(Qt.Horizontal)
        self._slider_progress.setRange(0, 1000)
        self._slider_progress.setValue(0)
        self._slider_progress.sliderMoved.connect(self._on_progress_slider_moved)
        self._slider_progress.sliderPressed.connect(self._on_progress_slider_pressed)
        self._slider_progress.sliderReleased.connect(self._on_progress_slider_released)
        row2.addWidget(self._slider_progress, 1)

        self._lbl_time = QLabel("0:00 / 0:00")
        self._lbl_time.setFont(QFont(FONT, 9))
        self._lbl_time.setFixedWidth(100)
        row2.addWidget(self._lbl_time)

        self._btn_volume_icon = QPushButton()
        self._btn_volume_icon.setFixedSize(24, 24)
        self._btn_volume_icon.clicked.connect(self._on_mute_toggle)
        row2.addWidget(self._btn_volume_icon)

        self._slider_volume = QSlider(Qt.Horizontal)
        self._slider_volume.setRange(0, 100)
        self._slider_volume.setValue(80)
        self._slider_volume.setFixedWidth(80)
        self._slider_volume.valueChanged.connect(self._on_volume_changed)
        row2.addWidget(self._slider_volume)

        bar_layout.addLayout(row2)

        self._update_control_icons()
        return bar

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(16, 12, 16, 8)
        lbl = QLabel(I18n.t("study.lbl.learning_materials"))
        lbl.setFont(QFont(FONT, 14, QFont.Bold))
        header.addWidget(lbl)
        header.addStretch()

        btn_refresh = QPushButton()
        btn_refresh.setFixedSize(28, 28)
        btn_refresh.setToolTip(I18n.t("study.btn.refresh"))
        btn_refresh.clicked.connect(self._refresh_library)
        header.addWidget(btn_refresh)
        self._lib_btn_refresh = btn_refresh

        btn_batch_del = QPushButton()
        btn_batch_del.setFixedSize(28, 28)
        btn_batch_del.setToolTip(I18n.t("study.btn.batch_delete"))
        btn_batch_del.clicked.connect(self._on_batch_delete)
        header.addWidget(btn_batch_del)
        self._lib_btn_batch_del = btn_batch_del

        layout.addLayout(header)

        self._lib_table = QTableWidget()
        self._lib_table.setColumnCount(6)
        self._lib_table.setHorizontalHeaderLabels([I18n.t("study.col.name"), I18n.t("study.col.import_time"), I18n.t("study.col.subtitle"), I18n.t("study.col.study_duration"), I18n.t("study.col.completion"), I18n.t("study.col.actions")])
        self._lib_table.verticalHeader().setVisible(False)
        self._lib_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._lib_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self._lib_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._lib_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 6):
            self._lib_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._lib_table.setShowGrid(False)
        self._lib_table.setAlternatingRowColors(True)
        self._lib_table.doubleClicked.connect(self._on_table_double_clicked)
        self._lib_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._lib_table.customContextMenuRequested.connect(self._on_table_context_menu)
        layout.addWidget(self._lib_table, 1)

        return page

    def _build_import_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        back_row = QHBoxLayout()
        back_row.addStretch()
        self._btn_import_back = QPushButton()
        self._btn_import_back.setFixedSize(28, 28)
        self._btn_import_back.setToolTip(I18n.t("study.btn.back_to_library"))
        self._btn_import_back.clicked.connect(lambda: self._switch_page(PAGE_LIBRARY))
        back_row.addWidget(self._btn_import_back)
        layout.addLayout(back_row)

        url_group = QGroupBox(I18n.t("study.group.import_url"))
        url_group.setFont(QFont(FONT, 10))
        url_layout = QVBoxLayout(url_group)
        url_layout.setSpacing(8)

        url_row = QHBoxLayout()
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText(I18n.t("study.placeholder.url"))
        self._url_input.setFont(QFont(FONT, 9))
        self._url_input.returnPressed.connect(self._on_import_url)
        url_row.addWidget(self._url_input, 1)

        self._btn_import_url = QPushButton(I18n.t("study.btn.import"))
        self._btn_import_url.setFont(QFont(FONT, 9))
        self._btn_import_url.setFixedWidth(70)
        self._btn_import_url.clicked.connect(self._on_import_url)
        url_row.addWidget(self._btn_import_url)
        url_layout.addLayout(url_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(I18n.t("study.lbl.subtitle_lang")))
        self._combo_lang = QComboBox()
        self._combo_lang.setFont(QFont(FONT, 9))
        self._combo_lang.addItems(["en", "zh-Hans", "ja", "ko", "fr", "de", "es"])
        self._combo_lang.setCurrentText("en")
        self._combo_lang.setFixedWidth(90)
        lang_row.addWidget(self._combo_lang)
        lang_row.addSpacing(16)
        lang_row.addWidget(QLabel(I18n.t("study.lbl.secondary_lang")))
        self._combo_lang_secondary = QComboBox()
        self._combo_lang_secondary.setFont(QFont(FONT, 9))
        self._combo_lang_secondary.addItem(I18n.t("study.lbl.none"))
        self._combo_lang_secondary.addItems(["en", "zh-Hans", "ja", "ko", "fr", "de", "es"])
        self._combo_lang_secondary.setFixedWidth(90)
        lang_row.addWidget(self._combo_lang_secondary)
        lang_row.addStretch()
        url_layout.addLayout(lang_row)

        layout.addWidget(url_group)

        local_group = QGroupBox(I18n.t("study.group.import_local"))
        local_group.setFont(QFont(FONT, 10))
        local_layout = QVBoxLayout(local_group)
        local_layout.setSpacing(8)

        local_row = QHBoxLayout()
        self._local_path = QLineEdit()
        self._local_path.setPlaceholderText(I18n.t("study.placeholder.local_file"))
        self._local_path.setFont(QFont(FONT, 9))
        self._local_path.setReadOnly(True)
        local_row.addWidget(self._local_path, 1)

        btn_browse = QPushButton(I18n.t("study.btn.browse"))
        btn_browse.setFont(QFont(FONT, 9))
        btn_browse.setFixedWidth(60)
        btn_browse.clicked.connect(self._on_browse_file)
        local_row.addWidget(btn_browse)

        self._btn_import_file = QPushButton(I18n.t("study.btn.import"))
        self._btn_import_file.setFont(QFont(FONT, 9))
        self._btn_import_file.setFixedWidth(60)
        self._btn_import_file.clicked.connect(self._on_import_file)
        local_row.addWidget(self._btn_import_file)
        local_layout.addLayout(local_row)

        sub_row = QHBoxLayout()
        self._local_sub_path = QLineEdit()
        self._local_sub_path.setPlaceholderText(I18n.t("study.placeholder.subtitle_file"))
        self._local_sub_path.setFont(QFont(FONT, 9))
        self._local_sub_path.setReadOnly(True)
        sub_row.addWidget(self._local_sub_path, 1)

        btn_browse_sub = QPushButton(I18n.t("study.btn.browse"))
        btn_browse_sub.setFont(QFont(FONT, 9))
        btn_browse_sub.setFixedWidth(60)
        btn_browse_sub.clicked.connect(self._on_browse_sub_file)
        sub_row.addWidget(btn_browse_sub)

        btn_clear_sub = QPushButton(I18n.t("study.btn.clear"))
        btn_clear_sub.setFont(QFont(FONT, 9))
        btn_clear_sub.setFixedWidth(50)
        btn_clear_sub.clicked.connect(lambda: self._local_sub_path.setText(""))
        sub_row.addWidget(btn_clear_sub)

        local_layout.addLayout(sub_row)

        folder_row = QHBoxLayout()
        self._local_folder_path = QLineEdit()
        self._local_folder_path.setPlaceholderText(I18n.t("study.placeholder.folder"))
        self._local_folder_path.setFont(QFont(FONT, 9))
        self._local_folder_path.setReadOnly(True)
        folder_row.addWidget(self._local_folder_path, 1)

        btn_browse_folder = QPushButton(I18n.t("study.btn.browse"))
        btn_browse_folder.setFont(QFont(FONT, 9))
        btn_browse_folder.setFixedWidth(60)
        btn_browse_folder.clicked.connect(self._on_browse_folder)
        folder_row.addWidget(btn_browse_folder)

        self._btn_import_folder = QPushButton(I18n.t("study.btn.batch_import"))
        self._btn_import_folder.setFont(QFont(FONT, 9))
        self._btn_import_folder.setFixedWidth(70)
        self._btn_import_folder.clicked.connect(self._on_import_folder)
        folder_row.addWidget(self._btn_import_folder)

        local_layout.addLayout(folder_row)

        layout.addWidget(local_group)

        progress_group = QGroupBox(I18n.t("study.group.import_progress"))
        progress_group.setFont(QFont(FONT, 10))
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(6)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)

        self._lbl_import_status = QLabel("")
        self._lbl_import_status.setFont(QFont(FONT, 9))
        progress_layout.addWidget(self._lbl_import_status)

        layout.addWidget(progress_group)
        layout.addStretch()

        return page

    def _build_subtitle_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 4)
        header_layout.setSpacing(2)

        header_top = QHBoxLayout()
        header_top.setSpacing(8)
        self._lbl_subtitle_title = QLabel("")
        self._lbl_subtitle_title.setFont(QFont(FONT, 12, QFont.Bold))
        header_top.addWidget(self._lbl_subtitle_title)
        header_top.addStretch()

        self._btn_subtitle_repeat = QPushButton(I18n.t("study.btn.repeat"))
        self._btn_subtitle_repeat.setFont(QFont(FONT, 9))
        self._btn_subtitle_repeat.setFixedHeight(22)
        self._btn_subtitle_repeat.setCheckable(True)
        self._btn_subtitle_repeat.setVisible(False)
        self._btn_subtitle_repeat.clicked.connect(self._on_subtitle_repeat_toggle)
        header_top.addWidget(self._btn_subtitle_repeat)

        self._combo_display_mode = QComboBox()
        self._combo_display_mode.setFont(QFont(FONT, 9))
        self._combo_display_mode.setFixedHeight(22)
        self._combo_display_mode.addItem(I18n.t("study.display.original"), "original")
        self._combo_display_mode.addItem(I18n.t("study.display.bilingual"), "bilingual")
        self._combo_display_mode.setVisible(False)
        self._combo_display_mode.currentIndexChanged.connect(self._on_display_mode_changed)
        header_top.addWidget(self._combo_display_mode)

        self._btn_switch_to_segment = QPushButton(I18n.t("study.btn.view_switch"))
        self._btn_switch_to_segment.setFont(QFont(FONT, 9))
        self._btn_switch_to_segment.setFixedHeight(22)
        self._btn_switch_to_segment.clicked.connect(self._on_switch_to_segment)
        header_top.addWidget(self._btn_switch_to_segment)

        header_layout.addLayout(header_top)

        self._lbl_subtitle_source = QLabel("")
        self._lbl_subtitle_source.setFont(QFont(FONT, 9))
        header_layout.addWidget(self._lbl_subtitle_source)

        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._subtitle_container = QWidget()
        self._subtitle_layout = QVBoxLayout(self._subtitle_container)
        self._subtitle_layout.setContentsMargins(10, 8, 10, 8)
        self._subtitle_layout.setSpacing(0)
        self._subtitle_layout.addStretch()

        self._lbl_no_subtitle = QLabel(I18n.t("study.msg.no_subtitle"))
        self._lbl_no_subtitle.setFont(QFont(FONT, 11))
        self._lbl_no_subtitle.setAlignment(Qt.AlignCenter)
        self._lbl_no_subtitle.setVisible(False)
        self._subtitle_layout.insertWidget(0, self._lbl_no_subtitle)

        self._btn_whisper_generate = QPushButton(I18n.t("study.btn.whisper_generate"))
        self._btn_whisper_generate.setFont(QFont(FONT, 10))
        self._btn_whisper_generate.setFixedHeight(28)
        self._btn_whisper_generate.setCursor(Qt.PointingHandCursor)
        self._btn_whisper_generate.setVisible(False)
        self._btn_whisper_generate.setStyleSheet(
            "QPushButton { color: #4a9eff; background: transparent; border: none; }"
            "QPushButton:hover { color: #6ab8ff; text-decoration: underline; }"
        )
        self._btn_whisper_generate.clicked.connect(self._on_whisper_generate_clicked)
        self._subtitle_layout.insertWidget(1, self._btn_whisper_generate)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._subtitle_container)
        self._subtitle_scroll = scroll
        layout.addWidget(scroll, 1)

        return page

    def _build_segment_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 8, 16, 4)
        header_layout.setSpacing(2)

        header_top = QHBoxLayout()
        header_top.setSpacing(8)
        self._lbl_seg_title = QLabel("")
        self._lbl_seg_title.setFont(QFont(FONT, 12, QFont.Bold))
        header_top.addWidget(self._lbl_seg_title)
        header_top.addStretch()

        self._btn_seg_repeat = QPushButton(I18n.t("study.btn.repeat"))
        self._btn_seg_repeat.setFont(QFont(FONT, 9))
        self._btn_seg_repeat.setFixedHeight(22)
        self._btn_seg_repeat.setCheckable(True)
        self._btn_seg_repeat.clicked.connect(self._on_seg_repeat_toggle)
        header_top.addWidget(self._btn_seg_repeat)

        self._btn_switch_to_subtitle = QPushButton(I18n.t("study.btn.view_switch"))
        self._btn_switch_to_subtitle.setFont(QFont(FONT, 9))
        self._btn_switch_to_subtitle.setFixedHeight(22)
        self._btn_switch_to_subtitle.clicked.connect(self._on_switch_to_subtitle)
        header_top.addWidget(self._btn_switch_to_subtitle)

        header_layout.addLayout(header_top)

        self._lbl_seg_info = QLabel(I18n.t("study.lbl.auto_segment_info"))
        self._lbl_seg_info.setFont(QFont(FONT, 9))
        self._lbl_seg_info.setStyleSheet("color: #888;")
        header_layout.addWidget(self._lbl_seg_info)

        layout.addWidget(header)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._seg_table = QTableWidget()
        self._seg_table.setColumnCount(3)
        self._seg_table.setHorizontalHeaderLabels(["#", I18n.t("study.col.name"), I18n.t("study.col.actions")])
        self._seg_table.verticalHeader().setVisible(False)
        self._seg_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._seg_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self._seg_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._seg_table.verticalHeader().setDefaultSectionSize(36)
        self._seg_table.setShowGrid(False)

        sh = self._seg_table.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        sh.setSectionResizeMode(1, QHeaderView.Stretch)
        sh.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self._seg_table.cellDoubleClicked.connect(self._on_seg_double_clicked)
        layout.addWidget(self._seg_table, 1)

        self._seg_empty_widget = QWidget()
        seg_empty_layout = QVBoxLayout(self._seg_empty_widget)
        seg_empty_layout.setAlignment(Qt.AlignCenter)
        self._lbl_no_segment = QLabel(I18n.t("study.msg.no_segment"))
        self._lbl_no_segment.setFont(QFont(FONT, 11))
        self._lbl_no_segment.setAlignment(Qt.AlignCenter)
        seg_empty_layout.addWidget(self._lbl_no_segment)
        self._btn_seg_generate = QPushButton(I18n.t("study.btn.segment"))
        self._btn_seg_generate.setFont(QFont(FONT, 10))
        self._btn_seg_generate.setFixedHeight(28)
        self._btn_seg_generate.setCursor(Qt.PointingHandCursor)
        self._btn_seg_generate.setStyleSheet(
            "QPushButton { color: #4a9eff; background: transparent; border: none; }"
            "QPushButton:hover { color: #6ab8ff; text-decoration: underline; }"
        )
        self._btn_seg_generate.clicked.connect(self._on_seg_generate_clicked)
        seg_empty_layout.addWidget(self._btn_seg_generate, 0, Qt.AlignCenter)
        self._seg_empty_widget.setVisible(False)
        layout.addWidget(self._seg_empty_widget, 1)

        return page

    def _switch_page(self, index):
        self._stack.setCurrentIndex(index)
        self._btn_subtitle_toggle.setChecked(index in (PAGE_SUBTITLE, PAGE_SEGMENT))
        if index == PAGE_LIBRARY:
            self._refresh_library()
        self._update_help_if_visible()

    def _toggle_help(self):
        if self._help_window.isVisible():
            self._help_window.hide()
        else:
            help_id = self._get_current_help_id()
            self._help_window.show_help(help_id)

    def _get_current_help_id(self) -> str:
        page = self._stack.currentIndex()
        if page == PAGE_IMPORT:
            return "study_import"
        elif page == PAGE_SUBTITLE:
            return "study_subtitle"
        elif page == PAGE_SEGMENT:
            return "study_segment"
        return "study_library"

    def _on_help_closed(self):
        pass

    def _update_help_if_visible(self):
        if hasattr(self, '_help_window') and self._help_window.isVisible():
            help_id = self._get_current_help_id()
            self._help_window.show_help(help_id)

    def _update_control_icons(self):
        tc = ThemeEngine().get_current_colors()
        color = tc.get("text_primary", "#cccccc")
        sz = 16
        sz_sm = 14

        self._btn_import.setIcon(get_icon("import", color, sz))
        self._btn_play.setIcon(get_icon("play", color, sz))
        self._btn_prev.setIcon(get_icon("skip-back", color, sz))
        self._btn_next.setIcon(get_icon("skip-forward", color, sz))

        self._btn_prev_sentence.setIcon(get_icon("chevron-left", color, sz_sm))
        self._btn_next_sentence.setIcon(get_icon("chevron-right", color, sz_sm))
        self._btn_repeat_current.setIcon(get_icon("repeat-sentence", color, sz_sm))
        self._btn_back_5.setIcon(get_icon("chevrons-left", color, sz_sm))
        self._btn_forward_5.setIcon(get_icon("chevrons-right", color, sz_sm))
        self._btn_first_sentence.setIcon(get_icon("arrow-left-to-line", color, sz_sm))
        self._btn_last_sentence.setIcon(get_icon("arrow-right-to-line", color, sz_sm))

        self._btn_shadowing.setIcon(get_icon("mic", color, sz_sm))
        self._btn_subtitle_toggle.setIcon(get_icon("subtitles", color, sz_sm))
        self._btn_dict_toggle.setIcon(get_icon("languages", color, sz_sm))
        self._btn_full.setIcon(get_icon("maximize", color, sz))
        self._btn_volume_icon.setIcon(get_icon("volume-2", color, 14))

        self._btn_title_minimize.setIcon(get_icon("minimize-2", color, 16))
        self._btn_title_maximize.setIcon(get_icon("maximize-2", color, 16))
        self._btn_title_close.setIcon(get_icon("x", color, 16))
        self._btn_title_help.setIcon(get_icon("circle-help", color, 16))

        if hasattr(self, "_lib_btn_refresh"):
            self._lib_btn_refresh.setIcon(get_icon("refresh-cw", color, 14))

        if hasattr(self, "_lib_btn_batch_del"):
            self._lib_btn_batch_del.setIcon(get_icon("trash-2", color, 14))

        if hasattr(self, "_btn_import_back"):
            self._btn_import_back.setIcon(get_icon("arrow-left", color, 14))

    def _apply_style(self):
        tc = ThemeEngine().get_current_colors()
        bg = tc.get("surface", "#1a1a2e")
        surface2 = tc.get("surface_alt", "#222240")
        accent = tc.get("accent", "#32c864")
        text = tc.get("text_primary", "#e0e0e0")
        text2 = tc.get("text_secondary", "#888888")
        btn_bg = tc.get("button_bg", "rgba(255,255,255,20)")
        btn_hover = tc.get("button_bg_hover", "rgba(255,255,255,40)")
        btn_pressed = tc.get("button_bg_pressed", "rgba(255,255,255,50)")
        danger = tc.get("danger", "#e74c3c")
        border_color = tc.get("border", "#444444")

        self.setStyleSheet(f"""
            StudyWindow {{
                background-color: {bg};
            }}
            QWidget {{
                background-color: {bg};
                color: {text};
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {text};
                border: none;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton:checked {{
                background-color: {accent};
                color: {bg};
            }}
            QSlider::groove:horizontal {{
                background: {surface2};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {accent};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QComboBox {{
                background-color: {surface2};
                color: {text};
                border: 1px solid rgba(255,255,255,30);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {surface2};
                color: {text};
                selection-background-color: {accent};
            }}
            QLineEdit {{
                background-color: {surface2};
                color: {text};
                border: 1px solid rgba(255,255,255,30);
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QGroupBox {{
                color: {text};
                border: 1px solid rgba(255,255,255,20);
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 16px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
            }}
            QProgressBar {{
                background-color: {surface2};
                border: none;
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {accent};
                border-radius: 4px;
            }}
            QScrollArea {{
                border: none;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
            QTableWidget {{
                background-color: {bg};
                alternate-background-color: {surface2};
                gridline-color: transparent;
                border: none;
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 4px 8px;
            }}
            QTableWidget::item:selected {{
                background-color: {accent};
                color: {bg};
            }}
            QHeaderView::section {{
                background-color: {surface2};
                color: {text2};
                border: none;
                border-bottom: 1px solid rgba(255,255,255,20);
                padding: 6px 8px;
                font-size: 11px;
                font-weight: bold;
            }}
            QWidget#StudyTitleBar {{
                background-color: {bg};
                border-bottom: 1px solid {border_color};
            }}
            QLabel#StudyTitleLabel {{
                color: {text};
                font: bold 12px 'Microsoft YaHei';
                padding-left: 4px;
                background: transparent;
                border: none;
            }}
            QPushButton#StudyTitleBarButton {{
                background-color: transparent;
                color: {text};
                border: none;
                font-size: 14px;
                padding: 0;
            }}
            QPushButton#StudyTitleBarButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#StudyTitleBarButton:pressed {{
                background-color: {btn_pressed};
            }}
            QPushButton#StudyTitleBarCloseButton {{
                background-color: transparent;
                color: {text};
                border: none;
                font-size: 16px;
                padding: 0;
            }}
            QPushButton#StudyTitleBarCloseButton:hover {{
                background-color: {danger};
                color: white;
            }}
            QPushButton#StudyTitleBarCloseButton:pressed {{
                background-color: {danger};
                color: white;
            }}
        """)

    def _save_geometry(self):
        s = QSettings("Music++", "StudyWindow")
        s.setValue("geometry", self.saveGeometry())

    def closeEvent(self, event):
        self._player.stop()
        self._save_geometry()
        if hasattr(self, '_help_window'):
            self._help_window.hide()
        self.closed.emit()
        super().closeEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, '_help_window') and self._help_window.isVisible():
            self._help_window.sync_position()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_help_window') and self._help_window.isVisible():
            self._help_window.sync_position()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_F1:
            self._toggle_help()
            event.accept()
            return
        elif key == Qt.Key_Space:
            self._on_toggle_play()
        elif key == Qt.Key_Left:
            pos = max(0, self._player.get_position_ms() - 5000)
            self._player.seek_to_ms(pos)
        elif key == Qt.Key_Right:
            pos = self._player.get_position_ms() + 5000
            dur = self._player.get_duration_ms()
            self._player.seek_to_ms(min(pos, dur))
        elif key == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_library()
        self._apply_style()
        self._update_control_icons()
        self._init_dict_toggle_state()
        if hasattr(self, '_help_window'):
            self._help_window.refresh_style()

    def _fmt_ms(self, ms) -> str:
        if not isinstance(ms, (int, float)) or ms <= 0:
            return "0:00"
        total = int(ms / 1000)
        m = total // 60
        s = total % 60
        h = total // 3600
        if h > 0:
            return f"{h}:{m % 60:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _init_dict_toggle_state(self):
        try:
            from src.business.config_manager import ConfigManager
            enabled = ConfigManager().get("Dictionary", "WordLookupEnabled", "true")
            checked = str(enabled).lower() not in ("false", "0", "no")
        except Exception:
            checked = True
        self._btn_dict_toggle.blockSignals(True)
        self._btn_dict_toggle.setChecked(checked)
        self._btn_dict_toggle.blockSignals(False)
        from src.business.dictionary_service import DictionaryService
        DictionaryService().set_word_lookup_enabled(checked)

    def _on_player_position(self, pos_ms, dur_ms):
        if dur_ms > 0 and not self._slider_progress.isSliderDown():
            self._slider_progress.blockSignals(True)
            self._slider_progress.setValue(int(pos_ms / dur_ms * 1000))
            self._slider_progress.blockSignals(False)
        self._lbl_time.setText(f"{self._fmt_ms(pos_ms)} / {self._fmt_ms(dur_ms)}")

    def _on_player_subtitle(self, index):
        for i, w in enumerate(self._subtitle_widgets):
            w.set_current(i == index)
            w.set_played(i < index)
        if 0 <= index < len(self._subtitle_widgets):
            w = self._subtitle_widgets[index]
            self._subtitle_scroll.ensureWidgetVisible(w, 50, 50)
        self._highlight_current_segment(index)

    def _highlight_current_segment(self, index):
        if self._stack.currentIndex() != PAGE_SEGMENT:
            return
        tc = ThemeEngine().get_current_colors()
        playing_bg = tc.get("lyric_active", "#32c864")
        bg_normal = tc.get("surface", "#1a1a2e")
        text_normal = tc.get("text_primary", "#e0e0e0")
        text_dim = tc.get("text_secondary", "#888888")
        row_count = self._seg_table.rowCount()
        for i in range(row_count):
            is_current = (i == index)
            for col in range(2):
                item = self._seg_table.item(i, col)
                if item:
                    if is_current:
                        item.setBackground(QColor(playing_bg))
                        item.setForeground(QColor(bg_normal))
                    else:
                        item.setBackground(QColor(bg_normal))
                        item.setForeground(QColor(text_normal) if i <= index else QColor(text_dim))
        if 0 <= index < row_count:
            self._seg_table.scrollToItem(self._seg_table.item(index, 0), QAbstractItemView.PositionAtCenter)

    def _on_player_state(self, state):
        tc = ThemeEngine().get_current_colors()
        color = tc.get("text_primary", "#cccccc")
        if state == StudyPlayer.STATE_PLAYING:
            self._btn_play.setIcon(get_icon("pause", color, 16))
            self._btn_play.setToolTip(I18n.t("study.btn.pause"))
        elif state == StudyPlayer.STATE_SHADOWING_WAIT:
            self._btn_play.setIcon(get_icon("play", color, 16))
            self._btn_play.setToolTip(I18n.t("study.msg.shadowing_wait"))
        else:
            self._btn_play.setIcon(get_icon("play", color, 16))
            self._btn_play.setToolTip(I18n.t("study.btn.play"))

    def _on_player_repeat_progress(self, current, total):
        self._lbl_repeat_status.setText(I18n.tf("study.msg.repeat_progress", current=current, total=total))

    def _on_player_repeat_done(self):
        self._lbl_repeat_status.setText("")
        self._btn_subtitle_repeat.setChecked(False)
        self._update_subtitle_repeat_btn_style(False)
        self._btn_seg_repeat.setChecked(False)
        self._update_seg_repeat_btn_style(False)

    def _on_player_shadowing_wait(self, subtitle_index, wait_ms):
        wait_sec = wait_ms / 1000.0
        self._lbl_repeat_status.setText(I18n.tf("study.msg.shadowing_wait_status", sec=f"{wait_sec:.1f}"))

    def _on_player_shadowing_resume(self, subtitle_index):
        self._lbl_repeat_status.setText("")

    def _on_player_auto_segment_done(self, segments):
        if self._player.is_auto_segmented():
            self._refresh_segment_table()
            if self._stack.currentIndex() != PAGE_SEGMENT:
                self._switch_page(PAGE_SEGMENT)
                self._btn_subtitle_toggle.setChecked(True)
        else:
            effective_lines = self._player._subtitle_lines
            self._build_subtitle_widgets(effective_lines)
            if self._stack.currentIndex() != PAGE_SUBTITLE:
                self._switch_page(PAGE_SUBTITLE)
                self._btn_subtitle_toggle.setChecked(True)

    def _on_progress_slider_moved(self, value):
        dur = self._player.get_duration_ms()
        if dur > 0:
            self._player.seek_to_ms(int(value / 1000.0 * dur))

    def _on_progress_slider_pressed(self):
        # placeholder for future implementation
        pass

    def _on_progress_slider_released(self):
        # placeholder for future implementation
        pass

    def _on_volume_changed(self, value):
        self._player.set_volume(value)
        tc = ThemeEngine().get_current_colors()
        color = tc.get("text_primary", "#cccccc")
        if value == 0:
            self._btn_volume_icon.setIcon(get_icon("volume-x", color, 14))
        elif value < 50:
            self._btn_volume_icon.setIcon(get_icon("volume-1", color, 14))
        else:
            self._btn_volume_icon.setIcon(get_icon("volume-2", color, 14))

    def _on_mute_toggle(self):
        if self._slider_volume.value() > 0:
            self._pre_mute_vol = self._slider_volume.value()
            self._slider_volume.setValue(0)
        else:
            self._slider_volume.setValue(getattr(self, "_pre_mute_vol", 80))

    def _on_speed_changed(self, index):
        speeds = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]
        if 0 <= index < len(speeds):
            self._player.set_speed(speeds[index])

    def _on_toggle_shadowing(self, checked):
        try:
            from src.business.config_manager import ConfigManager
            extra_sec = int(ConfigManager().get("Study", "ShadowingExtraSec", "3"))
        except Exception:
            extra_sec = 3
        self._player.set_shadowing_mode(checked, extra_sec)
        if checked and self._player._state == StudyPlayer.STATE_SHADOWING_WAIT:
            self._player._cancel_shadowing_wait()
            if self._player._current_subtitle_index + 1 < len(self._player._subtitle_lines):
                self._player.seek_to_subtitle(self._player._current_subtitle_index + 1)
                self._player.play()

    def _on_skip_shadowing_wait(self):
        if self._player._state == StudyPlayer.STATE_SHADOWING_WAIT:
            self._player._cancel_shadowing_wait()
            next_idx = self._player._current_subtitle_index + 1
            if next_idx < len(self._player._subtitle_lines):
                self._player.seek_to_subtitle(next_idx)
                self._player.play()
            self._lbl_repeat_status.setText("")

    def _on_toggle_play(self):
        if self._player._material is None and self._materials:
            self._play_material_at(0)
        elif self._player._state == StudyPlayer.STATE_SHADOWING_WAIT:
            self._on_skip_shadowing_wait()
        else:
            self._player.toggle_play()

    def _on_prev_material(self):
        if not self._materials:
            return
        idx = self._current_material_index - 1
        if idx < 0:
            idx = len(self._materials) - 1
        self._play_material_at(idx)

    def _on_next_material(self):
        if not self._materials:
            return
        idx = self._current_material_index + 1
        if idx >= len(self._materials):
            idx = 0
        self._play_material_at(idx)

    def _on_full_mode(self):
        self.switch_to_full.emit()

    def _on_toggle_dict_lookup(self, checked):
        from src.business.dictionary_service import DictionaryService
        svc = DictionaryService()
        svc.set_word_lookup_enabled(checked)
        try:
            from src.business.config_manager import ConfigManager
            ConfigManager().set("Dictionary", "WordLookupEnabled", checked)
        except Exception:
            pass
        if not checked:
            for w in self._subtitle_widgets:
                if hasattr(w, '_text_label') and isinstance(w._text_label, WordHoverLabel):
                    w._text_label._hide_tooltip()
                    w._text_label._current_word = ""
            for row in range(self._seg_table.rowCount()):
                cw = self._seg_table.cellWidget(row, 1)
                if isinstance(cw, WordHoverLabel):
                    cw._hide_tooltip()
                    cw._current_word = ""

    def _on_prev_sentence(self):
        idx = self._player._current_subtitle_index
        if idx < 0:
            idx = 0
        elif idx > 0:
            idx -= 1
        self._player.seek_to_subtitle(idx)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_next_sentence(self):
        idx = self._player._current_subtitle_index
        lines = self._player._subtitle_lines
        if not lines:
            return
        if idx < 0:
            idx = 0
        elif idx < len(lines) - 1:
            idx += 1
        self._player.seek_to_subtitle(idx)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_repeat_current_sentence(self):
        idx = self._player._current_subtitle_index
        if idx < 0:
            return
        try:
            from src.business.config_manager import ConfigManager
            rc = int(ConfigManager().get("Study", "RepeatCount", "3"))
            ps = int(ConfigManager().get("Study", "RepeatPauseSec", "3"))
        except Exception:
            rc, ps = 3, 3
        self._player.start_sentence_repeat(idx, rc, ps)

    def _on_jump_sentences(self, delta):
        lines = self._player._subtitle_lines
        if not lines:
            return
        idx = self._player._current_subtitle_index
        if idx < 0:
            idx = 0
        new_idx = idx + delta
        new_idx = max(0, min(new_idx, len(lines) - 1))
        self._player.seek_to_subtitle(new_idx)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_first_sentence(self):
        lines = self._player._subtitle_lines
        if not lines:
            return
        self._player.seek_to_subtitle(0)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_last_sentence(self):
        lines = self._player._subtitle_lines
        if not lines:
            return
        self._player.seek_to_subtitle(len(lines) - 1)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_toggle_subtitle(self, checked):
        if checked:
            if self._player._material and self._player.is_auto_segmented():
                self._refresh_segment_table()
                self._switch_page(PAGE_SEGMENT)
            else:
                self._switch_page(PAGE_SUBTITLE)
        else:
            self._switch_page(PAGE_LIBRARY)

    def _on_switch_to_segment(self):
        self._refresh_segment_table()
        self._switch_page(PAGE_SEGMENT)

    def _on_switch_to_subtitle(self):
        effective_lines = self._player._subtitle_lines
        self._build_subtitle_widgets(effective_lines)
        self._switch_page(PAGE_SUBTITLE)

    def _on_subtitle_repeat_toggle(self, checked):
        if checked:
            indices = sorted(self._selected_subtitle_indices)
            if not indices:
                self._btn_subtitle_repeat.setChecked(False)
                return
            if len(indices) >= 2:
                self._player.start_range_repeat(indices[0], indices[-1])
            else:
                self._player.start_sentence_repeat(indices[0], 999999)
            self._update_subtitle_repeat_btn_style(True)
        else:
            self._player.stop_repeat()
            self._lbl_repeat_status.setText("")
            self._update_subtitle_repeat_btn_style(False)
            self._player.play()

    def _update_subtitle_repeat_btn_style(self, active):
        tc = ThemeEngine().get_current_colors()
        if active:
            color = tc.get("lyric_active", "#32c864")
            self._btn_subtitle_repeat.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 4px; border: none; color: #fff; }}"
            )
        else:
            self._btn_subtitle_repeat.setStyleSheet("")

    def _refresh_segment_table(self):
        lines = self._player._subtitle_lines
        if not lines:
            self._seg_table.setVisible(False)
            self._seg_empty_widget.setVisible(True)
            if self._player._segment_worker and self._player._segment_worker.isRunning():
                self._lbl_no_segment.setText(I18n.t("study.msg.segmenting"))
                self._btn_seg_generate.setVisible(False)
            else:
                self._lbl_no_segment.setText(I18n.t("study.msg.no_segment"))
                self._btn_seg_generate.setVisible(True)
            if self._player._material:
                self._lbl_seg_title.setText(self._player._material.title)
            self._lbl_seg_info.setText("")
            return

        self._seg_table.setVisible(True)
        self._seg_empty_widget.setVisible(False)
        self._seg_table.setRowCount(len(lines))
        tc = ThemeEngine().get_current_colors()
        accent = tc.get("accent", "#4a9eff")
        danger = tc.get("danger", "#e05050")

        for i, line in enumerate(lines):
            idx_item = QTableWidgetItem(str(i + 1))
            idx_item.setTextAlignment(Qt.AlignCenter)
            idx_item.setFont(QFont(FONT, 10))
            self._seg_table.setItem(i, 0, idx_item)

            name = line.text if line.text and not line.text.startswith("(auto") else I18n.tf("study.lbl.sentence_n", n=i + 1)
            name_label = WordHoverLabel(name)
            name_label.setFont(QFont(FONT, 16))
            name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_label.setWordWrap(True)
            name_label.setMouseTracking(True)
            self._seg_table.setCellWidget(i, 1, name_label)

            ops_widget = QWidget()
            ops_layout = QHBoxLayout(ops_widget)
            ops_layout.setContentsMargins(2, 0, 2, 0)
            ops_layout.setSpacing(4)

            btn_style = (
                f"QPushButton {{ color: {accent}; background: transparent; border: none; "
                f"font-size: 12px; }} QPushButton:hover {{ color: #6ab8ff; }}"
            )
            btn_play = QPushButton(I18n.t("study.btn.play"))
            btn_play.setStyleSheet(btn_style)
            btn_play.setCursor(Qt.PointingHandCursor)
            btn_play.setFixedHeight(24)
            btn_play.clicked.connect(lambda checked, idx=i: self._on_seg_play(idx))
            ops_layout.addWidget(btn_play)

            repeat_style = (
                f"QPushButton {{ color: {danger}; background: transparent; border: none; "
                f"font-size: 12px; }} QPushButton:hover {{ color: #ff6666; }}"
            )
            btn_repeat = QPushButton(I18n.t("study.btn.repeat"))
            btn_repeat.setStyleSheet(repeat_style)
            btn_repeat.setCursor(Qt.PointingHandCursor)
            btn_repeat.setFixedHeight(24)
            btn_repeat.clicked.connect(lambda checked, idx=i: self._on_seg_repeat(idx))
            ops_layout.addWidget(btn_repeat)

            self._seg_table.setCellWidget(i, 2, ops_widget)

        if self._player._material:
            self._lbl_seg_title.setText(self._player._material.title)
        self._lbl_seg_info.setText(I18n.tf("study.lbl.auto_segment_count", count=len(lines)))

    def _on_seg_play(self, index):
        if self._player.get_repeat_mode() > 0:
            self._player.stop_repeat()
            self._btn_seg_repeat.setChecked(False)
            self._update_seg_repeat_btn_style(False)
            self._btn_subtitle_repeat.setChecked(False)
            self._update_subtitle_repeat_btn_style(False)
            self._lbl_repeat_status.setText("")
        self._player.seek_to_subtitle(index)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_seg_repeat(self, index):
        if self._player.get_repeat_mode() > 0:
            self._player.stop_repeat()
            self._btn_seg_repeat.setChecked(False)
            self._update_seg_repeat_btn_style(False)
            self._btn_subtitle_repeat.setChecked(False)
            self._update_subtitle_repeat_btn_style(False)
            self._lbl_repeat_status.setText("")
            return
        selected_rows = self._get_selected_seg_rows()
        if len(selected_rows) >= 2:
            start_idx = min(selected_rows)
            end_idx = max(selected_rows)
            self._player.start_range_repeat(start_idx, end_idx)
        else:
            self._player.start_sentence_repeat(index)

    def _on_seg_repeat_toggle(self, checked):
        if checked:
            selected_rows = self._get_selected_seg_rows()
            if len(selected_rows) >= 2:
                start_idx = min(selected_rows)
                end_idx = max(selected_rows)
                self._player.start_range_repeat(start_idx, end_idx)
            elif self._player._current_subtitle_index >= 0:
                self._player.start_sentence_repeat(self._player._current_subtitle_index, 999999)
            else:
                self._btn_seg_repeat.setChecked(False)
                return
            self._update_seg_repeat_btn_style(True)
        else:
            self._player.stop_repeat()
            self._lbl_repeat_status.setText("")
            self._update_seg_repeat_btn_style(False)
            self._player.play()

    def _update_seg_repeat_btn_style(self, active):
        tc = ThemeEngine().get_current_colors()
        if active:
            color = tc.get("lyric_active", "#32c864")
            self._btn_seg_repeat.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 4px; border: none; color: #fff; }}"
            )
        else:
            self._btn_seg_repeat.setStyleSheet("")

    def _on_whisper_generate_clicked(self):
        if self._current_material_index < 0:
            return
        self._on_whisper_at(self._current_material_index)

    def _on_seg_generate_clicked(self):
        if self._current_material_index < 0:
            return
        self._on_segment_at(self._current_material_index)

    def _on_display_mode_changed(self, index):
        mode = self._combo_display_mode.itemData(index)
        has_translation = any(w._line.translation for w in self._subtitle_widgets)
        if mode == "bilingual" and has_translation:
            for w in self._subtitle_widgets:
                w.set_translation_visible(True)
        else:
            for w in self._subtitle_widgets:
                w.set_translation_visible(False)

        try:
            from src.business.config_manager import ConfigManager
            ConfigManager().set("Study", "SubtitleDisplayMode", mode)
        except Exception:
            pass

    def _get_selected_seg_rows(self) -> list:
        rows = set()
        for item in self._seg_table.selectedItems():
            rows.add(item.row())
        return sorted(rows)

    def _on_seg_double_clicked(self, row, col):
        if 0 <= row < len(self._player._subtitle_lines):
            self._on_seg_play(row)

    def _on_subtitle_clicked(self, index):
        if self._player.get_repeat_mode() > 0:
            self._player.stop_repeat()
            self._btn_subtitle_repeat.setChecked(False)
            self._update_subtitle_repeat_btn_style(False)
            self._btn_seg_repeat.setChecked(False)
            self._update_seg_repeat_btn_style(False)
            self._lbl_repeat_status.setText("")
        self._selected_subtitle_indices.clear()
        self._selected_subtitle_indices.add(index)
        for i, w in enumerate(self._subtitle_widgets):
            w.set_selected(i == index)
        self._btn_subtitle_repeat.setVisible(True)
        self._player.seek_to_subtitle(index)
        if self._player.get_state() != StudyPlayer.STATE_PLAYING:
            self._player.play()

    def _on_subtitle_ctrl_clicked(self, index):
        if index in self._selected_subtitle_indices:
            self._selected_subtitle_indices.discard(index)
        else:
            self._selected_subtitle_indices.add(index)

        for i, w in enumerate(self._subtitle_widgets):
            w.set_selected(i in self._selected_subtitle_indices)

        self._btn_subtitle_repeat.setVisible(len(self._selected_subtitle_indices) >= 1)

    def _on_subtitle_shift_clicked(self, index):
        if not self._selected_subtitle_indices:
            self._selected_subtitle_indices.add(index)
        else:
            anchor = min(self._selected_subtitle_indices)
            for i in range(anchor, index + 1):
                self._selected_subtitle_indices.add(i)

        for i, w in enumerate(self._subtitle_widgets):
            w.set_selected(i in self._selected_subtitle_indices)

        self._btn_subtitle_repeat.setVisible(len(self._selected_subtitle_indices) >= 1)

    def _refresh_library(self):
        self._materials = self._mgr.get_materials()
        self._lib_table.setRowCount(len(self._materials))

        for row, mat in enumerate(self._materials):
            name_item = QTableWidgetItem(mat.title)
            name_item.setData(Qt.UserRole, row)
            self._lib_table.setItem(row, 0, name_item)

            created = mat.created_at[:10] if mat.created_at else ""
            self._lib_table.setItem(row, 1, QTableWidgetItem(created))

            has_sub = bool(mat.subtitle_path) and os.path.exists(mat.subtitle_path)
            has_seg = self._mgr.has_segment_file(mat.id)
            if has_sub:
                sub_text = "✓"
            elif has_seg:
                sub_text = "⚡"
            else:
                sub_text = "✗"
            sub_item = QTableWidgetItem(sub_text)
            sub_item.setTextAlignment(Qt.AlignCenter)
            self._lib_table.setItem(row, 2, sub_item)

            study_sec = int(mat.progress_ms / 1000) if mat.progress_ms else 0
            study_m = study_sec // 60
            study_s = study_sec % 60
            self._lib_table.setItem(row, 3, QTableWidgetItem(f"{study_m}:{study_s:02d}"))

            progress_pct = 0
            if mat.duration_ms > 0:
                progress_pct = int(mat.progress_ms / mat.duration_ms * 100)
            pct_item = QTableWidgetItem(f"{progress_pct}%")
            pct_item.setTextAlignment(Qt.AlignCenter)
            self._lib_table.setItem(row, 4, pct_item)

            ops_widget = QWidget()
            ops_layout = QHBoxLayout(ops_widget)
            ops_layout.setContentsMargins(4, 2, 4, 2)
            ops_layout.setSpacing(4)

            btn_play = QPushButton()
            btn_play.setFixedSize(24, 24)
            btn_play.setToolTip(I18n.t("study.btn.play"))
            btn_play.setIcon(get_icon("play", ThemeEngine().get_current_colors().get("text", "#fff"), 12))
            btn_play.clicked.connect(lambda checked, idx=row: self._play_material_at(idx))
            ops_layout.addWidget(btn_play)

            btn_resub = QPushButton()
            btn_resub.setFixedSize(24, 24)
            btn_resub.setToolTip(I18n.t("study.btn.resubtitle"))
            btn_resub.setIcon(get_icon("subtitles", ThemeEngine().get_current_colors().get("text", "#fff"), 12))
            btn_resub.clicked.connect(lambda checked, idx=row: self._on_resubtitle_at(idx))
            ops_layout.addWidget(btn_resub)

            btn_seg = QPushButton()
            btn_seg.setFixedSize(24, 24)
            btn_seg.setToolTip(I18n.t("study.btn.segment"))
            btn_seg.setIcon(get_icon("mic", ThemeEngine().get_current_colors().get("text", "#fff"), 12))
            btn_seg.clicked.connect(lambda checked, idx=row: self._on_segment_at(idx))
            ops_layout.addWidget(btn_seg)

            btn_whisper = QPushButton()
            btn_whisper.setFixedSize(24, 24)
            btn_whisper.setToolTip(I18n.t("study.btn.whisper_subtitle"))
            btn_whisper.setIcon(get_icon("wand-2", ThemeEngine().get_current_colors().get("text", "#fff"), 12))
            btn_whisper.clicked.connect(lambda checked, idx=row: self._on_whisper_at(idx))
            ops_layout.addWidget(btn_whisper)

            btn_del = QPushButton()
            btn_del.setFixedSize(24, 24)
            btn_del.setToolTip(I18n.t("study.btn.delete"))
            btn_del.setIcon(get_icon("trash-2", ThemeEngine().get_current_colors().get("text", "#fff"), 12))
            btn_del.clicked.connect(lambda checked, idx=row: self._on_delete_material_at(idx))
            ops_layout.addWidget(btn_del)

            ops_layout.addStretch()
            self._lib_table.setCellWidget(row, 5, ops_widget)

        self._lib_table.resizeRowsToContents()

    def _play_material_at(self, index):
        if index < 0 or index >= len(self._materials):
            return
        mat = self._materials[index]
        self._current_material_index = index

        subtitle_lines = self._mgr.get_subtitle_lines(mat.id)
        logger.info(f"Loading material: {mat.title}, subtitle_lines: {len(subtitle_lines)}, audio: {mat.audio_path}")
        if not self._player.load_material(mat, subtitle_lines):
            log_msgbox("warning", I18n.t("study.msg.error"), I18n.t("study.msg.cannot_load_audio"))
            ThemedMessageBox.warning(self, I18n.t("study.msg.error"), I18n.t("study.msg.cannot_load_audio"))
            return

        self._mgr.update_last_played(mat.id)

        self._lbl_subtitle_title.setText(mat.title)
        source = mat.source_url if mat.source == "url" else I18n.t("study.lbl.local_file")
        self._lbl_subtitle_source.setText(I18n.tf("study.lbl.source", source=source))

        if self._player.is_auto_segmented():
            self._refresh_segment_table()
            self._switch_page(PAGE_SEGMENT)
        else:
            effective_lines = self._player._subtitle_lines
            self._build_subtitle_widgets(effective_lines)
            self._switch_page(PAGE_SUBTITLE)

        self._btn_subtitle_toggle.setChecked(True)
        self._btn_subtitle_repeat.setChecked(False)
        self._update_subtitle_repeat_btn_style(False)
        self._btn_seg_repeat.setChecked(False)
        self._update_seg_repeat_btn_style(False)
        self._player.play()

    def _build_subtitle_widgets(self, lines: list):
        for w in self._subtitle_widgets:
            w.deleteLater()
        self._subtitle_widgets.clear()
        self._selected_subtitle_indices.clear()
        self._btn_subtitle_repeat.setVisible(False)
        self._combo_display_mode.setVisible(False)

        while self._subtitle_layout.count() > 3:
            item = self._subtitle_layout.takeAt(2)
            w = item.widget()
            if w:
                w.deleteLater()

        if not lines:
            self._lbl_no_subtitle.setVisible(True)
            if self._player._segment_worker and self._player._segment_worker.isRunning():
                self._lbl_no_subtitle.setText(I18n.t("study.msg.auto_segmenting"))
                self._btn_whisper_generate.setVisible(False)
            else:
                self._lbl_no_subtitle.setText(I18n.t("study.msg.no_subtitle"))
                self._btn_whisper_generate.setVisible(True)
            logger.warning(f"_build_subtitle_widgets: no subtitle lines available")
            return

        self._lbl_no_subtitle.setVisible(False)
        self._btn_whisper_generate.setVisible(False)
        if self._player.is_auto_segmented():
            self._lbl_no_subtitle.setVisible(True)
            self._lbl_no_subtitle.setText(I18n.t("study.msg.auto_segmented"))
        logger.info(f"_build_subtitle_widgets: creating {len(lines)} subtitle widgets")

        has_translation = any(line.translation for line in lines)

        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            display_mode = cm.get("Study", "SubtitleDisplayMode", "original")
        except Exception:
            display_mode = "original"

        if has_translation:
            self._combo_display_mode.setVisible(True)
            if display_mode == "bilingual":
                self._combo_display_mode.setCurrentIndex(1)
            else:
                self._combo_display_mode.setCurrentIndex(0)
        else:
            self._combo_display_mode.setCurrentIndex(0)

        for i, line in enumerate(lines):
            w = SubtitleLineWidget(line, i)
            w.clicked.connect(self._on_subtitle_clicked)
            w.ctrl_clicked.connect(self._on_subtitle_ctrl_clicked)
            w.shift_clicked.connect(self._on_subtitle_shift_clicked)
            if has_translation and display_mode == "bilingual":
                w.set_translation_visible(True)
            else:
                w.set_translation_visible(False)
            self._subtitle_layout.insertWidget(self._subtitle_layout.count() - 1, w)
            self._subtitle_widgets.append(w)

        logger.info(f"_build_subtitle_widgets: done, total widgets={len(self._subtitle_widgets)}, layout count={self._subtitle_layout.count()}")

    def _on_table_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._materials):
            self._play_material_at(row)

    def _on_table_context_menu(self, pos):
        row = self._lib_table.rowAt(pos.y())
        if row < 0 or row >= len(self._materials):
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        mat = self._materials[row]
        menu.addAction(I18n.t("study.btn.play"), lambda: self._play_material_at(row))
        menu.addAction(I18n.t("study.btn.resubtitle"), lambda: self._on_resubtitle_at(row))
        menu.addAction(I18n.t("study.btn.segment"), lambda: self._on_segment_at(row))
        menu.addAction(I18n.t("study.btn.whisper_subtitle"), lambda: self._on_whisper_at(row))
        menu.addSeparator()
        menu.addAction(I18n.t("study.btn.delete"), lambda: self._on_delete_material_at(row))
        menu.exec(self._lib_table.viewport().mapToGlobal(pos))

    def _on_delete_material_at(self, index):
        if index < 0 or index >= len(self._materials):
            return
        mat = self._materials[index]
        log_msgbox("question", I18n.t("study.dlg.delete_material"),
            I18n.tf("study.msg.confirm_delete", title=mat.title))
        reply = ThemedMessageBox.question(
            self, I18n.t("study.dlg.delete_material"),
            I18n.tf("study.msg.confirm_delete", title=mat.title),
            buttons=[("yes", I18n.t("study.btn.yes")), ("no", I18n.t("study.btn.no"))], default_button="no",
        )
        if reply == 1:
            if self._current_material_index == index:
                self._player.stop()
            self._mgr.delete_material(mat.id)
            self._current_material_index = -1
            self._refresh_library()

    def _on_batch_delete(self):
        rows = set()
        for item in self._lib_table.selectedItems():
            rows.add(item.row())
        if not rows:
            log_msgbox("info", I18n.t("study.dlg.batch_delete"), I18n.t("study.msg.select_materials_first"))
            ThemedMessageBox.information(self, I18n.t("study.dlg.batch_delete"), I18n.t("study.msg.select_materials_first"))
            return
        indices = sorted(rows)
        names = []
        for r in indices:
            if r < len(self._materials):
                names.append(self._materials[r].title)
        batch_msg = I18n.tf("study.msg.confirm_batch_delete", count=len(names)) + "\n\n" + "\n".join(f"• {n}" for n in names[:10]) + (I18n.tf("study.msg.and_more", count=len(names)) if len(names) > 10 else "") + "\n\n" + I18n.t("study.msg.files_will_be_deleted")
        log_msgbox("question", I18n.t("study.dlg.batch_delete"),
            batch_msg)
        reply = ThemedMessageBox.question(
            self, I18n.t("study.dlg.batch_delete"),
            batch_msg,
            buttons=[("yes", I18n.t("study.btn.yes")), ("no", I18n.t("study.btn.no"))], default_button="no",
        )
        if reply == 1:
            for r in reversed(indices):
                if r < len(self._materials):
                    if self._current_material_index == r:
                        self._player.stop()
                    self._mgr.delete_material(self._materials[r].id)
            self._current_material_index = -1
            self._refresh_library()

    def _on_resubtitle_at(self, index):
        if index < 0 or index >= len(self._materials):
            return
        mat = self._materials[index]
        self._lbl_no_subtitle.setText(I18n.t("study.msg.extracting_subtitle"))
        self._lbl_no_subtitle.setVisible(True)
        QApplication.processEvents()

        ok = self._mgr.re_extract_subtitle(mat.id)
        if ok:
            log_msgbox("info", I18n.t("study.dlg.resubtitle"), I18n.tf("study.msg.subtitle_extract_success", title=mat.title))
            ThemedMessageBox.information(self, I18n.t("study.dlg.resubtitle"), I18n.tf("study.msg.subtitle_extract_success", title=mat.title))
            self._refresh_library()
            if self._current_material_index == index:
                self._play_material_at(index)
        else:
            log_msgbox("warning", I18n.t("study.dlg.resubtitle"),
                I18n.tf("study.msg.cannot_extract_subtitle", title=mat.title))
            ThemedMessageBox.warning(
                self, I18n.t("study.dlg.resubtitle"),
                I18n.tf("study.msg.cannot_extract_subtitle", title=mat.title)
            )
            self._lbl_no_subtitle.setVisible(False)

    def _on_segment_at(self, index):
        if index < 0 or index >= len(self._materials):
            return
        mat = self._materials[index]

        if self._mgr.has_segment_file(mat.id):
            log_msgbox("question", I18n.t("study.dlg.segment"),
                I18n.tf("study.msg.confirm_re_segment", title=mat.title))
            reply = ThemedMessageBox.question(
                self, I18n.t("study.dlg.segment"),
                I18n.tf("study.msg.confirm_re_segment", title=mat.title),
                buttons=[("yes", I18n.t("study.btn.yes")), ("no", I18n.t("study.btn.no"))], default_button="no",
            )
            if reply == 0:
                return

        self._player.stop()

        self._lbl_no_subtitle.setText(I18n.t("study.msg.segmenting"))
        self._lbl_no_subtitle.setVisible(True)
        self._btn_whisper_generate.setVisible(False)
        if self._stack.currentIndex() == PAGE_SEGMENT:
            self._lbl_no_segment.setText(I18n.t("study.msg.segmenting"))
            self._btn_seg_generate.setVisible(False)
        QApplication.processEvents()

        ok = self._mgr.run_segmentation(mat.id)
        if ok:
            log_msgbox("info", I18n.t("study.dlg.segment"), I18n.tf("study.msg.segments_done", title=mat.title))
            ThemedMessageBox.information(self, I18n.t("study.dlg.segment"), I18n.tf("study.msg.segments_done", title=mat.title))
            self._refresh_library()
            if self._current_material_index == index:
                self._play_material_at(index)
        else:
            log_msgbox("warning", I18n.t("study.dlg.segment"), I18n.tf("study.msg.segments_failed", title=mat.title))
            ThemedMessageBox.warning(self, I18n.t("study.dlg.segment"), I18n.tf("study.msg.segments_failed", title=mat.title))
            self._lbl_no_subtitle.setVisible(False)
            self._btn_whisper_generate.setVisible(True)
            if self._stack.currentIndex() == PAGE_SEGMENT:
                self._lbl_no_segment.setText(I18n.t("study.msg.no_segment"))
                self._btn_seg_generate.setVisible(True)

    def _on_whisper_at(self, index):
        if index < 0 or index >= len(self._materials):
            return
        mat = self._materials[index]

        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()
        if not plugin.is_available():
            log_msgbox("question", I18n.t("study.dlg.whisper_subtitle"),
                I18n.t("study.msg.whisper_not_installed"))
            reply = ThemedMessageBox.question(
                self, I18n.t("study.dlg.whisper_subtitle"),
                I18n.t("study.msg.whisper_not_installed"),
                buttons=[("yes", I18n.t("study.btn.yes")), ("no", I18n.t("study.btn.no"))], default_button="yes",
            )
            if reply == 1:
                self._install_whisper_and_transcribe(index)
            return

        self._start_whisper_transcription(index)

    def _install_whisper_and_transcribe(self, index):
        from src.plugins.whisper_plugin import WhisperPlugin
        plugin = WhisperPlugin()

        self._lbl_no_subtitle.setText(I18n.t("study.msg.installing_whisper"))
        self._lbl_no_subtitle.setVisible(True)
        self._btn_whisper_generate.setVisible(False)
        QApplication.processEvents()

        ok = plugin.install()
        if not ok:
            log_msgbox("warning", I18n.t("study.dlg.whisper_install"), I18n.t("study.msg.whisper_install_failed"))
            ThemedMessageBox.warning(self, I18n.t("study.dlg.whisper_install"), I18n.t("study.msg.whisper_install_failed"))
            self._lbl_no_subtitle.setVisible(False)
            self._btn_whisper_generate.setVisible(True)
            return

        log_msgbox("info", I18n.t("study.dlg.whisper_install"), I18n.t("study.msg.whisper_install_success"))
        ThemedMessageBox.information(self, I18n.t("study.dlg.whisper_install"), I18n.t("study.msg.whisper_install_success"))
        self._start_whisper_transcription(index)

    def _start_whisper_transcription(self, index):
        mat = self._materials[index]

        try:
            from src.business.config_manager import ConfigManager
            cm = ConfigManager()
            model_name = cm.get("Whisper", "Model", "base")
            device = cm.get("Whisper", "Device", "auto")
            language = cm.get("Whisper", "Language", "")
            hf_mirror_url = cm.get("Whisper", "HFMirror", "")
        except Exception:
            model_name = "base"
            device = "auto"
            language = ""
            hf_mirror_url = ""

        if language == "auto" or language == I18n.t("study.lbl.auto_detect"):
            language = ""

        self._player.stop()

        self._lbl_no_subtitle.setText(I18n.tf("study.msg.whisper_transcribing", model=model_name))
        self._lbl_no_subtitle.setVisible(True)
        self._btn_whisper_generate.setVisible(False)
        QApplication.processEvents()

        self._whisper_worker = WhisperWorker(
            material_id=mat.id,
            audio_path=mat.audio_path,
            model_name=model_name,
            language=language,
            device=device,
            hf_mirror_url=hf_mirror_url,
        )
        self._whisper_worker.progress.connect(self._on_whisper_progress)
        self._whisper_worker.finished.connect(self._on_whisper_finished)
        self._whisper_worker.error.connect(self._on_whisper_error)
        self._whisper_worker.start()

    def _on_whisper_progress(self, msg, pct):
        self._lbl_no_subtitle.setText(f"⏳ {msg} ({pct}%)")
        QApplication.processEvents()

    def _on_whisper_finished(self, material_id, subtitles):
        if self._whisper_worker:
            self._whisper_worker.wait()
            self._whisper_worker = None

        mat = None
        idx = -1
        for i, m in enumerate(self._materials):
            if m.id == material_id:
                mat = m
                idx = i
                break

        count = len(subtitles) if subtitles else 0
        log_msgbox("info", I18n.t("study.dlg.whisper_transcribe"), I18n.tf("study.msg.whisper_done", count=count))
        ThemedMessageBox.information(self, I18n.t("study.dlg.whisper_transcribe"), I18n.tf("study.msg.whisper_done", count=count))
        self._lbl_no_subtitle.setVisible(False)

        if idx >= 0:
            self._refresh_library()
            if self._current_material_index == idx:
                self._play_material_at(idx)

    def _on_whisper_error(self, material_id, error_msg):
        if self._whisper_worker:
            self._whisper_worker.wait()
            self._whisper_worker = None

        log_msgbox("warning", I18n.t("study.dlg.whisper_transcribe"), I18n.tf("study.msg.whisper_error", error=error_msg))
        ThemedMessageBox.warning(self, I18n.t("study.dlg.whisper_transcribe"), I18n.tf("study.msg.whisper_error", error=error_msg))
        self._lbl_no_subtitle.setVisible(True)
        self._lbl_no_subtitle.setText(I18n.t("study.msg.no_subtitle"))
        self._btn_whisper_generate.setVisible(True)

    def _on_import_url(self):
        url = self._url_input.text().strip()
        if not url:
            return
        lang = self._combo_lang.currentText()
        lang_sec = self._combo_lang_secondary.currentText()
        if lang_sec == I18n.t("study.lbl.none"):
            lang_sec = ""

        self._set_importing(True)
        self._import_worker = ImportWorker(
            mode="url", url=url, lang=lang, lang_secondary=lang_sec
        )
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("study.dlg.select_media_file"), "",
            I18n.t("study.filter.media_files") + " (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts *.mp3 *.m4a *.flac *.wav *.ogg *.aac);;" + I18n.t("study.filter.video_files") + " (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts);;" + I18n.t("study.filter.audio_files") + " (*.mp3 *.m4a *.flac *.wav *.ogg *.aac);;" + I18n.t("study.filter.all_files") + " (*)"
        )
        if path:
            self._local_path.setText(path)
            auto_sub = self._find_subtitle_for_file(path)
            if auto_sub:
                self._local_sub_path.setText(auto_sub)

    def _on_browse_sub_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, I18n.t("study.dlg.select_subtitle_file"), "",
            I18n.t("study.filter.subtitle_files") + " (*.srt *.ass *.ssa *.vtt *.lrc);;" + I18n.t("study.filter.all_files") + " (*)"
        )
        if path:
            self._local_sub_path.setText(path)

    def _find_subtitle_for_file(self, file_path: str) -> str:
        base = os.path.splitext(file_path)[0]
        for ext in [".srt", ".ass", ".ssa", ".vtt", ".lrc", ".SRT", ".ASS", ".VTT", ".LRC"]:
            path = base + ext
            if os.path.exists(path):
                return path
        for ext in [".srt", ".ass", ".ssa", ".vtt", ".lrc"]:
            for suffix in [".en", ".zh", ".zh-CN", ".zh-Hans", ".chi", ".eng", ".chinese", ".english"]:
                path = base + suffix + ext
                if os.path.exists(path):
                    return path
        return ""

    def _on_import_file(self):
        path = self._local_path.text().strip()
        if not path:
            return
        sub_path = self._local_sub_path.text().strip()
        self._set_importing(True)
        self._import_worker = ImportWorker(mode="file", file_path=path, subtitle_path=sub_path)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, I18n.t("study.dlg.select_folder"))
        if folder:
            self._local_folder_path.setText(folder)

    def _on_import_folder(self):
        folder = self._local_folder_path.text().strip()
        if not folder:
            return
        files = self._mgr.scan_folder_for_media(folder)
        if not files:
            log_msgbox("info", I18n.t("study.dlg.batch_import"), I18n.t("study.msg.folder_no_media"))
            ThemedMessageBox.information(self, I18n.t("study.dlg.batch_import"), I18n.t("study.msg.folder_no_media"))
            return
        log_msgbox("question", I18n.t("study.dlg.batch_import"),
            I18n.tf("study.msg.confirm_batch_import", count=len(files)))
        reply = ThemedMessageBox.question(
            self, I18n.t("study.dlg.batch_import"),
            I18n.tf("study.msg.confirm_batch_import", count=len(files)),
            buttons=[("yes", I18n.t("study.btn.yes")), ("no", I18n.t("study.btn.no"))], default_button="yes",
        )
        if reply != 1:
            return
        self._set_importing(True)
        self._import_worker = ImportWorker(mode="folder", folder_path=folder)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.batch_finished.connect(self._on_batch_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.start()

    def _on_batch_import_finished(self, materials):
        self._set_importing(False)
        self._progress_bar.setValue(100)
        self._lbl_import_status.setText(I18n.tf("study.msg.batch_import_done", count=len(materials)))
        self._refresh_library()

    def _set_importing(self, importing: bool):
        self._btn_import_url.setEnabled(not importing)
        self._btn_import_file.setEnabled(not importing)
        self._btn_import_folder.setEnabled(not importing)
        if importing:
            self._progress_bar.setValue(0)
            self._lbl_import_status.setText(I18n.t("study.msg.importing"))

    def _on_import_progress(self, msg: str, pct: int):
        self._progress_bar.setValue(pct)
        self._lbl_import_status.setText(msg)

    def _on_import_finished(self, material):
        self._set_importing(False)
        self._progress_bar.setValue(100)
        self._lbl_import_status.setText(I18n.tf("study.msg.import_success", title=material.title))
        self._url_input.clear()
        self._local_path.clear()
        self._refresh_library()
        for i, mat in enumerate(self._materials):
            if mat.id == material.id:
                self._play_material_at(i)
                break

    def _on_import_error(self, error_msg: str):
        self._set_importing(False)
        self._progress_bar.setValue(0)
        self._lbl_import_status.setText(I18n.tf("study.msg.import_error", error=error_msg))


