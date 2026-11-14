from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .i18n import tr

log = logging.getLogger(__name__)


class TrayController(QObject):
    show_settings = Signal()
    toggle_listening = Signal()
    toggle_overlay = Signal()
    toggle_lock = Signal()
    quit_app = Signal()

    def __init__(self, icon: QIcon, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(tr("浮译 LiveFloat", "LiveFloat"))
        self._menu = QMenu()
        self._listening = False
        self._locked = False
        self._build_menu()
        self.tray.setContextMenu(self._menu)
        self.tray.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        m = self._menu
        m.clear()
        self.act_settings = QAction(tr("打开控制台", "Open settings"), m)
        self.act_start = QAction(tr("开始翻译", "Start"), m)
        self.act_overlay = QAction(tr("显示/隐藏字幕浮窗", "Show / hide overlay"), m)
        self.act_lock = QAction(tr("锁定/解锁字幕（鼠标穿透）", "Lock / unlock overlay"), m)
        self.act_quit = QAction(tr("退出", "Quit"), m)
        for a in (self.act_settings, self.act_start, self.act_overlay, self.act_lock):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_quit)

        self.act_settings.triggered.connect(self.show_settings.emit)
        self.act_start.triggered.connect(self.toggle_listening.emit)
        self.act_overlay.triggered.connect(self.toggle_overlay.emit)
        self.act_lock.triggered.connect(self.toggle_lock.emit)
        self.act_quit.triggered.connect(self.quit_app.emit)

        self.set_listening(self._listening)
        self.set_locked(self._locked)

    def retranslate(self) -> None:
        self.tray.setToolTip(tr("浮译 LiveFloat", "LiveFloat"))
        self._build_menu()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_settings.emit()

    def show(self) -> None:
        self.tray.show()

    def hide(self) -> None:
        self.tray.hide()

    def set_listening(self, listening: bool) -> None:
        self._listening = listening
        self.act_start.setText(tr("停止翻译", "Stop") if listening else tr("开始翻译", "Start"))

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.act_lock.setText(tr("解锁字幕（恢复点击）", "Unlock overlay") if locked else tr("锁定字幕（鼠标穿透）", "Lock overlay (click-through)"))

    def notify(self, title: str, message: str) -> None:
        try:
            self.tray.showMessage(title, message, QSystemTrayIcon.Information, 4000)
        except Exception:
            log.warning("tray notification failed", exc_info=True)
