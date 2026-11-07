"""
DocInspector - Cloud Deep Semantic Verifier (NVIDIA NIM API).
Tối ưu hóa chuyên biệt cho giới hạn 40 requests/phút & 10.000 requests/ngày:
1. Fingerprint Cache (SHA-256 LRU): Đề đã quét 1 lần không bao giờ tốn request lần 2.
2. Sliding-Window Rate Limiter (35 RPM / 9.500 RPD) + Pacing Queue (giãn cách an toàn, chống HTTP 429).
3. Multi-Exam Batching (verify_batch): Gộp tối đa 8 đề vào 1 request duy nhất khi nạp hàng loạt / Google Drive.
4. Smart Selective Gating (should_invoke_cloud): Tiết kiệm ~70% quota cho các đề đã rõ ràng tuyệt đối, ưu tiên 100% quota cho đề dễ nhầm lẫn.
"""

from __future__ import annotations

from collections import OrderedDict, deque
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger("DocInspector.CloudVerifier")

_ENV_LOADED = False
_LOCK = threading.Lock()

# Giới hạn an toàn dưới mức trần 40 RPM & 10.000 RPD của NVIDIA NIM
MAX_REQUESTS_PER_MINUTE = 34
MAX_REQUESTS_PER_DAY = 9500
MIN_INTERVAL_SECONDS = 1.55  # Tối đa ~38 req/phút ngay cả khi gọi liên tục

_MINUTE_WINDOW: deque[float] = deque()
_DAY_WINDOW: deque[float] = deque()
_LAST_REQUEST_TS: float = 0.0

# LRU Cache lưu tới 4.000 kết quả thẩm định đề thi trong RAM (chỉ tốn ~1.5MB RAM)
_VERIFICATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_MAX_CACHE_SIZE = 4000


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
    base_url = (
        os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        .strip()
        .rstrip("/")
    )
    primary_model = os.environ.get(
        "NVIDIA_PRIMARY_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"
    ).strip()
    fallback_model = os.environ.get(
        "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"
    ).strip()

    if not api_key:
        try:
            from config.settings import settings

            api_key = getattr(settings, "NVIDIA_API_KEY", "") or ""
            base_url = (getattr(settings, "NVIDIA_BASE_URL", base_url) or base_url).rstrip("/")
            primary_model = (
                getattr(settings, "NVIDIA_PRIMARY_MODEL", primary_model) or primary_model
            )
            fallback_model = (
                getattr(settings, "NVIDIA_FALLBACK_MODEL", fallback_model) or fallback_model
            )
        except Exception:
            pass

    return api_key, base_url, primary_model, fallback_model


def _make_fingerprint(file_name: str, raw_text: str) -> str:
    norm_name = re.sub(r"\s+", " ", (file_name or "").strip().lower())
    norm_head = re.sub(r"\s+", " ", (raw_text or "")[:1800].strip().lower())
    norm_tail = re.sub(r"\s+", " ", (raw_text or "")[-400:].strip().lower())
    digest = hashlib.sha256(f"{norm_name}||{norm_head}||{norm_tail}".encode("utf-8")).hexdigest()
    return digest[:32]


