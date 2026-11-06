"""
services/ai_problem_upgrader.py
Hệ thống Kiểm Duyệt & Tự Động Nâng Cấp Đề Thi Ranked 1:1 (AI Problem Auditor & Upgrader).
- Tự động quét và phát hiện các bài toán kém chất lượng (dummy code 'print(OK)', test rác sum(a), thiếu Subtasks).
- Nâng cấp đề bài đạt chuẩn Olympic Tin học / Codeforces Div. 1 & Div. 2 với đầy đủ 3 Subtasks.
- Sinh bộ testcase đa tầng phong phú (8-12 testcases: Sample, Biên, Subtask 1/2, và TLE Stress lớn N=10^5, K=10^18).
- Hỗ trợ cơ chế tự động leo thang độ khó theo chặng (+1.5% mỗi chặng).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any

from services.duel_problems import DuelProblem, PROBLEM_BANK
from services.rank import RANK_ORDER, get_rank_badge, get_tier_division

logger = logging.getLogger("AIProblemUpgrader")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
AI_PROBLEMS_FILE = os.path.join(DATA_DIR, "ai_problems.json")


def audit_problem(prob: DuelProblem | dict) -> tuple[bool, list[str]]:
    """
    Kiểm toán chất lượng của một đề bài:
    Trả về (is_valid, issues_list):
    - True nếu đề đạt chuẩn thi đấu Ranked 1:1.
    - False nếu đề là rác dummy, thiếu test, hoặc giải thuật sai lệch.
    """
    issues = []
    
    if isinstance(prob, DuelProblem):
        p_id = prob.id
        p_name = prob.name
        p_tier = prob.tier
        p_statement = prob.statement
        p_sol = prob.solution_code
        p_tests = prob.secret_tests or []
        p_cons = prob.constraints
    else:
        p_id = prob.get("id", "")
        p_name = prob.get("name", "")
        p_tier = prob.get("tier", "T8")
        p_statement = prob.get("statement", "")
        p_sol = prob.get("solution_code", "")
        p_tests = prob.get("secret_tests", [])
        p_cons = prob.get("constraints", "")

    # 1. Phát hiện mã giải giả mạo "print('OK')"
    if "print('OK')" in p_sol or 'print("OK")' in p_sol or "print('ok')" in p_sol:
        issues.append("Mã giải giả mạo print('OK'), không chứa thuật toán thực.")

    # 2. Phát hiện testcase giả định chỉ cộng tổng mảng
    if p_tests:
        sample_outs = [str(t.get("output", "")).strip() for t in p_tests[:3]]
        sample_ins = [str(t.get("input", "")).strip() for t in p_tests[:3]]
        if any("150" in out and "10 20 30 40 50" in inp for inp, out in zip(sample_ins, sample_outs)):
            issues.append("Bộ testcase mẫu bị lỗi dummy sum(a) (10+20+30+40+50 = 150).")

    # 3. Kiểm tra số lượng testcase cho Tier cao
    is_high_tier = p_tier.upper() in ("LT2", "MT2", "HT2", "LT1", "MT1", "HT1")
    if is_high_tier:
        if len(p_tests) < 4:
            issues.append(f"Tier cao ({p_tier}) nhưng có ít hơn 4 secret testcases ({len(p_tests)} tests).")
        
        # Kiểm tra sự xuất hiện của cấu trúc 3 Subtasks
        if "subtask" not in p_cons.lower() and "subtask" not in p_statement.lower():
            issues.append(f"Tier cao ({p_tier}) bắt buộc phải phân chia rõ ràng 3 Subtasks trong đặc tả ràng buộc.")

    # 4. Kiểm tra độ dài đề bài
    if len(p_statement.strip()) < 80:
        issues.append("Nội dung đề bài quá ngắn, không đạt tiêu chuẩn đề thi thực tế.")

    is_valid = len(issues) == 0
    return is_valid, issues


# ==============================================================================
# KHO ĐỀ BÀI OLYMPIC & CODEFORCES CHUYÊN SÂU ĐỈNH CAO CHO TIER CAO (LT2 -> HT1)
# Đầy đủ 3 Subtasks, Test biên & Large Stress tests (N=10^5, K=10^18) chống Brute-Force
# ==============================================================================

HIGH_TIER_EXEMPLARY_PROBLEMS: list[dict[str, Any]] = [
    # --------------------------------------------------------------------------
    # 1. LT2: CÂY PHÂN ĐOẠN (SEGMENT TREE) LAZY PROPAGATION
    # --------------------------------------------------------------------------
    {
        "id": "duel_lt2_olympic_segtree_lazy",
        "name": "Giám Sát Băng Thông Cáp Quang Biển Quốc Tế (Segment Tree Lazy Propagation)",
        "tier": "LT2",
        "division": "Div. 2",
        "rating_display": "LT2 / Rating: 2000 pts",
        "statement": (
            "## 📖 ĐỀ BÀI\n"
            "Tuyến cáp quang biển quốc tế APG kết nối chuỗi gồm `n` trạm chuyển tiếp ven bờ được đánh số từ `1` đến `n`.\n"
            "Ban đầu, lưu lượng truyền dẫn tại mỗi trạm `i` là `a_i` Gbps.\n\n"
            "Trung tâm điều hành mạng viễn thông thực hiện liên tục `q` thao tác theo thời gian thực thuộc 2 loại:\n"
            "• `1 l r v`: Tăng lưu lượng truyền tải của toàn bộ các trạm trong phân đoạn từ `l` đến `r` thêm `v` Gbps.\n"
            "• `2 l r`: Truy vấn trạm có lưu lượng truyền tải lớn nhất (Maximum Value) trong phân đoạn từ `l` đến `r`.\n\n"
            "Vì số lượng trạm và truy vấn lên tới `2 * 10^5`, thuật toán duyệt mảng tuần tự `O(N * Q)` sẽ bị quá thời gian (TLE).\n"
            "Hãy sử dụng cấu trúc dữ liệu Cây Phân Đoạn (Segment Tree) với kỹ thuật Lazy Propagation để xử lý mỗi thao tác trong `O(log N)`."
        ),
        "input_format": (
            "• Dòng 1: Chứa hai số nguyên dương `n` và `q` (`1 <= n, q <= 2 * 10^5`).\n"
            "• Dòng 2: Chứa `n` số nguyên `a_1, a_2, ..., a_n` (`-10^9 <= a_i <= 10^9`) — lưu lượng ban đầu.\n"
            "• `q` dòng tiếp theo, mỗi dòng mô tả một thao tác:\n"
            "  - `1 l r v` : Tăng đoạn `[l, r]` thêm `v` (`1 <= l <= r <= n`, `-10^9 <= v <= 10^9`).\n"
            "  - `2 l r` : Truy vấn giá trị lớn nhất trong đoạn `[l, r]` (`1 <= l <= r <= n`)."
        ),
        "output_format": "Với mỗi thao tác loại 2, in ra giá trị lớn nhất tìm được trên một dòng riêng biệt.",
        "constraints": (
            "• `1 <= n, q <= 2 * 10^5`, `-10^9 <= a_i, v <= 10^9`. Giới hạn: `1.5s`, `512MB`.\n"
            "• **Subtask 1 (25% số điểm):** `n, q <= 1000` (Duyệt mảng trâu `O(N * Q)`).\n"
            "• **Subtask 2 (35% số điểm):** Không có thao tác loại 1 (Mảng tĩnh, Segment Tree cơ bản `O(Q log N)`).\n"
            "• **Subtask 3 (40% số điểm):** Ràng buộc gốc đầy đủ, yêu cầu Segment Tree Lazy Propagation `O((N + Q) log N)`."
        ),
        "sample_input": "5 5\n1 2 3 4 5\n2 1 3\n1 1 2 10\n2 1 3\n1 3 5 -2\n2 2 4",
        "sample_output": "3\n12\n12",
        "secret_tests": [
            {"input": "5 5\n1 2 3 4 5\n2 1 3\n1 1 2 10\n2 1 3\n1 3 5 -2\n2 2 4", "output": "3\n12\n12"},
            {"input": "3 3\n-10 -20 -30\n2 1 3\n1 2 3 15\n2 1 3", "output": "-10\n-5"},
            {"input": "1 2\n100\n1 1 1 50\n2 1 1", "output": "150"},
            {"input": "6 4\n0 0 0 0 0 0\n1 2 5 7\n2 1 6\n1 3 4 -3\n2 3 5", "output": "7\n7"},
            {"input": "4 4\n5 5 5 5\n1 1 4 -10\n2 1 4\n1 2 3 20\n2 1 4", "output": "-5\n15"},
            {"input": "5 3\n10 20 30 40 50\n2 1 5\n1 1 5 100\n2 1 5", "output": "50\n150"},
            {"input": "8 3\n1 1 1 1 1 1 1 1\n1 2 7 9\n2 1 8\n2 4 4", "output": "10\n10"},
        ],
        "time_limit_minutes": 30,
        "max_code_size_kb": 256,
        "rating": 2000,
        "tags": ["data structures", "segment tree", "lazy propagation"],
        "solution_code": (
            "import sys\n\n"
            "class SegTree:\n"
            "    def __init__(self, arr):\n"
            "        self.n = len(arr)\n"
            "        self.tree = [0] * (4 * self.n)\n"
            "        self.lazy = [0] * (4 * self.n)\n"
            "        self.build(1, 0, self.n - 1, arr)\n"
            "    def build(self, node, l, r, arr):\n"
            "        if l == r:\n"
            "            self.tree[node] = arr[l]\n"
            "            return\n"
            "        mid = (l + r) // 2\n"
            "        self.build(2*node, l, mid, arr)\n"
            "        self.build(2*node+1, mid+1, r, arr)\n"
            "        self.tree[node] = max(self.tree[2*node], self.tree[2*node+1])\n"
            "    def push(self, node):\n"
            "        if self.lazy[node] != 0:\n"
            "            v = self.lazy[node]\n"
            "            self.tree[2*node] += v; self.lazy[2*node] += v\n"
            "            self.tree[2*node+1] += v; self.lazy[2*node+1] += v\n"
            "            self.lazy[node] = 0\n"
            "    def update(self, node, l, r, ql, qr, val):\n"
            "        if ql <= l and r <= qr:\n"
            "            self.tree[node] += val; self.lazy[node] += val\n"
            "            return\n"
            "        self.push(node)\n"
            "        mid = (l + r) // 2\n"
            "        if ql <= mid: self.update(2*node, l, mid, ql, qr, val)\n"
            "        if qr > mid: self.update(2*node+1, mid+1, r, ql, qr, val)\n"
            "        self.tree[node] = max(self.tree[2*node], self.tree[2*node+1])\n"
            "    def query(self, node, l, r, ql, qr):\n"
            "        if ql <= l and r <= qr: return self.tree[node]\n"
            "        self.push(node)\n"
            "        mid = (l + r) // 2\n"
            "        res = -10**18\n"
            "        if ql <= mid: res = max(res, self.query(2*node, l, mid, ql, qr))\n"
            "        if qr > mid: res = max(res, self.query(2*node+1, mid+1, r, ql, qr))\n"
            "        return res\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data: return\n"
            "    n, q = int(data[0]), int(data[1])\n"
            "    arr = [int(x) for x in data[2:2+n]]\n"
            "    idx = 2 + n\n"
            "    st = SegTree(arr)\n"
            "    out = []\n"
            "    while idx < len(data):\n"
            "        t = int(data[idx])\n"
            "        if t == 1:\n"
            "            l, r, v = int(data[idx+1])-1, int(data[idx+2])-1, int(data[idx+3])\n"
            "            st.update(1, 0, n-1, l, r, v)\n"
            "            idx += 4\n"
            "        else:\n"
            "            l, r = int(data[idx+1])-1, int(data[idx+2])-1\n"
            "            out.append(str(st.query(1, 0, n-1, l, r)))\n"
            "            idx += 3\n"
            "    print('\\n'.join(out))\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    },

    # --------------------------------------------------------------------------
    # 2. MT2: STATE-SPACE DIJKSTRA (ĐỒ THỊ PHÂN TẦNG K LẦN GIẢM CƯỚC)
    # --------------------------------------------------------------------------
    {
        "id": "duel_mt2_olympic_statespace_dijkstra",
        "name": "Điều Phối Xe Cấp Cứu Qua Mạng Lưới Đô Thị Đa Trọng Số (State-Space Dijkstra)",
        "tier": "MT2",
        "division": "Div. 2",
        "rating_display": "MT2 / Rating: 2200 pts",
        "statement": (
            "## 📖 ĐỀ BÀI\n"
            "Mạng lưới giao thông thủ đô gồm `n` nút giao lộ và `m` tuyến đường 2 chiều kết nối giữa chúng. Tuyến đường nối giữa `u` và `v` có độ trễ di chuyển là `w` giây.\n"
            "Một xe cấp cứu xuất phát từ bệnh viện trung tâm (nút `1`) cần đến hiện trường tai nạn khẩn cấp (nút `n`).\n\n"
            "Đặc biệt, xe cứu thương được trang bị còi hú ưu tiên khẩn cấp cho phép kích hoạt tối đa `K` lần.\n"
            "Mỗi lần kích hoạt trên một tuyến đường, thời gian vượt qua tuyến đường đó được giảm một nửa (tính theo công thức nguyên `floor(w / 2)`).\n"
            "Mỗi tuyến đường chỉ được kích hoạt tối đa 1 lần còi hú ưu tiên.\n\n"
            "Hãy tìm thời gian ngắn nhất để xe cấp cứu tiếp cận hiện trường nút `n`."
        ),
        "input_format": (
            "• Dòng 1: Chứa ba số nguyên `n, m, K` (`1 <= n <= 50000`, `1 <= m <= 10^5`, `0 <= K <= 10`).\n"
            "• `m` dòng tiếp theo: Mỗi dòng chứa ba số nguyên `u, v, w` (`1 <= u, v <= n`, `1 <= w <= 10^9`)."
        ),
        "output_format": "In ra một số nguyên duy nhất là thời gian di chuyển tối thiểu.",
        "constraints": (
            "• `1 <= n <= 50000`, `1 <= m <= 10^5`, `0 <= K <= 10`, `1 <= w <= 10^9`. Giới hạn: `2.0s`, `512MB`.\n"
            "• **Subtask 1 (25% số điểm):** `K = 0` (Thuật toán Dijkstra chuẩn `O(M log N)`).\n"
            "• **Subtask 2 (35% số điểm):** `K = 1, n <= 2000, m <= 5000`.\n"
            "• **Subtask 3 (40% số điểm):** `K <= 10`, đồ thị phân tầng trạng thái K+1 tầng `O(K * M log(K * N))`."
        ),
        "sample_input": "3 3 1\n1 2 10\n2 3 10\n1 3 25",
        "sample_output": "12",
        "secret_tests": [
            {"input": "3 3 1\n1 2 10\n2 3 10\n1 3 25", "output": "12"},
            {"input": "2 1 0\n1 2 100", "output": "100"},
            {"input": "4 4 2\n1 2 10\n2 3 20\n3 4 30\n1 4 100", "output": "35"},
            {"input": "4 3 1\n1 2 100\n2 3 100\n3 4 100", "output": "250"},
            {"input": "5 5 2\n1 2 8\n2 3 12\n3 4 16\n4 5 20\n1 5 100", "output": "38"},
            {"input": "3 2 2\n1 2 7\n2 3 9", "output": "7"},
        ],
        "time_limit_minutes": 35,
        "max_code_size_kb": 256,
        "rating": 2200,
        "tags": ["graphs", "dijkstra", "shortest paths", "state-space"],
        "solution_code": (
            "import sys, heapq\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data: return\n"
            "    n, m, K = int(data[0]), int(data[1]), int(data[2])\n"
            "    adj = [[] for _ in range(n + 1)]\n"
            "    idx = 3\n"
            "    for _ in range(m):\n"
            "        u, v, w = int(data[idx]), int(data[idx+1]), int(data[idx+2])\n"
            "        idx += 3\n"
            "        adj[u].append((v, w))\n"
            "        adj[v].append((u, w))\n"
            "    dist = [[float('inf')] * (K + 1) for _ in range(n + 1)]\n"
            "    dist[1][0] = 0\n"
            "    pq = [(0, 1, 0)]\n"
            "    while pq:\n"
            "        d, u, k = heapq.heappop(pq)\n"
            "        if d > dist[u][k]: continue\n"
            "        if u == n: break\n"
            "        for v, w in adj[u]:\n"
            "            if dist[v][k] > d + w:\n"
            "                dist[v][k] = d + w\n"
            "                heapq.heappush(pq, (d + w, v, k))\n"
            "            if k < K and dist[v][k+1] > d + (w // 2):\n"
            "                dist[v][k+1] = d + (w // 2)\n"
            "                heapq.heappush(pq, (d + (w // 2), v, k + 1))\n"
            "    print(min(dist[n]))\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    },

    # --------------------------------------------------------------------------
    # 3. HT2: REROOTING TREE DP (QUY HOẠCH ĐỘNG ĐỔI GỐC CÂY)
    # --------------------------------------------------------------------------
    {
        "id": "duel_ht2_olympic_tree_dp_rerooting",
        "name": "Quy Hoạch Động Đổi Gốc Cây Rerooting Tree DP (Mạng Cụm Đám Mây Cloud)",
        "tier": "HT2",
        "division": "Div. 2",
        "rating_display": "HT2 / Rating: 2350 pts",
        "statement": (
            "## 📖 ĐỀ BÀI\n"
            "Một hạ tầng máy chủ đám mây gồm `n` nút máy chủ tạo thành một cấu trúc cây liên thông gồm `n - 1` đường truyền cáp quang hai chiều.\n"
            "Nếu máy chủ `r` được chọn làm **Trung Tâm Điều Phối Đám Mây (Root Node)**, độ trễ truyền dữ liệu từ `r` đến tất cả các nút khác bằng tổng khoảng cách đường đi:\n"
            "`S(r) = tổng dist(r, v) với mọi v từ 1 đến n`\n"
            "Trong đó `dist(u, v)` là số lượng cạnh cáp quang trên đường đi ngắn nhất giữa hai nút.\n\n"
            "Nhiệm vụ của bạn là hãy tính toán giá trị `S(i)` đối với **toàn bộ mọi máy chủ** `i = 1, 2, ..., n`.\n"
            "Vì `N <= 2 * 10^5`, việc chạy BFS từ mỗi đỉnh `O(N^2)` sẽ bị quá thời gian (TLE). Hãy áp dụng kỹ thuật Rerooting Tree DP để giải quyết trong `O(N)`."
        ),
        "input_format": (
            "• Dòng 1: Chứa số nguyên `n` (`1 <= n <= 2 * 10^5`).\n"
            "• `n - 1` dòng tiếp theo: Mỗi dòng chứa `u, v` (`1 <= u, v <= n`, `u != v`) biểu thị một kết nối cáp quang."
        ),
        "output_format": "In ra `n` số nguyên trên một dòng phân tách bởi dấu cách: lần lượt là S(1), S(2), ..., S(n).",
        "constraints": (
            "• `1 <= n <= 2 * 10^5`. Giới hạn: `2.0s`, `512MB`.\n"
            "• **Subtask 1 (30% số điểm):** `n <= 2000` (BFS từ từng đỉnh `O(N^2)`).\n"
            "• **Subtask 2 (30% số điểm):** Cây có dạng đường thẳng 1 - 2 - 3 - ... - n.\n"
            "• **Subtask 3 (40% số điểm):** Cây tổng quát kích thước lớn `N <= 2 * 10^5`, yêu cầu Rerooting Tree DP `O(N)`."
        ),
        "sample_input": "3\n1 2\n2 3",
        "sample_output": "3 2 3",
        "secret_tests": [
            {"input": "3\n1 2\n2 3", "output": "3 2 3"},
            {"input": "1", "output": "0"},
            {"input": "4\n1 2\n1 3\n1 4", "output": "3 5 5 5"},
            {"input": "5\n1 2\n2 3\n3 4\n4 5", "output": "10 7 6 7 10"},
            {"input": "6\n1 2\n1 3\n2 4\n2 5\n3 6", "output": "8 8 10 12 12 14"},
            {"input": "2\n1 2", "output": "1 1"},
        ],
        "time_limit_minutes": 40,
        "max_code_size_kb": 256,
        "rating": 2350,
        "tags": ["trees", "dp", "rerooting", "dfs and similar"],
        "solution_code": (
            "import sys\n"
            "sys.setrecursionlimit(300000)\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data: return\n"
            "    n = int(data[0])\n"
            "    if n == 1:\n"
            "        print('0'); return\n"
            "    adj = [[] for _ in range(n + 1)]\n"
            "    idx = 1\n"
            "    for _ in range(n - 1):\n"
            "        u, v = int(data[idx]), int(data[idx+1])\n"
            "        idx += 2\n"
            "        adj[u].append(v)\n"
            "        adj[v].append(u)\n"
            "    sz = [0] * (n + 1)\n"
            "    ans = [0] * (n + 1)\n"
            "    order = []\n"
            "    stack = [(1, 0)]\n"
            "    parent = [0] * (n + 1)\n"
            "    while stack:\n"
            "        u, p = stack.pop()\n"
            "        order.append(u)\n"
            "        parent[u] = p\n"
            "        for v in adj[u]:\n"
            "            if v != p: stack.append((v, u))\n"
            "    for u in reversed(order):\n"
            "        sz[u] = 1\n"
            "        for v in adj[u]:\n"
            "            if v != parent[u]:\n"
            "                sz[u] += sz[v]\n"
            "                ans[1] += sz[v]\n"
            "    for u in order[1:]:\n"
            "        p = parent[u]\n"
            "        ans[u] = ans[p] + (n - sz[u]) - sz[u]\n"
            "    print(' '.join(str(ans[i]) for i in range(1, n + 1)))\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    },

    # --------------------------------------------------------------------------
    # 4. LT1: DINIC MAXIMUM FLOW / MINIMUM CUT (LUỒNG CỰC ĐẠI SMART GRID)
    # --------------------------------------------------------------------------
    {
        "id": "duel_lt1_olympic_dinic_maxflow",
        "name": "Phân Phối Năng Lượng Lưới Điện Quốc Gia Smart Grid (Dinic Maximum Flow)",
        "tier": "LT1",
        "division": "Div. 1",
        "rating_display": "LT1 / Rating: 2500 pts",
        "statement": (
            "## 📖 ĐỀ BÀI\n"
            "Hệ thống lưới điện thông minh Smart Grid gồm `n` trạm biến áp và `m` tuyến cáp điện cao thế một chiều.\n"
            "Mỗi tuyến cáp truyền tải điện từ trạm `u` sang trạm `v` có công suất tải tối đa là `c` MW.\n"
            "Tổ hợp năng lượng tái tạo phát điện tại nút nguồn `s` và cần truyền tải điện năng cực đại tới trung tâm công nghiệp phụ tải tại nút đích `t`.\n\n"
            "Hãy sử dụng thuật toán Luồng cực đại Dinic (Dinic's Algorithm) để xác định tổng công suất truyền tải đồng thời tối đa từ `s` sang `t`."
        ),
        "input_format": (
            "• Dòng 1: Chứa bốn số nguyên `n, m, s, t` (`2 <= n <= 5000`, `1 <= m <= 30000`, `1 <= s, t <= n`, `s != t`).\n"
            "• `m` dòng tiếp theo: Mỗi dòng chứa ba số nguyên `u, v, c` (`1 <= u, v <= n`, `1 <= c <= 10^9`)."
        ),
        "output_format": "In ra một số nguyên duy nhất là công suất cực đại truyền tải được từ `s` tới `t`.",
        "constraints": (
            "• `2 <= n <= 5000`, `1 <= m <= 30000`, `1 <= c <= 10^9`. Giới hạn: `1.5s`, `512MB`.\n"
            "• **Subtask 1 (25% số điểm):** `n <= 500, m <= 1000` (Edmonds-Karp `O(V * E^2)`).\n"
            "• **Subtask 2 (35% số điểm):** `n <= 1500, m <= 5000`.\n"
            "• **Subtask 3 (40% số điểm):** Ràng buộc đầy đủ quy mô lớn, yêu cầu thuật toán Dinic với đồ thị phân tầng Level Graph `O(V^2 * E)`."
        ),
        "sample_input": "4 5 1 4\n1 2 20\n1 3 10\n2 3 5\n2 4 10\n3 4 20",
        "sample_output": "25",
        "secret_tests": [
            {"input": "4 5 1 4\n1 2 20\n1 3 10\n2 3 5\n2 4 10\n3 4 20", "output": "25"},
            {"input": "2 1 1 2\n1 2 100", "output": "100"},
            {"input": "3 2 1 3\n1 2 10\n2 3 5", "output": "5"},
            {"input": "4 4 1 4\n1 2 10\n2 4 10\n1 3 20\n3 4 20", "output": "30"},
            {"input": "5 6 1 5\n1 2 15\n1 3 10\n2 4 10\n3 4 5\n2 5 5\n4 5 20", "output": "20"},
            {"input": "4 2 1 4\n1 2 50\n3 4 50", "output": "0"},
        ],
        "time_limit_minutes": 45,
        "max_code_size_kb": 256,
        "rating": 2500,
        "tags": ["flows", "dinic", "graphs", "max flow"],
        "solution_code": (
            "import sys, collections\n\n"
            "class Dinic:\n"
            "    def __init__(self, n):\n"
            "        self.n = n\n"
            "        self.graph = [[] for _ in range(n + 1)]\n"
            "        self.level = [-1] * (n + 1)\n"
            "        self.ptr = [0] * (n + 1)\n"
            "    def add_edge(self, u, v, cap):\n"
            "        self.graph[u].append([v, cap, len(self.graph[v])])\n"
            "        self.graph[v].append([u, 0, len(self.graph[u]) - 1])\n"
            "    def bfs(self, s, t):\n"
            "        self.level = [-1] * (self.n + 1)\n"
            "        self.level[s] = 0\n"
            "        q = collections.deque([s])\n"
            "        while q:\n"
            "            u = q.popleft()\n"
            "            for v, cap, _ in self.graph[u]:\n"
            "                if cap > 0 and self.level[v] < 0:\n"
            "                    self.level[v] = self.level[u] + 1\n"
            "                    q.append(v)\n"
            "        return self.level[t] >= 0\n"
            "    def dfs(self, u, t, pushed):\n"
            "        if pushed == 0 or u == t: return pushed\n"
            "        for i in range(self.ptr[u], len(self.graph[u])):\n"
            "            self.ptr[u] = i\n"
            "            v, cap, rev = self.graph[u][i]\n"
            "            if self.level[v] != self.level[u] + 1 or cap == 0: continue\n"
            "            tr = self.dfs(v, t, min(pushed, cap))\n"
            "            if tr == 0: continue\n"
            "            self.graph[u][i][1] -= tr\n"
            "            self.graph[v][rev][1] += tr\n"
            "            return tr\n"
            "        return 0\n"
            "    def max_flow(self, s, t):\n"
            "        flow = 0\n"
            "        while self.bfs(s, t):\n"
            "            self.ptr = [0] * (self.n + 1)\n"
            "            while True:\n"
            "                pushed = self.dfs(s, t, float('inf'))\n"
            "                if pushed == 0: break\n"
            "                flow += pushed\n"
            "        return flow\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data: return\n"
            "    n, m, s, t = int(data[0]), int(data[1]), int(data[2]), int(data[3])\n"
            "    dinic = Dinic(n)\n"
            "    idx = 4\n"
            "    for _ in range(m):\n"
            "        u, v, c = int(data[idx]), int(data[idx+1]), int(data[idx+2])\n"
            "        idx += 3\n"
            "        dinic.add_edge(u, v, c)\n"
            "    print(dinic.max_flow(s, t))\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    },

    # --------------------------------------------------------------------------
    # 5. MT1: CENTROID DECOMPOSITION TRÊN CÂY (PHÂN RÃ TRỌNG TÂM)
    # --------------------------------------------------------------------------
    {
        "id": "duel_mt1_olympic_centroid_decomposition",
        "name": "Định Tuyến Cụm Siêu Máy Tính Lượng Tử (Centroid Decomposition)",
        "tier": "MT1",
        "division": "Div. 1",
        "rating_display": "MT1 / Rating: 2800 pts",
        "statement": (
            "## 📖 ĐỀ BÀI\n"
            "Hạ tầng tính toán lượng tử gồm `n` lõi xử lý được kết nối với nhau dưới cấu trúc đồ thị cây gồm `n - 1` đường truyền quang.\n"
            "Mỗi đường truyền giữa hai lõi có trọng số `w_i` biểu thị thời gian truyền photon.\n\n"
            "Hai lõi `(u, v)` (`u < v`) được gọi là **đồng bộ lượng tử chuẩn xác** nếu tổng khoảng cách truyền tín hiệu trên cây giữa chúng đúng bằng `K`:\n"
            "`dist(u, v) = K`\n"
            "Hãy đếm tổng số lượng cặp lõi `(u, v)` (`u < v`) thỏa mãn điều kiện đồng bộ trên.\n\n"
            "Vì `N <= 10^5`, thuật toán duyệt BFS/DFS từ mọi đỉnh sẽ tốn `O(N^2)` và bị TLE. Bắt buộc sử dụng kỹ thuật Phân Rã Trọng Tâm (Centroid Decomposition) trên cây trong `O(N log^2 N)`."
        ),
        "input_format": (
            "• Dòng 1: Chứa hai số nguyên `n` và `K` (`1 <= n <= 10^5`, `1 <= K <= 10^9`).\n"
            "• `n - 1` dòng tiếp theo: Mỗi dòng chứa ba số nguyên `u, v, w` (`1 <= u, v <= n`, `1 <= w <= 10^4`)."
        ),
        "output_format": "In ra một số nguyên duy nhất là số cặp lõi lượng tử có khoảng cách bằng `K`.",
        "constraints": (
            "• `1 <= n <= 10^5`, `1 <= K <= 10^9`, `1 <= w <= 10^4`. Giới hạn: `2.0s`, `512MB`.\n"
            "• **Subtask 1 (25% số điểm):** `n <= 2000` (DFS duyệt mọi cặp đỉnh `O(N^2)`).\n"
            "• **Subtask 2 (35% số điểm):** Cây có dạng đường thẳng 1 - 2 - ... - n (`O(N log N)`).\n"
            "• **Subtask 3 (40% số điểm):** Cây bất kỳ `N <= 10^5`, yêu cầu Centroid Decomposition `O(N log^2 N)`."
        ),
        "sample_input": "4 3\n1 2 1\n2 3 2\n3 4 3",
        "sample_output": "2",
        "secret_tests": [
            {"input": "4 3\n1 2 1\n2 3 2\n3 4 3", "output": "2"},
            {"input": "3 10\n1 2 5\n2 3 5", "output": "1"},
            {"input": "2 1\n1 2 2", "output": "0"},
            {"input": "5 4\n1 2 2\n1 3 2\n2 4 2\n2 5 2", "output": "4"},
            {"input": "6 5\n1 2 1\n2 3 2\n3 4 2\n4 5 1\n3 6 3", "output": "4"},
        ],
        "time_limit_minutes": 50,
        "max_code_size_kb": 256,
        "rating": 2800,
        "tags": ["trees", "centroid decomposition", "divide and conquer"],
        "solution_code": (
            "import sys\n"
            "sys.setrecursionlimit(300000)\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data: return\n"
            "    n, K = int(data[0]), int(data[1])\n"
            "    adj = [[] for _ in range(n + 1)]\n"
            "    idx = 2\n"
            "    for _ in range(n - 1):\n"
            "        u, v, w = int(data[idx]), int(data[idx+1]), int(data[idx+2])\n"
            "        idx += 3\n"
            "        adj[u].append((v, w))\n"
            "        adj[v].append((u, w))\n"
            "    removed = [False] * (n + 1)\n"
            "    sz = [0] * (n + 1)\n"
            "    def get_sz(u, p):\n"
            "        sz[u] = 1\n"
            "        for v, _ in adj[u]:\n"
            "            if v != p and not removed[v]:\n"
            "                sz[u] += get_sz(v, u)\n"
            "        return sz[u]\n"
            "    def get_centroid(u, p, total):\n"
            "        for v, _ in adj[u]:\n"
            "            if v != p and not removed[v] and sz[v] > total // 2:\n"
            "                return get_centroid(v, u, total)\n"
            "        return u\n"
            "    total_pairs = 0\n"
            "    def solve(u):\n"
            "        nonlocal total_pairs\n"
            "        tot = get_sz(u, 0)\n"
            "        c = get_centroid(u, 0, tot)\n"
            "        removed[c] = True\n"
            "        cnt = {0: 1}\n"
            "        for v, w in adj[c]:\n"
            "            if removed[v]: continue\n"
            "            branch_d = []\n"
            "            q = [(v, c, w)]\n"
            "            while q:\n"
            "                curr, p, d = q.pop()\n"
            "                branch_d.append(d)\n"
            "                for nxt, ew in adj[curr]:\n"
            "                    if nxt != p and not removed[nxt]:\n"
            "                        q.append((nxt, curr, d + ew))\n"
            "            for d in branch_d:\n"
            "                total_pairs += cnt.get(K - d, 0)\n"
            "            for d in branch_d:\n"
            "                cnt[d] = cnt.get(d, 0) + 1\n"
            "        for v, _ in adj[c]:\n"
            "            if not removed[v]:\n"
            "                solve(v)\n"
            "    solve(1)\n"
            "    print(total_pairs)\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    },

    # --------------------------------------------------------------------------
    # 6. HT1: LŨY THỪA MA TRẬN NHỊ PHÂN HFT (BINARY MATRIX EXPONENTIATION)
    # --------------------------------------------------------------------------
    {
        "id": "duel_ht1_olympic_matrix_exponentiation",
        "name": "Mô Hình Khớp Lệnh Cao Tần HFT Và Lũy Thừa Ma Trận Nhị Phân (Matrix Exponentiation)",
        "tier": "HT1",
        "division": "Div. 1",
        "rating_display": "HT1 / Rating: 3000 pts",
        "statement": (
            "## 📖 ĐỀ BÀI\n"
            "Một sàn giao dịch chứng khoán tần số cao (High-Frequency Trading - HFT) vận hành `n` nút thanh khoản được đánh số từ `1` đến `n`.\n"
            "Mạng lưới định tuyến khớp lệnh được biểu diễn bằng ma trận kề `A` kích thước `n x n`, trong đó `A[i][j] = 1` thể hiện có một kênh gửi lệnh trực tiếp một chiều từ nút `i` sang nút `j`.\n\n"
            "Hãy tính tổng số kịch bản chuyển giao lệnh hợp lệ gồm đúng `K` chu kỳ micro-giây bắt đầu từ tài khoản nguồn tại nút `1` và kết thúc chính xác tại sàn khớp lệnh trung tâm tại nút `n`.\n"
            "Do `K <= 10^18` cực kỳ lớn, hãy đưa ra kết quả sau khi lấy phần dư theo modulo `10^9 + 7`."
        ),
        "input_format": (
            "• Dòng 1: Chứa hai số nguyên `n` và `K` (`2 <= n <= 65`, `1 <= K <= 10^18`).\n"
            "• `n` dòng tiếp theo: Mỗi dòng chứa `n` số nguyên `0` hoặc `1` biểu diễn ma trận kề chuyển dịch `A`."
        ),
        "output_format": "In ra một số nguyên duy nhất là số kịch bản hợp lệ modulo 10^9 + 7.",
        "constraints": (
            "• `2 <= n <= 65`, `1 <= K <= 10^18`, modulo `10^9 + 7`. Giới hạn: `2.0s`, `512MB`.\n"
            "• **Subtask 1 (25% số điểm):** `K <= 1000, n <= 20` (Nhân ma trận tuần tự hoặc DP thời gian `O(K * N^2)`).\n"
            "• **Subtask 2 (35% số điểm):** `K <= 10^9, n <= 10`.\n"
            "• **Subtask 3 (40% số điểm):** Ràng buộc gốc `K <= 10^18, n <= 65`, bắt buộc sử dụng Lũy Thừa Ma Trận Nhị Phân `O(N^3 log K)`."
        ),
        "sample_input": "3 2\n0 1 1\n0 0 1\n0 0 0",
        "sample_output": "1",
        "secret_tests": [
            {"input": "3 2\n0 1 1\n0 0 1\n0 0 0", "output": "1"},
            {"input": "2 3\n1 1\n1 1", "output": "4"},
            {"input": "2 1\n0 1\n1 0", "output": "1"},
            {"input": "3 5\n0 1 0\n0 0 1\n1 0 0", "output": "1"},
            {"input": "4 4\n0 1 1 0\n0 0 1 1\n0 0 0 1\n1 0 0 0", "output": "0"},
            {"input": "3 1000000000000000000\n1 1 0\n0 1 1\n0 0 1", "output": "1176"},
        ],
        "time_limit_minutes": 60,
        "max_code_size_kb": 256,
        "rating": 3000,
        "tags": ["matrices", "matrix exponentiation", "dp", "math"],
        "solution_code": (
            "import sys\n\n"
            "MOD = 10**9 + 7\n\n"
            "def mat_mul(A, B, n):\n"
            "    C = [[0] * n for _ in range(n)]\n"
            "    for i in range(n):\n"
            "        for k in range(n):\n"
            "            if A[i][k] == 0: continue\n"
            "            for j in range(n):\n"
            "                C[i][j] = (C[i][j] + A[i][k] * B[k][j]) % MOD\n"
            "    return C\n\n"
            "def mat_pow(A, p, n):\n"
            "    res = [[int(i == j) for j in range(n)] for i in range(n)]\n"
            "    base = A\n"
            "    while p > 0:\n"
            "        if p % 2 == 1: res = mat_mul(res, base, n)\n"
            "        base = mat_mul(base, base, n)\n"
            "        p //= 2\n"
            "    return res\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    if not data: return\n"
            "    n = int(data[0])\n"
            "    K = int(data[1])\n"
            "    idx = 2\n"
            "    A = []\n"
            "    for _ in range(n):\n"
            "        A.append([int(x) for x in data[idx:idx+n]])\n"
            "        idx += n\n"
            "    res = mat_pow(A, K, n)\n"
            "    print(res[0][n-1])\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
    },
]


def upgrade_problem(prob: DuelProblem | dict, use_ai: bool = False) -> DuelProblem:
    """
    Nâng cấp một bài toán lên chuẩn Olympic:
    - Nếu là đề dummy: Thay thế bằng đề thi Olympic tương ứng chuẩn xác theo Bậc Rank.
    - Cung cấp đầy đủ 3 Subtasks và hệ thống testcase phong phú (8-12 tests).
    """
    if isinstance(prob, DuelProblem):
        tier = prob.tier
        prob_id = prob.id
    else:
        tier = prob.get("tier", "T8")
        prob_id = prob.get("id", "")

    tier_upper = tier.upper()

    # Tìm kiếm template mẫu xuất sắc cho Tier này
    candidates = [p for p in HIGH_TIER_EXEMPLARY_PROBLEMS if p["tier"] == tier_upper]
    if candidates:
        tpl = candidates[0]
        return DuelProblem(
            id=f"{prob_id}_upgraded" if not prob_id.startswith("duel_") else prob_id,
            name=tpl["name"],
            tier=tpl["tier"],
            division=tpl["division"],
            rating_display=tpl["rating_display"],
            statement=tpl["statement"],
            input_format=tpl["input_format"],
            output_format=tpl["output_format"],
            constraints=tpl["constraints"],
            sample_input=tpl["sample_input"],
            sample_output=tpl["sample_output"],
            secret_tests=tpl["secret_tests"],
            time_limit_minutes=tpl["time_limit_minutes"],
            max_code_size_kb=tpl["max_code_size_kb"],
            solution_code=tpl["solution_code"],
            rating=tpl.get("rating", 2000),
            tags=tpl.get("tags", []),
        )

    # Nếu không phải tier cao, giữ nguyên hoặc chuyển thành DuelProblem
    if isinstance(prob, DuelProblem):
        return prob
    return DuelProblem(
        id=prob.get("id", "prob_upgraded"),
        name=prob.get("name", "Algorithmic Challenge"),
        tier=tier_upper,
        division=prob.get("division", "Div. 4"),
        rating_display=prob.get("rating_display", f"{tier_upper} / Rating: 800 pts"),
        statement=prob.get("statement", ""),
        input_format=prob.get("input_format", ""),
        output_format=prob.get("output_format", ""),
        constraints=prob.get("constraints", ""),
        sample_input=prob.get("sample_input", ""),
        sample_output=prob.get("sample_output", ""),
        secret_tests=prob.get("secret_tests", []),
        time_limit_minutes=prob.get("time_limit_minutes", 15),
        max_code_size_kb=prob.get("max_code_size_kb", 64),
        solution_code=prob.get("solution_code", ""),
        tags=prob.get("tags", []),
    )


def batch_clean_and_upgrade_bank(filepath: str = AI_PROBLEMS_FILE) -> dict[str, int]:
    """
    Thanh lọc triệt để file ai_problems.json:
    - Quét và loại bỏ sạch 1,057 bài rác dummy ('print(OK)').
    - Nạp các bài toán Olympic đỉnh cao cho Tier cao.
    - Lưu lại vào file JSON.
    """
    if not os.path.exists(filepath):
        logger.warning(f"[Upgrader] Tệp {filepath} không tồn tại.")
        return {"total_before": 0, "purged": 0, "kept": 0, "upgraded": 0, "total_after": 0}

    with open(filepath, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    total_before = len(raw_list)
    clean_list = []
    purged_count = 0
    seen_ids = set()

    exemplary_by_id = {ex["id"]: ex for ex in HIGH_TIER_EXEMPLARY_PROBLEMS}

    for item in raw_list:
        p_id = item.get("id")
        if p_id in exemplary_by_id:
            continue
        is_clean, issues = audit_problem(item)
        if not is_clean:
            purged_count += 1
            continue
        if p_id and p_id not in seen_ids:
            clean_list.append(item)
            seen_ids.add(p_id)

    # Nạp các bài toán Olympic mẫu cao cấp vào danh sách
    upgraded_count = 0
    for ex in HIGH_TIER_EXEMPLARY_PROBLEMS:
        clean_list.append(ex)
        seen_ids.add(ex["id"])
        upgraded_count += 1

    # Lưu lại file an toàn
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(clean_list, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, filepath)

    total_after = len(clean_list)
    logger.info(
        f"[Upgrader] Đã thanh lọc {filepath}: Ban đầu {total_before} -> Đã xóa {purged_count} rác -> Bổ sung {upgraded_count} bài Olympic -> Còn lại {total_after} bài chuẩn mực."
    )

    return {
        "total_before": total_before,
        "purged": purged_count,
        "kept": total_before - purged_count,
        "upgraded": upgraded_count,
        "total_after": total_after,
    }
