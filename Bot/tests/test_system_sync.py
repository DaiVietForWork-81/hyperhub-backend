"""Kiểm thử Hệ Thống Đồng Bộ Discord & Cập Nhật GitHub (System Sync Service)."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.system_sync_service import (
    DEFAULT_SYNC_CHANNEL_ID,
    SystemControlView,
    SystemSyncService,
    SystemUpdateView,
    system_sync_service,
)


class TestSystemSyncService(unittest.IsolatedAsyncioTestCase):
    """Bộ kiểm thử cho SystemSyncService và các Persistent Views."""

    async def test_singleton_instance(self):
        """Đảm bảo system_sync_service là instance của SystemSyncService."""
        self.assertIsInstance(system_sync_service, SystemSyncService)

    async def test_get_current_git_info(self):
        """Kiểm tra lấy thông tin Git không bị crash và trả về đúng dict format."""
        info = await system_sync_service.get_current_git_info()
        self.assertIn("hash", info)
        self.assertIn("full_hash", info)
        self.assertIn("commit_msg", info)
        self.assertIn("branch", info)
        self.assertTrue(len(info["hash"]) > 0)

    @patch("services.system_sync_service._run_git_cmd")
    async def test_check_github_update_no_update(self, mock_git):
        """Kiểm tra khi không có update mới từ GitHub."""
        mock_git.side_effect = lambda args, **kw: (
            "abc12345" if args[0] == "rev-parse" and args[1] == "HEAD"
            else "abc12345" if args[0] == "rev-parse" and args[1] == "origin/main"
            else None
        )
        service = SystemSyncService()
        res = await service.check_github_update()
        self.assertFalse(res["has_update"])
        self.assertEqual(res["local_hash"], "abc12345")
        self.assertEqual(res["remote_hash"], "abc12345")
        self.assertIsNone(service.pending_update)

    @patch("services.system_sync_service._run_git_cmd")
    async def test_check_github_update_has_update(self, mock_git):
        """Kiểm tra phát hiện commit mới từ GitHub."""
        def _git(args, **kw):
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return "1111222233334444"
            if args[0] == "rev-parse" and args[1] == "origin/main":
                return "5555666677778888"
            if args[0] == "log":
                return "• [55556666] feat: new update\n• [77778888] fix: minor bug"
            return None

        mock_git.side_effect = _git
        service = SystemSyncService()
        res = await service.check_github_update()
        self.assertTrue(res["has_update"])
        self.assertEqual(res["local_hash"], "11112222")
        self.assertEqual(res["remote_hash"], "55556666")
        self.assertEqual(len(res["commits"]), 2)
        self.assertIsNotNone(service.pending_update)

    async def test_send_startup_announcement(self):
        """Kiểm tra gửi tin nhắn khởi động và link Vercel vào kênh Discord."""
        mock_bot = MagicMock()
        mock_bot.wait_until_ready = AsyncMock()
        mock_bot.latency = 0.045
        mock_bot.user = MagicMock()
        mock_bot.user.id = 123456789
        mock_bot.user.display_avatar.url = "https://example.com/avatar.png"
        mock_bot.user.__str__ = MagicMock(return_value="HyperHub#0001")
        mock_bot.guilds = [MagicMock()]
        mock_bot.extensions = {"cogs.admin": MagicMock(), "cogs.doc_intake": MagicMock()}
        mock_bot.tree.get_commands = MagicMock(return_value=[MagicMock(), MagicMock()])

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)

        with patch("asyncio.sleep", AsyncMock()):
            sent = await system_sync_service.send_startup_announcement(mock_bot)

        self.assertTrue(sent)
        mock_channel.send.assert_called_once()
        call_kwargs = mock_channel.send.call_args.kwargs
        embed = call_kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertIn("HYPERHUB SYSTEM ONLINE", embed.title)
        self.assertIn("hyperhub-one.vercel.app", str(embed.to_dict()))

    async def test_notify_github_update(self):
        """Kiểm tra gửi thông báo cập nhật GitHub kèm nút 1-click update."""
        mock_bot = MagicMock()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)

        update_info = {
            "has_update": True,
            "local_hash": "a1b2c3d4",
            "remote_hash": "e5f6g7h8",
            "commits": ["• [e5f6g7h8] feat: add new feature"],
        }
        sent = await system_sync_service.notify_github_update(mock_bot, update_info)
        self.assertTrue(sent)
        mock_channel.send.assert_called_once()
        embed = mock_channel.send.call_args.kwargs.get("embed")
        self.assertIn("PHÁT HIỆN BẢN CẬP NHẬT MỚI", embed.title)

    async def test_views_initialization(self):
        """Đảm bảo SystemControlView và SystemUpdateView khởi tạo đúng số buttons."""
        control_view = SystemControlView()
        self.assertIsNone(control_view.timeout)
        # Có ít nhất 4 items: Link Vault, Link Admin, Check Update, Quick Reload
        self.assertGreaterEqual(len(control_view.children), 4)

        update_view = SystemUpdateView()
        self.assertIsNone(update_view.timeout)
        # Có ít nhất 3 items: Link Admin, Apply Update, Quick Reload
        self.assertGreaterEqual(len(update_view.children), 3)


if __name__ == "__main__":
    unittest.main()
