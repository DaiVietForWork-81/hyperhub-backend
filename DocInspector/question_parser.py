"""
Context-Aware Rule-Based Question Parser, Sub-Question Tree Builder, and Answer Key Linker.
Implements Part IV (Mục 8–16) and Part VII (Mục 22–23):
- Multi-signal question boundary detection with negative context guards (rejects TOC, Chương, Ví dụ, mid-sentence refs)
- Flexible option parsing (A., A), (A), A:, a), 2 to 6+ options, inline/2-col/multiline)
- All 15 CanonicalQuestionType classifications
- True/False StatementItem extraction (never fabricating answers)
- Fill-in-the-blank BlankSlot extraction (preserving blanks in stem + prefix/suffix/root_word_hint)
- Matching column extraction (col_a / col_b), Ordering, Classification, Table Completion, Calculation, Proof
- Multi-level SubQuestionNode tree (Câu 1 -> a), b) -> i), ii))
- Context-safe Answer Key & Multi-Exam-Code (Mã đề 101, 102...) extraction
- 100% Backward Compatible with ExtractedQuestion & CognitiveBreakdown.
100% Deterministic, Offline, Zero-LLM.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .layout_analyzer import LayoutAnalyzer
from .models import (
    CognitiveBreakdown,
    CognitiveLevel,
    ExamDetailedMetadata,
    ExtractedQuestion,
)
from .schema import (
    AnswerKeyEntry,
    BlankSlot,
    CanonicalQuestionType,
    DocumentBlock,
    ImageAsset,
    OptionItem,
    ParseWarning,
    QuestionConfidence,
    SourceReference,
    StandardizedQuestion,
    StatementItem,
    SubQuestionNode,
    TableModel,
    WarningSeverity,
)
from .signatures import (
    RE_COG_APPLICATION,
    RE_COG_COMPREHENSION,
    RE_COG_HIGH_APPLICATION,
    RE_COG_RECOGNITION,
    RE_EXAM_CODE,
    RE_EXAM_DURATION,
    RE_EXAM_PERIOD,
    RE_FIGURE_GRAPH_CUE,
    RE_MCQ_FOUR_OPTIONS,
    RE_MOET_PART1,
    RE_MOET_PART2,
    RE_MOET_PART3,
    RE_QUESTION_HEADING,
    RE_QUESTION_POINTS,
    RE_QUESTION_SOLUTION_SPLIT,
    RE_READING_PASSAGE_CUE,
    RE_TABLE_CUE,
    RE_TOTAL_POINTS,
    RE_TRUE_FALSE_SUBITEMS,
    TOPIC_SIGNATURES,
    VIETNAM_PROVINCES,
)


# ============================================================================
# EXTENDED DETERMINISTIC REGEX PATTERNS (PHẦN IV & VII)
# ============================================================================

# Mẫu nhận diện ranh giới kết thúc đề và bắt đầu phần đáp án / lời giải chung ở cuối tài liệu
RE_EXAM_END_OR_ANSWER_SECTION = re.compile(
    r"(?im)(?:"
    r"^\s*[-–—⎯_=\*]{2,}\s*(?:h[ếe?.\s]t|the\s+end)\s*[-–—⎯_=\*]{2,}"
    r"|^\s*(?:b[ảa?.\s]ng\s*[đd?.\s][áa?.\s]p\s*[áa?.\s]n|đáp\s*án\s*(?:và\s*hướng\s*dẫn\s*chấm|tham\s*khảo|chi\s*tiết)?|"
    r"hướng\s*dẫn\s*chấm(?:\s*chi\s*tiết)?|answer\s*keys?)\s*[:：\-–—]?\s*$"
    r")"
)

# Mẫu dòng mục lục (Table of Contents) có dấu chấm dẫn tới số trang: "Bài 1: Hàm số ...... 15"
RE_TOC_DOTTED_LINE = re.compile(r"(?:\.{3,}|…{2,}|\s\.[\s.]+\.)\s*\d{1,4}\s*$")

# Mẫu phủ định trước vị trí "Câu X" / "Bài X" (ví dụ: "xem Câu 1", "tương tự Bài 2", "ở Câu 3")
RE_PRECEDING_REF_GUARD = re.compile(
    r"(?i)(?:xem|ở|tại|như|theo|tương\s+tự|áp\s+dụng|kết\s+quả|đáp\s+án|của|từ|đến)\s+$"
)

# Mẫu nhận diện phương án trắc nghiệm linh hoạt (A-F):
# Hỗ trợ: A. / A) / (A) / A:
RE_FLEX_OPTION = re.compile(
    r"(?:^|(?<=\s)|(?<=\|))"
    r"(?:\(([A-F])\)|([A-F])\s*[.:)])\s+"
    r"(.+?)"
    r"(?=(?:\s+(?:\([A-F]\)|[A-F]\s*[.:)])\s+)|(?:\n\s*(?:\([A-F]\)|[A-F]\s*[.:)])\s+)|\Z)",
    re.DOTALL,
)

# Mẫu phương án chữ thường a) b) c) d) khi dùng làm MCQ hoặc mệnh đề Đúng/Sai
RE_LOWER_SUBITEM = re.compile(
    r"(?:^|\n|\|\s*)\s*(?:[\|\*\_]*\s*)(?:\(([a-f])\)|([a-f])[.)])\s+(.+?)(?=(?:\n\s*(?:[\|\*\_]*\s*)(?:\([a-f]\)|[a-f][.)])\s+)|\Z)",
    re.DOTALL,
)

# Mẫu ý con cấp 2: i), ii), iii), iv)
RE_ROMAN_SUBITEM = re.compile(
    r"(?:^|\n)\s*(?:\((i{1,3}|iv|v|vi)\)|(i{1,3}|iv|v|vi)[.)])\s+(.+?)(?=(?:\n\s*(?:\((?:i{1,3}|iv|v|vi)\)|(?:i{1,3}|iv|v|vi)[.)])\s+)|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Mẫu chỗ trống điền khuyết (Fill-in-the-blank): ______, ......., (1)______, [___]
RE_BLANK_SLOT = re.compile(
    r"(?:\(\d{1,2}\)\s*)?(?:_{3,}|\.{4,}|\[\s*_{1,}\s*\]|\(\s*_{2,}\s*\))"
    r"(?:\s*\(([a-zA-ZÀ-ỹ\s/\-]{2,25})\))?"
)

# Mẫu đáp án rõ ràng trong lời giải: "Chọn A", "Đáp án: B", "Đáp án đúng là C", "Đáp số: 12,5"
RE_INLINE_EXPLICIT_ANSWER = re.compile(
    r"(?i)\b(?:chọn(?:\s+đáp\s+án)?|đáp\s+án(?:\s+đúng(?:\s+là)?)?|key)\s*[:：]?\s*\b([A-F])\b"
)
RE_INLINE_SHORT_ANSWER = re.compile(
    r"(?i)\b(?:đáp\s+số|vậy\s+kết\s+quả(?:\s+là)?)\s*[:：]\s*([-+]?\d+(?:[.,]\d+)?)\b"
)


class QuestionParser:
    """
    Bộ phân tích cấu trúc câu hỏi đa tín hiệu (Phần IV & VII).
    Đảm bảo tương thích ngược 100% với ExtractedQuestion và cung cấp StandardizedQuestion v2.0.0.
    """

    @classmethod
    def parse_all_questions(
        cls,
        text: str,
        answer_map: Optional[Dict[int, str]] = None,
        subject: Optional[str] = None,
    ) -> Tuple[List[ExtractedQuestion], CognitiveBreakdown]:
        """
        API công khai hiện có: Trả về (List[ExtractedQuestion], CognitiveBreakdown).
        Giữ nguyên chữ ký và hành vi cho toàn bộ các module hiện tại.
        """
        _, legacy_questions, breakdown, _ = cls.parse_standardized_questions(
            text=text,
            answer_map=answer_map,
            subject=subject,
        )
        return legacy_questions, breakdown

    @classmethod
    def parse_standardized_questions(
        cls,
        text: str,
        blocks: Optional[List[DocumentBlock]] = None,
        tables: Optional[List[TableModel]] = None,
        images: Optional[List[ImageAsset]] = None,
        answer_map: Optional[Dict[int, str]] = None,
        subject: Optional[str] = None,
        file_name: str = "document",
    ) -> Tuple[List[StandardizedQuestion], List[ExtractedQuestion], CognitiveBreakdown, List[ParseWarning]]:
        """
        Phân tích văn bản tài liệu thành danh sách StandardizedQuestion (schema v2.0.0)
        đồng thời tạo danh sách ExtractedQuestion (tương thích ngược).
        """
        if not text or not text.strip():
            return [], [], CognitiveBreakdown(), []

        warnings: List[ParseWarning] = []

        # 1. Tách phần đề bài (question_corpus) và phần cuối đề (Bảng đáp án / Hướng dẫn chấm)
        question_corpus, trailing_section = cls._split_exam_and_answer_section(text)

        # 2. Nhận diện danh sách ranh giới bắt đầu câu hỏi với bộ lọc ngữ cảnh âm (Negative Context Guards)
        boundary_spans = cls._find_question_boundaries(question_corpus)

        # 3. Trích xuất đáp án tường minh (ưu tiên từ trailing_section để không bắt nhầm "1-A" trong thân câu hỏi)
        answer_keys = answer_map if answer_map is not None else cls.extract_answer_keys(text)

        trailing_has_solutions = bool(
            trailing_section
            and re.search(
                r"(?i)\b(?:hướng\s*dẫn\s*giải|lời\s*giải\s*chi\s*tiết|giải\s*chi\s*tiết|hướng\s*dẫn\s*chấm\s*chi\s*tiết)\b",
                trailing_section,
            )
        )

        # Vị trí các phần chuẩn Bộ GD&ĐT 2025 (Phần I, II, III)
        p1_m = RE_MOET_PART1.search(question_corpus)
        p2_m = RE_MOET_PART2.search(question_corpus)
        p3_m = RE_MOET_PART3.search(question_corpus)
        p1_pos = p1_m.start() if p1_m else -1
        p2_pos = p2_m.start() if p2_m else -1
        p3_pos = p3_m.start() if p3_m else -1

        std_questions: List[StandardizedQuestion] = []
        legacy_questions: List[ExtractedQuestion] = []

        rec_count = 0
        comp_count = 0
        app_count = 0
        high_count = 0

        for idx, (start_pos, end_pos, q_num, raw_label) in enumerate(boundary_spans):
            raw_chunk = question_corpus[start_pos:end_pos]
            # Chặn nếu trong chunk có dấu hiệu kết thúc đề hoặc tiêu đề PHẦN mới nằm ở cuối chunk
            chunk = cls._trim_trailing_section_headers(raw_chunk)

            section_hint = 0
            if p1_pos != -1 and start_pos >= p1_pos and (p2_pos == -1 or start_pos < p2_pos) and (p3_pos == -1 or start_pos < p3_pos):
                section_hint = 1
            elif p2_pos != -1 and start_pos >= p2_pos and (p3_pos == -1 or start_pos < p3_pos):
                section_hint = 2
            elif p3_pos != -1 and start_pos >= p3_pos:
                section_hint = 3

            # Phân tích chi tiết câu hỏi
            std_q, leg_q, q_warns = cls._build_question_pair(
                seq_index=idx + 1,
                q_num=q_num,
                raw_label=raw_label,
                chunk=chunk,
                section_hint=section_hint,
                subject=subject,
                explicit_ans=answer_keys.get(q_num),
                trailing_has_solutions=trailing_has_solutions,
                file_name=file_name,
                blocks=blocks,
            )
            warnings.extend(q_warns)

            cog_level = leg_q.cognitive_level
            if cog_level == CognitiveLevel.RECOGNITION:
                rec_count += 1
            elif cog_level == CognitiveLevel.COMPREHENSION:
                comp_count += 1
            elif cog_level == CognitiveLevel.APPLICATION:
                app_count += 1
            else:
                high_count += 1

            std_questions.append(std_q)
            legacy_questions.append(leg_q)

        # Kiểm tra tính liên tục của số thứ tự câu hỏi (Sequence Continuity Check)
        if len(std_questions) >= 2:
            nums = [q.number for q in std_questions]
            seen_nums: Dict[int, int] = {}
            for q in std_questions:
                seen_nums[q.number] = seen_nums.get(q.number, 0) + 1
                if seen_nums[q.number] > 1 and q.number != 1:
                    w = ParseWarning(
                        code="DUPLICATE_QUESTION_NUMBER",
                        message=f"Số thứ tự câu hỏi {q.number} xuất hiện nhiều lần ({seen_nums[q.number]} lần).",
                        severity=WarningSeverity.INFO,
                        question_id=q.id,
                        reason="Tài liệu có thể chia làm nhiều Phần (Phần I, II, III) đánh số lại từ Câu 1 hoặc bị trùng số câu.",
                    )
                    q.warnings.append(w)
                    warnings.append(w)

            for k in range(len(nums) - 1):
                cur_n, nxt_n = nums[k], nums[k + 1]
                # Nếu số câu nhảy cóc trong cùng một phần (ví dụ: Câu 2 -> Câu 4, thiếu Câu 3)
                if nxt_n > cur_n + 1 and (nxt_n - cur_n) <= 5:
                    missing = list(range(cur_n + 1, nxt_n))
                    warnings.append(
                        ParseWarning(
                            code="MISSING_QUESTION_SEQUENCE",
                            message=f"Dãy câu hỏi bị khuyết số thứ tự {missing} giữa Câu {cur_n} và Câu {nxt_n}.",
                            severity=WarningSeverity.WARNING,
                            question_id=std_questions[k].id,
                            reason="Có thể câu hỏi bị mất dấu ngắt dòng hoặc bị đánh số sai trong đề gốc.",
                            requires_manual_review=True,
                        )
                    )

        total_q = max(1, len(legacy_questions))
        difficulty_score = (
            rec_count * 2.0 + comp_count * 4.5 + app_count * 7.0 + high_count * 9.5
        ) / total_q
        difficulty_score = max(1.0, min(10.0, round(difficulty_score, 1)))

        breakdown = CognitiveBreakdown(
            recognition_count=rec_count,
            comprehension_count=comp_count,
            application_count=app_count,
            high_application_count=high_count,
            estimated_difficulty_index=difficulty_score,
        )

        return std_questions, legacy_questions, breakdown, warnings

    @classmethod
    def _split_exam_and_answer_section(cls, text: str) -> Tuple[str, str]:
        """Tách phần thân đề thi và phần Bảng đáp án / Hướng dẫn giải ở cuối đề."""
        for m in RE_EXAM_END_OR_ANSWER_SECTION.finditer(text):
            if m.start() > 40:
                prefix = text[: m.start()]
                if RE_QUESTION_HEADING.search(prefix) or re.search(r"(?i)\b(?:câu|question|bài)\s+\d+", prefix):
                    return prefix, text[m.start():]
        return text, ""

    @staticmethod
    def _trim_trailing_section_headers(raw_chunk: str) -> str:
        """Loại bỏ tiêu đề PHẦN II / PHẦN III hoặc '--- HẾT ---' bị dính vào cuối câu hỏi trước đó."""
        chunk = raw_chunk
        # 1. Cắt tại "--- HẾT ---" hoặc "BẢNG ĐÁP ÁN"
        end_m = RE_EXAM_END_OR_ANSWER_SECTION.search(chunk)
        if end_m and end_m.start() > 12:
            chunk = chunk[: end_m.start()]

        # 2. Cắt nếu cuối chunk có dòng tiêu đề PHẦN I / PHẦN II / PHẦN III / II. TỰ LUẬN cho phần kế tiếp
        sec_m = re.search(
            r"(?im)\n\s*(?:phần\s+(?:[IVX]+|\d+|một|hai|ba|bốn)|part\s+(?:[IVX]+|\d+)|[IVX]+\.\s*(?:trắc\s+nghiệm|tự\s+luận))\b.*$",
            chunk,
        )
        if sec_m and sec_m.start() > 20:
            chunk = chunk[: sec_m.start()]

        return chunk.strip()

    @classmethod
    def _find_question_boundaries(cls, question_corpus: str) -> List[Tuple[int, int, int, str]]:
        """
        Nhận diện ranh giới bắt đầu câu hỏi với bộ lọc ngữ cảnh âm (Phần IV - Mục 8):
        - Loại trừ dòng Mục lục (Table of Contents có ".... 12")
        - Loại trừ tham chiếu giữa câu ("xem Câu 1", "theo Bài 2")
        - Loại trừ "Câu X" nằm bên trong phần "Lời giải:" của câu trước đó
        Trả về danh sách: [(start_pos, end_pos, question_number, raw_label)]
        """
        raw_matches = list(RE_QUESTION_HEADING.finditer(question_corpus))

        if not raw_matches:
            fallback_pat = re.compile(
                r"(?im)(?:^|\n)\s*(?P<label>(?:câu(?:\s+hỏi)?|cau|bài(?:\s+tập)?|bai|question|problem|task|exercise)\s+(?P<num>\d{1,3}))\s*(?:[.:)/]|[-–—]|\(\d)"
            )
            raw_matches = list(fallback_pat.finditer(question_corpus))

        if not raw_matches:
            inline_pat = re.compile(r"(?i)(?:^|[\s;])((?:câu|cau|bài|bai|question)\s+(\d{1,3}))\s*[:.)]\s+")
            inline_m = list(inline_pat.finditer(question_corpus))
            if len(inline_m) >= 2:
                raw_matches = inline_m

        if not raw_matches:
            numbered_pat = re.compile(r"(?:^|\n)\s*(\d{1,3})[.)]\s+(?=[^\n\r]{4,})")
            pot = list(numbered_pat.finditer(question_corpus))
            if len(pot) >= 2:
                first_nums = [int(p.group(1)) for p in pot[:8] if p.group(1).isdigit()]
                if first_nums and (1 in first_nums or first_nums[0] <= 5):
                    raw_matches = pot

        if not raw_matches:
            wf_pat = re.compile(r"(?:^|\n)\s*(?:(\d{1,3})[.)]\s*)?.*?[_.]{3,}.*?\(([a-zA-Z\s/\-]{2,25})\)")
            wf_m = list(wf_pat.finditer(question_corpus))
            if len(wf_m) >= 3:
                raw_matches = wf_m

        if not raw_matches:
            return []

        valid_entries: List[Tuple[int, int, str]] = []  # (start_pos, q_num, label)
        seen_starts: set[int] = set()

        for idx, m in enumerate(raw_matches):
            st = m.start()
            # Nếu match bắt đầu bằng \n, khoảng trắng hoặc dấu '|', dịch start_pos tới ký tự chữ/số đầu tiên của nhãn
            full_m_str = m.group(0)
            leading_ws = len(full_m_str) - len(full_m_str.lstrip(" \t\r\n|*_#-•"))
            actual_start = st + leading_ws
            if actual_start in seen_starts:
                continue

            # Lấy dòng chứa match để kiểm tra TOC và ngữ cảnh trước đó
            line_start = question_corpus.rfind("\n", 0, actual_start) + 1
            line_end = question_corpus.find("\n", actual_start)
            if line_end == -1:
                line_end = len(question_corpus)
            current_line = question_corpus[line_start:line_end].strip()

            # Guard 1: Bỏ qua dòng Mục lục có dấu chấm dẫn tới số trang ("Bài 1: Mệnh đề ........ 5")
            if RE_TOC_DOTTED_LINE.search(current_line):
                continue

            # Guard 2: Bỏ qua nếu phía trước ngay trên cùng dòng là từ tham chiếu ("xem Câu 1", "ở Bài 2")
            prefix_on_line = question_corpus[line_start:actual_start]
            if prefix_on_line.strip():
                if RE_PRECEDING_REF_GUARD.search(prefix_on_line):
                    continue
                # Nếu không phải ở đầu dòng và không phải sau dấu chấm câu/chấm phẩy/cột bảng thì bỏ qua
                if not re.search(r"(?:[.;:|]\s*|\s{3,})$", prefix_on_line):
                    continue

            # Xác định số thứ tự câu hỏi và nhãn gốc
            q_num = idx + 1
            if "num" in m.groupdict() and m.group("num"):
                q_num = int(m.group("num"))
            elif m.lastindex:
                for g_i in range(1, m.lastindex + 1):
                    g_val = m.group(g_i)
                    if g_val and g_val.isdigit():
                        q_num = int(g_val)
                        break

            if q_num > 500:
                continue

            label_match = re.match(
                r"(?i)^((?:câu(?:\s+hỏi)?|cau|bài(?:\s+tập)?|bai|question|problem|task|exercise)\s+\d{1,3}|\d{1,3})",
                question_corpus[actual_start : min(len(question_corpus), actual_start + 35)].strip(),
            )
            raw_label = label_match.group(1) if label_match else f"Câu {q_num}"

            seen_starts.add(actual_start)
            valid_entries.append((actual_start, q_num, raw_label))

        if not valid_entries:
            return []

        spans: List[Tuple[int, int, int, str]] = []
        for i, (st, q_num, lbl) in enumerate(valid_entries):
            ed = valid_entries[i + 1][0] if i + 1 < len(valid_entries) else len(question_corpus)
            spans.append((st, ed, q_num, lbl))

        return spans

    @classmethod
    def _build_question_pair(
        cls,
        seq_index: int,
        q_num: int,
        raw_label: str,
        chunk: str,
        section_hint: int,
        subject: Optional[str],
        explicit_ans: Optional[str],
        trailing_has_solutions: bool,
        file_name: str,
        blocks: Optional[List[DocumentBlock]] = None,
    ) -> Tuple[StandardizedQuestion, ExtractedQuestion, List[ParseWarning]]:
        """Phân tích một chunk câu hỏi thành cả StandardizedQuestion và ExtractedQuestion."""
        q_warnings: List[ParseWarning] = []
        q_id = f"q_{seq_index:03d}"

        # 1. Tách phần Lời giải / Hướng dẫn giải nếu nằm ngay dưới câu hỏi
        solution_text: Optional[str] = None
        has_solution = False
        sol_match = RE_QUESTION_SOLUTION_SPLIT.search(chunk)
        if sol_match:
            has_solution = True
            question_body = chunk[: sol_match.start()].strip()
            solution_text = chunk[sol_match.end() :].strip()
            if not question_body:
                question_body = chunk
        else:
            question_body = chunk
            has_solution = bool(re.search(r"(?i)\b(?:lời\s*giải|hướng\s*dẫn\s*giải|giải\s*chi\s*tiết)\b", chunk))

        # Tìm đáp án tường minh trong solution_text nếu chưa có trong bảng đáp án
        resolved_answer = explicit_ans
        if not resolved_answer and solution_text:
            ans_m = RE_INLINE_EXPLICIT_ANSWER.search(solution_text)
            if ans_m:
                resolved_answer = ans_m.group(1).upper()
            else:
                short_m = RE_INLINE_SHORT_ANSWER.search(solution_text)
                if short_m:
                    resolved_answer = short_m.group(1)

        # 2. Thang điểm của câu hỏi (ví dụ: "(1,0 điểm)", "[0.5 đ]")
        score_points: Optional[float] = None
        pts_match = RE_QUESTION_POINTS.search(question_body)
        if pts_match:
            try:
                score_points = float(pts_match.group(1).replace(",", "."))
            except (ValueError, IndexError):
                score_points = None

        has_figure_or_graph = bool(RE_FIGURE_GRAPH_CUE.search(chunk))
        has_table_data = bool(RE_TABLE_CUE.search(chunk)) or ("|" in question_body and "---" in question_body)

        # 3. Trích xuất danh sách phương án lựa chọn (OptionItem), mệnh đề Đúng/Sai (StatementItem),
        #    chỗ trống (BlankSlot), cột nối (matching_columns) và cây ý nhỏ (SubQuestionNode)
        option_items, options_dict, first_opt_pos = cls._extract_options(question_body, file_name)
        statement_items, legacy_sub_items, sub_nodes, first_sub_pos = cls._extract_statements_and_subquestions(
            question_body, q_id, section_hint, has_options=bool(option_items), file_name=file_name
        )

        # Xác định phần dẫn câu hỏi (stem) trước các phương án hoặc ý con
        if option_items and first_opt_pos > 0:
            raw_stem = question_body[:first_opt_pos].strip()
        elif (statement_items or sub_nodes) and first_sub_pos > 0:
            raw_stem = question_body[:first_sub_pos].strip()
        else:
            raw_stem = question_body.strip()

        # Làm sạch nhãn "Câu 1." ở đầu stem và tách chỉ dẫn riêng (instructions) nếu có
        clean_stem, instructions = cls._clean_stem_and_extract_instructions(raw_stem)

        # Trích xuất chỗ trống điền khuyết (BlankSlot) mà vẫn GIỮ NGUYÊN ký hiệu chỗ trống trong clean_stem
        blank_slots = cls._extract_blank_slots(clean_stem)

        # Trích xuất 2 cột nối (Matching columns) nếu là câu hỏi ghép đôi
        matching_cols = cls._extract_matching_columns(question_body)

        # 4. Phân loại CanonicalQuestionType xác định theo tín hiệu đa chiều
        canonical_type = cls._classify_canonical_question_type(
            stem=clean_stem,
            full_body=question_body,
            option_items=option_items,
            statement_items=statement_items,
            blank_slots=blank_slots,
            matching_cols=matching_cols,
            sub_nodes=sub_nodes,
            section_hint=section_hint,
            resolved_answer=resolved_answer,
            has_table_data=has_table_data,
        )

        # Ánh xạ đáp án Đúng/Sai tường minh vào từng StatementItem nếu có
        if canonical_type == CanonicalQuestionType.TRUE_FALSE and resolved_answer and statement_items:
            cls._bind_true_false_answers(statement_items, resolved_answer)

        # 5. Kiểm tra cảnh báo chất lượng câu hỏi và tính điểm QuestionConfidence
        conf = QuestionConfidence(
            structure=0.92,
            content=0.94,
            association=1.0,
            question_type=0.90,
            signals=[f"label:{raw_label}", f"type:{canonical_type.value}"],
        )

        if not clean_stem:
            conf.structure = 0.45
            conf.content = 0.40
            q_warnings.append(
                ParseWarning(
                    code="EMPTY_QUESTION_STEM",
                    message=f"{raw_label} có phần dẫn (stem) trống.",
                    severity=WarningSeverity.WARNING,
                    question_id=q_id,
                    reason="Không tìm thấy nội dung câu hỏi trước danh sách phương án.",
                    requires_manual_review=True,
                )
            )

        if canonical_type in (
            CanonicalQuestionType.SINGLE_CHOICE,
            CanonicalQuestionType.MULTIPLE_CHOICE,
            CanonicalQuestionType.CHOICE_UNKNOWN,
        ):
            opt_cnt = len(option_items)
            if opt_cnt >= 4:
                conf.option_parsing = 0.96
            elif opt_cnt in (2, 3):
                conf.option_parsing = 0.78
                if section_hint == 1 and opt_cnt < 4:
                    q_warnings.append(
                        ParseWarning(
                            code="INCOMPLETE_MCQ_OPTIONS",
                            message=f"{raw_label} chỉ trích xuất được {opt_cnt} phương án ({[o.marker for o in option_items]}).",
                            severity=WarningSeverity.WARNING,
                            question_id=q_id,
                            reason="Một số phương án có thể bị mất nhãn A/B/C/D hoặc nằm trong ảnh công thức.",
                            requires_manual_review=True,
                        )
                    )
            else:
                conf.option_parsing = 0.35
                conf.structure = 0.50

            # Kiểm tra phương án trống nội dung
            for opt in option_items:
                if not opt.text.strip():
                    conf.option_parsing = min(conf.option_parsing or 0.5, 0.45)
                    q_warnings.append(
                        ParseWarning(
                            code="EMPTY_OPTION_TEXT",
                            message=f"Phương án {opt.marker} của {raw_label} bị trống nội dung.",
                            severity=WarningSeverity.WARNING,
                            question_id=q_id,
                            requires_manual_review=True,
                        )
                    )

            # Kiểm tra tính hợp lệ của đáp án gắn với danh sách phương án
            if resolved_answer:
                valid_markers = {o.marker.upper() for o in option_items}
                ans_letters = [ch for ch in resolved_answer.upper() if "A" <= ch <= "F"]
                if ans_letters and valid_markers and not set(ans_letters).issubset(valid_markers):
                    conf.answer_key_association = 0.30
                    q_warnings.append(
                        ParseWarning(
                            code="ANSWER_KEY_OPTION_MISMATCH",
                            message=f"Đáp án '{resolved_answer}' của {raw_label} không nằm trong tập phương án {sorted(valid_markers)}.",
                            severity=WarningSeverity.WARNING,
                            question_id=q_id,
                            requires_manual_review=True,
                        )
                    )
                else:
                    conf.answer_key_association = 0.98

        conf.compute_level()
        status = "needs_review" if (conf.level == "low" or any(w.requires_manual_review for w in q_warnings)) else "parsed"

        # 6. Truy vết SourceReference từ danh sách DocumentBlock (nếu có)
        source_refs, spans_multi_pages = cls._resolve_source_references(chunk, clean_stem, file_name, blocks)
        if spans_multi_pages:
            conf.signals.append("cross_page_merged")

        topic_domain = cls.detect_topic_domain(clean_stem or question_body, subject=subject)
        cog_level = cls._estimate_cognitive_level(chunk)

        std_q = StandardizedQuestion(
            id=q_id,
            number=q_num,
            label=raw_label,
            type=canonical_type,
            raw_text=chunk,
            stem=clean_stem,
            instructions=instructions,
            options=option_items,
            statements=statement_items,
            blanks=blank_slots,
            matching_columns=matching_cols,
            sub_questions=sub_nodes,
            answer=resolved_answer,
            solution_text=solution_text,
            score_points=score_points,
            topic_domain=topic_domain,
            cognitive_level=cog_level.value,
            spans_multiple_pages=spans_multi_pages,
            source_refs=source_refs,
            confidence=conf,
            status=status,
            warnings=q_warnings,
        )

        # Tạo đối tượng ExtractedQuestion tương thích ngược 100%
        legacy_q_type = canonical_type.to_legacy_type()
        leg_q = ExtractedQuestion(
            question_index=q_num,
            label=f"Câu {q_num}",
            prompt=clean_stem,
            options=options_dict,
            sub_questions=legacy_sub_items,
            question_type=legacy_q_type,
            cognitive_level=cog_level,
            detected_answer=resolved_answer,
            has_solution_text=has_solution or trailing_has_solutions,
            solution_text=solution_text,
            score_points=score_points,
            has_figure_or_graph=has_figure_or_graph,
            has_table_data=has_table_data,
            topic_domain=topic_domain,
        )

        return std_q, leg_q, q_warnings

    @classmethod
    def _extract_options(
        cls,
        question_body: str,
        file_name: str,
    ) -> Tuple[List[OptionItem], Dict[str, str], int]:
        """
        Trích xuất các phương án lựa chọn (2 đến 6 phương án A..F):
        - Hỗ trợ A., A), (A), A:
        - Bảo vệ chống nhận nhầm chữ cái A, B, C trong đề bài hình học/hóa học bằng kiểm tra thứ tự chữ cái bắt đầu từ A.
        """
        raw_matches = list(RE_FLEX_OPTION.finditer(question_body))
        if len(raw_matches) < 2:
            raw_matches = list(RE_MCQ_FOUR_OPTIONS.finditer(question_body))
            if len(raw_matches) < 2:
                return [], {}, -1

        # Tìm chuỗi phương án bắt đầu từ 'A' và tăng dần liên tục (A -> B -> C -> D -> E -> F)
        best_chain: List[ Tuple[str, str, int] ] = []
        for start_i, m in enumerate(raw_matches):
            letter = (m.group(1) or m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)).upper()
            if letter != "A":
                continue
            # Không nhận 'A' nếu nó nằm ngay ở ký tự đầu tiên của cả câu hỏi (chưa có stem)
            if m.start() < 6:
                continue

            chain: List[Tuple[str, str, int]] = []
            expected_ord = ord("A")
            for sub_m in raw_matches[start_i:]:
                if sub_m.lastindex and sub_m.lastindex >= 3:
                    ltr = (sub_m.group(1) or sub_m.group(2)).upper()
                    txt_raw = sub_m.group(3)
                else:
                    ltr = sub_m.group(1).upper()
                    txt_raw = sub_m.group(2)

                if ord(ltr) == expected_ord:
                    chain.append((ltr, txt_raw, sub_m.start()))
                    expected_ord += 1
                elif ord(ltr) == expected_ord + 1 and len(chain) >= 2:
                    # Cho phép trường hợp khuyết 1 phương án giữa chừng (ví dụ A, B, D)
                    chain.append((ltr, txt_raw, sub_m.start()))
                    expected_ord = ord(ltr) + 1

            if len(chain) > len(best_chain):
                best_chain = chain

        if len(best_chain) < 2:
            return [], {}, -1

        option_items: List[OptionItem] = []
        options_dict: Dict[str, str] = {}
        first_pos = best_chain[0][2]

        for ltr, raw_opt_txt, _ in best_chain:
            clean_opt = re.sub(r"[\s|]+$", "", raw_opt_txt).strip()
            is_multi = "\n" in clean_opt
            has_math = LayoutAnalyzer.contains_math_expression(clean_opt)
            option_items.append(
                OptionItem(
                    marker=ltr,
                    raw_text=raw_opt_txt.strip(),
                    text=clean_opt,
                    is_multiline=is_multi,
                    contains_formula=has_math,
                    source_ref=SourceReference(
                        file_name=file_name,
                        extraction_method="context_option_parser",
                    ),
                )
            )
            options_dict[ltr] = clean_opt

        return option_items, options_dict, first_pos

    @classmethod
    def _extract_statements_and_subquestions(
        cls,
        question_body: str,
        parent_id: str,
        section_hint: int,
        has_options: bool,
        file_name: str,
    ) -> Tuple[List[StatementItem], List[str], List[SubQuestionNode], int]:
        """
        Trích xuất:
        - Mệnh đề Đúng/Sai (StatementItem) khi câu hỏi thuộc Phần II hoặc có tín hiệu Đúng/Sai.
        - Cây câu hỏi con nhiều tầng (SubQuestionNode: a), b) -> i), ii)) khi là bài toán tự luận có nhiều ý nhỏ.
        """
        if has_options:
            return [], [], [], -1

        lower_matches = list(RE_LOWER_SUBITEM.finditer(question_body))
        if not lower_matches:
            tf_fallback = list(RE_TRUE_FALSE_SUBITEMS.finditer(question_body))
            if not tf_fallback:
                return [], [], [], -1
            lower_matches = tf_fallback

        # Kiểm tra xem chuỗi bắt đầu từ 'a'
        valid_matches = []
        for m in lower_matches:
            if m.lastindex and m.lastindex >= 3:
                ltr = (m.group(1) or m.group(2)).lower()
                body = m.group(3)
            else:
                ltr = m.group(1).lower()
                body = m.group(2)
            valid_matches.append((ltr, body, m.start()))

        if not valid_matches or valid_matches[0][0] != "a":
            return [], [], [], -1

        first_pos = valid_matches[0][2]
        is_true_false_context = (
            section_hint == 2
            or len(valid_matches) == 4
            and bool(
                re.search(
                    r"(?i)\b(?:đúng\s+hay\s+sai|mỗi\s+ý\s+a\s*,\s*b\s*,\s*c\s*,\s*d|chọn\s+đúng\s+hoặc\s+sai|"
                    r"xét\s+tính\s+đúng\s+sai|phát\s+biểu\s+sau\s+đây\s+đúng\s+hay\s+sai|phần\s+ii)\b",
                    question_body,
                )
            )
            or (len(valid_matches) == 4 and not re.search(r"(?i)\b(?:tính|chứng\s+minh|giải\s+phương\s+trình|rút\s+gọn)\b", valid_matches[0][1]))
        )

        statements: List[StatementItem] = []
        legacy_subs: List[str] = []
        sub_nodes: List[SubQuestionNode] = []

        for idx, (ltr, raw_sub_body, _) in enumerate(valid_matches):
            clean_sub = re.sub(r"[\s|]+$", "", raw_sub_body).strip()
            legacy_subs.append(f"{ltr}) {clean_sub}")

            if is_true_false_context:
                statements.append(
                    StatementItem(
                        marker=ltr,
                        raw_text=raw_sub_body.strip(),
                        text=clean_sub,
                        explicit_answer=None,  # Tuyệt đối không tự đoán Đ/S khi chưa có đáp án tường minh
                        source_ref=SourceReference(file_name=file_name, extraction_method="tf_statement_parser"),
                    )
                )
            else:
                # Phân tích ý nhỏ cấp 2: i), ii), iii) bên trong ý a), b)
                child_nodes: List[SubQuestionNode] = []
                roman_matches = list(RE_ROMAN_SUBITEM.finditer(clean_sub))
                sub_stem = clean_sub
                if roman_matches and len(roman_matches) >= 2:
                    sub_stem = clean_sub[: roman_matches[0].start()].strip()
                    for c_idx, rm in enumerate(roman_matches):
                        r_marker = (rm.group(1) or rm.group(2)).lower()
                        r_body = rm.group(3).strip()
                        child_nodes.append(
                            SubQuestionNode(
                                sub_id=f"{parent_id}_{ltr}_{r_marker}",
                                marker=r_marker,
                                raw_text=r_body,
                                stem=r_body,
                                type=cls._infer_subquestion_type(r_body),
                            )
                        )

                sub_pts: Optional[float] = None
                pts_m = RE_QUESTION_POINTS.search(sub_stem)
                if pts_m:
                    try:
                        sub_pts = float(pts_m.group(1).replace(",", "."))
                    except ValueError:
                        pass

                sub_nodes.append(
                    SubQuestionNode(
                        sub_id=f"{parent_id}_{ltr}",
                        marker=ltr,
                        raw_text=raw_sub_body.strip(),
                        stem=sub_stem,
                        type=cls._infer_subquestion_type(sub_stem),
                        score_points=sub_pts,
                        children=child_nodes,
                        source_ref=SourceReference(file_name=file_name, extraction_method="subquestion_tree_parser"),
                    )
                )

        return statements, legacy_subs, sub_nodes, first_pos

    @staticmethod
    def _infer_subquestion_type(text: str) -> CanonicalQuestionType:
        if re.search(r"(?i)\b(?:chứng\s+minh|chứng\s+tỏ)\b", text):
            return CanonicalQuestionType.PROOF
        if re.search(r"(?i)\b(?:tính|tìm|giải\s+phương\s+trình|rút\s+gọn|xác\s+định\s+giá\s+trị)\b", text):
            return CanonicalQuestionType.CALCULATION
        return CanonicalQuestionType.ESSAY

    @staticmethod
    def _clean_stem_and_extract_instructions(raw_stem: str) -> Tuple[str, Optional[str]]:
        """
        Làm sạch nhãn 'Câu 1.' ở đầu stem và tách riêng phần chỉ dẫn (instructions) nếu có.
        """
        stem = re.sub(
            r"(?i)^[\s|\*\_\#\-\•]*(?:câu(?:\s+hỏi)?|cau|bài(?:\s+tập)?|bai|question|problem|task|exercise)\s+\d{1,3}(?:\s*\([^)\n]{1,25}\))?[\s*.:\)\-–—|/]+",
            "",
            raw_stem,
        ).strip()
        stem = re.sub(r"^\d{1,3}[.)]\s+", "", stem).strip()
        stem = re.sub(r"^\|\s*|\s*\|$", "", stem).strip()

        instructions: Optional[str] = None
        # Nếu câu bắt đầu bằng dòng chỉ dẫn đóng mở ngoặc hoặc kiểu "Chọn đáp án đúng nhất:"
        inst_match = re.match(
            r"(?i)^(\([^)\n]{4,80}\)|(?:chọn\s+phương\s+án\s+đúng(?:\s+nhất)?|chọn\s+tất\s+cả\s+các\s+đáp\s+án\s+đúng|"
            r"choose\s+the\s+best\s+answer|mark\s+the\s+letter\s+A,\s*B,\s*C,?\s*or\s*D)[^:\n]*[:.])\s*(.+)$",
            stem,
            re.DOTALL,
        )
        if inst_match and inst_match.group(2).strip():
            instructions = inst_match.group(1).strip()
            stem = inst_match.group(2).strip()

        return stem, instructions

    @staticmethod
    def _extract_blank_slots(stem: str) -> List[BlankSlot]:
        """
        Nhận diện các vị trí điền khuyết (BlankSlot) trong câu hỏi điền từ mà không xóa mất ký hiệu chỗ trống.
        """
        if not stem:
            return []
        slots: List[BlankSlot] = []
        for idx, m in enumerate(RE_BLANK_SLOT.finditer(stem)):
            st, ed = m.start(), m.end()
            prefix = stem[max(0, st - 35) : st].strip()
            suffix = stem[ed : min(len(stem), ed + 35)].strip()
            hint = m.group(1).strip() if m.lastindex and m.group(1) else None
            slots.append(
                BlankSlot(
                    slot_index=idx + 1,
                    raw_marker=m.group(0),
                    prefix_text=prefix,
                    suffix_text=suffix,
                    root_word_hint=hint,
                )
            )
        return slots

    @staticmethod
    def _extract_matching_columns(question_body: str) -> Optional[Dict[str, List[str]]]:
        """
        Trích xuất hai cột ghép đôi (Cột A / Cột B) nếu là câu hỏi nối cột (Matching).
        """
        if not re.search(
            r"(?i)\b(?:nối\s+cột\s+A\s+với\s+cột\s+B|ghép\s+mỗi\s+ý\s+ở\s+cột\s+A|match\s+column\s+A|cột\s+A.*cột\s+B)\b",
            question_body,
            re.DOTALL,
        ):
            return None

        col_a: List[str] = []
        col_b: List[str] = []

        # Kiểm tra nếu có bảng Markdown 2 cột | Cột A | Cột B |
        for line in question_body.splitlines():
            s = line.strip()
            if s.startswith("|") and s.endswith("|") and not re.match(r"^\|[\s\-:|]+\|$", s):
                cells = [c.strip() for c in s.split("|")[1:-1]]
                if len(cells) >= 2:
                    if re.search(r"(?i)^cột\s+[AB]|^column\s+[AB]", cells[0]):
                        continue
                    if cells[0]:
                        col_a.append(cells[0])
                    if cells[1]:
                        col_b.append(cells[1])

        if col_a and col_b:
            return {"col_a": col_a, "col_b": col_b}
        return {"col_a": [], "col_b": []}

    @classmethod
    def _classify_canonical_question_type(
        cls,
        stem: str,
        full_body: str,
        option_items: List[OptionItem],
        statement_items: List[StatementItem],
        blank_slots: List[BlankSlot],
        matching_cols: Optional[Dict[str, List[str]]],
        sub_nodes: List[SubQuestionNode],
        section_hint: int,
        resolved_answer: Optional[str],
        has_table_data: bool,
    ) -> CanonicalQuestionType:
        """Phân loại câu hỏi vào đúng 1 trong 15 giá trị của CanonicalQuestionType (Phần VIII - Mục 25)."""
        # 1. Nếu có danh sách phương án A, B, C, D...
        if len(option_items) >= 2:
            is_multi = bool(
                re.search(
                    r"(?i)\b(?:chọn\s+tất\s+cả\s+các\s+đáp\s+án\s+đúng|chọn\s+nhiều\s+đáp\s+án|"
                    r"choose\s+(?:two|three|all)|select\s+all\s+that\s+apply|có\s+thể\s+có\s+nhiều\s+hơn\s+1\s+đáp\s+án)\b",
                    full_body,
                )
            ) or bool(resolved_answer and len(re.findall(r"[A-F]", resolved_answer.upper())) >= 2)
            if is_multi:
                return CanonicalQuestionType.MULTIPLE_CHOICE
            return CanonicalQuestionType.SINGLE_CHOICE

        # 2. Nếu có danh sách mệnh đề Đúng/Sai (Phần II)
        if statement_items or section_hint == 2:
            return CanonicalQuestionType.TRUE_FALSE

        # 3. Nếu là câu hỏi nối cột (Matching)
        if matching_cols is not None:
            return CanonicalQuestionType.MATCHING

        # 4. Nếu là câu hỏi sắp xếp thứ tự (Ordering)
        if re.search(
            r"(?i)\b(?:sắp\s+xếp\s+các\s+(?:bước|sự\s+kiện|từ|câu|chất|số)|"
            r"theo\s+thứ\s+tự\s+(?:tăng\s+dần|giảm\s+dần|thời\s+gian|đúng)|"
            r"rearrange\s+the\s+following|put\s+the\s+sentences\s+in\s+the\s+correct\s+order)\b",
            stem,
        ):
            return CanonicalQuestionType.ORDERING

        # 5. Nếu là câu hỏi phân loại vào nhóm (Classification)
        if re.search(
            r"(?i)\b(?:phân\s+loại\s+các\s+(?:chất|từ|đối\s+tượng|hợp\s+chất)|"
            r"xếp\s+các\s+.*\s+vào\s+nhóm\s+thích\s+hợp|classify\s+the\s+following)\b",
            stem,
        ):
            return CanonicalQuestionType.CLASSIFICATION

        # 6. Nếu là câu hỏi hoàn thành bảng (Table Completion)
        if has_table_data and re.search(
            r"(?i)\b(?:hoàn\s+thành\s+bảng|điền\s+(?:thông\s+tin|số\s+liệu|kết\s+quả)?\s*(?:còn\s+thiếu\s+)?vào\s+bảng|complete\s+the\s+table)\b",
            stem,
        ):
            return CanonicalQuestionType.TABLE_COMPLETION

        # 7. Nếu có chỗ trống điền khuyết (Fill in the blank) mà không có lựa chọn A-D
        if blank_slots or re.search(r"(?i)\b(?:điền\s+từ\s+thích\s+hợp\s+vào\s+chỗ\s+trống|fill\s+in\s+the\s+blank)\b", stem):
            return CanonicalQuestionType.FILL_BLANK

        # 8. Nếu thuộc Phần III (Trả lời ngắn) hoặc ghi rõ trả lời ngắn
        if section_hint == 3 or re.search(
            r"(?i)\b(?:trả\s*lời\s*ngắn|điền\s*đáp\s*số|kết\s*quả\s*làm\s*tròn\s*đến)\b",
            full_body,
        ):
            return CanonicalQuestionType.SHORT_ANSWER

        # 9. Nếu là câu hỏi phức hợp có cây ý nhỏ nhiều tầng (Composite)
        if len(sub_nodes) >= 2:
            sub_types = {sn.type for sn in sub_nodes}
            if len(sub_types) >= 2 or any(sn.children for sn in sub_nodes):
                return CanonicalQuestionType.COMPOSITE

        # 10. Nếu là câu hỏi Chứng minh (Proof)
        if re.search(r"(?i)\b(?:chứng\s+minh\s+rằng|chứng\s+minh\s+đẳng\s+thức|chứng\s+minh\s+bất\s+đẳng\s+thức|chứng\s+tỏ\s+rằng|prove\s+that)\b", stem):
            return CanonicalQuestionType.PROOF

        # 11. Nếu là bài toán Tính toán / Giải phương trình (Calculation)
        if re.search(
            r"(?i)(?:\b(?:tính\s+(?:giá\s+trị|tích\s+phân|đạo\s+hàm|giới\s+hạn|diện\s+tích|thể\s+tích|chu\s+vi|độ\s+dài|khoảng\s+cách|góc|tổng|hiệu|vận\s+tốc|khối\s+lượng|nồng\s+độ)|"
            r"hãy\s+tính\b|gi[ảa?]i\s+(?:ph[ươu?]{1,2}ng\s+tr[ìi?]nh|b[ấa?]t\s+ph[ươu?]{1,2}ng\s+tr[ìi?]nh|h[ệe?]\s+ph[ươu?]{1,2}ng\s+tr[ìi?]nh)|tìm\s+x\b|rút\s+gọn\s+biểu\s+thức)\b"
            r"|\b\d*[xXyYzZ](?:\^\d+)?\s*[+\-]\s*\d*[xXyYzZ0-9].*=\s*[-+]?\d+)",
            stem,
        ):
            return CanonicalQuestionType.CALCULATION

        # 12. Nếu nằm ở Phần I mà mất các phương án A-D
        if section_hint == 1:
            return CanonicalQuestionType.CHOICE_UNKNOWN

        return CanonicalQuestionType.ESSAY

    @staticmethod
    def _bind_true_false_answers(statements: List[StatementItem], ans_str: str) -> None:
        """Gắn đáp án Đúng/Sai tường minh từ chuỗi đáp án (ví dụ: 'a-Đ, b-S, c-Đ, d-S' hoặc 'Đ-S-Đ-S')."""
        pairs = re.findall(r"(?i)([a-d])\s*[-.:)]?\s*([đds]|đúng|sai|true|false)", ans_str)
        if pairs:
            ans_by_m = {ltr.lower(): val.upper() for ltr, val in pairs}
            for st in statements:
                raw_v = ans_by_m.get(st.marker.lower())
                if raw_v:
                    st.explicit_answer = "Đ" if raw_v.startswith(("Đ", "D", "T")) else "S"
            return

        # Trường hợp chuỗi 'Đ - S - Đ - S' theo thứ tự a, b, c, d
        tokens = re.findall(r"(?i)\b([đds]|đúng|sai|true|false)\b", ans_str)
        if len(tokens) == len(statements):
            for st, tok in zip(statements, tokens):
                st.explicit_answer = "Đ" if tok.upper().startswith(("Đ", "D", "T")) else "S"

    @staticmethod
    def _resolve_source_references(
        chunk: str,
        stem: str,
        file_name: str,
        blocks: Optional[List[DocumentBlock]],
    ) -> Tuple[List[SourceReference], bool]:
        """Truy vết câu hỏi về trang và block_id trong tài liệu gốc (Phần VIII - Mục 26)."""
        if not blocks:
            return [SourceReference(file_name=file_name, page=1, extraction_method="text_stream")], False

        probe = (stem or chunk)[:35].strip()
        matched_refs: List[SourceReference] = []
        pages_touched: set[int] = set()

        for b in blocks:
            if probe and (probe in b.text or probe in b.raw_text or b.text[:30] in chunk):
                pages_touched.add(b.page)
                matched_refs.append(
                    SourceReference(
                        file_name=file_name,
                        page=b.page,
                        block_id=b.block_id,
                        bbox=b.bbox,
                        table_id=b.table_id,
                        image_id=b.image_id,
                        reading_order=b.reading_order,
                        extraction_method=b.source_type,
                    )
                )

        if not matched_refs:
            matched_refs.append(
                SourceReference(file_name=file_name, page=1, extraction_method="text_stream")
            )

        return matched_refs, len(pages_touched) > 1

    # ============================================================================
    # ANSWER KEY PARSER & MULTI-EXAM-CODE EXTRACTOR (Phần VII - Mục 22 & 23)
    # ============================================================================

    @classmethod
    def extract_answer_keys(cls, text: str) -> Dict[int, str]:
        """
        Trích xuất bảng đáp án tường minh (Phần VII - Mục 22):
        - Ưu tiên quét vùng BẢNG ĐÁP ÁN / HƯỚNG DẪN CHẤM ở cuối tài liệu trước.
        - Tuyệt đối KHÔNG quét mù quáng biểu thức "1-A" bên trong thân câu hỏi đề bài để tránh nhận nhầm!
        """
        entries, _ = cls.extract_answer_key_entries(text)
        return {q_num: entry.normalized_answer for q_num, entry in entries.items()}

    @classmethod
    def extract_answer_key_entries(
        cls,
        text: str,
        file_name: str = "document",
    ) -> Tuple[Dict[int, AnswerKeyEntry], Dict[str, Dict[int, str]]]:
        """
        Trích xuất đầy đủ AnswerKeyEntry và bảng đáp án theo từng Mã đề (exam_code).
        Trả về: (default_answer_entries, answers_by_exam_code)
        """
        entries: Dict[int, AnswerKeyEntry] = {}
        by_exam_code: Dict[str, Dict[int, str]] = {}
        if not text:
            return entries, by_exam_code

        # Tách phần đề thi và phần Bảng đáp án ở cuối đề
        _, trailing_ans_section = cls._split_exam_and_answer_section(text)

        # Kiểm tra xem toàn bộ văn bản có phải là file Đáp án độc lập hoặc chuỗi đáp án ngắn không
        has_question_stems = len(list(RE_QUESTION_HEADING.finditer(text))) >= 2 and bool(RE_MCQ_FOUR_OPTIONS.search(text))
        target_scan_text = trailing_ans_section if (trailing_ans_section and has_question_stems) else text

        # 1. Phát hiện đáp án phân theo nhiều Mã đề (ví dụ: "Mã đề 101: ... Mã đề 102: ...")
        exam_code_splits = list(
            re.finditer(r"(?im)^\s*(?:mã\s*đề(?:\s*thi)?|đề\s*số)\s*[:.]?\s*(\d{2,6})\b", target_scan_text)
        )
        if len(exam_code_splits) >= 2:
            for idx, cm in enumerate(exam_code_splits):
                code_str = cm.group(1).strip()
                seg_start = cm.end()
                seg_end = exam_code_splits[idx + 1].start() if idx + 1 < len(exam_code_splits) else len(target_scan_text)
                seg_dict = cls._scan_answer_segment(target_scan_text[seg_start:seg_end], allow_loose_pairs=True)
                if seg_dict:
                    by_exam_code[code_str] = seg_dict
                    if not entries:
                        for q_n, a_val in seg_dict.items():
                            entries[q_n] = AnswerKeyEntry(
                                question_number=q_n,
                                raw_answer=a_val,
                                normalized_answer=a_val,
                                exam_code=code_str,
                                source_ref=SourceReference(file_name=file_name, extraction_method="exam_code_answer_table"),
                            )

        # 2. Quét bảng đáp án Markdown (| Câu | Đáp án | hoặc | 1 | A |) trên toàn văn bản
        table_ans = cls._scan_markdown_answer_tables(text)
        for q_n, a_val in table_ans.items():
            if q_n not in entries:
                entries[q_n] = AnswerKeyEntry(
                    question_number=q_n,
                    raw_answer=a_val,
                    normalized_answer=a_val,
                    source_ref=SourceReference(file_name=file_name, extraction_method="markdown_answer_table"),
                )

        # 3. Quét vùng Bảng đáp án (trailing_ans_section) hoặc văn bản không chứa thân đề
        if trailing_ans_section or not has_question_stems:
            seg_ans = cls._scan_answer_segment(target_scan_text, allow_loose_pairs=True)
            for q_n, a_val in seg_ans.items():
                if q_n not in entries:
                    entries[q_n] = AnswerKeyEntry(
                        question_number=q_n,
                        raw_answer=a_val,
                        normalized_answer=a_val,
                        source_ref=SourceReference(file_name=file_name, extraction_method="answer_section_scanner"),
                    )
        else:
            # Khi không có phần Bảng đáp án tách riêng ở cuối đề và văn bản có chứa thân câu hỏi:
            # Chỉ trích xuất khi có chuỗi đáp án dày đặc (>= 3 cặp trên cùng 1 dòng như "1-A 2-B 3-C 4-D")
            # hoặc mẫu tường minh "Câu 1: A  Câu 2: B" để KHÔNG bắt nhầm "1-A" trong thân câu hỏi!
            safe_ans = cls._scan_answer_segment(text, allow_loose_pairs=False)
            for q_n, a_val in safe_ans.items():
                if q_n not in entries:
                    entries[q_n] = AnswerKeyEntry(
                        question_number=q_n,
                        raw_answer=a_val,
                        normalized_answer=a_val,
                        source_ref=SourceReference(file_name=file_name, extraction_method="dense_answer_line"),
                    )

        return entries, by_exam_code

    @classmethod
    def _scan_answer_segment(cls, segment: str, allow_loose_pairs: bool = True) -> Dict[int, str]:
        """Quét các mẫu đáp án từ một phân đoạn văn bản."""
        results: Dict[int, str] = {}
        if not segment:
            return results

        p_pair = re.compile(r"\b([1-9]|[1-9][0-9]|1[0-9]{2}|200)\s*[-.:/]\s*([A-F])\b")
        if allow_loose_pairs:
            for m in p_pair.finditer(segment):
                results[int(m.group(1))] = m.group(2).upper()
        else:
            # Chỉ nhận dòng có >= 3 cặp "1-A 2-B 3-C" hoặc dòng chỉ chứa thuần các cặp đáp án (>= 2 cặp)
            for line in segment.splitlines():
                line_matches = list(p_pair.finditer(line))
                if len(line_matches) >= 3 or (
                    len(line_matches) >= 2 and len(re.sub(r"[\d\s\-.:/A-Fa-f,;]", "", line.strip())) == 0
                ):
                    for m in line_matches:
                        results[int(m.group(1))] = m.group(2).upper()

        # Mẫu "Câu 1: A", "Câu 2: B" (chỉ nhận khi sau chữ cái A-F là khoảng trắng/dấu phẩy/xuống dòng, không phải nội dung câu hỏi)
        p_cau = re.compile(
            r"\b(?:[cC][âaÂA]u|[qQ]uestion)\s+(\d{1,3})\s*[:.-]?\s*([A-F])(?=\s*(?:[,;|]|\b(?:câu|question)\b|$|\n))"
        )
        for m in p_cau.finditer(segment):
            q_idx = int(m.group(1))
            if 1 <= q_idx <= 200 and q_idx not in results:
                results[q_idx] = m.group(2).upper()

        # Mẫu viết liền: "1A 2B 3C 4D" (>= 3 kết quả)
        p_dense = re.compile(r"\b(\d{1,3})([A-D])\b")
        dense_matches = list(p_dense.finditer(segment))
        if len(dense_matches) >= 3:
            for m in dense_matches:
                q_idx = int(m.group(1))
                if 1 <= q_idx <= 200 and q_idx not in results:
                    results[q_idx] = m.group(2).upper()

        # Mẫu Đúng/Sai Phần II: "Câu 1: a-Đ, b-S, c-Đ, d-S"
        p_tf = re.compile(
            r"(?i)(?:câu\s+)?(\d{1,3})\s*[:.-]?\s*([a-d]\s*[-.:]?\s*[đds][\s,;|]+[a-d]\s*[-.:]?\s*[đds].*?)(?=\n|\b(?:câu\s+)?\d{1,3}\s*[:.-]?\s*[a-d]|$)"
        )
        for m in p_tf.finditer(segment):
            q_idx = int(m.group(1))
            if 1 <= q_idx <= 200 and q_idx not in results:
                results[q_idx] = m.group(2).strip()

        # Mẫu Trả lời ngắn Phần III
        p_part3 = re.compile(r"(?i)(?:phần\s+iii|trả\s*lời\s*ngắn).*?(?=\n\n|\Z)", re.DOTALL)
        p3_m = p_part3.search(segment)
        if p3_m:
            p3_items = re.compile(r"(?i)(?:câu\s+)?(\d{1,3})\s*[:.-]\s*([-+]?\d+(?:[.,]\d+)?)")
            for m in p3_items.finditer(p3_m.group(0)):
                q_idx = int(m.group(1))
                if 1 <= q_idx <= 200 and q_idx not in results:
                    results[q_idx] = m.group(2)

        return results

    @classmethod
    def _scan_markdown_answer_tables(cls, text: str) -> Dict[int, str]:
        """Quét bảng đáp án định dạng Markdown (dọc, đa cột hoặc ngang)."""
        results: Dict[int, str] = {}
        table_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("|") and line.strip().endswith("|")
        ]
        content_table_lines = [l for l in table_lines if not re.match(r"^\|[\s\-:|]+\|$", l)]
        if not content_table_lines:
            return results

        re_cell_compact = re.compile(r"^(\d{1,3})\s*[-.:/]?\s*([A-F])$", re.IGNORECASE)
        re_tf_seq = re.compile(r"(?i)^(?:[a-d]\s*[-.:)]?\s*)?[đds](?:[\s,;\-|/]+(?:[a-d]\s*[-.:)]?\s*)?[đds]){1,3}$")
        re_short_num = re.compile(r"^[-+]?\d+(?:[.,]\d+)?$")

        for line in content_table_lines:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            for cell in parts:
                cm = re_cell_compact.match(re.sub(r"(?i)^(?:câu|cau|bài|bai|q)\s*", "", cell).strip())
                if cm:
                    q_idx = int(cm.group(1))
                    if 1 <= q_idx <= 200 and q_idx not in results:
                        results[q_idx] = cm.group(2).upper()

            k = 0
            while k < len(parts) - 1:
                p_num = re.sub(r"(?i)^(?:câu|cau|bài|bai|q)\s*", "", parts[k]).strip()
                if p_num.isdigit():
                    q_idx = int(p_num)
                    ans_raw = parts[k + 1].strip()
                    ans_upper = ans_raw.upper()
                    if 1 <= q_idx <= 200 and q_idx not in results:
                        if ans_upper in ("A", "B", "C", "D", "E", "F"):
                            results[q_idx] = ans_upper
                            k += 2
                            continue
                        elif re_tf_seq.match(ans_raw):
                            results[q_idx] = ans_raw
                            k += 2
                            continue
                        elif re_short_num.match(ans_raw) and not parts[k].isdigit():
                            results[q_idx] = ans_raw
                            k += 2
                            continue
                k += 1

        for i in range(len(content_table_lines) - 1):
            row1 = [p.strip() for p in content_table_lines[i].split("|")[1:-1]]
            row2 = [p.strip() for p in content_table_lines[i + 1].split("|")[1:-1]]
            if len(row1) == len(row2) and len(row1) >= 2:
                nums: List[int] = []
                is_num_row = True
                for val in row1:
                    v_clean = re.sub(r"(?i)^(?:câu|cau|bài|bai|q)\s*", "", val).strip()
                    if v_clean.isdigit() and 1 <= int(v_clean) <= 200:
                        nums.append(int(v_clean))
                    elif any(
                        k in val.lower()
                        for k in ["câu", "cau", "bài", "tt", "stt", "no", "q", "đáp án", "dap an", "mã đề", "ma de"]
                    ):
                        nums.append(-1)
                    else:
                        is_num_row = False
                        break
                if is_num_row and any(n > 0 for n in nums):
                    for q_idx, ans_val in zip(nums, row2):
                        ans_clean = ans_val.strip()
                        ans_upper = ans_clean.upper()
                        if q_idx > 0 and q_idx not in results:
                            if ans_upper in ("A", "B", "C", "D", "E", "F"):
                                results[q_idx] = ans_upper
                            elif re_tf_seq.match(ans_clean) or re_short_num.match(ans_clean):
                                results[q_idx] = ans_clean

        return results

    @classmethod
    def detect_topic_domain(cls, text: str, subject: Optional[str] = None) -> Optional[str]:
        if not text:
            return None
        subj_key = None
        if subject:
            s = str(subject).upper()
            if any(k in s for k in ["MATH", "TOAN", "TOÁN"]):
                subj_key = "MATHEMATICS"
            elif any(k in s for k in ["PHYS", "LY", "LÝ"]):
                subj_key = "PHYSICS"
            elif any(k in s for k in ["CHEM", "HOA", "HÓA"]):
                subj_key = "CHEMISTRY"
            elif any(k in s for k in ["BIO", "SINH"]):
                subj_key = "BIOLOGY"
            elif any(k in s for k in ["ENG", "ANH"]):
                subj_key = "ENGLISH"
            elif s in TOPIC_SIGNATURES:
                subj_key = s

        targets = [subj_key] if (subj_key and subj_key in TOPIC_SIGNATURES) else list(TOPIC_SIGNATURES.keys())
        for k in targets:
            for topic_name, pat in TOPIC_SIGNATURES[k]:
                if pat.search(text):
                    return topic_name
        return None

    @classmethod
    def _estimate_cognitive_level(cls, text: str) -> CognitiveLevel:
        if RE_COG_HIGH_APPLICATION.search(text):
            return CognitiveLevel.HIGH_APPLICATION
        if RE_COG_APPLICATION.search(text):
            return CognitiveLevel.APPLICATION
        if RE_COG_COMPREHENSION.search(text):
            return CognitiveLevel.COMPREHENSION
        if RE_COG_RECOGNITION.search(text):
            return CognitiveLevel.RECOGNITION
        if len(text) < 120:
            return CognitiveLevel.RECOGNITION
        return CognitiveLevel.COMPREHENSION

    @classmethod
    def extract_deep_metadata(
        cls,
        text: str,
        questions: Optional[List[ExtractedQuestion]] = None,
        subject: Optional[str] = None,
    ) -> ExamDetailedMetadata:
        """Trích xuất siêu dữ liệu sâu của đề thi 100% bằng Heuristic & Regex xác định (Zero-LLM)."""
        header_slice = text[:3500] if text else ""

        duration_minutes: Optional[int] = None
        duration_raw: Optional[str] = None
        dur_match = RE_EXAM_DURATION.search(header_slice)
        if dur_match:
            try:
                duration_minutes = int(dur_match.group(1))
                duration_raw = f"{duration_minutes} phút"
            except (ValueError, IndexError):
                pass

        exam_period: Optional[str] = None
        period_matches = list(RE_EXAM_PERIOD.finditer(header_slice))
        if period_matches:
            periods_found: List[str] = []
            for pm in period_matches:
                g = pm.groups()
                p_name: Optional[str] = None
                if g[0]:
                    p_raw = g[0].lower()
                    p_name = "Giữa học kỳ 1" if ("giữa" in p_raw or "gk" in p_raw) else "Học kỳ 1"
                elif g[1]:
                    p_raw = g[1].lower()
                    p_name = "Giữa học kỳ 2" if ("giữa" in p_raw or "gk" in p_raw) else "Học kỳ 2"
                elif g[2]:
                    p_name = "Thi thử tốt nghiệp THPT"
                elif g[3]:
                    p_name = "Khảo sát chất lượng (KSCL)"
                elif g[4]:
                    p_name = "Học sinh giỏi (HSG) / Olympic"
                elif g[5]:
                    p_name = "Tuyển sinh vào lớp 10"
                elif g[6]:
                    p_name = "Đánh giá năng lực (ĐGNL) / Đánh giá tư duy"
                else:
                    p_name = pm.group(0).strip()
                if p_name and p_name not in periods_found:
                    periods_found.append(p_name)
            if periods_found:
                exam_period = " - ".join(periods_found)

        exam_code: Optional[str] = None
        code_match = RE_EXAM_CODE.search(header_slice)
        if code_match:
            exam_code = code_match.group(1).strip()

        province: Optional[str] = None
        for prov in VIETNAM_PROVINCES:
            pat = re.compile(
                r"(?i)\b(?:sở\s*(?:gd[&]?đt|giáo\s*dục(?:\s*và\s*đào\s*tạo)?)|tỉnh|thành\s*phố|tp\.?|ubnd\s*tỉnh)\s+"
                + re.escape(prov)
                + r"\b"
            )
            if pat.search(header_slice):
                province = prov
                break
        if not province:
            first_lines = "\n".join(header_slice.splitlines()[:15])
            for prov in VIETNAM_PROVINCES:
                if re.search(r"(?i)\b" + re.escape(prov) + r"\b", first_lines):
                    province = prov
                    break

        total_score: Optional[float] = None
        score_match = RE_TOTAL_POINTS.search(header_slice)
        if score_match:
            try:
                total_score = float(score_match.group(1).replace(",", "."))
            except (ValueError, IndexError):
                pass

        moet_p1 = 0
        moet_p2 = 0
        moet_p3 = 0
        essay_cnt = 0
        has_ans = False
        has_sol = False
        topic_dist: Dict[str, int] = {}

        if questions:
            for q in questions:
                if not q.topic_domain and subject:
                    q.topic_domain = cls.detect_topic_domain(q.prompt, subject=subject)
                if q.topic_domain:
                    topic_dist[q.topic_domain] = topic_dist.get(q.topic_domain, 0) + 1
                if q.question_type == "MCQ_4":
                    moet_p1 += 1
                elif q.question_type == "TRUE_FALSE_GROUP":
                    moet_p2 += 1
                elif q.question_type == "SHORT_ANSWER":
                    moet_p3 += 1
                else:
                    essay_cnt += 1
                if q.detected_answer:
                    has_ans = True
                if q.has_solution_text or q.solution_text:
                    has_sol = True

        p1_m = RE_MOET_PART1.search(text)
        p2_m = RE_MOET_PART2.search(text)
        p3_m = RE_MOET_PART3.search(text)
        p1_pos = p1_m.start() if p1_m else -1
        p2_pos = p2_m.start() if p2_m else -1
        p3_pos = p3_m.start() if p3_m else -1

        if moet_p1 == 0 and p1_pos != -1:
            p1_end = p2_pos if p2_pos != -1 else (p3_pos if p3_pos != -1 else len(text))
            moet_p1 = len(list(re.finditer(r"(?i)\b(?:câu|cau)\s+\d+", text[p1_pos:p1_end])))
        if moet_p2 == 0 and p2_pos != -1:
            p2_end = p3_pos if p3_pos != -1 else len(text)
            moet_p2 = len(list(re.finditer(r"(?i)\b(?:câu|cau)\s+\d+", text[p2_pos:p2_end])))
        if moet_p3 == 0 and p3_pos != -1:
            moet_p3 = len(list(re.finditer(r"(?i)\b(?:câu|cau)\s+\d+", text[p3_pos:])))

        if not has_ans:
            has_ans = bool(
                re.search(r"(?i)\b(?:bảng\s*đáp\s*án|đáp\s*án|hướng\s*dẫn\s*chấm|đáp\s*số|answer\s*keys?)\b", text)
            )
        if not has_sol:
            has_sol = bool(
                re.search(
                    r"(?i)\b(?:hướng\s*dẫn\s*giải|lời\s*giải\s*chi\s*tiết|giải\s*chi\s*tiết|hướng\s*dẫn\s*chấm\s*chi\s*tiết)\b",
                    text,
                )
            )

        has_matrix = bool(
            re.search(r"(?i)\b(?:ma\s*trận(?:\s*đề\s*thi|\s*đề)?|bảng\s*đặc\s*tả|matrix|specification)\b", text)
        )

        return ExamDetailedMetadata(
            duration_minutes=duration_minutes,
            duration_raw=duration_raw,
            exam_period=exam_period,
            exam_code=exam_code,
            province=province,
            total_score=total_score,
            moet_part1_count=moet_p1,
            moet_part2_count=moet_p2,
            moet_part3_count=moet_p3,
            essay_count=essay_cnt,
            has_answer_keys=has_ans,
            has_detailed_solutions=has_sol,
            has_matrix_or_spec=has_matrix,
            topic_distribution=topic_dist,
        )
