from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds, parsers, permissions
from utils.pagination import PaginatedView
from utils.respond import mod_error, mod_permission_gate

log = logging.getLogger(__name__)


class Warnings(commands.Cog):
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

    def _build_warn_embed(
        self,
        action: str,
        success: list,
        failed: list,
        moderator: discord.Member,
        reason: str,
    ) -> discord.Embed:
        if success and not failed:
            color = embeds.SUCCESS_COLOR
        elif not success:
            color = embeds.ERROR_COLOR
        else:
            color = embeds.WARN_COLOR

        embed = discord.Embed(
            title=f"Kết quả {action}",
            description=f"Thành công: {len(success)} | Thất bại: {len(failed)}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        if success:
            names = "\n".join(f"{u.mention} ({u})" for u in success[:15])
            embed.add_field(
                name=f"Đã {action} thành công ({len(success)})",
                value=names or "Không có",
                inline=False,
            )

        if failed:
            details = "\n".join(f"{u[0].mention} - {u[1]}" for u in failed[:10])
            embed.add_field(
                name=f"Thất bại ({len(failed)})",
                value=details or "Không có",
                inline=False,
            )

        embed.add_field(name="Moderator", value=moderator.mention, inline=False)
        embed.add_field(name="Lý do", value=reason, inline=False)

        embeds.add_credit(embed, self.credit)
        embeds.attach_logo(embed)
        return embed

    @app_commands.command(name="warn", description="Cảnh cáo thành viên")
    @app_commands.describe(
        user="Thành viên cần cảnh cáo (dùng @mention hoặc chọn)",
        additional="Thêm ID hoặc @mention (cách nhau bằng dấu cách)",
        reason="Lý do cảnh cáo",
    )
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
        additional: Optional[str] = None,
    ) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        await interaction.response.defer()

        targets = await parsers.collect_members(interaction.guild, user, additional)

        success: list[discord.Member] = []
        failed: list[tuple[discord.Member, str]] = []

        for target in targets:
            hierarchy_error = permissions.check_hierarchy(interaction, target, warn=True)
            if hierarchy_error:
                failed.append((target, hierarchy_error))
                continue

            try:
                warn_count = (await self.moderation.get_warn_count(target.id)) + 1
                dm_embed = discord.Embed(
                    title=f"Cảnh cáo từ {interaction.guild.name}",
                    description=f"**Lý do:** {reason}",
                    color=embeds.WARN_COLOR,
                    timestamp=datetime.now(timezone.utc),
                )
                dm_embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
                dm_embed.add_field(name="Cảnh cáo #", value=str(warn_count), inline=False)
                embeds.attach_logo(dm_embed)
                try:
                    await target.send(embed=dm_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

                success.append(target)
                await self.moderation.log_warn(
                    target.id, str(target), interaction.user.id, str(interaction.user), reason,
                )
                log.info("Warn | %s | by %s | Reason: %s", target, interaction.user, reason)
            except Exception as e:
                failed.append((target, str(e)))
            await asyncio.sleep(self.settings.batch_delay_seconds)

        for s in success:
            log_embed = embeds.build_log_embed(
                "Warn", f"{s.mention} ({s})", interaction.user.mention, reason,
                color=embeds.WARN_COLOR, credit=self.credit,
            )
            await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)

        embed = self._build_warn_embed("Warn", success, failed, interaction.user, reason)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="warnlist", description="Xem lịch sử cảnh cáo")
    async def warnlist(self, interaction: discord.Interaction) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        await interaction.response.defer()

        rows = await self.moderation.get_warn_logs()
        if not rows:
            embed = discord.Embed(
                title="Lịch sử cảnh cáo",
                description="Chưa có bản ghi cảnh cáo nào.",
                color=embeds.INFO_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            embeds.add_credit(embed, self.credit)
            embeds.attach_logo(embed)
            await interaction.followup.send(embed=embed)
            return

        counts = await self.moderation.get_warn_counts(
            [row["target_id"] for row in rows]
        )

        items_per_page = 5
        pages = [rows[i:i + items_per_page] for i in range(0, len(rows), items_per_page)]
        embed_list: list[discord.Embed] = []

        for idx, page in enumerate(pages):
            embed = discord.Embed(
                title=f"Lịch sử cảnh cáo (Trang {idx + 1}/{len(pages)})",
                color=embeds.INFO_COLOR,
                timestamp=datetime.now(timezone.utc),
            )
            embeds.add_credit(embed, self.credit)
            for row in page:
                count = counts.get(row["target_id"], 0)
                embed.add_field(
                    name=f"<@{row['target_id']}> ({row['target_name']}) — ⚠ {count} total",
                    value=(
                        f"**Moderator:** <@{row['moderator_id']}> ({row['moderator_name']})\n"
                        f"**Lý do:** {row['reason']}\n"
                        f"**Thời gian:** <t:{int(datetime.fromisoformat(row['timestamp']).timestamp())}:f>"
                    ),
                    inline=False,
                )
            embed_list.append(embed)

        view = PaginatedView(embed_list, interaction.user.id)
        await interaction.followup.send(embed=embed_list[0], view=view)

    @app_commands.command(name="deletewarn", description="Xoá một cảnh cáo cụ thể theo số thứ tự")
    @app_commands.describe(
        user="Thành viên cần xoá cảnh cáo",
        reason="Lý do xoá cảnh cáo",
        number="Số cảnh cáo cần xoá (1 = cũ nhất)",
    )
    async def deletewarn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
        number: int,
    ) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        if number < 1:
            await mod_error(interaction, "Số cảnh cáo phải từ 1 trở lên.", self.settings)
            return

        await interaction.response.defer()

        warns = await self.moderation.get_warn_logs_for_user(user.id)
        if number > len(warns):
            await mod_error(
                interaction,
                f"{user.mention} chỉ có {len(warns)} cảnh cáo. Không thể xoá cảnh cáo #{number}.",
                self.settings,
            )
            return

        warn = warns[number - 1]
        deleted = await self.moderation.delete_warn(warn["id"])

        if not deleted:
            await mod_error(interaction, "Không thể xoá cảnh cáo.", self.settings)
            return

        embed = embeds.mod_success_embed(
            "Đã xoá cảnh cáo",
            f"Đã xoá cảnh cáo #{number} của {user.mention}.",
            credit=self.credit,
        )
        embed.add_field(name="Lý do cũ", value=warn["reason"], inline=False)
        embed.add_field(name="Lý do mới", value=reason, inline=False)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        await interaction.followup.send(embed=embed)

        log.info("DeleteWarn | %s | #%s | by %s | Reason: %s", user, number, interaction.user, reason)

        log_embed = embeds.build_log_embed(
            "DeleteWarn", f"{user.mention} ({user})", interaction.user.mention, reason,
            color=embeds.AURA_COLOR,
            extra=[("Đã xoá Warn #", str(number)), ("Lý do cũ", warn["reason"])],
            credit=self.credit,
        )
        await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)

    @app_commands.command(name="warntest", description="Gửi cảnh cáo test qua DM (không lưu cơ sở dữ liệu)")
    @app_commands.describe(
        user="Thành viên cần gửi cảnh cáo test",
        reason="Lý do cảnh cáo test",
    )
    async def warntest(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
    ) -> None:
        if interaction.user.id not in self.settings.allowed_user_ids:
            await mod_error(
                interaction, "Chỉ những người dùng được phép mới dùng lệnh này.", self.settings
            )
            return

        await interaction.response.defer()

        dm_embed = discord.Embed(
            title=f"Cảnh cáo từ {interaction.guild.name}",
            description=f"**Lý do:** {reason}",
            color=embeds.WARN_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embeds.attach_logo(dm_embed)

        try:
            await user.send(embed=dm_embed)
            embed = embeds.mod_success_embed(
                "Đã gửi cảnh cáo test",
                f"Đã gửi cảnh cáo test đến {user.mention}.",
                credit=self.credit,
            )
            embed.add_field(name="Lý do", value=reason, inline=False)
            await interaction.followup.send(embed=embed)
            log.info("TestWarn | %s | by %s | Reason: %s", user, interaction.user, reason)
        except discord.Forbidden:
            await mod_error(
                interaction, f"Không thể DM {user.mention}. Họ đã tắt DM.", self.settings
            )
        except discord.HTTPException as e:
            await mod_error(interaction, f"Gửi DM thất bại: {e}", self.settings)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Warnings(bot))