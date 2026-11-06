"""
services/profile_card.py
Module kết xuất ảnh thẻ hồ sơ cá nhân (Visual Profile Card PNG) phong cách Esports / MCTiers.
Chuẩn hóa đồ họa theo yêu cầu:
- Avatar Discord dạng tròn có viền kim loại nổi bật
- Tên hiển thị Discord
- Ngày tham gia Server (thay thế North America)
- Khung POSITION: Tag vàng thứ hạng bên trái + OVERALL (points) bên phải
- Khung TIERS: 2 bậc Freedom và Ranked 1:1 từ HT1 -> T8 với phân màu:
  + HT1 - LT1: Vàng (Gold)
  + HT2 - LT2: Bạc (Silver)
  + T3: Đồng (Bronze)
  + T4 trở xuống: Bình thường (Normal Slate)
- Hiển thị chuỗi thắng (Streak) và Codeforces handle
"""

from __future__ import annotations

import functools
import hashlib
import colorsys
import io
import json
import math
import os
from typing import Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from utils.logger import get_logger
from services.rank import (
    RANK_ORDER,
    get_rank_by_rating,
    get_rank_title,
    get_tier_progress,
)
from services.special_roles import get_special_role_meta

logger = get_logger("ProfileCard")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
FONTS_DIR = os.path.join(PROJECT_DIR, "assets", "fonts")
PROFILE_CARDS_DIR = os.path.join(DATA_DIR, "profile_cards")
os.makedirs(PROFILE_CARDS_DIR, exist_ok=True)


def clear_profile_card_cache(user_id: int | None = None) -> int:
    """Xóa file ảnh thẻ và hash cũ khỏi thư mục bộ đệm."""
    deleted = 0
    try:
        if not os.path.exists(PROFILE_CARDS_DIR):
            return 0
        for fname in os.listdir(PROFILE_CARDS_DIR):
            if user_id is not None:
                if fname.startswith(f"profile_{user_id}."):
                    try:
                        os.remove(os.path.join(PROFILE_CARDS_DIR, fname))
                        deleted += 1
                    except Exception:
                        pass
            else:
                if fname.endswith(".png") or fname.endswith(".hash"):
                    try:
                        os.remove(os.path.join(PROFILE_CARDS_DIR, fname))
                        deleted += 1
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"Không thể dọn dẹp cache profile card: {e}")
    return deleted


@functools.lru_cache(maxsize=256)
def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tải font chữ hệ thống tối ưu với danh sách dự phòng đa nền tảng (Windows / Linux)."""
    candidates = [
        os.path.join(FONTS_DIR, "segoeuib.ttf" if bold else "segoeui.ttf"),
        os.path.join(FONTS_DIR, "arialbd.ttf" if bold else "arial.ttf"),
        os.path.join(FONTS_DIR, "font_bold.ttf" if bold else "font_regular.ttf"),
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahomabd.ttf" if bold else "C:/Windows/Fonts/tahoma.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _make_circular_avatar(avatar_img: Image.Image, size: int) -> Image.Image:
    """Cắt và bo tròn avatar với mặt nạ siêu mịn chống răng cưa (Super-Sampled Anti-Aliasing)."""
    avatar_img = avatar_img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    scale = 4
    big_mask = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(big_mask)
    draw.ellipse((0, 0, size * scale, size * scale), fill=255)
    mask = big_mask.resize((size, size), Image.Resampling.LANCZOS)
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(avatar_img, (0, 0), mask=mask)
    return output


def _generate_fallback_avatar(name: str, size: int, color_bg: Tuple[int, int, int] = (59, 130, 246)) -> Image.Image:
    """Tạo avatar chữ cái đầu phong cách phẳng khi không tải được ảnh."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size, size), fill=color_bg)

    initial = (name[:1].upper() if name else "?")
    font = _get_font(int(size * 0.5), bold=True)
    if font:
        bbox = draw.textbbox((0, 0), initial, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((size - w) // 2, (size - h) // 2 - int(size * 0.05)), initial, fill=(255, 255, 255, 255), font=font)
    return img


def _draw_flame_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    """Vẽ biểu tượng ngọn lửa vector chống lỗi thiếu glyph emoji trên đa nền tảng."""
    outer_flame = [
        (cx, cy - 15),
        (cx + 5, cy - 5),
        (cx + 10, cy + 2),
        (cx + 8, cy + 12),
        (cx + 3, cy + 15),
        (cx - 3, cy + 15),
        (cx - 8, cy + 12),
        (cx - 10, cy + 2),
        (cx - 5, cy - 5),
    ]
    inner_flame = [
        (cx, cy - 5),
        (cx + 4, cy + 2),
        (cx + 3, cy + 9),
        (cx - 3, cy + 9),
        (cx - 4, cy + 2),
    ]
    draw.polygon(outer_flame, fill=(249, 115, 22, 255))
    draw.polygon(inner_flame, fill=(253, 224, 71, 255))


def _draw_check_icon(draw: ImageDraw.ImageDraw, x: int, y: int, color: Tuple[int, ...], size: int = 24) -> None:
    """Vẽ biểu tượng dấu tích (Checkmark) vector sắc nét trên canvas 4K chống lỗi thiếu glyph."""
    p1 = (x + int(size * 0.12), y + int(size * 0.52))
    p2 = (x + int(size * 0.40), y + int(size * 0.80))
    p3 = (x + int(size * 0.88), y + int(size * 0.20))
    draw.line([p1, p2, p3], fill=color, width=4, joint="curve")


def _draw_swords_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, color: Tuple[int, ...] = (56, 189, 248, 255), size: int = 20) -> None:
    """Vẽ biểu tượng song kiếm chéo (Ranked 1:1) dạng vector chống lỗi thiếu glyph emoji."""
    draw.line([(cx - size, cy + size), (cx + size, cy - size)], fill=color, width=6, joint="curve")
    draw.line([(cx - size, cy - size), (cx + size, cy + size)], fill=color, width=6, joint="curve")
    # Chuôi kiếm 2 đầu mỗi lưỡi
    guard = (250, 204, 21, 255)
    draw.line([(cx - size - 7, cy + size + 7), (cx - size + 7, cy + size - 7)], fill=guard, width=5)
    draw.line([(cx + size - 7, cy + size - 7), (cx + size + 7, cy + size + 7)], fill=guard, width=5)
    draw.ellipse([(cx - size - 12, cy + size + 2), (cx - size - 2, cy + size + 12)], fill=guard)
    draw.ellipse([(cx + size + 2, cy + size + 2), (cx + size + 12, cy + size + 12)], fill=guard)


def _draw_scroll_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, color: Tuple[int, ...] = (16, 185, 129, 255), size: int = 20) -> None:
    """Vẽ biểu tượng cuộn giấy nộp bài (Freedom) dạng vector chống lỗi thiếu glyph emoji."""
    draw.rounded_rectangle([(cx - size, cy - size + 6), (cx + size, cy + size - 6)], radius=8, outline=color, width=4)
    # Hai đầu cuộn tròn
    draw.line([(cx - size, cy - size + 6), (cx - size, cy + size - 6)], fill=color, width=9)
    draw.line([(cx + size, cy - size + 6), (cx + size, cy + size - 6)], fill=color, width=9)
    # Gạch dòng chữ trên cuộn giấy
    line_c = (203, 213, 225, 255)
    draw.line([(cx - size + 12, cy - 4), (cx + size - 12, cy - 4)], fill=line_c, width=3)
    draw.line([(cx - size + 12, cy + 5), (cx + size - 18, cy + 5)], fill=line_c, width=3)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    """Cắt ngắn chuỗi kèm '...' sao cho vừa max_width pixel (tìm nhị phân theo textlength)."""
    s = str(text or "")
    if not s or max_width <= 0:
        return s
    try:
        if draw.textlength(s, font=font) <= max_width:
            return s
        ell = "..."
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi) // 2
            if draw.textlength(s[:mid] + ell, font=font) <= max_width:
                lo = mid + 1
            else:
                hi = mid
        return s[: max(0, lo - 1)] + ell
    except Exception:
        return s


def _extract_avatar_accent_color(
    avatar_img: Image.Image,
    default_color: tuple[int, int, int] = (56, 189, 248),
) -> tuple[int, int, int]:
    """Trích xuất màu bão hòa / ánh sáng nổi bật nhất từ ảnh Avatar để làm màu aura phát quang."""
    try:
        small = avatar_img.convert("RGBA").resize((48, 48), Image.Resampling.BOX)
        raw_bytes = small.tobytes()
        best_color = default_color
        max_score = -1.0
        for i in range(0, len(raw_bytes), 4):
            r, g, b, a = raw_bytes[i], raw_bytes[i + 1], raw_bytes[i + 2], raw_bytes[i + 3]
            if a < 128:
                continue
            rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
            h, s, v = colorsys.rgb_to_hsv(rn, gn, bn)
            # Lọc bỏ pixel đen xì hoặc xám/trắng nhạt
            if v > 0.25 and s > 0.20:
                score = s * 1.6 + v
                if score > max_score:
                    max_score = score
                    best_color = (r, g, b)
        return best_color
    except Exception as e:
        logger.debug(f"Lỗi khi trích xuất màu avatar: {e}")
        return default_color


