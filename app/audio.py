from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

TARGET_RATE = 16_000
FRAME_SECONDS = 0.02


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    rate: int
    channels: int
    is_default: bool = False
    is_loopback: bool = True

    @property
    def display_name(self) -> str:
        suffix = "（默认）" if self.is_default else ""
        return f"{self.name}{suffix}"


def _import_pyaudio():
    try:
        import pyaudiowpatch as pyaudio  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on host
        raise RuntimeError(
            "未安装 pyaudiowpatch，无法捕获系统声音。请运行 start.bat 重新安装依赖。"
        ) from exc
    return pyaudio


def enumerate_loopback_devices() -> list[AudioDevice]:
    """List WASAPI loopback endpoints (the speakers you can hear)."""
    pyaudio = _import_pyaudio()
    p = pyaudio.PyAudio()
    devices: list[AudioDevice] = []
    try:
        try:
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        except Exception:
            wasapi = None
        default_name = ""
        if wasapi is not None:
            default_index = int(wasapi.get("defaultOutputDevice", -1))
            if default_index >= 0:
                try:
                    default_name = str(p.get_device_info_by_index(default_index).get("name", ""))
                except Exception:
                    default_name = ""
        for info in p.get_loopback_device_info_generator():
            name = str(info.get("name", "未知音频设备"))
            rate = int(info.get("defaultSampleRate", 48000) or 48000)
            channels = int(info.get("maxInputChannels", 2) or 2)
            is_default = bool(default_name) and (
                default_name in name or name.replace(" [Loopback]", "") == default_name
            )
            devices.append(
                AudioDevice(
                    index=int(info.get("index", -1)),
                    name=name,
                    rate=rate,
                    channels=max(1, min(2, channels)),
                    is_default=is_default,
                )
            )
    finally:
        p.terminate()
    devices.sort(key=lambda d: (not d.is_default, d.name.lower()))
    return devices


def default_device(devices: list[AudioDevice] | None = None) -> AudioDevice | None:
    devices = devices if devices is not None else enumerate_loopback_devices()
    if not devices:
        return None
    for dev in devices:
        if dev.is_default:
            return dev
    return devices[0]


def resolve_device(
    name: str,
    index: int = -1,
    devices: list[AudioDevice] | None = None,
) -> AudioDevice | None:
    devices = devices if devices is not None else enumerate_loopback_devices()
    if not devices:
        return None
    if name:
        for dev in devices:
            if dev.name == name:
                return dev
        # Device names occasionally change when the endpoint is re-plugged.
        for dev in devices:
            if name and (name in dev.name or dev.name in name):
                return dev
    if 0 <= index < len(devices) and devices[index].index == index:
        return devices[index]
    return default_device(devices)


class AudioCapture:
    """WASAPI loopback capture running on a dedicated thread.

    The callback receives mono float32 audio already resampled to 16 kHz,
    plus a smoothed level between 0 and 1 for the UI meter.
    """

    def __init__(
        self,
        device_name: str = "",
        device_index: int = -1,
        on_chunk: Callable[[np.ndarray], None] | None = None,
        on_level: Callable[[float], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.device_name = device_name
        self.device_index = device_index
        self.on_chunk = on_chunk or (lambda _chunk: None)
        self.on_level = on_level or (lambda _level: None)
        self.on_error = on_error or (lambda _message: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._level = 0.0
        self._device: AudioDevice | None = None

    @property
    def device(self) -> AudioDevice | None:
        return self._device

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="LiveFloat-Audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=0.3)
        self._thread = None

    # ------------------------------------------------------------------
    def _run(self) -> None:
        pyaudio = None
        stream = None
        p = None
        try:
            pyaudio = _import_pyaudio()
            p = pyaudio.PyAudio()
            devices = enumerate_loopback_devices()
            device = resolve_device(self.device_name, self.device_index, devices)
            if device is None:
                self.on_error(
                    "没有找到可用的扬声器环回设备。请确认电脑已连接扬声器/耳机，"
                    "并在“声音设置”中有一个启用的播放设备。"
                )
                return
            self._device = device
            rate = device.rate or 48000
            channels = max(1, min(2, device.channels))
            frames = max(256, int(rate * FRAME_SECONDS))
            stream = p.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=rate,
                input=True,
                frames_per_buffer=frames,
                input_device_index=device.index,
            )
            log.info("Audio capture started: %s (%s Hz, %s ch)", device.name, rate, channels)
            self.on_level(0.0)
            last_emit = 0.0
            while not self._stop.is_set():
                try:
                    data = stream.read(frames, exception_on_overflow=False)
                except Exception as exc:
                    if self._stop.is_set():
                        break
                    self.on_error(f"读取系统音频失败：{exc}")
                    time.sleep(0.4)
                    continue
                if not data:
                    continue
                raw = np.frombuffer(data, dtype=np.float32)
                if raw.size == 0:
                    continue
                usable = raw.size - (raw.size % channels)
                if usable <= 0:
                    continue
                samples = raw[:usable].reshape(-1, channels).mean(axis=1)
                samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
                rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64) + 1e-12))
                level = self._smooth_level(rms)
                self._level = level
                now = time.monotonic()
                if now - last_emit >= 0.05:
                    last_emit = now
                    self.on_level(level)
                mono16 = _resample(samples, rate, TARGET_RATE)
                if mono16.size:
                    try:
                        self.on_chunk(mono16)
                    except Exception:
                        log.exception("Audio chunk callback failed")
        except Exception as exc:
            log.exception("Audio capture failed")
            self.on_error(f"启动系统音频捕获失败：{exc}")
        finally:
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            try:
                if p is not None:
                    p.terminate()
            except Exception:
                pass
            self.on_level(0.0)
            log.info("Audio capture stopped")

    def _smooth_level(self, rms: float) -> float:
        db = 20.0 * math.log10(max(rms, 1e-7))
        # -60 dB -> 0, -4 dB -> 1
        value = max(0.0, min(1.0, (db + 60.0) / 56.0))
        # Fast attack, slow release.
        if value > self._level:
            self._level = self._level * 0.35 + value * 0.65
        else:
            self._level = self._level * 0.88 + value * 0.12
        return self._level


def _resample(samples: np.ndarray, in_rate: int, out_rate: int) -> np.ndarray:
    if in_rate == out_rate:
        return np.ascontiguousarray(samples, dtype=np.float32)
    try:
        import soxr  # type: ignore

        out = soxr.resample(samples, in_rate, out_rate, quality="LQ")
        return np.ascontiguousarray(out, dtype=np.float32)
    except Exception:
        # Linear interpolation fallback (adequate for speech).
        duration = samples.size / float(in_rate)
        count = max(1, int(round(duration * out_rate)))
        x_old = np.linspace(0.0, duration, num=samples.size, endpoint=False, dtype=np.float64)
        x_new = np.linspace(0.0, duration, num=count, endpoint=False, dtype=np.float64)
        out = np.interp(x_new, x_old, samples).astype(np.float32)
        return np.ascontiguousarray(out)
