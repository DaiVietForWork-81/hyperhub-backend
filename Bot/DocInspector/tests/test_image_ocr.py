import io
import unittest
from PIL import Image, ImageDraw

from DocInspector.core import DocumentInspector
from DocInspector.extractors import FastDocumentExtractor
from DocInspector.hybrid_classifier import HybridExamClassifier
from DocInspector.models import Subject


class TestImageOCR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Tạo ảnh đề thi giả lập bằng PIL
        img = Image.new("RGB", (800, 260), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((20, 15), "SO GIAO DUC VA DAO TAO HA NOI", fill=(0, 0, 0))
        d.text((20, 45), "TRUONG THPT CHUYEN HA NOI - AMSTERDAM", fill=(0, 0, 0))
        d.text((20, 75), "DE THI HOC KY 1 NAM HOC 2024 - 2025", fill=(0, 0, 0))
        d.text((20, 105), "MON: HOA HOC - LOP 12", fill=(0, 0, 0))
        d.text((20, 140), "Cau 1: Cho m gam Fe tac dung hoan toan voi dung dich HCl du thu duoc 2.24 lit H2.", fill=(0, 0, 0))
        d.text((40, 170), "A. 2.8g        B. 5.6g        C. 11.2g        D. 8.4g", fill=(0, 0, 0))
        d.text((20, 205), "Cau 2: Chat nao sau day la este no, don chuc, mach ho?", fill=(0, 0, 0))
        d.text((40, 230), "A. CH3COOCH3   B. HCOOCH=CH2  C. CH3COOH      D. C2H5OH", fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        cls.image_bytes = buf.getvalue()

    def test_extract_image_ocr(self):
        doc = FastDocumentExtractor.extract(self.image_bytes, file_name="de_thi_hoa_12.png")
        self.assertEqual(doc.raw_type, "IMAGE")
        self.assertGreater(doc.char_count, 50)
        self.assertIn("AMSTERDAM", doc.full_text.upper())

    def test_hybrid_classifier_image(self):
        res = HybridExamClassifier.classify(self.image_bytes, file_name="de_thi_hoa_12.png")
        self.assertIn(res.subject, ("CHEMISTRY", "CHEM"))
        self.assertIn("12", str(res.grade))
        self.assertIn("2024-2025", str(res.academic_year))

    def test_document_inspector_inspect_image(self):
        report = DocumentInspector.inspect(self.image_bytes, file_name="de_thi_hoa_12.png")
        self.assertEqual(report.detected_subject, Subject.CHEMISTRY)
        self.assertIsNotNone(report.academic_year)
        self.assertIn("2024-2025", report.academic_year)


if __name__ == "__main__":
    unittest.main()
