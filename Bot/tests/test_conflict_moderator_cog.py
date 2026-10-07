"""
tests/test_conflict_moderator_cog.py
Kiểm thử toàn diện tính năng:
- AI KHÔNG can thiệp trực tiếp vào việc chửi bậy/chat/war (không timeout, không xóa tin, không gửi tin vào kênh chat).
- AI gửi báo cáo kín (Staff Advisory) tới kênh Log của Mod/Staff.
- Nút bấm StaffConflictActionView chỉ cho phép Mod/Staff/Admin thực thi.
"""

import asyncio
from datetime import timedelta
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.conflict_moderator import ConflictModeratorCog, StaffConflictActionView
from services.conflict_detector import ConflictEvaluationResult


class TestConflictModeratorCog(unittest.IsolatedAsyncioTestCase):
    async def test_ai_does_not_intervene_in_user_chat(self):
        """AI tuyệt đối KHÔNG can thiệp vào kênh chat người dùng (không timeout, không delete, không send)."""
        bot = MagicMock()
        cog = ConflictModeratorCog(bot)

        guild = MagicMock(spec=discord.Guild)
        guild.id = 111222333

        # Kênh chat của thành viên
        user_channel = MagicMock(spec=discord.TextChannel)
        user_channel.id = 555666777
        user_channel.name = "general-chat"
        user_channel.category_id = cog.monitored_category_id
        user_channel.send = AsyncMock()

        # Tin nhắn của thành viên
        msg = MagicMock(spec=discord.Message)
        msg.id = 901
        msg.content = "Tao đập chết mày bây giờ!"
        msg.author.bot = False
        msg.author.id = 201
        msg.author.display_name = "UserA"
        msg.webhook_id = None
        msg.guild = guild
        msg.channel = user_channel
        msg.delete = AsyncMock()

        # Đối tượng UserA và UserB
        member_a = MagicMock(spec=discord.Member)
        member_a.id = 201
        member_a.timeout = AsyncMock()

        member_b = MagicMock(spec=discord.Member)
        member_b.id = 202
        member_b.timeout = AsyncMock()

        guild.get_member.side_effect = lambda uid: member_a if uid == 201 else member_b

        # Kênh Log của Staff
        staff_log_channel = MagicMock(spec=discord.TextChannel)
        staff_log_channel.id = 1536199276273860638
        staff_log_channel.send = AsyncMock()

        cog.staff_log_channel_id = 1536199276273860638
        guild.get_channel.side_effect = lambda cid: staff_log_channel if cid == 1536199276273860638 else user_channel

        # Mock phễu lọc và AI đánh giá trả về conflict
        fake_result = ConflictEvaluationResult(
            is_conflict=True,
            involved_users=[201, 202],
            offending_message_ids=[901, 902],
            reason="Thù địch gay gắt và đe dọa bạo lực",
            severity="high",
            ai_used=True,
            evaluation_time_ms=50.0,
        )

        with patch("services.conflict_detector.conflict_detector.fast_filter", return_value=(True, [201, 202], [], 80)):
            with patch("services.conflict_detector.conflict_detector.evaluate_conflict", return_value=fake_result):
                await cog.on_message(msg)

        # 1. XÁC MINH AI KHÔNG CAN THIỆP TRỰC TIẾP
        member_a.timeout.assert_not_called()
        member_b.timeout.assert_not_called()
        msg.delete.assert_not_called()
        user_channel.send.assert_not_called()

        # 2. XÁC MINH AI GỬI BÁO CÁO KÍN CHO STAFF QUA KÊNH LOG
        staff_log_channel.send.assert_called_once()
        call_kwargs = staff_log_channel.send.call_args[1]
        sent_embed = call_kwargs["embed"]
        sent_view = call_kwargs["view"]

        self.assertIn("STAFF ALERT", sent_embed.title)
        self.assertIn("KHÔNG CAN THIỆP", sent_embed.description)
        self.assertIsInstance(sent_view, StaffConflictActionView)

    async def test_staff_action_view_permissions_and_execution(self):
        """Kiểm tra bảng nút bấm của Staff: Chặn thành viên thường, cho phép Mod/Admin xử lý."""
        view = StaffConflictActionView(
            guild_id=111,
            channel_id=222,
            involved_users=[301, 302],
            offending_message_ids=[901, 902],
            mute_minutes=5,
        )

        # 1. Thử nghiệm với Member thường (Không có quyền)
        normal_user = MagicMock(spec=discord.Member)
        normal_user.id = 999
        normal_user.guild_permissions.moderate_members = False
        normal_user.guild_permissions.manage_messages = False
        normal_user.guild_permissions.administrator = False

        inter_normal = MagicMock(spec=discord.Interaction)
        inter_normal.user = normal_user
        inter_normal.response.send_message = AsyncMock()

        # Bấm nút Mute P1
        mute_p1_btn = view.children[0]
        await mute_p1_btn.callback(inter_normal)
        inter_normal.response.send_message.assert_called_once()
        self.assertIn("Chỉ Mod/Staff/Admin", inter_normal.response.send_message.call_args[0][0])

        # 2. Thử nghiệm với Mod (Có quyền moderate_members)
        mod_user = MagicMock(spec=discord.Member)
        mod_user.id = 888
        mod_user.mention = "<@888>"
        mod_user.guild_permissions.moderate_members = True
        mod_user.guild_permissions.manage_messages = True
        mod_user.guild_permissions.administrator = False

        target_member = MagicMock(spec=discord.Member)
        target_member.id = 301
        target_member.mention = "<@301>"
        target_member.timeout = AsyncMock()

        guild = MagicMock(spec=discord.Guild)
        guild.get_member.return_value = target_member

        inter_mod = MagicMock(spec=discord.Interaction)
        inter_mod.user = mod_user
        inter_mod.guild = guild
        inter_mod.message = MagicMock()
        inter_mod.message.embeds = [discord.Embed(title="Alert")]
        inter_mod.response.edit_message = AsyncMock()

        await mute_p1_btn.callback(inter_mod)
        # Xác nhận Mod đã timeout thành công target
        target_member.timeout.assert_called_once()
        inter_mod.response.edit_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
