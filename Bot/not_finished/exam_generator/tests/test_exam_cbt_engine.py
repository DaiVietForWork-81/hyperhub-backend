"""tests/test_exam_cbt_engine.py
Kiểm thử toàn diện động cơ Thi Thử Trực Tuyến & Chấm Điểm Khảo Thí (Exam CBT Engine).
"""

import unittest

from not_finished.exam_generator.services.exam_cbt_engine import (
    ExamCBTManager,
    ExamSessionStatus,
    exam_cbt_manager,
)


class TestExamCBTEngine(unittest.TestCase):
    def setUp(self):
        self.cbt = ExamCBTManager()
        self.mock_exam_data = {
            "metadata": {
                "exam_title": "ĐỀ KIỂM TRA ĐỊNH KỲ TOÁN 12",
                "duration": "45 phút",
            },
            "questions": [
                {
                    "number": "1",
                    "type": "question",
                    "text": "Tập xác định của hàm số y = 1/x là?",
                    "options": [
                        "A. R \\ {0}",
                        "B. R",
                        "C. (0; +inf)",
                        "D. (-inf; 0)",
                    ],
                    "points": "0.5 điểm",
                },
                {
                    "number": "2",
                    "type": "question",
                    "text": "Đạo hàm của hàm số y = sin(x) là?",
                    "options": [
                        "A. -cos(x)",
                        "B. cos(x)",
                        "C. sin(x)",
                        "D. -sin(x)",
                    ],
                    "points": "0.5 điểm",
                },
            ],
            "solutions": [
                {
                    "number": "1",
                    "is_multiple_choice": True,
                    "correct_key": "A",
                    "explanation": "Mẫu số x khác 0 => D = R \\ {0}.",
                    "common_mistakes": "Quên điều kiện mẫu số khác 0.",
                },
                {
                    "number": "2",
                    "is_multiple_choice": True,
                    "correct_key": "B",
                    "explanation": "(sin x)' = cos x.",
                    "common_mistakes": "Nhầm dấu với đạo hàm của cos x.",
                },
            ],
        }

    def test_session_lifecycle(self):
        """Kiểm tra toàn bộ chu trình sống của một phiên thi trực tuyến (CREATED -> IN_PROGRESS -> COMPLETED)."""
        user_id = 99887766
        session = self.cbt.create_session(
            user_id=user_id,
            exam_data=self.mock_exam_data,
            duration_minutes=45,
        )
        self.assertIsNotNone(session)
        self.assertEqual(session.status, ExamSessionStatus.CREATED)
        self.assertEqual(session.duration_minutes, 45)

        # 1. Bắt đầu làm bài
        started_session = self.cbt.start_session(session.session_id)
        self.assertEqual(started_session.status, ExamSessionStatus.IN_PROGRESS)
        self.assertIsNotNone(started_session.started_at)
        self.assertGreater(started_session.remaining_seconds, 0)
        self.assertFalse(started_session.is_expired)

        # 2. Thí sinh trả lời câu 1: Đúng (Chọn A)
        sub1 = self.cbt.submit_answer(
            session_id=session.session_id,
            question_number="1",
            selected_key="A",
            time_spent_seconds=15.0,
        )
        self.assertEqual(sub1.selected_key, "A")
        self.assertEqual(sub1.change_count, 0)

        # 3. Thí sinh trả lời câu 2: Sai (Chọn A thay vì B)
        sub2 = self.cbt.submit_answer(
            session_id=session.session_id,
            question_number="2",
            selected_key="A",
            time_spent_seconds=20.0,
        )
        self.assertEqual(sub2.selected_key, "A")

        # 4. Thí sinh nộp bài kết thúc phiên
        report = self.cbt.finish_session(session.session_id)
        self.assertIsNotNone(report)
        self.assertEqual(session.status, ExamSessionStatus.COMPLETED)
        self.assertEqual(report.total_questions, 2)
        self.assertEqual(report.correct_count, 1)  # Đúng 1/2 câu
        self.assertAlmostEqual(report.percentage, 50.0)

        # Báo cáo sai sót phải chỉ ra câu 2 đã chọn A, đáp án đúng là B và kèm phân tích bẫy tư duy
        self.assertEqual(len(report.mistakes_analysis), 1)
        mistake = report.mistakes_analysis[0]
        self.assertEqual(mistake["question_number"], "2")
        self.assertEqual(mistake["user_selected"], "A")
        self.assertEqual(mistake["correct_key"], "B")
        self.assertIn("Nhầm dấu", mistake["trap_warning"])

    def test_cancel_session(self):
        """Kiểm tra hủy phiên thi của thí sinh."""
        session = self.cbt.create_session(
            user_id=12345,
            exam_data=self.mock_exam_data,
            duration_minutes=30,
        )
        res = self.cbt.cancel_session(session.session_id)
        self.assertTrue(res)
        self.assertEqual(session.status, ExamSessionStatus.CANCELLED)

        # Đảm bảo không còn phiên active cho user
        active = self.cbt.get_active_session(12345)
        self.assertIsNone(active)


if __name__ == "__main__":
    unittest.main()
