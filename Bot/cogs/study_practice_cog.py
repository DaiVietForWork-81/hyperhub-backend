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
# CỜ TÍNH NĂNG (FEATURE FLAG): ĐÃ KÍCH HOẠT ĐỒNG BỘ WEB HUB <-> DISCORD BOT
# ==============================================================================
IS_STUDY_PRACTICE_ENABLED: bool = True


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
        description="🎯 Tính năng Luyện Đề & Thi Thử Trực Tuyến Orbit | Vietnam (Dành cho học sinh)",
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
            embed.set_footer(text="Orbit Study Engine | Vietnam • Trạng thái: Chưa kích hoạt")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Khi được kích hoạt: đồng bộ Chuỗi Ngày Học (Study Streak) & mở đề thực chiến từ kho
        await interaction.response.defer(ephemeral=True)
        session = StudyPracticeSession(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id or 0,
            subject=mon or "MATHEMATICS",
            duration_minutes=thoi_gian or 45,
        )
        self.active_sessions[interaction.user.id] = session

        # Bốc 1 đề thực tế từ kho documents_archive theo môn đã chọn
        doc_row = None
        streak_val = 1
        xp_val = 50
        if hasattr(self.bot, "db") and self.bot.db:
            try:
                doc_row = await self.bot.db.fetchone(
                    """
                    SELECT id, title, file_name, estimated_level, page_count, jump_url
                    FROM documents_archive
                    WHERE LOWER(subject) = LOWER(?)
                    ORDER BY RANDOM() LIMIT 1
                    """,
                    mon or "MATHEMATICS",
                )
                if not doc_row:
                    doc_row = await self.bot.db.fetchone(
                        "SELECT id, title, file_name, estimated_level, page_count, jump_url FROM documents_archive ORDER BY RANDOM() LIMIT 1"
                    )
                # Ghi nhận điểm danh chuỗi ngày học khi bắt đầu luyện đề trên Discord
                vn_tz = datetime.timezone(datetime.timedelta(hours=7))
                today_str = datetime.datetime.now(vn_tz).strftime("%Y-%m-%d")
                yesterday_str = (datetime.datetime.now(vn_tz) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                prof = await self.bot.db.fetchone(
                    "SELECT current_streak, max_streak, last_study_date, study_xp, exams_completed FROM study_profiles WHERE discord_id = ?",
                    interaction.user.id,
                )
                if prof:
                    c_streak, m_streak, l_date, s_xp, ex_done = prof[0] or 0, prof[1] or 0, prof[2] or "", prof[3] or 0, prof[4] or 0
                    if l_date != today_str:
                        c_streak = (c_streak + 1) if l_date == yesterday_str else 1
                        m_streak = max(m_streak, c_streak)
                        s_xp += 50
                    s_xp += 30
                    streak_val = c_streak
                    xp_val = s_xp
                    await self.bot.db.execute(
                        """
                        UPDATE study_profiles
                        SET username = ?, display_name = ?, current_streak = ?, max_streak = ?,
                            last_study_date = ?, study_xp = ?, exams_completed = ?, updated_at = ?
                        WHERE discord_id = ?
                        """,
                        interaction.user.name, interaction.user.display_name, c_streak, m_streak,
                        today_str, s_xp, ex_done + 1, now_iso, interaction.user.id,
                    )
                else:
                    streak_val = 1
                    xp_val = 80
                    await self.bot.db.execute(
                        """
                        INSERT INTO study_profiles
                        (discord_id, username, display_name, avatar_url, current_streak, max_streak,
                         last_study_date, study_xp, pomodoro_count, study_minutes, exams_completed,
                         docs_contributed, dream_school, dream_score, updated_at)
                        VALUES (?, ?, ?, ?, 1, 1, ?, 80, 0, ?, 1, 0, '', '', ?)
                        """,
                        interaction.user.id, interaction.user.name, interaction.user.display_name,
                        str(interaction.user.display_avatar.url) if interaction.user.display_avatar else "",
                        today_str, thoi_gian or 45, now_iso,
                    )
            except Exception as e:
                log.debug("Lỗi đồng bộ study_profiles trong /luyende: %s", e)

        doc_info = ""
        view = discord.ui.View(timeout=300)
        if doc_row:
            doc_id, d_title, d_fname, d_level, d_pages, d_jump = doc_row
            doc_info = (
                f"\n📄 **Đề thi được giao:** `{d_title or d_fname}`\n"
                f"🎓 **Khối lớp:** `{d_level or 'THPT'}` • **Quy mô:** `{d_pages or 1} trang`\n"
            )
            if d_jump:
                view.add_item(discord.ui.Button(label="🔗 Mở Bài Đăng Gốc", url=d_jump, style=discord.ButtonStyle.link))
            view.add_item(
                discord.ui.Button(
                    label="📖 Đọc PDF & Làm Đề Trên Web",
                    url=f"https://orbit-psi-black.vercel.app/hub#exam-{doc_id}",
                    style=discord.ButtonStyle.link,
                )
            )

        embed = discord.Embed(
            title=f"🎯 Phòng Thi Thực Chiến: {mon}",
            description=(
                f"⏱️ **Thời gian làm bài:** `{thoi_gian} phút`\n"
                f"👤 **Thí sinh:** {interaction.user.mention}\n"
                f"🔥 **Chuỗi ngày học (Streak):** `{streak_val} ngày` • **Tổng XP:** `{xp_val} XP`"
                f"{doc_info}\n"
                "💡 *Mẹo: Nhấn **Đọc PDF & Làm Đề Trên Web** để mở chế độ Chia Đôi Màn Hình (Đọc PDF + Phiếu Trả Lời Chuẩn 2025)!*"
            ),
            color=0xA855F7,
        )
        embed.set_footer(text="Orbit Study Engine • Đồng bộ Hồ Sơ & Streak 2 chiều Discord ↔ Web")
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="chuoi",
        description="🔥 Xem Chuỗi Ngày Học (Study Streak), Cấp bậc Học Thuật & Bảng Xếp Hạng đồng bộ Web ↔ Discord",
    )
    async def cmd_chuoi_hoc_tap(self, interaction: discord.Interaction) -> None:
        """Lệnh điểm danh và xem hồ sơ chuỗi ngày học ngay trên Discord."""
        await interaction.response.defer(ephemeral=True)
        if not hasattr(self.bot, "db") or not self.bot.db:
            await interaction.followup.send("❌ Cơ sở dữ liệu chưa sẵn sàng.", ephemeral=True)
            return

        vn_tz = datetime.timezone(datetime.timedelta(hours=7))
        today_str = datetime.datetime.now(vn_tz).strftime("%Y-%m-%d")
        yesterday_str = (datetime.datetime.now(vn_tz) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        contrib_row = await self.bot.db.fetchone(
            "SELECT COUNT(*) FROM documents_archive WHERE author_id = ?",
            interaction.user.id,
        )
        docs_contrib = contrib_row[0] if contrib_row else 0

        prof = await self.bot.db.fetchone(
            """
            SELECT current_streak, max_streak, last_study_date, study_xp,
                   pomodoro_count, study_minutes, exams_completed, dream_school
            FROM study_profiles
            WHERE discord_id = ?
            """,
            interaction.user.id,
        )

        checked_in_now = False
        if prof:
            c_streak, m_streak, l_date, s_xp, pomo, mins, exams, dream = (
                prof[0] or 0, prof[1] or 0, prof[2] or "", prof[3] or 0,
                prof[4] or 0, prof[5] or 0, prof[6] or 0, prof[7] or ""
            )
            if l_date != today_str:
                c_streak = (c_streak + 1) if l_date == yesterday_str else 1
                m_streak = max(m_streak, c_streak)
                s_xp += 50
                checked_in_now = True
                await self.bot.db.execute(
                    """
                    UPDATE study_profiles
                    SET username = ?, display_name = ?, current_streak = ?, max_streak = ?,
                        last_study_date = ?, study_xp = ?, docs_contributed = MAX(docs_contributed, ?), updated_at = ?
                    WHERE discord_id = ?
                    """,
                    interaction.user.name, interaction.user.display_name, c_streak, m_streak,
                    today_str, s_xp, docs_contrib, now_iso, interaction.user.id,
                )
        else:
            c_streak, m_streak, s_xp, pomo, mins, exams, dream = 1, 1, 50 + docs_contrib * 50, 0, 0, 0, ""
            checked_in_now = True
            await self.bot.db.execute(
                """
                INSERT INTO study_profiles
                (discord_id, username, display_name, avatar_url, current_streak, max_streak,
                 last_study_date, study_xp, pomodoro_count, study_minutes, exams_completed,
                 docs_contributed, dream_school, dream_score, updated_at)
                VALUES (?, ?, ?, ?, 1, 1, ?, ?, 0, 0, 0, ?, '', '', ?)
                """,
                interaction.user.id, interaction.user.name, interaction.user.display_name,
                str(interaction.user.display_avatar.url) if interaction.user.display_avatar else "",
                today_str, s_xp, docs_contrib, now_iso,
            )

        status_line = "✨ **Đã điểm danh hôm nay (+50 XP)!**" if checked_in_now else "✅ **Hôm nay bạn đã duy trì chuỗi thành công!**"
        embed = discord.Embed(
            title=f"🔥 Hồ Sơ Học Thuật & Chuỗi Ngày Học — {interaction.user.display_name}",
            description=(
                f"{status_line}\n\n"
                f"• 🔥 **Chuỗi hiện tại:** `{c_streak} ngày liên tiếp` (Kỷ lục: `{m_streak} ngày`)\n"
                f"• ⚡ **Điểm Kinh Nghiệm:** `{s_xp} XP`\n"
                f"• 📝 **Đề đã luyện:** `{exams} đề` • **Pomodoro:** `{pomo} phiên ({mins} phút)`\n"
                f"• 📚 **Đề đóng góp cho kho:** `{docs_contrib} đề`\n"
                + (f"• 🎯 **Mục tiêu NV1:** `{dream}`\n" if dream else "")
            ),
            color=0xFF4FCB,
        )
        embed.set_footer(text="Đồng bộ 100% với Orbit Web Hub (orbit-psi-black.vercel.app/hub)")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    """Đăng ký Cog vào Bot Discord."""
    await bot.add_cog(StudyPracticeCog(bot))
