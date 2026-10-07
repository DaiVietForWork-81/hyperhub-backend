from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds, permissions
from utils.respond import reply

log = logging.getLogger(__name__)

MAX_SELECT_ROLES = 25


class RoleSyncView(discord.ui.View):
    """Chọn role được phép (tích = cho phép, bỏ tích = thu hồi) rồi Lưu."""

    def __init__(
        self,
        bot: commands.Bot,
        roles: list[discord.Role],
        allowed_ids: set[int],
        credit: str,
    ) -> None:
        super().__init__(timeout=120)
        self.bot = bot
        self.credit = credit
        self.role_map = {role.id: role for role in roles}
        self.message: discord.Message | None = None
        self._select = self._build_select(roles, allowed_ids)
        self.add_item(self._select)

    @staticmethod
    def _build_select(roles: list[discord.Role], allowed_ids: set[int]) -> discord.ui.Select:
        options = []
        for role in roles[:MAX_SELECT_ROLES]:
            label = role.name[:90]
            if role.id in allowed_ids:
                label = f"\u2713 {label}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(role.id),
                    description=f"ID: {role.id}",
                    default=role.id in allowed_ids,
                )
            )
        max_values = len(options) or 1
        select = discord.ui.Select(
            placeholder="Tích role được phép, bỏ tích để thu hồi quyền...",
            min_values=0,
            max_values=max_values,
            options=options or [discord.SelectOption(label="Không có role nào", value="none")],
        )
        select.callback = RoleSyncView._on_select
        return select

    async def _on_select(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

    def _result_embed(self, description: str, title: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=embeds.SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embeds.add_credit(embed, self.credit)
        embeds.attach_logo(embed)
        return embed

    @discord.ui.button(label="Lưu thay đổi", style=discord.ButtonStyle.success)
    async def save(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        selected_ids = {int(v) for v in self._select.values if v != "none"}
        db_ids = await self.bot.config.get_mod_role_ids()
        to_add = selected_ids - db_ids
        to_remove = db_ids - selected_ids

        added = await self.bot.config.add_mod_roles(sorted(to_add), interaction.user.id) if to_add else 0
        removed = await self.bot.config.remove_mod_roles(sorted(to_remove)) if to_remove else 0

        if added or removed:
            lines = []
            if added:
                names = ", ".join(self.role_map[rid].mention for rid in sorted(to_add) if rid in self.role_map)
                lines.append(f"**Đã cho phép (+{added}):** {names or 'không xác định'}")
            if removed:
                names = ", ".join(self.role_map[rid].mention for rid in sorted(to_remove) if rid in self.role_map)
                lines.append(f"**Đã thu hồi (-{removed}):** {names or 'không xác định'}")
            embed = self._result_embed("\n".join(lines), "Đã cập nhật quyền moderation")
            log.info("Mod roles changed by %s: +%s -%s", interaction.user, sorted(to_add), sorted(to_remove))
        else:
            embed = self._result_embed("Không có thay đổi nào.", "Đã cập nhật quyền moderation")
        self.clear_items()
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Huỷ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.clear_items()
        if interaction.response.is_done():
            await interaction.followup.send("Đã huỷ.", ephemeral=True)
        else:
            await interaction.response.edit_message(content="Đã huỷ.", embed=None, view=None)

    async def on_timeout(self) -> None:
        self.clear_items()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class RoleManager(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def settings(self):
        return self.bot.settings

    @property
    def credit(self) -> str:
        return self.settings.credit

    async def _admin_only(self, interaction: discord.Interaction) -> bool:
        if permissions.is_admin(interaction.user, self.bot.settings):
            return True
        await reply(
            interaction,
            embeds.error("Chỉ người dùng có quyền **Administrator** (hoặc OWNER_ID) mới dùng lệnh này."),
            title="Không có quyền",
        )
        return False

    @app_commands.command(
        name="role",
        description="Quản lý role được phép dùng lệnh moderation (chỉ admin/owner)",
    )
    async def role(self, interaction: discord.Interaction) -> None:
        if not await self._admin_only(interaction):
            return
        db_ids = await self.bot.config.get_mod_role_ids()
        guild = interaction.guild

        all_roles = sorted(
            (role for role in guild.roles if not role.is_default()),
            key=lambda role: role.position,
            reverse=True,
        )
        by_id = {role.id: role for role in all_roles}

        roles = [
            by_id[rid]
            for rid in sorted(db_ids, key=lambda rid: by_id[rid].position, reverse=True)
            if rid in by_id
        ]
        seen = {role.id for role in roles}
        roles.extend(role for role in all_roles if role.id not in seen)
        roles = roles[:MAX_SELECT_ROLES]

        view = RoleSyncView(self.bot, roles, db_ids, self.credit)
        embed = embeds.info(
            "Tích (\u2713) các role được phép dùng lệnh moderation, **bỏ tích để thu hồi**, "
            "sau đó nhấn **Lưu thay đổi**.\n\n"
            "Role có quyền **Administrator** tự động được phép — không cần thêm.",
            title="\U0001F6E1\uFE0F Quản lý role moderation",
        )
        message = await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleManager(bot))