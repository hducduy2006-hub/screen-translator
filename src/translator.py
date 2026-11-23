"""
Bộ dịch thuật đa ngôn ngữ hỗ trợ chuỗi dự phòng 3 tầng + tùy chọn Gemini AI:
1. Google Translate (clients5 dict-chrome-ex — hỗ trợ dịch theo lô chuẩn xác, phát hiện ngôn ngữ từng đoạn).
2. Google Translate (translate.googleapis.com gtx — dự phòng 1).
3. MyMemory API (dự phòng 2, tự nhận diện tiếng Việt/Trung/Nhật/Hàn/Anh khi nguồn = auto).
4. Gemini AI (tùy chọn nâng cao trong Cài đặt khi người dùng nhập API Key).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re
import threading
from typing import List, Optional, Tuple

import httpx

from src.config import LANG_LABELS

_PURE_SYMBOL_RE = re.compile(r"^[\d\s\W_]+$")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_KANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
_VI_DIACRITIC_RE = re.compile(
    r"[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ"
    r"ÀÁẢÃẠẰẮẲẴẶẦẤẨẪẬÈÉẺẼẸỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌỒỐỔỖỘỜỚỞỠỢÙÚỦŨỤỪỨỬỮỰỲÝỶỸỴ]"
)


@dataclass
class TranslationResult:
    translated_text: str
    detected_lang: str = ""
    provider: str = "google"
    from_cache: bool = False


def _normalize_lang_code(code: str) -> str:
    c = (code or "").strip()
    low = c.lower()
    if low in ("zh", "zh-cn", "zh_cn", "zh-hans"):
        return "zh-CN"
    if low in ("zh-tw", "zh_tw", "zh-hk", "zh-hant"):
        return "zh-TW"
    return low or "auto"


def _same_language(detected: str, target: str) -> bool:
    d = _normalize_lang_code(detected)
    t = _normalize_lang_code(target)
    if not d or d == "auto":
        return False
    return d == t


def guess_script_lang(text: str) -> str:
    """Đoán nhanh ngôn ngữ theo hệ chữ viết dùng cho bộ dự phòng MyMemory khi nguồn là auto."""
    if _KANA_RE.search(text):
        return "ja"
    if _HANGUL_RE.search(text):
        return "ko"
    if _CJK_RE.search(text):
        return "zh-CN"
    if _VI_DIACRITIC_RE.search(text):
        return "vi"
    return "en"


class TranslationEngine:
    """Bộ dịch thuật có bộ nhớ đệm LRU, hỗ trợ dịch đơn lẻ và dịch nhiều khối cùng lúc."""

    def __init__(self, cache_size: int = 512) -> None:
        self._cache: OrderedDict[Tuple[str, str, str, str], TranslationResult] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._client = httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                )
            },
            follow_redirects=True,
        )

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def _cache_get(self, key: Tuple[str, str, str, str]) -> Optional[TranslationResult]:
        with self._lock:
            val = self._cache.get(key)
            if val is not None:
                self._cache.move_to_end(key)
                return TranslationResult(
                    translated_text=val.translated_text,
                    detected_lang=val.detected_lang,
                    provider=val.provider,
                    from_cache=True,
                )
        return None

    def _cache_put(self, key: Tuple[str, str, str, str], val: TranslationResult) -> None:
        with self._lock:
            self._cache[key] = val
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def translate(
        self,
        text: str,
        source_lang: str = "auto",
        target_lang: str = "vi",
        provider: str = "google",
        gemini_api_key: str = "",
        gemini_model: str = "gemini-2.5-flash",
    ) -> TranslationResult:
        res_list = self.translate_batch(
            texts=[text],
            source_lang=source_lang,
            target_lang=target_lang,
            provider=provider,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
        )
        return res_list[0]

    def translate_batch(
        self,
        texts: List[str],
        source_lang: str = "auto",
        target_lang: str = "vi",
        provider: str = "google",
        gemini_api_key: str = "",
        gemini_model: str = "gemini-2.5-flash",
    ) -> List[TranslationResult]:
        """Dịch danh sách khối văn bản nhanh trong 1 yêu cầu (giữ đúng thứ tự và cache từng khối)."""
        if not texts:
            return []

        src = _normalize_lang_code(source_lang)
        tgt = _normalize_lang_code(target_lang)
        effective_provider = "gemini" if (provider == "gemini" and gemini_api_key.strip()) else "google"

        results: List[Optional[TranslationResult]] = [None] * len(texts)
        pending_indices: List[int] = []
        pending_texts: List[str] = []

        for idx, raw in enumerate(texts):
            clean = (raw or "").strip()
            if not clean or _PURE_SYMBOL_RE.match(clean):
                results[idx] = TranslationResult(translated_text=clean, detected_lang=src, provider="noop")
                continue
            if src != "auto" and _same_language(src, tgt):
                results[idx] = TranslationResult(translated_text=clean, detected_lang=src, provider="noop")
                continue
            cached = self._cache_get((effective_provider, src, tgt, clean))
            if cached is not None:
                results[idx] = cached
            else:
                pending_indices.append(idx)
                pending_texts.append(clean)

        if not pending_texts:
            return [r for r in results if r is not None]

        # Nếu chọn Gemini AI
        if effective_provider == "gemini":
            all_ok = True
            for idx, orig in zip(pending_indices, pending_texts):
                try:
                    item = self._translate_gemini(orig, src, tgt, gemini_api_key.strip(), gemini_model)
                    self._cache_put((effective_provider, src, tgt, orig), item)
                    results[idx] = item
                except Exception:
                    all_ok = False
                    break
            if all_ok:
                return [r for r in results if r is not None]

        # Tầng 1: Google clients5 (hỗ trợ native batch nhiều tham số q -> siêu nhanh và chính xác từng đoạn!)
        if sum(len(t) for t in pending_texts) <= 4500:
            try:
                batch_items = self._translate_google_clients5(pending_texts, src, tgt)
                if len(batch_items) == len(pending_texts):
                    for idx, orig, item in zip(pending_indices, pending_texts, batch_items):
                        self._cache_put((effective_provider, src, tgt, orig), item)
                        results[idx] = item
                    return [r for r in results if r is not None]
            except Exception:
                pass

        # Tầng 2 & 3: Dịch từng đoạn qua clients5 -> gtx -> MyMemory
        for idx, orig in zip(pending_indices, pending_texts):
            if results[idx] is not None:
                continue
            item = self._translate_single_fallback_chain(orig, src, tgt)
            self._cache_put((effective_provider, src, tgt, orig), item)
            results[idx] = item

        return [r for r in results if r is not None]

    def _translate_single_fallback_chain(self, text: str, src: str, tgt: str) -> TranslationResult:
        try:
            items = self._translate_google_clients5([text], src, tgt)
            if items:
                return items[0]
        except Exception:
            pass

        try:
            return self._translate_google_gtx(text, src, tgt)
        except Exception:
            pass

        return self._translate_mymemory(text, src, tgt)

    def _translate_google_clients5(self, texts: List[str], src: str, tgt: str) -> List[TranslationResult]:
        params = [("client", "dict-chrome-ex"), ("sl", src), ("tl", tgt)]
        for t in texts:
            params.append(("q", t))
        resp = self._client.get("https://clients5.google.com/translate_a/t", params=params)
        resp.raise_for_status()
        data = resp.json()

        out: List[TranslationResult] = []
        if isinstance(data, list):
            for idx, entry in enumerate(data):
                orig = texts[idx] if idx < len(texts) else ""
                if isinstance(entry, list) and len(entry) >= 1:
                    trans = str(entry[0]).strip()
                    det = _normalize_lang_code(str(entry[1])) if len(entry) >= 2 and entry[1] else src
                elif isinstance(entry, str):
                    trans = entry.strip()
                    det = src
                else:
                    trans = orig
                    det = src
                out.append(
                    TranslationResult(
                        translated_text=trans or orig,
                        detected_lang=det,
                        provider="google",
                    )
                )
        return out

    def _translate_google_gtx(self, text: str, src: str, tgt: str) -> TranslationResult:
        resp = self._client.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": src,
                "tl": tgt,
                "dt": "t",
                "q": text,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        segments = data[0] if isinstance(data, list) and len(data) > 0 and data[0] else []
        translated = "".join(seg[0] for seg in segments if isinstance(seg, list) and seg and seg[0])
        detected = (
            _normalize_lang_code(str(data[2]))
            if isinstance(data, list) and len(data) > 2 and data[2]
            else src
        )
        return TranslationResult(
            translated_text=translated.strip() or text,
            detected_lang=detected,
            provider="google-gtx",
        )

    def _translate_mymemory(self, text: str, src: str, tgt: str) -> TranslationResult:
        mm_src = guess_script_lang(text) if src == "auto" else src
        if _same_language(mm_src, tgt):
            return TranslationResult(translated_text=text, detected_lang=mm_src, provider="noop")

        resp = self._client.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text[:480], "langpair": f"{mm_src}|{tgt}"},
        )
        resp.raise_for_status()
        data = resp.json()
        translated = data.get("responseData", {}).get("translatedText") or text
        return TranslationResult(
            translated_text=str(translated).strip(),
            detected_lang=mm_src,
            provider="mymemory",
        )

    def _translate_gemini(
        self, text: str, src: str, tgt: str, api_key: str, model: str
    ) -> TranslationResult:
        tgt_name = LANG_LABELS.get(tgt, tgt)
        src_hint = "auto-detect" if src == "auto" else LANG_LABELS.get(src, src)
        prompt = (
            f"Translate the following screen-captured text from {src_hint} to {tgt_name}. "
            "Keep the translation natural, concise, and faithful to the original meaning. "
            "Output ONLY the translated text without explanations or quotation marks.\n\n"
            f"{text}"
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        resp = self._client.post(
            url,
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1},
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        candidates = payload.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        translated = "".join(p.get("text", "") for p in parts).strip()
        if not translated:
            raise ValueError("Empty Gemini response")
        return TranslationResult(
            translated_text=translated,
            detected_lang=src,
            provider="gemini",
        )
