"""
Layout Analysis and Reading-Order Reconstruction Engine (Phần III - Mục 5, 6, 7).
Provides deterministic, coordinate-aware and rule-based layout reconstruction:
- 1-column, 2-column, 3-column, spanning block, and sidebar detection
- Duplicate text layer (shadow text) detection and deduplication
- Multi-page repeating header/footer & page number detection without losing unique edge content
- Borderless table detection from aligned text rows
- Intermediate DocumentBlock classification
100% Offline, Deterministic, Zero-LLM.
"""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from .schema import (
    BlockKind,
    DocumentBlock,
    PageContentState,
    PageLayout,
    ParseWarning,
    TableCellModel,
    TableModel,
    WarningSeverity,
)

# ============================================================================
# REGEX PATTERNS FOR BLOCK CLASSIFICATION & LAYOUT SIGNALS
# ============================================================================

RE_PAGE_NUM_STANDALONE = re.compile(
    r"^\s*(?:"
    r"trang\s+\d+(?:\s*/\s*\d+|\s+trên\s+\d+)?"
    r"|page\s+\d+(?:\s+of\s+\d+|\s*/\s*\d+)?"
    r"|-\s*\d+\s*-"
    r"|\[\s*\d+\s*\]"
    r")(?:[\s\-–—|]+mã\s*đề(?:\s*thi)?\s*[:.]?\s*\d{2,6})?\s*$",
    re.IGNORECASE,
)

RE_RUNNING_HEADER_FOOTER = re.compile(
    r"^\s*(?:"
    r"trang\s+\d+\s*/\s*\d+.*mã\s*đề\s*\d+"
    r"|mã\s*đề(?:\s*thi)?\s*[:.]?\s*\d+\s*[-–—|]\s*trang\s+\d+"
    r"|đề\s+thi\s+gồm\s+có\s+\d+\s+trang"
    r"|họ\s+và\s+tên\s+thí\s+sinh\s*:.*"
    r"|số\s+báo\s+danh\s*:.*"
    r")\s*$",
    re.IGNORECASE,
)

RE_SECTION_HEADING = re.compile(
    r"^\s*(?:"
    r"(?:phần|part|section|chương)\s+(?:[IVX]+|\d+|một|hai|ba|bốn|năm)\b"
    r"|[IVX]+\.\s+(?:trắc\s+nghiệm|tự\s+luận|reading|writing|listening|grammar|vocabulary|phonetics)"
    r")",
    re.IGNORECASE,
)

RE_ANSWER_KEY_HEADER = re.compile(
    r"^\s*(?:bảng\s+đáp\s+án|đáp\s+án\s+và\s+hướng\s+dẫn\s+chấm|hướng\s+dẫn\s+giải|answer\s+key|đáp\s+án\s+tham\s+khảo)\b",
    re.IGNORECASE,
)

RE_QUESTION_START = re.compile(
    r"^\s*(?:câu(?:\s+hỏi)?|question|bài(?:\s+tập)?|problem)\s+\d{1,4}\s*(?:[.:)/]|[-–—]|\(\d+(?:[.,]\d+)?\s*(?:đ|điểm|pts?|points?)\))",
    re.IGNORECASE,
)

RE_OPTION_START = re.compile(
    r"^\s*(?:\([A-Fa-f]\)|[A-Fa-f][.:)])\s+\S+",
)

RE_CAPTION_START = re.compile(
    r"^\s*(?:hình|figure|fig\.|bảng|table|biểu\s+đồ|sơ\s+đồ)\s+\d+(?:[.:]\d+)?\b",
    re.IGNORECASE,
)

RE_CONTEXT_PASSAGE_CUE = re.compile(
    r"(?:đọc\s+đoạn\s+văn|đọc\s+văn\s+bản|dựa\s+vào\s+thông\s+tin|dựa\s+vào\s+bảng\s+số\s+liệu|"
    r"cho\s+bảng\s+số\s+liệu|cho\s+hình\s+vẽ|read\s+the\s+following\s+passage|"
    r"use\s+the\s+following\s+information|questions?\s+\d+\s*(?:[-–—]|to)\s*\d+|"
    r"trả\s+lời\s+(?:các\s+)?câu\s+hỏi\s+từ\s+(?:câu\s+)?\d+\s+đến\s+(?:câu\s+)?\d+)",
    re.IGNORECASE,
)

