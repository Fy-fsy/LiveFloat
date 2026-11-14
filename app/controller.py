from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import Config, ConfigStore
from .hotkeys import HotkeyManager
from .i18n import tr
from .overlay import SubtitleOverlay
from .pipeline import Pipeline, Segment
from .settings import SettingsWindow
from .subtitle_log import SubtitleRecorder
from .tray import TrayController

log = logging.getLogger(__name__)


class AppController(QObject):
    def __init__(self, store: ConfigStore, icon: QIcon) -> None:
        super().__init__()
        self.store = store
        self.icon = icon
        self.segments: list[Segment] = []
        self._max_segments = 600
        self._recorded_ids: set[int] = set()
        self._last_state = "idle"
        self.recorder = SubtitleRecorder()

        self.pipeline = Pipeline(store.get)
        self.settings = SettingsWindow(store, icon, recorder=self.recorder)
        self.overlay = SubtitleOverlay(
            store.get(),
            on_settings=self.show_settings,
            on_lock_toggle=self._on_lock_changed,
            on_hide=self._on_overlay_hidden,
            on_position_changed=self._on_position_changed,
        )
        self.tray = TrayController(icon)
        self.hotkeys = HotkeyManager()

        self._connect_signals()
        self._apply_overlay_config(store.get(), first=True)

    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        p = self.pipeline
        p.state_changed.connect(self._on_pipeline_state)
        p.status_message.connect(self._on_status)
        p.level_changed.connect(self._on_level)
        p.segment_added.connect(self._on_segment_added)
        p.segment_updated.connect(self._on_segment_updated)
        p.error.connect(self._on_error)
        p.download_progress.connect(self._on_download_progress)

        self.tray.show_settings.connect(self.show_settings)
        self.tray.toggle_listening.connect(self.toggle_listening)
        self.tray.toggle_overlay.connect(self.toggle_overlay)
        self.tray.toggle_lock.connect(self.toggle_lock)
        self.tray.quit_app.connect(self.quit)

        self.hotkeys.toggle_overlay.connect(self.toggle_overlay)
        self.hotkeys.toggle_lock.connect(self.toggle_lock)
        self.hotkeys.open_settings.connect(self.show_settings)

        self._wire_settings(self.settings)

    def _wire_settings(self, s: SettingsWindow) -> None:
        s.config_changed.connect(self._on_config_changed)
        s.start_clicked.connect(self.toggle_listening)
        s.stop_clicked.connect(self.stop_listening)
        s.preload_clicked.connect(self._on_preload)
        s.preview_requested.connect(self._on_preview)
        s.install_offline_requested.connect(self._on_install_offline)
        s.delete_subtitles_requested.connect(self._on_delete_subtitles)
        s.language_changed.connect(self._on_language_changed)
        s.theme_changed.connect(self._on_theme_changed)
        s.quit_requested.connect(self.quit)

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.hotkeys.register_defaults()
        QApplication.instance().installNativeEventFilter(self.hotkeys.native_filter)
        self.tray.show()
        self.overlay.set_status("idle")
        if self.store.get().show_overlay:
            self.overlay.show_overlay()
        cfg = self.store.get()
        if cfg.first_run:
            self.settings.show_and_raise()
            self.tray.notify("LiveFloat", tr("首次使用：请先打开控制台，点击“开始翻译”自动下载识别模型。", "First run: open settings and press “Start” to download the ASR model."))
            cfg.first_run = False
            self.store.save()
        else:
            self.settings.show_and_raise()
        if cfg.auto_start:
            QTimer.singleShot(600, self.toggle_listening)

    # ------------------------------------------------------------------
    def toggle_listening(self) -> None:
        if self.pipeline.running:
            self.stop_listening()
        else:
            self.start_listening()

    def start_listening(self) -> None:
        if self.pipeline.running:
            return
        cfg = self.store.get()
        if not cfg.show_overlay:
            cfg.show_overlay = True
            self.store.save()
        self.recorder.set_directory(cfg.subtitle_dir)
        if cfg.record_subtitles:
            self.recorder.start_session(cfg.subtitle_format)
            self.settings.update_subtitle_path()
        self.overlay.show_overlay()
        self.overlay.set_status("loading")
        self.pipeline.start()

    def stop_listening(self) -> None:
        self.pipeline.stop()

    # ------------------------------------------------------------------
    def _on_pipeline_state(self, state: str) -> None:
        self._last_state = state
        self.settings.set_pipeline_state(state)
        self.overlay.set_status(state)
        self.tray.set_listening(state in ("loading", "listening"))

    def _on_status(self, message: str) -> None:
        self.settings.set_footer_status(message)
        self.settings.set_model_status(message)

    def _on_level(self, level: float) -> None:
        # Route dynamically so the meter keeps working after a window rebuild.
        self.settings.set_level(level)
        self.overlay.set_level(level)

    def _on_download_progress(self, pct: int) -> None:
        self.settings.set_download_progress(pct)

    def _on_error(self, message: str) -> None:
        log.error("Pipeline error: %s", message)
        self.settings.set_footer_status(tr("错误：", "Error: ") + message)
        self.tray.notify(tr("浮译 · 出错了", "LiveFloat · Error"), message)

    # ------------------------------------------------------------------
    def _on_segment_added(self, segment: Segment) -> None:
        self.segments.append(segment)
        if len(self.segments) > self._max_segments:
            self.segments = self.segments[-self._max_segments:]
        self.overlay.set_segments(self.segments)
        self._maybe_record(segment)

    def _on_segment_updated(self, segment: Segment) -> None:
        for i, existing in enumerate(self.segments):
            if existing.id == segment.id:
                self.segments[i] = segment
                break
        self.overlay.set_segments(self.segments)
        self._maybe_record(segment)

    def _maybe_record(self, segment: Segment) -> None:
        if segment.state != "done" or segment.id in self._recorded_ids:
            return
        if not segment.translation:
            return
        cfg = self.store.get()
        if not cfg.record_subtitles:
            return
        self._recorded_ids.add(segment.id)
        if len(self._recorded_ids) > 2000:
            self._recorded_ids.clear()
        try:
            self.recorder.append(segment.text, segment.translation, cfg.subtitle_format)
        except Exception as exc:
            log.warning("subtitle record failed: %s", exc)

    # ------------------------------------------------------------------
    def _on_config_changed(self, cfg: Config) -> None:
        self.store.replace(cfg)
        self._apply_overlay_config(cfg)

    def _apply_overlay_config(self, cfg: Config, first: bool = False) -> None:
        self.overlay.apply_config(cfg)
        if not cfg.show_overlay:
            self.overlay.hide_overlay()
        elif not first:
            self.overlay.show_overlay()

    def _on_lock_changed(self, locked: bool) -> None:
        cfg = self.store.get()
        cfg.click_through = locked
        self.store.save()
        self.settings.click_through_cb.blockSignals(True)
        self.settings.click_through_cb.setChecked(locked)
        self.settings.click_through_cb.blockSignals(False)
        self.tray.set_locked(locked)

    def _on_overlay_hidden(self) -> None:
        cfg = self.store.get()
        cfg.show_overlay = False
        self.store.save()
        self.settings.show_overlay_cb.blockSignals(True)
        self.settings.show_overlay_cb.setChecked(False)
        self.settings.show_overlay_cb.blockSignals(False)

    def _on_position_changed(self, x: int, y: int) -> None:
        cfg = self.store.get()
        cfg.overlay_x = x
        cfg.overlay_y = y
        self.store.save()

    # ------------------------------------------------------------------
    def _on_preload(self) -> None:
        self.pipeline.preload_model(status_cb=self.settings.set_model_status)

    def _on_preview(self) -> None:
        preview = [
            Segment(id=-1, text="So the first thing we need to understand is how it works.",
                    translation="所以首先我们需要理解它是如何工作的。", state="done", source_lang="en", target_lang="zh-CN"),
            Segment(id=-2, text="Let me show you a quick example.",
                    translation="让我给你看一个简单的例子。", state="done", source_lang="en", target_lang="zh-CN"),
        ]
        self.overlay.set_segments(preview)

    def _on_install_offline(self) -> None:
        pair = self.store.get().argos_pair

        def _work() -> None:
            try:
                from .offline import install_model

                install_model(pair, status_cb=self.settings.set_offline_status)
                self.settings.refresh_offline_status()
                self.settings.set_offline_status(tr("离线模型已就绪，可在“翻译通道”选择 Argos 离线", "Offline model ready — choose “Argos offline” as the provider"))
            except Exception as exc:
                self.settings.set_offline_status(tr("下载失败：", "Download failed: ") + str(exc))

        self.settings.set_offline_status(tr("开始下载离线模型…", "Starting offline model download…"))
        threading.Thread(target=_work, daemon=True).start()

    def _on_delete_subtitles(self) -> None:
        n = self.recorder.delete_all()
        self.settings.update_subtitle_path()
        self.settings.set_footer_status(tr(f"已删除 {n} 个字幕记录文件", f"Deleted {n} subtitle file(s)"))
        self.tray.notify(tr("字幕记录", "Subtitles"), tr(f"已删除 {n} 个文件", f"Deleted {n} file(s)"))

    # ------------------------------------------------------------------
    def _on_language_changed(self, lang: str) -> None:
        from .i18n import set_language

        set_language(lang)
        self.overlay.retranslate_ui()
        self.tray.retranslate()
        self.settings.retranslate_ui()

    def _on_theme_changed(self, theme: str) -> None:
        from .theme import apply_theme

        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self.settings.refresh_theme()

    # ------------------------------------------------------------------
    def toggle_overlay(self) -> None:
        cfg = self.store.get()
        if self.overlay.isVisible():
            self.overlay.hide_overlay()
            cfg.show_overlay = False
        else:
            cfg.show_overlay = True
            self.overlay.show_overlay()
        self.store.save()
        self.settings.show_overlay_cb.blockSignals(True)
        self.settings.show_overlay_cb.setChecked(cfg.show_overlay)
        self.settings.show_overlay_cb.blockSignals(False)

    def toggle_lock(self) -> None:
        cfg = self.store.get()
        target = not cfg.click_through
        cfg.click_through = target
        self.store.save()
        self.overlay.set_click_through(target)
        self.settings.click_through_cb.blockSignals(True)
        self.settings.click_through_cb.setChecked(target)
        self.settings.click_through_cb.blockSignals(False)
        self.tray.set_locked(target)

    def show_settings(self) -> None:
        self.settings.show_and_raise()

    # ------------------------------------------------------------------
    def quit(self) -> None:
        self.pipeline.shutdown()
        self.hotkeys.unregister_all()
        self.tray.hide()
        self.overlay.close()
        QApplication.instance().quit()
