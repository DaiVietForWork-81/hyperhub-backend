"""
services/self_healer.py
Hệ thống Tự Động Vá Lỗi Mã Nguồn / Cú Pháp Bằng AI Local (Self-Healing Engine).
Đặc điểm:
- Tự động bắt và phân tích các lỗi cú pháp (SyntaxError, IndentationError, Unterminated String, Escape Sequences...)
- Sử dụng mô hình AI Local (Ollama) và các giải thuật AST Healing để sửa lỗi chính xác.
- QUY TẮC BẤT BIẾN: Tuyệt đối KHÔNG thay đổi cấu trúc discord.Embed, giao diện, văn bản, logic gốc của bot.
- Tự động kiểm tra tính hợp lệ bằng AST / compile() trước khi áp dụng.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from config.settings import settings, AI_MODEL_NAME

logger = logging.getLogger("SelfHealer")


class SelfHealer:
    """Bộ máy tự phục hồi và sửa lỗi mã nguồn bằng AI Local cho Discord Bot."""

    @staticmethod
    def is_syntax_or_fixable_error(exc: Exception | str) -> bool:
        """Kiểm tra xem lỗi có thuộc nhóm cú pháp / có thể tự sửa chữa được không."""
        err_str = str(exc).lower()
        fixable_keywords = [
            "syntaxerror",
            "indentationerror",
            "taberror",
            "unterminated string literal",
            "invalid syntax",
            "expected an indented block",
            "unmatched",
            "was never closed",
            "invalid escape sequence",
            "positional argument follows keyword argument",
        ]
        return any(k in err_str for k in fixable_keywords)

    @staticmethod
    def extract_error_location(exc: Exception) -> tuple[str | None, int | None]:
        """Trích xuất đường dẫn file và số dòng gây ra lỗi từ Exception hoặc Traceback."""
        if isinstance(exc, SyntaxError):
            return exc.filename, exc.lineno

        tb = traceback.extract_tb(exc.__traceback__)
        if tb:
            for frame in reversed(tb):
                if "site-packages" not in frame.filename:
                    return frame.filename, frame.lineno
            return tb[-1].filename, tb[-1].lineno

        return None, None

    @staticmethod
    def fix_common_syntax_patterns(code: str) -> str:
        """Thuật toán xử lý nhanh các lỗi chuỗi vỡ hàng hoặc ký tự escape phổ biến."""
        fixed = code

        # 1. Sửa lỗi đa dòng bị cắt hàng thành chuỗi hở trong f-string / thường
        fixed = re.sub(r'(?<!\\)\\(?!["\'\\abfnrtv0-9xuU\n])', r'\\\\', fixed)

        # 2. Xóa các khoảng trắng lạ / ký tự BOM
        fixed = fixed.replace("\ufeff", "").replace("\r\n", "\n")

        return fixed

    @classmethod
    async def call_local_ai_fix(
        cls,
        file_content: str,
        error_msg: str,
        lineno: int | None = None,
        timeout: int = 45,
    ) -> str | None:
        """Gọi AI Local (Ollama) để phân tích và sửa lỗi cú pháp Python."""
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = AI_MODEL_NAME

        lines = file_content.splitlines()
        is_partial = False
        start_line = 0
        end_line = len(lines)

        if len(lines) > 250 and lineno is not None:
            is_partial = True
            start_line = max(0, lineno - 60)
            end_line = min(len(lines), lineno + 60)
            target_snippet = "\n".join(lines[start_line:end_line])
        else:
            target_snippet = file_content

        prompt = f"""You are an Expert Python Autonomous Code Repair System.
Fix the following Python code that raised this error:
ERROR: {error_msg}
LINE HINT: {lineno}

CRITICAL RULES:
1. Fix ONLY the syntax / indentation / formatting error.
2. STRICTLY PRESERVE all discord.Embed descriptions, titles, colors, buttons, logic, comments, and strings. DO NOT rewrite UI or Embeds.
3. Return ONLY the complete corrected Python code snippet inside a ```python ``` code block. No explanations.

