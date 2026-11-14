from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Any

import requests

from .config import Config, language_name_for_prompt
from .i18n import tr

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LiveFloat/1.0",
}


class TranslationError(RuntimeError):
    pass


def _normalise_source(source: str | None) -> str:
    if not source or source == "auto":
        return "en"
    return source


def _same_language(source: str, target: str) -> bool:
    if not source or source == "auto":
        return False
    s = source.lower().split("-")[0]
    t = target.lower().split("-")[0]
    return s == t


def _offline_pair(source: str, target: str) -> str | None:
    """Map a source/target pair to an installed Argos model pair, if any."""
    s = _normalise_source(source).split("-")[0]
    t = target.lower().split("-")[0]
    if s == "en" and t == "zh":
        return "en_zh"
    if s == "zh" and t == "en":
        return "zh_en"
    return None


def _split_text(text: str, limit: int = 440) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    # Prefer sentence boundaries, then spaces, then hard cut.
    remaining = text
    while len(remaining) > limit:
        cut = -1
        for marker in ("。", "！", "？", ". ", "! ", "? ", "\n"):
            idx = remaining.rfind(marker, 0, limit)
            if idx > limit * 0.4:
                cut = idx + len(marker.rstrip())
                break
        if cut <= 0:
            idx = remaining.rfind(" ", 0, limit)
            if idx > limit * 0.4:
                cut = idx
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class MyMemoryTranslator:
    name = "mymemory"

    def __init__(self, email: str = "") -> None:
        self.email = email
        self.session = requests.Session()

    def translate(self, text: str, source: str, target: str) -> str:
        src = _normalise_source(source)
        langpair = f"{src}|{target}"
        results: list[str] = []
        for chunk in _split_text(text):
            params: dict[str, Any] = {"q": chunk, "langpair": langpair}
            if self.email:
                params["de"] = self.email
            try:
                resp = self.session.get(
                    "https://api.mymemory.translated.net/get",
                    params=params,
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                raise TranslationError(f"MyMemory 请求失败：{exc}") from exc
            status = str(data.get("responseStatus", ""))
            if status not in ("200", 200):
                raise TranslationError(f"MyMemory 返回状态 {status}")
            out = data.get("responseData", {}).get("translatedText", "")
            out = html.unescape(out or "").strip()
            if not out:
                raise TranslationError("MyMemory 返回空结果")
            if "MYMEMORY WARNING" in out.upper() or "QUOTA" in out.upper():
                raise TranslationError("MyMemory 免费额度已用尽，请稍后再试或切换翻译通道")
            results.append(out)
        return " ".join(results)


class GoogleTranslator:
    name = "google"

    def __init__(self) -> None:
        self.session = requests.Session()

    def translate(self, text: str, source: str, target: str) -> str:
        src = _normalise_source(source)
        url = "https://translate.googleapis.com/translate_a/single"
        out_parts: list[str] = []
        for chunk in _split_text(text):
            params = {"client": "gtx", "sl": src, "tl": target, "dt": "t", "q": chunk}
            try:
                resp = self.session.get(url, params=params, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                raise TranslationError(f"Google 翻译失败（可能无法访问）：{exc}") from exc
            try:
                parts = [seg[0] for seg in data[0] if seg and seg[0]]
                out_parts.append("".join(parts).strip())
            except Exception as exc:
                raise TranslationError("Google 翻译响应解析失败") from exc
        return " ".join(out_parts)


class EdgeTranslator:
    name = "edge"

    _TARGET_MAP = {"zh-CN": "zh-Hans", "zh-TW": "zh-Hant"}

    def __init__(self) -> None:
        self.session = requests.Session()

    def translate(self, text: str, source: str, target: str) -> str:
        # The old token flow (edge.microsoft.com/translate/auth) was retired in
        # 2026-07.  The unauthenticated successor is a bare JSON array POST.
        src = "" if not source or source == "auto" else _normalise_source(source)
        tgt = self._TARGET_MAP.get(target, target)
        url = "https://edge.microsoft.com/translate/translatetext"
        params = {"from": src, "to": tgt, "isEnterpriseClient": "false"}
        # The endpoint runs an HTML tag aligner, so escape markup-like chars.
        payload = [html.escape(text, quote=False)]
        try:
            resp = self.session.post(
                url, params=params, json=payload, headers=HEADERS, timeout=20
            )
            resp.raise_for_status()
            data = resp.json()
            result = data[0]["translations"][0]["text"]
            return html.unescape(result).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslationError("Edge 翻译响应解析失败") from exc
        except requests.RequestException as exc:
            raise TranslationError(f"Edge 翻译失败：{exc}") from exc


class LlmTranslator:
    name = "llm"

    def __init__(self, api_base: str, api_key: str, api_model: str) -> None:
        self.api_base = api_base.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.api_model = api_model.strip() or "deepseek-chat"
        self.session = requests.Session()

    def _url(self) -> str:
        base = self.api_base
        if base.endswith("/chat/completions"):
            return base
        if re.search(r"/v\d+$", base):
            return base + "/chat/completions"
        return base + "/v1/chat/completions"

    def translate(self, text: str, source: str, target: str) -> str:
        if not self.api_key:
            raise TranslationError("尚未填写 API Key")
        target_name = language_name_for_prompt(target)
        system = (
            "你是专业的实时字幕翻译引擎。把用户发来的口语化字幕翻译成"
            f"{target_name}。要求：只输出译文本身，不要任何解释、引号或前后缀；"
            "保留说话的语气与标点；专有名词和数字保持不变；如果原文已经是你目标语言，"
            "原样返回。"
        )
        payload = {
            "model": self.api_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
            "stream": False,
        }
        headers = {**HEADERS, "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            resp = self.session.post(self._url(), headers=headers, json=payload, timeout=30)
            if resp.status_code == 401 or resp.status_code == 403:
                raise TranslationError("API Key 无效或没有权限")
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except TranslationError:
            raise
        except Exception as exc:
            raise TranslationError(f"大模型翻译失败：{exc}") from exc
        content = _clean_llm_output(content or "")
        if not content:
            raise TranslationError("大模型返回空内容")
        return content


def _clean_llm_output(content: str) -> str:
    # Drop "thinking" blocks some reasoning models emit.
    content = re.sub(r"<[^>]*think[^>]*>.*?</[^>]*>", "", content, flags=re.S | re.I)
    content = re.sub(r"^\s*(?:译文|翻译)[:：]\s*", "", content)
    content = content.strip()
    content = content.strip('"“”\'')
    return content.strip()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class TranslationManager:
    def __init__(self, max_cache: int = 1000) -> None:
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()
        self.max_cache = max_cache
        self._providers: dict[str, Any] = {}
        self._offline_translators: dict[str, Any] = {}

    def _provider(self, cfg: Config) -> Any:
        key = cfg.translator
        if key in self._providers:
            return self._providers[key]
        if key == "google":
            prov = GoogleTranslator()
        elif key == "edge":
            prov = EdgeTranslator()
        elif key == "deepseek":
            prov = LlmTranslator(cfg.api_base, cfg.api_key, cfg.api_model)
        else:
            prov = MyMemoryTranslator(cfg.mymemory_email)
        self._providers[key] = prov
        return prov

    def _cache_key(self, provider: str, source: str, target: str, text: str) -> tuple:
        return (provider, _normalise_source(source), target, text)

    def translate(self, text: str, source: str, target: str, cfg: Config) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if _same_language(source, target):
            return text

        # Offline Argos provider (fully local, no network).
        if cfg.translator == "offline":
            pair = _offline_pair(source, target)
            if not pair:
                raise TranslationError(tr("离线翻译暂不支持该语言对，请切换翻译通道", "Offline translation does not support this language pair"))
            result = self._offline(pair).translate(text)
            if not result:
                raise TranslationError(tr("离线翻译返回空结果", "Offline translation returned empty result"))
            return result

        order = [cfg.translator]
        if cfg.translator != "mymemory":
            order.append("mymemory")  # graceful free fallback

        errors: list[str] = []
        for provider_name in order:
            key = self._cache_key(provider_name, source, target, text)
            with self._lock:
                cached = self._cache.get(key)
            if cached is not None:
                self._touch(key)
                return cached
            try:
                prov = self._provider(cfg)
                result = prov.translate(text, source, target)
                if result:
                    with self._lock:
                        self._cache[key] = result
                        while len(self._cache) > self.max_cache:
                            self._cache.popitem(last=False)
                    return result
            except TranslationError as exc:
                errors.append(f"{provider_name}: {exc}")
            except Exception as exc:
                errors.append(f"{provider_name}: {exc}")
        raise TranslationError("；".join(errors) or "翻译失败")

    def _offline(self, pair: str):
        if pair not in self._offline_translators:
            from .offline import ArgosOfflineTranslator

            self._offline_translators[pair] = ArgosOfflineTranslator(pair)
        return self._offline_translators[pair]

    def _touch(self, key: tuple) -> None:
        with self._lock:
            self._cache.move_to_end(key)

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._providers.clear()
            self._offline_translators.clear()

    def test(self, cfg: Config, sample: str = "Hello world, this is a subtitle test.") -> str:
        return self.translate(sample, "en", cfg.target_lang, cfg)
