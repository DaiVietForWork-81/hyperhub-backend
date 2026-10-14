"""
Unit test suite for PDF & Word extraction optimizations:
1. Otsu Adaptive Thresholding
2. Multi-PSM OCR & resolution
3. Per-page Hybrid PDF extraction (mixed digital + scanned)
4. DOCX Header, Footer, Table, and Textbox extraction
5. Legacy .DOC UTF-16LE Unicode & CP1258 extraction
"""

import io
import unittest
from PIL import Image, ImageDraw

import fitz  # PyMuPDF
from docx import Document

from DocInspector.extractors import (
    FastDocumentExtractor,
    _compute_otsu_threshold,
    _preprocess_image_for_ocr,
)


class TestExtractionOptimizations(unittest.TestCase):

    def test_otsu_threshold_dark_and_light(self):
        """Kiểm tra thuật toán Otsu tính toán chính xác ngưỡng tách biệt nền/chữ."""
        # 1. Ảnh nền xám sáng (220) với chữ đen (30)
        hist_light = [0] * 256
        hist_light[30] = 500   # Chữ
        hist_light[220] = 2000 # Nền
        th_light = _compute_otsu_threshold(hist_light)
        self.assertTrue(30 < th_light < 220, f"Ngưỡng {th_light} phải nằm giữa 30 và 220")

        # 2. Ảnh nền xám tối (80) với chữ sáng (240)
        hist_dark = [0] * 256
        hist_dark[60] = 2000  # Nền tối
        hist_dark[230] = 500  # Chữ sáng
        th_dark = _compute_otsu_threshold(hist_dark)
        self.assertTrue(60 < th_dark < 230, f"Ngưỡng {th_dark} phải nằm giữa 60 và 230")

    def test_legacy_doc_utf16le_extraction(self):
        """Kiểm tra bóc tách văn bản tiếng Việt Unicode UTF-16LE từ nhị phân file .doc."""
        sample_text = "ĐỀ THI HỌC KỲ 1 MÔN TOÁN LỚP 12 NĂM HỌC 2024-2025 TRƯỜNG THPT CHUYÊN HÀ NỘI AMSTERDAM\nCâu 1: Cho hàm số y = f(x) đồng biến trên R."
        # Giả lập luồng nhị phân OLE2 WordDocument chứa chuỗi UTF-16LE
        prefix = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64 + b"WordDocument" + b"\x00" * 32
        utf16_bytes = sample_text.encode("utf-16le")
        suffix = b"\x00" * 64
        fake_doc_bytes = prefix + utf16_bytes + suffix

        extracted = FastDocumentExtractor.extract(fake_doc_bytes, file_name="de_thi_cu.doc")
        self.assertEqual(extracted.raw_type, "DOC")
        self.assertIn("TOÁN", extracted.full_text)
        self.assertIn("HỌC KỲ", extracted.full_text)
        self.assertIn("AMSTERDAM", extracted.full_text)

    def test_docx_headers_and_footers(self):
        """Kiểm tra trích xuất Header & Footer từ tệp DOCX."""
        doc = Document()
        section = doc.sections[0]
        header = section.header
        hp = header.paragraphs[0]
        hp.text = "SỞ GD&ĐT HÀ NỘI - TRƯỜNG THPT CHUYÊN AMSTERDAM"

        footer = section.footer
        fp = footer.paragraphs[0]
        fp.text = "MÃ ĐỀ THI: 101 - TRANG 1/4"

        p1 = doc.add_paragraph("Câu 1: Phương trình bậc hai ax^2 + bx + c = 0.")
        table = doc.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Cột A: Dữ liệu vào"
        table.rows[0].cells[1].text = "Cột B: Dữ liệu ra"

        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        extracted = FastDocumentExtractor.extract(docx_bytes, file_name="de_thi.docx")
        self.assertEqual(extracted.raw_type, "DOCX")
        # Header phải được bóc tách
        self.assertIn("AMSTERDAM", extracted.full_text)
        self.assertIn("SỞ GD&ĐT", extracted.full_text)
        # Footer phải được bóc tách
        self.assertIn("MÃ ĐỀ THI: 101", extracted.full_text)
        # Nội dung chính và bảng biểu
        self.assertIn("Phương trình bậc hai", extracted.full_text)
        self.assertIn("Cột A: Dữ liệu vào", extracted.full_text)
        self.assertTrue(len(extracted.headers) > 0)

    def test_hybrid_pdf_extraction(self):
        """Kiểm tra PDF dạng lai (trang 1 là digital text, trang 2 là trang scan có ảnh)
        không bị mất text trang 1 và gộp được cả 2 trang."""
        pdf_doc = fitz.open()

        # Trang 1: Text số hóa chuẩn (dùng font cơ bản của PyMuPDF)
        page1 = pdf_doc.new_page()
        page1.insert_text(
            (50, 72),
            "SO GD&DT TP HO CHI MINH - TRUONG THPT CHUYEN LE HONG PHONG\n"
            "DE THI HOC KY 2 NAM HOC 2024-2025\n"
            "MON: VAT LY 11 - THOI GIAN: 50 PHUT\n"
            "Cau 1: Mot vat dao dong dieu hoa voi chu ky T = 2s.\n"
            "Cau 2: Song co truyen trong moi truong dan hoi co buoc song lambda.\n"
            "Cau 3: Dien xoay chieu co hieu dien the hieu dung U = 220V."
        )

        # Trang 2: Giả lập trang scan có ảnh câu hỏi
        page2 = pdf_doc.new_page()
        # Tạo ảnh scan chứa chữ
        scan_img = Image.new("RGB", (600, 150), color=(255, 255, 255))
        draw = ImageDraw.Draw(scan_img)
        draw.text((20, 20), "Cau 4: Con lac lo xo co do cung k = 100 N/m.", fill=(0, 0, 0))
        draw.text((20, 60), "Cau 5: Quang pho vach phat xa duoc phat ra boi chat nao?", fill=(0, 0, 0))
        img_buf = io.BytesIO()
        scan_img.save(img_buf, format="PNG")
        img_bytes = img_buf.getvalue()

        # Chèn ảnh vào trang 2
        page2.insert_image(fitz.Rect(50, 50, 550, 200), stream=img_bytes)

        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        extracted = FastDocumentExtractor.extract(pdf_bytes, file_name="de_thi_vat_ly.pdf", deep=True)
        self.assertEqual(extracted.raw_type, "PDF")
        self.assertEqual(extracted.page_count, 2)
        # Trang 1 digital text không được bị mất
        self.assertIn("LE HONG PHONG", extracted.full_text)
        self.assertIn("dao dong dieu hoa", extracted.full_text)
        self.assertIn("VAT LY", extracted.full_text)
        # Trang 2 OCR được gộp vào
        self.assertIn("Quang pho", extracted.full_text)
        self.assertTrue(len(extracted.full_text) > 200)


if __name__ == "__main__":
    unittest.main()
