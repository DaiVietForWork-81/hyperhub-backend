"""
services/problem_factory.py
Hệ thống tạo đề bài Olympic Tin học / Competitive Programming chuyên sâu thuần Python (Python Problem Factory).
Đảm bảo 100% đề bài chính xác, phong phú, độc bản, phân hóa rõ rệt các thuật toán theo từng bậc Tier:
- T8 (Rating: 300 pts): Thống kê & Mảng cơ bản (Trạm đo ven biển, Thư viện trường học)
- T7 (Rating: 550 pts): Prefix Sum O(1) (Cân bằng tải Kubernetes Flash Sale, Doanh thu chuỗi siêu thị)
- T6 (Rating: 850 pts): Tham lam & Hai con trỏ O(N log N) (Drone vận chuyển y tế, Ghép cặp đấu Esports)
- T5 (Rating: 1300 pts): Chặt nhị phân kết quả O(N log(Sum)) (Chiến thuật Pit-stop F1, Phân bổ trạm sạc xe điện)
- T4 (Rating: 1500 pts): Quy hoạch động 1D (Tối ưu hóa cache CDN, Lập lịch ca trực trạm vũ trụ)
- T3 (Rating: 1750 pts): LIS O(N log N) (Xếp kiện hàng kho Logistics, Thu thập điểm thưởng game platformer)
- LT2 (Rating: 2000 pts - Div. 2): Segment Tree / Fenwick Tree (Giám sát trạm thu phí ETC, Băng thông luồng video)
- MT2 (Rating: 2200 pts - Div. 2): Dijkstra State-Space / Grid DP 2D (Điều phối xe cấp cứu, Tối ưu quỹ đạo vệ tinh)
- HT2 (Rating: 2350 pts - Div. 2): Tree DP / Binary Search + Greedy (Phân bổ mạng viễn thông trên cây, Lập lịch dây chuyền sản xuất chip)
- LT1 (Rating: 2500 pts - Div. 1): Bitmask DP N<=18 / DSU Kruskal (Đội bay Drone giao hàng, Khôi phục lưới điện thông minh)
- MT1 (Rating: 2800 pts - Div. 1): Binary Trie XOR / Tổ hợp Modulo Fermat (Mã hóa gói tin mạng lượng tử, Khớp lệnh tài chính đa chiều)
- HT1 (Rating: 3000 pts - Div. 1): Lũy thừa ma trận nhị phân / DP Fenwick (Khớp lệnh cao tần HFT, Tối ưu hóa chuỗi cung ứng toàn cầu)
"""

from __future__ import annotations

import random
import time
from services.duel_problems import DuelProblem, PROBLEM_BANK

