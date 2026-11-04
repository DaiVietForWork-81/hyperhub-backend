"""
Independent 18-Point Structural Validator, Multi-Dimensional Confidence Scorer,
Targeted Recovery Stage, 7-Stage Pipeline Orchestrator, and Evaluation Metrics (Phần IX, X, XIII).
100% Deterministic, Offline, Zero-LLM.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import OCRMode, get_config
from .context_linker import ContextLinker
from .question_parser import QuestionParser
from .readers import DocumentReaderRegistry, ReaderOptions, ReaderOutput
from .schema import (
    BlockKind,
    CanonicalQuestionType,
    DocumentConfidenceSummary,
    OptionItem,
    PageContentState,
    ParseError,
    ParseWarning,
    SourceReference,
    StandardizedDocument,
    StandardizedQuestion,
    WarningSeverity,
)


# ============================================================================
# TARGETED RECOVERY STAGE (Phần X - Mục 29 & 30: Stage 6 Recovery)
# ============================================================================

class TargetedQuestionRecovery:
    """
    Khôi phục cục bộ cho từng vùng/câu hỏi gặp lỗi mà KHÔNG xóa câu hỏi không hợp lệ:
    1. Nếu một phương án (Option D) nuốt nhầm câu hỏi kế tiếp do thiếu dấu xuống dòng, tách câu hỏi bị nuốt ra.
    2. Nếu câu hỏi trắc nghiệm bị thiếu phương án do ký hiệu ngăn cách đặc biệt (ví dụ A - ... B - ...),
       chạy parser phương án thứ cấp trên stem của câu hỏi đó.
    """

    RE_SWALLOWED_QUESTION = re.compile(
        r"(?is)^(?P<opt_head>.+?)\n+\s*(?P<next_q>(?:câu(?:\s+hỏi)?|question|bài)\s+(?P<q_num>\d{1,3})\s*[.:)]\s+.+)$"
    )
    RE_DASH_OPTION_FALLBACK = re.compile(
        r"(?:^|\n|\s{2,})([A-D])\s*[-–—]\s+(.+?)(?=(?:\s{2,}[A-D]\s*[-–—]\s+)|(?:\n\s*[A-D]\s*[-–—]\s+)|\Z)",
        re.DOTALL,
    )

    @classmethod
    def run_targeted_recovery(
        cls,
        questions: List[StandardizedQuestion],
        file_name: str = "document",
    ) -> Tuple[List[StandardizedQuestion], List[ParseWarning]]:
        recovered_list: List[StandardizedQuestion] = []
        warnings: List[ParseWarning] = []

        for q in questions:
            # Recovery 1: Kiểm tra xem phương án cuối cùng có nuốt nhầm một câu hỏi kế tiếp không
            if q.options:
                last_opt = q.options[-1]
                m_swal = cls.RE_SWALLOWED_QUESTION.match(last_opt.text)
                if m_swal:
                    clean_opt_txt = m_swal.group("opt_head").strip()
                    swallowed_chunk = m_swal.group("next_q").strip()
                    swallowed_num = int(m_swal.group("q_num"))
                    last_opt.text = clean_opt_txt
                    last_opt.raw_text = clean_opt_txt

                    recovered_list.append(q)
                    sub_stds, _, _, sub_warns = QuestionParser.parse_standardized_questions(
                        swallowed_chunk, file_name=file_name
                    )
                    if sub_stds:
                        for sq in sub_stds:
                            sq.id = f"q_rec_{swallowed_num:03d}"
                            sq.confidence.signals.append("recovered_from_previous_option")
                            recovered_list.append(sq)
                        warnings.append(
                            ParseWarning(
                                code="RECOVERED_SWALLOWED_QUESTION",
                                message=f"Đã tách và khôi phục Câu {swallowed_num} bị dính vào phương án {last_opt.marker} của {q.label}.",
                                severity=WarningSeverity.INFO,
                                question_id=q.id,
                                attempted_method="option_tail_boundary_split",
                            )
                        )
                        warnings.extend(sub_warns)
                        continue

            # Recovery 2: Nếu câu hỏi thuộc loại CHOICE_UNKNOWN hoặc thiếu phương án, thử tìm mẫu A - ... B - ...
            if not q.options and q.type in (
                CanonicalQuestionType.CHOICE_UNKNOWN,
                CanonicalQuestionType.ESSAY,
            ):
                dash_matches = list(cls.RE_DASH_OPTION_FALLBACK.finditer(q.stem))
                if len(dash_matches) >= 3 and dash_matches[0].group(1).upper() == "A":
                    first_st = dash_matches[0].start()
                    if first_st > 8:
                        new_opts: List[OptionItem] = []
                        for dm in dash_matches:
                            ltr = dm.group(1).upper()
                            otxt = dm.group(2).strip()
                            new_opts.append(
                                OptionItem(
                                    marker=ltr,
                                    raw_text=otxt,
                                    text=otxt,
                                    source_ref=SourceReference(
                                        file_name=file_name,
                                        extraction_method="dash_option_fallback",
                                    ),
                                )
                            )
                        q.stem = q.stem[:first_st].strip()
                        q.options = new_opts
                        q.type = CanonicalQuestionType.SINGLE_CHOICE
                        q.confidence.option_parsing = 0.82
                        q.confidence.signals.append("recovered_dash_options")
                        q.status = "parsed"
                        warnings.append(
                            ParseWarning(
                                code="RECOVERED_DASH_OPTIONS",
                                message=f"Đã khôi phục {len(new_opts)} phương án dạng gạch ngang (A - ...) cho {q.label}.",
                                severity=WarningSeverity.INFO,
                                question_id=q.id,
                                attempted_method="dash_option_fallback",
                            )
                        )

            recovered_list.append(q)

        # Đánh lại id tuần tự nếu có câu hỏi mới được tách ra
        for idx, q in enumerate(recovered_list):
            q.id = f"q_{idx + 1:03d}"

        return recovered_list, warnings


# ============================================================================
# INDEPENDENT 18-POINT STRUCTURAL VALIDATOR (Phần IX - Mục 27 & 28)
# ============================================================================

class StructuralValidator:
    """
    Bộ kiểm định cấu trúc độc lập với parser (Phần IX - Mục 28):
    Kiểm tra đủ 18 điều kiện bất biến (invariants) trên StandardizedDocument,
    cập nhật danh sách questions_needing_review và tính bảng điểm DocumentConfidenceSummary.
    Không bao giờ tự động xóa câu hỏi lỗi; luôn giữ lại với status='needs_review'.
    """

    @classmethod
    def validate_document(cls, doc: StandardizedDocument) -> bool:
        """
        Thực thi 18 kiểm tra cấu trúc trên StandardizedDocument.
        Trả về True nếu không có lỗi nghiêm trọng (ParseError không thể phục hồi).
        """
        new_warnings: List[ParseWarning] = []
        existing_codes_per_q: Set[Tuple[Optional[str], str]] = {
            (w.question_id, w.code) for w in doc.warnings
        }

        def _add_warn(w: ParseWarning, target_q: Optional[StandardizedQuestion] = None) -> None:
            key = (w.question_id, w.code)
            if key not in existing_codes_per_q:
                existing_codes_per_q.add(key)
                new_warnings.append(w)
                if target_q is not None:
                    target_q.warnings.append(w)

        # Kiểm tra 1: Tài liệu có văn bản trích xuất hoặc block hợp lệ không?
        has_any_text = bool(doc.normalized_text.strip()) or any(b.text.strip() for b in doc.blocks)
        if not has_any_text and not doc.images:
            _add_warn(
                ParseWarning(
                    code="INV_01_EMPTY_DOCUMENT",
                    message="Tài liệu không có văn bản cũng không có tài nguyên hình ảnh nào.",
                    severity=WarningSeverity.ERROR,
                    requires_manual_review=True,
                )
            )

        # Kiểm tra 2: Có nhận diện được câu hỏi khi văn bản có tín hiệu đề thi không?
        exam_cues = len(re.findall(r"(?i)\b(?:câu\s+\d+|question\s+\d+|đề\s+thi|bài\s+kiểm\s+tra)\b", doc.normalized_text))
        if exam_cues >= 2 and len(doc.questions) == 0:
            _add_warn(
                ParseWarning(
                    code="INV_02_NO_QUESTIONS_PARSED_DESPITE_CUES",
                    message="Văn bản có tín hiệu đề thi nhưng chưa tách được câu hỏi nào.",
                    severity=WarningSeverity.WARNING,
                    requires_manual_review=True,
                )
            )

        # Tập hợp ID hợp lệ để đối chiếu tham chiếu chéo (Checks 12, 13, 14)
        valid_context_ids: Set[str] = {c.context_id for c in doc.contexts}
        valid_group_ids: Set[str] = {g.group_id for g in doc.question_groups}
        valid_asset_ids: Set[str] = {t.table_id for t in doc.tables} | {im.image_id for im in doc.images}
        parsed_q_numbers: Set[int] = {q.number for q in doc.questions}

        # Kiểm tra 3 & 4: Thứ tự số câu hỏi có liên tục hoặc trùng lặp bất thường không?
        if len(doc.questions) >= 2:
            for idx in range(len(doc.questions) - 1):
                q_curr = doc.questions[idx]
                q_next = doc.questions[idx + 1]
                # Nếu cùng group_id mà số câu giảm lùi (không phải bắt đầu lại từ Câu 1 của phần mới)
                if q_curr.group_id == q_next.group_id and q_next.number < q_curr.number and q_next.number != 1:
                    _add_warn(
                        ParseWarning(
                            code="INV_03_OUT_OF_ORDER_QUESTION_NUMBER",
                            message=f"Thứ tự câu hỏi bị đảo ngược: {q_curr.label} đứng trước {q_next.label}.",
                            severity=WarningSeverity.WARNING,
                            question_id=q_next.id,
                            requires_manual_review=True,
                        ),
                        q_next,
                    )

        # Duyệt từng câu hỏi để kiểm tra các điều kiện 5 -> 16
        for q in doc.questions:
            # Kiểm tra 5: Câu hỏi có stem khác rỗng không?
            if not q.stem or not q.stem.strip():
                q.status = "needs_review"
                _add_warn(
                    ParseWarning(
                        code="INV_05_MISSING_STEM",
                        message=f"{q.label} thiếu nội dung phần dẫn (stem).",
                        severity=WarningSeverity.WARNING,
                        question_id=q.id,
                        requires_manual_review=True,
                    ),
                    q,
                )

            # Kiểm tra 6, 7, 8, 9: Kiểm định phương án cho câu hỏi trắc nghiệm
            if q.type in (
                CanonicalQuestionType.SINGLE_CHOICE,
                CanonicalQuestionType.MULTIPLE_CHOICE,
                CanonicalQuestionType.CHOICE_UNKNOWN,
            ):
                if len(q.options) < 2:
                    q.status = "needs_review"
                    _add_warn(
                        ParseWarning(
                            code="INV_06_MCQ_MISSING_OPTIONS",
                            message=f"Câu hỏi trắc nghiệm {q.label} có ít hơn 2 phương án ({len(q.options)}).",
                            severity=WarningSeverity.WARNING,
                            question_id=q.id,
                            requires_manual_review=True,
                        ),
                        q,
                    )

                seen_markers: Set[str] = set()
                for opt in q.options:
                    m_up = opt.marker.upper()
                    # Kiểm tra 7: Trùng nhãn phương án trong cùng 1 câu
                    if m_up in seen_markers:
                        q.status = "needs_review"
                        _add_warn(
                            ParseWarning(
                                code="INV_07_DUPLICATE_OPTION_MARKER",
                                message=f"{q.label} có nhãn phương án '{m_up}' bị lặp lại.",
                                severity=WarningSeverity.WARNING,
                                question_id=q.id,
                                requires_manual_review=True,
                            ),
                            q,
                        )
                    seen_markers.add(m_up)

                    # Kiểm tra 8: Phương án rỗng nội dung
                    if not opt.text.strip() and not opt.image_ids and not opt.table_ids:
                        q.status = "needs_review"
                        _add_warn(
                            ParseWarning(
                                code="INV_08_EMPTY_OPTION_CONTENT",
                                message=f"Phương án {m_up} của {q.label} bị rỗng.",
                                severity=WarningSeverity.WARNING,
                                question_id=q.id,
                                requires_manual_review=True,
                            ),
                            q,
                        )

                    # Kiểm tra 9: Phương án có nuốt nhầm tiêu đề câu hỏi tiếp theo không?
                    if re.search(r"(?im)^\s*(?:câu(?:\s+hỏi)?|question)\s+\d{1,3}\s*[.:)]", opt.text):
                        q.status = "needs_review"
                        _add_warn(
                            ParseWarning(
                                code="INV_09_OPTION_CONTAINS_QUESTION_HEADER",
                                message=f"Phương án {m_up} của {q.label} có dấu hiệu chứa tiêu đề câu hỏi khác.",
                                severity=WarningSeverity.WARNING,
                                question_id=q.id,
                                requires_manual_review=True,
                            ),
                            q,
                        )

            # Kiểm tra 10: Câu hỏi Đúng/Sai phải có danh sách mệnh đề statements
            if q.type == CanonicalQuestionType.TRUE_FALSE and not q.statements:
                q.status = "needs_review"
                _add_warn(
                    ParseWarning(
                        code="INV_10_TRUE_FALSE_MISSING_STATEMENTS",
                        message=f"Câu hỏi Đúng/Sai {q.label} chưa tách được các mệnh đề a), b), c), d).",
                        severity=WarningSeverity.WARNING,
                        question_id=q.id,
                        requires_manual_review=True,
                    ),
                    q,
                )

            # Kiểm tra 11: Câu hỏi điền khuyết nên có BlankSlot
            if q.type == CanonicalQuestionType.FILL_BLANK and not q.blanks:
                _add_warn(
                    ParseWarning(
                        code="INV_11_FILL_BLANK_NO_EXPLICIT_MARKER",
                        message=f"Câu hỏi điền khuyết {q.label} không có ký hiệu gạch chân/dấu chấm tường minh.",
                        severity=WarningSeverity.INFO,
                        question_id=q.id,
                    ),
                    q,
                )

            # Kiểm tra 12: context_id phải tồn tại trong doc.contexts
            if q.context_id and q.context_id not in valid_context_ids:
                q.status = "needs_review"
                _add_warn(
                    ParseWarning(
                        code="INV_12_DANGLING_CONTEXT_ID",
                        message=f"{q.label} tham chiếu tới context_id '{q.context_id}' không tồn tại.",
                        severity=WarningSeverity.WARNING,
                        question_id=q.id,
                        requires_manual_review=True,
                    ),
                    q,
                )

            # Kiểm tra 13: group_id phải tồn tại trong doc.question_groups
            if q.group_id and q.group_id not in valid_group_ids:
                _add_warn(
                    ParseWarning(
                        code="INV_13_DANGLING_GROUP_ID",
                        message=f"{q.label} tham chiếu tới group_id '{q.group_id}' không tồn tại.",
                        severity=WarningSeverity.WARNING,
                        question_id=q.id,
                    ),
                    q,
                )

            # Kiểm tra 14: assets (image_id / table_id) phải tồn tại
            for asset_id in q.assets:
                if asset_id not in valid_asset_ids:
                    _add_warn(
                        ParseWarning(
                            code="INV_14_DANGLING_ASSET_ID",
                            message=f"{q.label} liên kết tới tài nguyên '{asset_id}' không tồn tại.",
                            severity=WarningSeverity.WARNING,
                            question_id=q.id,
                        ),
                        q,
                    )

            # Kiểm tra 16: Đáp án gắn với câu hỏi trắc nghiệm phải thuộc tập nhãn phương án hợp lệ
            if q.answer and q.options:
                valid_m = {o.marker.upper() for o in q.options}
                ans_letters = [ch for ch in q.answer.upper() if "A" <= ch <= "F"]
                if ans_letters and not set(ans_letters).issubset(valid_m):
                    q.status = "needs_review"
                    _add_warn(
                        ParseWarning(
                            code="INV_16_INVALID_ANSWER_FOR_OPTIONS",
                            message=f"Đáp án '{q.answer}' của {q.label} không khớp với các phương án {sorted(valid_m)}.",
                            severity=WarningSeverity.WARNING,
                            question_id=q.id,
                            requires_manual_review=True,
                        ),
                        q,
                    )

        # Kiểm tra 15: Bảng đáp án có chứa câu hỏi mồ côi (không tồn tại trong danh sách câu hỏi) không?
        if doc.answer_keys and doc.questions:
            orphan_keys = sorted(k for k in doc.answer_keys.keys() if k not in parsed_q_numbers)
            if orphan_keys:
                _add_warn(
                    ParseWarning(
                        code="INV_15_ORPHAN_ANSWER_KEYS",
                        message=f"Bảng đáp án có {len(orphan_keys)} mục ({orphan_keys[:10]}) không tìm thấy câu hỏi tương ứng.",
                        severity=WarningSeverity.WARNING,
                        reason="Một số câu hỏi có thể bị khuyết hoặc bảng đáp án thuộc mã đề đầy đủ hơn.",
                        requires_manual_review=True,
                    )
                )

        # Kiểm tra 17: Đếm số block giống câu hỏi nhưng chưa được phân loại vào câu hỏi nào
        unclassified_cnt = 0
        all_q_raw = "\n".join(q.raw_text for q in doc.questions)
        for b in doc.blocks:
            if b.kind in (BlockKind.HEADER, BlockKind.FOOTER, BlockKind.PAGE_NUMBER, BlockKind.TITLE, BlockKind.SECTION_HEADING, BlockKind.ANSWER_KEY_BLOCK):
                continue
            probe = b.text[:30].strip()
            if probe and probe not in all_q_raw:
                if b.kind == BlockKind.QUESTION:
                    unclassified_cnt += 1
        doc.unclassified_blocks_count = unclassified_cnt
        if unclassified_cnt > 0:
            _add_warn(
                ParseWarning(
                    code="INV_17_UNCLASSIFIED_QUESTION_BLOCKS",
                    message=f"Phát hiện {unclassified_cnt} block có dấu hiệu câu hỏi nhưng chưa được gắn vào danh sách câu hỏi.",
                    severity=WarningSeverity.WARNING,
                    requires_manual_review=True,
                )
            )

        # Kiểm tra 18: Tỷ lệ bảo toàn ký tự văn bản
        if len(doc.normalized_text) > 200 and doc.questions:
            retained_chars = (
                sum(len(q.raw_text) for q in doc.questions)
                + sum(len(c.raw_text) for c in doc.contexts)
                + sum(len(t.markdown) for t in doc.tables)
            )
            retention_ratio = min(1.0, retained_chars / max(1, len(doc.normalized_text)))
            if retention_ratio < 0.25:
                _add_warn(
                    ParseWarning(
                        code="INV_18_LOW_TEXT_RETENTION_RATIO",
                        message=f"Tỷ lệ văn bản nằm trong các cấu trúc câu hỏi thấp ({retention_ratio:.0%}). Có thể tài liệu chứa nhiều lý thuyết hoặc phụ lục.",
                        severity=WarningSeverity.INFO,
                    )
                )

        doc.warnings.extend(new_warnings)

        # Tổng hợp danh sách ID câu hỏi cần kiểm tra thủ công
        doc.questions_needing_review = [
            q.id for q in doc.questions if q.status == "needs_review" or q.confidence.level == "low"
        ]

        # Tính toán bảng điểm DocumentConfidenceSummary đa chiều
        doc.confidence = cls.compute_document_confidence(doc)
        doc.validation_passed = len([e for e in doc.errors if not e.recoverable]) == 0
        return doc.validation_passed

    @staticmethod
    def compute_document_confidence(doc: StandardizedDocument) -> DocumentConfidenceSummary:
        """Tính điểm độ tin cậy tách biệt theo 7 chiều (Phần IX - Mục 27)."""
        summary = DocumentConfidenceSummary()

        # 1. text_extraction
        if doc.pages:
            summary.text_extraction = sum(p.extraction_confidence for p in doc.pages) / len(doc.pages)
        else:
            summary.text_extraction = 0.90 if doc.normalized_text.strip() else 0.0

        # 2. layout
        if doc.pages:
            summary.layout = sum(p.layout_confidence for p in doc.pages) / len(doc.pages)
            if any(p.state == PageContentState.ROTATED_PAGE for p in doc.pages):
                summary.layout = max(0.65, summary.layout - 0.10)
        else:
            summary.layout = 0.90

        # 3. question_boundary & 4. option_parsing & 6. question_type
        if doc.questions:
            summary.question_boundary = sum(q.confidence.structure for q in doc.questions) / len(doc.questions)
            summary.question_type = sum(q.confidence.question_type for q in doc.questions) / len(doc.questions)
            opt_scores = [q.confidence.option_parsing for q in doc.questions if q.confidence.option_parsing is not None]
            summary.option_parsing = (sum(opt_scores) / len(opt_scores)) if opt_scores else 0.95
        else:
            summary.question_boundary = 0.50 if doc.normalized_text.strip() else 0.0
            summary.option_parsing = 0.50
            summary.question_type = 0.50

        # 5. context_association
        orphan_ctx_warns = [w for w in doc.warnings if w.code in ("ORPHAN_SHARED_CONTEXT", "INV_12_DANGLING_CONTEXT_ID")]
        summary.context_association = max(0.40, 1.0 - 0.25 * len(orphan_ctx_warns))

        # 7. answer_key_association
        ans_mismatch_warns = [
            w for w in doc.warnings if w.code in ("ANSWER_KEY_OPTION_MISMATCH", "INV_15_ORPHAN_ANSWER_KEYS", "INV_16_INVALID_ANSWER_FOR_OPTIONS")
        ]
        summary.answer_key_association = max(0.35, 1.0 - 0.25 * len(ans_mismatch_warns))

        # Overall level
        dims = [
            summary.text_extraction,
            summary.layout,
            summary.question_boundary,
            summary.option_parsing,
            summary.context_association,
            summary.question_type,
            summary.answer_key_association,
        ]
        avg_score = sum(dims) / len(dims)
        if avg_score >= 0.82 and min(dims) >= 0.60 and not doc.errors:
            summary.overall_level = "high"
        elif avg_score >= 0.55 and not any(not e.recoverable for e in doc.errors):
            summary.overall_level = "medium"
        else:
            summary.overall_level = "low"

        summary.explanations.append(
            f"Trích xuất văn bản: {summary.text_extraction:.0%} | Bố cục: {summary.layout:.0%} | "
            f"Ranh giới câu hỏi: {summary.question_boundary:.0%} | Phương án: {summary.option_parsing:.0%}"
        )
        if doc.questions_needing_review:
            summary.explanations.append(
                f"Có {len(doc.questions_needing_review)}/{len(doc.questions)} câu hỏi cần kiểm tra lại ({doc.questions_needing_review[:5]})."
            )

        return summary


# ============================================================================
# 7-STAGE PIPELINE ORCHESTRATOR (Phần X - Mục 29: ExamParsingEngineV2)
# ============================================================================

class ExamParsingEngineV2:
    """
    Bộ máy điều phối 7 tầng chuẩn hóa (Phần X - Mục 29):
    Stage 1: Format detection & Security/Resource validation
    Stage 2: Native extraction & Per-page Local OCR (honoring OCR_MODE=local/off)
    Stage 3: Layout analysis & Reading-order reconstruction
    Stage 4: Context-aware question parsing & Answer key extraction
    Stage 5: Shared context & Question group linking
    Stage 6: Targeted fallback recovery
    Stage 7: Independent 18-point structural validation
    """

    def __init__(self) -> None:
        self.registry = DocumentReaderRegistry()

    def parse_document(
        self,
        source: bytes | str,
        file_name: str = "document",
        ocr_mode: Optional[OCRMode] = None,
        subject: Optional[str] = None,
        reader_output: Optional[ReaderOutput] = None,
    ) -> StandardizedDocument:
        t_start = time.perf_counter()
        cfg = get_config()
        effective_ocr = ocr_mode if ocr_mode is not None else cfg.ocr_mode

        # Stage 1, 2, 3: Đọc tài liệu và phân tích bố cục qua DocumentReaderRegistry
        if reader_output is None:
            opts = ReaderOptions(file_name=file_name, ocr_mode=effective_ocr)
            r_out = self.registry.read_any(source, opts)
        else:
            r_out = reader_output

        doc = StandardizedDocument(
            schema_version="2.0.0",
            file_name=r_out.file_name,
            source_format=r_out.detected_format,
            ocr_mode_used=r_out.ocr_mode_used,
            page_count=r_out.page_count,
            raw_text=r_out.raw_text,
            normalized_text=r_out.normalized_text,
            pages=list(r_out.pages),
            blocks=list(r_out.blocks),
            tables=list(r_out.tables),
            images=list(r_out.images),
            headers=list(r_out.headers),
            footers=list(r_out.footers),
            stage_timings=r_out.stage_timings,
            warnings=list(r_out.warnings),
            errors=list(r_out.errors),
        )

        if r_out.is_corrupted or r_out.is_encrypted:
            doc.validation_passed = False
            doc.confidence = StructuralValidator.compute_document_confidence(doc)
            doc.stage_timings.total_ms = (time.perf_counter() - t_start) * 1000.0
            return doc

        # Stage 4: Phân tích câu hỏi và trích xuất bảng đáp án (kèm mã đề)
        t_qparse = time.perf_counter()
        ans_entries, ans_by_code = QuestionParser.extract_answer_key_entries(
            doc.normalized_text, file_name=doc.file_name
        )
        doc.answer_keys = ans_entries
        doc.answer_keys_by_exam_code = ans_by_code

        # Nhận diện tất cả mã đề xuất hiện trong tài liệu
        exam_codes = sorted(
            set(re.findall(r"(?i)\bmã\s*đề(?:\s*thi)?\s*[:.]?\s*(\d{2,6})\b", doc.normalized_text))
            | set(ans_by_code.keys())
        )
        doc.detected_exam_codes = exam_codes

        flat_ans_map = {k: v.normalized_answer for k, v in ans_entries.items()}
        std_questions, _, _, q_warns = QuestionParser.parse_standardized_questions(
            text=doc.normalized_text,
            blocks=doc.blocks,
            tables=doc.tables,
            images=doc.images,
            answer_map=flat_ans_map,
            subject=subject,
            file_name=doc.file_name,
        )
        doc.warnings.extend(q_warns)

        # Stage 5: Liên kết ngữ cảnh bài đọc / hình vẽ / bảng dùng chung (ContextLinker)
        contexts, groups, ctx_warns = ContextLinker.extract_and_link_contexts(
            full_text=doc.normalized_text,
            questions=std_questions,
            blocks=doc.blocks,
            tables=doc.tables,
            images=doc.images,
            file_name=doc.file_name,
        )
        doc.contexts = contexts
        doc.question_groups = groups
        doc.warnings.extend(ctx_warns)

        # Stage 6: Khôi phục cục bộ (Targeted Recovery)
        recovered_questions, rec_warns = TargetedQuestionRecovery.run_targeted_recovery(
            std_questions, file_name=doc.file_name
        )
        doc.questions = recovered_questions
        doc.warnings.extend(rec_warns)
        doc.stage_timings.question_parsing_ms = (time.perf_counter() - t_qparse) * 1000.0

        # Stage 7: Kiểm định cấu trúc độc lập 18 điểm (StructuralValidator)
        t_val = time.perf_counter()
        StructuralValidator.validate_document(doc)
        doc.stage_timings.validation_ms = (time.perf_counter() - t_val) * 1000.0
        doc.stage_timings.total_ms = (time.perf_counter() - t_start) * 1000.0

        return doc


# ============================================================================
# EVALUATION METRICS CALCULATOR (Phần XIII - Mục 37)
# ============================================================================

@dataclass
class EvaluationBenchmarkResult:
    """Bộ chỉ số đánh giá định lượng chất lượng Parser so với Ground Truth (Phần XIII - Mục 37)."""
    question_boundary_precision: float = 1.0
    question_boundary_recall: float = 1.0
    question_boundary_f1: float = 1.0
    option_extraction_accuracy: float = 1.0
    question_type_accuracy: float = 1.0
    context_linking_accuracy: float = 1.0
    answer_key_accuracy: float = 1.0
    block_retention_rate: float = 1.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_boundary_precision": round(self.question_boundary_precision, 4),
            "question_boundary_recall": round(self.question_boundary_recall, 4),
            "question_boundary_f1": round(self.question_boundary_f1, 4),
            "option_extraction_accuracy": round(self.option_extraction_accuracy, 4),
            "question_type_accuracy": round(self.question_type_accuracy, 4),
            "context_linking_accuracy": round(self.context_linking_accuracy, 4),
            "answer_key_accuracy": round(self.answer_key_accuracy, 4),
            "block_retention_rate": round(self.block_retention_rate, 4),
            "details": self.details,
        }


class ParserEvaluator:
    """Công cụ tính toán Precision, Recall, F1 và Accuracy của StandardizedDocument so với Ground Truth."""

    @staticmethod
    def evaluate(
        doc: StandardizedDocument,
        expected_question_numbers: List[int],
        expected_option_counts: Optional[Dict[int, int]] = None,
        expected_types: Optional[Dict[int, CanonicalQuestionType]] = None,
        expected_context_questions: Optional[List[int]] = None,
        expected_answers: Optional[Dict[int, str]] = None,
    ) -> EvaluationBenchmarkResult:
        res = EvaluationBenchmarkResult()

        pred_nums = [q.number for q in doc.questions]
        exp_set = set(expected_question_numbers)
        pred_set = set(pred_nums)

        tp = len(exp_set & pred_set)
        fp = len(pred_set - exp_set)
        fn = len(exp_set - pred_set)

        res.question_boundary_precision = tp / max(1, tp + fp) if pred_set else (1.0 if not exp_set else 0.0)
        res.question_boundary_recall = tp / max(1, tp + fn) if exp_set else 1.0
        p, r = res.question_boundary_precision, res.question_boundary_recall
        res.question_boundary_f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

        q_by_num = {q.number: q for q in doc.questions}

        if expected_option_counts:
            correct_opts = sum(
                1 for qn, cnt in expected_option_counts.items()
                if qn in q_by_num and len(q_by_num[qn].options) == cnt
            )
            res.option_extraction_accuracy = correct_opts / max(1, len(expected_option_counts))

        if expected_types:
            correct_types = sum(
                1 for qn, qt in expected_types.items()
                if qn in q_by_num and q_by_num[qn].type == qt
            )
            res.question_type_accuracy = correct_types / max(1, len(expected_types))

        if expected_context_questions is not None:
            pred_ctx_qs = {q.number for q in doc.questions if q.context_id is not None}
            exp_ctx_set = set(expected_context_questions)
            if exp_ctx_set:
                res.context_linking_accuracy = len(pred_ctx_qs & exp_ctx_set) / len(exp_ctx_set)

        if expected_answers:
            correct_ans = sum(
                1 for qn, ans in expected_answers.items()
                if qn in q_by_num and (q_by_num[qn].answer or "").upper() == ans.upper()
            )
            res.answer_key_accuracy = correct_ans / max(1, len(expected_answers))

        total_blocks = len(doc.blocks)
        res.block_retention_rate = (
            max(0.0, (total_blocks - doc.unclassified_blocks_count) / total_blocks)
            if total_blocks > 0
            else 1.0
        )

        res.details = {
            "expected_questions": len(expected_question_numbers),
            "parsed_questions": len(doc.questions),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
        }
        return res
