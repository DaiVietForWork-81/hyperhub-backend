import unittest
import tempfile
import os
from pathlib import Path

from services.doc_service import DocumentService, DocumentAnalysisResult
from cogs.doc_intake import format_bytes_to_human


class TestDocumentIntake(unittest.TestCase):
    def test_safe_url_validation(self):
        # Valid URLs
        safe, _ = DocumentService.is_safe_url("https://drive.google.com/file/d/12345/view")
        self.assertTrue(safe)
        safe, _ = DocumentService.is_safe_url("https://codeforces.com/contest/1234")
        self.assertTrue(safe)

        # Dangerous Extension
        safe, reason = DocumentService.is_safe_url("https://example.com/malware.exe")
        self.assertFalse(safe)
        self.assertIn("nguy hại", reason)

        # Private IP / Localhost
        safe, reason = DocumentService.is_safe_url("http://127.0.0.1:8080/test")
        self.assertFalse(safe)
        self.assertTrue(any(w in reason.lower() for w in ["localhost", "nội bộ", "private"]))

        safe, reason = DocumentService.is_safe_url("http://192.168.1.1/admin")
        self.assertFalse(safe)
        self.assertIn("private", reason.lower())

    def test_format_bytes_to_human(self):
        self.assertEqual(format_bytes_to_human(500), "500 Bytes")
        self.assertEqual(format_bytes_to_human(1024 * 10), "10.0 KB")
        self.assertEqual(format_bytes_to_human(1024 * 1024 * 5.5), "5.50 MB")
        self.assertEqual(format_bytes_to_human(1024 * 1024 * 1024 * 2.3), "2.30 GB")

    def test_classify_informatics(self):
        text = """
        KỲ THI CHỌN HỌC SINH GIỎI TỈNH MÔN TIN HỌC
        Bài 1: Đếm số lượng cặp phần tử.
        Cho mảng A gồm N phần tử. Giới hạn thời gian: 1.0s, Bộ nhớ: 256MB.
        Subtask 1 (30% số điểm): N <= 1000.
        Subtask 2 (70% số điểm): Thuật toán cây phân đoạn Segment Tree O(N log N).
        """
        res = DocumentService.classify_subject(text, "Đề thi HSG Tin Học 2026")
        self.assertEqual(res["subject"], "Tin Học")
        self.assertEqual(res["icon"], "💻")
        self.assertEqual(res["channel_name"], "đề-tin")

    def test_classify_english(self):
        text = """
        PRACTICE TEST FOR NATIONAL HIGH SCHOOL EXAMINATION
        Mark the letter A, B, C, or D on your answer sheet to indicate the word whose underlined part differs from the other three.
        Question 1: A. finished  B. looked  C. stopped  D. played
        Question 2: Choose the word that differs from the rest in pronunciation.
        Reading comprehension: Read the following passage and choose the correct answer.
        """
        res = DocumentService.classify_subject(text, "English Test 2026")
        self.assertEqual(res["subject"], "Tiếng Anh")
        self.assertEqual(res["icon"], "🇬🇧")
        self.assertEqual(res["channel_name"], "đề-anh")

    def test_classify_chemistry(self):
        text = """
        ĐỀ THI THỬ TỐT NGHIỆP THPT MÔN HÓA HỌC
        Câu 1: Cho m gam kim loại Fe tác dụng hoàn toàn với dung dịch H2SO4 loãng dư.
        Sau phản ứng thu được V lít khí H2 (đktc) và dung dịch X.
        Câu 2: Thủy phân hoàn toàn este no, đơn chức, mạch hở bằng dung dịch NaOH đun nóng.
        """
        res = DocumentService.classify_subject(text, "De Thi Hoa Hoc")
        self.assertEqual(res["subject"], "Hóa Học")
        self.assertEqual(res["icon"], "🧪")
        self.assertEqual(res["channel_name"], "đề-hóa")

    def test_classify_biology(self):
        text = """
        ĐỀ THI HỌC SINH GIỎI MÔN SINH HỌC
        Câu 1: Phân tử ADN mạch kép có tỉ lệ A + T / G + X = 1.5.
        Quá trình nhân đôi NST diễn ra ở pha S của chu kỳ tế bào.
        Câu 2: Đột biến gen làm thay đổi một bộ ba trên phân tử mARN.
        """
        res = DocumentService.classify_subject(text, "De Thi Sinh Hoc")
        self.assertEqual(res["subject"], "Sinh Học")
        self.assertEqual(res["icon"], "🧬")
        self.assertEqual(res["channel_name"], "đề-sinh")

    def test_classify_mathematics(self):
        text = """
        ĐỀ KIỂM TRA ĐỊNH KỲ MÔN TOÁN HỌC LỚP 12
        Câu 1: Cho hàm số y = f(x) có đạo hàm liên tục trên R. Tìm tiệm cận đứng và cực trị.
        Câu 2: Tính tích phân I = int_0^1 (2x + 1) dx.
        Câu 3: Cho hình chóp S.ABCD có đáy là hình vuông cạnh a, thể tích khối chóp là.
        """
        res = DocumentService.classify_subject(text, "De Thi Toan")
        self.assertEqual(res["subject"], "Toán Học")
        self.assertEqual(res["icon"], "📐")
        self.assertEqual(res["channel_name"], "đề-toán")

    def test_extract_text_and_cleanup(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as f:
            f.write("Bài tập Tin Học: Thuật toán Dijkstra tìm đường đi ngắn nhất trên đồ thị.")
            tmp_name = f.name

        text, pages, f_type = DocumentService._extract_text_from_file_sync(Path(tmp_name))
        self.assertIn("Dijkstra", text)
        self.assertEqual(f_type, "TXT")

        DocumentService.cleanup_file(tmp_name)
        self.assertFalse(os.path.exists(tmp_name))


if __name__ == "__main__":
    unittest.main()
