from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds, parsers, permissions
from utils.respond import mod_error, mod_permission_gate
from utils.time_parser import parse_time

log = logging.getLogger(__name__)

MIN_DURATION_SECONDS = 30
MAX_MUTE_SECONDS = 28 * 86400


class Moderation(commands.Cog):
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

    async def _failure(self, interaction: discord.Interaction, message: str) -> None:
        await mod_error(interaction, message, self.settings, ephemeral=False)

    @app_commands.command(name="kick", description="Kick thành viên khỏi server")
    @app_commands.describe(
        user="Thành viên cần kick (dùng @mention hoặc chọn)",
        additional="Thêm ID hoặc @mention (cách nhau bằng dấu cách)",
        reason="Lý do kick",
    )
    async def kick(
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
            hierarchy_error = permissions.check_hierarchy(interaction, target)
            if hierarchy_error:
                failed.append((target, hierarchy_error))
                continue

            try:
                await target.kick(reason=reason)
                success.append(target)
                await self.moderation.log_kick(
                    target.id, str(target), interaction.user.id, str(interaction.user), reason,
                )
                log.info("Kick | %s | by %s | Reason: %s", target, interaction.user, reason)
            except discord.Forbidden:
                failed.append((target, "Thiếu quyền"))
            except discord.HTTPException as e:
                failed.append((target, f"API error: {e.status}"))
            except Exception as e:
                failed.append((target, str(e)))
            await asyncio.sleep(self.settings.batch_delay_seconds)

        for s in success:
            log_embed = embeds.build_log_embed(
                "Kick", f"{s.mention} ({s})", interaction.user.mention, reason,
                color=0xF59E0B, credit=self.credit,
            )
            await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)

        embed = self._build_result_embed(
            "Kick", success, failed, interaction.user, reason,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="mute", description="Timeout thành viên")
    @app_commands.describe(
        user="Thành viên cần mute (dùng @mention hoặc chọn)",
        additional="Thêm ID hoặc @mention (cách nhau bằng dấu cách)",
        reason="Lý do mute",
        duration="Thời gian (30s, 1m, 1h, 1d...)",
    )
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str,
        duration: str,
        additional: Optional[str] = None,
    ) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        time_duration = parse_time(duration)
        if time_duration is None:
            await mod_error(
                interaction,
                "Định dạng thời gian không hợp lệ. VD: `30s`, `1m`, `1h`, `2d`, `5d`.",
                self.settings,
            )
            return

        if time_duration < MIN_DURATION_SECONDS:
            await mod_error(interaction, "Thời gian mute tối thiểu là 30 giây.", self.settings)
            return

        if time_duration > MAX_MUTE_SECONDS:
            await mod_error(interaction, "Thời gian mute tối đa là 28 ngày.", self.settings)
            return

        await interaction.response.defer()

        targets = await parsers.collect_members(interaction.guild, user, additional)

        success: list[discord.Member] = []
        failed: list[tuple[discord.Member, str]] = []

        for target in targets:
            hierarchy_error = permissions.check_hierarchy(interaction, target)
            if hierarchy_error:
                failed.append((target, hierarchy_error))
                continue

            try:
                await target.timeout(timedelta(seconds=time_duration), reason=reason)
                success.append(target)
                await self.moderation.log_mute(
                    target.id, str(target), interaction.user.id, str(interaction.user),
                    reason, time_duration,
                )
                log.info(
                    "Mute | %s | by %s | Duration: %s | Reason: %s",
                    target, interaction.user, duration, reason,
                )
            except discord.Forbidden:
                failed.append((target, "Thiếu quyền"))
            except discord.HTTPException as e:
                failed.append((target, f"API error: {e.status}"))
            except Exception as e:
                failed.append((target, str(e)))
            await asyncio.sleep(self.settings.batch_delay_seconds)

        for s in success:
            log_embed = embeds.build_log_embed(
                "Mute", f"{s.mention} ({s})", interaction.user.mention, reason,
                color=0xFACC15, extra=[("Duration", duration)], credit=self.credit,
            )
            await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)

        embed = self._build_result_embed(
            "Mute", success, failed, interaction.user, reason,
            extra_field=("Duration", duration),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="unmute", description="Gỡ timeout cho thành viên")
    @app_commands.describe(
        user="Thành viên cần unmute",
        reason="Lý do unmute",
    )
    async def unmute(
        self, interaction: discord.Interaction, user: discord.Member, reason: str
    ) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        await interaction.response.defer()

        hierarchy_error = permissions.check_hierarchy(interaction, user)
        if hierarchy_error:
            await self._failure(interaction, hierarchy_error)
            return

        try:
            await user.timeout(None, reason=reason)
            embed = embeds.mod_success_embed(
                "Unmute thành công", f"{user.mention} đã được gỡ timeout.", credit=self.credit
            )
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            embed.add_field(name="Lý do", value=reason, inline=False)
            await interaction.followup.send(embed=embed)
            log.info("Unmute | %s | by %s | Reason: %s", user, interaction.user, reason)
            log_embed = embeds.build_log_embed(
                "Unmute", f"{user.mention} ({user})", interaction.user.mention, reason,
                color=0x34D399, credit=self.credit,
            )
            await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)
        except discord.Forbidden:
            await self._failure(interaction, "Bot không có quyền unmute thành viên này.")
        except Exception:
            log.exception("Unmute failed")
            await self._failure(interaction, "Đã xảy ra lỗi không mong muốn.")

    @app_commands.command(name="ban", description="Ban người dùng khỏi server")
    @app_commands.describe(
        user="Người dùng cần ban (dùng @mention, ID, hoặc chọn)",
        additional="Thêm ID hoặc @mention (cách nhau bằng dấu cách)",
        reason="Lý do ban",
        duration="Thời gian cho ban tạm thời (30s, 1m, 1h, 1d...). Để trống là vĩnh viễn.",
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: str,
        duration: Optional[str] = None,
        additional: Optional[str] = None,
    ) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        time_duration = 0
        is_temporary = False
        end_time: Optional[datetime] = None

        if duration:
            time_duration = parse_time(duration)
            if time_duration is None:
                await mod_error(
                    interaction,
                    "Định dạng thời gian không hợp lệ. VD: `30s`, `1m`, `1h`, `2d`, `5d`.",
                    self.settings,
                )
                return
            if time_duration < MIN_DURATION_SECONDS:
                await mod_error(interaction, "Thời gian ban tối thiểu là 30 giây.", self.settings)
                return
            is_temporary = True
            end_time = datetime.now(timezone.utc) + timedelta(seconds=time_duration)

        await interaction.response.defer()

        targets = await parsers.collect_users(self.bot, interaction.guild, user, additional)

        success: list[discord.User] = []
        failed: list[tuple[discord.User, str]] = []

        for target in targets:
            member = interaction.guild.get_member(target.id)
            if member:
                hierarchy_error = permissions.check_hierarchy(interaction, member)
                if hierarchy_error:
                    failed.append((target, hierarchy_error))
                    continue

            try:
                await interaction.guild.ban(target, reason=reason)
                success.append(target)

                start_time = datetime.now(timezone.utc).isoformat()
                end_time_str = end_time.isoformat() if end_time else None

                await self.moderation.log_ban(
                    target.id, str(target), interaction.user.id, str(interaction.user),
                    reason, is_temporary, time_duration if is_temporary else None,
                    start_time, end_time_str,
                )

                if is_temporary and end_time:
                    entry_id = await self.moderation.schedule_unban(
                        target.id, str(target), interaction.guild_id,
                        interaction.user.id, str(interaction.user),
                        reason, start_time, end_time_str,
                    )
                    scheduler = getattr(self.bot, "scheduler", None)
                    if scheduler:
                        await scheduler.schedule_ban({
                            "id": entry_id,
                            "target_id": target.id,
                            "target_name": str(target),
                            "guild_id": interaction.guild_id,
                            "moderator_id": interaction.user.id,
                            "moderator_name": str(interaction.user),
                            "reason": reason,
                            "start_time": start_time,
                            "end_time": end_time_str,
                        })

                ban_type = "Tạm thời" if is_temporary else "Vĩnh viễn"
                log.info(
                    "Ban (%s) | %s | by %s | %s | Reason: %s",
                    ban_type, target, interaction.user,
                    f"Duration: {duration}" if duration else "Permanent", reason,
                )

            except discord.Forbidden:
                failed.append((target, "Thiếu quyền"))
            except discord.HTTPException as e:
                if e.status == 429:
                    failed.append((target, "Rate limited"))
                else:
                    failed.append((target, f"API error: {e.status}"))
            except Exception as e:
                failed.append((target, str(e)))
            await asyncio.sleep(self.settings.batch_delay_seconds)

        for s in success:
            extra_log = [("Type", "Tạm thời" if is_temporary else "Vĩnh viễn")]
            if is_temporary and duration:
                extra_log.append(("Duration", duration))
            log_embed = embeds.build_log_embed(
                "Ban", f"{s.mention} ({s})", interaction.user.mention, reason,
                color=0xB91C1C, extra=extra_log, credit=self.credit,
            )
            await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)

        extra = ("Duration", duration) if is_temporary else None
        embed = self._build_result_embed(
            "Ban", success, failed, interaction.user, reason, extra_field=extra,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="unban", description="Unban một người dùng")
    @app_commands.describe(
        user_id="ID Discord của người dùng cần unban",
        reason="Lý do unban",
    )
    @app_commands.rename(user_id="user")
    async def unban(
        self, interaction: discord.Interaction, user_id: str, reason: str
    ) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        await interaction.response.defer()

        clean_id = user_id.strip().replace("<@", "").replace(">", "").replace("!", "")
        try:
            uid = int(clean_id)
        except ValueError:
            await self._failure(
                interaction, "ID người dùng không hợp lệ. Cung cấp ID Discord dạng số."
            )
            return

        try:
            try:
                ban_entry = await interaction.guild.fetch_ban(uid)
            except discord.NotFound:
                await self._failure(interaction, "Người dùng này không bị ban.")
                return

            await interaction.guild.unban(ban_entry.user, reason=reason)

            embed = embeds.mod_success_embed(
                "Unban thành công", f"{ban_entry.user} đã được unban.", credit=self.credit
            )
            embed.add_field(
                name="Người dùng",
                value=f"{ban_entry.user} (ID: {ban_entry.user.id})",
                inline=False,
            )
            embed.add_field(name="Lý do", value=reason, inline=False)
            embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
            await interaction.followup.send(embed=embed)

            log.info("Unban | %s | by %s | Reason: %s", ban_entry.user, interaction.user, reason)
            log_embed = embeds.build_log_embed(
                "Unban", f"{ban_entry.user} (ID: {ban_entry.user.id})",
                interaction.user.mention, reason,
                color=0x34D399, credit=self.credit,
            )
            await embeds.send_log(self.bot, interaction.guild, log_embed, self.settings)

        except discord.Forbidden:
            await self._failure(interaction, "Bot không có quyền unban thành viên.")
        except Exception:
            log.exception("Unban failed")
            await self._failure(interaction, "Đã xảy ra lỗi không mong muốn.")

    def _build_result_embed(
        self,
        action: str,
        success: list,
        failed: list,
        moderator: discord.Member,
        reason: str,
        extra_field: Optional[tuple[str, str]] = None,
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

        if extra_field:
            embed.add_field(name=extra_field[0], value=extra_field[1], inline=False)

        embeds.add_credit(embed, self.credit)
        embeds.attach_logo(embed)
        return embed

    @app_commands.command(name="reset", description="Xoá toàn bộ log kick/mute/ban/warn")
    async def reset(self, interaction: discord.Interaction) -> None:
        if not await mod_permission_gate(interaction, self.settings):
            return

        await interaction.response.defer()

        counts = await self.moderation.reset_all_logs()
        total = sum(counts.values())
        embed = discord.Embed(
            title="Đã xoá log",
            description=f"Đã xoá **{total}** bản ghi",
            color=embeds.SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        details = "\n".join(
            f"**{t.replace('_', ' ').title()}:** {c}" for t, c in counts.items()
        )
        embed.add_field(name="Chi tiết", value=details or "Không có", inline=False)
        embeds.add_credit(embed, self.credit)
        embeds.attach_logo(embed)
        await interaction.followup.send(embed=embed)

        log.info("Logs reset by %s — %s", interaction.user, counts)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))