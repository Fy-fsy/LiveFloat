from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .audio import enumerate_loopback_devices
from .config import (
    ASR_MODELS,
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
    TRANSLATORS,
    ConfigStore,
)
from .i18n import set_language, tr
from .offline import ARGOS_MODELS, is_installed
from .subtitle_log import SubtitleRecorder
from .theme import theme_tokens

log = logging.getLogger(__name__)

SUCCESS = "#3DDC97"
WARNING = "#FFB454"
DANGER = "#FF6B6B"


class LevelMeter(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(14)
        self._level = 0.0

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        from .theme import current_theme, theme_tokens

        tok = theme_tokens(current_theme())
        track = tok["BORDER"]
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(track))
        p.drawRoundedRect(0, 1, self.width(), self.height() - 2, 7, 7)
        color = QColor(SUCCESS) if self._level > 0.02 else QColor(track)
        p.setBrush(color)
        p.drawRoundedRect(0, 1, int(self.width() * self._level), self.height() - 2, 7, 7)
        p.end()


class SettingsWindow(QWidget):
    config_changed = Signal(object)   # Config
    start_clicked = Signal()
    stop_clicked = Signal()
    preload_clicked = Signal()
    preview_requested = Signal()
    install_offline_requested = Signal()
    delete_subtitles_requested = Signal()
    language_changed = Signal(str)
    theme_changed = Signal(str)
    quit_requested = Signal()

    def __init__(self, store: ConfigStore, icon: QIcon | None = None, recorder: SubtitleRecorder | None = None) -> None:
        super().__init__()
        self.store = store
        self.cfg = store.get()
        self._loading = True
        self._active = False
        self._state = "idle"
        self._footer_text = tr("就绪", "Ready")
        self.recorder = recorder or SubtitleRecorder()
        self.setWindowTitle(tr("浮译 LiveFloat · 控制台", "LiveFloat · Settings"))
        self.setWindowIcon(icon) if icon else None
        self.resize(900, 720)
        self.setMinimumSize(780, 620)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(350)
        self._save_timer.timeout.connect(self._do_save)

        self._build_ui()
        self._load_config_into_ui()
        self._loading = False

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 10)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)
        self.title_box = QVBoxLayout()
        self.title_box.setSpacing(1)
        self.title_label = QLabel(tr("浮译 LiveFloat", "LiveFloat"))
        self.title_label.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.subtitle_label = QLabel(tr("网页音频 · 实时识别 · 浮窗翻译", "Web audio · live ASR · floating subtitles"))
        self.subtitle_label.setObjectName("cardSubtitle")
        self.title_box.addWidget(self.title_label)
        self.title_box.addWidget(self.subtitle_label)
        header.addLayout(self.title_box)
        header.addStretch(1)

        self.lang_btn = QPushButton("EN")
        self.lang_btn.setCursor(Qt.PointingHandCursor)
        self.lang_btn.setToolTip(tr("切换界面语言", "Switch UI language"))
        self.lang_btn.clicked.connect(self._on_lang_switch)
        header.addWidget(self.lang_btn)

        self.theme_btn = QPushButton()
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip(tr("切换深色/亮色模式", "Toggle dark / light mode"))
        self.theme_btn.clicked.connect(self._on_theme_switch)
        header.addWidget(self.theme_btn)

        self.status_pill = QLabel(tr("未开始", "Idle"))
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setAlignment(Qt.AlignCenter)
        self.status_pill.setStyleSheet(self._pill_style("idle"))
        header.addWidget(self.status_pill)
        self.start_btn = QPushButton(tr("开始翻译", "Start"))
        self.start_btn.setObjectName("primary")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_start_btn)
        header.addWidget(self.start_btn)
        root.addLayout(header)

        # Tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_tabs()

        # Footer
        footer = QHBoxLayout()
        self.footer_status = QLabel(tr("就绪", "Ready"))
        self.footer_status.setObjectName("hint")
        footer.addWidget(self.footer_status)
        footer.addStretch(1)
        root.addLayout(footer)

    def _build_tabs(self) -> None:
        self.tabs.addTab(self._build_audio_tab(), tr("音频", "Audio"))
        self.tabs.addTab(self._build_recognition_tab(), tr("识别", "Recognition"))
        self.tabs.addTab(self._build_translation_tab(), tr("翻译", "Translate"))
        self.tabs.addTab(self._build_overlay_tab(), tr("浮窗", "Overlay"))
        self.tabs.addTab(self._build_subtitles_tab(), tr("字幕记录", "Transcript"))
        self.tabs.addTab(self._build_about_tab(), tr("关于", "About"))

    # ------------------------------------------------------------------
    def _card(self, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("cardTitle")
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("cardSubtitle")
            s.setWordWrap(True)
            lay.addWidget(s)
        return frame, lay

    def _scroll(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        return area

    # ------------------------------------------------------------------
    def _build_audio_tab(self) -> QWidget:
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(14)

        # Device card.
        dev_card, dev_lay = self._card(
            tr("播放设备", "Output device"),
            tr("直接捕获电脑正在播放的声音（WASAPI 环回），无需安装虚拟声卡。", "Captures whatever your PC is playing (WASAPI loopback) — no virtual sound card needed."),
        )
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(34)
        self.refresh_devices_btn = QPushButton(tr("刷新设备", "Refresh"))
        self.refresh_devices_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_devices_btn.clicked.connect(self._refresh_devices)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.device_combo, 1)
        row.addWidget(self.refresh_devices_btn)
        dev_lay.addLayout(row)
        dev_hint = QLabel(tr("如果网页声音从耳机播放，请选择对应的耳机设备；切换设备后需重新“开始”。", "Pick the device the web audio actually plays from (e.g. headphones); restart after switching."))
        dev_hint.setObjectName("hint")
        dev_hint.setWordWrap(True)
        dev_lay.addWidget(dev_hint)
        page_lay.addWidget(dev_card)

        # Level card.
        lvl_card, lvl_lay = self._card(
            tr("输入音量", "Input level"),
            tr("播放网页/视频/会议时，此条会随声音起伏。", "Moves with the sound while audio is playing."),
        )
        level_row = QHBoxLayout()
        level_row.setSpacing(12)
        self.level_label = QLabel(tr("当前电平", "Level"))
        self.level_label.setObjectName("hint")
        self.level_meter = LevelMeter()
        self.level_meter.setFixedHeight(24)
        self.level_value = QLabel("0%")
        self.level_value.setObjectName("cardSubtitle")
        self.level_value.setFixedWidth(44)
        self.level_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        level_row.addWidget(self.level_label)
        level_row.addWidget(self.level_meter, 1)
        level_row.addWidget(self.level_value)
        lvl_lay.addLayout(level_row)
        page_lay.addWidget(lvl_card)
        page_lay.addStretch(1)

        self._refresh_devices()
        return self._scroll(page)

    def _refresh_devices(self) -> None:
        current = self.device_combo.currentData()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        try:
            devices = enumerate_loopback_devices()
        except Exception as exc:
            self.device_combo.addItem(tr("（无法枚举设备：%s）", "(cannot enumerate: %s)") % exc, None)
        else:
            for dev in devices:
                self.device_combo.addItem(dev.display_name, dev.name)
        self.device_combo.blockSignals(False)
        if current:
            idx = self.device_combo.findData(current)
            if idx >= 0:
                self.device_combo.setCurrentIndex(idx)
        if self.device_combo.count() == 0:
            self.device_combo.addItem(tr("（未找到可用播放设备）", "(no output device found)"), None)

    # ------------------------------------------------------------------
    def _build_recognition_tab(self) -> QWidget:
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(10)

        card, lay = self._card(
            tr("识别引擎", "Speech recognition"),
            tr("使用 faster-whisper 本地识别（离线、免费、隐私安全）。首次使用会自动下载模型。", "Local faster-whisper ASR (offline, free, private). The model is downloaded on first use."),
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.model_combo = QComboBox()
        for key, (label, _repo, _size) in ASR_MODELS.items():
            self.model_combo.addItem(label, key)
        form.addRow(tr("模型：", "Model:"), self.model_combo)

        self.source_combo = QComboBox()
        for value, label in SOURCE_LANGUAGES:
            self.source_combo.addItem(label, value)
        form.addRow(tr("源语言：", "Source language:"), self.source_combo)

        preload = QPushButton(tr("提前下载 / 加载模型", "Pre-download / load model"))
        preload.clicked.connect(self.preload_clicked.emit)
        form.addRow("", preload)
        lay.addLayout(form)

        self.rec_model_status = QLabel(tr("尚未加载模型", "Model not loaded yet"))
        self.rec_model_status.setObjectName("hint")
        self.rec_model_status.setWordWrap(True)
        lay.addWidget(self.rec_model_status)

        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 100)
        self.model_progress.setValue(0)
        self.model_progress.setTextVisible(True)
        self.model_progress.setFormat(tr("下载中 %p%", "Downloading %p%"))
        self.model_progress.hide()
        lay.addWidget(self.model_progress)
        page_lay.addWidget(card)

        adv, adv_lay = self._card(tr("高级（VAD 分段）", "Advanced (VAD)"), tr("一般无需修改。", "Usually no changes needed."))
        adv_form = QFormLayout()
        adv_form.setSpacing(10)
        self.vad_slider = QSlider(Qt.Horizontal)
        self.vad_slider.setRange(20, 85)
        self.vad_value = QLabel("0.50")
        self.vad_slider.valueChanged.connect(lambda v: self.vad_value.setText(f"{v / 100:.2f}"))
        vr = QHBoxLayout(); vr.addWidget(self.vad_slider, 1); vr.addWidget(self.vad_value)
        adv_form.addRow(tr("VAD 阈值：", "VAD threshold:"), vr)

        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(250, 1800)
        self.silence_spin.setSingleStep(50)
        self.silence_spin.setSuffix(" ms")
        adv_form.addRow(tr("静音断句：", "Silence gap:"), self.silence_spin)

        self.max_seg_spin = QDoubleSpinBox()
        self.max_seg_spin.setRange(4.0, 15.0)
        self.max_seg_spin.setSingleStep(0.5)
        self.max_seg_spin.setSuffix(tr(" 秒", " s"))
        adv_form.addRow(tr("最长分段：", "Max segment:"), self.max_seg_spin)
        adv_lay.addLayout(adv_form)
        page_lay.addWidget(adv)
        page_lay.addStretch(1)

        for w in (self.model_combo, self.source_combo):
            w.currentIndexChanged.connect(lambda _i: self._mark_changed())
        for w in (self.vad_slider, self.silence_spin, self.max_seg_spin):
            if isinstance(w, QSlider):
                w.valueChanged.connect(lambda _v: self._mark_changed())
            else:
                w.valueChanged.connect(lambda _v: self._mark_changed())
        return self._scroll(page)

    # ------------------------------------------------------------------
    def _build_translation_tab(self) -> QWidget:
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(10)

        card, lay = self._card(
            tr("在线翻译通道", "Online translation"),
            tr("MyMemory 免费无需密钥；追求质量与稳定性请使用 DeepSeek/OpenAI 兼容接口。", "MyMemory is free with no key; use a DeepSeek/OpenAI-compatible endpoint for best quality."),
        )
        form = QFormLayout()
        form.setSpacing(10)
        self.provider_combo = QComboBox()
        for value, label in TRANSLATORS:
            self.provider_combo.addItem(label, value)
        form.addRow(tr("翻译通道：", "Provider:"), self.provider_combo)

        self.target_combo = QComboBox()
        for value, label in TARGET_LANGUAGES:
            self.target_combo.addItem(label, value)
        form.addRow(tr("目标语言：", "Target language:"), self.target_combo)
        lay.addLayout(form)

        api_form = QFormLayout()
        api_form.setSpacing(10)
        self.api_base_edit = QLineEdit()
        self.api_base_edit.setPlaceholderText("https://api.deepseek.com/v1")
        api_form.addRow(tr("API Base：", "API Base:"), self.api_base_edit)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_key_edit.setPlaceholderText("sk-…")
        api_form.addRow(tr("API Key：", "API Key:"), self.api_key_edit)
        self.api_model_edit = QLineEdit()
        self.api_model_edit.setPlaceholderText("deepseek-chat")
        api_form.addRow(tr("模型名：", "Model:"), self.api_model_edit)
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText(tr("（可选）填入邮箱可提高 MyMemory 免费额度", "(optional) email raises the MyMemory free quota"))
        api_form.addRow(tr("MyMemory 邮箱：", "MyMemory email:"), self.email_edit)
        lay.addLayout(api_form)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton(tr("测试翻译", "Test translation"))
        self.test_btn.clicked.connect(self._on_test_translate)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        self.test_result.setObjectName("hint")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result, 1)
        lay.addLayout(test_row)
        page_lay.addWidget(card)

        # Offline Argos card (download UI lives outside the provider combo).
        off_card, off_lay = self._card(
            tr("离线翻译模型（Argos）", "Offline translation model (Argos)"),
            tr("在“翻译通道”选择 Argos 离线后使用。完全离线、无需联网、无需密钥；首次使用需下载约 70 MB 模型。", "Select “Argos offline” as the provider to use it. Fully offline, no network, no key; first use downloads a ~70 MB model."),
        )
        off_form = QFormLayout()
        self.argos_pair_combo = QComboBox()
        for pair, (_url, label, _size) in ARGOS_MODELS.items():
            self.argos_pair_combo.addItem(label, pair)
        off_form.addRow(tr("离线方向：", "Direction:"), self.argos_pair_combo)
        off_lay.addLayout(off_form)

        self.offline_status = QLabel("")
        self.offline_status.setObjectName("hint")
        self.offline_status.setWordWrap(True)
        off_lay.addWidget(self.offline_status)

        self.install_offline_btn = QPushButton(tr("下载 / 安装离线模型", "Download / install offline model"))
        self.install_offline_btn.clicked.connect(self.install_offline_requested.emit)
        off_lay.addWidget(self.install_offline_btn)
        page_lay.addWidget(off_card)
        page_lay.addStretch(1)

        for w in (self.provider_combo, self.target_combo):
            w.currentIndexChanged.connect(self._on_provider_changed)
        for w in (self.api_base_edit, self.api_key_edit, self.api_model_edit, self.email_edit):
            w.textChanged.connect(lambda _t: self._mark_changed())
        self.argos_pair_combo.currentIndexChanged.connect(lambda _i: self._mark_changed())
        self._on_provider_changed()
        return self._scroll(page)

    def _on_provider_changed(self) -> None:
        if not hasattr(self, "api_key_edit"):
            return
        provider = self.provider_combo.currentData()
        is_llm = provider == "deepseek"
        is_mymemory = provider == "mymemory"
        # DeepSeek needs API fields; MyMemory needs the email; others need none.
        for w in (self.api_base_edit, self.api_key_edit, self.api_model_edit):
            w.setEnabled(is_llm)
        self.email_edit.setEnabled(is_mymemory)
        self._mark_changed()

    def _on_test_translate(self) -> None:
        from .translate import TranslationManager

        self.test_result.setText(tr("翻译中…", "Translating…"))
        self._mark_changed()
        self._do_save()
        manager = TranslationManager()

        def _run() -> None:
            try:
                result = manager.test(self.store.get())
                self.test_result.setText(tr("结果：", "Result: ") + result)
            except Exception as exc:
                self.test_result.setText(tr("失败：", "Failed: ") + str(exc))

        import threading

        threading.Thread(target=_run, daemon=True).start()

    # ------------------------------------------------------------------
    def _build_overlay_tab(self) -> QWidget:
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(10)

        card, lay = self._card(
            tr("字幕浮窗", "Subtitle overlay"),
            tr("置顶、半透明、可拖拽；锁定后鼠标穿透。字幕浮窗内可上下滑动查看历史。", "Always-on-top, translucent, draggable; click-through when locked. Scroll inside the overlay to review history."),
        )
        grid = QGridLayout()
        grid.setSpacing(12)
        self.show_overlay_cb = QCheckBox(tr("显示字幕浮窗", "Show subtitle overlay"))
        self.click_through_cb = QCheckBox(tr("锁定（鼠标穿透）", "Lock (click-through)"))
        self.show_original_cb = QCheckBox(tr("同时显示原文", "Show original text"))
        grid.addWidget(self.show_overlay_cb, 0, 0)
        grid.addWidget(self.click_through_cb, 0, 1)
        grid.addWidget(self.show_original_cb, 1, 0)
        lay.addLayout(grid)

        form = QFormLayout()
        form.setSpacing(12)
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(16, 58)
        self.font_value = QLabel("30")
        self.font_slider.valueChanged.connect(lambda v: self.font_value.setText(str(v)))
        self.font_slider.sliderReleased.connect(self._mark_changed)
        fr = QHBoxLayout(); fr.addWidget(self.font_slider, 1); fr.addWidget(self.font_value)
        form.addRow(tr("字号：", "Font size:"), fr)

        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(35, 100)
        self.opacity_value = QLabel("86%")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_value.setText(f"{v}%"))
        self.opacity_slider.sliderReleased.connect(self._mark_changed)
        orow = QHBoxLayout(); orow.addWidget(self.opacity_slider, 1); orow.addWidget(self.opacity_value)
        form.addRow(tr("背景不透明度：", "Opacity:"), orow)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(560, 1800)
        self.width_spin.setSingleStep(20)
        self.width_spin.setSuffix(" px")
        form.addRow(tr("浮窗宽度：", "Width:"), self.width_spin)

        self.history_spin = QSpinBox()
        self.history_spin.setRange(10, 1000)
        self.history_spin.setSingleStep(10)
        form.addRow(tr("历史保留条数：", "History kept:"), self.history_spin)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton(tr("重置浮窗位置", "Reset position"))
        reset_btn.clicked.connect(self._on_reset_position)
        self.preview_btn = QPushButton(tr("预览示例字幕", "Preview sample"))
        self.preview_btn.clicked.connect(self._on_preview)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(self.preview_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        hint = QLabel(tr("快捷键：Ctrl+Alt+F 显示/隐藏浮窗 · Ctrl+Alt+L 锁定/解锁 · Ctrl+Alt+S 打开控制台", "Hotkeys: Ctrl+Alt+F overlay · Ctrl+Alt+L lock · Ctrl+Alt+S settings"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        page_lay.addWidget(card)
        page_lay.addStretch(1)

        for w in (self.show_overlay_cb, self.click_through_cb, self.show_original_cb):
            w.toggled.connect(lambda _v: self._mark_changed())
        for w in (self.width_spin, self.history_spin):
            w.valueChanged.connect(lambda _v: self._mark_changed())
        return self._scroll(page)

    def _on_reset_position(self) -> None:
        self._reset_position_signal = True
        self._mark_changed()

    def _on_preview(self) -> None:
        self.preview_requested.emit()

    # ------------------------------------------------------------------
    def _build_subtitles_tab(self) -> QWidget:
        page = QWidget()
        page_lay = QVBoxLayout(page)
        page_lay.setContentsMargins(8, 8, 8, 8)
        page_lay.setSpacing(10)

        card, lay = self._card(
            tr("字幕记录", "Subtitle recording"),
            tr("每次“开始翻译”到“停止/退出”会生成一个独立会话文件。", "Each Start→Stop session writes to its own file."),
        )
        self.record_cb = QCheckBox(tr("记录字幕到文件", "Record subtitles to file"))
        lay.addWidget(self.record_cb)

        form = QFormLayout()
        form.setSpacing(10)
        self.format_combo = QComboBox()
        self.format_combo.addItem("Markdown (.md)", "md")
        self.format_combo.addItem("Text (.txt)", "txt")
        form.addRow(tr("文件格式：", "Format:"), self.format_combo)

        self.subtitle_dir_edit = QLineEdit()
        self.subtitle_dir_edit.setPlaceholderText(tr("（默认）应用数据目录", "(default) app data dir"))
        self.subtitle_dir_btn = QPushButton(tr("选择…", "Browse…"))
        self.subtitle_dir_btn.clicked.connect(self._on_choose_subtitle_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.subtitle_dir_edit, 1)
        dir_row.addWidget(self.subtitle_dir_btn)
        form.addRow(tr("保存位置：", "Save location:"), dir_row)
        lay.addLayout(form)

        self.subtitle_path_label = QLabel("")
        self.subtitle_path_label.setObjectName("hint")
        self.subtitle_path_label.setWordWrap(True)
        self.subtitle_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.subtitle_path_label)

        btn_row = QHBoxLayout()
        self.delete_btn = QPushButton(tr("一键删除字幕记录文件", "Delete all recorded subtitle files"))
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self.delete_subtitles_requested.emit)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        page_lay.addWidget(card)
        page_lay.addStretch(1)

        self.record_cb.toggled.connect(lambda _v: self._mark_changed())
        self.format_combo.currentIndexChanged.connect(lambda _i: self._mark_changed())
        self.subtitle_dir_edit.textChanged.connect(lambda _t: self._mark_changed())
        return self._scroll(page)

    def _on_choose_subtitle_dir(self) -> None:
        start = self.subtitle_dir_edit.text().strip() or str(self.recorder._dir())
        chosen = QFileDialog.getExistingDirectory(self, tr("选择字幕保存位置", "Choose subtitle save location"), start)
        if chosen:
            self.subtitle_dir_edit.setText(chosen)

    def update_subtitle_path(self) -> None:
        fmt = self.format_combo.currentData() or "md"
        current = self.recorder.current_file
        if current is not None:
            self.subtitle_path_label.setText(tr("当前会话文件：", "Current session file: ") + str(current))
        else:
            d = self.recorder._dir()
            self.subtitle_path_label.setText(tr("保存目录：", "Save directory: ") + str(d))

    # ------------------------------------------------------------------
    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        title = QLabel(f"LiveFloat v{__version__}")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        lay.addWidget(title)

        producer = QLabel(tr("制作人：风色龑", "Author: 风色龑"))
        producer.setStyleSheet("font-size: 14px; font-weight: 600;")
        lay.addWidget(producer)

        github = QLabel()
        github.setOpenExternalLinks(True)
        github.setTextFormat(Qt.RichText)
        github.setText(
            tr(
                '项目仓库：<a href="https://github.com/Fy-fsy/LiveFloat">https://github.com/Fy-fsy/LiveFloat</a>',
                'Repository: <a href="https://github.com/Fy-fsy/LiveFloat">https://github.com/Fy-fsy/LiveFloat</a>',
            )
        )
        lay.addWidget(github)

        about = QLabel(
            tr(
                "实时捕获 Windows 系统音频，本地语音识别 + 多通道翻译，以置顶浮窗形式显示双语字幕。\n\n"
                "致谢 / Credits：\n"
                "· 主程序由 DeepSeek AI 生成，风色龑提供提示词与需求\n"
                "· 语音识别：faster-whisper (SYSTRAN)\n"
                "· 语音活动检测：Silero VAD\n"
                "· 音频捕获：PyAudioWPatch（WASAPI 环回）\n"
                "· 离线翻译：Argos Translate / CTranslate2 / SentencePiece\n"
                "· 重采样：soxr\n"
                "· 界面：PySide6 (Qt)\n"
                "· 模型托管：Hugging Face（镜像 hf-mirror.com）\n\n"
                "识别模型由 Hugging Face 提供；离线翻译模型来自 Argos Translate。\n"
                "本软件仅供学习交流。",
                "Captures Windows system audio, transcribes locally, translates via multiple providers, and shows bilingual subtitles in an always-on-top overlay.\n\n"
                "Credits:\n"
                "· Main program generated by DeepSeek AI; prompts & requirements by 风色龑\n"
                "· ASR: faster-whisper (SYSTRAN)\n"
                "· VAD: Silero VAD\n"
                "· Audio capture: PyAudioWPatch (WASAPI loopback)\n"
                "· Offline translation: Argos Translate / CTranslate2 / SentencePiece\n"
                "· Resampling: soxr\n"
                "· UI: PySide6 (Qt)\n"
                "· Model hosting: Hugging Face (mirror hf-mirror.com)\n\n"
                "For learning purposes only.",
            )
        )
        about.setWordWrap(True)
        about.setObjectName("cardSubtitle")
        lay.addWidget(about)
        lay.addStretch(1)
        return self._scroll(page)

    # ------------------------------------------------------------------
    def _load_config_into_ui(self) -> None:
        c = self.cfg
        self.device_combo.setCurrentIndex(self.device_combo.findData(c.audio_device_name))

        self.model_combo.setCurrentIndex(self._find_data(self.model_combo, c.asr_model))
        self.source_combo.setCurrentIndex(self._find_data(self.source_combo, c.source_lang))
        self.vad_slider.setValue(int(round(c.vad_threshold * 100)))
        self.silence_spin.setValue(c.silence_ms)
        self.max_seg_spin.setValue(c.max_segment_s)

        self.provider_combo.setCurrentIndex(self._find_data(self.provider_combo, c.translator))
        self.target_combo.setCurrentIndex(self._find_data(self.target_combo, c.target_lang))
        self.api_base_edit.setText(c.api_base)
        self.api_key_edit.setText(c.api_key)
        self.api_model_edit.setText(c.api_model)
        self.email_edit.setText(c.mymemory_email)
        self.argos_pair_combo.setCurrentIndex(self._find_data(self.argos_pair_combo, c.argos_pair))

        self.show_overlay_cb.setChecked(c.show_overlay)
        self.click_through_cb.setChecked(c.click_through)
        self.show_original_cb.setChecked(c.show_original)
        self.font_slider.setValue(c.overlay_font_size)
        self.opacity_slider.setValue(int(round(c.overlay_opacity * 100)))
        self.width_spin.setValue(c.overlay_width)
        self.history_spin.setValue(c.overlay_max_history)

        self.record_cb.setChecked(c.record_subtitles)
        self.format_combo.setCurrentIndex(self._find_data(self.format_combo, c.subtitle_format))
        self.subtitle_dir_edit.setText(c.subtitle_dir)
        self.recorder.set_directory(c.subtitle_dir)

        self.lang_btn.setText("EN" if c.ui_lang == "zh-CN" else "中文")
        self.theme_btn.setText(tr("亮色", "Light") if c.ui_theme == "dark" else tr("深色", "Dark"))
        self._on_provider_changed()
        self.refresh_offline_status()
        self.update_subtitle_path()

    @staticmethod
    def _find_data(combo: QComboBox, data: str) -> int:
        idx = combo.findData(data)
        return idx if idx >= 0 else 0

    # ------------------------------------------------------------------
    def _mark_changed(self) -> None:
        if self._loading:
            return
        c = self.store.get()
        c.audio_device_name = self.device_combo.currentData() or ""
        c.asr_model = self.model_combo.currentData()
        c.source_lang = self.source_combo.currentData()
        c.vad_threshold = self.vad_slider.value() / 100.0
        c.silence_ms = self.silence_spin.value()
        c.max_segment_s = self.max_seg_spin.value()

        c.translator = self.provider_combo.currentData()
        c.target_lang = self.target_combo.currentData()
        c.api_base = self.api_base_edit.text().strip()
        c.api_key = self.api_key_edit.text().strip()
        c.api_model = self.api_model_edit.text().strip()
        c.mymemory_email = self.email_edit.text().strip()
        c.argos_pair = self.argos_pair_combo.currentData()

        c.show_overlay = self.show_overlay_cb.isChecked()
        c.click_through = self.click_through_cb.isChecked()
        c.show_original = self.show_original_cb.isChecked()
        c.overlay_font_size = self.font_slider.value()
        c.overlay_opacity = self.opacity_slider.value() / 100.0
        c.overlay_width = self.width_spin.value()
        c.overlay_max_history = self.history_spin.value()

        c.record_subtitles = self.record_cb.isChecked()
        c.subtitle_format = self.format_combo.currentData()
        c.subtitle_dir = self.subtitle_dir_edit.text().strip()
        self.recorder.set_directory(c.subtitle_dir)

        if getattr(self, "_reset_position_signal", False):
            c.overlay_x = -99999
            c.overlay_y = -99999
            self._reset_position_signal = False

        c.normalise()
        self.update_subtitle_path()
        self.refresh_offline_status()
        self.config_changed.emit(c)
        self._save_timer.start()

    def _do_save(self) -> None:
        try:
            self.store.save()
        except Exception as exc:
            log.warning("save config failed: %s", exc)

    # ------------------------------------------------------------------
    def refresh_offline_status(self) -> None:
        pair = self.argos_pair_combo.currentData() or "en_zh"
        if is_installed(pair):
            self.offline_status.setText(tr("✅ 离线模型已安装", "✅ Offline model installed"))
        else:
            self.offline_status.setText(tr("⚠ 尚未安装离线模型，请点击下方按钮下载", "⚠ Offline model not installed — download below"))

    def set_offline_status(self, text: str) -> None:
        self.offline_status.setText(text)

    def set_subtitle_result(self, text: str) -> None:
        self.set_footer_status(text)

    def _on_lang_switch(self) -> None:
        c = self.store.get()
        new_lang = "en" if c.ui_lang == "zh-CN" else "zh-CN"
        set_language(new_lang)
        c.ui_lang = new_lang
        c.normalise()
        self.store.replace(c)
        self.language_changed.emit(new_lang)

    def _on_theme_switch(self) -> None:
        c = self.store.get()
        new_theme = "light" if c.ui_theme == "dark" else "dark"
        c.ui_theme = new_theme
        c.normalise()
        self.store.replace(c)
        self.theme_btn.setText(tr("深色", "Dark") if new_theme == "light" else tr("亮色", "Light"))
        self.theme_changed.emit(new_theme)

    # ------------------------------------------------------------------
    def _pill_style(self, state: str) -> str:
        light = self.store.get().ui_theme == "light"
        tok = theme_tokens("light" if light else "dark")
        if state == "idle":
            bg, fg = tok["PANEL_2"], tok["MUTED"]
        elif light:
            # Solid, high-contrast pill backgrounds for the light theme.
            if state == "loading":
                bg, fg = "#FFE3B3", "#7a4a00"
            elif state == "listening":
                bg, fg = "#C9F2DE", "#0a6b45"
            else:
                bg, fg = "#FFD4D4", "#a02020"
        else:
            if state == "loading":
                bg, fg = WARNING + "22", WARNING
            elif state == "listening":
                bg, fg = SUCCESS + "22", SUCCESS
            else:
                bg, fg = DANGER + "22", DANGER
        return f"padding: 5px 14px; border-radius: 14px; background: {bg}; color: {fg}; font-weight: 600;"

    def set_pipeline_state(self, state: str, message: str = "") -> None:
        label = {
            "idle": tr("未开始", "Idle"),
            "loading": tr("准备中", "Loading"),
            "listening": tr("聆听中", "Listening"),
            "error": tr("出错", "Error"),
        }.get(state, tr("未开始", "Idle"))
        self.status_pill.setText(label)
        self.status_pill.setStyleSheet(self._pill_style(state))
        self._state = state
        self._active = state in ("loading", "listening")
        self.start_btn.setText(tr("停止", "Stop") if self._active else tr("开始翻译", "Start"))

    def retranslate_ui(self) -> None:
        c = self.store.get()
        self.setWindowTitle(tr("浮译 LiveFloat · 控制台", "LiveFloat · Settings"))
        self.title_label.setText(tr("浮译 LiveFloat", "LiveFloat"))
        self.subtitle_label.setText(tr("网页音频 · 实时识别 · 浮窗翻译", "Web audio · live ASR · floating subtitles"))
        self.lang_btn.setText("EN" if c.ui_lang == "zh-CN" else "中文")
        self.theme_btn.setText(tr("亮色", "Light") if c.ui_theme == "dark" else tr("深色", "Dark"))
        self.start_btn.setText(tr("停止", "Stop") if self._active else tr("开始翻译", "Start"))
        self.status_pill.setText({
            "idle": tr("未开始", "Idle"),
            "loading": tr("准备中", "Loading"),
            "listening": tr("聆听中", "Listening"),
            "error": tr("出错", "Error"),
        }.get(self._state, tr("未开始", "Idle")))
        self.status_pill.setStyleSheet(self._pill_style(self._state))
        # Rebuild tab pages in place (window geometry is preserved).
        idx = self.tabs.currentIndex()
        self.tabs.clear()
        self._build_tabs()
        self.tabs.setCurrentIndex(min(idx, self.tabs.count() - 1))
        self._loading = True
        self._load_config_into_ui()
        self._loading = False

    def refresh_theme(self) -> None:
        c = self.store.get()
        self.theme_btn.setText(tr("亮色", "Light") if c.ui_theme == "dark" else tr("深色", "Dark"))
        self.status_pill.setStyleSheet(self._pill_style(self._state))

    def set_level(self, level: float) -> None:
        self.level_meter.set_level(level)
        if hasattr(self, "level_value"):
            self.level_value.setText(f"{int(level * 100)}%")

    def set_model_status(self, text: str) -> None:
        self.rec_model_status.setText(text)

    def set_download_progress(self, pct: int) -> None:
        self.model_progress.setValue(max(0, min(100, int(pct))))
        if pct >= 100:
            self.model_progress.hide()
        else:
            self.model_progress.show()

    def set_footer_status(self, text: str) -> None:
        self._footer_text = text
        self.footer_status.setText(text)

    def _on_start_btn(self) -> None:
        if self._active:
            self.stop_clicked.emit()
        else:
            self.start_clicked.emit()

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.store.get().close_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()
