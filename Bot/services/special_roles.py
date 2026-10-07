"""Hệ thống Danh Hiệu Động & Tỉ Lệ Thắng (Dynamic Special Roles & Win Probability)

6 Danh Hiệu Đặc Biệt:
1. 👑 Overlord: Thắng chuỗi 50 liên tiếp trong Đấu Trường Ranked 1:1.
2. ⚡ Outclassed: Kỹ năng vượt trội, 10 ván liên tiếp đều có tỉ lệ thắng >80%.
3. 🔥 Clutchmaster: Chuyên lật kèo từ thế thua (10 lần lật từ <=10% hoặc 1 lần lật từ <5%).
4. 🍀 Godly Luck: 20 ván liên tiếp thắng ở thế tỉ lệ thắng <15%.
5. 🍀 Fortune: 10 ván thắng ở thế tỉ lệ thắng <15%.
6. 💀 Doomed: Tưởng thắng chắc nhưng bị đối thủ lật kèo.

Tất cả danh hiệu đều có thể biến mất khi người chơi không còn giữ vững điều kiện hoặc bị thua.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class SpecialRoleMeta:
    key: str
    name: str
    badge: str
    card_label: str
    full_title: str
    desc: str
    color_rgb: tuple[int, int, int]
    color_hex: int
    priority: int  # Độ ưu tiên hiển thị (số càng nhỏ ưu tiên càng cao)


SPECIAL_ROLES: dict[str, SpecialRoleMeta] = {
    "OVERLORD": SpecialRoleMeta(
        key="OVERLORD",
        name="Overlord",
        badge="👑",
        card_label="OVERLORD",
        full_title="👑 Overlord",
        desc="Thắng chuỗi 50 trận liên tiếp trong Đấu Trường Ranked 1:1",
        color_rgb=(251, 191, 36),
        color_hex=0xFBBF24,
        priority=1,
    ),
    "GODLY_LUCK": SpecialRoleMeta(
        key="GODLY_LUCK",
        name="Godly Luck",
        badge="🍀",
        card_label="GODLY LUCK",
        full_title="🍀 Godly Luck",
        desc="20 ván thắng ở thế tỉ lệ thắng cực thấp (<15%)",
        color_rgb=(16, 185, 129),
        color_hex=0x10B981,
        priority=2,
    ),
    "CLUTCHMASTER": SpecialRoleMeta(
        key="CLUTCHMASTER",
        name="Clutchmaster",
        badge="🔥",
        card_label="CLUTCHMASTER",
        full_title="🔥 Clutchmaster",
        desc="Chuyên lật kèo từ thế thua (10 lần lật từ ≤10% hoặc 1 lần lật từ <5%)",
        color_rgb=(239, 68, 68),
        color_hex=0xEF4444,
        priority=3,
    ),
    "OUTCLASSED": SpecialRoleMeta(
        key="OUTCLASSED",
        name="Outclassed",
        badge="⚡",
        card_label="OUTCLASSED",
        full_title="⚡ Outclassed",
        desc="Kỹ năng vượt trội, 10 ván liên tiếp đều có tỉ lệ thắng >80%",
        color_rgb=(250, 204, 21),
        color_hex=0xFACC15,
        priority=4,
    ),
    "FORTUNE": SpecialRoleMeta(
        key="FORTUNE",
        name="Fortune",
        badge="🍀",
        card_label="FORTUNE",
        full_title="🍀 Fortune",
        desc="10 ván thắng ở thế tỉ lệ thắng thấp (<15%)",
        color_rgb=(52, 211, 153),
        color_hex=0x34D399,
        priority=5,
    ),
    "DOOMED": SpecialRoleMeta(
        key="DOOMED",
        name="Doomed",
        badge="💀",
        card_label="DOOMED",
        full_title="💀 Doomed",
        desc="Tưởng thắng chắc nhưng bị đối thủ lật kèo ngoạn mục",
        color_rgb=(168, 85, 247),
        color_hex=0xA855F7,
        priority=6,
    ),
}


def get_special_role_meta(key: str | None) -> SpecialRoleMeta | None:
    """Lấy metadata của danh hiệu đặc biệt theo key."""
    if not key:
        return None
    return SPECIAL_ROLES.get(key.strip().upper())


def calculate_win_probability(
    p1_rating: int,
    p2_rating: int,
    p1_lives: int = 2,
    p2_lives: int = 2,
) -> tuple[float, float]:
    """
    Tính tỉ lệ phần trăm chiến thắng động (Dynamic Win Probability) giữa 2 người chơi (0.0% đến 100.0%).
    
    1. Xác suất cơ sở Elo (Pre-match Elo Probability):
       P_base1 = 1 / (1 + 10^((R2 - R1) / 400))
       P_base2 = 1 - P_base1
    
    2. Điều chỉnh theo số Mạng sống (Hearts System):
       - Khi 2 - 2 hoặc 1 - 1: tỉ lệ theo P_base
       - Khi 2 - 1: Người 1 mạng phải thắng liên tiếp 2 chặng:
         P_1_heart = (P_base)^2
         Người 2 mạng = 1.0 - P_1_heart
    """
    # 1. Elo base probability
    rating_diff = float(p2_rating - p1_rating)
    p_base1 = 1.0 / (1.0 + 10.0 ** (rating_diff / 400.0))
    p_base1 = max(0.01, min(0.99, p_base1))
    p_base2 = 1.0 - p_base1

    # 2. Lives factor
    if p1_lives <= 0:
        return 0.0, 100.0
    if p2_lives <= 0:
        return 100.0, 0.0

    if p1_lives == 2 and p2_lives == 1:
        # Player 2 only has 1 life, needs 2 consecutive wins
        p2_win = p_base2 ** 2.0
        p1_win = 1.0 - p2_win
    elif p1_lives == 1 and p2_lives == 2:
        # Player 1 only has 1 life, needs 2 consecutive wins
        p1_win = p_base1 ** 2.0
        p2_win = 1.0 - p1_win
    else:
        # 2-2 or 1-1
        p1_win = p_base1
        p2_win = p_base2

    pct1 = round(max(1.0, min(99.0, p1_win * 100.0)), 1)
    pct2 = round(100.0 - pct1, 1)
    return pct1, pct2


def evaluate_match_special_roles(
    winner_prev_role: str | None,
    winner_streak: int,
    winner_fortune_count: int,
    winner_outclassed_count: int,
    winner_clutch_count: int,
    winner_is_doomed: bool,
    winner_start_prob: float,
    winner_min_prob: float,
    loser_prev_role: str | None,
    loser_streak: int,
    loser_fortune_count: int,
    loser_outclassed_count: int,
    loser_clutch_count: int,
    loser_is_doomed: bool,
    loser_start_prob: float,
    loser_max_prob: float,
    loser_had_two_lives_when_winner_one: bool,
) -> dict[str, Any]:
    """
    Đánh giá và cập nhật trạng thái danh hiệu đặc biệt cho cả Người Thắng và Người Thua.
    Trả về dict chứa:
    - winner_new_role, winner_fortune_count, winner_outclassed_count, winner_clutch_count, winner_is_doomed
    - loser_new_role, loser_fortune_count, loser_outclassed_count, loser_clutch_count, loser_is_doomed
    - notifications: danh sách thông điệp vinh danh hoặc mất role
    """
    notifications: list[str] = []

    # ==========================================
    # 1. XỬ LÝ NGƯỜI THẮNG (WINNER)
    # ==========================================
    w_fortune = winner_fortune_count
    w_outclassed = winner_outclassed_count
    w_clutch = winner_clutch_count
    w_doomed = winner_is_doomed
    w_unlocked_roles: list[str] = []

    # A. 👑 Overlord: Thắng chuỗi 50 liên tiếp
    if winner_streak >= 50:
        w_unlocked_roles.append("OVERLORD")
        if winner_streak == 50:
            notifications.append("👑 **DANH HIỆU TỐI THƯỢNG: OVERLORD!** Bạn đã chạm mốc chuỗi 50 trận toàn thắng liên tiếp!")

    # B. ⚡ Outclassed: 10 ván liên tiếp tỉ lệ thắng > 80%
    if winner_start_prob > 80.0:
        w_outclassed += 1
        if w_outclassed >= 10:
            w_unlocked_roles.append("OUTCLASSED")
            if w_outclassed == 10:
                notifications.append("⚡ **MỞ KHÓA OUTCLASSED!** Kỹ năng vượt trội với 10 trận liên tiếp áp đảo tỉ lệ >80%!")
    else:
        # Gặp 1 ván tỉ lệ <= 80% -> mất chuỗi Outclassed
        if w_outclassed > 0 and "OUTCLASSED" in (winner_prev_role or ""):
            notifications.append("⚡ *Danh hiệu Outclassed đã biến mất do gặp trận đấu có tỉ lệ ≤80%.*")
        w_outclassed = 0

    # C. 🔥 Clutchmaster: Lật kèo từ thế thua
    # Điều kiện 1: Thắng 1 ván cực hiểm khi tỉ lệ < 5%
    # Điều kiện 2: 10 lần lật kèo từ tỉ lệ <= 10%
    clutched_extreme = (winner_min_prob < 5.0)
    clutched_normal = (winner_min_prob <= 10.0)

    if clutched_extreme:
        w_unlocked_roles.append("CLUTCHMASTER")
        notifications.append(f"🔥 **LẬT KÈO KINH ĐIỂN!** Bạn vừa giành chiến thắng từ thế tỉ lệ cược chỉ {winner_min_prob}%! Mở khóa **🔥 Clutchmaster**!")
    elif clutched_normal:
        w_clutch += 1
        if w_clutch >= 10:
            w_unlocked_roles.append("CLUTCHMASTER")
            if w_clutch == 10:
                notifications.append("🔥 **MỞ KHÓA CLUTCHMASTER!** Chuyên gia lật kèo: Đã 10 lần lật ngược thế cờ từ ≤10% tỉ lệ win!")

    # D. 🍀 Fortune & 🍀 Godly Luck: Thắng ở thế tỉ lệ ban đầu < 15%
    if winner_start_prob < 15.0:
        w_fortune += 1
        if w_fortune >= 20:
            w_unlocked_roles.append("GODLY_LUCK")
            if w_fortune == 20:
                notifications.append("🍀 **THẦN MAY MẮN TỐI THƯỢNG: GODLY LUCK!** Đạt chuỗi 20 ván chiến thắng ở thế cửa dưới (<15%)!")
        elif w_fortune >= 10:
            w_unlocked_roles.append("FORTUNE")
            if w_fortune == 10:
                notifications.append("🍀 **MỞ KHÓA FORTUNE!** 10 ván thắng ngoạn mục ở thế cửa dưới (<15%)!")
    else:
        # Ván thắng bình thường (>= 15%): Theo luật "sẽ không tính" -> giữ nguyên w_fortune, không cộng và không reset
        if w_fortune >= 20:
            w_unlocked_roles.append("GODLY_LUCK")
        elif w_fortune >= 10:
            w_unlocked_roles.append("FORTUNE")

    # E. 💀 Doomed: Chuộc tội khi thắng
    if w_doomed:
        w_doomed = False
        notifications.append("✨ **TẨY TRẦN DOOMED!** Bạn đã giành lại chiến thắng, xóa bỏ danh xưng 💀 Doomed!")

    # Xác định danh hiệu chính hiển thị cho Winner theo độ ưu tiên
    w_new_role = None
    if "OVERLORD" in w_unlocked_roles:
        w_new_role = "OVERLORD"
    elif "GODLY_LUCK" in w_unlocked_roles:
        w_new_role = "GODLY_LUCK"
    elif "CLUTCHMASTER" in w_unlocked_roles:
        w_new_role = "CLUTCHMASTER"
    elif "OUTCLASSED" in w_unlocked_roles:
        w_new_role = "OUTCLASSED"
    elif "FORTUNE" in w_unlocked_roles:
        w_new_role = "FORTUNE"

    # ==========================================
    # 2. XỬ LÝ NGƯỜI THUA (LOSER)
    # ==========================================
    l_lost_roles: list[str] = []
    if loser_prev_role in ("OVERLORD", "OUTCLASSED", "CLUTCHMASTER", "FORTUNE", "GODLY_LUCK"):
        l_lost_roles.append(loser_prev_role)

    # Thua trận -> Reset các chuỗi
    l_fortune = 0  # "reset khi bị chết"
    l_outclassed = 0
    l_clutch = 0
    l_new_role = None

    # F. 💀 Doomed: Tưởng thắng chắc nhưng bị đối thủ lật kèo
    # Điều kiện: Đối thủ từng có tỉ lệ <= 10% (hoặc người thua từng đạt >= 85% tỉ lệ win & dẫn 2 mạng vs 1 mạng)
    # nhưng cuối cùng người thua bị đối thủ lật ngược trận đấu!
    l_doomed = loser_is_doomed
    if (loser_max_prob >= 85.0 or loser_had_two_lives_when_winner_one) and (clutched_extreme or clutched_normal):
        l_doomed = True
        l_new_role = "DOOMED"
        notifications.append("💀 **BI KỊCH: DOOMED!** Bạn đã cầm chắc phần thắng nhưng lại để đối thủ lật kèo ngoạn mục! Nhận danh xưng 💀 Doomed.")
    elif l_doomed:
        l_new_role = "DOOMED"

    if l_lost_roles and not l_doomed:
        notifications.append(f"❌ *Danh hiệu {', '.join(l_lost_roles)} của người thua đã biến mất do bị hạ gục.*")

    return {
        "winner_new_role": w_new_role,
        "winner_fortune_count": w_fortune,
        "winner_outclassed_count": w_outclassed,
        "winner_clutch_count": w_clutch,
        "winner_is_doomed": w_doomed,
        "loser_new_role": l_new_role,
        "loser_fortune_count": l_fortune,
        "loser_outclassed_count": l_outclassed,
        "loser_clutch_count": l_clutch,
        "loser_is_doomed": l_doomed,
        "notifications": notifications,
    }
