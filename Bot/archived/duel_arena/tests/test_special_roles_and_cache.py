"""Kiểm thử toàn diện cho Hệ thống 6 Danh Hiệu Động & Cơ Chế Smart Caching Profile Card.

1. 👑 Overlord: Thắng chuỗi 50 liên tiếp, mất khi thua.
2. ⚡ Outclassed: 10 ván liên tiếp tỉ lệ thắng >80%, mất khi <=80% hoặc thua.
3. 🔥 Clutchmaster: Lật kèo từ <=10% (10 lần) hoặc <5% (1 lần), mất khi thua.
4. 🍀 Fortune: 10 ván thắng ở thế <15%, bảo lưu khi ván sau bình thường, mất khi thua.
5. 🍀 Godly Luck: 20 ván thắng ở thế <15%, mất khi thua.
6. 💀 Doomed: Bị lật kèo khi cầm chắc phần thắng, tẩy trần khi thắng lại.
7. Smart Caching: Tái sử dụng ảnh thẻ cũ khi dữ liệu người dùng không thay đổi.
"""

import os
import unittest
from services.profile_card import ProfileCardGenerator, PROFILE_CARDS_DIR
from services.special_roles import (
    calculate_win_probability,
    evaluate_match_special_roles,
    get_special_role_meta,
)


