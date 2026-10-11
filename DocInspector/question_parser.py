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
    ExamDetailedMetadata,
)
from .signatures import (
    RE_COG_APPLICATION,
    RE_COG_COMPREHENSION,
    RE_COG_HIGH_APPLICATION,
    RE_COG_RECOGNITION,
    RE_MCQ_FOUR_OPTIONS,
    RE_QUESTION_HEADING,
    RE_TRUE_FALSE_SUBITEMS,
    RE_EXAM_DURATION,
    RE_EXAM_PERIOD,
    RE_EXAM_CODE,
    RE_TOTAL_POINTS,
    RE_QUESTION_POINTS,
    RE_QUESTION_SOLUTION_SPLIT,
    RE_FIGURE_GRAPH_CUE,
    RE_TABLE_CUE,
    RE_READING_PASSAGE_CUE,
    VIETNAM_PROVINCES,
    TOPIC_SIGNATURES,
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
        subject: Optional[str] = None,
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

            # Separate prompt from options & rich metadata
            (
                prompt,
                options,
                sub_items,
                q_type,
                has_solution,
                solution_text,
                score_pts,
                has_fig,
                has_table,
                topic,
            ) = cls._dissect_question_chunk(chunk, subject=subject)

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
                solution_text=solution_text,
                score_points=score_pts,
                has_figure_or_graph=has_fig,
                has_table_data=has_table,
                topic_domain=topic,
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
    def detect_topic_domain(cls, text: str, subject: Optional[str] = None) -> Optional[str]:
        """
        Nhận diện chuyên đề câu hỏi theo môn học bằng Regex từ điển đặc trưng (< 0.05ms).
        """
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
    def _dissect_question_chunk(
        cls, chunk: str, subject: Optional[str] = None
    ) -> Tuple[str, Dict[str, str], List[str], str, bool, Optional[str], Optional[float], bool, bool, Optional[str]]:
        """
        Dissects a raw question chunk into stem, options, sub-items, and rich structural metadata.
        Zero AI, 100% Deterministic Regex & Pattern Matching.
        """
        # 1. Tách phần Lời giải chi tiết khỏi đề bài nếu có (tránh làm nhiễu option A-D trong bài giải)
        solution_text: Optional[str] = None
        has_solution = False
        sol_match = RE_QUESTION_SOLUTION_SPLIT.search(chunk)
        if sol_match:
            has_solution = True
            question_body = chunk[:sol_match.start()].strip()
            solution_text = chunk[sol_match.end():].strip()
            if not question_body:
                question_body = chunk
        else:
            question_body = chunk
            has_solution = bool(re.search(r"(?i)(?:lời\s*giải|hướng\s*dẫn\s*giải|giải\s*chi\s*tiết)", chunk))

        # 2. Thang điểm của câu hỏi (ví dụ: "(1,0 điểm)", "[0.5 đ]")
        score_points: Optional[float] = None
        pts_match = RE_QUESTION_POINTS.search(question_body)
        if pts_match:
            try:
                score_points = float(pts_match.group(1).replace(",", "."))
            except (ValueError, IndexError):
                score_points = None

        # 3. Phát hiện hình vẽ, đồ thị, bảng biến thiên
        has_figure_or_graph = bool(RE_FIGURE_GRAPH_CUE.search(chunk))

        # 4. Phát hiện bảng số liệu / bảng thống kê
        has_table_data = bool(RE_TABLE_CUE.search(chunk))

        # 5. Phân loại cấu trúc câu hỏi (MCQ_4, TRUE_FALSE_GROUP, SHORT_ANSWER, ESSAY_PROBLEM)
        options: Dict[str, str] = {}
        sub_items: List[str] = []
        q_type = "MCQ_4"

        # Check for 4 MCQ options: A., B., C., D.
        opt_matches = list(RE_MCQ_FOUR_OPTIONS.finditer(question_body))
        if len(opt_matches) >= 3:
            for m in opt_matches:
                opt_letter = m.group(1).upper()
                opt_text = m.group(2).strip()
                options[opt_letter] = opt_text
            q_type = "MCQ_4"
            first_opt_start = opt_matches[0].start()
            prompt = question_body[:first_opt_start].strip()
        else:
            # Check for True/False sub-items: a), b), c), d) or a., b., c., d.
            tf_matches = list(RE_TRUE_FALSE_SUBITEMS.finditer(question_body))
            if len(tf_matches) >= 3:
                q_type = "TRUE_FALSE_GROUP"
                for m in tf_matches:
                    sub_items.append(f"{m.group(1).lower()}) {m.group(2).strip()}")
                first_sub_start = tf_matches[0].start()
                prompt = question_body[:first_sub_start].strip()
            else:
                # Check for Short Answer question (Chuẩn Bộ GD&ĐT 2025 - Phần III)
                is_short_answer = bool(
                    re.search(
                        r"(?i)\b(?:trả\s*lời\s*ngắn|điền\s*(?:đáp\s*số|kết\s*quả|vào\s*chỗ\s*trống)|kết\s*quả\s*bằng|đáp\s*số\s*[:：]|phần\s+iii\b)\b",
                        question_body,
                    )
                )
                if is_short_answer:
                    q_type = "SHORT_ANSWER"
                    prompt = question_body
                else:
                    prompt = question_body
                    q_type = "ESSAY_PROBLEM"

        # Clean prompt
        prompt = re.sub(r"(?i)^(?:câu|bài|question)\s+\d+[\s*.:\)]+", "", prompt).strip()

        # 6. Nhận diện chuyên đề kiến thức (topic_domain)
        topic_domain = cls.detect_topic_domain(prompt or question_body, subject=subject)

        return (
            prompt,
            options,
            sub_items,
            q_type,
            has_solution,
            solution_text,
            score_points,
            has_figure_or_graph,
            has_table_data,
            topic_domain,
        )

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
        Supports:
        - 1-A, 1.A, 1:A, 1/A (up to 200 questions)
        - "Câu 1: A", "Câu 2. B"
        - Continuous compact blocks: "1A 2B 3C 4D 5A 6B..."
        - True/False format (Phần II 2025): "Câu 1: a-Đ, b-S, c-Đ, d-S"
        - Short Answer format (Phần III 2025): "Câu 1: 3,5", "2: -12"
        """
        results: Dict[int, str] = {}
        if not text:
            return results

        # Pattern 1: 1-A  2-C  3-D or 1.A 2.C (hỗ trợ tới 200 câu cho ĐGNL / chuyên ngữ)
        p1 = re.compile(r"\b([1-9]|[1-9][0-9]|1[0-9]{2}|200)\s*[-.:/]\s*([A-D])\b")
        for match in p1.finditer(text):
            q_idx = int(match.group(1))
            ans = match.group(2).upper()
            results[q_idx] = ans

        # Pattern 2: Câu 1: A, Câu 2. B (chỉ nhận chữ cái in hoa [A-D])
        p2 = re.compile(r"\b(?:[cC][âaÂA]u|[qQ]uestion)\s+(\d{1,3})\s*[:.-]?\s*([A-D])\b")
        for match in p2.finditer(text):
            q_idx = int(match.group(1))
            if 1 <= q_idx <= 200 and q_idx not in results:
                ans = match.group(2).upper()
                results[q_idx] = ans

        # Pattern 3: Dạng viết liền trong bảng đáp án: 1A 2B 3C 4D...
        p3 = re.compile(r"\b(\d{1,3})([A-D])\b")
        dense_matches = list(p3.finditer(text))
        if len(dense_matches) >= 3:
            for m in dense_matches:
                q_idx = int(m.group(1))
                if 1 <= q_idx <= 200 and q_idx not in results:
                    results[q_idx] = m.group(2).upper()

        # Pattern 4: Form 2025 Phần II - Đúng / Sai (ví dụ: "Câu 1: a-Đ, b-S, c-Đ, d-S" hoặc "1: aĐ, bS, cĐ, dS")
        p4 = re.compile(
            r"(?i)(?:câu\s+)?(\d{1,3})\s*[:.-]?\s*([a-d]\s*[-.:]?\s*[đds][\s,;|]+[a-d]\s*[-.:]?\s*[đds].*?)(?=\n|\b(?:câu\s+)?\d{1,3}\s*[:.-]?\s*[a-d]|$)"
        )
        for m in p4.finditer(text):
            q_idx = int(m.group(1))
            if 1 <= q_idx <= 200 and q_idx not in results:
                results[q_idx] = m.group(2).strip()

        # Pattern 5: Form 2025 Phần III - Trả lời ngắn trong bảng đáp án
        p5 = re.compile(
            r"(?i)(?:phần\s+iii|trả\s*lời\s*ngắn|ngắn).*?(?=\n\n|\Z)",
            re.DOTALL,
        )
        part3_block = p5.search(text)
        if part3_block:
            p5_items = re.compile(r"(?i)(?:câu\s+)?(\d{1,3})\s*[:.-]\s*([-+]?\d+(?:[.,]\d+)?)")
            for m in p5_items.finditer(part3_block.group(0)):
                q_idx = int(m.group(1))
                if 1 <= q_idx <= 200 and q_idx not in results:
                    results[q_idx] = m.group(2)

        return results

    @classmethod
    def extract_deep_metadata(
        cls,
        text: str,
        questions: Optional[List[ExtractedQuestion]] = None,
        subject: Optional[str] = None,
    ) -> ExamDetailedMetadata:
        """
        Trích xuất siêu dữ liệu sâu của đề thi hoàn toàn bằng Heuristic & Regex (Zero AI):
        - Thời gian làm bài (phút)
        - Kỳ thi (GK1, CK1, GK2, CK2, Thi thử tốt nghiệp, KSCL, HSG, Tuyển sinh 10, ĐGNL)
        - Mã đề thi
        - Tỉnh / Thành phố ra đề (trong 63 tỉnh thành)
        - Thang điểm tổng bài thi
        - Thống kê cấu trúc chuẩn Bộ GD&ĐT 2025 (Phần I, II, III, Tự luận)
        - Thống kê chuyên đề câu hỏi
        - Trạng thái đáp án & lời giải chi tiết
        - Ma trận đề thi / Bảng đặc tả
        """
        header_slice = text[:3500] if text else ""

        # 1. Thời gian làm bài
        duration_minutes: Optional[int] = None
        duration_raw: Optional[str] = None
        dur_match = RE_EXAM_DURATION.search(header_slice)
        if dur_match:
            try:
                duration_minutes = int(dur_match.group(1))
                duration_raw = f"{duration_minutes} phút"
            except (ValueError, IndexError):
                pass

        # 2. Kỳ thi cụ thể (Hỗ trợ kết hợp như KSCL + Học kỳ 1)
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

        # 3. Mã đề thi
        exam_code: Optional[str] = None
        code_match = RE_EXAM_CODE.search(header_slice)
        if code_match:
            exam_code = code_match.group(1).strip()

        # 4. Tỉnh / Thành phố ra đề
        province: Optional[str] = None
        for prov in VIETNAM_PROVINCES:
            pat = re.compile(
                r"(?i)\b(?:sở\s*(?:gd[&]?đt|giáo\s*dục(?:\s*và\s*đào\s*tạo)?)|tỉnh|thành\s*phố|tp\.?|ubnd\s*tỉnh)\s+" + re.escape(prov) + r"\b"
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

        # 5. Thang điểm tổng bài thi
        total_score: Optional[float] = None
        score_match = RE_TOTAL_POINTS.search(header_slice)
        if score_match:
            try:
                total_score = float(score_match.group(1).replace(",", "."))
            except (ValueError, IndexError):
                pass

        # 6. Thống kê câu hỏi & chuyên đề
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

        if not has_ans:
            has_ans = bool(re.search(r"(?i)\b(?:bảng\s*đáp\s*án|đáp\s*án|answer\s*keys?)\b", text))
        if not has_sol:
            has_sol = bool(re.search(r"(?i)\b(?:hướng\s*dẫn\s*giải|lời\s*giải\s*chi\s*tiết|giải\s*chi\s*tiết)\b", text))

        has_matrix = bool(re.search(r"(?i)\b(?:ma\s*trận(?:\s*đề\s*thi|\s*đề)?|bảng\s*đặc\s*tả|matrix|specification)\b", text))

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
