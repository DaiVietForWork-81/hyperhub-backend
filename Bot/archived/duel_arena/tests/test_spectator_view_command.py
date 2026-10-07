"""
tests/test_spectator_view_command.py
Kiểm thử toàn diện tính năng Chế Độ Khán Giả:
- Lệnh /view {id}: vào xem trực tiếp trận chỉ định
- Lệnh /view (không kèm id): hiển thị danh sách các trận đang diễn ra kèm menu chọn (chỉ user thấy - ephemeral)
- Lựa chọn trận từ Select Menu
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.ranked_duel import (
    RankedDuelCog,
    SpectatorMatchSelectView,
    SpectatorMatchSelect,
    grant_spectator_permission,
)
from services.duel_service import DuelSession, MatchmakingManager


class TestSpectatorViewCommand(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = RankedDuelCog(self.bot)
        self.matchmaker = self.cog.matchmaker

        self.spectator = MagicMock(spec=discord.Member)
        self.spectator.id = 777000111
        self.spectator.display_name = "ViewerFan"

        # Tạo mock 2 trận đấu active
        self.p1 = MagicMock(spec=discord.Member)
        self.p1.id = 1001
        self.p1.display_name = "PlayerA"

        self.p2 = MagicMock(spec=discord.Member)
        self.p2.id = 1002
        self.p2.display_name = "PlayerB"

        self.p3 = MagicMock(spec=discord.Member)
        self.p3.id = 1003
        self.p3.display_name = "PlayerC"

        self.p4 = MagicMock(spec=discord.Member)
        self.p4.id = 1004
        self.p4.display_name = "PlayerD"

        self.channel1 = MagicMock(spec=discord.TextChannel)
        self.channel1.id = 8881
        self.channel1.mention = "<#8881>"
        self.channel1.jump_url = "https://discord.com/channels/1/8881"
        self.channel1.set_permissions = AsyncMock()

        self.channel2 = MagicMock(spec=discord.TextChannel)
        self.channel2.id = 8882
        self.channel2.mention = "<#8882>"
        self.channel2.jump_url = "https://discord.com/channels/1/8882"
        self.channel2.set_permissions = AsyncMock()

        self.duel1 = DuelSession(
            bot=self.bot,
            guild=MagicMock(),
            player1=self.p1,
            player2=self.p2,
            p1_ranked_rank="T6",
            p1_ranked_rating=800,
            p2_ranked_rank="T6",
            p2_ranked_rating=850,
            is_custom_match=False,
        )
        self.duel1.match_code = "match1"
        self.duel1.channel = self.channel1
        self.duel1.is_active = True

        self.duel2 = DuelSession(
            bot=self.bot,
            guild=MagicMock(),
            player1=self.p3,
            player2=self.p4,
            p1_ranked_rank="T4",
            p1_ranked_rating=1500,
            p2_ranked_rank="T4",
            p2_ranked_rating=1480,
            is_custom_match=True,
        )
        self.duel2.match_code = "match2"
        self.duel2.channel = self.channel2
        self.duel2.is_active = True

    async def test_view_command_with_valid_id(self):
        """Kiểm tra /view {id} khi mã trận hợp lệ -> cấp quyền xem trực tiếp (ephemeral)."""
        self.matchmaker.active_sessions = {8881: self.duel1, 8882: self.duel2}

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.spectator
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await self.cog.view.callback(self.cog, interaction, id="match1")

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.channel1.set_permissions.assert_called_once()
        perm_target, perm_kwargs = self.channel1.set_permissions.call_args
        self.assertEqual(perm_target[0], self.spectator)
        self.assertTrue(perm_kwargs["read_messages"])
        self.assertFalse(perm_kwargs["send_messages"])
        self.assertFalse(perm_kwargs["add_reactions"])

        interaction.followup.send.assert_called_once()
        _, send_kwargs = interaction.followup.send.call_args
        self.assertTrue(send_kwargs.get("ephemeral"))
        self.assertIn("embed", send_kwargs)
        self.assertIn("view", send_kwargs)

    async def test_view_command_with_invalid_id(self):
        """Kiểm tra /view {id} khi mã trận không tồn tại -> thông báo lỗi gợi ý dùng /view."""
        self.matchmaker.active_sessions = {8881: self.duel1}

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.spectator
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await self.cog.view.callback(self.cog, interaction, id="non_existent_code")

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.channel1.set_permissions.assert_not_called()
        interaction.followup.send.assert_called_once()
        _, send_kwargs = interaction.followup.send.call_args
        self.assertTrue(send_kwargs.get("ephemeral"))
        self.assertIn("KHÔNG TÌM THẤY TRẬN ĐẤU", send_kwargs["embed"].title)

    async def test_view_command_as_participant(self):
        """Kiểm tra /view {id} nếu người gõ lệnh chính là đấu thủ trong trận đó -> nhắc nhở kênh đấu."""
        self.matchmaker.active_sessions = {8881: self.duel1}

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.p1  # Đấu thủ 1
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await self.cog.view.callback(self.cog, interaction, id="match1")

        self.channel1.set_permissions.assert_not_called()
        interaction.followup.send.assert_called_once()
        send_args, send_kwargs = interaction.followup.send.call_args
        self.assertTrue(send_kwargs.get("ephemeral"))
        self.assertIn("đấu thủ chính thức", send_args[0])

    async def test_view_command_without_id_empty(self):
        """Kiểm tra /view khi không có trận nào đang diễn ra -> thông báo chưa có trận."""
        self.matchmaker.active_sessions = {}

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.spectator
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await self.cog.view.callback(self.cog, interaction, id=None)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        interaction.followup.send.assert_called_once()
        _, send_kwargs = interaction.followup.send.call_args
        self.assertTrue(send_kwargs.get("ephemeral"))
        self.assertIn("KHÔNG CÓ TRẬN ĐẤU NÀO", send_kwargs["embed"].title)

    async def test_view_command_without_id_list_and_select(self):
        """Kiểm tra /view (không kèm id) -> list trận đấu và trả về Select Menu (chỉ user thấy)."""
        self.matchmaker.active_sessions = {8881: self.duel1, 8882: self.duel2}

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.spectator
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await self.cog.view.callback(self.cog, interaction, id=None)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        interaction.followup.send.assert_called_once()
        _, send_kwargs = interaction.followup.send.call_args
        self.assertTrue(send_kwargs.get("ephemeral"))
        self.assertIn("DANH SÁCH TRẬN ĐẤU", send_kwargs["embed"].title)

        # Kiểm tra View chứa Select Menu với đúng 2 options
        view = send_kwargs.get("view")
        self.assertIsInstance(view, SpectatorMatchSelectView)
        select_item = [c for c in view.children if isinstance(c, SpectatorMatchSelect)][0]
        self.assertEqual(len(select_item.options), 2)
        opt_values = [opt.value for opt in select_item.options]
        self.assertIn("match1", opt_values)
        self.assertIn("match2", opt_values)

    async def test_spectator_select_menu_callback(self):
        """Kiểm tra khi người dùng chọn trận từ Select Menu -> cấp quyền và gửi link phòng đấu."""
        self.matchmaker.active_sessions = {8881: self.duel1, 8882: self.duel2}

        select_view = SpectatorMatchSelectView([self.duel1, self.duel2], self.matchmaker)
        select_item = [c for c in select_view.children if isinstance(c, SpectatorMatchSelect)][0]
        select_item._values = ["match2"]

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = self.spectator
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        await select_item.callback(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.channel2.set_permissions.assert_called_once()
        perm_target, perm_kwargs = self.channel2.set_permissions.call_args
        self.assertEqual(perm_target[0], self.spectator)
        self.assertTrue(perm_kwargs["read_messages"])
        self.assertFalse(perm_kwargs["send_messages"])

        interaction.followup.send.assert_called_once()
        _, send_kwargs = interaction.followup.send.call_args
        self.assertTrue(send_kwargs.get("ephemeral"))
        self.assertIn("embed", send_kwargs)
        self.assertIn("view", send_kwargs)
