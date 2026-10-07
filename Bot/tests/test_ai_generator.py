"""Unit tests for services/ai_generator.py problem generator and sandbox validator."""

import unittest
from unittest.mock import patch, MagicMock
from services.ai_generator import (
    QwenProblemGenerator,
    validate_python_solution,
    TIER_GUIDELINES,
)
from services.problem_types import DuelProblem


class TestAIGenerator(unittest.TestCase):
    """Test suite for Local AI Problem Generator."""

    def test_tier_guidelines_coverage(self):
        """Kiá»ƒm tra Ä‘áº§y Ä‘á»§ 10 báº­c Tier trong hÆ°á»›ng dáº«n sinh Ä‘á» AI."""
        required_tiers = ["T8", "T7", "T6", "T5", "T4", "T3", "LT2", "HT2", "LT1", "HT1"]
        for tier in required_tiers:
            self.assertIn(tier, TIER_GUIDELINES)
            guide = TIER_GUIDELINES[tier]
            self.assertIn("division", guide)
            self.assertIn("rating", guide)
            self.assertIn("topics", guide)
            self.assertIn("constraints", guide)

    def test_sandbox_validation_success(self):
        """Kiá»ƒm tra sandbox validator cháº¡y Ä‘Ãºng vá»›i solution chÃ­nh xÃ¡c."""
        sol_code = """
import sys

def main():
    lines = sys.stdin.read().split()
    if not lines:
        return
    n = int(lines[0])
    arr = [int(x) for x in lines[1:n+1]]
    print(sum(arr))

if __name__ == '__main__':
    main()
"""
        sample_in = "3\n1 2 3"
        sample_out = "6"
        secret_tests = [
            {"input": "1\n10", "output": "10"},
            {"input": "4\n5 5 5 5", "output": "20"},
            {"input": "5\n-1 -2 3 4 0", "output": "4"},
        ]

        is_valid, msg = validate_python_solution(sol_code, sample_in, sample_out, secret_tests)
        self.assertTrue(is_valid, f"Expected success but got: {msg}")
        self.assertIn("Passed all 4 tests", msg)

    def test_sandbox_validation_wrong_answer(self):
        """Kiá»ƒm tra sandbox validator phÃ¡t hiá»‡n khi code giáº£i cho káº¿t quáº£ sai."""
        wrong_code = "print(0)"
        sample_in = "3\n1 2 3"
        sample_out = "6"
        secret_tests = [{"input": "2\n1 1", "output": "2"}]

        is_valid, msg = validate_python_solution(wrong_code, sample_in, sample_out, secret_tests)
        self.assertFalse(is_valid)
        self.assertIn("Wrong Answer", msg)

    def test_sandbox_validation_syntax_error(self):
        """Kiá»ƒm tra sandbox validator báº¯t lá»—i Runtime/Syntax Error."""
        broken_code = "def invalid_syntax(: pass"
        sample_in = "1"
        sample_out = "1"
        secret_tests = []

        is_valid, msg = validate_python_solution(broken_code, sample_in, sample_out, secret_tests)
        self.assertFalse(is_valid)
        self.assertIn("Runtime Error", msg)

    def test_build_prompt(self):
        """Kiá»ƒm tra hÃ m táº¡o prompt chá»©a Ä‘áº§y Ä‘á»§ thÃ´ng tin cáº¥u trÃºc JSON."""
        gen = QwenProblemGenerator()
        prompt = gen.build_prompt("T5", "ngÃ¢n hÃ ng & giao dá»‹ch")
        self.assertIn("T5", prompt)
        self.assertIn("Div. 3", prompt)
        self.assertIn("ngÃ¢n hÃ ng & giao dá»‹ch", prompt)
        self.assertIn("sample_input", prompt)
        self.assertIn("secret_tests", prompt)
        self.assertIn("solution_code", prompt)


if __name__ == "__main__":
    unittest.main()
