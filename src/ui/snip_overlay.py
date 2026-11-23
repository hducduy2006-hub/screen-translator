"""Lớp phủ chọn vùng màn hình (Snip Overlay) hỗ trợ đa màn hình và tự động đóng băng khung hình."""

from __future__ import annotations

from typing import Optional

import cv2
import mss
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget


class SnipOverlay(QWidget):
    """
    Lớp phủ toàn màn hình cho phép kéo chuột chọn bất kỳ vùng chữ nào để dịch ngay lập tức.
    Trả về: (logical_rect_global, cropped_rgb_array, scale_x, scale_y).
    """

    region_selected = Signal(QRect, object, float, float)
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._bg_pixmap: Optional[QPixmap] = None
        self._bg_rgb: Optional[np.ndarray] = None
        self._virtual_rect = QRect()
        self._origin: Optional[QPoint] = None
        self._current: Optional[QPoint] = None
        self._dragging = False

    def start_snip(self) -> None:
        """Đóng băng màn hình hiện tại và mở lớp phủ chọn vùng."""
        # Chụp trực tiếp bằng mss để giữ nguyên cả mảng RGB gốc độ phân giải vật lý
        with mss.mss() as sct:
            virt = sct.monitors[0]
            raw = sct.grab(virt)
            bgra = np.asarray(raw, dtype=np.uint8)
            rgb = np.ascontiguousarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB))

        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        virtual_rect = QRect()
        for sc in QGuiApplication.screens():
            virtual_rect = virtual_rect.united(sc.geometry())

        self._bg_rgb = rgb
        self._bg_pixmap = QPixmap.fromImage(qimg)
        self._virtual_rect = virtual_rect
        self._origin = None
        self._current = None
        self._dragging = False

        self.setGeometry(virtual_rect)
        self.show()
        self.raise_()
        self.activateWindow()

    def _selection_rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Vẽ ảnh nền màn hình đã đóng băng
        if self._bg_pixmap is not None:
            p.drawPixmap(self.rect(), self._bg_pixmap)

        # Phủ lớp tối nhẹ toàn màn hình, chừa sáng phần đang chọn
        sel = self._selection_rect()
        overlay_path = QPainterPath()
        overlay_path.addRect(self.rect())
        if not sel.isNull() and sel.width() > 2 and sel.height() > 2:
            hole = QPainterPath()
            hole.addRect(sel)
            overlay_path = overlay_path.subtracted(hole)
        p.fillPath(overlay_path, QColor(8, 12, 24, 125))

        # Thanh hướng dẫn nổi phía trên cùng màn hình chính
        guide_text = "Kéo chuột chọn vùng chữ cần dịch  •  Nhấn Esc hoặc chuột phải để hủy"
        font = QFont("Segoe UI", 11, QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(guide_text) + 34
        th = 36
        gx = (self.width() - tw) // 2
        gy = 24
        guide_rect = QRect(gx, gy, tw, th)
        p.setPen(QPen(QColor(56, 189, 248, 180), 1.2))
        p.setBrush(QColor(15, 23, 42, 230))
        p.drawRoundedRect(guide_rect, 18, 18)
        p.setPen(QColor("#F8FAFC"))
        p.drawText(guide_rect, Qt.AlignmentFlag.AlignCenter, guide_text)

        # Vẽ khung vùng đang kéo chọn + nhãn kích thước
        if not sel.isNull() and sel.width() > 2 and sel.height() > 2:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor("#38BDF8"), 2))
            p.drawRect(sel)

            # 4 góc nhấn sáng
            p.setPen(QPen(QColor("#E0F2FE"), 3))
            c = min(14, sel.width() // 3, sel.height() // 3)
            l, t, r, b = sel.left(), sel.top(), sel.right(), sel.bottom()
            p.drawLine(l, t, l + c, t)
            p.drawLine(l, t, l, t + c)
            p.drawLine(r, t, r - c, t)
            p.drawLine(r, t, r, t + c)
            p.drawLine(l, b, l + c, b)
            p.drawLine(l, b, l, b - c)
            p.drawLine(r, b, r - c, b)
            p.drawLine(r, b, r, b - c)

            # Nhãn kích thước
            dim_text = f"{sel.width()} × {sel.height()} px"
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            dfm = p.fontMetrics()
            dw = dfm.horizontalAdvance(dim_text) + 18
            dh = 24
            dy = sel.top() - dh - 6 if sel.top() > dh + 10 else sel.bottom() + 6
            dx = max(6, min(sel.left(), self.width() - dw - 6))
            dim_rect = QRect(dx, dy, dw, dh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(15, 23, 42, 230))
            p.drawRoundedRect(dim_rect, 6, 6)
            p.setPen(QColor("#38BDF8"))
            p.drawText(dim_rect, Qt.AlignmentFlag.AlignCenter, dim_text)

        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._cancel()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._origin = pos
            self._current = pos
            self._dragging = True
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        self._current = event.position().toPoint()
        sel = self._selection_rect()
        self.hide()

        if sel.width() < 12 or sel.height() < 12 or self._bg_rgb is None:
            self.cancelled.emit()
            return

        # Cắt chính xác từ ảnh RGB vật lý đã chụp (không bị lệch DPI)
        img_h, img_w = self._bg_rgb.shape[:2]
        sx = img_w / max(1, self.width())
        sy = img_h / max(1, self.height())

        px1 = max(0, int(round(sel.left() * sx)))
        py1 = max(0, int(round(sel.top() * sy)))
        px2 = min(img_w, int(round(sel.right() * sx)))
        py2 = min(img_h, int(round(sel.bottom() * sy)))

        if px2 - px1 < 8 or py2 - py1 < 8:
            self.cancelled.emit()
            return

        cropped = np.ascontiguousarray(self._bg_rgb[py1:py2, px1:px2])
        global_rect = QRect(
            self._virtual_rect.left() + sel.left(),
            self._virtual_rect.top() + sel.top(),
            sel.width(),
            sel.height(),
        )
        eff_sx = cropped.shape[1] / max(1, global_rect.width())
        eff_sy = cropped.shape[0] / max(1, global_rect.height())
        self.region_selected.emit(global_rect, cropped, eff_sx, eff_sy)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _cancel(self) -> None:
        self._dragging = False
        self.hide()
        self.cancelled.emit()
