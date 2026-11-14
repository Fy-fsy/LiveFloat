"""End-to-end loopback test: play the TTS WAV through the default speaker and
capture it back via WASAPI loopback, then transcribe the captured audio.
Run with:  python tools/test_e2e.py
"""

import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.audio import AudioCapture, enumerate_loopback_devices, resolve_device, TARGET_RATE  # noqa: E402
from app.asr import AsrEngine, configure_hf  # noqa: E402
from app.paths import resource_path  # noqa: E402

WAV = ROOT / "tools" / "test_audio.wav"


def main() -> int:
    configure_hf("https://hf-mirror.com")

    devices = enumerate_loopback_devices()
    if not devices:
        print("no loopback device")
        return 1
    device = resolve_device("", -1, devices)
    print("loopback:", device.name)

    # Start playback asynchronously.
    import winsound

    chunks: list[np.ndarray] = []
    cap = AudioCapture(
        device_name=device.name,
        device_index=device.index,
        on_chunk=chunks.append,
        on_error=lambda m: print("CAPERR", m),
    )
    cap.start()
    time.sleep(0.4)
    winsound.PlaySound(str(WAV), winsound.SND_FILENAME | winsound.SND_ASYNC)
    time.sleep(9.5)
    cap.stop()

    if not chunks:
        print("nothing captured")
        return 1
    audio = np.concatenate(chunks)
    peak = float(np.max(np.abs(audio)))
    print(f"captured {audio.size/TARGET_RATE:.2f}s peak={peak:.3f}")
    if peak < 0.01:
        print("WARNING: captured audio is near-silent (no active playback endpoint?)")
        return 1

    engine = AsrEngine("base")
    engine.load(status_cb=print)
    text, lang, prob = engine.transcribe(audio, None)
    print(f"lang={lang} prob={prob:.2f}")
    print("ASR:", text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
