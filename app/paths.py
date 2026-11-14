from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "LiveFloat"
APP_ID = "LiveFloat.App.1"
APP_DISPLAY_NAME = "浮译 LiveFloat"
VERSION = "1.0.0"


def project_root() -> Path:
    """Directory that contains the ``assets`` folder (works frozen and from source)."""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: sys._MEIPASS is the _internal folder.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return project_root().joinpath("assets", *parts)


def _probe_writable(path: Path) -> bool:
    """True if we can actually create and remove a file inside ``path``."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        try:
            probe.unlink()
        except OSError:
            pass
        return True
    except OSError:
        return False


def app_data_dir() -> Path:
    """Return a directory that is *guaranteed* writable for config/logs/models.

    Candidates are tried in order and the first one that passes a real
    write test wins:
      1. ``LIVEFLOAT_DATA_DIR`` environment override
      2. ``%LOCALAPPDATA%\\LiveFloat`` (normal per-user location)
      3. next to the executable / project root (portable mode)
      4. the OS temp directory (last resort)
    """
    import tempfile

    candidates: list[Path] = []

    override = os.environ.get("LIVEFLOAT_DATA_DIR")
    if override:
        candidates.append(Path(override))

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        candidates.append(Path(base) / APP_NAME)
    else:
        candidates.append(Path.home() / "AppData" / "Local" / APP_NAME)

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "LiveFloat-data")
    else:
        candidates.append(project_root() / ".data")

    user = os.environ.get("USERNAME", "user")
    candidates.append(Path(tempfile.gettempdir()) / f"{APP_NAME}-{user}")

    for path in candidates:
        if _probe_writable(path):
            return path
    return candidates[-1]


def _subdir(name: str) -> Path:
    root = app_data_dir()
    path = root / name
    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        import tempfile

        alt = Path(tempfile.gettempdir()) / f"{APP_NAME}-{name}"
        alt.mkdir(parents=True, exist_ok=True)
        return alt


def models_dir() -> Path:
    return _subdir("models")


def logs_dir() -> Path:
    return _subdir("logs")


def config_path() -> Path:
    return app_data_dir() / "config.json"


def cache_dir() -> Path:
    return _subdir("cache")
