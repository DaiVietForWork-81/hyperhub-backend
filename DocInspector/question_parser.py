"""
High-Speed Question Itemizer & Cognitive Level Analyzer.
Extracts individual questions, options, sub-items, and maps answer keys.
100% Deterministic, Zero AI.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .models import (
    CognitiveBreakdown,
    CognitiveLevel,
    ExtractedQuestion,
)
from .signatures import (
    RE_COG_APPLICATION,
    RE_COG_COMPREHENSION,
    RE_COG_HIGH_APPLICATION,
    RE_COG_RECOGNITION,
    RE_MCQ_FOUR_OPTIONS,
    RE_QUESTION_HEADING,
    RE_TRUE_FALSE_SUBITEMS,
)


class QuestionParser:
    """
    Parses and categorizes questions from raw document text.
    Operates in < 5ms for standard 50-question documents.
    """

    @classmethod
    def parse_all_questions(
        cls,
        text: str,
        answer_map: Optional[Dict[int, str]] = None,
    ) -> Tuple[List[ExtractedQuestion], CognitiveBreakdown]:
        """
        Extract all discrete questions, classify cognitive levels,
        and bind answer keys.
        """
        if not text:
            return [], CognitiveBreakdown()

        # Find question headings and their spans (hỗ trợ không dấu cho OCR)
        matches = list(RE_QUESTION_HEADING.finditer(text))
        if not matches:
            # Fallback 1: check for "Câu 1:", "Bài 1:", "Question 1:", "Exercise 1:", "Task 1:" (có/không dấu)
            fallback_pattern = re.compile(r"(?i)\b(?:câu|cau|bài|bai|question|task|part|exercise|problem)\s+(\d+)[:.]\s*")
            matches = list(fallback_pattern.finditer(text))

        if not matches:
            # Fallback 1b: inline "Câu 1." không cần newline (scan/PDF mất ngắt dòng)
            inline_pattern = re.compile(r"(?i)(?:^|[\s;])((?:câu|cau|bài|bai)\s+(\d+))\s*[:.)]\s+")
            inline_matches = list(inline_pattern.finditer(text))
            if len(inline_matches) >= 2:
                matches = inline_matches

        if not matches:
            # Fallback 2: Check for numbered exercise lines: e.g. "^1.", "^2.", "^1)"
            numbered_item_pattern = re.compile(r"(?:^|\n)\s*(\d+)[\.\)]\s+(?=[^\n\r]{4,})")
            potential = list(numbered_item_pattern.finditer(text))
            if len(potential) >= 3:
                first_nums = []
                for p in potential[:8]:
                    try:
                        first_nums.append(int(p.group(1)))
                    except ValueError:
                        pass
                if first_nums and (1 in first_nums or first_nums[0] <= 5):
                    matches = potential

        if not matches:
            # Fallback 3: Word formation / fill-in items with blanks and bracketed root words:
            # e.g. "1. She was ________ (amaze)" or "The ______ (develop) of..."
            wf_pattern = re.compile(r"(?:^|\n)\s*(?:(\d+)[\.\)]\s*)?.*?[_\.]{2,}.*?\(([a-zA-Z\s/-]{2,25})\)")
            wf_matches = list(wf_pattern.finditer(text))
            if len(wf_matches) >= 3:
                matches = wf_matches

        # Lọc trùng vị trí + validate số thứ tự (chống "Bảng 1/Hình 1" nhận nhầm thành câu hỏi)
        if matches:
            seen_starts: set[int] = set()
            deduped = []
            for m in matches:
                if m.start() not in seen_starts:
                    seen_starts.add(m.start())
                    deduped.append(m)
            matches = deduped
            # Nếu có số thứ tự, chỉ giữ dãy tăng dần hợp lý (loại outlier như "Bảng 1999")
            nums: list[int] = []
            for m in matches:
                try:
                    g = m.group(1) if m.lastindex and m.group(1) else None
                    # group(1) có thể là text dài ở wf_pattern -> bỏ qua
                    nums.append(int(g) if g is not None and g.isdigit() else -1)
                except (ValueError, IndexError):
                    nums.append(-1)
            if any(n > 0 for n in nums):
                filtered = [m for m, n in zip(matches, nums) if n == -1 or n <= 500]
                # Giữ ít nhất 1 match để không mất đề
                if filtered:
                    matches = filtered

        questions: List[ExtractedQuestion] = []
        answer_keys = answer_map or cls.extract_answer_keys(text)

        rec_count = 0
        comp_count = 0
        app_count = 0
        high_count = 0

        for i, match in enumerate(matches):
            q_num_str = match.group(1) if match.lastindex and match.group(1) else None
            try:
                q_num = int(q_num_str) if q_num_str is not None else (i + 1)
            except ValueError:
                q_num = i + 1

            start_pos = match.start()
            end_pos = matches[i + 1].start() if (i + 1) < len(matches) else len(text)
            
            # Bound question chunk to avoid swallowing entire answer tables
            chunk = text[start_pos:end_pos].strip()

            # Separate prompt from options
            prompt, options, sub_items, q_type = cls._dissect_question_chunk(chunk)

            # Estimate cognitive level
            cog_level = cls._estimate_cognitive_level(chunk)
            if cog_level == CognitiveLevel.RECOGNITION:
                rec_count += 1
            elif cog_level == CognitiveLevel.COMPREHENSION:
                comp_count += 1
            elif cog_level == CognitiveLevel.APPLICATION:
                app_count += 1
            else:
                high_count += 1

            # Answer key binding
            ans = answer_keys.get(q_num)

            has_solution = bool(re.search(r"(?i)(?:lời\s*giải|hướng\s*dẫn|giải\s*chi\s*tiết)", chunk))

            question_obj = ExtractedQuestion(
                question_index=q_num,
                label=f"Câu {q_num}",
                prompt=prompt,
                options=options,
                sub_questions=sub_items,
                question_type=q_type,
                cognitive_level=cog_level,
                detected_answer=ans,
                has_solution_text=has_solution,
            )
            questions.append(question_obj)

        total_q = max(1, len(questions))
        # Compute difficulty index (1.0 to 10.0 scale)
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

        return questions, breakdown

    @classmethod
    def _dissect_question_chunk(
        cls, chunk: str
    ) -> Tuple[str, Dict[str, str], List[str], str]:
        """
        Dissects a raw question chunk into stem, options, and sub-items.
        """
        lines = chunk.splitlines()
        first_line = lines[0] if lines else ""

        options: Dict[str, str] = {}
        sub_items: List[str] = []
        q_type = "MCQ_4"

        # Check for 4 MCQ options: A., B., C., D.
        # Find all occurrences of A., B., C., D.
        opt_matches = list(RE_MCQ_FOUR_OPTIONS.finditer(chunk))
        if len(opt_matches) >= 3:
            for m in opt_matches:
                opt_letter = m.group(1).upper()
                opt_text = m.group(2).strip()
                options[opt_letter] = opt_text
            q_type = "MCQ_4"
            # Stem is everything before the first option
            first_opt_start = opt_matches[0].start()
            prompt = chunk[:first_opt_start].strip()
        else:
            # Check for True/False sub-items: a), b), c), d)
            tf_matches = list(RE_TRUE_FALSE_SUBITEMS.finditer(chunk))
            if len(tf_matches) >= 3:
                q_type = "TRUE_FALSE_GROUP"
                for m in tf_matches:
                    sub_items.append(f"{m.group(1).lower()}) {m.group(2).strip()}")
                first_sub_start = tf_matches[0].start()
                prompt = chunk[:first_sub_start].strip()
            else:
                prompt = chunk
                q_type = "ESSAY_PROBLEM"

        # Clean prompt
        prompt = re.sub(r"(?i)^(?:câu|bài|question)\s+\d+[\s*.:\)]+", "", prompt).strip()

        return prompt, options, sub_items, q_type

    @classmethod
    def _estimate_cognitive_level(cls, text: str) -> CognitiveLevel:
        """
        Deterministically estimate cognitive level using keyword signatures
        and complexity metrics.
        """
        # 1. High Application cues (Vận dụng cao)
        if RE_COG_HIGH_APPLICATION.search(text):
            return CognitiveLevel.HIGH_APPLICATION

        # 2. Application cues (Vận dụng)
        if RE_COG_APPLICATION.search(text):
            return CognitiveLevel.APPLICATION

        # 3. Comprehension cues (Thông hiểu)
        if RE_COG_COMPREHENSION.search(text):
            return CognitiveLevel.COMPREHENSION

        # 4. Recognition cues (Nhận biết)
        if RE_COG_RECOGNITION.search(text):
            return CognitiveLevel.RECOGNITION

        # Complexity length fallback: short definitions tend to be Recognition/Comprehension
        if len(text) < 120:
            return CognitiveLevel.RECOGNITION

        return CognitiveLevel.COMPREHENSION

    @classmethod
    def extract_answer_keys(cls, text: str) -> Dict[int, str]:
        """
        Scans document for answer tables and matrices.
        e.g., 1-A 2-B 3-C or Câu 1: A, Câu 2: B
        """
        results: Dict[int, str] = {}

        # Pattern 1: 1-A  2-C  3-D or 1.A 2.C
        p1 = re.compile(r"\b([1-9]|[1-4][0-9]|50)\s*[-.:/]\s*([A-D])\b")
        for match in p1.finditer(text):
            q_idx = int(match.group(1))
            ans = match.group(2).upper()
            results[q_idx] = ans

        # Pattern 2: Câu 1: A, Câu 2. B
        p2 = re.compile(r"(?i)\bcâu\s+(\d+)\s*[:.]\s*([A-D])\b")
        for match in p2.finditer(text):
            q_idx = int(match.group(1))
            ans = match.group(2).upper()
            results[q_idx] = ans

        return results
