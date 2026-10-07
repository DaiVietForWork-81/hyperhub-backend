"""Unit test for DiscordDirectClient in Web bridge using DISCORD_TOKEN."""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock

import aiohttp

# Import from Web
import sys
from pathlib import Path

web_dir = Path(__file__).parent.parent.parent / "Web"
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

from bridge.discord_client import DiscordDirectClient


class TestDiscordDirectClient(unittest.IsolatedAsyncioTestCase):
    """Kiểm tra DiscordDirectClient tương tác với Discord REST API."""

    async def test_discord_client_headers(self):
        client = DiscordDirectClient(token="TEST_DISCORD_TOKEN_12345")
        headers = client._get_headers()
        self.assertEqual(headers["Authorization"], "Bot TEST_DISCORD_TOKEN_12345")
        self.assertEqual(headers["Content-Type"], "application/json")
        await client.close()

    async def test_get_guild_mock(self):
        client = DiscordDirectClient(token="TEST_TOKEN")

        mock_resp_data = {
            "id": "1532265330079174697",
            "name": "HyperHub",
            "icon": "abc123456",
            "approximate_member_count": 42,
            "approximate_presence_count": 15,
            "description": "Competitive Programming Hub",
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_resp_data)

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp
        mock_session.closed = False

        client._session = mock_session

        guild = await client.get_guild(1532265330079174697)
        self.assertEqual(guild["name"], "HyperHub")
        self.assertEqual(guild["approximate_member_count"], 42)
        self.assertIn("abc123456", guild["icon_url"])

        await client.close()

    async def test_send_channel_message_mock(self):
        client = DiscordDirectClient(token="TEST_TOKEN")

        mock_resp = AsyncMock()
        mock_resp.status = 200

        mock_session = MagicMock()
        mock_session.post.return_value.__aenter__.return_value = mock_resp
        mock_session.closed = False

        client._session = mock_session

        ok = await client.send_channel_message(123456, "Hello from Web!")
        self.assertTrue(ok)
        mock_session.post.assert_called_once()

        await client.close()


if __name__ == "__main__":
    unittest.main()
