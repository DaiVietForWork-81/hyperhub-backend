from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds
from utils.pagination import PaginatedView
from utils.respond import mod_error, mod_permission_gate

log = logging.getLogger(__name__)


class Lists(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def settings(self):
        return self.bot.settings

    @property
    def moderation(self):
        return self.bot.moderation

    @property
    def credit(self) -> str:
        return self.settings.credit

    async def _require_mod(self, interaction: discord.Interaction) -> bool:
        return await mod_permission_gate(interaction, self.settings)

    def _empty_embed(self, title: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description="Chưa có bản ghi nào.",
            color=embeds.INFO_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embeds.add_credit(embed, self.credit)
        embeds.attach_logo(embed)
        return embed

    @app_commands.command(name="kicklist", description="Xem lịch sử kick")
    async def kicklist(self, interaction: discord.Interaction) -> None:
        if not await self._require_mod(interaction):
            return

        await interaction.response.defer()

        rows = await self.moderation.get_kick_logs()
        if not rows:
            await interaction.followup.send(embed=self._empty_embed("Lịch sử Kick"))
            return

        embed_list = self._build_log_embeds("Lịch sử Kick", rows, lambda r: (
            f"**Target:** <@{r['target_id']}> ({r['target_name']})\n"
            f"**Moderator:** <@{r['moderator_id']}> ({r['moderator_name']})\n"
            f"**Lý do:** {r['reason']}\n"
            f"**Thời gian:** <t:{int(datetime.fromisoformat(r['timestamp']).timestamp())}:f>"
        ))

        view = PaginatedView(embed_list, interaction.user.id)
        await interaction.followup.send(embed=embed_list[0], view=view)

    @app_commands.command(name="mutelist", description="Xem lịch sử mute")
    async def mutelist(self, interaction: discord.Interaction) -> None:
        if not await self._require_mod(interaction):
            return

        await interaction.response.defer()

        rows = await self.moderation.get_mute_logs()
        if not rows:
            await interaction.followup.send(embed=self._empty_embed("Lịch sử Mute"))
            return

        embed_list = self._build_log_embeds("Lịch sử Mute", rows, lambda r: (
            f"**Target:** <@{r['target_id']}> ({r['target_name']})\n"
            f"**Moderator:** <@{r['moderator_id']}> ({r['moderator_name']})\n"
            f"**Lý do:** {r['reason']}\n"
            f"**Thời lượng:** {r['duration']}s\n"
            f"**Thời gian:** <t:{int(datetime.fromisoformat(r['timestamp']).timestamp())}:f>"
        ))

        view = PaginatedView(embed_list, interaction.user.id)
        await interaction.followup.send(embed=embed_list[0], view=view)

    @app_commands.command(name="banlist", description="Xem lịch sử ban")
    async def banlist(self, interaction: discord.Interaction) -> None:
        if not await self._require_mod(interaction):
            return

        await interaction.response.defer()

        rows = await self.moderation.get_ban_logs()
        if not rows:
            await interaction.followup.send(embed=self._empty_embed("Lịch sử Ban"))
            return

        def format_ban(row) -> str:
            ban_type = "Tạm thời" if row["is_temporary"] else "Vĩnh viễn"
            start = datetime.fromisoformat(row["start_time"])
            lines = [
                f"**Target:** <@{row['target_id']}> ({row['target_name']})",
                f"**Moderator:** <@{row['moderator_id']}> ({row['moderator_name']})",
                f"**Lý do:** {row['reason']}",
                f"**Loại:** {ban_type}",
                f"**Bắt đầu:** <t:{int(start.timestamp())}:f>",
            ]
            if row["duration"]:
                lines.append(f"**Thời lượng:** {row['duration']}s")
            if row["end_time"]:
                end = datetime.fromisoformat(row["end_time"])
                lines.append(f"**Kết thúc:** <t:{int(end.timestamp())}:f>")
            return "\n".join(lines)

        embed_list = self._build_log_embeds("Lịch sử Ban", rows, format_ban)
        view = PaginatedView(embed_list, interaction.user.id)
        await interaction.followup.send(embed=embed_list[0], view=view)

    @app_commands.command(name="rolelist", description="Xem danh sách role và người dùng được phép")
    async def rolelist(self, interaction: discord.Interaction) -> None:
        if not await self._require_mod(interaction):
            return

        embed = discord.Embed(
            title="Cấu hình quyền",
            color=embeds.INFO_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embeds.add_credit(embed, self.credit)
        embeds.attach_logo(embed)

        db_role_ids = await self.bot.config.get_mod_role_ids()
        roles_text = ""
        for role_id in sorted(db_role_ids):
            role = interaction.guild.get_role(role_id)
            if role:
                roles_text += f"{role.mention} - ID: {role.id}\n"
            else:
                roles_text += f"Role không xác định - ID: {role_id} (không tìm thấy trong server)\n"

        embed.add_field(
            name=f"Role được phép ({len(db_role_ids)})",
            value=(roles_text or "Chưa có — dùng `/role` để cấp quyền")
            + "\n\nRole có quyền **Administrator** tự động được phép.",
            inline=False,
        )

        users_text = ""
        for user_id in self.settings.allowed_user_ids:
            user = self.bot.get_user(user_id)
            if user:
                users_text += f"{user.mention} - ID: {user.id}\n"
            else:
                users_text += f"Người dùng không xác định - ID: {user_id}\n"

        embed.add_field(
            name=f"Người dùng được phép ({len(self.settings.allowed_user_ids)})",
            value=users_text or "Chưa cấu hình",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    def _build_log_embeds(
        self, title: str, rows: list, formatter: Callable
    ) -> list[discord.Embed]:
        items_per_page = 5
        pages = [rows[i:i + items_per_page] for i in range(0, len(rows), items_per_page)]
        embed_list: list[discord.Embed] = []

        for idx, page in enumerate(pages):
            embed = discord.Embed(
                title=f"{title} (Trang {idx + 1}/{len(pages)})",
                color=embeds.INFO_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            embeds.add_credit(embed, self.credit)
            for row in page:
                embed.add_field(
                    name=f"#{row['id']}",
                    value=formatter(row),
                    inline=False,
                )
            embeds.attach_logo(embed)
            embed_list.append(embed)

        return embed_list


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Lists(bot))