"""Codeforces-compliant Logistic Elo Rating, Event Multiplier (1.2x - 1.75x), and Score Engine."""

import math


class RatingEngine:
    """
    Hệ thống tính điểm và Rating chuẩn thuật toán Logistic Elo Codeforces:
    1. Rating: Điểm kỹ năng thi đấu tương đối (Elo Codeforces).
    2. Score: Điểm tích lũy bài tập giải đúng (Mode 1: 100%, Mode 2: 90%).
    3. Event Bonus: Nhân 1.2x - 1.75x điểm cho bài Event / Hot Challenge.
    4. Rating Penalty: Trừ điểm phong độ chuẩn Elo, bảo vệ tân binh dưới T4.
    """

    MODE1_MULTIPLIER = (
        0.85  # Mode 1 (CF Sync): Giảm 15% điểm so với thi đấu bot trực tiếp
    )
    MODE2_MULTIPLIER = 1.00  # Mode 2 (Bot Sandbox Judge): 100% điểm chuẩn

    @classmethod
    def get_event_bonus_multiplier(
        cls,
        contest_name: str = "",
        problem_name: str = "",
        problem_rating: int | None = None,
    ) -> tuple[bool, float, str]:
        """
        Kiểm tra bài tập / cuộc thi có thuộc diện Event / Hot Challenge không và trả về:
        (is_event, multiplier (1.2x - 1.75x), event_badge_tag).
        """
        text = f"{contest_name} {problem_name}".lower()
        r = problem_rating or 1200

        event_keywords = [
            "icpc",
            "huawei",
            "challenge",
            "global",
            "championship",
            "cup",
            "marathon",
            "kotlin",
            "pinely",
            "harbour",
            "codeton",
            "good bye",
            "hello",
            "epic",
            "ton",
        ]
        is_keyword_event = any(k in text for k in event_keywords)

        if is_keyword_event or r >= 2000:
            if "icpc" in text or "huawei" in text or r >= 2400:
                return True, 1.75, "🔥 ICPC & Grand Challenge (1.75x Điểm)"
            elif "global" in text or "championship" in text or r >= 2100:
                return True, 1.50, "💎 Global Championship Event (1.50x Điểm)"
            elif r >= 1800 or "pinely" in text or "codeton" in text:
                return True, 1.35, "⚡ Special Round Challenge (1.35x Điểm)"
            else:
                return True, 1.20, "🌟 Hot Community Event (1.20x Điểm)"

        return False, 1.0, ""

    @classmethod
    def estimate_cf_problem_rating(
        cls,
        contest_name: str = "",
        problem_index: str = "A",
    ) -> int:
        """
        Ước lượng điểm rating thực tế của bài tập Codeforces khi chưa có official rating.
        Chống lạm phát rating bằng cách nhận diện chính xác Division (Div. 4, Div. 3, Div. 2, Div. 1, Global...)
        và vị trí chữ cái bài toán (A, B, C, D, E, F...).
        """
        name_lower = contest_name.lower()
        idx_letter = (
            problem_index[0].upper()
            if problem_index and problem_index[0].isalpha()
            else "A"
        )
        offset = ord(idx_letter) - ord("A")

        # 1. Nhóm Div. 4: Thang rating 800 - 1500
        if "div. 4" in name_lower or "div 4" in name_lower:
            div4_ratings = [800, 800, 800, 900, 1100, 1200, 1400, 1500]
            if offset < len(div4_ratings):
                return div4_ratings[offset]
            return min(1600, 1500 + (offset - 7) * 100)

        # 2. Nhóm Div. 3: Thang rating 800 - 1900
        if "div. 3" in name_lower or "div 3" in name_lower:
            div3_ratings = [800, 900, 1000, 1200, 1500, 1700, 1900]
            if offset < len(div3_ratings):
                return div3_ratings[offset]
            return min(2100, 1900 + (offset - 6) * 100)

        # 3. Nhóm Div. 2: Thang rating 1000 - 2400
        if "div. 2" in name_lower or "div 2" in name_lower:
            div2_ratings = [1000, 1200, 1500, 1800, 2100, 2400]
            if offset < len(div2_ratings):
                return div2_ratings[offset]
            return min(2800, 2400 + (offset - 5) * 150)

        # 4. Nhóm Div. 1: Thang rating 1800 - 3400
        if "div. 1" in name_lower or "div 1" in name_lower:
            div1_ratings = [1800, 2100, 2400, 2700, 3000, 3300]
            if offset < len(div1_ratings):
                return div1_ratings[offset]
            return min(3500, 3300 + (offset - 5) * 150)

        # 5. Nhóm Global / Educational / Pinely / TON / HarBour / CodeTON
        if any(
            k in name_lower
            for k in [
                "educational",
                "edu",
                "global",
                "pinely",
                "ton",
                "harbour",
                "codeton",
                "hello",
                "good bye",
            ]
        ):
            global_ratings = [800, 1000, 1300, 1600, 1900, 2300, 2700, 3000]
            if offset < len(global_ratings):
                return global_ratings[offset]
            return min(3500, 3000 + (offset - 7) * 150)

        # Mặc định tương thích: Thang trung bình Div. 3 / Div. 2
        default_ratings = [800, 1000, 1200, 1500, 1800, 2100, 2400]
        if offset < len(default_ratings):
            return default_ratings[offset]
        return min(3500, 2400 + (offset - 6) * 200)

    @classmethod
    def calculate_problem_score(
        cls, problem_rating: int, is_mode1: bool = True, event_multiplier: float = 1.0
    ) -> float:
        """
        Tính điểm Score tích lũy khi giải đúng bài tập (Hỗ trợ hệ số Event 1.2x - 1.75x).
        Mode 1: 85% (giảm 15%), Mode 2: 100%.
        """
        base_rating = max(800, min(3500, problem_rating or 1200))
        base_points = round(base_rating / 10.0, 1)

        mode_mult = cls.MODE1_MULTIPLIER if is_mode1 else cls.MODE2_MULTIPLIER
        final_points = base_points * mode_mult * max(1.0, event_multiplier)
        return round(final_points, 1)

    @classmethod
    def calculate_problem_score_penalty(
        cls, problem_rating: int | None = None, is_mode1: bool = True
    ) -> float:
        """
        Tính điểm Score bị trừ khi làm sai bài tập theo nguyên tắc tỷ lệ thuận với độ khó:
        - Bài dễ (800): trừ ít (-20.0 pts)
        - Bài vừa (1200): trừ vừa (-30.0 pts)
        - Bài khó (2000 - 3500): trừ nhiều (-50.0 đến -87.5 pts)
        Mode 1: hệ số 0.85, Mode 2: hệ số 1.00.
        """
        base_rating = max(800, min(3500, problem_rating or 1200))
        base_points = base_rating / 10.0
        penalty_ratio = 0.25  # Trừ 25% giá trị bài
        mode_factor = cls.MODE1_MULTIPLIER if is_mode1 else cls.MODE2_MULTIPLIER
        raw_penalty = round(base_points * penalty_ratio * mode_factor, 1)
        return -max(15.0, raw_penalty)

    @classmethod
    def _calculate_expected_prob(cls, user_rating: int, problem_rating: int) -> float:
        """
        Xác suất kỳ vọng thí sinh giải thành công bài tập theo công thức Codeforces Elo:
        E = 1 / (1 + 10^((R_problem - R_user) / 400))
        """
        u_rating = float(user_rating or 0)
        p_rating = float(max(800, problem_rating or 1200))
        diff = (p_rating - u_rating) / 400.0
        diff = max(-10.0, min(10.0, diff))
        return 1.0 / (1.0 + math.pow(10.0, diff))

    @classmethod
    def calculate_problem_rating_delta(
        cls,
        user_rating: int,
        problem_rating: int,
        is_mode1: bool = True,
        event_multiplier: float = 1.0,
    ) -> int:
        """
        Tính lượng điểm Rating cộng thêm khi GIẢI ĐÚNG bài tập (có nhân hệ số Event).
        Bài Tier càng cao cộng càng nhiều điểm; User Tier cao làm bài Tier thấp cộng rất ít điểm.
        """
        expected_prob = cls._calculate_expected_prob(user_rating, problem_rating)
        u_r = user_rating or 0
        if u_r < 1200:
            k_factor = 60.0
        elif u_r < 2000:
            k_factor = 45.0
        else:
            k_factor = 35.0

        raw_delta = k_factor * (1.0 - expected_prob) * max(1.0, event_multiplier)
        factor = cls.MODE1_MULTIPLIER if is_mode1 else cls.MODE2_MULTIPLIER
        delta = max(1, int(round(raw_delta * factor)))
        return delta

    @classmethod
    def calculate_problem_rating_penalty(
        cls,
        user_rating: int,
        problem_rating: int,
        is_mode1: bool = True,
        is_event: bool = False,
        tests_passed_ratio: float = 0.0,
    ) -> int:
        """
        Tính toán lượng điểm Rating BỊ TRỪ khi LÀM SAI bài tập (Tỷ lệ thuận theo độ khó bài tập):
        - Bài dễ (Rating 800-1000): trừ ít (-10 đến -15 pts).
        - Bài khó (Rating 2000-3000+): trừ nhiều (-35 đến -50 pts).
        - Quy tắc bảo vệ tân binh bài Event: Thí sinh dưới Rank T4 (rating < 1400) làm sai bài Event KHÔNG BỊ TRỪ ĐIỂM (penalty = 0).
        """
        u_r = user_rating or 0
        p_r = max(800, min(3500, problem_rating or 1200))

        # Nếu là bài Event và user chưa đạt rank T4 (< 1400 rating): Miễn trừ điểm phạt!
        if is_event and u_r < 1400:
            return 0

        # Phạt cơ sở tỷ lệ thuận với độ khó bài tập
        difficulty_ratio = p_r / 2500.0
        raw_penalty = 50.0 * min(1.0, max(0.25, difficulty_ratio))

        # Điều chỉnh mức phạt theo tỷ lệ testcase vượt qua (nếu là bài Event)
        if is_event:
            if tests_passed_ratio < 0.20:
                raw_penalty *= 1.35
            elif tests_passed_ratio < 0.40:
                raw_penalty *= 1.20
            else:
                raw_penalty *= 0.70
            raw_penalty = min(50.0, raw_penalty)

        factor = cls.MODE1_MULTIPLIER if is_mode1 else cls.MODE2_MULTIPLIER
        penalty = -max(5, int(round(raw_penalty * factor)))
        return penalty

    @classmethod
    def evaluate_mode2_two_step_submission(
        cls,
        tests_passed: int,
        total_tests: int,
        user_rating: int,
        problem_rating: int,
        contest_participants: int | None = None,
        contest_percentile: float | None = None,
        is_event: bool = False,
        event_multiplier: float = 1.0,
    ) -> dict:
        """
        Đánh giá điểm Mode 2 theo quy trình 2 bước chuẩn:
        - Bước 1: Kiểm tra % testcase đúng (ngưỡng 50%).
          + Nếu đúng < 50%: Trừ điểm Rating & Score.
          + Nếu đúng >= 50%: Chuyển sang Bước 2 và tính điểm cơ sở.
        - Bước 2: Phân tích Thứ hạng Bảng Xếp Hạng Contest (Standings Percentile):
          + Percentile > 70% (Top 30% giỏi nhất): Điểm cao (1.4x).
          + Percentile > 50% (Top 50%): Điểm trung bình (1.0x).
          + Percentile > 30% (Top 70%): Cộng ít (0.5x).
          + Percentile > 10% (Top 90%): Không cộng (+0 Rating).
          + Percentile <= 10% hoặc User Rating cao mà xếp hạng quá thấp: Trừ điểm phong độ.
          + Nếu không có BXH contest / quá ít người: Bỏ qua Bước 2 và tính điểm chuẩn Elo theo bài.
        """
        from services.rank import get_rank_by_rating

        tot_t = max(1, total_tests)
        pass_ratio = tests_passed / tot_t
        prob_r = problem_rating or 1200
        u_r = max(0, user_rating or 0)
        prob_tier = get_rank_by_rating(prob_r)

        # ── BƯỚC 1: KIỂM TRA % TESTCASE ĐÚNG (NGƯỠNG 40%) ──
        if pass_ratio < 0.40:
            rating_delta = cls.calculate_problem_rating_penalty(
                user_rating=u_r,
                problem_rating=prob_r,
                is_mode1=False,
                is_event=is_event,
                tests_passed_ratio=pass_ratio,
            )
            score_delta = cls.calculate_problem_score_penalty(prob_r, is_mode1=False)

            return {
                "step1_passed": False,
                "pass_ratio": pass_ratio,
                "step2_evaluated": False,
                "rating_delta": rating_delta,
                "score_delta": score_delta,
                "multiplier": 0.0,
                "prob_tier": prob_tier,
                "step1_desc": f"❌ **Bước 1 (Độ chính xác Testcase):** Đạt `{tests_passed}/{tot_t}` test (`{pass_ratio*100:.1f}%` < 40%) ➔ **Không chấp nhận**",
                "step2_desc": "⛔ **Bước 2 (BXH Contest):** Đã bỏ qua do không vượt qua Bước 1.",
                "summary": f"📉 Đúng `{tests_passed}/{tot_t}` test (< 40%) ➔ Bị trừ `{abs(rating_delta)}` Rating & `{abs(score_delta):.1f}` Score.",
            }

        # Bước 1 đạt (>= 40% test)
        step1_desc = f"✅ **Bước 1 (Độ chính xác Testcase):** Đạt `{tests_passed}/{tot_t}` test (`{pass_ratio*100:.1f}%` ≥ 40%) ➔ **Đạt điều kiện cộng điểm!**"

        base_score = cls.calculate_problem_score(
            prob_r, is_mode1=False, event_multiplier=event_multiplier
        )
        base_rating_delta = cls.calculate_problem_rating_delta(
            u_r, prob_r, is_mode1=False, event_multiplier=event_multiplier
        )

        # ── BƯỚC 2: PHÂN TÍCH THỨ HẠNG BẢNG XẾP HẠNG CONTEST ──
        has_valid_standings = (
            contest_percentile is not None
            and contest_participants is not None
            and contest_participants >= 20
        )

        if not has_valid_standings:
            # Không có hoặc quá ít người trong BXH -> Bỏ qua bước 2, dùng điểm chuẩn Elo
            score_delta = round(base_score, 1)
            rating_delta = base_rating_delta
            return {
                "step1_passed": True,
                "pass_ratio": pass_ratio,
                "step2_evaluated": False,
                "rating_delta": rating_delta,
                "score_delta": score_delta,
                "multiplier": 1.0,
                "prob_tier": prob_tier,
                "step1_desc": step1_desc,
                "step2_desc": "⏭️ **Bước 2 (BXH Contest):** Không đủ dữ liệu BXH ➔ Tự động tính điểm chuẩn (pts) theo độ khó bài.",
                "summary": f"🌟 Giải đúng `{tests_passed}/{tot_t}` test (`{prob_tier}`) ➔ Cộng `+{rating_delta}` Rating & `+{score_delta:.1f}` Score.",
            }

        p = float(contest_percentile or 0.5)
        top_pct = max(1, int(round((1.0 - p) * 100)))

        # Kiểm tra trường hợp user rating cao nhưng đứng quá thấp
        is_overqualified_underperforming = (u_r >= prob_r + 300) and (p <= 0.30)

        if is_overqualified_underperforming or p <= 0.10:
            # Xếp hạng quá thấp (< 10%) hoặc cao thủ làm bài dễ mà đứng thấp (< 30%)
            penalty_val = abs(
                cls.calculate_problem_rating_penalty(u_r, prob_r, is_mode1=False)
            )
            rating_delta = -max(5, int(round(penalty_val * 0.6)))
            score_delta = 0.0
            mult = -0.5
            step2_desc = (
                f"🔻 **Bước 2 (BXH Contest):** Xếp hạng Top `{top_pct}%` ({contest_participants:,} người)\n"
                f"> ⚠️ **Cảnh báo phong độ:** Thứ hạng quá thấp so với đẳng cấp Rating `{u_r}` ➔ **Bị trừ điểm phong độ** (`{rating_delta}` pts)."
            )
            summary = f"📉 Đứng Top {top_pct}% BXH (dưới kỳ vọng) ➔ Trừ `{abs(rating_delta)}` Rating."
        elif p > 0.70:
            # Top 30% giỏi nhất (> 70% người)
            mult = 1.40
            rating_delta = max(1, int(round(base_rating_delta * mult)))
            score_delta = round(base_score * mult, 1)
            step2_desc = (
                f"🚀 **Bước 2 (BXH Contest):** Xếp hạng Top `{top_pct}%` vượt trội (> 70% thí sinh)\n"
                f"> 🏆 **Thành tích xuất sắc:** Thưởng nhân **`1.40x`** điểm Rating & Score!"
            )
            summary = f"🚀 Top {top_pct}% BXH Contest ➔ Thưởng 1.4x (+{rating_delta} Rating & +{score_delta:.1f} Score)."
        elif p > 0.50:
            # Top 50%
            mult = 1.00
            rating_delta = base_rating_delta
            score_delta = round(base_score, 1)
            step2_desc = (
                f"⚖️ **Bước 2 (BXH Contest):** Xếp hạng Top `{top_pct}%` (> 50% thí sinh)\n"
                f"> 🎯 **Đạt kỳ vọng chuẩn:** Nhận **`1.00x`** điểm Rating & Score."
            )
            summary = f"⚖️ Top {top_pct}% BXH Contest ➔ Nhận điểm chuẩn (+{rating_delta} Rating & +{score_delta:.1f} Score)."
        elif p > 0.30:
            # Top 70% (> 30% người)
            mult = 0.50
            rating_delta = max(1, int(round(base_rating_delta * mult)))
            score_delta = round(base_score * mult, 1)
            step2_desc = (
                f"📉 **Bước 2 (BXH Contest):** Xếp hạng Top `{top_pct}%` (> 30% thí sinh)\n"
                f"> 💡 **Cộng điểm khuyến khích:** Nhận **`0.50x`** điểm Rating & Score."
            )
            summary = f"📉 Top {top_pct}% BXH Contest ➔ Cộng ít (+{rating_delta} Rating & +{score_delta:.1f} Score)."
        else:
            # 10% < p <= 30%
            mult = 0.0
            rating_delta = 0
            score_delta = round(base_score * 0.25, 1)
            step2_desc = (
                f"⚠️ **Bước 2 (BXH Contest):** Xếp hạng Top `{top_pct}%` (> 10% thí sinh)\n"
                f"> 🛡️ **Không cộng Rating:** Thứ hạng chưa đủ cao để tăng Rating (+0 pts)."
            )
            summary = f"⚠️ Top {top_pct}% BXH Contest ➔ Rating giữ nguyên (+0 pts), cộng +{score_delta:.1f} Score."

        return {
            "step1_passed": True,
            "pass_ratio": pass_ratio,
            "step2_evaluated": True,
            "rating_delta": rating_delta,
            "score_delta": score_delta,
            "multiplier": mult,
            "prob_tier": prob_tier,
            "step1_desc": step1_desc,
            "step2_desc": step2_desc,
            "summary": summary,
        }

    @classmethod
    def calculate_seed(cls, rating: float, opponent_ratings: list[int]) -> float:
        """
        Tính thứ hạng kỳ vọng (Seed) của một thí sinh với mức rating đối đầu với danh sách đối thủ:
        Seed(R) = 1 + sum(1 / (1 + 10^((R - R_opp) / 400)))
        """
        seed = 1.0
        for opp in opponent_ratings:
            diff = (rating - float(opp)) / 400.0
            diff = max(-10.0, min(10.0, diff))
            seed += 1.0 / (1.0 + math.pow(10.0, diff))
        return seed

    @classmethod
    def calculate_contest_performance(
        cls,
        user_rank: int,
        total_participants: int,
        opponent_ratings: list[int],
        current_user_rating: int | None = None,
    ) -> float:
        """
        Tính phong độ thi đấu (Performance Rating) trong contest theo thuật toán Codeforces chuẩn:
        - Nếu có current_user_rating: Tính target rank m = sqrt(user_rank * Seed(current_user_rating))
        - Tìm kiếm nhị phân R_perf sao cho Seed(R_perf) = target_rank.
        """
        if not opponent_ratings or total_participants <= 1:
            return float(current_user_rating or 1400)

        # Tính target rank m theo trung bình nhân Codeforces
        if current_user_rating is not None:
            user_seed = cls.calculate_seed(float(current_user_rating), opponent_ratings)
            target_rank = math.sqrt(float(user_rank) * user_seed)
        else:
            target_rank = float(user_rank)

        low = 0.0
        high = 4500.0

        for _ in range(50):
            mid = (low + high) / 2.0
            seed = cls.calculate_seed(mid, opponent_ratings)
            if seed > target_rank:
                low = mid
            else:
                high = mid

        return round((low + high) / 2.0, 1)

    @classmethod
    def calculate_contest_rating_change(
        cls, current_rating: int, performance: float, volatility: float = 0.5
    ) -> tuple[int, int]:
        """
        Tính toán rating delta sau khi kết thúc cuộc thi theo chuẩn Codeforces:
        Delta = (Performance - Current Rating) * 0.5.
        """
        raw_delta = (performance - float(current_rating)) * volatility
        rating_delta = int(round(raw_delta))
        new_rating = max(0, current_rating + rating_delta)
        return new_rating, rating_delta

    @classmethod
    def calculate_full_contest_simulation(
        cls,
        user_rating: int,
        user_rank: int,
        total_participants: int,
        opponent_ratings: list[int] | None = None,
        avg_opponent_rating: int | None = None,
    ) -> dict:
        """
        Mô phỏng đầy đủ quy trình tính toán Rating sau một kỳ thi Codeforces (Contest Rating Engine).
        """
        from services.rank import get_rank_badge, get_rank_by_rating

        total_p = max(2, total_participants)
        u_rank = max(1, min(total_p, user_rank))
        u_r = max(0, user_rating)

        # Nếu không có danh sách đối thủ chi tiết, sinh phân phối đối thủ thực tế
        if not opponent_ratings:
            avg_r = avg_opponent_rating or max(1000, u_r)
            opponents = []
            for i in range(total_p - 1):
                # Phân phối đều trải dài quanh mức trung bình
                spread = (i / max(1, total_p - 2) - 0.5) * 1200
                opp_r = int(max(400, min(3500, avg_r + spread)))
                opponents.append(opp_r)
        else:
            opponents = list(opponent_ratings)

        user_seed = cls.calculate_seed(float(u_r), opponents)
        target_rank = math.sqrt(float(u_rank) * user_seed)
        perf = cls.calculate_contest_performance(
            u_rank, total_p, opponents, current_user_rating=u_r
        )
        new_r, delta = cls.calculate_contest_rating_change(u_r, perf, volatility=0.5)

        old_rank_str = get_rank_by_rating(u_r)
        new_rank_str = get_rank_by_rating(new_r)
        old_badge = get_rank_badge(old_rank_str)
        new_badge = get_rank_badge(new_rank_str)

        if delta > 0:
            analysis = f"🚀 **Thi đấu vượt kỳ vọng!** Bạn đứng #{u_rank} (Hệ thống dự đoán: #{user_seed:.0f}), phong độ tương đương `{perf:.0f}` pts (+{delta} Rating)."
        elif delta < 0:
            analysis = f"📉 **Thi đấu dưới kỳ vọng!** Bạn đứng #{u_rank} (Hệ thống dự đoán: #{user_seed:.0f}), phong độ tương đương `{perf:.0f}` pts ({delta} Rating)."
        else:
            analysis = f"⚖️ **Thi đấu đúng phong độ!** Bạn đứng #{u_rank} khớp với dự đoán kỳ vọng (Rating giữ nguyên)."

        return {
            "old_rating": u_r,
            "rank": u_rank,
            "total_participants": total_p,
            "seed": round(user_seed, 1),
            "target_rank": round(target_rank, 1),
            "performance": perf,
            "delta": delta,
            "new_rating": new_r,
            "old_rank_str": old_rank_str,
            "new_rank_str": new_rank_str,
            "old_badge": old_badge,
            "new_badge": new_badge,
            "analysis": analysis,
        }


estimate_cf_problem_rating = RatingEngine.estimate_cf_problem_rating
