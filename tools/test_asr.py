"""Quick ASR sanity check:  python tools/test_asr.py tools/test_audio.wav"""

import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.asr import AsrEngine, configure_hf  # noqa: E402


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        data = wf.readframes(n)
        pcm = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:
        import soxr

        pcm = soxr.resample(pcm, sr, 16000, quality="LQ")
    return np.ascontiguousarray(pcm, dtype=np.float32)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python tools/test_asr.py <wav>")
        sys.exit(1)
    configure_hf("https://hf-mirror.com")
    engine = AsrEngine("base")
    t0 = time.time()
    engine.load(status_cb=print)
    print(f"model loaded in {time.time()-t0:.1f}s")
    audio = read_wav(sys.argv[1])
    t1 = time.time()
    text, lang, prob = engine.transcribe(audio, None)
    print(f"transcribed in {time.time()-t1:.1f}s | lang={lang} prob={prob:.2f}")
    print("TEXT:", text)


if __name__ == "__main__":
    main()