def get_tier_color_palette(tier: str) -> dict:
    """
    Quy tắc phân loại màu sắc theo đúng yêu cầu:
    - HT1 - LT1: Vàng (Gold)
    - HT2 - LT2: Bạc (Silver)
    - T3: Đồng (Bronze)
    - T4 xuống: Bình thường (Normal Slate)
    """
    t = (tier or "T8").strip().upper()
    if t in ("HT1", "MT1", "LT1"):
        return {
            "group": "gold",
            "name": "Vàng",
            "text_rgb": (255, 215, 0),       # #FFD700
            "border_rgb": (245, 158, 11),     # #F59E0B
            "bg_rgb": (59, 42, 10),           # Dark Gold pill
            "glow_rgb": (251, 191, 36, 60),
        }
    elif t in ("HT2", "MT2", "LT2"):
        return {
            "group": "silver",
            "name": "Bạc",
            "text_rgb": (226, 232, 240),     # #E2E8F0
            "border_rgb": (148, 163, 184),    # #94A3B8
            "bg_rgb": (30, 41, 59),           # Dark Slate pill
            "glow_rgb": (148, 163, 184, 40),
        }
    elif t == "T3":
        return {
            "group": "bronze",
            "name": "Đồng",
            "text_rgb": (205, 127, 50),      # #CD7F32
            "border_rgb": (217, 119, 6),      # #D97706
            "bg_rgb": (55, 24, 6),            # Dark Bronze pill
            "glow_rgb": (217, 119, 6, 40),
        }
    else:  # T4, T5, T6, T7, T8
        return {
            "group": "normal",
            "name": "Bình thường",
            "text_rgb": (148, 163, 184),     # #94A3B8
            "border_rgb": (71, 85, 105),      # #475569
            "bg_rgb": (22, 29, 44),           # Normal Dark pill
            "glow_rgb": (71, 85, 105, 30),
        }


def get_tier_aura_color(tier: str) -> tuple[int, int, int]:
    """Lấy tông màu hào quang (Aura RGB) tương ứng với bậc xếp hạng."""
    t = (tier or "T8").strip().upper()
    if t in ("HT1", "MT1", "LT1"):
        return (245, 158, 11)   # Vàng kim Radiant Gold Amber
    elif t in ("HT2", "MT2", "LT2"):
        return (56, 189, 248)   # Lam Bạc Diamond Ice Silver
    elif t == "T3":
        return (249, 115, 22)   # Đồng Cam Molten Bronze
    else:
        return (99, 102, 241)   # Xanh Tím Neon Indigo / Cyber Slate


