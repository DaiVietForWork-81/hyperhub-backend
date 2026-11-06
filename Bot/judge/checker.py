"""Output verification and comparison checker with 100% Vietnamese diagnostic messages."""

from dataclasses import dataclass


from cpp_core.bridge import fast_compare_output


@dataclass
class CheckResult:
    passed: bool
    verdict: str  # "Chấp nhận (Accepted)", "Kết quả sai (Wrong Answer)"
    details: str | None = None
    expected_preview: str | None = None
    actual_preview: str | None = None


class OutputChecker:
    """Kiểm tra và so khớp đầu ra của chương trình thí sinh với kết quả kỳ vọng."""

    @classmethod
    def compare(
        cls,
        actual: str,
        expected: str,
        float_epsilon: float = 1e-6,
    ) -> CheckResult:
        """
        So khớp chuẩn theo từng từ khóa (token-by-token):
        - Tối ưu hóa tốc độ cao qua C++ Native Core (với Fallback Python thuần)
        - Bỏ qua khoảng trắng thừa và ký tự xuống dòng
        - So sánh số thực với sai số epsilon cho phép
        - Thông báo lỗi chi tiết bằng tiếng Việt
        """
        passed, verdict, details = fast_compare_output(
            actual=actual,
            expected=expected,
            float_epsilon=float_epsilon,
        )
        return CheckResult(
            passed=passed,
            verdict=verdict,
            details=details,
            expected_preview=cls._truncate(expected),
            actual_preview=cls._truncate(actual),
        )

    @staticmethod
    def _truncate(text: str, max_chars: int = 120) -> str:
        text = text.strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."
