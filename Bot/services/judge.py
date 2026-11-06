"""Mode 2 Judge Orchestrator with Event Bonus, Already-Solved Protection, Detailed Error Diagnostics, and Fix Guides."""

import asyncio
import os
import shutil
import tempfile
import time
from dataclasses import dataclass

import discord

from config.settings import settings
from database.database import async_session_factory
from database.repositories.rating_repo import RatingRepository
from database.repositories.submission_repo import SubmissionRepository
from database.repositories.user_repo import UserRepository
from judge.checker import OutputChecker
from judge.languages import get_language_by_alias
from judge.sandbox import CodeSandbox, ExecutionResult
from judge.static_analyzer import StaticComplexityAnalyzer
from judge.testcase_generator import TestcaseGenerator
from services.ai_detector import AIDetector
from services.codeforces_api import cf_api
from services.hardware_profiler import HardwareProfile, ResourceGovernor
from services.problem_fetcher import ProblemData, ProblemFetcher
from services.rank import (
    get_rank_badge,
    get_rank_by_rating,
    is_rank_sufficient,
)
from services.rating import RatingEngine
from services.role_manager import RoleManager
from utils.cooldown import duplicate_guard, submission_cooldown
from utils.embeds import EmbedType, create_embed, generate_progress_bar
from utils.logger import get_logger
from utils.permissions import is_owner_user

logger = get_logger("JudgeService")

# ============================================================================
# CHÍNH SÁCH LIÊM CHÍNH (bất di bất dịch trừ khi chủ ý đổi + review con người):
# - Điểm nghi vấn AI là heuristic XÁC SUẤT (dễ false positive, thiên vị phong
#   cách viết) nên KHÔNG BAO GIỜ được dùng để tự động hủy bài, trừ điểm hay
#   cấm thi đấu. Nghi vấn cao chỉ gắn cờ cho mod xem xét thủ công.
# - Giữ False vĩnh viễn. Test test_ai_fairness.py khóa điều này.
# ============================================================================
AI_AUTO_PUNISH_ENABLED = False


@dataclass
class JudgeResponse:
    success: bool
    verdict: str
    embed: discord.Embed
    analysis_embed: discord.Embed | None
    tests_passed: int
    total_tests: int
    score_earned: float
    rating_delta: int


def get_error_diagnostic_and_fix(
    verdict: str, failed_reason: str, language: str, problem: ProblemData
) -> tuple[str, str]:
    """Phân tích nguyên nhân lỗi và đưa ra hướng dẫn khắc phục cụ thể cho thí sinh."""
    v_lower = verdict.lower()
    lang_lower = language.lower()

    if "wrong answer" in v_lower or "kết quả sai" in v_lower:
        detail = (
            failed_reason
            or "Chương trình trả về kết quả không khớp với đáp án mẫu tại một test case."
        )
        fix = (
            "• 🔢 **Kiểm tra kiểu dữ liệu & Tràn số:** Dùng `long long` (C++) hoặc `BigInteger` khi tính tổng/tích lớn (`N * M > 2 * 10^9`).\n"
            "• 🎯 **Trường hợp biên (Corner Cases):** Thử kiểm tra các trường hợp `N = 0, 1`, mảng rỗng, số âm, số lẻ/chẵn, hoặc giá trị lớn nhất theo giới hạn đề bài.\n"
            "• 🧮 **Độ chính xác số thực:** Nếu bài toán yêu cầu in số thực, hãy sử dụng `double` hoặc `long double` kèm định dạng `fixed << setprecision(9)` (C++) hoặc `%.9f` (Python).\n"
            "• 📌 **Chỉ số mảng:** Kiểm tra mảng được đánh số từ `0` hay từ `1`."
        )
    elif "tle" in v_lower or "thời gian" in v_lower:
        detail = (
            failed_reason
            or f"Thời gian thực thi vượt quá giới hạn {problem.time_limit}s cho phép."
        )
        if "python" in lang_lower:
            io_tip = "• 🚀 **Fast I/O trong Python:** Thêm `import sys; input = sys.stdin.readline` ở đầu file thay cho `input()`."
        else:
            io_tip = "• 🚀 **Fast I/O trong C++:** Thêm `ios_base::sync_with_stdio(false); cin.tie(NULL);` ở đầu hàm `main()` và thay `endl` bằng `'\\n'`."
        fix = (
            f"• ⚡ **Tối ưu độ phức tạp thuật toán:** Nếu `N >= 10^5`, thuật toán `O(N^2)` sẽ bị TLE. Hãy chuyển sang giải thuật `O(N log N)` hoặc `O(N)`.\n"
            f"{io_tip}\n"
            "• 🔁 **Kiểm tra vòng lặp vô hạn:** Đảm bảo biến đếm trong vòng lặp `while` luôn tiến tới điều kiện dừng."
        )
    elif "mle" in v_lower or "bộ nhớ" in v_lower:
        detail = (
            failed_reason
            or f"Bộ nhớ sử dụng vượt quá giới hạn {problem.memory_limit} MB cho phép."
        )
        fix = (
            "• 💾 **Tối ưu cấu trúc mảng:** Tránh khai báo mảng 2 chiều quá lớn (ví dụ: `int a[10000][10000]`). Hãy dùng mảng 1 chiều cuộn hoặc cấp phát động `vector`.\n"
            "• 🔁 **Tránh đệ quy quá sâu:** Hạn chế DFS đệ quy không kiểm soát trên đồ thị lớn để tránh tràn Stack bộ nhớ."
        )
    elif "rte" in v_lower or "thực thi" in v_lower:
        detail = (
            failed_reason
            or "Chương trình dừng đột ngột do lỗi ngoại lệ trong quá trình thực thi."
        )
        rec_tip = (
            "• 🐍 **Python Recursion Limit:** Thêm `import sys; sys.setrecursionlimit(200000)` nếu dùng đệ quy sâu."
            if "python" in lang_lower
            else "• 🚫 **Kiểm tra kích thước mảng:** Tăng kích thước mảng thêm một vài phần tử (ví dụ: `const int MAXN = 200005;`) để tránh tràn mảng."
        )
        fix = (
            "• 🚫 **Truy cập ngoài mảng (Index Out of Bounds):** Kiểm tra xem có truy cập chỉ số âm hoặc chỉ số `>= N` hay không.\n"
            "• 0️⃣ **Chia cho 0 (Division by Zero):** Kiểm tra mẫu số trước các phép toán `/` hoặc `%`.\n"
            f"{rec_tip}\n"
            "• 📦 **Con trỏ / Null Reference:** Đảm bảo dữ liệu đã được khởi tạo trước khi truy xuất."
        )
    elif "compilation" in v_lower or "biên dịch" in v_lower or "ce" in v_lower:
        detail = (
            failed_reason
            or "Chương trình không thể biên dịch do sai cú pháp hoặc thiếu thư viện."
        )
        fix = (
            "• 📦 **Thư viện & Header:** Đảm bảo đã khai báo đầy đủ các header như `#include <iostream>`, `#include <vector>`, `#include <algorithm>` hoặc `#include <bits/stdc++.h>` (C++).\n"
            "• 🏷️ **Cú pháp ngôn ngữ:** Kiểm tra xem có quên dấu chấm phẩy `;`, đóng ngoặc `}` hoặc đặt sai tên biến hay không."
        )
    else:
        detail = failed_reason or f"Trạng thái: {verdict}"
        fix = "• 🔍 Kiểm tra lại toàn bộ logic thuật toán, đọc kỹ đề bài và đối chiếu với các testcase mẫu."

    return detail, fix


