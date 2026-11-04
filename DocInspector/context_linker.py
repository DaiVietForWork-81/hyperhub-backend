"""
Shared Context and Question Group Linker (Phần IV - Mục 14, 15).
Detects and links:
- Reading comprehension passages ("Đọc đoạn văn sau và trả lời các câu hỏi từ 1 đến 5", "Read the following passage ... from 31 to 35")
- Shared data tables ("Dựa vào bảng số liệu sau, trả lời các câu 10 - 12")
- Shared figures/diagrams ("Cho hình vẽ sau, trả lời câu 4 và câu 5")
- Section groups (PHẦN I, PHẦN II, PHẦN III, I. TRẮC NGHIỆM, II. TỰ LUẬN)
Also detaches trailing shared passages that accidentally got appended to the end of the preceding question's block.
100% Deterministic, Rule-based, Zero-LLM.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .schema import (
    CanonicalQuestionType,
    DocumentBlock,
    ImageAsset,
    ParseWarning,
    QuestionGroup,
    SharedContext,
    SourceReference,
    StandardizedQuestion,
    TableModel,
    WarningSeverity,
)

# ============================================================================
# REGEX PATTERNS FOR SHARED CONTEXT & QUESTION RANGE DETECTION
# ============================================================================

# Mẫu nhận diện câu dẫn ngữ cảnh dùng chung kèm dải số thứ tự câu hỏi (ví dụ: từ câu 1 đến câu 5, questions 31 to 35)
RE_SHARED_CONTEXT_RANGE = re.compile(
    r"(?is)"
    r"(?:^|\n)\s*"
    r"(?P<cue>"
    r"(?:đọc\s+(?:đoạn\s+văn|văn\s+bản| ngữ\s+liệu|bài\s+đọc)|"
    r"dựa\s+vào\s+(?:thông\s+tin|đoạn\s+tư\s+liệu|bảng\s+số\s+liệu|hình\s+vẽ|biểu\s+đồ|sơ\s+đồ)|"
    r"cho\s+(?:thông\s+tin|đoạn\s+tư\s+liệu|bảng\s+số\s+liệu|hình\s+vẽ|biểu\s+đồ)|"
    r"read\s+the\s+following\s+(?:passage|text|extract|article)|"
    r"use\s+the\s+following\s+(?:information|table|graph|diagram)|"
    r"questions?\s+(?P<q_start_en>\d{1,3})\s*(?:[-–—]|to|through)\s*(?P<q_end_en>\d{1,3})\s+refer\s+to)"
    r"[^\n]{0,220}?"
    r"(?:"
    r"(?:từ\s+(?:câu\s+)?|câu\s+(?:hỏi\s+)?|from\s+(?:question\s+)?|questions?\s+)"
    r"(?P<q_start>\d{1,3})\s*(?:[-–—]|đến(?:\s+câu)?|to|through|và)\s*(?P<q_end>\d{1,3})"
    r")?"
    r"[^\n]*)"
    r"(?P<body>.+)$"
)

# Mẫu dải câu hỏi rời rạc: "trả lời các câu hỏi 1, 2, 3" hoặc "câu 4 và câu 5"
RE_EXPLICIT_Q_NUMBERS = re.compile(
    r"(?i)(?:từ\s+(?:câu\s+)?|các\s+câu(?:\s+hỏi)?\s+|câu(?:\s+hỏi)?\s+|questions?\s+|from\s+)"
    r"(\d{1,3})\s*(?:[-–—]|đến(?:\s+câu)?|to|through|và|and|,)\s*(?:câu\s+)?(\d{1,3})(?:\s*(?:,|và|and)\s*(?:câu\s+)?(\d{1,3}))?"
)

RE_SECTION_LINE = re.compile(
    r"(?im)^\s*(?P<marker>"
    r"phần\s+(?:[IVX]+|\d+|một|hai|ba|bốn)"
    r"|part\s+(?:[IVX]+|\d+)"
    r"|[IVX]+\.\s*(?:phần\s+)?(?:trắc\s+nghiệm|tự\s+luận|reading|writing|grammar|vocabulary)"
    r")\s*(?:[:.\-–—]\s*(?P<title>[^\n]+))?$"
)


class ContextLinker:
    """Bộ liên kết ngữ cảnh dùng chung (SharedContext) và nhóm câu hỏi (QuestionGroup)."""

    @classmethod
    def extract_and_link_contexts(
        cls,
        full_text: str,
        questions: List[StandardizedQuestion],
        blocks: List[DocumentBlock],
        tables: List[TableModel],
        images: List[ImageAsset],
        file_name: str = "document",
    ) -> Tuple[List[SharedContext], List[QuestionGroup], List[ParseWarning]]:
        """
        1. Tách các đoạn ngữ cảnh dùng chung (bài đọc, bảng số liệu, hình vẽ) bị dính vào cuối câu hỏi phía trước
           hoặc nằm ở phần mở đầu trước câu hỏi đầu tiên của nhóm.
        2. Tạo SharedContext (context_id) và QuestionGroup (group_id).
        3. Gắn context_id, group_id và assets (table_id, image_id) cho từng câu hỏi thuộc phạm vi.
        """
        contexts: List[SharedContext] = []
        groups: List[QuestionGroup] = []
        warnings: List[ParseWarning] = []

        if not questions:
            return contexts, groups, warnings

        q_by_num: Dict[int, StandardizedQuestion] = {q.number: q for q in questions}
        ctx_seq = 0

        # Bước 1: Kiểm tra đoạn văn bản nằm TRƯỚC câu hỏi đầu tiên trong full_text
        first_q = questions[0]
        first_q_pos = full_text.find(first_q.raw_text[: min(40, len(first_q.raw_text))]) if first_q.raw_text else -1
        if first_q_pos > 20:
            preamble = full_text[:first_q_pos].strip()
            ctx_obj = cls._try_parse_shared_context_block(
                preamble,
                next_question_number=first_q.number,
                ctx_seq=ctx_seq + 1,
                file_name=file_name,
            )
            if ctx_obj is not None:
                ctx_seq += 1
                contexts.append(ctx_obj)

        # Bước 2: Kiểm tra đuôi của từng câu hỏi xem có chứa đoạn ngữ cảnh dùng chung cho các câu tiếp theo không
        for idx, q in enumerate(questions):
            next_q_num = questions[idx + 1].number if idx + 1 < len(questions) else (q.number + 1)

            # Kiểm tra trong stem hoặc trong option cuối cùng của câu hỏi hiện tại
            if q.options:
                last_opt = q.options[-1]
                detached_opt_text, ctx_obj = cls._detach_trailing_context(
                    last_opt.text, next_q_num, ctx_seq + 1, file_name
                )
                if ctx_obj is not None:
                    ctx_seq += 1
                    last_opt.text = detached_opt_text.strip()
                    last_opt.raw_text = detached_opt_text.strip()
                    # Cập nhật lại q.raw_text
                    pos = q.raw_text.find(ctx_obj.instructions or ctx_obj.raw_text[:30])
                    if pos > 0:
                        q.raw_text = q.raw_text[:pos].strip()
                    contexts.append(ctx_obj)
                    continue

            detached_stem, ctx_obj = cls._detach_trailing_context(
                q.stem, next_q_num, ctx_seq + 1, file_name
            )
            if ctx_obj is not None:
                ctx_seq += 1
                q.stem = detached_stem.strip()
                pos = q.raw_text.find(ctx_obj.instructions or ctx_obj.raw_text[:30])
                if pos > 0:
                    q.raw_text = q.raw_text[:pos].strip()
                contexts.append(ctx_obj)

        # Bước 3: Liên kết mỗi SharedContext tới các câu hỏi mục tiêu và tạo QuestionGroup tương ứng
        for ctx in contexts:
            grp = QuestionGroup(
                group_id=ctx.group_id,
                title=ctx.instructions or f"Nhóm câu hỏi {ctx.context_id}",
                instructions=ctx.instructions,
                context_id=ctx.context_id,
            )
            linked_any = False
            for q_num in ctx.target_question_numbers:
                target_q = q_by_num.get(q_num)
                if target_q is not None:
                    target_q.context_id = ctx.context_id
                    target_q.group_id = ctx.group_id
                    if ctx.kind == "reading_passage" and target_q.type in (
                        CanonicalQuestionType.SINGLE_CHOICE,
                        CanonicalQuestionType.CHOICE_UNKNOWN,
                    ):
                        # Giữ thông tin bài đọc liên kết trong tín hiệu confidence
                        target_q.confidence.signals.append(f"linked_to_{ctx.context_id}")
                    grp.question_ids.append(target_q.id)
                    linked_any = True

            if not linked_any:
                warnings.append(
                    ParseWarning(
                        code="ORPHAN_SHARED_CONTEXT",
                        message=f"Phát hiện ngữ cảnh chung '{ctx.context_id}' (câu {ctx.target_question_numbers}) nhưng không tìm thấy câu hỏi khớp số thứ tự.",
                        severity=WarningSeverity.WARNING,
                        reason="Các câu hỏi mục tiêu có thể bị khuyết hoặc đánh số khác dải dự kiến.",
                        requires_manual_review=True,
                    )
                )
            groups.append(grp)

        # Bước 4: Tạo thêm các QuestionGroup theo Phần (PHẦN I, PHẦN II, PHẦN III) nếu có trong văn bản
        section_groups = cls._extract_section_groups(full_text, questions)
        for sg in section_groups:
            groups.append(sg)
            for q_id in sg.question_ids:
                for q in questions:
                    if q.id == q_id and not q.group_id:
                        q.group_id = sg.group_id

        # Bước 5: Liên kết Bảng (TableModel) và Hình ảnh (ImageAsset) vào SharedContext / Question cùng trang
        cls._link_tables_and_images(questions, contexts, tables, images)

        return contexts, groups, warnings

    @classmethod
    def _detach_trailing_context(
        cls,
        text_segment: str,
        next_question_number: int,
        ctx_seq: int,
        file_name: str,
    ) -> Tuple[str, Optional[SharedContext]]:
        """
        Kiểm tra xem ở cuối một đoạn text (stem hoặc option D của câu trước) có dính đoạn văn/dữ liệu chung
        cho các câu hỏi tiếp theo hay không. Nếu có, tách rời và trả về (clean_text, SharedContext).
        """
        if not text_segment or len(text_segment) < 40:
            return text_segment, None

        lines = text_segment.split("\n")
        if len(lines) < 2:
            return text_segment, None

        # Tìm dòng đầu tiên có chứa tín hiệu dẫn nhập bài đọc / dữ liệu chung + dải câu hỏi
        for line_idx in range(1, len(lines)):
            candidate_tail = "\n".join(lines[line_idx:]).strip()
            first_tail_line = lines[line_idx].strip()
            if not first_tail_line:
                continue
            if re.search(
                r"(?i)^(?:đọc\s+(?:đoạn\s+văn|văn\s+bản|bài\s+đọc)|"
                r"dựa\s+vào\s+(?:thông\s+tin|bảng\s+số\s+liệu|hình\s+vẽ|đoạn\s+tư\s+liệu)|"
                r"cho\s+(?:thông\s+tin|bảng\s+số\s+liệu|hình\s+vẽ|đoạn\s+tư\s+liệu)|"
                r"read\s+the\s+following\s+(?:passage|text|extract)|"
                r"questions?\s+\d+\s*(?:[-–—]|to)\s*\d+\s+refer\s+to)",
                first_tail_line,
            ):
                ctx = cls._try_parse_shared_context_block(
                    candidate_tail,
                    next_question_number=next_question_number,
                    ctx_seq=ctx_seq,
                    file_name=file_name,
                )
                if ctx is not None:
                    clean_head = "\n".join(lines[:line_idx]).strip()
                    return clean_head, ctx

        return text_segment, None

    @classmethod
    def _try_parse_shared_context_block(
        cls,
        block_text: str,
        next_question_number: int,
        ctx_seq: int,
        file_name: str,
    ) -> Optional[SharedContext]:
        """Phân tích một khối văn bản ứng viên thành SharedContext nếu có tín hiệu xác định."""
        if not block_text or len(block_text.strip()) < 25:
            return None

        m = RE_SHARED_CONTEXT_RANGE.search(block_text)
        if not m:
            return None

        cue_line = (m.group("cue") or "").strip()
        body_text = (m.group("body") or "").strip()

        # Xác định dải câu hỏi mục tiêu
        q_start: Optional[int] = None
        q_end: Optional[int] = None

        if m.group("q_start") and m.group("q_end"):
            q_start = int(m.group("q_start"))
            q_end = int(m.group("q_end"))
        elif m.group("q_start_en") and m.group("q_end_en"):
            q_start = int(m.group("q_start_en"))
            q_end = int(m.group("q_end_en"))
        else:
            range_m = RE_EXPLICIT_Q_NUMBERS.search(cue_line)
            if range_m:
                q_start = int(range_m.group(1))
                q_end = int(range_m.group(3) or range_m.group(2))

        if q_start is not None and q_end is not None and q_end >= q_start and (q_end - q_start) <= 25:
            target_nums = list(range(q_start, q_end + 1))
            q_range: Optional[Tuple[int, int]] = (q_start, q_end)
        else:
            # Nếu không ghi rõ số câu kết thúc, liên kết mặc định tới câu hỏi kế tiếp
            target_nums = [next_question_number]
            q_range = (next_question_number, next_question_number)

        cue_lower = cue_line.lower()
        if any(w in cue_lower for w in ("bảng số liệu", "bảng sau", "table")):
            kind = "shared_table"
        elif any(w in cue_lower for w in ("hình vẽ", "biểu đồ", "sơ đồ", "figure", "graph", "diagram")):
            kind = "shared_figure"
        else:
            kind = "reading_passage"

        ctx_id = f"ctx_{ctx_seq:03d}"
        grp_id = f"grp_{ctx_id}"
        full_ctx_text = (cue_line + "\n" + body_text).strip() if body_text else cue_line

        return SharedContext(
            context_id=ctx_id,
            group_id=grp_id,
            kind=kind,
            raw_text=full_ctx_text,
            text=body_text if body_text else full_ctx_text,
            instructions=cue_line,
            question_range=q_range,
            target_question_numbers=target_nums,
            source_refs=[
                SourceReference(
                    file_name=file_name,
                    page=1,
                    extraction_method="context_range_linker",
                )
            ],
        )

    @classmethod
    def _extract_section_groups(
        cls,
        full_text: str,
        questions: List[StandardizedQuestion],
    ) -> List[QuestionGroup]:
        """Tạo danh sách QuestionGroup từ các tiêu đề PHẦN I, PHẦN II, PHẦN III trong tài liệu."""
        matches = list(RE_SECTION_LINE.finditer(full_text))
        if not matches:
            return []

        sec_groups: List[QuestionGroup] = []
        for idx, m in enumerate(matches):
            sec_start = m.start()
            sec_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(full_text)
            marker = (m.group("marker") or "").strip()
            title = (m.group("title") or "").strip()
            full_title = f"{marker}: {title}" if title else marker
            grp_id = f"sec_{idx + 1:02d}"
            grp = QuestionGroup(
                group_id=grp_id,
                title=full_title,
                section_marker=marker,
            )
            sec_slice = full_text[sec_start:sec_end]
            for q in questions:
                probe = q.raw_text[: min(35, len(q.raw_text))] if q.raw_text else q.label
                if probe and probe in sec_slice:
                    grp.question_ids.append(q.id)
            if grp.question_ids:
                sec_groups.append(grp)

        return sec_groups

    @staticmethod
    def _link_tables_and_images(
        questions: List[StandardizedQuestion],
        contexts: List[SharedContext],
        tables: List[TableModel],
        images: List[ImageAsset],
    ) -> None:
        """Gắn ID bảng (table_id) và hình ảnh (image_id) vào câu hỏi hoặc ngữ cảnh tương ứng."""
        # Liên kết bảng vào câu hỏi nếu markdown của bảng nằm trong raw_text hoặc cùng trang và câu hỏi nhắc đến "bảng"
        for tbl in tables:
            linked = False
            first_row_probe = " | ".join(tbl.headers[:2]).strip() if tbl.headers else ""
            for ctx in contexts:
                if (first_row_probe and first_row_probe in ctx.raw_text) or ctx.kind == "shared_table":
                    if tbl.table_id not in ctx.table_ids:
                        ctx.table_ids.append(tbl.table_id)
                        linked = True
            for q in questions:
                if (first_row_probe and first_row_probe in q.raw_text) or (
                    re.search(r"(?i)\b(?:bảng\s+số\s+liệu|bảng\s+bên|bảng\s+dưới|table)\b", q.stem)
                    and any(sr.page == tbl.page for sr in q.source_refs if sr.page)
                ):
                    if tbl.table_id not in q.assets:
                        q.assets.append(tbl.table_id)
                        linked = True
            if not linked and questions:
                # Nếu câu hỏi cùng trang có loại TABLE_COMPLETION
                for q in questions:
                    if q.type == CanonicalQuestionType.TABLE_COMPLETION and tbl.table_id not in q.assets:
                        q.assets.append(tbl.table_id)

        # Liên kết hình ảnh vào câu hỏi nhắc tới "hình vẽ", "sơ đồ", "đồ thị" trên cùng trang
        for img in images:
            for ctx in contexts:
                if ctx.kind == "shared_figure" and img.image_id not in ctx.image_ids:
                    ctx.image_ids.append(img.image_id)
            for q in questions:
                same_page = any(sr.page == img.page for sr in q.source_refs if sr.page) or img.page == 1
                if same_page and re.search(
                    r"(?i)\b(?:hình\s+vẽ|hình\s+bên|hình\s+\d+|đồ\s+thị|sơ\s+đồ|biểu\s+đồ|figure|diagram|graph)\b",
                    q.stem,
                ):
                    if img.image_id not in q.assets:
                        q.assets.append(img.image_id)
