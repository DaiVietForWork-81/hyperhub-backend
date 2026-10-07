"""Unit tests for AdminCog, including /setpts and .setpts for Freedom and Ranked modes."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.admin import AdminCog
from config.settings import settings
from database.database import async_session_factory, init_db
from database.repositories.user_repo import UserRepository


class TestAdminCog(unittest.IsolatedAsyncioTestCase):
    """Test suite for AdminCog setpts command."""

    async def asyncSetUp(self):
        await init_db()
        self.bot = MagicMock()
        self.cog = AdminCog(self.bot)
        self.user_id = 999888777111

    async def asyncTearDown(self):
        async with async_session_factory() as session:
            from sqlalchemy import delete
            from database.models import User

            await session.execute(delete(User).where(User.discord_id == self.user_id))
            await session.commit()

    async def test_setpts_freedom_mode(self):
        """Kiểm tra /setpts với mode='freedom'."""
        member = MagicMock()
        member.id = self.user_id
        member.mention = f"<@{self.user_id}>"
        member.display_name = "TestFreedomUser"

        interaction = MagicMock()
        interaction.user.id = settings.OWNER_ID
        interaction.user.guild_permissions.administrator = True
        interaction.guild = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch("cogs.admin.is_admin_or_owner", return_value=True):
            with patch("cogs.admin.RoleManager.sync_user_roles", AsyncMock(return_value=True)):
                await self.cog.setpts.callback(
                    self.cog,
                    interaction=interaction,
                    user=member,
                    number=1500,
                    mode="freedom",
                )

        # Kiểm tra database đã cập nhật Freedom rating = 1500 và rank = T4
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u = await repo.get_by_id(self.user_id)
            self.assertIsNotNone(u)
            self.assertEqual(u.rating, 1500)
            self.assertEqual(u.rank, "T4")

        interaction.followup.send.assert_called_once()
        sent_embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("FREEDOM MODE", sent_embed.title)

    async def test_setpts_ranked_mode(self):
        """Kiểm tra /setpts với mode='ranked'."""
        member = MagicMock()
        member.id = self.user_id
        member.mention = f"<@{self.user_id}>"
        member.display_name = "TestRankedUser"

        interaction = MagicMock()
        interaction.user.id = settings.OWNER_ID
        interaction.user.guild_permissions.administrator = True
        interaction.guild = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch("cogs.admin.is_admin_or_owner", return_value=True):
            with patch("cogs.admin.RoleManager.sync_ranked_user_roles", AsyncMock(return_value=True)):
                await self.cog.setpts.callback(
                    self.cog,
                    interaction=interaction,
                    user=member,
                    number=2400,
                    mode="ranked",
                )

        # Kiểm tra database đã cập nhật Ranked rating = 2400 và rank = LT1
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u = await repo.get_by_id(self.user_id)
            self.assertIsNotNone(u)
            self.assertEqual(u.ranked_rating, 2400)
            self.assertEqual(u.ranked_rank, "LT1")

        interaction.followup.send.assert_called_once()
        sent_embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("RANKED 1:1 MODE", sent_embed.title)


if __name__ == "__main__":
    unittest.main()
