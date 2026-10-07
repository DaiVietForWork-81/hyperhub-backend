"""Unit tests verifying rating, performance, event bonus (1.2x - 1.75x), and 2-step Mode 2 score calculation logic."""

import unittest

from services.rating import RatingEngine


class TestRatingEngine(unittest.TestCase):

    def test_mode_score_multipliers(self):
        # Problem rating 1200 -> Base score = 120.0
        # Mode 1 is 85% (15% reduction), Mode 2 is 100%
        score_mode1 = RatingEngine.calculate_problem_score(1200, is_mode1=True)
        score_mode2 = RatingEngine.calculate_problem_score(1200, is_mode1=False)

        self.assertEqual(score_mode1, 102.0)  # 85% of 120.0
        self.assertEqual(score_mode2, 120.0)  # 100% of 120.0

    def test_problem_rating_delta(self):
        # High difficulty delta: user rating 1000, problem rating 1500 (diff = +500)
        # Mode 2 is 100% factor, Mode 1 is 85% factor
        delta_m2 = RatingEngine.calculate_problem_rating_delta(
            1000, 1500, is_mode1=False
        )
        self.assertEqual(delta_m2, 57)

        delta_m1 = RatingEngine.calculate_problem_rating_delta(
            1000, 1500, is_mode1=True
        )
        self.assertEqual(delta_m1, 48)  # 85% of 57

        # High tier user doing low tier problem: user rating 2500, problem rating 800 -> 1 point
        delta_easy = RatingEngine.calculate_problem_rating_delta(
            2500, 800, is_mode1=False
        )
        self.assertEqual(delta_easy, 1)

    def test_contest_performance_calculation(self):
        opponents = [1200, 1400, 1500, 1600, 1800]
        total_participants = len(opponents)

        perf_1st = RatingEngine.calculate_contest_performance(
            1, total_participants, opponents
        )
        self.assertGreater(perf_1st, 1800)

        perf_mid = RatingEngine.calculate_contest_performance(
            3, total_participants, opponents
        )
        self.assertTrue(1400 <= perf_mid <= 1600)

        perf_last = RatingEngine.calculate_contest_performance(
            5, total_participants, opponents
        )
        self.assertLess(perf_last, 1400)

    def test_contest_rating_change(self):
        new_r, delta = RatingEngine.calculate_contest_rating_change(
            1500, 1800.0, volatility=0.5
        )
        self.assertEqual(delta, 150)
        self.assertEqual(new_r, 1650)

        new_r_drop, delta_drop = RatingEngine.calculate_contest_rating_change(
            1600, 1200.0, volatility=0.5
        )
        self.assertEqual(delta_drop, -200)
        self.assertEqual(new_r_drop, 1400)

    def test_problem_rating_penalty(self):
        # Easy problem (800) in Mode 2 (factor 1.0) -> penalty (-16)
        penalty_easy_m2 = RatingEngine.calculate_problem_rating_penalty(
            1000, 800, is_mode1=False
        )
        self.assertEqual(penalty_easy_m2, -16)

        # Mid problem (1500) in Mode 2 (factor 1.0) -> penalty (-30)
        penalty_mid_m2 = RatingEngine.calculate_problem_rating_penalty(
            1500, 1500, is_mode1=False
        )
        self.assertEqual(penalty_mid_m2, -30)

        # Very hard problem (2500+) in Mode 2 (factor 1.0) -> penalty (-50)
        penalty_hard_m2 = RatingEngine.calculate_problem_rating_penalty(
            1000, 2500, is_mode1=False
        )
        self.assertEqual(penalty_hard_m2, -50)

        # Mode 1 penalty (factor 0.85) -> round(-30 * 0.85) = -26
        penalty_mid_m1 = RatingEngine.calculate_problem_rating_penalty(
            1500, 1500, is_mode1=True
        )
        self.assertEqual(penalty_mid_m1, -26)

    def test_event_bonus_multipliers(self):
        # ICPC Huawei Challenge -> 1.75x bonus
        is_event, mult, tag = RatingEngine.get_event_bonus_multiplier(
            contest_name="ICPC 2026 Online Challenge 1 powered by Huawei",
            problem_rating=2200,
        )
        self.assertTrue(is_event)
        self.assertEqual(mult, 1.75)

        # Score with 1.75x Mode 2: 2200 rating -> base = 220.0 -> mode2 * 1.75 = 385.0
        score_icpc_m2 = RatingEngine.calculate_problem_score(
            2200, is_mode1=False, event_multiplier=mult
        )
        self.assertEqual(score_icpc_m2, 385.0)

    def test_event_penalty_and_t4_protection(self):
        # User under T4 (e.g. rating 1000) failing event problem -> Penalty = 0 (Bảo vệ tân binh)
        penalty_newbie = RatingEngine.calculate_problem_rating_penalty(
            user_rating=1000,
            problem_rating=2200,
            is_mode1=False,
            is_event=True,
            tests_passed_ratio=0.1,
        )
        self.assertEqual(penalty_newbie, 0)

        # User at or above T4 (e.g. rating 1600) failing event problem with < 20% test ratio -> 1.35x penalty
        penalty_t4_fail = RatingEngine.calculate_problem_rating_penalty(
            user_rating=1600,
            problem_rating=1600,
            is_mode1=False,
            is_event=True,
            tests_passed_ratio=0.1,  # < 20% tests passed
        )
        self.assertLess(penalty_t4_fail, 0)
        self.assertGreaterEqual(penalty_t4_fail, -50)

    def test_problem_score_penalty(self):
        # Easy problem (800) -> -17.0 pts (Mode 1: 0.85), -20.0 pts (Mode 2: 1.00)
        self.assertEqual(
            RatingEngine.calculate_problem_score_penalty(800, is_mode1=True), -17.0
        )
        self.assertEqual(
            RatingEngine.calculate_problem_score_penalty(800, is_mode1=False), -20.0
        )

        # Mid problem (1200) -> -25.5 pts (Mode 1), -30.0 pts (Mode 2)
        self.assertEqual(
            RatingEngine.calculate_problem_score_penalty(1200, is_mode1=True), -25.5
        )
        self.assertEqual(
            RatingEngine.calculate_problem_score_penalty(1200, is_mode1=False), -30.0
        )

    def test_mode2_two_step_evaluation_step1_fail(self):
        # Pass ratio < 40% (e.g., 1/5 = 20%) -> Step 1 Failed, penalty applied
        res = RatingEngine.evaluate_mode2_two_step_submission(
            tests_passed=1,
            total_tests=5,
            user_rating=1200,
            problem_rating=1400,
        )
        self.assertFalse(res["step1_passed"])
        self.assertLess(res["rating_delta"], 0)
        self.assertLess(res["score_delta"], 0)
        self.assertIn("Không chấp nhận", res["step1_desc"])

    def test_mode2_two_step_evaluation_step2_top_percentile(self):
        # Pass ratio >= 50% (5/5) and Top 15% (> 70% of people) -> 1.4x bonus
        res = RatingEngine.evaluate_mode2_two_step_submission(
            tests_passed=5,
            total_tests=5,
            user_rating=1200,
            problem_rating=1400,
            contest_participants=100,
            contest_percentile=0.85,
        )
        self.assertTrue(res["step1_passed"])
        self.assertTrue(res["step2_evaluated"])
        self.assertEqual(res["multiplier"], 1.40)
        self.assertGreater(res["rating_delta"], 0)
        self.assertGreater(res["score_delta"], 0)

    def test_mode2_two_step_evaluation_underperformance_penalty(self):
        # User rating high (2000) doing easy problem (800) but standing in bottom 5% (percentile 0.05)
        # Should result in a rating penalty despite passing testcases
        res = RatingEngine.evaluate_mode2_two_step_submission(
            tests_passed=5,
            total_tests=5,
            user_rating=2000,
            problem_rating=800,
            contest_participants=100,
            contest_percentile=0.05,
        )
    def test_estimate_cf_problem_rating(self):
        """Kiểm tra ước lượng rating bài tập Codeforces chính xác theo từng Division (chống thổi phồng rating)."""
        # 1. Div. 4: Thang từ 800 đến 1500 (Bài D chỉ 900, F chỉ 1200)
        c_div4 = "Codeforces Round 974 (Div. 4)"
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div4, "A"), 800)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div4, "B"), 800)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div4, "C"), 800)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div4, "D"), 900)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div4, "E"), 1100)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div4, "F"), 1200)

        # 2. Div. 3: Thang từ 800 đến 1900
        c_div3 = "Codeforces Round 970 (Div. 3)"
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div3, "A"), 800)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div3, "C"), 1000)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div3, "D"), 1200)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div3, "E"), 1500)

        # 3. Div. 2: Thang từ 1000 đến 2400
        c_div2 = "Codeforces Round 969 (Div. 2)"
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div2, "A"), 1000)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div2, "B"), 1200)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div2, "C"), 1500)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div2, "D"), 1800)

        # 4. Div. 1: Thang từ 1800 đến 3400
        c_div1 = "Codeforces Round 968 (Div. 1)"
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div1, "A"), 1800)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div1, "B"), 2100)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_div1, "C"), 2400)

        # 5. Global / Edu: Thang từ 800 đến 3000
        c_edu = "Educational Codeforces Round 170"
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_edu, "A"), 800)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_edu, "B"), 1000)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_edu, "C"), 1300)
        self.assertEqual(RatingEngine.estimate_cf_problem_rating(c_edu, "D"), 1600)


if __name__ == "__main__":
    unittest.main()
