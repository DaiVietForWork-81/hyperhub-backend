"""
tests/test_problem_archive.py
Kiểm thử toàn diện dịch vụ lưu trữ tự động ProblemArchiveService và lệnh /search.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from services.problem_archive import ProblemArchiveService
from cogs.search import SearchCog


class TestProblemArchive(unittest.IsolatedAsyncioTestCase):
    def test_normalize_id(self):
        self.assertEqual(ProblemArchiveService.normalize_id("  1700a  "), "1700A")
        self.assertEqual(ProblemArchiveService.normalize_id("prb-t8-01"), "PRB-T8-01")
        self.assertEqual(ProblemArchiveService.normalize_id(""), "")

    async def test_search_ranked_problem_in_bank(self):
        bot = MagicMock(spec=commands.Bot)
        res = await ProblemArchiveService.search_problem(bot, "duel_t8_sum_even")
        self.assertIsNotNone(res)
        self.assertEqual(res["id"], "duel_t8_sum_even")
        self.assertEqual(res["mode"], "Ranked 1:1")
        self.assertTrue("solution_code" in res)
        self.assertTrue(len(res["solution_code"]) > 0)

    async def test_search_freedom_problem_fetcher(self):
        bot = MagicMock(spec=commands.Bot)
        mock_p_data = MagicMock()
        mock_p_data.id = "1700A"
        mock_p_data.name = "Optimal Path"
        mock_p_data.contest_id = 1700
        mock_p_data.index = "A"
        mock_p_data.rating = 800
        mock_p_data.time_limit = 2.0
        mock_p_data.memory_limit = 256
        mock_p_data.min_rank_required = "T8"
        mock_p_data.samples = [("1\n", "1\n")]

        with patch("services.problem_fetcher.ProblemFetcher.fetch_problem", new=AsyncMock(return_value=mock_p_data)):
            res = await ProblemArchiveService.search_problem(bot, "1700A")
            self.assertIsNotNone(res)
            self.assertEqual(res["id"], "1700A")
            self.assertEqual(res["mode"], "Freedom")
            self.assertEqual(res["name"], "Optimal Path")

    async def test_archive_problem_deduplication(self):
        bot = MagicMock(spec=commands.Bot)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_msg = MagicMock()
        mock_msg.id = 999888777
        mock_msg.jump_url = "https://discord.com/channels/1/2/999888777"
        mock_channel.send = AsyncMock(return_value=mock_msg)
        bot.get_channel.return_value = mock_channel

        prob_data = {
            "id": "TEST-DEDUP-01",
            "name": "Deduplication Problem Test",
            "mode": "Ranked 1:1",
            "tier": "T8",
            "rating": 800,
            "statement": "Statement test",
            "editorial": "Editorial test",
        }

        # Clear cache for this test ID
        ProblemArchiveService._load_cache()
        if "TEST-DEDUP-01" in ProblemArchiveService._archived_cache:
            del ProblemArchiveService._archived_cache["TEST-DEDUP-01"]

        # 1st archive -> should send message
        msg1 = await ProblemArchiveService.archive_problem(bot, prob_data)
        self.assertIsNotNone(msg1)
        self.assertEqual(mock_channel.send.call_count, 1)

        # 2nd archive with same ID -> should deduplicate and return None
        msg2 = await ProblemArchiveService.archive_problem(bot, prob_data)
        self.assertIsNone(msg2)
        self.assertEqual(mock_channel.send.call_count, 1)

    async def test_search_slash_command(self):
        bot = MagicMock(spec=commands.Bot)
        cog = SearchCog(bot)

        interaction = MagicMock(spec=discord.Interaction)
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        # Test search existing problem
        await cog.search.callback(cog, interaction, id="duel_t8_sum_even")
        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        call_kwargs = interaction.followup.send.call_args[1]
        self.assertIn("embeds", call_kwargs)
        self.assertEqual(len(call_kwargs["embeds"]), 2)
        self.assertIn("view", call_kwargs)
