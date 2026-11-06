"""Algorithmic Problem Bank & Generator for Ranked 1:1 Duels with Fine-Grained Tier Hierarchy and Practical Real-World Algorithms."""

import random
from dataclasses import dataclass, field
import discord
from services.rank import RANK_ORDER, get_rank_badge, get_rank_index, get_tier_division


@dataclass
class DuelProblem:
    """Represents a competitive programming algorithmic problem for 1:1 duel."""

    id: str
    name: str
    tier: str  # T8, T7, T6, T5, T4, T3, LT2, MT2, HT2, LT1, MT1, HT1
    division: str  # Div. 4, Div. 3, Div. 2, Div. 1
    rating_display: str  # e.g. "T8 / Rating: 300 pts", "T5 / Rating: 1300 pts"
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
        """Trả về bản hướng dẫn tư duy giải thuật chi tiết (Editorial), không lộ mã nguồn đáp án."""
        if self.editorial:
            return self.editorial.strip()
        
        # Tạo bản hướng dẫn chuyên sâu từ hint và ràng buộc
        return (
            f"🧠 **Ý TƯỞNG THUẬT TOÁN TRỌNG TÂM:**\n"
            f"{self.hint}\n\n"
            f"⚙️ **PHÂN TÍCH TIẾP CẬN & CẤU TRÚC DỮ LIỆU:**\n"
            f"• Xem xét kỹ ràng buộc dữ liệu ({self.constraints.split('.')[0] if '.' in self.constraints else self.constraints}) để lựa chọn thuật toán có độ phức tạp phù hợp.\n"
            f"• Xác định rõ trạng thái ban đầu, công thức chuyển đổi hoặc quy tắc cập nhật trên cây / đồ thị / mảng.\n\n"
            f"⚠️ **CÁC BẪY TESTCASE & TRƯỜNG HỢP BIÊN:**\n"
            f"• Kiểm tra kỹ các trường hợp đặc biệt: `N = 1`, đồ thị không liên thông, giá trị âm hoặc mảng đã sắp xếp sẵn.\n"
            f"• Chú ý kiểm soát tràn số nguyên (khuyến nghị dùng kiểu số nguyên 64-bit `long long`)."
        )

    def get_solution_for_lang(self, lang: str = "cpp") -> tuple[str, str]:
        """
        Trả về (mã_nguồn, cú_pháp_highlight) có chú thích giải thuật (# hoặc //):
        - Nếu lang là Python ('py', 'python', 'python3') -> Trả về solution_py (hoặc solution_code).
        - Nếu lang là Java ('java') -> Trả về solution Java.
        - Nếu lang là Pascal ('pas', 'pascal') -> Trả về solution Pascal.
        - Nếu lang là C/C++ ('cpp', 'c', 'cxx') -> Trả về solution_cpp (hoặc solution_code).
        """
        l = (lang or "").lower()
        if any(x in l for x in ["py", "python"]):
            if self.solution_py:
                return self.solution_py.strip(), "python"
            if self.solution_code and ("import " in self.solution_code or "def " in self.solution_code):
                return self.solution_code.strip(), "python"
            py_fallback = (
                f"# [1] Lời giải mẫu Python 3 cho: {self.name} ({self.tier} • {self.division})\n"
                f"import sys\n\n"
                f"def solve():\n"
                f"    # [2] Phân tách và đọc dữ liệu đầu vào tốc độ cao\n"
                f"    data = sys.stdin.read().split()\n"
                f"    if not data: return\n"
                f"    # [3] Thuật toán xử lý và in kết quả\n"
                f"    # {self.hint}\n"
                f"    pass\n\n"
                f"if __name__ == '__main__':\n"
                f"    solve()\n"
            )
            return py_fallback, "python"
        elif any(x in l for x in ["java"]):
            java_fallback = (
                f"// [1] Lời giải mẫu Java cho: {self.name} ({self.tier} • {self.division})\n"
                f"import java.io.*;\n"
                f"import java.util.*;\n\n"
                f"public class Main {{\n"
                f"    public static void main(String[] args) throws IOException {{\n"
                f"        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n"
                f"        StringTokenizer st = new StringTokenizer(br.readLine() == null ? \"\" : br.readLine());\n"
                f"        // {self.hint}\n"
                f"    }}\n"
                f"}}\n"
            )
            return java_fallback, "java"
        elif any(x in l for x in ["pascal", "pas"]):
            pas_fallback = (
                f"// [1] Lời giải mẫu Pascal cho: {self.name} ({self.tier} • {self.division})\n"
                f"program Solution;\n"
                f"var n: int64;\n"
                f"begin\n"
                f"    // {self.hint}\n"
                f"end.\n"
            )
            return pas_fallback, "pascal"
        else:
            if self.solution_cpp:
                return self.solution_cpp.strip(), "cpp"
            if self.solution_code:
                return self.solution_code.strip(), "cpp"
            cpp_fallback = (
                f"// [1] Lời giải mẫu C++ cho: {self.name} ({self.tier} • {self.division})\n"
                f"#include <iostream>\n"
                f"#include <vector>\n"
                f"#include <algorithm>\n"
                f"using namespace std;\n\n"
                f"int main() {{\n"
                f"    // [2] Tối ưu hóa I/O tốc độ cao\n"
                f"    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
                f"    // [3] Thuật toán xử lý: {self.hint}\n"
                f"    return 0;\n"
                f"}}\n"
            )
            return cpp_fallback, "cpp"

    def render_embeds(self) -> list[discord.Embed]:
        """
        Tách giao diện đề bài thành 3 Rich Embeds gọn gàng, trực diện:
        - Embed 1: Tên bài & Thông số thi đấu (Bậc Rank, Rating, Điểm chặng, File nộp .py, .cpp...)
        - Embed 2: Đề bài (Trực diện, không tiêu đề rườm rà, có ảnh nếu có)
        - Embed 3: Input, Output, Ràng buộc & Ví dụ (Trực diện, không tiêu đề cồng kềnh)
        """
        badge = get_rank_badge(self.tier)
        color = (
            0xF1C40F
            if self.division == "Div. 4"
            else 0x3498DB
            if self.division == "Div. 3"
            else 0x9B59B6
            if self.division == "Div. 2"
            else 0xE74C3C
        )

        tags_str = " ".join(f"`{t}`" for t in self.tags) if self.tags else "`ad-hoc`"

        # Hiển thị độ khó leo thang nếu là chặng 2 trở đi
        escalation_str = ""
        bonus_pct = getattr(self, "difficulty_bonus_pct", 0)
        round_idx = getattr(self, "round_index", 1)
        if bonus_pct > 0 or round_idx > 1:
            escalation_str = f"• 🔥 **Áp lực đấu trường (Chặng {round_idx}):** Độ khó `+{bonus_pct}%` *(Thử thách leo thang!)*\n"

        scaled_rating = int(round(self.rating * (1.0 + bonus_pct / 100.0))) if bonus_pct > 0 else self.rating
        if bonus_pct > 0:
            rating_text = f"{self.tier} / Rating: {scaled_rating} pts (+{bonus_pct}%)"
        else:
            rating_text = self.rating_display or f"{self.tier} / Rating: {self.rating} pts"

        # Embed 1: Tên bài & Thông số chặng đấu
        embed_info = discord.Embed(
            title=f"⚔️ {self.name.upper()}",
            description=(
                f"• **Bậc Rank:** {badge} `{self.tier}` • 🏷️ `{self.division}`\n"
                f"• **Thang điểm Rating:** `{rating_text}`\n"
                f"{escalation_str}"
                f"• **Tags Thuật toán:** {tags_str}\n"
                f"• **Cơ chế chặng:** Thua mất 1 mạng (💔) • Thắng giữ nguyên mạng (❤️❤️)\n"
                f"• **Thời gian làm bài:** `{self.time_limit_minutes} phút`  •  **Giới hạn thực thi:** `{self.time_limit_sec}s` • `{self.memory_limit_mb}MB` • `≤ {self.max_code_size_kb} KB`\n"
                f"• **Định dạng file nộp:** Đính kèm file code (`.py`, `.cpp`, `.java`, `.c`, `.cs`, `.js`...)"
            ),
            color=color,
        )

        # Embed 2: Đề bài (Chữ to, rõ ràng với Header Markdown và Blockquote)
        statement_text = self.statement.strip()
        # Đảm bảo có Heading lớn ở đầu nếu chưa có
        if not statement_text.startswith("#"):
            statement_text = f"## 📖 ĐỀ BÀI CHI TIẾT\n{statement_text}"

        embed_statement = discord.Embed(
            description=statement_text,
            color=color,
        )
        if getattr(self, "image_url", None):
            embed_statement.set_image(url=self.image_url)

        # Embed 3: Input, Output, Ràng buộc, Ví dụ & Giải thích (Chữ to rõ với Heading 2)
        spec_text = (
            f"## 📥 Input Format\n{self.input_format.strip()}\n\n"
            f"## 📤 Output Format\n{self.output_format.strip()}\n\n"
            f"## ⚠️ Ràng buộc\n{self.constraints.strip()}\n\n"
            f"## 💡 Ví dụ Mẫu\n"
            f"**Input:**\n```text\n{self.sample_input.strip()}\n```\n"
            f"**Output:**\n```text\n{self.sample_output.strip()}\n```"
        )
        if self.sample_explanation:
            spec_text += f"\n\n## 💡 Giải thích ví dụ\n{self.sample_explanation.strip()}"

        embed_spec = discord.Embed(
            description=spec_text,
            color=color,
        )

        return [embed_info, embed_statement, embed_spec]

    def render_embed(self) -> discord.Embed:
        """Hỗ trợ tương thích ngược trả về Embed 1."""
        return self.render_embeds()[0]


# ==============================================================================
# NGÂN HÀNG ĐỀ BÀI THUẬT TOÁN ĐA DẠNG & THỰC TẾ TRẢI DÀI 12 BẬC TIER (T8 -> HT1)
# ==============================================================================

