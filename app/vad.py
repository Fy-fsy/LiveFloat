from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .i18n import tr

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 512          # 32 ms at 16 kHz
FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE


@dataclass
class SpeechSegment:
    audio: np.ndarray
    duration: float
    started_at: float = 0.0
    ended_at: float = 0.0


class SileroVad:
    """Silero VAD (v5) running through ONNX Runtime on CPU.

    The model is tiny (~2.2 MB) and adds almost no latency.  If it fails to
    load we degrade to :class:`EnergyVad` instead of crashing the pipeline.
    """

    def __init__(self, model_path: str | Path, threads: int = 1) -> None:
        self.model_path = Path(model_path)
        self._session = None
        self._threads = threads
        self.reset()
        self._load()

    def _load(self) -> None:
        try:
            import onnxruntime as ort  # type: ignore

            options = ort.SessionOptions()
            options.intra_op_num_threads = self._threads
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            self._session = None
            raise RuntimeError(f"Silero VAD 模型加载失败：{exc}") from exc

    @property
    def available(self) -> bool:
        return self._session is not None

    def reset(self) -> None:
        # Silero v5 hidden/cell state.
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)

    def _input_names(self):
        return [i.name for i in self._session.get_inputs()]

    def __call__(self, chunk: np.ndarray) -> float:
        if self._session is None:
            return 0.0
        x = np.ascontiguousarray(chunk, dtype=np.float32).reshape(1, -1)
        # Map our canonical names onto whatever the ONNX graph declares.
        names = self._input_names()
        state_key = "state" if "state" in names else (names[1] if len(names) > 1 else "state")
        sr_key = "sr" if "sr" in names else (names[2] if len(names) > 2 else "sr")
        feed = {"input": x, state_key: self._state, sr_key: self._sr}
        outputs = self._session.run(None, feed)
        self._state = outputs[1]
        prob = float(np.asarray(outputs[0]).reshape(-1)[0])
        return max(0.0, min(1.0, prob))


class EnergyVad:
    """Very cheap RMS-based fallback.  Less accurate than Silero but has no
    external dependency and never fails to import."""

    def __init__(self, threshold_db: float = -42.0) -> None:
        self.threshold_db = threshold_db
        self._noise = -70.0

    @property
    def available(self) -> bool:
        return True

    def reset(self) -> None:
        self._noise = -70.0

    def __call__(self, chunk: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(np.asarray(chunk, dtype=np.float32))) + 1e-12))
        db = 20.0 * math.log10(rms + 1e-9)
        # Track a slow noise floor while quiet.
        if db < self.threshold_db:
            self._noise = 0.98 * self._noise + 0.02 * db
        gate = self._noise + 8.0
        spread = 6.0
        p = 1.0 / (1.0 + math.exp(-(db - gate) / spread))
        return float(max(0.0, min(1.0, p)))


class Segmenter:
    """Turns a stream of 512-sample frames into speech segments.

    Uses a pre-roll buffer so the start of each utterance is preserved, a
    hangover so short pauses do not split one sentence, and a hard cap so a
    long monologue still gets transcribed progressively.
    """

    def __init__(
        self,
        threshold: float = 0.50,
        silence_ms: int = 650,
        max_segment_s: float = 8.0,
        min_speech_s: float = 0.35,
        pre_roll_ms: int = 300,
    ) -> None:
        self.threshold = threshold
        self.neg_threshold = max(0.10, threshold - 0.18)
        self.silence_frames = max(3, int(round(silence_ms / 1000.0 / FRAME_SECONDS)))
        self.max_frames = max(60, int(round(max_segment_s / FRAME_SECONDS)))
        self.min_speech_frames = max(2, int(round(min_speech_s / FRAME_SECONDS)))
        self.pre_roll = deque(maxlen=max(2, int(round(pre_roll_ms / 1000.0 / FRAME_SECONDS))))
        self.buffer: list[np.ndarray] = []
        self.in_speech = False
        self.speech_frames = 0
        self.quiet_frames = 0
        self._clock = 0.0

    def reset(self) -> None:
        self.pre_roll.clear()
        self.buffer.clear()
        self.in_speech = False
        self.speech_frames = 0
        self.quiet_frames = 0

    def push(self, chunk: np.ndarray, prob: float) -> list[SpeechSegment]:
        x = np.ascontiguousarray(chunk, dtype=np.float32)
        self._clock += FRAME_SECONDS
        emitted: list[SpeechSegment] = []

        if not self.in_speech:
            self.pre_roll.append(x)
            if prob >= self.threshold:
                self.speech_frames += 1
                if self.speech_frames >= 2:
                    self.in_speech = True
                    self.buffer = list(self.pre_roll)
                    self.quiet_frames = 0
                    self.speech_frames = len(self.buffer)
            else:
                self.speech_frames = 0
            return emitted

        # In speech.
        self.buffer.append(x)
        if prob >= self.neg_threshold:
            self.quiet_frames = 0
        else:
            self.quiet_frames += 1

        force = len(self.buffer) >= self.max_frames
        if self.quiet_frames >= self.silence_frames or force:
            seg = self._finalise(force)
            if seg is not None:
                emitted.append(seg)

        return emitted

    def _finalise(self, force: bool) -> SpeechSegment | None:
        if force:
            keep_tail = 3
        else:
            keep_tail = min(3, max(1, self.silence_frames // 4))
        trim = max(0, self.quiet_frames - keep_tail)
        end = len(self.buffer) - trim if trim > 0 else len(self.buffer)
        audio = self.buffer[:end]
        self.buffer = []
        self.in_speech = False
        self.speech_frames = 0
        self.quiet_frames = 0

        # Re-seed pre-roll with a little context for the next segment.
        if audio:
            self.pre_roll.extend(audio[-max(1, keep_tail):])

        if not audio or len(audio) < self.min_speech_frames:
            return None
        samples = np.concatenate(audio).astype(np.float32)
        duration = samples.size / SAMPLE_RATE
        if duration < 0.30:
            return None
        return SpeechSegment(audio=samples, duration=duration, started_at=0.0, ended_at=self._clock)

    def flush(self) -> SpeechSegment | None:
        if not self.in_speech or len(self.buffer) < self.min_speech_frames:
            self.reset()
            return None
        audio = np.concatenate(self.buffer).astype(np.float32)
        self.reset()
        if audio.size / SAMPLE_RATE < 0.30:
            return None
        return SpeechSegment(audio=audio, duration=audio.size / SAMPLE_RATE, started_at=0.0, ended_at=self._clock)


def build_vad(model_path: str | Path | None) -> tuple[SileroVad | EnergyVad, str]:
    """Create the best available VAD; returns (vad, description)."""
    if model_path and Path(model_path).exists():
        try:
            vad = SileroVad(model_path, threads=1)
            if vad.available:
                return vad, "Silero VAD"
        except Exception as exc:
            log.warning("Silero VAD unavailable, falling back to energy VAD: %s", exc)
    energy = EnergyVad()
    return energy, tr("能量检测（低精度）", "energy VAD (low accuracy)")
