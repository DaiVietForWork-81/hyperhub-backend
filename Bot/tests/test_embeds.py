"""Test chia tin nhắn dài theo ranh giới từ (utils/embeds.py)."""

import unittest

from utils.embeds import MAX_PLAIN_MSG_LEN, split_by_words, split_long_text


class TestSplitByWords(unittest.TestCase):
    def test_short_text_single_chunk(self):
        self.assertEqual(split_by_words("hello"), ["hello"])

    def test_chunks_within_limit(self):
        text = ("từ vựng tiếng Việt " * 300).strip()
        parts = split_by_words(text)
        self.assertTrue(len(parts) > 1)
        for p in parts:
            self.assertLessEqual(len(p), MAX_PLAIN_MSG_LEN)

    def test_no_mid_word_cut(self):
        text = ("abcdefghij " * 500).strip()
        parts = split_by_words(text, max_len=100)
        for p in parts:
            self.assertLessEqual(len(p), 100)
            # Mỗi chunk phải kết thúc bằng từ nguyên vẹn
            self.assertTrue(p.endswith("abcdefghij"))

    def test_paragraph_boundary_preferred(self):
        para = "Nội dung đoạn văn. " * 20
        text = f"{para}\n\n{para}\n\n{para}"
        parts = split_by_words(text, max_len=500)
        self.assertTrue(len(parts) >= 2)
        for p in parts:
            self.assertLessEqual(len(p), 500)

    def test_long_single_word_hard_cut(self):
        text = "x" * 2500
        parts = split_by_words(text)
        self.assertEqual(len(parts), 2)
        self.assertEqual(len("".join(parts)), 2500)

    def test_empty_text(self):
        self.assertEqual(split_by_words(""), [""])

    def test_roundtrip_no_loss(self):
        text = ("Câu tiếng Việt có dấu. " * 200).strip() + "\n\nĐoạn hai.\nDòng hai."
        parts = split_by_words(text)
        rejoined = " ".join(" ".join(p.split()) for p in parts)
        self.assertEqual(rejoined, " ".join(text.split()))

    def test_split_long_text_no_crash(self):
        # Regression: split_long_text từng thiếu `import re` -> NameError
        para = "Câu dài không xuống dòng. " * 500
        parts = split_long_text(para.strip(), max_len=1000)
        self.assertTrue(len(parts) > 1)
        for p in parts:
            self.assertLessEqual(len(p), 1000)


if __name__ == "__main__":
    unittest.main()