PROBLEM_BANK: list[DuelProblem] = [
    # --------------------------------------------------------------------------
    # 1. BẬC T8 (Div. 4 - Rating: 300 pts) — Dễ nhất, toán/mảng cơ bản (15p, 64KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_t8_sum_even",
        name="Tổng Doanh Thu Ca Tối (Các Giao Dịch Chẵn)",
        tier="T8",
        division="Div. 4",
        rating_display="T8 / Rating: 300 pts",
        statement=(
            "Một cửa hàng tiện lợi tổng kết `n` giao dịch trong ngày với giá trị lần lượt là `a_1, a_2, ..., a_n`.\n"
            "Chương trình khuyến mãi chỉ áp dụng chiết khấu tích điểm cho các giao dịch có giá trị là số chẵn.\n"
            "Hãy viết chương trình tính tổng giá trị của toàn bộ các giao dịch số chẵn trong ngày."
        ),
        input_format="Dòng đầu tiên chứa số nguyên `n` (`1 <= n <= 10^4`). Dòng thứ hai chứa `n` số nguyên `a_i` (`-10^9 <= a_i <= 10^9`).",
        output_format="In ra một số nguyên duy nhất là tổng giá trị các giao dịch chẵn.",
        constraints="`1 <= n <= 10^4`, `-10^9 <= a_i <= 10^9`. Giới hạn: `1.0s`, `256MB`, `64KB`.",
        sample_input="5\n1 2 3 4 5",
        sample_output="6",
        secret_tests=[
            {"input": "5\n1 2 3 4 5", "output": "6"},
            {"input": "4\n-2 4 6 7", "output": "8"},
            {"input": "3\n1 3 5", "output": "0"},
            {"input": "1\n100", "output": "100"},
            {"input": "6\n0 0 2 -4 5 10", "output": "8"},
        ],
        time_limit_minutes=15,
        max_code_size_kb=64,
        rating=300,
        tags=["implementation", "math"],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Các giao dịch có giá trị chẵn trong ngày là 2 và 4. Tổng giá trị: 2 + 4 = 6.",
        hint="💡 Gợi ý: Dùng vòng lặp for duyệt từng phần tử và toán tử % 2 == 0 để lọc các số chẵn cộng dồn!",
        solution_code=(
            "#include <iostream>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n; if (!(cin >> n)) return 0;\n"
            "    long long sum = 0;\n"
            "    for (int i = 0; i < n; ++i) {\n"
            "        long long x; cin >> x;\n"
            "        if (x % 2 == 0) sum += x;\n"
            "    }\n"
            '    cout << sum << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    DuelProblem(
        id="duel_t8_palindrome",
        name="Kiểm Tra Mã Vận Đơn Đối Xứng (Palindrome)",
        tier="T8",
        division="Div. 4",
        rating_display="T8 / Rating: 350 pts",
        statement=(
            "Công ty chuyển phát nhanh quy ước các kiện hàng cao cấp có mã vận đơn là một chuỗi ký tự đối xứng (Palindrome).\n"
            "Cho chuỗi mã vận đơn `s` chỉ gồm các chữ cái in thường. Hãy kiểm tra xem mã vận đơn này có phải là chuỗi đối xứng hay không."
        ),
        input_format="Một dòng duy nhất chứa chuỗi ký tự `s` có độ dài từ `1` đến `10^5`.",
        output_format="In ra `YES` nếu mã vận đơn đối xứng, ngược lại in ra `NO`.",
        constraints="`1 <= |s| <= 10^5`. Các ký tự chỉ từ `a` đến `z`. Giới hạn: `1.0s`, `256MB`, `64KB`.",
        sample_input="racecar",
        sample_output="YES",
        secret_tests=[
            {"input": "racecar", "output": "YES"},
            {"input": "hello", "output": "NO"},
            {"input": "a", "output": "YES"},
            {"input": "abccba", "output": "YES"},
            {"input": "abcdeba", "output": "NO"},
        ],
        time_limit_minutes=15,
        max_code_size_kb=64,
        rating=350,
        tags=['strings', 'implementation'],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Chuỗi 'racecar' đọc từ trái sang phải hay từ phải sang trái đều giống nhau nên in ra YES.",
        hint="💡 Gợi ý: So sánh ký tự tại hai đầu chuỗi với kỹ thuật 2 con trỏ l = 0, r = len - 1!",
        solution_code=(
            "#include <iostream>\n"
            "#include <string>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    string s; if (!(cin >> s)) return 0;\n"
            "    int l = 0, r = (int)s.length() - 1;\n"
            "    bool ok = true;\n"
            "    while (l < r) {\n"
            "        if (s[l++] != s[r--]) { ok = false; break; }\n"
            "    }\n"
            '    cout << (ok ? "YES" : "NO") << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 2. BẬC T7 (Div. 4 - Rating: 550 pts) — Sàng nguyên tố & Mảng tiền tố (15p, 64KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_t7_prime_count",
        name="Thống Kê Khách Hàng VIP Có Mã ID Nguyên Tố",
        tier="T7",
        division="Div. 4",
        rating_display="T7 / Rating: 550 pts",
        statement=(
            "Sàn thương mại điện tử triển khai tri ân các khách hàng có mã định danh `ID` là một số nguyên tố.\n"
            "Cho một khoảng mã định danh từ `L` đến `R`. Hãy đếm xem có bao nhiêu khách hàng VIP có mã ID nguyên tố trong đoạn `[L, R]`."
        ),
        input_format="Một dòng duy nhất chứa hai số nguyên `L` và `R` (`1 <= L <= R <= 10^6`).",
        output_format="In ra số lượng mã ID nguyên tố trong đoạn `[L, R]`.",
        constraints="`1 <= L <= R <= 10^6`. Yêu cầu thuật toán sàng Eratosthenes + Mảng tiền tố `O(N)`. Giới hạn: `1.0s`, `256MB`, `64KB`.",
        sample_input="1 10",
        sample_output="4",
        secret_tests=[
            {"input": "1 10", "output": "4"},
            {"input": "10 20", "output": "4"},
            {"input": "14 16", "output": "0"},
            {"input": "2 2", "output": "1"},
            {"input": "1 100", "output": "25"},
        ],
        time_limit_minutes=15,
        max_code_size_kb=64,
        rating=550,
        tags=["number theory", "math"],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Các số nguyên tố trong đoạn [1, 10] là 2, 3, 5, 7. Tổng cộng có 4 mã ID khách hàng VIP.",
        hint="💡 Gợi ý: Dùng sàng Eratosthenes tiền xử lý mảng nguyên tố đến 10^6 và mảng tiền tố để đếm trong O(1)!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "using namespace std;\n\n"
            "const int MAXN = 1000000;\n"
            "int pref[MAXN + 1];\n"
            "bool is_p[MAXN + 1];\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    for (int i = 2; i <= MAXN; i++) is_p[i] = true;\n"
            "    for (int p = 2; p * p <= MAXN; p++) {\n"
            "        if (is_p[p]) {\n"
            "            for (int i = p * p; i <= MAXN; i += p) is_p[i] = false;\n"
            "        }\n"
            "    }\n"
            "    for (int i = 1; i <= MAXN; i++) pref[i] = pref[i - 1] + (is_p[i] ? 1 : 0);\n"
            "    int l, r;\n"
            '    if (cin >> l >> r) cout << pref[r] - pref[l - 1] << "\\n";\n'
            "    return 0;\n"
            "}\n"
        ),
    ),
    # --------------------------------------------------------------------------
    # 3. BẬC T6 (Div. 4 / Div. 3 - Rating: 850-950 pts) — Chứng khoán & Kadane O(N) (18p, 64KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_t6_stock_trading",
        name="Giao Dịch Cổ Phiếu Tối Ưu Lợi Nhuận",
        tier="T6",
        division="Div. 4",
        rating_display="T6 / Rating: 850 pts",
        statement=(
            "Một nhà đầu tư theo dõi giá cổ phiếu của một tập đoàn công nghệ trong `n` ngày liên tiếp, ngày thứ `i` có giá là `a_i`.\n"
            "Nhà đầu tư được phép chọn 1 ngày `i` để mua vào và 1 ngày `j` (`j > i`) sau đó để bán ra.\n"
            "Hãy tìm lợi nhuận tối đa `a_j - a_i` mà nhà đầu tư có thể đạt được (nếu giá chỉ giảm liên tục, lợi nhuận có thể là số âm thể hiện khoản lỗ nhỏ nhất)."
        ),
        input_format="Dòng đầu chứa số nguyên `n` (`2 <= n <= 10^5`). Dòng thứ hai chứa `n` số nguyên `a_i` (`-10^9 <= a_i <= 10^9`).",
        output_format="In ra một số nguyên duy nhất là lợi nhuận lớn nhất tìm được.",
        constraints="`2 <= n <= 10^5`, `-10^9 <= a_i <= 10^9`. Thuật toán `O(N)` 1 lần duyệt. Giới hạn: `1.0s`, `256MB`, `64KB`.",
        sample_input="5\n7 1 5 3 6",
        sample_output="5",
        secret_tests=[
            {"input": "5\n7 1 5 3 6", "output": "5"},
            {"input": "5\n7 6 4 3 1", "output": "-1"},
            {"input": "2\n10 20", "output": "10"},
            {"input": "4\n3 3 3 3", "output": "0"},
        ],
        time_limit_minutes=18,
        max_code_size_kb=64,
        rating=850,
        tags=["greedy", "implementation"],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Mua tại ngày thứ 2 với giá 1 và bán tại ngày thứ 5 với giá 6. Lợi nhuận lớn nhất thu được: 6 - 1 = 5.",
        hint="💡 Gợi ý: Duyệt từ trái sang phải, vừa duy trì giá trị nhỏ nhất min_val vừa cập nhật max_diff = max(max_diff, a[j] - min_val)!",
        solution_code=(
            "#include <iostream>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n; if (!(cin >> n)) return 0;\n"
            "    long long min_val; cin >> min_val;\n"
            "    long long max_diff = -2e18;\n"
            "    for (int i = 1; i < n; i++) {\n"
            "        long long x; cin >> x;\n"
            "        max_diff = max(max_diff, x - min_val);\n"
            "        min_val = min(min_val, x);\n"
            "    }\n"
            '    cout << max_diff << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    DuelProblem(
        id="duel_t6_max_subarray",
        name="Chuỗi Ngày Doanh Thu Liên Tiếp Lớn Nhất (Kadane)",
        tier="T6",
        division="Div. 4",
        rating_display="T6 / Rating: 950 pts",
        statement=(
            "Một công ty khởi nghiệp ghi nhận bảng biến động lợi nhuận ròng hàng ngày trong `n` ngày (có ngày lời dương, ngày lỗ âm).\n"
            "Ban giám đốc muốn tìm một khoảng thời gian liên tục gồm ít nhất 1 ngày có tổng lợi nhuận ròng đạt giá trị lớn nhất."
        ),
        input_format="Dòng đầu chứa số nguyên `n` (`1 <= n <= 10^5`). Dòng thứ hai chứa `n` số nguyên `a_i` (`-10^9 <= a_i <= 10^9`).",
        output_format="In ra tổng lợi nhuận lớn nhất của đoạn ngày liên tiếp.",
        constraints="`1 <= n <= 10^5`, `-10^9 <= a_i <= 10^9`. Thuật toán Kadane `O(N)`. Giới hạn: `1.0s`, `256MB`, `64KB`.",
        sample_input="8\n-2 -3 4 -1 -2 1 5 -3",
        sample_output="7",
        secret_tests=[
            {"input": "8\n-2 -3 4 -1 -2 1 5 -3", "output": "7"},
            {"input": "5\n-1 -2 -3 -4 -5", "output": "-1"},
            {"input": "4\n1 2 3 4", "output": "10"},
            {"input": "1\n-100", "output": "-100"},
            {"input": "6\n5 -2 3 -1 2 -5", "output": "7"},
        ],
        time_limit_minutes=18,
        max_code_size_kb=64,
        rating=950,
        tags=["dp", "greedy"],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Đoạn con liên tiếp có tổng lớn nhất là [4, -1, 2, 1] với tổng doanh thu tích lũy = 6.",
        hint="💡 Gợi ý: Áp dụng thuật toán Kadane O(N) lưu trữ max_ending_here và max_so_far!",
        solution_code=(
            "#include <iostream>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n; if (!(cin >> n)) return 0;\n"
            "    long long x; cin >> x;\n"
            "    long long max_so_far = x, max_ending = x;\n"
            "    for (int i = 1; i < n; i++) {\n"
            "        cin >> x;\n"
            "        max_ending = max(x, max_ending + x);\n"
            "        max_so_far = max(max_so_far, max_ending);\n"
            "    }\n"
            '    cout << max_so_far << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 4. BẬC T5 (Div. 3 - Rating: 1300 pts) — Đối soát ngân hàng Two Pointers (20p, 128KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_t5_two_sum_sorted",
        name="Đối Soát Khớp Lệnh Giao Dịch Ngân Hàng Tổng K",
        tier="T5",
        division="Div. 3",
        rating_display="T5 / Rating: 1300 pts",
        statement=(
            "Hệ thống thanh toán tự động của ngân hàng nhận được `n` hóa đơn đã được sắp xếp tăng dần theo giá trị tiền.\n"
            "Bộ phận kế toán cần ghép cặp hai hóa đơn bất kỳ `(i, j)` với `1 <= i < j <= n` sao cho tổng số tiền của chúng đúng bằng hạn mức `k`.\n"
            "Hãy đếm xem có bao nhiêu cặp hóa đơn thỏa mãn điều kiện khớp lệnh trên."
        ),
        input_format="Dòng đầu chứa hai số `n` và `k` (`1 <= n <= 2 * 10^5`, `-10^9 <= k <= 10^9`). Dòng hai chứa `n` số nguyên tăng dần.",
        output_format="In ra số lượng cặp hóa đơn thỏa mãn.",
        constraints="`1 <= n <= 2 * 10^5`. Yêu cầu thuật toán Hai con trỏ `O(N)`. Giới hạn: `1.0s`, `256MB`, `128KB`.",
        sample_input="6 6\n1 2 3 3 4 5",
        sample_output="3",
        secret_tests=[
            {"input": "6 6\n1 2 3 3 4 5", "output": "3"},
            {"input": "4 10\n1 2 3 4", "output": "0"},
            {"input": "5 4\n2 2 2 2 2", "output": "10"},
            {"input": "2 0\n-5 5", "output": "1"},
        ],
        time_limit_minutes=20,
        max_code_size_kb=128,
        rating=1300,
        tags=["two pointers", "sortings"],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Các cặp chỉ số (i, j) có a[i] + a[j] = 6 là: (1, 6) [1 + 5 = 6], (2, 5) [2 + 4 = 6], (3, 4) [3 + 3 = 6]. Tổng cộng có 3 cặp khớp lệnh.",
        hint="💡 Gợi ý: Tận dụng mảng đã sắp xếp với kỹ thuật 2 con trỏ (Two Pointers) từ 2 đầu mảng!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n; long long k;\n"
            "    if (!(cin >> n >> k)) return 0;\n"
            "    vector<long long> a(n);\n"
            "    for (int i = 0; i < n; i++) cin >> a[i];\n"
            "    int l = 0, r = n - 1;\n"
            "    long long ans = 0;\n"
            "    while (l < r) {\n"
            "        long long sum = a[l] + a[r];\n"
            "        if (sum == k) {\n"
            "            if (a[l] == a[r]) {\n"
            "                long long cnt = r - l + 1;\n"
            "                ans += cnt * (cnt - 1) / 2;\n"
            "                break;\n"
            "            } else {\n"
            "                int c1 = 1, c2 = 1;\n"
            "                while (l + 1 < r && a[l] == a[l + 1]) { l++; c1++; }\n"
            "                while (r - 1 > l && a[r] == a[r - 1]) { r--; c2++; }\n"
            "                ans += 1LL * c1 * c2;\n"
            "                l++; r--;\n"
            "            }\n"
            "        } else if (sum < k) l++;\n"
            "        else r--;\n"
            "    }\n"
            '    cout << ans << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 5. BẬC T4 (Div. 3 - Rating: 1500 pts) — ATM & Quy hoạch động 1D (22p, 128KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_t4_coin_change",
        name="Cây ATM Trả Tiền Tối Thiểu Số Lượng Tờ Tiền (DP 1D)",
        tier="T4",
        division="Div. 3",
        rating_display="T4 / Rating: 1500 pts",
        statement=(
            "Một máy ATM thế hệ mới được nạp `n` loại mệnh giá tiền mặt `c_1, c_2, ..., c_n` (số lượng mỗi mệnh giá là không giới hạn).\n"
            "Khách hàng yêu cầu rút số tiền đúng bằng `S`. Hãy lập trình để máy ATM nhả ra số lượng tờ tiền là ít nhất có thể.\n"
            "Nếu không thể đổi được chính xác số tiền `S`, in ra `-1`."
        ),
        input_format="Dòng đầu chứa hai số `n` và `S` (`1 <= n <= 100`, `1 <= S <= 10^5`). Dòng thứ hai chứa `n` số nguyên `c_i` (`1 <= c_i <= 10^4`).",
        output_format="In ra số lượng tờ tiền ít nhất, hoặc `-1` nếu không thể đổi được.",
        constraints="`1 <= n <= 100`, `1 <= S <= 10^5`. Thuật toán quy hoạch động 1 chiều `O(n * S)`. Giới hạn: `1.0s`, `256MB`, `128KB`.",
        sample_input="3 11\n1 5 6",
        sample_output="2",
        secret_tests=[
            {"input": "3 11\n1 5 6", "output": "2"},
            {"input": "2 3\n2 4", "output": "-1"},
            {"input": "1 10\n1", "output": "10"},
            {"input": "4 20\n1 2 5 10", "output": "2"},
        ],
        time_limit_minutes=22,
        max_code_size_kb=128,
        rating=1500,
        tags=["dp"],
        time_limit_sec=1.0,
        memory_limit_mb=256,
        sample_explanation="Để rút 11 đồng, phương án tối ưu là trả 2 tờ: 1 tờ 5 đồng và 1 tờ 6 đồng (5 + 6 = 11).",
        hint="💡 Gợi ý: Quy hoạch động 1 chiều dp[S] = min(dp[S], dp[S - coin] + 1) với dp[0] = 0!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "const int INF = 1e9;\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n, S; if (!(cin >> n >> S)) return 0;\n"
            "    vector<int> c(n);\n"
            "    for (int i = 0; i < n; i++) cin >> c[i];\n"
            "    vector<int> dp(S + 1, INF);\n"
            "    dp[0] = 0;\n"
            "    for (int i = 1; i <= S; i++) {\n"
            "        for (int coin : c) {\n"
            "            if (i >= coin && dp[i - coin] != INF) {\n"
            "                dp[i] = min(dp[i], dp[i - coin] + 1);\n"
            "            }\n"
            "        }\n"
            "    }\n"
            '    cout << (dp[S] == INF ? -1 : dp[S]) << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 6. BẬC T3 (Div. 3 - Rating: 1750 pts) — Xếp tầng kho hàng LIS O(N log N) (25p, 128KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_t3_lis",
        name="Xếp Tầng Kiện Hàng Kho Thông Minh (LIS O(N log N))",
        tier="T3",
        division="Div. 3",
        rating_display="T3 / Rating: 1750 pts",
        statement=(
            "Tại một trung tâm xử lý logistics tự động, robot nhận `n` kiện hàng di chuyển trên băng chuyền với trọng lượng lần lượt là `a_1, ..., a_n`.\n"
            "Robot cần chọn ra một chuỗi kiện hàng theo đúng thứ tự xuất hiện sao cho kiện hàng sau luôn có trọng lượng nghiêm ngặt lớn hơn kiện hàng trước để xếp chồng lên tháp chứa hàng.\n"
            "Hãy tìm số lượng kiện hàng tối đa mà robot có thể xếp chồng thành một tháp (độ dài dãy con tăng nghiêm ngặt dài nhất)."
        ),
        input_format="Dòng đầu chứa `n` (`1 <= n <= 2 * 10^5`). Dòng hai chứa `n` số nguyên `a_1, ..., a_n` (`-10^9 <= a_i <= 10^9`).",
        output_format="In ra chiều cao tháp kiện hàng tối đa (độ dài LIS).",
        constraints="`1 <= n <= 2 * 10^5`. Yêu cầu thuật toán `O(N log N)` (Binary Search / Fenwick Tree). Giới hạn: `1.5s`, `256MB`, `128KB`.",
        sample_input="8\n10 9 2 5 3 7 101 18",
        sample_output="4",
        secret_tests=[
            {"input": "8\n10 9 2 5 3 7 101 18", "output": "4"},
            {"input": "6\n0 1 0 3 2 3", "output": "4"},
            {"input": "7\n7 7 7 7 7 7 7", "output": "1"},
            {"input": "5\n1 2 3 4 5", "output": "5"},
        ],
        time_limit_minutes=25,
        max_code_size_kb=128,
        rating=1750,
        tags=["dp", "binary search"],
        time_limit_sec=1.5,
        memory_limit_mb=256,
        sample_explanation="Dãy con tăng dài nhất là [10, 20, 30, 40] có độ dài bằng 4 kiện hàng xếp chồng được lên nhau.",
        hint="💡 Gợi ý: Kết hợp mảng dp với Tìm kiếm nhị phân (std::lower_bound) để đạt O(N log N)!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n; if (!(cin >> n)) return 0;\n"
            "    vector<long long> tails;\n"
            "    for (int i = 0; i < n; i++) {\n"
            "        long long x; cin >> x;\n"
            "        auto it = lower_bound(tails.begin(), tails.end(), x);\n"
            "        if (it == tails.end()) tails.push_back(x);\n"
            "        else *it = x;\n"
            "    }\n"
            '    cout << tails.size() << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 7. BẬC LT2 (Div. 2 - Rating: 2000 pts) — Trạm thu phí thông minh Fenwick (30p, 256KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_lt2_segment_tree",
        name="Giám Sát Lưu Lượng Trạm Thu Phí Cao Tốc Không Dừng (Fenwick Tree)",
        tier="LT2",
        division="Div. 2",
        rating_display="LT2 / Rating: 2000 pts",
        statement=(
            "Hệ thống giám sát giao thông trên tuyến cao tốc gồm `n` trạm thu phí tự động không dừng (ETC), ban đầu tất cả các trạm đều ghi nhận `0` lượt xe.\n"
            "Trung tâm điều hành nhận được `q` sự kiện cập nhật và truy vấn liên tục theo thời gian thực:\n\n"
            "• **Loại 1 (`1 i x`):** Trạm thứ `i` ghi nhận thêm một lưu lượng xe điều chỉnh thành giá trị `x` (`a[i] = x`).\n"
            "• **Loại 2 (`2 l r`):** Trung tâm điều hành cần truy vấn tổng lưu lượng xe lưu thông trong phân đoạn từ trạm `l` đến trạm `r`, tức `a[l] + a[l+1] + ... + a[r]`.\n\n"
            "Vì `N, Q <= 2 * 10^5`, thuật toán duyệt tuần tự sẽ gây tắc nghẽn hệ thống (TLE). "
            "Bạn hãy lập trình cấu trúc dữ liệu cây Fenwick (Binary Indexed Tree) hoặc Segment Tree để xử lý mỗi thao tác trong thời gian `O(log N)`."
        ),
        input_format=(
            "• Dòng đầu tiên chứa hai số nguyên dương `n` và `q` (`1 <= n, q <= 2 * 10^5`) — lần lượt là số lượng trạm thu phí và tổng số sự kiện truy vấn.\n"
            "• `q` dòng tiếp theo, mỗi dòng mô tả một sự kiện theo một trong hai định dạng sau:\n"
            "  - `1 i x` : Trạm thứ `i` ghi nhận lưu lượng xe điều chỉnh thành giá trị `x` (`1 <= i <= n`, `0 <= x <= 10^9`).\n"
            "  - `2 l r` : Truy vấn tổng lưu lượng xe từ trạm `l` đến trạm `r` (`1 <= l <= r <= n`)."
        ),
        output_format="Với mỗi sự kiện loại 2, in ra một số nguyên duy nhất trên một dòng là tổng lưu lượng xe trong đoạn `[l, r]`.",
        constraints=(
            "• `1 <= n, q <= 2 * 10^5`\n"
            "• `1 <= i <= n`, `0 <= x <= 10^9`\n"
            "• `1 <= l <= r <= n` (Bắt buộc dùng `long long` cho tổng đoạn)\n\n"
            "**Phân bổ điểm số & Subtasks (3 Subtasks):**\n"
            "• **Subtask 1 (30% số điểm):** `n, q <= 1000` (Duyệt tuần tự mảng trâu `O(N * Q)`)\n"
            "• **Subtask 2 (30% số điểm):** `n, q <= 5 * 10^4` (Chia căn Block Decomposition `O(Q * sqrt(N))`)\n"
            "• **Subtask 3 (40% số điểm):** `n, q <= 2 * 10^5` (Cây Fenwick BIT / Segment Tree `O((N + Q) log N)`)\n\n"
            "**Giới hạn tài nguyên:** Thời gian: `2.0 giây`, Bộ nhớ: `512 MB`, Kích thước code: `256 KB`."
        ),
        sample_input="5 5\n1 1 3\n1 2 5\n2 1 2\n1 1 2\n2 1 2",
        sample_output="8\n7",
        secret_tests=[
            {"input": "5 5\n1 1 3\n1 2 5\n2 1 2\n1 1 2\n2 1 2", "output": "8\n7"},
            {"input": "3 3\n1 2 10\n2 1 3\n2 2 2", "output": "10\n10"},
        ],
        time_limit_minutes=30,
        max_code_size_kb=256,
        rating=2000,
        tags=["data structures"],
        time_limit_sec=2.0,
        memory_limit_mb=512,
        sample_explanation="Mảng ban đầu [1, 2, 3, 4, 5]. Truy vấn 2: tổng đoạn [1, 5] = 15. Truy vấn 1: trạm 3 tăng thêm 2 thành 5. Truy vấn 2: tổng đoạn [1, 5] mới = 17.",
        hint="💡 Gợi ý: Cây Fenwick (BIT) lưu trữ tổng đoạn, thao tác bitwise `i += i & -i` và `i -= i & -i`!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "using namespace std;\n\n"
            "struct Fenwick {\n"
            "    int n; vector<long long> tree;\n"
            "    Fenwick(int n): n(n), tree(n + 1, 0) {}\n"
            "    void add(int i, long long delta) {\n"
            "        for (; i <= n; i += i & -i) tree[i] += delta;\n"
            "    }\n"
            "    long long query(int i) {\n"
            "        long long sum = 0;\n"
            "        for (; i > 0; i -= i & -i) sum += tree[i];\n"
            "        return sum;\n"
            "    }\n"
            "    long long query(int l, int r) { return query(r) - query(l - 1); }\n"
            "};\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n, q; if (!(cin >> n >> q)) return 0;\n"
            "    Fenwick bit(n);\n"
            "    vector<long long> a(n + 1, 0);\n"
            "    while (q--) {\n"
            "        int type; cin >> type;\n"
            "        if (type == 1) {\n"
            "            int i; long long x; cin >> i >> x;\n"
            "            bit.add(i, x - a[i]);\n"
            "            a[i] = x;\n"
            "        } else {\n"
            "            int l, r; cin >> l >> r;\n"
            '            cout << bit.query(l, r) << "\\n";\n'
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 8. BẬC MT2 (Div. 2 - Rating: 2200 pts) — Điều phối xe cấp cứu Dijkstra (35p, 256KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_mt2_dijkstra",
        name="Tuyến Đường Xe Cấp Cứu Khẩn Cấp Ngắn Nhất (Dijkstra)",
        tier="MT2",
        division="Div. 2",
        rating_display="MT2 / Rating: 2200 pts",
        statement=(
            "Một xe cứu thương xuất phát từ bệnh viện dã chiến tại giao lộ `1` cần di chuyển khẩn cấp tới hiện trường vụ tai nạn tại giao lộ `n`.\n"
            "Bản đồ giao thông gồm `n` nút giao lộ và `m` tuyến đường một chiều, mỗi tuyến đường nối từ `u` sang `v` có thời gian di chuyển là `w` giây.\n"
            "Hãy tìm tuyến đường có tổng thời gian di chuyển ngắn nhất từ giao lộ `1` đến giao lộ `n`. Nếu không thể tiếp cận hiện trường, in ra `-1`."
        ),
        input_format=(
            "• Dòng đầu tiên chứa hai số nguyên dương `n` và `m` (`1 <= n <= 10^5`, `1 <= m <= 2 * 10^5`) — lần lượt là số lượng giao lộ và số lượng tuyến đường một chiều.\n"
            "• `m` dòng tiếp theo, mỗi dòng chứa ba số nguyên `u, v, w` (`1 <= u, v <= n`, `1 <= w <= 10^9`) — thể hiện một tuyến đường 1 chiều từ giao lộ `u` sang `v` mất `w` giây di chuyển."
        ),
        output_format="In ra một số nguyên duy nhất là thời gian di chuyển ngắn nhất từ giao lộ 1 tới giao lộ `n`, hoặc in ra `-1` nếu không thể tiếp cận hiện trường.",
        constraints=(
            "• `1 <= n <= 10^5`\n"
            "• `1 <= m <= 2 * 10^5`\n"
            "• `1 <= w <= 10^9` (Trọng số lớn, bắt buộc dùng kiểu dữ liệu `long long`)\n\n"
            "**Phân bổ điểm số & Subtasks (3 Subtasks):**\n"
            "• **Subtask 1 (30% số điểm):** `n <= 1000, m <= 2000` (Dijkstra mảng tĩnh `O(N^2)`)\n"
            "• **Subtask 2 (30% số điểm):** `n <= 10^4, m <= 5 * 10^4, w <= 10^5` (SPFA / BFS đồ thị trọng số nhỏ)\n"
            "• **Subtask 3 (40% số điểm):** `n <= 10^5, m <= 2 * 10^5, w <= 10^9` (Dijkstra Priority Queue `O(M log N)`)\n\n"
            "**Giới hạn tài nguyên:** Thời gian: `2.0 giây`, Bộ nhớ: `512 MB`, Kích thước code: `256 KB`."
        ),
        sample_input="4 5\n1 2 2\n2 4 5\n1 3 1\n3 4 3\n1 4 10",
        sample_output="4",
        secret_tests=[
            {
                "input": "4 5\n1 2 2\n2 4 5\n1 3 1\n3 4 3\n1 4 10",
                "output": "4",
            },
            {"input": "3 1\n1 2 5", "output": "-1"},
            {"input": "2 1\n1 2 100", "output": "100"},
        ],
        time_limit_minutes=35,
        max_code_size_kb=256,
        rating=2200,
        tags=["graphs", "shortest paths"],
        time_limit_sec=2.0,
        memory_limit_mb=512,
        sample_explanation="Tuyến đường đi từ bệnh viện 1 đến trung tâm cấp cứu 4 ngắn nhất là 1 -> 2 -> 4 với tổng thời gian di chuyển = 2 + 1 = 3.",
        hint="💡 Gợi ý: Sử dụng thuật toán Dijkstra kết hợp std::priority_queue<pair<long long, int>, vector<...>, greater<...>> và mảng dist khởi tạo vô cùng!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <queue>\n"
            "using namespace std;\n\n"
            "const long long INF = 1e18;\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n, m; if (!(cin >> n >> m)) return 0;\n"
            "    vector<vector<pair<int, long long>>> adj(n + 1);\n"
            "    for (int i = 0; i < m; i++) {\n"
            "        int u, v; long long w; cin >> u >> v >> w;\n"
            "        adj[u].push_back({v, w});\n"
            "    }\n"
            "    vector<long long> dist(n + 1, INF);\n"
            "    priority_queue<pair<long long, int>, vector<pair<long long, int>>, greater<pair<long long, int>>> pq;\n"
            "    dist[1] = 0; pq.push({0, 1});\n"
            "    while (!pq.empty()) {\n"
            "        auto [d, u] = pq.top(); pq.pop();\n"
            "        if (d > dist[u]) continue;\n"
            "        for (auto& [v, w] : adj[u]) {\n"
            "            if (dist[u] + w < dist[v]) {\n"
            "                dist[v] = dist[u] + w;\n"
            "                pq.push({dist[v], v});\n"
            "            }\n"
            "        }\n"
            "    }\n"
            '    cout << (dist[n] == INF ? -1 : dist[n]) << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 9. BẬC HT2 (Div. 2 - Rating: 2350 pts) — Cây mạng doanh nghiệp Tree DP (40p, 256KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_ht2_tree_dp",
        name="Tối Ưu Hóa Tuyến Đường Truyền Dữ Liệu Mạng Doanh Nghiệp (Tree DP)",
        tier="HT2",
        division="Div. 2",
        rating_display="HT2 / Rating: 2350 pts",
        statement=(
            "Hạ tầng mạng máy chủ của một tập đoàn tài chính đa quốc gia được tổ chức dưới dạng một đồ thị cây gồm `n` nút máy chủ và `n - 1` đường cáp quang kết nối.\n"
            "Mỗi máy chủ `i` có hiệu suất băng thông mang giá trị số nguyên `v_i` (có thể dương nếu là máy chủ tăng tốc, hoặc âm nếu là nút thắt cổ chai bị nghẽn mạng).\n\n"
            "Một tuyến truyền dữ liệu đơn tuyến là một chuỗi các máy chủ nối tiếp nhau qua các đường cáp quang.\n"
            "Băng thông tổng hợp của tuyến truyền bằng tổng giá trị `v_u` của tất cả các máy chủ tham gia trên tuyến.\n"
            "Hãy tìm tuyến truyền dữ liệu đơn có tổng băng thông lớn nhất trong hệ thống mạng cây đã cho."
        ),
        input_format=(
            "• Dòng đầu tiên chứa số nguyên dương `n` (`1 <= n <= 2 * 10^5`) — tổng số lượng nút máy chủ.\n"
            "• Dòng thứ hai chứa `n` số nguyên `v_1, v_2, ..., v_n` (`-10^9 <= v_i <= 10^9`) — hiệu suất băng thông của từng máy chủ.\n"
            "• `n - 1` dòng tiếp theo, mỗi dòng chứa hai số nguyên `u` và `v` (`1 <= u, v <= n`, `u != v`) — biểu diễn tuyến cáp quang nối giữa hai máy chủ `u` và `v`."
        ),
        output_format="In ra một số nguyên duy nhất là tổng băng thông lớn nhất của một tuyến truyền dữ liệu đơn trên cây.",
        constraints=(
            "• `1 <= n <= 2 * 10^5`\n"
            "• `-10^9 <= v_i <= 10^9` (Lưu ý dùng kiểu `long long` để tránh tràn số khi cộng dồn)\n"
            "• Đồ thị luôn đảm bảo là một cây liên thông gồm `n` đỉnh và `n - 1` cạnh.\n\n"
            "**Phân bổ điểm số & Subtasks (3 Subtasks):**\n"
            "• **Subtask 1 (30% số điểm):** `1 <= n <= 1000` (DFS từ mọi đỉnh `O(N^2)`)\n"
            "• **Subtask 2 (30% số điểm):** Cây suy biến thành đường thẳng `n <= 10^5` (Thuật toán Kadane `O(N)`)\n"
            "• **Subtask 3 (40% số điểm):** Cây liên thông tổng quát `n <= 2 * 10^5` (Quy hoạch động Tree DP `O(N)`)\n\n"
            "**Giới hạn tài nguyên:** Thời gian: `2.0 giây`, Bộ nhớ: `512 MB`, Kích thước code: `256 KB`."
        ),
        sample_input="5\n-10 2 3 -20 4\n1 2\n1 3\n2 4\n2 5",
        sample_output="6",
        secret_tests=[
            {"input": "5\n-10 2 3 -20 4\n1 2\n1 3\n2 4\n2 5", "output": "6"},
            {"input": "3\n-1 -2 -3\n1 2\n2 3", "output": "-1"},
        ],
        time_limit_minutes=40,
        max_code_size_kb=256,
        rating=2350,
        tags=["dp", "trees"],
        time_limit_sec=2.0,
        memory_limit_mb=512,
        sample_explanation="Tuyến đường đi liên thông đơn có tổng trọng số lớn nhất đi qua các nút 1 -> 2 -> 4 với tổng lưu lượng = 10 + 20 + 15 = 45.",
        hint="💡 Gợi ý: Sử dụng DFS trên cây, với mỗi đỉnh u tính max đường đi dài nhất trong các cây con của nó, kết hợp 2 nhánh con lớn nhất qua u!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "int n;\n"
            "vector<long long> val;\n"
            "vector<vector<int>> adj;\n"
            "long long ans = -1e18;\n\n"
            "long long dfs(int u, int p) {\n"
            "    long long max1 = 0, max2 = 0;\n"
            "    for (int v : adj[u]) {\n"
            "        if (v == p) continue;\n"
            "        long long res = dfs(v, u);\n"
            "        if (res > max1) { max2 = max1; max1 = res; }\n"
            "        else if (res > max2) { max2 = res; }\n"
            "    }\n"
            "    ans = max(ans, val[u] + max1 + max2);\n"
            "    return max(0LL, val[u] + max1);\n"
            "}\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    if (!(cin >> n)) return 0;\n"
            "    val.resize(n + 1); adj.resize(n + 1);\n"
            "    for (int i = 1; i <= n; i++) cin >> val[i];\n"
            "    for (int i = 0; i < n - 1; i++) {\n"
            "        int u, v; cin >> u >> v;\n"
            "        adj[u].push_back(v); adj[v].push_back(u);\n"
            "    }\n"
            "    dfs(1, 0);\n"
            '    cout << ans << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 10. BẬC LT1 (Div. 1 - Rating: 2500 pts) — Phân phối năng lượng lưới điện Dinic (45p, 512KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_lt1_max_flow_dinic",
        name="Phân Phối Năng Lượng Lưới Điện Quốc Gia Tối Đa (Dinic Max Flow)",
        tier="LT1",
        division="Div. 1",
        rating_display="LT1 / Rating: 2500 pts",
        statement=(
            "Tập đoàn điện lực quốc gia đang vận hành mạng lưới điều phối năng lượng thông minh (Smart Grid) gồm `n` trạm biến áp và trung tâm phân phối, được đánh số từ `1` đến `n`.\n\n"
            "Nhà máy điện hạt nhân nguồn đặt tại trạm biến áp số `1` (`s = 1`), và khu phức hợp công nghiệp tiêu thụ trọng điểm đặt tại trạm biến áp số `n` (`t = n`). Mạng lưới gồm `m` đường dây cao thế một chiều kết nối giữa các trạm. Mỗi đường dây cao thế nối từ trạm `u` sang trạm `v` có một ngưỡng công suất tải tối đa là `c(u, v)` Megawatt (MW).\n\n"
            "Để đáp ứng nhu cầu sản xuất gia tăng đột biến, ban quản lý năng lượng cần tìm phương án điều phối dòng điện từ nhà máy nguồn `1` đến đích tiêu thụ `n` sao cho tổng công suất truyền tải đạt giá trị cực đại (Maximum Flow), đồng thời đảm bảo trên mỗi đường dây `(u, v)`, lượng điện năng truyền qua không vượt quá công suất định mức `c(u, v)` và tại mọi trạm trung gian (từ `2` đến `n - 1`), tổng lượng điện đi vào trạm luôn bằng tổng lượng điện đi ra khỏi trạm.\n\n"
            "Bạn hãy lập trình thuật toán luồng cực đại (Dinic) để tính toán công suất truyền tải điện năng cực đại của toàn hệ thống."
        ),
        input_format=(
            "• Dòng đầu tiên chứa hai số nguyên dương `n` và `m` (`2 <= n <= 1000`, `1 <= m <= 10000`) — lần lượt là số lượng trạm biến áp và số lượng đường dây cao thế.\n"
            "• `m` dòng tiếp theo, mỗi dòng chứa ba số nguyên `u, v, c` (`1 <= u, v <= n`, `u != v`, `1 <= c <= 10^9`) — thể hiện một đường dây truyền tải điện 1 chiều từ trạm `u` sang trạm `v` với công suất truyền tải tối đa là `c` MW."
        ),
        output_format="In ra một số nguyên duy nhất là tổng công suất truyền tải điện năng cực đại (Maximum Flow) có thể điều phối từ nhà máy nguồn `1` tới trung tâm tiêu thụ `n`.",
        constraints=(
            "• `2 <= n <= 1000`\n"
            "• `1 <= m <= 10000`\n"
            "• `1 <= c <= 10^9` (Công suất lớn, lưu ý dùng kiểu số nguyên 64-bit `long long` tránh tràn số)\n\n"
            "**Phân bổ điểm số & Subtasks (3 Subtasks):**\n"
            "• **Subtask 1 (25% số điểm):** `n <= 50, m <= 200, c <= 100` (Ford-Fulkerson BFS cơ bản)\n"
            "• **Subtask 2 (35% số điểm):** `n <= 500, m <= 2000, c <= 10^6` (Edmonds-Karp `O(V * E^2)`)\n"
            "• **Subtask 3 (40% số điểm):** `n <= 1000, m <= 10000, c <= 10^9` (Dinic Maximum Flow `O(V^2 * E)`)\n\n"
            "**Giới hạn tài nguyên:** Thời gian: `2.0 giây`, Bộ nhớ: `512 MB`, Kích thước code: `512 KB`."
        ),
        sample_input="4 5\n1 2 3\n2 4 2\n1 3 2\n3 4 3\n2 3 1",
        sample_output="5",
        secret_tests=[
            {"input": "4 5\n1 2 3\n2 4 2\n1 3 2\n3 4 3\n2 3 1", "output": "5"},
            {"input": "3 2\n1 2 10\n2 3 5", "output": "5"},
            {"input": "2 1\n1 2 1000000000", "output": "1000000000"},
        ],
        time_limit_minutes=45,
        max_code_size_kb=512,
        rating=2500,
        tags=["flows", "graph matchings"],
        time_limit_sec=2.0,
        memory_limit_mb=512,
        sample_explanation="Luồng điện cực đại truyền từ nhà máy phát điện 1 đến trạm tiêu thụ trung tâm 4 là 5 đơn vị công suất.",
        hint="💡 Gợi ý: Sử dụng BFS xây dựng đồ thị phân tầng level[], sau đó dùng DFS tìm Blocking Flow với mảng ptr[]!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <queue>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "struct Edge {\n"
            "    int to; long long cap, flow; int rev;\n"
            "};\n\n"
            "struct Dinic {\n"
            "    int n, s, t;\n"
            "    vector<vector<Edge>> adj;\n"
            "    vector<int> level, ptr;\n"
            "    Dinic(int n, int s, int t): n(n), s(s), t(t), adj(n + 1), level(n + 1), ptr(n + 1) {}\n"
            "    void add_edge(int from, int to, long long cap) {\n"
            "        adj[from].push_back({to, cap, 0, (int)adj[to].size()});\n"
            "        adj[to].push_back({from, 0, 0, (int)adj[from].size() - 1});\n"
            "    }\n"
            "    bool bfs() {\n"
            "        fill(level.begin(), level.end(), -1);\n"
            "        level[s] = 0;\n"
            "        queue<int> q;\n"
            "        q.push(s);\n"
            "        while (!q.empty()) {\n"
            "            int v = q.front(); q.pop();\n"
            "            for (auto& edge : adj[v]) {\n"
            "                if (edge.cap - edge.flow > 0 && level[edge.to] == -1) {\n"
            "                    level[edge.to] = level[v] + 1;\n"
            "                    q.push(edge.to);\n"
            "                }\n"
            "            }\n"
            "        }\n"
            "        return level[t] != -1;\n"
            "    }\n"
            "    long long dfs(int v, long long pushed) {\n"
            "        if (pushed == 0 || v == t) return pushed;\n"
            "        for (int& cid = ptr[v]; cid < adj[v].size(); ++cid) {\n"
            "            auto& edge = adj[v][cid];\n"
            "            int tr = edge.to;\n"
            "            if (level[v] + 1 != level[tr] || edge.cap - edge.flow == 0) continue;\n"
            "            long long tr_pushed = dfs(tr, min(pushed, edge.cap - edge.flow));\n"
            "            if (tr_pushed == 0) continue;\n"
            "            edge.flow += tr_pushed;\n"
            "            adj[tr][edge.rev].flow -= tr_pushed;\n"
            "            return tr_pushed;\n"
            "        }\n"
            "        return 0;\n"
            "    }\n"
            "    long long max_flow() {\n"
            "        long long flow = 0;\n"
            "        while (bfs()) {\n"
            "            fill(ptr.begin(), ptr.end(), 0);\n"
            "            while (long long pushed = dfs(s, 1e18)) flow += pushed;\n"
            "        }\n"
            "        return flow;\n"
            "    }\n"
            "};\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n, m; if (!(cin >> n >> m)) return 0;\n"
            "    Dinic dinic(n, 1, n);\n"
            "    for (int i = 0; i < m; i++) {\n"
            "        int u, v; long long c; cin >> u >> v >> c;\n"
            "        dinic.add_edge(u, v, c);\n"
            "    }\n"
            '    cout << dinic.max_flow() << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 11. BẬC MT1 (Div. 1 - Rating: 2800 pts) — Đặt Data Center CDN Centroid (50p, 512KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_mt1_centroid_decomp",
        name="Định Vị Trạm Máy Chủ Đám Mây CDN Tối Ưu (Centroid Decomposition)",
        tier="MT1",
        division="Div. 1",
        rating_display="MT1 / Rating: 2800 pts",
        statement=(
            "Mạng lưới phân phối nội dung đa phương tiện toàn cầu (Content Delivery Network - CDN) triển khai hạ tầng gồm `n` cụm máy chủ trung tâm dữ liệu được đánh số từ `1` đến `n`.\n\n"
            "Các máy chủ này được liên kết với nhau thông qua `n - 1` tuyến cáp quang tốc độ cao tạo thành một cấu trúc đồ thị cây (Tree) không có chu trình. Mỗi tuyến cáp quang kết nối trực tiếp giữa hai máy chủ có độ trễ truyền dữ liệu chuẩn hóa đúng bằng `1` bước nhảy (hop). Độ trễ liên lạc giữa hai máy chủ bất kỳ `(u, v)` được định nghĩa là độ dài đường đi đơn ngắn nhất (số lượng cáp quang) nối giữa `u` và `v` trên cây, ký hiệu là `dist(u, v)`.\n\n"
            "Để tối ưu hóa chất lượng dịch vụ (QoS) và tránh tình trạng nghẽn cổ chai mạng, bộ điều phối trung tâm cần thống kê chất lượng liên lạc của toàn bộ hạ tầng. Cụ thể, hệ thống yêu cầu đếm tổng số lượng cặp máy chủ không có thứ tự `(u, v)` (`1 <= u < v <= n`) sao cho độ trễ truyền dữ liệu giữa chúng không vượt quá ngưỡng trần an toàn `k` bước nhảy, tức thỏa mãn điều kiện `dist(u, v) <= k`.\n\n"
            "Do quy mô hệ thống rất lớn với `n <= 10^5`, thuật toán duyệt thông thường `O(n^2)` sẽ gây quá tải thời gian. Hãy thiết kế thuật toán tối ưu (sử dụng phương pháp Phân Rã Trọng Tâm - Centroid Decomposition trên cây) để xử lý bài toán hiệu quả."
        ),
        input_format=(
            "• Dòng đầu tiên chứa hai số nguyên dương `n` và `k` (`1 <= n <= 10^5`, `1 <= k <= n`) — lần lượt là tổng số cụm máy chủ trung tâm dữ liệu CDN và ngưỡng trần độ trễ cho phép.\n"
            "• `n - 1` dòng tiếp theo, mỗi dòng chứa hai số nguyên `u` và `v` (`1 <= u, v <= n`, `u != v`) — biểu diễn tuyến cáp quang tốc độ cao 2 chiều nối trực tiếp giữa máy chủ `u` và máy chủ `v`."
        ),
        output_format="In ra một số nguyên duy nhất là tổng số lượng cặp máy chủ `(u, v)` (`1 <= u < v <= n`) có độ trễ truyền dữ liệu `dist(u, v) <= k`.",
        constraints=(
            "• `1 <= n <= 10^5`\n"
            "• `1 <= k <= n`\n"
            "• Đồ thị luôn đảm bảo là một cây liên thông gồm `n` đỉnh và `n - 1` cạnh.\n\n"
            "**Phân bổ điểm số & Subtasks (3 Subtasks):**\n"
            "• **Subtask 1 (25% số điểm):** `1 <= n <= 2000` (DFS/BFS mọi cặp đỉnh `O(N^2)`)\n"
            "• **Subtask 2 (35% số điểm):** Cây dạng đường thẳng `1 <= n <= 10^5` (Two Pointers / Sliding Window `O(N)`)\n"
            "• **Subtask 3 (40% số điểm):** Cây bất kỳ `1 <= n <= 10^5` (Phân rã trọng tâm Centroid Decomposition `O(N log^2 N)`)\n\n"
            "**Giới hạn tài nguyên:** Thời gian: `2.0 giây`, Bộ nhớ: `512 MB`, Kích thước code: `512 KB`."
        ),
        sample_input="5 2\n1 2\n2 3\n3 4\n4 5",
        sample_output="7",
        secret_tests=[
            {"input": "5 2\n1 2\n2 3\n3 4\n4 5", "output": "7"},
            {"input": "4 1\n1 2\n1 3\n1 4", "output": "3"},
            {"input": "3 3\n1 2\n2 3", "output": "3"},
        ],
        time_limit_minutes=50,
        max_code_size_kb=512,
        rating=2800,
        tags=["trees", "divide and conquer", "data structures"],
        time_limit_sec=2.0,
        memory_limit_mb=512,
        sample_explanation="Các cặp đỉnh có khoảng cách đường đi <= 2 là: (1,2), (1,3), (1,4), (1,5), (2,3), (2,4), (2,5), (3,4), (3,5). Tổng cộng có 9 cặp nút thỏa mãn điều kiện độ trễ.",
        hint="💡 Gợi ý: Tìm trọng tâm centroid của cây, gom độ sâu từ các nhánh con và dùng Two Pointers hoặc BIT để đếm cặp dist <= k rồi chia để trị đệ quy!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "#include <algorithm>\n"
            "using namespace std;\n\n"
            "int n, k;\n"
            "vector<vector<int>> adj;\n"
            "vector<int> sz;\n"
            "vector<bool> removed;\n"
            "long long total_pairs = 0;\n\n"
            "void get_sizes(int u, int p) {\n"
            "    sz[u] = 1;\n"
            "    for (int v : adj[u]) if (v != p && !removed[v]) {\n"
            "        get_sizes(v, u); sz[u] += sz[v];\n"
            "    }\n"
            "}\n\n"
            "int get_centroid(int u, int p, int total) {\n"
            "    for (int v : adj[u]) if (v != p && !removed[v] && sz[v] > total / 2)\n"
            "        return get_centroid(v, u, total);\n"
            "    return u;\n"
            "}\n\n"
            "void get_depths(int u, int p, int d, vector<int>& depths) {\n"
            "    if (d > k) return;\n"
            "    depths.push_back(d);\n"
            "    for (int v : adj[u]) if (v != p && !removed[v]) get_depths(v, u, d + 1, depths);\n"
            "}\n\n"
            "long long count_pairs(vector<int>& depths) {\n"
            "    sort(depths.begin(), depths.end());\n"
            "    long long cnt = 0;\n"
            "    int l = 0, r = (int)depths.size() - 1;\n"
            "    while (l < r) {\n"
            "        if (depths[l] + depths[r] <= k) { cnt += r - l; l++; }\n"
            "        else r--;\n"
            "    }\n"
            "    return cnt;\n"
            "}\n\n"
            "void decompose(int u) {\n"
            "    get_sizes(u, 0);\n"
            "    int c = get_centroid(u, 0, sz[u]);\n"
            "    removed[c] = true;\n"
            "    vector<int> all_depths = {0};\n"
            "    for (int v : adj[c]) if (!removed[v]) {\n"
            "        vector<int> sub_depths;\n"
            "        get_depths(v, c, 1, sub_depths);\n"
            "        total_pairs -= count_pairs(sub_depths);\n"
            "        all_depths.insert(all_depths.end(), sub_depths.begin(), sub_depths.end());\n"
            "    }\n"
            "    total_pairs += count_pairs(all_depths);\n"
            "    for (int v : adj[c]) if (!removed[v]) decompose(v);\n"
            "}\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    if (!(cin >> n >> k)) return 0;\n"
            "    adj.resize(n + 1); sz.resize(n + 1); removed.resize(n + 1, false);\n"
            "    for (int i = 0; i < n - 1; i++) {\n"
            "        int u, v; cin >> u >> v;\n"
            "        adj[u].push_back(v); adj[v].push_back(u);\n"
            "    }\n"
            "    decompose(1);\n"
            '    cout << total_pairs << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
    # --------------------------------------------------------------------------
    # 12. BẬC HT1 (Div. 1 - Rating: 3000+ pts) — Tài chính tốc độ cao HFT Matrix Expo (60p, 512KB)
    # --------------------------------------------------------------------------
    DuelProblem(
        id="duel_ht1_matrix_expo",
        name="Dự Báo Thị Trường Tài Chính Sau K Bước Giao Dịch Tần Số Cao (Matrix Exponentiation)",
        tier="HT1",
        division="Div. 1",
        rating_display="HT1 / Rating: 3000 pts",
        statement=(
            "Thị trường tài chính phái sinh và tiền tệ tốc độ cao (High-Frequency Trading - HFT) vận hành một mạng lưới định tuyến thanh khoản liên ngân hàng gồm `n` nút giao dịch trọng yếu, được đánh số từ `1` đến `n`.\n\n"
            "Tại mỗi micro-giây, các thuật toán giao dịch tự động liên tục luân chuyển dòng vốn và lệnh khớp qua các kênh truyền trực tiếp. Cấu trúc liên thông giữa các nút được biểu diễn thông qua ma trận kề `A` kích thước `n x n`, trong đó `A[i][j] = 1` thể hiện có một kênh định tuyến thông suốt 1 chiều cho phép truyền lệnh từ nút thanh khoản `i` sang nút thanh khoản `j`, ngược lại `A[i][j] = 0` nếu không tồn tại đường truyền khả dụng giữa hai nút.\n\n"
            "Một kịch bản thực thi lệnh hợp lệ có độ dài đúng bằng `k` chu kỳ chuyển dịch được định nghĩa là một dãy gồm `k + 1` nút `(u_0, u_1, u_2, ..., u_k)` sao cho tại mọi thời điểm `t` (`0 <= t < k`), bước chuyển từ `u_t` sang `u_{t+1}` phải là một kênh truyền hợp lệ trong hệ thống, tức `A[u_t][u_{t+1}] = 1`.\n\n"
            "Một tổ chức tài chính lớn cần thực hiện chuỗi lệnh mua bán bắt đầu từ tài khoản nguồn tại nút thanh khoản `1` (`u_0 = 1`) và phải kết thúc chính xác tại sàn giao dịch trung tâm tại nút `n` (`u_k = n`) sau đúng `k` chu kỳ micro-giây chuyển dịch.\n\n"
            "Nhiệm vụ của bạn là hãy tính toán tổng số lượng kịch bản khớp lệnh hợp lệ khác nhau thỏa mãn toàn bộ các điều kiện trên. Do hệ thống vận hành trong khoảng thời gian siêu dài với `k` có thể lên tới `10^18`, kết quả có thể cực kỳ lớn, vì vậy hãy in ra số lượng kịch bản sau khi lấy số dư cho `10^9 + 7`."
        ),
        input_format=(
            "• Dòng đầu tiên chứa hai số nguyên dương `n` và `k` (`1 <= n <= 100`, `1 <= k <= 10^18`) — lần lượt biểu thị số lượng nút giao dịch thanh khoản trong mạng lưới và tổng số chu kỳ micro-giây của chuỗi khớp lệnh.\n"
            "• `n` dòng tiếp theo, mỗi dòng chứa `n` số nguyên `A[i][j]` thuộc `{0, 1}` được phân tách bởi dấu cách — biểu diễn ma trận kề chuyển dịch thanh khoản `A` kích thước `n x n` (`A[i][j] = 1` nếu có kênh truyền trực tiếp 1 chiều từ nút `i` sang nút `j`, ngược lại `A[i][j] = 0`)."
        ),
        output_format=(
            "In ra một số nguyên duy nhất trên một dòng là tổng số lượng kịch bản khớp lệnh hợp lệ xuất phát từ tài khoản thanh khoản 1 (`u_0 = 1`) và kết thúc chính xác tại sàn trung tâm `n` (`u_k = n`) sau đúng `k` chu kỳ chuyển dịch, lấy phần dư theo modulo `10^9 + 7`."
        ),
        constraints=(
            "• `1 <= n <= 100`\n"
            "• `1 <= k <= 10^18` (Chu kỳ thời gian cực lớn, bắt buộc sử dụng kiểu dữ liệu số nguyên 64-bit `long long`)\n"
            "• `A[i][j]` thuộc `{0, 1}` với mọi `1 <= i, j <= n`\n\n"
            "**Phân bổ điểm số & Subtasks:**\n"
            "• **Subtask 1 (25% số điểm):** `1 <= n <= 10`, `1 <= k <= 20` (Duyệt quay lui / BFS đếm đường đi)\n"
            "• **Subtask 2 (35% số điểm):** `1 <= n <= 50`, `1 <= k <= 10^5` (Quy hoạch động ma trận `O(K * N^2)`)\n"
            "• **Subtask 3 (40% số điểm):** `1 <= n <= 100`, `1 <= k <= 10^18` (Lũy thừa ma trận nhị phân `O(N^3 log K)`)\n\n"
            "**Giới hạn tài nguyên:** Thời gian: `2.0 giây`, Bộ nhớ: `512 MB`, Kích thước code: `512 KB`."
        ),
        sample_input="3 3\n0 1 0\n0 0 1\n1 0 0",
        sample_output="0",
        secret_tests=[
            {"input": "3 3\n0 1 0\n0 0 1\n1 0 0", "output": "0"},
            {"input": "3 4\n0 1 0\n0 0 1\n1 0 0", "output": "1"},
        ],
        time_limit_minutes=60,
        max_code_size_kb=512,
        rating=3000,
        tags=["matrices", "dp", "math"],
        time_limit_sec=2.0,
        memory_limit_mb=512,
        sample_explanation="Sau k = 3 bước di chuyển từ nút 1 theo ma trận kề vòng tròn 1 -> 2 -> 3 -> 1, đường đi kết thúc tại nút 1 chứ không phải nút n = 3, do đó số kịch bản kết thúc tại nút 3 sau 3 bước là 0.",
        hint="💡 Gợi ý: Số lượng đường đi độ dài k giữa mọi cặp đỉnh chính là phần tử tương ứng của ma trận lũy thừa A^k!",
        solution_code=(
            "#include <iostream>\n"
            "#include <vector>\n"
            "using namespace std;\n\n"
            "const int MOD = 1e9 + 7;\n"
            "typedef vector<vector<long long>> Matrix;\n\n"
            "Matrix mul(const Matrix& A, const Matrix& B, int n) {\n"
            "    Matrix C(n, vector<long long>(n, 0));\n"
            "    for (int i = 0; i < n; i++)\n"
            "        for (int k = 0; k < n; k++)\n"
            "            for (int j = 0; j < n; j++)\n"
            "                C[i][j] = (C[i][j] + A[i][k] * B[k][j]) % MOD;\n"
            "    return C;\n"
            "}\n\n"
            "Matrix power(Matrix A, long long p, int n) {\n"
            "    Matrix res(n, vector<long long>(n, 0));\n"
            "    for (int i = 0; i < n; i++) res[i][i] = 1;\n"
            "    while (p > 0) {\n"
            "        if (p & 1) res = mul(res, A, n);\n"
            "        A = mul(A, A, n);\n"
            "        p >>= 1;\n"
            "    }\n"
            "    return res;\n"
            "}\n\n"
            "int main() {\n"
            "    ios_base::sync_with_stdio(false); cin.tie(NULL);\n"
            "    int n; long long k;\n"
            "    if (!(cin >> n >> k)) return 0;\n"
            "    Matrix A(n, vector<long long>(n));\n"
            "    for (int i = 0; i < n; i++)\n"
            "        for (int j = 0; j < n; j++) cin >> A[i][j];\n"
            "    Matrix Res = power(A, k, n);\n"
            '    cout << Res[0][n - 1] << "\\n";\n'
            "    return 0;\n"
            "}"
        ),
    ),
]

import json
import os

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AI_PROBLEMS_FILE = os.path.join(PROJECT_DIR, "data", "ai_problems.json")

TIER_DEFAULT_RATINGS: dict[str, int] = {
    "T8": 300,
    "T7": 550,
    "T6": 850,
    "T5": 1300,
    "T4": 1500,
    "T3": 1750,
    "LT2": 2000,
    "MT2": 2200,
    "HT2": 2350,
    "LT1": 2500,
    "MT1": 2800,
    "HT1": 3000,
}


def _load_cached_ai_problems() -> int:
    """Tự động nạp toàn bộ kho đề phong phú từ data/ai_problems.json vào PROBLEM_BANK sau khi kiểm duyệt."""
    if not os.path.isfile(AI_PROBLEMS_FILE):
        return 0
    try:
        from services.ai_problem_upgrader import audit_problem
        with open(AI_PROBLEMS_FILE, "r", encoding="utf-8") as f:
            items = json.load(f)
        existing_ids = {p.id: i for i, p in enumerate(PROBLEM_BANK)}
        loaded = 0
        for item in items:
            p_id = item.get("id")
            if not p_id:
                continue
            is_valid, _ = audit_problem(item)
            if not is_valid:
                continue

            tier_val = item.get("tier", "T8")
            raw_rating = item.get("rating")
            calc_rating = int(raw_rating) if (raw_rating is not None and int(raw_rating) > 0) else TIER_DEFAULT_RATINGS.get(tier_val, 800)

            prob = DuelProblem(
                id=p_id,
                name=item.get("name", "Algorithmic Challenge"),
                tier=tier_val,
                division=item.get("division", "Div. 4"),
                rating_display=item.get("rating_display", f"{tier_val} / Rating: {calc_rating} pts"),
                statement=item.get("statement", ""),
                input_format=item.get("input_format", ""),
                output_format=item.get("output_format", ""),
                constraints=item.get("constraints", ""),
                sample_input=item.get("sample_input", ""),
                sample_output=item.get("sample_output", ""),
                secret_tests=item.get("secret_tests", []),
                time_limit_minutes=item.get("time_limit_minutes", 15),
                max_code_size_kb=item.get("max_code_size_kb", 64),
                solution_code=item.get("solution_code", ""),
                solution_cpp=item.get("solution_cpp", ""),
                solution_py=item.get("solution_py", ""),
                tags=item.get("tags", []),
                rating=calc_rating,
            )
            if p_id in existing_ids:
                PROBLEM_BANK[existing_ids[p_id]] = prob
            else:
                PROBLEM_BANK.append(prob)
                existing_ids[p_id] = len(PROBLEM_BANK) - 1
                loaded += 1
        return loaded
    except Exception:
        return 0


_load_cached_ai_problems()


def get_problem_for_match(
    p1_tier: str,
    p2_tier: str,
    exclude_ids: set[str] | None = None,
    round_index: int = 1,
) -> DuelProblem:
    """
    Lựa chọn đề bài chuẩn xác theo từng bậc Tier và cơ chế leo thang độ khó:
    - Cơ chế leo thang (Escalation): Chặng càng dài bài càng khó (~1-2%, chọn 1.5% mỗi chặng tiếp theo).
      difficulty_bonus_pct = round((max(1, round_index) - 1) * 1.5, 1)
      difficulty_factor = 1.0 + (max(1, round_index) - 1) * 0.015
    - Khi round_index >= 3: Mở rộng ngưỡng trần +1 Tier để tạo bước ngoặt đột phá cho các chặng giằng co.
    - Mỗi đề chỉ được dùng TỐI ĐA 3 LẦN trong toàn bộ hệ thống Ranked.
    - Trong cùng 1 trận đấu giữa 2 người: Đề đã xuất hiện sẽ KHÔNG BAO GIỜ lặp lại ở các chặng sau.
    - Đối với Tier cao (LT2 - HT1): Tuyệt đối KHÔNG fallback về đề cấp thấp (T8 - T5).
    - Nếu kho đề hết bài: Tự động khởi tạo ngay đề mới chuẩn xác qua Problem Factory hoặc kho Olympic.
    """
    exclude_ids = exclude_ids or set()
    idx1 = get_rank_index(p1_tier)
    idx2 = get_rank_index(p2_tier)
    min_idx = min(idx1, idx2)
    max_idx = max(idx1, idx2)

    # Escalation: Từ chặng 3 trở đi, đẩy ngưỡng cận trên lên +1 Tier (nếu chưa max)
    if round_index >= 3 and max_idx < len(RANK_ORDER) - 1:
        max_idx += 1

    target_tiers = [RANK_ORDER[i] for i in range(min_idx, max_idx + 1)]

    # 1. Ưu tiên 1: Bài thuộc đúng target_tiers, chưa xuất hiện trong trận này VÀ used_count < 3
    candidates = [
        p for p in PROBLEM_BANK
        if p.tier in target_tiers and p.id not in exclude_ids and getattr(p, "used_count", 0) < 3
    ]

    # 2. Ưu tiên 2: Bài thuộc đúng target_tiers, chưa xuất hiện trong trận này (cho phép tái sử dụng bài cùng tier)
    if not candidates:
        candidates = [
            p for p in PROBLEM_BANK
            if p.tier in target_tiers and p.id not in exclude_ids
        ]

    # 3. Ưu tiên 3: Khởi tạo đề bài mới tinh chuẩn xác theo target_tiers từ Problem Factory
    if not candidates:
        try:
            from services.problem_factory import generate_synthesized_problem
            chosen_tier = random.choice(target_tiers)
            new_prob = generate_synthesized_problem(tier=chosen_tier)
            if new_prob and new_prob.tier in target_tiers:
                PROBLEM_BANK.append(new_prob)
                candidates = [new_prob]
        except Exception:
            candidates = []

    # 4. Ưu tiên 4: Mở rộng hợp lý theo phân cấp nếu kho đề cạn kiệt hoàn toàn
    if not candidates:
        if min_idx >= 6:  # Tier cao (LT2, MT2, HT2, LT1, MT1, HT1)
            high_tiers = [RANK_ORDER[i] for i in range(6, len(RANK_ORDER))]
            candidates = [
                p for p in PROBLEM_BANK
                if p.tier in high_tiers and p.id not in exclude_ids
            ]
        else:
            exp_min = max(0, min_idx - 1)
            exp_max = min(len(RANK_ORDER) - 1, max_idx + 1)
            exp_tiers = [RANK_ORDER[i] for i in range(exp_min, exp_max + 1)]
            candidates = [
                p for p in PROBLEM_BANK
                if p.tier in exp_tiers and p.id not in exclude_ids
            ]

    if not candidates:
        candidates = [p for p in PROBLEM_BANK if p.id not in exclude_ids] or PROBLEM_BANK

    # Lựa chọn bài toán theo độ khó leo thang
    difficulty_bonus_pct = round((max(1, round_index) - 1) * 1.5, 1)
    if len(candidates) > 1 and round_index > 1:
        candidates.sort(key=lambda p: getattr(p, "rating", 1000))
        pick_idx = min(len(candidates) - 1, int(len(candidates) * min(1.0, 0.4 + 0.15 * (round_index - 1))))
        selected = candidates[pick_idx]
    else:
        selected = random.choice(candidates)

    selected.round_index = round_index
    selected.difficulty_bonus_pct = difficulty_bonus_pct
    selected.used_count = getattr(selected, "used_count", 0) + 1
    return selected


def get_div1_problem() -> DuelProblem:
    """Trả về ngẫu nhiên một đề bài thuộc Division 1 (LT1, MT1, HT1 - 2400 đến 3000+ pts)."""
    div1_problems = [
        p
        for p in PROBLEM_BANK
        if p.division == "Div. 1" or p.tier in ("LT1", "MT1", "HT1")
    ]
    if div1_problems:
        return random.choice(div1_problems)
    return PROBLEM_BANK[-1]


def get_problem_by_tier(tier: str, exclude_ids: set[str] | None = None, round_index: int = 1) -> DuelProblem:
    """Trả về ngẫu nhiên một bài toán thuộc chính xác Bậc Tier được chọn (HT1 đến T8)."""
    exclude = exclude_ids or set()
    tier_upper = tier.upper()
    candidates = [
        p for p in PROBLEM_BANK
        if p.tier.upper() == tier_upper and p.id not in exclude
    ]
    if not candidates:
        candidates = [p for p in PROBLEM_BANK if p.tier.upper() == tier_upper]
    if not candidates:
        # Dự phòng bằng get_problem_for_match nếu chưa có bài đúng tier
        return get_problem_for_match(tier_upper, tier_upper, exclude_ids=exclude, round_index=round_index)

    difficulty_bonus_pct = round((max(1, round_index) - 1) * 1.5, 1)
    if len(candidates) > 1 and round_index > 1:
        candidates.sort(key=lambda p: getattr(p, "rating", 1000))
        pick_idx = min(len(candidates) - 1, int(len(candidates) * min(1.0, 0.4 + 0.15 * (round_index - 1))))
        selected = candidates[pick_idx]
    else:
        selected = random.choice(candidates)

    selected.round_index = round_index
    selected.difficulty_bonus_pct = difficulty_bonus_pct
    selected.used_count = getattr(selected, "used_count", 0) + 1
    return selected


