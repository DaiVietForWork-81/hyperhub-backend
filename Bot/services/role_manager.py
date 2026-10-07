"""Automatic Discord Role synchronization based on Rating changes."""

import discord

from config.settings import settings
from services.rank import get_rank_index
from utils.logger import get_logger

logger = get_logger("RoleManager")


class RoleManager:
    """Manages Discord role synchronization when a user's rank changes."""

    @classmethod
    async def sync_user_roles(
        cls,
        guild: discord.Guild,
        member: discord.Member,
        old_rating: int,
        new_rating: int,
        old_rank: str,
        new_rank: str,
        bot: discord.Client,
    ) -> bool:
        """
        Đồng bộ Freedom Role cho thành viên:
        1. Gỡ bỏ tất cả các role Freedom khác mà thành viên đang có.
        2. Cấp Role Freedom tương ứng với Bậc Rank mới.
        """
        try:
            freedom_role_ids = settings.get_all_freedom_rank_role_ids()
            new_role_id = settings.get_freedom_role_id_for_rank(new_rank)

            roles_to_remove = [
                role
                for role in member.roles
                if role.id in freedom_role_ids and role.id != new_role_id
            ]
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"Freedom Rank change: {old_rank} -> {new_rank}",
                )

            if new_role_id:
                new_role = guild.get_role(new_role_id)
                if new_role and new_role not in member.roles:
                    await member.add_roles(
                        new_role, reason=f"Assigned Freedom rank role {new_rank}"
                    )

            if get_rank_index(new_rank) > get_rank_index(old_rank):
                logger.info(
                    f"User {member} Freedom ranked up from {old_rank} to {new_rank} ({old_rating} -> {new_rating})"
                )

            return True
        except discord.Forbidden:
            logger.error(
                f"Missing permissions to manage Freedom roles for user {member} in guild {guild.name}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Error while syncing Freedom roles for user {member}: {e}",
                exc_info=True,
            )
            return False

    @classmethod
    async def sync_ranked_user_roles(
        cls,
        guild: discord.Guild,
        member: discord.Member,
        old_rating: int,
        new_rating: int,
        old_rank: str,
        new_rank: str,
        bot: discord.Client,
    ) -> bool:
        """
        Đồng bộ Ranked Role cho thành viên sau trận đấu 1:1:
        1. Gỡ bỏ tất cả các role Ranked khác mà thành viên đang có.
        2. Cấp Role Ranked tương ứng với Bậc Rank Ranked mới.
        """
        try:
            ranked_role_ids = settings.get_all_ranked_role_ids()
            new_role_id = settings.get_ranked_role_id_for_rank(new_rank)

            roles_to_remove = [
                role
                for role in member.roles
                if role.id in ranked_role_ids and role.id != new_role_id
            ]
            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"Ranked 1:1 change: {old_rank} -> {new_rank}",
                )

            if new_role_id:
                new_role = guild.get_role(new_role_id)
                if new_role and new_role not in member.roles:
                    await member.add_roles(
                        new_role, reason=f"Assigned Ranked 1:1 role {new_rank}"
                    )

            if get_rank_index(new_rank) > get_rank_index(old_rank):
                logger.info(
                    f"User {member} Ranked 1:1 ranked up from {old_rank} to {new_rank} ({old_rating} -> {new_rating})"
                )

            return True
        except discord.Forbidden:
            logger.error(
                f"Missing permissions to manage Ranked roles for user {member} in guild {guild.name}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Error while syncing Ranked roles for user {member}: {e}",
                exc_info=True,
            )
            return False

    @classmethod
    async def sync_special_achievement_roles(
        cls,
        guild: discord.Guild,
        member: discord.Member,
        active_role_key: str | None,
        bot: discord.Client,
    ) -> bool:
        """
        Đồng bộ Role Discord danh hiệu đặc biệt động (Overlord, Outclassed, Clutchmaster, Godly Luck, Fortune, Doomed):
        1. Tìm kiếm và gỡ bỏ tất cả các role danh hiệu đặc biệt khác không còn nắm giữ.
        2. Cấp Role tương ứng nếu người dùng đạt danh hiệu mới.
        """
        from services.special_roles import SPECIAL_ROLES

        try:
            # Thu thập tên các role đặc biệt
            role_keywords = {meta.name.lower() for meta in SPECIAL_ROLES.values()}
            role_keywords.update({k.lower() for k in SPECIAL_ROLES.keys()})

            target_meta = SPECIAL_ROLES.get(active_role_key.upper()) if active_role_key else None
            target_name = target_meta.name.lower() if target_meta else None

            roles_to_remove = []
            role_to_add = None

            for role in member.roles:
                r_lower = role.name.lower()
                for kw in role_keywords:
                    if kw in r_lower:
                        if target_name and target_name in r_lower:
                            # Đang có đúng role mục tiêu rồi
                            role_to_add = role
                        else:
                            roles_to_remove.append(role)
                        break

            if roles_to_remove:
                await member.remove_roles(
                    *roles_to_remove,
                    reason=f"Special Title expired or updated",
                )

            # Nếu chưa có role mục tiêu trên người, tìm role trong guild để cấp
            if target_meta and not role_to_add:
                for g_role in guild.roles:
                    g_lower = g_role.name.lower()
                    if target_name and target_name in g_lower:
                        await member.add_roles(
                            g_role, reason=f"Assigned Special Title: {target_meta.full_title}"
                        )
                        break

            return True
        except discord.Forbidden:
            logger.warning(
                f"Missing permissions to manage special roles for user {member} in guild {guild.name}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Error while syncing special roles for user {member}: {e}",
                exc_info=True,
            )
            return False

