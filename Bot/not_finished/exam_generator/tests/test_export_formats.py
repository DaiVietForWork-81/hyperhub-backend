"""tests/test_export_formats.py
Kiểm thử toàn diện động cơ xuất bản đa định dạng (Azota CSV, Quizizz CSV, Anki TSV & LaTeX Source).
"""

import os
import shutil
import tempfile
import unittest

from not_finished.exam_generator.services.export_formats import export_formats_service


class TestExportFormats(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.metadata = {
            "exam_title": "ĐỀ THI THỬ THPT QUỐC GIA 2025",
            "subject": "Toán Học",
            "duration": "90 phút",
            "exam_code": "HH-TEST",
        }
        self.content_blocks = [
            {
                "type": "section_header",
                "title": "PHẦN I: TRẮC NGHIỆM KHÁCH QUAN",
            },
            {
                "type": "question",
                "number": "1",
                "text": "Cho hàm số y = f(x) có đạo hàm f'(x) = 2x. Tìm f(1) biết f(0) = 1.",
                "options": [
                    "A. 1",
                    "B. 2",
                    "C. 3",
                    "D. 4",
                ],
                "points": "0.25 điểm",
            },
        ]
        self.solution_blocks = [
            {
                "number": "1",
                "is_multiple_choice": True,
                "correct_key": "B",
                "explanation": "Ta có f(x) = x^2 + C. Vì f(0) = 1 nên C = 1 => f(1) = 1 + 1 = 2.",
                "common_mistakes": "Quên cộng hằng số tích phân C.",
            }
        ]

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_export_azota_csv(self):
        """Kiểm tra xuất file Azota CSV có UTF-8-SIG (BOM) và đúng cấu trúc cột."""
        output_file = os.path.join(self.temp_dir, "test_azota.csv")
        res_path = export_formats_service.export_azota_csv(
            self.metadata, self.content_blocks, self.solution_blocks, output_file
        )
        self.assertTrue(os.path.exists(res_path))

        with open(res_path, "rb") as f:
            raw = f.read()
            # Phải có UTF-8-SIG BOM (\xef\xbb\xbf)
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "Azota CSV bắt buộc phải có UTF-8 BOM để Excel hiển thị đúng dấu!")

        with open(res_path, "r", encoding="utf-8-sig") as f:
            lines = [line.strip() for line in f if line.strip()]
            self.assertGreaterEqual(len(lines), 2)
            self.assertIn("Phương án A", lines[0])
            self.assertIn("Đáp án đúng", lines[0])
            self.assertIn("Câu 1", lines[1])
            self.assertIn("B", lines[1])

    def test_export_quizizz_csv(self):
        """Kiểm tra xuất file Quizizz CSV đúng thứ tự cột và chỉ số đáp án đúng (1-4)."""
        output_file = os.path.join(self.temp_dir, "test_quizizz.csv")
        res_path = export_formats_service.export_quizizz_csv(
            self.metadata, self.content_blocks, self.solution_blocks, output_file
        )
        self.assertTrue(os.path.exists(res_path))

        with open(res_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("Question Text", content)
            self.assertIn("Option 1", content)
            self.assertIn("Correct Answer", content)
            # Đáp án đúng B tương ứng với chỉ số 2 trong Quizizz
            self.assertIn(",2,", content)

    def test_export_anki_deck(self):
        """Kiểm tra xuất file Anki Deck chuẩn TSV kèm các directives headers."""
        output_file = os.path.join(self.temp_dir, "test_anki.txt")
        res_path = export_formats_service.export_anki_deck(
            self.metadata, self.content_blocks, self.solution_blocks, output_file
        )
        self.assertTrue(os.path.exists(res_path))

        with open(res_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            self.assertIn("#separator:tab", lines[0])
            self.assertIn("#html:true", lines[1])
            content_all = "\n".join(lines)
            self.assertIn("ĐÁP ÁN ĐÚNG: B", content_all)

    def test_export_latex_tex(self):
        """Kiểm tra xuất mã nguồn LaTeX chuẩn Overleaf tiếng Việt và gói amsmath/geometry."""
        output_file = os.path.join(self.temp_dir, "test_exam.tex")
        res_path = export_formats_service.export_latex_tex(
            self.metadata, self.content_blocks, self.solution_blocks, output_file
        )
        self.assertTrue(os.path.exists(res_path))

        with open(res_path, "r", encoding="utf-8") as f:
            tex_content = f.read()
            self.assertIn(r"\documentclass", tex_content)
            self.assertIn(r"\usepackage[utf8]{vietnam}", tex_content)
            self.assertIn(r"\usepackage{amsmath,amssymb,amsfonts}", tex_content)
            self.assertIn(r"\begin{document}", tex_content)
            self.assertIn(r"\end{document}", tex_content)
            self.assertIn("Câu 1", tex_content)


if __name__ == "__main__":
    unittest.main()
