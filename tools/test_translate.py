"""Translation sanity check against the configured provider."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402
from app.translate import TranslationManager  # noqa: E402


def main() -> None:
    cfg = Config()
    cfg.target_lang = "zh-CN"
    manager = TranslationManager()
    samples = [
        "Hello world, this is a subtitle test.",
        "The quick brown fox jumps over the lazy dog.",
    ]
    for s in samples:
        try:
            out = manager.translate(s, "en", "zh-CN", cfg)
            print(f"EN : {s}\nZH : {out}\n")
        except Exception as exc:
            print(f"FAILED: {s} -> {exc}")


if __name__ == "__main__":
    main()
