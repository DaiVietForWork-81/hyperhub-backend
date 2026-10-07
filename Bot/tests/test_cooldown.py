"""Unit tests verifying Rank-based submission cooldowns (10m for T8-T4, 5m for T3-HT1)."""

import unittest

from utils.cooldown import SubmissionCooldownManager


class TestSubmissionCooldown(unittest.TestCase):

    def setUp(self):
        self.manager = SubmissionCooldownManager()

    def test_cooldown_duration_by_rank(self):
        # T8 -> T4: 10 minutes (600 seconds)
        for rank in ["T8", "T7", "T6", "T5", "T4", "t8", "t4"]:
            cd = self.manager.get_cooldown_seconds_for_rank(rank)
            self.assertEqual(cd, 600, f"Rank {rank} should have 600s (10 min) cooldown")

        # T3 -> HT1: 5 minutes (300 seconds)
        for rank in ["T3", "T2", "T1", "MT2", "MT1", "LT2", "HT1", "RHT1", "t3", "ht1"]:
            cd = self.manager.get_cooldown_seconds_for_rank(rank)
            self.assertEqual(cd, 300, f"Rank {rank} should have 300s (5 min) cooldown")

    def test_record_and_remaining_cooldown(self):
        user_t8 = 10001
        user_t2 = 10002

        # User T8 records submission
        cd_t8 = self.manager.record_submission(user_t8, rank="T8")
        self.assertEqual(cd_t8, 600)

        rem_t8, total_t8, rank_t8 = self.manager.get_remaining_cooldown(user_t8)
        self.assertTrue(595 <= rem_t8 <= 600)
        self.assertEqual(total_t8, 600)
        self.assertEqual(rank_t8, "T8")

        # User T2 records submission
        cd_t2 = self.manager.record_submission(user_t2, rank="T2")
        self.assertEqual(cd_t2, 300)

        rem_t2, total_t2, rank_t2 = self.manager.get_remaining_cooldown(user_t2)
        self.assertTrue(295 <= rem_t2 <= 300)
        self.assertEqual(total_t2, 300)
        self.assertEqual(rank_t2, "T2")

        # Reset user
        self.manager.reset_user(user_t8)
        rem_after_reset, _, _ = self.manager.get_remaining_cooldown(user_t8)
        self.assertEqual(rem_after_reset, 0.0)

    def test_time_formatting(self):
        self.assertEqual(
            SubmissionCooldownManager.format_remaining_time(600), "**10 phút**"
        )
        self.assertEqual(
            SubmissionCooldownManager.format_remaining_time(575), "**9 phút 35 giây**"
        )
        self.assertEqual(
            SubmissionCooldownManager.format_remaining_time(300), "**5 phút**"
        )
        self.assertEqual(
            SubmissionCooldownManager.format_remaining_time(45), "**45 giây**"
        )


if __name__ == "__main__":
    unittest.main()
