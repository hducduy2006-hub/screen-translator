"""
Chế độ Dịch Trực Tiếp Liên Tục (Live Auto-Translate):
- LiveCaptureFrame: Khung quét trong suốt có thể kéo & đổi kích thước đặt lên phụ đề phim,
  hội thoại game, khung chat hoặc tài liệu. Sử dụng Windows WDA_EXCLUDEFROMCAPTURE nên không
  bao giờ tự chụp đè lên chính mình — hỗ trợ cả chế độ Phụ đề nổi và Đè chữ trực tiếp!
- LiveSubtitleWindow: Khung phụ đề bản dịch trực tiếp tùy biến cỡ chữ, độ mờ, và chế độ xuyên chuột.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from src.layout import TextBlock
from src.win32_utils import set_click_through, set_exclude_from_capture


class LiveCaptureFrame(QWidget):
    """
    Khung quét trực tiếp trên màn hình:
    - Phần ruột hoàn toàn trong suốt (alpha=0 -> click xuyên qua được ứng dụng bên dưới!).
    - Viền phát sáng xanh ngọc có thể kéo giãn 4 cạnh & 4 góc.
    - Thanh tiêu đề nhỏ gọn phía trên để di chuyển, Tạm dừng, hoặc bật chế độ Đè chữ trực tiếp.
    """

    region_changed = Signal(QRect)
    pause_toggled = Signal(bool)
    direct_mode_toggled = Signal(bool)
    closed = Signal()

    HEADER_H = 30
    BORDER_MARGIN = 10

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(180, 96)

        self._paused = False
        self._direct_overlay = False
        self._blocks: List[TextBlock] = []
        self._drag_mode: Optional[str] = None
        self._drag_start_global = QPoint()
        self._drag_start_geo = QRect()

        # Thanh điều khiển nhỏ gắn trên đỉnh khung quét
        self._header = QWidget(self)
        self._header.setObjectName("LiveHeader")
        self._header.setFixedHeight(self.HEADER_H)
        self._header.setStyleSheet(
            """
            QWidget#LiveHeader {
                background-color: rgba(15, 23, 42, 235);
                border: 1px solid rgba(16, 185, 129, 0.75);
                border-top-left-radius: 9px;
                border-top-right-radius: 9px;
                border-bottom: none;
            }
            QLabel {
                color: #6EE7B7;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton {
                background-color: rgba(30, 41, 59, 210);
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 5px;
                padding: 2px 7px;
                color: #F1F5F9;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(51, 65, 85, 240);
                border-color: #38BDF8;
            }
            QPushButton#ActiveModeBtn {
                background-color: rgba(37, 99, 235, 0.85);
                border-color: #60A5FA;
                color: #FFFFFF;
            }
            QPushButton#CloseMini:hover {
                background-color: rgba(244, 63, 94, 0.85);
                border-color: #FB7185;
            }
            """
        )
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(8, 2, 6, 2)
        hl.setSpacing(5)

        self._lbl_state = QLabel("● Đang dịch trực tiếp")
        self._btn_pause = QPushButton("Tạm dừng")
        self._btn_pause.clicked.connect(self._on_toggle_pause)

        self._btn_direct = QPushButton("Đè chữ")
        self._btn_direct.setToolTip(
            "Bật để hiển thị bản dịch đè trực tiếp ngay trong khung quét (nhờ ẩn khỏi ảnh chụp Windows)"
        )
        self._btn_direct.clicked.connect(self._on_toggle_direct)

        self._btn_close = QPushButton("✕")
        self._btn_close.setObjectName("CloseMini")
        self._btn_close.setFixedWidth(24)
        self._btn_close.setToolTip("Tắt Dịch trực tiếp (Alt+W)")
        self._btn_close.clicked.connect(self._on_close)

        hl.addWidget(self._lbl_state)
        hl.addStretch(1)
        hl.addWidget(self._btn_pause)
        hl.addWidget(self._btn_direct)
        hl.addWidget(self._btn_close)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        set_exclude_from_capture(int(self.winId()), True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._header.setGeometry(0, 0, self.width(), self.HEADER_H)

    def set_capture_rect(self, rect: QRect) -> None:
        """Đặt vị trí & kích thước dựa theo vùng quét thực tế (tự cộng thêm chiều cao thanh header)."""
        self.setGeometry(rect.x(), max(0, rect.y() - self.HEADER_H), rect.width(), rect.height() + self.HEADER_H)

    def get_capture_rect(self) -> QRect:
        """Trả về QRect toàn cục (tọa độ logic) của đúng phần khung quét bên dưới header."""
        top_left = self.mapToGlobal(QPoint(3, self.HEADER_H + 3))
        w = max(20, self.width() - 6)
        h = max(20, self.height() - self.HEADER_H - 6)
        return QRect(top_left.x(), top_left.y(), w, h)

    def set_blocks(self, blocks: List[TextBlock]) -> None:
        self._blocks = list(blocks)
        if self._direct_overlay:
            self.update()

    def is_paused(self) -> bool:
        return self._paused

    def is_direct_overlay(self) -> bool:
        return self._direct_overlay

    def _on_toggle_pause(self) -> None:
        self._paused = not self._paused
        self._btn_pause.setText("Tiếp tục" if self._paused else "Tạm dừng")
        self._lbl_state.setText("⏸ Đã tạm dừng" if self._paused else "● Đang dịch trực tiếp")
        self._lbl_state.setStyleSheet(
            "color: #FBBF24; font-size: 12px; font-weight: 600;"
            if self._paused
            else "color: #6EE7B7; font-size: 12px; font-weight: 600;"
        )
        self.pause_toggled.emit(self._paused)
        self.update()

    def _on_toggle_direct(self) -> None:
        self._direct_overlay = not self._direct_overlay
        self._btn_direct.setObjectName("ActiveModeBtn" if self._direct_overlay else "")
        self._btn_direct.style().unpolish(self._btn_direct)
        self._btn_direct.style().polish(self._btn_direct)
        self.direct_mode_toggled.emit(self._direct_overlay)
        self.update()

    def _on_close(self) -> None:
        self.hide()
        self.closed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        frame_rect = QRectF(1.5, self.HEADER_H, self.width() - 3.0, self.height() - self.HEADER_H - 1.5)
        border_color = QColor("#F59E0B") if self._paused else QColor("#10B981")

        # Vẽ viền khung quét (ruột để alpha=0 hoàn toàn để click xuyên qua!)
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(border_color, 2.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(frame_rect, 6, 6)

        # Vẽ 4 góc kéo kích thước nổi bật
        corner_pen = QPen(QColor("#E2E8F0"), 3.2)
        p.setPen(corner_pen)
        c = 12.0
        l, t, r, b = frame_rect.left(), frame_rect.top(), frame_rect.right(), frame_rect.bottom()
        p.drawLine(QPoint(int(l), int(b)), QPoint(int(l + c), int(b)))
        p.drawLine(QPoint(int(l), int(b)), QPoint(int(l), int(b - c)))
        p.drawLine(QPoint(int(r), int(b)), QPoint(int(r - c), int(b)))
        p.drawLine(QPoint(int(r), int(b)), QPoint(int(r), int(b - c)))

        # Nếu bật chế độ "Đè chữ trực tiếp", vẽ các khung bản dịch ngay bên trong khung quét!
        if self._direct_overlay and self._blocks:
            used_bottoms: List[Tuple[float, float, float]] = []
            for block in self._blocks:
                text = block.translated_text or block.original_text
                bx = 3.0 + block.x1 - 3.0
                by = self.HEADER_H + 3.0 + block.y1 - 2.0
                bw = min(max(block.width + 8.0, 64.0), max(64.0, self.width() - bx - 6.0))
                bh = max(block.height + 4.0, 24.0)

                base_pt = int(round(max(10.0, min(20.0, block.avg_line_height * 0.54))))
                chosen_pt = base_pt
                needed_h = bh
                for pt in range(base_pt, 8, -1):
                    fm = QFontMetricsF(QFont("Segoe UI", pt))
                    br = fm.boundingRect(
                        QRectF(0, 0, max(28.0, bw - 12.0), 1200.0),
                        Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                        text,
                    )
                    if br.height() + 8.0 <= bh * 1.3 or pt == 9:
                        chosen_pt = pt
                        needed_h = max(bh, br.height() + 8.0)
                        break

                for ux1, ux2, ubot in used_bottoms:
                    if min(bx + bw, ux2) - max(bx, ux1) > 8 and by < ubot + 2:
                        by = ubot + 2

                rect = QRectF(bx, by, bw, needed_h)
                if rect.bottom() > self.height() - 4:
                    rect.setBottom(self.height() - 4)
                used_bottoms.append((bx, bx + bw, rect.bottom()))

                path = QPainterPath()
                path.addRoundedRect(rect, 6, 6)
                p.fillPath(path, QColor(15, 23, 42, 232))
                p.setPen(QPen(QColor(56, 189, 248, 175), 1.0))
                p.drawPath(path)

                p.setPen(QColor("#F8FAFC"))
                p.setFont(QFont("Segoe UI", chosen_pt, QFont.Weight.Medium))
                p.drawText(
                    rect.adjusted(6, 3, -6, -3),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                    text,
                )

        p.end()

    def _hit_test_edge(self, pos: QPoint) -> Optional[str]:
        m = self.BORDER_MARGIN
        w, h = self.width(), self.height()
        if pos.y() <= self.HEADER_H:
            return "move"
        on_left = pos.x() <= m
        on_right = pos.x() >= w - m
        on_bottom = pos.y() >= h - m
        if on_left and on_bottom:
            return "bl"
        if on_right and on_bottom:
            return "br"
        if on_left:
            return "l"
        if on_right:
            return "r"
        if on_bottom:
            return "b"
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            mode = self._hit_test_edge(pos)
            if mode:
                self._drag_mode = mode
                self._drag_start_global = event.globalPosition().toPoint()
                self._drag_start_geo = self.geometry()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if not self._drag_mode:
            edge = self._hit_test_edge(pos)
            cursor_map = {
                "move": Qt.CursorShape.SizeAllCursor,
                "l": Qt.CursorShape.SizeHorCursor,
                "r": Qt.CursorShape.SizeHorCursor,
                "b": Qt.CursorShape.SizeVerCursor,
                "bl": Qt.CursorShape.SizeBDiagCursor,
                "br": Qt.CursorShape.SizeFDiagCursor,
            }
            self.setCursor(cursor_map.get(edge, Qt.CursorShape.ArrowCursor))
            return

        delta = event.globalPosition().toPoint() - self._drag_start_global
        geo = QRect(self._drag_start_geo)
        min_w, min_h = self.minimumWidth(), self.minimumHeight()

        if self._drag_mode == "move":
            geo.translate(delta)
        else:
            if "l" in self._drag_mode:
                new_left = min(geo.right() - min_w, geo.left() + delta.x())
                geo.setLeft(new_left)
            if "r" in self._drag_mode:
                geo.setRight(max(geo.left() + min_w, geo.right() + delta.x()))
            if "b" in self._drag_mode:
                geo.setBottom(max(geo.top() + min_h, geo.bottom() + delta.y()))

        self.setGeometry(geo)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_mode is not None:
            self._drag_mode = None
            self.region_changed.emit(self.get_capture_rect())


class LiveSubtitleWindow(QWidget):
    """Khung phụ đề nổi hiển thị bản dịch trực tiếp liên tục (có thể xuyên chuột & tùy biến cỡ chữ)."""

    geometry_changed = Signal(QRect)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(280, 86)

        self._opacity = 0.88
        self._font_size = 15
        self._show_original = True
        self._click_through = False
        self._drag_pos: Optional[QPoint] = None
        self._last_translated = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame()
        self._card.setObjectName("SubCard")
        outer.addWidget(self._card)

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(14, 8, 12, 10)
        layout.setSpacing(4)

        # Hàng thông tin trên cùng
        top = QHBoxLayout()
        top.setSpacing(6)
        self._lbl_meta = QLabel("Dịch trực tiếp • Đang chờ chữ...")
        self._lbl_meta.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600;")

        self._btn_copy = QPushButton("Sao chép")
        self._btn_copy.setFixedHeight(22)
        self._btn_copy.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 1px 8px; border-radius: 5px; }"
        )
        self._btn_copy.clicked.connect(self._copy_text)

        self._btn_lock = QPushButton("Xuyên chuột")
        self._btn_lock.setFixedHeight(22)
        self._btn_lock.setToolTip("Khóa click xuyên qua khung phụ đề (nhấn Alt+S để mở khóa lại)")
        self._btn_lock.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 1px 8px; border-radius: 5px; }"
        )
        self._btn_lock.clicked.connect(lambda: self.set_click_through_mode(True))

        top.addWidget(self._lbl_meta)
        top.addStretch(1)
        top.addWidget(self._btn_copy)
        top.addWidget(self._btn_lock)
        layout.addLayout(top)

        self._lbl_original = QLabel("")
        self._lbl_original.setWordWrap(True)
        self._lbl_original.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(self._lbl_original)

        self._lbl_translated = QLabel("Đặt khung màu xanh lên vùng chữ bất kỳ để dịch tự động...")
        self._lbl_translated.setWordWrap(True)
        self._lbl_translated.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._lbl_translated, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addStretch(1)
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(14, 14)
        bottom.addWidget(self._grip)
        layout.addLayout(bottom)

        self.apply_appearance(self._opacity, self._font_size, self._show_original)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        set_exclude_from_capture(int(self.winId()), True)
        if self._click_through:
            set_click_through(int(self.winId()), True)

    def apply_appearance(self, opacity: float, font_size: int, show_original: bool) -> None:
        self._opacity = max(0.35, min(0.98, opacity))
        self._font_size = max(10, min(30, font_size))
        self._show_original = show_original
        alpha = int(round(self._opacity * 255))
        self._card.setStyleSheet(
            f"""
            QFrame#SubCard {{
                background-color: rgba(15, 23, 42, {alpha});
                border: 1px solid rgba(56, 189, 248, 0.42);
                border-radius: 12px;
            }}
            """
        )
        self._lbl_translated.setStyleSheet(
            f"color: #F8FAFC; font-size: {self._font_size}px; font-weight: 600;"
        )
        self._lbl_original.setVisible(show_original and bool(self._lbl_original.text()))

    def set_click_through_mode(self, enabled: bool) -> None:
        self._click_through = enabled
        self._btn_copy.setVisible(not enabled)
        self._btn_lock.setVisible(not enabled)
        self._grip.setVisible(not enabled)
        if enabled:
            self._lbl_meta.setText("📌 Chế độ xuyên chuột (Nhấn Alt+S để mở khóa)")
        if self.isVisible():
            set_click_through(int(self.winId()), enabled)

    def is_click_through(self) -> bool:
        return self._click_through

    def update_translation(
        self,
        original: str,
        translated: str,
        meta_text: str = "Dịch trực tiếp",
    ) -> None:
        self._last_translated = translated
        if not self._click_through:
            self._lbl_meta.setText(meta_text)
        self._lbl_original.setText(original.replace("\n\n", "  •  "))
        self._lbl_original.setVisible(self._show_original and bool(original.strip()))
        self._lbl_translated.setText(translated if translated.strip() else "Đang chờ nội dung mới...")

    def _copy_text(self) -> None:
        if self._last_translated.strip():
            QApplication.clipboard().setText(self._last_translated)
            self._lbl_meta.setText("✓ Đã sao chép bản dịch!")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self._click_through:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None:
            self._drag_pos = None
            self.geometry_changed.emit(self.geometry())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.isVisible():
            self.geometry_changed.emit(self.geometry())
