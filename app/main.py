from __future__ import annotations

import ctypes
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox

from .config import Config
from .paths import APP_ID, APP_NAME, config_path, logs_dir, resource_path

_MUTEX_NAME = f"Local\\{APP_NAME}.SingleInstance"


def _setup_logging() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        logs_dir().mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(logs_dir() / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    return logging.getLogger("LiveFloat")


log = _setup_logging()


def _load_icon() -> QIcon:
    path = resource_path("icon.png")
    if path.exists():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    # Fallback: a solid rounded square so the tray/icon never looks broken.
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    from PySide6.QtGui import QColor, QPainter, QPainterPath

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path_rect = QPainterPath()
    path_rect.addRoundedRect(8, 8, 240, 240, 56, 56)
    p.fillPath(path_rect, QColor("#5B8CFF"))
    p.setPen(QColor("#FFFFFF"))
    font = p.font()
    font.setPixelSize(120)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pm.rect(), Qt.AlignCenter, "译")
    p.end()
    return QIcon(pm)


def _bring_existing_to_front() -> None:
    try:
        user32 = ctypes.windll.user32
        hwnd = (
            user32.FindWindowW(None, "浮译 LiveFloat · 控制台")
            or user32.FindWindowW(None, "LiveFloat · Settings")
        )
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _ensure_single_instance() -> bool:
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            _bring_existing_to_front()
            return False
        return True
    except Exception:
        return True


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log.error("Unhandled exception:\n%s", text)
    try:
        QMessageBox.critical(None, "浮译 LiveFloat · 发生错误", text[-2000:])
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main() -> int:
    sys.excepthook = _excepthook

    # Load config early so we can point Hugging Face at a reachable mirror
    # before faster-whisper (and huggingface_hub) is imported.
    cfg = Config.load()
    from .asr import configure_hf

    configure_hf(cfg.hf_endpoint)

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("LiveFloat")
    app.setQuitOnLastWindowClosed(False)

    from .theme import apply_theme

    apply_theme(app, cfg.ui_theme)

    icon = _load_icon()
    app.setWindowIcon(icon)

    if not _ensure_single_instance():
        return 0

    from .config import ConfigStore
    from .controller import AppController
    from . import __version__

    store = ConfigStore(cfg)
    controller = AppController(store, icon)
    controller.start()

    log.info("LiveFloat %s started (config=%s)", __version__, config_path())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
