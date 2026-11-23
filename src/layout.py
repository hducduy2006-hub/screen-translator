"""Nhóm các dòng chữ OCR thành đoạn văn (paragraph) tự nhiên để dịch mượt mà và định vị overlay chính xác."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import List, Tuple

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


@dataclass
class TextLine:
    """Một dòng chữ nhận diện được từ OCR (tọa độ tương đối so với vùng chụp, đơn vị pixel logic)."""

    x1: float
    y1: float
    x2: float
    y2: float
    text: str
    confidence: float = 1.0

    @property
    def width(self) -> float:
        return max(1.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(1.0, self.y2 - self.y1)

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) * 0.5

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) * 0.5


@dataclass
class TextBlock:
    """Một khối/đoạn văn bản (gồm 1 hoặc nhiều TextLine đã gộp) sẵn sàng để dịch và hiển thị overlay."""

    x1: float
    y1: float
    x2: float
    y2: float
    original_text: str
    translated_text: str = ""
    detected_lang: str = ""
    confidence: float = 1.0
    lines: List[TextLine] = field(default_factory=list)

    @property
    def width(self) -> float:
        return max(1.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(1.0, self.y2 - self.y1)

    @property
    def avg_line_height(self) -> float:
        if not self.lines:
            return self.height
        return sum(ln.height for ln in self.lines) / len(self.lines)


def _join_line_texts(texts: List[str]) -> str:
    """Ghép các dòng trong cùng đoạn: không thêm khoảng trắng thừa giữa chữ Hán, nối từ có dấu gạch ngang."""
    if not texts:
        return ""
    result = texts[0].strip()
    for nxt in texts[1:]:
        nxt = nxt.strip()
        if not nxt:
            continue
        if not result:
            result = nxt
            continue
        # Xử lý nối từ tiếng Anh cuối dòng có dấu '-'
        if result.endswith("-") and not result.endswith(" -") and nxt[0].isascii() and nxt[0].isalpha():
            result = result[:-1] + nxt
        elif contains_cjk(result[-1]) and contains_cjk(nxt[0]):
            result = result + nxt
        else:
            result = result + " " + nxt
    return result


def _horizontal_overlap_ratio(a_x1: float, a_x2: float, b_x1: float, b_x2: float) -> float:
    inter = max(0.0, min(a_x2, b_x2) - max(a_x1, b_x1))
    min_w = max(1.0, min(a_x2 - a_x1, b_x2 - b_x1))
    return inter / min_w


def _merge_same_row_lines(lines: List[TextLine]) -> List[TextLine]:
    """Gộp các mảnh chữ nằm trên CÙNG một dòng ngang và sát nhau (do detector tách rời dấu câu/từ)."""
    if len(lines) <= 1:
        return list(lines)

    ordered = sorted(lines, key=lambda l: (l.y1, l.x1))
    merged: List[TextLine] = []

    for ln in ordered:
        attached = False
        for idx, prev in enumerate(merged):
            # Kiểm tra chồng lấn theo chiều dọc >= 55%
            v_inter = max(0.0, min(prev.y2, ln.y2) - max(prev.y1, ln.y1))
            v_ratio = v_inter / max(1.0, min(prev.height, ln.height))
            if v_ratio < 0.55:
                continue

            # Khoảng cách ngang nhỏ (<= 1.6x chiều cao chữ) -> cùng một dòng!
            avg_h = 0.5 * (prev.height + ln.height)
            if prev.x1 <= ln.x1:
                left, right = prev, ln
            else:
                left, right = ln, prev
            h_gap = right.x1 - left.x2
            if -avg_h * 0.4 <= h_gap <= avg_h * 1.6:
                sep = "" if (contains_cjk(left.text[-1:]) and contains_cjk(right.text[:1])) else " "
                combined_text = (left.text.rstrip() + sep + right.text.lstrip()).strip()
                merged[idx] = TextLine(
                    x1=min(left.x1, right.x1),
                    y1=min(left.y1, right.y1),
                    x2=max(left.x2, right.x2),
                    y2=max(left.y2, right.y2),
                    text=combined_text,
                    confidence=0.5 * (left.confidence + right.confidence),
                )
                attached = True
                break
        if not attached:
            merged.append(ln)
    return merged


def group_lines_to_blocks(lines: List[TextLine], merge_paragraphs: bool = True) -> List[TextBlock]:
    """
    Nhóm danh sách TextLine thành danh sách TextBlock theo trật tự đọc tự nhiên.
    Khi merge_paragraphs=False: giữ nguyên từng dòng (phù hợp với menu/bảng biểu/nút bấm).
    Khi merge_paragraphs=True: gộp các dòng liền kề cùng đoạn thành 1 khối để dịch tự nhiên.
    """
    clean_lines = [ln for ln in lines if ln.text and ln.text.strip()]
    if not clean_lines:
        return []

    row_lines = _merge_same_row_lines(clean_lines)
    # Sắp xếp từ trên xuống, trái sang phải
    row_lines.sort(key=lambda l: (round(l.y1 / max(6.0, l.height * 0.5)), l.x1))

    if not merge_paragraphs:
        return [
            TextBlock(
                x1=ln.x1,
                y1=ln.y1,
                x2=ln.x2,
                y2=ln.y2,
                original_text=ln.text.strip(),
                confidence=ln.confidence,
                lines=[ln],
            )
            for ln in row_lines
        ]

    clusters: List[List[TextLine]] = []
    for ln in row_lines:
        best_cluster_idx = -1
        best_vgap = float("inf")

        for idx, cluster in enumerate(clusters):
            last = cluster[-1]
            avg_h = sum(c.height for c in cluster) / len(cluster)

            # Chiều cao font phải tương đồng (tránh gộp tiêu đề lớn vào đoạn văn nhỏ)
            h_ratio = ln.height / max(1.0, avg_h)
            if not (0.62 <= h_ratio <= 1.58):
                continue

            # Khoảng cách dọc giữa đáy dòng trước và đỉnh dòng mới
            v_gap = ln.y1 - last.y2
            if v_gap < -avg_h * 0.35 or v_gap > avg_h * 0.95:
                continue

            # Kiểm tra độ thẳng hàng / chồng lấn theo chiều ngang với khối
            cl_x1 = min(c.x1 for c in cluster)
            cl_x2 = max(c.x2 for c in cluster)
            h_overlap = _horizontal_overlap_ratio(cl_x1, cl_x2, ln.x1, ln.x2)
            left_aligned = abs(ln.x1 - cl_x1) <= avg_h * 2.2
            center_aligned = abs(ln.cx - 0.5 * (cl_x1 + cl_x2)) <= avg_h * 2.2

            if h_overlap >= 0.25 or left_aligned or center_aligned:
                if v_gap < best_vgap:
                    best_vgap = v_gap
                    best_cluster_idx = idx

        if best_cluster_idx >= 0:
            clusters[best_cluster_idx].append(ln)
        else:
            clusters.append([ln])

    blocks: List[TextBlock] = []
    for cl in clusters:
        cl.sort(key=lambda l: (l.y1, l.x1))
        text = _join_line_texts([l.text for l in cl])
        if not text:
            continue
        blocks.append(
            TextBlock(
                x1=min(l.x1 for l in cl),
                y1=min(l.y1 for l in cl),
                x2=max(l.x2 for l in cl),
                y2=max(l.y2 for l in cl),
                original_text=text,
                confidence=sum(l.confidence for l in cl) / len(cl),
                lines=cl,
            )
        )

    blocks.sort(key=lambda b: (b.y1, b.x1))
    return blocks
