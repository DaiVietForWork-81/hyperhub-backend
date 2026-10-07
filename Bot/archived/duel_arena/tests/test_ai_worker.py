import asyncio
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.ai_worker import (
    ProblemWorker,
    load_cached_problems_into_bank,
    save_problem_to_cache,
    AI_PROBLEMS_FILE,
)
from services.duel_problems import DuelProblem, PROBLEM_BANK


class TestAIWorker(unittest.IsolatedAsyncioTestCase):
    """Kiá»ƒm tra hoáº¡t Ä‘á»™ng cá»§a AI Worker sinh Ä‘á» ná»n."""

    async def test_save_and_load_cached_problems(self):
        """Kiá»ƒm tra lÆ°u Ä‘á» bÃ i vÃ o JSON vÃ  náº¡p láº¡i vÃ o PROBLEM_BANK."""
        test_prob = DuelProblem(
            id="duel_test_worker_01",
            name="Test Worker Problem",
            tier="T6",
            division="Div. 4",
            rating_display="T6 / Rating: 850 pts",
            statement="Test statement",
            input_format="Test input",
            output_format="Test output",
            constraints="1 <= N <= 100",
            sample_input="1",
            sample_output="1",
            secret_tests=[{"input": "2", "output": "2"}],
        )

        await save_problem_to_cache(test_prob)
        self.assertTrue(os.path.exists(AI_PROBLEMS_FILE))

        # Kiá»ƒm tra náº¡p láº¡i
        loaded = load_cached_problems_into_bank()
        self.assertTrue(any(p.id == "duel_test_worker_01" for p in PROBLEM_BANK))

    def test_has_active_duels_detection(self):
        """Kiá»ƒm tra phÃ¡t hiá»‡n tráº­n duel Ä‘ang diá»…n ra Ä‘á»ƒ táº¡m dá»«ng sinh Ä‘á» ngáº§m."""
        worker = ProblemWorker()
        mock_bot = MagicMock()

        # TrÆ°á»ng há»£p 1: KhÃ´ng cÃ³ RankedDuelCog
        mock_bot.get_cog.return_value = None
        self.assertFalse(worker.has_active_duels(mock_bot))

        # TrÆ°á»ng há»£p 2: CÃ³ matchmaker nhÆ°ng rá»—ng
        mock_cog = MagicMock()
        mock_cog.matchmaker.active_sessions = {}
        mock_bot.get_cog.return_value = mock_cog
        self.assertFalse(worker.has_active_duels(mock_bot))

        # TrÆ°á»ng há»£p 3: CÃ³ tráº­n duel Ä‘ang active
        mock_session = MagicMock()
        mock_session.is_active = True
        mock_cog.matchmaker.active_sessions = {12345: mock_session}
        self.assertTrue(worker.has_active_duels(mock_bot))

    def test_ai_chat_pause_and_cooldown(self):
        """Worker pauses while AI is chatting, slows down during post-chat cooldown."""
        import time

        from services.ai_core import ai_core, AICoreState

        worker = ProblemWorker()
        mock_bot = MagicMock()
        mock_bot.get_cog.return_value = None
        mock_bot.player = None
        old_state = ai_core.state
        old_stamp = ai_core.last_llm_call_time

        try:
            # 1. AI chatting -> worker detects busy + high delay
            ai_core.state = AICoreState.ANALYZING
            self.assertTrue(worker.is_ai_chat_active())
            delay, msg = worker.get_activity_load(mock_bot)
            self.assertGreaterEqual(delay, 35)
            self.assertIn("AI", msg)

            # 2. AI done but chatted 10s ago -> cooldown, medium delay
            ai_core.state = AICoreState.IDLE
            ai_core.last_llm_call_time = time.time() - 10
            self.assertTrue(worker.is_ai_chat_active())
            delay, msg = worker.get_activity_load(mock_bot)
            self.assertGreaterEqual(delay, 15)

            # 3. AI idle long (> 5 min) -> worker full speed
            ai_core.last_llm_call_time = time.time() - 400
            self.assertFalse(worker.is_ai_chat_active())
            delay, _ = worker.get_activity_load(mock_bot)
            self.assertEqual(delay, 1)
        finally:
            ai_core.state = old_state
            ai_core.last_llm_call_time = old_stamp

    def test_adaptive_inventory_status(self):
        """Kiểm tra thống kê kho đề: phân loại starving, saturated, is_oversaturated."""
        worker = ProblemWorker()

        # Tạo danh sách mock problem giả lập
        mock_problems = []
        # T8: 3 bài (fresh < 5 -> starving)
        for i in range(3):
            mock_problems.append(DuelProblem(
                id=f"test_t8_{i}", name=f"P T8 {i}", tier="T8", division="Div. 4",
                rating_display="T8", statement="", input_format="", output_format="",
                constraints="", sample_input="", sample_output="", secret_tests=[]
            ))
        # T7: 16 bài (fresh >= 15 -> saturated)
        for i in range(16):
            mock_problems.append(DuelProblem(
                id=f"test_t7_{i}", name=f"P T7 {i}", tier="T7", division="Div. 4",
                rating_display="T7", statement="", input_format="", output_format="",
                constraints="", sample_input="", sample_output="", secret_tests=[]
            ))

        with patch("services.ai_worker.PROBLEM_BANK", mock_problems):
            inv = worker.get_inventory_status()
            self.assertIn("T8", inv["starving"])
            self.assertIn("T7", inv["saturated"])
            self.assertFalse(inv["is_oversaturated"])

        # Kiểm tra khi kho đạt >= 120 bài -> is_oversaturated = True
        many_problems = [
            DuelProblem(
                id=f"test_huge_{i}", name=f"P {i}", tier="T8", division="Div. 4",
                rating_display="T8", statement="", input_format="", output_format="",
                constraints="", sample_input="", sample_output="", secret_tests=[]
            ) for i in range(125)
        ]
        with patch("services.ai_worker.PROBLEM_BANK", many_problems):
            inv = worker.get_inventory_status()
            self.assertTrue(inv["is_oversaturated"])

    def test_adaptive_crowd_and_demand_status(self):
        """Kiểm tra nhận diện độ đông đúc và các tier hot đang cần đề."""
        worker = ProblemWorker()
        mock_bot = MagicMock()

        # Mock RankedDuelCog với 1 session active (T6 vs T5) và 1 player trong queue (HT1)
        mock_cog = MagicMock()
        mock_session = MagicMock()
        mock_session.is_active = True
        mock_session.p1_ranked_rank = "T6"
        mock_session.p2_ranked_rank = "T5"
        mock_session.custom_tier = None
        mock_cog.matchmaker.active_sessions = {999: mock_session}

        mock_queue_item = MagicMock()
        mock_queue_item.ranked_rank = "HT1"
        mock_cog.matchmaker.queue = [mock_queue_item]

        mock_bot.get_cog.return_value = mock_cog

        status = worker.get_crowd_and_demand_status(mock_bot)
        self.assertTrue(status["is_crowded"])
        self.assertEqual(status["active_duels_count"], 1)
        self.assertEqual(status["queue_count"], 1)
        self.assertIn("T6", status["hot_tiers"])
        self.assertIn("T5", status["hot_tiers"])
        self.assertIn("HT1", status["hot_tiers"])

    def test_adaptive_delay_when_oversaturated(self):
        """Nếu quá nhiều bài (đầy kho) -> AI không sinh thêm / nghỉ 180s."""
        worker = ProblemWorker()
        mock_bot = MagicMock()
        mock_bot.get_cog.return_value = None
        mock_bot.player = None

        with patch.object(worker, "is_ai_chat_active", return_value=False):
            with patch.object(worker, "get_inventory_status", return_value={
                "total": 130, "counts": {}, "fresh_counts": {}, "starving": [], "saturated": ["T8"], "is_oversaturated": True
            }):
                delay, msg = worker.get_adaptive_delay(mock_bot, target_tier="T8")
                self.assertEqual(delay, 180)
                self.assertIn("🛑", msg)

    def test_adaptive_delay_crowded_and_starving(self):
        """Khi đông người chơi và thiếu đề -> Tăng tốc sinh siêu tốc (2s/bài)."""
        worker = ProblemWorker()
        mock_bot = MagicMock()

        with patch.object(worker, "is_ai_chat_active", return_value=False):
            with patch.object(worker, "get_inventory_status", return_value={
                "total": 30, "counts": {"T6": 2}, "fresh_counts": {"T6": 2}, "starving": ["T6"], "saturated": [], "is_oversaturated": False
            }):
                with patch.object(worker, "get_crowd_and_demand_status", return_value={
                    "is_crowded": True, "hot_tiers": ["T6"], "active_duels_count": 1, "queue_count": 0
                }):
                    delay, msg = worker.get_adaptive_delay(mock_bot, target_tier="T6")
                    self.assertEqual(delay, 2)
                    self.assertIn("TURBO", msg)

    def test_adaptive_delay_crowded_and_comfortable(self):
        """Khi đông người chơi nhưng đề đã dồi dào -> Nhường CPU cho trận đấu (45s)."""
        worker = ProblemWorker()
        mock_bot = MagicMock()

        with patch.object(worker, "is_ai_chat_active", return_value=False):
            with patch.object(worker, "get_inventory_status", return_value={
                "total": 80, "counts": {"T4": 12}, "fresh_counts": {"T4": 12}, "starving": [], "saturated": [], "is_oversaturated": False
            }):
                with patch.object(worker, "get_crowd_and_demand_status", return_value={
                    "is_crowded": True, "hot_tiers": ["T4"], "active_duels_count": 2, "queue_count": 1
                }):
                    delay, msg = worker.get_adaptive_delay(mock_bot, target_tier="T4")
                    self.assertEqual(delay, 45)
                    self.assertIn("NHƯỜNG TÀI NGUYÊN", msg)

    def test_adaptive_delay_idle_and_saturated_tier(self):
        """Khi vắng nhưng tier này đã đạt tối đa đề -> Sinh chậm (60s)."""
        worker = ProblemWorker()
        mock_bot = MagicMock()
        mock_bot.get_cog.return_value = None
        mock_bot.player = None

        with patch.object(worker, "is_ai_chat_active", return_value=False):
            with patch.object(worker, "get_inventory_status", return_value={
                "total": 40, "counts": {"HT1": 15}, "fresh_counts": {"HT1": 15}, "starving": [], "saturated": ["HT1"], "is_oversaturated": False
            }):
                with patch.object(worker, "get_crowd_and_demand_status", return_value={
                    "is_crowded": False, "hot_tiers": [], "active_duels_count": 0, "queue_count": 0
                }):
                    delay, msg = worker.get_adaptive_delay(mock_bot, target_tier="HT1")
                    self.assertEqual(delay, 60)
                    self.assertIn("ĐỦ ĐỀ", msg)


if __name__ == "__main__":
    unittest.main()

