from __future__ import annotations

# Current UI language.  Default is Simplified Chinese; the settings window has
# a switch button that flips it to English.
_LANG = "zh-CN"

SUPPORTED = ("zh-CN", "en")


def set_language(lang: str) -> str:
    global _LANG
    _LANG = lang if lang in SUPPORTED else "zh-CN"
    return _LANG


def language() -> str:
    return _LANG


def tr(zh: str, en: str) -> str:
    """Return the string for the current language (Chinese is the default)."""
    return en if _LANG == "en" else zh
