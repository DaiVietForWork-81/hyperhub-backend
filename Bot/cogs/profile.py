"""Hồ sơ cá nhân và chỉ số thành tích thi đấu tinh gọn, trực quan (Hỗ trợ bảo lưu Rating Kỷ Lục cho RHT1 / Giải Nghệ)."""

import os
import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from database.database import async_session_factory
from database.repositories.cf_repo import CFAccountRepository
from database.repositories.submission_repo import SubmissionRepository
from database.repositories.user_repo import UserRepository
from services.codeforces_api import cf_api
from services.rank import (
    get_rank_badge,
    get_rank_by_rating,
    get_rank_color,
    get_rank_title,
)
# [ARCHIVED] ProfileCardGenerator — đã lưu trữ tại archived/duel_arena/services/profile_card.py
# from services.profile_card import ProfileCardGenerator
from utils.logger import get_logger

logger = get_logger("ProfileCog")


class ProfileCog(commands.Cog, name="Profile"):
    """Lệnh xem hồ sơ và thống kê thành tích thi đấu của thí sinh."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="profile",
        description="Xem hồ sơ Competitive Programming, điểm Rating (pts) và Rank của bạn hoặc người khác",
    )
    @app_commands.describe(
        user="Thành viên Discord cần xem hồ sơ (để trống nếu xem chính mình)"
    )
    async def profile(
        self, interaction: discord.Interaction, user: discord.Member | None = None
    ) -> None:
        target_user = user or interaction.user
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
        except Exception as defer_err:
            logger.warning(f"Lỗi defer /profile: {defer_err}")

        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            cf_repo = CFAccountRepository(session)
            sub_repo = SubmissionRepository(session)
            db_user, _ = await user_repo.get_or_create(target_user.id)
            cf_acc = await cf_repo.get_by_discord_id(target_user.id)
            server_standing = await user_repo.get_user_standing(target_user.id, sort_by="rating")
            recent_subs, _ = await sub_repo.get_user_submissions(target_user.id, page=1, per_page=5)

        r_curr = "Unrated"
        r_max = "Unrated"
        if cf_acc and cf_acc.cf_handle:
            try:
                cf_info = await cf_api.get_user_info(cf_acc.cf_handle)
                if cf_info:
                    r_curr = str(cf_info.get("rating", "Unrated"))
                    r_max = str(cf_info.get("maxRating", "Unrated"))
            except Exception:
                pass

        rank_title = get_rank_title(db_user.rank)
        rank_badge = get_rank_badge(db_user.rank)
        rank_color = get_rank_color(db_user.rank)

        embed = discord.Embed(
            title=f"{rank_badge} Hồ Sơ: {target_user.display_name}",
            color=rank_color,
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)
        embed.add_field(
            name="🏅 Rank / Rating",
            value=f"`{rank_title}` — **{db_user.rating} pts**",
            inline=True,
        )
        embed.add_field(
            name="🏆 Thứ hạng Server",
            value=f"#{server_standing}" if server_standing else "Chưa xếp hạng",
            inline=True,
        )
        embed.add_field(
            name="📊 Nộp bài",
            value=f"✅ {db_user.accepted} AC / {db_user.total_submissions} tổng",
            inline=True,
        )
        if cf_acc and cf_acc.cf_handle:
            embed.add_field(
                name="🔗 Codeforces",
                value=f"`{cf_acc.cf_handle}` — Rating: **{r_curr}** (Peak: **{r_max}**)",
                inline=False,
            )

        if recent_subs:
            sub_lines = []
            for s in recent_subs:
                verdict_icon = "✅" if s.verdict == "AC" else "❌"
                sub_lines.append(f"{verdict_icon} `{s.problem_id}` — {s.language}")
            embed.add_field(
                name="📝 Bài Nộp Gần Nhất",
                value="\n".join(sub_lines),
                inline=False,
            )

        embed.set_footer(text="HyperHub CP Bot • /help để xem thêm lệnh")

        try:
            await interaction.followup.send(embed=embed)
        except discord.NotFound:
            logger.warning("Interaction /profile đã hết hạn trước khi gửi phản hồi.")
        except Exception as send_err:
            logger.error(f"Lỗi khi gửi phản hồi /profile: {send_err}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
