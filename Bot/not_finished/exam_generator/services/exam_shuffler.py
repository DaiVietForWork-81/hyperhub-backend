"""Dịch vụ xáo trộn đề thi tự nhiên sư phạm (Exam Shuffler Service).

Tính năng:
1. Tạo mã đề mới tự động (VD: HH-101 -> HH-102, HH-103...).
2. Đảo ngẫu nhiên thứ tự các câu hỏi trắc nghiệm trong cùng phân đoạn (section).
3. Đảo ngẫu nhiên vị trí các phương án A, B, C, D của từng câu trắc nghiệm.
4. Tự động đồng bộ và cập nhật lại mã đề, bảng đáp án đúng (correct_key) tương ứng 100%.
5. Xử lý tức thì (< 0.5 giây) bằng thuật toán hoán vị mà không cần gọi LLM.
"""

from __future__ import annotations

import copy
import random
import re
from typing import Any


class ExamShuffler:
    """Bộ máy xáo trộn đề thi và tái lập bảng đáp án tự nhiên."""

    @staticmethod
    def _clean_option_text(opt: str) -> str:
        """Tách nội dung phương án ra khỏi nhãn A, B, C, D ban đầu."""
        m = re.match(r"^[A-Da-d][\.\:\)\-]\s*(.*)$", opt.strip())
        return m.group(1).strip() if m else opt.strip()

    @classmethod
    def shuffle_exam(
        cls,
        exam_data: dict[str, Any],
        new_exam_code: str | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Tạo một bản sao đề thi mới đã qua xáo trộn tự nhiên chuẩn sư phạm."""
        if seed is not None:
            random.seed(seed)

        shuffled = copy.deepcopy(exam_data)
        meta = shuffled.get("metadata", {})
        old_code = meta.get("exam_code", "HH-101")

        if not new_exam_code:
            # Tự động tăng số mã đề (VD: HH-101 -> HH-102)
            m_code = re.search(r"(\d+)$", old_code)
            if m_code:
                num = int(m_code.group(1)) + random.randint(1, 9)
                prefix = old_code[: m_code.start()]
                new_exam_code = f"{prefix}{num}"
            else:
                new_exam_code = f"{old_code}-S{random.randint(10, 99)}"

        meta["exam_code"] = new_exam_code
        meta["is_shuffled"] = True
        meta["original_exam_code"] = old_code

        questions = shuffled.get("questions", [])
        solutions = shuffled.get("solutions", [])

        # Lập bản đồ tra cứu lời giải theo question number ban đầu
        sol_map: dict[str, dict[str, Any]] = {}
        for sol in solutions:
            sol_map[str(sol.get("number", ""))] = sol

        # Gom câu hỏi theo từng nhóm section để xáo trộn trong nội bộ section
        grouped_sections: list[list[dict[str, Any]]] = []
        current_group: list[dict[str, Any]] = []

        for q in questions:
            if q.get("type") == "section_header":
                if current_group:
                    grouped_sections.append(current_group)
                    current_group = []
                grouped_sections.append([q])
            else:
                current_group.append(q)

        if current_group:
            grouped_sections.append(current_group)

        # Xáo trộn từng nhóm câu hỏi trắc nghiệm
        new_questions: list[dict[str, Any]] = []
        q_counter = 1
        new_sol_list: list[dict[str, Any]] = []

        for group in grouped_sections:
            if len(group) == 1 and group[0].get("type") == "section_header":
                new_questions.append(group[0])
                continue

            # Chỉ xáo trộn vị trí các câu hỏi trắc nghiệm khách quan
            # Các câu có bài đọc chung hoặc tự luận dài có thể giữ nguyên cấu trúc
            mc_questions = [q for q in group if q.get("options")]
            other_questions = [q for q in group if not q.get("options")]

            random.shuffle(mc_questions)
            reordered_group = mc_questions + other_questions

            for q in reordered_group:
                old_num = str(q.get("number", ""))
                new_num = str(q_counter)
                q["number"] = new_num
                q_counter += 1

                sol = sol_map.get(old_num)
                if not sol:
                    # Tạo solution dự phòng nếu chưa có
                    sol = {"number": new_num, "explanation": "Xem đáp án tương ứng."}
                else:
                    sol = copy.deepcopy(sol)
                    sol["number"] = new_num

                # Đảo các phương án lựa chọn A, B, C, D
                raw_options = q.get("options", [])
                if raw_options and len(raw_options) >= 2:
                    old_correct_key = sol.get("correct_key", "A").upper().strip()
                    old_labels = ["A", "B", "C", "D", "E", "F"][: len(raw_options)]

                    # Tìm nội dung phương án đúng cũ
                    correct_content = ""
                    options_payload: list[dict[str, Any]] = []
                    for idx, opt_str in enumerate(raw_options):
                        lbl = old_labels[idx]
                        clean_content = cls._clean_option_text(opt_str)
                        is_correct = (lbl == old_correct_key)
                        if is_correct:
                            correct_content = clean_content
                        options_payload.append({
                            "clean": clean_content,
                            "is_correct": is_correct,
                        })

                    # Xáo trộn danh sách phương án
                    random.shuffle(options_payload)

                    # Gán lại nhãn mới A, B, C, D
                    new_options_str: list[str] = []
                    new_correct_key = "A"
                    for idx, item in enumerate(options_payload):
                        new_lbl = old_labels[idx]
                        new_options_str.append(f"{new_lbl}. {item['clean']}")
                        if item["is_correct"]:
                            new_correct_key = new_lbl

                    q["options"] = new_options_str
                    sol["correct_key"] = new_correct_key

                new_questions.append(q)
                new_sol_list.append(sol)

        shuffled["questions"] = new_questions
        shuffled["solutions"] = new_sol_list
        return shuffled


exam_shuffler = ExamShuffler()
