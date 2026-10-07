"""
services/problem_types.py
Định nghĩa kiểu dữ liệu bài toán (DuelProblem) dùng chung cho AI Generator.
Tách riêng khỏi duel_service để có thể dùng mà không cần kích hoạt tính năng thi đấu.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DuelProblem:
    """Represents a competitive programming algorithmic problem."""

    id: str
    name: str
    tier: str  # T8, T7, T6, T5, T4, T3, LT2, MT2, HT2, LT1, MT1, HT1
    division: str  # Div. 4, Div. 3, Div. 2, Div. 1
    rating_display: str  # e.g. "T8 / Rating: 300 pts"
    statement: str
    input_format: str
    output_format: str
    constraints: str
    sample_input: str
    sample_output: str
    secret_tests: list[dict[str, str]] = field(default_factory=list)
    time_limit_minutes: int = 15
    max_code_size_kb: int = 64
    editorial: str = ""
    hint: str = (
        "💡 Gợi ý: Đọc kỹ điều kiện bài toán và kiểm tra các trường hợp biên đặc biệt!"
    )
    solution_code: str = ""
    solution_cpp: str = ""
    solution_py: str = ""
    image_url: str | None = None
    rating: int = 800
    tags: list[str] = field(default_factory=list)
    time_limit_sec: float = 1.0
    memory_limit_mb: int = 256
    sample_explanation: str = ""

    @property
    def editorial_text(self) -> str:
        """Trả về hướng dẫn thuật toán, không lộ mã nguồn đáp án."""
        if self.editorial:
            return self.editorial.strip()
        return (
            f"🧠 **Ý TƯỞNG THUẬT TOÁN TRỌNG TÂM:**\n"
            f"{self.hint}\n\n"
            f"⚙️ **PHÂN TÍCH TIẾP CẬN & CẤU TRÚC DỮ LIỆU:**\n"
            f"• Xem xét kỹ ràng buộc dữ liệu ({self.constraints.split('.')[0] if '.' in self.constraints else self.constraints}) "
            f"để lựa chọn thuật toán có độ phức tạp phù hợp.\n\n"
            f"⚠️ **CÁC TRƯỜNG HỢP BIÊN:**\n"
            f"• Kiểm tra: N=1, giá trị âm, mảng đã sắp xếp, đồ thị không liên thông.\n"
            f"• Chú ý nguy cơ tràn số nguyên 64-bit (long long / int64)."
        )
