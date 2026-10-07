"""Rank calculations, tier mappings, badge icons, and Vietnamese titles."""

# Thứ tự bậc Rank từ thấp nhất (T8) đến cao nhất (HT1)
RANK_ORDER: list[str] = [
    "T8",
    "T7",
    "T6",
    "T5",
    "T4",
    "T3",
    "LT2",
    "MT2",
    "HT2",
    "LT1",
    "MT1",
    "HT1",
]

# Ngưỡng điểm Rating tương ứng từng bậc rank
RANK_THRESHOLDS: list[tuple[str, int, int]] = [
    ("HT1", 3000, 99999),
    ("MT1", 2600, 2999),
    ("LT1", 2400, 2599),
    ("HT2", 2300, 2399),
    ("MT2", 2100, 2299),
    ("LT2", 1900, 2099),
    ("T3", 1600, 1899),
    ("T4", 1400, 1599),
    ("T5", 1200, 1399),
    ("T6", 700, 1199),
    ("T7", 400, 699),
    ("T8", 0, 399),
]

# Biểu tượng huy hiệu cho từng bậc Rank (Đồng bộ với Server)
RANK_BADGES: dict[str, str] = {
    "RHT1": "🥀",
    "HT1": "👑",
    "MT1": "💎",
    "LT1": "🏆",
    "HT2": "🔱",
    "MT2": "⚜️",
    "LT2": "🛡️",
    "T3": "💠",
    "T4": "🔷",
    "T5": "🔶",
    "T6": "⭐",
    "T7": "⭐",
    "T8": "⭐",
}

# Tên danh hiệu hiển thị chuẩn hóa theo chủ đề Redstone & Minecraft Logic
RANK_TITLES: dict[str, str] = {
    "RHT1": "Retired Redstone Mastermind",
    "HT1": "Redstone Mastermind",
    "MT1": "Redstone Engineer",
    "LT1": "Command Mastermind",
    "HT2": "Command Engineer",
    "MT2": "Code Crafter",
    "LT2": "Logic Crafter",
    "T3": "Redstone Crafter",
    "T4": "System Builder",
    "T5": "Code Builder",
    "T6": "Circuit Explorer",
    "T7": "Code Miner",
    "T8": "Code Novice",
}

# Ý nghĩa mô tả từng bậc rank
RANK_MEANINGS: dict[str, str] = {
    "RHT1": "Bảo lưu thành tích kỷ lục Redstone Mastermind",
    "HT1": "Bậc thầy tư duy hệ thống Redstone",
    "MT1": "Kỹ thuật Redstone chuyên sâu",
    "LT1": "Bậc thầy tư duy hệ thống Command",
    "HT2": "Command nâng cao",
    "MT2": "Code + Minecraft",
    "LT2": "Logic + Minecraft",
    "T3": "Redstone cơ bản → nâng cao",
    "T4": "Xây dựng hệ thống",
    "T5": "Code + xây dựng",
    "T6": "Khám phá circuit/logic",
    "T7": "Bắt đầu 'đào' code",
    "T8": "Người mới",
}

RANK_MIN_RATINGS: dict[str, int] = {t[0]: t[1] for t in RANK_THRESHOLDS}
RANK_THRESHOLDS_DICT: dict[str, tuple[int, int]] = {t[0]: (t[1], t[2]) for t in RANK_THRESHOLDS}

# Bảng mã màu Hex Discord cho từng bậc rank
RANK_COLORS: dict[str, int] = {
    "RHT1": 0x95A5A6,  # Màu xám khói danh dự
    "HT1": 0xFF0000,  # Đỏ huyền thoại
    "MT1": 0xFF8C00,  # Cam đậm
    "LT1": 0xAA00AA,  # Tím violet
    "HT2": 0x0000FF,  # Xanh dương
    "MT2": 0x03A89E,  # Xanh ngọc
    "LT2": 0x008000,  # Xanh lá
    "T3": 0x808080,  # Xám hiệp sĩ
    "T4": 0x708090,  # Xám đá
    "T5": 0x8B4513,  # Nâu đất
    "T6": 0xCD853F,  # Nâu sáng
    "T7": 0x9E9E9E,  # Xám nhạt
    "T8": 0xCCCCCC,  # Bạc tân binh
}


def get_rank_by_rating(rating: int) -> str:
    """Trả về mã bậc rank tương ứng với điểm rating hiện tại của thí sinh."""
    if rating >= 3000:
        return "HT1"
    if rating >= 2600:
        return "MT1"
    if rating >= 2400:
        return "LT1"
    if rating >= 2300:
        return "HT2"
    if rating >= 2100:
        return "MT2"
    if rating >= 1900:
        return "LT2"
    if rating >= 1600:
        return "T3"
    if rating >= 1400:
        return "T4"
    if rating >= 1200:
        return "T5"
    if rating >= 700:
        return "T6"
    if rating >= 400:
        return "T7"
    return "T8"


def get_rank_index(rank: str) -> int:
    """Trả về chỉ số số học của rank (0 = T8, 11 = HT1)."""
    rank_upper = rank.upper().replace("+", "")
    try:
        return RANK_ORDER.index(rank_upper)
    except ValueError:
        return 0


