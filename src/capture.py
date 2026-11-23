"""Chụp màn hình tốc độ cao (mss), ánh xạ tọa độ DPI chuẩn xác và phát hiện thay đổi khung hình."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import mss
import numpy as np
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class CaptureResult:
    """Ảnh RGB chụp được cùng thông tin vùng tọa độ logic (Qt) và tỷ lệ DPI."""

    image_rgb: np.ndarray
    logical_rect: QRect
    scale_x: float
    scale_y: float


def logical_rect_to_physical(rect: QRect) -> Tuple[int, int, int, int]:
    """
    Chuyển đổi QRect theo tọa độ logic của Qt sang tọa độ pixel vật lý thực tế của Windows
    (hỗ trợ màn hình 125%/150%/200% DPI và hệ thống đa màn hình).
    """
    center = rect.center()
    screen = QGuiApplication.screenAt(center) or QGuiApplication.primaryScreen()
    if screen is None:
        return rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height())

    dpr = float(screen.devicePixelRatio())
    s_geo = screen.geometry()  # logic coordinates
    # Trên Windows + Qt6, gốc màn hình vật lý khớp với s_geo khi xét trong hệ tọa độ screen,
    # tuy nhiên với multi-monitor mixed DPI, cần tính offset từ gốc màn hình đó.
    native_x = int(round(s_geo.x() * dpr)) if s_geo.x() == 0 else s_geo.x()
    native_y = int(round(s_geo.y() * dpr)) if s_geo.y() == 0 else s_geo.y()

    # Dùng Win32 MonitorInfo hoặc tính theo màn hình chính (0,0) nếu ở primary screen
    if s_geo.x() == 0 and s_geo.y() == 0:
        px = int(round(rect.x() * dpr))
        py = int(round(rect.y() * dpr))
    else:
        # Tính tương đối theo gốc của màn hình chứa tâm rect
        rel_x = rect.x() - s_geo.x()
        rel_y = rect.y() - s_geo.y()
        # Lấy tọa độ vật lý thực tế của màn hình thông qua Qt QScreen.handle / hoặc mss
        # Trên Windows Qt6 HighDpiScaleFactorRoundingPolicy, s_geo.topLeft() đã ở hệ tọa độ virtual
        # Dùng tỷ lệ an toàn:
        px = int(round(s_geo.x() * dpr + rel_x * dpr))
        py = int(round(s_geo.y() * dpr + rel_y * dpr))
        # Clamp vào phạm vi thực của mss virtual desktop nếu cần
        with mss.mss() as sct:
            virt = sct.monitors[0]
            max_x = virt["left"] + virt["width"]
            max_y = virt["top"] + virt["height"]
            if px >= max_x or px < virt["left"]:
                px = int(round(native_x + rel_x * dpr))
            if py >= max_y or py < virt["top"]:
                py = int(round(native_y + rel_y * dpr))

    pw = max(1, int(round(rect.width() * dpr)))
    ph = max(1, int(round(rect.height() * dpr)))
    return px, py, pw, ph


def capture_logical_rect(rect: QRect) -> Optional[CaptureResult]:
    """Chụp trực tiếp vùng QRect (tọa độ logic Qt) bằng mss -> mảng RGB uint8."""
    if rect.width() < 6 or rect.height() < 6:
        return None

    px, py, pw, ph = logical_rect_to_physical(rect)
    with mss.mss() as sct:
        virt = sct.monitors[0]
        left = max(virt["left"], px)
        top = max(virt["top"], py)
        right = min(virt["left"] + virt["width"], px + pw)
        bottom = min(virt["top"] + virt["height"], py + ph)
        w = right - left
        h = bottom - top
        if w < 6 or h < 6:
            return None

        raw = sct.grab({"left": left, "top": top, "width": w, "height": h})
        # mss trả về BGRA -> chuyển sang RGB
        bgra = np.asarray(raw, dtype=np.uint8)
        rgb = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB)

    scale_x = rgb.shape[1] / max(1, rect.width())
    scale_y = rgb.shape[0] / max(1, rect.height())
    return CaptureResult(
        image_rgb=rgb,
        logical_rect=QRect(rect),
        scale_x=scale_x,
        scale_y=scale_y,
    )


def capture_virtual_desktop_qimage():
    """
    Chụp toàn bộ màn hình ảo (tất cả màn hình) bằng Qt QScreen.grabWindow
    dùng làm nền đóng băng cho lớp phủ Snip (giúp kéo chọn không bị trôi chữ).
    """
    screens = QGuiApplication.screens()
    if not screens:
        return None, QRect()

    virtual_rect = QRect()
    for sc in screens:
        virtual_rect = virtual_rect.united(sc.geometry())

    # Dùng mss chụp full virtual monitor rồi chuyển sang QImage để đảm bảo khớp pixel
    from PySide6.QtGui import QImage

    with mss.mss() as sct:
        virt = sct.monitors[0]
        raw = sct.grab(virt)
        bgra = np.asarray(raw, dtype=np.uint8)
        rgb = np.ascontiguousarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB))
        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

    return qimg, virtual_rect


class FrameDiffer:
    """
    Phát hiện thay đổi nội dung hình ảnh trong chế độ Dịch Trực Tiếp (Live Mode).
    So sánh ảnh xám thu nhỏ để bỏ qua nhiễu nhỏ / nhấp nháy con trỏ và tiết kiệm CPU khi màn hình đứng yên.
    """

    def __init__(self, threshold: float = 2.6, pixel_ratio_threshold: float = 0.008) -> None:
        self._last_gray: Optional[np.ndarray] = None
        self._last_shape: Optional[Tuple[int, int]] = None
        self._threshold = threshold
        self._pixel_ratio_threshold = pixel_ratio_threshold

    def reset(self) -> None:
        self._last_gray = None
        self._last_shape = None

    def has_changed(self, image_rgb: np.ndarray) -> bool:
        h, w = image_rgb.shape[:2]
        # Thu nhỏ về chiều rộng tối đa 320px để tính diff siêu nhanh (<1ms)
        target_w = min(w, 320)
        target_h = max(8, int(round(h * (target_w / max(1, w)))))
        small = cv2.resize(image_rgb, (target_w, target_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)

        if self._last_gray is None or self._last_shape != gray.shape:
            self._last_gray = gray
            self._last_shape = gray.shape
            return True

        diff = cv2.absdiff(gray, self._last_gray)
        mean_diff = float(diff.mean())
        changed_ratio = float((diff > 18).mean())

        if mean_diff >= self._threshold or changed_ratio >= self._pixel_ratio_threshold:
            self._last_gray = gray
            self._last_shape = gray.shape
            return True
        return False
