from __future__ import annotations

import discord

from config.settings import Settings
from utils import embeds, permissions


async def reply(interaction: discord.Interaction, embed: discord.Embed, *, ephemeral: bool = True) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)


async def mod_permission_gate(interaction: discord.Interaction, settings: Settings) -> bool:
    """Chặn nếu user không có quyền moderation. Trả về True nếu được phép."""
    mod_role_ids: set[int] | None = None
    config = getattr(interaction.client, "config", None)
    if config is not None:
        try:
            mod_role_ids = await config.get_mod_role_ids()
        except Exception:
            mod_role_ids = None
    if permissions.has_mod_permission(interaction.user, settings, mod_role_ids):
        return True
    await mod_error(interaction, "Bạn không có quyền sử dụng lệnh này.", settings)
    return False


async def mod_error(
    interaction: discord.Interaction,
    message: str,
    settings: Settings,
    *,
    ephemeral: bool = True,
) -> None:
    await reply(
        interaction,
        embeds.mod_error_embed("Lỗi", message, credit=settings.credit),
        ephemeral=ephemeral,
    )