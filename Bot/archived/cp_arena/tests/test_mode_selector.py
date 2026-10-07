# -*- coding: utf-8 -*-
"""
tests/test_mode_selector.py
Kiem thu toan dien giao dien kenh CHON_ID (So tay may chu HyperHub)
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.mode_selector import ModeSelectorCog, ModeInteractiveView


class TestModeSelector(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = MagicMock(spec=commands.Bot)
        self.cog = ModeSelectorCog(self.bot)

    def test_build_mode_explanation_embeds_count_and_structure(self):
        """Kiem tra ham tao 6 Embeds So Tay Toan Dien."""
        embeds = ModeSelectorCog.build_mode_explanation_embeds()
        self.assertEqual(len(embeds), 6)

        # Embed 1: So tay toan dien may chu
        self.assertIn('[1]', embeds[0].title)
        self.assertIn('HYPERHUB CP ARENA', embeds[0].title)
        self.assertIn('MỤC TIÊU', embeds[0].description)
        self.assertIn('QUICK START', embeds[0].description)

        # Embed 2: 12 Bac Rank
        self.assertIn('[2]', embeds[1].title)
        self.assertIn('12 BẬC RANK', embeds[1].title)
        self.assertIn('Tier 8', embeds[1].description)
        self.assertIn('Tier 1', embeds[1].description)
        self.assertIn('Bảo hiểm tân binh', embeds[1].description)

        # Embed 3: Freedom Mode
        self.assertIn('[3]', embeds[2].title)
        self.assertIn('FREEDOM MODE', embeds[2].title)
        self.assertIn('Codeforces', embeds[2].description)

        # Embed 4: Ranked Arena 1:1
        self.assertIn('[4]', embeds[3].title)
        self.assertIn('1:1', embeds[3].title)
        self.assertIn('2 Mạng', embeds[3].description)
        self.assertIn('Focus Mode', embeds[3].description)

        # Embed 5: Kho De, Khan Gia, Profile 4K
        self.assertIn('[5]', embeds[4].title)
        self.assertIn('/search', embeds[4].title)
        self.assertIn('/view', embeds[4].title)
        self.assertIn('3840×2160', embeds[4].description)

        # Embed 6: Anti-Cheat & Rules
        self.assertIn('[6]', embeds[5].title)
        self.assertIn('ANTI-CHEAT 2.0', embeds[5].title)
        self.assertIn('Nghiêm Cấm Tuyệt Đối AI', embeds[5].description)

    def test_interactive_view_components(self):
        """Kiem tra cac thanh phan cua ModeInteractiveView."""
        view = ModeInteractiveView(self.bot)

        # Tim select menu
        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        self.assertEqual(len(selects), 1)
        select = selects[0]
        self.assertEqual(select.custom_id, 'select_mode_guide')
        self.assertEqual(len(select.options), 6)
        option_values = [opt.value for opt in select.options]
        self.assertEqual(option_values, ['overview', 'ranks', 'freedom', 'ranked', 'features', 'rules'])

        # Tim cac nut bam
        buttons = [item for item in view.children if isinstance(item, discord.ui.Button)]
        self.assertEqual(len(buttons), 7)
        btn_ids = [btn.custom_id for btn in buttons]
        self.assertIn('btn_mode_link_cf', btn_ids)
        self.assertIn('btn_mode_submit_open', btn_ids)
        self.assertIn('btn_mode_ranked_duel', btn_ids)
        self.assertIn('btn_mode_view_rank', btn_ids)
        self.assertIn('btn_mode_search_prob', btn_ids)
        self.assertIn('btn_mode_spectate', btn_ids)
        self.assertIn('btn_mode_profile', btn_ids)

    async def test_auto_setup_chon_channel_success(self):
        """Kiem tra auto_setup_chon_channel purge va post thanh cong."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 1541436758904799392
        mock_channel.name = 'mode'
        mock_channel.purge = AsyncMock()
        mock_channel.send = AsyncMock()

        self.bot.get_channel.return_value = mock_channel

        with patch('cogs.mode_selector.settings') as mock_settings:
            mock_settings.CHON_ID = 1541436758904799392
            await self.cog.auto_setup_chon_channel()

            mock_channel.purge.assert_awaited_once_with(limit=25)
            self.assertEqual(mock_channel.send.call_count, 2)
            # Call 1: Embeds 1-3
            call1_kwargs = mock_channel.send.call_args_list[0][1]
            self.assertEqual(len(call1_kwargs['embeds']), 3)
            # Call 2: Embeds 4-6 + View
            call2_kwargs = mock_channel.send.call_args_list[1][1]
            self.assertEqual(len(call2_kwargs['embeds']), 3)
            self.assertIsInstance(call2_kwargs['view'], ModeInteractiveView)

    async def test_alias_auto_setup_mode_channel(self):
        """Kiem tra tinh tuong thich cua auto_setup_mode_channel."""
        self.assertEqual(self.cog.auto_setup_mode_channel, self.cog.auto_setup_chon_channel)

    async def test_select_menu_interaction(self):
        """Kiem tra khi user chon muc trong dropdown menu se tra ve dung embed."""
        mode_view = ModeInteractiveView(self.bot)
        selects = [item for item in mode_view.children if isinstance(item, discord.ui.Select)]
        select = selects[0]

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        select._values = ['features']
        await select.callback(mock_interaction)

        mock_interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        mock_interaction.followup.send.assert_awaited_once()
        _, kwargs = mock_interaction.followup.send.call_args
        self.assertIn('[5]', kwargs['embed'].title)
        self.assertTrue(kwargs['ephemeral'])


if __name__ == '__main__':
    unittest.main()
