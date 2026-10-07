#!/usr/bin/env python3
"""
================================================================================
          CODEFORCES RATING & SCORING CALCULATION ENGINE (STANDALONE)
================================================================================
File giải quyết toàn diện và độc lập toàn bộ các thuật toán tính điểm:
1. CONTEST RATING ALGORITHM (Thuật toán chính thức của Codeforces):
   - Tính Seed (Hạng kỳ vọng theo Elo): Seed(R) = 1 + sum(1 / (1 + 10^((R - R_opp) / 400)))
   - Tính Hạng điều chỉnh mục tiêu: m = sqrt(Rank * Seed)
   - Tìm Performance Rating (R_perf) bằng Binary Search (Tìm kiếm nhị phân)
   - Tính Rating Delta: Delta = (R_perf - R_old) / 2
   - Hiệu chỉnh chống lạm phát điểm (Anti-Inflation Zero-Sum Shift)
   - Mô phỏng toàn bộ bảng điểm Contest nhiều thí sinh (Batch Contest Simulation)

2. PRACTICE / ARENA SCORING & RATING ALGORITHM (Luyện tập & Đấu trường Discord):
   - Tính Điểm Score tích lũy (Cộng khi Đúng, Trừ khi Sai theo độ khó bài tập)
   - Tính Điểm Rating Elo (Tỷ lệ thuận theo độ khó bài tập)
   - Hệ số Mode 1 (100% Codeforces) & Mode 2 (90% Discord Sandbox)
   - Hệ số Event Challenge (1.2x - 1.75x)
   - Cơ chế Bảo Vệ Tân Binh (Tân Binh Shield cho thí sinh dưới T4)
================================================================================
"""

import math
import sys
from dataclasses import dataclass
from typing import Any

# Cấu hình an toàn UTF-8 cho Terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ==============================================================================
# PHẦN 1: BẢNG 12 BẬC RANK ĐẤU TRƯỜNG
# ==============================================================================
@dataclass(frozen=True)
class RankTier:
    code: str
    name: str
    min_rating: int
    max_rating: int
    badge: str
    color_hex: int


RANK_TIERS = [
    RankTier("T8", "Tier 8 (Tân Binh)", 0, 1049, "⭐", 0x808080),
    RankTier("T7", "Tier 7 (Tập Sự)", 1050, 1199, "⭐", 0x008000),
    RankTier("T6", "Tier 6 (Thực Tập)", 1200, 1349, "⭐", 0x03A89E),
    RankTier("T5", "Tier 5 (Tiềm Năng)", 1350, 1499, "⭐", 0x0000FF),
    RankTier("T4", "Tier 4 (Chiến Binh)", 1500, 1699, "🔷", 0xAA00AA),
    RankTier("T3", "Tier 3 (Tinh Anh)", 1700, 1899, "🔷", 0xFF8C00),
    RankTier("T2", "Tier 2 (Cao Thủ)", 1900, 2099, "🔷", 0xFF0000),
    RankTier("T1", "Tier 1 (Đại Cao Thủ)", 2100, 2299, "🔷", 0xC00000),
    RankTier("MT2", "Mid Tier 2 (Kiện Tướng)", 2300, 2599, "⚜️", 0xFFD700),
    RankTier("MT1", "Mid Tier 1 (Đại Kiện Tướng)", 2600, 2999, "⚜️", 0xE5E4E2),
    RankTier("LT2", "Low Tier 2 (Huyền Thoại)", 3000, 3499, "🛡️", 0x00FFFF),
    RankTier("HT1", "High Tier 1 (Thần Thoại)", 3500, 99999, "👑", 0xFF1493),
]


def get_rank_by_rating(rating: int) -> RankTier:
    """Xác định bậc Rank dựa trên điểm Rating."""
    r = max(0, rating)
    for tier in RANK_TIERS:
        if tier.min_rating <= r <= tier.max_rating:
            return tier
    return RANK_TIERS[-1]


