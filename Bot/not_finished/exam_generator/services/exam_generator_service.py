"""Dịch vụ điều phối chuỗi AI đa mô hình và quy trình sinh đề thi tự động (Exam Generator Service).

========================================================================================
KIẾN TRÚC ĐIỀU PHỐI HYBRID PIPELINE (GEMMA THINKING ON <-> QWEN THINKING OFF):
========================================================================================
1. [Bước 0] 🧠 Gemma 3:4B (Thinking ON - Planner):
   - Đóng vai Kiến trúc sư Khảo thí (Exam Architect).
   - Sử dụng tư duy sâu (reasoning tokens) để phân tích yêu cầu đề bài.
   - Lập Bản thiết kế tổng thể (Exam Blueprint & Task List) bao gồm:
     + Ma trận nhận thức Bloom (40% Nhận biết, 30% Thông hiểu, 20% Vận dụng, 10% Vận dụng cao).
     + 3 bẫy tư duy trắc nghiệm thực tế bắt buộc cài cắm.
     + Tiêu chí đáp án và barem chấm điểm chi tiết.
   - Sau khi hoàn thành, tự động dỡ RAM ngay lập tức để nhường tài nguyên cho Qwen.

2. [Bước 1] ⚡ Qwen 3.5:4B / Qwen 2.5:4B (Thinking OFF - Drafter):
   - Đóng vai Kỹ sư Thi công Soạn thảo (Fast Drafter).
   - TẮT THINKING (Thinking OFF) để triệt tiêu thời gian suy luận rườm rà, tập trung 100%
     bộ nhớ và tốc độ sinh text để hoàn thành trọn vẹn bộ câu hỏi + đáp án JSON chuẩn.
   - Tuân thủ nghiêm ngặt chỉ thị từ Task List của Gemma Planner.

3. [Bước 2] 🔍 Gemma 3:4B (Thinking ON - Auditor & Quality Council):
   - Đóng vai Chủ tịch Hội đồng Thẩm định Khảo thí Quốc gia.
   - BẬT THINKING (Thinking ON) để độc lập tính toán/giải lại từng câu hỏi.
   - Đối chiếu sản phẩm của Qwen với Bản thiết kế Blueprint ban đầu.
   - Phát hiện và sửa trực tiếp 100% lỗi về công thức, logic đáp án đúng, bẫy trắc nghiệm.

4. [Bước 3] 🧹 Qwen 2.5:0.5B (Thinking OFF - Cleaner & Formatter):
   - Quét sạch lỗi chính tả, chuẩn hóa văn phong và cú pháp LaTeX / Markdown.

5. [Bước 4] 📦 Đóng gói Song song (Parallel Packager & Exporter):
   - Tự động vẽ các sơ đồ hình học / lưu đồ / trục tọa độ Oxy theo lô (asyncio.gather).
   - Xuất đồng thời 4 tệp tin: [De_Thi].docx, [Huong_Dan_Giai].docx, [De_Thi].pdf, [Huong_Dan_Giai].pdf.

========================================================================================
BẢO TỒN TÀI NGUYÊN PHẦN CỨNG (HARDWARE MUTEX & DYNAMIC GOVERNOR):
========================================================================================
- Khóa đơn nhiệm `_MODEL_MUTEX`: Đảm bảo tại một thời điểm chỉ có DUY NHẤT 1 mô hình
  hoạt động trong VRAM/RAM GPU. Mô hình chạy xong lập tức dỡ RAM (keep_alive: 0) trước khi
  mô hình tiếp theo được nạp vào, giúp máy chủ luôn mát mẻ và không bị OOM (Out Of Memory).
- Bộ điều tiết tài nguyên `ExamResourceGovernor`: Đọc CPU%, RAM khả dụng thực tế qua psutil,
  tự động co giãn num_thread (1 đến full cores), num_ctx (1024 - 8192) theo số lượng jobs.
"""

from __future__ import annotations

import asyncio
import collections
import gc
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import aiohttp

from config.settings import settings
try:
    from not_finished.exam_generator.services.diagram_drawer import diagram_drawer
    from not_finished.exam_generator.services.document_exporter import document_exporter
    from not_finished.exam_generator.services.exam_blueprint_engine import (
        ExamBlueprintEngine,
        exam_blueprint_engine,
    )
    from not_finished.exam_generator.services.user_token_service import user_token_service
    from not_finished.exam_generator.services.math_sandbox_verifier import math_sandbox_verifier
    from not_finished.exam_generator.services.vision_exam_service import vision_exam_service
    from not_finished.exam_generator.services.export_formats import export_formats_service
    from not_finished.exam_generator.services.exam_cbt_engine import exam_cbt_manager
    from not_finished.exam_generator.services.listening_exam_service import listening_exam_service
    from not_finished.exam_generator.services.exam_analytics_service import exam_analytics_service
except ImportError:
    from services.diagram_drawer import diagram_drawer
    from services.document_exporter import document_exporter
    from services.exam_blueprint_engine import (
        ExamBlueprintEngine,
        exam_blueprint_engine,
    )
    from services.user_token_service import user_token_service
    from services.math_sandbox_verifier import math_sandbox_verifier
    from services.vision_exam_service import vision_exam_service
    from services.export_formats import export_formats_service
    from services.exam_cbt_engine import exam_cbt_manager
    from services.listening_exam_service import listening_exam_service
    from services.exam_analytics_service import exam_analytics_service
from services.disk_cache_service import disk_cache_service
from services.hardware_profiler import ResourceGovernor
from utils.logger import get_logger

logger = get_logger("ExamGeneratorService")

# URL máy chủ Ollama cục bộ (mặc định cổng 11434)
BASE_OLLAMA_URL = getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
if "localhost" in BASE_OLLAMA_URL:
    BASE_OLLAMA_URL = BASE_OLLAMA_URL.replace("localhost", "127.0.0.1")

_session: aiohttp.ClientSession | None = None
_session_loop: asyncio.AbstractEventLoop | None = None


async def _get_http_session() -> aiohttp.ClientSession:
    """Khởi tạo hoặc tái sử dụng HTTP ClientSession với keep-alive connection pool an toàn đa luồng."""
    global _session, _session_loop
    current_loop = asyncio.get_running_loop()
    if _session is None or _session.closed or _session_loop != current_loop:
        if _session is not None and not _session.closed:
            try:
                await _session.close()
            except Exception:
                pass
        connector = aiohttp.TCPConnector(
            limit=10,
            keepalive_timeout=60,
        )
        _session = aiohttp.ClientSession(connector=connector)
        _session_loop = current_loop
    return _session

# Danh sách tên các mô hình AI trong chuỗi pipeline
# (Có thể cấu hình tùy biến khi cài thêm các weights mới vào Ollama)
MODEL_DRAFT = "qwen3.5:4b"      # Model soạn thảo chính cho gói trả phí
MODEL_VERIFIER = "gemma3:4b"     # Model tư duy sâu cho lập plan và thẩm định
MODEL_CLEANER = "qwen2.5:0.5b"   # Model nhỏ gọn siêu tốc để quét chính tả

# Semaphore toàn cục: Giới hạn tối đa 3 tác vụ AI xử lý song song để tránh nghẽn I/O Ollama
_OLLAMA_SEM: asyncio.Semaphore = asyncio.Semaphore(3)

# Cửa sổ chống spam (Rate-limit Sliding Window):
# Cho phép tối đa 5 yêu cầu tạo đề / 10 phút đối với mỗi người dùng Discord
_RATE_WINDOW_SECS = 600
_RATE_MAX_CALLS = 5
_user_rate_window: dict[int, collections.deque] = {}


@dataclass
class OllamaParams:
    """Bộ thông số cấu hình động cho từng lần gọi mô hình AI qua Ollama.

    Được tính toán tự động bởi ExamResourceGovernor dựa trên tình trạng tải máy chủ thực tế.
    Hỗ trợ chế độ lai: RAM + GPU (VRAM Offload) hoặc RAM + CPU (Multi-threading).
    """
    num_thread: int       # Số luồng CPU phân bổ cho lượt gọi này
    num_ctx: int          # Kích thước ngữ cảnh (Context Window) tính bằng tokens
    num_predict: int      # Giới hạn số tokens sinh tối đa (chống vòng lặp vô hạn)
    top_p: float          # Độ rộng lấy mẫu xác suất (0.80 - 0.95)
    timeout_scale: float  # Hệ số nhân mở rộng timeout khi máy chủ đang chịu tải cao
    hw_badge: str         # Nhãn trạng thái trực quan hiển thị trên Discord (🟢, 🟡, 🔴)
    hw_detail: str        # Thông tin chi tiết về % CPU, GB RAM trống và số job đang chạy
    num_gpu: int = 0      # 99 nếu GPU khả dụng (RAM + GPU), 0 nếu chạy CPU (RAM + CPU)
    compute_mode: str = "RAM + CPU"  # "RAM + GPU" hoặc "RAM + CPU"
    vram_free_gb: float = 0.0        # Dung lượng VRAM khả dụng (GB)
    ram_free_gb: float = 0.0         # Dung lượng RAM khả dụng (GB)
    offload_strategy: str = ""       # Mô tả chiến lược phân bổ layers vào phần cứng