def is_rank_sufficient(user_rank: str, required_rank: str) -> bool:
    """
    Kiểm tra rank của thí sinh có đạt yêu cầu tối thiểu hay không.
    Ví dụ: thí sinh T4, yêu cầu T6+ -> Hợp lệ (True).
    """
    user_idx = get_rank_index(user_rank)
    req_idx = get_rank_index(required_rank)
    return user_idx >= req_idx


def get_rank_badge(rank: str) -> str:
    """Trả về icon huy hiệu của rank."""
    return RANK_BADGES.get(rank.upper(), "🌱")


def get_rank_title(rank: str) -> str:
    """Trả về tên danh hiệu đầy đủ của rank."""
    return RANK_TITLES.get(rank.upper(), f"Hạng {rank}")


get_rank_name = get_rank_title


def get_rank_meaning(rank: str) -> str:
    """Trả về ý nghĩa mô tả của bậc rank."""
    return RANK_MEANINGS.get(rank.upper(), "")


def get_rank_color(rank: str) -> int:
    """Trả về mã màu hex của rank."""
    return RANK_COLORS.get(rank.upper(), 0x3498DB)


# Phân nhóm Bậc Tier tương ứng với Codeforces Division:
# • Tier 8 - 7 - 6 : Div. 4 (Nhập môn & cơ bản)
# • Tier 6 - 5 - 4 - 3 : Div. 3 (Trung bình & thuật toán nền tảng)
# • LT2 - MT2 - HT2 : Div. 2 (Nâng cao & cấu trúc dữ liệu khó)
# • LT1 - MT1 - HT1 : Div. 1 (Chuyên sâu & giải thuật đỉnh cao)
TIER_DIVISIONS: dict[str, str] = {
    "T8": "Div. 4",
    "T7": "Div. 4",
    "T6": "Div. 4 / Div. 3",
    "T5": "Div. 3",
    "T4": "Div. 3",
    "T3": "Div. 3",
    "LT2": "Div. 2",
    "MT2": "Div. 2",
    "HT2": "Div. 2",
    "LT1": "Div. 1",
    "MT1": "Div. 1",
    "HT1": "Div. 1",
    "RHT1": "Div. 1",
}


def get_tier_division(rank: str) -> str:
    """Trả về nhóm Division tương ứng của bậc rank."""
    return TIER_DIVISIONS.get(rank.upper().replace("+", ""), "Div. 4")


def get_tier_progress(rating: int, rank: str | None = None) -> dict:
    """
    Tính toán tiến độ của bậc Rank hiện tại dựa trên Rating thực tế.
    Trả về dict chứa thông tin tiến độ, điểm cần để thăng hạng và nhãn hiển thị.
    """
    if not rank:
        rank = get_rank_by_rating(rating)
    r_upper = rank.upper().replace("+", "")

    # Đảm bảo rank luôn đồng bộ chính xác với rating thực tế (trừ trường hợp danh hiệu bảo lưu RHT1)
    if r_upper != "RHT1":
        actual_rank = get_rank_by_rating(rating)
        if r_upper != actual_rank:
            r_upper = actual_rank

    if r_upper in ("HT1", "RHT1") or rating >= 3000:
        return {
            "current_tier": r_upper,
            "current_tier_title": get_rank_title(r_upper),
            "current_rating": rating,
            "min_rating": 3000,
            "next_tier": None,
            "next_tier_title": None,
            "target_rating": 3000,
            "needed_points": 0,
            "progress_pct": 100.0,
            "is_max_tier": True,
            "label": "MAX TIER • No higher tier",
        }

    idx = get_rank_index(r_upper)
    next_idx = min(len(RANK_ORDER) - 1, idx + 1)
    next_tier = RANK_ORDER[next_idx]

    # Tìm ngưỡng min của current tier và next tier
    curr_min = 0
    next_min = 3000
    for t_name, t_min, _ in RANK_THRESHOLDS:
        if t_name == r_upper:
            curr_min = t_min
        if t_name == next_tier:
            next_min = t_min

    span = max(1, next_min - curr_min)
    points_in_tier = max(0, rating - curr_min)
    pct = min(100.0, max(0.0, (points_in_tier / span) * 100.0))
    needed = max(0, next_min - rating)

    return {
        "current_tier": r_upper,
        "current_tier_title": get_rank_title(r_upper),
        "current_rating": rating,
        "min_rating": curr_min,
        "next_tier": next_tier,
        "next_tier_title": get_rank_title(next_tier),
        "target_rating": next_min,
        "needed_points": needed,
        "progress_pct": round(pct, 1),
        "is_max_tier": False,
        "label": f"{needed} Rating to next tier: {next_tier}",
    }


def calculate_match_performance(
    rating_delta: float,
    rounds_won: int = 2,
    lives_left: int = 2,
    is_winner: bool = True,
) -> dict:
    """Đánh giá phong độ thi đấu (Performance Grade & Elo Impact) cho trận đấu."""
    if is_winner:
        if lives_left >= 2 and rounds_won >= 2:
            grade = "S+"
        elif lives_left >= 1:
            grade = "S"
        else:
            grade = "A+"

        if abs(rating_delta) >= 28:
            impact = "Excellent"
        elif abs(rating_delta) >= 15:
            impact = "Strong"
        else:
            impact = "Solid"
    else:
        if rounds_won >= 1 or lives_left >= 1:
            grade = "A"
        else:
            grade = "B"
        impact = "Solid"

    return {
        "grade": grade,
        "impact": impact,
        "mvp": is_winner,
    }