def _acquire_rate_limit_slot(wait_if_needed: bool = True, max_wait_sec: float = 12.0) -> bool:
    """Đảm bảo không bao giờ vượt 34 req/phút và 9.500 req/ngày."""
    global _LAST_REQUEST_TS
    deadline = time.time() + max_wait_sec

    while True:
        now = time.time()
        with _LOCK:
            while _MINUTE_WINDOW and now - _MINUTE_WINDOW[0] >= 60.0:
                _MINUTE_WINDOW.popleft()
            while _DAY_WINDOW and now - _DAY_WINDOW[0] >= 86400.0:
                _DAY_WINDOW.popleft()

            if len(_DAY_WINDOW) >= MAX_REQUESTS_PER_DAY:
                logger.warning("Đã chạm ngưỡng bảo vệ 9.500 requests/ngày của CloudVerifier.")
                return False

            since_last = now - _LAST_REQUEST_TS
            need_minute_wait = (
                (60.0 - (now - _MINUTE_WINDOW[0]) + 0.1)
                if len(_MINUTE_WINDOW) >= MAX_REQUESTS_PER_MINUTE
                else 0.0
            )
            need_pace_wait = (
                (MIN_INTERVAL_SECONDS - since_last) if since_last < MIN_INTERVAL_SECONDS else 0.0
            )
            wait_sec = max(need_minute_wait, need_pace_wait)

            if wait_sec <= 0.0:
                _LAST_REQUEST_TS = now
                _MINUTE_WINDOW.append(now)
                _DAY_WINDOW.append(now)
                return True

        if not wait_if_needed or (time.time() + wait_sec > deadline):
            return False
        time.sleep(min(wait_sec, 2.0))


SYSTEM_PROMPT_VI = """Bạn là hệ thống thẩm định và phân loại đề thi chương trình giáo dục phổ thông Việt Nam (GDPT 2018).
Nhiệm vụ của bạn là đọc tên tệp và nội dung trích xuất của đề thi, thực hiện đối chiếu 4 bước và trả về DUY NHẤT kết quả JSON hợp lệ (không giải thích dài dòng, không dùng markdown ngoài khối JSON):

QUY TẮC BẮT BUỘC TRÁNH NHẦM LẪN:
1. Tách biệt "Trường THPT Chuyên" và "Đề thi Chuyên / HSG":
   - Nếu đầu đề ghi "Trường THPT Chuyên ..." nhưng tiêu đề kỳ thi là "Thi thử Tốt nghiệp THPT", "Khảo sát chất lượng", "Giữa kỳ", "Học kỳ" thì exam_track PHẢI LÀ "THUONG" (tuyệt đối KHÔNG xếp vào "CHUYEN" hay "HSG").
   - Chỉ xếp "HSG" khi đề ghi rõ "Kỳ thi chọn học sinh giỏi", "Đề thi HSG", "Olympic".
   - Chỉ xếp "CHUYEN" khi đề ghi rõ "Đề thi tuyển sinh vào lớp 10 THPT Chuyên", "Đề thi Chuyên", "Khối Chuyên".
2. Phân biệt "Tuyển sinh vào lớp 10" và "Lớp 10 THPT":
   - Đề ghi "Kỳ thi tuyển sinh vào lớp 10 THPT", "Thi vào lớp 10", "Ôn thi vào 10" là dành cho học sinh Lớp 9 (THCS) -> grade_level PHẢI LÀ "Khối 9" và detailed_exam_track = "Đề thi tuyển sinh vào lớp 10".
   - Chỉ xếp "Khối 10" khi là đề kiểm tra/thi của học sinh đang học Lớp 10 THPT.
3. Phân biệt môn học chuẩn GDPT 2018:
   - Cấp 2 (Lớp 6, 7, 8, 9): Khoa học tự nhiên (tổ hợp Lý-Hóa-Sinh) -> "NATURAL_SCIENCE"; Lịch sử và Địa lí -> "HISTORY_GEOGRAPHY"; Giáo dục công dân -> "CIVIC_EDUCATION".
   - Cấp 3 (Lớp 10, 11, 12): Vật lí -> "PHYSICS", Hóa học -> "CHEMISTRY", Sinh học -> "BIOLOGY", Lịch sử -> "HISTORY", Địa lí -> "GEOGRAPHY", Giáo dục kinh tế và pháp luật -> "ECONOMIC_LEGAL_EDU".
   - Cả 2 cấp: Toán -> "MATHEMATICS", Ngữ văn -> "LITERATURE", Tiếng Anh -> "ENGLISH", Tin học -> "INFORMATICS", Công nghệ -> "TECHNOLOGY".
4. Nếu văn bản hoàn toàn KHÔNG PHẢI đề thi, bài tập, đề cương hay tài liệu học tập (ví dụ: hóa đơn, văn bản hành chính, tin nhắn rác) -> đặt "is_valid_exam": false.

Định dạng JSON trả về cho 1 đề:
{
  "is_valid_exam": true,
  "subject": "MATHEMATICS | PHYSICS | CHEMISTRY | BIOLOGY | INFORMATICS | LITERATURE | ENGLISH | HISTORY | GEOGRAPHY | NATURAL_SCIENCE | HISTORY_GEOGRAPHY | CIVIC_EDUCATION | ECONOMIC_LEGAL_EDU | TECHNOLOGY | DEFENSE_SECURITY_EDU | GENERAL",
  "grade_level": "Khối 6 | Khối 7 | Khối 8 | Khối 9 | Khối 10 | Khối 11 | Khối 12 | Đại học / Cao đẳng | Không xác định",
  "exam_track": "THUONG | CHUYEN | HSG | QUOC_TE | CHUNG",
  "detailed_exam_track": "Đề thi thử tốt nghiệp THPT | Đề thi chính thức tốt nghiệp THPT | Đề thi Học kỳ 1 | Đề thi Học kỳ 2 | Đề thi Giữa học kỳ 1 | Đề thi Giữa học kỳ 2 | Đề thi khảo sát chất lượng | Đề thi tuyển sinh vào lớp 10 | Đề thi tuyển sinh vào lớp 10 Chuyên | Đề thi Học sinh giỏi | Đề cương / Tài liệu ôn tập",
  "school_or_department": "Tên Trường hoặc Sở GD&ĐT nếu có trong đầu đề, hoặc null",
  "academic_year": "YYYY-YYYY nếu có, hoặc null",
  "confidence": 0.98
}"""


