"""
DocInspector - Cloud Deep Semantic Verifier & 45s Batch Aggregator (NVIDIA NIM API).
Sử dụng dàn Model mạnh nhất trên build.nvidia.com (timeout < 60s / file):
1. Primary: nvidia/nemotron-3-ultra-550b-a55b (550 tỷ tham số - Deep Reasoning + JSON, ~5-8s/file)
2. Fallback 1: nvidia/nemotron-3.5-super-vl-120b-a12b (120 tỷ tham số)
3. Fallback 2: google/gemma-4-31b-it (31 tỷ tham số)
4. Fallback 3: z-ai/glm-5.3-flash & nvidia/nemotron-3.5-bolt-e4b

Cơ chế gom lô 45 giây (45s Batch Aggregator):
- Cứ mỗi 45 giây, toàn bộ các tệp mà Bot đã list/tổng hợp được sẽ được gom lại và gửi về Cloud Model để đọc hiểu & phân tích sâu.
- Kết hợp Fingerprint Cache (SHA-256) và Rate Guard (<= 34 req/phút, <= 9.500 req/ngày).
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
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("DocInspector.CloudVerifier")

_ENV_LOADED = False
_LOCK = threading.Lock()

# Giới hạn an toàn dưới mức trần 40 RPM & 10.000 RPD của NVIDIA NIM
MAX_REQUESTS_PER_MINUTE = 34
MAX_REQUESTS_PER_DAY = 9500
MIN_INTERVAL_SECONDS = 1.6
BATCH_FLUSH_INTERVAL_SECONDS = 45.0  # Chu kỳ 45 giây gom và phân tích toàn bộ file đã list

_MINUTE_WINDOW: deque[float] = deque()
_DAY_WINDOW: deque[float] = deque()
_LAST_REQUEST_TS: float = 0.0

# LRU Cache lưu tới 4.000 kết quả thẩm định đề thi trong RAM
_VERIFICATION_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
_MAX_CACHE_SIZE = 4000

# Hàng đợi gom các file mà Bot đã list/tổng hợp để phân tích định kỳ mỗi 45 giây
_PENDING_45S_QUEUE: OrderedDict[str, Dict[str, Any]] = OrderedDict()


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
        "NVIDIA_PRIMARY_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"
    ).strip()
    fallback_model = os.environ.get(
        "NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b"
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


def _acquire_rate_limit_slot(wait_if_needed: bool = True, max_wait_sec: float = 45.0) -> bool:
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
Nhiệm vụ của bạn là đọc tên tệp và nội dung trích xuất của đề thi, thực hiện đối chiếu 4 bước và trả về DUY NHẤT kết quả JSON hợp lệ (không giải thích ngoài khối JSON):

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


def _build_model_chain(primary_model: str, fallback_model: str) -> List[str]:
    chain: List[str] = []
    for m in (
        primary_model,
        fallback_model,
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3.5-super-vl-120b-a12b",
        "google/gemma-4-31b-it",
        "z-ai/glm-5.3-flash",
        "nvidia/nemotron-3.5-bolt-e4b",
    ):
        if m and m not in chain:
            chain.append(m)
    return chain


def _build_payload_for_model(
    model_name: str, system_prompt: str, user_prompt: str, base_tokens: int = 320
) -> Dict[str, Any]:
    """Tối ưu tham số riêng cho từng dòng model (550B Ultra / GLM dùng reasoning sâu; 120B / Gemma trả thẳng JSON)."""
    is_deep_reasoning = any(
        k in model_name for k in ("ultra-550b", "glm-5.3", "kimi", "deepseek")
    )
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max(1300, base_tokens * 3) if is_deep_reasoning else base_tokens,
        "temperature": 0.0,
    }
    if not is_deep_reasoning:
        payload["chat_template_kwargs"] = {
            "thinking": False,
            "enable_thinking": False,
        }
    return payload


class CloudExamVerifier:
    """Bộ đối chiếu đề thi qua NVIDIA NIM API (Model 550B + Chu kỳ gom lô 45 giây)."""

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
                "pending_45s_queue": len(_PENDING_45S_QUEUE),
            }

    @classmethod
    def enqueue_for_45s_batch(
        cls,
        doc_id: int | str,
        file_name: str,
        raw_text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Đưa tệp vừa được Bot list/tổng hợp vào hàng đợi để chu kỳ 45s gom gửi phân tích."""
        if not raw_text or len(raw_text.strip()) < 25:
            return
        fp = _make_fingerprint(file_name, raw_text)
        with _LOCK:
            if fp in _VERIFICATION_CACHE:
                return
            key = str(doc_id or fp)
            _PENDING_45S_QUEUE[key] = {
                "doc_id": doc_id,
                "file_name": file_name,
                "raw_text": raw_text,
                "fingerprint": fp,
                "metadata": metadata or {},
                "enqueued_at": time.time(),
            }

    @classmethod
    def flush_45s_batch(cls, max_items: int = 24) -> List[Dict[str, Any]]:
        """
        Được gọi định kỳ mỗi 45 giây bởi Bot:
        Lấy toàn bộ các file đã được list/tổng hợp trong 45s qua, gom thành các lô (batch)
        và gửi tới Model 550B để đọc hiểu & phân loại sâu.
        Trả về danh sách kết quả [{"doc_id": ..., "file_name": ..., "verified": {...}, "metadata": {...}}].
        """
        with _LOCK:
            if not _PENDING_45S_QUEUE:
                return []
            batch_entries: List[Dict[str, Any]] = []
            keys_to_pop = list(_PENDING_45S_QUEUE.keys())[:max_items]
            for k in keys_to_pop:
                batch_entries.append(_PENDING_45S_QUEUE.pop(k))

        items_input = [
            {"file_name": e["file_name"], "raw_text": e["raw_text"]} for e in batch_entries
        ]
        verified_list = cls.verify_batch(items_input, timeout_sec=50.0)

        completed: List[Dict[str, Any]] = []
        for entry, v_res in zip(batch_entries, verified_list):
            if v_res and isinstance(v_res, dict) and v_res.get("subject"):
                completed.append(
                    {
                        "doc_id": entry["doc_id"],
                        "file_name": entry["file_name"],
                        "verified": v_res,
                        "metadata": entry["metadata"],
                    }
                )
        return completed

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
        if stats["rpm_used"] < 20 and stats["rpd_used"] < 8000:
            return True

        return False

    @classmethod
    def verify_exam(
        cls,
        file_name: str,
        raw_text: str,
        timeout_sec: float = 45.0,
    ) -> Optional[Dict[str, Any]]:
        """Phân tích sâu 1 đề thi (timeout mặc định 45s < 1 phút/file để model 550B suy luận kỹ nhất)."""
        api_key, base_url, primary_model, fallback_model = _get_nvidia_credentials()
        if not api_key or not raw_text or len(raw_text.strip()) < 25:
            return None

        fp = _make_fingerprint(file_name, raw_text)
        with _LOCK:
            cached = _VERIFICATION_CACHE.get(fp)
            if cached is not None:
                _VERIFICATION_CACHE.move_to_end(fp)
                return dict(cached)

        if not _acquire_rate_limit_slot(wait_if_needed=True, max_wait_sec=35.0):
            logger.info("CloudExamVerifier đưa file '%s' vào hàng đợi 45s để bảo vệ trần 40 RPM.", file_name)
            cls.enqueue_for_45s_batch(doc_id=fp, file_name=file_name, raw_text=raw_text)
            return None

        clean_text = raw_text.strip()
        if len(clean_text) > 4200:
            snippet = clean_text[:3200] + "\n...\n" + clean_text[-900:]
        else:
            snippet = clean_text

        user_prompt = (
            f"Tên tệp: {file_name}\n"
            f"Nội dung trích xuất:\n{snippet}\n\n"
            "Chỉ trả về đúng 1 JSON theo quy định:"
        )

        models_chain = _build_model_chain(primary_model, fallback_model)

        for model_name in models_chain:
            for attempt in range(2):
                try:
                    payload = _build_payload_for_model(
                        model_name, SYSTEM_PROMPT_VI, user_prompt, base_tokens=320
                    )
                    req = urllib.request.Request(
                        f"{base_url}/chat/completions",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        msg = body.get("choices", [{}])[0].get("message", {})
                        content = (msg.get("content") or "").strip()
                        if not content:
                            content = (msg.get("reasoning_content") or "").strip()
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
                        time.sleep(2.5)
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
        timeout_sec: float = 50.0,
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Gộp tối đa 6 đề thi vào 1 request duy nhất để phân tích sâu trong chu kỳ 45s.
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

        models_chain = _build_model_chain(primary_model, fallback_model)
        batch_size = 6

        for start in range(0, len(uncached_indices), batch_size):
            chunk_indices = uncached_indices[start : start + batch_size]
            chunk_fps = uncached_fps[start : start + batch_size]

            if not _acquire_rate_limit_slot(wait_if_needed=True, max_wait_sec=40.0):
                break

            blocks = []
            for local_i, orig_idx in enumerate(chunk_indices):
                fn = items[orig_idx].get("file_name", "")
                rt = items[orig_idx].get("raw_text", "").strip()
                snippet = rt[:1500] + ("\n...\n" + rt[-400:] if len(rt) > 1900 else "")
                blocks.append(f"--- ĐỀ SỐ {local_i} ---\nTên tệp: {fn}\nNội dung:\n{snippet}")

            batch_prompt = (
                "Phân loại danh sách các đề thi dưới đây. "
                'Trả về DUY NHẤT 1 đối tượng JSON có dạng {"items": [ ... ]} '
                f"gồm đúng {len(chunk_indices)} phần tử theo đúng thứ tự ĐỀ SỐ 0 đến ĐỀ SỐ {len(chunk_indices) - 1}.\n\n"
                + "\n\n".join(blocks)
            )

            batch_succeeded = False
            for model_name in models_chain:
                try:
                    payload = _build_payload_for_model(
                        model_name,
                        SYSTEM_PROMPT_VI,
                        batch_prompt,
                        base_tokens=260 * len(chunk_indices),
                    )
                    req = urllib.request.Request(
                        f"{base_url}/chat/completions",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        msg = body.get("choices", [{}])[0].get("message", {})
                        content = (msg.get("content") or "").strip()
                        if not content:
                            content = (msg.get("reasoning_content") or "").strip()
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
                            batch_succeeded = True
                            break
                except Exception as e:
                    logger.debug("CloudExamVerifier batch (%s) bỏ qua: %s", model_name, e)
                    continue

            # Nếu batch gộp bị lệch định dạng, fallback sang quét từng đề trong lô
            if not batch_succeeded:
                for orig_idx in chunk_indices:
                    results[orig_idx] = cls.verify_exam(
                        items[orig_idx].get("file_name", ""),
                        items[orig_idx].get("raw_text", ""),
                        timeout_sec=timeout_sec,
                    )

        return results

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        # Nếu có nhiều cặp {...}, ưu tiên khối JSON cuối cùng (sau khi reasoning xong)
        matches = list(re.finditer(r"\{[\s\S]*\}", text))
        if not matches:
            return None
        raw_block = matches[-1].group(0)
        try:
            obj = json.loads(raw_block)
            return obj if isinstance(obj, dict) else None
        except Exception:
            # Thử tìm khối JSON khép kín cuối cùng
            sub_matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
            for candidate in reversed(sub_matches):
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict) and ("subject" in obj or "items" in obj):
                        return obj
                except Exception:
                    continue
            return None
