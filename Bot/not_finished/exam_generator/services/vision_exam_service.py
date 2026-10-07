"""Dịch vụ Soạn Đề Song Sinh Từ Ảnh Chụp Sách & Đề Thật (Vision-to-Exam Engine).

Khả năng:
1. Nhận diện chữ viết, bảng biểu và công thức toán học từ ảnh chụp đề thi / trang sách bài tập.
2. Tận dụng mô hình Multimodal Vision (Gemma 3 Vision qua Ollama) hoặc OCR cục bộ (pytesseract).
3. Động cơ Đề Song Sinh (Parallel Form Generator):
   - Giữ nguyên 100% cấu trúc, dạng câu hỏi và ma trận nhận thức Bloom của đề gốc trong ảnh.
   - Thay đổi 100% số liệu thực nghiệm, thông số bài toán, tên nhân vật và ngữ cảnh để chống học sinh học vẹt.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import Any, Optional

from PIL import Image

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

from utils.logger import get_logger

logger = get_logger("VisionExamService")


class VisionExamService:
    """Xử lý hình ảnh đề thi và sinh đề tương đương (Parallel Form)."""

    @staticmethod
    def encode_image_base64(image_path: str | Path) -> str:
        """Mã hóa file ảnh sang chuỗi base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @classmethod
    async def extract_content_from_image(
        cls,
        image_path: str | Path,
        ollama_base_url: str = "http://127.0.0.1:11434",
        vision_model: str = "gemma3:4b",
    ) -> str:
        """Bóc tách toàn bộ nội dung câu hỏi và công thức từ ảnh chụp đề thi.

        Thử nghiệm tuần tự:
        1. Gọi mô hình Vision Ollama (Gemma 3 Multimodal với images base64).
        2. Fallback sang pytesseract OCR cục bộ.
        3. Fallback sang đọc thông tin cơ bản của ảnh.
        """
        img_p = Path(image_path)
        if not img_p.exists():
            raise FileNotFoundError(f"Không tìm thấy file ảnh: {image_path}")

        # ── 1. Thử dùng Ollama Multimodal Vision API ──
        try:
            import aiohttp
            b64_img = cls.encode_image_base64(img_p)
            prompt = (
                "Hãy đọc và sao chép lại toàn bộ các câu hỏi trắc nghiệm, bài tập tự luận và công thức toán học "
                "có trong bức ảnh này. Giữ nguyên cú pháp LaTeX chuẩn $...$ cho các công thức."
            )
            payload = {
                "model": vision_model,
                "prompt": prompt,
                "images": [b64_img],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 4096},
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{ollama_base_url}/api/generate", json=payload, timeout=aiohttp.ClientTimeout(total=45)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get("response", "").strip()
                        if text:
                            logger.info(f"👁️ [Vision AI] Đã bóc tách thành công nội dung từ ảnh bằng {vision_model}.")
                            return text
        except Exception as vision_err:
            logger.debug(f"Ollama vision request không khả dụng: {vision_err}")

        # ── 2. Fallback sang pytesseract OCR ──
        if HAS_PYTESSERACT:
            try:
                img = Image.open(img_p)
                ocr_text = pytesseract.image_to_string(img, lang="vie+eng")
                if ocr_text.strip():
                    logger.info("📷 [Tesseract OCR] Đã trích xuất văn bản từ ảnh qua OCR cục bộ.")
                    return ocr_text.strip()
            except Exception as ocr_err:
                logger.debug(f"Tesseract OCR lỗi: {ocr_err}")

        # ── 3. Fallback cơ bản ──
        try:
            with Image.open(img_p) as img:
                w, h = img.size
                return f"[Đề thi trích xuất từ ảnh {img_p.name} ({w}x{h} px)]"
        except Exception:
            return f"[Đề thi tham chiếu từ file ảnh {img_p.name}]"

    @classmethod
    def build_parallel_form_prompt(
        cls,
        extracted_content: str,
        subject: str = "",
        custom_instructions: str = "",
    ) -> str:
        """Tạo chỉ thị thiết kế Bộ Đề Song Sinh (Parallel Form Generation).

        Nguyên tắc sư phạm:
        - Giữ nguyên cấu trúc, độ khó nhận thức Bloom và các bẫy tư duy của đề gốc trong ảnh.
        - Đổi mới 100% số liệu tính toán, hàm số, ngữ cảnh thực tiễn để chống học vẹt.
        """
        lines = [
            "=== [CHỈ THỊ SOẠN BỘ ĐỀ SONG SINH TƯƠNG ĐƯƠNG (PARALLEL FORM)] ===",
            "Hệ thống đã nhận diện được tài liệu tham chiếu từ ảnh chụp đề thi gốc / trang sách bài tập:",
            "--------------------------------------------------",
            extracted_content[:2500],
            "--------------------------------------------------",
            "",
            "QUY TẮC THIẾT KẾ ĐỀ SONG SINH BẮT BUỘC:",
            "1. CẤU TRÚC ĐỒNG DẠNG: Giữ nguyên 100% số lượng câu hỏi, tỷ lệ phân bố mức độ nhận thức (Nhận biết, Thông hiểu, Vận dụng) và phong cách ra đề của đề gốc.",
            "2. ĐỔI MỚI SỐ LIỆU: Toàn bộ hệ số, nghiệm số, hàm số toán học, dữ kiện bài toán và ngữ cảnh thực tiễn BẮT BUỘC phải thay đổi (không được sao chép nguyên văn số liệu đề gốc).",
            "3. BẢO TỒN ĐỘ PHÂN HÓA: Câu hỏi nào trong đề gốc là câu vận dụng cao thì câu tương ứng trong đề mới cũng phải có độ phức tạp tư duy tương đương.",
            "4. ĐÁP ÁN MỚI CHÍNH XÁC: Tính toán lại lời giải chi tiết và bảng đáp án đúng 100% dựa trên các số liệu mới vừa tạo.",
        ]

        if subject:
            lines.append(f"• Môn học chỉ định: {subject}")
        if custom_instructions:
            lines.append(f"• Yêu cầu bổ sung từ giáo viên: {custom_instructions}")

        return "\n".join(lines)


# Singleton instance dùng chung
vision_exam_service = VisionExamService()
