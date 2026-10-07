"""Unit tests for Ranked 1:1 Duel Arena (Matchmaking, 2 Hearts Life System, Problems, and Scoring)."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from config.settings import settings
from database.database import async_session_factory, close_db_engine, init_db
from database.repositories.user_repo import UserRepository
from services.duel_problems import PROBLEM_BANK, get_problem_for_match
from services.duel_service import (
    DuelSession,
    MatchmakingManager,
    calculate_ranked_rating_deltas,
)
from services.rank import get_rank_by_rating


class TestRankedDuelSystem(unittest.IsolatedAsyncioTestCase):
    """Test suite for Ranked 1:1 Duel features."""

    async def asyncSetUp(self):
        await init_db()
        # Tạo 2 users test
        self.p1_id = 999111222
        self.p2_id = 999333444
        self.p3_low_id = 999555666

        async with async_session_factory() as session:
            from sqlalchemy import delete
            from database.models import User, DuelMatch

            await session.execute(
                delete(User).where(
                    User.discord_id.in_([self.p1_id, self.p2_id, self.p3_low_id])
                )
            )
            await session.execute(
                delete(DuelMatch).where(
                    DuelMatch.player1_id.in_([self.p1_id, self.p2_id])
                    | DuelMatch.player2_id.in_([self.p1_id, self.p2_id])
                )
            )
            await session.commit()

        async with async_session_factory() as session:
            repo = UserRepository(session)
            u1, _ = await repo.get_or_create(self.p1_id)
            u1.rating = 800  # T6 Freedom (Đủ điều kiện >= 400 pts)
            u1.rank = "T6"
            u1.ranked_rating = 100
            u1.ranked_rank = "T8"
            u1.ranked_wins = 0
            u1.ranked_losses = 0
            u1.ranked_draws = 0

            u2, _ = await repo.get_or_create(self.p2_id)
            u2.rating = 600  # T7 Freedom (Đủ điều kiện >= 400 pts)
            u2.rank = "T7"
            u2.ranked_rating = 450
            u2.ranked_rank = "T7"
            u2.ranked_wins = 0
            u2.ranked_losses = 0
            u2.ranked_draws = 0

            u3, _ = await repo.get_or_create(self.p3_low_id)
            u3.rating = 200  # T8 Freedom (< 400 pts -> Chưa mở khóa)
            u3.rank = "T8"
            u3.ranked_rating = 0
            u3.ranked_rank = "T8"
            u3.ranked_wins = 0
            u3.ranked_losses = 0
            u3.ranked_draws = 0

            await session.commit()

    async def asyncTearDown(self):
        # Dọn dẹp sạch sẽ dữ liệu test
        async with async_session_factory() as session:
            from sqlalchemy import delete
            from database.models import User, DuelMatch

            await session.execute(
                delete(User).where(
                    User.discord_id.in_([self.p1_id, self.p2_id, self.p3_low_id])
                )
            )
            await session.execute(
                delete(DuelMatch).where(
                    DuelMatch.player1_id.in_([self.p1_id, self.p2_id])
                    | DuelMatch.player2_id.in_([self.p1_id, self.p2_id])
                )
            )
            await session.commit()

    def test_problem_bank_and_generator(self):
        """Kiểm tra ngân hàng đề bài và bộ sinh đề theo từng bậc Tier (Tier càng cao bài càng khó hơn)."""
        self.assertGreaterEqual(len(PROBLEM_BANK), 12)

        # Test sinh đề chính xác theo từng bậc Tier
        prob_t8 = get_problem_for_match("T8", "T8")
        self.assertEqual(prob_t8.tier, "T8")
        self.assertEqual(prob_t8.division, "Div. 4")
        self.assertGreaterEqual(prob_t8.time_limit_minutes, 10)

        prob_t7 = get_problem_for_match("T7", "T7")
        self.assertEqual(prob_t7.tier, "T7")
        self.assertEqual(prob_t7.division, "Div. 4")

        prob_t6 = get_problem_for_match("T6", "T6")
        self.assertEqual(prob_t6.tier, "T6")

        prob_t5 = get_problem_for_match("T5", "T5")
        self.assertEqual(prob_t5.tier, "T5")
        self.assertEqual(prob_t5.division, "Div. 3")

        prob_t4 = get_problem_for_match("T4", "T4")
        self.assertEqual(prob_t4.tier, "T4")
        self.assertEqual(prob_t4.division, "Div. 3")

        prob_t3 = get_problem_for_match("T3", "T3")
        self.assertEqual(prob_t3.tier, "T3")
        self.assertEqual(prob_t3.division, "Div. 3")

        prob_lt2 = get_problem_for_match("LT2", "LT2")
        self.assertEqual(prob_lt2.tier, "LT2")
        self.assertEqual(prob_lt2.division, "Div. 2")

        prob_mt2 = get_problem_for_match("MT2", "MT2")
        self.assertEqual(prob_mt2.tier, "MT2")
        self.assertEqual(prob_mt2.division, "Div. 2")

        prob_ht2 = get_problem_for_match("HT2", "HT2")
        self.assertEqual(prob_ht2.tier, "HT2")
        self.assertEqual(prob_ht2.division, "Div. 2")

        prob_lt1 = get_problem_for_match("LT1", "LT1")
        self.assertEqual(prob_lt1.tier, "LT1")
        self.assertEqual(prob_lt1.division, "Div. 1")

        prob_mt1 = get_problem_for_match("MT1", "MT1")
        self.assertEqual(prob_mt1.tier, "MT1")
        self.assertEqual(prob_mt1.division, "Div. 1")

        prob_ht1 = get_problem_for_match("HT1", "HT1")
        self.assertEqual(prob_ht1.tier, "HT1")
        self.assertEqual(prob_ht1.division, "Div. 1")
        self.assertGreaterEqual(prob_ht1.time_limit_minutes, 15)

        # Test render embeds (tách 3 Rich Embeds gọn gàng, không tiêu đề rườm rà)
        embeds = prob_t8.render_embeds()
        self.assertEqual(len(embeds), 3)
        # Embed 1: Tên bài & Thông tin (không có [1/3], có hướng dẫn đuôi file)
        self.assertIn(prob_t8.name.upper(), embeds[0].title)
        self.assertIn(".py", embeds[0].description)
        self.assertIn(".cpp", embeds[0].description)
        self.assertNotIn("💡 Gợi ý", embeds[0].description)
        self.assertNotIn("[1/3]", str(embeds[0].title))
        # Embed 2: Đề bài (không có [2/3])
        self.assertIn(prob_t8.statement[:20], embeds[1].description)
        self.assertNotIn("[2/3]", str(embeds[1].title))
        # Embed 3: Input, Output, Ràng buộc, Ví dụ (không có [3/3])
        self.assertIn("Input Format", embeds[2].description)
        self.assertIn("Output Format", embeds[2].description)
        self.assertNotIn("[3/3]", str(embeds[2].title))

        # Kiểm tra không có ký hiệu math LaTeX thô $...$ trong statement của toàn bộ ngân hàng đề
        for p in PROBLEM_BANK:
            self.assertNotIn("$", p.statement, f"Bài {p.id} còn chứa ký hiệu $ thô trong statement!")
            self.assertNotIn("$", p.constraints, f"Bài {p.id} còn chứa ký hiệu $ thô trong constraints!")
            self.assertNotIn("$", p.input_format, f"Bài {p.id} còn chứa ký hiệu $ thô trong input_format!")

        # Kiểm tra tính chất: Tier càng cao, thời gian làm bài và code size tăng dần
        self.assertLessEqual(prob_t8.time_limit_minutes, prob_t6.time_limit_minutes)
        self.assertLessEqual(prob_t6.time_limit_minutes, prob_t5.time_limit_minutes)
        self.assertLessEqual(prob_t5.time_limit_minutes, prob_t3.time_limit_minutes)
        self.assertLessEqual(prob_t3.time_limit_minutes, prob_lt2.time_limit_minutes)
        self.assertLessEqual(prob_lt2.time_limit_minutes, prob_ht2.time_limit_minutes)
        self.assertLessEqual(prob_ht2.time_limit_minutes, prob_lt1.time_limit_minutes)
        self.assertLessEqual(prob_lt1.time_limit_minutes, prob_ht1.time_limit_minutes)

        self.assertLessEqual(prob_t8.max_code_size_kb, prob_t5.max_code_size_kb)
        self.assertLessEqual(prob_t5.max_code_size_kb, prob_lt2.max_code_size_kb)
        self.assertLessEqual(prob_lt2.max_code_size_kb, prob_ht1.max_code_size_kb)

    def test_ranked_rating_deltas_option_b(self):
        """Kiểm tra tính điểm Dynamic Elo Option B & Performance Match Length (Cùng Tier, Hơn Tier, Kém Tier, Rating Bonus, Stamina 5-15 pts)."""
        # 1. Cùng Tier, Rating bằng nhau (T4 1500 vs T4 1500, 2 chặng)
        w_delta, l_delta, _ = calculate_ranked_rating_deltas("T4", "T4", 1500, 1500, winner_lives=2, rounds_played=2)
        self.assertEqual(w_delta, 60)
        self.assertEqual(l_delta, -60)

        # 1 mạng (75%)
        w_delta_1, l_delta_1, _ = calculate_ranked_rating_deltas("T4", "T4", 1500, 1500, winner_lives=1, rounds_played=2)
        self.assertEqual(w_delta_1, 45)  # 60 * 0.75 = 45
        self.assertEqual(l_delta_1, -60)

        # 2. Kèo dưới thắng Kèo trên (T5 1300 thắng T4 1500 -> diff = +200 -> bonus = +8)
        w_delta, l_delta, _ = calculate_ranked_rating_deltas("T5", "T4", 1300, 1500, winner_lives=2, rounds_played=2)
        self.assertEqual(w_delta, 88)  # 80 + 8 = 88
        self.assertEqual(l_delta, -88) # -(80 + 8) = -88

        # 3. Kèo trên thắng Kèo dưới (T4 1500 thắng T5 1300 -> diff = -200 -> bonus = -8)
        w_delta, l_delta, _ = calculate_ranked_rating_deltas("T4", "T5", 1500, 1300, winner_lives=2, rounds_played=2)
        self.assertEqual(w_delta, 42)  # 50 - 8 = 42
        self.assertEqual(l_delta, -42) # -(50 - 8) = -42

        # 4. Performance Modifier: Kèo dưới kéo dài 4 chặng (+10 pts stamina)
        w_delta_long, l_delta_long, details = calculate_ranked_rating_deltas("T5", "T4", 1300, 1500, winner_lives=2, rounds_played=4)
        self.assertEqual(w_delta_long, 98)  # 88 + 10 = 98
        self.assertEqual(l_delta_long, -98)
        self.assertIn("10 pts kiên cường", details)

        # 5. Performance Modifier: Kèo trên thắng chật vật sau 4 chặng (-10 pts stamina)
        w_delta_fav_long, l_delta_fav_long, details_fav = calculate_ranked_rating_deltas("T4", "T5", 1500, 1300, winner_lives=2, rounds_played=4)
        self.assertEqual(w_delta_fav_long, 32)  # 42 - 10 = 32
        self.assertEqual(l_delta_fav_long, -32)
        self.assertIn("-10 pts chật vật", details_fav)

    async def test_matchmaking_unlock_condition(self):
        """Kiểm tra điều kiện mở khóa Ranked 1:1 (Phải >= T7 Freedom)."""
        bot = MagicMock()
        mm = MatchmakingManager(bot)

        guild = MagicMock()
        channel = MagicMock()

        # User 3 có Rating Freedom 200 (< 400 pts) -> Bị từ chối
        member3 = MagicMock()
        member3.id = self.p3_low_id
        member3.guild = guild

        ok, msg, session = await mm.add_to_queue(member3, channel)
        self.assertFalse(ok)
        title = msg.title if hasattr(msg, "title") else str(msg)
        self.assertIn("ĐIỀU KIỆN MỞ KHÓA", title)
        self.assertEqual(len(mm.queue), 0)

    async def test_matchmaking_pairing_rule(self):
        """Kiểm tra quy tắc ghép trận (chênh lệch <= 1 Tier)."""
        bot = MagicMock()
        mm = MatchmakingManager(bot)

        guild = MagicMock()
        channel = MagicMock()

        # P1 (Ranked T8) vào queue
        m1 = MagicMock()
        m1.id = self.p1_id
        m1.guild = guild

        # P2 (Ranked T7) vào queue -> T8 vs T7 (chênh 1 Tier) -> Ghép thành công!
        m2 = MagicMock()
        m2.id = self.p2_id
        m2.guild = guild

        guild.get_member.side_effect = lambda uid: m1 if uid == self.p1_id else m2

        # P1 vào queue
        ok1, msg1, s1 = await mm.add_to_queue(m1, channel)
        self.assertTrue(ok1)
        self.assertIsNone(s1)
        self.assertEqual(len(mm.queue), 1)

        # Mock create_text_channel
        created_channel = MagicMock()
        created_channel.id = 123456789
        created_channel.send = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=created_channel)

        # P2 vào queue -> Ghép trận
        ok2, msg2, s2 = await mm.add_to_queue(m2, channel)
        self.assertTrue(ok2)
        self.assertIsNotNone(s2)
        title2 = msg2.title if hasattr(msg2, "title") else str(msg2)
        self.assertIn("GHÉP TRẬN THÀNH CÔNG", title2)
        self.assertEqual(len(mm.queue), 0)  # Cả 2 đã rời queue

    async def test_scoring_and_life_deduction(self):
        """Kiểm tra cơ chế 2 mạng và công thức tính điểm (100% khi còn 2 mạng, 75% khi còn 1 mạng, thua -80 pts)."""
        bot = MagicMock()
        guild = MagicMock()
        guild.get_role.return_value = None
        p1 = MagicMock()
        p1.id = self.p1_id
        p1.display_name = "Player1"
        p1.mention = "<@999111222>"
        p1.roles = []
        p1.remove_roles = AsyncMock()
        p1.add_roles = AsyncMock()

        p2 = MagicMock()
        p2.id = self.p2_id
        p2.display_name = "Player2"
        p2.mention = "<@999333444>"
        p2.roles = []
        p2.remove_roles = AsyncMock()
        p2.add_roles = AsyncMock()

        channel = MagicMock()
        channel.id = 777888999
        channel.send = AsyncMock()
        channel.delete = AsyncMock()

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=100,
            p2_ranked_rank="T7",
            p2_ranked_rating=450,
        )
        duel.channel = channel
        duel.current_problem = PROBLEM_BANK[0]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            # Vòng 1: Hòa (P1 100%, P2 95% -> cách biệt 5% <= 10%) -> Không ai mất mạng
            duel.round_submissions[p1.id] = {"score": 100.0, "passed": 5, "total": 5}
            duel.round_submissions[p2.id] = {"score": 95.0, "passed": 5, "total": 5}
            await duel._evaluate_round(timeout=False)
            self.assertEqual(duel.p1_lives, 2)
            self.assertEqual(duel.p2_lives, 2)

            # Vòng 2: P1 100%, P2 50% -> P2 mất 1 mạng (còn 1)
            duel.round_submissions[p1.id] = {"score": 100.0, "passed": 5, "total": 5}
            duel.round_submissions[p2.id] = {"score": 50.0, "passed": 2, "total": 5}
            await duel._evaluate_round(timeout=False)
            self.assertEqual(duel.p1_lives, 2)
            self.assertEqual(duel.p2_lives, 1)

            # Vòng 3: P1 100%, P2 0% -> P2 mất mạng thứ 2 (còn 0 mạng) -> Game Over!
            duel.round_submissions[p1.id] = {"score": 100.0, "passed": 5, "total": 5}
            duel.round_submissions[p2.id] = {"score": 0.0, "passed": 0, "total": 5}

            # Mock broadcast_winner to avoid network call
            duel._broadcast_winner = AsyncMock()

            # Đánh giá vòng 3
            await duel._evaluate_round(timeout=False)
            self.assertEqual(duel.p1_lives, 2)
            self.assertEqual(duel.p2_lives, 0)
            self.assertFalse(duel.is_active)

        # Kiểm tra điểm trong CSDL theo Option B (Dynamic Elo):
        # P1 (T8, 100 pts) đánh bại P2 (T7, 450 pts - Kèo trên hơn 350 pts):
        # diff = 350 pts -> bonus = 350 // 25 = +14 pts
        # Winner (2 mạng): Base Win 80 + 14 = +94 pts (100 -> 194)
        # Loser: -(Base Loss 80 + 14) = -94 pts (450 -> 356)
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u1 = await repo.get_by_id(self.p1_id)
            u2 = await repo.get_by_id(self.p2_id)

            # Trận đấu diễn ra 3 chặng -> extra_rounds = 1 -> stamina = +5 pts
            # Base 80 + diff bonus 14 + stamina 5 = +99 pts (100 -> 199)
            # Loser: -(80 + 14 + 5) = -99 pts (450 -> 351)
            self.assertEqual(u1.ranked_rating, 199)
            self.assertEqual(u1.ranked_wins, 1)
            self.assertEqual(u2.ranked_rating, 351)
            self.assertEqual(u2.ranked_losses, 1)

    async def test_dual_embeds_leaderboard(self):
        """Kiểm tra xuất 2 Embeds song song cho Leaderboard (Freedom & Ranked 1:1) và chu kỳ 45 phút."""
        from cogs.leaderboard import RankChannelLeaderboardView, AUTO_UPDATE_INTERVAL

        self.assertEqual(AUTO_UPDATE_INTERVAL, 45 * 60)

        bot = MagicMock()
        view = RankChannelLeaderboardView(bot=bot, page=1)
        embed_freedom, embed_ranked = await view.render_embeds()

        self.assertIn("FREEDOM MODE", embed_freedom.title)
        self.assertIn("RANKED 1:1", embed_ranked.title)
        self.assertIn("45 phút", embed_freedom.footer.text)
        self.assertIn("45 phút", embed_ranked.footer.text)

    async def test_close_and_surrender_flow(self):
        """Kiểm tra luồng lệnh .close và cơ chế xác nhận đầu hàng."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock()
        p1.id = self.p1_id
        p1.mention = "<@999111222>"
        p2 = MagicMock()
        p2.id = self.p2_id
        p2.mention = "<@999333444>"

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=100,
            p2_ranked_rank="T7",
            p2_ranked_rating=450,
        )
        duel.channel = MagicMock()
        duel.channel.send = AsyncMock()
        duel._finish_match = AsyncMock()

        # Thử gọi handle_surrender cho Player 2
        await duel.handle_surrender(p2)
        self.assertEqual(duel.p2_lives, 0)
        self.assertEqual(duel.p1_lives, 2)
        duel._finish_match.assert_called_once()

    async def test_list_command_history(self):
        """Kiểm tra lệnh .list xuất danh sách các bài/chặng đã làm."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock()
        p1.id = self.p1_id
        p1.mention = "<@999111222>"
        p1.display_name = "Player1"
        p2 = MagicMock()
        p2.id = self.p2_id
        p2.mention = "<@999333444>"
        p2.display_name = "Player2"

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=100,
            p2_ranked_rank="T7",
            p2_ranked_rating=450,
        )
        duel.channel = MagicMock()
        duel.channel.send = AsyncMock()

        msg = MagicMock()
        msg.author = p1
        await duel.handle_list_command(msg)
        duel.channel.send.assert_called_once()

    async def test_test_command_owner_fast_win(self):
        """Kiểm tra lệnh .test chỉ cho phép Owner ID đóng trận thắng test."""
        from config.settings import settings

        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock()
        p1.id = self.p1_id
        p1.mention = "<@999111222>"
        p2 = MagicMock()
        p2.id = self.p2_id
        p2.mention = "<@999333444>"

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=100,
            p2_ranked_rank="T7",
            p2_ranked_rating=450,
        )
        duel.channel = MagicMock()
        duel.channel.send = AsyncMock()
        duel._finish_match = AsyncMock()

        # Non-owner dùng .test -> Bị từ chối
        non_owner_msg = MagicMock()
        non_owner_msg.author.id = 111222333444
        non_owner_msg.author.mention = "<@111222333444>"
        await duel.handle_test_command(non_owner_msg)
        duel._finish_match.assert_not_called()

        # Owner dùng .test -> Đóng trận, P1 thắng
        owner_msg = MagicMock()
        owner_msg.author.id = settings.OWNER_ID
        owner_msg.author.mention = f"<@{settings.OWNER_ID}>"
        await duel.handle_test_command(owner_msg)
        duel._finish_match.assert_called_once()
        self.assertEqual(duel.p2_lives, 0)
        self.assertGreater(duel.p1_lives, 0)

    async def test_owner_excluded_from_leaderboard(self):
        """Kiểm tra Owner ID không nằm trong bảng xếp hạng get_leaderboard."""
        from config.settings import settings

        async with async_session_factory() as session:
            repo = UserRepository(session)
            if settings.OWNER_ID > 0:
                owner, _ = await repo.get_or_create(settings.OWNER_ID)
                owner.rating = 5000
                owner.ranked_rating = 5000
                await session.commit()

                users, total = await repo.get_leaderboard(page=1, per_page=100)
                owner_ids = [u.discord_id for u in users]
                self.assertNotIn(settings.OWNER_ID, owner_ids)

                standing = await repo.get_user_standing(settings.OWNER_ID)
                self.assertEqual(standing, 0)

    async def test_skip_command_and_solution_code(self):
        """Kiểm tra lệnh .skip bỏ qua chặng 1, cung cấp code giải mẫu và tăng lên chặng 2."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock()
        p1.id = self.p1_id
        p1.mention = "<@999111222>"
        p2 = MagicMock()
        p2.id = self.p2_id
        p2.mention = "<@999333444>"

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T8",
            p1_ranked_rating=100,
            p2_ranked_rank="T7",
            p2_ranked_rating=450,
        )
        duel.channel = MagicMock()
        duel.channel.send = AsyncMock()
        duel._start_round = AsyncMock()

        # Giả lập đang ở chặng 1 với đề bài
        from services.duel_problems import PROBLEM_BANK

        duel.current_problem = PROBLEM_BANK[0]
        self.assertEqual(duel.current_round, 1)

        # Thí sinh 1 gọi .skip
        msg = MagicMock()
        msg.author = p1
        await duel.handle_skip_command(msg)

        # Chặng tăng lên 2, không ai bị trừ mạng
        self.assertEqual(duel.current_round, 2)
        self.assertEqual(duel.p1_lives, 2)
        self.assertEqual(duel.p2_lives, 2)
        self.assertEqual(len(duel.history), 1)
        self.assertIn("Skipped", duel.history[0].problem_title)

        # Đã gửi embed giải mẫu và embed nghỉ giải lao
        self.assertGreaterEqual(duel.channel.send.call_count, 2)

        # Kiểm tra khi dùng .skip -> Đề chặng sau tự động là bài thuộc Division 1 (Div. 1: LT1, MT1, HT1)
        owner_msg = MagicMock()
        owner_msg.author = p1
        await duel.handle_skip_command(owner_msg)
        duel._start_round.assert_called()
        called_problem = duel._start_round.call_args[1]["problem"]
        self.assertEqual(called_problem.division, "Div. 1")
        self.assertIn(called_problem.tier, ["LT1", "MT1", "HT1"])

    async def test_start_mock_duel_for_owner(self):
        """Kiểm tra chức năng skip hàng chờ và tạo trận mô phỏng dành cho Owner (Bậc cao nhất HT1)."""
        bot = MagicMock()
        mm = MatchmakingManager(bot)

        guild = MagicMock()
        channel = MagicMock()
        owner_member = MagicMock()
        owner_member.id = self.p1_id
        owner_member.guild = guild
        guild.me = MagicMock()
        guild.me.mention = "<@bot>"

        created_channel = MagicMock()
        created_channel.id = 99887766
        created_channel.send = AsyncMock()
        guild.create_text_channel = AsyncMock(return_value=created_channel)

        ok, embed, duel_session = await mm.start_mock_duel_for_owner(
            owner_member, channel
        )
        self.assertTrue(ok)
        self.assertIsNotNone(duel_session)
        self.assertEqual(duel_session.p1_ranked_rank, "HT1")
        self.assertEqual(duel_session.p2_ranked_rank, "HT1")
        self.assertIn("HẠNG CAO NHẤT HT1", embed.title)
        self.assertIn(created_channel.id, mm.active_sessions)


    async def test_prep_phase_allows_chat(self):
        """Kiểm tra: Trong 15s chuẩn bị, tin nhắn chat thông thường KHÔNG bị xóa."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock(spec=discord.Member)
        p1.id = self.p1_id
        p2 = MagicMock(spec=discord.Member)
        p2.id = self.p2_id

        duel = DuelSession(bot, guild, p1, p2, "T6", 800, "T7", 600)
        duel.channel = AsyncMock()
        duel.in_prep_phase = True
        duel.focus_mode = False
        duel.current_problem = MagicMock()

        chat_msg = AsyncMock()
        chat_msg.author = p1
        chat_msg.content = "chào bạn nhé, chúc thi đấu tốt!"

        await duel.handle_raw_text_submission(chat_msg)
        # Không được gọi delete vì đang trong giai đoạn chuẩn bị
        chat_msg.delete.assert_not_called()

    async def test_focus_mode_silence_deletes_chat(self):
        """Kiểm tra: Khi phát đề và bật Chế Độ Giữ Im Lặng, tin nhắn chat thường BỊ XÓA NGAY và cảnh báo."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock(spec=discord.Member)
        p1.id = self.p1_id
        p2 = MagicMock(spec=discord.Member)
        p2.id = self.p2_id

        duel = DuelSession(bot, guild, p1, p2, "T6", 800, "T7", 600)
        duel.channel = AsyncMock()
        duel.in_prep_phase = False
        duel.focus_mode = True
        duel.current_problem = MagicMock()

        chat_msg = AsyncMock()
        chat_msg.author = p1
        chat_msg.content = "bài này giải bằng quy hoạch động hả bạn ơi?"

        await duel.handle_raw_text_submission(chat_msg)
        # Tin nhắn chat bị xóa ngay lập tức
        chat_msg.delete.assert_called_once()
        # Đã gửi cảnh báo tạm thời
        duel.channel.send.assert_called_once()
        self.assertIn("Không được nhắn tin lúc này", duel.channel.send.call_args[0][0])

    async def test_single_submission_enforced(self):
        """Kiểm tra: Mỗi đấu thủ chỉ được nộp bài 1 lần duy nhất trong mỗi chặng."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock(spec=discord.Member)
        p1.id = self.p1_id
        p2 = MagicMock(spec=discord.Member)
        p2.id = self.p2_id

        duel = DuelSession(bot, guild, p1, p2, "T6", 800, "T7", 600)
        duel.channel = AsyncMock()
        duel.current_problem = MagicMock()
        # Giả lập p1 đã nộp bài trước đó
        duel.round_submissions[p1.id] = {"score": 100.0, "passed": 5, "total": 5}

        second_sub_msg = AsyncMock()
        second_sub_msg.author = p1
        code_str = "print('second submission')"

        lang_cfg = MagicMock()
        lang_cfg.source_filename = "solution.py"
        lang_cfg.name = "Python 3"

        await duel._execute_and_grade_submission(
            p1.id, lang_cfg, "python3", code_str, "test.py", second_sub_msg
        )
        # Tin nhắn nộp lần 2 bị xóa ngay lập tức
        second_sub_msg.delete.assert_called_once()
        # Có cảnh báo chỉ nộp 1 lần duy nhất
        duel.channel.send.assert_called_once()
        self.assertIn("1 LẦN DUY NHẤT", duel.channel.send.call_args[0][0])

    async def test_timeout_unsubmitted_loses_life(self):
        """Kiểm tra Quyết định A3: Khi hết giờ, người không nộp bài bị xử thua chặng và trừ 1 mạng."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock(spec=discord.Member)
        p1.id = self.p1_id
        p2 = MagicMock(spec=discord.Member)
        p2.id = self.p2_id

        duel = DuelSession(bot, guild, p1, p2, "T6", 800, "T7", 600)
        duel.channel = AsyncMock()
        duel._start_round = AsyncMock()
        duel.current_problem = MagicMock()
        duel.current_problem.secret_tests = [{}] * 5

        # P2 đã nộp bài kịp (100%), P1 KHÔNG NỘP BÀI
        duel.round_submissions[p2.id] = {"score": 100.0, "passed": 5, "total": 5, "verdict": "AC"}

        self.assertEqual(duel.p1_lives, 2)
        self.assertEqual(duel.p2_lives, 2)

        # Hết giờ gọi evaluate_round(timeout=True)
        await duel._evaluate_round(timeout=True)

        # P1 bị trừ 1 mạng do không nộp bài, P2 bảo toàn 2 mạng
        self.assertEqual(duel.p1_lives, 1)
        self.assertEqual(duel.p2_lives, 2)

    def test_both_failed_partial_win_rating_reduction(self):
        """Kiểm tra Quyết định A1: Khi cả 2 đều làm sai, người đúng nhiều test hơn thắng và bị giảm trừ 50-85% điểm."""
        # 1. Trận thắng chuẩn (AC): T6 (800) vs T7 (600), Cùng Tier T6 vs T7
        w_normal, l_normal, _ = calculate_ranked_rating_deltas(
            "T6", "T7", 800, 600, winner_lives=2, rounds_played=2, is_partial_win=False
        )

        # 2. Trận thắng khi cả 2 đều làm sai (is_partial_win=True)
        w_partial, l_partial, details = calculate_ranked_rating_deltas(
            "T6", "T7", 800, 600, winner_lives=2, rounds_played=2, is_partial_win=True
        )

        # Điểm thưởng bị giảm trừ 50% - 85%
        self.assertLess(w_partial, w_normal)
        self.assertGreater(l_partial, l_normal)  # Ít âm hơn
        self.assertIn("Giảm trừ", details)
        self.assertIn("Cả 2 đều chưa AC", details)


if __name__ == "__main__":
    unittest.main()

