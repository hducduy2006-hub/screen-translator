"""Hộp thoại Cài đặt tiếng Việt đầy đủ cho ScreenLens Translate."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config import AppConfig


class SettingsDialog(QDialog):
    """Cài đặt chế độ hiển thị, tốc độ OCR, phụ đề Live Mode và bộ dịch Google / Gemini."""

    def __init__(self, config: AppConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cài đặt — ScreenLens Translate")
        self.setMinimumWidth(470)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #0F172A;
                color: #F1F5F9;
            }
            QFrame#Section {
                background-color: rgba(30, 41, 59, 0.55);
                border: 1px solid rgba(148, 163, 184, 0.20);
                border-radius: 10px;
            }
            QLabel#SectionTitle {
                color: #38BDF8;
                font-weight: 700;
                font-size: 13px;
            }
            """
        )

        self._config = config
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(12)

        # --- Nhóm 1: Quét vùng & OCR ---
        sec1 = QFrame()
        sec1.setObjectName("Section")
        s1_layout = QVBoxLayout(sec1)
        s1_layout.setContentsMargins(12, 10, 12, 10)
        s1_layout.setSpacing(8)
        t1 = QLabel("Quét màn hình & Nhận diện chữ (OCR)")
        t1.setObjectName("SectionTitle")
        s1_layout.addWidget(t1)

        form1 = QFormLayout()
        form1.setSpacing(8)

        self._cb_display = QComboBox()
        self._cb_display.addItem("Đè trực tiếp lên chữ + Bảng kết quả", "both")
        self._cb_display.addItem("Chỉ đè trực tiếp lên màn hình", "inplace")
        self._cb_display.addItem("Chỉ hiện bảng kết quả nổi", "panel")
        idx_disp = self._cb_display.findData(config.snip_display_mode)
        self._cb_display.setCurrentIndex(max(0, idx_disp))
        form1.addRow("Khi quét vùng (Alt+Q):", self._cb_display)

        self._cb_ocr_speed = QComboBox()
        self._cb_ocr_speed.addItem("Chính xác cao (Khuyên dùng)", False)
        self._cb_ocr_speed.addItem("Siêu nhanh (Tiết kiệm CPU cho máy yếu)", True)
        self._cb_ocr_speed.setCurrentIndex(1 if config.ocr_fast_mode else 0)
        form1.addRow("Chế độ OCR:", self._cb_ocr_speed)

        s1_layout.addLayout(form1)

        self._chk_merge = QCheckBox("Tự động gộp các dòng liền nhau thành đoạn văn để dịch mượt hơn")
        self._chk_merge.setChecked(config.merge_paragraphs)
        s1_layout.addWidget(self._chk_merge)

        self._chk_autocopy = QCheckBox("Tự động sao chép bản dịch vào Clipboard sau khi quét")
        self._chk_autocopy.setChecked(config.auto_copy)
        s1_layout.addWidget(self._chk_autocopy)

        root.addWidget(sec1)

        # --- Nhóm 2: Dịch trực tiếp liên tục (Live Mode) ---
        sec2 = QFrame()
        sec2.setObjectName("Section")
        s2_layout = QVBoxLayout(sec2)
        s2_layout.setContentsMargins(12, 10, 12, 10)
        s2_layout.setSpacing(8)
        t2 = QLabel("Dịch trực tiếp liên tục (Live Mode — Alt+W)")
        t2.setObjectName("SectionTitle")
        s2_layout.addWidget(t2)

        form2 = QFormLayout()
        form2.setSpacing(8)

        self._spin_interval = QSpinBox()
        self._spin_interval.setRange(400, 3000)
        self._spin_interval.setSingleStep(100)
        self._spin_interval.setSuffix(" ms")
        self._spin_interval.setValue(config.live_interval_ms)
        form2.addRow("Chu kỳ quét thay đổi:", self._spin_interval)

        self._spin_font = QSpinBox()
        self._spin_font.setRange(11, 28)
        self._spin_font.setSuffix(" px")
        self._spin_font.setValue(config.live_font_size)
        form2.addRow("Cỡ chữ khung phụ đề:", self._spin_font)

        op_row = QHBoxLayout()
        self._slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self._slider_opacity.setRange(35, 98)
        self._slider_opacity.setValue(int(round(config.live_overlay_opacity * 100)))
        self._lbl_opacity = QLabel(f"{self._slider_opacity.value()}%")
        self._lbl_opacity.setFixedWidth(38)
        self._slider_opacity.valueChanged.connect(lambda v: self._lbl_opacity.setText(f"{v}%"))
        op_row.addWidget(self._slider_opacity)
        op_row.addWidget(self._lbl_opacity)
        form2.addRow("Độ đậm nền phụ đề:", op_row)

        s2_layout.addLayout(form2)

        self._chk_show_orig = QCheckBox("Hiển thị kèm văn bản gốc phía trên bản dịch phụ đề")
        self._chk_show_orig.setChecked(config.live_show_original)
        s2_layout.addWidget(self._chk_show_orig)

        root.addWidget(sec2)

        # --- Nhóm 3: Bộ dịch thuật ---
        sec3 = QFrame()
        sec3.setObjectName("Section")
        s3_layout = QVBoxLayout(sec3)
        s3_layout.setContentsMargins(12, 10, 12, 10)
        s3_layout.setSpacing(8)
        t3 = QLabel("Bộ dịch thuật (Engine)")
        t3.setObjectName("SectionTitle")
        s3_layout.addWidget(t3)

        form3 = QFormLayout()
        form3.setSpacing(8)
        self._cb_provider = QComboBox()
        self._cb_provider.addItem("Google Translate (Miễn phí, không cần khóa)", "google")
        self._cb_provider.addItem("Gemini AI (Dịch tự nhiên theo ngữ cảnh, cần API Key)", "gemini")
        idx_prov = self._cb_provider.findData(config.translator_provider)
        self._cb_provider.setCurrentIndex(max(0, idx_prov))
        self._cb_provider.currentIndexChanged.connect(self._update_provider_fields)
        form3.addRow("Nhà cung cấp dịch:", self._cb_provider)

        self._edit_gemini_key = QLineEdit(config.gemini_api_key)
        self._edit_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit_gemini_key.setPlaceholderText("Dán khóa Gemini API (AIza...) nếu dùng chế độ AI")
        form3.addRow("Gemini API Key:", self._edit_gemini_key)

        self._edit_gemini_model = QLineEdit(config.gemini_model)
        self._edit_gemini_model.setPlaceholderText("gemini-2.5-flash")
        form3.addRow("Mô hình Gemini:", self._edit_gemini_model)
        s3_layout.addLayout(form3)

        root.addWidget(sec3)

        # --- Phím tắt nhanh ---
        hk_label = QLabel(
            "Phím tắt toàn cục:   Alt + Q  Quét vùng & dịch đè   |   "
            "Alt + W  Bật/Tắt Dịch trực tiếp   |   Alt + S  Mở khóa / Ẩn-Hiện overlay   |   Esc  Đóng lớp phủ"
        )
        hk_label.setWordWrap(True)
        hk_label.setStyleSheet(
            "color: #94A3B8; font-size: 11px; padding: 6px 8px; "
            "background-color: rgba(15, 23, 42, 0.7); border-radius: 6px;"
        )
        root.addWidget(hk_label)

        # Nút Lưu / Hủy
        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_cancel = QPushButton("Hủy")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Lưu cài đặt")
        btn_save.setObjectName("PrimaryBtn")
        btn_save.clicked.connect(self._apply_and_accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_save)
        root.addLayout(btns)

        self._update_provider_fields()

    def _update_provider_fields(self) -> None:
        is_gemini = self._cb_provider.currentData() == "gemini"
        self._edit_gemini_key.setEnabled(is_gemini)
        self._edit_gemini_model.setEnabled(is_gemini)

    def _apply_and_accept(self) -> None:
        self._config.snip_display_mode = str(self._cb_display.currentData())
        self._config.ocr_fast_mode = bool(self._cb_ocr_speed.currentData())
        self._config.merge_paragraphs = self._chk_merge.isChecked()
        self._config.auto_copy = self._chk_autocopy.isChecked()
        self._config.live_interval_ms = self._spin_interval.value()
        self._config.live_font_size = self._spin_font.value()
        self._config.live_overlay_opacity = self._slider_opacity.value() / 100.0
        self._config.live_show_original = self._chk_show_orig.isChecked()
        self._config.translator_provider = str(self._cb_provider.currentData())
        self._config.gemini_api_key = self._edit_gemini_key.text().strip()
        self._config.gemini_model = self._edit_gemini_model.text().strip() or "gemini-2.5-flash"
        self._config.save()
        self.accept()
