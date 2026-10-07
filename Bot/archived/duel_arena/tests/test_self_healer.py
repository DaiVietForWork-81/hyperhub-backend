import unittest
import tempfile
import os
from pathlib import Path

from services.self_healer import SelfHealer
from services.ai_worker import ProblemWorker


class MockPlayer:
    def __init__(self, connected=False, playing=False, queue=None):
        self._connected = connected
        self._playing = playing
        self.queue = queue or []

    def is_connected(self):
        return self._connected

    def is_playing(self):
        return self._playing


class MockBot:
    def __init__(self, has_duel=False, player=None):
        self.player = player
        self._has_duel = has_duel

    def get_cog(self, name):
        if name == "RankedDuelCog" and self._has_duel:
            class MockSession:
                is_active = True
            class MockMM:
                active_sessions = {"session_1": MockSession()}
            class MockCog:
                matchmaker = MockMM()
            return MockCog()
        return None


class TestSelfHealerAndDynamicLoad(unittest.TestCase):
    def test_dynamic_load_calculation(self):
        worker = ProblemWorker()

        # 1. Idle bot: 0 task -> 1s (Min)
        idle_bot = MockBot(has_duel=False, player=None)
        delay, msg = worker.get_activity_load(idle_bot)
        self.assertEqual(delay, 1)
        self.assertIn("1s/bài", msg)
        self.assertIn("Siêu rảnh rỗi", msg)

        # 2. Voice connected (not playing) -> ~4s
        voice_idle_bot = MockBot(has_duel=False, player=MockPlayer(connected=True, playing=False))
        delay, msg = worker.get_activity_load(voice_idle_bot)
        self.assertEqual(delay, 4)
        self.assertIn("4s/bài", msg)

        # 3. Voice playing with queue -> ~25s
        music_bot = MockBot(has_duel=False, player=MockPlayer(connected=True, playing=True, queue=["t1", "t2"]))
        delay, msg = worker.get_activity_load(music_bot)
        self.assertEqual(delay, 25)
        self.assertIn("25s/bài", msg)

        # 4. Active Ranked Duel -> ~36s - 45s (Max capped at 45)
        duel_bot = MockBot(has_duel=True, player=MockPlayer(connected=True, playing=True, queue=["t1", "t2", "t3"]))
        delay, msg = worker.get_activity_load(duel_bot)
        self.assertEqual(delay, 45)
        self.assertIn("45s/bài", msg)

    def test_syntax_pattern_healing(self):
        broken_code = """
import os

def test_func():
    path = "C:\\some\\folder\\new"
    return path
"""
        fixed = SelfHealer.fix_common_syntax_patterns(broken_code)
        self.assertTrue(SelfHealer.validate_python_code(fixed))

    def test_error_location_extraction(self):
        code_with_error = "def broken(\n    return 123"
        try:
            compile(code_with_error, "test_file.py", "exec")
        except SyntaxError as e:
            f, line = SelfHealer.extract_error_location(e)
            self.assertEqual(f, "test_file.py")
            self.assertIn(line, [1, 2])
            self.assertTrue(SelfHealer.is_syntax_or_fixable_error(e))


if __name__ == "__main__":
    unittest.main()
