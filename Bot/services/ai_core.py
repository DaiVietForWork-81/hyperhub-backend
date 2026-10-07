"""
services/ai_core.py
AI Core & Bot Supervisor Service (model name lấy từ config AI_MODEL_NAME).

Chức năng trung tâm:
1. Quản lý trạng thái AI Core:
   - IDLE: Khi bot ổn định, KHÔNG gọi LLM, KHÔNG tự sửa, KHÔNG spam Discord.
   - ANALYZING: Khi tiếp nhận yêu cầu từ Admin hoặc phát hiện lỗi hệ thống.
   - PATCHING: Khi Admin yêu cầu sửa lỗi (quy trình: phân tích -> minimal patch -> AST validate -> test -> rollback nếu fail).
2. Bảo mật (Security & Privacy):
   - Tự động lọc sạch Discord Token, API Keys, Passwords, .env trước khi gửi cho LLM hoặc hiển thị lên Discord.
   - Chặn hành vi nguy hiểm (xóa DB, shutdown server) nếu không có xác nhận admin.
3. Resource Efficiency:
   - Ưu tiên xử lý deterministic (rule-based log parsing, health checks) trước.
    - Chỉ gọi Qwen3 qua Ollama khi cần suy luận logic.
4. Auto Monitoring:
   - Tự động ghi nhận exception/crash/command failure khi có error event.
   - Quét log định kỳ để phát hiện lỗi mới.
5. Destructive Action Confirmation:
   - Yêu cầu admin xác nhận trước khi thực hiện hành động nguy hiểm.
"""

from __future__ import annotations

import ast
import asyncio
import collections
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from config.settings import settings, AI_MODEL_NAME
from services.self_healer import SelfHealer
from services.hardware import format_hardware_report, get_hardware_info, recommend_llm_options
from services.knowledge_base import kb
from utils.logger import get_logger

logger = get_logger("AICore")

# ============================================================
# DANGEROUS ACTIONS requiring admin confirmation
# ============================================================
DESTRUCTIVE_ACTIONS = frozenset([
    "delete database",
    "delete files",
    "reset database",
    "shutdown server",
    "restart bot",
    "drop table",
    "remove all",
    "xóa database",
    "xóa file",
    "xóa dữ liệu",
    "khởi động lại",
    "tắt server",
    "shutdown",
])

# ============================================================
# RULE-BASED DIAGNOSTIC PATTERNS (deterministic, 0 token)
# ============================================================
LOG_ERROR_PATTERNS = [
    (re.compile(r"(?i)(?:unhandled.?exception|traceback|error:)"), "EXCEPTION"),
    (re.compile(r"(?i)(?:command.?failed|command.?raised|on_command_error)"), "COMMAND_FAILURE"),
    (re.compile(r"(?i)(?:database.?error|sqlite.?error|sql.?error)"), "DATABASE_ERROR"),
    (re.compile(r"(?i)(?:connection.?refused|timeout|timed.?out)"), "API_TIMEOUT"),
    (re.compile(r"(?i)(?:memory.?error|out.?of.?memory|oom)"), "RESOURCE_ERROR"),
    (re.compile(r"(?i)(?:import.?error|module.?not.?found|ModuleNotFoundError)"), "DEPENDENCY_ERROR"),
]


class ConversationMemory:
    """Quản lý lịch sử hội thoại đa lượt (multi-turn memory) theo session (user_id / channel_id).
    Giúp AI nhớ ngữ cảnh, hiểu đại từ/tham chiếu, trò chuyện tự nhiên và mượt mà như terminal Ollama."""

    def __init__(self, max_turns: int = 12, ttl_seconds: float = 1800.0):
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self._threads: dict[str, dict[str, Any]] = {}

    def _clean_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._threads.items() if now - v.get("last_active", 0) > self.ttl_seconds]
        for k in expired:
            self._threads.pop(k, None)

    def get_history(self, session_key: str | int) -> list[dict[str, str]]:
        self._clean_expired()
        thread = self._threads.get(str(session_key))
        if not thread:
            return []
        return list(thread.get("messages", []))

    def add_turn(self, session_key: str | int, user_msg: str, assistant_msg: str) -> None:
        self._clean_expired()
        key = str(session_key)
        if key not in self._threads:
            self._threads[key] = {
                "last_active": time.time(),
                "messages": collections.deque(maxlen=self.max_turns * 2),
            }
        thread = self._threads[key]
        thread["last_active"] = time.time()
        thread["messages"].append({"role": "user", "content": user_msg})
        thread["messages"].append({"role": "assistant", "content": assistant_msg})

    def clear(self, session_key: str | int | None = None) -> None:
        if session_key is not None:
            self._threads.pop(str(session_key), None)
        else:
            self._threads.clear()


DEFAULT_CHAT_SYSTEM_PROMPT = (
    f"Bạn là AI Core ({AI_MODEL_NAME}) - Trợ lý AI thông minh, nhiệt tình và thân thiện của Discord Bot.\n"
    "Phong cách giao tiếp:\n"
    "1. Tự nhiên, linh hoạt, gần gũi và thông minh y như khi trò chuyện trực tiếp trên Ollama terminal.\n"
    "2. Trả lời bằng Tiếng Việt chuẩn, mượt mà, tự nhiên, sinh động, có thể dùng emoji phù hợp ngữ cảnh.\n"
    "3. Khả năng phong phú: Bạn giỏi về mọi lĩnh vực: lập trình (Python, C++, Java, Web, CP), toán học, khoa học, "
    "trò chuyện giải trí, hỗ trợ học tập, trả lời thắc mắc đời sống.\n"
    "4. Luôn theo dõi ngữ cảnh các lượt chat trước để hiểu rõ người dùng đang nói về ai hoặc điều gì.\n"
    "5. Tuyệt đối KHÔNG tiết lộ token, mật khẩu, API key hay thông tin bí mật hệ thống."
)


class AICoreState:
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    PATCHING = "PATCHING"


