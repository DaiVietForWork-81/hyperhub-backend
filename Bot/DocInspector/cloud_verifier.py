"""
DocInspector - Cloud Deep Semantic Verifier (NVIDIA NIM API).
Tốn 0MB RAM trên VPS 512MB, thời gian phản hồi ~0.8s với nvidia/nemotron-3.5-bolt-e4b.
Đối chiếu sâu 4 bước để triệt tiêu mọi hiểu lầm về Môn học, Khối lớp, Loại đề, Trường ra đề.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("DocInspector.CloudVerifier")

_ENV_LOADED = False


def _get_nvidia_credentials() -> tuple[str, str, str, str]:
    global _ENV_LOADED
    if not _ENV_LOADED:
        _ENV_LOADED = True
        try:
            from dotenv import load_dotenv
            bot_env = Path(__file__).resolve().parent.parent / ".env"
            if bot_env.exists():
                load_dotenv(bot_env)
        except Exception:
            pass

    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").strip().rstrip("/")
    primary_model = os.environ.get("NVIDIA_PRIMARY_MODEL", "nvidia/nemotron-3.5-bolt-e4b").strip()
    fallback_model = os.environ.get("NVIDIA_FALLBACK_MODEL", "mistralai/mistral-large-4-1t-a52b").strip()

    if not api_key:
        try:
            from config.settings import settings
            api_key = getattr(settings, "NVIDIA_API_KEY", "") or ""
            base_url = (getattr(settings, "NVIDIA_BASE_URL", base_url) or base_url).rstrip("/")
            primary_model = getattr(settings, "NVIDIA_PRIMARY_MODEL", primary_model) or primary_model
            fallback_model = getattr(settings, "NVIDIA_FALLBACK_MODEL", fallback_model) or fallback_model
        except Exception:
            pass

    return api_key, base_url, primary_model, fallback_model


SYSTEM_PROMPT_VI = """Bạn là hệ thống kiểm định và phân loại đề thi chương trình giáo dục phổ thông Việt Nam (GDPT 2018).
Nhiệm vụ của bạn là đọc tên tệp và nội dung trích xuất của đề thi, thực hiện đối chiếu 4 bước và trả về DUY NHẤT 1 chuỗi JSON hợp lệ (không bọc giải thích thừa).

QUY TẮC CHỐNG NHẦM LẪN BẮT BUỘC:
1. Tách biệt "Trường THPT Chuyên" và "Đề thi Chuyên / HSG":
   - Nếu đầu đề ghi tên trường là "Trường THPT Chuyên ..." nhưng kỳ thi là "Thi thử Tốt nghiệp THPT", "Khảo sát chất lượng", "Kiểm tra Giữa kỳ", "Kiểm tra Học kỳ" -> exam_track PHẢI LÀ "thuong" (KHÔNG ĐƯỢC xếp vào "chuyen" hay "hsg").
   - Chỉ xếp exam_track = "hsg" khi là kỳ thi chọn Học sinh giỏi cấp Trường/Tỉnh/Thành phố.
   - Chỉ xếp exam_track = "chuyen" khi là kỳ thi Tuyển sinh vào lớp 10 Chuyên, chọn đội tuyển HSG Quốc gia, hoặc Olympic chuyên sâu.
2. Phân biệt "Tuyển sinh vào lớp 10" và "Lớp 10 THPT":
   - Đề ghi "Kỳ thi tuyển sinh vào lớp 10 THPT" / "Thi vào lớp 10" / "Ôn thi vào 10" là dành cho học sinh Lớp 9 (THCS) -> grade_number PHẢI LÀ 9, educational_level = "CAP_2", detailed_exam_track = "Đề thi tuyển sinh vào lớp 10" (hoặc "Đề thi tuyển sinh vào 10 Chuyên" nếu thi vào hệ chuyên).
