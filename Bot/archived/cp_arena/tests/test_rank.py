"""Unit tests verifying rank tiers, ordering, and permission checking."""

import unittest

from services.rank import (
    get_rank_badge,
    get_rank_by_rating,
    is_rank_sufficient,
)


class TestRankSystem(unittest.TestCase):

    def test_rank_by_rating_brackets(self):
        # Điểm số vô hạn (5000, 10000, 50000 pts) đều là HT1
        self.assertEqual(get_rank_by_rating(50000), "HT1")
        self.assertEqual(get_rank_by_rating(10000), "HT1")
        self.assertEqual(get_rank_by_rating(5000), "HT1")
        self.assertEqual(get_rank_by_rating(3500), "HT1")
        self.assertEqual(get_rank_by_rating(3000), "HT1")
        self.assertEqual(get_rank_by_rating(2999), "MT1")
        self.assertEqual(get_rank_by_rating(2600), "MT1")
        self.assertEqual(get_rank_by_rating(2599), "LT1")
        self.assertEqual(get_rank_by_rating(2400), "LT1")
        self.assertEqual(get_rank_by_rating(2350), "HT2")
        self.assertEqual(get_rank_by_rating(2200), "MT2")
        self.assertEqual(get_rank_by_rating(2000), "LT2")
        self.assertEqual(get_rank_by_rating(1750), "T3")
        self.assertEqual(get_rank_by_rating(1500), "T4")
        self.assertEqual(get_rank_by_rating(1300), "T5")
        self.assertEqual(get_rank_by_rating(900), "T6")
        self.assertEqual(get_rank_by_rating(500), "T7")
        self.assertEqual(get_rank_by_rating(200), "T8")
        self.assertEqual(get_rank_by_rating(0), "T8")

    def test_rank_sufficiency(self):
        # T4 user trying to access T6 problem -> Allowed
        self.assertTrue(is_rank_sufficient("T4", "T6"))
        self.assertTrue(is_rank_sufficient("T4", "T6+"))

        # T6 user trying to access T4 problem -> Denied
        self.assertFalse(is_rank_sufficient("T6", "T4"))

        # HT1 user trying to access anything -> Allowed
        self.assertTrue(is_rank_sufficient("HT1", "T3"))
        self.assertTrue(is_rank_sufficient("HT1", "HT1"))

        # Same rank -> Allowed
        self.assertTrue(is_rank_sufficient("T5", "T5"))

    def test_rank_badges(self):
        self.assertEqual(get_rank_badge("RHT1"), "🥀")
        self.assertEqual(get_rank_badge("HT1"), "👑")
        self.assertEqual(get_rank_badge("T8"), "⭐")

    def test_tier_division_mapping(self):
        """Kiểm tra phân nhóm 4 Division:
        • Tier 8-7-6: Div. 4
        • Tier 6-5-4-3: Div. 3
        • LT2-HT2: Div. 2
        • LT1-HT1: Div. 1
        """
        from services.rank import get_tier_division

        self.assertEqual(get_tier_division("T8"), "Div. 4")
        self.assertEqual(get_tier_division("T7"), "Div. 4")
        self.assertIn("Div. 4", get_tier_division("T6"))

        self.assertEqual(get_tier_division("T5"), "Div. 3")
        self.assertEqual(get_tier_division("T4"), "Div. 3")
        self.assertEqual(get_tier_division("T3"), "Div. 3")

        self.assertEqual(get_tier_division("LT2"), "Div. 2")
        self.assertEqual(get_tier_division("MT2"), "Div. 2")
        self.assertEqual(get_tier_division("HT2"), "Div. 2")

        self.assertEqual(get_tier_division("LT1"), "Div. 1")
        self.assertEqual(get_tier_division("MT1"), "Div. 1")
        self.assertEqual(get_tier_division("HT1"), "Div. 1")


if __name__ == "__main__":
    unittest.main()
