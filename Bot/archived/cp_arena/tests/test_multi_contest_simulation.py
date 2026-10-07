"""Simulation and stress test for 3-4 sample contests using Mode 2 Sandbox, Themis 2-Step Evaluation, and Anti-Cheat."""

import unittest
from unittest.mock import MagicMock

from sqlalchemy import delete

from database.database import async_session_factory, close_db_engine, init_db
from database.models import Submission, User
from database.repositories.user_repo import UserRepository
from services.judge import JudgeService
from services.problem_fetcher import ProblemFetcher
from utils.cooldown import submission_cooldown


class TestMultiContestSimulation(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        submission_cooldown.reset_user(1529864608813416449)
        submission_cooldown.reset_user(1000000001)
        submission_cooldown.reset_user(1000000002)
        submission_cooldown.reset_user(1000000003)
        submission_cooldown.reset_user(1000000004)

        async with async_session_factory() as session:
            await session.execute(delete(Submission))
            u_repo = UserRepository(session)
            for uid in [
                1529864608813416449,
                1000000001,
                1000000002,
                1000000003,
                1000000004,
            ]:
                u, _ = await u_repo.get_or_create(uid)
                u.rank = "HT1"
                u.rating = 3000
                u.total_score = 0.0
            await session.commit()

    async def asyncTearDown(self):
        async with async_session_factory() as session:
            await session.execute(
                delete(Submission).where(
                    Submission.discord_id.in_(
                        [1000000001, 1000000002, 1000000003, 1000000004]
                    )
                )
            )
            await session.execute(
                delete(User).where(
                    User.discord_id.in_(
                        [1000000001, 1000000002, 1000000003, 1000000004]
                    )
                )
            )
            await session.commit()
        await close_db_engine()

    async def test_contest_1_watermelon_4a_python_accepted(self):
        """Contest #1: Codeforces Beta Round 4 - Bài 4A (Watermelon) bằng Python 3."""
        bot = MagicMock()
        judge = JudgeService(bot)
        user = MagicMock()
        user.id = 1000000001
        user.name = "Thí_Sinh_Contest_1"
        user.mention = "<@1000000001>"

        # Code chuẩn Python
        code_py = "w = int(input())\nif w > 2 and w % 2 == 0:\n    print('YES')\nelse:\n    print('NO')\n"

        res = await judge.judge_submission(
            user=user,
            problem_id="4A",
            language_alias="python3",
            code=code_py,
            is_rated=True,
        )

        self.assertTrue(res.success, f"Contest 1 thất bại: {res.verdict}")
        self.assertEqual(res.verdict, "Chấp nhận (Accepted)")
        self.assertGreaterEqual(
            res.tests_passed, 10, "Themis phải chạy ít nhất 10 tests"
        )
        self.assertGreater(res.rating_delta, 0, "Giải đúng phải được cộng rating")
        self.assertGreater(res.score_earned, 0, "Giải đúng phải được cộng score")

    async def test_contest_2_way_too_long_words_71a_cpp_accepted(self):
        """Contest #2: Codeforces Beta Round 65 - Bài 71A (Way Too Long Words) bằng Python 3."""
        bot = MagicMock()
        judge = JudgeService(bot)
        user = MagicMock()
        user.id = 1000000002
        user.name = "Thí_Sinh_Contest_2"
        user.mention = "<@1000000002>"

        # Code chuẩn Python cho bài 71A
        code_py = (
            "n = int(input())\n"
            "for _ in range(n):\n"
            "    s = input().strip()\n"
            "    if len(s) > 10:\n"
            "        print(f'{s[0]}{len(s)-2}{s[-1]}')\n"
            "    else:\n"
            "        print(s)\n"
        )

        res = await judge.judge_submission(
            user=user,
            problem_id="71A",
            language_alias="python3",
            code=code_py,
            is_rated=True,
        )

        self.assertTrue(res.success, f"Contest 2 thất bại: {res.verdict}")
        self.assertEqual(res.verdict, "Chấp nhận (Accepted)")
        self.assertGreater(res.tests_passed, 0)
        self.assertGreater(res.rating_delta, 0)

    async def test_contest_3_team_231a_wrong_answer_rated_secure(self):
        """Contest #3: Codeforces Round 143 - Bài 231A (Team) cố tình làm sai -> Kiểm tra Bước 1 fail & Bảo mật Rated."""
        bot = MagicMock()
        judge = JudgeService(bot)
        user = MagicMock()
        user.id = 1000000003
        user.name = "Thí_Sinh_Contest_3"
        user.mention = "<@1000000003>"

        # Code sai: luôn in 0
        code_wa = "n = int(input())\nprint(0)\n"

        res = await judge.judge_submission(
            user=user,
            problem_id="231A",
            language_alias="python3",
            code=code_wa,
            is_rated=True,
        )

        self.assertFalse(res.success, "Bài sai không được tính là success")
        self.assertIn("Wrong Answer", res.verdict)
        self.assertLessEqual(
            res.rating_delta, 0, "Làm sai Bước 1 phải bị trừ điểm/phạt phong độ"
        )

        # Kiểm tra embed không để lộ đáp án đúng
        embed_dict = res.embed.to_dict()
        fields_text = " ".join(f.get("value", "") for f in embed_dict.get("fields", []))
        self.assertNotIn(
            "Expected: 2",
            fields_text,
            "Không được để lộ expected output của testcase cho Rated",
        )

    async def test_contest_4_unrated_anti_cheat_and_sample_template(self):
        """Contest #4: Thử nghiệm nộp Unrated cho bài 158A -> Kiểm tra ghép bài tương đương và sinh code mẫu."""
        prob_id = "158A"
        eq_prob = await ProblemFetcher.get_equivalent_unrated_problem(
            prob_id, rating=800
        )
        self.assertIsNotNone(eq_prob)
        assert eq_prob is not None
        self.assertNotEqual(
            eq_prob.id,
            prob_id,
            "Bài Unrated phải là một bài khác bài thi đấu để chống gian lận",
        )
        self.assertEqual(
            eq_prob.rating, 800, "Độ khó bài Unrated ghép phải tương đương (800 pts)"
        )

        # Nộp Unrated
        bot = MagicMock()
        judge = JudgeService(bot)
        user = MagicMock()
        user.id = 1000000004
        user.name = "Thí_Sinh_Contest_4"
        user.mention = "<@1000000004>"

        code_unrated = (
            "w = int(input())\nprint('YES' if w > 2 and w % 2 == 0 else 'NO')\n"
        )
        res_unrated = await judge.judge_submission(
            user=user,
            problem_id=eq_prob.id,
            language_alias="python3",
            code=code_unrated,
            is_rated=False,
        )

        self.assertTrue(res_unrated.success)
        self.assertEqual(
            res_unrated.rating_delta, 0, "Unrated không được thay đổi rating"
        )
        self.assertEqual(
            res_unrated.score_earned, 0.0, "Unrated không được thay đổi score"
        )

        # Embed 2 phải có Phân Tích & Tối Ưu
        self.assertIsNotNone(res_unrated.analysis_embed)
        assert res_unrated.analysis_embed is not None
        embed_dict = res_unrated.analysis_embed.to_dict()
        field_names = [f.get("name", "") for f in embed_dict.get("fields", [])]
        self.assertTrue(
            any(
                "Tối Ưu" in name or "Clean Code" in name or "Bộ Nhớ" in name
                for name in field_names
            ),
            "Embed 2 phải có phân tích tối ưu",
        )


if __name__ == "__main__":
    unittest.main()
