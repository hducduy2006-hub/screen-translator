"""Kiểm thử toàn diện OCR (Anh - Việt - Trung), gom đoạn, dịch thuật và khởi tạo giao diện Qt."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Đảm bảo import từ thư mục gốc dự án
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.capture import FrameDiffer
from src.config import AppConfig
from src.layout import TextLine, group_lines_to_blocks
from src.ocr_engine import MultilingualOCREngine
from src.pipeline import ScreenTranslatePipeline
from src.translator import TranslationEngine


def _render_lines(lines_with_fonts, width=1100, height=260, bg=(255, 255, 255), fg=(18, 18, 18)) -> np.ndarray:
    img = Image.new("RGB", (width, height), color=bg)
    draw = ImageDraw.Draw(img)
    y = 26
    for text, font_path, size in lines_with_fonts:
        font = ImageFont.truetype(font_path, size)
        draw.text((28, y), text, fill=fg, font=font)
        y += int(size * 1.65)
    return np.array(img)


def test_config_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cfg.json"
        cfg = AppConfig(source_lang="zh-CN", target_lang="vi", live_font_size=18, auto_copy=True)
        cfg.save(p)
        loaded = AppConfig.load(p)
        assert loaded.source_lang == "zh-CN"
        assert loaded.target_lang == "vi"
        assert loaded.live_font_size == 18
        assert loaded.auto_copy is True
    print("[PASS] test_config_roundtrip")


def test_layout_grouping() -> None:
    lines = [
        TextLine(10, 10, 300, 34, "This is a multi-"),
        TextLine(10, 40, 290, 64, "line English paragraph."),
        TextLine(10, 140, 220, 166, "你好世界"),
        TextLine(10, 172, 220, 198, "屏幕翻译"),
    ]
    blocks = group_lines_to_blocks(lines, merge_paragraphs=True)
    assert len(blocks) == 2, f"Expected 2 blocks, got {len(blocks)}"
    assert blocks[0].original_text == "This is a multiline English paragraph."
    assert blocks[1].original_text == "你好世界屏幕翻译"

    unmerged = group_lines_to_blocks(lines, merge_paragraphs=False)
    assert len(unmerged) == 4
    print("[PASS] test_layout_grouping")


def test_frame_differ() -> None:
    differ = FrameDiffer()
    img1 = np.full((120, 300, 3), 240, dtype=np.uint8)
    assert differ.has_changed(img1) is True
    # Không đổi -> False
    assert differ.has_changed(img1.copy()) is False
    # Thay đổi vùng chữ -> True
    img2 = img1.copy()
    img2[40:80, 40:260] = 20
    assert differ.has_changed(img2) is True
    print("[PASS] test_frame_differ")


def test_pipeline_multilingual_ocr_and_translate() -> None:
    ocr = MultilingualOCREngine()
    translator = TranslationEngine()
    pipeline = ScreenTranslatePipeline(ocr, translator)

    segoe = r"C:\Windows\Fonts\segoeui.ttf"
    msyh = r"C:\Windows\Fonts\msyh.ttc"
    msjh = r"C:\Windows\Fonts\msjh.ttc"

    # 1. Tiếng Anh -> Tiếng Việt (chế độ auto)
    en_img = _render_lines([("Artificial intelligence is transforming everyday software.", segoe, 30)], height=110)
    out_en = pipeline.process_image(en_img, AppConfig(source_lang="auto", target_lang="vi"))
    assert not out_en.error, out_en.error
    assert "Artificial intelligence" in out_en.full_original
    assert len(out_en.full_translated) > 10
    print(f"  [EN->VI] {out_en.full_original!r} => {out_en.full_translated!r} ({out_en.ocr_ms:.0f}ms + {out_en.translate_ms:.0f}ms)")

    # 2. Tiếng Việt có dấu đầy đủ -> Tiếng Anh (chế độ auto)
    vi_img = _render_lines([("Phần mềm dịch trực tiếp trên màn hình hỗ trợ tiếng Việt có dấu.", segoe, 28)], height=110)
    out_vi = pipeline.process_image(vi_img, AppConfig(source_lang="auto", target_lang="en"))
    assert not out_vi.error, out_vi.error
    assert "Phần mềm dịch trực tiếp" in out_vi.full_original, f"OCR VI sai dấu: {out_vi.full_original!r}"
    assert "tiếng Việt" in out_vi.full_original, f"OCR VI sai dấu: {out_vi.full_original!r}"
    assert "Vietnamese" in out_vi.full_translated or "screen" in out_vi.full_translated.lower()
    print(f"  [VI->EN] {out_vi.full_original!r} => {out_vi.full_translated!r} ({out_vi.ocr_ms:.0f}ms + {out_vi.translate_ms:.0f}ms)")

    # 3. Tiếng Việt -> Tiếng Trung Giản thể
    out_vi_zh = pipeline.process_image(vi_img, AppConfig(source_lang="vi", target_lang="zh-CN"))
    assert not out_vi_zh.error, out_vi_zh.error
    assert any("\u4e00" <= ch <= "\u9fff" for ch in out_vi_zh.full_translated)
    print(f"  [VI->ZH] {out_vi_zh.full_original!r} => {out_vi_zh.full_translated!r}")

    # 4. Tiếng Trung Giản thể -> Tiếng Việt (chế độ auto)
    zh_s_img = _render_lines([("这款软件可以直接在屏幕上实时翻译中文和英文。", msyh, 32)], height=110)
    out_zhs = pipeline.process_image(zh_s_img, AppConfig(source_lang="auto", target_lang="vi"))
    assert not out_zhs.error, out_zhs.error
    assert "这款软件" in out_zhs.full_original
    assert len(out_zhs.full_translated) > 10
    print(f"  [ZHS->VI] {out_zhs.full_original!r} => {out_zhs.full_translated!r}")

    # 5. Tiếng Trung Phồn thể -> Tiếng Việt (chế độ auto)
    zh_t_img = _render_lines([("歡迎使用螢幕即時翻譯軟體，操作簡單快速。", msjh, 32)], height=110)
    out_zht = pipeline.process_image(zh_t_img, AppConfig(source_lang="auto", target_lang="vi"))
    assert not out_zht.error, out_zht.error
    assert "歡迎使用" in out_zht.full_original
    print(f"  [ZHT->VI] {out_zht.full_original!r} => {out_zht.full_translated!r}")

    # 6. Ảnh pha trộn cả 3 ngôn ngữ Trung + Việt + Anh trên cùng 1 khung (chế độ auto, không gộp đoạn)
    mixed_img = _render_lines(
        [
            ("你好，今天天气真好！", msyh, 30),
            ("Hôm nay trời thật đẹp và trong xanh!", segoe, 28),
            ("Screen translation works seamlessly.", segoe, 28),
        ],
        height=240,
    )
    out_mix = pipeline.process_image(
        mixed_img, AppConfig(source_lang="auto", target_lang="vi", merge_paragraphs=False)
    )
    assert not out_mix.error, out_mix.error
    joined_orig = " | ".join(b.original_text for b in out_mix.blocks)
    assert "你好" in joined_orig, joined_orig
    assert "Hôm nay trời thật đẹp" in joined_orig, joined_orig
    assert "Screen translation" in joined_orig, joined_orig
    print(f"  [MIXED ] {joined_orig!r}")

    translator.close()
    print("[PASS] test_pipeline_multilingual_ocr_and_translate")


def test_gui_smoke() -> None:
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from src.layout import TextBlock
    from src.ui.control_bar import ControlBar
    from src.ui.history_panel import HistoryPanel
    from src.ui.inplace_overlay import InPlaceOverlay
    from src.ui.live_overlay import LiveCaptureFrame, LiveSubtitleWindow
    from src.ui.settings_dialog import SettingsDialog
    from src.ui.snip_overlay import SnipOverlay
    from src.ui.styles import DARK_GLASS_QSS
    from src.win32_utils import set_exclude_from_capture

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(DARK_GLASS_QSS)

    cfg = AppConfig()
    bar = ControlBar(cfg)
    bar.show()
    ok_affinity = set_exclude_from_capture(int(bar.winId()), True)
    assert ok_affinity is True, "WDA_EXCLUDEFROMCAPTURE failed on ControlBar"

    snip = SnipOverlay()
    inplace = InPlaceOverlay()
    inplace.show_blocks(
        QRect(100, 100, 320, 120),
        [TextBlock(10, 10, 280, 44, "Hello World", "Xin chào thế giới")],
        "EN → VI",
    )
    live_frame = LiveCaptureFrame()
    live_sub = LiveSubtitleWindow()
    live_sub.update_translation("Hello", "Xin chào", "EN → VI")
    hist = HistoryPanel()
    hist.add_result("Hello", "Xin chào", "EN → VI")
    dlg = SettingsDialog(cfg)

    app.processEvents()
    widgets = [bar, snip, inplace, live_frame, live_sub, hist, dlg]
    for w in widgets:
        w.close()
        w.deleteLater()
    widgets.clear()
    del bar, snip, inplace, live_frame, live_sub, hist, dlg
    app.processEvents()
    print("[PASS] test_gui_smoke (all 7 Qt windows + WDA_EXCLUDEFROMCAPTURE verified)")


if __name__ == "__main__":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    test_config_roundtrip()
    test_layout_grouping()
    test_frame_differ()
    test_pipeline_multilingual_ocr_and_translate()
    test_gui_smoke()
    print("\nALL TESTS PASSED!")
