"""AI-generated code heuristic detector integrating stylometric analysis, LLM signature patterns, and CP heuristics."""

import re
from re import Pattern

# Cố gắng tích hợp ai_slopcheck nếu khả dụng
try:
    import ai_slopcheck

    HAS_AI_SLOPCHECK = True
except ImportError:
    HAS_AI_SLOPCHECK = False

from cpp_core.bridge import fast_code_metrics, calculate_entropy, IS_NATIVE_ACCELERATED


class AIDetector:
    """
    Bộ phân tích mã nguồn phát hiện AI/LLM đa tầng (Multi-Layer AI Detector):
    - Tầng 1: Rò rỉ chữ ký trực tiếp từ Chatbot (Direct Chatbot Leaks & Markdown artifacts).
    - Tầng 2: Đặc trưng hành văn giải thuật LLM (Time/Space complexity, Step-by-step comments).
    - Tầng 3: Phong cách đặt tên biến lý thuyết & Docstring Enterprise quá mức.
    - Tầng 4: Bộ lọc chống gắn cờ oan (Human CP Heuristics Discount) dựa trên thói quen Competitive Programming.

    Thang đo điểm nghi vấn (0 - 100):
      • 0 - 29:   Bình thường (Mã nguồn tự nhiên, phong cách CP đích thực)
      • 30 - 59:  Nghi vấn nhẹ (Có một số comment / tên biến sách giáo khoa)
      • 60 - 69:  Đáng ngờ (Cấu trúc tương đồng với template LLM)
      • 70 - 100: Cực kỳ đáng ngờ (Phát hiện mã nguồn sao chép từ AI)
    """

    # ── TẦNG 1 & 2: DẤU HIỆU RÒ RỈ CHATBOT & COMMENT GIẢI THUẬT SÁCH GIÁO KHOA ──
    _COMPILED_COMMENT_PATTERNS: list[tuple[Pattern, int, str]] = [
        (
            re.compile(r"(?i)\btime\s+complexity\s*:\s*O\(", re.MULTILINE),
            30,
            "Độ phức tạp thời gian chuẩn định dạng LLM (`Time Complexity: O(...)`)",
        ),
        (
            re.compile(r"(?i)\bspace\s+complexity\s*:\s*O\(", re.MULTILINE),
            30,
            "Độ phức tạp bộ nhớ chuẩn định dạng LLM (`Space Complexity: O(...)`)",
        ),
        (
            re.compile(
                r"(?i)\bhere\s+is\s+the\s+(complete\s+)?(c\+\+|python|java|rust|go|solution|code)",
                re.MULTILINE,
            ),
            40,
            "Câu mở đầu đặc trưng của ChatGPT ('Here is the complete solution...')",
        ),
        (
            re.compile(
                r"(?i)\blet['’]?s\s+(break\s+down|analyze|explain|understand)",
                re.MULTILINE,
            ),
            25,
            "Câu hướng dẫn phân tích của AI ('Let's break down...')",
        ),
        (
            re.compile(
                r"(?i)\bin\s+this\s+(approach|solution|problem|implementation),?\s+we",
                re.MULTILINE,
            ),
            20,
            "Mẫu giải thích thuật toán kiểu sách giáo khoa ('In this approach, we...')",
        ),
        (
            re.compile(r"(?i)\bstep\s+[1-9]\s*:\s*", re.MULTILINE),
            15,
            "Chia bước giải thích Step 1 / Step 2 của LLM",
        ),
        (
            re.compile(r"(?i)\balgorithm\s+explanation\s*:", re.MULTILINE),
            25,
            "Mục giải thích thuật toán ('Algorithm explanation:')",
        ),
        (
            re.compile(r"(?i)\bbase\s+cases?\s*:\s*", re.MULTILINE),
            15,
            "Mô tả trường hợp cơ sở kiểu AI ('Base case:')",
        ),
        (
            re.compile(r"(?i)\bto\s+solve\s+this\s+problem,?\s+we\s+can", re.MULTILINE),
            20,
            "Câu mở bài giải thích của AI ('To solve this problem, we can...')",
        ),
        (
            re.compile(
                r"(?i)\bnote\s+that\s+we\s+(use|handle|can|need|should)", re.MULTILINE
            ),
            15,
            "Ghi chú phân tích của AI ('Note that we use...')",
        ),
        (
            re.compile(r"(?i)\bthis\s+ensures\s+that\s+we\s+avoid", re.MULTILINE),
            15,
            "Câu khẳng định tính đúng đắn ('This ensures that we avoid...')",
        ),
        (
            re.compile(r"(?i)\bthe\s+overall\s+time\s+complexity\s+is", re.MULTILINE),
            25,
            "Tổng kết độ phức tạp ('The overall time complexity is...')",
        ),
        (
            re.compile(r"(?i)```(cpp|python|java|rust|go|c\+\+|py)?", re.MULTILINE),
            45,
            "Dấu Markdown codeblock bị rò rỉ khi sao chép từ chatbot (```)",
        ),
        (
            re.compile(r"(?i)\bfeel\s+free\s+to\s+ask", re.MULTILINE),
            40,
            "Câu kết chatbot ('Feel free to ask...')",
        ),
        (
            re.compile(r"(?i)\bhope\s+this\s+helps", re.MULTILINE),
            40,
            "Câu chào kết thúc chatbot ('Hope this helps!')",
        ),
        (
            re.compile(r"(?i)\b(intuition|approach|dry\s+run)\s*:\s*", re.MULTILINE),
            20,
            "Cấu trúc phân tích LeetCode/ChatGPT ('Intuition:', 'Approach:')",
        ),
        (
            re.compile(
                r"(?i)\bhelper\s+function\s+to\s+(solve|check|calculate|find)",
                re.MULTILINE,
            ),
            20,
            "Mô tả hàm phụ trợ kiểu LLM ('Helper function to solve...')",
        ),
        (
            re.compile(
                r"(?i)\bread\s+input\s+(values|data|from\s+stdin)", re.MULTILINE
            ),
            15,
            "Chú thích từng bước cơ bản ('Read input values...')",
        ),
        (
            re.compile(
                r"(?i)\bprint\s+the\s+(final\s+)?(result|answer|output)", re.MULTILINE
            ),
            15,
            "Chú thích bước in output ('Print the result...')",
        ),
        (
            re.compile(r"(?i)\bcorner\s+cases?\s*:\s*", re.MULTILINE),
            15,
            "Chú thích trường hợp đặc biệt ('Corner case:')",
        ),
        (
            re.compile(
                r"(?i)\b(driver\s+code|driver\s+program|main\s+driver\s+function)",
                re.MULTILINE,
            ),
            20,
            "Chú thích Driver Code đặc trưng ChatGPT",
        ),
    ]

    # ── TẦNG 3: TÊN BIẾN LÝ THUYẾT GIÁO TRÌNH QUÁ DÀI DÒNG ──
    _COMPILED_VERBOSE_PATTERNS: list[tuple[Pattern, str]] = [
        (
            re.compile(r"\boptimal_substructure\b", re.IGNORECASE),
            "optimal_substructure",
        ),
        (
            re.compile(r"\boverlapping_subproblems\b", re.IGNORECASE),
            "overlapping_subproblems",
        ),
        (re.compile(r"\bmemoization_table\b", re.IGNORECASE), "memoization_table"),
        (
            re.compile(r"\badjacency_list_graph\b", re.IGNORECASE),
            "adjacency_list_graph",
        ),
        (
            re.compile(r"\bvisited_array_tracker\b", re.IGNORECASE),
            "visited_array_tracker",
        ),
        (
            re.compile(r"\bdisjoint_set_union_find\b", re.IGNORECASE),
            "disjoint_set_union_find",
        ),
        (re.compile(r"\binput_number_count\b", re.IGNORECASE), "input_number_count"),
        (
            re.compile(r"\btarget_sum_accumulator\b", re.IGNORECASE),
            "target_sum_accumulator",
        ),
        (
            re.compile(r"\bcurrent_subarray_sum\b", re.IGNORECASE),
            "current_subarray_sum",
        ),
        (
            re.compile(r"\bmaximum_subarray_sum\b", re.IGNORECASE),
            "maximum_subarray_sum",
        ),
        (re.compile(r"\bnumber_of_elements\b", re.IGNORECASE), "number_of_elements"),
        (
            re.compile(r"\bpriority_queue_min_heap\b", re.IGNORECASE),
            "priority_queue_min_heap",
        ),
    ]

    # ── TẦNG 4: DẤU HIỆU CODE CP NGƯỜI THẬT (HUMAN CP HEURISTICS - GIẢM ĐIỂM NGHI VẤN) ──
    _CP_HUMAN_PATTERNS: list[tuple[Pattern, int, str]] = [
        (
            re.compile(r"#include\s*<bits/stdc\+\+\.h>"),
            10,
            "Header siêu thư viện chuẩn CP (`#include <bits/stdc++.h>`)",
        ),
        (
            re.compile(
                r"(#define\s+int\s+long\s+long|using\s+ll\s*=\s*long\s+long|typedef\s+long\s+long\s+ll;)"
            ),
            15,
            "Định nghĩa kiểu số nguyên chuẩn CP (`ll / int long long`)",
        ),
        (
            re.compile(r"#define\s+(pb|fi|se|all|sz|rep|FOR|debug)\b"),
            15,
            "Sử dụng macro viết tắt Competitive Programming (`pb, fi, se, all`)",
        ),
        (
            re.compile(r"(ios_base::sync_with_stdio|cin\.tie|sys\.stdin\.readline)"),
            5,
            "Cấu hình Fast I/O ngắn gọn chuẩn thi đấu",
        ),
        (
            re.compile(
                r"(//|#)\s*(nhap|tinh|xuat|kiem tra|dap an|dem|tong|chay|quy hoach dong)",
                re.IGNORECASE,
            ),
            15,
            "Chú thích tiếng Việt tự nhiên của thí sinh",
        ),
    ]

    _PYTHON_DOCSTRING_PATTERN = re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')')
    _PYTHON_ENTERPRISE_DOC_PATTERN = re.compile(
        r"(?i)(Args\s*:|Returns\s*:|Parameters\s*:|Raises\s*:)"
    )

    @classmethod
    def analyze(cls, code: str, language: str = "") -> dict[str, object]:
        """
        Quét mã nguồn và tính toán điểm nghi vấn AI đa tầng (0 - 100) kèm chẩn đoán tiếng Việt chi tiết.
        Tối ưu tốc độ cao và áp dụng bộ lọc giảm trừ điểm cho thói quen CP người thật.
        """
        if not code or len(code.strip()) == 0:
            return {
                "score": 0,
                "status": "Bình thường",
                "signals": [],
                "is_flagged": False,
                "has_slopcheck": HAS_AI_SLOPCHECK,
                "entropy": 0.0,
                "native_accelerated": IS_NATIVE_ACCELERATED,
            }

        metrics = fast_code_metrics(code)
        score = 0
        signals: list[str] = []
        total_lines = max(1, metrics["lines"])

        # 1. Quét các mẫu chữ ký văn phong Chatbot & AI
        for regex, weight, desc in cls._COMPILED_COMMENT_PATTERNS:
            matches = regex.findall(code)
            if matches:
                matched_count = len(matches)
                added_score = min(weight * matched_count, weight * 2)
                score += added_score
                signals.append(f"{desc} (+{added_score})")

        # 2. Tỷ lệ dòng chú thích (Comment Density) - Sử dụng metrics từ C++ Native Core
        comment_ratio = metrics["comment_ratio"]
        if comment_ratio > 0.45 and total_lines > 12:
            score += 25
            signals.append(
                f"Mật độ chú thích bất thường ({int(comment_ratio * 100)}% tổng số dòng) (+25)"
            )
        elif comment_ratio > 0.30 and total_lines > 12:
            score += 15
            signals.append(
                f"Mật độ chú thích cao ({int(comment_ratio * 100)}% tổng số dòng) (+15)"
            )

        # 3. Quét Docstring dài & định dạng Enterprise (Args:/Returns:) trong Python
        docstrings = cls._PYTHON_DOCSTRING_PATTERN.findall(code)
        docstring_chars = sum(len(ds) for ds in docstrings)
        if docstring_chars > 150:
            score += 20
            signals.append(
                f"Chứa docstring giải thích chi tiết bất thường ({docstring_chars} ký tự) (+20)"
            )
        if any(cls._PYTHON_ENTERPRISE_DOC_PATTERN.search(ds) for ds in docstrings):
            score += 20
            signals.append(
                "Định dạng docstring chuẩn tài liệu Enterprise (`Args: / Returns:`) (+20)"
            )

        # 4. Quét tên biến / cấu trúc giáo trình lý thuyết AI
        for regex, name in cls._COMPILED_VERBOSE_PATTERNS:
            if regex.search(code):
                score += 10
                signals.append(f"Tên biến/cấu trúc lý thuyết mẫu `{name}` (+10)")

        # 5. Áp dụng Bộ Lọc Giảm Trừ Điểm cho Thói Quen CP Người Thật (Chống False Positive)
        discount = 0
        for regex, disc_val, desc in cls._CP_HUMAN_PATTERNS:
            if regex.search(code):
                discount += disc_val

        # Nếu code mang phong cách CP đích thực, giảm bớt điểm nghi vấn
        if discount > 0 and score > 0:
            actual_discount = min(score, discount)
            score -= actual_discount

        # 6. Giới hạn thang điểm 0 - 100
        score = min(100, max(0, score))

        # Phân loại mức độ theo thang điểm chuẩn
        if score >= 70:
            status = "Cực kỳ đáng ngờ"
        elif score >= 60:
            status = "Rất đáng ngờ"
        elif score >= 30:
            status = "Nghi vấn nhẹ"
        else:
            status = "Bình thường"

        return {
            "score": score,
            "status": status,
            "signals": signals,
            "is_flagged": score >= 70,
            "has_slopcheck": HAS_AI_SLOPCHECK,
            "entropy": metrics["entropy"],
            "native_accelerated": IS_NATIVE_ACCELERATED,
        }
