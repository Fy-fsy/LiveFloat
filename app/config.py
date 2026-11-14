from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .paths import config_path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Choices shown in the UI.  The value in the second tuple item is what gets
# persisted; the first item is the human readable label.
# ---------------------------------------------------------------------------

SOURCE_LANGUAGES: list[tuple[str, str]] = [
    ("auto", "自动检测"),
    ("en", "英语 English"),
    ("ja", "日语 日本語"),
    ("ko", "韩语 한국어"),
    ("zh", "中文"),
    ("fr", "法语 Français"),
    ("de", "德语 Deutsch"),
    ("es", "西班牙语 Español"),
    ("ru", "俄语 Русский"),
    ("it", "意大利语 Italiano"),
    ("pt", "葡萄牙语 Português"),
]

TARGET_LANGUAGES: list[tuple[str, str]] = [
    ("zh-CN", "简体中文"),
    ("zh-TW", "繁體中文"),
    ("en", "English"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("ru", "Русский"),
]

# key -> (UI label, faster-whisper repository id, approximate download size)
ASR_MODELS: dict[str, tuple[str, str, str]] = {
    "base": ("Base · 推荐（约 145 MB，速度与准确度均衡）", "Systran/faster-whisper-base", "145 MB"),
    "small": ("Small · 更准确（约 480 MB，CPU 占用更高）", "Systran/faster-whisper-small", "480 MB"),
    "base.en": ("Base English · 英文专用（约 145 MB，最快）", "Systran/faster-whisper-base.en", "145 MB"),
    "small.en": ("Small English · 英文专用（约 480 MB）", "Systran/faster-whisper-small.en", "480 MB"),
    "medium": ("Medium · 高准确度（约 1.5 GB，较慢）", "Systran/faster-whisper-medium", "1.5 GB"),
}

TRANSLATORS: list[tuple[str, str]] = [
    ("mymemory", "MyMemory · 免费在线（无需密钥）"),
    ("deepseek", "DeepSeek / OpenAI 兼容 · 质量最佳"),
    ("google", "Google 翻译 · 需网络可访问"),
    ("edge", "Microsoft Edge 翻译"),
    ("offline", "Argos 离线翻译（完全本地）"),
]

PROVIDER_LABELS = dict(TRANSLATORS)


def language_label(code: str) -> str:
    for value, label in SOURCE_LANGUAGES + TARGET_LANGUAGES:
        if value == code:
            return label
    return code


def language_name_for_prompt(code: str) -> str:
    """Human language name used in LLM prompts."""
    names = {
        "zh-CN": "简体中文",
        "zh-TW": "繁體中文",
        "zh": "中文",
        "en": "English",
        "ja": "日本語",
        "ko": "한국어",
        "fr": "Français",
        "de": "Deutsch",
        "es": "Español",
        "ru": "Русский",
        "it": "Italiano",
        "pt": "Português",
    }
    return names.get(code, code)


@dataclass
class Config:
    # --- audio -------------------------------------------------------------
    audio_device_name: str = ""
    audio_device_index: int = -1

    # --- recognition -------------------------------------------------------
    asr_model: str = "base"
    source_lang: str = "auto"
    compute_type: str = "int8"
    vad_threshold: float = 0.50
    silence_ms: int = 650
    max_segment_s: float = 8.0
    hf_endpoint: str = "https://hf-mirror.com"

    # --- translation -------------------------------------------------------
    translator: str = "mymemory"
    target_lang: str = "zh-CN"
    api_base: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    api_model: str = "deepseek-chat"
    mymemory_email: str = ""
    # Offline (Argos) translation direction.
    argos_pair: str = "en_zh"

    # --- overlay -----------------------------------------------------------
    show_overlay: bool = True
    click_through: bool = False
    overlay_font_size: int = 30
    overlay_opacity: float = 0.86
    overlay_width: int = 980
    overlay_max_lines: int = 3
    overlay_max_history: int = 300
    show_original: bool = True
    overlay_x: int = -99999
    overlay_y: int = -99999

    # --- subtitles recording ----------------------------------------------
    record_subtitles: bool = True
    subtitle_format: str = "md"
    subtitle_dir: str = ""

    # --- application -------------------------------------------------------
    auto_start: bool = False
    close_to_tray: bool = True
    first_run: bool = True
    ui_lang: str = "zh-CN"
    ui_theme: str = "dark"

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        cfg = cls()
        if not path.exists():
            return cfg
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config root is not an object")
            known = {f.name for f in fields(cls)}
            for key, value in raw.items():
                if key in known and value is not None:
                    setattr(cfg, key, value)
            cfg.normalise()
        except Exception as exc:  # corrupt config should never prevent startup
            log.warning("Could not read config %s: %s", path, exc)
            try:
                path.replace(path.with_suffix(".bad.json"))
            except OSError:
                pass
        return cfg

    def normalise(self) -> None:
        if self.asr_model not in ASR_MODELS:
            self.asr_model = "base"
        if self.source_lang not in {v for v, _ in SOURCE_LANGUAGES}:
            self.source_lang = "auto"
        if self.target_lang not in {v for v, _ in TARGET_LANGUAGES}:
            self.target_lang = "zh-CN"
        if self.translator not in {v for v, _ in TRANSLATORS}:
            self.translator = "mymemory"
        self.vad_threshold = min(0.85, max(0.20, float(self.vad_threshold)))
        self.silence_ms = int(min(1800, max(250, self.silence_ms)))
        self.max_segment_s = float(min(15.0, max(4.0, self.max_segment_s)))
        self.overlay_font_size = int(min(58, max(16, self.overlay_font_size)))
        self.overlay_opacity = float(min(1.0, max(0.35, self.overlay_opacity)))
        self.overlay_width = int(min(1800, max(560, self.overlay_width)))
        self.overlay_max_lines = int(min(6, max(1, self.overlay_max_lines)))
        self.overlay_max_history = int(min(1000, max(10, self.overlay_max_history)))
        if self.subtitle_format not in ("md", "txt"):
            self.subtitle_format = "md"
        if self.ui_lang not in ("zh-CN", "en"):
            self.ui_lang = "zh-CN"
        if self.ui_theme not in ("dark", "light"):
            self.ui_theme = "dark"
        if self.argos_pair not in ("en_zh", "zh_en"):
            self.argos_pair = "en_zh"
        self.audio_device_index = int(self.audio_device_index)
        self.overlay_x = int(self.overlay_x)
        self.overlay_y = int(self.overlay_y)
        if not self.hf_endpoint:
            self.hf_endpoint = "https://hf-mirror.com"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self) -> None:
        path = config_path()
        tmp = path.with_suffix(".tmp")
        data = json.dumps(self.as_dict(), ensure_ascii=False, indent=2)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            # Never let a read-only/blocked data dir take the whole app down.
            log.warning("Could not save config to %s: %s", path, exc)

    def copy(self) -> "Config":
        return Config(**self.as_dict())


class ConfigStore:
    """Thread-safe wrapper around Config with atomic persistence."""

    def __init__(self, config: Config | None = None) -> None:
        self._lock = threading.RLock()
        self.config = config or Config.load()
        self.config.normalise()

    def get(self) -> Config:
        with self._lock:
            return self.config

    def replace(self, cfg: Config) -> None:
        with self._lock:
            self.config = cfg
            cfg.normalise()
            cfg.save()

    def save(self) -> None:
        with self._lock:
            self.config.save()

    def update(self, **kwargs: Any) -> Config:
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
            self.config.normalise()
            self.config.save()
            return self.config


def default_model_cache_path() -> Path:
    from .paths import models_dir

    return models_dir()