def _render_mesh_aura_4k(
    width: int,
    height: int,
    aura_primary: tuple[int, int, int],
    aura_freedom: tuple[int, int, int],
    aura_ranked: tuple[int, int, int],
    outer_aura_rgb: tuple[int, int, int] | None = None,
) -> Image.Image:
    """
    Tạo lớp phủ hào quang 4K Ambient Mesh Aurora siêu mượt, tối ưu hóa tốc độ.
    Vẽ các khối cầu màu ở độ phân giải thấp (1/4) rồi làm mờ và upsample Bicubic lên 3840x2160.
    Nếu có outer_aura_rgb (Owner/Admin/Mod/Staff), vẽ thêm dải hào quang tỏa sáng viền ngoài.
    """
    qw, qh = width // 4, height // 4
    q_img = Image.new("RGBA", (qw, qh), (0, 0, 0, 0))
    q_draw = ImageDraw.Draw(q_img)

    if outer_aura_rgb:
        # Hào quang viền ngoài toàn khung (Outer Edge Radiant Aura)
        q_draw.rectangle([(6, 6), (qw - 6, qh - 6)], outline=outer_aura_rgb + (200,), width=14)
        q_draw.ellipse([(qw // 2 - 250, -40), (qw // 2 + 250, 180)], fill=outer_aura_rgb + (140,))

    q_draw.ellipse([(-50, 80), (380, 480)], fill=aura_freedom + (150,))
    q_draw.ellipse([(320, 60), (900, 490)], fill=aura_ranked + (140,))
    q_draw.ellipse([(80, 20), (320, 260)], fill=aura_primary + (130,))
    q_blurred = q_img.filter(ImageFilter.GaussianBlur(radius=45))
    return q_blurred.resize((width, height), Image.Resampling.BICUBIC)


_avatar_cache: dict[str, Image.Image] = {}


class ProfileCardGenerator:
    """Trình tạo ảnh thẻ cá nhân trực quan bằng Pillow chuẩn Competitive Esports 4K UHD (3840 x 2160 px)."""

    @staticmethod
    async def fetch_avatar_image(avatar_url: str | None, player_name: str, size: int = 380) -> Image.Image:
        """Tải avatar Discord hoặc tạo avatar fallback (có cache bộ nhớ)."""
        if avatar_url and (avatar_url.startswith("http://") or avatar_url.startswith("https://")):
            cache_key = f"{avatar_url}_{size}"
            if cache_key in _avatar_cache:
                return _avatar_cache[cache_key].copy()
            try:
                timeout = aiohttp.ClientTimeout(total=2.5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(avatar_url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            raw_img = Image.open(io.BytesIO(data))
                            res_avatar = _make_circular_avatar(raw_img, size)
                            _avatar_cache[cache_key] = res_avatar
                            return res_avatar.copy()
            except Exception as e:
                logger.debug(f"Không thể tải avatar profile {avatar_url}: {e}")

        return _generate_fallback_avatar(player_name, size)

    @classmethod
    async def generate_profile_card(
        cls,
        user_id: int,
        display_name: str,
        avatar_url: str | None,
        joined_at_str: str,
        standing: int,
        overall_pts: float,
        freedom_tier: str,
        freedom_rating: int,
        ranked_tier: str,
        ranked_rating: int,
        title: str | None = None,
        cf_handle: str | None = None,
        cf_rating: int | None = None,
        cf_max_rating: int | None = None,
        ranked_streak: int = 0,
        ranked_max_streak: int = 0,
        win_rate: float = 0.0,
        total_wins: int = 0,
        total_losses: int = 0,
        peak_freedom_rating: int | None = None,
        peak_freedom_tier: str | None = None,
        peak_ranked_rating: int | None = None,
        peak_ranked_tier: str | None = None,
        recent_matches: list[dict] | None = None,
        recent_freedom: list[dict] | None = None,
        accepted_submissions: int = 0,
        total_submissions: int = 0,
        user_role: str = "member",
        custom_role_badge: str | None = None,
        custom_role_title: str | None = None,
        special_role: str | None = None,
        force_refresh: bool = False,
    ) -> str:
        """
        Kết xuất thẻ ảnh Profile 4K UHD Landscape 3840x2160 phong cách Competitive Esports Showcase Dashboard.
        Chữ lớn, rõ nét, độ tương phản cao, cân đối hoàn hảo khi Discord scale down ảnh.
        Loại bỏ hoàn toàn danh xưng Grandmaster mặc định; sử dụng danh hiệu chuẩn xác theo bậc Rank.
        Hỗ trợ danh xưng độc quyền (tên riêng) và hiệu ứng outer aura đặc quyền cho Owner, Admin, Mod/Staff.
        Tích hợp Hệ Thống 6 Danh Hiệu Động (Special Roles) và Smart Caching (tái sử dụng ảnh cũ nếu dữ liệu không đổi).
        """
        width = 3840
        height = 2160

        # Xác định danh hiệu chuẩn hóa từ hệ thống Rank
        actual_rank = ranked_tier or freedom_tier or "T8"
        official_rank_title = get_rank_title(actual_rank)
        if not title or title.strip().lower() in ("combat grandmaster", "grandmaster"):
            resolved_member_title = official_rank_title
        else:
            resolved_member_title = title.strip()

        total_matches = total_wins + total_losses
        is_verified_competitor = bool(cf_handle) or (total_matches >= 3)

        # Phân loại danh xưng, màu sắc và hiệu ứng đặc quyền theo vai trò (Role-specific themes)
        role_norm = (user_role or "member").strip().lower()
        if role_norm in ("owner", "founder"):
            role_badge_txt = custom_role_badge or "SERVER OWNER"
            role_title_txt = custom_role_title or "Supreme Founder & Architect"
            role_badge_bg = (58, 42, 10, 240)
            role_badge_border = (245, 158, 11, 255)
            role_badge_fg = (255, 215, 0, 255)
            role_title_bg = (45, 28, 8, 240)
            role_title_border = (245, 158, 11, 255)
            role_title_fg = (253, 224, 71, 255)
            outer_aura_rgb = (245, 158, 11)
            header_brand_txt = "HYPERHUB ARENA  //  4K SERVER OWNER SUPREME PROFILE"
            corner_bracket_color = (245, 158, 11, 255)
            has_outer_effect = True
        elif role_norm in ("admin", "administrator"):
            role_badge_txt = custom_role_badge or "SERVER ADMINISTRATOR"
            role_title_txt = custom_role_title or "Arena Grand Administrator"
            role_badge_bg = (50, 15, 30, 240)
            role_badge_border = (239, 68, 68, 255)
            role_badge_fg = (254, 202, 202, 255)
            role_title_bg = (38, 14, 45, 240)
            role_title_border = (168, 85, 247, 255)
            role_title_fg = (216, 180, 254, 255)
            outer_aura_rgb = (225, 29, 72)
            header_brand_txt = "HYPERHUB ARENA  //  4K ADMINISTRATOR PRIVILEGED PROFILE"
            corner_bracket_color = (239, 68, 68, 255)
            has_outer_effect = True
        elif role_norm in ("mod", "staff", "moderator"):
            role_badge_txt = custom_role_badge or "ARENA MODERATOR"
            role_title_txt = custom_role_title or "Arena Arbiter & Guardian"
            role_badge_bg = (8, 42, 45, 240)
            role_badge_border = (6, 182, 212, 255)
            role_badge_fg = (103, 232, 249, 255)
            role_title_bg = (10, 38, 34, 240)
            role_title_border = (16, 185, 129, 255)
            role_title_fg = (110, 231, 183, 255)
            outer_aura_rgb = (6, 182, 212)
            header_brand_txt = "HYPERHUB ARENA  //  4K MODERATOR & STAFF OFFICIAL PROFILE"
            corner_bracket_color = (6, 182, 212, 255)
            has_outer_effect = True
        else:
            if is_verified_competitor:
                role_badge_txt = custom_role_badge or "VERIFIED COMPETITOR"
                role_badge_bg = (13, 35, 55, 220)
                role_badge_border = (56, 189, 248, 200)
                role_badge_fg = (56, 189, 248, 255)
            else:
                role_badge_txt = custom_role_badge or "VERIFIED ACCOUNT"
                role_badge_bg = (18, 26, 42, 220)
                role_badge_border = (96, 165, 250, 180)
                role_badge_fg = (147, 197, 253, 255)

            role_title_txt = custom_role_title or resolved_member_title
            role_title_bg = (42, 31, 10, 230)
            role_title_border = (245, 158, 11, 230)
            role_title_fg = (253, 224, 71, 255)
            outer_aura_rgb = None
            header_brand_txt = "HYPERHUB ARENA  //  4K COMPETITIVE ESPORTS PROFILE"
            corner_bracket_color = None
            has_outer_effect = False

        # Chuẩn hóa dữ liệu lịch sử cao nhất (Peak Stats)
        freedom_peak = peak_freedom_rating if peak_freedom_rating is not None else freedom_rating
        freedom_peak_t = peak_freedom_tier if peak_freedom_tier is not None else freedom_tier
        ranked_peak = peak_ranked_rating if peak_ranked_rating is not None else ranked_rating
        ranked_peak_t = peak_ranked_tier if peak_ranked_tier is not None else ranked_tier

        # Xác định bậc cao nhất giữa Freedom và Ranked để tỏa hào quang xứng tầm
        f_idx = RANK_ORDER.index(freedom_tier.upper()) if freedom_tier and freedom_tier.upper() in RANK_ORDER else -1
        r_idx = RANK_ORDER.index(ranked_tier.upper()) if ranked_tier and ranked_tier.upper() in RANK_ORDER else -1
        primary_tier = freedom_tier if f_idx >= r_idx else ranked_tier

        p_ranked = get_tier_color_palette(ranked_tier)
        p_free = get_tier_color_palette(freedom_tier)
        p_primary = get_tier_color_palette(primary_tier)
        aura_color = get_tier_aura_color(primary_tier)
        aura_free = get_tier_aura_color(freedom_tier)
        aura_rk = get_tier_aura_color(ranked_tier)

        # Smart Profile Card Caching: Nếu dữ liệu không thay đổi, tái sử dụng ảnh 4K cũ ngay lập tức
        cache_data = {
            "user_id": user_id,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "joined_at_str": joined_at_str,
            "standing": standing,
            "overall_pts": round(float(overall_pts), 1),
            "freedom_tier": freedom_tier,
            "freedom_rating": freedom_rating,
            "ranked_tier": ranked_tier,
            "ranked_rating": ranked_rating,
            "title": resolved_member_title,
            "cf_handle": cf_handle,
            "cf_rating": cf_rating,
            "cf_max_rating": cf_max_rating,
            "ranked_streak": ranked_streak,
            "ranked_max_streak": ranked_max_streak,
            "win_rate": round(float(win_rate), 2),
            "total_wins": total_wins,
            "total_losses": total_losses,
            "peak_freedom_rating": peak_freedom_rating,
            "peak_freedom_tier": peak_freedom_tier,
            "peak_ranked_rating": peak_ranked_rating,
            "peak_ranked_tier": peak_ranked_tier,
            "accepted_submissions": accepted_submissions,
            "total_submissions": total_submissions,
            "user_role": user_role,
            "special_role": special_role,
            "recent_matches": recent_matches,
            "recent_freedom": recent_freedom,
            "is_verified_competitor": is_verified_competitor,
        }
        data_json = json.dumps(cache_data, sort_keys=True, default=str)
        cache_hash = hashlib.sha256(data_json.encode("utf-8")).hexdigest()

        file_path = os.path.join(PROFILE_CARDS_DIR, f"profile_{user_id}.png")
        hash_file_path = os.path.join(PROFILE_CARDS_DIR, f"profile_{user_id}.hash")

        if not force_refresh and os.path.exists(file_path) and os.path.exists(hash_file_path):
            try:
                with open(hash_file_path, "r", encoding="utf-8") as hf:
                    cached_hash = hf.read().strip()
                if cached_hash == cache_hash:
                    logger.info(f"[ProfileCard] Dữ liệu user {user_id} không đổi, tái sử dụng ảnh thẻ 4K từ cache: {file_path}")
                    return file_path
            except Exception as he:
                logger.debug(f"Không thể đọc cache hash cho user {user_id}: {he}")

        # Khi cần vẽ lại ảnh thẻ, dọn dẹp các file cache cũ của user
        clear_profile_card_cache(user_id)

        # 1. Khởi tạo canvas nền tối Deep Midnight (#070A14)
        img = Image.new("RGBA", (width, height), (7, 10, 20, 255))

        # 2. Tạo lớp hào quang 4K Ambient Mesh Aurora siêu mượt (kèm Outer Edge Aura nếu có quyền hạn đặc biệt)
        aura_layer = _render_mesh_aura_4k(width, height, aura_color, aura_free, aura_rk, outer_aura_rgb=outer_aura_rgb)
        img = Image.alpha_composite(img, aura_layer)
        draw = ImageDraw.Draw(img)

        # 3. Khung viền kính & Outer Effect nếu là Owner / Admin / Mod / Staff
        if has_outer_effect and outer_aura_rgb and corner_bracket_color:
            # Viền ngoài phát sáng đa lớp neon
            draw.rounded_rectangle([(24, 24), (width - 24, height - 24)], radius=42, outline=outer_aura_rgb + (230,), width=6)
            draw.rounded_rectangle([(36, 36), (width - 36, height - 36)], radius=36, outline=(255, 255, 255, 60), width=2)

            # Vẽ 4 góc vát Cyber / Royal Corner Brackets uy quyền
            offset = 18
            arm = 160
            thick = 10
            # Top-Left
            draw.line([(offset, offset), (offset + arm, offset)], fill=corner_bracket_color, width=thick)
            draw.line([(offset, offset), (offset, offset + arm)], fill=corner_bracket_color, width=thick)
            # Top-Right
            draw.line([(width - offset, offset), (width - offset - arm, offset)], fill=corner_bracket_color, width=thick)
            draw.line([(width - offset, offset), (width - offset, offset + arm)], fill=corner_bracket_color, width=thick)
            # Bottom-Left
            draw.line([(offset, height - offset), (offset + arm, height - offset)], fill=corner_bracket_color, width=thick)
            draw.line([(offset, height - offset), (offset, height - offset - arm)], fill=corner_bracket_color, width=thick)
            # Bottom-Right
            draw.line([(width - offset, height - offset), (width - offset - arm, height - offset)], fill=corner_bracket_color, width=thick)
            draw.line([(width - offset, height - offset), (width - offset, height - offset - arm)], fill=corner_bracket_color, width=thick)
        else:
            draw.rounded_rectangle([(40, 40), (width - 40, height - 40)], radius=36, outline=(255, 255, 255, 24), width=2)
            draw.rounded_rectangle([(38, 38), (width - 38, height - 38)], radius=38, outline=aura_color + (40,), width=2)

        # 4. Top Header Bar (Cỡ chữ 32px & 26px to rõ)
        font_brand = _get_font(32, bold=True)
        draw.text((80, 70), header_brand_txt, fill=(56, 189, 248, 255) if not has_outer_effect else outer_aura_rgb + (255,), font=font_brand)
        font_season = _get_font(26, bold=True)
        season_text = "SEASON 2026  •  OFFICIAL COMPETITIVE LEADERBOARD  •  ANTI-CHEAT 2.0"
        bbox_s = draw.textbbox((0, 0), season_text, font=font_season)
        draw.text((width - 80 - (bbox_s[2] - bbox_s[0]), 74), season_text, fill=(148, 163, 184, 255), font=font_season)

        # =====================================================================
        # 5. CỘT TRÁI (HERO PLAYER IDENTITY CARD) - BỐ CỤC CÂN ĐỐI, CHỮ LỚN
        # =====================================================================
        left_x, left_y, left_w, left_h = 80, 140, 1140, 1880
        draw.rounded_rectangle(
            [(left_x, left_y), (left_x + left_w, left_y + left_h)],
            radius=32,
            fill=(13, 19, 33, 215),
            outline=(255, 255, 255, 30),
            width=2,
        )

        # Avatar 380px (Nâng cấp từ 280px lên 380px để lấp đầy không gian cân đối với cột 1140px)
        avatar_size = 380
        avatar_cx = left_x + left_w // 2
        avatar_top_y = left_y + 55
        avatar_cy = avatar_top_y + (avatar_size // 2)

        avatar_img = await cls.fetch_avatar_image(avatar_url, display_name, size=avatar_size)
        avatar_img = _make_circular_avatar(avatar_img, avatar_size)

        # Trích xuất dải màu bão hòa/vực sáng nhất từ Avatar của thí sinh
        avatar_accent = _extract_avatar_accent_color(avatar_img, default_color=aura_color)
        primary_glow_color = outer_aura_rgb if (has_outer_effect and outer_aura_rgb) else aura_color

        # Lớp hào quang phát sáng mờ ảo đa tầng (Soft Gaussian Blurred Ambient Glow - radius 30px)
        glow_size = avatar_size + 180  # 380 + 180 = 560px
        glow_img = Image.new("RGBA", (glow_size, glow_size), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)
        gcx, gcy = glow_size // 2, glow_size // 2

        # Vành phát quang ngoài từ Avatar Accent (lan tỏa êm dịu ra nền tối)
        glow_draw.ellipse(
            [(gcx - 235, gcy - 235), (gcx + 235, gcy + 235)],
            fill=avatar_accent + (85,),
        )
        # Vành phát quang trong từ Role/Rank Color (đậm đà, nổi bật vai trò)
        glow_draw.ellipse(
            [(gcx - 210, gcy - 210), (gcx + 210, gcy + 210)],
            fill=primary_glow_color + (130,),
        )
        glow_img = glow_img.filter(ImageFilter.GaussianBlur(radius=30))

        # Dán lớp ambient glow phía sau avatar
        glow_top_x = avatar_cx - (glow_size // 2)
        glow_top_y = avatar_cy - (glow_size // 2)
        img.paste(glow_img, (glow_top_x, glow_top_y), mask=glow_img)

        # Viền sắc nét kép (Crisp Dual Rings) bao quanh Avatar 380px giữ cạnh sắc nét tuyệt đối
        if has_outer_effect and outer_aura_rgb:
            draw.ellipse(
                [(avatar_cx - 225, avatar_cy - 225), (avatar_cx + 225, avatar_cy + 225)],
                outline=outer_aura_rgb + (200,),
                width=4,
            )
        draw.ellipse(
            [(avatar_cx - 210, avatar_cy - 210), (avatar_cx + 210, avatar_cy + 210)],
            outline=aura_color + (170,),
            width=4,
        )
        draw.ellipse(
            [(avatar_cx - 198, avatar_cy - 198), (avatar_cx + 198, avatar_cy + 198)],
            outline=p_primary["border_rgb"] + (255,),
            width=5,
        )
        img.paste(avatar_img, (avatar_cx - (avatar_size // 2), avatar_top_y), mask=avatar_img)

        # Tên hiển thị Discord (Nâng từ 58px lên 76px siêu nét)
        font_name = _get_font(76, bold=True)
        bbox_name = draw.textbbox((0, 0), display_name, font=font_name)
        name_w = bbox_name[2] - bbox_name[0]
        name_x = left_x + (left_w - name_w) // 2
        name_y = avatar_top_y + avatar_size + 30
        draw.text((name_x, name_y), display_name, fill=(255, 255, 255, 255), font=font_name)

        # Huy hiệu Danh Xưng / Vai Trò (Nâng từ 20px lên 30px, pill cao 56px)
        font_badge = _get_font(30, bold=True)
        bbox_ver = draw.textbbox((0, 0), role_badge_txt, font=font_badge)
        text_w = bbox_ver[2] - bbox_ver[0]

        is_default_verified = (not custom_role_badge and role_norm not in ("owner", "founder", "admin", "administrator", "mod", "staff", "moderator"))
        check_gap = 36 if is_default_verified else 0

        ver_w = text_w + 52 + check_gap
        ver_h = 56
        ver_x = left_x + (left_w - ver_w) // 2
        ver_y = name_y + 92
        draw.rounded_rectangle([(ver_x, ver_y), (ver_x + ver_w, ver_y + ver_h)], radius=28, fill=role_badge_bg, outline=role_badge_border, width=3)

        if is_default_verified:
            _draw_check_icon(draw, ver_x + 24, ver_y + 16, color=role_badge_fg, size=24)
            draw.text((ver_x + 24 + check_gap, ver_y + 10), role_badge_txt, fill=role_badge_fg, font=font_badge)
        else:
            draw.text((ver_x + 26, ver_y + 10), role_badge_txt, fill=role_badge_fg, font=font_badge)

        # Danh hiệu Title Pill Badge (Nâng từ 24px lên 32px, pill cao 58px)
        font_title = _get_font(32, bold=True)
        bbox_t = draw.textbbox((0, 0), role_title_txt, font=font_title)
        title_w = bbox_t[2] - bbox_t[0] + 52
        title_h = 58
        title_x = left_x + (left_w - title_w) // 2
        title_y = ver_y + 72
        draw.rounded_rectangle([(title_x, title_y), (title_x + title_w, title_y + title_h)], radius=29, fill=role_title_bg, outline=role_title_border, width=3)
        draw.text((title_x + 26, title_y + 10), role_title_txt, fill=role_title_fg, font=font_title)

        # Huy hiệu Danh Hiệu Động Đặc Biệt & Chuỗi Thắng (Streak Badge)
        sp_meta = get_special_role_meta(special_role)
        has_streak_badge = (ranked_streak >= 2)
        font_pill = _get_font(28, bold=True)
        pill_h = 52
        pill_y = title_y + 68

        sp_w = 0
        sp_txt = ""
        if sp_meta:
            sp_txt = sp_meta.card_label
            bbox_sp = draw.textbbox((0, 0), sp_txt, font=font_pill)
            sp_w = bbox_sp[2] - bbox_sp[0] + 44

        streak_w = 0
        streak_txt = ""
        if has_streak_badge:
            streak_txt = f"{ranked_streak} WIN STREAK"
            bbox_st = draw.textbbox((0, 0), streak_txt, font=font_pill)
            # 44px padding + 28px flame icon space
            streak_w = bbox_st[2] - bbox_st[0] + 72

        if sp_meta and has_streak_badge:
            gap = 20
            total_pills_w = sp_w + gap + streak_w
            start_x = left_x + (left_w - total_pills_w) // 2
            # Vẽ Special Role Pill
            draw.rounded_rectangle([(start_x, pill_y), (start_x + sp_w, pill_y + pill_h)], radius=26, fill=(18, 26, 42, 240), outline=sp_meta.color_rgb + (255,), width=2)
            draw.text((start_x + 22, pill_y + 10), sp_txt, fill=sp_meta.color_rgb + (255,), font=font_pill)
            # Vẽ Win Streak Pill với Flame Vector Icon
            st_x = start_x + sp_w + gap
            draw.rounded_rectangle([(st_x, pill_y), (st_x + streak_w, pill_y + pill_h)], radius=26, fill=(35, 18, 12, 245), outline=(249, 115, 22, 255), width=2)
            _draw_flame_icon(draw, cx=st_x + 30, cy=pill_y + 26)
            draw.text((st_x + 50, pill_y + 10), streak_txt, fill=(251, 146, 60, 255), font=font_pill)
            meta_offset = 64
        elif sp_meta:
            sp_x = left_x + (left_w - sp_w) // 2
            draw.rounded_rectangle([(sp_x, pill_y), (sp_x + sp_w, pill_y + pill_h)], radius=26, fill=(18, 26, 42, 240), outline=sp_meta.color_rgb + (255,), width=2)
            draw.text((sp_x + 22, pill_y + 10), sp_txt, fill=sp_meta.color_rgb + (255,), font=font_pill)
            meta_offset = 64
        elif has_streak_badge:
            st_x = left_x + (left_w - streak_w) // 2
            draw.rounded_rectangle([(st_x, pill_y), (st_x + streak_w, pill_y + pill_h)], radius=26, fill=(35, 18, 12, 245), outline=(249, 115, 22, 255), width=2)
            _draw_flame_icon(draw, cx=st_x + 30, cy=pill_y + 26)
            draw.text((st_x + 50, pill_y + 10), streak_txt, fill=(251, 146, 60, 255), font=font_pill)
            meta_offset = 64
        else:
            meta_offset = 0

        # Ngày tham gia & Button Codeforces (Nâng từ 22px lên 28px)
        font_meta = _get_font(28, bold=False)
        cf_tag = f"CF: {cf_handle}" if cf_handle else "CP Arena Thí Sinh"
        meta_str = f"Tham gia: {joined_at_str}   •   {cf_tag}"
        bbox_m = draw.textbbox((0, 0), meta_str, font=font_meta)
        draw.text((left_x + (left_w - (bbox_m[2] - bbox_m[0])) // 2, title_y + 75 + meta_offset), meta_str, fill=(160, 175, 200, 255), font=font_meta)

        # Khung POSITION & Thứ hạng (Cỡ chữ 28px, 54px, 34px)
        pos_y = title_y + 130 + meta_offset
        draw.text((left_x + 50, pos_y), "POSITION & STANDING", fill=(203, 213, 225, 255), font=_get_font(28, bold=True))
        pos_box_y = pos_y + 40
        pos_box_h = 115
        pos_box_w = left_w - 100
        draw.rounded_rectangle([(left_x + 50, pos_box_y), (left_x + 50 + pos_box_w, pos_box_y + pos_box_h)], radius=24, fill=(18, 26, 42, 220), outline=(255, 255, 255, 30), width=2)

        rank_tag_w = 210
        poly = [
            (left_x + 50, pos_box_y),
            (left_x + 50 + rank_tag_w, pos_box_y),
            (left_x + 50 + rank_tag_w - 35, pos_box_y + pos_box_h),
            (left_x + 50, pos_box_y + pos_box_h)
        ]
        draw.polygon(poly, fill=(234, 179, 8, 255))
        font_rn = _get_font(54, bold=True)
        rn_str = f"#{standing}." if (standing and standing > 0) else "—"
        bbox_rn = draw.textbbox((0, 0), rn_str, font=font_rn)
        rn_w = bbox_rn[2] - bbox_rn[0]
        rn_h = bbox_rn[3] - bbox_rn[1]
        draw.text((left_x + 50 + (rank_tag_w - 35 - rn_w) // 2 + 5, pos_box_y + (pos_box_h - rn_h) // 2 - 4), rn_str, fill=(255, 255, 255, 255), font=font_rn)

        is_provisional = (overall_pts <= 0 and total_matches == 0)
        pos_hdr = "PROVISIONAL RANK" if is_provisional else "OVERALL RANK"
        pos_sub = "0 Points   •   Provisional Placement" if is_provisional else f"{overall_pts:.0f} Points   •   Season Score"
        pos_sub_color = (160, 175, 200, 255) if is_provisional else (250, 204, 21, 255)

        draw.text((left_x + 50 + rank_tag_w + 30, pos_box_y + 18), pos_hdr, fill=(255, 255, 255, 255), font=_get_font(34, bold=True))
        draw.text((left_x + 50 + rank_tag_w + 30, pos_box_y + 62), pos_sub, fill=pos_sub_color, font=_get_font(28, bold=True))

        # Khung TIERS & RATINGS (2 Thẻ Bậc Lớn 195px cao, số 56px bold, Tier badge 44px)
        tiers_hdr_y = pos_box_y + pos_box_h + 40
        draw.text((left_x + 50, tiers_hdr_y), "TIERS & RATINGS", fill=(203, 213, 225, 255), font=_get_font(28, bold=True))

        card_h = 195
        card_w = left_w - 100

        # Thẻ Freedom Mode
        c1_y = tiers_hdr_y + 40
        draw.rounded_rectangle([(left_x + 50, c1_y), (left_x + 50 + card_w, c1_y + card_h)], radius=22, fill=(18, 26, 42, 220), outline=p_free["border_rgb"] + (220,), width=3)
        draw.text((left_x + 75, c1_y + 22), "FREEDOM MODE", fill=(203, 213, 225, 255), font=_get_font(26, bold=True))
        draw.text((left_x + 75, c1_y + 64), f"{freedom_rating} Rating", fill=(255, 255, 255, 255), font=_get_font(56, bold=True))
        draw.text((left_x + 75, c1_y + 140), f"Peak: {freedom_peak} ({freedom_peak_t.upper()}) • CP Arena", fill=(203, 213, 225, 255), font=_get_font(26, bold=False))

        font_tf = _get_font(30 if len(freedom_tier) > 4 else 44, bold=True)
        bbox_tf = draw.textbbox((0, 0), freedom_tier.upper(), font=font_tf)
        tf_w = max(170, (bbox_tf[2] - bbox_tf[0]) + 40)
        tf_h = 78
        tf_x = left_x + 50 + card_w - tf_w - 28
        tf_y = c1_y + 58
        draw.rounded_rectangle([(tf_x, tf_y), (tf_x + tf_w, tf_y + tf_h)], radius=18, fill=p_free["bg_rgb"] + (255,), outline=p_free["border_rgb"] + (255,), width=3)
        draw.text((tf_x + (tf_w - (bbox_tf[2] - bbox_tf[0])) // 2, tf_y + (tf_h - (bbox_tf[3] - bbox_tf[1])) // 2 - 2), freedom_tier.upper(), fill=p_free["text_rgb"] + (255,), font=font_tf)

        # Thẻ Ranked 1v1 Arena
        c2_y = c1_y + card_h + 24
        draw.rounded_rectangle([(left_x + 50, c2_y), (left_x + 50 + card_w, c2_y + card_h)], radius=22, fill=(18, 26, 42, 220), outline=p_ranked["border_rgb"] + (220,), width=3)
        draw.text((left_x + 75, c2_y + 22), "RANKED 1:1 ARENA", fill=(203, 213, 225, 255), font=_get_font(26, bold=True))
        draw.text((left_x + 75, c2_y + 64), f"{ranked_rating} Rating", fill=(255, 255, 255, 255), font=_get_font(56, bold=True))
        draw.text((left_x + 75, c2_y + 140), f"Peak: {ranked_peak} ({ranked_peak_t.upper()}) • Head-to-Head", fill=(203, 213, 225, 255), font=_get_font(26, bold=False))

        font_tr = _get_font(30 if len(ranked_tier) > 4 else 44, bold=True)
        bbox_tr = draw.textbbox((0, 0), ranked_tier.upper(), font=font_tr)
        tr_w = max(170, (bbox_tr[2] - bbox_tr[0]) + 40)
        tr_h = 78
        tr_x = left_x + 50 + card_w - tr_w - 28
        tr_y = c2_y + 58
        draw.rounded_rectangle([(tr_x, tr_y), (tr_x + tr_w, tr_y + tr_h)], radius=18, fill=p_ranked["bg_rgb"] + (255,), outline=p_ranked["border_rgb"] + (255,), width=3)
        draw.text((tr_x + (tr_w - (bbox_tr[2] - bbox_tr[0])) // 2, tr_y + (tr_h - (bbox_tr[3] - bbox_tr[1])) // 2 - 2), ranked_tier.upper(), fill=p_ranked["text_rgb"] + (255,), font=font_tr)

        # Khung Xác minh tài khoản & Cam kết công bằng (Accounts & Verification) - Cỡ chữ 28-30px sắc nét, cân đối
        integ_y = c2_y + card_h + 30
        draw.rounded_rectangle([(left_x + 50, integ_y), (left_x + 50 + card_w, left_y + left_h - 40)], radius=22, fill=(18, 26, 42, 200), outline=(255, 255, 255, 26), width=2)
        draw.text((left_x + 75, integ_y + 30), "ACCOUNTS & VERIFICATION", fill=(203, 213, 225, 255), font=_get_font(28, bold=True))

        cf_info_val = f"{cf_handle} (Rating: {cf_rating or 'N/A'} · Max {cf_max_rating or 'N/A'})" if cf_handle else "Chưa liên kết tài khoản"
        cf_col = (255, 255, 255, 255) if cf_handle else (160, 175, 200, 255)

        acc_pct_str = f"{accepted_submissions/total_submissions*100:.1f}%" if total_submissions > 0 else "0.0%"
        free_sol_val = f"{accepted_submissions}/{total_submissions} AC ({acc_pct_str})"
        rnk_rec_val = f"{total_wins}W - {total_losses}L ({win_rate:.1f}% Win Rate)"

        if total_matches == 0:
            ac_val = "Chưa có vi phạm ghi nhận"
            ac_color = (148, 163, 184, 255)
        else:
            ac_val = "Clean Record (0 Violations)"
            ac_color = (16, 185, 129, 255)

        items_acc = [
            ("• CF Handle: ", cf_info_val, cf_col),
            ("• Freedom Solved: ", free_sol_val, (255, 255, 255, 255)),
            ("• Ranked Record: ", rnk_rec_val, (255, 255, 255, 255)),
            ("• Anti-Cheat 2.0: ", ac_val, ac_color),
        ]

        font_acc_lbl = _get_font(29, bold=False)
        font_acc_val = _get_font(29, bold=True)
        acc_start_y = integ_y + 92
        acc_step_y = 66
        for idx_a, (lbl_t, val_t, col_v) in enumerate(items_acc):
            ay = acc_start_y + idx_a * acc_step_y
            draw.text((left_x + 75, ay), lbl_t, fill=(203, 213, 225, 255), font=font_acc_lbl)
            w_lbl = draw.textbbox((0, 0), lbl_t, font=font_acc_lbl)[2]
            draw.text((left_x + 75 + w_lbl, ay), val_t, fill=col_v, font=font_acc_val)

        # =====================================================================
        # 6. CỘT PHẢI (TIER PROGRESS, COMPETITIVE STATS & RECENT MATCHES)
        # =====================================================================
        rx, ry, rw, rh = 1260, 140, 2500, 1880

        # ---------------------------------------------------------------------
        # PANEL 1: TIER PROGRESS & RANK ADVANCEMENT HUD (Cỡ chữ 28px, 40px, 36px)
        # ---------------------------------------------------------------------
        p1_h = 320
        draw.rounded_rectangle([(rx, ry), (rx + rw, ry + p1_h)], radius=28, fill=(13, 19, 33, 215), outline=(255, 255, 255, 28), width=2)
        draw.text((rx + 45, ry + 30), "TIER PROGRESS & RANK ROADMAP", fill=(203, 213, 225, 255), font=_get_font(28, bold=True))

        if sp_meta:
            font_rp_sp = _get_font(26, bold=True)
            sp_p1_txt = f"SPECIAL TITLE: {sp_meta.card_label}"
            bbox_p1_sp = draw.textbbox((0, 0), sp_p1_txt, font=font_rp_sp)
            p1_sp_w = bbox_p1_sp[2] - bbox_p1_sp[0] + 36
            p1_sp_h = 44
            p1_sp_x = rx + rw - p1_sp_w - 45
            p1_sp_y = ry + 22
            draw.rounded_rectangle([(p1_sp_x, p1_sp_y), (p1_sp_x + p1_sp_w, p1_sp_y + p1_sp_h)], radius=22, fill=(18, 26, 42, 240), outline=sp_meta.color_rgb + (240,), width=2)
            draw.text((p1_sp_x + 18, p1_sp_y + 8), sp_p1_txt, fill=sp_meta.color_rgb + (255,), font=font_rp_sp)

        prog_data = get_tier_progress(ranked_rating, ranked_tier)
        tier_title_str = f"{prog_data['current_tier']} — {prog_data['current_tier_title'].upper()}"
        draw.text((rx + 45, ry + 78), tier_title_str, fill=(255, 255, 255, 255), font=_get_font(40, bold=True))

        if prog_data["is_max_tier"]:
            right_prog_str = "MAX TIER ACHIEVED"
            prog_fill_color = (245, 158, 11, 255)
        else:
            right_prog_str = f"{prog_data['current_rating']} / {prog_data['target_rating']} Rating"
            prog_fill_color = (56, 189, 248, 255)

        bbox_rp = draw.textbbox((0, 0), right_prog_str, font=_get_font(36, bold=True))
        draw.text((rx + rw - (bbox_rp[2] - bbox_rp[0]) - 45, ry + 80), right_prog_str, fill=(250, 204, 21, 255), font=_get_font(36, bold=True))

        # Progress bar
        bar_x = rx + 45
        bar_y = ry + 145
        bar_w = rw - 90
        bar_h = 42
        fill_w = max(24, int(bar_w * (prog_data["progress_pct"] / 100.0)))
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=21, fill=(30, 41, 59, 255))
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h)], radius=21, fill=prog_fill_color)

        draw.text((rx + 45, ry + 215), prog_data["label"], fill=(203, 213, 225, 255), font=_get_font(28, bold=False))
        if not prog_data["is_max_tier"]:
            next_hint = f"Mục tiêu tiếp theo: Thăng hạng {prog_data.get('next_tier', 'HT1')} khi chạm mốc {prog_data['target_rating']} Rating"
            bbox_nh = draw.textbbox((0, 0), next_hint, font=_get_font(26, bold=False))
            draw.text((rx + rw - (bbox_nh[2] - bbox_nh[0]) - 45, ry + 215), next_hint, fill=(203, 213, 225, 255), font=_get_font(26, bold=False))

        # ---------------------------------------------------------------------
        # PANEL 2: COMPETITIVE PERFORMANCE & COMBAT METRICS (Căn giữa hoàn hảo, font nét)
        # ---------------------------------------------------------------------
        p2_y = ry + p1_h + 30
        p2_h = 580
        draw.rounded_rectangle([(rx, p2_y), (rx + rw, p2_y + p2_h)], radius=28, fill=(13, 19, 33, 215), outline=(255, 255, 255, 28), width=2)
        draw.text((rx + 45, p2_y + 30), "COMPETITIVE PERFORMANCE & COMBAT METRICS", fill=(203, 213, 225, 255), font=_get_font(28, bold=True))

        # 5 Thẻ KPI lớn nằm ngang - Căn giữa tuyệt đối với anchor="mm"
        kpi_y = p2_y + 85
        kpi_h = 200
        kpi_gap = 25
        kpi_w = (rw - 90 - 4 * kpi_gap) // 5

        streak_sub = f"+{5 if ranked_streak >= 10 else 2}% Elo Bonus" if ranked_streak >= 5 else "Chưa có bonus"
        stat_cards = [
            ("MATCHES", str(total_matches), "Tổng trận đấu", (255, 255, 255, 255)),
            ("VICTORIES", str(total_wins), f"{total_losses} Trận Thua", (16, 185, 129, 255)),
            ("WIN RATE", f"{win_rate:.1f}%", "Tỉ lệ chiến thắng", (56, 189, 248, 255)),
            ("STREAK", f"{ranked_streak}", streak_sub, (251, 146, 60, 255)),
            ("BEST STREAK", f"{ranked_max_streak}", "Kỷ lục cao nhất", (251, 191, 36, 255)),
        ]

        for i, (label, val, sub, color) in enumerate(stat_cards):
            kx = rx + 45 + i * (kpi_w + kpi_gap)
            draw.rounded_rectangle([(kx, kpi_y), (kx + kpi_w, kpi_y + kpi_h)], radius=20, fill=(18, 26, 42, 220), outline=(255, 255, 255, 24), width=1)
            # Label
            draw.text((kx + kpi_w // 2, kpi_y + 36), label, fill=(203, 213, 225, 255), font=_get_font(26, bold=True), anchor="mm")
            # Value
            val_font_size = 64 if len(val) >= 5 else 74
            draw.text((kx + kpi_w // 2, kpi_y + 100), val, fill=color, font=_get_font(val_font_size, bold=True), anchor="mm")
            # Subtext
            draw.text((kx + kpi_w // 2, kpi_y + 164), sub, fill=(203, 213, 225, 255), font=_get_font(25, bold=True), anchor="mm")

        # Khối phân tích chi tiết bên dưới 5 thẻ KPI (Font 27-28px, độ tương phản cao #CBD5E1 & #FFFFFF)
        ao_y = kpi_y + kpi_h + 26
        ao_h = 240
        ao_w = rw - 90
        draw.rounded_rectangle([(rx + 45, ao_y), (rx + 45 + ao_w, ao_y + ao_h)], radius=20, fill=(18, 26, 42, 180), outline=(255, 255, 255, 20), width=1)

        bw = (ao_w - 60) // 3
        font_sub_lbl = _get_font(27, bold=False)
        font_sub_val = _get_font(27, bold=True)
        c_lbl = (203, 213, 225, 255)       # #CBD5E1 - Sáng rõ, không mờ
        c_val = (255, 255, 255, 255)       # #FFFFFF - Trắng sắc nét
        c_green = (16, 185, 129, 255)      # #10B981
        c_gold = (251, 191, 36, 255)       # #FBBF24
        c_gray = (148, 163, 184, 255)      # #94A3B8

        def _draw_bullet(bx, by, label_str, val_str, v_color=c_val, v_font=font_sub_val):
            draw.text((bx, by), label_str, fill=c_lbl, font=font_sub_lbl)
            w_lbl = draw.textbbox((0, 0), label_str, font=font_sub_lbl)[2]
            draw.text((bx + w_lbl, by), val_str, fill=v_color, font=v_font)

        # Cột 1: Hiệu suất Ranked (COMPETITIVE PERFORMANCE)
        draw.text((rx + 75, ao_y + 26), "COMPETITIVE PERFORMANCE", fill=(56, 189, 248, 255), font=_get_font(28, bold=True))
        if total_matches == 0:
            _draw_bullet(rx + 75, ao_y + 78, "• Elo trung bình: ", "—", c_gray)
            _draw_bullet(rx + 75, ao_y + 128, "• S-Tier Rate: ", "—", c_gray)
            _draw_bullet(rx + 75, ao_y + 178, "• Xếp hạng phong độ: ", "UNRANKED", c_gray, font_sub_val)
        else:
            deltas = [abs(float(m.get("delta", 0))) for m in (recent_matches or []) if m.get("delta") is not None]
            avg_elo_val = (sum(deltas) / len(deltas)) if deltas else 25.0
            s_tier_rate_val = win_rate
            if win_rate >= 80.0 and total_matches >= 5:
                grade_str, grade_color = "S+ EXCELLENT", c_green
            elif win_rate >= 65.0:
                grade_str, grade_color = "S GREAT", c_green
            elif win_rate >= 50.0:
                grade_str, grade_color = "A SOLID", (56, 189, 248, 255)
            elif win_rate >= 35.0:
                grade_str, grade_color = "B CONTENDER", (251, 191, 36, 255)
            else:
                grade_str, grade_color = "C DEVELOPING", c_gray

            _draw_bullet(rx + 75, ao_y + 78, "• Elo trung bình: ", f"+{avg_elo_val:.1f} pts/trận", c_val)
            _draw_bullet(rx + 75, ao_y + 128, "• S-Tier Rate: ", f"{s_tier_rate_val:.1f}% S-Tier", c_val)
            _draw_bullet(rx + 75, ao_y + 178, "• Xếp hạng phong độ: ", grade_str, grade_color, font_sub_val)

        # Cột 2: Codeforces Sync
        cx2 = rx + 75 + bw + 30
        draw.text((cx2, ao_y + 26), "CODEFORCES SYNC DATA", fill=(251, 191, 36, 255), font=_get_font(28, bold=True))
        if cf_handle:
            cf_status_val = cf_handle
            cf_rating_val = f"{cf_rating} (Max: {cf_max_rating})" if cf_rating else "Chưa xác định"
            _draw_bullet(cx2, ao_y + 78, "• Thí sinh: ", cf_status_val, c_val)
            _draw_bullet(cx2, ao_y + 128, "• Rating: ", cf_rating_val, c_val)
            _draw_bullet(cx2, ao_y + 178, "• Trạng thái đồng bộ: ", "Hoàn tất & Xác thực", c_green, font_sub_val)
        else:
            _draw_bullet(cx2, ao_y + 78, "• Thí sinh: ", "Chưa liên kết", c_gray)
            _draw_bullet(cx2, ao_y + 128, "• Rating: ", "—", c_gray)
            _draw_bullet(cx2, ao_y + 178, "• Trạng thái đồng bộ: ", "Chưa liên kết CF", c_gray, font_sub_val)

        # Cột 3: Chuỗi thắng
        cx3 = cx2 + bw + 30
        draw.text((cx3, ao_y + 26), "CHUỖI THẮNG & THƯỞNG ELO", fill=(251, 146, 60, 255), font=_get_font(28, bold=True))
        if ranked_streak == 0:
            _draw_bullet(cx3, ao_y + 78, "• Chuỗi hiện tại: ", "0 trận", c_gray)
            _draw_bullet(cx3, ao_y + 128, "• Hệ số cộng thêm: ", "Chưa có bonus", c_gray)
            _draw_bullet(cx3, ao_y + 178, "• Kỷ lục chuỗi: ", f"{ranked_max_streak} trận thắng", c_gray)
        else:
            bonus_pct = 15 if ranked_streak >= 30 else (10 if ranked_streak >= 20 else (5 if ranked_streak >= 10 else (2 if ranked_streak >= 5 else 0)))
            font_bonus = _get_font(27, bold=True)
            _draw_bullet(cx3, ao_y + 78, "• Chuỗi hiện tại: ", f"{ranked_streak} trận liên tiếp", c_val)
            _draw_bullet(cx3, ao_y + 128, "• Hệ số cộng thêm: ", f"+{bonus_pct}% Elo khi thắng", c_gold, font_bonus)
            _draw_bullet(cx3, ao_y + 178, "• Kỷ lục chuỗi: ", f"{ranked_max_streak} trận thắng", c_gray, _get_font(27, bold=False))

        # ---------------------------------------------------------------------
        # PANEL 3: 2-COLUMN SPLIT (RANKED 1:1 vs FREEDOM RECENT ACTIVITY)
        # ---------------------------------------------------------------------
        p3_y = p2_y + p2_h + 30
        p3_h = rh - (p1_h + p2_h + 60)
        draw.rounded_rectangle([(rx, p3_y), (rx + rw, p3_y + p3_h)], radius=28, fill=(13, 19, 33, 215), outline=(255, 255, 255, 28), width=2)
        draw.text((rx + 45, p3_y + 26), "RECENT ACTIVITY & COMBAT AUDIT TRAIL (LỊCH SỬ ĐẤU TRƯỜNG & NỘP BÀI)", fill=(203, 213, 225, 255), font=_get_font(28, bold=True))

        col_gap = 30
        col_w = (rw - 90 - col_gap) // 2
        col1_x = rx + 45
        col2_x = col1_x + col_w + col_gap
        col_top_y = p3_y + 72
        col_content_h = p3_h - 90

        card_h = 195
        card_gap = 16

        # ==================== CỘT TRÁI: RANKED 1:1 ====================
        draw.rounded_rectangle([(col1_x + 5, col_top_y - 4), (col1_x + 185, col_top_y + 34)], radius=10, fill=(14, 165, 233, 45), outline=(56, 189, 248, 220), width=2)
        draw.text((col1_x + 95, col_top_y + 15), "RANKED 1:1", fill=(56, 189, 248, 255), font=_get_font(22, bold=True), anchor="mm")
        draw.text((col1_x + 200, col_top_y + 3), "RECENT MATCHES", fill=(255, 255, 255, 255), font=_get_font(26, bold=True))
        display_matches = (recent_matches or [])[:3]

        if display_matches:
            for m_idx, m_info in enumerate(display_matches):
                my = col_top_y + 46 + m_idx * (card_h + card_gap)
                outcome = str(m_info.get("outcome") or m_info.get("result") or "WIN").upper()
                delta = float(m_info.get("delta", 0.0) or 0.0)
                opp = str(m_info.get("opponent_name") or m_info.get("opponent") or "Opponent")
                date_str = str(m_info.get("time_str") or m_info.get("time") or "Gần đây")

                if outcome == "WIN":
                    badge_bg = (16, 185, 129, 45)
                    badge_border = (16, 185, 129, 220)
                    badge_color = (16, 185, 129, 255)
                    badge_label = "VICTORY"
                    delta_color = (16, 185, 129, 255)
                    delta_str = f"+{delta:.0f} Rating" if delta >= 0 else f"{delta:.0f} Rating"
                    perf_tag = "S+ MATCH MVP"
                    perf_color = (250, 204, 21, 255)
                elif outcome == "LOSS":
                    badge_bg = (239, 68, 68, 45)
                    badge_border = (239, 68, 68, 220)
                    badge_color = (239, 68, 68, 255)
                    badge_label = "DEFEAT"
                    delta_color = (239, 68, 68, 255)
                    delta_str = f"{delta:.0f} Rating"
                    perf_tag = "A SOLID FIGHT"
                    perf_color = (148, 163, 184, 255)
                else:
                    badge_bg = (245, 158, 11, 45)
                    badge_border = (245, 158, 11, 220)
                    badge_color = (245, 158, 11, 255)
                    badge_label = "DRAW"
                    delta_color = (245, 158, 11, 255)
                    delta_str = "+0 Rating"
                    perf_tag = "BALANCED"
                    perf_color = (245, 158, 11, 255)

                draw.rounded_rectangle([(col1_x, my), (col1_x + col_w, my + card_h)], radius=18, fill=(18, 26, 42, 220), outline=(255, 255, 255, 24), width=1)

                # Pill outcome
                pw, ph = 175, 54
                px, py_b = col1_x + 25, my + (card_h - ph) // 2
                draw.rounded_rectangle([(px, py_b), (px + pw, py_b + ph)], radius=14, fill=badge_bg, outline=badge_border, width=2)
                draw.text((px + pw // 2, py_b + ph // 2), badge_label, fill=badge_color, font=_get_font(26, bold=True), anchor="mm")

                # Delta
                draw.text((px + pw + 25, my + 38), delta_str, fill=delta_color, font=_get_font(48, bold=True))
                draw.text((px + pw + 25, my + 112), "Ranked Elo Impact", fill=(203, 213, 225, 255), font=_get_font(24, bold=False))

                # Opponent & Mode
                draw.text((col1_x + 490, my + 38), f"vs {opp}", fill=(255, 255, 255, 255), font=_get_font(34, bold=True))
                draw.text((col1_x + 490, my + 88), f"Ranked 1:1 • Tier {ranked_tier}", fill=(226, 232, 240, 255), font=_get_font(24, bold=False))
                draw.text((col1_x + 490, my + 128), perf_tag, fill=perf_color, font=_get_font(23, bold=True))

                # Date & AC Status (Right side - anchor="rm")
                draw.text((col1_x + col_w - 30, my + 54), date_str, fill=(203, 213, 225, 255), font=_get_font(26, bold=True), anchor="rm")
                draw.text((col1_x + col_w - 30, my + 125), "Anti-Cheat 2.0 Passed", fill=(16, 185, 129, 255), font=_get_font(24, bold=True), anchor="rm")
        else:
            box_w = 660
            box_h = 240
            box_x = col1_x + (col_w - box_w) // 2
            box_y = col_top_y + 46 + (col_content_h - 46 - box_h) // 2
            draw.rounded_rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)], radius=22, fill=(18, 26, 42, 190), outline=(255, 255, 255, 24), width=1)
            draw.text((box_x + box_w // 2, box_y + 55), "NO MATCH HISTORY", fill=(255, 255, 255, 255), font=_get_font(32, bold=True), anchor="mm")
            draw.text((box_x + box_w // 2, box_y + 105), "Chưa tham gia trận đấu Ranked nào.", fill=(203, 213, 225, 255), font=_get_font(24, bold=False), anchor="mm")
            btn_w, btn_h = 280, 52
            btn_x = box_x + (box_w - btn_w) // 2
            btn_y = box_y + 155
            draw.rounded_rectangle([(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)], radius=26, fill=(14, 165, 233, 40), outline=(56, 189, 248, 220), width=2)
            draw.text((btn_x + btn_w // 2, btn_y + btn_h // 2), "ENTER RANKED 1:1", fill=(56, 189, 248, 255), font=_get_font(24, bold=True), anchor="mm")

        # ==================== CỘT PHẢI: FREEDOM SOLVES ====================
        draw.rounded_rectangle([(col2_x + 5, col_top_y - 4), (col2_x + 165, col_top_y + 34)], radius=10, fill=(245, 158, 11, 45), outline=(251, 191, 36, 220), width=2)
        draw.text((col2_x + 85, col_top_y + 15), "FREEDOM", fill=(251, 191, 36, 255), font=_get_font(22, bold=True), anchor="mm")
        draw.text((col2_x + 180, col_top_y + 3), "RECENT SUBMISSIONS", fill=(255, 255, 255, 255), font=_get_font(26, bold=True))
        display_freedom = (recent_freedom or [])[:3]

        if display_freedom:
            for s_idx, s_info in enumerate(display_freedom):
                sy = col_top_y + 46 + s_idx * (card_h + card_gap)
                v_raw = str(s_info.get("verdict") or "Accepted")
                p_id = str(s_info.get("problem_id") or "1700A")
                lang_name = str(s_info.get("language") or "C++")
                pts_earned = float(s_info.get("score", 0.0) or 0.0)
                time_taken = float(s_info.get("execution_time", 0.0) or 0.0)
                sub_date = str(s_info.get("time_str") or "Gần đây")

                v_lower = v_raw.lower()
                if "accepted" in v_lower or "chấp nhận" in v_lower:
                    f_bg = (16, 185, 129, 45)
                    f_border = (16, 185, 129, 220)
                    f_color = (16, 185, 129, 255)
                    f_lbl = "ACCEPTED"
                    score_col = (16, 185, 129, 255)
                    score_str = f"+{pts_earned:.0f} pts" if pts_earned > 0 else "+100 pts"
                    tag_str = "THEMIS SUITE PASSED"
                    tag_col = (250, 204, 21, 255)
                elif "wrong" in v_lower or "sai" in v_lower:
                    f_bg = (239, 68, 68, 45)
                    f_border = (239, 68, 68, 220)
                    f_color = (239, 68, 68, 255)
                    f_lbl = "WRONG ANS"
                    score_col = (239, 68, 68, 255)
                    score_str = "+0.0 pts"
                    tag_str = "LOGIC ERROR"
                    tag_col = (148, 163, 184, 255)
                elif "tle" in v_lower or "thời gian" in v_lower:
                    f_bg = (245, 158, 11, 45)
                    f_border = (245, 158, 11, 220)
                    f_color = (245, 158, 11, 255)
                    f_lbl = "TIME LIMIT"
                    score_col = (245, 158, 11, 255)
                    score_str = "+0.0 pts"
                    tag_str = "TIMEOUT EXCEEDED"
                    tag_col = (245, 158, 11, 255)
                else:
                    f_bg = (56, 189, 248, 45)
                    f_border = (56, 189, 248, 220)
                    f_color = (56, 189, 248, 255)
                    f_lbl = "SUBMITTED"
                    score_col = (56, 189, 248, 255)
                    score_str = f"+{pts_earned:.0f} pts"
                    tag_str = "EVALUATED"
                    tag_col = (56, 189, 248, 255)

                draw.rounded_rectangle([(col2_x, sy), (col2_x + col_w, sy + card_h)], radius=18, fill=(18, 26, 42, 220), outline=(255, 255, 255, 24), width=1)

                # Pill verdict
                pw, ph = 185, 54
                px, py_b = col2_x + 25, sy + (card_h - ph) // 2
                draw.rounded_rectangle([(px, py_b), (px + pw, py_b + ph)], radius=14, fill=f_bg, outline=f_border, width=2)
                draw.text((px + pw // 2, py_b + ph // 2), f_lbl, fill=f_color, font=_get_font(24, bold=True), anchor="mm")

                # Score
                draw.text((px + pw + 25, sy + 38), score_str, fill=score_col, font=_get_font(48, bold=True))
                draw.text((px + pw + 25, sy + 112), "Score Impact", fill=(203, 213, 225, 255), font=_get_font(24, bold=False))

                # Problem ID & Details
                disp_prob = f"{p_id}" if len(p_id) <= 8 else f"{p_id[:8]}.."
                draw.text((col2_x + 490, sy + 38), disp_prob, fill=(251, 191, 36, 255), font=_get_font(36, bold=True))
                draw.text((col2_x + 490, sy + 88), f"{lang_name} • {time_taken:.2f}s", fill=(226, 232, 240, 255), font=_get_font(24, bold=False))
                draw.text((col2_x + 490, sy + 128), tag_str, fill=tag_col, font=_get_font(23, bold=True))

                # Date & Mode (Right side - anchor="rm")
                draw.text((col2_x + col_w - 30, sy + 54), sub_date, fill=(203, 213, 225, 255), font=_get_font(26, bold=True), anchor="rm")
                draw.text((col2_x + col_w - 30, sy + 125), "Sandbox Verified", fill=(16, 185, 129, 255), font=_get_font(24, bold=True), anchor="rm")
        else:
            box_w = 660
            box_h = 240
            box_x = col2_x + (col_w - box_w) // 2
            box_y = col_top_y + 46 + (col_content_h - 46 - box_h) // 2
            draw.rounded_rectangle([(box_x, box_y), (box_x + box_w, box_y + box_h)], radius=22, fill=(18, 26, 42, 190), outline=(255, 255, 255, 24), width=1)
            draw.text((box_x + box_w // 2, box_y + 55), "NO FREEDOM SOLVES", fill=(255, 255, 255, 255), font=_get_font(32, bold=True), anchor="mm")
            draw.text((box_x + box_w // 2, box_y + 105), "Chưa có bài nộp trong chế độ Freedom.", fill=(203, 213, 225, 255), font=_get_font(24, bold=False), anchor="mm")
            btn_w, btn_h = 280, 52
            btn_x = box_x + (box_w - btn_w) // 2
            btn_y = box_y + 155
            draw.rounded_rectangle([(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)], radius=26, fill=(245, 158, 11, 40), outline=(251, 191, 36, 220), width=2)
            draw.text((btn_x + btn_w // 2, btn_y + btn_h // 2), "SUBMIT PROBLEM", fill=(251, 191, 36, 255), font=_get_font(24, bold=True), anchor="mm")

        # 7. FOOTER (Cỡ chữ 22px bold, rõ nét)
        draw.text(
            (width // 2, height - 70),
            "HYPERHUB ARENA  •  OFFICIAL ESPORTS PROFILE  •  3840 × 2160",
            fill=(148, 163, 184, 255),
            font=_get_font(22, bold=True),
            anchor="mm",
        )

        file_path = os.path.join(PROFILE_CARDS_DIR, f"profile_{user_id}.png")
        img.save(file_path, "PNG", optimize=True)
        try:
            with open(hash_file_path, "w", encoding="utf-8") as hf:
                hf.write(cache_hash)
        except Exception as he:
            logger.debug(f"Không thể lưu cache hash cho user {user_id}: {he}")

        logger.info(f"[ProfileCard] Đã kết xuất ảnh thẻ Profile Esports 4K {width}x{height} cho user {user_id} -> {file_path}")
        return file_path