RE_MATH_EXPRESSION = re.compile(
    r"(?:\\frac|\\sqrt|\\sum|\\int|\\lim|\\alpha|\\beta|\\gamma|\\Delta|\\pi|\\infty|"
    r"[∑∫√±≤≥≠≈≡∞∆∇∈∉⊂⊃∪∩⇒⇔→⇌↑↓]|"
    r"\b[a-zA-Z]\^\d+|\b[A-Z][a-z]?\d+\b.*(?:→|⇌)|"
    r"\b(?:sin|cos|tan|cot|log|ln)\s*\()"
)

RE_MCQ_OPTION_LINE = re.compile(
    r"(?:^|\s)(?:\([A-Fa-f]\)|[A-Fa-f][.:)])\s+.+(?:\s+(?:\([B-Fb-f]\)|[B-Fb-f][.:)])\s+)",
)


class LayoutAnalyzer:
    """
    Bộ phân tích bố cục trung gian và tái dựng thứ tự đọc (Phần III - Mục 5, 6, 7).
    Hoạt động hoàn toàn xác định dựa trên tọa độ bounding box, đặc trưng hình học và ngữ cảnh.
    """

    @staticmethod
    def contains_math_expression(text: str) -> bool:
        if not text:
            return False
        return bool(RE_MATH_EXPRESSION.search(text))

    @classmethod
    def classify_block_kind(
        cls,
        text: str,
        page_number: int = 1,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        page_width: float = 595.0,
        page_height: float = 842.0,
        style_meta: Optional[Dict[str, Any]] = None,
    ) -> BlockKind:
        """Phân loại block văn bản thành BlockKind xác định."""
        stripped = (text or "").strip()
        if not stripped:
            return BlockKind.PARAGRAPH

        first_line = stripped.splitlines()[0].strip()

        # 1. Kiểm tra số trang độc lập hoặc header/footer mẫu cố định
        if len(stripped) <= 90 and RE_PAGE_NUM_STANDALONE.match(stripped):
            return BlockKind.PAGE_NUMBER
        if len(stripped) <= 140 and RE_RUNNING_HEADER_FOOTER.match(stripped):
            if bbox and page_height > 0 and bbox[1] > page_height * 0.85:
                return BlockKind.FOOTER
            return BlockKind.HEADER

        # 2. Kiểm tra tiêu đề bảng đáp án
        if RE_ANSWER_KEY_HEADER.match(first_line):
            return BlockKind.ANSWER_KEY_BLOCK

        # 3. Kiểm tra tiêu đề phần (PHẦN I, PART 1...)
        if RE_SECTION_HEADING.match(first_line) and len(first_line) <= 140:
            return BlockKind.SECTION_HEADING

        # 4. Kiểm tra ngữ cảnh bài đọc / dữ liệu dùng chung
        if RE_CONTEXT_PASSAGE_CUE.search(first_line):
            return BlockKind.CONTEXT_PASSAGE

        # 5. Kiểm tra bắt đầu câu hỏi
        if RE_QUESTION_START.match(first_line):
            return BlockKind.QUESTION

        # 6. Kiểm tra dòng phương án A. B. C. D.
        if RE_OPTION_START.match(first_line) and len(stripped) < 600:
            return BlockKind.OPTION

        # 7. Kiểm tra chú thích hình/bảng (Caption)
        if RE_CAPTION_START.match(first_line) and len(stripped) <= 220:
            return BlockKind.CAPTION

        # 8. Kiểm tra tiêu đề lớn ở đầu trang 1
        if page_number == 1 and len(stripped) <= 250:
            is_top = (bbox is None) or (page_height > 0 and bbox[1] < page_height * 0.25)
            is_bold_or_upper = (
                stripped.isupper()
                or bool(style_meta and style_meta.get("is_heading"))
                or bool(re.search(r"(?i)\b(?:ĐỀ\s+THI|ĐỀ\s+KIỂM\s+TRA|KỲ\s+THI|BÀI\s+KIỂM\s+TRA)\b", stripped))
            )
            if is_top and is_bold_or_upper:
                return BlockKind.TITLE

        # 9. Kiểm tra công thức độc lập (ngắn và mật độ toán học cao)
        if len(stripped) <= 180 and cls.contains_math_expression(stripped):
            math_hits = len(RE_MATH_EXPRESSION.findall(stripped))
            if math_hits >= 2 and not RE_QUESTION_START.match(first_line):
                return BlockKind.FORMULA

        return BlockKind.PARAGRAPH

    @staticmethod
    def _bbox_iou(
        box_a: Tuple[float, float, float, float],
        box_b: Tuple[float, float, float, float],
    ) -> float:
        x0 = max(box_a[0], box_b[0])
        y0 = max(box_a[1], box_b[1])
        x1 = min(box_a[2], box_b[2])
        y1 = min(box_a[3], box_b[3])
        inter_w = max(0.0, x1 - x0)
        inter_h = max(0.0, y1 - y0)
        inter_area = inter_w * inter_h
        if inter_area <= 0.0:
            return 0.0
        area_a = max(1.0, (box_a[2] - box_a[0]) * (box_a[3] - box_a[1]))
        area_b = max(1.0, (box_b[2] - box_b[0]) * (box_b[3] - box_b[1]))
        return inter_area / min(area_a, area_b)

    @classmethod
    def detect_and_remove_duplicate_blocks(
        cls,
        raw_blocks: List[Tuple[float, float, float, float, str, int]],
        page_number: int,
    ) -> Tuple[List[Tuple[float, float, float, float, str, int]], int, List[ParseWarning]]:
        """
        Phát hiện và khử các lớp văn bản trùng lặp (shadow text / duplicate text layer) trên cùng một trang PDF.
        Trả về: (filtered_blocks, removed_count, warnings).
        """
        if len(raw_blocks) <= 1:
            return raw_blocks, 0, []

        kept: List[Tuple[float, float, float, float, str, int]] = []
        removed_count = 0
        warnings: List[ParseWarning] = []

        for candidate in raw_blocks:
            cx0, cy0, cx1, cy1, ctext, cbtype = candidate
            if cbtype != 0:
                kept.append(candidate)
                continue
            c_clean = re.sub(r"\s+", " ", (ctext or "").strip())
            if not c_clean:
                continue

            is_dup = False
            for existing in kept:
                ex0, ey0, ex1, ey1, etext, ebtype = existing
                if ebtype != 0:
                    continue
                # Kiểm tra khoảng cách tọa độ rất gần hoặc IoU lớn
                near_origin = abs(cx0 - ex0) <= 4.5 and abs(cy0 - ey0) <= 4.5
                iou = cls._bbox_iou((cx0, cy0, cx1, cy1), (ex0, ey0, ex1, ey1))
                if not near_origin and iou < 0.65:
                    continue

                e_clean = re.sub(r"\s+", " ", (etext or "").strip())
                if c_clean == e_clean:
                    is_dup = True
                    break
                if len(c_clean) >= 8 and len(e_clean) >= 8:
                    ratio = SequenceMatcher(None, c_clean, e_clean).ratio()
                    if ratio >= 0.88:
                        is_dup = True
                        break

            if is_dup:
                removed_count += 1
            else:
                kept.append(candidate)

        if removed_count > 0:
            warnings.append(
                ParseWarning(
                    code="DUPLICATE_TEXT_LAYER",
                    message=f"Trang {page_number} có {removed_count} block văn bản trùng lặp (duplicate/shadow text layer) đã được khử trùng.",
                    severity=WarningSeverity.INFO,
                    page=page_number,
                    reason="Phát hiện các block văn bản có tọa độ chồng lấp và nội dung giống nhau >= 88%.",
                    attempted_method="coordinate_iou_and_text_similarity_dedup",
                )
            )

        return kept, removed_count, warnings

    @classmethod
    def reconstruct_page_reading_order(
        cls,
        blocks: List[DocumentBlock],
        page_width: float,
        page_height: float,
    ) -> Tuple[List[DocumentBlock], int, bool]:
        """
        Tái dựng thứ tự đọc cho một trang tài liệu (Phần III - Mục 6):
        - Hỗ trợ bố cục 1 cột, 2 cột, 3 cột, khối tràn cột (spanning blocks) và cột phụ (sidebar).
        - Chia trang thành các dải ngang (horizontal bands) phân cách bởi các spanning blocks.
        - Trong mỗi dải nhiều cột: đọc cột trái từ trên xuống dưới -> cột giữa -> cột phải.
        Trả về: (sorted_blocks, detected_max_columns, has_sidebar)
        """
        if not blocks or page_width <= 0:
            return blocks, 1, False

        # Nếu các block không có bbox, giữ nguyên thứ tự gốc
        with_bbox = [b for b in blocks if b.bbox is not None]
        if len(with_bbox) < 2:
            for idx, b in enumerate(blocks):
                b.column_index = 0
                b.reading_order = idx + 1
            return blocks, 1, False

        # Sắp xếp sơ bộ theo y0 rồi x0
        prelim = sorted(
            blocks,
            key=lambda b: (round(b.bbox[1], 1) if b.bbox else 0.0, round(b.bbox[0], 1) if b.bbox else 0.0),
        )

        # Bước 1: Nhận diện các block tràn ngang (spanning blocks) và header/footer
        # Một block được coi là spanning nếu:
        # - Là HEADER / FOOTER / PAGE_NUMBER / TITLE / SECTION_HEADING rộng
        # - Hoặc chiều rộng > 58% chiều rộng trang
        # - Hoặc bắt đầu ở nửa trái (< 0.42 * W) và kết thúc ở nửa phải (> 0.58 * W) và có chiều rộng > 35% W
        def _is_spanning(b: DocumentBlock) -> bool:
            if b.bbox is None:
                return True
            if b.kind in (BlockKind.HEADER, BlockKind.FOOTER, BlockKind.PAGE_NUMBER, BlockKind.TITLE):
                return True
            x0, _, x1, _ = b.bbox
            bw = x1 - x0
            if bw >= page_width * 0.58:
                return True
            if x0 < page_width * 0.40 and x1 > page_width * 0.60 and bw >= page_width * 0.30:
                return True
            return False

        # Bước 2: Phân đoạn các block thành các dải (segments) xen kẽ giữa spanning block và vùng đa cột
        segments: List[Tuple[bool, List[DocumentBlock]]] = []
        current_non_spanning: List[DocumentBlock] = []

        for b in prelim:
            if _is_spanning(b):
                if current_non_spanning:
                    segments.append((False, current_non_spanning))
                    current_non_spanning = []
                b.column_index = 0
                segments.append((True, [b]))
            else:
                current_non_spanning.append(b)

        if current_non_spanning:
            segments.append((False, current_non_spanning))

        ordered_result: List[DocumentBlock] = []
        max_columns_detected = 1
        has_sidebar = False

        for is_span_seg, seg_blocks in segments:
            if is_span_seg or len(seg_blocks) < 2:
                for b in seg_blocks:
                    b.column_index = 0
                    ordered_result.append(b)
                continue

            # Phân tích cấu trúc cột trong dải seg_blocks
            sorted_cols, col_count, seg_sidebar = cls._sort_multicolumn_segment(
                seg_blocks, page_width
            )
            if col_count > max_columns_detected:
                max_columns_detected = col_count
            if seg_sidebar:
                has_sidebar = True
            ordered_result.extend(sorted_cols)

        for idx, b in enumerate(ordered_result):
            b.reading_order = idx + 1

        return ordered_result, max_columns_detected, has_sidebar

    @classmethod
    def _sort_multicolumn_segment(
        cls,
        seg_blocks: List[DocumentBlock],
        page_width: float,
    ) -> Tuple[List[DocumentBlock], int, bool]:
        """
        Phân tích một dải các block không tràn trang để phát hiện 1, 2 hoặc 3 cột (hoặc sidebar).
        """
        # Kiểm tra 3 cột trước: chia làm 3 miền [0, 0.35W], [0.32W, 0.68W], [0.65W, W]
        t1 = page_width / 3.0
        t2 = 2.0 * page_width / 3.0
        col3_left = [b for b in seg_blocks if b.bbox and b.bbox[2] <= t1 + page_width * 0.04]
        col3_mid = [
            b for b in seg_blocks
            if b.bbox and b.bbox[0] >= t1 - page_width * 0.04 and b.bbox[2] <= t2 + page_width * 0.04
        ]
        col3_right = [b for b in seg_blocks if b.bbox and b.bbox[0] >= t2 - page_width * 0.04]

        if (
            len(col3_left) >= 1
            and len(col3_mid) >= 1
            and len(col3_right) >= 1
            and len(col3_left) + len(col3_mid) + len(col3_right) == len(seg_blocks)
        ):
            # Kiểm tra thực sự có sự song song theo trục Y (ít nhất 2 cột có giao khoảng Y)
            y_ranges = [
                (min(b.bbox[1] for b in col), max(b.bbox[3] for b in col))
                for col in (col3_left, col3_mid, col3_right)
            ]
            overlap_12 = min(y_ranges[0][1], y_ranges[1][1]) - max(y_ranges[0][0], y_ranges[1][0])
            overlap_23 = min(y_ranges[1][1], y_ranges[2][1]) - max(y_ranges[1][0], y_ranges[2][0])
            if overlap_12 > -10 or overlap_23 > -10:
                col3_left.sort(key=lambda b: (round(b.bbox[1], 1), round(b.bbox[0], 1)))
                col3_mid.sort(key=lambda b: (round(b.bbox[1], 1), round(b.bbox[0], 1)))
                col3_right.sort(key=lambda b: (round(b.bbox[1], 1), round(b.bbox[0], 1)))
                for b in col3_left:
                    b.column_index = 1
                for b in col3_mid:
                    b.column_index = 2
                for b in col3_right:
                    b.column_index = 3
                return col3_left + col3_mid + col3_right, 3, False

        # Kiểm tra 2 cột (bao gồm cột cân đối quanh 0.5W hoặc sidebar lệch ở 0.25W / 0.75W)
        candidate_gutters = [
            page_width * 0.50,
            page_width * 0.28,
            page_width * 0.72,
        ]
        for gutter in candidate_gutters:
            tol = page_width * 0.03
            left_col = [b for b in seg_blocks if b.bbox and b.bbox[2] <= gutter + tol]
            right_col = [b for b in seg_blocks if b.bbox and b.bbox[0] >= gutter - tol]
            if (
                len(left_col) >= 1
                and len(right_col) >= 1
                and len(left_col) + len(right_col) == len(seg_blocks)
            ):
                # Đảm bảo không có block nào nằm ở cả 2 danh sách
                left_ids = {b.block_id for b in left_col}
                right_col = [b for b in right_col if b.block_id not in left_ids]
                if not left_col or not right_col:
                    continue

                left_col.sort(key=lambda b: (round(b.bbox[1], 1), round(b.bbox[0], 1)))
                right_col.sort(key=lambda b: (round(b.bbox[1], 1), round(b.bbox[0], 1)))

                is_sidebar = abs(gutter - page_width * 0.50) > page_width * 0.15
                for b in left_col:
                    b.column_index = 1
                    if is_sidebar and gutter < page_width * 0.35 and b.kind == BlockKind.PARAGRAPH:
                        b.kind = BlockKind.SIDEBAR
                for b in right_col:
                    b.column_index = 2
                    if is_sidebar and gutter > page_width * 0.65 and b.kind == BlockKind.PARAGRAPH:
                        b.kind = BlockKind.SIDEBAR
                return left_col + right_col, 2, is_sidebar

        # Mặc định 1 cột: sắp xếp từ trên xuống dưới, trái sang phải
        seg_sorted = sorted(
            seg_blocks,
            key=lambda b: (round(b.bbox[1], 1) if b.bbox else 0.0, round(b.bbox[0], 1) if b.bbox else 0.0),
        )
        for b in seg_sorted:
            b.column_index = 1
        return seg_sorted, 1, False

    @staticmethod
    def _normalize_header_footer_signature(text: str) -> str:
        """Chuẩn hóa chuỗi để so khớp header/footer lặp lại qua các trang (thay số bằng #)."""
        s = re.sub(r"\s+", " ", (text or "").strip().lower())
        s = re.sub(r"\d+", "#", s)
        return s

    @classmethod
    def detect_repeating_headers_footers(
        cls,
        blocks: List[DocumentBlock],
        pages: List[PageLayout],
    ) -> Tuple[List[str], List[str]]:
        """
        Nhận diện header, footer và số trang lặp lại qua nhiều trang (Phần III - Mục 7):
        - Không xóa mù quáng mọi dòng đầu/cuối trang nếu nội dung đó chỉ xuất hiện 1 lần và giống câu hỏi.
        - Trả về (unique_headers, unique_footers) và gắn nhãn BlockKind.HEADER / FOOTER / PAGE_NUMBER.
        """
        page_heights: Dict[int, float] = {p.page_number: p.height for p in pages}
        total_pages = len(pages)

        top_candidates: List[Tuple[DocumentBlock, str]] = []
        bottom_candidates: List[Tuple[DocumentBlock, str]] = []

        for b in blocks:
            txt = (b.text or "").strip()
            if not txt or len(txt) > 180:
                continue
            # Không bao giờ đánh dấu câu hỏi hoặc phương án là header/footer
            if RE_QUESTION_START.match(txt) or RE_OPTION_START.match(txt):
                continue

            ph = page_heights.get(b.page, 842.0) or 842.0
            sig = cls._normalize_header_footer_signature(txt)

            if b.kind in (BlockKind.HEADER, BlockKind.FOOTER, BlockKind.PAGE_NUMBER):
                if b.kind == BlockKind.HEADER:
                    top_candidates.append((b, sig))
                else:
                    bottom_candidates.append((b, sig))
                continue

            if b.bbox is not None and ph > 0:
                _, y0, _, y1 = b.bbox
                if y1 <= ph * 0.095:
                    top_candidates.append((b, sig))
                elif y0 >= ph * 0.905:
                    bottom_candidates.append((b, sig))

        # Đếm số trang xuất hiện của từng chữ ký (signature)
        top_sig_pages: Dict[str, set] = {}
        for b, sig in top_candidates:
            top_sig_pages.setdefault(sig, set()).add(b.page)

        bottom_sig_pages: Dict[str, set] = {}
        for b, sig in bottom_candidates:
            bottom_sig_pages.setdefault(sig, set()).add(b.page)

        headers_collected: List[str] = []
        footers_collected: List[str] = []

        min_repeat = 2 if total_pages >= 2 else 999

        for b, sig in top_candidates:
            if len(top_sig_pages.get(sig, set())) >= min_repeat or RE_RUNNING_HEADER_FOOTER.match(b.text):
                b.kind = BlockKind.HEADER
                if b.text not in headers_collected:
                    headers_collected.append(b.text)

        for b, sig in bottom_candidates:
            if RE_PAGE_NUM_STANDALONE.match(b.text):
                b.kind = BlockKind.PAGE_NUMBER
                if b.text not in footers_collected:
                    footers_collected.append(b.text)
            elif len(bottom_sig_pages.get(sig, set())) >= min_repeat or RE_RUNNING_HEADER_FOOTER.match(b.text):
                b.kind = BlockKind.FOOTER
                if b.text not in footers_collected:
                    footers_collected.append(b.text)

        return headers_collected, footers_collected

    @classmethod
    def detect_borderless_tables(
        cls,
        blocks: List[DocumentBlock],
        existing_table_count: int = 0,
    ) -> List[TableModel]:
        """
        Phát hiện các bảng không kẻ viền (borderless tables) được căn cột bằng dấu tab hoặc >= 3 khoảng trắng
        qua ít nhất 2 dòng liên tiếp (Phần V - Mục 17).
        Loại trừ các dòng phương án trắc nghiệm A. ... B. ... C. ... D. ...
        """
        detected_tables: List[TableModel] = []
        tbl_seq = existing_table_count

        for b in blocks:
            if b.kind in (BlockKind.TABLE, BlockKind.HEADER, BlockKind.FOOTER, BlockKind.OPTION):
                continue
            lines = [ln.strip() for ln in (b.raw_text or b.text or "").splitlines() if ln.strip()]
            if len(lines) < 2:
                continue

            candidate_rows: List[List[str]] = []
            for ln in lines:
                if RE_MCQ_OPTION_LINE.search(ln) or RE_QUESTION_START.match(ln):
                    continue
                if "\t" in ln:
                    parts = [p.strip() for p in ln.split("\t") if p.strip()]
                else:
                    parts = [p.strip() for p in re.split(r"\s{3,}", ln) if p.strip()]
                if len(parts) >= 2:
                    candidate_rows.append(parts)
                else:
                    if len(candidate_rows) >= 2:
                        break
                    candidate_rows = []

            if len(candidate_rows) >= 2:
                col_counts = Counter(len(r) for r in candidate_rows)
                dominant_cols, freq = col_counts.most_common(1)[0]
                if dominant_cols >= 2 and freq >= 2:
                    aligned_rows = [r for r in candidate_rows if len(r) == dominant_cols]
                    if len(aligned_rows) >= 2:
                        tbl_seq += 1
                        table_id = f"tbl_p{b.page:02d}_{tbl_seq:03d}"
                        cells: List[TableCellModel] = []
                        for r_idx, row_vals in enumerate(aligned_rows):
                            for c_idx, cell_val in enumerate(row_vals):
                                cells.append(
                                    TableCellModel(
                                        cell_id=f"{table_id}_r{r_idx}_c{c_idx}",
                                        row_index=r_idx,
                                        col_index=c_idx,
                                        raw_text=cell_val,
                                        text=cell_val,
                                        is_header=(r_idx == 0),
                                        contains_formula=cls.contains_math_expression(cell_val),
                                    )
                                )
                        md_lines = [
                            "| " + " | ".join(aligned_rows[0]) + " |",
                            "| " + " | ".join(["---"] * dominant_cols) + " |",
                        ]
                        for row_vals in aligned_rows[1:]:
                            md_lines.append("| " + " | ".join(row_vals) + " |")
                        detected_tables.append(
                            TableModel(
                                table_id=table_id,
                                page=b.page,
                                row_count=len(aligned_rows),
                                col_count=dominant_cols,
                                headers=aligned_rows[0],
                                cells=cells,
                                rows=aligned_rows,
                                markdown="\n".join(md_lines),
                                bbox=b.bbox,
                                is_borderless=True,
                                source_type="borderless_layout_table",
                            )
                        )
                        b.table_id = table_id

        return detected_tables

    @staticmethod
    def classify_page_state(
        native_char_count: int,
        ocr_char_count: int,
        image_count: int,
        rotation_deg: int,
        duplicate_blocks_removed: int,
        ocr_disabled_unprocessed_images: bool = False,
    ) -> PageContentState:
        """Phân loại trạng thái của từng trang PDF (Phần II - Mục 4)."""
        if rotation_deg in (90, 180, 270):
            return PageContentState.ROTATED_PAGE
        if duplicate_blocks_removed >= 2:
            return PageContentState.DUPLICATE_TEXT_LAYER
        if native_char_count < 20 and ocr_char_count == 0 and image_count == 0:
            return PageContentState.BLANK_PAGE
        if native_char_count < 35 and image_count > 0:
            if ocr_char_count > 0 and ocr_char_count < 40:
                return PageContentState.LOW_QUALITY_SCAN
            return PageContentState.SCANNED_IMAGE_ONLY
        if native_char_count >= 35 and (ocr_char_count > 20 or (image_count > 0 and ocr_disabled_unprocessed_images)):
            return PageContentState.HYBRID_TEXT_AND_SCAN
        return PageContentState.NATIVE_TEXT
