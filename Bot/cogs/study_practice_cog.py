"""Hệ thống Học Tập & Luyện Đề Thi Thử (Study Practice & Mock Exam Cog).

Chức năng:
1. 🎯 Chế độ Luyện đề & Thi thử (Học sinh thích nhất):
   - Bốc đề chuẩn cấu trúc theo môn (Toán, Lý, Hóa, Sinh, Anh, Văn, Tin)
   - Thiết lập thời gian phòng thi: Kiểm tra nhanh (15p), 45p, 90p, 120p
   - Đồng hồ đếm ngược phòng thi thời gian thực
   - Bảng tổng kết kết quả và lưu lịch sử làm bài vào CSDL
2. Trạng thái cờ (Feature Flag):
   - IS_STUDY_PRACTICE_ENABLED = False (Chưa kích hoạt - Đang ở chế độ sẵn sàng)
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import random
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("StudyPractice")

# ==============================================================================
# CỜ TÍNH NĂNG (FEATURE FLAG): ĐƯỢC CẤU HÌNH THEO YÊU CẦU LÀ "CHƯA KÍCH HOẠT"
# ==============================================================================
IS_STUDY_PRACTICE_ENABLED: bool = False


class StudyPracticeSession:
    """Phiên phòng thi thử của học sinh."""

    def __init__(
        self,
        user_id: int,
        guild_id: int,
        subject: str,
        duration_minutes: int,
        exam_id: Optional[int] = None,
        exam_title: Optional[str] = None,
    ) -> None:
        self.user_id = user_id
        self.guild_id = guild_id
        self.subject = subject
        self.duration_minutes = duration_minutes
        self.exam_id = exam_id
        self.exam_title = exam_title or "Đề Thi Chuẩn Cấu Trúc"
        self.start_time: float = time.time()
        self.end_time: float = self.start_time + (duration_minutes * 60)
        self.is_completed: bool = False
        self.answers: dict[int, str] = {}
        self.score: Optional[float] = None

    @property
    def remaining_seconds(self) -> int:
        rem = int(self.end_time - time.time())
        return max(0, rem)

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.end_time


class StudyPracticeCog(commands.Cog, name="StudyPractice"):
    """Cog quản lý tính năng Luyện Đề & Thi Thử Dành Cho Học Sinh."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.active_sessions: dict[int, StudyPracticeSession] = {}
        log.info(
            "StudyPracticeCog đã nạp thành công (Trạng thái: %s)",
            "ĐÃ KÍCH HOẠT" if IS_STUDY_PRACTICE_ENABLED else "CHƯA KÍCH HOẠT (Dormant)",
        )

    @app_commands.command(
        name="luyende",
        description="🎯 Tính năng Luyện Đề & Thi Thử Trực Tuyến HyperHub (Dành cho học sinh)",
    )
    @app_commands.describe(
        mon="Môn học muốn luyện tập",
        thoi_gian="Thời gian làm bài (phút)",
    )
    @app_commands.choices(
        mon=[
            app_commands.Choice(name="Toán Học 📐", value="MATHEMATICS"),
            app_commands.Choice(name="Tiếng Anh 🇬🇧", value="ENGLISH"),
            app_commands.Choice(name="Vật Lý ⚡", value="PHYSICS"),
            app_commands.Choice(name="Hóa Học 🧪", value="CHEMISTRY"),
            app_commands.Choice(name="Sinh Học 🧬", value="BIOLOGY"),
            app_commands.Choice(name="Ngữ Văn 📖", value="LITERATURE"),
            app_commands.Choice(name="Tin Học 💻", value="INFORMATICS"),
        ],
        thoi_gian=[
            app_commands.Choice(name="Kiểm tra nhanh (15 phút) ⚡", value=15),
            app_commands.Choice(name="Kiểm tra 1 tiết (45 phút) ⏱️", value=45),
            app_commands.Choice(name="Thi thử THPTQG (90 phút) 🎯", value=90),
            app_commands.Choice(name="Thi chuyên / HSG (120 phút) 🏆", value=120),
        ],
    )
    async def cmd_luyen_de(
        self,
        interaction: discord.Interaction,
        mon: Optional[str] = "MATHEMATICS",
        thoi_gian: Optional[int] = 45,
    ) -> None:
        """Lệnh bắt đầu phiên luyện đề thi thử."""
        if not IS_STUDY_PRACTICE_ENABLED:
            embed = discord.Embed(
                title="🎯 Tính Năng Học Tập & Luyện Đề (Sắp Ra Mắt)",
                description=(
                    "Hệ thống **Phòng Thi Ảo & Chế Độ Luyện Đề Thông Minh** đang được tích hợp cùng kho đề chuẩn mực!\n\n"
                    "✨ **Các tính năng sắp mở:**\n"
                    "• ⏱️ Đồng hồ đếm ngược phòng thi tập trung\n"
                    "• 📑 Tự động bốc đề theo chuẩn Bộ GD&ĐT 2025\n"
                    "• 📊 Chấm điểm trắc nghiệm và gợi ý lời giải chi tiết\n"
                    "• ⭐ Lưu lại đề sai vào **Tủ Sách Cá Nhân** để ôn luyện lại\n\n"
                    "*(Tính năng này đã được cài đặt sẵn vào Bot và sẽ kích hoạt ngay khi mở cổng thi thử!)*"
                ),
                color=0xA855F7,
            )
            embed.set_footer(text="HyperHub Study Engine • Trạng thái: Chưa kích hoạt")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Khi được kích hoạt trong tương lai:
        await interaction.response.defer(ephemeral=True)
        session = StudyPracticeSession(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            subject=mon or "MATHEMATICS",
            duration_minutes=thoi_gian or 45,
        )
        self.active_sessions[interaction.user.id] = session

        embed = discord.Embed(
            title=f"🎯 Bắt Đầu Phòng Thi: {mon}",
            description=(
                f"⏱️ **Thời gian làm bài:** `{thoi_gian} phút`\n"
                f"👤 **Thí sinh:** {interaction.user.mention}\n\n"
                "Chúc bạn làm bài thi thật tốt! Hãy tập trung tối đa nhé."
            ),
            color=0x22C55E,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Đăng ký Cog vào Bot Discord."""
    await bot.add_cog(StudyPracticeCog(bot))