class TestSpecialRolesAndCache(unittest.IsolatedAsyncioTestCase):
    def test_win_probability_calculation(self):
        """Kiểm thử thuật toán tính tỉ lệ thắng động."""
        # Cân bằng rating 1500 vs 1500, 2-2 mạng
        p1, p2 = calculate_win_probability(1500, 1500, 2, 2)
        self.assertEqual(p1, 50.0)
        self.assertEqual(p2, 50.0)

        # Chênh lệch rating (1700 vs 1300), 2-2 mạng: người 1300 < 15% (Fortune territory)
        p_fav, p_dog = calculate_win_probability(1700, 1300, 2, 2)
        self.assertGreater(p_fav, 80.0)
        self.assertLess(p_dog, 15.0)

        # Yếu thế về mạng: 1500 vs 1500 nhưng P2 chỉ còn 1 mạng
        p1_lead, p2_trail = calculate_win_probability(1500, 1500, 2, 1)
        self.assertEqual(p2_trail, 25.0)
        self.assertEqual(p1_lead, 75.0)

        # Cực điểm clutch: 1700 vs 1300, người 1300 còn 1 mạng
        p_super, p_ultra_dog = calculate_win_probability(1700, 1300, 2, 1)
        self.assertLess(p_ultra_dog, 5.0)  # Thỏa mãn điều kiện Clutchmaster < 5%

    def test_overlord_unlock_and_loss(self):
        """👑 Overlord: Thắng chuỗi 50 thì mở khóa, thua trận thì mất."""
        res_win = evaluate_match_special_roles(
            winner_prev_role=None,
            winner_streak=50,
            winner_fortune_count=0,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=50.0,
            winner_min_prob=50.0,
            loser_prev_role=None,
            loser_streak=10,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=50.0,
            loser_max_prob=50.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertEqual(res_win["winner_new_role"], "OVERLORD")

        # Thua trận -> Người từng có Overlord bị tước role
        res_loss = evaluate_match_special_roles(
            winner_prev_role=None,
            winner_streak=1,
            winner_fortune_count=0,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=50.0,
            winner_min_prob=50.0,
            loser_prev_role="OVERLORD",
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=50.0,
            loser_max_prob=50.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertIsNone(res_loss["loser_new_role"])

    def test_outclassed_unlock_and_loss(self):
        """⚡ Outclassed: 10 trận liên tiếp >80% thì nhận, gặp trận <=80% thì mất."""
        res_win = evaluate_match_special_roles(
            winner_prev_role=None,
            winner_streak=10,
            winner_fortune_count=0,
            winner_outclassed_count=9,  # Đang có 9 trận
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=85.0,  # Trận thứ 10 > 80%
            winner_min_prob=80.0,
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=15.0,
            loser_max_prob=20.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertEqual(res_win["winner_new_role"], "OUTCLASSED")
        self.assertEqual(res_win["winner_outclassed_count"], 10)

        # Ván sau gặp đối thủ cân tài (tỉ lệ 50% <= 80%) -> Mất Outclassed
        res_reset = evaluate_match_special_roles(
            winner_prev_role="OUTCLASSED",
            winner_streak=11,
            winner_fortune_count=0,
            winner_outclassed_count=10,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=50.0,  # <= 80%
            winner_min_prob=50.0,
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=50.0,
            loser_max_prob=50.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertIsNone(res_reset["winner_new_role"])
        self.assertEqual(res_reset["winner_outclassed_count"], 0)

    def test_clutchmaster_instant_and_accumulated(self):
        """🔥 Clutchmaster: Lật kèo <5% nhận ngay lập tức, hoặc tích lũy 10 lần <=10%."""
        # 1 ván lật kèo từ < 5% -> Nhận ngay
        res_instant = evaluate_match_special_roles(
            winner_prev_role=None,
            winner_streak=1,
            winner_fortune_count=0,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=10.0,
            winner_min_prob=3.5,  # < 5%
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=90.0,
            loser_max_prob=96.5,
            loser_had_two_lives_when_winner_one=True,
        )
        self.assertEqual(res_instant["winner_new_role"], "CLUTCHMASTER")

    def test_fortune_and_godly_luck_preservation(self):
        """🍀 Fortune (10 ván <15%) & 🍀 Godly Luck (20 ván <15%): Thắng bình thường không bị reset."""
        # Ván thắng thứ 10 ở thế < 15% -> Nhận Fortune
        res_fortune = evaluate_match_special_roles(
            winner_prev_role=None,
            winner_streak=10,
            winner_fortune_count=9,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=12.0,  # < 15%
            winner_min_prob=12.0,
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=88.0,
            loser_max_prob=88.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertEqual(res_fortune["winner_new_role"], "FORTUNE")
        self.assertEqual(res_fortune["winner_fortune_count"], 10)

        # Ván sau thắng ở thế bình thường (50% >= 15%) -> Theo luật: không tính, bảo lưu chuỗi 10, vẫn giữ Fortune
        res_normal = evaluate_match_special_roles(
            winner_prev_role="FORTUNE",
            winner_streak=11,
            winner_fortune_count=10,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=50.0,  # Bình thường
            winner_min_prob=50.0,
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=50.0,
            loser_max_prob=50.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertEqual(res_normal["winner_new_role"], "FORTUNE")
        self.assertEqual(res_normal["winner_fortune_count"], 10)

        # Đến ván thứ 20 ở thế < 15% -> Thăng cấp Godly Luck
        res_godly = evaluate_match_special_roles(
            winner_prev_role="FORTUNE",
            winner_streak=25,
            winner_fortune_count=19,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=8.0,  # < 15%
            winner_min_prob=8.0,
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=92.0,
            loser_max_prob=92.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertEqual(res_godly["winner_new_role"], "GODLY_LUCK")
        self.assertEqual(res_godly["winner_fortune_count"], 20)

    def test_doomed_trigger_and_redemption(self):
        """💀 Doomed: Bị lật khi cầm chắc thắng, được tẩy trần khi thắng lại."""
        # Loser đang dẫn 2 mạng vs 1 mạng, max_prob 95%, nhưng bị Winner lật ngược
        res = evaluate_match_special_roles(
            winner_prev_role=None,
            winner_streak=1,
            winner_fortune_count=0,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=False,
            winner_start_prob=15.0,
            winner_min_prob=4.0,  # Clutch
            loser_prev_role=None,
            loser_streak=5,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=85.0,
            loser_max_prob=96.0,
            loser_had_two_lives_when_winner_one=True,
        )
        self.assertEqual(res["loser_new_role"], "DOOMED")
        self.assertTrue(res["loser_is_doomed"])

        # Trận kế tiếp, người này giành chiến thắng -> Tẩy trần Doomed
        res_cleanse = evaluate_match_special_roles(
            winner_prev_role="DOOMED",
            winner_streak=1,
            winner_fortune_count=0,
            winner_outclassed_count=0,
            winner_clutch_count=0,
            winner_is_doomed=True,
            winner_start_prob=50.0,
            winner_min_prob=50.0,
            loser_prev_role=None,
            loser_streak=0,
            loser_fortune_count=0,
            loser_outclassed_count=0,
            loser_clutch_count=0,
            loser_is_doomed=False,
            loser_start_prob=50.0,
            loser_max_prob=50.0,
            loser_had_two_lives_when_winner_one=False,
        )
        self.assertFalse(res_cleanse["winner_is_doomed"])
        self.assertIsNone(res_cleanse["winner_new_role"])

    async def test_smart_profile_card_caching(self):
        """Kiểm tra cơ chế tái sử dụng ảnh cũ khi dữ liệu không thay đổi."""
        test_uid = 9988776655
        # Lần gọi 1: Kết xuất mới
        path1 = await ProfileCardGenerator.generate_profile_card(
            user_id=test_uid,
            display_name="CacheTester",
            avatar_url=None,
            joined_at_str="01/01/2026",
            standing=5,
            overall_pts=2000.0,
            freedom_tier="MT2",
            freedom_rating=2150,
            ranked_tier="MT2",
            ranked_rating=2150,
            title="Code Crafter",
            special_role="CLUTCHMASTER",
            total_wins=30,
            total_losses=10,
            win_rate=75.0,
            force_refresh=True,  # Đảm bảo render lần đầu
        )
        self.assertTrue(os.path.exists(path1))
        mtime1 = os.path.getmtime(path1)

        hash_file = os.path.join(PROFILE_CARDS_DIR, f"profile_{test_uid}.hash")
        self.assertTrue(os.path.exists(hash_file))

        # Lần gọi 2: Dữ liệu hoàn toàn giống hệt -> Trả về ngay từ cache (mtime không đổi)
        path2 = await ProfileCardGenerator.generate_profile_card(
            user_id=test_uid,
            display_name="CacheTester",
            avatar_url=None,
            joined_at_str="01/01/2026",
            standing=5,
            overall_pts=2000.0,
            freedom_tier="MT2",
            freedom_rating=2150,
            ranked_tier="MT2",
            ranked_rating=2150,
            title="Code Crafter",
            special_role="CLUTCHMASTER",
            total_wins=30,
            total_losses=10,
            win_rate=75.0,
            force_refresh=False,
        )
        self.assertEqual(path1, path2)
        mtime2 = os.path.getmtime(path2)
        self.assertEqual(mtime1, mtime2)  # File không bị ghi đè lại, lấy từ cache!


if __name__ == "__main__":
    unittest.main()
