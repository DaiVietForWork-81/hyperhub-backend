"""Unit tests verifying judge output comparator with Vietnamese verdicts."""

import unittest

from judge.checker import OutputChecker


class TestOutputChecker(unittest.TestCase):

    def test_exact_match(self):
        actual = "42\n"
        expected = "42"
        result = OutputChecker.compare(actual, expected)
        self.assertTrue(result.passed)
        self.assertIn("Accepted", result.verdict)

    def test_whitespace_and_newline_normalization(self):
        actual = "  1   2   3\n4 5 \n\n"
        expected = "1 2 3 4 5"
        result = OutputChecker.compare(actual, expected)
        self.assertTrue(result.passed)
        self.assertIn("Accepted", result.verdict)

    def test_floating_point_epsilon(self):
        actual = "3.14159265"
        expected = "3.1415927"
        # Default epsilon is 1e-6 -> diff is ~5e-8 <= 1e-6 -> Pass
        result = OutputChecker.compare(actual, expected, float_epsilon=1e-6)
        self.assertTrue(result.passed)

    def test_token_mismatch(self):
        actual = "1 2 4"
        expected = "1 2 3"
        result = OutputChecker.compare(actual, expected)
        self.assertFalse(result.passed)
        self.assertIn("Wrong Answer", result.verdict)
        self.assertIn("`3`", result.details or "")
        self.assertIn("`4`", result.details or "")


if __name__ == "__main__":
    unittest.main()
