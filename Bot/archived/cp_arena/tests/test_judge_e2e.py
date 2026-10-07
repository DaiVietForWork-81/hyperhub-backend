"""End-to-end judge test for problem 4A and already-solved protection."""

import unittest
from unittest.mock import MagicMock

from database.database import async_session_factory, close_db_engine, init_db
from database.repositories.submission_repo import SubmissionRepository
from services.judge import JudgeService, get_error_diagnostic_and_fix
from services.problem_fetcher import ProblemData


from sqlalchemy import delete
from database.models import Submission, User


class TestJudgeE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        async with async_session_factory() as session:
            await session.execute(
                delete(Submission).where(Submission.discord_id == 999888777)
            )
            await session.execute(delete(User).where(User.discord_id == 999888777))
            await session.commit()
        await close_db_engine()

    async def test_judge_accepted_flow(self):
        bot = MagicMock()
        judge = JudgeService(bot)
        user = MagicMock()
        user.id = 1529864608813416449
        user.mention = "<@1529864608813416449>"

        code = "w = int(input())\nif w > 2 and w % 2 == 0:\n    print('YES')\nelse:\n    print('NO')\n"
        res = await judge.judge_submission(
            user=user,
            problem_id="4A",
            language_alias="python3",
            code=code,
            is_rated=False,
        )
        self.assertEqual(res.verdict, "Chấp nhận (Accepted)")
        self.assertTrue(res.success)
        self.assertGreater(res.tests_passed, 0)

    async def test_already_solved_lock_flow(self):
        bot = MagicMock()
        judge = JudgeService(bot)
        user = MagicMock()
        user.id = 999888777
        user.mention = "<@999888777>"

        # Đánh dấu bài 4A đã giải trong DB
        async with async_session_factory() as session:
            sub_repo = SubmissionRepository(session)
            await sub_repo.create_submission(
                discord_id=999888777,
                problem_id="4A",
                problem_name="Watermelon",
                language="Python 3",
                verdict="Chấp nhận (Accepted)",
                score=100.0,
                execution_time=0.1,
                memory=10.0,
                mode=2,
                tests_passed=5,
                total_tests=5,
                ai_suspicion_score=0.0,
            )

        code = "w = int(input())\nif w > 2 and w % 2 == 0:\n    print('YES')\nelse:\n    print('NO')\n"

        # Nộp Rated -> Bị chặn
        res_rated = await judge.judge_submission(
            user=user,
            problem_id="4A",
            language_alias="python3",
            code=code,
            is_rated=True,
        )
        self.assertEqual(res_rated.verdict, "Already Solved")
        self.assertFalse(res_rated.success)

        # Reset cooldown để test lần nộp tiếp theo
        from utils.cooldown import submission_cooldown

        submission_cooldown.reset_user(user.id)

        # Nộp Unrated -> Được phép
        code_unrated = (
            "w = int(input())\nprint('YES' if (w > 2 and w % 2 == 0) else 'NO')\n"
        )
        res_unrated = await judge.judge_submission(
            user=user,
            problem_id="4A",
            language_alias="python3",
            code=code_unrated,
            is_rated=False,
        )
        self.assertEqual(res_unrated.verdict, "Chấp nhận (Accepted)")
        self.assertTrue(res_unrated.success)

    def test_error_diagnostic_and_fix(self):
        prob = ProblemData("4A", 4, "A", "Watermelon", 800, 1.0, 256, [], "T8")
        wa_detail, wa_fix = get_error_diagnostic_and_fix(
            "Wrong Answer", "Output mismatch", "cpp17", prob
        )
        self.assertIn("long long", wa_fix)

        tle_detail, tle_fix = get_error_diagnostic_and_fix(
            "TLE", "Exceeded 1.0s", "cpp17", prob
        )
        self.assertIn("Fast I/O", tle_fix)

    def test_unrated_sample_code_and_deep_review(self):
        from services.judge import (
            get_sample_solution_template,
            get_unrated_deep_code_review,
        )

        prob = ProblemData("4A", 4, "A", "Watermelon", 800, 1.0, 256, [], "T8")

        # Test sample code template generation
        py_tpl = get_sample_solution_template(prob, "python3")
        self.assertIn("def solve():", py_tpl)
        self.assertIn("Watermelon", py_tpl)

        cpp_tpl = get_sample_solution_template(prob, "cpp17")
        self.assertIn("#include <bits/stdc++.h>", cpp_tpl)
        self.assertIn("ios_base::sync_with_stdio", cpp_tpl)

        # Test deep review when WA/Fail
        title_fail, rev_fail = get_unrated_deep_code_review(
            code="int main() { int a; cin >> a; return 0; }",
            language="cpp17",
            problem=prob,
            is_accepted=False,
            verdict="Wrong Answer",
            failed_reason="Mismatch on test 2",
            tests_passed=1,
            total_tests=5,
        )
        self.assertIn("LỖI SAI", title_fail)
        self.assertIn("Mismatch on test 2", rev_fail)

        # Test deep review when Accepted
        title_ok, rev_ok = get_unrated_deep_code_review(
            code="int main() { int a; cin >> a; return 0; }",
            language="cpp17",
            problem=prob,
            is_accepted=True,
            verdict="Accepted",
            failed_reason="",
            tests_passed=5,
            total_tests=5,
        )
        self.assertIn("TỐI ƯU", title_ok)
        self.assertIn("Fast I/O", rev_ok)

    def test_themis_step2_test_suite_generation(self):
        from judge.testcase_generator import TestcaseGenerator

        samples = [("1\n", "1\n"), ("2\n", "2\n")]
        suite = TestcaseGenerator.generate_themis_step2_suite(
            sample_tests=samples,
            problem_id="4A",
            time_limit=2.0,
            problem_rating=1400,
            target_test_count=18,
        )
        self.assertGreaterEqual(len(suite), 15)
        self.assertLessEqual(len(suite), 22)

        types = {t.test_type for t in suite}
        self.assertIn("SAMPLE", types)
        self.assertIn("EDGE_CASE", types)
        self.assertIn("TLE_STRESS", types)
        self.assertIn("MEMORY_STRESS", types)

    def test_rated_error_diagnostic_hides_expected_output(self):
        from services.judge import get_rated_error_diagnostic_and_location

        prob = ProblemData("4A", 4, "A", "Watermelon", 800, 1.0, 256, [], "T8")
        code = "int main() { int n; cin >> n; int ans = n * 1000000; return 0; }"

        loc_detail, fix_guide = get_rated_error_diagnostic_and_location(
            code=code,
            language="cpp17",
            problem=prob,
            verdict="Wrong Answer",
            failed_test_type="TLE_STRESS",
        )
        # Check that location is identified
        self.assertIn("Vị trí lỗi", loc_detail)
        self.assertIn("tràn số", loc_detail)
        # Ensure NO raw expected answer / testcase output leak
        self.assertNotIn("Expected:", loc_detail)
        self.assertNotIn("Got:", loc_detail)

    def test_line_by_line_analysis(self):
        from services.judge import get_line_by_line_code_analysis

        prob = ProblemData("4A", 4, "A", "Watermelon", 800, 1.0, 256, [], "T8")
        code = (
            "#include <iostream>\n"
            "using namespace std;\n"
            "int main() {\n"
            "    int n;\n"
            "    cin >> n;\n"
            "    int total = n * 100000;\n"
            "    cout << total << endl;\n"
            "    return 0;\n"
            "}\n"
        )
        analysis = get_line_by_line_code_analysis(
            code=code,
            language="cpp17",
            problem=prob,
            verdict="Wrong Answer",
            is_accepted=False,
        )
        self.assertIn("Dòng 5:", analysis)
        self.assertIn("cin", analysis)
        self.assertIn("Dòng 7:", analysis)
        self.assertIn("endl", analysis)

    async def test_equivalent_unrated_problem_pairing(self):
        from services.problem_fetcher import ProblemFetcher

        eq_prob = await ProblemFetcher.get_equivalent_unrated_problem(
            "2258A", rating=800
        )
        self.assertIsNotNone(eq_prob)
        assert eq_prob is not None
        self.assertNotEqual(eq_prob.id, "2258A")
        self.assertEqual(eq_prob.rating, 800)


if __name__ == "__main__":
    unittest.main()
