"""
Unit tests for Win Streak Bonus, Duel Cooldown (5 mins), Match Card PNG Generation,
and Custom Match 1:1 Flow (/custom_match).
"""

import asyncio
import datetime
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image

from database.database import async_session_factory, init_db
from database.models import User
from database.repositories.user_repo import UserRepository
from services.duel_problems import get_problem_by_tier
from services.duel_service import (
    DuelSession,
    MatchmakingManager,
    calculate_ranked_rating_deltas,
    get_streak_bonus_pct,
)
from services.match_card import MatchCardGenerator


class TestCustomMatchAndStreak(unittest.IsolatedAsyncioTestCase):
    """Test suite for streak bonuses, cooldowns, visual match card, and custom matches."""

    async def asyncSetUp(self):
        await init_db()

    def test_streak_bonus_calculation(self):
        """1. Kiểm tra chính xác hệ số thưởng chuỗi thắng (+2%, +5%, +10%, +15%)."""
        # Kiểm tra hàm tính %
        self.assertEqual(get_streak_bonus_pct(0), 0)
        self.assertEqual(get_streak_bonus_pct(4), 0)
        self.assertEqual(get_streak_bonus_pct(5), 2)
        self.assertEqual(get_streak_bonus_pct(9), 2)
        self.assertEqual(get_streak_bonus_pct(10), 5)
        self.assertEqual(get_streak_bonus_pct(19), 5)
        self.assertEqual(get_streak_bonus_pct(20), 10)
        self.assertEqual(get_streak_bonus_pct(29), 10)
        self.assertEqual(get_streak_bonus_pct(30), 15)
        self.assertEqual(get_streak_bonus_pct(50), 15)

        # Kiểm tra tính điểm delta khi có chuỗi
        # Chuỗi 0: Base delta (cùng rank T5, 1300 rating, 2 mạng) = 60 pts
        w0, l0, desc0 = calculate_ranked_rating_deltas("T5", "T5", 1300, 1300, winner_streak=0)
        self.assertEqual(w0, 60)
        self.assertEqual(l0, -60)
        self.assertNotIn("Chuỗi", desc0)

        # Chuỗi 5 (+2% của 60 là round(1.2) = 1 -> 61 pts)
        w5, l5, desc5 = calculate_ranked_rating_deltas("T5", "T5", 1300, 1300, winner_streak=5)
        self.assertEqual(w5, 61)
        self.assertIn("+2%", desc5)

        # Chuỗi 10 (+5% của 60 là 3 -> 63 pts)
        w10, l10, desc10 = calculate_ranked_rating_deltas("T5", "T5", 1300, 1300, winner_streak=10)
        self.assertEqual(w10, 63)
        self.assertIn("+5%", desc10)

        # Chuỗi 20 (+10% của 60 là 6 -> 66 pts)
        w20, l20, desc20 = calculate_ranked_rating_deltas("T5", "T5", 1300, 1300, winner_streak=20)
        self.assertEqual(w20, 66)
        self.assertIn("+10%", desc20)

        # Chuỗi 30 (+15% của 60 là 9 -> 69 pts)
        w30, l30, desc30 = calculate_ranked_rating_deltas("T5", "T5", 1300, 1300, winner_streak=30)
        self.assertEqual(w30, 69)
        self.assertIn("+15%", desc30)

    async def test_user_repository_streak_and_cooldown(self):
        """2. Kiểm tra CSDL lưu trữ chuỗi thắng, kỷ lục và cooldown 5 phút."""
        import random
        uid_win = random.randint(10000000, 89999999)
        uid_loss = random.randint(90000000, 99999999)

        async with async_session_factory() as session:
            repo = UserRepository(session)
            # Thắng lần 1
            u1 = await repo.update_ranked_stats(uid_win, rating_delta=60, is_winner=True)
            self.assertEqual(u1.ranked_streak, 1)
            self.assertEqual(u1.ranked_max_streak, 1)
            self.assertIsNotNone(u1.last_duel_at)

            # Thắng lần 2
            u1 = await repo.update_ranked_stats(uid_win, rating_delta=60, is_winner=True)
            self.assertEqual(u1.ranked_streak, 2)
            self.assertEqual(u1.ranked_max_streak, 2)

            # Thua -> Reset chuỗi về 0 nhưng max_streak vẫn giữ 2
            u1 = await repo.update_ranked_stats(uid_win, rating_delta=-50, is_winner=False)
            self.assertEqual(u1.ranked_streak, 0)
            self.assertEqual(u1.ranked_max_streak, 2)

            # Kiểm tra Cooldown: Vừa mới kết thúc -> Đang cooldown
            is_cd, rem_secs, rem_str = await repo.get_duel_cooldown(uid_win, cooldown_seconds=300)
            self.assertTrue(is_cd)
            self.assertGreater(rem_secs, 280)
            self.assertIn("phút", rem_str)

            # Giả lập thời gian kết thúc trước đó 6 phút (> 300s)
            u1.last_duel_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=6)
            await session.commit()

            is_cd2, rem_secs2, _ = await repo.get_duel_cooldown(uid_win, cooldown_seconds=300)
            self.assertFalse(is_cd2)
            self.assertEqual(rem_secs2, 0)

    async def test_matchmaking_cooldown_rejection(self):
        """3. Kiểm tra hàng chờ matchmaking từ chối khi đang trong 5 phút cooldown."""
        bot = MagicMock()
        mm = MatchmakingManager(bot)

        member = MagicMock()
        import random
        member.id = random.randint(20000000, 29999999)
        member.guild.id = 12345
        member.display_name = "CooldownTester"

        channel = MagicMock()
        channel.id = 54321

        # Tạo user với rating mở khóa ranked và last_duel_at vừa xong
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u, _ = await repo.get_or_create(member.id)
            u.rating = 800
            u.rank = "T6"
            u.ranked_rating = 800
            u.ranked_rank = "T6"
            u.last_duel_at = datetime.datetime.now(datetime.timezone.utc)
            await session.commit()

        # Thử tìm trận -> Phải bị từ chối do Cooldown
        ok, embed, sess = await mm.add_to_queue(member, channel)
        self.assertFalse(ok)
        self.assertIsNone(sess)
        self.assertIn("THỜI GIAN NGHỈ NGƠI", embed.title)
        self.assertIn("nghỉ ngơi tối thiểu 5 phút", embed.description)

    async def test_match_card_generation(self):
        """4. Kiểm tra module MatchCardGenerator kết xuất ảnh PNG chuẩn 4K UHD (3840x2160) hợp lệ."""
        test_dir = "duel_transcripts"
        os.makedirs(test_dir, exist_ok=True)
        code = "unittest_card"

        card_path = await MatchCardGenerator.generate_match_card(
            match_code=code,
            player1_name="AlphaCoder",
            player2_name="BetaHacker",
            p1_is_winner=True,
            p2_is_winner=False,
            is_draw=False,
            p1_rank="T4",
            p2_rank="T5",
            p1_rating=1450,
            p2_rating=1320,
            p1_delta=32.0,
            p2_delta=-28.0,
            p1_lives=2,
            p2_lives=0,
            problem_tier="T4",
            problem_name="Binary Search Tree Optimization",
            rounds_played=2,
            p1_streak=5,
            p2_streak=0,
            streak_bonus_pct=2,
            is_custom=False,
            output_dir=test_dir,
        )

        self.assertTrue(os.path.exists(card_path))

        # Kiểm tra kích thước và định dạng ảnh
        with Image.open(card_path) as img:
            self.assertEqual(img.size, (3840, 2160))
            self.assertEqual(img.format, "PNG")

        # Kiểm tra ảnh trận Giao Hữu (Custom Match)
        custom_code = "unittest_custom_card"
        custom_card_path = await MatchCardGenerator.generate_match_card(
            match_code=custom_code,
            player1_name="Friend1",
            player2_name="Friend2",
            p1_is_winner=False,
            p2_is_winner=True,
            is_draw=False,
            p1_rank="T7",
            p2_rank="T7",
            p1_rating=500,
            p2_rating=520,
            p1_delta=0.0,
            p2_delta=0.0,
            p1_lives=1,
            p2_lives=2,
            problem_tier="T7",
            problem_name="Simple Array Sum",
            rounds_played=1,
            is_custom=True,
            output_dir=test_dir,
        )
        self.assertTrue(os.path.exists(custom_card_path))
        with Image.open(custom_card_path) as cimg:
            self.assertEqual(cimg.size, (3840, 2160))
            self.assertEqual(cimg.format, "PNG")

    def test_get_problem_by_tier(self):
        """5. Kiểm tra hàm get_problem_by_tier trả về đúng tier yêu cầu."""
        tiers_to_test = ["T8", "T7", "T6", "T5", "T4", "T3"]
        for t in tiers_to_test:
            prob = get_problem_by_tier(t)
            self.assertIsNotNone(prob)
            self.assertEqual(prob.tier.upper(), t.upper())

    async def test_custom_match_session_flow(self):
        """6. Kiểm tra luồng DuelSession ở chế độ Custom Match (không đổi Elo, đề đúng tier)."""
        bot = MagicMock()
        guild = MagicMock()
        import random
        p1 = MagicMock(spec=["id", "mention", "display_name", "display_avatar"])
        p1.id = random.randint(30000000, 39999999)
        p1.display_name = "PlayerA"
        p1.mention = f"<@{p1.id}>"
        p1.display_avatar.url = "https://example.com/a.png"

        p2 = MagicMock(spec=["id", "mention", "display_name", "display_avatar"])
        p2.id = random.randint(40000000, 49999999)
        p2.display_name = "PlayerB"
        p2.mention = f"<@{p2.id}>"
        p2.display_avatar.url = "https://example.com/b.png"

        session = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T5",
            p1_ranked_rating=1300,
            p2_ranked_rank="T6",
            p2_ranked_rating=1100,
            is_custom_match=True,
            custom_tier="T4",
        )

        self.assertTrue(session.is_custom_match)
        self.assertEqual(session.custom_tier, "T4")

        # Mock kênh Discord
        channel = AsyncMock()
        channel.id = 999111
        session.channel = channel

        # Khởi động round -> Đề bài phải là Tier T4
        await session._start_round(prep_delay=False)
        self.assertIsNotNone(session.current_problem)
        self.assertEqual(session.current_problem.tier, "T4")

        # Giả lập kết thúc trận đấu giao hữu (P1 thắng)
        session.p1_lives = 2
        session.p2_lives = 0

        # Lưu rating ban đầu trong DB
        async with async_session_factory() as db_sess:
            repo = UserRepository(db_sess)
            await repo.get_or_create(p1.id)
            await repo.get_or_create(p2.id)

        # Chạy _finish_match
        with patch.object(session, "_delayed_cleanup", return_value=None):
            await session._finish_match()

        # Kiểm tra thông báo hiển thị "GIAO HỮU" và rating không đổi
        channel.send.assert_called()
        embed_calls = [
            c[1]["embed"] for c in channel.send.call_args_list if "embed" in c[1]
        ]
        self.assertTrue(len(embed_calls) > 0)
        sent_embed = embed_calls[0]
        self.assertIn("KẾT QUẢ TRẬN GIAO HỮU", sent_embed.title)
        self.assertIn("Giữ nguyên", sent_embed.description)

    async def test_custom_match_challenge_view_flow(self):
        """7. Kiểm tra tương tác View xác nhận thách đấu (Accept & Decline qua DM)."""
        from cogs.ranked_duel import CustomMatchChallengeView

        bot = MagicMock()
        mm = MatchmakingManager(bot)

        challenger = MagicMock(spec=["id", "mention", "guild", "send"])
        challenger.id = 55551111
        challenger.mention = "<@55551111>"
        challenger.guild = MagicMock()
        challenger.send = AsyncMock()

        target = MagicMock(spec=["id", "mention", "display_name", "send"])
        target.id = 55552222
        target.mention = "<@55552222>"
        target.display_name = "TargetFriend"
        target.send = AsyncMock()

        view = CustomMatchChallengeView(
            matchmaker=mm,
            challenger=challenger,
            target_member=target,
            tier="T5",
        )

        # 1. Kiểm tra interaction_check: người khác bấm -> từ chối
        wrong_inter = AsyncMock()
        wrong_inter.user.id = 99999999
        check_res = await view.interaction_check(wrong_inter)
        self.assertFalse(check_res)
        wrong_inter.response.send_message.assert_called_with(
            "❌ Lời thách đấu này không dành cho bạn!", ephemeral=True
        )

        # 2. Kiểm tra bấm Từ Chối (Decline)
        decline_inter = AsyncMock()
        decline_inter.user.id = target.id
        await view.children[1].callback(decline_inter)
        decline_inter.response.edit_message.assert_called_once()
        self.assertIn("từ chối", decline_inter.response.edit_message.call_args[1]["content"])
        challenger.send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
