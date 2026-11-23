"""Phong cách giao diện Dark Glass hiện đại và biểu tượng ứng dụng."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

FONT_FAMILY = "Segoe UI, Microsoft YaHei UI, Arial, sans-serif"

DARK_GLASS_QSS = f"""
QWidget {{
    font-family: {FONT_FAMILY};
    color: #F1F5F9;
    font-size: 13px;
}}

QFrame#ControlBarCard {{
    background-color: rgba(15, 23, 42, 238);
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 14px;
}}

QFrame#FloatingPanel {{
    background-color: rgba(15, 23, 42, 244);
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 14px;
}}

QComboBox {{
    background-color: rgba(30, 41, 59, 220);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 8px;
    padding: 5px 10px;
    color: #F8FAFC;
    min-height: 20px;
}}

QComboBox:hover {{
    border-color: rgba(56, 189, 248, 0.75);
    background-color: rgba(30, 41, 59, 250);
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: #0F172A;
    color: #F8FAFC;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 8px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
    padding: 4px;
    outline: none;
}}

QPushButton {{
    background-color: rgba(30, 41, 59, 215);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 8px;
    padding: 6px 11px;
    color: #F1F5F9;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: rgba(51, 65, 85, 235);
    border-color: rgba(148, 163, 184, 0.45);
}}

QPushButton:pressed {{
    background-color: rgba(30, 41, 59, 255);
}}

QPushButton#PrimaryBtn {{
    background-color: #2563EB;
    border: 1px solid #3B82F6;
    color: #FFFFFF;
    font-weight: 600;
}}

QPushButton#PrimaryBtn:hover {{
    background-color: #1D4ED8;
    border-color: #60A5FA;
}}

QPushButton#LiveBtn {{
    background-color: rgba(16, 185, 129, 0.16);
    border: 1px solid rgba(16, 185, 129, 0.50);
    color: #6EE7B7;
    font-weight: 600;
}}

QPushButton#LiveBtn:hover {{
    background-color: rgba(16, 185, 129, 0.28);
    border-color: #34D399;
}}

QPushButton#LiveBtn[active="true"] {{
    background-color: #059669;
    border: 1px solid #34D399;
    color: #FFFFFF;
}}

QPushButton#IconBtn {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 4px 7px;
    color: #CBD5E1;
    font-weight: 600;
}}

QPushButton#IconBtn:hover {{
    background-color: rgba(51, 65, 85, 180);
    color: #FFFFFF;
}}

QPushButton#CloseBtn {{
    background-color: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px 7px;
    color: #94A3B8;
    font-weight: 700;
}}

QPushButton#CloseBtn:hover {{
    background-color: rgba(244, 63, 94, 0.85);
    color: #FFFFFF;
}}

QTextEdit, QPlainTextEdit, QLineEdit, QSpinBox {{
    background-color: rgba(30, 41, 59, 210);
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 8px;
    padding: 6px 8px;
    color: #F8FAFC;
    selection-background-color: #2563EB;
}}

QTextEdit:focus, QPlainTextEdit:focus, QLineEdit:focus, QSpinBox:focus {{
    border-color: #38BDF8;
}}

QCheckBox {{
    spacing: 8px;
    color: #E2E8F0;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid rgba(148, 163, 184, 0.45);
    background-color: rgba(30, 41, 59, 220);
}}

QCheckBox::indicator:checked {{
    background-color: #2563EB;
    border-color: #60A5FA;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: rgba(51, 65, 85, 220);
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
    background: #38BDF8;
}}

QListWidget {{
    background-color: rgba(15, 23, 42, 160);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 8px;
    outline: none;
}}

QListWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    color: #E2E8F0;
}}

QListWidget::item:selected {{
    background-color: rgba(37, 99, 235, 0.35);
    color: #FFFFFF;
}}

QListWidget::item:hover {{
    background-color: rgba(51, 65, 85, 0.45);
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: rgba(148, 163, 184, 0.35);
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


def create_app_icon(size: int = 64) -> QIcon:
    """Vẽ biểu tượng ứng dụng ScreenLens Translate sắc nét bằng QPainter."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    grad = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    grad.setColorAt(0.0, QColor("#2563EB"))
    grad.setColorAt(0.55, QColor("#0EA5E9"))
    grad.setColorAt(1.0, QColor("#10B981"))

    path = QPainterPath()
    r = size * 0.22
    path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), r, r)
    p.fillPath(path, grad)

    # Khung kính ngắm quét màn hình
    pen = QPen(QColor(255, 255, 255, 220), max(2.0, size * 0.055), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m = size * 0.18
    arm = size * 0.16
    # 4 góc khung quét
    p.drawLine(QPointF(m, m), QPointF(m + arm, m))
    p.drawLine(QPointF(m, m), QPointF(m, m + arm))

    p.drawLine(QPointF(size - m, m), QPointF(size - m - arm, m))
    p.drawLine(QPointF(size - m, m), QPointF(size - m, m + arm))

    p.drawLine(QPointF(m, size - m), QPointF(m + arm, size - m))
    p.drawLine(QPointF(m, size - m), QPointF(m, size - m - arm))

    p.drawLine(QPointF(size - m, size - m), QPointF(size - m - arm, size - m))
    p.drawLine(QPointF(size - m, size - m), QPointF(size - m, size - m - arm))

    # Chữ "A文" ở giữa
    font = QFont("Segoe UI", int(size * 0.28), QFont.Weight.Bold)
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "A文")

    p.end()
    return QIcon(pm)
