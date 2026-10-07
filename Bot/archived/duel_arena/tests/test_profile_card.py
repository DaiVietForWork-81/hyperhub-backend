"""
tests/test_profile_card.py
Kiểm thử toàn diện module ProfileCardGenerator:
- Phân loại màu sắc theo quy tắc: HT1-LT1 vàng, HT2-LT2 bạc, T3 đồng, T4 trở xuống bình thường.
- Tạo ảnh PNG 560x780 hợp lệ, có avatar fallback hoặc avatar ảnh.
"""

import asyncio
import os
import unittest
from PIL import Image

from services.profile_card import ProfileCardGenerator, get_tier_color_palette


class TestProfileCard(unittest.IsolatedAsyncioTestCase):
    def test_tier_color_palette_rules(self):
        """Kiểm tra quy tắc gán màu: Vàng, Bạc, Đồng, Bình thường."""
        # 1. HT1 - LT1: Vàng
        for t in ["HT1", "MT1", "LT1"]:
            pal = get_tier_color_palette(t)
            self.assertEqual(pal["group"], "gold")
            self.assertEqual(pal["name"], "Vàng")
            self.assertEqual(pal["text_rgb"], (255, 215, 0))

        # 2. HT2 - LT2: Bạc
        for t in ["HT2", "MT2", "LT2"]:
            pal = get_tier_color_palette(t)
            self.assertEqual(pal["group"], "silver")
            self.assertEqual(pal["name"], "Bạc")
            self.assertEqual(pal["text_rgb"], (226, 232, 240))

        # 3. T3: Đồng
        pal_t3 = get_tier_color_palette("T3")
        self.assertEqual(pal_t3["group"], "bronze")
        self.assertEqual(pal_t3["name"], "Đồng")
        self.assertEqual(pal_t3["text_rgb"], (205, 127, 50))

        # 4. T4 trở xuống: Bình thường
        for t in ["T4", "T5", "T6", "T7", "T8"]:
            pal = get_tier_color_palette(t)
            self.assertEqual(pal["group"], "normal")
            self.assertEqual(pal["name"], "Bình thường")
            self.assertEqual(pal["text_rgb"], (148, 163, 184))

    async def test_generate_profile_card_gold_silver(self):
        """Tạo thẻ hồ sơ với Freedom HT1 (Vàng) và Ranked HT2 (Bạc)."""
        card_path = await ProfileCardGenerator.generate_profile_card(
            user_id=123456789,
            display_name="Marlowww",
            avatar_url=None,
            joined_at_str="12/05/2024",
            standing=1,
            overall_pts=450.0,
            freedom_tier="HT1",
            freedom_rating=3200,
            ranked_tier="HT2",
            ranked_rating=2350,
            title="Combat Grandmaster",
            cf_handle="tourist",
            ranked_streak=12,
            ranked_max_streak=15,
            win_rate=78.5,
            total_wins=40,
            total_losses=11,
        )

        self.assertTrue(os.path.exists(card_path))
        with Image.open(card_path) as img:
            self.assertEqual(img.format, "PNG")
            self.assertEqual(img.size, (3840, 2160))

    async def test_generate_profile_card_bronze_normal(self):
        """Tạo thẻ hồ sơ với Freedom T3 (Đồng) và Ranked T5 (Bình thường)."""
        card_path = await ProfileCardGenerator.generate_profile_card(
            user_id=987654321,
            display_name="NovicePlayer",
            avatar_url=None,
            joined_at_str="01/01/2026",
            standing=45,
            overall_pts=150.0,
            freedom_tier="T3",
            freedom_rating=1750,
            ranked_tier="T5",
            ranked_rating=1300,
            title="Tier 3 Contender",
            cf_handle=None,
            ranked_streak=0,
            ranked_max_streak=3,
            win_rate=45.0,
            total_wins=9,
            total_losses=11,
        )

        self.assertTrue(os.path.exists(card_path))
        with Image.open(card_path) as img:
            self.assertEqual(img.format, "PNG")
            self.assertEqual(img.size, (3840, 2160))

    async def test_profile_slash_command_with_card_attachment(self):
        """Kiểm tra lệnh /profile trong cogs/profile.py: đính kèm thẻ ảnh và gửi phản hồi."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone
        import discord
        from cogs.profile import ProfileCog
        from database.models import User

        bot = MagicMock()
        cog = ProfileCog(bot)

        target_member = MagicMock(spec=discord.Member)
        target_member.id = 555888999
        target_member.display_name = "Marlowww"
        target_member.joined_at = datetime(2024, 5, 12, tzinfo=timezone.utc)
        target_member.roles = []
        target_member.color.value = 0
        avatar_mock = MagicMock()
        avatar_mock.url = "https://cdn.discordapp.com/embed/avatars/0.png"
        target_member.display_avatar.with_size.return_value = avatar_mock

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = target_member
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        mock_db_user = MagicMock(spec=User)
        mock_db_user.id = target_member.id
        mock_db_user.rank = "HT1"
        mock_db_user.rating = 3100
        mock_db_user.max_rating = 3150
        mock_db_user.total_submissions = 100
        mock_db_user.accepted = 90
        mock_db_user.ranked_rank = "HT1"
        mock_db_user.ranked_rating = 3050
        mock_db_user.ranked_max_rating = 3050
        mock_db_user.ranked_wins = 50
        mock_db_user.ranked_losses = 5
        mock_db_user.total_score = 5000.0
        mock_db_user.ranked_streak = 8
        mock_db_user.ranked_max_streak = 15

        with patch("cogs.profile.async_session_factory") as mock_asf:
            mock_session = AsyncMock()
            mock_asf.return_value.__aenter__.return_value = mock_session

            with patch("cogs.profile.UserRepository") as mock_user_repo_cls:
                mock_repo = MagicMock()
                mock_repo.get_or_create = AsyncMock(return_value=(mock_db_user, False))
                mock_repo.get_user_standing = AsyncMock(return_value=1)
                mock_repo.get_recent_duel_matches = AsyncMock(return_value=[])
                mock_user_repo_cls.return_value = mock_repo

                with patch("cogs.profile.CFAccountRepository") as mock_cf_repo_cls:
                    mock_cf_repo = MagicMock()
                    mock_cf_repo.get_by_discord_id = AsyncMock(return_value=None)
                    mock_cf_repo_cls.return_value = mock_cf_repo

                    await cog.profile.callback(cog, interaction, user=None)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        send_kwargs = interaction.followup.send.call_args[1]
        self.assertNotIn("embed", send_kwargs)
        self.assertIn("file", send_kwargs)
        self.assertEqual(send_kwargs["file"].filename, "profile_card.png")

    async def test_profile_slash_command_with_linked_cf_account(self):
        """Kiểm tra /profile khi người dùng đã liên kết CFAccount: không bị lỗi CFAccount object has no attribute 'rating'."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import datetime, timezone
        import discord
        from cogs.profile import ProfileCog
        from database.models import User, CFAccount

        bot = MagicMock()
        cog = ProfileCog(bot)

        target_member = MagicMock(spec=discord.Member)
        target_member.id = 111222333
        target_member.display_name = "CFMaster"
        target_member.joined_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        target_member.roles = []
        target_member.color.value = 0
        avatar_mock = MagicMock()
        avatar_mock.url = "https://cdn.discordapp.com/embed/avatars/1.png"
        target_member.display_avatar.with_size.return_value = avatar_mock

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user = target_member
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        mock_db_user = MagicMock(spec=User)
        mock_db_user.id = target_member.id
        mock_db_user.rank = "HT2"
        mock_db_user.rating = 2200
        mock_db_user.max_rating = 2300
        mock_db_user.total_submissions = 50
        mock_db_user.accepted = 45
        mock_db_user.ranked_rank = "HT2"
        mock_db_user.ranked_rating = 2250
        mock_db_user.ranked_max_rating = 2250
        mock_db_user.ranked_wins = 30
        mock_db_user.ranked_losses = 10
        mock_db_user.total_score = 3000.0
        mock_db_user.ranked_streak = 5
        mock_db_user.ranked_max_streak = 10

        mock_cf_acc = MagicMock(spec=CFAccount)
        mock_cf_acc.discord_id = target_member.id
        mock_cf_acc.cf_handle = "tourist"

        with patch("cogs.profile.async_session_factory") as mock_asf:
            mock_session = AsyncMock()
            mock_asf.return_value.__aenter__.return_value = mock_session

            with patch("cogs.profile.UserRepository") as mock_user_repo_cls:
                mock_repo = MagicMock()
                mock_repo.get_or_create = AsyncMock(return_value=(mock_db_user, False))
                mock_repo.get_user_standing = AsyncMock(return_value=2)
                mock_repo.get_recent_duel_matches = AsyncMock(return_value=[])
                mock_user_repo_cls.return_value = mock_repo

                with patch("cogs.profile.CFAccountRepository") as mock_cf_repo_cls:
                    mock_cf_repo = MagicMock()
                    mock_cf_repo.get_by_discord_id = AsyncMock(return_value=mock_cf_acc)
                    mock_cf_repo_cls.return_value = mock_cf_repo

                    with patch("cogs.profile.cf_api.get_user_info", new_callable=AsyncMock) as mock_cf_info:
                        mock_cf_info.return_value = {"rating": 3900, "maxRating": 4000, "contribution": 150}
                        await cog.profile.callback(cog, interaction, user=None)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        send_kwargs = interaction.followup.send.call_args[1]
        self.assertNotIn("embed", send_kwargs)
        self.assertIn("file", send_kwargs)
        self.assertEqual(send_kwargs["file"].filename, "profile_card.png")


    def test_avatar_accent_color_extraction(self):
        """Kiểm tra hàm _extract_avatar_accent_color phân tích đúng màu sắc nổi bật."""
        from services.profile_card import _extract_avatar_accent_color
        # 1. Ảnh đỏ rực
        img_red = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        color_red = _extract_avatar_accent_color(img_red, default_color=(100, 100, 100))
        self.assertEqual(color_red, (255, 0, 0))

        # 2. Ảnh đen tuyền (không thỏa mãn v > 0.25 và s > 0.20) -> fallback về default_color
        img_black = Image.new("RGBA", (100, 100), (10, 10, 10, 255))
        color_def = _extract_avatar_accent_color(img_black, default_color=(56, 189, 248))
        self.assertEqual(color_def, (56, 189, 248))

    async def test_generate_profile_card_with_custom_avatar_and_empty_matches(self):
        """Kiểm tra tạo thẻ 4K với avatar thực tế (test dynamic aura) và empty matches."""
        from unittest.mock import patch, AsyncMock
        # Tạo 1 avatar ảnh mẫu có màu cyan neon
        avatar_img = Image.new("RGBA", (380, 380), (6, 182, 212, 255))
        with patch.object(ProfileCardGenerator, "fetch_avatar_image", new=AsyncMock(return_value=avatar_img)):
            card_path = await ProfileCardGenerator.generate_profile_card(
                user_id=88889999,
                display_name="AuraMaster",
                avatar_url="https://example.com/avatar.png",
                joined_at_str="15/08/2024",
                standing=3,
                overall_pts=380.0,
                freedom_tier="HT1",
                freedom_rating=3050,
                ranked_tier="HT1",
                ranked_rating=3010,
                title="Overlord Champion",
                special_role="overlord",
                ranked_streak=50,
                ranked_max_streak=50,
                win_rate=95.0,
                total_wins=95,
                total_losses=5,
                recent_matches=[],
                force_refresh=True,
            )
        self.assertTrue(os.path.exists(card_path))
        with Image.open(card_path) as img:
            self.assertEqual(img.size, (3840, 2160))


if __name__ == "__main__":

    unittest.main()
