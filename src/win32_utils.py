"""Tiện ích Windows API: phím tắt toàn cục (RegisterHotKey), ẩn cửa sổ khỏi ảnh chụp màn hình và xuyên chuột."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from typing import Callable, Dict, Optional

from PySide6.QtCore import QAbstractNativeEventFilter

IS_WINDOWS = sys.platform == "win32"

# Windows constants
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# SetWindowDisplayAffinity constants
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

# Window extended styles for click-through
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

if IS_WINDOWS:
    _user32 = ctypes.windll.user32
else:
    _user32 = None


def set_exclude_from_capture(hwnd: int, exclude: bool = True) -> bool:
    """
    Ẩn cửa sổ khỏi ảnh chụp màn hình (mss/BitBlt) nhưng vẫn hiển thị bình thường
    với mắt người dùng (Windows 10 2004+ / Windows 11).
    Nhờ đó chế độ Dịch Trực Tiếp không bị chụp đè chính khung bản dịch!
    """
    if not IS_WINDOWS or _user32 is None or not hwnd:
        return False
    try:
        win_ver = sys.getwindowsversion()
        if win_ver.build < 19041:
            return False
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        res = _user32.SetWindowDisplayAffinity(wintypes.HWND(hwnd), wintypes.DWORD(affinity))
        return bool(res)
    except Exception:
        return False


def set_click_through(hwnd: int, enabled: bool) -> bool:
    """Bật/tắt chế độ xuyên chuột (click-through) cho cửa sổ overlay."""
    if not IS_WINDOWS or _user32 is None or not hwnd:
        return False
    try:
        # 64-bit safe GetWindowLongPtrW / SetWindowLongPtrW
        get_long = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
        set_long = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
        get_long.restype = ctypes.c_ssize_t
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        set_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

        style = get_long(hwnd, GWL_EXSTYLE)
        if enabled:
            style |= WS_EX_TRANSPARENT | WS_EX_LAYERED
        else:
            style &= ~WS_EX_TRANSPARENT
        set_long(hwnd, GWL_EXSTYLE, style)
        return True
    except Exception:
        return False


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class GlobalHotkeyManager(QAbstractNativeEventFilter):
    """
    Quản lý phím tắt toàn cục trên Windows bằng Win32 RegisterHotKey.
    Ưu điểm: không cần quyền Admin, không gây lag bàn phím, hoạt động cả khi đang ở ứng dụng/game khác.
    """

    def __init__(self) -> None:
        super().__init__()
        self._callbacks: Dict[int, Callable[[], None]] = {}
        self._next_id = 100

    def register(self, modifiers: int, vk_code: int, callback: Callable[[], None]) -> Optional[int]:
        if not IS_WINDOWS or _user32 is None:
            return None
        hotkey_id = self._next_id
        self._next_id += 1
        ok = _user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, vk_code)
        if not ok:
            return None
        self._callbacks[hotkey_id] = callback
        return hotkey_id

    def unregister_all(self) -> None:
        if not IS_WINDOWS or _user32 is None:
            return
        for hotkey_id in list(self._callbacks.keys()):
            try:
                _user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._callbacks.clear()

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if IS_WINDOWS and eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            try:
                msg = _MSG.from_address(int(message))
                if msg.message == WM_HOTKEY:
                    hotkey_id = int(msg.wParam)
                    cb = self._callbacks.get(hotkey_id)
                    if cb is not None:
                        cb()
                        return True, 0
            except Exception:
                pass
        return False, 0
