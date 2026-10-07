"""Unit tests for Codeforces API client signature calculation and parameters."""

import hashlib
import unittest

from services.codeforces_api import CodeforcesAPI


class TestCodeforcesAPI(unittest.TestCase):

    def test_api_sig_generation(self):
        client = CodeforcesAPI(api_key="mock_key", api_secret="mock_secret")
        method = "user.info"
        params = {"handles": "tourist", "time": 1600000000, "apiKey": "mock_key"}

        sig = client._generate_api_sig(method, params)
        self.assertEqual(
            len(sig), 6 + 128
        )  # 6 char random prefix + 128 hex chars (SHA-512)

        rand = sig[:6]
        expected_hash_part = sig[6:]

        sorted_params = sorted(params.items())
        query_str = "&".join(f"{k}={v}" for k, v in sorted_params)
        to_hash = f"{rand}/{method}?{query_str}#mock_secret"
        expected_hex = hashlib.sha512(to_hash.encode("utf-8")).hexdigest()

        self.assertEqual(expected_hash_part, expected_hex)

    def test_easy_verify_problems_pool(self):
        from cogs.codeforces import EASY_VERIFY_PROBLEMS

        self.assertGreaterEqual(len(EASY_VERIFY_PROBLEMS), 5)
        for prob in EASY_VERIFY_PROBLEMS:
            self.assertIn("contest_id", prob)
            self.assertIn("index", prob)
            self.assertIn("name", prob)
            self.assertIn("url", prob)
            self.assertIn("cpp", prob)
            self.assertIn("py", prob)
            self.assertTrue(prob["url"].startswith("https://codeforces.com/"))


if __name__ == "__main__":
    unittest.main()
