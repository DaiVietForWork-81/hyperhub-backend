"""
services/problem_archive.py
Dịch vụ quản lý, tự động lưu trữ và tra cứu kho bài tập thống nhất (Freedom & Ranked 1:1).

Chức năng:
1. Tự động đăng lưu trữ bài toán (đề bài, ràng buộc, phân tích thuật toán editorial, code mẫu)
   vào kênh lưu trữ chuyên dụng PROBLEM_ARCHIVE_CHANNEL_ID (1548627763467128912).
2. Chống gửi trùng lặp bài đã lưu trữ bằng bộ nhớ đệm và file data/archived_problems.json.
3. Cung cấp hàm search_problem hỗ trợ tra cứu đề bài theo ID thống nhất từ cả DB, file và quét kênh Discord.
"""

from __future__ import annotations

import json
import os
import re
import datetime
from typing import Any

import discord
from discord.ext import commands

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("ProblemArchive")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
ARCHIVE_INDEX_FILE = os.path.join(DATA_DIR, "archived_problems.json")
os.makedirs(DATA_DIR, exist_ok=True)


class ProblemArchiveService:
    """Quản lý kho lưu trữ bài tập và tra cứu đề bài theo ID thống nhất."""

    _archived_cache: dict[str, dict[str, Any]] = {}
    _loaded: bool = False

    @classmethod
    def _load_cache(cls) -> None:
        if cls._loaded:
            return
        if os.path.isfile(ARCHIVE_INDEX_FILE):
            try:
                with open(ARCHIVE_INDEX_FILE, "r", encoding="utf-8") as f:
                    cls._archived_cache = json.load(f)
            except Exception as e:
                logger.warning(f"Không thể đọc file {ARCHIVE_INDEX_FILE}: {e}")
                cls._archived_cache = {}
        cls._loaded = True

    @classmethod
    def _save_cache(cls) -> None:
        try:
            with open(ARCHIVE_INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._archived_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Không thể lưu file {ARCHIVE_INDEX_FILE}: {e}")

    @classmethod
    def normalize_id(cls, raw_id: str) -> str:
        """Chuẩn hóa ID bài tập thống nhất (không phân biệt hoa/thường, xóa khoảng trắng)."""
        clean = (raw_id or "").strip().upper()
        return clean

    @classmethod
    async def archive_problem(
        cls,
        bot: commands.Bot,
        problem_data: dict[str, Any],
    ) -> discord.Message | None:
        """
        Tự động đăng lưu trữ bài tập vào kênh PROBLEM_ARCHIVE_CHANNEL_ID (1548627763467128912).
        Đảm bảo không gửi trùng lặp nếu bài đã được lưu trữ trước đó.
        """
        cls._load_cache()
        p_id = cls.normalize_id(problem_data.get("id", ""))
        if not p_id:
            return None

        channel_id = getattr(settings, "PROBLEM_ARCHIVE_CHANNEL_ID", 1548627763467128912)
        channel = bot.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.debug(f"[Archive] Kênh {channel_id} chưa sẵn sàng hoặc không tìm thấy.")
            return None

        # Kiểm tra xem bài đã được đăng lưu trữ hay chưa
        if p_id in cls._archived_cache and cls._archived_cache[p_id].get("message_id"):
            logger.debug(f"[Archive] Bài toán ID {p_id} đã được lưu trữ trước đó, bỏ qua.")
            return None

        name = problem_data.get("name", f"Bài tập {p_id}")
        mode = problem_data.get("mode", "Freedom")
        tier = problem_data.get("tier", "T8")
        division = problem_data.get("division", "")
        rating = problem_data.get("rating", 800)
        time_limit = problem_data.get("time_limit", 1.0)
        memory_limit = problem_data.get("memory_limit", 256)
        statement = problem_data.get("statement", "Chưa có mô tả chi tiết.")
        input_format = problem_data.get("input_format", "Đọc từ standard input (cin/stdin).")
        output_format = problem_data.get("output_format", "In ra standard output (cout/stdout).")
        constraints = problem_data.get("constraints", "Thời gian thực thi trong giới hạn.")
        editorial = problem_data.get("editorial", "Xem xét kỹ cấu trúc dữ liệu và trường hợp biên.")
        sample_in = problem_data.get("sample_input", "")
        sample_out = problem_data.get("sample_output", "")
        solution_code = problem_data.get("solution_code", "")
        solution_lang = problem_data.get("solution_lang", "cpp")

        stmt_display = statement[:1024] if len(statement) > 1024 else statement
        edit_display = editorial[:1024] if len(editorial) > 1024 else editorial
        if len(solution_code) > 1000:
            sol_display = solution_code[:950] + "\n// ... [Mã nguồn rút gọn để tối ưu hiển thị Discord] ..."
        else:
            sol_display = solution_code

        div_str = f" • {division}" if division else ""
        header_text = f"📦 **[PROBLEM_ARCHIVE] ID: `{p_id}`**"

        embed = discord.Embed(
            title=f"📖 {name} (ID: {p_id})",
            description=(
                f"🎯 **Chế độ:** `{mode}` | **Phân hạng:** `{tier}`{div_str} | **Rating:** `{rating} pts`\n"
                f"⏱️ **Giới hạn thời gian:** `{time_limit}s` | **Bộ nhớ:** `{memory_limit} MB`\n\n"
                f"📝 **MÔ TẢ BÀI TOÁN (STATEMENT):**\n{stmt_display}"
            ),
            color=0x38BDF8 if str(mode).lower() == "freedom" else 0xFBBF24,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        embed.add_field(
            name="📥 INPUT & OUTPUT FORMAT",
            value=f"• **Input:** {input_format[:450]}\n• **Output:** {output_format[:450]}",
            inline=False,
        )

        embed.add_field(
            name="📋 RÀNG BUỘC & VÍ DỤ",
            value=(
                f"• **Ràng buộc:** {constraints[:400]}\n"
                f"• **Sample Input:** `{sample_in[:150] or 'N/A'}`\n"
                f"• **Sample Output:** `{sample_out[:150] or 'N/A'}`"
            ),
            inline=False,
        )

        embed.add_field(
            name="💡 PHÂN TÍCH THUẬT TOÁN (EDITORIAL)",
            value=edit_display,
            inline=False,
        )

        if sol_display:
            embed.add_field(
                name=f"💻 CODE MẪU CHUẨN AC ({solution_lang.upper()})",
                value=f"```{solution_lang}\n{sol_display}\n```",
                inline=False,
            )

        embed.set_footer(text=f"Kho Lưu Trữ Đề Bài Tự Động • Tra cứu bằng: /search {p_id}")

        try:
            msg = await channel.send(content=header_text, embed=embed)
            cls._archived_cache[p_id] = {
                "id": p_id,
                "name": name,
                "mode": mode,
                "tier": tier,
                "rating": rating,
                "message_id": msg.id,
                "channel_id": channel.id,
                "jump_url": msg.jump_url,
                "archived_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            cls._save_cache()
            logger.info(f"✅ [Archive] Đã lưu trữ bài {p_id} ({name}) vào kênh {channel_id} (Msg: {msg.id})")
            return msg
        except Exception as e:
            logger.error(f"❌ [Archive] Lỗi khi đăng lưu trữ bài {p_id}: {e}", exc_info=True)
            return None

    @classmethod
    async def search_problem(
        cls,
        bot: commands.Bot,
        query_id: str,
    ) -> dict[str, Any] | None:
        """
        Tra cứu bài tập theo ID thống nhất từ:
        1. Kho đề Ranked 1:1 (PROBLEM_BANK & ai_problems.json)
        2. Kho đề Freedom / Codeforces (Database & ProblemFetcher)
        3. Quét lịch sử tin nhắn trong kênh lưu trữ 1548627763467128912
        """
        cls._load_cache()
        qid = cls.normalize_id(query_id)
        if not qid:
            return None

        # 1. Tìm trong kho đề Ranked (PROBLEM_BANK)
        try:
            try:
                from services.duel_problems import PROBLEM_BANK
            except ImportError:
                from archived.duel_arena.services.duel_problems import PROBLEM_BANK
            clean_q = re.sub(r"[^A-Z0-9]", "", qid)
            for p in PROBLEM_BANK:
                clean_pid = re.sub(r"[^A-Z0-9]", "", p.id.upper())
                if clean_pid == clean_q or (len(clean_q) >= 4 and (clean_pid.endswith(clean_q) or clean_q in clean_pid)):
                    sol_code, sol_syntax = p.get_solution_for_lang("cpp")
                    return {
                        "id": p.id,
                        "name": p.name,
                        "mode": "Ranked 1:1",
                        "tier": p.tier,
                        "division": p.division,
                        "rating": p.rating,
                        "statement": p.statement,
                        "input_format": p.input_format,
                        "output_format": p.output_format,
                        "constraints": p.constraints,
                        "sample_input": p.sample_input,
                        "sample_output": p.sample_output,
                        "editorial": p.editorial_text,
                        "solution_code": sol_code,
                        "solution_lang": sol_syntax,
                        "time_limit": p.time_limit_sec,
                        "memory_limit": p.memory_limit_mb,
                        "jump_url": cls._archived_cache.get(cls.normalize_id(p.id), {}).get("jump_url"),
                    }
        except Exception as e:
            logger.debug(f"[Search] Lỗi tra cứu PROBLEM_BANK: {e}")

        # 2. Tìm trong kho bài Freedom / Codeforces
        try:
            from services.problem_fetcher import ProblemFetcher
            p_data = await ProblemFetcher.fetch_problem(qid)
            if not p_data:
                clean_num = re.sub(r"^[A-Za-z]+[-_]?", "", qid)
                if clean_num:
                    p_data = await ProblemFetcher.fetch_problem(clean_num)

            if p_data:
                from services.judge import get_sample_solution_template
                sol_cpp = get_sample_solution_template(p_data, "cpp")
                samples_str = "\n".join(f"In: {inp} -> Out: {out}" for inp, out in p_data.samples[:2])
                return {
                    "id": p_data.id,
                    "name": p_data.name,
                    "mode": "Freedom",
                    "tier": p_data.min_rank_required,
                    "division": f"Contest #{p_data.contest_id}",
                    "rating": p_data.rating or 1200,
                    "statement": f"Bài tập Codeforces #{p_data.contest_id}{p_data.index}.\nXem trực tiếp tại: https://codeforces.com/contest/{p_data.contest_id}/problem/{p_data.index}",
                    "input_format": "Chuẩn Codeforces tiêu chuẩn.",
                    "output_format": "Chuẩn Codeforces tiêu chuẩn.",
                    "constraints": f"Thời gian: {p_data.time_limit}s • Bộ nhớ: {p_data.memory_limit}MB",
                    "sample_input": p_data.samples[0][0] if p_data.samples else "",
                    "sample_output": p_data.samples[0][1] if p_data.samples else "",
                    "editorial": f"Bài tập phân loại {p_data.rating} pts. Áp dụng các thuật toán tương ứng phân hạng {p_data.min_rank_required}.",
                    "solution_code": sol_cpp,
                    "solution_lang": "cpp",
                    "time_limit": p_data.time_limit,
                    "memory_limit": p_data.memory_limit,
                    "jump_url": cls._archived_cache.get(cls.normalize_id(p_data.id), {}).get("jump_url"),
                }
        except Exception as e:
            logger.debug(f"[Search] Lỗi tra cứu ProblemFetcher: {e}")

        # 3. Quét kênh lưu trữ 1548627763467128912 nếu chưa có dữ liệu chi tiết
        channel_id = getattr(settings, "PROBLEM_ARCHIVE_CHANNEL_ID", 1548627763467128912)
        channel = bot.get_channel(channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                async for msg in channel.history(limit=100):
                    content = msg.content or ""
                    if f"ID: `{qid}`" in content or f"ID: {qid}" in content or f"ID: **{qid}**" in content:
                        if msg.embeds:
                            emb = msg.embeds[0]
                            return {
                                "id": qid,
                                "name": emb.title or f"Bài tập {qid}",
                                "mode": "Archived",
                                "tier": "N/A",
                                "division": "",
                                "rating": 1000,
                                "statement": emb.description or "",
                                "input_format": "",
                                "output_format": "",
                                "constraints": "",
                                "sample_input": "",
                                "sample_output": "",
                                "editorial": "",
                                "solution_code": "",
                                "solution_lang": "cpp",
                                "time_limit": 1.0,
                                "memory_limit": 256,
                                "jump_url": msg.jump_url,
                            }
            except Exception as e:
                logger.debug(f"[Search] Lỗi quét kênh lưu trữ {channel_id}: {e}")

        return None
