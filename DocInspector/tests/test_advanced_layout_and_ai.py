"""
Unit test suite for Advanced Layout-Aware PDF extraction,
Docx Math/Table enhancements, Markdown Table Answer Key Parsing,
and AIDocumentEnhancer circuit breaker resilience.
"""

import io
import unittest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
import fitz  # PyMuPDF

from DocInspector.extractors import FastDocumentExtractor
from DocInspector.question_parser import QuestionParser
from DocInspector.ai_extractor import AIDocumentEnhancer


class TestAdvancedLayoutAndAI(unittest.TestCase):

    def test_two_column_pdf_reading_order(self):
        """Kiểm tra bố cục 2 cột không bị đan xen dòng (đọc hết cột trái rồi mới sang cột phải)."""
        doc = fitz.open()
        p = doc.new_page(width=600, height=800)

        # Header phủ ngang trang
        p.insert_text((50, 40), "SO GD&DT HA NOI - DE THI HOC KY 1")

        # Cột trái (x ~ 50)
        p.insert_text((50, 100), "Cau 1: Ham so y = f(x) dong bien tren khoang nao?")
        p.insert_text((50, 120), "A. (0; 1)    B. (1; 2)")
        p.insert_text((50, 150), "Cau 2: Tich phan tu 0 den 1 cua e^x dx bang:")
        p.insert_text((50, 170), "A. e - 1    B. e + 1")

        # Cột phải (x ~ 320)
        p.insert_text((320, 100), "Cau 3: The tich khoi lang tru co dien tich day B:")
        p.insert_text((320, 120), "A. V = B*h    B. V = B*h/3")
        p.insert_text((320, 150), "Cau 4: Trong khong gian Oxyz, mat cau (S) co ban kinh:")
        p.insert_text((320, 170), "A. R = 3      B. R = 9")

        # Footer
        p.insert_text((50, 750), "--- HET --- Thi sinh khong duoc su dung tai lieu")

        pdf_bytes = doc.tobytes()
        doc.close()

        extracted = FastDocumentExtractor.extract(pdf_bytes, file_name="de_thi_2_cot.pdf")

        # Kiểm tra thứ tự xuất hiện trong full_text:
        # Header -> Cau 1 -> Cau 2 -> Cau 3 -> Cau 4 -> Footer
        pos_header = extracted.full_text.find("HOC KY 1")
        pos_c1 = extracted.full_text.find("Cau 1")
        pos_c2 = extracted.full_text.find("Cau 2")
        pos_c3 = extracted.full_text.find("Cau 3")
        pos_c4 = extracted.full_text.find("Cau 4")
        pos_footer = extracted.full_text.find("--- HET ---")

        self.assertTrue(pos_header != -1 and pos_c1 != -1 and pos_c2 != -1 and pos_c3 != -1 and pos_c4 != -1)
        self.assertTrue(pos_header < pos_c1 < pos_c2 < pos_c3 < pos_c4 < pos_footer,
                        f"Thứ tự đọc sai! pos: Header={pos_header}, C1={pos_c1}, C2={pos_c2}, C3={pos_c3}, C4={pos_c4}, Foot={pos_footer}")

    def test_two_column_with_spanning_passage(self):
        """Kiểm tra đề thi có đoạn văn đọc hiểu phủ ngang (spanning block) ở giữa 2 cột."""
        doc = fitz.open()
        p = doc.new_page(width=600, height=800)

        p.insert_text((50, 40), "ĐỀ THI TIẾNG ANH - HỌC KỲ 1")
        p.insert_text((50, 100), "Câu 1: Phonetics")
        p.insert_text((320, 100), "Câu 2: Stress")

        # Spanning reading passage phủ từ x=50 đến x=550 ở y=250
        p.insert_text((50, 250), "Read the following passage and mark the correct answer to each question:")

        p.insert_text((50, 350), "Câu 3: The word 'it' in paragraph 2 refers to:")
        p.insert_text((320, 350), "Câu 4: What is the main idea of the passage?")

        pdf_bytes = doc.tobytes()
        doc.close()

        extracted = FastDocumentExtractor.extract(pdf_bytes, file_name="de_thi_passage.pdf")

        pos_c1 = extracted.full_text.find("Câu 1")
        pos_c2 = extracted.full_text.find("Câu 2")
        pos_passage = extracted.full_text.find("Read the following passage")
        pos_c3 = extracted.full_text.find("Câu 3")
        pos_c4 = extracted.full_text.find("Câu 4")

        self.assertTrue(pos_c1 < pos_c2 < pos_passage < pos_c3 < pos_c4,
                        f"Thứ tự phân đoạn sai! C1={pos_c1}, C2={pos_c2}, Pass={pos_passage}, C3={pos_c3}, C4={pos_c4}")

    def test_docx_omml_math_formula_extraction(self):
        """Kiểm tra trích xuất công thức toán OMML trong DOCX không bị mất."""
        doc = Document()
        p = doc.add_paragraph("Phương trình: ")

        # Chèn phần tử giả lập OMML math: <m:oMath><m:r><m:t>x^2 + 2x - 3 = 0</m:t></m:r></m:oMath>
        omath = OxmlElement('m:oMath')
        r = OxmlElement('m:r')
        t = OxmlElement('m:t')
        t.text = "x^2 + 2x - 3 = 0"
        r.append(t)
        omath.append(r)
        p._p.append(omath)

        # Chèn bảng
        table = doc.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "Câu"
        table.rows[0].cells[1].text = "Đáp án"
        table.rows[1].cells[0].text = "1"
        table.rows[1].cells[1].text = "C"

        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        extracted = FastDocumentExtractor.extract(docx_bytes, file_name="toan_omml.docx")
        self.assertIn("x^2 + 2x - 3 = 0", extracted.full_text)
        self.assertIn("| Câu | Đáp án |", extracted.full_text)
        self.assertIn("| 1 | C |", extracted.full_text)

    def test_markdown_table_answer_key_extraction(self):
        """Kiểm tra bóc tách đáp án từ bảng Markdown (Pattern 6)."""
        # Bảng dạng dọc
        vertical_table = (
            "# ĐÁP ÁN ĐỀ THI\n\n"
            "| Câu | Đáp án |\n"
            "|---|---|\n"
            "| 1 | A |\n"
            "| 2 | B |\n"
            "| 3 | C |\n"
            "| 4 | D |\n"
        )
        keys_v = QuestionParser.extract_answer_keys(vertical_table)
        self.assertEqual(keys_v.get(1), "A")
        self.assertEqual(keys_v.get(2), "B")
        self.assertEqual(keys_v.get(3), "C")
        self.assertEqual(keys_v.get(4), "D")

        # Bảng dạng ngang
        horizontal_table = (
            "BẢNG ĐÁP ÁN TRẮC NGHIỆM\n\n"
            "| Câu | 1 | 2 | 3 | 4 | 5 |\n"
            "|---|---|---|---|---|---|\n"
            "| Đáp án | A | C | B | D | A |\n"
        )
        keys_h = QuestionParser.extract_answer_keys(horizontal_table)
        self.assertEqual(keys_h.get(1), "A")
        self.assertEqual(keys_h.get(2), "C")
        self.assertEqual(keys_h.get(3), "B")
        self.assertEqual(keys_h.get(4), "D")
        self.assertEqual(keys_h.get(5), "A")

    def test_ai_circuit_breaker_resilience(self):
        """Kiểm tra AIDocumentEnhancer an toàn tuyệt đối khi Ollama/Gemini offline (Zero Crash)."""
        # probe offline
        is_avail = AIDocumentEnhancer.is_available()
        # Even if unavailable, calling clean_noisy_ocr_text returns original string without crashing
        sample_ocr = "Cau 1: Ham so dong bien tren khoang nao?\nA. (0; 1)    B. (1; 2)"
        res = AIDocumentEnhancer.clean_noisy_ocr_text(sample_ocr)
        self.assertTrue(len(res) > 0)
        self.assertIn("Cau 1", res)

        # Calling metadata extraction returns None or dict safely
        meta = AIDocumentEnhancer.extract_structured_metadata_with_ai(sample_ocr)
        self.assertTrue(meta is None or isinstance(meta, dict))


if __name__ == "__main__":
    unittest.main()
