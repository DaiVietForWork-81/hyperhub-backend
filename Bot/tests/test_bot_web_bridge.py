"""Unit tests for Bot & Web API Bridge (Dual-Channel connection)."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from config.settings import settings
from services.api_bridge import BotAPIBridge


class TestBotAPIBridge(AioHTTPTestCase):
    """Kiểm tra các endpoint RESTful của BotAPIBridge."""

    async def get_application(self):
        # Mock Discord Bot instance
        self.mock_bot = MagicMock()
        self.mock_bot.latency = 0.025
        self.mock_bot.user = MagicMock()
        self.mock_bot.user.id = 123456789
        self.mock_bot.user.__str__.return_value = "HyperHub#0594"
        self.mock_bot.guilds = [MagicMock()]

        bridge = BotAPIBridge(self.mock_bot)
        return bridge.app

    @unittest_run_loop
    async def test_get_status_endpoint(self):
        """Kiểm tra GET /api/status trả về đúng thông tin bot."""
        resp = await self.client.request("GET", "/api/status")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["bot_user"], "HyperHub#0594")
        self.assertEqual(data["guilds_count"], 1)
        self.assertGreaterEqual(data["ping_ms"], 0)

    @unittest_run_loop
    async def test_auth_middleware_blocks_invalid_post(self):
        """Kiểm tra POST /api/notify bị từ chối nếu không có token hợp lệ."""
        payload = {"channel_id": 111, "message": "hello"}
        # Không có header auth
        resp = await self.client.request("POST", "/api/notify", json=payload)
        self.assertEqual(resp.status, 401)

        # Sai token
        headers = {"Authorization": "Bearer wrong_token"}
        resp_wrong = await self.client.request("POST", "/api/notify", json=payload, headers=headers)
        self.assertEqual(resp_wrong.status, 401)

    @unittest_run_loop
    async def test_auth_middleware_accepts_valid_token(self):
        """Kiểm tra POST /api/notify chấp nhận token đúng."""
        headers = {"Authorization": f"Bearer {settings.BOT_API_SECRET}"}
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        self.mock_bot.get_channel.return_value = mock_channel

        payload = {"channel_id": 999999, "message": "Test message from web"}
        resp = await self.client.request("POST", "/api/notify", json=payload, headers=headers)
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data.get("success"))
        # Chấp nhận allowed_mentions=none() (chống mass-ping @everyone/@here)
        self.assertEqual(mock_channel.send.call_count, 1)
        _args, _kwargs = mock_channel.send.call_args
        self.assertEqual(_args[0], "Test message from web")
        self.assertIn("allowed_mentions", _kwargs)

    @unittest_run_loop
    async def test_request_exam_requires_server_member(self):
        """GET /api/documents/request_exam: chặn khi không token / token chết / chưa verify / ngoài server."""
        from unittest.mock import AsyncMock as _AM

        # 1. Không token -> 401
        resp = await self.client.request("GET", "/api/documents/request_exam")
        self.assertEqual(resp.status, 401)
        data = await resp.json()
        self.assertEqual(data.get("reason"), "no_token")

        # Chuẩn bị guild mock: không có member nào
        guild = MagicMock()
        guild.get_member.return_value = None
        guild.fetch_member = _AM(side_effect=Exception("not found"))
        self.mock_bot.get_guild.return_value = guild
        self.mock_bot.guilds = [guild]

        # 2. Token chết (Discord từ chối) -> 401
        with patch.object(BotAPIBridge, "_verify_discord_bearer_token", new=_AM(return_value=None)):
            resp = await self.client.request(
                "GET", "/api/documents/request_exam",
                headers={"Authorization": "Bearer dead_token"},
            )
            self.assertEqual(resp.status, 401)

        # 3. Chưa verify email -> 403 unverified
        with patch.object(
            BotAPIBridge, "_verify_discord_bearer_token",
            new=_AM(return_value={"id": "111", "username": "u", "verified": False}),
        ):
            resp = await self.client.request(
                "GET", "/api/documents/request_exam",
                headers={"Authorization": "Bearer unverified_token"},
            )
            self.assertEqual(resp.status, 403)
            data = await resp.json()
            self.assertEqual(data.get("reason"), "unverified")

        # 4. Verified nhưng ngoài server -> 403 not_member + guild_id
        with patch.object(
            BotAPIBridge, "_verify_discord_bearer_token",
            new=_AM(return_value={"id": "222", "username": "u2", "verified": True}),
        ):
            resp = await self.client.request(
                "GET", "/api/documents/request_exam",
                headers={"Authorization": "Bearer outsider_token"},
            )
            self.assertEqual(resp.status, 403)
            data = await resp.json()
            self.assertEqual(data.get("reason"), "not_member")
            self.assertTrue(data.get("guild_id"))

    @unittest_run_loop
    async def test_admin_input_validation(self):
        """Kiểm tra backend trả 400 (không 500) khi admin gửi dữ liệu sai định dạng."""
        headers = {"Authorization": f"Bearer {settings.BOT_API_SECRET}"}

        # Ban với delete_message_days không phải số
        resp = await self.client.request(
            "POST", "/api/admin/ban",
            json={"user_id": "123", "delete_message_days": "abc"},
            headers=headers,
        )
        self.assertEqual(resp.status, 400)

        # Timeout với duration_seconds không phải số
        mock_guild = MagicMock()
        mock_member = MagicMock()
        mock_member.timeout = AsyncMock()
        mock_guild.get_member.return_value = mock_member
        self.mock_bot.get_guild.return_value = mock_guild
        self.mock_bot.guilds = [mock_guild]
        resp2 = await self.client.request(
            "POST", "/api/admin/timeout",
            json={"user_id": "123", "action": "mute", "duration_seconds": "xyz"},
            headers=headers,
        )
        self.assertEqual(resp2.status, 400)

        # Notify với channel_id không phải số
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        self.mock_bot.get_channel.return_value = mock_channel
        resp3 = await self.client.request(
            "POST", "/api/notify",
            json={"channel_id": "not-a-number", "message": "hi"},
            headers=headers,
        )
        self.assertEqual(resp3.status, 400)

    @unittest_run_loop
    async def test_get_active_duels_endpoint(self):
        resp = await self.client.request("GET", "/api/duels/active")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("active_count", data)
        self.assertIn("duels", data)


class TestWebBotClientFallback(unittest.IsolatedAsyncioTestCase):
    """Kiểm tra BotBridgeClient cơ chế fallback CSDL."""

    async def test_web_bridge_client_offline_fallback(self):
        """Kiểm tra khi Bot offline, client tự động trả về offline hoặc fallback CSDL an toàn."""
        import sys
        from pathlib import Path
        web_dir = Path(__file__).parent.parent.parent / "Web"
        if str(web_dir) not in sys.path:
            sys.path.insert(0, str(web_dir))

        from bridge.bot_client import BotBridgeClient
        client = BotBridgeClient(base_url="http://127.0.0.1:59999")  # Port không tồn tại

        status = await client.get_bot_status()
        self.assertEqual(status["status"], "offline")

        # Fallback query DB trực tiếp
        lb = await client.get_leaderboard(mode="ranked", limit=5)
        self.assertIn("leaderboard", lb)

        await client.close()


if __name__ == "__main__":
    unittest.main()
