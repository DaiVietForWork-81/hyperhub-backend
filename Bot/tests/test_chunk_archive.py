"""Unit tests for chunk_archive offload (split/limit/path safety). No network, no Discord."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.chunk_archive import find_local_file, get_chunk_size_limit, split_bytes


class TestChunkArchive(unittest.TestCase):
    def test_chunk_size_limit_safe(self):
        limit = get_chunk_size_limit()
        # Da do thuc te: 20MiB OK, 24MB 413 -> chot 20.000.000
        self.assertEqual(limit, 20 * 1000 * 1000)

    def test_split_bytes_boundaries(self):
        data = bytes(range(256)) * 100  # 25600 bytes
        parts = split_bytes(data, 10000)
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(len(p) <= 10000 for p in parts))
        self.assertEqual(b"".join(parts), data)

    def test_split_exact_multiple(self):
        data = b"x" * 20000
        parts = split_bytes(data, 10000)
        self.assertEqual(len(parts), 2)
        self.assertEqual(b"".join(parts), data)

    def test_split_smaller_than_chunk(self):
        data = b"abc"
        parts = split_bytes(data, 10000)
        self.assertEqual(parts, [b"abc"])

    def test_find_local_file_traversal_guard(self):
        # Ten file chua .. khong duoc thoat khoi uploads/
        self.assertIsNone(find_local_file(1, "../../bot.db"))
        self.assertIsNone(find_local_file(999999, "khong_ton_tai.pdf"))


if __name__ == "__main__":
    unittest.main()
