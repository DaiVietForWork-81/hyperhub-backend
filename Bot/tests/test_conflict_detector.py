"""
tests/test_conflict_detector.py
Kiểm thử toàn diện Hệ Thống AI Giám Sát & Ngăn Chặn Xung Đột Siêu Nhẹ (Conflict Detector & Fast Filter).
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.conflict_detector import (
    ConflictDetector,
    ConflictEvaluationResult,
    ConflictLexiconManager,
    conflict_detector,
    lexicon,
)


class TestConflictDetector(unittest.TestCase):
    def setUp(self):
        self.detector = ConflictDetector(window_size=8, time_window_seconds=90.0)
        self.channel_id = 999111222

    # =========================================================================
    # 1. KIỂM THỬ PHỄU LỌC NHANH (FAST FILTER — 0% CPU, 0 TOKEN)
    # =========================================================================
    def test_single_user_no_conflict(self):
        """Chỉ có 1 người chat một mình -> Phễu lọc bỏ qua ngay (0% CPU)."""
        self.detector.record_message(self.channel_id, 1, 100, "Alice", "Đm bài này khó vcl.")
        self.detector.record_message(self.channel_id, 2, 100, "Alice", "Bực mình quá đi mất!")
        should_eval, users, records, score = self.detector.fast_filter(self.channel_id)
        self.assertFalse(should_eval)
        self.assertEqual(len(users), 0)

    def test_casual_banter_friendly_chat(self):
        """Chửi thề đùa giỡn, gaming banter, cười đùa -> Bỏ qua, không coi là xung đột."""
        self.detector.record_message(self.channel_id, 1, 101, "Alice", "Đm hôm nay server lag vcl anh em ơi.")
        self.detector.record_message(self.channel_id, 2, 102, "Bob", "Haha kêu cc gì mạng nhà m cùi bắp ấy chứ kk.")
        self.detector.record_message(self.channel_id, 3, 101, "Alice", "Kkk đùa tí làm gì căng.")

        should_eval, users, records, score = self.detector.fast_filter(self.channel_id)
        self.assertFalse(should_eval)

    def test_escalating_hostile_conflict(self):
        """Hai người chửi bới, xúc phạm, thách thức đánh nhau -> Kích hoạt phễu tầng 1."""
        self.detector.record_message(self.channel_id, 1, 201, "UserA", "Mày làm ăn như hạch, thứ ngu si đần độn.")
        self.detector.record_message(self.channel_id, 2, 202, "UserB", "Câm mồm lại con chó, mày thích solo không tao cho mày nát gáo bây giờ?")

        should_eval, users, records, score = self.detector.fast_filter(self.channel_id)
        self.assertTrue(should_eval)
        self.assertIn(201, users)
        self.assertIn(202, users)
        self.assertGreaterEqual(score, 60)

    # =========================================================================
    # 2. KIỂM THỬ ĐÁNH GIÁ NGỮ CẢNH (EVALUATE CONFLICT)
    # =========================================================================
    def test_evaluate_conflict_with_mock_ai(self):
        """Mô phỏng phản hồi AI trả về xung đột hợp lệ."""
        async def run():
            self.detector.record_message(self.channel_id, 10, 301, "Tom", "Thằng rác rưởi cút đi.")
            self.detector.record_message(self.channel_id, 11, 302, "Jerry", "Bố mày tát vỡ mồm m, ra cổng trường gặp tao!")

            # Mock aiohttp request tới Ollama trả về JSON is_conflict=True
            with patch("aiohttp.ClientSession.post") as mock_post:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value={
                    "message": {
                        "content": '{"is_conflict": true, "reason": "Thù địch và đe dọa bạo lực", "severity": "high"}'
                    }
                })
                mock_post.return_value.__aenter__.return_value = mock_resp

                res = await self.detector.evaluate_conflict(self.channel_id)
                self.assertTrue(res.is_conflict)
                self.assertIn(301, res.involved_users)
                self.assertIn(302, res.involved_users)
                self.assertEqual(res.severity, "high")
                self.assertTrue(res.ai_used)

        asyncio.run(run())

    def test_heuristic_fallback_when_ai_offline(self):
        """Khi AI ngoại tuyến hoặc lỗi, fallback Heuristic tự xử lý dựa trên điểm thù địch."""
        async def run():
            self.detector.record_message(self.channel_id, 20, 401, "Nam", "Thằng súc vật cút đi.")
            self.detector.record_message(self.channel_id, 21, 402, "Binh", "Bố mày đập chết mày bây giờ, thích va chạm không?")

            with patch("aiohttp.ClientSession.post", side_effect=Exception("Connection refused")):
                res = await self.detector.evaluate_conflict(self.channel_id)
                self.assertTrue(res.is_conflict)
                self.assertIn(401, res.involved_users)
                self.assertIn(402, res.involved_users)
                self.assertFalse(res.ai_used)

        asyncio.run(run())

    # =========================================================================
    # 3. KIỂM THỬ TỪ ĐIỂN LÓNG & HỌC TỪ MỚI (LEXICON MANAGER)
    # =========================================================================
    def test_lexicon_learning(self):
        """Kiểm thử thêm từ lóng mới vào từ điển."""
        initial_count = len(lexicon.learned_slang)
        test_word = "test_slang_12345"

        lexicon.add_learned_slang(test_word, "casual", "Từ lóng thử nghiệm")
        self.assertIn(test_word, lexicon.learned_slang)
        self.assertIn(test_word, lexicon.casual_banter)

        # Xóa dọn dẹp
        lexicon.learned_slang.pop(test_word, None)
        lexicon.casual_banter.discard(test_word)
        lexicon.save()
        self.assertEqual(len(lexicon.learned_slang), initial_count)


if __name__ == "__main__":
    unittest.main()
