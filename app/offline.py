from __future__ import annotations

import io
import logging
import re
import time
import zipfile
from pathlib import Path
from typing import Callable

import requests

from .paths import models_dir

log = logging.getLogger(__name__)

_CJK_SPACE_RE = re.compile(r"([\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af])\s+(?=[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af])")

# Argos OpenNMT models (CTranslate2 + SentencePiece).  The .argosmodel file is
# a plain zip containing a `model/` directory and `sentencepiece.model`.
ARGOS_MODELS: dict[str, tuple[str, str, str]] = {
    # pair -> (download url, human label, ~size)
    "en_zh": (
        "https://argos-net.com/v1/translate-en_zh-1_9.argosmodel",
        "English → 简体中文",
        "约 70 MB",
    ),
    "zh_en": (
        "https://argos-net.com/v1/translate-zh_en-1_9.argosmodel",
        "中文 → English",
        "约 70 MB",
    ),
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LiveFloat/1.0"}


def model_dir(pair: str) -> Path:
    return models_dir() / "argos" / pair


def _locate_base(pair: str) -> Path | None:
    """Find the folder that directly contains `sentencepiece.model` + `model/`.

    Argos .argosmodel zips wrap everything in a top-level directory named
    ``translate-en_zh-1_9``, so we search one or two levels deep.
    """
    root = model_dir(pair)
    candidates: list[Path] = [root]
    if root.exists():
        candidates += [p for p in root.iterdir() if p.is_dir()]
    for cand in candidates:
        if (cand / "sentencepiece.model").exists() and (cand / "model").is_dir():
            return cand
    return None


def is_installed(pair: str) -> bool:
    base = _locate_base(pair)
    if base is None:
        return False
    return any((base / "model").glob("model.bin"))


def install_model(pair: str, status_cb: Callable[[str], None] | None = None) -> Path:
    """Download and extract an Argos model.  Returns the model directory."""
    if pair not in ARGOS_MODELS:
        raise ValueError(f"unknown argos pair {pair}")
    url, _label, _size = ARGOS_MODELS[pair]
    dest = model_dir(pair)
    dest.mkdir(parents=True, exist_ok=True)

    def emit(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    emit(f"正在下载离线翻译模型（{_size}，仅首次）…")
    try:
        resp = requests.get(url, headers=_HEADERS, stream=True, timeout=60)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"离线翻译模型下载失败：{exc}") from exc

    total = int(resp.headers.get("Content-Length") or 0)
    buf = io.BytesIO()
    done = 0
    last = time.monotonic()
    for chunk in resp.iter_content(chunk_size=256 * 1024):
        if not chunk:
            continue
        buf.write(chunk)
        done += len(chunk)
        now = time.monotonic()
        if now - last >= 1.0:
            last = now
            if total:
                emit(f"正在下载离线翻译模型… {done * 100 // total}%")
    emit("正在解压离线翻译模型…")
    buf.seek(0)
    try:
        with zipfile.ZipFile(buf) as zf:
            zf.extractall(dest)
    except zipfile.BadZipFile as exc:
        raise RuntimeError("离线翻译模型文件损坏，请删除后重新下载") from exc
    base = _locate_base(pair)
    if base is None:
        raise RuntimeError("离线翻译模型解压后结构异常")
    emit("离线翻译模型已就绪")
    return base


class ArgosOfflineTranslator:
    """Translate with a downloaded Argos model using ctranslate2 + sentencepiece."""

    def __init__(self, pair: str = "en_zh") -> None:
        import ctranslate2
        import sentencepiece as spm

        base = _locate_base(pair)
        if base is None:
            raise RuntimeError("离线翻译模型尚未安装")
        mdir = base / "model"
        if not mdir.exists():
            raise RuntimeError("离线翻译模型缺少 model 目录")

        sp_path = None
        for cand in ("sentencepiece.model", "source.spm"):
            p = base / cand
            if p.exists():
                sp_path = p
                break
        if sp_path is None:
            raise RuntimeError("离线翻译模型缺少 sentencepiece 词表")

        self._sp = spm.SentencePieceProcessor(model_file=str(sp_path))
        self._translator = ctranslate2.Translator(str(mdir), device="cpu", compute_type="int8")

    def translate(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        tokens = self._sp.encode(text, out_type=str)
        if not tokens:
            return ""
        results = self._translator.translate_batch([tokens], beam_size=4, max_batch_size=1)
        out = self._sp.decode(results[0].hypotheses[0])
        # SentencePiece emits "▁" word-boundary markers; normalise them.
        out = out.replace("▁", " ").strip()
        out = re.sub(r"\s+", " ", out)
        out = _CJK_SPACE_RE.sub(r"\1", out)
        return out.strip()