class AICore:
    """Trung tâm điều phối & giám sát AI Core (Qwen3 qua Ollama)."""

    def __init__(self):
        self.state = AICoreState.IDLE
        self.recent_errors: collections.deque[dict[str, Any]] = collections.deque(maxlen=50)
        self.last_activity_time = time.time()
        self.project_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        self._pending_confirmations: dict[str, dict[str, Any]] = {}
        self._last_log_scan_pos: int = 0
        self.plain_text_mode: bool = False
        # Timestamp lần gọi LLM gần nhất (để ProblemWorker nhường tài nguyên khi AI đang chat)
        self.last_llm_call_time: float = 0.0
        # Bộ nhớ hội thoại đa lượt (multi-turn memory)
        self.conversation_memory = ConversationMemory(max_turns=12, ttl_seconds=1800.0)

    @property
    def model_name(self) -> str:
        return AI_MODEL_NAME

    def is_busy(self, cooldown_sec: float = 120.0) -> bool:
        """AI có đang bận không: đang ANALYZING/PATCHING hoặc vừa gọi LLM trong cooldown."""
        if self.state != AICoreState.IDLE:
            return True
        try:
            return (time.time() - float(self.last_llm_call_time or 0.0)) < cooldown_sec
        except Exception:
            return False

    @property
    def base_url(self) -> str:
        return getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    # ================================================================
    # SECURITY: Sanitize all text before LLM or Discord output
    # ================================================================

    def sanitize_text(self, text: str) -> str:
        """Lọc bỏ toàn bộ token, mật khẩu, khóa bí mật khỏi văn bản."""
        if not text:
            return ""

        sanitized = str(text)

        # 1. Lọc Discord Bot Token
        sanitized = re.sub(
            r"(?i)(?:mfa\.[a-z0-9_-]{20,}|[a-z0-9_-]{23,30}\.[a-z0-9_-]{5,8}\.[a-z0-9_-]{25,45})",
            "[DISCORD_TOKEN_REDACTED]",
            sanitized,
        )

        # 2. Lọc các giá trị nhạy cảm từ settings
        secrets_to_redact = [
            getattr(settings, "DISCORD_TOKEN", ""),
            getattr(settings, "CF_API_KEY", ""),
            getattr(settings, "CF_API_SECRET", ""),
            getattr(settings, "SPOTIFY_CLIENT_SECRET", ""),
        ]

        for s in secrets_to_redact:
            if s and len(str(s).strip()) > 5:
                sanitized = sanitized.replace(str(s).strip(), "[REDACTED_SECRET]")

        # 3. Lọc pattern password=..., token=..., api_key=...
        sanitized = re.sub(
            r'(?i)\b(password|token|secret|api_key)\b\s*[:=]\s*["\']?(?!\[[A-Z0-9_]+\])([^"\'\s,]+)',
            r'\1=[REDACTED]',
            sanitized,
        )

        return sanitized

    # ================================================================
    # ERROR RECORDING & MONITORING
    # ================================================================

    def record_error(self, source: str, error: Exception | str, context: str = "") -> None:
        """Ghi nhận lỗi hệ thống vào bộ đệm giám sát."""
        err_msg = str(error)
        tb_str = ""
        if isinstance(error, Exception) and error.__traceback__:
            tb_str = "".join(traceback.format_tb(error.__traceback__))

        record = {
            "source": source,
            "message": self.sanitize_text(err_msg),
            "traceback": self.sanitize_text(tb_str),
            "context": self.sanitize_text(context),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.recent_errors.append(record)
        logger.warning(f"[AI Core Monitor] Đã ghi nhận lỗi từ '{source}': {err_msg[:120]}")

    def get_recent_errors(self, count: int = 10) -> list[dict[str, Any]]:
        """Lấy danh sách lỗi gần đây."""
        return list(self.recent_errors)[-count:]

    # ================================================================
    # LOG READING & RULE-BASED SCANNING
    # ================================================================

    def read_recent_logs(self, max_lines: int = 40) -> list[str]:
        """Đọc an toàn các dòng log gần nhất từ logs/bot.log."""
        log_file = self.project_root / "logs" / "bot.log"
        if not log_file.exists():
            return ["(Chưa có tệp logs/bot.log)"]

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                recent = lines[-max_lines:]
                return [self.sanitize_text(l.strip()) for l in recent if l.strip()]
        except Exception as e:
            return [f"(Lỗi đọc file log: {e})"]

    def scan_logs_for_errors(self) -> list[dict[str, str]]:
        """Quét log file theo rule-based patterns, trả về danh sách lỗi phát hiện (0 token)."""
        log_file = self.project_root / "logs" / "bot.log"
        if not log_file.exists():
            return []

        found_errors = []
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for line in lines[self._last_log_scan_pos:]:
                for pattern, category in LOG_ERROR_PATTERNS:
                    if pattern.search(line):
                        found_errors.append({
                            "category": category,
                            "line": self.sanitize_text(line.strip()[:300]),
                        })
                        break

            self._last_log_scan_pos = len(lines)
        except Exception:
            pass

        return found_errors

    # ================================================================
    # SOURCE CODE READING (for debugging)
    # ================================================================

    # File text được phép đọc (chặn secrets & binary)
    READABLE_SUFFIXES = frozenset({
        ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
        ".cfg", ".ini", ".bat", ".ps1", ".example",
    })
    BLOCKED_NAMES = frozenset({".env", "bot.db", "bot.db-journal", "bot.db-wal", "bot.db-shm"})
    SKIP_DIRS = frozenset({
        "__pycache__", ".git", ".venv", "venv", ".pytest_cache",
        "models", "ollama_bin", "logs", "data", "node_modules",
        ".local", "site-packages",
    })

    def read_source_file(self, file_path: str) -> dict[str, Any]:
        """Đọc nội dung file text trong dự án (chặn secrets, giới hạn 1 MB)."""
        target = Path(file_path)
        if not target.is_absolute():
            target = self.project_root / file_path

        try:
            target = target.resolve()
            if self.project_root.resolve() not in target.parents and target != self.project_root.resolve():
                return {"error": "Từ chối: đường dẫn nằm ngoài thư mục dự án."}
        except Exception:
            pass

        if not target.exists() or not target.is_file():
            return {"error": f"File không tồn tại: {file_path}"}
        if target.name in self.BLOCKED_NAMES or target.suffix == ".db":
            return {"error": f"Từ chối đọc file nhạy cảm: {target.name} (chứa secrets/dữ liệu)."}
        if target.suffix.lower() not in self.READABLE_SUFFIXES:
            return {"error": f"Chỉ hỗ trợ đọc file text ({sorted(self.READABLE_SUFFIXES)}): {target.name}"}
        if target.stat().st_size > 1_048_576:
            return {"error": f"File quá lớn ({target.stat().st_size / 1024:.0f} KB), giới hạn 1024 KB"}

        try:
            content = self.sanitize_text(target.read_text(encoding="utf-8", errors="ignore"))
            return {
                "path": str(target.relative_to(self.project_root)),
                "content": content,
                "lines": len(content.splitlines()),
                "size_kb": f"{target.stat().st_size / 1024:.1f}",
            }
        except Exception as e:
            return {"error": f"Lỗi đọc file: {e}"}

    def find_related_files(self, keyword: str, max_results: int = 25) -> list[str]:
        """Tìm file liên quan đến keyword trong TOÀN BỘ project (đệ quy, bỏ qua thư mục rác)."""
        results = []
        keyword_lower = keyword.lower()

        for path in self.project_root.rglob("*.py"):
            if len(results) >= max_results:
                break
            try:
                rel_parts = path.relative_to(self.project_root).parts
                if any(part in self.SKIP_DIRS or part.startswith(".") for part in rel_parts[:-1]):
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")
                if keyword_lower in content.lower() or keyword_lower in path.name.lower():
                    results.append(str(path.relative_to(self.project_root)))
            except Exception:
                continue

        return results

    def get_project_tree(self, max_entries: int = 120) -> str:
        """Liệt kê cây thư mục dự án (bỏ qua thư mục rác/binary)."""
        lines: list[str] = []
        count = 0

        def _walk(directory: Path, prefix: str = "") -> None:
            nonlocal count
            try:
                entries = sorted(
                    [e for e in directory.iterdir() if not e.name.startswith(".")],
                    key=lambda e: (not e.is_dir(), e.name.lower()),
                )
            except Exception:
                return
            for i, entry in enumerate(entries):
                if count >= max_entries:
                    lines.append("... (còn nữa, danh sách đã cắt ngắn)")
                    return
                if entry.name in self.SKIP_DIRS or entry.suffix in {".db", ".pyc"}:
                    continue
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}")
                count += 1
                if entry.is_dir():
                    extension = "    " if i == len(entries) - 1 else "│   "
                    _walk(entry, prefix + extension)

        _walk(self.project_root)
        return "\n".join(lines) if lines else "(Thư mục dự án rỗng)"

    # ================================================================
    # SYSTEM HEALTH DIAGNOSIS
    # ================================================================

    def diagnose_system_health(self) -> dict[str, Any]:
        """Chẩn đoán nhanh trạng thái hoạt động của toàn bộ các phân hệ Bot."""
        checks = {}

        # 1. Database Check
        db_path = self.project_root / "bot.db"
        checks["database"] = {
            "status": "OK" if db_path.exists() else "WARNING",
            "details": f"SQLite DB size: {db_path.stat().st_size / 1024:.1f} KB" if db_path.exists() else "File bot.db chưa tạo",
        }

        # 2. Ngân hàng đề bài Ranked 1:1
        problems_file = self.project_root / "data" / "ai_problems.json"
        if problems_file.exists():
            try:
                with open(problems_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                checks["problem_bank"] = {
                    "status": "OK",
                    "count": len(data),
                    "size_mb": f"{problems_file.stat().st_size / (1024 * 1024):.2f} MB",
                }
            except Exception as e:
                checks["problem_bank"] = {"status": "ERROR", "details": f"File JSON hỏng: {e}"}
        else:
            checks["problem_bank"] = {"status": "OK", "count": 0, "size_mb": "0 MB"}

        # 3. Lỗi gần đây
        recent_err_count = len(self.recent_errors)
        checks["error_rate"] = {
            "status": "OK" if recent_err_count == 0 else ("WARNING" if recent_err_count < 5 else "CRITICAL"),
            "recent_errors": recent_err_count,
        }

        # 4. Trạng thái AI Core
        checks["ai_core"] = {
            "model": self.model_name,
            "state": self.state,
            "status": "OK",
        }

        # 5. Phần cứng (CPU/RAM/GPU/Disk) — phục vụ auto-tune & báo cáo
        try:
            hw = get_hardware_info()
            ram = hw.get("ram", {})
            checks["hardware"] = {
                "status": "OK",
                "ram_free_gb": ram.get("free_gb"),
                "ram_total_gb": ram.get("total_gb"),
                "gpu_count": len(hw.get("gpus", [])),
                "details": format_hardware_report(hw),
            }
        except Exception as e:
            checks["hardware"] = {"status": "WARNING", "details": f"Không đọc được phần cứng: {e}"}

        # 6. Log scan (rule-based)
        new_errors = self.scan_logs_for_errors()
        if new_errors:
            checks["log_errors"] = {
                "status": "WARNING",
                "new_errors_found": len(new_errors),
                "categories": list({e["category"] for e in new_errors}),
            }

        return checks

    # ================================================================
    # DESTRUCTIVE ACTION CONFIRMATION
    # ================================================================

    def check_destructive_action(self, query: str) -> bool | str:
        """Kiểm tra xem query có chứa hành động nguy hiểm không.
        Returns False nếu an toàn, hoặc chuỗi xác nhận key nếu nguy hiểm.
        """
        q_lower = query.lower()
        for action in DESTRUCTIVE_ACTIONS:
            if action in q_lower:
                confirm_key = f"confirm_{int(time.time())}"
                self._pending_confirmations[confirm_key] = {
                    "action": action,
                    "query": query,
                    "timestamp": time.time(),
                }
                return confirm_key
        return False

    def validate_confirmation(self, confirm_key: str) -> bool:
        """Xác nhận hành động nguy hiểm từ admin."""
        if confirm_key in self._pending_confirmations:
            entry = self._pending_confirmations.pop(confirm_key)
            if time.time() - entry["timestamp"] < 300:
                return True
        return False

    # ================================================================
    # CHAT & CONVERSATION ENGINE (Multi-Turn Natural Chat)
    # ================================================================

    def _is_casual_chat(self, text: str) -> bool:
        """Detect chat casual: lời chào, trò chuyện thông thường."""
        chat_patterns = [
            r'^(hi|hello|hey|chào|chào bạn|xin chào|alo|e|ê|a|ơi)[\s!?.]*$',
            r'^(cảm ơn|thanks|thank you|tk|tks|cam on)[\s!?.]*$',
            r'^(tạm biệt|bye|goodbye|gg)[\s!?.]*$',
            r'^(khỏe không|how are you|khỏe ko|khoe khong)[\s!?.]*$',
            r'^(làm gì|what are you doing|lam gi|đang làm gì)[\s!?.]*$',
            r'^(ngủ chưa|ngu chua)[\s!?.]*$',
            r'^(ăn chưa|an chua)[\s!?.]*$',
            r'^(bạn là ai|who are you|bạn tên gì|ten gi)[\s!?.]*$',
        ]
        import re
        for pattern in chat_patterns:
            if re.match(pattern, text.strip(), re.IGNORECASE):
                return True
        return False

    async def _handle_casual_chat(
        self, user_query: str, session_key: str | int | None = None
    ) -> dict[str, Any]:
        """Trả lời chat casual bằng mô hình LLM thực thụ kèm multi-turn memory."""
        return await self._chat_with_llm(user_query, session_key=session_key)

    async def _chat_with_llm(
        self,
        user_query: str,
        session_key: str | int | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Gọi LLM trò chuyện tự nhiên đa lượt với ngữ cảnh liên tục hệt như terminal Ollama."""
        key = str(session_key or "default")
        try:
            history = self.conversation_memory.get_history(key)
            current_messages = history + [{"role": "user", "content": user_query}]

            response = await self.call_chat(
                messages=current_messages,
                system_prompt=system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT,
                temperature=0.7,
                top_p=0.9,
            )

            if not response.strip():
                raise ValueError("LLM trả về rỗng")

            self.conversation_memory.add_turn(key, user_query, response)

            return {
                "title": f"💬 AI Core ({self.model_name})",
                "description": response,
                "color": 0x3498DB,
                "is_chat": True,
            }
        except Exception as e:
            logger.error(f"[AI Core] Lỗi trò chuyện LLM: {e}")
            return {
                "title": f"💬 AI Core ({self.model_name})",
                "description": "😅 Mình gặp chút trục trặc khi kết nối với mô hình Ollama, bạn thử lại sau ít giây nhé!",
                "color": 0xF39C12,
                "is_chat": True,
            }

    # ================================================================
    # LLM CALLS (/api/chat & /api/generate)
    # ================================================================

    @staticmethod
    def clean_llm_output(text: str) -> str:
        """Làm sạch output thô từ Qwen3: bỏ <think>, gộp từ/đoạn lặp qua C++ Native Core (chống nói lắp tiếng Việt)."""
        if not text:
            return ""
        raw = str(text).strip()
        # Nếu mô hình bắt đầu sinh suy luận trực tiếp và chỉ đóng bằng </think> (không có <think> mở)
        if "<think>" not in raw.lower() and "</think>" in raw.lower():
            parts = re.split(r"(?i)</think>", raw, maxsplit=1)
            if len(parts) > 1 and parts[1].strip():
                raw = parts[1].strip()

        from cpp_core.bridge import clean_think_tags, dedup_words

        # 1. Bỏ khối suy luận <think>...</think> (C++ O(N) zero-allocation)
        cleaned = clean_think_tags(raw).strip()

        # Loại bỏ triệt để mọi thẻ think còn sót lại hoặc mở/đóng dở dang (ví dụ </think> lẻ loi)
        cleaned = re.sub(r"(?is)^.*?</think>", "", cleaned).strip()
        cleaned = re.sub(r"(?i)</?think[^>]*>", "", cleaned).strip()
        cleaned = re.sub(r"</?>", "", cleaned).strip()

        # 2. Gộp từ lặp liên tiếp (C++ O(N) thay cho chuỗi regex loops lặp lại)
        cleaned = dedup_words(cleaned).strip()

        # 3. Gộp đoạn văn lặp liên tiếp
        blocks = re.split(r"\n\s*\n", cleaned)
        deduped: list[str] = []
        for b in blocks:
            b_stripped = b.strip()
            if not b_stripped:
                continue
            if deduped and deduped[-1].strip() == b_stripped:
                continue
            deduped.append(b)
        cleaned = "\n\n".join(deduped).strip()

        # 4. Fallback nếu làm sạch xong rỗng
        if not cleaned:
            cleaned = re.sub(r"(?i)</?think.*?>?", "", raw).strip()[:2000]
        return cleaned

    async def call_chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        timeout: int | None = None,
    ) -> str:
        """Gửi chuỗi hội thoại đa lượt đến Qwen3 qua Ollama /api/chat.
        Đảm bảo chat tự nhiên, giữ ngữ cảnh liên tục hệt như 'ollama run' trên terminal."""
        self.last_llm_call_time = time.time()
        if timeout is None:
            timeout = getattr(settings, "OLLAMA_TIMEOUT", 600)

        sys_p = system_prompt or DEFAULT_CHAT_SYSTEM_PROMPT

        chat_messages = [{"role": "system", "content": sys_p}]
        for m in messages:
            chat_messages.append({
                "role": m.get("role", "user"),
                "content": self.sanitize_text(m.get("content", "")),
            })

        try:
            hw_options = recommend_llm_options()
        except Exception:
            hw_options = {"num_ctx": 2048, "num_thread": 4, "num_gpu": 0}

        env_num_gpu = getattr(settings, "OLLAMA_NUM_GPU", None)
        if env_num_gpu is not None:
            num_gpu = int(env_num_gpu)
        else:
            num_gpu = int(hw_options.get("num_gpu") if hw_options.get("num_gpu") is not None else 0)

        llm_options: dict[str, Any] = {
            "temperature": temperature,
            "top_p": top_p,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "num_ctx": hw_options.get("num_ctx", 2048),
            "num_predict": 512,
            "num_thread": hw_options.get("num_thread", os.cpu_count() or 4),
            "num_gpu": num_gpu,
        }

        payload = {
            "model": self.model_name,
            "messages": chat_messages,
            "stream": False,
            "keep_alive": -1,
            "options": llm_options,
        }

        def _sync_chat_request() -> str:
            req = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    content = data.get("message", {}).get("content", "")
                    return AICore.clean_llm_output(content)
                raise RuntimeError(f"Ollama HTTP {res.status}")

        try:
            return await asyncio.to_thread(_sync_chat_request)
        except Exception as e:
            logger.warning(f"[AI Core] /api/chat error: {e}, fallback sang /api/generate")
            last_content = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_content = m.get("content", "")
                    break
            return await self.call_llm(
                prompt=last_content,
                system_prompt=sys_p,
                timeout=timeout,
                temperature=temperature,
            )

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        timeout: int | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Gửi prompt đến Qwen3 qua Ollama /api/generate."""
        self.last_llm_call_time = time.time()
        if timeout is None:
            timeout = getattr(settings, "OLLAMA_TIMEOUT", 600)
        sys_p = system_prompt or (
            f"Bạn là AI Core ({self.model_name}) - Trung tâm Giám Sát, Điều Hành & Bảo Trì của Discord Bot.\n"
            "Quy tắc phản hồi:\n"
            "1. Phản hồi súc tích, chuyên nghiệp, chính xác bằng Tiếng Việt chuẩn.\n"
            "2. Tuyệt đối KHÔNG viết lặp từ liên tiếp (ví dụ sai: 'tại tại', 'thiết thiết', 'Không Không'). Mỗi từ chỉ viết 1 lần.\n"
            "3. Tuyệt đối KHÔNG tiết lộ token, mật khẩu, key API, chuỗi bí mật.\n"
            "4. Khi phân tích lỗi: Nêu rõ Nguyên nhân -> Vị trí file/dòng -> Giải pháp khắc phục tối thiểu (Minimal Patch).\n"
            "5. Phân biệt rõ ràng: Chỉ phân tích (Analyze) nếu không có yêu cầu sửa, và chỉ sửa (Modify) khi có chỉ thị trực tiếp.\n"
            "6. KHÔNG tự ý thực hiện hành động destructive nếu chưa được admin xác nhận.\n"
            "7. Phân biệt 'Discord Embed' (định dạng tin nhắn Discord) với 'embedding/vector' (kỹ thuật ML). "
            "Nếu người dùng nói 'bỏ embed/tắt embed' mà không nhắc tới model/vector/RAG thì hiểu là Discord Embed."
        )

        safe_prompt = self.sanitize_text(prompt)

        try:
            hw_options = recommend_llm_options()
        except Exception:
            hw_options = {"num_ctx": 2048, "num_thread": 4, "num_gpu": 0}

        env_num_gpu = getattr(settings, "OLLAMA_NUM_GPU", None)
        if env_num_gpu is not None:
            num_gpu = int(env_num_gpu)
        else:
            num_gpu = int(hw_options.get("num_gpu") if hw_options.get("num_gpu") is not None else 0)

        llm_options: dict[str, Any] = {
            "temperature": temperature,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.15,
            "repeat_last_n": 64,
            "num_ctx": hw_options.get("num_ctx", 2048),
            "num_predict": -1,
            "num_thread": hw_options.get("num_thread", os.cpu_count() or 4),
            "num_gpu": num_gpu,
        }

        payload = {
            "model": self.model_name,
            "prompt": safe_prompt,
            "system": sys_p,
            "stream": False,
            "keep_alive": -1,
            "options": llm_options,
        }

        def _sync_request() -> str:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    return AICore.clean_llm_output(data.get("response", ""))
                raise RuntimeError(f"Ollama HTTP {res.status}")

        try:
            return await asyncio.to_thread(_sync_request)
        except Exception as e:
            logger.error(f"[AI Core] Lỗi gọi mô hình {self.model_name}: {e}")
            return f"❌ Không thể kết nối với mô hình {self.model_name} qua Ollama ({e})."

    # ================================================================
    # MAIN QUERY HANDLER
    # ================================================================

    async def handle_user_query(
        self,
        user_query: str,
        author_id: int,
        channel_id: int | None = None,
        is_chat: bool = False,
    ) -> dict[str, Any]:
        """Xử lý yêu cầu từ người dùng / Administrator trong AI Control Channel hoặc Chat Channel."""
        self.state = AICoreState.ANALYZING
        self.last_activity_time = time.time()
        session_key = str(author_id)

        q_clean = user_query.strip().lower()

        # ==========================================
        # -1. RESET BỘ NHỚ HỘI THOẠI
        # ==========================================
        if any(k == q_clean or k in q_clean for k in [
            "reset chat", "xóa chat", "quên đi", "clear chat", "reset hội thoại", "bắt đầu lại", "xóa ký ức"
        ]):
            self.conversation_memory.clear(session_key)
            self.state = AICoreState.IDLE
            return {
                "title": f"✨ AI Core ({self.model_name}) • Làm Mới Hội Thoại",
                "description": "Đã làm mới ký ức cuộc trò chuyện.",
                "color": 0x2ECC71,
                "is_chat": False,
            }

        # ==========================================
        # 0. KIỂM TRA DESTRUCTIVE ACTION (BẢO MẬT)
        # ==========================================
        confirm_key = self.check_destructive_action(user_query)
        if confirm_key:
            self.state = AICoreState.IDLE
            return {
                "title": f"🛡️ AI Core ({self.model_name}) • Xác Nhận Hành Động Nguy Hiểm",
                "description": (
                    f"⚠️ **Phát hiện hành động có thể gây nguy hiểm trong yêu cầu của bạn.**\n\n"
                    f"🔑 **Mã xác nhận:** `{confirm_key}`\n"
                    f"📝 **Yêu cầu:** `{user_query[:200]}`\n\n"
                    f"Để xác nhận thực thi, hãy sử dụng lệnh:\n"
                    f"`/ai_confirm key:{confirm_key}`\n\n"
                    f"⏰ Mã hết hạn sau **5 phút**."
                ),
                "color": 0xE74C3C,
                "requires_confirmation": True,
                "confirm_key": confirm_key,
            }

        # ==========================================
        # 0.5. CHAT CASUAL ĐÃ ĐƯỢC GỠ BỎ
        # ==========================================
        if is_chat or self._is_casual_chat(q_clean):
            self.state = AICoreState.IDLE
            return {
                "title": f"ℹ️ Thông Báo • AI Core",
                "description": (
                    "Tính năng trò chuyện trực tiếp với AI đã được tắt theo thiết lập máy chủ.\n"
                    "Bot tập trung toàn bộ tài nguyên cho Đấu Trường Competitive Programming và sinh đề bài thi đấu."
                ),
                "color": 0x95A5A6,
                "is_chat": False,
            }

        # ==========================================
        # 1. XỬ LÝ NHANH CÁC LỆNH DETERMINISTIC (0 MS / 0 TOKEN)
        # ==========================================

        # A. Trạng thái tổng quan / kiểm tra bot
        if any(k in q_clean for k in ["trạng thái", "status", "bot ổn không", "kiểm tra bot", "kiểm tra toàn bộ", "health"]):
            health = self.diagnose_system_health()
            recent_logs = self.read_recent_logs(5)
            log_preview = "\n".join(recent_logs[-5:]) if recent_logs else "Không có log."

            err_count = len(self.recent_errors)
            status_symbol = "🟢" if err_count == 0 else "🟡"

            hw_line = ""
            try:
                hw = get_hardware_info()
                ram = hw.get("ram", {})
                gpu_txt = hw["gpus"][0]["name"] if hw.get("gpus") else "CPU-only"
                hw_line = (
                    f"• 💾 **RAM trống:** `{ram.get('free_gb', 'N/A')} / {ram.get('total_gb', 'N/A')} GB`"
                    f" | 🎮 **GPU:** `{gpu_txt}`\n"
                )
            except Exception:
                pass

            desc = (
                f"{status_symbol} **Trạng Thái Hệ Thống:** `{ 'ỔN ĐỊNH' if err_count == 0 else 'CẦN CHÚ Ý' }`\n"
                f"• 🤖 **AI Core Model:** `{self.model_name}`\n"
                f"• ⚡ **Trạng thái AI Core:** `{self.state}`\n"
                f"{hw_line}"
                f"• 🗄️ **Cơ sở dữ liệu:** `{health['database']['status']}` ({health['database'].get('details', '')})\n"
                f"• 📑 **Kho đề Ranked 1:1:** `{health['problem_bank'].get('count', 0)} bài` ({health['problem_bank'].get('size_mb', '0 MB')})\n"
                f"• ⚠️ **Lỗi ghi nhận gần đây:** `{err_count} lỗi`\n\n"
                f"### 📋 Nhật Ký Gần Nhất:\n```text\n{log_preview[-800:]}\n```"
            )
            self.state = AICoreState.IDLE
            return {
                "title": f"🧠 AI Core ({self.model_name}) • Báo Cáo Sức Khỏe Bot",
                "description": desc,
                "color": 0x2ECC71 if err_count == 0 else 0xF1C40F,
            }

        # B. Kiểm tra lỗi đang xảy ra
        if any(k in q_clean for k in ["lỗi gì", "có lỗi", "bị lỗi", "error", "exception", "traceback"]):
            if not self.recent_errors:
                self.state = AICoreState.IDLE
                return {
                    "title": f"🧠 AI Core ({self.model_name}) • Giám Sát Lỗi",
                    "description": (
                        "🟢 **Hệ thống không ghi nhận bất kỳ lỗi hay Exception nào gần đây!**\n\n"
                        "• Bot đang hoạt động hoàn toàn bình thường.\n"
                        f"• AI Core chuyển về chế độ: **`{AICoreState.IDLE}`**."
                    ),
                    "color": 0x2ECC71,
                }

            last_err = self.recent_errors[-1]
            desc = (
                f"⚠️ **Phát hiện lỗi gần nhất từ nguồn:** `{last_err['source']}`\n"
                f"• ⏰ **Thời gian:** `{last_err['timestamp']}`\n"
                f"• ❌ **Thông điệp:** `{last_err['message'][:300]}`\n"
            )
            if last_err.get("traceback"):
                desc += f"\n### 🔍 Traceback:\n```python\n{last_err['traceback'][-800:]}\n```"

            analysis_prompt = (
                f"Hãy phân tích nguyên nhân của lỗi sau và đề xuất cách sửa (chưa sửa, chỉ phân tích):\n"
                f"Source: {last_err['source']}\n"
                f"Error: {last_err['message']}\n"
                f"Traceback: {last_err.get('traceback', '')[:1000]}\n"
            )
            ai_analysis = await self.call_llm(analysis_prompt)
            desc += f"\n\n### 💡 Phân Tích & Đề Xuất Từ AI Core:\n{ai_analysis[:4000]}"

            self.state = AICoreState.IDLE
            return {
                "title": f"🧠 AI Core ({self.model_name}) • Phân Tích Lỗi Hệ Thống",
                "description": desc,
                "color": 0xE74C3C,
            }

        # C. Đọc log gần đây
        if any(k in q_clean for k in ["kiểm tra log", "xem log", "read log", "log gần đây"]):
            logs = self.read_recent_logs(25)
            log_text = "\n".join(logs) if logs else "File log rỗng."
            self.state = AICoreState.IDLE
            return {
                "title": f"📋 AI Core ({self.model_name}) • Nhật Ký Hoạt Động (25 dòng cuối)",
                "description": f"```text\n{log_text[-1800:]}\n```",
                "color": 0x3498DB,
            }

        # D. Đọc file mã nguồn
        if any(k in q_clean for k in ["đọc file", "xem code", "read file", "source code", "xem source"]):
            # Extract file path from query
            file_match = re.search(
                r'(?:cogs|services|utils|judge|database|config|music|tests)[/\\][\w\-./\\]+\.(?:py|md|txt|json|yaml|yml|toml|bat|ps1|cfg|ini|example)',
                user_query,
            )
            if file_match:
                file_path = file_match.group(0)
                result = self.read_source_file(file_path)
                if "error" in result:
                    desc = f"❌ {result['error']}"
                    color = 0xE74C3C
                else:
                    desc = (
                        f"📁 **Tệp:** `{result['path']}`\n"
                        f"• **Số dòng:** {result['lines']} | **Kích thước:** {result['size_kb']} KB\n\n"
                        f"```python\n{result['content'][:3500]}\n```"
                    )
                    color = 0x3498DB
            else:
                desc = "❌ Vui lòng chỉ rõ đường dẫn file (VD: `cogs/admin.py`, `services/rank.py`)"
                color = 0xE74C3C

            self.state = AICoreState.IDLE
            return {
                "title": f"📂 AI Core ({self.model_name}) • Đọc Mã Nguồn",
                "description": desc,
                "color": color,
            }

        # E. Tìm file liên quan
        if any(k in q_clean for k in ["tìm file", "find file", "file nào", "liên quan"]):
            keyword_match = re.search(r'(?:tìm|find|liên quan)\s+(?:file\s+)?(?:về\s+)?(\w+)', q_clean)
            keyword = keyword_match.group(1) if keyword_match else q_clean.split()[-1]
            related = self.find_related_files(keyword)
            if related:
                file_list = "\n".join(f"• `{f}`" for f in related[:15])
                desc = f"🔍 **Tìm thấy {len(related)} file liên quan đến '{keyword}':**\n\n{file_list}"
            else:
                desc = f"🔍 Không tìm thấy file nào liên quan đến '{keyword}'."
            self.state = AICoreState.IDLE
            return {
                "title": f"📂 AI Core ({self.model_name}) • Tìm File Liên Quan",
                "description": desc,
                "color": 0x3498DB,
            }

        # F. KB Search - Tìm kiếm trong Knowledge Base
        if any(k in q_clean for k in ["kb search", "kb tìm", "knowledge search", "search kb"]):
            keyword = q_clean
            for kw in ["kb search", "kb tìm", "knowledge search", "search kb"]:
                keyword = keyword.replace(kw, "").strip()
            if not keyword:
                keyword = q_clean.split()[-1]
            
            results = await kb.search(keyword, top_k=5)
            if results:
                desc_parts = [f"🔍 **KB Search: '{keyword}' - {len(results)} kết quả:**"]
                for i, r in enumerate(results, 1):
                    desc_parts.append(f"{i}. [{r['source_name']} ({r['source_type']})] {r['content'][:200]}... (relevance: {r['relevance']:.2f})")
                desc = "\n".join(desc_parts)
            else:
                desc = f"🔍 KB không có nội dung liên quan đến '{keyword}'."
            self.state = AICoreState.IDLE
            return {
                "title": f"📚 AI Core ({self.model_name}) • KB Search",
                "description": desc,
                "color": 0x3498DB,
            }

        # G. KB Stats
        if any(k in q_clean for k in ["kb stats", "kb thống kê", "knowledge stats"]):
            stats = await kb.stats()
            desc = (
                f"📊 **Knowledge Base Stats:**\n"
                f"• 📦 Chunks: {stats['total_chunks']}\n"
                f"• 📚 Sources: {stats['total_sources']}\n"
                f"• 📝 Total chars: {stats['total_chars']:,}\n"
                f"• 💾 Storage: {stats['storage_mb']} MB"
            )
            self.state = AICoreState.IDLE
            return {
                "title": f"📊 AI Core ({self.model_name}) • KB Stats",
                "description": desc,
                "color": 0x3498DB,
            }

        # H. KB List Sources
        if any(k in q_clean for k in ["kb list", "kb sources", "kb nguồn"]):
            sources = await kb.list_sources()
            if sources:
                src_list = "\n".join(f"• `{s['name']}` ({s['type']}) - {s['chunks']} chunks, {s['total_chars']:,} chars" for s in sources[:20])
                desc = f"📚 **KB Sources ({len(sources)} total):**\n{src_list}"
            else:
                desc = "📚 KB chưa có source nào."
            self.state = AICoreState.IDLE
            return {
                "title": f"📚 AI Core ({self.model_name}) • KB Sources",
                "description": desc,
                "color": 0x3498DB,
            }

        # I. KB Web Search & Learn
        if any(k in q_clean for k in ["kb learn", "kb học", "web search", "tìm web", "học từ web"]):
            query = q_clean
            for kw in ["kb learn", "kb học", "web search", "tìm web", "học từ web"]:
                query = query.replace(kw, "").strip()
            if not query:
                query = q_clean.split()[-1]
            
            self.state = AICoreState.ANALYZING
            result = await kb.search_and_learn(query, max_sources=3)
            self.state = AICoreState.IDLE
            
            if result.get("success"):
                desc = f"✅ **Đã học từ web: '{query}'**\n• Ingested: {result['ingested']} sources\n"
                if result.get("errors"):
                    desc += f"• Errors: {', '.join(result['errors'])}"
            else:
                desc = f"❌ **Học thất bại:** {result.get('error')}"
            
            return {
                "title": f"🌐 AI Core ({self.model_name}) • Web Learn",
                "description": desc,
                "color": 0x2ECC71 if result.get("success") else 0xE74C3C,
            }

        # J. KB Fetch URL
        if any(k in q_clean for k in ["kb fetch", "kb url", "fetch url", "crawl url"]):
            url_match = re.search(r'(https?://\S+)', user_query)
            if url_match:
                url = url_match.group(1)
                self.state = AICoreState.ANALYZING
                result = await kb.fetch_and_learn(url)
                self.state = AICoreState.IDLE
                
                if result.get("success"):
                    desc = f"✅ **Đã fetch & ingest: {url}**\n• Chunks: {result['chunks']}"
                else:
                    desc = f"❌ **Fetch thất bại:** {result.get('error')}"
                
                return {
                    "title": f"🌐 AI Core ({self.model_name}) • URL Fetch",
                    "description": desc,
                    "color": 0x2ECC71 if result.get("success") else 0xE74C3C,
                }
            else:
                self.state = AICoreState.IDLE
                return {
                    "title": f"🌐 AI Core ({self.model_name}) • URL Fetch",
                    "description": "❌ Vui lòng cung cấp URL hợp lệ (VD: `kb fetch https://example.com`)",
                    "color": 0xE74C3C,
                }

        # F. Tối ưu module
        if any(k in q_clean for k in ["tối ưu", "optimize", "refactor"]):
            recent_err = self.recent_errors[-1] if self.recent_errors else None
            opt_prompt = (
                f"Yêu cầu từ Quản trị viên: '{user_query}'\n"
                f"Lỗi gần đây: {json.dumps(recent_err) if recent_err else 'Không có'}\n"
                "Hãy phân tích module liên quan và đề xuất các tối ưu cụ thể, an toàn. "
                "KHÔNG viết lại toàn bộ code. Chỉ gợi ý minimal improvements."
            )
            ai_response = await self.call_llm(opt_prompt)
            self.state = AICoreState.IDLE
            return {
                "title": f"⚡ AI Core ({self.model_name}) • Đề Xuất Tối Ưu",
                "description": ai_response,
                "color": 0xF39C12,
            }

        # G. Kiểm tra tại sao bot phản hồi chậm
        if any(k in q_clean for k in ["phản hồi chậm", "chậm", "slow", "performance", "tài nguyên"]):
            health = self.diagnose_system_health()
            desc = (
                f"⚡ **Phân Tích Hiệu Năng Hệ Thống:**\n\n"
                f"• 🤖 **AI Core:** `{self.model_name}` | State: `{self.state}`\n"
                f"• 🗄️ **Database:** `{health['database']['status']}`\n"
                f"• 📑 **Problem Bank:** {health['problem_bank'].get('count', 0)} bài\n"
                f"• ⚠️ **Lỗi gần đây:** {health['error_rate']['recent_errors']}\n"
            )

            if health.get("log_errors"):
                desc += f"• 🔴 **Log errors:** {health['log_errors']['new_errors_found']} ({', '.join(health['log_errors']['categories'])})\n"

            opt_prompt = (
                f"Bot đang phản hồi chậm. Dữ liệu hệ thống:\n"
                f"{json.dumps(health, indent=2, default=str)}\n"
                "Hãy đề xuất nguyên nhân có thể và cách khắc phục hiệu năng."
            )
            ai_response = await self.call_llm(opt_prompt)
            desc += f"\n### 💡 Đề Xuất Từ AI Core:\n{ai_response[:4000]}"

            self.state = AICoreState.IDLE
            return {
                "title": f"⚡ AI Core ({self.model_name}) • Phân Tích Hiệu Năng",
                "description": desc,
                "color": 0xF39C12,
            }

        # H. Kiểm tra permission / quyền
        if any(k in q_clean for k in ["permission", "quyền", "ai core permission", "kiểm tra quyền"]):
            desc = (
                f"🔐 **Phân Tích Quyền AI Core:**\n\n"
                f"• **Model:** `{self.model_name}`\n"
                f"• **State:** `{self.state}`\n"
                f"• **Control Channel ID:** `{getattr(settings, 'AI_CORE_CHANNEL_ID', 'N/A')}`\n"
                f"• **Owner ID:** `{getattr(settings, 'OWNER_ID', 'N/A')}`\n\n"
                f"**Quyền hạn:**\n"
                f"• ✅ Đọc log & mã nguồn\n"
                f"• ✅ Phân tích lỗi & đề xuất fix\n"
                f"• ✅ Tự sửa lỗi cú pháp khi được yêu cầu\n"
                f"• ✅ Ghi nhận lỗi hệ thống\n"
                f"• ❌ KHÔNG tự ý xóa file/database\n"
                f"• ❌ KHÔNG restart/shutdown bot\n"
                f"• ❌ KHÔNG tiết lộ secrets\n"
                f"• ⚠️ Cần xác nhận admin cho hành động destructive"
            )
            self.state = AICoreState.IDLE
            return {
                "title": f"🔐 AI Core ({self.model_name}) • Phân Tích Quyền",
                "description": desc,
                "color": 0x9B59B6,
            }

        # I. Yêu cầu SỬA LỖI (Explicit Modify / Fix Request)
        if any(k in q_clean for k in ["sửa lỗi", "fix lỗi", "sửa code", "patch", "sửa command"]):
            self.state = AICoreState.PATCHING

            # Tìm file cần sửa dựa trên nội dung câu hỏi
            target_file = None
            if "rank" in q_clean:
                target_file = self.project_root / "cogs" / "ranked_duel.py"
            elif "doc" in q_clean or "tài liệu" in q_clean:
                target_file = self.project_root / "cogs" / "doc_intake.py"
            elif "admin" in q_clean:
                target_file = self.project_root / "cogs" / "admin.py"
            elif "music" in q_clean:
                target_file = self.project_root / "cogs" / "music.py"
            elif "moderation" in q_clean or "warn" in q_clean:
                target_file = self.project_root / "cogs" / "moderation.py"
            elif "submission" in q_clean or "submit" in q_clean:
                target_file = self.project_root / "cogs" / "submission.py"

            if target_file and target_file.exists():
                with open(target_file, "r", encoding="utf-8") as f:
                    code = f.read()

                is_valid = SelfHealer.validate_python_code(code, str(target_file))
                if not is_valid:
                    healed = await SelfHealer.heal_file(str(target_file), "Admin requested fix", None)
                    self.state = AICoreState.IDLE
                    if healed:
                        return {
                            "title": f"✨ AI Core ({self.model_name}) • Đã Tự Động Vá Lỗi",
                            "description": (
                                f"✅ **Đã vá lỗi thành công cho tệp:** `{target_file.name}`\n"
                                "• 🛡️ Cú pháp AST đã được xác thực 100% hợp lệ.\n"
                                f"• 💾 Bản sao lưu an toàn tại `{target_file.name}.bak`.\n"
                                "• 🟢 Trạng thái hệ thống: **STABLE**."
                            ),
                            "color": 0x2ECC71,
                        }

            recent_err = self.recent_errors[-1] if self.recent_errors else None
            fix_prompt = (
                f"Yêu cầu từ Quản trị viên: '{user_query}'\n"
                f"Lỗi gần đây nhất trong hệ thống: {json.dumps(recent_err) if recent_err else 'Không có lỗi ghi nhận'}\n"
                "Hãy hướng dẫn từng bước tối thiểu (Minimal Patch) để xử lý yêu cầu trên một cách an toàn nhất."
            )
            ai_patch_guide = await self.call_llm(fix_prompt)
            self.state = AICoreState.IDLE
            return {
                "title": f"🛠️ AI Core ({self.model_name}) • Hướng Dẫn Sửa Lỗi Tối Thiểu",
                "description": ai_patch_guide,
                "color": 0x9B59B6,
            }

        # ==========================================
        # K. "EMBED": Discord Embed (định dạng tin nhắn) vs embedding ML
        # ==========================================
        if "embed" in q_clean:
            ml_keywords = (
                "embedding", "vector", "rag", "cho model", "của model",
                "mô hình", "huấn luyện", "train", "embedding model",
            )
            if not any(k in q_clean for k in ml_keywords):
                turn_off = any(k in q_clean for k in [
                    "bỏ", "tắt", "không dùng", "thôi", "plain",
                    "text thường", "chữ thường", "tin nhắn thường",
                ])
                turn_on = any(k in q_clean for k in [
                    "bật", "dùng embed", "hiện embed", "hiển thị embed",
                ])
                self.state = AICoreState.IDLE
                if turn_off and not turn_on:
                    self.plain_text_mode = True
                    return {
                        "title": f"💬 AI Core ({self.model_name}) • Chế Độ Tin Nhắn Thường",
                        "description": (
                            "✅ **Đã TẮT Discord Embed.** Từ giờ bot trả lời bằng **tin nhắn chữ thường** (plain text).\n\n"
                            "• Muốn bật lại Embed: nhắn `bật embed`."
                        ),
                        "color": 0x2ECC71,
                        "plain_text": True,
                    }
                if turn_on:
                    self.plain_text_mode = False
                    return {
                        "title": f"🧠 AI Core ({self.model_name}) • Chế Độ Discord Embed",
                        "description": "✅ **Đã BẬT lại Discord Embed.**",
                        "color": 0x2ECC71,
                        "plain_text": False,
                    }
                return {
                    "title": f"🧠 AI Core ({self.model_name}) • Phân Biệt 'Embed'",
                    "description": (
                        "🔍 **Từ 'embed' có 2 nghĩa khác nhau:**\n\n"
                        "1. 💬 **Discord Embed** = khung tin nhắn màu mè của Discord "
                        "(cái bot đang dùng để trả lời). Muốn tắt thì nhắn `bỏ embed`.\n"
                        "2. 🧠 **Embedding/Vector (ML)** = kỹ thuật biến chữ thành vector số "
                        "nằm BÊN TRONG model, **không thể tắt** (tắt là model tê liệt).\n\n"
                        "👉 Bạn muốn **bỏ Discord Embed** (tin nhắn chữ thường) "
                        "hay hỏi về **embedding của model**?"
                    ),
                    "color": 0x3498DB,
                }

        # ==========================================
        # L. ĐỌC TOÀN BỘ DỰ ÁN (cây thư mục / full project)
        # ==========================================
        if any(k in q_clean for k in [
            "cây thư mục", "project tree", "cấu trúc dự án", "toàn bộ dự án",
            "full project", "liệt kê file", "dự án có gì", "toàn bộ project",
            "đọc toàn bộ", "quét dự án", "quét project",
        ]):
            tree = self.get_project_tree()
            self.state = AICoreState.IDLE
            return {
                "title": f"📂 AI Core ({self.model_name}) • Cấu Trúc Toàn Bộ Dự Án",
                "description": (
                    "🌳 **Cây thư mục dự án (bot đọc được 100% các file text):**\n"
                    f"```text\n{tree[:3000]}\n```\n\n"
                    "📖 Đọc file cụ thể: nhắn `đọc file services/ai_core.py`\n"
                    "🔍 Tìm file theo từ khóa: nhắn `tìm file rank`"
                ),
                "color": 0x3498DB,
            }

        # ==========================================
        # M. INTERNET / THẾ GIỚI BÊN NGOÀI (web search + tóm tắt)
        # ==========================================
        if any(k in q_clean for k in [
            "internet", "thế giới", "tin tức", "tra cứu", "tìm trên mạng",
            "trên mạng", "trên web", "bên ngoài", "mới nhất", "hôm nay có gì",
            "thời tiết", "xem thế giới", "tin mới",
        ]):
            web_query = user_query.strip()
            for kw in ["tra cứu", "tìm trên mạng", "trên mạng", "trên web",
                       "xem thế giới", "thế giới", "internet", "tin tức",
                       "hôm nay có gì", "tin mới", "kb learn", "web search"]:
                web_query = web_query.replace(kw, "").replace(kw.title(), "").strip(" :-,.")
            if not web_query:
                web_query = user_query.strip()

            self.state = AICoreState.ANALYZING
            from services.knowledge_base import search_web, fetch_url_content
            web_results = await search_web(web_query, max_results=5)
            snippets: list[str] = []
            sources: list[str] = []
            for r in web_results[:3]:
                snippets.append(f"- {r.get('title', '')}: {r.get('snippet', '')[:300]}")
                url = r.get("url", "")
                if url:
                    sources.append(url)
                    content = await fetch_url_content(url)
                    if content:
                        snippets.append(f"  Chi tiết ({url[:60]}): {content[:800]}")
                    if len("\n".join(snippets)) > 2500:
                        break

            if not snippets:
                self.state = AICoreState.IDLE
                return {
                    "title": f"🌐 AI Core ({self.model_name}) • Internet",
                    "description": (
                        f"❌ **Không tìm được kết quả web cho:** `{web_query[:150]}`\n\n"
                        "• Kiểm tra lại kết nối internet của server.\n"
                        "• Thử từ khóa khác, ngắn gọn hơn."
                    ),
                    "color": 0xE74C3C,
                }

            summary_prompt = (
                f"Người dùng hỏi về thế giới bên ngoài: '{user_query}'\n\n"
                f"Kết quả tìm kiếm web cho '{web_query}':\n" + "\n".join(snippets) + "\n\n"
                "Hãy tóm tắt câu trả lời bằng tiếng Việt chuẩn, súc tích, "
                "KHÔNG lặp từ liên tiếp, ghi rõ nguồn URL ở cuối."
            )
            ai_summary = await self.call_llm(summary_prompt)
            src_block = "\n".join(f"• {u}" for u in sources[:3])
            self.state = AICoreState.IDLE
            return {
                "title": f"🌐 AI Core ({self.model_name}) • Kết Quả Internet",
                "description": f"{ai_summary}\n\n**🔗 Nguồn:**\n{src_block}",
                "color": 0x2ECC71,
            }

        # ==========================================
        # N. PHẦN CỨNG: CPU / RAM / GPU / DISK (+ auto-tune)
        # ==========================================
        if any(k in q_clean for k in [
            "phần cứng", "phan cung", "hardware", "cấu hình máy", "cau hinh may",
            "máy chủ", "may chu", "server mạnh", "gpu", "vram", "cuda",
            "cpu", "ram", "bộ nhớ máy",
        ]):
            try:
                hw_report = await asyncio.to_thread(format_hardware_report)
                color = 0x2ECC71
            except Exception as e:
                hw_report = f"❌ Không đọc được phần cứng: {e}"
                color = 0xE74C3C
            self.state = AICoreState.IDLE
            return {
                "title": f"🖥️ AI Core ({self.model_name}) • Phần Cứng & Auto-Tune",
                "description": hw_report[:3800],
                "color": color,
            }

        # ==========================================
        # O. RANK SERVER: ai rank cao nhất / top BXH (đọc trực tiếp từ DB)
        # ==========================================
        if any(k in q_clean for k in [
            "rank cao nhất", "top 1", "top server", "bảng xếp hạng", "bang xep hang",
            "leaderboard", "bxh", "đứng đầu", "dung dau", "đứng top", "dung top",
            "cao nhất server", "cao nhat server", "mạnh nhất", "manh nhat",
            "top 5", "top 10", "xếp hạng server", "xep hang server",
        ]):
            try:
                from database.database import async_session_factory
                from database.repositories.user_repo import UserRepository

                async with async_session_factory() as session:
                    repo = UserRepository(session)
                    top_users, total = await repo.get_leaderboard(
                        page=1, per_page=5, sort_by="rating"
                    )

                self.state = AICoreState.IDLE
                if not top_users:
                    return {
                        "title": f"🏆 AI Core ({self.model_name}) • Xếp Hạng Server",
                        "description": (
                            "📭 **Chưa có ai trên bảng xếp hạng.**\n\n"
                            "• Thành viên cần nộp bài / đấu ranked để có rating."
                        ),
                        "color": 0xF39C12,
                    }

                medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                lines = []
                for i, u in enumerate(top_users):
                    mark = " 👑 **CAO NHẤT SERVER**" if i == 0 else ""
                    lines.append(
                        f"{medals[i] if i < len(medals) else f'{i+1}.'} <@{u.discord_id}>"
                        f" — **{u.rating} rating** (`{u.rank}`){mark}"
                    )
                return {
                    "title": f"🏆 AI Core ({self.model_name}) • Top Rank Server",
                    "description": (
                        f"👑 **Rank cao nhất server hiện tại:**\n\n"
                        + "\n".join(lines)
                        + f"\n\n📊 Tổng `{total}` thành viên trên BXH."
                    ),
                    "color": 0xFFD700,
                }
            except Exception as e:
                logger.error(f"[AI Core] Lỗi đọc BXH server: {e}")
                self.state = AICoreState.IDLE
                return {
                    "title": f"🏆 AI Core ({self.model_name}) • Xếp Hạng Server",
                    "description": f"❌ Không đọc được BXH lúc này: {e}",
                    "color": 0xE74C3C,
                }

        # ==========================================
        # 2. CÁC YÊU CẦU PHỨC TẠP / HỎI ĐÁP KHÁC (Gọi LLM + RAG)
        # ==========================================
        # Kiểm tra xem có phải câu hỏi kỹ thuật về bot không
        is_bot_architecture_query = any(k in q_clean for k in [
            "kiến trúc bot", "bot hoạt động", "cấu trúc bot", "module", "hệ thống bot", "cơ chế bot", "workflow"
        ])

        # RAG: Lấy context từ Knowledge Base (chỉ lấy khi thực sự liên quan, min_relevance=0.35)
        kb_context = await kb.get_context_for_query(user_query, max_chars=3000, min_relevance=0.35)

        if is_bot_architecture_query:
            recent_err_summary = [f"- [{e['source']}] {e['message'][:100]}" for e in list(self.recent_errors)[-3:]]
            err_block = "\n".join(recent_err_summary) if recent_err_summary else "(Không có lỗi nào)"
            context_prompt = (
                f"Bối cảnh hệ thống bot:\n"
                f"- Model AI: {self.model_name}\n"
                f"- Lỗi gần đây:\n{err_block}\n"
            )
            if kb_context:
                context_prompt += f"\n📚 **Kiến thức liên quan từ Knowledge Base:**\n{kb_context}\n"
            context_prompt += (
                f"\nCâu hỏi của Quản trị viên: '{user_query}'\n\n"
                "Hãy trả lời rõ ràng, cụ thể, bám sát kiến trúc bot."
            )
            response_text = await self.call_llm(context_prompt)
            self.state = AICoreState.IDLE
            return {
                "title": f"🧠 AI Core ({self.model_name})",
                "description": response_text,
                "color": 0x3498DB,
            }
        else:
            # Trò chuyện tự nhiên đã bị tắt: Trả về thông báo hướng dẫn
            self.state = AICoreState.IDLE
            return {
                "title": f"ℹ️ Thông Báo • AI Core",
                "description": (
                    "Tính năng trò chuyện trực tiếp với AI đã được tắt theo thiết lập máy chủ.\n"
                    "Bot chỉ hỗ trợ quản trị hệ thống và Đấu Trường Competitive Programming."
                ),
                "color": 0x95A5A6,
                "is_chat": False,
            }


# Singleton instance
ai_core = AICore()
