"""Static complexity analyzer checking loops, recursions, and constraints with Vietnamese warnings."""

import ast
import re


class StaticComplexityAnalyzer:
    """
    Phân tích tĩnh cây cú pháp (AST) / cấu trúc code để ước tính độ phức tạp thời gian
    và cảnh báo thuật toán duyệt trâu (Brute-force) khi giới hạn dữ liệu lớn.
    Lưu ý: Thời gian chạy thực tế trong Sandbox luôn được ưu tiên hơn phân tích tĩnh.
    """

    @classmethod
    def analyze(
        cls, code: str, language: str, constraint_n: int | None = None
    ) -> dict[str, object]:
        """
        Phân tích độ phức tạp mã nguồn và cảnh báo nếu có nguy cơ TLE so với giới hạn N.
        """
        loop_depth = cls._estimate_loop_depth(code, language)
        estimated_complexity = cls._map_depth_to_complexity(loop_depth)

        warnings: list[str] = []
        is_suspicious_tle = False

        effective_n = constraint_n or 200000
        if effective_n >= 100000 and loop_depth >= 2:
            warnings.append(
                f"⚠️ Nguy cơ TLE: Phát hiện vòng lặp lồng nhau (ước tính {estimated_complexity}) "
                f"trên dữ liệu N ≈ {effective_n:,}. Bài toán yêu cầu thuật toán tối ưu O(N log N) hoặc O(N)."
            )
            is_suspicious_tle = True

        return {
            "max_loop_depth": loop_depth,
            "estimated_complexity": estimated_complexity,
            "warnings": warnings,
            "is_suspicious_tle": is_suspicious_tle,
        }

    @classmethod
    def _estimate_loop_depth(cls, code: str, language: str) -> int:
        """Ước lượng độ sâu vòng lặp lồng nhau tối đa."""
        lang = language.lower()
        if "python" in lang:
            return cls._analyze_python_ast(code)
        else:
            return cls._analyze_regex_braces(code)

    @classmethod
    def _analyze_python_ast(cls, code: str) -> int:
        """Dùng AST Python để duyệt chính xác cấu trúc vòng lặp."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return cls._analyze_regex_indent(code)

        max_depth = 0

        def traverse(node: ast.AST, current_depth: int):
            nonlocal max_depth
            is_loop = isinstance(node, (ast.For, ast.While))
            new_depth = current_depth + (1 if is_loop else 0)
            max_depth = max(max_depth, new_depth)

            for child in ast.iter_child_nodes(node):
                traverse(child, new_depth)

        traverse(tree, 0)
        return max_depth

    @classmethod
    def _analyze_regex_indent(cls, code: str) -> int:
        lines = code.split("\n")
        loop_levels = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith("for ") or stripped.startswith("while "):
                indent = len(line) - len(stripped)
                loop_levels.append(indent)
        return len(loop_levels)

    @classmethod
    def _analyze_regex_braces(cls, code: str) -> int:
        lines = code.split("\n")
        max_depth = 0
        current_depth = 0

        for line in lines:
            line = re.sub(r"//.*$", "", line)
            if re.search(r"\b(for|while)\s*\(", line):
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            if "}" in line and current_depth > 0:
                current_depth = max(0, current_depth - line.count("}"))

        return max_depth

    @staticmethod
    def _map_depth_to_complexity(depth: int) -> str:
        if depth == 0:
            return "O(1)"
        elif depth == 1:
            return "O(N)"
        elif depth == 2:
            return "O(N²)"
        elif depth == 3:
            return "O(N³)"
        else:
            return f"O(N^{depth})"
