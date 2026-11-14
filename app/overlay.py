from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import Config
from .i18n import tr
from .pipeline import Segment
from .winutil import (
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    set_ex_style,
    set_topmost,
    show_no_activate,
)

log = logging.getLogger(__name__)

_MARGIN_BOTTOM = 72


class LevelBars(QWidget):
    """Tiny animated level meter shown in the overlay header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(26, 14)
        self._level = 0.0

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bars = 5
        gap = 3
        w = (self.width() - gap * (bars - 1)) / bars
        for i in range(bars):
            amp = [0.5, 0.75, 1.0, 0.75, 0.5][i]
            h = max(2, int(self.height() * amp * (0.25 + 0.75 * self._level)))
            x = i * (w + gap)
            y = self.height() - h
            active = self._level > 0.03
            color = QColor("#5B8CFF") if active else QColor("#3A4660")
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(int(x), int(y), int(w), int(h), 1.5, 1.5)
        p.end()


class SegmentRow(QFrame):
    def __init__(self, cfg: Config, current: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("segmentRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        self.original = QLabel()
        self.original.setObjectName("originalText")
        self.original.setWordWrap(True)
        self.original.setTextInteractionFlags(Qt.NoTextInteraction)
        self.original.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.translation = QLabel()
        self.translation.setObjectName("translationText")
        self.translation.setWordWrap(True)
        self.translation.setTextInteractionFlags(Qt.NoTextInteraction)
        self.translation.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout.addWidget(self.original)
        layout.addWidget(self.translation)

        if current:
            self.setObjectName("segmentRowCurrent")
        self._apply_fonts(cfg, current)

    def _apply_fonts(self, cfg: Config, current: bool) -> None:
        base = cfg.overlay_font_size
        if current:
            t_size = base
            o_size = max(11, int(base * 0.52))
        else:
            t_size = max(12, int(base * 0.76))
            o_size = max(10, int(base * 0.48))
        tf = QFont("Microsoft YaHei UI", t_size)
        tf.setWeight(QFont.DemiBold if current else QFont.Normal)
        self.translation.setFont(tf)
        of = QFont("Microsoft YaHei UI", o_size)
        self.original.setFont(of)


class SubtitleOverlay(QWidget):
    def __init__(
        self,
        config: Config,
        on_settings: Callable[[], None] | None = None,
        on_lock_toggle: Callable[[bool], None] | None = None,
        on_hide: Callable[[], None] | None = None,
        on_position_changed: Callable[[int, int], None] | None = None,
    ) -> None:
        super().__init__(None)
        self.cfg = config
        self.on_settings = on_settings
        self.on_lock_toggle = on_lock_toggle
        self.on_hide = on_hide
        self.on_position_changed = on_position_changed

        self._segments: list[Segment] = []
        self._status = "idle"
        self._topmost_enabled = True
        self._auto_position = config.overlay_x <= -9999 and config.overlay_y <= -9999
        self._drag_offset: QPoint | None = None
        self._level = 0.0
        self._pinned_to_bottom = True
        self._click_through_applied: bool | None = None
        self._snapshot = self._snapshot_fields(config)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setWindowTitle(tr("浮译 LiveFloat", "LiveFloat"))

        self._build_ui()

        self._top_timer = QTimer(self)
        self._top_timer.timeout.connect(self._reassert_topmost)
        self._top_timer.start(1500)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QFrame()
        self.card.setObjectName("overlayCard")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(42)
        shadow.setColor(QColor(0, 0, 0, 170))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)
        root.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(14, 10, 14, 14)
        card_layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        self.title_label = QLabel(tr("浮译", "LiveFloat"))
        self.title_label.setObjectName("overlayTitle")
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setFixedWidth(16)
        self.level_bars = LevelBars()
        header.addWidget(self.title_label)
        header.addWidget(self.status_dot)
        header.addSpacing(6)
        header.addWidget(self.level_bars)
        header.addStretch(1)

        self.lock_btn = QToolButton()
        self.lock_btn.setObjectName("overlayBtn")
        self.lock_btn.setText("🔓")
        self.lock_btn.setCursor(Qt.PointingHandCursor)
        self.lock_btn.clicked.connect(self._on_lock_clicked)

        self.settings_btn = QToolButton()
        self.settings_btn.setObjectName("overlayBtn")
        self.settings_btn.setText("⚙")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self._on_settings)

        self.close_btn = QToolButton()
        self.close_btn.setObjectName("overlayBtn")
        self.close_btn.setText("✕")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_hide)

        header.addWidget(self.lock_btn)
        header.addWidget(self.settings_btn)
        header.addWidget(self.close_btn)
        self.header_widget = QWidget()
        self.header_widget.setLayout(header)
        card_layout.addWidget(self.header_widget)

        # Scrollable history.
        self.scroll = QScrollArea()
        self.scroll.setObjectName("historyScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.history_widget = QWidget()
        self.history_widget.setObjectName("historyWidget")
        self.history_layout = QVBoxLayout(self.history_widget)
        self.history_layout.setContentsMargins(0, 0, 2, 0)
        self.history_layout.setSpacing(4)
        self.scroll.setWidget(self.history_widget)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_value)
        card_layout.addWidget(self.scroll, 1)

        self._apply_style()
        self._retranslate()
        self._rebuild()

    # ------------------------------------------------------------------
    def _apply_style(self) -> None:
        alpha = int(self.cfg.overlay_opacity * 235)
        self.setStyleSheet(
            f"""
            #overlayCard {{
                background: rgba(10, 13, 20, {alpha});
                border: 1px solid rgba(255, 255, 255, 28);
                border-radius: 18px;
            }}
            #historyScroll, #historyWidget {{ background: transparent; border: none; }}
            #historyScroll QScrollBar:vertical {{
                background: transparent; width: 8px; margin: 2px 0;
            }}
            #historyScroll QScrollBar::handle:vertical {{
                background: rgba(255,255,255,40); border-radius: 4px; min-height: 24px;
            }}
            #historyScroll QScrollBar::add-line:vertical,
            #historyScroll QScrollBar::sub-line:vertical {{ height: 0; }}
            #overlayTitle {{
                color: rgba(255, 255, 255, 150);
                font-size: 12px;
                font-weight: 600;
            }}
            #statusDot {{ color: #8A94A6; font-size: 12px; }}
            #overlayBtn {{
                background: transparent; border: none; border-radius: 6px;
                color: rgba(255, 255, 255, 150); font-size: 15px; padding: 3px;
            }}
            #overlayBtn:hover {{ background: rgba(255, 255, 255, 22); }}
            #originalText {{ color: rgba(255, 255, 255, 145); }}
            #translationText {{ color: #FFFFFF; }}
            #segmentRowCurrent {{ border-left: 3px solid #5B8CFF; border-radius: 8px; }}
            #placeholderText {{ color: rgba(255, 255, 255, 115); }}
            #errorText {{ color: #FF6B6B; }}
            """
        )
        self._status_color()

    def _status_color(self) -> None:
        colors = {
            "listening": "#3DDC97",
            "loading": "#FFB454",
            "error": "#FF6B6B",
            "idle": "#8A94A6",
        }
        self.status_dot.setStyleSheet(f"#statusDot {{ color: {colors.get(self._status, '#8A94A6')}; font-size: 12px; }}")

    def _retranslate(self) -> None:
        self.setWindowTitle(tr("浮译 LiveFloat", "LiveFloat"))
        self.title_label.setText(tr("浮译", "LiveFloat"))
        self.lock_btn.setToolTip(tr("锁定后字幕将鼠标穿透（快捷键 Ctrl+Alt+L）", "Lock to make subtitles click-through (Ctrl+Alt+L)"))
        self.settings_btn.setToolTip(tr("打开控制台", "Open settings"))
        self.close_btn.setToolTip(tr("隐藏字幕", "Hide subtitles"))

    # ------------------------------------------------------------------
    def set_segments(self, segments: list[Segment]) -> None:
        self._segments = list(segments)
        self._rebuild()

    def set_status(self, status: str) -> None:
        self._status = status
        self._status_color()
        if not self._segments:
            self._rebuild()

    def set_level(self, level: float) -> None:
        self._level = level
        self.level_bars.set_level(level)

    def retranslate_ui(self) -> None:
        self._retranslate()
        self._rebuild()

    def _rebuild(self) -> None:
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not self._segments:
            placeholder = QLabel()
            placeholder.setObjectName("placeholderText")
            placeholder.setWordWrap(True)
            placeholder.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if self._status == "listening":
                placeholder.setText(tr("正在聆听，等待网页声音…", "Listening — waiting for audio…"))
            elif self._status == "loading":
                placeholder.setText(tr("正在加载识别模型…", "Loading speech model…"))
            elif self._status == "error":
                placeholder.setText(tr("启动失败，请打开控制台查看原因", "Failed to start — open settings for details"))
            else:
                placeholder.setText(tr("浮译已就绪 · 打开控制台并点击“开始翻译”", "Ready — open settings and press “Start”"))
            f = QFont("Microsoft YaHei UI", max(13, int(self.cfg.overlay_font_size * 0.55)))
            placeholder.setFont(f)
            self.history_layout.addStretch(1)
            self.history_layout.addWidget(placeholder)
            self.history_layout.addStretch(1)
        else:
            # Top spacer pushes the newest segment to the bottom of the box
            # (and collapses to nothing once history fills the viewport).
            self.history_layout.addStretch(1)
            show = self._segments[-self.cfg.overlay_max_history:]
            for i, seg in enumerate(show):
                current = i == len(show) - 1
                row = SegmentRow(self.cfg, current)
                same = seg.translation == seg.text
                row.original.setVisible(self.cfg.show_original and not same)
                row.original.setText(seg.text)
                if seg.state == "error":
                    row.translation.setText(f"⚠ {seg.text}" if same else f"⚠ {tr('翻译失败', 'Translation failed')}：{seg.error or tr('未知错误', 'unknown error')}")
                    row.translation.setObjectName("errorText")
                elif not seg.translation:
                    row.translation.setText(tr("翻译中…", "Translating…"))
                else:
                    row.translation.setText(seg.translation)
                self.history_layout.addWidget(row)

        self._update_size()
        if self._pinned_to_bottom:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _update_size(self) -> None:
        self.setFixedWidth(self.cfg.overlay_width)
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        # A subtitle box viewport of roughly `overlay_max_lines` rows, capped
        # at 55% of the screen height.
        row_h = int(self.cfg.overlay_font_size * 2.0)
        desired = max(90, row_h * max(1, self.cfg.overlay_max_lines))
        cap = max(120, int(geo.height() * 0.55))
        self.scroll.setFixedHeight(min(desired, cap))
        self.adjustSize()
        self._clamp_and_position()

    def _clamp_and_position(self) -> None:
        screen = QGuiApplication.screenAt(self.frameGeometry().center()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        w = min(self.width(), geo.width() - 24)
        self.setFixedWidth(max(360, w))

        if self._auto_position or self.cfg.overlay_x <= -9999:
            x = geo.left() + (geo.width() - self.width()) // 2
            y = geo.bottom() - self.height() - _MARGIN_BOTTOM
            self.move(x, max(geo.top(), y))
        else:
            x = min(max(self.cfg.overlay_x, geo.left()), geo.right() - self.width())
            y = min(max(self.cfg.overlay_y, geo.top()), geo.bottom() - self.height())
            self.move(x, y)

    # ------------------------------------------------------------------
    @staticmethod
    def _snapshot_fields(cfg: Config) -> tuple:
        return (
            cfg.overlay_font_size,
            cfg.overlay_width,
            cfg.overlay_max_lines,
            cfg.overlay_max_history,
            cfg.show_original,
            cfg.ui_lang,
            cfg.overlay_opacity,
            cfg.click_through,
        )

    def apply_config(self, cfg: Config) -> None:
        # Compare against a value snapshot, not the object reference: the
        # store mutates the *same* Config instance, so object identity is
        # useless for detecting changes.
        old = self._snapshot
        new = self._snapshot_fields(cfg)
        layout_changed = new[0:6] != old[0:6]
        opacity_changed = new[6] != old[6]
        click_changed = new[7] != old[7]
        lang_changed = new[5] != old[5]
        self._snapshot = new
        self.cfg = cfg

        if opacity_changed or layout_changed or lang_changed:
            self._apply_style()
        if lang_changed:
            self._retranslate()
        if layout_changed or not self._segments:
            self._rebuild()
        if click_changed:
            self.set_click_through(cfg.click_through)

    def set_click_through(self, enabled: bool) -> None:
        changed = self._click_through_applied is None or enabled != self.cfg.click_through
        self.cfg.click_through = enabled
        self.header_widget.setVisible(not enabled)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, enabled)
        self.lock_btn.setText("🔒" if enabled else "🔓")
        if changed:
            self._click_through_applied = enabled
            self._reapply_flags()

    def set_topmost_enabled(self, enabled: bool) -> None:
        self._topmost_enabled = enabled
        self._reassert_topmost()

    def show_overlay(self) -> None:
        if not self.cfg.show_overlay:
            return
        self.show()
        self._after_show()

    def hide_overlay(self) -> None:
        self.hide()

    def reset_position(self) -> None:
        self._auto_position = True
        self.cfg.overlay_x = -99999
        self.cfg.overlay_y = -99999
        self._rebuild()

    # ------------------------------------------------------------------
    def _on_scroll_value(self, value: int) -> None:
        bar = self.scroll.verticalScrollBar()
        self._pinned_to_bottom = value >= bar.maximum() - 4

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_lock_clicked(self) -> None:
        target = not self.cfg.click_through
        self.set_click_through(target)
        if self.on_lock_toggle:
            self.on_lock_toggle(target)

    def _on_settings(self) -> None:
        if self.on_settings:
            self.on_settings()

    def _on_hide(self) -> None:
        self.hide()
        if self.on_hide:
            self.on_hide()

    # ------------------------------------------------------------------
    def _reapply_flags(self) -> None:
        self.setWindowFlag(Qt.WindowTransparentForInput, self.cfg.click_through)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.show()
        self._after_show()

    def _after_show(self) -> None:
        hwnd = int(self.winId())
        set_ex_style(hwnd, WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        set_topmost(hwnd, self._topmost_enabled)
        show_no_activate(hwnd)

    def _reassert_topmost(self) -> None:
        if self.isVisible() and self._topmost_enabled:
            set_topmost(int(self.winId()), True)

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._after_show()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.header_widget.geometry().contains(event.position().toPoint()):
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._auto_position = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint()) or QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                new_pos.setX(min(max(new_pos.x(), geo.left()), geo.right() - self.width()))
                new_pos.setY(min(max(new_pos.y(), geo.top()), geo.bottom() - self.height()))
            self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_offset is not None and event.button() == Qt.LeftButton:
            self._drag_offset = None
            self.cfg.overlay_x = self.x()
            self.cfg.overlay_y = self.y()
            if self.on_position_changed:
                self.on_position_changed(self.x(), self.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)
