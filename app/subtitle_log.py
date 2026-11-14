from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from .i18n import tr
from .paths import cache_dir

log = logging.getLogger(__name__)


class SubtitleRecorder:
    """Writes subtitles to a per-session file (one session = Start → Stop)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session_file: Path | None = None
        self._custom_dir = ""

    def set_directory(self, path: str) -> None:
        self._custom_dir = (path or "").strip()

    def _dir(self) -> Path:
        if self._custom_dir:
            d = Path(self._custom_dir)
        else:
            d = cache_dir() / "subtitles"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def current_file(self) -> Path | None:
        return self._session_file

    def start_session(self, fmt: str) -> Path:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = self._dir() / f"session-{ts}.{fmt}"
        with self._lock:
            self._session_file = path
            try:
                path.write_text(f"# {tr('浮译字幕记录', 'LiveFloat transcript')} · {ts}\n", encoding="utf-8")
            except OSError as exc:
                log.warning("Could not init subtitle file: %s", exc)
        return path

    def append(self, text: str, translation: str, fmt: str = "md") -> None:
        if not text and not translation:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        original_label = tr("原文", "Original")
        translated_label = tr("译文", "Translation")
        with self._lock:
            if self._session_file is None:
                self.start_session(fmt)
            if self._session_file is None:
                return
            if fmt == "md":
                lines = [
                    f"\n## {ts}\n",
                    f"- {original_label}：{text}\n",
                    f"- {translated_label}：{translation}\n",
                ]
            else:
                lines = [
                    f"[{ts}] {original_label}：{text}\n",
                    f"[{ts}] {translated_label}：{translation}\n",
                ]
            try:
                with self._session_file.open("a", encoding="utf-8") as fh:
                    fh.writelines(lines)
            except OSError as exc:
                log.warning("Could not write subtitle record: %s", exc)

    def list_files(self) -> list[Path]:
        try:
            return sorted(self._dir().glob("session-*"))
        except OSError:
            return []

    def delete_all(self) -> int:
        """Delete every recorded subtitle file; return the number removed."""
        removed = 0
        with self._lock:
            for path in self.list_files():
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    log.warning("Could not delete %s", path)
        return removed