class ExamResourceGovernor:
    """Bộ Điều Tiết Tài Nguyên Tự Động (Smart Hardware & Load Governor).

    Nguyên lý hoạt động:
    - Đo đạc định kỳ 3 trục thông số:
      1. Tình trạng phần cứng: OPTIMAL (khỏe), BALANCED (vừa), CONSTRAINED (quá tải).
      2. Số tiến trình tạo đề song song: active_jobs (1 job, 2-3 jobs, hoặc >= 4 jobs).
      3. Gói thành viên của người dùng: Pro/Ultra/Elite được cộng thêm +1 thread ưu tiên.
    - Xuất ra bộ thông số OllamaParams tương thích nhất để cân bằng giữa TỐC ĐỘ và ĐỘ ỔN ĐỊNH.
    """

    # Bảng tỷ lệ luồng CPU: [Chế_độ_máy_chủ][Bucket_số_lượng_job]
    # Bucket 0: 0-1 job (server rảnh) -> cấp tối đa năng lực
    # Bucket 1: 2-3 jobs (server bình thường) -> chia sẻ 40-60% luồng
    # Bucket 2: >= 4 jobs (server đông) -> co cụm tài nguyên để tránh nghẽn
    _THREAD_RATIO: dict[str, list[float]] = {
        "OPTIMAL":     [1.0,   0.6,  0.35],   # Máy chủ khỏe (CPU < 60%, RAM dư dả)
        "BALANCED":    [0.6,   0.4,  0.25],   # Máy chủ ở mức trung bình (CPU 60-80%)
        "CONSTRAINED": [0.3,   0.2,  0.15],   # Máy chủ quá tải (CPU > 82% hoặc RAM < 1GB)
    }

    # Bảng co giãn Context Window (num_ctx) khi máy chủ bận để tiết kiệm RAM
    _CTX_SCALE: dict[str, list[float]] = {
        "OPTIMAL":     [1.0,  0.85, 0.70],
        "BALANCED":    [0.80, 0.65, 0.55],
        "CONSTRAINED": [0.60, 0.50, 0.40],
    }

    # Bảng co hẹp Top-P: Giảm độ phân tán khi máy bận giúp AI sinh token nhanh hơn
    _TOP_P: dict[str, list[float]] = {
        "OPTIMAL":     [0.93, 0.90, 0.87],
        "BALANCED":    [0.90, 0.87, 0.84],
        "CONSTRAINED": [0.86, 0.83, 0.80],
    }

    # Bảng hệ số bù giờ (Timeout Scale) khi máy chủ chịu tải cao
    _TIMEOUT_SCALE: dict[str, list[float]] = {
        "OPTIMAL":     [0.80, 0.90, 1.00],
        "BALANCED":    [1.00, 1.10, 1.20],
        "CONSTRAINED": [1.25, 1.35, 1.45],
    }

    @classmethod
    def compute_params(
        cls,
        base_num_ctx: int,
        active_jobs: int,
        tier: str = "Free",
    ) -> OllamaParams:
        """Tính toán OllamaParams tối ưu tự động co giãn theo cấu hình phần cứng thực tế."""
        hw = ResourceGovernor.get_current_profile()
        mode = hw.mode  # "OPTIMAL" | "BALANCED" | "CONSTRAINED"
        cpu_cores = hw.cpu_cores
        ram_free_gb = round(hw.ram_available_mb / 1024, 1)

        # ── 1. Tự động điều chỉnh CPU Threads theo cấu hình & tải thực tế ──
        if active_jobs <= 1:
            bucket = 0
        elif active_jobs <= 3:
            bucket = 1
        else:
            bucket = 2

        ratio = cls._THREAD_RATIO.get(mode, cls._THREAD_RATIO["BALANCED"])[bucket]
        raw_threads = max(1, int(cpu_cores * ratio))

        # Pro/Elite/Ultra được cộng thêm 1 thread ưu tiên
        tier_upper = tier.upper()
        if tier_upper not in ("FREE", "HYPER FREE"):
            raw_threads = min(cpu_cores, raw_threads + 1)

        # Nếu có từ 2 jobs chạy đồng thời: Giới hạn xuống mức an toàn để máy chủ không nghẽn
        if active_jobs > 1:
            raw_threads = max(1, min(raw_threads, max(1, (cpu_cores - 1) // active_jobs)))

        # ── 2. Tự động điều chỉnh Context Window (num_ctx) theo dung lượng RAM thực tế ──
        if ram_free_gb >= 12.0:
            ram_ctx_cap = 16384
        elif ram_free_gb >= 6.0:
            ram_ctx_cap = 8192
        elif ram_free_gb >= 3.0:
            ram_ctx_cap = 4096
        else:
            ram_ctx_cap = 2048

        ctx_scale = cls._CTX_SCALE.get(mode, cls._CTX_SCALE["BALANCED"])[bucket]
        final_ctx = max(1024, min(ram_ctx_cap, int(base_num_ctx * ctx_scale)))
        # Làm tròn về bội số 512 cho Ollama
        final_ctx = (final_ctx // 512) * 512

        top_p = cls._TOP_P.get(mode, cls._TOP_P["BALANCED"])[bucket]
        timeout_scale = cls._TIMEOUT_SCALE.get(mode, cls._TIMEOUT_SCALE["BALANCED"])[bucket]

        # ── 3. Tự động điều chỉnh GPU Layers & VRAM Offload ──
        has_gpu = False
        gpu_name = ""
        vram_free = 0.0
        try:
            from services.hardware import get_gpu_info
            gpus = get_gpu_info()
            if gpus and len(gpus) > 0:
                first_gpu = gpus[0]
                vram_free = first_gpu.get("vram_free_gb") or 0.0
                gpu_name = first_gpu.get("name", "GPU")
                if vram_free >= 1.5:
                    has_gpu = True
        except Exception:
            has_gpu = False

        if has_gpu:
            compute_mode = "RAM + GPU"
            if vram_free >= 7.0:
                num_gpu = 99
                offload_strategy = f"100% VRAM ({vram_free:.1f}GB)"
            elif vram_free >= 3.5:
                num_gpu = 99
                offload_strategy = f"Toàn bộ mô hình trong VRAM ({vram_free:.1f}GB)"
            else:
                # 1.5GB <= VRAM < 3.5GB: Hybrid Dynamic Offload
                num_gpu = max(8, min(24, int((vram_free - 0.5) / 2.7 * 32)))
                offload_strategy = f"Hybrid ({num_gpu}/32 Layers GPU + Phần còn lại RAM)"
            hw_tag = f"🎮 [RAM + GPU: {gpu_name} • {offload_strategy} • {ram_free_gb}GB RAM trống (ctx={final_ctx})]"
        else:
            compute_mode = "RAM + CPU"
            num_gpu = 0
            offload_strategy = f"Pure CPU ({raw_threads} Threads)"
            hw_tag = f"⚡ [RAM + CPU: {raw_threads}/{cpu_cores} Cores • {ram_free_gb}GB RAM trống (ctx={final_ctx})]"

        hw_detail = (
            f"{hw_tag} | CPU {hw.cpu_percent:.0f}%"
            f" | {active_jobs} job{'s' if active_jobs != 1 else ''} đang chạy"
        )

        badges = {
            "OPTIMAL":     "🟢 Server: Hiệu năng tối đa",
            "BALANCED":    "🟡 Server: Cân bằng tải",
            "CONSTRAINED": "🔴 Server: Đang bận cao",
        }

        return OllamaParams(
            num_thread=raw_threads,
            num_ctx=final_ctx,
            num_predict=max(512, int(final_ctx * 0.75)),
            top_p=round(top_p, 2),
            timeout_scale=round(timeout_scale, 2),
            hw_badge=badges.get(mode, "🟡 Server: Cân bằng tải"),
            hw_detail=hw_detail,
            num_gpu=num_gpu,
            compute_mode=compute_mode,
            vram_free_gb=vram_free,
            ram_free_gb=ram_free_gb,
            offload_strategy=offload_strategy,
        )

    @classmethod
    def check_rate_limit(cls, discord_id: int) -> bool:
        """Kiểm tra user có vượt quá rate-limit (5 yêu cầu / 10 phút) không.

        Returns:
            True nếu được phép, False nếu bị chặn.
        """
        now = time.monotonic()
        if discord_id not in _user_rate_window:
            _user_rate_window[discord_id] = collections.deque()
        window = _user_rate_window[discord_id]
        # Xóa timestamps cũ hơn 10 phút
        while window and now - window[0] > _RATE_WINDOW_SECS:
            window.popleft()
        if len(window) >= _RATE_MAX_CALLS:
            return False
        window.append(now)
        return True


# Lock đơn nhiệm phần cứng: Đảm bảo chỉ 1 mô hình hoạt động tại một thời điểm
_MODEL_MUTEX: asyncio.Lock = asyncio.Lock()


class ExamGeneratorService:
    """Dịch vụ sinh đề thi sư phạm & hướng dẫn giải chi tiết qua chuỗi AI."""

    _cancelled_jobs: set[str] = set()
    _active_jobs: int = 0  # Số job đang chạy song song hiện tại

    @classmethod
    def cancel_job(cls, job_id: str) -> None:
        """Đánh dấu yêu cầu hủy tiến trình sinh bài từ người dùng."""
        cls._cancelled_jobs.add(job_id)
        logger.info(f"🚫 Đã gửi tín hiệu hủy cho Job ID: {job_id}")

    @classmethod
    def is_job_cancelled(cls, job_id: str) -> bool:
        """Kiểm tra xem Job ID có bị người dùng hủy hay không."""
        return job_id in cls._cancelled_jobs

    @classmethod
    def calculate_scale(cls, length_tier: str, mode: str) -> dict[str, Any]:
        """Tính toán quy mô câu hỏi và số trang mục tiêu theo ma trận Độ Dài x Chế Độ."""
        base_configs = {
            "Ngắn": {
                "base_pages": "2–3 trang",
                "min_mc": 6,
                "min_essay": 1,
                "passage_words": "350–450 từ",
                "duration": "45 phút",
            },
            "Vừa": {
                "base_pages": "4–6 trang",
                "min_mc": 12,
                "min_essay": 2,
                "passage_words": "550–700 từ",
                "duration": "90 phút",
            },
            "Dài": {
                "base_pages": "8–12 trang",
                "min_mc": 22,
                "min_essay": 3,
                "passage_words": "800–1200 từ",
                "duration": "120 phút",
            },
            "To": {
                "base_pages": "15–18 trang",
                "min_mc": 35,
                "min_essay": 4,
                "passage_words": "1400–1800 từ",
                "duration": "150 phút",
            },
        }

        mode_multipliers = {
            "LITE": {"multiplier": 1.0, "eta_seconds": 180, "desc": "Tạo nhanh, chuẩn trang cơ bản"},
            "FLASH": {"multiplier": 1.3, "eta_seconds": 300, "desc": "Chi tiết nâng cao, đa dạng câu hỏi"},
            "PRO": {"multiplier": 1.7, "eta_seconds": 450, "desc": "Chuyên sâu, độ dài tăng rõ rệt"},
            "MAX": {"multiplier": 2.3, "eta_seconds": 650, "desc": "Siêu chi tiết, đào sâu chuyên đề"},
            "ULTRA": {"multiplier": 3.0, "eta_seconds": 900, "desc": "Cực phẩm khảo thí, độ khó và độ dài tối đa"},
        }

        base = base_configs.get(length_tier, base_configs["Vừa"])
        mode_upper = mode.upper()
        mode_info = mode_multipliers.get(mode_upper, mode_multipliers["LITE"])

        mult = mode_info["multiplier"]
        target_mc = max(4, int(base["min_mc"] * mult))
        target_essay = max(1, int(base["min_essay"] * mult))

        if length_tier == "Ngắn":
            if mode_upper == "LITE":
                pages = "2–3 trang"
            elif mode_upper == "FLASH":
                pages = "3–4 trang"
            elif mode_upper == "PRO":
                pages = "4–5 trang"
            elif mode_upper == "MAX":
                pages = "6–7 trang"
            else:
                pages = "8–10 trang"
        elif length_tier == "Vừa":
            if mode_upper == "LITE":
                pages = "4–6 trang"
            elif mode_upper == "FLASH":
                pages = "6–8 trang"
            elif mode_upper == "PRO":
                pages = "8–10 trang"
            elif mode_upper == "MAX":
                pages = "11–14 trang"
            else:
                pages = "15–18 trang"
        elif length_tier == "Dài":
            pages = "8–12 trang" if mode_upper == "LITE" else f"{int(8*mult)}–{int(12*mult)} trang"
        else:
            pages = "15–18 trang" if mode_upper == "LITE" else f"{int(15*mult)}–{int(18*mult)} trang"

        return {
            "target_pages": pages,
            "target_mc": target_mc,
            "target_essay": target_essay,
            "passage_words": base["passage_words"],
            "duration": base["duration"],
            "eta_seconds": mode_info["eta_seconds"],
            "desc": mode_info["desc"],
        }

    @classmethod
    async def _unload_model(cls, model_name: str) -> None:
        """Giải phóng mô hình khỏi RAM ngay lập tức bằng keep_alive: 0 và thu gom rác bộ nhớ."""
        try:
            session = await _get_http_session()
            async with session.post(
                f"{BASE_OLLAMA_URL}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as res:
                await res.read()
            logger.info(f"🧹 Đã dỡ mô hình {model_name} khỏi RAM (keep_alive: 0).")
        except Exception as e:
            logger.debug(f"Không thể dỡ mô hình {model_name} qua aiohttp, thử lại sync: {e}")

            def _sync_unload():
                try:
                    payload = json.dumps({"model": model_name, "keep_alive": 0}).encode("utf-8")
                    req = urllib.request.Request(
                        f"{BASE_OLLAMA_URL}/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=10) as res:
                        res.read()
                    logger.info(f"🧹 Đã dỡ mô hình {model_name} khỏi RAM (sync).")
                except Exception as sync_e:
                    logger.debug(f"Không thể dỡ mô hình {model_name}: {sync_e}")

            await asyncio.to_thread(_sync_unload)
        finally:
            gc.collect()

    # Context window (tokens) và max output tokens theo từng model
    _MODEL_CTX: dict[str, int] = {
        "qwen2.5:0.5b":    2048,
        "qwen2.5:1.5b":    2048,
        "qwen2.5:3b":      4096,
        "qwen2.5:4b":      4096,
        "qwen3.5:2b":      6144,
        "qwen3.5:4b":      8192,
        "qwen3:4b-q4_K_M": 8192,
        "gemma3:4b":       4096,
    }
    _MODEL_MAX_TOKENS: dict[str, int] = {
        "qwen2.5:0.5b":    1024,
        "qwen2.5:1.5b":    2048,
        "qwen2.5:3b":      3072,
        "qwen2.5:4b":      4096,
        "qwen3.5:2b":      4096,
        "qwen3.5:4b":      6144,
        "qwen3:4b-q4_K_M": 6144,
        "gemma3:4b":       4096,
    }
    # Số GPU layer — tự động phát hiện 1 lần khi class load
    _NUM_GPU: int = 1 if os.environ.get("CUDA_VISIBLE_DEVICES", "") not in ("", "-1", "none") else 0

    @classmethod
    async def _query_ollama(
        cls,
        model_name: str,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        timeout: int = 600,
        keep_alive: int = 0,
        params: Optional[OllamaParams] = None,
        enable_thinking: Optional[bool] = None,
        use_cache: bool = True,
    ) -> str:
        """Gửi prompt đến Ollama với điều tiết tài nguyên, bộ đệm đĩa SSD nội bộ & bật/tắt Thinking.

        - Kiểm tra bộ nhớ đệm SSD/HDD nội bộ dự án (data/cache/) trước khi gọi mô hình.
        - Tự động bật Thinking cho Gemma (enable_thinking=True) và tắt Thinking cho Qwen (enable_thinking=False).
        - Sử dụng _MODEL_MUTEX đơn nhiệm: Chỉ 1 mô hình được nạp/chạy tại một thời điểm trên phần cứng.
        """
        # Tự động xác định cấu hình thinking theo model nếu chưa chỉ định:
        # Qwen → Tắt thinking để sinh bài siêu tốc. Gemma → Bật thinking để lập kế hoạch & thẩm định sâu.
        if enable_thinking is None:
            if "qwen" in model_name.lower():
                enable_thinking = False
            elif "gemma" in model_name.lower():
                enable_thinking = True
            else:
                enable_thinking = False

        # Lấy thông số động từ params hoặc fallback về defaults
        num_ctx = (params.num_ctx if params else None) or cls._MODEL_CTX.get(model_name, 4096)
        num_predict = (params.num_predict if params else None) or cls._MODEL_MAX_TOKENS.get(model_name, 4096)
        num_thread = (params.num_thread if params else None) or max(2, os.cpu_count() or 4)
        top_p = (params.top_p if params else None) or 0.90
        effective_timeout = int(timeout * (params.timeout_scale if params else 1.0))
        num_gpu = (params.num_gpu if params is not None else cls._NUM_GPU)

        options_dict: dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "num_thread": num_thread,
            "num_gpu": num_gpu,
            "think": enable_thinking,
            "thinking": enable_thinking,
        }

        # ── 1. Kiểm tra Bộ Nhớ Đệm SSD Khép Kín Nội Bộ (data/cache/) ──
        if use_cache:
            try:
                cached_res = await disk_cache_service.get(
                    model_name=model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    options=options_dict,
                )
                if cached_res is not None:
                    logger.info(
                        f"⚡ [SSD Cache Hit] Đọc phản hồi {model_name} từ data/cache/ (< 2ms) "
                        f"| Tiết kiệm 100% GPU/RAM"
                    )
                    return cached_res
            except Exception as cache_err:
                logger.debug(f"Không thể tra cứu disk cache: {cache_err}")

        payload = {
            "model": model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "options": options_dict,
        }

        async def _async_request() -> str:
            session = await _get_http_session()
            async with session.post(
                f"{BASE_OLLAMA_URL}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=effective_timeout),
            ) as res:
                if res.status == 200:
                    raw_data = await res.json()
                    return raw_data.get("response", "").strip()
                raise RuntimeError(f"Ollama trả về HTTP {res.status}")

        def _sync_request() -> str:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{BASE_OLLAMA_URL}/api/generate",
                data=data_bytes,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=effective_timeout) as res:
                if res.status == 200:
                    raw_data = json.loads(res.read().decode("utf-8"))
                    return raw_data.get("response", "").strip()
                raise RuntimeError(f"Ollama trả về HTTP {res.status}")

        # Chuỗi fallback tự động khi model không tồn tại trên máy chủ
        _FALLBACK: dict[str, str] = {
            "qwen2.5:4b":  "qwen2.5:3b",
            "qwen3.5:4b":  "qwen3:4b-q4_K_M",
            "qwen3.5:2b":  "qwen3:4b-q4_K_M",
        }

        async with _MODEL_MUTEX:
            async with _OLLAMA_SEM:
                t_start = time.monotonic()
                try:
                    try:
                        res_text = await _async_request()
                    except Exception as async_err:
                        logger.debug(f"aiohttp request failed ({async_err}), fallback sync...")
                        res_text = await asyncio.to_thread(_sync_request)
                    elapsed = time.monotonic() - t_start
                    compute_tag = "RAM + GPU" if num_gpu > 0 else "RAM + CPU"
                    logger.info(
                        f"✅ [{model_name}] {elapsed:.1f}s | think={enable_thinking} | {compute_tag}"
                        f" ctx={num_ctx} thr={num_thread} top_p={top_p} timeout={effective_timeout}s"
                    )

                    # ── 2. Lưu vào Bộ Nhớ Đệm SSD Khép Kín Nội Bộ (data/cache/) ──
                    if use_cache and res_text:
                        try:
                            await disk_cache_service.set(
                                model_name=model_name,
                                prompt=prompt,
                                response_text=res_text,
                                system_prompt=system_prompt,
                                options=options_dict,
                            )
                        except Exception as cache_set_err:
                            logger.debug(f"Không thể lưu disk cache: {cache_set_err}")

                    if keep_alive == 0:
                        await cls._unload_model(model_name)
                    return res_text
                except Exception as err:
                    err_lower = str(err).lower()
                    # 1. Fallback nếu GPU hết VRAM hoặc lỗi CUDA -> Chuyển sang RAM + CPU
                    if ("cuda" in err_lower or "out of memory" in err_lower or "vram" in err_lower or "gpu" in err_lower) and num_gpu > 0:
                        logger.warning(f"⚠️ Phát hiện nghẽn GPU/VRAM trên {model_name}, tự động chuyển đổi sang chế độ RAM + CPU (num_gpu=0)...")
                        if params:
                            params.num_gpu = 0
                            params.compute_mode = "RAM + CPU"
                        return await cls._query_ollama(
                            model_name=model_name,
                            prompt=prompt,
                            system_prompt=system_prompt,
                            temperature=temperature,
                            timeout=timeout,
                            keep_alive=keep_alive,
                            params=params,
                            enable_thinking=enable_thinking,
                        )

                    # 2. Fallback nếu không tìm thấy model
                    if "not found" in err_lower and model_name in _FALLBACK:
                        alt = _FALLBACK[model_name]
                        logger.warning(f"Không tìm thấy model {model_name}, tự động chuyển về {alt}")
                        return await cls._query_ollama(
                            model_name=alt,
                            prompt=prompt,
                            system_prompt=system_prompt,
                            temperature=temperature,
                            timeout=timeout,
                            keep_alive=keep_alive,
                            params=params,
                            enable_thinking=enable_thinking,
                        )
                    elapsed = time.monotonic() - t_start
                    logger.error(f"❌ [{model_name}] Lỗi sau {elapsed:.1f}s: {err}")
                    await cls._unload_model(model_name)
                    raise


    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Trích xuất và làm sạch dữ liệu JSON từ phản hồi của LLM."""
        # 1. Tìm trong khối code ```json ... ```
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        cand = m.group(1).strip() if m else text.strip()

        # Thử parse chuẩn với strict=False
        try:
            res = json.loads(cand, strict=False)
            if isinstance(res, dict):
                return res
        except Exception:
            pass

        # 2. Tìm khối ngoặc nhọn đầu và cuối { ... }
        start = cand.find("{")
        end = cand.rfind("}")
        if start != -1 and end != -1 and end > start:
            sub = cand[start : end + 1]
            try:
                res = json.loads(sub, strict=False)
                if isinstance(res, dict):
                    return res
            except Exception:
                pass

        # 3. Sử dụng json_repair để phục hồi triệt để các lỗi cú pháp LLM
        try:
            import json_repair
            repaired = json_repair.loads(cand)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

        # 4. Thử phục hồi trực tiếp từ toàn bộ raw text
        try:
            import json_repair
            repaired = json_repair.loads(text)
            if isinstance(repaired, dict):
                return repaired
        except Exception as e:
            logger.warning(f"Không thể parse JSON từ AI output: {e}")

        raise ValueError("Dữ liệu do AI sinh ra không đúng định dạng JSON chuẩn.")

    @classmethod
    async def generate_exam(
        cls,
        job_id: str,
        subject: str,
        style: str,
        length_tier: str,
        mode: str,
        output_format: str,
        output_dir: str,
        progress_callback: Optional[Callable[[str, float], Awaitable[None]]] = None,
        tier: str = "Free",
        discord_id: int = 0,
        blueprint_id: Optional[str] = None,
        reference_image_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Thực thi toàn bộ chuỗi Pipeline tạo đề và xuất 2 file riêng biệt.

        Tích hợp Smart Resource Governor & Exam Blueprint Engine: Tự động điều tiết
        tài nguyên và chuẩn hóa theo ma trận đề thi quốc gia (THPT 2025, ĐGNL, Vào 10...).
        """
        start_timestamp = time.time()

        # Kiểm tra rate-limit trước khi bắt đầu
        if discord_id and not ExamResourceGovernor.check_rate_limit(discord_id):
            raise RuntimeError(
                f"⏱️ Bạn đã tạo quá {_RATE_MAX_CALLS} bài trong 10 phút. "
                f"Vui lòng chờ thêm một chút rồi thử lại!"
            )

        # Kiểm tra hủy trước khi bắt đầu
        if cls.is_job_cancelled(job_id):
            cls._cancelled_jobs.discard(job_id)
            raise asyncio.CancelledError(f"Tiến trình {job_id} đã bị hủy bởi người dùng.")

        # ── Tăng counter active jobs ──
        cls._active_jobs += 1

        try:
            return await cls._run_pipeline(
                job_id=job_id, subject=subject, style=style,
                length_tier=length_tier, mode=mode, output_format=output_format,
                output_dir=output_dir, progress_callback=progress_callback,
                tier=tier, start_timestamp=start_timestamp,
                blueprint_id=blueprint_id,
                reference_image_path=reference_image_path,
            )
        finally:
            cls._active_jobs = max(0, cls._active_jobs - 1)
            logger.info(
                f"📊 Job {job_id} hoàn tất. Active jobs còn lại: {cls._active_jobs}"
            )

    @classmethod
    async def _run_pipeline(
        cls,
        job_id: str,
        subject: str,
        style: str,
        length_tier: str,
        mode: str,
        output_format: str,
        output_dir: str,
        progress_callback: Optional[Callable[[str, float], Awaitable[None]]],
        tier: str,
        start_timestamp: float,
        blueprint_id: Optional[str] = None,
        reference_image_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Nội lõi Pipeline 4 bước — được bọc bởi generate_exam để quản lý counter."""

        # ── Nhận diện và tích hợp Khung Đề Chuẩn Hóa (Exam Blueprint Engine) ──
        matched_bp = None
        blueprint_spec = ""
        if blueprint_id:
            matched_bp = ExamBlueprintEngine.get_blueprint(blueprint_id)
        if not matched_bp:
            matched_bp = ExamBlueprintEngine.find_best_match(subject)

        if matched_bp:
            blueprint_spec = ExamBlueprintEngine.build_prompt_spec(matched_bp, topic_context=style)
            logger.info(f"📐 [Blueprint Engine] Đã kích hoạt khung đề chuẩn: {matched_bp.name} ({matched_bp.blueprint_id})")

        # Tính toán quy mô mục tiêu (số trang, số câu hỏi, thời gian ETA)
        scale = cls.calculate_scale(length_tier, mode)

        # ── Phân bổ mô hình theo Gói thành viên (Tier) & Chế độ (Mode) ──
        # Gemma 3:4B luôn giữ vai trò Planner & Auditor (Thinking ON)
        # Qwen đảm nhận vai trò Drafter & Cleaner siêu tốc (Thinking OFF)
        tier_upper = tier.upper()
        is_free_user = tier_upper in ("FREE", "HYPER FREE")
        mode_upper = mode.upper()

        model_planner = MODEL_VERIFIER  # "gemma3:4b" (Thinking ON)
        model_verifier = MODEL_VERIFIER  # "gemma3:4b" (Thinking ON)
        model_cleaner = MODEL_CLEANER    # "qwen2.5:0.5b" (Thinking OFF)

        if is_free_user:
            model_draft = "qwen2.5:4b"   # Qwen 2.5:4B (Thinking OFF)
            verify_rounds = 1
        else:
            model_draft = "qwen3.5:4b"   # Qwen 3.5:4B (Thinking OFF)
            verify_rounds = 2 if mode_upper in ("MAX", "ULTRA") else 1

        # ── Adaptive temperature theo chế độ ──
        _TEMP_MAP = {
            "LITE": 0.45,   # Nhanh, đa dạng
            "FLASH": 0.38,
            "PRO": 0.28,
            "MAX": 0.20,
            "ULTRA": 0.13,  # Chính xác tuyệt đối
        }
        draft_temp = _TEMP_MAP.get(mode.upper(), 0.30)

        async def _notify(stage_msg: str, progress: float, show_hw: bool = False):
            if progress_callback:
                try:
                    if show_hw:
                        params_now = ExamResourceGovernor.compute_params(
                            base_num_ctx=cls._MODEL_CTX.get(model_draft, 8192),
                            active_jobs=cls._active_jobs,
                            tier=tier,
                        )
                        hw_line = f"\n> {params_now.hw_badge} • {params_now.hw_detail}"
                        await progress_callback(stage_msg + hw_line, progress)
                    else:
                        await progress_callback(stage_msg, progress)
                except Exception as cb_err:
                    logger.debug(f"Progress callback error: {cb_err}")

        # ── Hướng dẫn chuyên biệt theo môn học & Ma trận năng lực sư phạm ──
        special_subject_guide = ""
        subj_lower = (subject + " " + style).lower()

        if any(kw in subj_lower for kw in ["ielts", "toefl", "tiếng anh", "english", "listening"]):
            special_subject_guide = (
                f"\nYÊU CẦU CHUYÊN SÂU MÔN TIẾNG ANH / IELTS ACADEMIC 8.0:\n"
                f"- PHẦN I (Reading Academic): Cung cấp 1 bài đọc học thuật hoàn chỉnh ({scale['passage_words']}, chuẩn từ vựng C1-C2) "
                f"đặt trong question 1 hoặc section_header. Tạo ĐỦ {scale['target_mc']} câu hỏi dạng Multiple Choice, True/False/Not Given, hoặc Matching Headings bám sát văn bản.\n"
                f"- PHẦN II (Writing Academic): Cung cấp đề bài Writing Task 2 dạng Essay phân hóa cao (Opinion, Discussion, hoặc Cause-Solution).\n"
                f"- LỜI GIẢI (Solutions): Trích dẫn câu văn cụ thể trong bài đọc làm dẫn chứng cho từng câu trắc nghiệm. "
                f"Phần Task 2 BẮT BUỘC cung cấp 1 bài viết mẫu chuẩn Band 8.5 dài 250-300 từ kèm bảng chấm điểm 4 tiêu chí: Task Response (TR), Coherence & Cohesion (CC), Lexical Resource (LR), Grammatical Range & Accuracy (GRA).\n"
                + listening_exam_service.build_listening_prompt_guide()
            )
        elif any(kw in subj_lower for kw in ["toán", "math", "vật lý", "hóa học", "stem"]):
            special_subject_guide = (
                f"\nYÊU CẦU CHUYÊN SÂU MÔN STEM (TOÁN / LÝ / HÓA):\n"
                f"- Bắt buộc sử dụng cú pháp LaTeX chuẩn được bọc trong cặp dấu $...$ cho mọi công thức (ví dụ: $f(x) = x^2 + 2x + 1$, $\\frac{{a}}{{b}}$, $\\sqrt{{x}}$).\n"
                f"- Tạo ĐỦ {scale['target_mc']} câu trắc nghiệm và {scale['target_essay']} câu tự luận có tính phân hóa rõ rệt.\n"
                f"- Các phương án nhiễu (distractors) BẮT BUỘC dựa trên bẫy tư duy thực tế (nhầm dấu, quên ĐKXĐ, tính sai hằng số).\n"
                f"- Nếu có câu hỏi hình học, đồ thị hoặc mạch điện, đặt has_diagram: true và chỉ định diagram_type ('coordinate_system', 'triangle', 'flowchart').\n"
            )
        elif any(kw in subj_lower for kw in ["lập trình", "tin học", "c++", "python", "code", "dsa", "cấu trúc dữ liệu"]):
            special_subject_guide = (
                f"\nYÊU CẦU CHUYÊN SÂU MÔN LẬP TRÌNH / KHOA HỌC MÁY TÍNH:\n"
                f"- Các đoạn mã nguồn BẮT BUỘC phải đặt trong cặp dấu ```cpp ... ``` hoặc ```python ... ``` với cú pháp chuẩn xác.\n"
                f"- Đề thi phải bao phủ các dạng: Đọc hiểu mã nguồn, Tìm lỗi sai (Bug finding), Đánh giá độ phức tạp thời gian/bộ nhớ O(N), và Viết thuật toán.\n"
                f"- Lời giải chi tiết phải giải thích từng dòng code, phân tích edge-cases (Boundary conditions) và cho ví dụ Input/Output cụ thể.\n"
            )
        elif any(kw in subj_lower for kw in ["ngữ văn", "văn học", "lịch sử", "địa lý", "xã hội"]):
            special_subject_guide = (
                f"\nYÊU CẦU CHUYÊN SÂU MÔN NGỮ VĂN & KHOA HỌC XÃ HỘI:\n"
                f"- Cung cấp 1 đoạn trích văn học / tư liệu lịch sử trích dẫn rõ nguồn.\n"
                f"- Phần Đọc hiểu: Thiết kế câu hỏi từ mức độ Nhận biết (chỉ ra phương thức biểu đạt) đến Vận dụng cao (rút ra thông điệp sư phạm).\n"
                f"- Phần Nghị luận: Cung cấp dàn ý chi tiết (Mở bài - Thân bài với các luận điểm - Kết bài) kèm biểu điểm chấm chi tiết.\n"
            )

        # =====================================================================
        # BƯỚC 0: [1/4a] GEMMA PLANNER - THINKING ON (LẬP MA TRẬN & TASK LIST)
        # =====================================================================
        # ── Xử lý ảnh đề tham chiếu (Vision-to-Exam Parallel Form Engine) ──
        parallel_guide = ""
        if reference_image_path and os.path.exists(reference_image_path):
            await _notify("📷 Đang phân tích ảnh đề gốc bằng Gemma Vision OCR...", 0.08)
            try:
                extracted_img_text = await vision_exam_service.extract_content_from_image(
                    image_path=reference_image_path,
                    ollama_base_url=BASE_OLLAMA_URL,
                    vision_model=model_verifier,
                )
                parallel_guide = "\n" + vision_exam_service.build_parallel_form_prompt(
                    extracted_content=extracted_img_text,
                    subject=subject,
                ) + "\n"
                logger.info(f"📷 [Vision-to-Exam] Đã tích hợp chỉ thị đề song sinh từ {reference_image_path}")
            except Exception as v_err:
                logger.warning(f"Không thể xử lý ảnh đề tham chiếu: {v_err}")

        # Gemma 3:4B giữ vai trò "Kiến trúc sư khảo thí":
        # 1. Kích hoạt tính năng tư duy sâu (Thinking ON / reasoning tokens) để phân tích đề.
        # 2. Xây dựng bản phân bố năng lực Bloom's Taxonomy (40% - 30% - 20% - 10%).
        # 3. Lập danh sách bẫy tư duy thực tế (misconceptions) bắt buộc phải có trong phương án nhiễu.
        # 4. Khi hoàn thành, dỡ khỏi RAM ngay (keep_alive: 0) để giải phóng VRAM cho Qwen.
        gemma_planner_params = ExamResourceGovernor.compute_params(
            base_num_ctx=cls._MODEL_CTX.get(model_planner, 4096),
            active_jobs=cls._active_jobs,
            tier=tier,
        )
        await _notify(
            f"`[1/4a]` 🧠 **{model_planner}** đang tư duy sâu (Thinking ON) & lập ma trận task list...",
            0.15,
            show_hw=True,
        )

        if cls.is_job_cancelled(job_id):
            cls._cancelled_jobs.discard(job_id)
            raise asyncio.CancelledError(f"Tiến trình {job_id} đã bị hủy bởi người dùng.")

        planner_system = (
            "Bạn là Gemma - Kiến trúc sư Khảo thí & Trưởng ban Lập Kế hoạch Đề thi (Gemma Thinking Architect).\n"
            "Nhiệm vụ: Sử dụng năng lực tư duy sâu (Thinking ON) để phân tích yêu cầu bài toán, "
            "thiết lập Bản thiết kế tổng thể (Exam Blueprint) và Danh sách công việc (Task List) chi tiết "
            "để chỉ đạo mô hình Qwen tiến hành soạn thảo."
        )

        planner_prompt = f"""Hãy phân tích và lập Bản thiết kế tổng thể (Exam Blueprint & Task List) cho bộ đề thi sau:
- Môn học: {subject} | Phong cách: {style}
- Quy mô: {length_tier} ({scale['target_pages']}, ~{scale['target_mc']} trắc nghiệm, {scale['target_essay']} tự luận)
- Chế độ: {mode} ({scale['desc']}) | Thời gian: {scale['duration']}
{special_subject_guide}
{blueprint_spec}
{parallel_guide}

HÃY XÂY DỰNG BLUEPRINT THEO CÁC MỤC BẮT BUỘC:
1. TASK 1 (Phân bổ Bloom & Cấu trúc Phân đoạn): Liệt kê danh sách chủ đề theo ma trận nhận thức bám sát từng Phần (Section) của kỳ thi.
2. TASK 2 (Chiến lược Bẫy Trắc Nghiệm): Nêu cụ thể 3 bẫy tư duy thực tế cần cài cắm vào các phương án nhiễu.
3. TASK 3 (Chỉ thị Tiêu chuẩn Lời giải): Các điểm quan trọng phải giải thích chi tiết trong phần hướng dẫn giải và thang điểm.
4. TASK 4 (Định dạng): Quy định rõ về cú pháp LaTeX, mã nguồn hoặc bài viết mẫu.

Hãy xuất ra bản Task List & Blueprint rõ ràng, ngắn gọn và sắc bén."""

        # Gemma 3:4B chạy lập plan với Thinking ON
        exam_blueprint = await cls._query_ollama(
            model_name=model_planner,
            prompt=planner_prompt,
            system_prompt=planner_system,
            temperature=0.25,
            timeout=360,
            keep_alive=0,  # Dỡ RAM ngay sau khi lập plan để giải phóng cho Qwen
            params=gemma_planner_params,
            enable_thinking=True,
        )

        logger.info(f"📋 Gemma Planner đã lập xong Blueprint cho Job {job_id}")

        if cls.is_job_cancelled(job_id):
            cls._cancelled_jobs.discard(job_id)
            raise asyncio.CancelledError(f"Tiến trình {job_id} đã bị hủy bởi người dùng.")

        # =====================================================================
        # BƯỚC 1: [1/4b] QWEN DRAFTER - THINKING OFF (SINH NỘI DUNG SIÊU TỐC)
        # =====================================================================
        # Qwen đảm nhận vai trò "Kỹ sư thi công nội dung":
        # 1. Tắt hoàn toàn Thinking (Thinking OFF) để không sinh token suy nghĩ thừa thãi,
        #    tận dụng tối đa tốc độ sinh token để tạo toàn bộ JSON đầy đủ câu hỏi và lời giải.
        # 2. Nhiệt độ (temperature) được điều chỉnh thích ứng theo Mode (Lite: 0.45 -> Ultra: 0.13).
        # 3. Sau khi tạo xong, lưu checkpoint ngay vào DB để người dùng không bị mất bài nếu có sự cố.
        draft_base_ctx = cls._MODEL_CTX.get(model_draft, 8192)
        draft_params = ExamResourceGovernor.compute_params(
            base_num_ctx=draft_base_ctx,
            active_jobs=cls._active_jobs,
            tier=tier,
        )
        eta_min = max(1, int(scale["eta_seconds"] * draft_params.timeout_scale / 60))
        await _notify(
            f"`[1/4b]` ⚡ **{model_draft}** đang thi công soạn đề theo Blueprint (Thinking OFF)"
            f" • ⏳ ETA: ~{eta_min} phút...",
            0.30,
            show_hw=True,
        )

        draft_system = (
            "Bạn là Qwen - Chuyên gia Soạn thảo Đề thi Sư phạm Siêu tốc (Qwen Fast Engine).\n"
            "QUY TẮC TỐI THƯỢNG: TẮT THINKING (Thinking OFF). Không xuất thẻ <think> hay lập luận trung gian.\n"
            "Nhiệm vụ: Đọc chỉ thị Blueprint từ Gemma Planner và lập tức sinh toàn bộ đề thi kèm lời giải dưới dạng JSON chuẩn 100%."
        )

        draft_prompt = f"""Dưới đây là BẢN THIẾT KẾ TỔNG THỂ (BLUEPRINT & TASK LIST) do Gemma Planner lập:
---
{exam_blueprint}
---

Hãy thi công và hoàn thiện toàn bộ bộ đề thi theo các thông số:
- Mã đề: HH-{job_id[-4:]} | Môn: {subject} | Thời gian: {scale['duration']}
{special_subject_guide}
{parallel_guide}

YÊU CẦU THI CÔNG:
1. Tạo ĐỦ {scale['target_mc']} câu hỏi trắc nghiệm đánh số 1 đến {scale['target_mc']}.
2. Tạo ĐỦ {scale['target_essay']} câu hỏi tự luận đánh số tiếp theo.
3. Cài cắm đúng các bẫy trắc nghiệm sư phạm đã được chỉ định trong Task 2 của Blueprint.
4. Viết lời giải chi tiết cho 100% các câu, chỉ ra lý do chọn và phần common_mistakes.

YÊU CẦU CẤU TRÚC JSON BẮT BUỘC:
{{
  "metadata": {{
    "exam_title": "KỲ THI ĐÁNH GIÁ NĂNG LỰC HYPERHUB",
    "subject": "{subject}",
    "exam_code": "HH-{job_id[-4:]}",
    "duration": "{scale['duration']}",
    "length_tier": "{length_tier}",
    "job_id": "{job_id}"
  }},
  "questions": [
    {{
      "type": "section_header",
      "title": "PHẦN I: CÂU HỎI TRẮC NGHIỆM KHÁCH QUAN"
    }},
    {{
      "type": "question",
      "number": "1",
      "points": "0.5 điểm",
      "text": "Nội dung câu hỏi 1...",
      "options": ["A. Lựa chọn A", "B. Lựa chọn B", "C. Lựa chọn C", "D. Lựa chọn D"],
      "has_diagram": false
    }},
    {{
      "type": "section_header",
      "title": "PHẦN II: TỰ LUẬN & PHÂN HÓA NÂNG CAO"
    }},
    {{
      "type": "question",
      "number": "2",
      "points": "2.0 điểm",
      "text": "Nội dung bài toán tự luận...",
      "sub_items": [
        {{"label": "a", "text": "Yêu cầu ý a..."}},
        {{"label": "b", "text": "Yêu cầu ý b..."}}
      ],
      "has_diagram": false
    }}
  ],
  "solutions": [
    {{
      "number": "1",
      "is_multiple_choice": true,
      "correct_key": "A",
      "explanation": "Lời giải chi tiết từng bước cho câu 1...",
      "common_mistakes": "Bẫy tư duy học sinh dễ nhầm...",
      "rubric": [
        ["Chọn đúng đáp án A", 0.5]
      ]
    }},
    {{
      "number": "2",
      "is_multiple_choice": false,
      "explanation": "Lời giải chi tiết từng bước cho câu 2...",
      "rubric": [
        ["Giải đúng ý a", 1.0],
        ["Giải đúng ý b", 1.0]
      ]
    }}
  ]
}}

Chỉ trả về JSON. Không mở bài, không chào hỏi."""

        # Qwen chạy soạn đề với Thinking OFF (siêu tốc, không overhead)
        draft_response = await cls._query_ollama(
            model_name=model_draft,
            prompt=draft_prompt,
            system_prompt=draft_system,
            temperature=draft_temp,
            timeout=720,
            keep_alive=0,  # Dỡ RAM ngay khi hoàn thành
            params=draft_params,
            enable_thinking=False,
        )

        exam_json = cls._extract_json(draft_response)

        # Lưu checkpoint bản thảo
        try:
            await user_token_service.update_exam_job(
                job_id=job_id,
                status="GENERATING",
                checkpoint_data=json.dumps(exam_json, ensure_ascii=False),
            )
        except Exception as cp_err:
            logger.debug(f"Không thể lưu checkpoint draft cho {job_id}: {cp_err}")

        if cls.is_job_cancelled(job_id):
            cls._cancelled_jobs.discard(job_id)
            raise asyncio.CancelledError(f"Tiến trình {job_id} đã bị hủy bởi người dùng.")

        # =====================================================================
        # BƯỚC 2: [2/4] GEMMA AUDITOR - THINKING ON (ĐỐI CHIẾU BLUEPRINT & SỬA LỖI)
        # =====================================================================
        # Gemma 3:4B đóng vai trò "Chủ tịch Hội đồng Thẩm định Khảo thí":
        # 1. Bật Thinking (Thinking ON) để rà soát toàn diện từng câu hỏi.
        # 2. Tạo bản tóm tắt slim_str (cắt text 200 ký tự nhưng giữ nguyên options, đáp án và rubric)
        #    để giảm tải ~60% tokens đầu vào, tránh tràn context window của mô hình.
        # 3. Độc lập giải lại bài toán để kiểm tra xem `correct_key` có chính xác không.
        # 4. Kiểm tra tính độc nhất của 4 phương án (tránh lỗi 2 đáp án trùng nghĩa hoặc cùng đúng).
        for r_idx in range(1, verify_rounds + 1):
            verifier_params = ExamResourceGovernor.compute_params(
                base_num_ctx=cls._MODEL_CTX.get(model_verifier, 4096),
                active_jobs=cls._active_jobs,
                tier=tier,
            )
            await _notify(
                f"`[2/4]` 🔍 **{model_verifier}** đang đối chiếu Blueprint & kiểm tra logic (Thinking ON) (Vòng {r_idx}/{verify_rounds})...",
                0.45 + (r_idx * 0.1),
                show_hw=(r_idx == 1),
            )

            verifier_system = (
                "Bạn là Gemma - Chủ tịch Hội đồng Thẩm định Khảo thí (Gemma Quality Auditor).\n"
                "Nhiệm vụ: Sử dụng năng lực tư duy sâu (Thinking ON) để đối chiếu bộ đề thi Qwen vừa tạo "
                "với Bản thiết kế Blueprint ban đầu. Phát hiện và sửa chữa trực tiếp 100% các lỗi sai về logic, "
                "tính toán toán học, đáp án trắc nghiệm, bẫy sư phạm và biểu điểm rubric.\n"
                "Chỉ trả về JSON đã được hiệu chỉnh hoàn hảo."
            )

            # Tạo bản tóm tắt slim
            slim_questions = []
            for q in exam_json.get("questions", []):
                if q.get("type") == "question":
                    slim_q: dict[str, Any] = {
                        "number": q.get("number"),
                        "type": "question",
                        "text": (q.get("text") or "")[:200],
                    }
                    if q.get("options"):
                        slim_q["options"] = q["options"]
                    if q.get("sub_items"):
                        slim_q["sub_items"] = [{"label": s.get("label"), "text": (s.get("text",""))[:100]} for s in q["sub_items"]]
                    slim_questions.append(slim_q)

            slim_solutions = []
            for sol in exam_json.get("solutions", []):
                slim_sol: dict[str, Any] = {
                    "number": sol.get("number"),
                    "is_multiple_choice": sol.get("is_multiple_choice"),
                    "correct_key": sol.get("correct_key"),
                    "explanation": (sol.get("explanation") or "")[:150],
                    "rubric": sol.get("rubric", []),
                }
                slim_solutions.append(slim_sol)

            slim_payload = {
                "metadata": exam_json.get("metadata", {}),
                "questions": slim_questions,
                "solutions": slim_solutions,
            }
            slim_str = json.dumps(slim_payload, ensure_ascii=False)

            verifier_prompt = f"""Dưới đây là BẢN THIẾT KẾ BAN ĐẦU (BLUEPRINT):
{exam_blueprint[:1000]}

Và bộ đề thi Qwen vừa thi công:
{slim_str}

NHIỆM VỤ THẨM ĐỊNH LÝ TƯỞNG:
1. ĐỐI CHIẾU: Kiểm tra Qwen có thực hiện đúng các chỉ thị bẫy trắc nghiệm & yêu cầu môn học trong Blueprint chưa.
2. ĐÁP ÁN ĐÚNG: Tính toán/giải lại độc lập để đảm bảo `correct_key` chính xác 100%. Không có 2 đáp án cùng đúng hoặc 0 đáp án đúng.
3. PHƯƠNG ÁN NHIỄU: Đảm bảo 3 lựa chọn còn lại có giá trị phân hóa sư phạm.
4. KHẮC PHỤC LỖI: Sửa trực tiếp thông số sai và trả về DUY NHẤT mã JSON chuẩn đầy đủ."""

            # Gemma 3:4B kiểm định với Thinking ON
            verify_response = await cls._query_ollama(
                model_name=model_verifier,
                prompt=verifier_prompt,
                system_prompt=verifier_system,
                temperature=0.18,
                timeout=450,
                keep_alive=0,
                params=verifier_params,
                enable_thinking=True,
            )

            try:
                verified_json = cls._extract_json(verify_response)
                if verified_json and "questions" in verified_json and "solutions" in verified_json:
                    exam_json = verified_json
                    try:
                        await user_token_service.update_exam_job(
                            job_id=job_id,
                            status="GENERATING",
                            checkpoint_data=json.dumps(exam_json, ensure_ascii=False),
                        )
                    except Exception as cpe:
                        logger.debug(f"Không thể lưu checkpoint verifier cho {job_id}: {cpe}")
            except Exception as e:
                logger.warning(f"Vòng thẩm định {r_idx} không parse được JSON mới, giữ nguyên bản thảo trước: {e}")

        # ── Thẩm định đại số máy tính độc lập bằng SymPy Sandbox (Zero Math Hallucination) ──
        if any(kw in subj_lower for kw in ["toán", "math", "vật lý", "hóa học", "stem"]):
            try:
                exam_json, math_audit_results = math_sandbox_verifier.audit_exam_math(exam_json)
                corrected = [r for r in math_audit_results if r.was_corrected]
                if corrected:
                    logger.info(
                        f"🧮 [SymPy Verifier] Đã xác minh & tự động hiệu chỉnh {len(corrected)} câu hỏi toán."
                    )
                    try:
                        await user_token_service.update_exam_job(
                            job_id=job_id,
                            status="GENERATING",
                            checkpoint_data=json.dumps(exam_json, ensure_ascii=False),
                        )
                    except Exception as cp_err:
                        logger.debug(f"Không thể lưu checkpoint math verifier cho {job_id}: {cp_err}")
            except Exception as math_err:
                logger.warning(f"Lỗi khi chạy SymPy math sandbox verifier: {math_err}")

        if cls.is_job_cancelled(job_id):
            cls._cancelled_jobs.discard(job_id)
            raise asyncio.CancelledError(f"Tiến trình {job_id} đã bị hủy bởi người dùng.")

        # =====================================================================
        # BƯỚC 3: [3/4] CLEANER MODEL - FORMAT & TYPO SWEEP (text-only patch)
        # =====================================================================
        # Qwen 2.5:0.5B đảm nhận vai trò "Trợ lý biên tập văn phong":
        # - Mô hình 0.5B có context window nhỏ (2048), do đó KHÔNG gửi toàn bộ JSON 20KB+.
        # - Chỉ trích xuất mảng text thô (texts_to_clean: tối đa 12 đoạn văn/lời giải).
        # - Sau khi model trả về mảng đã sửa lỗi, dùng regex và id (q_1, s_1) để vá lại tại chỗ.
        cleaner_params = ExamResourceGovernor.compute_params(
            base_num_ctx=cls._MODEL_CTX.get(model_cleaner, 2048),
            active_jobs=cls._active_jobs,
            tier=tier,
        )
        await _notify(f"`[3/4]` 🧹 **{model_cleaner}** đang quét lỗi chính tả & chuẩn hóa văn phong...", 0.65)

        # Chỉ gửi các đoạn text thuần cần hiệu đính, không gửi toàn bộ JSON
        # để phù hợp với giới hạn num_ctx của model nhỏ (qwen2.5:0.5b).
        texts_to_clean: list[dict[str, Any]] = []
        for q in exam_json.get("questions", []):
            if q.get("type") == "question" and q.get("text"):
                texts_to_clean.append({"id": f"q_{q['number']}", "text": q["text"][:300]})
        for sol in exam_json.get("solutions", []):
            if sol.get("explanation"):
                texts_to_clean.append({"id": f"s_{sol['number']}", "text": sol["explanation"][:300]})

        # Tối ưu Fast-Path: Kiểm tra xem các đoạn văn bản có cần quét lại qua model 0.5B không
        needs_deep_clean = False
        for item in texts_to_clean:
            t = item["text"]
            # Cần quét nếu: lẻ dấu LaTeX ($), chứa thẻ HTML, hoặc kết thúc lửng lơ không dấu chấm câu
            if t.count("$") % 2 != 0 or "<" in t or ">" in t or not t.strip().endswith((".", "?", "!", ":", '"', "'", "$", "}")):
                needs_deep_clean = True
                break

        if not texts_to_clean:
            logger.info("ℹ️ Không có văn bản cần quét chính tả, hoàn tất Step 3.")
        elif not needs_deep_clean and mode_upper in ("LITE", "FLASH"):
            logger.info(f"⚡ [Fast-Path] Văn bản đã đạt chuẩn hình thức sau vòng thẩm định ({len(texts_to_clean)} mục), tiết kiệm ~15s gọi model.")
        else:
            cleaner_system = (
                "Bạn là trợ lý hiệu đính văn bản tiếng Việt.\n"
                "Sửa lỗi chính tả, dấu câu. Giữ nguyên nghĩa. Trả về JSON array với cấu trúc [{\"id\":...,\"text\":...}]."
            )
            cleaner_prompt = f"""Hãy sửa lỗi chính tả các đoạn văn sau:
{json.dumps(texts_to_clean[:12], ensure_ascii=False)}

Trả về JSON array: [{{"id": "...", "text": "..."}}]. Không thêm bất kỳ văn bản nào khác."""

            try:
                cleaned_response = await cls._query_ollama(
                    model_name=model_cleaner,
                    prompt=cleaner_prompt,
                    system_prompt=cleaner_system,
                    temperature=0.08,
                    timeout=240,
                    keep_alive=0,
                    params=cleaner_params,
                )
                # Patch kết quả trả về vào exam_json (best-effort)
                arr_match = re.search(r"\[[\s\S]*\]", cleaned_response)
                if arr_match:
                    cleaned_arr: list[dict] = json.loads(arr_match.group(0), strict=False)
                    patch_map = {item["id"]: item["text"] for item in cleaned_arr if "id" in item and "text" in item}
                    for q in exam_json.get("questions", []):
                        key = f"q_{q.get('number')}"
                        if key in patch_map and q.get("text"):
                            q["text"] = patch_map[key]
                    for sol in exam_json.get("solutions", []):
                        key = f"s_{sol.get('number')}"
                        if key in patch_map and sol.get("explanation"):
                            sol["explanation"] = patch_map[key]
            except Exception as e:
                logger.warning(f"Bỏ qua bước quét chính tả do lỗi parse, giữ nguyên bản thẩm định: {e}")

        if cls.is_job_cancelled(job_id):
            cls._cancelled_jobs.discard(job_id)
            raise asyncio.CancelledError(f"Tiến trình {job_id} đã bị hủy bởi người dùng.")

        # =====================================================================
        # BƯỚC 4: [4/4] VẼ SƠ ĐỒ BATCH & XUẤT 2 FILE SONG SONG
        # =====================================================================
        # Quy trình đóng gói và xuất bản tài liệu:
        # 1. Vẽ sơ đồ minh họa (Batch Drawing):
        #    - Quét toàn bộ câu hỏi có `has_diagram: true`.
        #    - Sử dụng Pillow / DiagramDrawer để vẽ đồ thị Oxy, hình học tam giác hoặc lưu đồ thuật toán.
        #    - Gom tất cả các tác vụ vẽ và chạy song song trong thread pool (`asyncio.gather`),
        #      giúp rút ngắn thời gian sinh ảnh từ vài giây xuống mili-giây.
        # 2. Xuất 2 bộ tài liệu riêng biệt chuẩn khảo thí (< 5MB):
        #    - [De_Thi]: Bộ câu hỏi sạch, phân chia Phần I (Trắc nghiệm) và Phần II (Tự luận), không lộ đáp án.
        #    - [Huong_Dan_Giai]: Bảng đáp án tổng hợp, lời giải từng bước, bẫy học sinh hay nhầm và rubric điểm.
        #    - Cả 4 file (DOCX đề, DOCX giải, PDF đề, PDF giải) được render đồng thời qua `asyncio.to_thread`.
        await _notify("`[4/4]` 📦 Đang vẽ sơ đồ & đóng gói 2 file **PDF/Word** song song (`< 5MB`)...", 0.85)

        # ── Batch vẽ sơ đồ: Gom tất cả diagram cần vẽ rồi chạy song song ──
        diag_dir = os.path.join(output_dir, "diagrams")
        Path(diag_dir).mkdir(parents=True, exist_ok=True)

        diagram_tasks: list[tuple[int, str, str, str]] = []  # (q_idx, diag_type, diag_file, q_num)
        for q_idx, q in enumerate(exam_json.get("questions", [])):
            if q.get("has_diagram"):
                diag_type = q.get("diagram_type", "coordinate_system")
                diag_file = os.path.join(diag_dir, f"diag_{job_id}_{q_idx+1}.png")
                diagram_tasks.append((q_idx, diag_type, diag_file, str(q.get("number", q_idx + 1))))

        def _draw_single(q_idx: int, diag_type: str, diag_file: str, q_num: str) -> str | None:
            try:
                if "triangle" in diag_type or "hinh_hoc" in diag_type:
                    diagram_drawer.draw_geometric_triangle(diag_file, title=f"Hình vẽ cho Câu {q_num}")
                elif "flowchart" in diag_type or "thuat_toan" in diag_type:
                    steps = ["Bắt đầu", "Nhập n và mảng A", "Kiểm tra điều kiện", "Cập nhật kết quả", "In và kết thúc"]
                    diagram_drawer.draw_flowchart_block(diag_file, steps=steps, title=f"Lưu đồ Câu {q_num}")
                else:
                    diagram_drawer.draw_coordinate_system(diag_file, title=f"Đồ thị cho Câu {q_num}")
                return diag_file
            except Exception as diag_err:
                logger.warning(f"Không thể vẽ sơ đồ cho câu {q_idx+1}: {diag_err}")
                return None

        # Chạy tất cả diagram trong thread pool đồng thời
        diagram_results = await asyncio.gather(
            *[asyncio.to_thread(_draw_single, *t) for t in diagram_tasks],
            return_exceptions=True,
        )
        diagram_paths: list[str] = [r for r in diagram_results if isinstance(r, str)]

        # ── Xuất 2 bộ tài liệu song song (Đề thi & Lời giải riêng biệt) ──
        meta = exam_json.get("metadata", {})
        meta["job_id"] = job_id
        meta["subject"] = subject
        meta["length_tier"] = length_tier

        content_blocks = exam_json.get("questions", [])
        solution_blocks = exam_json.get("solutions", [])
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        clean_subject = "".join(c for c in subject if c.isalnum() or c in "_-")
        fmt = output_format.lower()

        export_results: dict[str, list[str]] = {
            "exam_files": [],
            "solution_files": [],
            "azota_files": [],
            "quizizz_files": [],
            "anki_files": [],
            "latex_files": [],
            "audio_files": [],
        }

        # ── 1. Đánh giá Ma Trận Sư Phạm & Vẽ Biểu Đồ Radar Bloom ──
        radar_chart_file = os.path.join(output_dir, f"bloom_radar_{job_id}.png")
        pedagogy_eval = exam_analytics_service.evaluate_exam(exam_json, output_chart_path=radar_chart_file)
        meta["pedagogy_evaluation"] = pedagogy_eval.to_dict()
        if pedagogy_eval.radar_chart_path:
            meta["radar_chart_path"] = pedagogy_eval.radar_chart_path

        # ── 2. Tổng Hợp File Âm Thanh Bài Nghe (Listening Audio MP3) nếu có kịch bản ──
        script_turns = exam_json.get("listening_script") or meta.get("listening_script")
        audio_file = None
        if script_turns and isinstance(script_turns, list):
            await _notify("🎧 Đang tổng hợp file âm thanh bài nghe đa giọng đọc (Edge-TTS)...", 0.88)
            mp3_out = os.path.join(output_dir, f"[Audio_Listening]_{clean_subject}_{job_id}.mp3")
            try:
                audio_file = await listening_exam_service.synthesize_listening_audio(
                    script_turns=script_turns,
                    output_mp3_path=mp3_out,
                    job_id=job_id,
                )
                if audio_file:
                    export_results.setdefault("audio_files", []).append(audio_file)
                    export_results["exam_files"].append(audio_file)
                    meta["audio_file"] = audio_file
            except Exception as audio_err:
                logger.warning(f"Lỗi khi tổng hợp âm thanh bài nghe: {audio_err}")

        async def _export_parallel() -> None:
            """Chạy tất cả export tasks đồng thời trong thread pool."""
            tasks: list[Any] = []
            task_keys: list[tuple[str, str]] = []

            if fmt in ("word", "both", "all", "docx"):
                exam_docx = os.path.join(output_dir, f"[De_Thi]_{clean_subject}_{job_id}.docx")
                sol_docx = os.path.join(output_dir, f"[Huong_Dan_Giai]_{clean_subject}_{job_id}.docx")
                tasks.append(asyncio.to_thread(document_exporter.generate_exam_docx, meta, content_blocks, exam_docx, diagram_paths))
                task_keys.append(("exam_files", exam_docx))
                tasks.append(asyncio.to_thread(document_exporter.generate_solutions_docx, meta, solution_blocks, sol_docx, radar_chart_path=meta.get("radar_chart_path"), audio_script=script_turns))
                task_keys.append(("solution_files", sol_docx))

            if fmt in ("pdf", "both", "all"):
                exam_pdf = os.path.join(output_dir, f"[De_Thi]_{clean_subject}_{job_id}.pdf")
                sol_pdf = os.path.join(output_dir, f"[Huong_Dan_Giai]_{clean_subject}_{job_id}.pdf")
                tasks.append(asyncio.to_thread(document_exporter.generate_exam_pdf, meta, content_blocks, exam_pdf, diagram_paths))
                task_keys.append(("exam_files", exam_pdf))
                tasks.append(asyncio.to_thread(document_exporter.generate_solutions_pdf, meta, solution_blocks, sol_pdf, radar_chart_path=meta.get("radar_chart_path"), audio_script=script_turns))
                task_keys.append(("solution_files", sol_pdf))

            if fmt in ("azota", "csv", "all"):
                azota_csv = os.path.join(output_dir, f"[Azota]_{clean_subject}_{job_id}.csv")
                tasks.append(asyncio.to_thread(export_formats_service.export_azota_csv, meta, content_blocks, solution_blocks, azota_csv))
                task_keys.append(("azota_files", azota_csv))
                task_keys.append(("exam_files", azota_csv))

            if fmt in ("quizizz", "all"):
                quizizz_csv = os.path.join(output_dir, f"[Quizizz]_{clean_subject}_{job_id}.csv")
                tasks.append(asyncio.to_thread(export_formats_service.export_quizizz_csv, meta, content_blocks, solution_blocks, quizizz_csv))
                task_keys.append(("quizizz_files", quizizz_csv))
                task_keys.append(("exam_files", quizizz_csv))

            if fmt in ("anki", "flashcard", "all"):
                anki_txt = os.path.join(output_dir, f"[Anki]_{clean_subject}_{job_id}.txt")
                tasks.append(asyncio.to_thread(export_formats_service.export_anki_deck, meta, content_blocks, solution_blocks, anki_txt))
                task_keys.append(("anki_files", anki_txt))
                task_keys.append(("exam_files", anki_txt))

            if fmt in ("latex", "tex", "all"):
                latex_tex = os.path.join(output_dir, f"[LaTeX]_{clean_subject}_{job_id}.tex")
                tasks.append(asyncio.to_thread(export_formats_service.export_latex_tex, meta, content_blocks, solution_blocks, latex_tex))
                task_keys.append(("latex_files", latex_tex))
                task_keys.append(("exam_files", latex_tex))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for (key, filepath), result in zip(task_keys, results):
                if isinstance(result, Exception):
                    logger.error(f"Lỗi xuất file {filepath}: {result}")
                else:
                    if filepath not in export_results[key]:
                        export_results[key].append(filepath)

        await _export_parallel()

        total_elapsed = time.time() - start_timestamp
        await _notify(
            f"✅ **Hoàn tất 100%!** Đã tạo thành công các file tài liệu."
            f" _(Tổng thời gian: {total_elapsed:.0f}s)_",
            1.0,
        )
        logger.info(
            f"🎉 Job {job_id} hoàn tất trong {total_elapsed:.1f}s | "
            f"diagrams={len(diagram_paths)} | files={len(export_results['exam_files'])+len(export_results['solution_files'])}"
        )

        return {
            "job_id": job_id,
            "metadata": meta,
            "exam_data": exam_json,
            "exam_files": export_results.get("exam_files", []),
            "solution_files": export_results.get("solution_files", []),
            "azota_files": export_results.get("azota_files", []),
            "quizizz_files": export_results.get("quizizz_files", []),
            "anki_files": export_results.get("anki_files", []),
            "latex_files": export_results.get("latex_files", []),
            "audio_files": export_results.get("audio_files", []),
            "radar_chart_path": pedagogy_eval.radar_chart_path,
            "pedagogy_evaluation": pedagogy_eval.to_dict(),
            "diagram_paths": diagram_paths,
            "elapsed_seconds": round(total_elapsed, 1),
        }


exam_generator_service = ExamGeneratorService()