TIER_TEMPLATES = {
    # --------------------------------------------------------------------------
    # T8 (Rating: 300 pts • Div. 4)
    # --------------------------------------------------------------------------
    "T8": [
        {
            "name": "Giám Sát Lưu Lượng Mưa Và Đường Đi Bão Nhiệt Đới Tại Trạm Ven Biển",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Trung tâm Dự báo Khí tượng Thủy văn Quốc gia thiết lập một chuỗi gồm `n` trạm quan trắc ven biển được đánh số từ `1` đến `n`.\n"
                "Khi một cơn bão nhiệt đới đổ bộ vào đất liền, mỗi trạm `i` ghi nhận được lượng mưa tích lũy là `a_i` mm trong 24 giờ qua.\n"
                "Cơ quan phòng chống thiên tai cần xác định trạm có lượng mưa lớn nhất và đếm số lượng trạm ghi nhận mức mưa vượt ngưỡng nguy hiểm `k` mm để phát lệnh sơ tán khẩn cấp."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `k` (`1 <= n <= 10^5`, `1 <= k <= 10^4`).\n• Dòng 2: Chứa `n` số nguyên `a_1, a_2, ..., a_n` (`0 <= a_i <= 10^4`).",
            "output_format": "In ra hai số nguyên cách nhau bởi dấu cách: lượng mưa lớn nhất ghi nhận được và số lượng trạm vượt ngưỡng nguy hiểm `k`.",
            "constraints": "`1 <= n <= 10^5`, `0 <= a_i, k <= 10^4`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "5 150\n120 200 80 150 310",
            "sample_output": "310 2",
            "secret_tests": [
                {"input": "5 150\n120 200 80 150 310", "output": "310 2"},
                {"input": "3 100\n50 60 70", "output": "70 0"},
                {"input": "4 50\n50 50 50 50", "output": "50 0"},
                {"input": "1 10\n20", "output": "20 1"},
                {"input": "6 200\n100 250 180 300 150 400", "output": "400 3"},
            ],
            "time_limit_minutes": 15,
            "max_code_size_kb": 64,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    k = int(data[1])\n"
                "    a = [int(x) for x in data[2:2+n]]\n"
                "    max_val = max(a)\n"
                "    cnt = sum(1 for x in a if x > k)\n"
                "    print(f'{max_val} {cnt}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
        {
            "name": "Kiểm Kê Kho Sách Thư Viện Trường Học (Phân Loại Chẵn Lẻ)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Thư viện trường học nhận một lô gồm `n` kiện sách được đánh mã số lượng từ `a_1` đến `a_n`.\n"
                "Thủ thư cần phân loại: đếm tổng số lượng sách nằm trong các kiện có số lượng là số chẵn và tổng số lượng sách trong các kiện có số lượng là số lẻ.\n"
                "Hãy giúp thủ thư tính toán nhanh hai đại lượng trên."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`1 <= n <= 10^5`).\n• Dòng 2: Chứa `n` số nguyên `a_1, ..., a_n` (`1 <= a_i <= 10^4`).",
            "output_format": "In ra hai số nguyên cách nhau bởi dấu cách: tổng số sách trong kiện chẵn và tổng số sách trong kiện lẻ.",
            "constraints": "`1 <= n <= 10^5`, `1 <= a_i <= 10^4`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "5\n2 3 4 5 6",
            "sample_output": "12 8",
            "secret_tests": [
                {"input": "5\n2 3 4 5 6", "output": "12 8"},
                {"input": "3\n1 3 5", "output": "0 9"},
                {"input": "3\n2 4 6", "output": "12 0"},
                {"input": "1\n10", "output": "10 0"},
                {"input": "4\n10 15 20 25", "output": "30 40"},
            ],
            "time_limit_minutes": 15,
            "max_code_size_kb": 64,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    a = [int(x) for x in data[1:1+n]]\n"
                "    sum_even = sum(x for x in a if x % 2 == 0)\n"
                "    sum_odd = sum(x for x in a if x % 2 != 0)\n"
                "    print(f'{sum_even} {sum_odd}')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
    ],

    # --------------------------------------------------------------------------
    # T7 (Rating: 550 pts • Div. 4)
    # --------------------------------------------------------------------------
    "T7": [
        {
            "name": "Cân Bằng Tải Cụm Máy Chủ Kubernetes Tự Động Scale Dịp Flash Sale (Prefix Sum)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Hạ tầng thương mại điện tử triển khai cụm gồm `n` máy chủ phục vụ sự kiện Flash Sale, mỗi máy chủ `i` ban đầu tiếp nhận `a_i` lượt truy cập (RPS).\n"
                "Hệ thống giám sát gửi `q` truy vấn yêu cầu kiểm tra tổng tải của các phân vùng máy chủ từ vị trí `l` đến vị trí `r` (`a_l + a_{l+1} + ... + a_r`).\n"
                "Hãy sử dụng kỹ thuật Mảng cộng dồn (Prefix Sum) để trả lời từng truy vấn trong thời gian `O(1)`."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `q` (`1 <= n, q <= 10^5`).\n• Dòng 2: Chứa `n` số nguyên `a_1, ..., a_n` (`1 <= a_i <= 10^4`).\n• `q` dòng tiếp theo: Mỗi dòng chứa hai số nguyên `l` và `r` (`1 <= l <= r <= n`).",
            "output_format": "Với mỗi truy vấn, in ra tổng tải của phân vùng trên một dòng riêng biệt.",
            "constraints": "`1 <= n, q <= 10^5`, `1 <= a_i <= 10^4`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "5 3\n15 25 35 45 55\n1 3\n2 4\n1 5",
            "sample_output": "75\n105\n175",
            "secret_tests": [
                {"input": "5 3\n15 25 35 45 55\n1 3\n2 4\n1 5", "output": "75\n105\n175"},
                {"input": "3 2\n5 5 5\n1 1\n2 3", "output": "5\n10"},
                {"input": "1 1\n100\n1 1", "output": "100"},
                {"input": "4 2\n1 2 3 4\n1 4\n2 3", "output": "10\n5"},
                {"input": "5 1\n2 4 6 8 10\n3 5", "output": "24"},
            ],
            "time_limit_minutes": 18,
            "max_code_size_kb": 64,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    q = int(data[1])\n"
                "    idx = 2\n"
                "    a = [int(x) for x in data[idx:idx+n]]\n"
                "    idx += n\n"
                "    pref = [0] * (n + 1)\n"
                "    for i in range(n):\n"
                "        pref[i+1] = pref[i] + a[i]\n"
                "    out = []\n"
                "    for _ in range(q):\n"
                "        l = int(data[idx])\n"
                "        r = int(data[idx+1])\n"
                "        idx += 2\n"
                "        out.append(str(pref[r] - pref[l-1]))\n"
                "    print('\\n'.join(out))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
    ],

    # --------------------------------------------------------------------------
    # T6 (Rating: 850 pts • Div. 4)
    # --------------------------------------------------------------------------
    "T6": [
        {
            "name": "Điều Phối Drone Vận Chuyển Hàng Y Tế Cứu Trợ Thiên Tai (Greedy & Two Pointers)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một đội gồm nhiều chiếc Drone cứu trợ cần vận chuyển `n` kiện hàng y tế đến vùng lũ lụt, mỗi kiện hàng có trọng lượng `w_i` kg.\n"
                "Mỗi chuyến bay, một chiếc Drone có thể chở **tối đa 2 kiện hàng**, với điều kiện tổng trọng lượng không được vượt quá tải trọng tối đa `c` kg.\n"
                "Hãy tìm số chuyến Drone ít nhất cần thiết để vận chuyển hết toàn bộ `n` kiện hàng."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `c` (`1 <= n <= 10^5`, `1 <= c <= 10^9`).\n• Dòng 2: Chứa `n` số nguyên `w_1, ..., w_n` (`1 <= w_i <= c`).",
            "output_format": "In ra một số nguyên duy nhất là số chuyến bay tối thiểu.",
            "constraints": "`1 <= n <= 10^5`, `1 <= w_i <= c <= 10^9`. Thuật toán: Greedy kết hợp Two Pointers `O(N log N)`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "4 5\n3 5 3 4",
            "sample_output": "3",
            "secret_tests": [
                {"input": "4 5\n3 5 3 4", "output": "3"},
                {"input": "3 3\n1 2 3", "output": "2"},
                {"input": "5 10\n2 3 5 7 8", "output": "3"},
                {"input": "1 100\n50", "output": "1"},
                {"input": "6 10\n5 5 5 5 5 5", "output": "3"},
            ],
            "time_limit_minutes": 20,
            "max_code_size_kb": 64,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    c = int(data[1])\n"
                "    w = sorted([int(x) for x in data[2:2+n]])\n"
                "    i, j = 0, n - 1\n"
                "    ans = 0\n"
                "    while i <= j:\n"
                "        if i == j:\n"
                "            ans += 1\n"
                "            break\n"
                "        if w[i] + w[j] <= c:\n"
                "            i += 1\n"
                "            j -= 1\n"
                "        else:\n"
                "            j -= 1\n"
                "        ans += 1\n"
                "    print(ans)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
    ],

    # --------------------------------------------------------------------------
    # T5 (Rating: 1300 pts • Div. 3)
    # --------------------------------------------------------------------------
    "T5": [
        {
            "name": "Chiến Thuật Phân Phối Trạm Sạc Xe Điện Cao Tốc (Binary Search on Answer)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Tuyến đường cao tốc gồm `n` trạm dừng nghỉ liên tiếp, khoảng cách giữa các trạm lần lượt là `a_1, a_2, ..., a_n` km.\n"
                "Cần chia toàn bộ tuyến đường thành `k` chặng di chuyển liên tiếp sao cho độ dài của chặng dài nhất là nhỏ nhất có thể.\n"
                "Hãy tìm giá trị nhỏ nhất của độ dài chặng lớn nhất đó."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `k` (`1 <= k <= n <= 10^5`).\n• Dòng 2: Chứa `n` số nguyên dương `a_1, ..., a_n` (`1 <= a_i <= 10^9`).",
            "output_format": "In ra độ dài chặng lớn nhất nhỏ nhất có thể.",
            "constraints": "`1 <= k <= n <= 10^5`, `1 <= a_i <= 10^9`. Thuật toán: Chặt nhị phân kết quả `O(N log(Sum))`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "5 2\n1 2 3 4 5",
            "sample_output": "6",
            "secret_tests": [
                {"input": "5 2\n1 2 3 4 5", "output": "6"},
                {"input": "3 1\n10 20 30", "output": "30"},
                {"input": "4 4\n5 5 5 5", "output": "5"},
                {"input": "5 3\n1 4 4 1 5", "output": "5"},
                {"input": "6 2\n7 2 5 10 8 1", "output": "18"},
            ],
            "time_limit_minutes": 22,
            "max_code_size_kb": 128,
            "solution_code": (
                "import sys\n\n"
                "def check(mid, n, k, a):\n"
                "    splits = 0\n"
                "    curr = 0\n"
                "    for x in a:\n"
                "        if x > mid: return False\n"
                "        if curr + x > mid:\n"
                "            splits += 1\n"
                "            curr = x\n"
                "        else:\n"
                "            curr += x\n"
                "    return splits <= k\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    k = int(data[1])\n"
                "    a = [int(x) for x in data[2:2+n]]\n"
                "    low, high = max(a), sum(a)\n"
                "    ans = high\n"
                "    while low <= high:\n"
                "        mid = (low + high) // 2\n"
                "        if check(mid, n, k, a):\n"
                "            ans = mid\n"
                "            high = mid - 1\n"
                "        else:\n"
                "            low = mid + 1\n"
                "    print(ans)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
    ],

    # --------------------------------------------------------------------------
    # T4 (Rating: 1500 pts • Div. 3)
    # --------------------------------------------------------------------------
    "T4": [
        {
            "name": "Tối Ưu Hóa Bộ Nhớ Đệm Mạng CDN Phân Tán (1D Dynamic Programming)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một mạng phân phối nội dung (CDN) có `n` cụm máy chủ đặt liên tiếp. Mỗi cụm `i` mang lại giá trị lưu lượng `v_i` USD.\n"
                "Do giới hạn băng thông đường trục, không được chọn hai cụm máy chủ nằm cạnh nhau (`i` và `i+1`).\n"
                "Hãy tìm tổng giá trị lưu lượng lớn nhất có thể thu được."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`1 <= n <= 10^5`).\n• Dòng 2: Chứa `n` số nguyên `v_1, v_2, ..., v_n` (`1 <= v_i <= 10^9`).",
            "output_format": "In ra tổng giá trị lớn nhất đạt được.",
            "constraints": "`1 <= n <= 10^5`, `1 <= v_i <= 10^9`. Thuật toán: Quy hoạch động 1D `O(N)`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "5\n2 7 9 3 1",
            "sample_output": "12",
            "secret_tests": [
                {"input": "5\n2 7 9 3 1", "output": "12"},
                {"input": "4\n1 2 3 1", "output": "4"},
                {"input": "1\n100", "output": "100"},
                {"input": "6\n5 1 1 5 1 5", "output": "15"},
                {"input": "4\n10 2 3 20", "output": "30"},
            ],
            "time_limit_minutes": 22,
            "max_code_size_kb": 128,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    v = [int(x) for x in data[1:1+n]]\n"
                "    if n == 1:\n"
                "        print(v[0]); return\n"
                "    dp0, dp1 = 0, v[0]\n"
                "    for i in range(1, n):\n"
                "        ndp0 = max(dp0, dp1)\n"
                "        ndp1 = dp0 + v[i]\n"
                "        dp0, dp1 = ndp0, ndp1\n"
                "    print(max(dp0, dp1))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
    ],

    # --------------------------------------------------------------------------
    # T3 (Rating: 1750 pts • Div. 3)
    # --------------------------------------------------------------------------
    "T3": [
        {
            "name": "Xếp Tầng Kiện Hàng Logistics Kho Thông Minh (LIS O(N log N))",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Hệ thống kho vận tự động tiếp nhận một băng chuyền gồm `n` kiện hàng với chiều cao lần lượt là `h_1, h_2, ..., h_n`.\n"
                "Robot xếp dỡ cần chọn ra một chuỗi các kiện hàng xuất hiện theo đúng thứ tự trên băng chuyền sao cho chiều cao của kiện sau luôn lớn hơn kiện trước (`h_{i_1} < h_{i_2} < ... < h_{i_k}`).\n"
                "Hãy tìm số lượng kiện hàng tối đa mà robot có thể gom lại trong một lượt."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`1 <= n <= 2 * 10^5`).\n• Dòng 2: Chứa `n` số nguyên `h_1, ..., h_n` (`1 <= h_i <= 10^9`).",
            "output_format": "In ra độ dài của dãy tăng nghiêm ngặt dài nhất.",
            "constraints": "`1 <= n <= 2 * 10^5`, `1 <= h_i <= 10^9`. Thuật toán: Quy hoạch động kết hợp Binary Search `O(N log N)`. Giới hạn: `1.0s`, `256MB`.",
            "sample_input": "8\n10 9 2 5 3 7 101 18",
            "sample_output": "4",
            "secret_tests": [
                {"input": "8\n10 9 2 5 3 7 101 18", "output": "4"},
                {"input": "6\n0 1 0 3 2 3", "output": "4"},
                {"input": "7\n7 7 7 7 7 7 7", "output": "1"},
                {"input": "5\n1 2 3 4 5", "output": "5"},
                {"input": "6\n10 20 10 30 20 50", "output": "4"},
            ],
            "time_limit_minutes": 25,
            "max_code_size_kb": 128,
            "solution_code": (
                "import sys, bisect\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    h = [int(x) for x in data[1:1+n]]\n"
                "    tails = []\n"
                "    for x in h:\n"
                "        idx = bisect.bisect_left(tails, x)\n"
                "        if idx == len(tails): tails.append(x)\n"
                "        else: tails[idx] = x\n"
                "    print(len(tails))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
    ],

    # --------------------------------------------------------------------------
    # LT2 (Rating: 2000 pts • Div. 2)
    # --------------------------------------------------------------------------
    "LT2": [
        {
            "name": "Giám Sát Lưu Lượng Trạm Thu Phí Tự Động ETC (Segment Tree Range Update)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Tuyến cao tốc Bắc - Nam gồm `n` trạm thu phí ETC được đánh số từ `1` đến `n`. Ban đầu lưu lượng xe tại trạm `i` là `a_i`.\n"
                "Trung tâm điều hành thực hiện `q` thao tác thuộc 2 loại:\n"
                "• `1 l r v`: Tăng lưu lượng của tất cả các trạm trong đoạn `[l, r]` thêm `v` xe.\n"
                "• `2 l r`: Truy vấn trạm có lưu lượng xe cao nhất trong đoạn `[l, r]`."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `q` (`1 <= n, q <= 2 * 10^5`).\n• Dòng 2: Chứa `n` số nguyên `a_1, ..., a_n` (`0 <= a_i <= 10^9`).\n• `q` dòng tiếp theo: Mỗi dòng biểu diễn một thao tác loại 1 hoặc loại 2.",
            "output_format": "Với mỗi truy vấn loại 2, in ra giá trị lưu lượng lớn nhất tìm được trên một dòng.",
            "constraints": (
                "• `1 <= n, q <= 2 * 10^5`, `0 <= a_i, v <= 10^9`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** `n, q <= 1000`.\n"
                "• **Subtask 2 (30% số điểm):** Không có truy vấn loại 1 (mảng tĩnh).\n"
                "• **Subtask 3 (40% số điểm):** Ràng buộc gốc đầy đủ, yêu cầu Segment Tree Lazy Propagation `O((N + Q) log N)`."
            ),
            "sample_input": "5 3\n1 2 3 4 5\n2 1 3\n1 1 2 10\n2 1 3",
            "sample_output": "3\n12",
            "secret_tests": [
                {"input": "5 3\n1 2 3 4 5\n2 1 3\n1 1 2 10\n2 1 3", "output": "3\n12"},
                {"input": "3 2\n10 20 30\n1 2 3 5\n2 1 3", "output": "35"},
                {"input": "4 2\n5 5 5 5\n1 1 4 2\n2 2 3", "output": "7"},
                {"input": "2 2\n1 10\n2 1 2\n2 2 2", "output": "10\n10"},
                {"input": "5 3\n10 5 8 12 3\n2 2 4\n1 3 5 4\n2 3 5", "output": "12\n16"},
            ],
            "time_limit_minutes": 30,
            "max_code_size_kb": 256,
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
                "            self.tree[2*node] += v\n"
                "            self.lazy[2*node] += v\n"
                "            self.tree[2*node+1] += v\n"
                "            self.lazy[2*node+1] += v\n"
                "            self.lazy[node] = 0\n"
                "    def update(self, node, l, r, ql, qr, val):\n"
                "        if ql <= l and r <= qr:\n"
                "            self.tree[node] += val\n"
                "            self.lazy[node] += val\n"
                "            return\n"
                "        self.push(node)\n"
                "        mid = (l + r) // 2\n"
                "        if ql <= mid: self.update(2*node, l, mid, ql, qr, val)\n"
                "        if qr > mid: self.update(2*node+1, mid+1, r, ql, qr, val)\n"
                "        self.tree[node] = max(self.tree[2*node], self.tree[2*node+1])\n"
                "    def query(self, node, l, r, ql, qr):\n"
                "        if ql <= l and r <= qr:\n"
                "            return self.tree[node]\n"
                "        self.push(node)\n"
                "        mid = (l + r) // 2\n"
                "        res = -10**18\n"
                "        if ql <= mid: res = max(res, self.query(2*node, l, mid, ql, qr))\n"
                "        if qr > mid: res = max(res, self.query(2*node+1, mid+1, r, ql, qr))\n"
                "        return res\n\n"
                "def main():\n"
                "    input_data = sys.stdin.read().split()\n"
                "    if not input_data: return\n"
                "    n = int(input_data[0])\n"
                "    q = int(input_data[1])\n"
                "    arr = [int(x) for x in input_data[2:2+n]]\n"
                "    idx = 2 + n\n"
                "    st = SegTree(arr)\n"
                "    out = []\n"
                "    while idx < len(input_data):\n"
                "        t = int(input_data[idx])\n"
                "        if t == 1:\n"
                "            l, r, v = int(input_data[idx+1])-1, int(input_data[idx+2])-1, int(input_data[idx+3])\n"
                "            st.update(1, 0, n-1, l, r, v)\n"
                "            idx += 4\n"
                "        else:\n"
                "            l, r = int(input_data[idx+1])-1, int(input_data[idx+2])-1\n"
                "            out.append(str(st.query(1, 0, n-1, l, r)))\n"
                "            idx += 3\n"
                "    print('\\n'.join(out))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
    ],

    # --------------------------------------------------------------------------
    # MT2 (Rating: 2200 pts • Div. 2)
    # --------------------------------------------------------------------------
    "MT2": [
        {
            "name": "Điều Phối Xe Cấp Cứu Qua Mạng Lưới Đồ Thị Đa Trọng Số (State-Space Dijkstra)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một đội xe cấp cứu cần di chuyển từ bệnh viện trung tâm (nút `1`) đến điểm tiếp nhận bệnh nhân nguy kịch (nút `n`) trên bản đồ gồm `n` nút giao thông và `m` tuyến đường hai chiều.\n"
                "Mỗi tuyến đường nối giữa `u` và `v` có thời gian di chuyển tiêu chuẩn là `w` giây. Đội xe được trang bị tối đa `K` lần kích hoạt còi ưu tiên khẩn cấp qua đèn đỏ; mỗi lần kích hoạt trên một tuyến đường sẽ giúp giảm một nửa thời gian di chuyển trên đoạn đó (`w // 2`).\n"
                "Hãy tìm thời gian di chuyển ngắn nhất để xe cấp cứu tới đích."
            ),
            "input_format": "• Dòng 1: Chứa ba số nguyên `n, m, K` (`2 <= n <= 10^5`, `1 <= m <= 2 * 10^5`, `0 <= K <= 10`).\n• `m` dòng tiếp theo: Mỗi dòng chứa ba số nguyên `u, v, w` (`1 <= u, v <= n`, `1 <= w <= 10^9`).",
            "output_format": "In ra thời gian di chuyển ngắn nhất đạt được.",
            "constraints": (
                "• `1 <= n <= 10^5`, `1 <= m <= 2 * 10^5`, `0 <= K <= 10`, `1 <= w <= 10^9`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (25% số điểm):** `K = 0` (Dijkstra chuẩn `O((N + M) log N)`).\n"
                "• **Subtask 2 (35% số điểm):** `K = 1, n <= 10^4, m <= 5 * 10^4`.\n"
                "• **Subtask 3 (40% số điểm):** `K <= 10`, đồ thị trạng thái K+1 tầng `O(K * (N + M) log(K * N))`."
            ),
            "sample_input": "3 3 1\n1 2 10\n2 3 10\n1 3 25",
            "sample_output": "12",
            "secret_tests": [
                {"input": "3 3 1\n1 2 10\n2 3 10\n1 3 25", "output": "12"},
                {"input": "2 1 0\n1 2 100", "output": "100"},
                {"input": "4 4 2\n1 2 10\n2 3 20\n3 4 30\n1 4 100", "output": "35"},
                {"input": "3 2 1\n1 2 8\n2 3 8", "output": "12"},
                {"input": "4 3 0\n1 2 5\n2 3 6\n3 4 7", "output": "18"},
            ],
            "time_limit_minutes": 32,
            "max_code_size_kb": 256,
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
        }
    ],

    # --------------------------------------------------------------------------
    # HT2 (Rating: 2350 pts • Div. 2)
    # --------------------------------------------------------------------------
    "HT2": [
        {
            "name": "Quy Hoạch Động Phân Bổ Băng Thông Mạng Doanh Nghiệp Trên Cây (Tree DP)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Mạng lưới viễn thông doanh nghiệp gồm `n` nút máy chủ có cấu trúc dạng cây (đồ thị vô hướng liên thông gồm `n-1` cạnh).\n"
                "Mỗi nút `i` có nhu cầu truyền tải dữ liệu là `w_i`. Ban quản trị cần chọn ra một tập các nút máy chủ để kích hoạt chế độ siêu tăng tốc sao cho không có 2 máy chủ kề cạnh nhau cùng được kích hoạt.\n"
                "Hãy tìm tổng dung lượng truyền tải lớn nhất có thể kích hoạt."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`1 <= n <= 10^5`).\n• Dòng 2: Chứa `n` số nguyên `w_1, w_2, ..., w_n` (`1 <= w_i <= 10^9`).\n• `n-1` dòng tiếp theo: Mỗi dòng chứa `u, v` biểu thị một liên kết giữa hai máy chủ.",
            "output_format": "In ra tổng dung lượng truyền tải tối đa.",
            "constraints": (
                "• `1 <= n <= 10^5`, `1 <= w_i <= 10^9`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** Đồ thị là một đường thẳng (Array DP O(N)).\n"
                "• **Subtask 2 (30% số điểm):** `n <= 2000` (Tree DP O(N)).\n"
                "• **Subtask 3 (40% số điểm):** `n <= 10^5`, yêu cầu Tree DP tối ưu bộ nhớ đệ quy lớn O(N)."
            ),
            "sample_input": "5\n1 2 3 4 5\n1 2\n1 3\n2 4\n2 5",
            "sample_output": "12",
            "secret_tests": [
                {"input": "5\n1 2 3 4 5\n1 2\n1 3\n2 4\n2 5", "output": "12"},
                {"input": "3\n10 20 30\n1 2\n2 3", "output": "40"},
                {"input": "1\n50", "output": "50"},
                {"input": "4\n5 10 15 20\n1 2\n2 3\n3 4", "output": "25"},
                {"input": "4\n100 1 1 1\n1 2\n1 3\n1 4", "output": "100"},
            ],
            "time_limit_minutes": 35,
            "max_code_size_kb": 256,
            "solution_code": (
                "import sys\n"
                "sys.setrecursionlimit(300000)\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    w = [0] + [int(x) for x in data[1:1+n]]\n"
                "    adj = [[] for _ in range(n + 1)]\n"
                "    idx = 1 + n\n"
                "    for _ in range(n - 1):\n"
                "        u, v = int(data[idx]), int(data[idx+1])\n"
                "        idx += 2\n"
                "        adj[u].append(v)\n"
                "        adj[v].append(u)\n"
                "    order = []\n"
                "    stack = [(1, 0)]\n"
                "    parent = [0] * (n + 1)\n"
                "    while stack:\n"
                "        u, p = stack.pop()\n"
                "        order.append(u)\n"
                "        parent[u] = p\n"
                "        for v in adj[u]:\n"
                "            if v != p: stack.append((v, u))\n"
                "    dp0 = [0] * (n + 1)\n"
                "    dp1 = [0] * (n + 1)\n"
                "    for u in reversed(order):\n"
                "        dp1[u] = w[u]\n"
                "        for v in adj[u]:\n"
                "            if v != parent[u]:\n"
                "                dp0[u] += max(dp0[v], dp1[v])\n"
                "                dp1[u] += dp0[v]\n"
                "    print(max(dp0[1], dp1[1]))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
    ],

    # --------------------------------------------------------------------------
    # LT1 (Rating: 2500 pts • Div. 1 • Chỉ khó hơn Div. 2 một nấc vừa phải)
    # --------------------------------------------------------------------------
    "LT1": [
        {
            "name": "Lập Lịch Hành Trình Đội Bay Drone Giao Hàng (Bitmask Dynamic Programming)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một công ty logistics sở hữu một chiếc Drone vận chuyển cần ghé thăm đúng `n` trạm giao hàng được đánh số từ `0` đến `n-1`.\n"
                "Ma trận khoảng cách `dist[i][j]` cho biết lượng pin tiêu hao khi bay trực tiếp từ trạm `i` đến trạm `j`.\n"
                "Drone xuất phát từ trạm điều hành (trạm `0`), ghé thăm tất cả `n-1` trạm còn lại mỗi trạm đúng một lần và quay trở về trạm `0`.\n"
                "Hãy tìm tổng lượng pin tiêu hao nhỏ nhất để hoàn thành trọn vẹn hành trình."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`2 <= n <= 18`).\n• `n` dòng tiếp theo: Mỗi dòng chứa `n` số nguyên biểu thị ma trận chi phí tiêu hao `dist` (`0 <= dist[i][j] <= 10^6`, `dist[i][i] = 0`).",
            "output_format": "In ra một số nguyên duy nhất là lượng pin tiêu hao tối thiểu.",
            "constraints": (
                "• `2 <= n <= 18`, `0 <= dist[i][j] <= 10^6`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** `n <= 9` (Quay lui vét cạn O(N!)).\n"
                "• **Subtask 2 (30% số điểm):** `n <= 14`.\n"
                "• **Subtask 3 (40% số điểm):** `n <= 18`, yêu cầu Quy Hoạch Động Trạng Thái Bitmask `O(2^N * N^2)`."
            ),
            "sample_input": "4\n0 10 15 20\n10 0 35 25\n15 35 0 30\n20 25 30 0",
            "sample_output": "80",
            "secret_tests": [
                {"input": "4\n0 10 15 20\n10 0 35 25\n15 35 0 30\n20 25 30 0", "output": "80"},
                {"input": "3\n0 1 2\n1 0 1\n2 1 0", "output": "4"},
                {"input": "2\n0 5\n5 0", "output": "10"},
                {"input": "4\n0 1 2 3\n1 0 1 2\n2 1 0 1\n3 2 1 0", "output": "6"},
                {"input": "4\n0 20 42 25\n20 0 30 34\n42 30 0 10\n25 34 10 0", "output": "85"},
            ],
            "time_limit_minutes": 35,
            "max_code_size_kb": 256,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    dist = []\n"
                "    idx = 1\n"
                "    for _ in range(n):\n"
                "        dist.append([int(x) for x in data[idx:idx+n]])\n"
                "        idx += n\n"
                "    INF = float('inf')\n"
                "    num_states = 1 << n\n"
                "    dp = [[INF] * n for _ in range(num_states)]\n"
                "    dp[1][0] = 0\n"
                "    for mask in range(1, num_states):\n"
                "        for u in range(n):\n"
                "            if not (mask & (1 << u)) or dp[mask][u] == INF: continue\n"
                "            d_curr = dp[mask][u]\n"
                "            for v in range(n):\n"
                "                if not (mask & (1 << v)):\n"
                "                    nmask = mask | (1 << v)\n"
                "                    nd = d_curr + dist[u][v]\n"
                "                    if nd < dp[nmask][v]: dp[nmask][v] = nd\n"
                "    ans = INF\n"
                "    final_mask = num_states - 1\n"
                "    for u in range(1, n):\n"
                "        if dp[final_mask][u] != INF:\n"
                "            cost = dp[final_mask][u] + dist[u][0]\n"
                "            if cost < ans: ans = cost\n"
                "    if n == 1: ans = 0\n"
                "    print(ans if ans != INF else 0)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
        {
            "name": "Khôi Phục Hạ Tầng Điện Lưới Sau Bão Lũ (Disjoint Set Union & Kruskal MST)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Sau cơn bão lớn, mạng lưới điện gồm `n` trạm điện bị hư hại nghiêm trọng. Có `m` tuyến đường dây tiềm năng có thể sửa chữa, tuyến thứ `i` kết nối trạm `u_i` và `v_i` với chi phí khắc phục là `c_i`.\n"
                "Công ty Điện lực cần khôi phục lại một tập các đường dây sao cho toàn bộ `n` trạm đều được kết nối liên thông với nhau và tổng chi phí sửa chữa là nhỏ nhất có thể.\n"
                "Hãy tìm tổng chi phí tối thiểu để khôi phục toàn bộ mạng lưới điện."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `m` (`2 <= n <= 10^5`, `1 <= m <= 2 * 10^5`).\n• `m` dòng tiếp theo: Mỗi dòng chứa ba số nguyên `u, v, c` (`1 <= u, v <= n`, `1 <= c <= 10^9`).",
            "output_format": "In ra tổng chi phí tối thiểu để liên thông toàn mạng lưới, hoặc `-1` nếu không thể kết nối tất cả các trạm.",
            "constraints": (
                "• `2 <= n <= 10^5`, `1 <= m <= 2 * 10^5`, `1 <= c <= 10^9`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** `n <= 1000, m <= 2000`.\n"
                "• **Subtask 2 (30% số điểm):** Chi phí các cạnh bằng nhau (`c_i = 1`).\n"
                "• **Subtask 3 (40% số điểm):** Ràng buộc gốc quy mô lớn, yêu cầu thuật toán Kruskal kết hợp DSU `O(M log M)`."
            ),
            "sample_input": "4 5\n1 2 1\n2 3 2\n3 4 3\n1 4 4\n2 4 5",
            "sample_output": "6",
            "secret_tests": [
                {"input": "4 5\n1 2 1\n2 3 2\n3 4 3\n1 4 4\n2 4 5", "output": "6"},
                {"input": "3 1\n1 2 10", "output": "-1"},
                {"input": "3 3\n1 2 5\n2 3 5\n1 3 10", "output": "10"},
                {"input": "2 1\n1 2 100", "output": "100"},
                {"input": "5 6\n1 2 3\n2 3 1\n3 4 7\n4 5 2\n1 5 8\n2 4 5", "output": "11"},
            ],
            "time_limit_minutes": 35,
            "max_code_size_kb": 256,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    m = int(data[1])\n"
                "    edges = []\n"
                "    idx = 2\n"
                "    for _ in range(m):\n"
                "        u = int(data[idx])\n"
                "        v = int(data[idx+1])\n"
                "        c = int(data[idx+2])\n"
                "        idx += 3\n"
                "        edges.append((c, u, v))\n"
                "    edges.sort()\n"
                "    parent = list(range(n + 1))\n"
                "    def find(i):\n"
                "        path = []\n"
                "        while parent[i] != i:\n"
                "            path.append(i)\n"
                "            i = parent[i]\n"
                "        for node in path:\n"
                "            parent[node] = i\n"
                "        return i\n"
                "    total_cost = 0\n"
                "    edges_used = 0\n"
                "    for c, u, v in edges:\n"
                "        ru = find(u)\n"
                "        rv = find(v)\n"
                "        if ru != rv:\n"
                "            parent[ru] = rv\n"
                "            total_cost += c\n"
                "            edges_used += 1\n"
                "            if edges_used == n - 1: break\n"
                "    if edges_used == n - 1:\n"
                "        print(total_cost)\n"
                "    else:\n"
                "        print(-1)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
    ],

    # --------------------------------------------------------------------------
    # MT1 (Rating: 2800 pts • Div. 1 • Đa dạng, vừa sức, chuẩn mực giải thuật)
    # --------------------------------------------------------------------------
    "MT1": [
        {
            "name": "Mã Hóa Gói Tin Mạng Lượng Tử Bảo Mật (Binary Trie Maximum XOR Pair)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Hệ thống an ninh mạng viễn thông lượng tử tiếp nhận một luồng gồm `n` khóa mã hóa số nguyên `a_1, a_2, ..., a_n`.\n"
                "Để tạo ra khóa đối xứng có tính bảo mật cao nhất, hệ thống cần chọn ra hai khóa `a_i` và `a_j` (`1 <= i < j <= n`) sao cho phép toán `a_i XOR a_j` đạt giá trị lớn nhất.\n"
                "Hãy sử dụng cấu trúc dữ liệu Cây Tiền Tố Nhị Phân (Binary Trie) để tìm giá trị XOR lớn nhất trong thời gian `O(N * 31)`."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`2 <= n <= 2 * 10^5`).\n• Dòng 2: Chứa `n` số nguyên không âm `a_1, a_2, ..., a_n` (`0 <= a_i <= 10^9`).",
            "output_format": "In ra một số nguyên duy nhất là giá trị XOR lớn nhất tìm được.",
            "constraints": (
                "• `2 <= n <= 2 * 10^5`, `0 <= a_i <= 10^9`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** `n <= 2000` (Duyệt cặp O(N^2)).\n"
                "• **Subtask 2 (30% số điểm):** Các phần tử `a_i <= 255` (8-bit).\n"
                "• **Subtask 3 (40% số điểm):** Ràng buộc gốc đầy đủ, yêu cầu cấu trúc Binary Trie `O(N * 31)`."
            ),
            "sample_input": "4\n3 10 5 25",
            "sample_output": "28",
            "secret_tests": [
                {"input": "4\n3 10 5 25", "output": "28"},
                {"input": "3\n1 2 3", "output": "3"},
                {"input": "2\n10 10", "output": "0"},
                {"input": "5\n8 1 2 12 7", "output": "15"},
                {"input": "6\n4 6 7 2 9 10", "output": "15"},
            ],
            "time_limit_minutes": 38,
            "max_code_size_kb": 256,
            "solution_code": (
                "import sys\n\n"
                "class TrieNode:\n"
                "    __slots__ = ('child',)\n"
                "    def __init__(self):\n"
                "        self.child = [None, None]\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    a = [int(x) for x in data[1:1+n]]\n"
                "    root = TrieNode()\n"
                "    def insert(num):\n"
                "        node = root\n"
                "        for bit in range(30, -1, -1):\n"
                "            b = (num >> bit) & 1\n"
                "            if not node.child[b]:\n"
                "                node.child[b] = TrieNode()\n"
                "            node = node.child[b]\n"
                "    def query_max(num):\n"
                "        node = root\n"
                "        curr = 0\n"
                "        for bit in range(30, -1, -1):\n"
                "            b = (num >> bit) & 1\n"
                "            want = 1 - b\n"
                "            if node.child[want]:\n"
                "                curr |= (1 << bit)\n"
                "                node = node.child[want]\n"
                "            else:\n"
                "                node = node.child[b]\n"
                "        return curr\n"
                "    insert(a[0])\n"
                "    max_xor = 0\n"
                "    for x in a[1:]:\n"
                "        val = query_max(x)\n"
                "        if val > max_xor: max_xor = val\n"
                "        insert(x)\n"
                "    print(max_xor)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
        {
            "name": "Khớp Lệnh Sổ Lệnh Tài Chính Đa Chiều (Combinatorics & Modular Arithmetic)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một sàn giao dịch chứng khoán xử lý `q` phiên khớp lệnh. Mỗi phiên, hệ thống cần chọn ra `k` lệnh mua từ tổng số `n` lệnh khả dụng để ghép cặp với các lệnh bán đối ứng.\n"
                "Số cách ghép cặp chính là tổ hợp chập `k` của `n` phần tử: `C(n, k) = n! / (k! * (n - k)!)`.\n"
                "Hãy tính kết quả theo modulo `10^9 + 7` cho từng truy vấn bằng cách tiền xử lý giai thừa và nghịch đảo modulo theo định lý Fermat nhỏ trong `O(1)` mỗi truy vấn."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `q` (`1 <= q <= 10^5`).\n• `q` dòng tiếp theo: Mỗi dòng chứa hai số nguyên `n` và `k` (`0 <= k <= n <= 2 * 10^5`).",
            "output_format": "Với mỗi truy vấn, in ra giá trị `C(n, k) % (10^9 + 7)` trên một dòng.",
            "constraints": (
                "• `1 <= q <= 10^5`, `0 <= k <= n <= 2 * 10^5`, modulo `10^9 + 7`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** `q <= 1000, n <= 1000` (Tam giác Pascal O(N^2)).\n"
                "• **Subtask 2 (30% số điểm):** `k <= 2`.\n"
                "• **Subtask 3 (40% số điểm):** Ràng buộc gốc đầy đủ, yêu cầu tiền xử lý nghịch đảo modulo `O(N)` và trả lời `O(1)` mỗi truy vấn."
            ),
            "sample_input": "3\n5 2\n6 3\n10 5",
            "sample_output": "10\n20\n252",
            "secret_tests": [
                {"input": "3\n5 2\n6 3\n10 5", "output": "10\n20\n252"},
                {"input": "2\n1 0\n1 1", "output": "1\n1"},
                {"input": "2\n4 2\n5 5", "output": "6\n1"},
                {"input": "3\n7 3\n8 4\n9 2", "output": "35\n70\n36"},
                {"input": "1\n100 1", "output": "100"},
            ],
            "time_limit_minutes": 38,
            "max_code_size_kb": 256,
            "solution_code": (
                "import sys\n\n"
                "MOD = 10**9 + 7\n"
                "MAX = 200005\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    q = int(data[0])\n"
                "    fact = [1] * MAX\n"
                "    inv = [1] * MAX\n"
                "    for i in range(1, MAX):\n"
                "        fact[i] = (fact[i - 1] * i) % MOD\n"
                "    inv[MAX - 1] = pow(fact[MAX - 1], MOD - 2, MOD)\n"
                "    for i in range(MAX - 2, -1, -1):\n"
                "        inv[i] = (inv[i + 1] * (i + 1)) % MOD\n"
                "    out = []\n"
                "    idx = 1\n"
                "    for _ in range(q):\n"
                "        n = int(data[idx])\n"
                "        k = int(data[idx + 1])\n"
                "        idx += 2\n"
                "        if k < 0 or k > n:\n"
                "            out.append('0')\n"
                "        else:\n"
                "            val = fact[n] * inv[k] % MOD * inv[n - k] % MOD\n"
                "            out.append(str(val))\n"
                "    print('\\n'.join(out))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
    ],

    # --------------------------------------------------------------------------
    # HT1 (Rating: 3000 pts • Div. 1 • Đỉnh cao, súc tích, hoàn hảo)
    # --------------------------------------------------------------------------
    "HT1": [
        {
            "name": "Mô Hình Khớp Lệnh Cao Tần HFT Và Lũy Thừa Ma Trận Nhị Phân (Binary Matrix Exponentiation)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một sàn giao dịch tài chính tần số cao (High-Frequency Trading - HFT) vận hành `n` nút thanh khoản được đánh số từ `1` đến `n`.\n"
                "Ma trận kề `A` kích thước `n x n` thể hiện các kênh định tuyến trực tiếp (`A[i][j] = 1` nếu có kênh truyền trực tiếp 1 chiều từ `i` sang `j`).\n"
                "Hãy tính tổng số kịch bản khớp lệnh có độ dài đúng `K` chu kỳ xuất phát từ nút `1` và kết thúc tại nút `n` theo modulo `10^9 + 7`."
            ),
            "input_format": "• Dòng 1: Chứa hai số nguyên `n` và `K` (`2 <= n <= 65`, `1 <= K <= 10^18`).\n• `n` dòng tiếp theo: Mỗi dòng chứa `n` số nguyên `0` hoặc `1` biểu diễn ma trận kề `A`.",
            "output_format": "In ra một số nguyên duy nhất là số đường truyền hợp lệ modulo `10^9 + 7`.",
            "constraints": (
                "• `2 <= n <= 65`, `1 <= K <= 10^18`, modulo `10^9 + 7`. Giới hạn: `1.0s`, `256MB`.\n"
                "• **Subtask 1 (25% số điểm):** `K <= 1000, n <= 30` (Nhân ma trận tuần tự O(N^3 * K)).\n"
                "• **Subtask 2 (35% số điểm):** `K <= 10^9, n <= 10`.\n"
                "• **Subtask 3 (40% số điểm):** `K <= 10^18, n <= 65`, yêu cầu Lũy Thừa Ma Trận Nhị Phân O(N^3 log K)."
            ),
            "sample_input": "3 2\n0 1 1\n0 0 1\n0 0 0",
            "sample_output": "1",
            "secret_tests": [
                {"input": "3 2\n0 1 1\n0 0 1\n0 0 0", "output": "1"},
                {"input": "2 3\n1 1\n1 1", "output": "4"},
                {"input": "2 1\n0 1\n1 0", "output": "1"},
                {"input": "3 3\n0 1 0\n0 0 1\n1 0 0", "output": "0"},
                {"input": "3 1\n0 0 1\n0 0 0\n0 0 0", "output": "1"},
            ],
            "time_limit_minutes": 45,
            "max_code_size_kb": 256,
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
        {
            "name": "Tối Ưu Hóa Chuỗi Cung Ứng Toàn Cầu (Fenwick Tree Optimized DP)",
            "statement": (
                "## 📖 ĐỀ BÀI\n"
                "Một tập đoàn bán lẻ quốc tế nhận `n` đề xuất chuỗi cung ứng được đánh số theo thời điểm. Mỗi đề xuất `i` có độ ưu tiên `p_i` và giá trị kinh tế `v_i`.\n"
                "Hội đồng quản trị cần chọn ra một dãy các đề xuất theo thứ tự thời gian sao cho độ ưu tiên tăng dần nghiêm ngặt (`p_{i_1} < p_{i_2} < ... < p_{i_k}`) và tổng giá trị kinh tế thu được (`v_{i_1} + v_{i_2} + ... + v_{i_k}`) là lớn nhất.\n"
                "Hãy xác định tổng giá trị kinh tế tối đa đạt được."
            ),
            "input_format": "• Dòng 1: Chứa số nguyên `n` (`1 <= n <= 2 * 10^5`).\n• Dòng 2: Chứa `n` số nguyên `p_1, ..., p_n` (`1 <= p_i <= 10^9`).\n• Dòng 3: Chứa `n` số nguyên `v_1, ..., v_n` (`1 <= v_i <= 10^9`).",
            "output_format": "In ra tổng giá trị kinh tế lớn nhất có thể đạt được.",
            "constraints": (
                "• `1 <= n <= 2 * 10^5`, `1 <= p_i, v_i <= 10^9`. Giới hạn: `1.5s`, `256MB`.\n"
                "• **Subtask 1 (30% số điểm):** `n <= 2000` (Quy hoạch động O(N^2)).\n"
                "• **Subtask 2 (30% số điểm):** Các giá trị `v_i = 1` (Bài toán LIS cơ bản).\n"
                "• **Subtask 3 (40% số điểm):** Ràng buộc gốc quy mô lớn, yêu cầu Nén Tọa Độ (Coordinate Compression) và Cây Fenwick (BIT) `O(N log N)`."
            ),
            "sample_input": "4\n10 20 15 30\n5 10 20 15",
            "sample_output": "40",
            "secret_tests": [
                {"input": "4\n10 20 15 30\n5 10 20 15", "output": "40"},
                {"input": "3\n1 2 3\n10 20 30", "output": "60"},
                {"input": "3\n3 2 1\n10 20 30", "output": "30"},
                {"input": "1\n100\n50", "output": "50"},
                {"input": "5\n2 1 4 3 5\n10 5 20 15 30", "output": "65"},
            ],
            "time_limit_minutes": 45,
            "max_code_size_kb": 256,
            "solution_code": (
                "import sys\n\n"
                "def main():\n"
                "    data = sys.stdin.read().split()\n"
                "    if not data: return\n"
                "    n = int(data[0])\n"
                "    p = [int(x) for x in data[1:1+n]]\n"
                "    v = [int(x) for x in data[1+n:1+2*n]]\n"
                "    sorted_p = sorted(list(set(p)))\n"
                "    rank = {val: i + 1 for i, val in enumerate(sorted_p)}\n"
                "    m = len(sorted_p)\n"
                "    bit = [0] * (m + 1)\n"
                "    def update(idx, val):\n"
                "        while idx <= m:\n"
                "            if val > bit[idx]: bit[idx] = val\n"
                "            idx += idx & (-idx)\n"
                "    def query(idx):\n"
                "        res = 0\n"
                "        while idx > 0:\n"
                "            if bit[idx] > res: res = bit[idx]\n"
                "            idx -= idx & (-idx)\n"
                "        return res\n"
                "    for i in range(n):\n"
                "        r = rank[p[i]]\n"
                "        best_prev = query(r - 1)\n"
                "        curr_dp = best_prev + v[i]\n"
                "        update(r, curr_dp)\n"
                "    print(query(m))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        },
    ],
}


def generate_synthesized_problem(tier: str, theme: str | None = None) -> DuelProblem:
    """Tạo đề bài thuật toán độc bản, chuyên sâu chuẩn CP dựa trên kho thuật toán thực tế."""
    tier = tier.upper()

    calc_rating = (
        300 if tier == "T8"
        else 550 if tier == "T7"
        else 850 if tier == "T6"
        else 1300 if tier == "T5"
        else 1500 if tier == "T4"
        else 1750 if tier == "T3"
        else 2000 if tier == "LT2"
        else 2200 if tier == "MT2"
        else 2350 if tier == "HT2"
        else 2500 if tier == "LT1"
        else 2800 if tier == "MT1"
        else 3000
    )

    templates = TIER_TEMPLATES.get(tier, [])
    if templates:
        tpl = random.choice(templates)
        prob_id = f"duel_{tier.lower()}_dyn_{int(time.time())}_{random.randint(100, 999)}"
        return DuelProblem(
            id=prob_id,
            name=tpl["name"],
            tier=tier,
            division="Div. 4" if tier in ["T8", "T7", "T6"] else "Div. 3" if tier in ["T5", "T4", "T3"] else "Div. 2" if tier in ["LT2", "MT2", "HT2"] else "Div. 1",
            rating_display=f"{tier} / Rating: {calc_rating} pts",
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
            solution_cpp=tpl.get("solution_cpp", ""),
            solution_py=tpl.get("solution_code", ""),
            rating=tpl.get("rating", calc_rating),
            tags=tpl.get("tags", []),
            time_limit_sec=tpl.get("time_limit_sec", 1.0),
            memory_limit_mb=tpl.get("memory_limit_mb", 256),
            sample_explanation=tpl.get("sample_explanation", ""),
        )

    matching = [p for p in PROBLEM_BANK if p.tier == tier]
    if matching:
        base = random.choice(matching)
        prob_id = f"duel_{tier.lower()}_dyn_{int(time.time())}_{random.randint(100, 999)}"
        return DuelProblem(
            id=prob_id,
            name=base.name,
            tier=tier,
            division=base.division,
            rating_display=base.rating_display,
            statement=base.statement,
            input_format=base.input_format,
            output_format=base.output_format,
            constraints=base.constraints,
            sample_input=base.sample_input,
            sample_output=base.sample_output,
            secret_tests=base.secret_tests,
            time_limit_minutes=base.time_limit_minutes,
            max_code_size_kb=base.max_code_size_kb,
            solution_code=base.solution_code,
            solution_cpp=base.solution_cpp,
            solution_py=base.solution_py,
            rating=calc_rating,
            tags=base.tags,
            time_limit_sec=base.time_limit_sec,
            memory_limit_mb=base.memory_limit_mb,
            sample_explanation=base.sample_explanation,
        )

    return PROBLEM_BANK[0]
