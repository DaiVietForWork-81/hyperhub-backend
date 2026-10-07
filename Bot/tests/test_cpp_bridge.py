"""
Unit tests for C++ Native Acceleration Engine & Python Bridge (cpp_core).
"""

import pytest
from cpp_core.bridge import (
    IS_NATIVE_ACCELERATED,
    calculate_entropy,
    fast_code_metrics,
    fast_compare_output,
    fast_similarity,
    _py_calculate_entropy,
    _py_code_metrics,
    _py_compare_output,
    _py_levenshtein_similarity,
)


class TestCppBridgeEntropy:
    """Kiểm tra hàm tính Shannon Entropy."""

    def test_empty_string(self):
        assert calculate_entropy("") == 0.0
        assert _py_calculate_entropy("") == 0.0

    def test_single_repeated_char(self):
        # Chuỗi toàn 1 ký tự duy nhất -> entropy = 0.0
        text = "AAAAAAAAAA"
        assert calculate_entropy(text) == 0.0
        assert _py_calculate_entropy(text) == 0.0

    def test_uniform_distribution(self):
        # 4 ký tự phân bố đều -> entropy = -4 * (0.25 * log2(0.25)) = 2.0
        text = "ABCD"
        val = calculate_entropy(text)
        assert pytest.approx(val, 0.01) == 2.0

    def test_python_and_native_consistency(self):
        sample = """
        #include <iostream>
        using namespace std;
        int main() {
            int n; cin >> n;
            cout << n * 2 << endl;
            return 0;
        }
        """
        py_val = _py_calculate_entropy(sample)
        bridge_val = calculate_entropy(sample)
        assert pytest.approx(bridge_val, 0.01) == py_val


class TestCppBridgeCodeMetrics:
    """Kiểm tra hàm trích xuất chỉ số mã nguồn."""

    def test_empty_code(self):
        res = fast_code_metrics("")
        assert res["lines"] == 0
        assert res["comment_lines"] == 0
        assert res["blank_lines"] == 0

    def test_metrics_extraction(self):
        code = (
            "// Comment line 1\n"
            "/* Comment line 2 */\n"
            "# Comment line 3\n"
            "\n"
            "int a = 10;\n"
            "int b = 20;\n"
        )
        res = fast_code_metrics(code)
        assert res["lines"] == 6
        assert res["comment_lines"] == 3
        assert res["blank_lines"] == 1
        assert res["comment_ratio"] == pytest.approx(3 / 6, 0.01)


class TestCppBridgeOutputCompare:
    """Kiểm tra so khớp kết quả đầu ra."""

    def test_exact_match(self):
        actual = "1 2 3 4 5\n"
        expected = "1 2 3   4 5"
        passed, verdict, _ = fast_compare_output(actual, expected)
        assert passed is True
        assert "Accepted" in verdict

    def test_float_epsilon_match(self):
        actual = "3.1415926"
        expected = "3.1415927"
        passed, verdict, _ = fast_compare_output(actual, expected, float_epsilon=1e-5)
        assert passed is True
        assert "Accepted" in verdict

    def test_float_epsilon_fail(self):
        actual = "3.14"
        expected = "3.1415926"
        passed, verdict, details = fast_compare_output(actual, expected, float_epsilon=1e-5)
        assert passed is False
        assert "Wrong Answer" in verdict
        assert "Sai số thực" in details

    def test_token_count_mismatch(self):
        actual = "1 2 3"
        expected = "1 2 3 4"
        passed, verdict, details = fast_compare_output(actual, expected)
        assert passed is False
        assert "Thiếu dữ liệu" in details

    def test_string_token_mismatch(self):
        actual = "YES"
        expected = "NO"
        passed, verdict, details = fast_compare_output(actual, expected)
        assert passed is False
        assert "Giá trị không khớp" in details


class TestCppBridgeSimilarity:
    """Kiểm tra tính độ tương đồng Levenshtein."""

    def test_identical_strings(self):
        assert fast_similarity("hello world", "hello world") == 1.0

    def test_completely_different(self):
        assert fast_similarity("", "abc") == 0.0

    def test_partial_similarity(self):
        sim = fast_similarity("abcdef", "abcxyz")
        assert 0.4 <= sim <= 0.6


class TestCppBridgeAIHelpers:
    """Kiểm tra các hàm C++ tăng tốc xử lý AI."""

    def test_clean_think_tags(self):
        from cpp_core.bridge import clean_think_tags, _py_clean_think_tags

        raw = "<think>Đây là khối suy luận nội bộ của Qwen</think>Xin chào, tôi là AI!"
        expected = "Xin chào, tôi là AI!"
        assert clean_think_tags(raw).strip() == expected
        assert _py_clean_think_tags(raw).strip() == expected

    def test_dedup_words(self):
        from cpp_core.bridge import dedup_words, _py_dedup_words

        raw = "Bạn bạn hãy giải giải bài toán này nhé nhé"
        expected = "Bạn hãy giải bài toán này nhé"
        assert dedup_words(raw).strip() == expected
        assert _py_dedup_words(raw).strip() == expected

    def test_fast_extract_json(self):
        from cpp_core.bridge import fast_extract_json, _py_extract_json
        import json

        raw = 'Đây là kết quả:\n```json\n{"id": "t1", "name": "Bai toan", "arr": [1, 2, ],}\n```\nHy vọng giúp ích!'
        cleaned = fast_extract_json(raw)
        data = json.loads(cleaned)
        assert data["id"] == "t1"
        assert data["name"] == "Bai toan"
        assert data["arr"] == [1, 2]
