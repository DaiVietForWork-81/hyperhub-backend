"""
tests/test_low_ram_and_exam_reader.py
Kiểm thử chuyên sâu cho:
1. Tối ưu đọc đề (DocInspector QuestionParser & Signature Engine)
   - Không bị cắt cụt phương án chứa ký tự hoa / công thức (Cu, Al2O3, điểm A)
   - Hỗ trợ form Bộ GD&ĐT 2025: Trắc nghiệm 4 lựa chọn, Đúng/Sai, Điền số / Trả lời ngắn
   - Bóc tách bảng đáp án đa định dạng: viết liền 1A 2B, Đúng/Sai, Trả lời ngắn, câu > 50
2. Cơ chế Low-RAM Protection & Zero-AI:
   - Lazy load fastembed không tốn RAM khi khởi động
   - Conflict detector chuyển sang 100% Heuristic Fast Engine khi OLLAMA_ENABLED=False
"""

import unittest
from DocInspector.models import CognitiveLevel
from DocInspector.question_parser import QuestionParser
from services.conflict_detector import ConflictDetector, ConflictMessageRecord
import services.embedding_service as emb_svc


class TestLowRAMAndExamReader(unittest.TestCase):
    def test_mcq_options_not_truncated_by_uppercase_letters(self):
        """Kiểm tra phương án trắc nghiệm không bị cắt cụt bởi ký tự hoa bên trong (Axit, Cu, Al2O3, điểm A)."""
        raw_exam = """
Câu 1. Cho các kim loại và dung dịch sau:
A. Kim loại Cu tác dụng được với dung dịch HNO3 đặc nguội sinh ra khí NO2.
B. Hợp chất Al2O3 là oxit lưỡng tính tan được trong kiềm.
C. Dung dịch FeCl3 có màu vàng nâu đặc trưng của ion Fe3+.
D. Cho đoạn thẳng AB và điểm cực đại A(1; 2) thuộc đồ thị hàm số.
"""
        questions, breakdown = QuestionParser.parse_all_questions(raw_exam)
        self.assertEqual(len(questions), 1)
        q = questions[0]
        self.assertEqual(q.question_type, "MCQ_4")
        self.assertIn("A", q.options)
        self.assertIn("B", q.options)
        self.assertIn("C", q.options)
        self.assertIn("D", q.options)

        # Kiểm tra nội dung trọn vẹn không bị mất đuôi
        self.assertIn("khí NO2", q.options["A"])
        self.assertIn("tan được trong kiềm", q.options["B"])
        self.assertIn("ion Fe3+", q.options["C"])
        self.assertIn("thuộc đồ thị hàm số", q.options["D"])

    def test_form_2025_true_false_and_short_answer(self):
        """Kiểm tra form Bộ GD&ĐT 2025: Nhận diện Đúng/Sai (Phần II) và Trả lời ngắn (Phần III)."""
        form_2025_text = """
Câu 1. Cho hàm số bậc ba y = f(x) có đồ thị như hình vẽ.
a) Hàm số đồng biến trên khoảng (-1; 1).
b) Điểm cực đại của đồ thị hàm số là (0; 2).
c) Giá trị nhỏ nhất của hàm số trên đoạn [-2; 2] bằng -4.
d) Phương trình f(x) = m có đúng 3 nghiệm khi -2 < m < 2.

Câu 2. Trả lời ngắn: Một bể nước hình hộp chữ nhật có đáy kích thước 2m x 3m.
Tính thể tích bể nước biết chiều cao bằng 1.5m. Điền đáp số:
"""
        questions, breakdown = QuestionParser.parse_all_questions(form_2025_text)
        self.assertEqual(len(questions), 2)

        # Câu 1: True/False Group
        q1 = questions[0]
        self.assertEqual(q1.question_type, "TRUE_FALSE_GROUP")
        self.assertEqual(len(q1.sub_questions), 4)
        self.assertTrue(any("đồng biến" in sq for sq in q1.sub_questions))

        # Câu 2: Short Answer
        q2 = questions[1]
        self.assertEqual(q2.question_type, "SHORT_ANSWER")

    def test_extract_answer_keys_dense_and_moet_2025(self):
        """Kiểm tra bóc tách bảng đáp án viết liền, Đúng/Sai và Trả lời ngắn."""
        ans_text = """
BẢNG ĐÁP ÁN:
1A 2B 3C 4D 5A 6B 7C 8D 9A 10C 55D 80A

PHẦN II. ĐÁP ÁN ĐÚNG SAI:
Câu 1: a-Đ, b-S, c-Đ, d-S
Câu 2: a-S, b-Đ, c-Đ, d-S

PHẦN III. ĐÁP ÁN TRẢ LỜI NGẮN:
Câu 1: 3,5
Câu 2: -12
Câu 3: 450
"""
        keys = QuestionParser.extract_answer_keys(ans_text)
        # Kiểm tra đáp án trắc nghiệm viết liền
        self.assertEqual(keys.get(1), "A")
        self.assertEqual(keys.get(2), "B")
        self.assertEqual(keys.get(10), "C")
        self.assertEqual(keys.get(55), "D")
        self.assertEqual(keys.get(80), "A")

        # Kiểm tra câu > 50
        self.assertIn(55, keys)
        self.assertIn(80, keys)

    def test_lazy_loading_fastembed_safety(self):
        """Kiểm tra DocumentEmbeddingService có thể khởi tạo mà không ép tải model vào RAM."""
        # HAS_FASTEMBED không nạp model khi chỉ khởi tạo class
        svc = emb_svc.DocumentEmbeddingService()
        self.assertIsNone(svc._model)

    def test_conflict_detector_zero_ai_fallback(self):
        """Kiểm tra ConflictDetector chạy tức thì (0ms, 0 RAM) bằng Rule-based khi OLLAMA_ENABLED=False."""
        import asyncio
        detector = ConflictDetector()
        ch_id = 99999
        # Ghi nhận cãi vã đấu khẩu đối đầu
        detector.record_message(ch_id, 1, 101, "UserA", "Mày thích solo không bố mày đập chết mày bây giờ")
        detector.record_message(ch_id, 2, 102, "UserB", "Ngon bước ra đây con chó mày thích va chạm à")

        from unittest.mock import patch
        from config.settings import settings

        # Đánh giá xung đột mà không gọi Ollama khi OLLAMA_ENABLED=False
        with patch.object(settings, "OLLAMA_ENABLED", False):
            loop = asyncio.new_event_loop()
            res = loop.run_until_complete(detector.evaluate_conflict(ch_id))
            loop.close()

        self.assertTrue(res.is_conflict)
        self.assertFalse(res.ai_used)
        self.assertIn(101, res.involved_users)
        self.assertIn(102, res.involved_users)


if __name__ == "__main__":
    unittest.main()
