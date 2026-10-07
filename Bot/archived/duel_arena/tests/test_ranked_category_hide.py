"""
tests/test_ranked_category_hide.py
Kiểm thử tự động việc ẩn danh mục (Cộng Đồng, Tài Liệu, Voice Chat)
trong lúc thi Ranked 1:1 và khôi phục khi hoàn tất.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from config.settings import settings
from services.duel_service import DuelSession
from cogs.ranked_duel import RankedDuelCog


class TestRankedCategoryHide(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock(spec=commands.Bot)
        self.guild = MagicMock(spec=discord.Guild)

        self.p1 = MagicMock(spec=discord.Member)
        self.p1.id = 1000000000000001
        self.p1.display_name = "PlayerOne"
        self.p1.mention = "<@1000000000000001>"
        self.p1.voice = None
        self.p1.move_to = AsyncMock()

        self.p2 = MagicMock(spec=discord.Member)
        self.p2.id = 1000000000000002
        self.p2.display_name = "PlayerTwo"
        self.p2.mention = "<@1000000000000002>"
        self.p2.voice = None
        self.p2.move_to = AsyncMock()

        # Tạo 3 mock CategoryChannel cho các danh mục cần ẩn
        self.hidden_ids = [1534147161091211414, 1534147951797080174, 1534148003701719070]
        self.categories = {}
        for cid in self.hidden_ids:
            cat = MagicMock(spec=discord.CategoryChannel)
            cat.id = cid
            cat.name = f"Category-{cid}"
            cat.overwrites = {}
            cat.set_permissions = AsyncMock()
            self.categories[cid] = cat

        self.guild.get_channel = MagicMock(side_effect=lambda cid: self.categories.get(cid))

    async def test_hide_categories_during_ranked(self):
        """Kiểm tra khi bắt đầu Ranked, các danh mục quy định bị ẩn với 2 đấu thủ."""
        duel = DuelSession(
            bot=self.bot,
            guild=self.guild,
            player1=self.p1,
            player2=self.p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=200,
            p2_ranked_rank="T8",
            p2_ranked_rating=250,
            is_custom_match=False,
        )

        await duel._hide_contestant_categories()
        self.assertTrue(duel.categories_hidden)

        # Mỗi category trong 3 danh mục phải được gọi set_permissions 2 lần (cho p1 và p2)
        for cid in self.hidden_ids:
            cat = self.categories[cid]
            self.assertEqual(cat.set_permissions.call_count, 2)
            calls = cat.set_permissions.call_args_list
            targets = [c[0][0] for c in calls]
            self.assertIn(self.p1, targets)
            self.assertIn(self.p2, targets)
            for c in calls:
                self.assertFalse(c[1]["view_channel"])
                self.assertFalse(c[1]["connect"])
                self.assertFalse(c[1]["read_messages"])

    async def test_disconnect_voice_if_in_hidden_category(self):
        """Kiểm tra nếu thí sinh đang ở trong voice channel thuộc danh mục bị ẩn, bot sẽ disconnect họ."""
        v_ch = MagicMock(spec=discord.VoiceChannel)
        v_ch.id = 999888
        v_ch.category_id = 1534148003701719070  # Thuộc category Voice Chat
        v_state = MagicMock()
        v_state.channel = v_ch
        self.p1.voice = v_state

        duel = DuelSession(
            bot=self.bot,
            guild=self.guild,
            player1=self.p1,
            player2=self.p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=200,
            p2_ranked_rank="T8",
            p2_ranked_rating=250,
            is_custom_match=False,
        )

        await duel._hide_contestant_categories()
        self.p1.move_to.assert_called_once_with(
            None,
            reason=f"Ranked 1:1 #{duel.match_code}: Tự động ngắt kết nối voice chat",
        )

    async def test_restore_categories_on_match_finish(self):
        """Kiểm tra khi trận đấu kết thúc, quyền truy cập các danh mục được khôi phục nguyên vẹn."""
        duel = DuelSession(
            bot=self.bot,
            guild=self.guild,
            player1=self.p1,
            player2=self.p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=200,
            p2_ranked_rank="T8",
            p2_ranked_rating=250,
            is_custom_match=False,
        )

        # Ẩn danh mục trước
        await duel._hide_contestant_categories()
        self.assertTrue(duel.categories_hidden)

        # Reset mock calls để kiểm tra pha restore
        for cat in self.categories.values():
            cat.set_permissions.reset_mock()

        # Khôi phục danh mục
        await duel._restore_contestant_categories()
        self.assertFalse(duel.categories_hidden)

        for cid in self.hidden_ids:
            cat = self.categories[cid]
            self.assertEqual(cat.set_permissions.call_count, 2)
            calls = cat.set_permissions.call_args_list
            targets = [c[0][0] for c in calls]
            self.assertIn(self.p1, targets)
            self.assertIn(self.p2, targets)
            for c in calls:
                self.assertIn("overwrite", c[1])

    async def test_custom_match_does_not_hide_categories(self):
        """Trận đấu giao hữu (is_custom_match=True) không tự ý ẩn danh mục của người chơi."""
        duel = DuelSession(
            bot=self.bot,
            guild=self.guild,
            player1=self.p1,
            player2=self.p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=200,
            p2_ranked_rank="T8",
            p2_ranked_rating=250,
            is_custom_match=True,
        )

        await duel._hide_contestant_categories()
        self.assertFalse(duel.categories_hidden)
        for cat in self.categories.values():
            cat.set_permissions.assert_not_called()

    async def test_cleanup_orphaned_category_hides(self):
        """Kiểm tra tính năng dọn dẹp các quyền ẩn mồ côi khi bot restart."""
        cog = RankedDuelCog(self.bot)
        self.bot.guilds = [self.guild]

        orphan_member = MagicMock(spec=discord.Member)
        orphan_member.id = 888777666
        orphan_member.display_name = "StuckPlayer"

        # Giả lập danh mục voice có overwrite ẩn còn sót lại
        voice_cat = self.categories[1534148003701719070]
        stuck_ow = MagicMock()
        stuck_ow.view_channel = False
        stuck_ow.connect = False
        voice_cat.overwrites = {orphan_member: stuck_ow}

        await cog._cleanup_orphaned_category_hides()
        voice_cat.set_permissions.assert_called_once_with(
            orphan_member,
            overwrite=None,
            reason="Khôi phục danh mục do bot khởi động lại hoặc trận đấu đã kết thúc",
        )
