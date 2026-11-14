from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from PySide6.QtCore import QObject, Signal

from .asr import AsrEngine
from .audio import AudioCapture
from .config import Config
from .i18n import tr
from .paths import resource_path
from .translate import TranslationManager
from .vad import Segmenter, SpeechSegment, build_vad

log = logging.getLogger(__name__)


@dataclass
class Segment:
    id: int
    text: str
    translation: str = ""
    source_lang: str = ""
    target_lang: str = ""
    state: str = "translating"  # translating | done | error
    error: str = ""
    duration: float = 0.0
    created_at: float = field(default_factory=time.time)
    latency: float = 0.0


class Pipeline(QObject):
    state_changed = Signal(str)        # idle | loading | listening | error
    status_message = Signal(str)
    level_changed = Signal(float)
    segment_added = Signal(object)     # Segment
    segment_updated = Signal(object)   # Segment
    error = Signal(str)
    stats_changed = Signal(dict)
    download_progress = Signal(int)  # 0..100

    def __init__(self, get_config: Callable[[], Config]) -> None:
        super().__init__()
        self.get_config = get_config
        self._running = False
        self._run_stop: threading.Event | None = None
        self._threads: list[threading.Thread] = []
        self._engine: AsrEngine | None = None
        self._engine_key: tuple | None = None
        self._capture: AudioCapture | None = None
        self._last_text = ""
        self._last_text_at = 0.0
        self._seg_counter = 0
        self._translation_manager = TranslationManager()
        self._stats = {"segments": 0, "avg_latency": 0.0, "dropped": 0}

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stats = {"segments": 0, "avg_latency": 0.0, "dropped": 0}
        cfg = self.get_config().copy()

        stop = threading.Event()
        audio_q: queue.Queue = queue.Queue(maxsize=1200)
        asr_q: queue.Queue = queue.Queue(maxsize=24)
        tl_q: queue.Queue = queue.Queue(maxsize=128)
        self._run_stop = stop

        t_asr = threading.Thread(target=self._asr_loop, args=(asr_q, tl_q), name="LiveFloat-ASR", daemon=True)
        t_tl = threading.Thread(target=self._translate_loop, args=(tl_q,), name="LiveFloat-Translate", daemon=True)
        t_main = threading.Thread(
            target=self._coordinator,
            name="LiveFloat-Coordinator",
            args=(cfg, stop, audio_q, asr_q),
            daemon=True,
        )
        self._threads = [t_asr, t_tl, t_main]
        for t in self._threads:
            t.start()

    def stop(self) -> None:
        if not self._running and not self._threads:
            return
        was_running = self._running
        stop = self._run_stop
        if stop is not None:
            stop.set()
        self.status_message.emit(tr("正在停止…", "Stopping…"))
        capture = self._capture
        if capture is not None:
            try:
                capture.stop()
            except Exception:
                pass
        self._capture = None
        # Do not block the UI: the worker threads are daemons and stop on
        # their own (the download thread honours its stop event once it is
        # free to check it).
        self._threads = []
        self._running = False
        if was_running:
            self.state_changed.emit("idle")
            self.status_message.emit(tr("已停止", "Stopped"))

    def shutdown(self) -> None:
        self.stop()
        self._translation_manager.clear_cache()

    # ------------------------------------------------------------------
    def _coordinator(self, cfg: Config, stop: threading.Event, audio_q: queue.Queue, asr_q: queue.Queue) -> None:
        capture: AudioCapture | None = None
        try:
            self.state_changed.emit("loading")
            engine = self._ensure_engine(cfg)
            if engine is None:
                return  # error already emitted
            if stop.is_set():
                return

            vad_path = resource_path("silero_vad.onnx")
            vad, vad_desc = build_vad(vad_path)
            segmenter = Segmenter(
                threshold=cfg.vad_threshold,
                silence_ms=cfg.silence_ms,
                max_segment_s=cfg.max_segment_s,
            )

            def push_audio(chunk: np.ndarray) -> None:
                try:
                    audio_q.put_nowait(np.asarray(chunk, dtype=np.float32))
                except queue.Full:
                    try:
                        audio_q.get_nowait()
                        audio_q.put_nowait(np.asarray(chunk, dtype=np.float32))
                    except queue.Full:
                        pass

            def enqueue_segment(seg: SpeechSegment) -> None:
                self._seg_counter += 1
                item = (self._seg_counter, seg.audio, seg.duration)
                try:
                    asr_q.put_nowait(item)
                except queue.Full:
                    try:
                        asr_q.get_nowait()
                        asr_q.put_nowait(item)
                        self._stats["dropped"] += 1
                    except queue.Full:
                        self._stats["dropped"] += 1

            self.status_message.emit(tr("正在监听系统声音（{vad}）…", "Listening to system audio ({vad})…").format(vad=vad_desc))
            capture = AudioCapture(
                device_name=cfg.audio_device_name,
                device_index=cfg.audio_device_index,
                on_chunk=push_audio,
                on_level=self.level_changed.emit,
                on_error=self.error.emit,
            )
            if self._run_stop is stop:
                self._capture = capture
            capture.start()
            if stop.is_set():
                capture.stop()
                if self._capture is capture:
                    self._capture = None
                return
            self.state_changed.emit("listening")
            self.stats_changed.emit(dict(self._stats))

            pending = np.empty((0,), dtype=np.float32)
            while not stop.is_set():
                try:
                    chunk = audio_q.get(timeout=0.15)
                except queue.Empty:
                    continue
                if chunk is None:
                    break
                pending = np.concatenate([pending, np.asarray(chunk, dtype=np.float32)])
                while pending.size >= 512:
                    frame = pending[:512]
                    pending = pending[512:]
                    prob = vad(frame)
                    for seg in segmenter.push(frame, prob):
                        enqueue_segment(seg)

            # Flush the tail of the current utterance on stop.
            tail = segmenter.flush()
            if tail is not None:
                enqueue_segment(tail)
        except Exception as exc:
            log.exception("Pipeline coordinator failed")
            self.error.emit(tr("管线启动失败：", "Pipeline start failed: ") + str(exc))
            self.state_changed.emit("error")
            return
        finally:
            if capture is not None:
                try:
                    capture.stop()
                except Exception:
                    pass
                if self._capture is capture:
                    self._capture = None
            try:
                asr_q.put(None, timeout=1.0)
            except queue.Full:
                pass
            self.level_changed.emit(0.0)

    def _ensure_engine(self, cfg: Config) -> AsrEngine | None:
        key = (cfg.asr_model, cfg.compute_type)
        if self._engine is not None and self._engine_key == key and self._engine.model is not None:
            return self._engine
        engine = AsrEngine(cfg.asr_model, cfg.compute_type)
        try:
            engine.load(status_cb=self.status_message.emit, progress_cb=self.download_progress.emit)
        except Exception as exc:
            self.error.emit(str(exc))
            self.state_changed.emit("error")
            self._running = False
            return None
        self._engine = engine
        self._engine_key = key
        return engine

    # ------------------------------------------------------------------
    def _asr_loop(self, asr_q: queue.Queue, tl_q: queue.Queue) -> None:
        engine = None
        while True:
            try:
                item = asr_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            seg_id, audio, duration = item
            if engine is None:
                engine = self._engine
            if engine is None:
                self.error.emit("识别引擎未就绪")
                continue
            cfg = self.get_config()
            lang_hint = None if cfg.source_lang == "auto" else cfg.source_lang
            try:
                text, lang, prob = engine.transcribe(audio, lang_hint)
            except Exception as exc:
                log.exception("ASR failed")
                self.error.emit(f"识别失败：{exc}")
                continue
            if engine.is_hallucination(text, prob, duration):
                continue
            if not text:
                continue
            # De-duplicate rapid repeats (Whisper loop).
            now = time.time()
            if text == self._last_text and now - self._last_text_at < 3.0:
                continue
            self._last_text = text
            self._last_text_at = now

            segment = Segment(
                id=seg_id,
                text=text,
                source_lang=lang,
                target_lang=cfg.target_lang,
                duration=duration,
            )
            needs_translation = not (lang and lang.split("-")[0] == cfg.target_lang.split("-")[0])
            if not needs_translation:
                segment.translation = text
                segment.state = "done"
                segment.latency = time.time() - segment.created_at
            self.segment_added.emit(segment)
            self._stats["segments"] += 1
            if needs_translation:
                try:
                    tl_q.put_nowait(segment)
                except queue.Full:
                    try:
                        tl_q.get_nowait()
                        tl_q.put_nowait(segment)
                    except queue.Full:
                        pass
        # ASR queue is drained; now let the translator finish and exit.
        try:
            tl_q.put(None, timeout=1.0)
        except queue.Full:
            pass

    def _translate_loop(self, tl_q: queue.Queue) -> None:
        while True:
            try:
                segment = tl_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if segment is None:
                break
            cfg = self.get_config()
            try:
                result = self._translation_manager.translate(
                    segment.text, segment.source_lang, segment.target_lang, cfg
                )
                segment.translation = result
                segment.state = "done"
            except Exception as exc:
                segment.state = "error"
                segment.error = str(exc)
            segment.latency = time.time() - segment.created_at
            self.segment_updated.emit(segment)
            # Update rolling stats.
            total = self._stats.get("avg_latency", 0.0)
            n = self._stats.get("segments", 1)
            self._stats["avg_latency"] = (total * (n - 1) + segment.latency) / max(1, n)
            self.stats_changed.emit(dict(self._stats))

    # ------------------------------------------------------------------
    def preload_model(self, status_cb: Callable[[str], None] | None = None) -> None:
        """Download/load the selected model without starting capture."""

        def _work() -> None:
            cfg = self.get_config()
            engine = AsrEngine(cfg.asr_model, cfg.compute_type)
            try:
                engine.load(
                    status_cb=status_cb or self.status_message.emit,
                    progress_cb=self.download_progress.emit,
                )
                self._engine = engine
                self._engine_key = (cfg.asr_model, cfg.compute_type)
                if status_cb:
                    status_cb("模型已就绪，可以开始翻译")
            except Exception as exc:
                self.error.emit(str(exc))

        threading.Thread(target=_work, name="LiveFloat-Preload", daemon=True).start()