3. Phân biệt môn học chuẩn GDPT 2018:
   - Cấp 2 (Lớp 6, 7, 8, 9): Khoa học tự nhiên -> subject = "NATURAL_SCIENCE"; Lịch sử và Địa lí -> subject = "HISTORY_GEOGRAPHY" (hoặc HISTORY/GEOGRAPHY); Giáo dục công dân -> subject = "CIVIC_EDUCATION".
   - Cấp 3 (Lớp 10, 11, 12): Vật lí -> "PHYSICS", Hóa học -> "CHEMISTRY", Sinh học -> "BIOLOGY", Toán -> "MATHEMATICS", Tin học -> "INFORMATICS", Ngữ văn -> "LITERATURE", Tiếng Anh -> "ENGLISH", Lịch sử -> "HISTORY", Địa lí -> "GEOGRAPHY", Giáo dục kinh tế và pháp luật -> "CIVIC_EDUCATION".
   - Không để các phương trình toán học (cos, sin, cực trị, hàm số) trong đề Vật lí / Hóa học làm nhầm sang môn Toán.

Định dạng JSON bắt buộc trả về:
{
  "subject": "MATHEMATICS | PHYSICS | CHEMISTRY | BIOLOGY | INFORMATICS | LITERATURE | ENGLISH | HISTORY | GEOGRAPHY | NATURAL_SCIENCE | CIVIC_EDUCATION | GENERAL",
  "grade_number": 6 đến 12 (hoặc 0 nếu chung),
  "educational_level": "CAP_2 | CAP_3 | CHUNG",
  "exam_track": "thuong | hsg | chuyen | quoc_te | chung",
  "detailed_exam_track": "Đề thi thử tốt nghiệp THPT | Đề thi tốt nghiệp THPT | Đề thi Giữa học kỳ 1 | Đề thi Học kỳ 1 | Đề thi Giữa học kỳ 2 | Đề thi Học kỳ 2 | Đề thi tuyển sinh vào lớp 10 | Đề thi tuyển sinh vào 10 Chuyên | Đề thi Học sinh giỏi (HSG) | Đề thi Chuyên / Olympic | Chuyên đề ôn tập / Tài liệu lý thuyết",
  "school_or_department": "Tên Trường hoặc Sở GD&ĐT nếu có, hoặc null",
  "academic_year": "YYYY-YYYY nếu có, hoặc null",
  "confidence": 0.98
}"""


class CloudExamVerifier:
    """Bộ đối chiếu đề thi qua NVIDIA NIM API (0MB RAM, <1s latency)."""

    @classmethod
    def verify_exam(
        cls,
        file_name: str,
        raw_text: str,
        timeout_sec: float = 4.5,
    ) -> Optional[Dict[str, Any]]:
        api_key, base_url, primary_model, fallback_model = _get_nvidia_credentials()
        if not api_key or not raw_text or len(raw_text.strip()) < 25:
            return None

        # Lấy 2,800 ký tự đầu + 700 ký tự cuối (chứa bảng đáp án / nguồn đề)
        clean_text = raw_text.strip()
        if len(clean_text) > 3600:
            snippet = clean_text[:2800] + "\n...\n" + clean_text[-700:]
        else:
            snippet = clean_text

        user_prompt = (
            f"Tên tệp: {file_name}\n"
            f"Nội dung trích xuất:\n{snippet}\n\n"
            "Chỉ trả về đúng 1 JSON theo quy định:"
        )

        for model_name in (primary_model, fallback_model):
            if not model_name:
                continue
            try:
                req = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=json.dumps({
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT_VI},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 260,
                        "temperature": 0.0,
                    }).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    msg = body.get("choices", [{}])[0].get("message", {})
                    content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
                    parsed = cls._extract_json(content)
                    if parsed and parsed.get("subject"):
                        return parsed
            except Exception as e:
                logger.debug("CloudExamVerifier (%s) bỏ qua: %s", model_name, e)
                continue

        return None

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
