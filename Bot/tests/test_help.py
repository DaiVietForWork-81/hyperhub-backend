"""Unit tests for HelpCog and .help DM command for Owner ID."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.help import HelpCog
from config.settings import settings


class TestHelpCog(unittest.IsolatedAsyncioTestCase):
    """Test suite for HelpCog."""

    def setUp(self):
        self.bot = MagicMock()
        self.cog = HelpCog(self.bot)

    def test_build_owner_help_embeds(self):
        """Kiểm tra tạo 3 Rich Embeds cẩm nang dành cho Owner."""
        embeds = self.cog.build_owner_help_embeds()
        self.assertEqual(len(embeds), 3)
        self.assertIn("BOT OWNER", embeds[0].title)
        self.assertIn(".skip", embeds[0].description)
        self.assertIn(".test", embeds[0].description)
        self.assertIn(".close", embeds[0].description)
        self.assertIn(".list", embeds[0].description)

        self.assertIn("SLASH COMMANDS", embeds[1].title)
        self.assertIn("/reload", embeds[1].description)
        self.assertIn("/setpts", embeds[1].description)

        self.assertIn("6 KÊNH GIAO DIỆN", embeds[2].title)
        self.assertIn("#📋・ranked", embeds[2].description)

    async def test_send_owner_help_dm_success(self):
        """Kiểm tra gửi DM cẩm nang cho Owner ID thành công."""
        owner = MagicMock()
        owner.send = AsyncMock()
        self.bot.get_user.return_value = owner

        with patch.object(settings, "OWNER_ID", 123456789):
            sent = await self.cog.send_owner_help_dm()
            self.assertTrue(sent)
            owner.send.assert_called_once()

    async def test_on_message_help_trigger(self):
        """Prefix đã bị vô hiệu hóa: cog không còn listener on_message (slash-only)."""
        self.assertFalse(hasattr(self.cog, "on_message"))

    def test_admin_guide_embeds_allowlist_only(self):
        """Panel kênh admin chỉ liệt kê lệnh trong allowlist."""
        from unittest.mock import MagicMock as _MM
        from discord import app_commands as _ac

        async def _cb(interaction):
            pass

        keep = _ac.Command(name="ban", description="Ban user", callback=_cb)
        drop = _ac.Command(name="play", description="Play music", callback=_cb)
        fake_cog = _MM()
        fake_cog.__cog_app_commands__ = [keep, drop]
        fake_bot = _MM()
        fake_bot.cogs = {"Moderation": fake_cog, "Music": fake_cog}
        fake_bot.tree.get_commands.return_value = [keep, drop]
        self.cog.bot = fake_bot

        embeds = self.cog.build_admin_guide_embeds()
        self.assertEqual(len(embeds), 1)
        self.assertIn("/ban", embeds[0].description)
        self.assertNotIn("/play", embeds[0].description)

    def test_prune_tree_commands_allowlist(self):
        """prune_tree_commands chỉ giữ lệnh trong COMMAND_ALLOWLIST."""
        from unittest.mock import MagicMock as _MM
        from discord import app_commands as _ac
        from bot import COMMAND_ALLOWLIST, prune_tree_commands

        async def _cb(interaction):
            pass

        keep = _ac.Command(name="kick", description="Kick", callback=_cb)
        drop = _ac.Command(name="play", description="Play", callback=_cb)
        group = _ac.Group(name="exam", description="Exam group")
        fake_bot = _MM()
        fake_bot.tree.get_commands.return_value = [keep, drop, group]
        removed = []

        def _remove(name):
            removed.append(name)

        fake_bot.tree.remove_command.side_effect = _remove
        prune_tree_commands(fake_bot)
        self.assertIn("play", removed)
        self.assertIn("exam", removed)
        self.assertNotIn("kick", removed)
        self.assertTrue(len(COMMAND_ALLOWLIST) >= 11)


if __name__ == "__main__":
    unittest.main()