CODE TO FIX:
```python
{target_snippet}
```
"""

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
            },
        }

        try:
            req = urllib.request.Request(
                f"{base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            loop = asyncio.get_running_loop()
            res_data = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
            )
            parsed = json.loads(res_data)
            raw_response = parsed.get("response", "").strip()

            code_match = re.search(r"```(?:python)?\s*([\s\S]*?)\s*```", raw_response)
            fixed_code = code_match.group(1).strip() if code_match else raw_response

            if is_partial:
                reconstructed_lines = lines[:start_line] + fixed_code.splitlines() + lines[end_line:]
                full_fixed_code = "\n".join(reconstructed_lines)
            else:
                full_fixed_code = fixed_code

            return full_fixed_code
        except Exception as e:
            logger.warning(f"[Self-Healing] Không thể gọi AI Local để sửa code: {e}")
            return None

    @classmethod
    def validate_python_code(cls, code: str, file_path: str = "<healed_code>") -> bool:
        """Kiểm tra xem mã nguồn sau khi sửa có hợp lệ 100% về mặt cú pháp không."""
        try:
            ast.parse(code)
            compile(code, file_path, "exec")
            return True
        except Exception as e:
            logger.debug(f"[Self-Healing] Mã nguồn sau khi sửa vẫn còn lỗi cú pháp: {e}")
            return False

    @classmethod
    async def heal_file(cls, file_path: str, error_msg: str, lineno: int | None = None) -> bool:
        """Thực hiện tự động sửa một tệp tin Python bị lỗi."""
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            logger.warning(f"[Self-Healing] Không tìm thấy tệp: {file_path}")
            return False

        try:
            with open(p, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:
            logger.error(f"[Self-Healing] Không thể đọc file {file_path}: {e}")
            return False

        # 1. Bước 1: Thử sửa bằng thuật toán quy tắc nhanh (Pattern Heuristic)
        quick_fixed = cls.fix_common_syntax_patterns(original_content)
        if cls.validate_python_code(quick_fixed, file_path) and quick_fixed != original_content:
            cls._backup_and_save(p, quick_fixed)
            logger.info(f"✨ [Self-Healing] Đã tự động sửa cú pháp nhanh cho '{p.name}' thành công!")
            return True

        # 2. Bước 2: Gọi AI Local để sửa lỗi chuyên sâu
        logger.info(f"🤖 [Self-Healing] Đang sử dụng AI Local để sửa lỗi cú pháp tại dòng {lineno} trong '{p.name}'...")
        ai_fixed = await cls.call_local_ai_fix(original_content, error_msg, lineno)

        if ai_fixed and cls.validate_python_code(ai_fixed, file_path):
            cls._backup_and_save(p, ai_fixed)
            logger.info(f"✨ [Self-Healing] AI Local đã sửa thành công và ổn định mã nguồn '{p.name}'!")
            return True

        logger.warning(f"❌ [Self-Healing] Không thể tự động vá tệp '{p.name}'. Cần kiểm tra thủ công.")
        return False

    @classmethod
    def _backup_and_save(cls, path: Path, new_code: str) -> None:
        """Tạo bản backup .bak và ghi đè mã nguồn mới an toàn."""
        bak_path = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.copyfile(path, bak_path)
        except Exception:
            pass

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_code)

    @classmethod
    async def try_heal_extension(cls, extension_name: str, exception: Exception) -> bool:
        """Tự động phát hiện và vá lỗi cho một Extension Cog bị lỗi khi bot nạp."""
        if not cls.is_syntax_or_fixable_error(exception):
            return False

        filename, lineno = cls.extract_error_location(exception)

        if not filename:
            rel_path = extension_name.replace(".", "/") + ".py"
            project_root = Path(__file__).resolve().parent.parent
            guess_file = project_root / rel_path
            if guess_file.exists():
                filename = str(guess_file)

        if not filename:
            return False

        logger.info(f"🔧 [Self-Healing] Phát hiện lỗi cú pháp tại {filename}:{lineno}. Bắt đầu tự động sửa chữa...")
        return await cls.heal_file(filename, str(exception), lineno)
