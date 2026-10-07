"""Kiểm thử tự động cho Slash Command /check trong cogs/check_token.py."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

try:
    from not_finished.exam_generator.cogs.check_token import CheckTokenCog
    from not_finished.exam_generator.services.user_token_service import user_token_service
except ImportError:
    from cogs.check_token import CheckTokenCog
    from services.user_token_service import user_token_service


class TestCheckTokenCog:
    """Kiểm tra phản hồi của lệnh /check và định dạng embed."""

    @pytest.mark.asyncio
    async def test_check_slash_command_execution(self):
        """Kiểm tra lệnh /check trả về embed đầy đủ thông tin token, tier, progress bar."""
        bot_mock = MagicMock()
        cog = CheckTokenCog(bot_mock)

        # Mock interaction & user
        interaction = MagicMock(spec=discord.Interaction)
        interaction.response = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        user_mock = MagicMock(spec=discord.Member)
        user_mock.id = 1234567890
        user_mock.display_name = "TestStudent"
        user_mock.display_avatar = MagicMock()
        user_mock.display_avatar.url = "https://example.com/avatar.png"
        user_mock.roles = []

        interaction.user = user_mock
        interaction.guild = MagicMock()
        interaction.guild.get_member.return_value = user_mock

        mock_token_data = {
            "discord_id": 1234567890,
            "tier": "Pro",
            "tier_name": "Hyper Pro",
            "tier_icon": "🟣",
            "color": 0x9B59B6,
            "daily_tokens": 700,
            "used_tokens_today": 350,
            "remaining_tokens": 350,
            "is_unlimited": False,
            "total_generated": 3,
            "allow_to_length": True,
            "allow_max_ultra_mode": True,
        }

        with patch.object(
            user_token_service, "get_or_sync_user_token", new_callable=AsyncMock
        ) as mock_get_token, patch.object(
            user_token_service, "get_recent_jobs_by_user", new_callable=AsyncMock
        ) as mock_get_jobs:

            mock_get_token.return_value = mock_token_data
            mock_get_jobs.return_value = []

            await cog.check.callback(cog, interaction, user=None)

            interaction.response.defer.assert_awaited_once()
            interaction.followup.send.assert_awaited_once()

            sent_call_args = interaction.followup.send.call_args
            assert "embed" in sent_call_args.kwargs

            embed: discord.Embed = sent_call_args.kwargs["embed"]
            assert "Hyper Pro" in embed.title or "Hyper Pro" in str(embed.to_dict())
            assert "🟣" in embed.title

            # Kiểm tra các field hiển thị
            field_names = [f.name for f in embed.fields]
            assert any("Gói Thành Viên" in n for n in field_names)
            assert any("Hạn Mức" in n for n in field_names)
            assert any("Token Khả Dụng" in n for n in field_names)
            assert any("Tiến Trình" in n for n in field_names)
            assert any("Làm Mới" in n for n in field_names)
