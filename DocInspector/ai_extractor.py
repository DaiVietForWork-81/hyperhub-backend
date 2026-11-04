"""
AI-Enhanced Document Extraction & Verification Layer for DocInspector.
Zero-crash hybrid architecture:
- Primary: Local Ollama (Qwen 3.5 / Gemma) or Google Gemini API.
- Fallback: Deterministic fast extraction if AI is unavailable, slow, or offline.
- Fast probe & circuit breaker: 1.5s timeout, 0ms overhead when offline.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


class AIDocumentEnhancer:
    """
    Intelligent AI-powered refinement layer for document extraction.
    Enhances OCR text, extracts structured question-answer matrices,
    and infers complex metadata with highest accuracy.
    """

    _last_probe_time: float = 0.0
    _is_ollama_alive: bool = False
    _is_gemini_configured: bool = False
    _probe_interval_seconds: float = 60.0

    @classmethod
    def _probe_services(cls) -> Tuple[bool, bool]:
        """Probes Ollama and Gemini availability with 1.5s circuit breaker."""
        now = time.time()
        if now - cls._last_probe_time < cls._probe_interval_seconds:
            return cls._is_ollama_alive, cls._is_gemini_configured

        cls._last_probe_time = now

        # 1. Check Gemini API Key
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            # Check Bot/.env
            try:
                env_path = os.path.join(os.path.dirname(__file__), "..", "Bot", ".env")
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if line.strip().startswith("GEMINI_API_KEY="):
                                gemini_key = line.strip().split("=", 1)[1].strip()
                                break
            except Exception:
                pass

        cls._is_gemini_configured = bool(gemini_key)

        # 2. Probe Ollama local server
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        cls._is_ollama_alive = False
        try:
            req = urllib.request.Request(f"{ollama_url}/api/tags", headers={"User-Agent": "DocInspector-Probe"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    cls._is_ollama_alive = True
        except Exception:
            cls._is_ollama_alive = False

        return cls._is_ollama_alive, cls._is_gemini_configured

    @classmethod
    def is_available(cls) -> bool:
        """Returns True ONLY if LLM enhancement is explicitly enabled in config AND Ollama/Gemini is reachable."""
        try:
            from .config import get_config
            cfg = get_config()
            if cfg.strict_offline or not cfg.allow_llm_enhancement:
                return False
        except Exception:
            return False
        ollama_ok, gemini_ok = cls._probe_services()
        return ollama_ok or gemini_ok

    @classmethod
    def get_preferred_backend(cls) -> str:
        """Determines best active backend: 'gemini', 'ollama', or 'none'."""
        ollama_ok, gemini_ok = cls._probe_services()
        if gemini_ok:
            return "gemini"
        if ollama_ok:
            return "ollama"
        return "none"

    @classmethod
    def call_ollama(cls, prompt: str, system_prompt: str = "", model: str = "qwen3.5:4b", timeout: int = 15) -> Optional[str]:
        """Calls local Ollama server with circuit breaker and clean think-tag stripping."""
        ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "num_ctx": 4096,
            },
        }
        try:
            req = urllib.request.Request(
                f"{ollama_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = data.get("response", "")
                    # Strip think tags if present
                    text = re.sub(r"(?is)<think>.*?</think>", "", text).strip()
                    return text
        except Exception as e:
            log.debug("Ollama request failed: %s", e)
        return None

    @classmethod
    def call_gemini(cls, prompt: str, system_prompt: str = "", model: str = "gemini-2.5-flash", timeout: int = 20) -> Optional[str]:
        """Calls Google Gemini API via lightweight HTTP REST (zero external SDK requirement)."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"SYSTEM INSTRUCTION: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096,
            },
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        return "".join(p.get("text", "") for p in parts).strip()
        except Exception as e:
            log.debug("Gemini API request failed: %s", e)
        return None

    @classmethod
    def clean_noisy_ocr_text(cls, ocr_text: str, subject_hint: Optional[str] = None) -> str:
        """
        Dùng AI để làm sạch và khôi phục văn bản OCR bị mờ, méo, mất dấu hoặc sai công thức toán.
        Giữ nguyên 100% cấu trúc câu hỏi (Câu 1, Câu 2...) và các phương án (A, B, C, D).
        Nếu AI không khả dụng hoặc lỗi -> trả về nguyên bản ocr_text an toàn.
        """
        if not ocr_text or len(ocr_text.strip()) < 50:
            return ocr_text

        backend = cls.get_preferred_backend()
        if backend == "none":
            return ocr_text

        sys_prompt = (
            "Bạn là trợ lý chuyên gia khôi phục văn bản giáo dục và đề thi Việt Nam.\n"
            "Nhiệm vụ: Nhận văn bản OCR từ ảnh chụp/scan đề thi, sửa các từ bị sai dấu tiếng Việt, "
            "khôi phục đúng các công thức toán/lý/hóa học cơ bản, giữ nguyên chính xác số thứ tự câu hỏi "
            "(Câu 1, Câu 2...) và các lựa chọn (A., B., C., D.).\n"
            "Quy tắc tuyệt đối:\n"
            "1. KHÔNG tóm tắt, KHÔNG giải đề, KHÔNG thêm bớt câu hỏi.\n"
            "2. Chỉ xuất ra văn bản sạch dạng Markdown chuẩn.\n"
            "3. Không thêm lời chào, không giải thích gì thêm."
        )

        user_prompt = f"Văn bản OCR cần làm sạch (Môn: {subject_hint or 'Chung'}):\n\n```\n{ocr_text[:3500]}\n```"

        cleaned: Optional[str] = None
        if backend == "gemini":
            cleaned = cls.call_gemini(user_prompt, system_prompt=sys_prompt)
        elif backend == "ollama":
            cleaned = cls.call_ollama(user_prompt, system_prompt=sys_prompt)

        if cleaned and len(cleaned.strip()) >= len(ocr_text.strip()) * 0.5:
            # Lọc bỏ markdown code fences nếu có
            cleaned = re.sub(r"^```(?:markdown)?\s*\n", "", cleaned.strip())
            cleaned = re.sub(r"\n```$", "", cleaned.strip())
            return cleaned.strip()

        return ocr_text

    @classmethod
    def extract_structured_metadata_with_ai(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Trích xuất siêu dữ liệu sâu bằng AI (JSON format):
        Năm học, trường/tỉnh, mã đề, thời gian làm bài, kỳ thi, bảng đáp án.
        """
        backend = cls.get_preferred_backend()
        if backend == "none" or not text:
            return None

        sys_prompt = (
            "Bạn là AI chuyên gia trích xuất dữ liệu đề thi Việt Nam.\n"
            "Nhiệm vụ: Trích xuất thông tin từ đầu trang và cuối trang đề thi thành JSON.\n"
            "Cấu trúc JSON bắt buộc:\n"
            "{\n"
            '  "academic_year": "2024-2025" hoặc null,\n'
            '  "school_or_province": "THPT Chuyên Hà Nội Amsterdam" hoặc null,\n'
            '  "duration_minutes": 50 hoặc null,\n'
            '  "exam_code": "101" hoặc null,\n'
            '  "exam_period": "Học kỳ 1" hoặc "Thi thử tốt nghiệp THPT" hoặc null,\n'
            '  "answers": {"1": "A", "2": "C"} hoặc {}\n'
            "}\n"
            "Chỉ trả về JSON thuần túy, không có văn bản giải thích nào khác."
        )

        snippet = text[:2500] + ("\n...\n" + text[-2500:] if len(text) > 5000 else "")
        user_prompt = f"Trích xuất siêu dữ liệu đề thi sau thành JSON:\n\n{snippet}"

        res: Optional[str] = None
        if backend == "gemini":
            res = cls.call_gemini(user_prompt, system_prompt=sys_prompt, timeout=15)
        elif backend == "ollama":
            res = cls.call_ollama(user_prompt, system_prompt=sys_prompt, timeout=15)

        if res:
            try:
                # Tìm block JSON
                json_match = re.search(r"\{.*\}", res, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
            except Exception as e:
                log.debug("Lỗi phân tích JSON từ AI: %s", e)

        return None
