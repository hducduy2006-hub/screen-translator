"""Pipeline hoàn chỉnh: Ảnh chụp màn hình -> Nhận diện OCR -> Nhóm đoạn -> Dịch thuật."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import List, Optional

import numpy as np

from src.config import AppConfig
from src.layout import TextBlock, group_lines_to_blocks
from src.ocr_engine import MultilingualOCREngine
from src.translator import TranslationEngine


@dataclass
class PipelineOutput:
    """Kết quả đầy đủ của một lần nhận diện & dịch vùng màn hình."""

    blocks: List[TextBlock] = field(default_factory=list)
    full_original: str = ""
    full_translated: str = ""
    detected_lang: str = ""
    ocr_ms: float = 0.0
    translate_ms: float = 0.0
    error: str = ""


class ScreenTranslatePipeline:
    """Điều phối OCR đa ngôn ngữ + nhóm khối văn bản + dịch thuật."""

    def __init__(
        self,
        ocr_engine: MultilingualOCREngine,
        translator: TranslationEngine,
    ) -> None:
        self.ocr = ocr_engine
        self.translator = translator

    def process_image(
        self,
        image_rgb: np.ndarray,
        config: AppConfig,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
    ) -> PipelineOutput:
        t0 = time.perf_counter()
        try:
            lines = self.ocr.recognize(
                image_rgb=image_rgb,
                source_lang=config.source_lang,
                scale_x=scale_x,
                scale_y=scale_y,
                fast_mode=config.ocr_fast_mode,
            )
        except Exception as exc:
            return PipelineOutput(error=f"Lỗi nhận diện OCR: {exc}")
        ocr_ms = (time.perf_counter() - t0) * 1000.0

        if not lines:
            return PipelineOutput(ocr_ms=ocr_ms)

        blocks = group_lines_to_blocks(lines, merge_paragraphs=config.merge_paragraphs)
        if not blocks:
            return PipelineOutput(ocr_ms=ocr_ms)

        t1 = time.perf_counter()
        try:
            trans_results = self.translator.translate_batch(
                texts=[b.original_text for b in blocks],
                source_lang=config.source_lang,
                target_lang=config.target_lang,
                provider=config.translator_provider,
                gemini_api_key=config.gemini_api_key,
                gemini_model=config.gemini_model,
            )
        except Exception as exc:
            return PipelineOutput(
                blocks=blocks,
                full_original="\n".join(b.original_text for b in blocks),
                ocr_ms=ocr_ms,
                error=f"Lỗi kết nối dịch thuật: {exc}",
            )
        translate_ms = (time.perf_counter() - t1) * 1000.0

        detected_lang: Optional[str] = None
        for block, tr in zip(blocks, trans_results):
            block.translated_text = tr.translated_text
            block.detected_lang = tr.detected_lang
            if not detected_lang and tr.detected_lang and tr.detected_lang != "auto":
                detected_lang = tr.detected_lang

        full_original = "\n\n".join(b.original_text for b in blocks)
        full_translated = "\n\n".join(b.translated_text for b in blocks)

        return PipelineOutput(
            blocks=blocks,
            full_original=full_original,
            full_translated=full_translated,
            detected_lang=detected_lang or config.source_lang,
            ocr_ms=ocr_ms,
            translate_ms=translate_ms,
        )
