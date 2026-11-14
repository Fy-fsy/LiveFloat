from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

VK_F = 0x46
VK_L = 0x4C
VK_S = 0x53
VK_SPACE = 0x20


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "HotkeyManager") -> None:
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        try:
            if bytes(eventType) != b"windows_generic_MSG":
                return False, 0
            msg = _MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.manager._dispatch(int(msg.wParam))
                return True, 0
        except Exception:
            log.exception("native hotkey filter failed")
        return False, 0


class HotkeyManager(QObject):
    toggle_overlay = Signal()
    toggle_lock = Signal()
    open_settings = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ids: dict[int, str] = {}
        self._filter = _NativeFilter(self)

    def register_defaults(self) -> None:
        self.register(0x1001, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_F, "toggle_overlay")
        self.register(0x1002, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_L, "toggle_lock")
        self.register(0x1003, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_S, "open_settings")

    def register(self, hotkey_id: int, modifiers: int, vk: int, action: str) -> bool:
        user32 = ctypes.windll.user32
        ok = user32.RegisterHotKey(None, hotkey_id, modifiers, vk)
        if ok:
            self._ids[hotkey_id] = action
            log.info("Registered hotkey %s -> %s", hotkey_id, action)
        else:
            log.warning("Could not register hotkey %s (%s)", hotkey_id, action)
        return bool(ok)

    def unregister_all(self) -> None:
        user32 = ctypes.windll.user32
        for hotkey_id in self._ids:
            user32.UnregisterHotKey(None, hotkey_id)
        self._ids.clear()

    def _dispatch(self, hotkey_id: int) -> None:
        action = self._ids.get(hotkey_id)
        if action == "toggle_overlay":
            self.toggle_overlay.emit()
        elif action == "toggle_lock":
            self.toggle_lock.emit()
        elif action == "open_settings":
            self.open_settings.emit()

    @property
    def native_filter(self) -> _NativeFilter:
        return self._filter
