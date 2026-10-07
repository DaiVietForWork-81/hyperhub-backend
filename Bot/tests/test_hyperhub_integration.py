import unittest
import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from config.settings import settings
from database.database import Database
from database.cooldown import CooldownRepository
from database.moderation import ModerationRepository
from database.config import ConfigRepository
from utils import embeds, permissions, parsers, time_parser


class TestHyperHubIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_bot.db"
        self.db = Database(self.db_path)
        await self.db.connect()

    async def asyncTearDown(self):
        await self.db.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_cooldown_repository(self):
        repo = CooldownRepository(self.db)
        can, last = await repo.can_change(123456)
        self.assertTrue(can)
        self.assertIsNone(last)

        await repo.record_change(123456)
        can_after, last_after = await repo.can_change(123456)
        self.assertFalse(can_after)
        self.assertIsNotNone(last_after)

    async def test_config_repository(self):
        repo = ConfigRepository(self.db)
        color = await repo.get_embed_color()
        self.assertIsNone(color)

        await repo.set_embed_color(0x9F7AEA)
        color_after = await repo.get_embed_color()
        self.assertEqual(color_after, 0x9F7AEA)

    async def test_moderation_repository(self):
        repo = ModerationRepository(self.db)
        await repo.log_warn(
            target_id=111,
            target_name="User1",
            moderator_id=222,
            moderator_name="Mod1",
            reason="Test spam",
        )
        warns = await repo.get_warn_logs_for_user(111)
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["reason"], "Test spam")

    def test_time_parser(self):
        self.assertEqual(time_parser.parse_time("30s"), 30)
        self.assertEqual(time_parser.parse_time("5m"), 300)
        self.assertEqual(time_parser.parse_time("2h"), 7200)
        self.assertEqual(time_parser.parse_time("1d"), 86400)

    def test_hex_color_parser(self):
        self.assertEqual(parsers.parse_hex_color("#9F7AEA"), 0x9F7AEA)
        self.assertEqual(parsers.parse_hex_color("34d399"), 0x34D399)
        self.assertEqual(parsers.parse_hex_color("fff"), 0xFFFFFF)
        self.assertIsNone(parsers.parse_hex_color("invalid"))

    def test_embeds_hyperhub(self):
        embeds.set_theme_color(0x7C3AED)
        self.assertEqual(embeds.get_theme_color(), 0x7C3AED)
        e = embeds.success("Thành công")
        self.assertIn("Thành công", e.description)


if __name__ == "__main__":
    unittest.main()
