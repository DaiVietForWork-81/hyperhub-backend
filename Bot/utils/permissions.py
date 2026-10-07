"""Permissions and rank-checking utilities with owner bypass logging."""

import discord
from discord.ext import commands

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("Permissions")


def is_owner_user(user_id: int) -> bool:
    """Kiểm tra xem Discord ID có phải là OWNER_ID hay không."""
    return settings.OWNER_ID > 0 and user_id == settings.OWNER_ID


def is_owner_interaction(interaction: discord.Interaction) -> bool:
    """Kiểm tra xem interaction có phải do Owner gọi hay không."""
    return is_owner_user(interaction.user.id)


def is_admin_or_owner(interaction: discord.Interaction) -> bool:
    """Kiểm tra quyền hạn: Phải là Bot Owner HOẶC có quyền Quản trị viên (Administrator) trên Server."""
    if is_owner_user(interaction.user.id):
        return True
    if (
        isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    ):
        return True
    return False


def owner_only_check():
    """Custom command check requiring owner permission."""

    async def predicate(ctx: commands.Context) -> bool:
        if is_owner_user(ctx.author.id):
            logger.info(
                f"[OWNER_COMMAND] User {ctx.author} (ID: {ctx.author.id}) executed owner command: {ctx.command}"
            )
            return True
        return False

    return commands.check(predicate)


def check_and_log_owner_bypass(user_id: int, action: str) -> bool:
    """If user is owner, logs the bypass action and returns True. Otherwise False."""
    if is_owner_user(user_id):
        logger.warning(
            f"[OWNER_BYPASS] User ID {user_id} triggered bypass for action: {action}"
        )
        return True
    return False


from types import SimpleNamespace
from typing import Optional


def in_change_channel(interaction: discord.Interaction, settings: Any) -> bool:
    ch_id = getattr(settings, "change_channel_id", 0) or getattr(settings, "CHANGE_ID", 0)
    return interaction.channel is not None and interaction.channel.id == ch_id


def has_unlimited_role(member: Any, settings: Any) -> bool:
    unl_ids = getattr(settings, "unlimited_role_ids", set()) or set()
    if member is None or not unl_ids:
        return False
    roles = getattr(member, "roles", []) or []
    return any(role.id in unl_ids for role in roles)


def is_admin(member: Any, settings: Any) -> bool:
    if member is None:
        return False
    guild_permissions = getattr(member, "guild_permissions", None)
    if guild_permissions is not None and guild_permissions.administrator:
        return True
    owner_id = getattr(settings, "owner_id", 0) or getattr(settings, "OWNER_ID", 0)
    return owner_id > 0 and member.id == owner_id


def has_mod_permission(
    member: Any,
    settings: Any,
    mod_role_ids: set[int] | None = None,
) -> bool:
    """Cho phép khi: role có quyền Administrator, user là Owner, hoặc có role nằm trong mod_roles."""
    if member is None:
        return False
    guild_permissions = getattr(member, "guild_permissions", None)
    if guild_permissions is not None and guild_permissions.administrator:
        return True
    allowed_ids = getattr(settings, "allowed_user_ids", set()) or set()
    if member.id in allowed_ids:
        return True
    owner_id = getattr(settings, "owner_id", 0) or getattr(settings, "OWNER_ID", 0)
    if owner_id > 0 and member.id == owner_id:
        return True
    if mod_role_ids:
        roles = getattr(member, "roles", []) or []
        return any(role.id in mod_role_ids for role in roles)
    return False


def check_hierarchy(
    interaction: discord.Interaction, target: discord.Member, *, warn: bool = False
) -> Optional[str]:
    """Kiểm tra thứ bậc role trước khi kick/mute/ban/warn."""
    guild = target.guild
    actor = interaction.user

    if actor == target:
        return ("Bạn không thể cảnh cáo chính mình." if warn else "Bạn không thể quản lý chính mình.")

    if target == guild.owner:
        return ("Bạn không thể cảnh cáo chủ server." if warn else "Bạn không thể quản lý chủ server.")

    if not isinstance(actor, discord.Member):
        return "Không thể xác minh quyền của bạn."

    mod_top = actor.roles[-1] if actor.roles else None
    tgt_top = target.roles[-1] if target.roles else None

    if mod_top and tgt_top and mod_top <= tgt_top and actor.id != guild.owner_id:
        return ("Bạn không thể cảnh cáo thành viên có role ngang bằng hoặc cao hơn." if warn
                else "Bạn không thể quản lý thành viên có role ngang bằng hoặc cao hơn.")

    bot_member = guild.me
    bot_top = bot_member.roles[-1] if bot_member and bot_member.roles else None

    if not bot_top or (tgt_top and bot_top <= tgt_top):
        return ("Role của bot quá thấp để cảnh cáo thành viên này." if warn
                else "Role của bot quá thấp để quản lý thành viên này.")

    return None
