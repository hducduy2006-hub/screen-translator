"""
Lớp phủ dịch đè trực tiếp tại chỗ (In-Place Overlay):
Vẽ từng khung bản dịch gọn gàng ngay đè lên vị trí chữ gốc trên màn hình,
hỗ trợ hover xem chữ gốc, click sao chép từng đoạn, chuyển đổi Gốc/Dịch và đóng nhanh bằng Esc.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QToolTip, QWidget

from src.layout import TextBlock
from src.win32_utils import set_exclude_from_capture


class InPlaceOverlay(QWidget):
    """Hiển thị bản dịch trực tiếp đè lên vùng màn hình vừa quét."""

    closed = Signal()

    TOOLBAR_H = 38
    PAD = 10

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._region_rect = QRect()
        self._blocks: List[TextBlock] = []
        self._block_rects: List[Tuple[QRectF, TextBlock, int]] = []
        self._hover_idx: int = -1
        self._show_original = False
        self._loading = False
        self._loading_msg = "Đang nhận diện & dịch..."
        self._toast_msg = ""
        self._offset_x = self.PAD
        self._offset_y = self.TOOLBAR_H + self.PAD

        # Thanh công cụ mini nổi ngay phía trên vùng dịch
        self._toolbar = QWidget(self)
        self._toolbar.setObjectName("MiniToolbar")
        self._toolbar.setStyleSheet(
            """
            QWidget#MiniToolbar {
                background-color: rgba(15, 23, 42, 240);
                border: 1px solid rgba(56, 189, 248, 0.55);
                border-radius: 10px;
            }
            QPushButton {
                background-color: rgba(30, 41, 59, 210);
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 6px;
                padding: 3px 9px;
                color: #F8FAFC;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(37, 99, 235, 0.75);
                border-color: #60A5FA;
            }
            QPushButton#MiniClose:hover {
                background-color: rgba(244, 63, 94, 0.85);
                border-color: #FB7185;
            }
            QLabel {
                color: #38BDF8;
                font-size: 12px;
                font-weight: 600;
                padding: 0 4px;
            }
            """
        )
        tb_layout = QHBoxLayout(self._toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(6)

        self._lbl_badge = QLabel("Dịch đè")
        self._btn_toggle = QPushButton("Xem chữ gốc")
        self._btn_toggle.clicked.connect(self._toggle_original)

        self._btn_copy = QPushButton("Sao chép")
        self._btn_copy.clicked.connect(self._copy_all)

        self._btn_close = QPushButton("✕")
        self._btn_close.setObjectName("MiniClose")
        self._btn_close.setFixedWidth(26)
        self._btn_close.setToolTip("Đóng lớp phủ (Esc)")
        self._btn_close.clicked.connect(self.dismiss)

        tb_layout.addWidget(self._lbl_badge)
        tb_layout.addWidget(self._btn_toggle)
        tb_layout.addWidget(self._btn_copy)
        tb_layout.addWidget(self._btn_close)

        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)

    def show_loading(self, region_rect: QRect, message: str = "Đang nhận diện & dịch...") -> None:
        self._region_rect = QRect(region_rect)
        self._blocks = []
        self._block_rects = []
        self._show_original = False
        self._loading = True
        self._loading_msg = message
        self._btn_toggle.setText("Xem chữ gốc")
        self._lbl_badge.setText("⏳ Đang xử lý...")

        self._position_window(region_rect)
        self.show()
        set_exclude_from_capture(int(self.winId()), True)
        self.raise_()
        self.update()

    def show_blocks(self, region_rect: QRect, blocks: List[TextBlock], badge_text: str = "Đã dịch") -> None:
        self._region_rect = QRect(region_rect)
        self._blocks = list(blocks)
        self._loading = False
        self._show_original = False
        self._btn_toggle.setText("Xem chữ gốc")
        self._lbl_badge.setText(badge_text)

        self._position_window(region_rect)
        self._layout_block_rects()
        self.show()
        set_exclude_from_capture(int(self.winId()), True)
        self.raise_()
        self.activateWindow()
        self.update()

    def _position_window(self, region_rect: QRect) -> None:
        self._toolbar.adjustSize()
        min_w = max(region_rect.width() + self.PAD * 2, self._toolbar.width() + self.PAD * 2, 270)
        total_h = region_rect.height() + self.TOOLBAR_H + self.PAD * 2 + 24

        screen = QGuiApplication.screenAt(region_rect.center()) or QGuiApplication.primaryScreen()
        s_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        # Đặt toolbar phía trên vùng chọn; nếu sát mép trên quá thì đặt ở mép dưới
        win_x = region_rect.left() - self.PAD
        win_y = region_rect.top() - self.TOOLBAR_H - self.PAD
        toolbar_on_top = True
        if win_y < s_geo.top():
            win_y = region_rect.top() - self.PAD
            toolbar_on_top = False

        # Đảm bảo không tràn quá mép phải màn hình
        if win_x + min_w > s_geo.right():
            win_x = max(s_geo.left(), s_geo.right() - min_w)

        self.setGeometry(win_x, win_y, min_w, total_h)
        self._offset_x = region_rect.left() - win_x
        if toolbar_on_top:
            self._offset_y = region_rect.top() - win_y
            self._toolbar.move(max(4, self._offset_x), 2)
        else:
            self._offset_y = region_rect.top() - win_y
            self._toolbar.move(max(4, self._offset_x), self._offset_y + region_rect.height() + 6)
        self._toolbar.show()

    def _layout_block_rects(self) -> None:
        """Tính khung vẽ và cỡ chữ tự động cho từng khối bản dịch để chữ luôn dễ đọc và không chồng chéo."""
        self._block_rects = []
        used_bottoms: List[Tuple[float, float, float]] = []  # (x1, x2, bottom_y)

        for block in self._blocks:
            text = block.original_text if self._show_original else (block.translated_text or block.original_text)
            bx = self._offset_x + block.x1 - 4
            by = self._offset_y + block.y1 - 3
            bw = max(block.width + 10, 68.0)
            bh = max(block.height + 6, 26.0)

            # Chống tràn mép phải của cửa sổ overlay
            max_w = max(80.0, self.width() - bx - 6)
            bw = min(bw, max_w)

            # Chọn cỡ chữ thông minh dựa trên chiều cao dòng gốc
            base_pt = int(round(max(10.0, min(22.0, block.avg_line_height * 0.56))))
            chosen_pt = base_pt
            needed_h = bh

            for pt in range(base_pt, 8, -1):
                font = QFont("Segoe UI", pt)
                fm = QFontMetricsF(font)
                br = fm.boundingRect(
                    QRectF(0, 0, max(30.0, bw - 14), 2000),
                    Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap,
                    text,
                )
                req_h = br.height() + 10
                if req_h <= bh * 1.25 or pt == 9:
                    chosen_pt = pt
                    needed_h = max(bh, req_h)
                    break

            # Nếu khối trên bị đẩy xuống và chồng lấn ngang, dịch nhẹ xuống dưới
            for ux1, ux2, ubot in used_bottoms:
                if min(bx + bw, ux2) - max(bx, ux1) > 10 and by < ubot + 3:
                    by = ubot + 3

            rect = QRectF(bx, by, bw, needed_h)
            used_bottoms.append((bx, bx + bw, by + needed_h))
            self._block_rects.append((rect, block, chosen_pt))

        # Mở rộng chiều cao cửa sổ nếu các khối mở rộng vượt đáy
        if self._block_rects:
            max_bottom = max(r.bottom() for r, _, _ in self._block_rects)
            needed_win_h = int(max_bottom) + self.TOOLBAR_H + 16
            if needed_win_h > self.height():
                self.resize(self.width(), needed_win_h)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # Vẽ viền mảnh bao quanh vùng đã chọn
        region_local = QRectF(
            self._offset_x - 2,
            self._offset_y - 2,
            self._region_rect.width() + 4,
            self._region_rect.height() + 4,
        )
        border_pen = QPen(QColor(56, 189, 248, 175), 1.5, Qt.PenStyle.DashLine)
        p.setPen(border_pen)
        p.setBrush(QColor(15, 23, 42, 42))
        p.drawRoundedRect(region_local, 8, 8)

        if self._loading:
            # Khung đang tải ở giữa vùng chọn
            pill_w = min(max(210.0, region_local.width() * 0.7), 300.0)
            pill_h = 38.0
            pill = QRectF(
                region_local.center().x() - pill_w / 2,
                region_local.center().y() - pill_h / 2,
                pill_w,
                pill_h,
            )
            p.setPen(QPen(QColor("#38BDF8"), 1.5))
            p.setBrush(QColor(15, 23, 42, 238))
            p.drawRoundedRect(pill, 19, 19)
            p.setPen(QColor("#F8FAFC"))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, self._loading_msg)
            p.end()
            return

        if not self._block_rects:
            pill = QRectF(
                region_local.center().x() - 125,
                region_local.center().y() - 19,
                250,
                38,
            )
            p.setPen(QPen(QColor("#F59E0B"), 1.4))
            p.setBrush(QColor(15, 23, 42, 235))
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(QColor("#FDE68A"))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, "Không tìm thấy chữ trong vùng chọn")
            p.end()
            return

        # Vẽ từng khung bản dịch đè lên chữ gốc
        for idx, (rect, block, pt) in enumerate(self._block_rects):
            is_hover = idx == self._hover_idx
            bg = QColor(15, 23, 42, 240 if is_hover else 228)
            border = QColor("#38BDF8") if is_hover else QColor(148, 163, 184, 130)

            path = QPainterPath()
            path.addRoundedRect(rect, 7, 7)
            p.fillPath(path, bg)
            p.setPen(QPen(border, 1.5 if is_hover else 1.0))
            p.drawPath(path)

            text = block.original_text if self._show_original else (block.translated_text or block.original_text)
            text_color = QColor("#CBD5E1") if self._show_original else QColor("#F8FAFC")
            p.setPen(text_color)
            p.setFont(QFont("Segoe UI", pt, QFont.Weight.Medium))
            inner = rect.adjusted(7, 4, -7, -4)
            p.drawText(
                inner,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                text,
            )

        # Hiển thị thông báo nhỏ (toast) khi sao chép
        if self._toast_msg:
            toast = QRectF(region_local.center().x() - 95, region_local.top() + 8, 190, 30)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(16, 185, 129, 240))
            p.drawRoundedRect(toast, 15, 15)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            p.drawText(toast, Qt.AlignmentFlag.AlignCenter, self._toast_msg)

        p.end()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pt = event.position()
        new_hover = -1
        for idx, (rect, block, _) in enumerate(self._block_rects):
            if rect.contains(pt):
                new_hover = idx
                tip = f"Chữ gốc: {block.original_text}\n(Nhấn chuột trái để sao chép đoạn này)"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                break
        if new_hover != self._hover_idx:
            self._hover_idx = new_hover
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if new_hover >= 0 else Qt.CursorShape.ArrowCursor
            )
            self.update()
        if new_hover < 0:
            QToolTip.hideText()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self.dismiss()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            pt = event.position()
            for rect, block, _ in self._block_rects:
                if rect.contains(pt):
                    txt = block.original_text if self._show_original else (block.translated_text or block.original_text)
                    QApplication.clipboard().setText(txt)
                    self._show_toast("✓ Đã sao chép đoạn văn")
                    return

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()

    def _toggle_original(self) -> None:
        self._show_original = not self._show_original
        self._btn_toggle.setText("Xem bản dịch" if self._show_original else "Xem chữ gốc")
        self._layout_block_rects()
        self.update()

    def _copy_all(self) -> None:
        if not self._blocks:
            return
        texts = [
            (b.original_text if self._show_original else (b.translated_text or b.original_text))
            for b in self._blocks
        ]
        QApplication.clipboard().setText("\n\n".join(texts))
        self._show_toast("✓ Đã sao chép tất cả")

    def _show_toast(self, msg: str) -> None:
        self._toast_msg = msg
        self._toast_timer.start(1400)
        self.update()

    def _clear_toast(self) -> None:
        self._toast_msg = ""
        self.update()

    def dismiss(self) -> None:
        self.hide()
        self.closed.emit()
