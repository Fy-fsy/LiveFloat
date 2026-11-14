"""Capture 6 seconds of system audio to a WAV:  python tools/test_capture.py out.wav
Play something in the browser first so the recording is not silent.
"""

import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.audio import AudioCapture, enumerate_loopback_devices, resolve_device  # noqa: E402
from app.audio import TARGET_RATE  # noqa: E402


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "capture.wav"
    devices = enumerate_loopback_devices()
    print("Devices:")
    for d in devices:
        print(f"  [{d.index}] {d.name} rate={d.rate} ch={d.channels} default={d.is_default}")
    device = resolve_device("", -1, devices)
    if device is None:
        print("no loopback device")
        sys.exit(1)
    print("Capturing from:", device.name)

    chunks: list[np.ndarray] = []
    levels: list[float] = []
    cap = AudioCapture(
        device_name=device.name,
        device_index=device.index,
        on_chunk=lambda c: chunks.append(c),
        on_level=lambda l: levels.append(l),
        on_error=lambda m: print("ERR", m),
    )
    cap.start()
    time.sleep(6.0)
    cap.stop()

    if not chunks:
        print("no audio captured")
        sys.exit(1)
    audio = np.concatenate(chunks)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(TARGET_RATE)
        wf.writeframes(pcm.tobytes())
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    print(f"saved {out}: {audio.size/TARGET_RATE:.2f}s peak={peak:.3f} levels={len(levels)}")


if __name__ == "__main__":
    main()