# ==============================================================================
# PHẦN 2: THUẬT TOÁN TÍNH RATING CONTEST CODEFORCES (OFFICIAL CONTEST ELO)
# ==============================================================================
class CodeforcesContestEngine:
    """
    Thuật toán tính toán Rating chính thức của các kỳ thi Codeforces:
    - Không dựa vào số bài giải được hay độ khó từng bài.
    - Dựa vào: Rating trước kỳ thi của bạn, Thứ hạng (Rank) thực tế, và Rating của tất cả đối thủ.
    """

    @staticmethod
    def get_win_probability(ra: float, rb: float) -> float:
        """
        Xác suất thí sinh A (Rating ra) thắng thí sinh B (Rating rb):
        P(A > B) = 1 / (1 + 10^((rb - ra) / 400))
        """
        diff = (rb - ra) / 400.0
        diff = max(-10.0, min(10.0, diff))
        return 1.0 / (1.0 + math.pow(10.0, diff))

    @classmethod
    def calculate_seed(cls, rating: float, opponent_ratings: list[int]) -> float:
        """
        Tính Thứ hạng kỳ vọng (Seed) của một người có mức Rating 'rating' khi đấu với các đối thủ:
        Seed(R) = 1 + sum(P(Opponent > User))
        """
        seed = 1.0
        for opp in opponent_ratings:
            seed += cls.get_win_probability(float(opp), rating)
        return seed

    @classmethod
    def calculate_performance(
        cls,
        actual_rank: int,
        opponent_ratings: list[int],
        current_user_rating: int | None = None,
    ) -> float:
        """
        Tìm mức Rating phong độ (Performance Rating R_perf) bằng Binary Search (Tìm kiếm nhị phân):
        - Tính Target Rank m = sqrt(actual_rank * Seed(current_user_rating))
        - Tìm R_perf sao cho Seed(R_perf) = m.
        """
        if not opponent_ratings:
            return float(current_user_rating or 1400)

        # Tính Target Rank m theo trung bình nhân Codeforces
        if current_user_rating is not None:
            user_seed = cls.calculate_seed(float(current_user_rating), opponent_ratings)
            target_rank = math.sqrt(float(actual_rank) * user_seed)
        else:
            target_rank = float(actual_rank)

        low = 0.0
        high = 4500.0

        for _ in range(60):  # 60 vòng lặp cho độ chính xác cực cao
            mid = (low + high) / 2.0
            seed = cls.calculate_seed(mid, opponent_ratings)
            if seed > target_rank:
                low = mid
            else:
                high = mid

        return round((low + high) / 2.0, 1)

    @classmethod
    def calculate_single_contest_result(
        cls,
        user_rating: int,
        actual_rank: int,
        total_participants: int,
        opponent_ratings: list[int] | None = None,
        avg_opponent_rating: int | None = None,
    ) -> dict[str, Any]:
        """
        Tính toán chi tiết kết quả biến động Rating cho 1 thí sinh sau Contest.
        """
        total_p = max(2, total_participants)
        rank = max(1, min(total_p, actual_rank))
        u_r = max(0, user_rating)

        # Nếu không có danh sách chi tiết, tạo phân phối đối thủ chuẩn
        if not opponent_ratings:
            avg_r = avg_opponent_rating or max(1200, u_r)
            opponents = []
            for i in range(total_p - 1):
                spread = (i / max(1, total_p - 2) - 0.5) * 1200
                opp_r = int(max(400, min(3500, avg_r + spread)))
                opponents.append(opp_r)
        else:
            opponents = list(opponent_ratings)

        user_seed = cls.calculate_seed(float(u_r), opponents)
        target_rank = math.sqrt(float(rank) * user_seed)
        perf = cls.calculate_performance(rank, opponents, current_user_rating=u_r)

        raw_delta = (perf - float(u_r)) * 0.5
        delta = int(round(raw_delta))
        new_rating = max(0, u_r + delta)

        old_tier = get_rank_by_rating(u_r)
        new_tier = get_rank_by_rating(new_rating)

        return {
            "old_rating": u_r,
            "rank": rank,
            "total_participants": total_p,
            "seed": round(user_seed, 1),
            "target_rank": round(target_rank, 1),
            "performance": perf,
            "delta": delta,
            "new_rating": new_rating,
            "old_tier": old_tier,
            "new_tier": new_tier,
            "is_promoted": new_tier.min_rating > old_tier.min_rating,
            "is_demoted": new_tier.min_rating < old_tier.min_rating,
        }

    @classmethod
    def calculate_batch_contest(
        cls, participants: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Mô phỏng tính Rating cho TOÀN BỘ thí sinh trong một kỳ thi thực tế:
        Có áp dụng bước Anti-Inflation Zero-Sum Shift để bảo toàn tổng điểm hệ thống.
        Mỗi phần tử trong participants: {"name": str, "rating": int, "rank": int}
        """
        n = len(participants)
        if n <= 1:
            return participants

        all_ratings = [p["rating"] for p in participants]
        results = []

        # 1. Tính Delta ban đầu cho từng người
        deltas = []
        for i, p in enumerate(participants):
            opponents = all_ratings[:i] + all_ratings[i + 1 :]
            u_r = p["rating"]
            u_rank = p["rank"]

            user_seed = cls.calculate_seed(float(u_r), opponents)
            target_rank = math.sqrt(float(u_rank) * user_seed)
            perf = cls.calculate_performance(u_rank, opponents, current_user_rating=u_r)
            d = (perf - float(u_r)) * 0.5
            deltas.append(d)

        # 2. Hiệu chỉnh chống lạm phát điểm (Zero-sum adjustment)
        sum_delta = sum(deltas)
        inc = -sum_delta / n - 1.0

        for i, p in enumerate(participants):
            final_d = int(round(deltas[i] + inc))
            new_r = max(0, p["rating"] + final_d)
            results.append(
                {
                    "name": p.get("name", f"User #{i+1}"),
                    "old_rating": p["rating"],
                    "rank": p["rank"],
                    "delta": final_d,
                    "new_rating": new_r,
                    "old_rank": get_rank_by_rating(p["rating"]).name,
                    "new_rank": get_rank_by_rating(new_r).name,
                }
            )

        return results


# ==============================================================================
# PHẦN 3: THUẬT TOÁN TÍNH ĐIỂM LUYỆN TẬP & ĐẤU TRƯỜNG (ARENA PRACTICE SCORING)
# ==============================================================================
class ArenaScoringEngine:
    """
    Thuật toán tính điểm Score và biến động Rating khi luyện tập / thi đấu đơn lẻ:
    - Bài càng khó: Điểm cộng càng nhiều, Điểm phạt càng cao.
    - Bài càng dễ: Điểm cộng ít, Điểm phạt nhẹ.
    - Mode 1: 100% Điểm (Nộp trên web Codeforces).
    - Mode 2: 90% Điểm (Nộp trong Discord Sandbox).
    - Thưởng Event Challenge: 1.2x - 1.75x.
    - Bảo vệ tân binh (Tân Binh Shield cho người dưới Rank T4 khi thử sức bài Event).
    """

    MODE1_MULT = 1.00
    MODE2_MULT = 0.90

    @staticmethod
    def get_event_bonus(
        contest_name: str = "", problem_name: str = "", problem_rating: int = 1200
    ) -> tuple[bool, float, str]:
        """Xác định hệ số thưởng Event Challenge (1.2x - 1.75x)."""
        text = f"{contest_name} {problem_name}".lower()
        r = problem_rating or 1200

        if any(k in text for k in ["icpc", "huawei"]) or r >= 2400:
            return True, 1.75, "🔥 ICPC & Grand Challenge (1.75x)"
        elif any(k in text for k in ["global", "championship", "cup"]) or r >= 2100:
            return True, 1.50, "💎 Global Championship Event (1.50x)"
        elif any(k in text for k in ["pinely", "codeton", "special"]) or r >= 1800:
            return True, 1.35, "⚡ Special Round Challenge (1.35x)"
        elif r >= 2000:
            return True, 1.20, "🌟 Hot Community Event (1.20x)"
        return False, 1.00, ""

    @classmethod
    def calculate_score(
        cls,
        problem_rating: int,
        is_accepted: bool,
        is_mode1: bool = True,
        event_multiplier: float = 1.0,
    ) -> float:
        """
        Tính điểm Score tích lũy (Cộng khi Đúng, Trừ khi Sai theo độ khó bài):
        - Giải đúng: Base_Score * Mode_Mult * Event_Mult
        - Làm sai: - (Base_Score * 0.25 * Mode_Mult)
        """
        base_rating = max(800, min(3500, problem_rating or 1200))
        base_score = base_rating / 10.0
        mode_mult = cls.MODE1_MULT if is_mode1 else cls.MODE2_MULT

        if is_accepted:
            # Giải đúng -> Nhận điểm thưởng
            points = base_score * mode_mult * max(1.0, event_multiplier)
            return round(points, 1)
        else:
            # Làm sai -> Phạt 25% giá trị bài (Bài dễ phạt ít, bài khó phạt nhiều)
            penalty = base_score * 0.25 * mode_mult
            return -max(15.0, round(penalty, 1))

    @classmethod
    def calculate_rating_change(
        cls,
        user_rating: int,
        problem_rating: int,
        is_accepted: bool,
        is_mode1: bool = True,
        is_event: bool = False,
        event_multiplier: float = 1.0,
        tests_passed_ratio: float = 0.0,
    ) -> int:
        """
        Tính biến động Rating Elo trong Luyện tập / Đấu trường:
        - Khi Đúng: Tăng điểm theo xác suất kỳ vọng Elo (Bài khó tăng nhiều).
        - Khi Sai: Trừ điểm theo độ khó bài tập (Bài dễ trừ ít, bài khó trừ nhiều).
        - Bảo vệ tân binh: Rating < 1400 (Dưới T4) làm sai bài Event -> Delta = 0.
        """
        u_r = max(0, user_rating)
        p_r = max(800, min(3500, problem_rating or 1200))
        mode_factor = 1.0 if is_mode1 else 0.9

        if is_accepted:
            # Xác suất kỳ vọng giải đúng
            diff = (p_r - u_r) / 400.0
            diff = max(-10.0, min(10.0, diff))
            expected_prob = 1.0 / (1.0 + math.pow(10.0, diff))

            if u_r < 1200:
                k_factor = 60.0
            elif u_r < 2000:
                k_factor = 45.0
            else:
                k_factor = 35.0

            raw_delta = k_factor * (1.0 - expected_prob) * max(1.0, event_multiplier)
            delta = max(1, int(round(raw_delta * mode_factor)))
            return delta
        else:
            # Nếu là bài Event và user chưa đạt rank T4 (< 1400 rating): Miễn trừ điểm phạt!
            if is_event and u_r < 1400:
                return 0

            # Phạt tỷ lệ thuận theo độ khó bài
            difficulty_ratio = p_r / 2500.0
            raw_penalty = 50.0 * min(1.0, max(0.25, difficulty_ratio))

            if is_event:
                if tests_passed_ratio < 0.20:
                    raw_penalty *= 1.35
                elif tests_passed_ratio < 0.40:
                    raw_penalty *= 1.20
                else:
                    raw_penalty *= 0.70
                raw_penalty = min(50.0, raw_penalty)

            penalty = -max(5, int(round(raw_penalty * mode_factor)))
            return penalty


# ==============================================================================
# PHẦN 4: DEMO VÀ CHẠY THỰC NGHIỆM TỰ ĐỘNG
# ==============================================================================
def print_banner(title: str):
    print("\n" + "=" * 80)
    print(f" {title.center(78)} ")
    print("=" * 80)


def demo_contest_simulation():
    print_banner("DEMO 1: THUẬT TOÁN TÍNH RATING CONTEST CODEFORCES CHUẨN")

    # Kịch bản 1: Thí sinh 1500 đứng rank #150 / 1000
    res1 = CodeforcesContestEngine.calculate_single_contest_result(
        user_rating=1500,
        actual_rank=150,
        total_participants=1000,
        avg_opponent_rating=1500,
    )
    print("🎯 KỊCH BẢN 1: Thí sinh Rating 1500 thi đấu xuất sắc:")
    print(f"   • Rating trước thi : {res1['old_rating']} ({res1['old_tier'].name})")
    print(
        f"   • Hạng thực tế     : #{res1['rank']} / {res1['total_participants']} thí sinh"
    )
    print(f"   • Hạng kỳ vọng Seed: #{res1['seed']} (Dự đoán theo Elo)")
    print(f"   • Hạng điều chỉnh m: #{res1['target_rank']}")
    print(f"   • Performance R_perf: {res1['performance']} pts")
    print(f"   • Biến động Delta  : +{res1['delta']} pts 🚀")
    print(f"   • Rating Mới       : {res1['new_rating']} ({res1['new_tier'].name})")

    print("\n" + "-" * 80)

    # Kịch bản 2: Thí sinh 2000 đứng rank #400 / 1000
    res2 = CodeforcesContestEngine.calculate_single_contest_result(
        user_rating=2000,
        actual_rank=400,
        total_participants=1000,
        avg_opponent_rating=1500,
    )
    print("📉 KỊCH BẢN 2: Thí sinh Rating 2000 thi đấu dưới sức:")
    print(f"   • Rating trước thi : {res2['old_rating']} ({res2['old_tier'].name})")
    print(
        f"   • Hạng thực tế     : #{res2['rank']} / {res2['total_participants']} thí sinh"
    )
    print(f"   • Hạng kỳ vọng Seed: #{res2['seed']} (Dự đoán theo Elo)")
    print(f"   • Hạng điều chỉnh m: #{res2['target_rank']}")
    print(f"   • Performance R_perf: {res2['performance']} pts")
    print(f"   • Biến động Delta  : {res2['delta']} pts 📉")
    print(f"   • Rating Mới       : {res2['new_rating']} ({res2['new_tier'].name})")


def demo_arena_practice():
    print_banner("DEMO 2: TÍNH ĐIỂM & TRỪ ĐIỂM LUYỆN TẬP / ĐẤU TRƯỜNG THEO ĐỘ KHÓ")

    problems = [
        ("Bài Dễ (Rating 800)", 800, False, 1.0),
        ("Bài Vừa (Rating 1400)", 1400, False, 1.0),
        ("Bài Khó (Rating 2200)", 2200, True, 1.35),
        ("Bài Siêu Khó ICPC (Rating 3000)", 3000, True, 1.75),
    ]

    print(
        f"{'Tên Bài Tập':<35} | {'Đúng (+Score/Rating)':<22} | {'Sai (-Score/Rating)':<20}"
    )
    print("-" * 80)

    for name, r, is_ev, mult in problems:
        score_win_m1 = ArenaScoringEngine.calculate_score(
            r, is_accepted=True, is_mode1=True, event_multiplier=mult
        )
        rate_win_m1 = ArenaScoringEngine.calculate_rating_change(
            1500, r, is_accepted=True, is_mode1=True, event_multiplier=mult
        )

        score_loss_m1 = ArenaScoringEngine.calculate_score(
            r, is_accepted=False, is_mode1=True
        )
        rate_loss_m1 = ArenaScoringEngine.calculate_rating_change(
            1500, r, is_accepted=False, is_mode1=True, is_event=is_ev
        )

        win_str = f"+{score_win_m1} pts / +{rate_win_m1} R"
        loss_str = f"{score_loss_m1} pts / {rate_loss_m1} R"
        print(f"{name:<35} | {win_str:<22} | {loss_str:<20}")


if __name__ == "__main__":
    print("\n🚀 KHỞI ĐỘNG CÔNG CỤ TÍNH ĐIỂM & RATING CODEFORCES TOÀN DIỆN")
    demo_contest_simulation()
    demo_arena_practice()
    print_banner("HOÀN TẤT THỬ NGHIỆM 100% THÀNH CÔNG")
