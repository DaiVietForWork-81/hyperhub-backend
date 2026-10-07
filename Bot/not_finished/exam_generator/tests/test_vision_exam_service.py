"""tests/test_vision_exam_service.py
Kiểm thử toàn diện động cơ Soạn Đề Song Sinh Từ Ảnh Chụp (Vision-to-Exam Parallel Form Engine).
"""

import base64
import os
import shutil
import tempfile
import unittest

from PIL import Image

from not_finished.exam_generator.services.vision_exam_service import (
    VisionExamService,
    vision_exam_service,
)


class TestVisionExamService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_img_path = os.path.join(self.temp_dir, "sample_exam.png")

        # Tạo file ảnh trắng giả lập kích thước 100x100
        img = Image.new("RGB", (100, 100), color="white")
        img.save(self.test_img_path)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_encode_image_base64(self):
        """Kiểm tra mã hóa ảnh sang chuỗi base64 chuẩn RFC 4648."""
        b64 = vision_exam_service.encode_image_base64(self.test_img_path)
        self.assertIsInstance(b64, str)
        self.assertGreater(len(b64), 0)

        # Giải mã ngược lại để đối chiếu
        decoded = base64.b64decode(b64)
        with open(self.test_img_path, "rb") as f:
            original = f.read()
        self.assertEqual(decoded, original)

    def test_build_parallel_form_prompt(self):
        """Kiểm tra cấu trúc và các ràng buộc sư phạm trong prompt đề song sinh."""
        sample_extracted = "Câu 1: Cho tam giác ABC vuông tại A có AB=3, AC=4. Tính BC."
        prompt = vision_exam_service.build_parallel_form_prompt(
            extracted_content=sample_extracted,
            subject="Toán Học Lớp 9",
            custom_instructions="Tập trung vào định lý Pytago",
        )

        self.assertIn("CHỈ THỊ SOẠN BỘ ĐỀ SONG SINH", prompt)
        self.assertIn("CẤU TRÚC ĐỒNG DẠNG", prompt)
        self.assertIn("ĐỔI MỚI SỐ LIỆU", prompt)
        self.assertIn("BẢO TỒN ĐỘ PHÂN HÓA", prompt)
        self.assertIn("Toán Học Lớp 9", prompt)
        self.assertIn("Tập trung vào định lý Pytago", prompt)
        self.assertIn(sample_extracted, prompt)

    async def test_extract_content_missing_file(self):
        """Kiểm tra báo lỗi FileNotFoundError khi đường dẫn ảnh không tồn tại."""
        with self.assertRaises(FileNotFoundError):
            await vision_exam_service.extract_content_from_image(
                os.path.join(self.temp_dir, "non_existent.png")
            )

    async def test_extract_content_fallback_success(self):
        """Kiểm tra fallback cơ chế trích xuất khi không có Ollama Vision API khả dụng."""
        # Gọi với port không hợp lệ để ép fallback sang OCR / File metadata
        text = await vision_exam_service.extract_content_from_image(
            image_path=self.test_img_path,
            ollama_base_url="http://127.0.0.1:9999",
        )
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)


if __name__ == "__main__":
    unittest.main()
