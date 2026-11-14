"""Headless smoke test: construct the whole app under the offscreen platform
and make sure nothing throws.  Run with:  python tools/smoke_test.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402


def main() -> int:
    from app.config import Config, ConfigStore
    from app.controller import AppController
    from app.paths import resource_path

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    cfg = Config()
    cfg.first_run = False
    cfg.auto_start = False
    store = ConfigStore(cfg)

    from PySide6.QtGui import QIcon

    icon = QIcon(str(resource_path("icon.png")))
    controller = AppController(store, icon)

    # Don't actually start the pipeline / tray in headless mode.
    assert controller.pipeline is not None
    assert controller.overlay is not None
    assert controller.settings is not None
    assert controller.tray is not None
    assert controller.hotkeys is not None

    # Exercise the parts of the UI that don't need a real window station.
    controller.settings.set_pipeline_state("listening")
    controller.overlay.set_status("listening")
    controller.overlay.set_segments([])
    controller.settings.set_level(0.5)
    controller.overlay.set_level(0.5)
    controller.settings.set_model_status("smoke test ok")

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
