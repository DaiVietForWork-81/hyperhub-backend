"""Thẻ hạn mức Token và thông tin Gói Hyper của thành viên (Lệnh Slash /check).

Thay thế hoàn toàn lệnh /profile cũ. Cho phép thành viên và quản trị viên kiểm tra
Gói thành viên hiện tại (Free, Pro, Ultra, Elite), hạn mức Token trong ngày, thanh
tiến trình trực quan, thời gian đếm ngược làm mới (00:00 UTC+7) và lịch sử tạo đề gần nhất.
"""

from __future__ import annotations

import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

try:
    from not_finished.exam_generator.services.user_token_service import user_token_service
except ImportError:
    from services.user_token_service import user_token_service
from utils.logger import get_logger

logger = get_logger("CheckTokenCog")


class CheckTokenCog(commands.Cog, name="CheckToken"):
    """Lệnh kiểm tra hạn mức Token và Gói thành viên Hyper."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="check",
        description="Kiểm tra hạn mức Token hàng ngày, Gói Hyper và lịch sử tạo đề của bạn hoặc thành viên khác",
    )
    @app_commands.describe(
        user="Thành viên cần kiểm tra (để trống để kiểm tra chính bạn)"
    )
    async def check(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member] = None,
    ) -> None:
        """Hiển thị Thẻ Token Card trực quan của người dùng."""
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
        except Exception as defer_err:
            logger.warning(f"Lỗi defer /check: {defer_err}")

        target_user = user or interaction.user
        guild = interaction.guild

        # Đảm bảo target_user là discord.Member để đọc được role
        member_obj: Optional[discord.Member] = None
        if isinstance(target_user, discord.Member):
            member_obj = target_user
        elif guild:
            member_obj = guild.get_member(target_user.id)

        # Lấy thông tin token và đồng bộ role
        token_data = await user_token_service.get_or_sync_user_token(
            target_user.id, member_obj
        )

        # Tính toán timestamp Unix của lần reset tiếp theo (00:00 UTC+7)
        secs_left = user_token_service.get_seconds_until_next_reset()
        reset_unix = int(datetime.datetime.now(datetime.timezone.utc).timestamp() + secs_left)

        # Thanh tiến trình
        if token_data["is_unlimited"]:
            progress_bar = "`[██████████████]` *(Không giới hạn)*"
            remaining_str = "Vô hạn (**∞**)"
            daily_str = "Không giới hạn (**∞**)"
            used_str = f"**{token_data['used_tokens_today']}** lần"
        else:
            progress_bar = user_token_service.render_progress_bar(
                token_data["used_tokens_today"], token_data["daily_tokens"], length=14
            )
            remaining_str = f"**{token_data['remaining_tokens']}** / **{token_data['daily_tokens']}**"
            daily_str = f"**{token_data['daily_tokens']}** Tokens"
            used_str = f"**{token_data['used_tokens_today']}** Tokens"

        embed = discord.Embed(
            title=f"{token_data['tier_icon']} Thẻ Hạn Mức Token • {target_user.display_name}",
            color=token_data["color"],
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_thumbnail(url=target_user.display_avatar.url)

        embed.add_field(
            name="💎 Gói Thành Viên",
            value=f"**{token_data['tier_name']}**",
            inline=True,
        )
        embed.add_field(
            name="🎫 Hạn Mức / Ngày",
            value=daily_str,
            inline=True,
        )
        embed.add_field(
            name="⚡ Token Khả Dụng",
            value=remaining_str,
            inline=True,
        )

        embed.add_field(
            name="📊 Tiến Trình Tiêu Thụ Hôm Nay",
            value=f"{progress_bar}\nĐã dùng: {used_str}",
            inline=False,
        )

        embed.add_field(
            name="⏳ Làm Mới Hạn Mức",
            value=f"<t:{reset_unix}:R> *(00:00 UTC+7)*",
            inline=True,
        )
        embed.add_field(
            name="📦 Tổng Đề Đã Tạo",
            value=f"**{token_data['total_generated']}** bộ đề",
            inline=True,
        )

        # Lịch sử các đề thi đã tạo gần đây
        recent_jobs = await user_token_service.get_recent_jobs_by_user(target_user.id, limit=5)
        if recent_jobs:
            history_lines = []
            for j in recent_jobs:
                created_ts = int(j.created_at.timestamp()) if j.created_at else 0
                status_icon = "✅" if j.status in ("COMPLETED", "CLOSED") else ("🔄" if j.status == "IN_PROGRESS" else "❌")
                history_lines.append(
                    f"{status_icon} `{j.subject[:24]}` • **{j.length_tier}** ({j.mode}) — `{j.token_cost}` tk (<t:{created_ts}:R>)"
                )
            embed.add_field(
                name="📝 Đề Thi Đã Tạo Gần Nhất",
                value="\n".join(history_lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="📝 Đề Thi Đã Tạo Gần Nhất",
                value="*Chưa tạo đề nào. Hãy vào kênh <#1550896415046377615> để bắt đầu!*",
                inline=False,
            )

        embed.set_footer(
            text="HyperHub AI Generator • /check để kiểm tra hạn mức bất kỳ lúc nào"
        )

        try:
            await interaction.followup.send(embed=embed)
        except discord.NotFound:
            logger.warning("Interaction /check đã hết hạn trước khi gửi phản hồi.")
        except Exception as e:
            logger.error(f"Lỗi khi gửi phản hồi /check: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CheckTokenCog(bot))
