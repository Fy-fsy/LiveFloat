from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path
from typing import Callable

import numpy as np

from .config import ASR_MODELS
from .i18n import tr
from .paths import models_dir

log = logging.getLogger(__name__)

_HF_LOCK = threading.Lock()
_engine = None  # type: ignore

# Silly things Whisper occasionally emits on silence / music.  Lowercased,
# without trailing punctuation.
HALLUCINATIONS = {
    "thank you",
    "thank you for watching",
    "thanks for watching",
    "thanks for watching!",
    "subscribe",
    "subscribe to the channel",
    "please subscribe",
    "you",
    ".",
    "..",
    "...",
}

_CJK_RE = re.compile(r"([\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af])\s+(?=[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af])")
_WS_RE = re.compile(r"\s+")


def configure_hf(endpoint: str) -> None:
    """Point Hugging Face at a reachable mirror and a writable cache *before*
    faster_whisper / huggingface_hub is imported.

    The Xet download backend writes large temp files and can fail on locked-down
    machines, so it is disabled in favour of the plain HTTP downloader.
    """
    if endpoint:
        os.environ.setdefault("HF_ENDPOINT", endpoint.rstrip("/"))
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    # Keep the HF cache inside our own data directory.
    from .paths import app_data_dir

    os.environ.setdefault("HF_HOME", str(app_data_dir() / "hf_cache"))


class AsrEngine:
    def __init__(self, model_key: str = "base", compute_type: str = "int8", threads: int | None = None) -> None:
        self.model_key = model_key
        self.repo = ASR_MODELS.get(model_key, ASR_MODELS["base"])[1]
        self.compute_type = compute_type or "int8"
        self.threads = threads or max(2, (os.cpu_count() or 4) - 1)
        self.model = None

    def _local_dir(self) -> Path:
        return models_dir() / f"whisper-{self.model_key}"

    def _is_cached(self) -> bool:
        return (self._local_dir() / "model.bin").exists()

    # ------------------------------------------------------------------
    def load(
        self,
        status_cb: Callable[[str], None] | None = None,
        progress_cb: Callable[[int], None] | None = None,
    ) -> None:
        if self.model is not None:
            return
        if status_cb:
            status_cb(tr("正在加载识别模型 {m} …", "Loading speech model {m} …").format(m=self.model_key))
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:
            raise RuntimeError("faster-whisper 未安装，无法进行本地识别。") from exc

        local = self._local_dir()
        if not self._is_cached():
            if status_cb:
                status_cb(tr("正在下载识别模型（约 {s}，仅首次）…", "Downloading speech model (~{s}, first run only)…").format(s=ASR_MODELS[self.model_key][2]))
            try:
                self._download(local, progress_cb)
            except Exception as exc:
                raise RuntimeError(f"识别模型下载失败（{self.model_key}）：{exc}") from exc
        if status_cb:
            status_cb(tr("正在加载模型到内存…", "Loading model into memory…"))
        try:
            self.model = WhisperModel(
                str(local),
                device="cpu",
                compute_type=self.compute_type,
                cpu_threads=self.threads,
            )
        except Exception as exc:
            self.model = None
            raise RuntimeError(f"模型加载失败（{self.model_key}）：{exc}") from exc
        if status_cb:
            status_cb(tr("识别模型 {m} 已就绪", "Speech model {m} ready").format(m=self.model_key))

    def _download(self, local_dir: Path, progress_cb: Callable[[int], None] | None) -> None:
        from huggingface_hub import snapshot_download

        local_dir.mkdir(parents=True, exist_ok=True)
        tqdm_cls = _make_progress_tqdm(progress_cb)
        snapshot_download(
            self.repo,
            local_dir=str(local_dir),
            tqdm_class=tqdm_cls,
        )

    # ------------------------------------------------------------------
    def transcribe(self, audio: np.ndarray, language: str | None) -> tuple[str, str, float]:
        """Return (text, language_code, avg_logprob)."""
        if self.model is None:
            raise RuntimeError("识别模型尚未加载")
        samples = np.asarray(audio, dtype=np.float32)
        segments, info = self.model.transcribe(
            samples,
            language=language or None,
            task="transcribe",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            without_timestamps=True,
            vad_filter=False,
            no_speech_threshold=0.60,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            repetition_penalty=1.05,
        )
        parts: list[str] = []
        probs: list[float] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if text:
                parts.append(text)
                probs.append(float(getattr(seg, "avg_logprob", -1.0) or -1.0))
        text = clean_text(" ".join(parts))
        avg_prob = float(np.mean(probs)) if probs else -1.0
        lang = str(getattr(info, "language", language or "en") or "en")
        return text, lang, avg_prob

    def is_hallucination(self, text: str, avg_prob: float, duration: float) -> bool:
        if not text:
            return True
        key = re.sub(r"[.。!！?？,，、\s]+$", "", text.strip()).lower()
        if key in HALLUCINATIONS and duration < 1.2:
            return True
        if avg_prob < -1.25:
            return True
        return False


def clean_text(text: str) -> str:
    text = _WS_RE.sub(" ", text).strip()
    # Remove spaces that break CJK reading (Whisper sometimes inserts them).
    prev = None
    while prev != text:
        prev = text
        text = _CJK_RE.sub(r"\1", text)
    return text.strip()


def is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))


def model_cached(model_key: str) -> bool:
    """Best-effort check whether a model is already downloaded locally."""
    try:
        return (models_dir() / f"whisper-{model_key}" / "model.bin").exists()
    except Exception:
        return False


def _make_progress_tqdm(progress_cb: Callable[[int], None] | None):
    """A tqdm-compatible class that forwards percentage to ``progress_cb``."""

    class _ProgressTqdm:
        def __init__(self, total: int | None = None, desc: str = "", **kwargs):
            self.total = int(total or 0)
            self.desc = desc or ""
            self.n = 0
            self._cb = progress_cb

        def update(self, n: int = 1) -> None:
            self.n += int(n)
            if self.total and self._cb:
                self._cb(min(100, int(self.n * 100 / self.total)))

        def close(self) -> None:
            pass

        def set_description(self, desc: str) -> None:
            self.desc = desc

        def refresh(self) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _ProgressTqdm


def unload_global_engine() -> None:
    global _engine
    _engine = None