def get_line_by_line_code_analysis(
    code: str,
    language: str,
    problem: ProblemData,
    verdict: str,
    is_accepted: bool,
    failed_test_type: str = "SAMPLE",
    execution_time: float = 0.0,
    memory_used_mb: float = 0.0,
) -> str:
    """
    Phân tích chi tiết từng dòng mã nguồn của thí sinh:
    - Đánh số từng dòng code (1-indexed).
    - Chỉ ra các bẫy lỗi tiềm ẩn: tràn số, nghẽn I/O, bẫy vòng lặp TLE O(N^2),
      truy cập mảng ngoài biên, chia cho 0, hardcode kết quả, hoặc đề xuất tối ưu.
    """
    if not code or not code.strip():
        return "• ⚠️ Mã nguồn rỗng hoặc không thể đọc được."

    lines = code.splitlines()
    lang_lower = language.lower()
    v_lower = verdict.lower()
    analysis_items: List[str] = []

    has_fast_io = (
        "ios_base::sync_with_stdio" in code
        or "cin.tie" in code
        or "sys.stdin.readline" in code
    )
    has_long_long = "long long" in code or "int64_t" in code

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if (
            not line
            or line.startswith("//")
            or line.startswith("#")
            or line.startswith("/*")
            or line.startswith("*")
        ):
            continue

        item_notes: List[str] = []

        # 1. Kiểm tra I/O (Input/Output)
        if "c++" in lang_lower or "cpp" in lang_lower:
            if "cin >>" in line and not has_fast_io:
                item_notes.append(
                    "Đọc `cin` thiếu Fast I/O (`ios_base::sync_with_stdio(false); cin.tie(NULL);`) ở đầu `main()`."
                )
            if "endl" in line:
                item_notes.append(
                    "Dùng `endl` gây flush bộ đệm liên tục làm chậm I/O, nên đổi sang `'\\n'`."
                )
        elif "python" in lang_lower or "py" in lang_lower:
            if "input(" in line and "sys.stdin.readline" not in code:
                item_notes.append(
                    "Dùng `input()` chậm. Nên dùng `import sys; input = sys.stdin.readline` để xử lý mảng lớn `10^5` nhanh hơn."
                )
        elif "java" in lang_lower:
            if "Scanner" in line:
                item_notes.append(
                    "`Scanner` trong Java xử lý I/O rất chậm, nên thay bằng `BufferedReader` và `StringTokenizer`."
                )
        elif "go" in lang_lower:
            if "fmt.Scan" in line:
                item_notes.append(
                    "`fmt.Scan` chậm trong Go, nên dùng `bufio.NewReader` và `bufio.NewWriter`."
                )
        elif "c" == lang_lower or "gcc" in lang_lower:
            if "gets(" in line:
                item_notes.append(
                    "Hàm `gets()` không an toàn và dễ gây tràn bộ đệm (Buffer Overflow), nên dùng `fgets()`."
                )

        # 2. Kiểm tra khai báo & Tràn số (Integer Overflow)
        if (
            "c++" in lang_lower
            or "cpp" in lang_lower
            or "c" == lang_lower
            or "gcc" in lang_lower
        ) and not has_long_long:
            if any(
                p in line
                for p in [
                    "int sum",
                    "int ans",
                    "int total",
                    "int cnt",
                    "int res",
                    "int prod",
                ]
            ):
                if any(op in line for op in ["*", "+=", "+"]):
                    item_notes.append(
                        "Nguy cơ tràn số kiểu `int` 32-bit (`> 2 * 10^9`) khi thực hiện phép tính lớn. Hãy đổi sang `long long`."
                    )
        elif "pascal" in lang_lower and "integer" in line:
            item_notes.append(
                "Kiểu `integer` trong Free Pascal có thể chỉ là 16-bit, nên dùng `longint` hoặc `int64`."
            )

        # 3. Kiểm tra vòng lặp & Nguy cơ TLE O(N^2)
        if line.startswith("for") or line.startswith("while"):
            nest_level = sum(
                1
                for prev in lines[: idx - 1]
                if prev.strip().startswith(("for", "while"))
            )
            if nest_level >= 1 and (
                "tle" in v_lower or "thời gian" in v_lower or not is_accepted
            ):
                item_notes.append(
                    f"Vòng lặp lồng nhau (Cấp độ {nest_level + 1}) có nguy cơ đạt `O(N^2)`, dễ bị TLE khi `N >= 10^5`."
                )
            elif "while" in line and ("true" in line.lower() or "1" in line):
                item_notes.append(
                    "Vòng lặp `while(true)` cần kiểm tra kỹ điều kiện thoát `break` tránh vòng lặp vô tận."
                )

        # 4. Kiểm tra truy cập mảng & Ngoại lệ Runtime Error
        if "[" in line and "]" in line and not is_accepted:
            if any(k in line for k in ["[-1]", "[i-1]", "[i+1]", "[n]"]):
                item_notes.append(
                    "Cần kiểm tra chỉ số mảng biên (`i - 1 < 0` hoặc `i >= N`) tránh lỗi Out of Bounds."
                )
        if any(op in line for op in [" / ", " % ", "/=", "%="]) and not is_accepted:
            if any(
                z in line
                for z in ["/ 0", "% 0", "/ n", "% n", "/ k", "% k", "/ b", "% b"]
            ):
                item_notes.append(
                    "Đảm bảo mẫu số khác 0 trước khi thực hiện phép chia `/` hoặc chia lấy dư `%`."
                )

        # 5. Kiểm tra Hardcode kết quả
        if not is_accepted:
            if line in [
                "print(0)",
                "print('NO')",
                "print('YES')",
                "cout << 0;",
                "cout << 0 << endl;",
            ]:
                item_notes.append(
                    "Kết quả in đang bị cố định (hardcoded), chưa tính toán tương thích với toàn bộ testcases."
                )

        # 6. Tối ưu bộ nhớ & Truyền tham số
        if (
            ("c++" in lang_lower or "cpp" in lang_lower)
            and "vector" in line
            and "(" in line
            and ")" in line
        ):
            if "&" not in line and "const" not in line and "void" in line:
                item_notes.append(
                    "Nên truyền `const vector<int>&` để tránh copy mảng tốn `O(N)` bộ nhớ."
                )

        if item_notes:
            code_snippet = line[:42] + ("..." if len(line) > 42 else "")
            analysis_items.append(
                f"• 📍 **Dòng {idx}:** `{code_snippet}`\n  ↳ " + " | ".join(item_notes)
            )

    if not analysis_items:
        for idx, raw_line in enumerate(lines[:6], start=1):
            line = raw_line.strip()
            if line and not line.startswith(("//", "#", "/*", "*")):
                code_snippet = line[:45]
                if is_accepted:
                    analysis_items.append(
                        f"• 🟢 **Dòng {idx}:** `{code_snippet}` — Xử lý logic chuẩn xác."
                    )
                else:
                    analysis_items.append(
                        f"• 🔍 **Dòng {idx}:** `{code_snippet}` — Cần rà soát các trường hợp biên & kiểu dữ liệu."
                    )

    return "\n".join(analysis_items[:8])


def get_rated_error_diagnostic_and_location(
    code: str,
    language: str,
    problem: ProblemData,
    verdict: str,
    failed_test_type: str = "SAMPLE",
    execution_time: float = 0.0,
    memory_used_mb: float = 0.0,
) -> tuple[str, str]:
    """
    Phân tích vị trí và nguyên nhân lỗi cho bài thi đấu Rated:
    - Chỉ ra dòng / đoạn code bị nghi vấn gặp lỗi.
    - TUYỆT ĐỐI KHÔNG hiển thị đáp án đúng / output mẫu / testcase nội bộ để bảo mật.
    """
    lang_lower = language.lower()
    v_lower = verdict.lower()
    locations: List[str] = []
    advice: List[str] = []

    if "tle" in v_lower or "thời gian" in v_lower:
        locations.append(
            "⏱️ **Vị trí nghẽn thời gian:** Khối vòng lặp thuật toán chính hoặc đọc/ghi I/O."
        )
        if "python" in lang_lower:
            if "sys.stdin.readline" not in code:
                locations.append(
                    "• 📍 **Đoạn I/O:** Đang dùng `input()` làm chậm quá trình nạp dữ liệu."
                )
        elif "c++" in lang_lower or "cpp" in lang_lower:
            if "ios_base::sync_with_stdio" not in code:
                locations.append(
                    "• 📍 **Đầu main():** Thiếu cấu hình Fast I/O `ios_base::sync_with_stdio(false); cin.tie(NULL);`."
                )
            if "endl" in code:
                locations.append(
                    "• 📍 **Lệnh in xuất:** Đang dùng `endl` gây nghẽn đệm liên tục."
                )
        advice.append(
            "• 💡 Cần tối ưu thuật toán giảm từ `O(N^2)` xuống `O(N log N)` hoặc `O(N)`."
        )
    elif "wrong answer" in v_lower or "kết quả sai" in v_lower:
        if failed_test_type == "EDGE_CASE":
            locations.append(
                "🎯 **Vị trí lỗi (Trường hợp biên):** Khối kiểm tra điều kiện đầu vào hoặc khởi tạo ban đầu (`N = 1`, mảng rỗng hoặc số âm)."
            )
        elif failed_test_type == "TLE_STRESS":
            locations.append(
                "🔢 **Vị trí lỗi (Dữ liệu cực đại):** Các phép toán nhân/tổng dồn có nguy cơ tràn số 32-bit `int`."
            )
        else:
            locations.append(
                "🧩 **Vị trí lỗi (Logic giải thuật):** Khối xử lý tính toán kết quả trong hàm xử lý chính."
            )

        if (
            ("c++" in lang_lower or "cpp" in lang_lower)
            and "int main" in code
            and "long long" not in code
        ):
            locations.append(
                "• 📍 **Khai báo biến:** Đang dùng `int` cho toàn bộ biến tính toán, dễ tràn số khi `N >= 10^5`."
            )
        advice.append(
            "• 💡 Hãy rà soát lại logic xử lý và các điều kiện biên mà không cần xem đáp án mẫu."
        )
    elif "rte" in v_lower or "thực thi" in v_lower:
        locations.append(
            "💥 **Vị trí lỗi (Ngoại lệ thực thi):** Truy cập mảng ngoài biên, chia cho 0, hoặc đệ quy quá giới hạn Stack."
        )
        if "c++" in lang_lower or "cpp" in lang_lower:
            locations.append(
                "• 📍 **Khai báo mảng / Truy cập chỉ số:** Kiểm tra mảng đánh số từ 0 hay 1, và kích thước mảng."
            )
        advice.append(
            "• 💡 Đảm bảo mảng đủ lớn (`N + 5`) và điều kiện dừng đệ quy an toàn."
        )
    elif "mle" in v_lower or "bộ nhớ" in v_lower:
        locations.append(
            "🟣 **Vị trí lỗi (Bộ nhớ):** Khối cấp phát mảng 2 chiều hoặc cây đệ quy sâu."
        )
        advice.append("• 💡 Tối ưu bộ nhớ sang mảng cuộn 1 chiều (Rolling Array).")
    else:
        locations.append(
            "❓ **Vị trí lỗi:** Cần kiểm tra lại toàn bộ logic chương trình."
        )

    detail_str = "\n".join(locations)
    guide_str = (
        "\n".join(advice)
        if advice
        else "• 💡 Kiểm tra lại các ràng buộc và logic thuật toán."
    )
    return detail_str, guide_str


