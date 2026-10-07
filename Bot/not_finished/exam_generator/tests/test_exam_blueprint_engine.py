"""tests/test_exam_blueprint_engine.py
Kiểm thử toàn diện động cơ khung đề chuẩn hóa Exam Blueprint Engine.
"""

import unittest

from not_finished.exam_generator.services.exam_blueprint_engine import (
    ExamBlueprintEngine,
    QuestionType,
    STANDARD_BLUEPRINTS,
    exam_blueprint_engine,
)


class TestExamBlueprintEngine(unittest.TestCase):
    def test_standard_blueprints_loaded(self):
        """Đảm bảo các khung đề quốc gia chuẩn đã được nạp đầy đủ."""
        self.assertIn("thpt_qg_2025_toan", STANDARD_BLUEPRINTS)
        self.assertIn("thpt_qg_2025_vat_ly", STANDARD_BLUEPRINTS)
        self.assertIn("thpt_qg_2025_hoa_hoc", STANDARD_BLUEPRINTS)
        self.assertIn("thpt_qg_2025_tieng_anh", STANDARD_BLUEPRINTS)
        self.assertIn("thpt_qg_2025_ngu_van", STANDARD_BLUEPRINTS)
        self.assertIn("dgnl_hsa", STANDARD_BLUEPRINTS)
        self.assertIn("dgnl_vact", STANDARD_BLUEPRINTS)
        self.assertIn("tuyen_sinh_10_toan_chung", STANDARD_BLUEPRINTS)
        self.assertIn("chuyen_lop_10_toan", STANDARD_BLUEPRINTS)
        self.assertIn("dinh_ky_tt22_toan", STANDARD_BLUEPRINTS)

    def test_thpt_2025_toan_structure(self):
        """Kiểm tra cấu trúc 3 phần chuẩn BGDĐT 2025 môn Toán: 12 MCQ + 4 Đ/S + 6 Điền ngắn."""
        bp = ExamBlueprintEngine.get_blueprint("thpt_qg_2025_toan")
        self.assertIsNotNone(bp)
        self.assertEqual(bp.duration_minutes, 90)
        self.assertEqual(bp.total_questions, 22)
        self.assertEqual(bp.total_points, 10.0)
        self.assertEqual(len(bp.sections), 3)

        part1, part2, part3 = bp.sections
        self.assertEqual(part1.question_type, QuestionType.MCQ_SINGLE)
        self.assertEqual(part1.question_count, 12)
        self.assertEqual(part1.total_points, 3.0)

        self.assertEqual(part2.question_type, QuestionType.TRUE_FALSE_MULTISTEP)
        self.assertEqual(part2.question_count, 4)
        self.assertEqual(part2.total_points, 4.0)

        self.assertEqual(part3.question_type, QuestionType.SHORT_ANSWER)
        self.assertEqual(part3.question_count, 6)
        self.assertEqual(part3.total_points, 3.0)

    def test_true_false_score_calculation(self):
        """Kiểm tra bảng barem điểm trắc nghiệm Đúng/Sai 4 ý chuẩn Quyết định 764/BGDĐT."""
        self.assertEqual(ExamBlueprintEngine.calculate_true_false_score(0), 0.0)
        self.assertEqual(ExamBlueprintEngine.calculate_true_false_score(1), 0.10)
        self.assertEqual(ExamBlueprintEngine.calculate_true_false_score(2), 0.25)
        self.assertEqual(ExamBlueprintEngine.calculate_true_false_score(3), 0.50)
        self.assertEqual(ExamBlueprintEngine.calculate_true_false_score(4), 1.00)

    def test_find_best_match(self):
        """Kiểm tra khả năng nhận diện thông minh từ khóa kỳ thi của người dùng."""
        match_thpt = ExamBlueprintEngine.find_best_match("Thi tốt nghiệp thpt 2025", subject="Toán")
        self.assertIsNotNone(match_thpt)
        self.assertEqual(match_thpt.blueprint_id, "thpt_qg_2025_toan")

        match_hsa = ExamBlueprintEngine.find_best_match("Đánh giá năng lực HSA Hà Nội")
        self.assertIsNotNone(match_hsa)
        self.assertEqual(match_hsa.blueprint_id, "dgnl_hsa")

        match_10 = ExamBlueprintEngine.find_best_match("Thi thử vào 10 chuyên toán")
        self.assertIsNotNone(match_10)
        self.assertEqual(match_10.blueprint_id, "chuyen_lop_10_toan")

    def test_build_prompt_spec(self):
        """Kiểm tra việc sinh chuỗi đặc tả kỹ thuật đưa vào Gemma Planner."""
        spec = ExamBlueprintEngine.build_prompt_spec("thpt_qg_2025_toan", topic_context="Khảo sát hàm số & Tích phân")
        self.assertIn("CHỈ THỊ KHUNG ĐỀ CHUẨN HÓA BẮT BUỘC", spec)
        self.assertIn("PHẦN I: Câu trắc nghiệm nhiều phương án lựa chọn", spec)
        self.assertIn("PHẦN II: Câu trắc nghiệm Đúng/Sai đa ý", spec)
        self.assertIn("PHẦN III: Câu trắc nghiệm trả lời ngắn", spec)
        self.assertIn("Khảo sát hàm số & Tích phân", spec)

    def test_validate_exam_against_blueprint(self):
        """Kiểm tra chức năng thẩm định tính chuẩn hóa của đề thi."""
        valid_mock_exam = {
            "questions": [
                {
                    "id": f"q_{i}",
                    "type": "mcq",
                    "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
                    "correct_answer": "A",
                }
                for i in range(22)
            ]
        }
        res = ExamBlueprintEngine.validate_exam_against_blueprint(valid_mock_exam, "thpt_qg_2025_toan")
        self.assertTrue(res["valid"])
        self.assertEqual(res["actual_questions"], 22)


if __name__ == "__main__":
    unittest.main()
