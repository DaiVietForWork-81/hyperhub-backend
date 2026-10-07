"""Automated tests for Anti-Cheat 2.0, Match Telemetry, TXT Transcript Generation, and Duel History Slash Commands."""

import asyncio
import datetime
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from sqlalchemy import select
from config.settings import settings
from database.database import async_session_factory, init_db
from database.models import DuelMatch, User
from database.repositories.user_repo import UserRepository
from services.anti_cheat import AntiCheatEngine, AntiCheatReport
from services.duel_service import DuelSession


class TestAntiCheatAndMatchHistory(unittest.IsolatedAsyncioTestCase):
    """Test suite for Anti-Cheat 2.0 and Duel Transcript History."""

    async def asyncSetUp(self):
        await init_db()
        self.p1_id = 999111888
        self.p2_id = 999222888

        # Clean DB
        async with async_session_factory() as session:
            from sqlalchemy import delete

            await session.execute(
                delete(User).where(User.discord_id.in_([self.p1_id, self.p2_id]))
            )
            await session.execute(
                delete(DuelMatch).where(
                    DuelMatch.player1_id.in_([self.p1_id, self.p2_id])
                    | DuelMatch.player2_id.in_([self.p1_id, self.p2_id])
                )
            )
            await session.commit()

        # Seed test users
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u1, _ = await repo.get_or_create(self.p1_id)
            u1.ranked_rating = 500
            u1.ranked_rank = "T7"
            u2, _ = await repo.get_or_create(self.p2_id)
            u2.ranked_rating = 550
            u2.ranked_rank = "T7"
            await session.commit()

    async def asyncTearDown(self):
        async with async_session_factory() as session:
            from sqlalchemy import delete

            await session.execute(
                delete(User).where(User.discord_id.in_([self.p1_id, self.p2_id]))
            )
            await session.execute(
                delete(DuelMatch).where(
                    DuelMatch.player1_id.in_([self.p1_id, self.p2_id])
                    | DuelMatch.player2_id.in_([self.p1_id, self.p2_id])
                )
            )
            await session.commit()

    def test_rapid_paste_detection(self):
        """Kiểm tra: Nộp code dài trong < 7.5s bị phát hiện dán code chuẩn bị từ trước."""
        long_code = """
        #include <iostream>
        #include <vector>
        #include <algorithm>
        using namespace std;

        int main() {
            int n;
            cin >> n;
            vector<int> a(n);
            for (int i = 0; i < n; i++) cin >> a[i];
            sort(a.begin(), a.end());
            for (int i = 0; i < n; i++) cout << a[i] << " ";
            return 0;
        }
        """
        # 1. Nộp sau 3 giây -> Rapid paste suspect!
        is_rapid, detail = AntiCheatEngine.check_rapid_paste(long_code, time_elapsed_seconds=3.0)
        self.assertTrue(is_rapid)
        self.assertIn("vượt xa giới hạn", detail)

        # 2. Nộp sau 45 giây -> Bình thường
        is_rapid_normal, detail_normal = AntiCheatEngine.check_rapid_paste(long_code, time_elapsed_seconds=45.0)
        self.assertFalse(is_rapid_normal)
        self.assertIn("tự nhiên", detail_normal)

    def test_plagiarism_solution_detection(self):
        """Kiểm tra: Phát hiện sao chép bài giải mẫu của ngân hàng đề (kể cả khi đổi tên biến)."""
        sol_code = """
        #include <iostream>
        using namespace std;
        int main() {
            long long a, b;
            cin >> a >> b;
            cout << a * b - (a + b) << "\n";
            return 0;
        }
        """

        # Thí sinh đổi tên biến a -> x, b -> y, thêm comment vô nghĩa
        cand_code = """
        #include <iostream>
        using namespace std;
        // Giai thuat tinh tich tru tong
        int main() {
            long long x, y; // inputs
            cin >> x >> y;
            long long ans = x * y - (x + y);
            cout << ans << "\n";
            return 0;
        }
        """

        score = AntiCheatEngine.check_plagiarism(cand_code, sol_code, lang="cpp")
        self.assertGreaterEqual(score, 70.0)

        report = AntiCheatEngine.analyze_submission(
            source_code=cand_code,
            lang="cpp",
            time_elapsed_seconds=20.0,
            solution_code=sol_code,
        )
        self.assertIn(report.risk_level, ("SUSPICIOUS", "CHEATING_DETECTED"))
        self.assertGreaterEqual(report.plagiarism_solution_score, 70.0)

    def test_ai_detection_integration(self):
        """Kiểm tra: Tích hợp phát hiện dấu vết LLM/AI (Time/Space complexity, chatbot phrases)."""
        ai_code = """
        // Time Complexity: O(N log N)
        // Space Complexity: O(N)
        // Here is the complete C++ solution for this problem:
        #include <iostream>
        #include <vector>
        using namespace std;

        int main() {
            // Step 1: Read input
            int n;
            cin >> n;
            return 0;
        }
        """

        report = AntiCheatEngine.analyze_submission(
            source_code=ai_code,
            lang="cpp",
            time_elapsed_seconds=15.0,
        )
        self.assertGreaterEqual(report.ai_score, 60.0)
        self.assertIn("Time Complexity", "".join(report.ai_reasons))

    def test_transcript_generation_and_formatting(self):
        """Kiểm tra: Tạo file transcript .txt đầy đủ thông tin (tin nhắn, mã nguồn, test case, anti-cheat)."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock(spec=discord.Member)
        p1.id = self.p1_id
        p1.display_name = "PlayerOne"
        p2 = MagicMock(spec=discord.Member)
        p2.id = self.p2_id
        p2.display_name = "PlayerTwo"

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 123456789
        channel.name = "duel-test99"

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T7",
            p1_ranked_rating=500,
            p2_ranked_rank="T7",
            p2_ranked_rating=550,
        )
        duel.channel = channel
        duel.match_code = "test99"

        # Giả lập lịch sử tin nhắn
        duel.chat_logs.append({
            "timestamp": datetime.datetime(2026, 9, 8, 20, 0, 0, tzinfo=datetime.timezone.utc),
            "author_id": p1.id,
            "author_name": p1.display_name,
            "type": "15s_PREP_CHAT",
            "content": "Chao doi thu nhe!",
        })
        duel.chat_logs.append({
            "timestamp": datetime.datetime(2026, 9, 8, 20, 0, 20, tzinfo=datetime.timezone.utc),
            "author_id": p2.id,
            "author_name": p2.display_name,
            "type": "SILENCED_CHAT_BLOCKED",
            "content": "De bai nay lam sao ta?",
        })

        # Giả lập bài nộp
        duel.submission_details.append({
            "round_number": 1,
            "author_id": p1.id,
            "author_name": p1.display_name,
            "lang": "C++",
            "source_code": "#include <iostream>\nint main() { return 0; }",
            "score": 100.0,
            "passed": 5,
            "total": 5,
            "verdict": "AC",
            "elapsed_seconds": 42.5,
            "anti_cheat": {
                "risk_level": "CLEAN",
                "ai_score": 5.0,
                "plagiarism_solution_score": 10.0,
                "plagiarism_opponent_score": 0.0,
                "is_rapid_paste": False,
                "rapid_paste_details": "",
                "summary": "Mã nguồn hợp lệ",
            },
            "test_details": [
                {"index": 1, "passed": True, "status": "OK", "time_seconds": 0.015, "memory_mb": 2.1},
                {"index": 2, "passed": True, "status": "OK", "time_seconds": 0.018, "memory_mb": 2.2},
            ],
        })

        text = duel.generate_transcript_text(
            winner=p1,
            loser=p2,
            winner_delta=60.0,
            loser_delta=-60.0,
            winner_new_rank="T7",
            loser_new_rank="T8",
        )

        self.assertIn("RANKED 1:1 MATCH TRANSCRIPT", text)
        self.assertIn("#TEST99", text)
        self.assertIn("PlayerOne", text)
        self.assertIn("PlayerTwo", text)
        self.assertIn("Chao doi thu nhe!", text)
        self.assertIn("De bai nay lam sao ta?", text)
        self.assertIn("MÃ NGUỒN BÀI LÀM", text)
        self.assertIn("Anti-Cheat 2.0", text)
        self.assertIn("Test #1: PASS", text)

    async def test_send_match_transcript_to_log_channel(self):
        """Kiểm tra: Tự động gửi file transcript .txt vào phòng đấu và kênh nhật ký DUEL_LOG_CHANNEL_ID."""
        bot = MagicMock()
        guild = MagicMock()
        p1 = MagicMock(spec=discord.Member)
        p1.id = self.p1_id
        p1.display_name = "WinnerP1"
        p2 = MagicMock(spec=discord.Member)
        p2.id = self.p2_id
        p2.display_name = "LoserP2"

        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 123456789
        channel.name = "duel-test88"
        channel.send = AsyncMock()

        log_channel = MagicMock(spec=discord.TextChannel)
        log_channel.id = 1536199276273860638
        log_channel.name = "log-ranked-duels"
        log_channel.send = AsyncMock()

        # Guild trả về log_channel khi get_channel(1536199276273860638)
        guild.get_channel.side_effect = lambda cid: log_channel if cid == 1536199276273860638 else channel

        duel = DuelSession(
            bot=bot,
            guild=guild,
            player1=p1,
            player2=p2,
            p1_ranked_rank="T7",
            p1_ranked_rating=500,
            p2_ranked_rank="T7",
            p2_ranked_rating=550,
        )
        duel.channel = channel
        duel.match_code = "test88"

        file_path = await duel._send_match_transcript(
            winner=p1,
            loser=p2,
            winner_delta=65.0,
            loser_delta=-65.0,
            winner_new_rank="T6",
            loser_new_rank="T8",
        )

        # 1. Kiểm tra file tồn tại trên đĩa cứng
        self.assertTrue(os.path.exists(file_path))

        # 2. Kiểm tra file được gửi tới kênh thi đấu
        channel.send.assert_called_once()
        self.assertIn("NHẬT KÝ CHI TIẾT TRẬN ĐẤU", channel.send.call_args[1]["content"])

        # 3. Kiểm tra Embed và file được gửi tới kênh log 1536199276273860638
        log_channel.send.assert_called_once()
        embed_sent = log_channel.send.call_args[1]["embed"]
        self.assertIn("NHẬT KÝ TRẬN ĐẤU RANKED 1:1", embed_sent.title)
        self.assertIn("WinnerP1", embed_sent.description)

        # 4. Kiểm tra DuelMatch được ghi nhận trong CSDL
        async with async_session_factory() as session:
            from sqlalchemy import select

            stmt = select(DuelMatch).where(DuelMatch.match_code == "test88")
            res = await session.execute(stmt)
            match_rec = res.scalar_one_or_none()
            self.assertIsNotNone(match_rec)
            self.assertEqual(match_rec.status, "FINISHED")
            self.assertEqual(match_rec.winner_id, p1.id)
            self.assertEqual(match_rec.p1_rating_delta, 65.0)

    async def test_duel_history_and_view_slash_commands(self):
        """Kiểm tra lệnh /duel_history và /duel_view tra cứu lịch sử trận đấu và tải transcript."""
        from cogs.ranked_duel import RankedDuelCog

        bot = MagicMock()
        cog = RankedDuelCog(bot)

        # Chèn 1 trận đấu mẫu vào CSDL
        async with async_session_factory() as session:
            m = DuelMatch(
                match_code="hist01",
                channel_id=123456,
                player1_id=self.p1_id,
                player2_id=self.p2_id,
                p1_lives=2,
                p2_lives=0,
                current_round=2,
                winner_id=self.p1_id,
                p1_rating_delta=60.0,
                p2_rating_delta=-60.0,
                status="FINISHED",
                created_at=datetime.datetime.now(datetime.timezone.utc),
                finished_at=datetime.datetime.now(datetime.timezone.utc),
            )
            session.add(m)
            await session.commit()

        # Tạo file transcript giả lập
        os.makedirs("duel_transcripts", exist_ok=True)
        with open("duel_transcripts/match_hist01.txt", "w", encoding="utf-8") as f:
            f.write("SAMPLE TRANSCRIPT CONTENT FOR HIST01")

        # Kiểm tra truy vấn lịch sử trận đấu từ CSDL
        async with async_session_factory() as session:
            stmt = (
                select(DuelMatch)
                .where(
                    (DuelMatch.player1_id == self.p1_id)
                    | (DuelMatch.player2_id == self.p1_id)
                )
                .order_by(DuelMatch.id.desc())
            )
            res = await session.execute(stmt)
            matches = res.scalars().all()
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].match_code, "hist01")
            self.assertEqual(matches[0].winner_id, self.p1_id)

        # Kiểm tra file transcript lưu trữ trận đấu
        transcript_path = os.path.join("duel_transcripts", "match_hist01.txt")
        self.assertTrue(os.path.exists(transcript_path))
        with open(transcript_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "SAMPLE TRANSCRIPT CONTENT FOR HIST01")

        # Kiểm tra nút Thống Kê Ranked của người chơi trên RankedArenaView
        from cogs.ranked_duel import RankedArenaView
        view = RankedArenaView(cog.matchmaker)
        stats_btn = [c for c in view.children if getattr(c, "custom_id", None) == "btn_my_ranked_stats"][0]

        target_member = MagicMock(spec=discord.Member)
        target_member.id = self.p1_id
        target_member.mention = f"<@{self.p1_id}>"
        target_member.display_name = "TestPlayer1"

        interaction_stats = MagicMock(spec=discord.Interaction)
        interaction_stats.user = target_member
        interaction_stats.response.defer = AsyncMock()
        interaction_stats.followup.send = AsyncMock()
        await stats_btn.callback(interaction_stats)
        interaction_stats.followup.send.assert_called_once()
        embed_stats = interaction_stats.followup.send.call_args[1]["embed"]
        self.assertIn("THÔNG SỐ ĐẤU TRƯỜNG RANKED 1:1", embed_stats.title)


if __name__ == "__main__":
    unittest.main()