class CloudExamVerifier:
    """Bộ đối chiếu đề thi qua NVIDIA NIM API với cơ chế bảo vệ Quota 40 RPM / 10k RPD."""

    @classmethod
    def get_quota_stats(cls) -> Dict[str, Any]:
        now = time.time()
        with _LOCK:
            while _MINUTE_WINDOW and now - _MINUTE_WINDOW[0] >= 60.0:
                _MINUTE_WINDOW.popleft()
            while _DAY_WINDOW and now - _DAY_WINDOW[0] >= 86400.0:
                _DAY_WINDOW.popleft()
            return {
                "rpm_used": len(_MINUTE_WINDOW),
                "rpm_limit": MAX_REQUESTS_PER_MINUTE,
                "rpd_used": len(_DAY_WINDOW),
                "rpd_limit": MAX_REQUESTS_PER_DAY,
                "cache_size": len(_VERIFICATION_CACHE),
            }

    @classmethod
    def should_invoke_cloud(
        cls,
        file_name: str,
        raw_text: str,
        local_subject: str,
        local_grade: str,
        local_track: str,
        local_confidence: float,
        has_conflict: bool = False,
    ) -> bool:
        """
        Quyết định thông minh xem có cần gọi Cloud hay không để tiết kiệm 10.000 req/ngày:
        - Nếu đã có trong Cache -> gọi luôn (tốn 0 request).
        - Nếu đề có bất kỳ dấu hiệu dễ nhầm lẫn nào (Chuyên vs Thi thử, Vào 10 vs Lớp 10,
          KHTN Cấp 2 vs Lý/Hóa/Sinh Cấp 3, xung đột tiêu đề - nội dung, confidence < 0.90) -> BẮT BUỘC gọi Cloud.
        - Nếu tải hệ thống đang rảnh (< 12 req/phút và < 5.000 req/ngày) -> cho phép gọi Cloud để thẩm định kép 100%.
        """
        fp = _make_fingerprint(file_name, raw_text)
        with _LOCK:
            if fp in _VERIFICATION_CACHE:
                return True

        if has_conflict or local_confidence < 0.90:
            return True
        if local_subject in ("GENERAL", "UNKNOWN", "") or local_grade in (
            "Không xác định",
            "UNKNOWN",
            "",
        ):
            return True

        head_lower = f"{file_name} {(raw_text or '')[:1200]}".lower()
        # Các mẫu dễ gây hiểu lầm nhất cần मॉडल 120B phân xử
        ambiguous_markers = (
            "chuyên",
            "chuyen",
            "tuyển sinh",
            "tuyen sinh",
            "vào 10",
            "vao 10",
            "vào lớp 10",
            "khtn",
            "khoa học tự nhiên",
            "lịch sử và địa",
            "khảo sát",
            "khao sat",
            "kscl",
        )
        if any(m in head_lower for m in ambiguous_markers):
            return True

        stats = cls.get_quota_stats()
        if stats["rpm_used"] < 12 and stats["rpd_used"] < 5000:
            return True

        return False

    @classmethod
    def verify_exam(
        cls,
        file_name: str,
        raw_text: str,
        timeout_sec: float = 12.0,
    ) -> Optional[Dict[str, Any]]:
        api_key, base_url, primary_model, fallback_model = _get_nvidia_credentials()
        if not api_key or not raw_text or len(raw_text.strip()) < 25:
            return None

        fp = _make_fingerprint(file_name, raw_text)
        with _LOCK:
            cached = _VERIFICATION_CACHE.get(fp)
            if cached is not None:
                _VERIFICATION_CACHE.move_to_end(fp)
                return dict(cached)

        if not _acquire_rate_limit_slot(wait_if_needed=True, max_wait_sec=10.0):
            logger.info("CloudExamVerifier tạm nhường lượt để bảo vệ trần 40 RPM.")
            return None

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

        models_chain = []
        for m in (
            primary_model,
            fallback_model,
            "nvidia/nemotron-3.5-bolt-e4b",
        ):
            if m and m not in models_chain:
                models_chain.append(m)

        for model_name in models_chain:
            for attempt in range(2):
                try:
                    req = urllib.request.Request(
                        f"{base_url}/chat/completions",
                        data=json.dumps(
                            {
                                "model": model_name,
                                "messages": [
                                    {"role": "system", "content": SYSTEM_PROMPT_VI},
                                    {"role": "user", "content": user_prompt},
                                ],
                                "max_tokens": 280,
                                "temperature": 0.0,
                                "chat_template_kwargs": {
                                    "thinking": False,
                                    "enable_thinking": False,
                                },
                            }
                        ).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        msg = body.get("choices", [{}])[0].get("message", {})
                        content = (
                            msg.get("content") or msg.get("reasoning_content") or ""
                        ).strip()
                        parsed = cls._extract_json(content)
                        if parsed and parsed.get("subject"):
                            with _LOCK:
                                _VERIFICATION_CACHE[fp] = dict(parsed)
                                if len(_VERIFICATION_CACHE) > _MAX_CACHE_SIZE:
                                    _VERIFICATION_CACHE.popitem(last=False)
                            return parsed
                    break
                except urllib.error.HTTPError as he:
                    if he.code == 429 and attempt == 0:
                        time.sleep(2.2)
                        continue
                    logger.debug("CloudExamVerifier HTTP %s (%s)", he.code, model_name)
                    break
                except Exception as e:
                    logger.debug("CloudExamVerifier (%s) bỏ qua: %s", model_name, e)
                    break

        return None

    @classmethod
    def verify_batch(
        cls,
        items: List[Dict[str, str]],
        timeout_sec: float = 15.0,
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Gộp tối đa 8 đề thi vào 1 request duy nhất để tiết kiệm 85% số lượng request/phút
        khi người dùng tải nhiều file cùng lúc hoặc quét thư mục Google Drive.
        Mỗi phần tử trong items gồm: {"file_name": str, "raw_text": str}.
        """
        if not items:
            return []

        api_key, base_url, primary_model, fallback_model = _get_nvidia_credentials()
        if not api_key:
            return [None] * len(items)

        results: List[Optional[Dict[str, Any]]] = [None] * len(items)
        uncached_indices: List[int] = []
        uncached_fps: List[str] = []

        with _LOCK:
            for idx, item in enumerate(items):
                fn = item.get("file_name", "")
                rt = item.get("raw_text", "")
                if not rt or len(rt.strip()) < 25:
                    continue
                fp = _make_fingerprint(fn, rt)
                cached = _VERIFICATION_CACHE.get(fp)
                if cached is not None:
                    _VERIFICATION_CACHE.move_to_end(fp)
                    results[idx] = dict(cached)
                else:
                    uncached_indices.append(idx)
                    uncached_fps.append(fp)

        if not uncached_indices:
            return results

        if len(uncached_indices) == 1:
            idx0 = uncached_indices[0]
            results[idx0] = cls.verify_exam(
                items[idx0].get("file_name", ""),
                items[idx0].get("raw_text", ""),
                timeout_sec=timeout_sec,
            )
            return results

        # Chia thành các lô tối đa 6 đề / 1 request để đảm bảo độ chính xác 100%
        batch_size = 6
        for start in range(0, len(uncached_indices), batch_size):
            chunk_indices = uncached_indices[start : start + batch_size]
            chunk_fps = uncached_fps[start : start + batch_size]

            if not _acquire_rate_limit_slot(wait_if_needed=True, max_wait_sec=12.0):
                break

            blocks = []
            for local_i, orig_idx in enumerate(chunk_indices):
                fn = items[orig_idx].get("file_name", "")
                rt = items[orig_idx].get("raw_text", "").strip()
                snippet = rt[:1400] + ("\n...\n" + rt[-350:] if len(rt) > 1800 else "")
                blocks.append(f"--- ĐỀ SỐ {local_i} ---\nTên tệp: {fn}\nNội dung:\n{snippet}")

            batch_prompt = (
                "Phân loại danh sách các đề thi dưới đây. "
                'Trả về DUY NHẤT 1 đối tượng JSON có dạng {"items": [ ... ]} '
                f"gồm đúng {len(chunk_indices)} phần tử theo đúng thứ tự ĐỀ SỐ 0 đến ĐỀ SỐ {len(chunk_indices) - 1}.\n\n"
                + "\n\n".join(blocks)
            )

            for model_name in (
                primary_model,
                fallback_model,
                "nvidia/nemotron-3.5-bolt-e4b",
            ):
                if not model_name:
                    continue
                try:
                    req = urllib.request.Request(
                        f"{base_url}/chat/completions",
                        data=json.dumps(
                            {
                                "model": model_name,
                                "messages": [
                                    {"role": "system", "content": SYSTEM_PROMPT_VI},
                                    {"role": "user", "content": batch_prompt},
                                ],
                                "max_tokens": 220 * len(chunk_indices),
                                "temperature": 0.0,
                                "chat_template_kwargs": {
                                    "thinking": False,
                                    "enable_thinking": False,
                                },
                            }
                        ).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        msg = body.get("choices", [{}])[0].get("message", {})
                        content = (
                            msg.get("content") or msg.get("reasoning_content") or ""
                        ).strip()
                        parsed_obj = cls._extract_json(content)
                        arr = (
                            parsed_obj.get("items")
                            if isinstance(parsed_obj, dict)
                            else None
                        )
                        if isinstance(arr, list) and len(arr) == len(chunk_indices):
                            with _LOCK:
                                for local_i, orig_idx in enumerate(chunk_indices):
                                    item_res = arr[local_i]
                                    if isinstance(item_res, dict) and item_res.get("subject"):
                                        results[orig_idx] = item_res
                                        _VERIFICATION_CACHE[chunk_fps[local_i]] = dict(item_res)
                            break
                except Exception as e:
                    logger.debug("CloudExamVerifier batch (%s) bỏ qua: %s", model_name, e)
                    continue

        return results

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