def get_sample_solution_template(problem: ProblemData, language: str) -> str:
    """Tạo khung code mẫu chuẩn tham khảo cho bài tập theo đúng ngôn ngữ chỉ định (16 ngôn ngữ)."""
    lang_lower = language.lower()
    prob_title = f"{problem.id} - {problem.name}"

    # 1. C++ (GNU++17 / GNU++20 / GNU++23)
    if any(k in lang_lower for k in ["c++", "cpp", "g++", "gnu++"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: C++ (GNU++17 / GNU++20 / GNU++23)\n"
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "void solve() {\n"
            "    // 1. Đọc dữ liệu đầu vào\n"
            "    // 2. Xử lý giải thuật tối ưu O(N) / O(N log N)\n"
            "    // 3. In kết quả chuẩn xác\n"
            "}\n\n"
            "int main() {\n"
            "    // Tối ưu Fast I/O trong C++\n"
            "    ios_base::sync_with_stdio(false);\n"
            "    cin.tie(NULL);\n\n"
            "    int t = 1;\n"
            "    if (cin >> t) {\n"
            "        while (t--) solve();\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
        )
    # 2. Python & 3. PyPy (CPython 3.x / PyPy 3)
    elif any(k in lang_lower for k in ["python", "py", "pypy", "cpython"]):
        return (
            f"# 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "# Ngôn ngữ: Python 3 / PyPy 3 (Fast I/O)\n"
            "import sys\n\n"
            "def solve():\n"
            "    input = sys.stdin.readline\n"
            "    # 1. Đọc dữ liệu đầu vào:\n"
            "    # data = list(map(int, input().split()))\n"
            "    # 2. Xử lý thuật toán tối ưu O(N) / O(N log N)\n"
            "    # 3. In kết quả\n"
            "    pass\n\n"
            "if __name__ == '__main__':\n"
            "    try:\n"
            "        line = sys.stdin.readline()\n"
            "        if line and line.strip():\n"
            "            t = int(line.strip())\n"
            "            for _ in range(t):\n"
            "                solve()\n"
            "        else:\n"
            "            solve()\n"
            "    except Exception:\n"
            "        solve()\n"
        )
    # 4. Java (Java 17+)
    elif "java" in lang_lower:
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: Java 17+ (Fast I/O BufferedReader)\n"
            "import java.io.*;\n"
            "import java.util.*;\n\n"
            "public class Solution {\n"
            "    public static void main(String[] args) throws IOException {\n"
            "        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n"
            "        String line = br.readLine();\n"
            "        if (line != null && !line.trim().isEmpty()) {\n"
            "            int t = Integer.parseInt(line.trim());\n"
            "            while (t-- > 0) {\n"
            "                // solve(br);\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
    # 5. C (GCC 17/11)
    elif lang_lower in ["c", "gcc", "c11", "c17", "c99", "gnuc"]:
        return (
            f"/* 📖 Code mẫu chuẩn tham khảo bài: {prob_title} */\n"
            "/* Ngôn ngữ: C (GCC 17/11) */\n"
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n\n"
            "void solve() {\n"
            "    /* 1. Nhập dữ liệu */\n"
            "    /* 2. Xử lý thuật toán */\n"
            "    /* 3. Xuất kết quả */\n"
            "}\n\n"
            "int main() {\n"
            "    int t = 1;\n"
            '    if (scanf("%d", &t) == 1) {\n'
            "        while (t--) solve();\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
        )
    # 6. C# (.NET)
    elif any(k in lang_lower for k in ["c#", "cs", "csharp", "dotnet"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: C# (.NET)\n"
            "using System;\n"
            "using System.IO;\n\n"
            "class Solution {\n"
            "    static void Main() {\n"
            "        string line = Console.ReadLine();\n"
            "        if (int.TryParse(line, out int t)) {\n"
            "            while (t-- > 0) Solve();\n"
            "        }\n"
            "    }\n"
            "    static void Solve() {\n"
            "        // Xử lý bài toán\n"
            "    }\n"
            "}\n"
        )
    # 7. Kotlin (Kotlin/JVM)
    elif any(k in lang_lower for k in ["kotlin", "kt"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: Kotlin (Kotlin/JVM)\n"
            "import java.io.BufferedReader\n"
            "import java.io.InputStreamReader\n"
            "import java.util.StringTokenizer\n\n"
            "fun main() {\n"
            "    val reader = BufferedReader(InputStreamReader(System.`in`))\n"
            "    val tStr = reader.readLine() ?: return\n"
            "    val t = tStr.trim().toIntOrNull() ?: 1\n"
            "    for (i in 0 until t) {\n"
            "        // solve(reader)\n"
            "    }\n"
            "}\n"
        )
    # 8. Rust (rustc)
    elif any(k in lang_lower for k in ["rust", "rs"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: Rust (rustc 2021)\n"
            "use std::io::{{self, BufRead}};\n\n"
            "fn main() {{\n"
            "    let stdin = io::stdin();\n"
            "    let mut lines = stdin.lock().lines();\n"
            "    if let Some(Ok(line)) = lines.next() {{\n"
            "        if let Ok(t) = line.trim().parse::<i32>() {{\n"
            "            for _ in 0..t {{\n"
            "                // solve(&mut lines);\n"
            "            }}\n"
            "        }}\n"
            "    }}\n"
            "}}\n"
        )
    # 9. Go (Golang)
    elif any(k in lang_lower for k in ["go", "golang"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: Go (Golang)\n"
            "package main\n\n"
            "import (\n"
            '    "bufio"\n'
            '    "fmt"\n'
            '    "os"\n'
            ")\n\n"
            "func main() {\n"
            "    in := bufio.NewReader(os.Stdin)\n"
            "    out := bufio.NewWriter(os.Stdout)\n"
            "    defer out.Flush()\n\n"
            "    var t int\n"
            "    if _, err := fmt.Fscan(in, &t); err == nil {\n"
            "        for i := 0; i < t; i++ {\n"
            "            // solve(in, out)\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
    # 10. JavaScript (Node.js)
    elif any(k in lang_lower for k in ["javascript", "js", "node"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: JavaScript (Node.js)\n"
            "const fs = require('fs');\n\n"
            "function main() {\n"
            "    const input = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\n"
            "    if (!input || input.length === 0 || input[0] === '') return;\n"
            "    let ptr = 0;\n"
            "    const t = parseInt(input[ptr++], 10);\n"
            "    for (let i = 0; i < t; i++) {\n"
            "        // solve(input, ptr)\n"
            "    }\n"
            "}\n"
            "main();\n"
        )
    # 11. Pascal (Free Pascal)
    elif any(k in lang_lower for k in ["pascal", "pas", "fpc"]):
        return (
            f"{{ 📖 Code mẫu chuẩn tham khảo bài: {prob_title} }}\n"
            "{{ Ngôn ngữ: Pascal (Free Pascal) }}\n"
            "var\n"
            "    t, i: longint;\n"
            "begin\n"
            "    readln(t);\n"
            "    for i := 1 to t do\n"
            "    begin\n"
            "        { solve; }\n"
            "    end;\n"
            "end.\n"
        )
    # 12. Lua (Lua 5.4 / LuaJIT)
    elif "lua" in lang_lower:
        return (
            f"-- 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "-- Ngôn ngữ: Lua (Lua 5.4 / LuaJIT)\n"
            "local function solve()\n"
            '    -- 1. Nhập dữ liệu: local n = io.read("*n")\n'
            "    -- 2. Xử lý thuật toán\n"
            "    -- 3. Xuất kết quả: print(ans)\n"
            "end\n\n"
            'local t = io.read("*n")\n'
            "if t then\n"
            "    for i = 1, t do solve() end\n"
            "else\n"
            "    solve()\n"
            "end\n"
        )
    # 13. OCaml (ocamlopt)
    elif any(k in lang_lower for k in ["ocaml", "ml"]):
        return (
            f"(* 📖 Code mẫu chuẩn tham khảo bài: {prob_title} *)\n"
            "(* Ngôn ngữ: OCaml *)\n"
            "open Scanf\n"
            "open Printf\n\n"
            "let solve () =\n"
            '    (* 1. Đọc dữ liệu: let n = scanf " %d" (fun x -> x) in *)\n'
            "    (* 2. Xử lý và in kết quả *)\n"
            "    ()\n\n"
            "let () =\n"
            "    try\n"
            '        let t = scanf " %d" (fun x -> x) in\n'
            "        for _ = 1 to t do solve () done\n"
            "    with End_of_file -> solve ()\n"
        )
    # 14. Nim
    elif "nim" in lang_lower:
        return (
            f"# 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "# Ngôn ngữ: Nim\n"
            "import strutils, sequtils\n\n"
            "proc solve() =\n"
            "    # 1. Đọc dữ liệu\n"
            "    # 2. Xử lý thuật toán\n"
            "    # 3. Xuất kết quả\n"
            "    discard\n\n"
            "when isMainModule:\n"
            "    let line = stdin.readLine().strip()\n"
            "    if line.len > 0:\n"
            "        let t = parseInt(line)\n"
            "        for _ in 1..t: solve()\n"
            "    else: solve()\n"
        )
    # 15. Zig
    elif "zig" in lang_lower:
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: Zig\n"
            'const std = @import("std");\n\n'
            "pub fn main() !void {{\n"
            "    const stdin = std.io.getStdIn().reader();\n"
            "    const stdout = std.io.getStdOut().writer();\n"
            "    _ = stdin;\n"
            "    _ = stdout;\n"
            "    // Xử lý thuật toán\n"
            "}}\n"
        )
    # 16. Julia
    elif any(k in lang_lower for k in ["julia", "jl"]):
        return (
            f"# 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "# Ngôn ngữ: Julia\n"
            "function solve()\n"
            "    # 1. Đọc dữ liệu\n"
            "    # 2. Xử lý và in kết quả\n"
            "end\n\n"
            "function main()\n"
            "    solve()\n"
            "end\n"
            "main()\n"
        )
    # 17. TypeScript
    elif any(k in lang_lower for k in ["typescript", "ts"]):
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "// Ngôn ngữ: TypeScript (Node.js)\n"
            "import * as fs from 'fs';\n\n"
            "function main(): void {{\n"
            "    const input = fs.readFileSync(0, 'utf-8').trim().split(/\\s+/);\n"
            "    if (!input || input.length === 0 || input[0] === '') return;\n"
            "    // solve(input);\n"
            "}}\n"
            "main();\n"
        )
    # 18. Fortran
    elif any(k in lang_lower for k in ["fortran", "f90", "f95"]):
        return (
            f"! 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "! Ngôn ngữ: Fortran (GNU Fortran)\n"
            "program solution\n"
            "    implicit none\n"
            "    integer :: t, i\n"
            "    read(*,*,end=100) t\n"
            "    do i = 1, t\n"
            "        ! call solve()\n"
            "    end do\n"
            "100 continue\n"
            "end program solution\n"
        )
    # Mặc định C++
    else:
        return (
            f"// 📖 Code mẫu chuẩn tham khảo bài: {prob_title}\n"
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "void solve() {\n"
            "    // 1. Nhập dữ liệu\n"
            "    // 2. Xử lý thuật toán\n"
            "    // 3. Xuất kết quả\n"
            "}\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false);\n"
            "    cin.tie(NULL);\n"
            "    int t = 1;\n"
            "    if (cin >> t) {\n"
            "        while (t--) solve();\n"
            "    }\n"
            "    return 0;\n"
            "}\n"
        )


def get_unrated_deep_code_review(
    code: str,
    language: str,
    problem: ProblemData,
    is_accepted: bool,
    verdict: str,
    failed_reason: str,
    tests_passed: int,
    total_tests: int,
) -> tuple[str, str]:
    """
    Phân tích chuyên sâu mã nguồn khi nộp bài Luyện tập (Unrated):
    - Nếu sai: Chỉ ra từng lỗi sai cụ thể (Logic, tràn số, I/O, testcase fail).
    - Nếu đúng: Phân tích các vị trí có thể tối ưu thuật toán, I/O, và bộ nhớ.
    """
    lang_lower = language.lower()
    notes: List[str] = []

    if not is_accepted:
        title = "🔍 PHÂN TÍCH TỪNG LỖI SAI & HƯỚNG KHẮC PHỤC"
        # 1. Chi tiết testcase fail
        if failed_reason:
            notes.append(f"• ❌ **Lỗi tại Testcase:** {failed_reason}")
        else:
            notes.append(
                f"• ❌ **Trạng thái:** `{verdict}` tại test `{tests_passed + 1}/{total_tests}`."
            )

        # 2. Kiểm tra tràn số int / long long
        if "c++" in lang_lower or "cpp" in lang_lower:
            if "int main" in code and "long long" not in code:
                notes.append(
                    "• 🔢 **Cảnh báo tràn số kiểu dữ liệu:** Đang dùng `int` 32-bit (`< 2 * 10^9`). Nếu tổng các phần tử hoặc tích vượt quá giới hạn, hãy đổi sang `long long`."
                )
            if "endl" in code:
                notes.append(
                    "• ⚡ **Chậm I/O do `endl`:** Thay thế `endl` bằng `'\\n'` để tránh flush đệm liên tục gây TLE."
                )
        elif "python" in lang_lower:
            if "sys.stdin.readline" not in code and "input(" in code:
                notes.append(
                    "• ⚡ **Chậm I/O trong Python:** Thêm `import sys; input = sys.stdin.readline` ở đầu file để đọc dữ liệu nhanh gấp 5 lần."
                )

        # 3. Gợi ý kiểm tra biên
        notes.append(
            "• 🎯 **Kiểm tra trường hợp biên (Edge cases):** Hãy thử với `N = 1`, các giá trị lớn nhất trong giới hạn đề bài, mảng có tất cả phần tử bằng nhau hoặc có số âm."
        )
        notes.append(
            "• 💡 **Phân tích thuật toán:** Đọc lại giới hạn `N` và Time Limit để đảm bảo thuật toán không bị `O(N^2)` khi `N >= 10^5`."
        )
    else:
        title = "⚡ PHÂN TÍCH TỐI ƯU HÓA MÃ NGUỒN CHUYÊN SÂU"
        notes.append(
            "• 🟢 **Đánh giá giải thuật:** Chương trình đã vượt qua toàn bộ testcases chính xác 100%!"
        )

        if "c++" in lang_lower or "cpp" in lang_lower:
            if "ios_base::sync_with_stdio" not in code:
                notes.append(
                    "• ⚡ **Tối ưu tốc độ (Fast I/O):** Thêm `ios_base::sync_with_stdio(false); cin.tie(NULL);` ở đầu `main()` để giảm thời gian đọc dữ liệu."
                )
            if "endl" in code:
                notes.append(
                    "• ⚡ **Tối ưu xuất dữ liệu:** Thay `endl` bằng `'\\n'` để tăng tốc độ in."
                )
            if "&" not in code and "vector" in code:
                notes.append(
                    "• 💾 **Tối ưu bộ nhớ khi truyền tham số:** Truyền mảng/vector theo tham chiếu `const vector<int>& a` để tránh sao chép dữ liệu tốn `O(N)` bộ nhớ."
                )
        elif "python" in lang_lower:
            if "sys.stdin.readline" not in code:
                notes.append(
                    "• ⚡ **Tối ưu tốc độ đọc (Python Fast I/O):** Dùng `sys.stdin.read().split()` hoặc `sys.stdin.readline` để tối ưu hóa thời gian chạy tối đa."
                )

        notes.append(
            "• 🧹 **Clean Code:** Chia nhỏ logic thành hàm `solve()` riêng biệt cho từng test case để mã nguồn dễ bảo trì và mở rộng."
        )

    return title, "\n".join(notes)


class JudgeService:
    """Điều phối toàn bộ quy trình chấm bài nộp trực tiếp tại Discord (Mode 2) hỗ trợ Rated, Unrated và Event Challenges."""

    _SEMAPHORE = asyncio.Semaphore(
        1
    )  # Đảm bảo chấm bài tuần tự để đo đạc thời gian chính xác và tránh xung đột I/O

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.sandbox = CodeSandbox(
            timeout=settings.JUDGE_TIMEOUT,
            memory_limit_mb=settings.JUDGE_MEMORY_LIMIT,
            cpu_limit=settings.JUDGE_CPU_LIMIT,
            pids_limit=settings.JUDGE_PIDS_LIMIT,
        )

    async def judge_submission(
        self,
        user: discord.User | discord.Member,
        problem_id: str,
        language_alias: str,
        code: str,
        is_rated: bool = True,
        guild: discord.Guild | None = None,
    ) -> JudgeResponse:
        """Xử lý và chấm bài nộp trong môi trường Sandbox với hàng đợi cách ly chống xung đột code."""
        async with self._SEMAPHORE:
            return await self._judge_submission_internal(
                user=user,
                problem_id=problem_id,
                language_alias=language_alias,
                code=code,
                is_rated=is_rated,
                guild=guild,
            )

    async def _judge_submission_internal(
        self,
        user: discord.User | discord.Member,
        problem_id: str,
        language_alias: str,
        code: str,
        is_rated: bool = True,
        guild: discord.Guild | None = None,
    ) -> JudgeResponse:
        """Thực thi kiểm thử chi tiết trong môi trường Sandbox độc lập."""
        user_id = user.id

        # Kiểm tra lệnh cấm thi đấu do gian lận AI
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            is_banned, rem_sec, ban_time_str = await user_repo.get_ban_status(user_id)
            if is_banned:
                embed = create_embed(
                    title="🚫 BẠN ĐANG BỊ CẤM THI ĐẤU",
                    description=(
                        f"{user.mention}, tài khoản của bạn đang trong thời gian **TẠM KHÓA THI ĐẤU** do vi phạm quy chế liêm chính!\n\n"
                        f"• ⏱️ **Thời gian cấm còn lại:** `{ban_time_str}`\n"
                        f"• ⚠️ **Phạm vi áp dụng:** Tạm khóa nộp bài Freedom và Đấu Trường Ranked 1:1.\n"
                        f"• 🕊️ *Vui lòng liên hệ Bot Owner để được xem xét ân xá.*"
                    ),
                    embed_type=EmbedType.ERROR,
                )
                return JudgeResponse(False, "Banned", embed, None, 0, 0, 0.0, 0)

        # 1. Kiểm tra kích thước mã nguồn
        if len(code) > settings.MAX_CODE_LENGTH:
            embed = create_embed(
                title="BÀI NỘP BỊ TỪ CHỐI — MÃ NGUỒN QUÁ DÀI",
                description=f"Dung lượng code vượt quá giới hạn cho phép: **{len(code):,} / {settings.MAX_CODE_LENGTH:,} ký tự**.",
                embed_type=EmbedType.ERROR,
            )
            return JudgeResponse(False, "Rejected", embed, None, 0, 0, 0.0, 0)

        # 2. Kiểm tra Cooldown theo Rank (10 phút cho T8-T4, 5 phút cho T3-HT1)
        remaining_cd, total_cd, last_rank = submission_cooldown.get_remaining_cooldown(
            user_id
        )
        if remaining_cd > 0:
            time_str = submission_cooldown.format_remaining_time(remaining_cd)
            total_mins = total_cd // 60
            embed = create_embed(
                title="⏳ THỜI GIAN CHỜ GIỮA CÁC BÀI NỘP (COOLDOWN)",
                description=(
                    f"Vui lòng đợi {time_str} trước khi nộp bài tiếp theo!\n\n"
                    f"• ⏱️ **Quy định thời gian chờ sau mỗi bài nộp:**\n"
                    f"  - **Rank `⭐ T8 ➔ 🔷 T4`:** **10 phút** giữa các lần nộp bài.\n"
                    f"  - **Rank `🔷 T3 ➔ 👑 HT1`:** **5 phút** giữa các lần nộp bài.\n"
                    f"• 🏆 **Bậc Rank ghi nhận:** `{last_rank or 'Tân Binh'}` *(Thời gian chờ quy định: {total_mins} phút)*"
                ),
                embed_type=EmbedType.WARNING,
                footer_text="Quy định hạn chế tốc độ nộp bài • Discord Arena",
            )
            return JudgeResponse(False, "Rate Limited", embed, None, 0, 0, 0.0, 0)

        # 3. Kiểm tra chống nộp trùng lặp
        if duplicate_guard.is_duplicate(user_id, problem_id, code):
            embed = create_embed(
                title="PHÁT HIỆN BÀI NỘP TRÙNG LẶP",
                description="⚠️ Bạn vừa nộp cùng một đoạn mã cho bài tập này. Vui lòng kiểm tra lại trước khi gửi.",
                embed_type=EmbedType.WARNING,
            )
            return JudgeResponse(False, "Duplicate", embed, None, 0, 0, 0.0, 0)

        # 4. Kiểm tra tính hợp lệ của ngôn ngữ
        lang_config = get_language_by_alias(language_alias)
        if not lang_config:
            embed = create_embed(
                title="NGÔN NGỮ KHÔNG ĐƯỢC HỖ TRỢ",
                description=f"Ngôn ngữ `{language_alias}` không hợp lệ. Các ngôn ngữ được hỗ trợ: `cpp17`, `cpp20`, `python3`, `java`, `rust`, `go`, `javascript`, `csharp`.",
                embed_type=EmbedType.ERROR,
            )
            return JudgeResponse(False, "Invalid Language", embed, None, 0, 0, 0.0, 0)

        # 5. Lấy dữ liệu bài tập
        problem: ProblemData | None = await ProblemFetcher.fetch_problem(problem_id)
        if not problem:
            embed = create_embed(
                title="KHÔNG TÌM THẤY BÀI TẬP",
                description=f"Không tìm thấy bài tập với mã `{problem_id}` trên Codeforces. Vui lòng kiểm tra lại định dạng (Ví dụ: `1700A`).",
                embed_type=EmbedType.ERROR,
            )
            return JudgeResponse(False, "Problem Not Found", embed, None, 0, 0, 0.0, 0)

        # Kiểm tra xem bài có thuộc diện Event / Hot Challenge không
        is_event, event_mult, event_tag = RatingEngine.get_event_bonus_multiplier(
            contest_name=problem.name,
            problem_name=problem.name,
            problem_rating=problem.rating,
        )

        # 6. Kiểm tra bài đã giải hay chưa & Điều kiện bậc Rank (nếu thi đấu Rated)
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            sub_repo = SubmissionRepository(session)
            already_solved = await sub_repo.has_solved(user_id, problem.id)
            db_user, _ = await user_repo.get_or_create(user_id)
            user_rank = db_user.rank
            old_rating = db_user.rating
            old_rank = db_user.rank

        # Khóa nộp Rated nếu bài đã giải thành công trước đó (cho phép nộp Unrated luyện tập)
        if is_rated and already_solved:
            embed = create_embed(
                title="BÀI TẬP ĐÃ HOÀN THÀNH (ALREADY SOLVED) 🔒",
                description=(
                    f"❌ Bạn đã giải chính xác bài tập **`{problem.id} — {problem.name}`** trước đó!\n\n"
                    f"• **Quy định thi đấu:** Không thể nộp lại ở chế độ **Rated (Thi đấu 🏆)** để cày thêm điểm hoặc tăng Rating.\n"
                    f"• 💡 **Luyện tập tự do:** Bạn có thể chuyển sang chọn **`🌱 Nộp bài Luyện tập (Unrated)`** để tối ưu hóa mã nguồn, thử thuật toán mới hoặc thực hành ngôn ngữ khác mà không bị giới hạn!"
                ),
                embed_type=EmbedType.WARNING,
                footer_text="Quy định chống cày điểm • Chế độ Luyện tập Unrated luôn mở",
            )
            return JudgeResponse(False, "Already Solved", embed, None, 0, 0, 0.0, 0)

        if (
            is_rated
            and not is_owner_user(user_id)
            and not is_rank_sufficient(user_rank, problem.min_rank_required)
        ):
            embed = create_embed(
                title="TỪ CHỐI TRUY CẬP — CHƯA ĐẠT RANK YÊU CẦU",
                description=(
                    f"❌ Bạn không đủ điều kiện làm bài tập này ở chế độ **Rated**.\n\n"
                    f"• **Yêu cầu tối thiểu:** `{problem.min_rank_required}+`\n"
                    f"• **Rank hiện tại của bạn:** `{get_rank_badge(user_rank)} {user_rank}`\n\n"
                    f"💡 *Bạn có thể chọn nộp bài ở chế độ **Unrated (Luyện tập)** để làm bài tự do!*"
                ),
                embed_type=EmbedType.ERROR,
            )
            return JudgeResponse(False, "Insufficient Rank", embed, None, 0, 0, 0.0, 0)

        # 7. Quét phân tích nghi vấn AI (CHỈ GHI NHẬN - KHÔNG TỰ ĐỘNG PHẠT)
        # Lý do: detector heuristic chỉ mang tính xác suất (dễ false positive,
        # thiên vị phong cách viết), KHÔNG được dùng làm bằng chứng duy nhất để
        # hủy bài hay cấm thi đấu. Mọi nghi vấn cao được chuyển cho mod review thủ công.
        ai_analysis = AIDetector.analyze(code, lang_config.name)
        ai_score: float = float(ai_analysis.get("score", 0))
        ai_status: str = str(ai_analysis.get("status", "Bình thường"))
        ai_signals: list = ai_analysis.get("signals", [])
        ai_review_threshold: float = float(getattr(settings, "AI_CONFIDENCE_THRESHOLD", 70) or 70)

        ai_flagged_for_review = ai_score >= ai_review_threshold
        if ai_flagged_for_review and not AI_AUTO_PUNISH_ENABLED:
            try:
                _sig_preview = "; ".join(str(s) for s in (ai_signals or [])[:5])
                logger.warning(
                    "[AI-REVIEW] user_id=%s problem=%s ai_score=%.0f signals=[%s] "
                    "(cho mod review thu cong, KHONG tu dong phat)",
                    user_id, getattr(problem, "id", "?"), ai_score, _sig_preview,
                )
            except Exception:
                pass

        # 8. Phân tích độ phức tạp tĩnh
        static_analysis = StaticComplexityAnalyzer.analyze(code, lang_config.name)
        static_warnings: list = static_analysis.get("warnings", [])

        # 9. Giám sát tài nguyên máy chủ & Điều tiết thông minh (Adaptive Resource Governor)
        hw_profile: HardwareProfile = ResourceGovernor.get_current_profile()
        effective_time_limit: float = (
            problem.time_limit
            * lang_config.time_multiplier
            * hw_profile.time_limit_bonus
        )

        # 10. Chuẩn bị bộ testcases
        test_suite = TestcaseGenerator.build_full_test_suite(
            sample_tests=problem.samples,
            time_limit=problem.time_limit,
            problem_id=problem.id,
        )

        # 11. Tạo thư mục tạm độc lập và ghi mã nguồn
        temp_dir = tempfile.mkdtemp(
            prefix=f"cp_judge_{user_id}_{int(time.time() * 1000)}_"
        )
        try:
            source_file = os.path.join(temp_dir, lang_config.source_filename)
            with open(source_file, "w", encoding="utf-8") as f:
                f.write(code)

            # 12. Biên dịch mã nguồn
            compile_res: ExecutionResult = await self.sandbox.compile_source(
                work_dir=temp_dir,
                lang=lang_config,
                time_limit=max(5.0, effective_time_limit * 2.0),
            )
            if not compile_res.success:
                rating_delta = 0
                new_rating = old_rating
                new_rank = old_rank

                if is_rated:
                    rating_delta = RatingEngine.calculate_problem_rating_penalty(
                        user_rating=old_rating,
                        problem_rating=problem.rating or 1200,
                        is_mode1=False,
                        is_event=is_event,
                        tests_passed_ratio=0.0,
                    )
                    new_rating = max(0, old_rating + rating_delta)
                    new_rank = get_rank_by_rating(new_rating)

                    if rating_delta != 0:
                        async with async_session_factory() as session:
                            user_repo = UserRepository(session)
                            rating_repo = RatingRepository(session)

                            score_penalty = (
                                RatingEngine.calculate_problem_score_penalty(
                                    problem_rating=problem.rating or 1200,
                                    is_mode1=False,
                                )
                            )
                            await user_repo.update_stats(
                                discord_id=user_id,
                                is_accepted=False,
                                is_mode1=False,
                                score_delta=score_penalty,
                                rating_delta=rating_delta,
                                new_rank=new_rank,
                            )
                            await rating_repo.log_rating_change(
                                discord_id=user_id,
                                old_rating=old_rating,
                                new_rating=new_rating,
                                problem_id=problem.id,
                                reason="Lỗi biên dịch (CE) Mode 2 - Trừ phong độ",
                            )

                    if guild and isinstance(user, discord.Member):
                        await RoleManager.sync_user_roles(
                            guild=guild,
                            member=user,
                            old_rating=old_rating,
                            new_rating=new_rating,
                            old_rank=old_rank,
                            new_rank=new_rank,
                            bot=self.bot,
                        )

                embed = self._build_compilation_error_embed(
                    user=user,
                    problem=problem,
                    language=lang_config.name,
                    compile_log=compile_res.stderr or compile_res.stdout,
                    ai_score=ai_score,
                    old_rating=old_rating,
                    new_rating=new_rating,
                    is_rated=is_rated,
                    is_event=is_event,
                    event_tag=event_tag,
                )
                await self._save_submission(
                    user_id=user_id,
                    problem=problem,
                    language=lang_config.name,
                    verdict="Lỗi biên dịch (CE)",
                    score=0.0,
                    execution_time=0.0,
                    memory=0.0,
                    tests_passed=0,
                    total_tests=len(test_suite),
                    ai_score=ai_score,
                    code=code,
                )
                submission_cooldown.record_submission(user_id, rank=old_rank or "T8")
                return JudgeResponse(
                    False,
                    "Compilation Error",
                    embed,
                    None,
                    0,
                    len(test_suite),
                    0.0,
                    rating_delta,
                )

            # 12. GIAI ĐOẠN 1 (BƯỚC 1): Kiểm tra Testcase Mẫu Codeforces (CF Samples)
            step1_suite = TestcaseGenerator.generate_step1_sample_suite(
                sample_tests=problem.samples,
                problem_id=problem.id,
                time_limit=problem.time_limit,
            )
            step1_passed = 0
            step1_verdict = "Chấp nhận (Accepted)"
            step1_failed_reason = ""
            step1_failed_type = "SAMPLE"
            max_time = 0.0
            max_memory = 0.0

            for test in step1_suite:
                await asyncio.sleep(
                    hw_profile.inter_test_sleep
                )  # Pacing điều độ tài nguyên CPU & RAM thích ứng
                exec_result: ExecutionResult = await self.sandbox.execute_test(
                    work_dir=temp_dir,
                    lang=lang_config,
                    stdin_input=test.input_data,
                    time_limit=effective_time_limit,
                )
                max_time = max(max_time, exec_result.execution_time)
                max_memory = max(max_memory, exec_result.memory_used_mb)

                if exec_result.status == "TLE":
                    step1_verdict = "Vượt quá thời gian (TLE)"
                    step1_failed_reason = f"Vượt quá thời gian quy định ({exec_result.execution_time:.2f}s > {problem.time_limit}s) tại Test mẫu #{test.id}."
                    step1_failed_type = test.test_type
                    break
                elif exec_result.status == "MLE":
                    step1_verdict = "Vượt quá bộ nhớ (MLE)"
                    step1_failed_reason = f"Vượt quá giới hạn bộ nhớ quy định ({problem.memory_limit} MB) tại Test mẫu #{test.id}."
                    step1_failed_type = test.test_type
                    break
                elif exec_result.status == "RTE":
                    step1_verdict = "Lỗi thực thi (RTE)"
                    err_snippet = (
                        exec_result.stderr.strip()[:100]
                        if exec_result.stderr
                        else f"Exit code {exec_result.exit_code}"
                    )
                    step1_failed_reason = (
                        f"Lỗi thực thi tại Test mẫu #{test.id}: `{err_snippet}`"
                    )
                    step1_failed_type = test.test_type
                    break
                elif exec_result.status == "OK":
                    if test.expected_output is not None:
                        check_res = OutputChecker.compare(
                            exec_result.stdout, test.expected_output
                        )
                        if not check_res.passed:
                            step1_verdict = "Kết quả sai (Wrong Answer)"
                            step1_failed_reason = (
                                f"Test mẫu #{test.id}: {check_res.details}"
                            )
                            step1_failed_type = test.test_type
                            break
                    step1_passed += 1

            step1_pass_ratio = step1_passed / max(1, len(step1_suite))

            # 13. GIAI ĐOẠN 2 (BƯỚC 2): Themis Multi-Test Engine & Phân tích BXH Thích Ứng
            themis_passed = step1_passed
            total_themis_tests = len(step1_suite)
            final_verdict = step1_verdict
            failed_reason = step1_failed_reason
            failed_test_type = step1_failed_type

            # Lấy thông tin BXH Contest từ Codeforces API nếu có
            contest_participants = None
            contest_percentile = None
            if problem.contest_id:
                try:
                    standings_data = await cf_api.get_contest_standings(
                        contest_id=problem.contest_id, count=100
                    )
                    rows = standings_data.get("rows", [])
                    if rows:
                        contest_participants = len(rows)
                except Exception as e:
                    logger.debug(
                        f"Không lấy được BXH contest {problem.contest_id}: {e}"
                    )

            if step1_pass_ratio >= 0.40:
                # Kích hoạt Themis Multi-Test Suite với quy mô tương ứng tài nguyên phần cứng
                themis_suite = TestcaseGenerator.generate_themis_step2_suite(
                    sample_tests=problem.samples,
                    problem_id=problem.id,
                    time_limit=problem.time_limit,
                    problem_rating=problem.rating or 1200,
                    target_test_count=hw_profile.max_themis_tests,
                )
                themis_passed = 0
                themis_verdict = "Chấp nhận (Accepted)"
                themis_failed_reason = ""
                total_themis_tests = len(themis_suite)

                for t_test in themis_suite:
                    await asyncio.sleep(
                        hw_profile.inter_test_sleep
                    )  # Pacing điều độ tài nguyên CPU & RAM giữa các bài test Themis
                    t_exec: ExecutionResult = await self.sandbox.execute_test(
                        work_dir=temp_dir,
                        lang=lang_config,
                        stdin_input=t_test.input_data,
                        time_limit=effective_time_limit,
                    )
                    max_time = max(max_time, t_exec.execution_time)
                    max_memory = max(max_memory, t_exec.memory_used_mb)

                    if t_exec.status == "TLE":
                        if not themis_failed_reason:
                            themis_verdict = "Vượt quá thời gian (TLE)"
                            themis_failed_reason = (
                                f"Vượt quá thời gian tại {t_test.description}."
                            )
                            failed_test_type = t_test.test_type
                    elif t_exec.status == "MLE":
                        if not themis_failed_reason:
                            themis_verdict = "Vượt quá bộ nhớ (MLE)"
                            themis_failed_reason = (
                                f"Vượt quá bộ nhớ tại {t_test.description}."
                            )
                            failed_test_type = t_test.test_type
                    elif t_exec.status == "RTE":
                        if not themis_failed_reason:
                            themis_verdict = "Lỗi thực thi (RTE)"
                            err_snippet = (
                                t_exec.stderr.strip()[:100]
                                if t_exec.stderr
                                else f"Exit code {t_exec.exit_code}"
                            )
                            themis_failed_reason = f"Lỗi thực thi tại {t_test.description}: `{err_snippet}`"
                            failed_test_type = t_test.test_type
                    elif t_exec.status == "OK":
                        if t_test.expected_output is not None:
                            check_res = OutputChecker.compare(
                                t_exec.stdout, t_test.expected_output
                            )
                            if not check_res.passed:
                                if not themis_failed_reason:
                                    themis_verdict = "Kết quả sai (Wrong Answer)"
                                    themis_failed_reason = (
                                        f"Kết quả không khớp tại {t_test.description}."
                                    )
                                    failed_test_type = t_test.test_type
                            else:
                                themis_passed += 1
                        else:
                            themis_passed += 1

                pass_themis_ratio = themis_passed / max(1, total_themis_tests)
                time_ratio = max_time / max(0.1, problem.time_limit)

                # Phân định Verdict chuẩn theo KẾT QUẢ TEST (không dùng điểm AI để hạ verdict,
                # vì detector chỉ mang tính xác suất): >= 70% Chấp nhận, 40%-69% Tạm chấp nhận, < 40% Không chấp nhận
                if pass_themis_ratio >= 0.70:
                    final_verdict = "Chấp nhận (Accepted)"
                elif pass_themis_ratio >= 0.40:
                    final_verdict = "Tạm chấp nhận (Provisionally Accepted)"
                else:
                    final_verdict = themis_verdict
                    failed_reason = themis_failed_reason

                # Tính toán phân vị percentile Themis
                if pass_themis_ratio >= 0.70:
                    if pass_themis_ratio >= 1.0 and time_ratio <= 0.30:
                        contest_percentile = 0.85  # Top 15% (> 70% thí sinh) -> 1.4x
                    elif pass_themis_ratio >= 1.0 and time_ratio <= 0.70:
                        contest_percentile = 0.75  # Top 25% (> 70% thí sinh) -> 1.4x
                    else:
                        contest_percentile = 0.55  # Top 45% (> 50% thí sinh) -> 1.0x
                elif pass_themis_ratio >= 0.40:
                    contest_percentile = 0.35  # Top 65% (> 30% thí sinh) -> 0.5x
                else:
                    contest_percentile = (
                        0.05  # Bottom 95% (< 40% test) -> Trừ điểm phong độ
                    )

            # 14. Đánh giá 2 bước qua RatingEngine
            is_accepted = "Accepted" in final_verdict or "Chấp nhận" in final_verdict
            eval_res = RatingEngine.evaluate_mode2_two_step_submission(
                tests_passed=themis_passed,
                total_tests=total_themis_tests,
                user_rating=old_rating,
                problem_rating=problem.rating or 1200,
                contest_participants=contest_participants or 100,
                contest_percentile=contest_percentile,
                is_event=is_event,
                event_multiplier=event_mult,
            )

            score_earned = 0.0
            rating_delta = 0
            new_rating = old_rating
            new_rank = old_rank

            pass_themis_ratio = themis_passed / max(1, total_themis_tests)

            # Nếu là Tạm chấp nhận: Vẫn cộng điểm Score & Rating nhưng ít hơn (40% <= test < 70%)
            # (Điểm AI không ảnh hưởng điểm số — chỉ ghi nhận review)
            if "Tạm chấp nhận" in final_verdict:
                if pass_themis_ratio >= 0.60:
                    prov_mult = 0.55
                elif pass_themis_ratio >= 0.50:
                    prov_mult = 0.45
                else:
                    prov_mult = 0.35

                eval_res["score_delta"] = max(
                    5.0, round(eval_res["score_delta"] * prov_mult, 1)
                )
                eval_res["rating_delta"] = max(
                    1, int(round(eval_res["rating_delta"] * prov_mult))
                )
                eval_res["summary"] = (
                    f"Tạm chấp nhận ({themis_passed}/{total_themis_tests} tests - {pass_themis_ratio*100:.0f}%) ➔ Vẫn cộng điểm (+{eval_res['rating_delta']} Rating & +{eval_res['score_delta']:.1f} Score)"
                )

            async with async_session_factory() as session:
                sub_repo = SubmissionRepository(session)
                already_solved = await sub_repo.has_solved(user_id, problem.id)

                if not is_rated or already_solved:
                    score_earned = 0.0
                    rating_delta = 0
                    new_rating = old_rating
                    new_rank = old_rank
                else:
                    score_earned = eval_res["score_delta"]
                    rating_delta = eval_res["rating_delta"]
                    new_rating = max(0, old_rating + rating_delta)
                    new_rank = get_rank_by_rating(new_rating)

                    user_repo = UserRepository(session)
                    rating_repo = RatingRepository(session)

                    await user_repo.update_stats(
                        discord_id=user_id,
                        is_accepted=eval_res["step1_passed"] and is_accepted,
                        is_mode1=False,
                        score_delta=score_earned,
                        rating_delta=rating_delta,
                        new_rank=new_rank,
                    )

                    reason_text = f"Mode 2 Themis: {eval_res['summary']}"
                    await rating_repo.log_rating_change(
                        discord_id=user_id,
                        old_rating=old_rating,
                        new_rating=new_rating,
                        problem_id=problem.id,
                        reason=reason_text,
                    )

            # 15. Lưu bản ghi nộp bài
            await self._save_submission(
                user_id=user_id,
                problem=problem,
                language=lang_config.name,
                verdict=final_verdict if is_rated else f"{final_verdict} (Unrated)",
                score=score_earned,
                execution_time=max_time,
                memory=max_memory,
                tests_passed=themis_passed,
                total_tests=total_themis_tests,
                ai_score=ai_score,
                code=code,
            )

            # 16. Đồng bộ Role Discord
            if is_rated and guild and isinstance(user, discord.Member):
                await RoleManager.sync_user_roles(
                    guild=guild,
                    member=user,
                    old_rating=old_rating,
                    new_rating=new_rating,
                    old_rank=old_rank,
                    new_rank=new_rank,
                    bot=self.bot,
                )

            # 17. Khởi tạo 2 Rich Embeds riêng biệt:
            # - Embed 1: Kết Quả Bài Nộp (Điểm số, Themis Tests, BXH, Rating, AI Bar)
            # - Embed 2: Sửa Lỗi / Phân Tích / Tối Ưu Hóa Chuyên Sâu
            embed = self._build_result_embed(
                user=user,
                problem=problem,
                language=lang_config.name,
                verdict=final_verdict,
                tests_passed=themis_passed,
                total_tests=total_themis_tests,
                max_time=max_time,
                max_memory=max_memory,
                score_earned=score_earned,
                old_rating=old_rating,
                new_rating=new_rating,
                failed_reason=failed_reason,
                failed_test_type=failed_test_type,
                ai_score=ai_score,
                ai_status=ai_status,
                ai_signals=ai_signals,
                static_warnings=static_warnings,
                eval_res=eval_res,
                code=code,
                is_rated=is_rated,
                is_event=is_event,
                event_mult=event_mult,
                event_tag=event_tag,
            )

            analysis_embed = self._build_analysis_embed(
                user=user,
                problem=problem,
                language=lang_config.name,
                verdict=final_verdict,
                tests_passed=themis_passed,
                total_tests=total_themis_tests,
                max_time=max_time,
                max_memory=max_memory,
                failed_reason=failed_reason,
                failed_test_type=failed_test_type,
                code=code,
                is_rated=is_rated,
                ai_score=ai_score,
            )

            # 18. Tự động gửi cả 2 Embeds qua tin nhắn riêng (DM) cho thí sinh
            try:
                await user.send(embeds=[embed, analysis_embed])
            except Exception as dm_err:
                logger.debug(f"Không thể gửi DM riêng cho {user.name}: {dm_err}")

            # Ghi nhận thời điểm hoàn thành bài nộp để kích hoạt Cooldown theo Rank (10p T8-T4 / 5p T3-HT1)
            submission_cooldown.record_submission(user_id, rank=old_rank or "T8")

            # Tự động lưu trữ bài tập vào PROBLEM_ARCHIVE_CHANNEL_ID (1548627763467128912)
            try:
                from services.problem_archive import ProblemArchiveService
                asyncio.create_task(
                    ProblemArchiveService.archive_problem(
                        self.bot,
                        {
                            "id": problem.id,
                            "name": problem.name,
                            "mode": "Freedom",
                            "tier": prob_tier,
                            "rating": prob_r,
                            "time_limit": problem.time_limit,
                            "memory_limit": problem.memory_limit,
                            "statement": getattr(problem, "statement", "") or f"Bài tập `{problem.id}` trên hệ thống Codeforces.",
                            "input_format": getattr(problem, "input_format", "Đọc từ standard input (cin/stdin)."),
                            "output_format": getattr(problem, "output_format", "In ra standard output (cout/stdout)."),
                            "constraints": f"Thời gian giới hạn: {problem.time_limit}s • Bộ nhớ: {problem.memory_limit} MB",
                            "editorial": f"Bài tập Codeforces #{problem.contest_id}{problem.index} (Tier: {prob_tier} - Rating: {prob_r} pts).",
                            "sample_input": problem.samples[0][0] if problem.samples else "",
                            "sample_output": problem.samples[0][1] if problem.samples else "",
                            "solution_code": code if is_accepted else "",
                            "solution_lang": lang_config.extension if is_accepted else "cpp",
                        },
                    )
                )
            except Exception as archive_err:
                logger.debug(f"Không thể kích hoạt lưu trữ bài {problem.id}: {archive_err}")

            return JudgeResponse(
                success=is_accepted,
                verdict=final_verdict,
                embed=embed,
                analysis_embed=analysis_embed,
                tests_passed=themis_passed,
                total_tests=total_themis_tests,
                score_earned=score_earned,
                rating_delta=rating_delta,
            )

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _save_submission(
        self,
        user_id: int,
        problem: ProblemData,
        language: str,
        verdict: str,
        score: float,
        execution_time: float,
        memory: float,
        tests_passed: int,
        total_tests: int,
        ai_score: float,
        code: str,
    ) -> None:
        async with async_session_factory() as session:
            sub_repo = SubmissionRepository(session)
            await sub_repo.create_submission(
                discord_id=user_id,
                problem_id=problem.id,
                problem_name=problem.name,
                language=language,
                verdict=verdict,
                score=score,
                execution_time=execution_time,
                memory=memory,
                mode=2,
                tests_passed=tests_passed,
                total_tests=total_tests,
                ai_suspicion_score=ai_score,
                contest_id=problem.contest_id,
                code_snippet=code[:1000] if code else None,
            )

    def _build_compilation_error_embed(
        self,
        user: discord.User | discord.Member,
        problem: ProblemData,
        language: str,
        compile_log: str,
        ai_score: float,
        old_rating: int,
        new_rating: int,
        is_rated: bool = True,
        is_event: bool = False,
        event_tag: str = "",
    ) -> discord.Embed:
        truncated_log = compile_log.strip()[:600]
        mode_badge = (
            "🏆 Chế độ: **Rated (Tính điểm)**"
            if is_rated
            else "🌱 Chế độ: **Unrated (Luyện tập)**"
        )
        if is_event:
            mode_badge += f" • {event_tag}"

        error_detail, fix_guide = get_error_diagnostic_and_fix(
            "Compilation Error", truncated_log, language, problem
        )

        fields = [
            {"name": "👤 Thí sinh", "value": user.mention, "inline": True},
            {
                "name": "🧩 Bài tập",
                "value": f"[{problem.id} - {problem.name}](https://codeforces.com/contest/{problem.contest_id}/problem/{problem.index})",
                "inline": True,
            },
            {"name": "💻 Ngôn ngữ", "value": f"`{language}`", "inline": True},
            {
                "name": "📋 Chi tiết nhật ký biên dịch",
                "value": f"```\n{truncated_log}\n```",
                "inline": False,
            },
            {
                "name": "💡 Cách khắc phục & Hướng dẫn sửa",
                "value": fix_guide,
                "inline": False,
            },
        ]
        if is_rated and new_rating < old_rating:
            fields.append(
                {
                    "name": "📉 Biến động Rating",
                    "value": f"`{old_rating}` ➔ **`{new_rating}`** (`{new_rating - old_rating}` pts) *(Trừ phong độ)*",
                    "inline": True,
                }
            )
        elif is_event and old_rating < 1400:
            fields.append(
                {
                    "name": "🛡️ Bảo Vệ Tân Binh",
                    "value": "Miễn trừ điểm phạt bài Event (Bạn đang dưới Rank T4)",
                    "inline": True,
                }
            )
        elif not is_rated:
            fields.append(
                {
                    "name": "🌱 Chế độ Luyện Tập",
                    "value": "Không tính điểm Score & Không đổi Rating",
                    "inline": True,
                }
            )

        fields.append(
            {
                "name": "📝 Mã Tra Cứu Bài Tập",
                "value": f"`{problem.id}` — Dùng lệnh `/search {problem.id}` để tra cứu lại đề bài, cấu trúc dữ liệu và phân tích.",
                "inline": False,
            }
        )

        return create_embed(
            title="KẾT QUẢ CHẤM BÀI: 🔘 LỖI BIÊN DỊCH (COMPILATION ERROR)",
            description=f"❌ Chương trình không thể biên dịch thành công. Vui lòng kiểm tra lại cú pháp.\n• {mode_badge}",
            embed_type=EmbedType.ERROR,
            fields=fields,
            color=0x95A5A6,
            footer_text="Docker Sandbox Judge • Mode 2 In-Discord Judge",
        )

    def _build_result_embed(
        self,
        user: discord.User | discord.Member,
        problem: ProblemData,
        language: str,
        verdict: str,
        tests_passed: int,
        total_tests: int,
        max_time: float,
        max_memory: float,
        score_earned: float,
        old_rating: int,
        new_rating: int,
        failed_reason: str,
        failed_test_type: str = "SAMPLE",
        ai_score: float = 0.0,
        ai_status: str = "Bình thường",
        ai_signals: list | None = None,
        static_warnings: list | None = None,
        eval_res: dict | None = None,
        code: str = "",
        is_rated: bool = True,
        is_event: bool = False,
        event_mult: float = 1.0,
        event_tag: str = "",
    ) -> discord.Embed:
        """Tạo EMBED 1: Bảng tổng kết kết quả chấm bài, điểm số và biến động Rating."""
        from services.rank import get_rank_badge, get_rank_by_rating

        is_accepted = "Accepted" in verdict or "Chấp nhận" in verdict
        is_prov = "Tạm chấp nhận" in verdict
        # Tiêu đề theo KẾT QUẢ TEST. Điểm AI chỉ hiển thị dạng ghi chú tham khảo
        # ở phần AI Bar bên dưới (không dán nhãn cáo buộc lên tiêu đề).

        prob_r = problem.rating or 1200
        prob_tier = get_rank_by_rating(prob_r)
        prob_badge = get_rank_badge(prob_tier)

        if is_accepted and not is_prov:
            title_str = "🟢 CHẤP NHẬN (ACCEPTED)"
            color_hex = 0x2ECC71
            embed_type = EmbedType.SUCCESS
        elif is_prov:
            title_str = "🟡 TẠM CHẤP NHẬN (PROVISIONALLY ACCEPTED)"
            color_hex = 0xF1C40F
            embed_type = EmbedType.WARNING
        elif "Wrong Answer" in verdict or "Kết quả sai" in verdict:
            title_str = "🔴 KẾT QUẢ SAI (WRONG ANSWER)"
            color_hex = 0xE74C3C
            embed_type = EmbedType.ERROR
        elif "TLE" in verdict or "thời gian" in verdict:
            title_str = "🟠 VƯỢT QUÁ THỜI GIAN (TLE)"
            color_hex = 0xE67E22
            embed_type = EmbedType.WARNING
        elif "MLE" in verdict or "bộ nhớ" in verdict:
            title_str = "🟣 VƯỢT QUÁ BỘ NHỚ (MLE)"
            color_hex = 0x9B59B6
            embed_type = EmbedType.WARNING
        elif "RTE" in verdict or "thực thi" in verdict:
            title_str = "💥 LỖI THỰC THI (RUNTIME ERROR)"
            color_hex = 0xC0392B
            embed_type = EmbedType.ERROR
        else:
            title_str = f"❓ {verdict.upper()}"
            color_hex = 0x7F8C8D
            embed_type = EmbedType.INFO

        if is_event:
            title_str = f"🔥 EVENT: {title_str}"

        progress_str = generate_progress_bar(tests_passed, total_tests)

        if not is_rated:
            description = (
                f"🌱 **CHẾ ĐỘ LUYỆN TẬP TỰ DO (UNRATED)**\n"
                f"> Vượt qua: **`{tests_passed}/{total_tests}` tests** (Themis Multi-Test Suite).\n"
                "> 💡 *Xem bảng phân tích chi tiết và code mẫu bên dưới.*"
            )
            score_display = "`+0.0 pts` *(Chế độ Luyện tập / Không tính điểm)*"
        elif is_accepted and not is_prov:
            bonus_str = f" 🔥 **x{event_mult} Điểm Thưởng Event!**" if is_event else ""
            description = (
                f"✨ **KẾT QUẢ THẨM ĐỊNH: ĐÚNG (ACCEPTED)**{bonus_str}\n"
                f"> Thí sinh đã giải chính xác toàn bộ **`{tests_passed}/{total_tests}` tests** (Themis Suite)!\n"
                "> 🎯 Hệ thống đã ghi nhận bài giải thành công. Xem phân tích tối ưu chuyên sâu bên dưới."
            )
            score_display = f"🔥 **`+{score_earned:.1f}` pts** *(Bài ⭐ {prob_r} pts • {prob_badge} {prob_tier})*"
        elif is_prov:
            description = (
                f"🟡 **KẾT QUẢ THẨM ĐỊNH: TẠM CHẤP NHẬN (PROVISIONAL)**\n"
                f"> Chương trình đã giải đúng phần lớn **`{tests_passed}/{total_tests}` tests** (Themis Suite).\n"
                f"> ✨ **Vẫn được cộng điểm thưởng khuyến khích (+{score_earned:.1f} Score & +{max(0, new_rating - old_rating)} Rating)!** Vui lòng xem bảng phân tích bên dưới để hoàn thiện bài giải lên Chấp Nhận tuyệt đối."
            )
            score_display = f"⚡ **`+{score_earned:.1f}` pts** *(Vẫn cộng điểm khuyến khích Tạm chấp nhận)*"
        else:
            description = (
                f"❌ **KẾT QUẢ THẨM ĐỊNH: SAI ({verdict.upper()})**\n"
                f"> Chương trình chỉ vượt qua **`{tests_passed}/{total_tests}` tests** (Themis Suite).\n"
                "> 💡 *Xem bảng chẩn đoán vị trí đoạn code bị lỗi và hướng dẫn khắc phục bên dưới.*"
            )
            score_display = (
                f"`{score_earned:+.1f} pts` *(Trừ điểm do chưa đạt yêu cầu)*"
                if score_earned < 0
                else "`+0.0 pts`"
            )

        fields = [
            {"name": "👤 Thí sinh", "value": user.mention, "inline": True},
            {
                "name": "🧩 Bài tập",
                "value": f"[{problem.id} - {problem.name}](https://codeforces.com/contest/{problem.contest_id}/problem/{problem.index})\n`⭐ {prob_r} pts` • {prob_badge} `{prob_tier}`",
                "inline": True,
            },
            {"name": "💻 Ngôn ngữ", "value": f"`{language}`", "inline": True},
            {
                "name": "🧪 Tiến độ vượt qua Tests",
                "value": f"{progress_str} (`{tests_passed}/{total_tests}` tests)",
                "inline": False,
            },
            {
                "name": "⏱️ Thời gian chạy",
                "value": f"`{max_time:.2f}s` / `{problem.time_limit}s`",
                "inline": True,
            },
            {
                "name": "💾 Bộ nhớ sử dụng",
                "value": f"`{max_memory:.1f} MB` / `{problem.memory_limit} MB`",
                "inline": True,
            },
            {"name": "🎯 Điểm Score Mode 2", "value": score_display, "inline": False},
        ]

        if is_rated and eval_res:
            fields.append(
                {
                    "name": "⚖️ Đánh Giá 2 Bước (Themis 15-20 Tests & BXH Contest)",
                    "value": f"{eval_res.get('step1_desc', '')}\n{eval_res.get('step2_desc', '')}",
                    "inline": False,
                }
            )

        if is_event:
            fields.append(
                {
                    "name": "🔥 Thử Thách Sự Kiện (Event Challenge)",
                    "value": f"• **Phân loại:** `{event_tag}`\n• **Hệ số thưởng:** `x{event_mult}` điểm\n• **Bảo vệ Tân Binh:** Thí sinh dưới Rank T4 không bị trừ điểm khi làm sai.",
                    "inline": False,
                }
            )

        if is_rated:
            if new_rating != old_rating:
                delta_val = new_rating - old_rating
                if delta_val > 0:
                    fields.append(
                        {
                            "name": "📈 Điểm Rating Tăng",
                            "value": f"`{old_rating}` ➔ **`{new_rating}`** (`+{delta_val}` pts) 🚀",
                            "inline": True,
                        }
                    )
                else:
                    fields.append(
                        {
                            "name": "📉 Điểm Rating Bị Trừ",
                            "value": f"`{old_rating}` ➔ **`{new_rating}`** (`{delta_val}` pts) *(Trừ phong độ)*",
                            "inline": True,
                        }
                    )
            elif is_event and old_rating < 1400:
                fields.append(
                    {
                        "name": "🛡️ Bảo Vệ Điểm Tân Binh",
                        "value": f"`{old_rating}` pts *(Không trừ điểm vì bạn đang dưới Rank T4)*",
                        "inline": True,
                    }
                )
        else:
            fields.append(
                {
                    "name": "📈 Điểm Rating",
                    "value": f"`{old_rating}` pts *(Giữ nguyên - Chế độ Unrated)*",
                    "inline": True,
                }
            )

        ai_color_badge = "🟢" if ai_score <= 30 else ("🟡" if ai_score <= 60 else "🔴")
        ai_bar = generate_progress_bar(int(ai_score), 100)
        fields.append(
            {
                "name": "🤖 Thang Đo Nghi Vấn AI Scanner",
                "value": f"{ai_bar} {ai_color_badge} **`{ai_score:.0f}/100`** — *{ai_status}*",
                "inline": False,
            }
        )

        if ai_signals and ai_score >= 40:
            signals_preview = "\n".join(f"• {s}" for s in ai_signals[:3])
            if ai_score >= 70:
                signals_preview += (
                    "\n*⚠️ Điểm cao chỉ để mod xem xét thủ công — "
                    "bài của bạn vẫn được chấm và cộng điểm bình thường.*"
                )
            fields.append(
                {
                    "name": "🔍 Cảnh báo dấu hiệu mã AI (tham khảo)",
                    "value": signals_preview,
                    "inline": False,
                }
            )

        fields.append(
            {
                "name": "📝 Mã Tra Cứu Bài Tập",
                "value": f"`{problem.id}` — Dùng `/search {problem.id}` để xem lại toàn bộ đề bài, phân tích và đáp án.",
                "inline": False,
            }
        )

        footer_text = f"Mã tra cứu: {problem.id} • Dùng /search {problem.id} | Bảng Kết Quả • {'Chế độ Rated (Thi đấu)' if is_rated else 'Chế độ Unrated (Luyện tập)'}"
        if is_event:
            footer_text += f" • {event_tag}"

        embed = create_embed(
            title=f"KẾT QUẢ CHẤM BÀI: {title_str}",
            description=description,
            embed_type=embed_type,
            fields=fields,
            color=color_hex,
            footer_text=footer_text,
        )
        return embed

    def _build_analysis_embed(
        self,
        user: discord.User | discord.Member,
        problem: ProblemData,
        language: str,
        verdict: str,
        tests_passed: int,
        total_tests: int,
        max_time: float,
        max_memory: float,
        failed_reason: str,
        failed_test_type: str = "SAMPLE",
        code: str = "",
        is_rated: bool = True,
        ai_score: float = 0.0,
    ) -> discord.Embed:
        """Tạo EMBED PHÂN TÍCH: Bảng chẩn đoán vị trí lỗi sai từng dòng hoặc phân tích tối ưu hiệu năng chuyên sâu."""
        is_accepted = "Accepted" in verdict or "Chấp nhận" in verdict
        is_prov = "Tạm chấp nhận" in verdict
        fields = []

        # Phân tích từng dòng mã nguồn
        line_analysis = get_line_by_line_code_analysis(
            code=code,
            language=language,
            problem=problem,
            verdict=verdict,
            is_accepted=is_accepted,
            failed_test_type=failed_test_type,
            execution_time=max_time,
            memory_used_mb=max_memory,
        )

        if is_accepted and not is_prov:
            # ── EMBED: TỐI ƯU HÓA MÃ NGUỒN KHI ĐÚNG 100% ──
            title_str = "⚡ PHÂN TÍCH TỐI ƯU HÓA MÃ NGUỒN & HIỆU NĂNG CHUYÊN SÂU"
            color_hex = 0x2ECC71
            embed_type = EmbedType.SUCCESS
            desc = (
                f"🟢 **Mã nguồn đã giải quyết chính xác 100% bài toán `{problem.id} - {problem.name}`!**\n"
                f"> Dưới đây là phân tích chi tiết từng dòng, kỹ thuật Fast I/O và tối ưu bộ nhớ nhằm chuẩn bị cho các bài tập phân hạng cao hơn."
            )

            fields.append(
                {
                    "name": "📝 Phân Tích Chi Tiết Từng Dòng Mã Nguồn (Line-by-Line Code Review)",
                    "value": line_analysis,
                    "inline": False,
                }
            )

            lang_lower = language.lower()
            if "c++" in lang_lower or "cpp" in lang_lower:
                if "ios_base::sync_with_stdio" not in code:
                    fields.append(
                        {
                            "name": "🚀 Tối Ưu Tốc Độ Đọc/Ghi (C++ Fast I/O)",
                            "value": "Thêm `ios_base::sync_with_stdio(false); cin.tie(NULL);` ở đầu hàm `main()` để giảm thời gian đọc dữ liệu xuống gấp 3-5 lần.",
                            "inline": False,
                        }
                    )
                if "endl" in code:
                    fields.append(
                        {
                            "name": "⚡ Tối Ưu Xuất Dữ Liệu",
                            "value": "Thay thế `endl` bằng `'\\n'` để tránh thao tác `flush` bộ đệm liên tục gây chậm trễ thời gian I/O.",
                            "inline": False,
                        }
                    )
                fields.append(
                    {
                        "name": "💾 Quản Lý Bộ Nhớ & Tham Chiếu (Memory Efficiency)",
                        "value": "Luôn truyền mảng hoặc `vector` qua tham chiếu hằng (`const vector<int>& arr`) trong các hàm phụ trợ để tránh sao chép tốn `O(N)` bộ nhớ.",
                        "inline": False,
                    }
                )
            elif "python" in lang_lower:
                if "sys.stdin.readline" not in code:
                    fields.append(
                        {
                            "name": "🚀 Tối Ưu Đọc Dữ Liệu (Python Fast I/O)",
                            "value": "Thêm `import sys; input = sys.stdin.readline` ở đầu file thay cho hàm `input()` mặc định để xử lý mảng `10^5` phần tử cực nhanh.",
                            "inline": False,
                        }
                    )
                fields.append(
                    {
                        "name": "⚡ Cấu Trúc Dữ Liệu Tối Ưu",
                        "value": "Sử dụng `collections.deque` khi cần thao tác thêm/xóa ở 2 đầu hàng đợi (`O(1)`) thay vì `list.pop(0)` (`O(N)`).",
                        "inline": False,
                    }
                )

            fields.append(
                {
                    "name": "🧹 Clean Code & Cấu Trúc Mã Nguồn",
                    "value": "Nên tách logic giải bài thành một hàm `solve()` độc lập cho từng testcase để code sáng sủa, dễ gỡ lỗi và tái sử dụng.",
                    "inline": False,
                }
            )

        elif is_prov:
            # ── EMBED: HƯỚNG DẪN HOÀN THIỆN KHI TẠM CHẤP NHẬN ──
            title_str = "🟡 HƯỚNG DẪN HOÀN THIỆN ĐỂ ĐẠT ĐIỂM TUYỆT ĐỐI"
            color_hex = 0xF1C40F
            embed_type = EmbedType.WARNING
            desc = (
                f"🟡 **Bài nộp đã đạt trạng thái TẠM CHẤP NHẬN ({tests_passed}/{total_tests} tests)!**\n"
                f"> Bạn đã nhận được điểm cơ sở. Dưới đây là phân tích từng dòng và các vị trí cần chú ý để hoàn thiện 100% bài test:"
            )

            fields.append(
                {
                    "name": "📝 Phân Tích Chi Tiết Từng Dòng Mã Nguồn (Line-by-Line Code Review)",
                    "value": line_analysis,
                    "inline": False,
                }
            )
            fields.append(
                {
                    "name": "🎯 Kiểm Tra Các Trường Hợp Biên (Edge Cases)",
                    "value": (
                        "• `N = 1` hoặc mảng rỗng.\n"
                        "• Mảng có tất cả phần tử bằng nhau hoặc chứa số âm cực đại.\n"
                        "• Giá trị đầu vào đạt trần giới hạn `10^9` (kiểm tra nguy cơ tràn số `int` 32-bit)."
                    ),
                    "inline": False,
                }
            )
            fields.append(
                {
                    "name": "⚡ Tối Ưu Hóa Thời Gian Chạy (Tránh bẫy TLE)",
                    "value": (
                        f"• Thời gian chạy hiện tại: `{max_time:.2f}s` / `{problem.time_limit}s`.\n"
                        "• Đảm bảo không sử dụng vòng lặp lồng nhau `O(N^2)` khi `N >= 10^5`.\n"
                        "• Tích hợp Fast I/O để tăng tốc độ đọc dữ liệu."
                    ),
                    "inline": False,
                }
            )

        else:
            # ── EMBED: CHẨN ĐOÁN LỖI SAI KHI LÀM SAI / LỖI ──
            title_str = "🔍 CHẨN ĐOÁN & PHÂN TÍCH LỖI SAI TỪNG DÒNG MÃ NGUỒN"
            color_hex = 0xE74C3C
            embed_type = EmbedType.ERROR
            desc = (
                f"❌ **Chương trình chưa vượt qua toàn bộ bài test ({tests_passed}/{total_tests} tests).**\n"
                f"> Dưới đây là phân tích lỗi chi tiết từng dòng mã nguồn và hướng dẫn khắc phục:"
            )

            fields.append(
                {
                    "name": "📝 Phân Tích Lỗi Từng Dòng Mã Nguồn (Line-by-Line Error Analysis)",
                    "value": line_analysis,
                    "inline": False,
                }
            )

            if is_rated:
                loc_detail, fix_guide = get_rated_error_diagnostic_and_location(
                    code=code,
                    language=language,
                    problem=problem,
                    verdict=verdict,
                    failed_test_type=failed_test_type,
                    execution_time=max_time,
                    memory_used_mb=max_memory,
                )
                fields.append(
                    {
                        "name": "🔍 Phân Tích Khối Lệnh Nghi Vấn (Bảo Mật Rated)",
                        "value": loc_detail,
                        "inline": False,
                    }
                )
                fields.append(
                    {
                        "name": "💡 Hướng Dẫn Tự Sửa Lỗi Chi Tiết",
                        "value": fix_guide,
                        "inline": False,
                    }
                )
            else:
                sample_tpl = get_sample_solution_template(problem, language)
                lang_syntax = (
                    "python"
                    if "python" in language.lower() or "py" in language.lower()
                    else ("java" if "java" in language.lower() else "cpp")
                )
                fields.append(
                    {
                        "name": "📖 Code Mẫu Chuẩn Tham Khảo (Reference Template)",
                        "value": f"```{lang_syntax}\n{sample_tpl[:700]}\n```",
                        "inline": False,
                    }
                )

                review_title, review_content = get_unrated_deep_code_review(
                    code=code,
                    language=language,
                    problem=problem,
                    is_accepted=is_accepted,
                    verdict=verdict,
                    failed_reason=failed_reason,
                    tests_passed=tests_passed,
                    total_tests=total_tests,
                )
                fields.append(
                    {
                        "name": review_title,
                        "value": review_content,
                        "inline": False,
                    }
                )

        fields.append(
            {
                "name": "📝 Tra Cứu Toàn Bộ Dữ Liệu Bài Tập",
                "value": f"Sử dụng lệnh `/search {problem.id}` để xem lại đề bài, phân tích và lời giải chuẩn AC bất kỳ lúc nào.",
                "inline": False,
            }
        )

        embed = create_embed(
            title=title_str,
            description=desc,
            embed_type=embed_type,
            fields=fields,
            color=color_hex,
            footer_text=f"Mã tra cứu: {problem.id} • Dùng /search {problem.id} • Bảng Phân Tích & Hướng Dẫn",
        )
        return embed
