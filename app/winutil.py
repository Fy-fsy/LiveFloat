from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

SW_SHOWNOACTIVATE = 4


def _get_long(hwnd: int, index: int) -> int:
    return int(user32.GetWindowLongPtrW(wintypes.HWND(hwnd), index))


def _set_long(hwnd: int, index: int, value: int) -> int:
    return int(user32.SetWindowLongPtrW(wintypes.HWND(hwnd), index, value))


def get_ex_style(hwnd: int) -> int:
    return _get_long(hwnd, GWL_EXSTYLE)


def set_ex_style(hwnd: int, add: int, remove: int = 0) -> None:
    style = _get_long(hwnd, GWL_EXSTYLE)
    style = (style | add) & ~remove
    _set_long(hwnd, GWL_EXSTYLE, style)


def set_topmost(hwnd: int, topmost: bool) -> None:
    flag = HWND_TOPMOST if topmost else HWND_NOTOPMOST
    user32.SetWindowPos(
        wintypes.HWND(hwnd),
        wintypes.HWND(flag),
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
    )


def show_no_activate(hwnd: int) -> None:
    user32.ShowWindow(wintypes.HWND(hwnd), SW_SHOWNOACTIVATE)


def set_dark_titlebar(hwnd: int) -> None:
    """Enable the dark title bar on Windows 10/11."""
    for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE / older fallback
        value = ctypes.c_int(1)
        if dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), attr, ctypes.byref(value), ctypes.sizeof(value)
        ) == 0:
            return
