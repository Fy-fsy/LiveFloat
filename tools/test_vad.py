"""VAD / segmenter sanity check:  python tools/test_vad.py tools/test_audio.wav"""

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.vad import FRAME_SAMPLES, Segmenter, build_vad  # noqa: E402
from app.paths import resource_path  # noqa: E402


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        pcm = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:
        import soxr

        pcm = soxr.resample(pcm, sr, 16000, quality="LQ")
    return np.ascontiguousarray(pcm, dtype=np.float32)


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python tools/test_vad.py <wav>")
        sys.exit(1)
    audio = read_wav(sys.argv[1])
    vad, desc = build_vad(resource_path("silero_vad.onnx"))
    print("VAD:", desc)
    seg = Segmenter()
    pending = audio
    segments = []
    i = 0
    while i + FRAME_SAMPLES <= pending.size:
        frame = pending[i:i + FRAME_SAMPLES]
        i += FRAME_SAMPLES
        prob = vad(frame)
        segments.extend(seg.push(frame, prob))
    tail = seg.flush()
    if tail is not None:
        segments.append(tail)
    print(f"input={audio.size/16000:.2f}s segments={len(segments)}")
    for s in segments:
        print(f"  {s.duration:.2f}s  samples={s.audio.size}")


if __name__ == "__main__":
    main()
