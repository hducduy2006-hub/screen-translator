"""Bảng kết quả chi tiết, dịch nhập tay và lịch sử các bản dịch gần đây."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from src.win32_utils import set_exclude_from_capture


@dataclass
class HistoryEntry:
    timestamp: str
    lang_pair: str
    original: str
    translated: str


class HistoryPanel(QWidget):
    """Cửa sổ nổi hiển thị Văn bản gốc, Bản dịch (có thể chỉnh sửa & dịch lại) và Lịch sử dịch."""

    retranslate_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(410, 440)
        self.resize(450, 520)

        self._drag_pos: Optional[QPoint] = None
        self._entries: List[HistoryEntry] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("FloatingPanel")
        root.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        # Tiêu đề
        header = QHBoxLayout()
        title = QLabel("Kết quả & Lịch sử dịch")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F8FAFC;")
        self._lbl_info = QLabel("")
        self._lbl_info.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600;")

        btn_close = QPushButton("✕")
        btn_close.setObjectName("CloseBtn")
        btn_close.setFixedSize(26, 26)
        btn_close.clicked.connect(self.hide)

        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self._lbl_info)
        header.addStretch(1)
        header.addWidget(btn_close)
        layout.addLayout(header)

        # Vùng văn bản gốc
        orig_row = QHBoxLayout()
        lbl_orig = QLabel("Văn bản gốc (có thể gõ hoặc sửa để dịch lại)")
        lbl_orig.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600;")
        btn_retrans = QPushButton("Dịch lại")
        btn_retrans.setObjectName("PrimaryBtn")
        btn_retrans.setFixedHeight(26)
        btn_retrans.clicked.connect(self._on_retranslate)
        orig_row.addWidget(lbl_orig)
        orig_row.addStretch(1)
        orig_row.addWidget(btn_retrans)
        layout.addLayout(orig_row)

        self._txt_original = QPlainTextEdit()
        self._txt_original.setPlaceholderText("Quét màn hình (Alt+Q) hoặc nhập trực tiếp tiếng Anh / Việt / Trung vào đây...")
        self._txt_original.setMaximumHeight(110)
        layout.addWidget(self._txt_original)

        # Vùng bản dịch
        trans_row = QHBoxLayout()
        lbl_trans = QLabel("Bản dịch")
        lbl_trans.setStyleSheet("color: #38BDF8; font-size: 12px; font-weight: 600;")
        self._btn_copy_trans = QPushButton("Sao chép bản dịch")
        self._btn_copy_trans.setFixedHeight(26)
        self._btn_copy_trans.clicked.connect(self._copy_translated)
        trans_row.addWidget(lbl_trans)
        trans_row.addStretch(1)
        trans_row.addWidget(self._btn_copy_trans)
        layout.addLayout(trans_row)

        self._txt_translated = QPlainTextEdit()
        self._txt_translated.setReadOnly(True)
        self._txt_translated.setPlaceholderText("Bản dịch sẽ xuất hiện tại đây...")
        self._txt_translated.setStyleSheet(
            "QPlainTextEdit { font-size: 14px; font-weight: 500; color: #F8FAFC; }"
        )
        self._txt_translated.setMinimumHeight(110)
        layout.addWidget(self._txt_translated, 1)

        # Lịch sử dịch
        hist_row = QHBoxLayout()
        lbl_hist = QLabel("Lịch sử gần đây")
        lbl_hist.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600;")
        btn_clear = QPushButton("Xóa lịch sử")
        btn_clear.setFixedHeight(24)
        btn_clear.clicked.connect(self._clear_history)
        hist_row.addWidget(lbl_hist)
        hist_row.addStretch(1)
        hist_row.addWidget(btn_clear)
        layout.addLayout(hist_row)

        self._list_history = QListWidget()
        self._list_history.setMinimumHeight(110)
        self._list_history.itemClicked.connect(self._on_select_history)
        layout.addWidget(self._list_history, 1)

        # Góc kéo kích thước
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.addStretch(1)
        foot.addWidget(QSizeGrip(self))
        layout.addLayout(foot)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        set_exclude_from_capture(int(self.winId()), True)

    def add_result(
        self,
        original: str,
        translated: str,
        lang_pair: str,
        info_text: str = "",
        record_history: bool = True,
    ) -> None:
        self._txt_original.setPlainText(original)
        self._txt_translated.setPlainText(translated)
        self._lbl_info.setText(info_text or lang_pair)

        if not record_history or not original.strip():
            return
        # Tránh lưu trùng lặp liên tiếp
        if self._entries and self._entries[0].original == original and self._entries[0].translated == translated:
            return

        entry = HistoryEntry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            lang_pair=lang_pair,
            original=original,
            translated=translated,
        )
        self._entries.insert(0, entry)
        if len(self._entries) > 50:
            self._entries.pop()
        self._refresh_list()

    def _refresh_list(self) -> None:
        self._list_history.clear()
        for idx, e in enumerate(self._entries):
            preview_orig = e.original.replace("\n", " ")[:48]
            preview_trans = e.translated.replace("\n", " ")[:58]
            item = QListWidgetItem(f"[{e.timestamp} • {e.lang_pair}] {preview_orig}\n→ {preview_trans}")
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._list_history.addItem(item)

    def _on_select_history(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self._entries):
            e = self._entries[idx]
            self._txt_original.setPlainText(e.original)
            self._txt_translated.setPlainText(e.translated)
            self._lbl_info.setText(f"{e.lang_pair} ({e.timestamp})")

    def _on_retranslate(self) -> None:
        txt = self._txt_original.toPlainText().strip()
        if txt:
            self.retranslate_requested.emit(txt)

    def _copy_translated(self) -> None:
        txt = self._txt_translated.toPlainText().strip()
        if txt:
            QApplication.clipboard().setText(txt)
            self._btn_copy_trans.setText("✓ Đã sao chép")
            from PySide6.QtCore import QTimer

            QTimer.singleShot(1400, lambda: self._btn_copy_trans.setText("Sao chép bản dịch"))

    def _clear_history(self) -> None:
        self._entries.clear()
        self._list_history.clear()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= 42:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._drag_pos = None
