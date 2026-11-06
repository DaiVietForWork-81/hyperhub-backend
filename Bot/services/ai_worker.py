"""
services/ai_worker.py
Ollama Lifecycle & Background Problem Pre-Generator for Ranked 1:1 CP Arena.
Features:
- Starts Ollama background daemon on bot startup with OLLAMA_MODELS pointing to project ./models/
- Pre-generates high quality CP problems across all tiers (T8 -> HT1) and saves to data/ai_problems.json
- 30-second delay between generations to prevent CPU/RAM overload on 4GB RAM servers
- Automatically PAUSES background generation whenever an active 1:1 Duel is in progress to prioritize match resources.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any

from config.settings import settings
from services.ai_generator import ai_generator, TIER_GUIDELINES, DEFAULT_THEMES
from services.duel_problems import DuelProblem, PROBLEM_BANK
from services.hardware_profiler import ResourceGovernor

logger = logging.getLogger("AIWorker")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
AI_PROBLEMS_FILE = os.path.join(DATA_DIR, "ai_problems.json")
MODELS_DIR = os.path.join(PROJECT_DIR, "models")

# Cooldown sau khi AI Core chat xong: Worker vẫn chạy chậm để RAM/Ollama hồi phục
AI_CHAT_COOLDOWN_SEC = 120
AI_CHAT_RECENT_SEC = 300

# Cấu hình kiểm soát kho đề thích ứng (Adaptive Problem Stock Management)
TIER_STOCK_MIN = 5         # Mức tối thiểu mỗi Tier: Nếu < 5 bài -> Coi là THIẾU ĐỀ
TIER_STOCK_COMFORT = 10    # Mức dồi dào: Nếu >= 10 bài -> Coi là ĐỦ ĐỀ
TIER_STOCK_MAX = 15        # Mức tối đa mỗi Tier: Nếu >= 15 bài -> QUÁ NHIỀU ĐỀ, NGỪNG SINH CHO TIER NÀY
TOTAL_BANK_MAX = 120       # Tổng số bài tối đa toàn bộ kho: Đạt mốc này -> TẠM DỪNG HOÀN TOÀN TỰ SINH

_ollama_process: subprocess.Popen | None = None


def start_ollama_daemon() -> None:
    """
    Khởi động tiến trình Ollama nền khi bot khởi động (nếu chưa chạy).
    Tự động gắn biến môi trường OLLAMA_MODELS trỏ trực tiếp vào thư mục models/ của project (0 MB ổ C:).
    Hỗ trợ linh hoạt cả Linux (Ubuntu) và Windows.
    """
    global _ollama_process
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.environ["OLLAMA_MODELS"] = MODELS_DIR

    # Kiểm tra xem Ollama đã chạy sẵn trên máy chưa
    is_running, _ = ai_generator.check_connection()
    if is_running:
        logger.info("[Ollama Daemon] Ollama server đã đang chạy sẵn trên hệ thống.")
        return

    try:
        env = os.environ.copy()
        env["OLLAMA_MODELS"] = MODELS_DIR
        try:
            from services.hardware import get_gpu_info, classify_system

            cls = classify_system()
            profile = cls.get("profile", "auto")

            # Chỉ bật Flash Attention khi có GPU rời mạnh (NVIDIA hoặc AMD ROCm full)
            if profile in ("nvidia_full", "amd_full"):
                env["OLLAMA_FLASH_ATTENTION"] = "1"
                best_vram = 0.0
                for _g in get_gpu_info():
                    if _g.get("vendor") in ("nvidia", "amd"):
                        best_vram = max(best_vram, float(_g.get("vram_total_gb") or 0))
                if best_vram < 8:
                    env["OLLAMA_KV_CACHE_TYPE"] = "q8_0"
            else:
                # Trên CPU hoặc GPU đời cũ (AMD Legacy R5 M335 / Intel iGPU):
                # TẮT tuyệt đối Flash Attention và q8_0 KV-cache để tránh lỗi rác token / NaN activations
                env["OLLAMA_FLASH_ATTENTION"] = "0"
                env["OLLAMA_KV_CACHE_TYPE"] = "f16"

            # Tối ưu AMD ROCm: nếu người dùng cấu hình HSA_OVERRIDE_GFX_VERSION trong .env
            hsa_ver = getattr(settings, "HSA_OVERRIDE_GFX_VERSION", None) or os.getenv("HSA_OVERRIDE_GFX_VERSION")
            if hsa_ver:
                env["HSA_OVERRIDE_GFX_VERSION"] = str(hsa_ver)
                logger.info(f"[Ollama Daemon] Thiết lập HSA_OVERRIDE_GFX_VERSION={hsa_ver} cho AMD ROCm.")

            # Bảo vệ card AMD cũ: nếu là amd_legacy (VRAM <= 2GB) và OLLAMA_NUM_GPU chưa được ép thủ công
            if profile == "amd_legacy" and int(getattr(settings, "OLLAMA_NUM_GPU", 0) or 0) <= 0:
                env["OLLAMA_NUM_GPU"] = "0"
                logger.info(f"[Ollama Daemon] GPU AMD đời cũ ({cls.get('label')}) -> Tự động bật CPU fallback an toàn.")
        except Exception as e:
            env["OLLAMA_FLASH_ATTENTION"] = "0"

        # Tìm kiếm binary ollama đa nền tảng: ưu tiên thư mục ollama_bin/ trong project
        portable_candidates = [
            os.path.join(PROJECT_DIR, "ollama_bin", "ollama"),
            os.path.join(PROJECT_DIR, "ollama_bin", "ollama.exe"),
        ]
        ollama_cmd = "ollama"
        for candidate in portable_candidates:
            if os.path.isfile(candidate):
                if sys.platform != "win32":
                    try:
                        # Đảm bảo quyền thực thi trên Linux/macOS
                        mode = os.stat(candidate).st_mode
                        os.chmod(candidate, mode | 0o755)
                    except Exception as pe:
                        logger.debug(f"[Ollama Daemon] Không thể gán chmod +x cho {candidate}: {pe}")
                ollama_cmd = candidate
                break
        else:
            # Nếu không có trong ollama_bin, tìm trong PATH hệ thống
            found_which = shutil.which("ollama")
            if found_which:
                ollama_cmd = found_which

        # Thêm ollama_bin vào PATH nếu thư mục tồn tại
        portable_bin_dir = os.path.join(PROJECT_DIR, "ollama_bin")
        if os.path.exists(portable_bin_dir):
            env["PATH"] = portable_bin_dir + os.pathsep + env.get("PATH", "")

        # Khởi chạy ollama serve ở background
        if sys.platform == "win32":
            _ollama_process = subprocess.Popen(
                [ollama_cmd, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        else:
            _ollama_process = subprocess.Popen(
                [ollama_cmd, "serve"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        logger.info(f"[Ollama Daemon] Đã khởi động Ollama ({ollama_cmd}) tiến trình nền (Models: {MODELS_DIR}).")
    except Exception as e:
        logger.warning(f"[Ollama Daemon] Không thể tự động khởi động 'ollama serve': {e}")


def stop_ollama_daemon() -> None:
    """Tắt tiến trình Ollama khi Bot tắt."""
    global _ollama_process
    if _ollama_process:
        try:
            if sys.platform != "win32":
                import signal
                try:
                    os.killpg(os.getpgid(_ollama_process.pid), signal.SIGTERM)
                except Exception:
                    _ollama_process.terminate()
            else:
                _ollama_process.terminate()
            _ollama_process.wait(timeout=5)
            logger.info("[Ollama Daemon] Đã dừng tiến trình Ollama nền an toàn.")
        except Exception as e:
            logger.warning(f"[Ollama Daemon] Lỗi khi dừng Ollama: {e}")
        _ollama_process = None


def load_cached_problems_into_bank() -> int:
    """Nạp các bài toán đã được lưu trong data/ai_problems.json vào PROBLEM_BANK."""
    if not os.path.exists(AI_PROBLEMS_FILE):
        return 0

    loaded_count = 0
    try:
        with open(AI_PROBLEMS_FILE, "r", encoding="utf-8") as f:
            raw_list = json.load(f)

        existing_ids = {p.id for p in PROBLEM_BANK}
        for item in raw_list:
            if item.get("id") not in existing_ids:
                problem = DuelProblem(
                    id=item["id"],
                    name=item["name"],
                    tier=item["tier"],
                    division=item["division"],
                    rating_display=item["rating_display"],
                    statement=item["statement"],
                    input_format=item["input_format"],
                    output_format=item["output_format"],
                    constraints=item["constraints"],
                    sample_input=item["sample_input"],
                    sample_output=item["sample_output"],
                    secret_tests=item.get("secret_tests", []),
                    time_limit_minutes=item.get("time_limit_minutes", 15),
                    max_code_size_kb=item.get("max_code_size_kb", 64),
                    solution_code=item.get("solution_code", ""),
                )
                PROBLEM_BANK.append(problem)
                existing_ids.add(problem.id)
                loaded_count += 1

        if loaded_count > 0:
            logger.info(f"[AI Storage] Đã nạp thành công {loaded_count} bài toán AI từ cache '{AI_PROBLEMS_FILE}'")
    except Exception as e:
        logger.error(f"[AI Storage] Lỗi khi nạp file cache {AI_PROBLEMS_FILE}: {e}")

    return loaded_count


async def save_problem_to_cache(problem: DuelProblem) -> None:
    """Lưu bài toán vừa sinh vào file JSON để tái sử dụng vĩnh viễn (đã qua kiểm duyệt chất lượng)."""
    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        from services.ai_problem_upgrader import audit_problem
        is_valid, issues = audit_problem(problem)
        if not is_valid:
            logger.warning(f"[AI Storage] Bài '{problem.id}' không đạt chuẩn audit ({issues}), bỏ qua không lưu!")
            return
    except Exception as audit_err:
        logger.debug(f"[AI Storage] Bỏ qua kiểm tra audit: {audit_err}")

    from services.duel_problems import TIER_DEFAULT_RATINGS
    calc_rating = getattr(problem, "rating", None) or TIER_DEFAULT_RATINGS.get(problem.tier, 800)

    current_data = []
    if os.path.exists(AI_PROBLEMS_FILE):
        try:
            with open(AI_PROBLEMS_FILE, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        except Exception:
            current_data = []

    # Kiểm tra trùng lặp ID
    if not any(item.get("id") == problem.id for item in current_data):
        current_data.append({
            "id": problem.id,
            "name": problem.name,
            "tier": problem.tier,
            "division": problem.division,
            "rating": calc_rating,
            "rating_display": problem.rating_display,
            "statement": problem.statement,
            "input_format": problem.input_format,
            "output_format": problem.output_format,
            "constraints": problem.constraints,
            "sample_input": problem.sample_input,
            "sample_output": problem.sample_output,
            "secret_tests": problem.secret_tests,
            "time_limit_minutes": problem.time_limit_minutes,
            "max_code_size_kb": problem.max_code_size_kb,
            "solution_code": problem.solution_code,
            "solution_cpp": getattr(problem, "solution_cpp", ""),
            "solution_py": getattr(problem, "solution_py", ""),
            "tags": getattr(problem, "tags", []),
            "time_limit_sec": getattr(problem, "time_limit_sec", 1.0),
            "memory_limit_mb": getattr(problem, "memory_limit_mb", 256),
        })
        try:
            # Ghi atomic async: ghi ra file tạm trong thread pool để không block event loop
            tmp_file = AI_PROBLEMS_FILE + ".tmp"
            
            def _write_json():
                with open(tmp_file, "w", encoding="utf-8", newline="\n") as f:
                    json.dump(current_data, f, ensure_ascii=False, indent=2)
            
            await asyncio.to_thread(_write_json)
            await asyncio.to_thread(os.replace, tmp_file, AI_PROBLEMS_FILE)
            logger.info(f"[AI Storage] Đã lưu bài '{problem.id}' ({problem.name}, Rating: {calc_rating}) vào {AI_PROBLEMS_FILE}")
        except Exception as e:
            logger.error(f"[AI Storage] Lỗi khi lưu vào {AI_PROBLEMS_FILE}: {e}")


class ProblemWorker:
    """Worker sinh đề nền thông minh với cơ chế chống quá tải."""

    def __init__(self):
        self._is_running = False
        self._task: asyncio.Task | None = None
        self.delay_between_problems_sec = 5

    def get_current_storage_bytes(self) -> int:
        """Lấy dung lượng file lưu trữ ai_problems.json hiện tại trên ổ cứng."""
        if os.path.exists(AI_PROBLEMS_FILE):
            try:
                return os.path.getsize(AI_PROBLEMS_FILE)
            except Exception:
                pass
        return 0

    def get_activity_load(self, bot: Any) -> tuple[int, str]:
        """
        Xác định thời gian nghỉ động (Min 1s, Max 45s) DỰA VÀO CÔNG VIỆC BOT ĐANG THỰC HIỆN:
        - Hoàn toàn rảnh rỗi (0 task): 1s (Min)
        - Đang kết nối Voice / Tác vụ nhẹ: 2s - 8s
        - AI vừa chat < 5 phút (cooldown): +10s
        - Đang phát nhạc Voice / Tác vụ vừa: 15s - 30s
        - AI vừa chat < 2 phút (cooldown): +25s
        - Đang có trận đấu Ranked 1:1 / AI đang chat / Tác vụ nặng: 35s - 45s (Max)
        """
        score = 1.0  # Min 1s

        active_duels_count = 0
        is_music_playing = False
        is_voice_connected = False
        queue_len = 0

        if bot:
            # 1. Kiểm tra trận đấu Ranked 1:1
            try:
                ranked_cog = bot.get_cog("RankedDuelCog")
                if ranked_cog and hasattr(ranked_cog, "matchmaker"):
                    sessions = getattr(ranked_cog.matchmaker, "active_sessions", {})
                    active_duels_count = sum(1 for s in sessions.values() if getattr(s, "is_active", False))
                    score += active_duels_count * 35.0
            except Exception:
                pass

            # 2. Kiểm tra phát nhạc Voice Channel & Hàng đợi
            try:
                player = getattr(bot, "player", None)
                if player:
                    is_voice_connected = player.is_connected()
                    is_music_playing = player.is_playing()
                    queue_len = len(getattr(player, "queue", []))

                    if is_music_playing:
                        score += 20.0 + min(10.0, queue_len * 2.0)
                    elif is_voice_connected:
                        score += 3.0
            except Exception:
                pass

        # 3. Kiểm tra AI Core đang chat / vừa chat (tránh xung đột Ollama + quá tải RAM)
        #    (lazy import để tránh circular import với services.ai_core)
        ai_busy_now = False
        ai_recent_sec: float | None = None
        try:
            from services.ai_core import ai_core as _ai_core

            if getattr(_ai_core, "state", "IDLE") != "IDLE":
                ai_busy_now = True
                score += 40.0
            else:
                last_llm = float(getattr(_ai_core, "last_llm_call_time", 0.0) or 0.0)
                if last_llm > 0:
                    ai_recent_sec = time.time() - last_llm
                    if ai_recent_sec < AI_CHAT_COOLDOWN_SEC:
                        score += 25.0
                    elif ai_recent_sec < AI_CHAT_RECENT_SEC:
                        score += 10.0
        except Exception:
            pass

        delay_sec = max(1, min(45, int(round(score))))

        if ai_busy_now:
            load_msg = f"💬 AI đang chat ({delay_sec}s/bài - Nhường RAM/CPU cho Ollama trả lời user)"
        elif ai_recent_sec is not None and ai_recent_sec < AI_CHAT_COOLDOWN_SEC:
            load_msg = f"💬 Cooldown sau AI chat ({delay_sec}s/bài - AI vừa chat {ai_recent_sec:.0f}s trước)"
        elif delay_sec >= 35:
            load_msg = f"🔴 Tải cao ({delay_sec}s/bài - Có {active_duels_count} trận Ranked 1:1)"
        elif delay_sec >= 15:
            load_msg = f"🟡 Tải vừa ({delay_sec}s/bài - Đang phát nhạc Voice, queue {queue_len})"
        elif delay_sec > 1:
            load_msg = f"🟢 Tải nhẹ ({delay_sec}s/bài - Voice kết nối/hoạt động nhẹ)"
        else:
            load_msg = f"⚡ Siêu rảnh rỗi ({delay_sec}s/bài - Không có công việc nào)"

        return delay_sec, load_msg

    def get_inventory_status(self) -> dict:
        """
        Thống kê tình trạng kho đề chi tiết theo từng Tier:
        - total: tổng số bài trong PROBLEM_BANK
        - counts: dict {tier: số lượng bài}
        - fresh_counts: dict {tier: số lượng bài chưa dùng hoặc dùng < 3 lần}
        - starving_tiers: các tier thiếu bài (< TIER_STOCK_MIN)
        - saturated_tiers: các tier đã quá nhiều bài (>= TIER_STOCK_MAX)
        - is_oversaturated: toàn bộ kho đã quá nhiều bài (>= TOTAL_BANK_MAX hoặc tất cả tier >= TIER_STOCK_MAX)
        """
        tier_list = ["T8", "T7", "T6", "T5", "T4", "T3", "LT2", "MT2", "HT2", "LT1", "MT1", "HT1"]
        total = len(PROBLEM_BANK)
        counts = {}
        fresh_counts = {}
        starving = []
        saturated = []

        for t in tier_list:
            probs = [p for p in PROBLEM_BANK if p.tier == t]
            counts[t] = len(probs)
            fresh = sum(1 for p in probs if getattr(p, "used_count", 0) < 3)
            fresh_counts[t] = fresh
            if fresh < TIER_STOCK_MIN:
                starving.append(t)
            elif fresh >= TIER_STOCK_MAX:
                saturated.append(t)

        is_oversaturated = (total >= TOTAL_BANK_MAX) or (len(saturated) >= len(tier_list))

        return {
            "total": total,
            "counts": counts,
            "fresh_counts": fresh_counts,
            "starving": starving,
            "saturated": saturated,
            "is_oversaturated": is_oversaturated,
        }

    def get_crowd_and_demand_status(self, bot: Any) -> dict:
        """
        Xác định độ đông đúc và các Tier đang có nhu cầu cấp bách:
        - active_duels_count: số trận đang diễn ra
        - queue_count: số người đang trong hàng chờ
        - is_crowded: có người đang đấu hoặc đang tìm trận
        - hot_tiers: danh sách các tier đang có người thi đấu hoặc xếp hàng
        """
        active_duels_count = 0
        active_tiers = set()
        queue_count = 0
        queue_tiers = set()

        if bot:
            try:
                ranked_cog = bot.get_cog("RankedDuelCog")
                if ranked_cog and hasattr(ranked_cog, "matchmaker"):
                    mm = ranked_cog.matchmaker
                    sessions = getattr(mm, "active_sessions", {})
                    for s in sessions.values():
                        if getattr(s, "is_active", False):
                            active_duels_count += 1
                            if hasattr(s, "p1_ranked_rank"):
                                active_tiers.add(s.p1_ranked_rank)
                            if hasattr(s, "p2_ranked_rank"):
                                active_tiers.add(s.p2_ranked_rank)
                            if getattr(s, "custom_tier", None):
                                active_tiers.add(s.custom_tier)

                    queue = getattr(mm, "queue", [])
                    queue_count = len(queue)
                    for q in queue:
                        r = getattr(q, "ranked_rank", None)
                        if r:
                            queue_tiers.add(r)
            except Exception:
                pass

        is_crowded = (active_duels_count > 0 or queue_count > 0)
        hot_tiers = list(active_tiers | queue_tiers)

        return {
            "active_duels_count": active_duels_count,
            "queue_count": queue_count,
            "is_crowded": is_crowded,
            "hot_tiers": hot_tiers,
        }

    def get_adaptive_delay(self, bot: Any, target_tier: str | None = None) -> tuple[int, str]:
        """
        Xác định độ trễ sinh đề thích ứng:
        1. Quá nhiều bài đang có -> Không sinh / sinh rất chậm (60s - 180s).
        2. Khi đông & ít đề -> Tăng tốc sinh nhiều / nhanh (1s - 2s).
        3. Khi đông & đã nhiều đề -> Tạm dừng / sinh chậm (35s - 45s) để nhường CPU cho trận đấu.
        4. Rảnh rỗi -> Tốc độ bình thường theo tải bot.
        """
        if self.is_ai_chat_active():
            return 40, "💬 AI đang chat (Nhường RAM/CPU cho Ollama trả lời user)"

        inv = self.get_inventory_status()
        crowd = self.get_crowd_and_demand_status(bot)

        if inv["is_oversaturated"]:
            return 180, f"🛑 KHO ĐỀ QUÁ DỒI DÀO ({inv['total']} bài) -> Sinh rất chậm / nghỉ 180s"

        target_fresh = inv["fresh_counts"].get(target_tier, 0) if target_tier else min(inv["fresh_counts"].values(), default=0)

        # Khi ĐÔNG NGƯỜI CHƠI (đang đấu hoặc đang chờ)
        if crowd["is_crowded"]:
            is_hot_starving = any(t in inv["starving"] for t in crowd["hot_tiers"])
            if target_fresh < TIER_STOCK_MIN or is_hot_starving:
                return 2, f"⚡ TURBO CẤP BÁCH: Đông người chơi & thiếu đề (Tier {target_tier}: {target_fresh} bài) -> Sinh siêu tốc (2s/bài)"
            elif target_fresh < TIER_STOCK_COMFORT:
                return 5, f"🔥 TĂNG TỐC: Đông người chơi & cần nạp thêm đề (Tier {target_tier}: {target_fresh} bài) -> Sinh nhanh (5s/bài)"
            else:
                return 45, f"⚔️ NHƯỜNG TÀI NGUYÊN: Đang có trận đấu & kho đề Tier {target_tier} đã đủ ({target_fresh} bài) -> Nghỉ 45s"

        # Khi VẮNG / RẢNH RỖI
        if target_fresh >= TIER_STOCK_MAX:
            return 60, f"🛑 ĐỦ ĐỀ: Tier {target_tier} đã đạt {target_fresh} bài -> Sinh chậm (60s/bài)"
        elif target_fresh < TIER_STOCK_MIN:
            base_delay, _ = self.get_activity_load(bot)
            return min(base_delay, 5), f"🌱 BỔ SUNG ĐỀ: Tier {target_tier} ít đề ({target_fresh} bài) -> Bổ sung (5s/bài)"
        else:
            return self.get_activity_load(bot)

    def is_ai_chat_active(self) -> bool:
        """AI Core có đang chat với user không (đang ANALYZING/PATCHING hoặc vừa gọi LLM)."""
        try:
            from services.ai_core import ai_core as _ai_core

            return bool(_ai_core.is_busy(cooldown_sec=AI_CHAT_COOLDOWN_SEC))
        except Exception:
            return False

    def has_active_duels(self, bot: Any) -> bool:
        """Kiểm tra xem hiện tại có trận Duel 1:1 nào đang diễn ra trên Server hay không."""
        try:
            ranked_cog = bot.get_cog("RankedDuelCog")
            if ranked_cog and hasattr(ranked_cog, "matchmaker"):
                sessions = getattr(ranked_cog.matchmaker, "active_sessions", {})
                return any(getattr(s, "is_active", False) for s in sessions.values())
        except Exception:
            pass
        return False

    async def start(self, bot: Any) -> None:
        """Bắt đầu chu trình sinh đề nền sau khi Bot đã khởi động hoàn tất."""
        if self._is_running:
            return

        self._is_running = True
        # Nạp các bài toán đã lưu từ trước
        load_cached_problems_into_bank()

        # Chờ 15 giây sau khi bot khởi động hoàn toàn mới bắt đầu làm việc
        await asyncio.sleep(15)
        self._task = asyncio.create_task(self._run_loop(bot))
        logger.info("[AI Worker] Đã khởi động Background Worker sinh đề nền (Tự điều tiết thích ứng kho đề).")

    async def stop(self) -> None:
        """Dừng worker."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self, bot: Any) -> None:
        """Vòng lặp điều phối thích ứng thông minh theo tải và số lượng kho đề."""
        tier_list = ["T8", "T7", "T6", "T5", "T4", "T3", "LT2", "MT2", "HT2", "LT1", "MT1", "HT1"]

        while self._is_running:
            # 1. Kiểm tra kết nối Ollama
            is_ok, _ = ai_generator.check_connection()
            if not is_ok:
                await asyncio.sleep(60)
                continue

            inv = self.get_inventory_status()
            crowd = self.get_crowd_and_demand_status(bot)

            # 2. QUÁ NHIỀU BÀI ĐANG CÓ -> AI KHÔNG TỰ SINH THÊM / SINH CỰC CHẬM (Ngủ đông 180s)
            if inv["is_oversaturated"] or (len(inv["starving"]) == 0 and inv["total"] >= TOTAL_BANK_MAX):
                logger.info(f"[AI Worker] 🛑 Kho đề đã quá dồi dào ({inv['total']} bài trên 12 Tier). Không tự sinh thêm đề, ngủ đông 180s tiết kiệm 100% CPU/RAM...")
                await asyncio.sleep(180)
                continue

            # 3. Sắp xếp thứ tự ưu tiên sinh đề theo nhu cầu:
            # - Khi đông & ít đề: Hot tiers bị thiếu đề được ưu tiên số 1
            # - Các tier thiếu đề khác (< TIER_STOCK_MIN)
            # - Các tier chưa đầy (< TIER_STOCK_MAX)
            urgent_tiers = [t for t in crowd["hot_tiers"] if t in inv["starving"]]
            remaining_starving = [t for t in inv["starving"] if t not in urgent_tiers]
            normal_tiers = [t for t in tier_list if t not in inv["saturated"] and t not in urgent_tiers and t not in remaining_starving]

            tiers_to_generate = urgent_tiers + remaining_starving + normal_tiers

            if not tiers_to_generate:
                logger.info(f"[AI Worker] ✨ Mọi Tier đều đã đạt tối đa ({inv['total']} bài). Nghỉ 120s...")
                await asyncio.sleep(120)
                continue

            generated_in_cycle = 0
            for tier in tiers_to_generate:
                if not self._is_running:
                    break

                existing_for_tier = [p for p in PROBLEM_BANK if p.tier == tier]
                fresh_count = sum(1 for p in existing_for_tier if getattr(p, "used_count", 0) < 3)

                # NẾU QUÁ NHIỀU BÀI CHO TIER NÀY -> Bỏ qua không sinh thêm
                if fresh_count >= TIER_STOCK_MAX:
                    continue

                # Ưu tiên AI Chat: Luôn nhường CPU/RAM khi AI đang trả lời chat
                while self.is_ai_chat_active():
                    logger.info("[AI Worker] 💬 AI Core đang chat với user -> Tạm dừng sinh đề ngầm để nhường tài nguyên...")
                    await asyncio.sleep(10)

                # Trận đấu Ranked:
                # Nếu ĐÔNG & ĐÃ ĐỦ ĐỀ (>= TIER_STOCK_COMFORT) -> Tạm nghỉ nhường tài nguyên
                # Nếu ĐÔNG & ÍT ĐỀ (< TIER_STOCK_COMFORT) -> KHÔNG NGHỈ, TIẾP TỤC SINH CẤP TỐC!
                crowd_current = self.get_crowd_and_demand_status(bot)
                if crowd_current["is_crowded"] and fresh_count >= TIER_STOCK_COMFORT:
                    logger.info(f"[AI Worker] ⚔️ Đang có trận đấu & Tier {tier} đã có đủ {fresh_count} bài -> Tạm nhường CPU...")
                    await asyncio.sleep(20)
                    continue

                # 4. Tiến hành sinh bài mới
                try:
                    from services.online_context import get_realworld_theme
                    theme = await get_realworld_theme()
                except Exception:
                    import random
                    theme = random.choice(DEFAULT_THEMES)

                logger.info(f"[AI Worker] 🚀 Khởi tạo đề cho Tier {tier} ({fresh_count} bài khả dụng / {len(existing_for_tier)} tổng)...")

                try:
                    from services.problem_factory import generate_synthesized_problem
                    problem = generate_synthesized_problem(tier=tier, theme=theme)
                    if problem:
                        PROBLEM_BANK.append(problem)
                        await save_problem_to_cache(problem)
                        generated_in_cycle += 1
                        logger.info(f"[AI Worker] ✅ Đã nạp bài '{problem.name}' ({tier}) vào kho đề!")

                        delay_sec, load_msg = self.get_adaptive_delay(bot, target_tier=tier)
                        logger.info(f"[AI Worker] ⏳ Điều tiết thông minh: {load_msg}...")
                        await asyncio.sleep(delay_sec)
                except Exception as e:
                    logger.error(f"[AI Worker] Lỗi khởi tạo đề {tier}: {e}")
                    await asyncio.sleep(10)

            total_problems = len(PROBLEM_BANK)
            cycle_rest, cycle_msg = self.get_adaptive_delay(bot)
            if generated_in_cycle == 0:
                logger.info(f"[AI Worker] ✨ Kho đề đã đủ ({total_problems} bài trên 12 bậc Rank). Nghỉ {cycle_rest}s...")
            else:
                logger.info(f"[AI Worker] 🎉 Hoàn tất đợt sinh! Kho hiện tại: {total_problems} bài. Nghỉ {cycle_rest}s...")
            await asyncio.sleep(cycle_rest)


# Singleton
problem_worker = ProblemWorker()
