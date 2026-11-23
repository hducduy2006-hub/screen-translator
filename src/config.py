"""Cấu hình ứng dụng và danh sách ngôn ngữ hỗ trợ."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

APP_NAME = "ScreenLens Translate"
CONFIG_DIR = Path.home() / ".screenlens_translate"
CONFIG_PATH = CONFIG_DIR / "config.json"

# (code, display_name_vi, short_badge)
SOURCE_LANGUAGES: List[Tuple[str, str, str]] = [
    ("auto", "Tự động (Anh / Việt / Trung)", "AUTO"),
    ("en", "Tiếng Anh (English)", "EN"),
    ("vi", "Tiếng Việt", "VI"),
    ("zh-CN", "Tiếng Trung - Giản thể (简体)", "ZH-S"),
    ("zh-TW", "Tiếng Trung - Phồn thể (繁體)", "ZH-T"),
    ("ja", "Tiếng Nhật (日本語)", "JA"),
    ("ko", "Tiếng Hàn (한국어)", "KO"),
]

TARGET_LANGUAGES: List[Tuple[str, str, str]] = [
    ("vi", "Tiếng Việt", "VI"),
    ("en", "Tiếng Anh (English)", "EN"),
    ("zh-CN", "Tiếng Trung - Giản thể (简体)", "ZH-S"),
    ("zh-TW", "Tiếng Trung - Phồn thể (繁體)", "ZH-T"),
    ("ja", "Tiếng Nhật (日本語)", "JA"),
    ("ko", "Tiếng Hàn (한국어)", "KO"),
]

LANG_LABELS: Dict[str, str] = {code: label for code, label, _ in SOURCE_LANGUAGES}
LANG_BADGES: Dict[str, str] = {code: badge for code, _, badge in SOURCE_LANGUAGES}


@dataclass
class AppConfig:
    """Cấu hình lưu trữ của người dùng."""

    source_lang: str = "auto"
    target_lang: str = "vi"

    # Chế độ hiển thị khi quét vùng: "inplace" (đè chữ), "panel" (bảng kết quả), "both" (cả hai)
    snip_display_mode: str = "inplace"

    # Dịch trực tiếp liên tục (Live Mode)
    live_interval_ms: int = 850
    live_click_through: bool = False
    live_show_original: bool = True
    live_overlay_opacity: float = 0.88
    live_font_size: int = 15

    # Xử lý OCR & bố cục
    merge_paragraphs: bool = True
    ocr_fast_mode: bool = False  # False = độ chính xác cao, True = tốc độ tối đa

    # Bộ dịch: "google" (miễn phí, không cần key) hoặc "gemini" (cần API key)
    translator_provider: str = "google"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Vị trí cửa sổ lưu lại (rỗng = tự động căn giữa theo kích thước màn hình thực tế)
    bar_x: int = -1
    bar_y: int = -1
    live_region: List[int] = field(default_factory=list)
    subtitle_pos: List[int] = field(default_factory=list)

    # Tự động sao chép bản dịch vào clipboard
    auto_copy: bool = False

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AppConfig":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in raw.items() if k in valid_fields}
            return cls(**filtered)
        except Exception:
            return cls()
