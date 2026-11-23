"""Thanh điều khiển nổi nhỏ gọn (Floating Control Bar) luôn nằm gọn trên màn hình."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig, SOURCE_LANGUAGES, TARGET_LANGUAGES
from src.ui.styles import create_app_icon
from src.win32_utils import set_exclude_from_capture


class ControlBar(QWidget):
    """Thanh điều khiển chính của ScreenLens Translate."""

    snip_requested = Signal()
    live_toggled = Signal()
    history_toggled = Signal()
    settings_requested = Signal()
    languages_changed = Signal(str, str)
    minimize_to_tray_requested = Signal()
    quit_requested = Signal()
    position_changed = Signal(int, int)

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("ScreenLens Translate")
        self.setWindowIcon(create_app_icon(64))

        self._drag_pos: Optional[QPoint] = None
        self._suppress_lang_signal = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("ControlBarCard")
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 6)
        card_layout.setSpacing(4)

        # Hàng điều khiển chính
        row = QHBoxLayout()
        row.setSpacing(6)

        # Logo + tay kéo
        self._lbl_brand = QLabel("✦ Dịch Màn Hình")
        self._lbl_brand.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 13px; padding: 0 4px;")
        self._lbl_brand.setToolTip("Kéo giữ thanh này để di chuyển đến bất kỳ vị trí nào trên màn hình")
        row.addWidget(self._lbl_brand)

        # Ngôn ngữ nguồn
        self._cb_source = QComboBox()
        self._cb_source.setMinimumWidth(168)
        for code, label, _ in SOURCE_LANGUAGES:
            self._cb_source.addItem(label, code)
        self._set_combo_value(self._cb_source, config.source_lang)
        self._cb_source.currentIndexChanged.connect(self._on_lang_changed)
        row.addWidget(self._cb_source)

        # Nút đảo ngôn ngữ
        self._btn_swap = QPushButton("⇄")
        self._btn_swap.setObjectName("IconBtn")
        self._btn_swap.setFixedSize(28, 28)
        self._btn_swap.setToolTip("Đảo ngược ngôn ngữ nguồn ↔ đích")
        self._btn_swap.clicked.connect(self._on_swap)
        row.addWidget(self._btn_swap)

        # Ngôn ngữ đích
        self._cb_target = QComboBox()
        self._cb_target.setMinimumWidth(145)
        for code, label, _ in TARGET_LANGUAGES:
            self._cb_target.addItem(label, code)
        self._set_combo_value(self._cb_target, config.target_lang)
        self._cb_target.currentIndexChanged.connect(self._on_lang_changed)
        row.addWidget(self._cb_target)

        # Nút Quét dịch
        self._btn_snip = QPushButton("✂ Quét dịch")
        self._btn_snip.setObjectName("PrimaryBtn")
        self._btn_snip.setToolTip("Chọn vùng trên màn hình để dịch ngay (Phím tắt: Alt + Q)")
        self._btn_snip.clicked.connect(self.snip_requested.emit)
        row.addWidget(self._btn_snip)

        # Nút Dịch trực tiếp liên tục
        self._btn_live = QPushButton("▶ Dịch trực tiếp")
        self._btn_live.setObjectName("LiveBtn")
        self._btn_live.setProperty("active", False)
        self._btn_live.setToolTip("Mở khung tự động dịch trực tiếp liên tục theo thời gian thực (Alt + W)")
        self._btn_live.clicked.connect(self.live_toggled.emit)
        row.addWidget(self._btn_live)

        # Nút Bảng kết quả / Lịch sử
        self._btn_history = QPushButton("📋")
        self._btn_history.setObjectName("IconBtn")
        self._btn_history.setFixedSize(30, 28)
        self._btn_history.setToolTip("Mở bảng kết quả, dịch nhập tay & lịch sử")
        self._btn_history.clicked.connect(self.history_toggled.emit)
        row.addWidget(self._btn_history)

        # Nút Cài đặt
        self._btn_settings = QPushButton("⚙")
        self._btn_settings.setObjectName("IconBtn")
        self._btn_settings.setFixedSize(30, 28)
        self._btn_settings.setToolTip("Cài đặt hiển thị, OCR & bộ dịch")
        self._btn_settings.clicked.connect(self.settings_requested.emit)
        row.addWidget(self._btn_settings)

        # Thu gọn xuống khay hệ thống
        self._btn_tray = QPushButton("—")
        self._btn_tray.setObjectName("IconBtn")
        self._btn_tray.setFixedSize(26, 28)
        self._btn_tray.setToolTip("Thu gọn xuống khay hệ thống (vẫn dùng được phím tắt Alt+Q / Alt+W)")
        self._btn_tray.clicked.connect(self.minimize_to_tray_requested.emit)
        row.addWidget(self._btn_tray)

        # Thoát
        self._btn_quit = QPushButton("✕")
        self._btn_quit.setObjectName("CloseBtn")
        self._btn_quit.setFixedSize(26, 28)
        self._btn_quit.setToolTip("Thoát phần mềm")
        self._btn_quit.clicked.connect(self.quit_requested.emit)
        row.addWidget(self._btn_quit)

        card_layout.addLayout(row)

        # Dòng trạng thái mỏng phía dưới
        self._lbl_status = QLabel("Sẵn sàng  •  Phím tắt: Alt+Q (Quét dịch)  |  Alt+W (Dịch trực tiếp)  |  Alt+S (Mở khóa/Ẩn)")
        self._lbl_status.setStyleSheet("color: #94A3B8; font-size: 11px; padding-left: 4px;")
        card_layout.addWidget(self._lbl_status)

        self.adjustSize()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        set_exclude_from_capture(int(self.winId()), True)

    @staticmethod
    def _set_combo_value(combo: QComboBox, code: str) -> None:
        idx = combo.findData(code)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def set_status(self, message: str, color: str = "#94A3B8") -> None:
        self._lbl_status.setText(message)
        self._lbl_status.setStyleSheet(f"color: {color}; font-size: 11px; padding-left: 4px;")

    def set_live_active(self, active: bool) -> None:
        self._btn_live.setProperty("active", active)
        self._btn_live.setText("■ Dừng trực tiếp" if active else "▶ Dịch trực tiếp")
        self._btn_live.style().unpolish(self._btn_live)
        self._btn_live.style().polish(self._btn_live)

    def _on_lang_changed(self) -> None:
        if self._suppress_lang_signal:
            return
        src = str(self._cb_source.currentData())
        tgt = str(self._cb_target.currentData())
        self.languages_changed.emit(src, tgt)

    def _on_swap(self) -> None:
        src = str(self._cb_source.currentData())
        tgt = str(self._cb_target.currentData())
        # Nếu nguồn đang là "auto", đảo thành tgt -> "vi" (hoặc "en" nếu tgt == "vi")
        new_src = tgt
        new_tgt = "en" if (src == "auto" and tgt == "vi") else ("vi" if src == "auto" else src)

        self._suppress_lang_signal = True
        self._set_combo_value(self._cb_source, new_src)
        self._set_combo_value(self._cb_target, new_tgt)
        self._suppress_lang_signal = False
        self.languages_changed.emit(new_src, new_tgt)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None:
            self._drag_pos = None
            self.position_changed.emit(self.x(), self.y())
