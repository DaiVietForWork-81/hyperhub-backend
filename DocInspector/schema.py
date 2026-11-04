"""
Canonical Data Models and Standardized Schema (v2.0.0) for DocInspector Engine.
Covers Document, Page, Block, Table, TableCell, ImageAsset, SharedContext,
QuestionGroup, StandardizedQuestion, SubQuestionNode, OptionItem, StatementItem,
BlankSlot, AnswerKeyEntry, SourceReference, ParseWarning, ParseError, and MultiConfidence.
100% Deterministic, Traceable, Zero-LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class CanonicalQuestionType(str, Enum):
    """Chuẩn hóa loại câu hỏi thành tập enum ổn định (Phần VIII - Mục 25)."""
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    CHOICE_UNKNOWN = "choice_unknown"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    MATCHING = "matching"
    ORDERING = "ordering"
    CLASSIFICATION = "classification"
    TABLE_COMPLETION = "table_completion"
    CALCULATION = "calculation"
    PROOF = "proof"
    READING_COMPREHENSION = "reading_comprehension"
    COMPOSITE = "composite"
    UNKNOWN = "unknown"

    def to_legacy_type(self) -> str:
        """Ánh xạ ngược về question_type cũ để giữ tương thích 100% với các module hiện có."""
        if self in (
            CanonicalQuestionType.SINGLE_CHOICE,
            CanonicalQuestionType.MULTIPLE_CHOICE,
            CanonicalQuestionType.CHOICE_UNKNOWN,
            CanonicalQuestionType.READING_COMPREHENSION,
        ):
            return "MCQ_4"
        if self == CanonicalQuestionType.TRUE_FALSE:
            return "TRUE_FALSE_GROUP"
        if self in (CanonicalQuestionType.SHORT_ANSWER, CanonicalQuestionType.FILL_BLANK):
            return "SHORT_ANSWER"
        return "ESSAY_PROBLEM"


class BlockKind(str, Enum):
    """Loại phần tử bố cục trung gian trên trang tài liệu (Phần III - Mục 5)."""
    TITLE = "title"
    PARAGRAPH = "paragraph"
    QUESTION = "question"
    OPTION = "option"
    TABLE = "table"
    IMAGE = "image"
    CAPTION = "caption"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    FORMULA = "formula"
    NOTE = "note"
    SIDEBAR = "sidebar"
    CONTEXT_PASSAGE = "context_passage"
    SECTION_HEADING = "section_heading"
    ANSWER_KEY_BLOCK = "answer_key_block"


class PageContentState(str, Enum):
    """Phân loại trạng thái trích xuất của từng trang (Phần II - Mục 4)."""
    NATIVE_TEXT = "native_text"                         # Có văn bản gốc rõ ràng
    SCANNED_IMAGE_ONLY = "scanned_image_only"           # Không có text, toàn bộ là ảnh scan
    HYBRID_TEXT_AND_SCAN = "hybrid_text_and_scan"       # Vừa có text vừa có ảnh scan
    DUPLICATE_TEXT_LAYER = "duplicate_text_layer"       # Nhiều lớp text trùng lặp (shadow text)
    LOW_QUALITY_SCAN = "low_quality_scan"               # Trang scan mờ, nghiêng hoặc tương phản thấp
    ROTATED_PAGE = "rotated_page"                       # Trang bị xoay 90°, 180° hoặc 270°
    BLANK_PAGE = "blank_page"                           # Trang trắng
    CORRUPTED_PAGE = "corrupted_page"                   # Trang lỗi không thể đọc


class WarningSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class SourceReference:
    """Thông tin truy vết ngược về tài liệu gốc (Phần VIII - Mục 26)."""
    file_name: str
    page: Optional[int] = None
    block_id: Optional[str] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    table_id: Optional[str] = None
    cell_id: Optional[str] = None
    image_id: Optional[str] = None
    reading_order: Optional[int] = None
    extraction_method: str = "native"
    parser_version: str = "2.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_name": self.file_name,
            "page": self.page,
            "block_id": self.block_id,
            "bbox": list(self.bbox) if self.bbox else None,
            "table_id": self.table_id,
            "cell_id": self.cell_id,
            "image_id": self.image_id,
            "reading_order": self.reading_order,
            "extraction_method": self.extraction_method,
            "parser_version": self.parser_version,
        }


@dataclass
class ParseWarning:
    """Cảnh báo có khả năng giải thích rõ nguồn gốc và nguyên nhân (Phần XVI - Mục D)."""
    code: str
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    page: Optional[int] = None
    block_id: Optional[str] = None
    question_id: Optional[str] = None
    reason: Optional[str] = None
    attempted_method: Optional[str] = None
    requires_manual_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "page": self.page,
            "block_id": self.block_id,
            "question_id": self.question_id,
            "reason": self.reason,
            "attempted_method": self.attempted_method,
            "requires_manual_review": self.requires_manual_review,
        }


@dataclass
class ParseError:
    """Lỗi được chuẩn hóa trong quá trình đọc/phân tích."""
    code: str
    message: str
    stage: str
    page: Optional[int] = None
    block_id: Optional[str] = None
    recoverable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "page": self.page,
            "block_id": self.block_id,
            "recoverable": self.recoverable,
        }


@dataclass
class QuestionConfidence:
    """Điểm độ tin cậy đa chiều cho từng câu hỏi (Phần IX - Mục 27)."""
    structure: float = 0.85
    content: float = 0.90
    association: float = 1.0
    question_type: float = 0.85
    option_parsing: Optional[float] = None
    answer_key_association: Optional[float] = None
    level: str = "high"  # "high" | "medium" | "low"
    signals: List[str] = field(default_factory=list)

    def compute_level(self) -> str:
        vals = [self.structure, self.content, self.association, self.question_type]
        if self.option_parsing is not None:
            vals.append(self.option_parsing)
        avg = sum(vals) / max(1, len(vals))
        if avg >= 0.80 and min(vals) >= 0.60:
            self.level = "high"
        elif avg >= 0.55:
            self.level = "medium"
        else:
            self.level = "low"
        return self.level

    def to_dict(self) -> Dict[str, Any]:
        self.compute_level()
        return {
            "structure": round(self.structure, 3),
            "content": round(self.content, 3),
            "association": round(self.association, 3),
            "question_type": round(self.question_type, 3),
            "option_parsing": round(self.option_parsing, 3) if self.option_parsing is not None else None,
            "answer_key_association": round(self.answer_key_association, 3) if self.answer_key_association is not None else None,
            "level": self.level,
            "signals": self.signals,
        }


@dataclass
class DocumentConfidenceSummary:
    """Bảng điểm confidence tách biệt cho toàn bộ tài liệu (Phần IX - Mục 27)."""
    text_extraction: float = 1.0
    layout: float = 1.0
    question_boundary: float = 1.0
    option_parsing: float = 1.0
    context_association: float = 1.0
    question_type: float = 1.0
    answer_key_association: float = 1.0
    overall_level: str = "high"
    explanations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_extraction": round(self.text_extraction, 3),
            "layout": round(self.layout, 3),
            "question_boundary": round(self.question_boundary, 3),
            "option_parsing": round(self.option_parsing, 3),
            "context_association": round(self.context_association, 3),
            "question_type": round(self.question_type, 3),
            "answer_key_association": round(self.answer_key_association, 3),
            "overall_level": self.overall_level,
            "explanations": self.explanations,
        }


@dataclass
class TableCellModel:
    """Ô dữ liệu trong bảng với thông tin gộp hàng/cột và công thức."""
    cell_id: str
    row_index: int
    col_index: int
    row_span: int = 1
    col_span: int = 1
    raw_text: str = ""
    text: str = ""
    is_header: bool = False
    contains_formula: bool = False
    image_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "raw_text": self.raw_text,
            "text": self.text,
            "is_header": self.is_header,
            "contains_formula": self.contains_formula,
            "image_ids": self.image_ids,
        }


@dataclass
class TableModel:
    """Cấu trúc bảng dữ liệu bảo toàn hàng, cột, ô gộp và nguồn gốc (Phần V - Mục 17)."""
    table_id: str
    page: int
    row_count: int
    col_count: int
    headers: List[str] = field(default_factory=list)
    cells: List[TableCellModel] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    markdown: str = ""
    bbox: Optional[Tuple[float, float, float, float]] = None
    is_borderless: bool = False
    source_type: str = "native_table"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "page": self.page,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "headers": self.headers,
            "rows": self.rows,
            "cells": [c.to_dict() for c in self.cells],
            "markdown": self.markdown,
            "bbox": list(self.bbox) if self.bbox else None,
            "is_borderless": self.is_borderless,
            "source_type": self.source_type,
            "warnings": self.warnings,
        }


@dataclass
class ImageAsset:
    """Tài nguyên hình ảnh/sơ đồ với ID, vị trí và trạng thái nhận dạng (Phần V - Mục 19)."""
    image_id: str
    page: int
    width: int = 0
    height: int = 0
    bbox: Optional[Tuple[float, float, float, float]] = None
    orientation_deg: int = 0
    image_format: str = "PNG"
    byte_size: int = 0
    ocr_status: str = "not_processed"  # "ocr_disabled" | "ocr_completed" | "ocr_empty" | "not_processed"
    ocr_text: str = ""
    caption: Optional[str] = None
    requires_manual_review: bool = False
    source_ref: Optional[SourceReference] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "page": self.page,
            "width": self.width,
            "height": self.height,
            "bbox": list(self.bbox) if self.bbox else None,
            "orientation_deg": self.orientation_deg,
            "image_format": self.image_format,
            "byte_size": self.byte_size,
            "ocr_status": self.ocr_status,
            "ocr_text": self.ocr_text,
            "caption": self.caption,
            "requires_manual_review": self.requires_manual_review,
            "source_ref": self.source_ref.to_dict() if self.source_ref else None,
        }


@dataclass
class DocumentBlock:
    """Khối nội dung trung gian (Intermediate Block Representation - Phần III - Mục 5)."""
    block_id: str
    kind: BlockKind
    raw_text: str
    text: str
    page: int
    reading_order: int
    bbox: Optional[Tuple[float, float, float, float]] = None
    column_index: int = 0
    source_type: str = "native_text"
    style_meta: Dict[str, Any] = field(default_factory=dict)
    table_id: Optional[str] = None
    image_id: Optional[str] = None
    contains_math: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "kind": self.kind.value,
            "raw_text": self.raw_text,
            "text": self.text,
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox else None,
            "reading_order": self.reading_order,
            "column_index": self.column_index,
            "source_type": self.source_type,
            "style_meta": self.style_meta,
            "table_id": self.table_id,
            "image_id": self.image_id,
            "contains_math": self.contains_math,
            "warnings": self.warnings,
        }


@dataclass
class PageLayout:
    """Thông tin bố cục và chất lượng trích xuất theo từng trang."""
    page_number: int
    width: float = 0.0
    height: float = 0.0
    rotation_deg: int = 0
    state: PageContentState = PageContentState.NATIVE_TEXT
    column_count: int = 1
    has_sidebar: bool = False
    native_char_count: int = 0
    ocr_char_count: int = 0
    image_count: int = 0
    table_count: int = 0
    extraction_confidence: float = 1.0
    layout_confidence: float = 1.0
    block_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width": round(self.width, 1),
            "height": round(self.height, 1),
            "rotation_deg": self.rotation_deg,
            "state": self.state.value,
            "column_count": self.column_count,
            "has_sidebar": self.has_sidebar,
            "native_char_count": self.native_char_count,
            "ocr_char_count": self.ocr_char_count,
            "image_count": self.image_count,
            "table_count": self.table_count,
            "extraction_confidence": round(self.extraction_confidence, 3),
            "layout_confidence": round(self.layout_confidence, 3),
            "block_ids": self.block_ids,
            "warnings": self.warnings,
        }


@dataclass
class SharedContext:
    """Bài đọc chung, hình vẽ chung hoặc bảng số liệu dùng chung cho nhiều câu hỏi (Phần IV - Mục 14)."""
    context_id: str
    group_id: str
    kind: str  # "reading_passage" | "shared_figure" | "shared_table" | "shared_stem"
    raw_text: str
    text: str
    instructions: Optional[str] = None
    question_range: Optional[Tuple[int, int]] = None
    target_question_numbers: List[int] = field(default_factory=list)
    page_start: int = 1
    page_end: int = 1
    table_ids: List[str] = field(default_factory=list)
    image_ids: List[str] = field(default_factory=list)
    source_refs: List[SourceReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_id": self.context_id,
            "group_id": self.group_id,
            "kind": self.kind,
            "raw_text": self.raw_text,
            "text": self.text,
            "instructions": self.instructions,
            "question_range": list(self.question_range) if self.question_range else None,
            "target_question_numbers": self.target_question_numbers,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "table_ids": self.table_ids,
            "image_ids": self.image_ids,
            "source_refs": [s.to_dict() for s in self.source_refs],
        }


@dataclass
class QuestionGroup:
    """Nhóm câu hỏi theo Phần (Phần I, II, III) hoặc theo bài đọc chung."""
    group_id: str
    title: str
    instructions: Optional[str] = None
    section_marker: Optional[str] = None
    context_id: Optional[str] = None
    question_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "group_id": self.group_id,
            "title": self.title,
            "instructions": self.instructions,
            "section_marker": self.section_marker,
            "context_id": self.context_id,
            "question_ids": self.question_ids,
        }


@dataclass
class OptionItem:
    """Phương án lựa chọn trong câu hỏi trắc nghiệm (Phần IV - Mục 9 & 10)."""
    marker: str
    raw_text: str
    text: str
    is_multiline: bool = False
    contains_formula: bool = False
    image_ids: List[str] = field(default_factory=list)
    table_ids: List[str] = field(default_factory=list)
    source_ref: Optional[SourceReference] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "marker": self.marker,
            "raw_text": self.raw_text,
            "text": self.text,
            "is_multiline": self.is_multiline,
            "contains_formula": self.contains_formula,
            "image_ids": self.image_ids,
            "table_ids": self.table_ids,
            "source_ref": self.source_ref.to_dict() if self.source_ref else None,
        }


@dataclass
class StatementItem:
    """Mệnh đề trong câu hỏi Đúng/Sai (Phần IV - Mục 11)."""
    marker: str
    raw_text: str
    text: str
    explicit_answer: Optional[str] = None  # Chỉ gán khi có đáp án tường minh trong tài liệu
    source_ref: Optional[SourceReference] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "marker": self.marker,
            "raw_text": self.raw_text,
            "text": self.text,
            "explicit_answer": self.explicit_answer,
            "source_ref": self.source_ref.to_dict() if self.source_ref else None,
        }


@dataclass
class BlankSlot:
    """Vị trí chỗ trống trong câu hỏi điền khuyết (Phần IV - Mục 12)."""
    slot_index: int
    raw_marker: str
    prefix_text: str = ""
    suffix_text: str = ""
    root_word_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "raw_marker": self.raw_marker,
            "prefix_text": self.prefix_text,
            "suffix_text": self.suffix_text,
            "root_word_hint": self.root_word_hint,
        }


@dataclass
class SubQuestionNode:
    """Cây phân cấp ý nhỏ lồng nhau: Câu 1 -> a), b) -> i), ii) (Phần IV - Mục 13 & 16)."""
    sub_id: str
    marker: str
    raw_text: str
    stem: str
    type: CanonicalQuestionType = CanonicalQuestionType.ESSAY
    score_points: Optional[float] = None
    children: List["SubQuestionNode"] = field(default_factory=list)
    source_ref: Optional[SourceReference] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sub_id": self.sub_id,
            "marker": self.marker,
            "raw_text": self.raw_text,
            "stem": self.stem,
            "type": self.type.value,
            "score_points": self.score_points,
            "children": [c.to_dict() for c in self.children],
            "source_ref": self.source_ref.to_dict() if self.source_ref else None,
        }


@dataclass
class AnswerKeyEntry:
    """Mục đáp án tường minh trích xuất từ bảng đáp án hoặc lời giải (Phần VII - Mục 22 & 23)."""
    question_number: int
    raw_answer: str
    normalized_answer: str
    exam_code: Optional[str] = None
    part_section: Optional[str] = None
    solution_text: Optional[str] = None
    source_ref: Optional[SourceReference] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_number": self.question_number,
            "raw_answer": self.raw_answer,
            "normalized_answer": self.normalized_answer,
            "exam_code": self.exam_code,
            "part_section": self.part_section,
            "solution_text": self.solution_text,
            "source_ref": self.source_ref.to_dict() if self.source_ref else None,
        }


@dataclass
class StandardizedQuestion:
    """Schema câu hỏi chuẩn hóa chính thức (Phần VIII - Mục 24)."""
    id: str                                            # Ví dụ: "q_001"
    number: int                                        # Số thứ tự câu
    label: str                                         # Nhãn gốc: "Câu 1", "Question 1", "Bài 1"
    type: CanonicalQuestionType                        # Enum chuẩn hóa
    raw_text: str                                      # Văn bản gốc chưa cắt tỉa
    stem: str                                          # Nội dung câu hỏi chính
    instructions: Optional[str] = None                 # Chỉ dẫn riêng của câu hỏi (nếu có)
    options: List[OptionItem] = field(default_factory=list)
    statements: List[StatementItem] = field(default_factory=list)
    blanks: List[BlankSlot] = field(default_factory=list)
    matching_columns: Optional[Dict[str, List[str]]] = None
    sub_questions: List[SubQuestionNode] = field(default_factory=list)
    context_id: Optional[str] = None
    group_id: Optional[str] = None
    assets: List[str] = field(default_factory=list)    # Danh sách image_id / table_id liên kết
    answer: Optional[str] = None                       # Chỉ gán khi có đáp án tường minh
    solution_text: Optional[str] = None
    score_points: Optional[float] = None
    topic_domain: Optional[str] = None
    cognitive_level: str = "COMPREHENSION"
    spans_multiple_pages: bool = False
    source_refs: List[SourceReference] = field(default_factory=list)
    confidence: QuestionConfidence = field(default_factory=QuestionConfidence)
    status: str = "parsed"                             # "parsed" | "needs_review" | "partial"
    warnings: List[ParseWarning] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "label": self.label,
            "type": self.type.value,
            "legacy_type": self.type.to_legacy_type(),
            "raw_text": self.raw_text,
            "stem": self.stem,
            "instructions": self.instructions,
            "options": [o.to_dict() for o in self.options],
            "statements": [s.to_dict() for s in self.statements],
            "blanks": [b.to_dict() for b in self.blanks],
            "matching_columns": self.matching_columns,
            "sub_questions": [sq.to_dict() for sq in self.sub_questions],
            "context_id": self.context_id,
            "group_id": self.group_id,
            "assets": self.assets,
            "answer": self.answer,
            "solution_text": self.solution_text,
            "score_points": self.score_points,
            "topic_domain": self.topic_domain,
            "cognitive_level": self.cognitive_level,
            "spans_multiple_pages": self.spans_multiple_pages,
            "source_refs": [sr.to_dict() for sr in self.source_refs],
            "confidence": self.confidence.to_dict(),
            "status": self.status,
            "warnings": [w.to_dict() for w in self.warnings],
        }


@dataclass
class StageTiming:
    """Theo dõi thời gian thực thi của từng stage (Phần XII - Mục 34)."""
    file_loading_ms: float = 0.0
    native_extraction_ms: float = 0.0
    layout_reconstruction_ms: float = 0.0
    ocr_ms: float = 0.0
    question_parsing_ms: float = 0.0
    validation_ms: float = 0.0
    serialization_ms: float = 0.0
    total_ms: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "file_loading_ms": round(self.file_loading_ms, 2),
            "native_extraction_ms": round(self.native_extraction_ms, 2),
            "layout_reconstruction_ms": round(self.layout_reconstruction_ms, 2),
            "ocr_ms": round(self.ocr_ms, 2),
            "question_parsing_ms": round(self.question_parsing_ms, 2),
            "validation_ms": round(self.validation_ms, 2),
            "serialization_ms": round(self.serialization_ms, 2),
            "total_ms": round(self.total_ms, 2),
        }


@dataclass
class ManualCorrectionRecord:
    """Lưu trữ lịch sử chỉnh sửa thủ công mà không ghi đè mất raw result (Phần XIV - Mục 40)."""
    target_id: str
    field_name: str
    raw_value: Any
    corrected_value: Any
    author: str = "manual_reviewer"
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "field_name": self.field_name,
            "raw_value": self.raw_value,
            "corrected_value": self.corrected_value,
            "author": self.author,
            "reason": self.reason,
        }


@dataclass
class StandardizedDocument:
    """Đối tượng Document chuẩn hóa đầu ra của toàn bộ pipeline (Phần VIII - Mục 24)."""
    schema_version: str = "2.0.0"
    file_name: str = ""
    source_format: str = "UNKNOWN"
    ocr_mode_used: str = "local"
    page_count: int = 0
    raw_text: str = ""
    normalized_text: str = ""
    pages: List[PageLayout] = field(default_factory=list)
    blocks: List[DocumentBlock] = field(default_factory=list)
    tables: List[TableModel] = field(default_factory=list)
    images: List[ImageAsset] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)
    footers: List[str] = field(default_factory=list)
    contexts: List[SharedContext] = field(default_factory=list)
    question_groups: List[QuestionGroup] = field(default_factory=list)
    questions: List[StandardizedQuestion] = field(default_factory=list)
    answer_keys: Dict[int, AnswerKeyEntry] = field(default_factory=dict)
    answer_keys_by_exam_code: Dict[str, Dict[int, str]] = field(default_factory=dict)
    detected_exam_codes: List[str] = field(default_factory=list)
    unclassified_blocks_count: int = 0
    questions_needing_review: List[str] = field(default_factory=list)
    confidence: DocumentConfidenceSummary = field(default_factory=DocumentConfidenceSummary)
    stage_timings: StageTiming = field(default_factory=StageTiming)
    warnings: List[ParseWarning] = field(default_factory=list)
    errors: List[ParseError] = field(default_factory=list)
    validation_passed: bool = True
    manual_corrections: List[ManualCorrectionRecord] = field(default_factory=list)

    def apply_manual_correction(
        self,
        question_id: str,
        field_name: str,
        new_value: Any,
        author: str = "manual_reviewer",
        reason: str = "",
    ) -> bool:
        """Áp dụng hiệu chỉnh thủ công nhưng vẫn giữ nguyên raw_value để truy vết (Phần XIV - Mục 40)."""
        for q in self.questions:
            if q.id == question_id and hasattr(q, field_name):
                old_val = getattr(q, field_name)
                self.manual_corrections.append(
                    ManualCorrectionRecord(
                        target_id=question_id,
                        field_name=field_name,
                        raw_value=old_val,
                        corrected_value=new_value,
                        author=author,
                        reason=reason,
                    )
                )
                setattr(q, field_name, new_value)
                q.status = "manually_reviewed"
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "file_name": self.file_name,
            "source_format": self.source_format,
            "ocr_mode_used": self.ocr_mode_used,
            "page_count": self.page_count,
            "raw_text_length": len(self.raw_text),
            "normalized_text_length": len(self.normalized_text),
            "pages": [p.to_dict() for p in self.pages],
            "blocks": [b.to_dict() for b in self.blocks],
            "tables": [t.to_dict() for t in self.tables],
            "images": [img.to_dict() for img in self.images],
            "headers": self.headers,
            "footers": self.footers,
            "contexts": [c.to_dict() for c in self.contexts],
            "question_groups": [g.to_dict() for g in self.question_groups],
            "questions": [q.to_dict() for q in self.questions],
            "answer_keys": {str(k): v.to_dict() for k, v in self.answer_keys.items()},
            "answer_keys_by_exam_code": self.answer_keys_by_exam_code,
            "detected_exam_codes": self.detected_exam_codes,
            "unclassified_blocks_count": self.unclassified_blocks_count,
            "questions_needing_review": self.questions_needing_review,
            "confidence": self.confidence.to_dict(),
            "stage_timings": self.stage_timings.to_dict(),
            "warnings": [w.to_dict() for w in self.warnings],
            "errors": [e.to_dict() for e in self.errors],
            "validation_passed": self.validation_passed,
            "manual_corrections": [mc.to_dict() for mc in self.manual_corrections],
        }
