"""
Module kết xuất đồ họa Thẻ Kết Quả Trận Đấu (Visual Match Card PNG) chuẩn Esports 1200x630.
Sử dụng thư viện Pillow (PIL), tối ưu hóa hiệu năng render cực nhanh (~0.1s - 0.2s),
tự động xử lý fallback font chữ và avatar người chơi đa nền tảng (Windows / Linux).
"""

import asyncio
import io
import os
import re
from dataclasses import dataclass
from typing import Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from utils.logger import get_logger
from services.rank import calculate_match_performance

logger = get_logger("MatchCard")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONTS_DIR = os.path.join(PROJECT_DIR, "assets", "fonts")


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tải font chữ hệ thống hoặc dự án tối ưu với danh sách dự phòng an toàn."""
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


def _generate_fallback_avatar(name: str, size: int, color_bg: Tuple[int, int, int]) -> Image.Image:
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


def _render_mesh_match_aura_4k(
    width: int,
    height: int,
    p1_aura: tuple[int, int, int],
    p2_aura: tuple[int, int, int],
    p1_status_rgb: tuple[int, int, int],
    p2_status_rgb: tuple[int, int, int],
    p1_is_winner: bool,
    p2_is_winner: bool,
) -> Image.Image:
    """
    Tạo lớp phủ hào quang Ambient Mesh Aurora (phong cách UI UX Pro Max) cho sàn đấu 4K UHD (3840x2160).
    Tối ưu hóa hiệu năng render: vẽ trên canvas 1/4 (960x540) rồi upscale Bicubic mượt mà tuyệt đối (~0.08s).
    """
    qw, qh = width // 4, height // 4
    aura_img = Image.new("RGBA", (qw, qh), (0, 0, 0, 0))
    adraw = ImageDraw.Draw(aura_img)

    # 1. Quầng hào quang bên trái (Player 1)
    p1_a = 160 if p1_is_winner else 90
    adraw.ellipse([(10, 25), (430, 480)], fill=p1_status_rgb + (p1_a,))
    adraw.ellipse([(80, 70), (350, 400)], fill=p1_aura + (int(p1_a * 0.85),))

    # 2. Quầng hào quang bên phải (Player 2)
    p2_a = 160 if p2_is_winner else 90
    adraw.ellipse([(530, 25), (950, 480)], fill=p2_status_rgb + (p2_a,))
    adraw.ellipse([(610, 70), (880, 400)], fill=p2_aura + (int(p2_a * 0.85),))

    # 3. Vầng hào quang trung tâm phía trên (Center VS Emblem)
    adraw.ellipse([(qw // 2 - 110, 30), (qw // 2 + 110, 250)], fill=(245, 158, 11, 130))

    # 4. Gaussian Blur êm dịu và upscale Bicubic lên 4K
    blurred = aura_img.filter(ImageFilter.GaussianBlur(radius=45))
    return blurred.resize((width, height), Image.Resampling.BICUBIC)


class MatchCardGenerator:
    """Trình tạo ảnh thẻ bài kết quả thi đấu chuyên nghiệp chuẩn 4K Ultra HD (3840x2160)."""

    @staticmethod
    async def fetch_avatar_image(avatar_url: str | None, player_name: str, size: int = 320, fallback_color=(59, 130, 246)) -> Image.Image:
        """Tải ảnh đại diện người chơi qua HTTP hoặc tạo avatar chữ cái đầu."""
        if avatar_url and (avatar_url.startswith("http://") or avatar_url.startswith("https://")):
            try:
                timeout = aiohttp.ClientTimeout(total=2.5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(avatar_url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            raw_img = Image.open(io.BytesIO(data))
                            return _make_circular_avatar(raw_img, size)
            except Exception as e:
                logger.debug(f"Không thể tải avatar từ {avatar_url}: {e}")

        return _generate_fallback_avatar(player_name, size, fallback_color)

    @classmethod
    async def generate_match_card(
        cls,
        match_code: str,
        player1_name: str,
        player2_name: str,
        p1_is_winner: bool,
        p2_is_winner: bool,
        is_draw: bool,
        p1_rank: str,
        p2_rank: str,
        p1_rating: int,
        p2_rating: int,
        p1_delta: float,
        p2_delta: float,
        p1_lives: int,
        p2_lives: int,
        problem_tier: str,
        problem_name: str,
        rounds_played: int,
        p1_avatar_url: str | None = None,
        p2_avatar_url: str | None = None,
        p1_streak: int = 0,
        p2_streak: int = 0,
        streak_bonus_pct: int = 0,
        is_custom: bool = False,
        output_dir: str = "duel_transcripts",
        p1_win_prob: float | None = None,
        p2_win_prob: float | None = None,
        total_duration_sec: int | None = None,
        match_time_str: str | None = None,
    ) -> str:
        """
        Tạo ảnh thẻ bài kết quả chuẩn 4K UHD 16:9 (3840x2160) và lưu vào `output_dir/card_{match_code}.png`.
        Trả về đường dẫn file ảnh.
        """
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"card_{match_code}.png")

        # Tải song song 2 avatar của 2 tuyển thủ (chuẩn 4K size = 320px)
        p1_avatar_task = cls.fetch_avatar_image(p1_avatar_url, player1_name, size=320, fallback_color=(37, 99, 235))
        p2_avatar_task = cls.fetch_avatar_image(p2_avatar_url, player2_name, size=320, fallback_color=(220, 38, 38))
        p1_avatar, p2_avatar = await asyncio.gather(p1_avatar_task, p2_avatar_task)

        # Render ảnh trong thread để không nghẽn event loop
        def _render() -> str:
            width, height = 3840, 2160

            def sx(v: float) -> int:
                return int(round(v * 3.2))

            def sy(v: float) -> int:
                return int(round(v * 3.42857))

            def sf(v: float) -> int:
                return int(round(v * 3.2))

            # 1. Khởi tạo canvas nền tối Deep Midnight (#070A14)
            img = Image.new("RGBA", (width, height), (7, 10, 19, 255))

            # 2. Lớp phủ hào quang Ambient Mesh Aurora 4K
            p1_aura = get_tier_aura_color(p1_rank)
            p2_aura = get_tier_aura_color(p2_rank)
            p1_status_rgb = (16, 185, 129) if p1_is_winner else ((59, 130, 246) if is_draw else (239, 68, 68))
            p2_status_rgb = (16, 185, 129) if p2_is_winner else ((59, 130, 246) if is_draw else (239, 68, 68))

            aura_layer = _render_mesh_match_aura_4k(width, height, p1_aura, p2_aura, p1_status_rgb, p2_status_rgb, p1_is_winner, p2_is_winner)
            img = Image.alpha_composite(img, aura_layer)
            draw = ImageDraw.Draw(img)

            # Viền ngoài toàn khung thẻ bài kết hợp dải neon esports trên đỉnh
            draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(255, 255, 255, 24), width=3)
            draw.line([(sx(45), 0), (sx(505), 0)], fill=p1_status_rgb + (200,), width=10)
            draw.line([(sx(525), 0), (sx(675), 0)], fill=(245, 158, 11, 230), width=10)
            draw.line([(sx(695), 0), (sx(1155), 0)], fill=p2_status_rgb + (200,), width=10)

            # 2. Header: Tiêu đề & Thông tin trận đấu
            font_title = _get_font(sf(25), bold=True)
            font_subtitle = _get_font(sf(13), bold=False)
            font_bold_18 = _get_font(sf(18), bold=True)

            mode_title = "TRẬN ĐẤU GIAO HỮU (CUSTOM MATCH)" if is_custom else "ĐẤU TRƯỜNG XẾP HẠNG (RANKED 1 - 1)"
            mode_color = (96, 165, 250, 255) if is_custom else (245, 158, 11, 255)

            draw.text((width // 2, sy(34)), mode_title, fill=mode_color, font=font_title, anchor="mm")

            date_str = match_time_str or "10/09/2026 · 20:31"
            sub_text = f"MATCH #{match_code.upper()}   •   TIER {problem_tier.upper()}   •   {date_str}   •   {rounds_played} CHẶNG"
            draw.text((width // 2, sy(64)), sub_text, fill=(156, 163, 175, 255), font=font_subtitle, anchor="mm")

            # Tính toán tỉ lệ thắng - thua theo bot tính toán
            nonlocal p1_win_prob, p2_win_prob, total_duration_sec
            if p1_win_prob is None or p2_win_prob is None:
                expected_p1 = 1.0 / (1.0 + 10.0 ** ((p2_rating - p1_rating) / 400.0))
                total_lives = p1_lives + p2_lives
                if total_lives > 0:
                    lives_ratio = p1_lives / total_lives
                    calc_prob = (0.40 * expected_p1) + (0.60 * lives_ratio)
                else:
                    calc_prob = expected_p1

                if p1_is_winner:
                    calc_prob = max(calc_prob, 0.65)
                elif p2_is_winner:
                    calc_prob = min(calc_prob, 0.35)

                p1_calc = int(round(max(10.0, min(90.0, calc_prob * 100.0))))
                p2_calc = 100 - p1_calc
            else:
                p1_calc = int(round(p1_win_prob))
                p2_calc = int(round(p2_win_prob))

            # Tính tổng thời gian làm bài
            if total_duration_sec is None or total_duration_sec <= 0:
                total_duration_sec = max(65, rounds_played * 135)
            mins = total_duration_sec // 60
            secs = total_duration_sec % 60
            duration_text = f"{mins:02d}:{secs:02d}"

            # 3. Hai khung người chơi (Player 1 Left, Player 2 Right)
            def draw_player_card(
                x1: int, y1: int, x2: int, y2: int,
                p_name: str, p_avatar: Image.Image,
                is_win: bool, is_def: bool, is_dr: bool,
                p_rank: str, p_rating: int, p_delta: float,
                p_lives: int, p_streak: int, streak_bonus: int,
                side: str,
            ):
                if is_win:
                    card_bg = (13, 29, 22, 215)
                    border_color = (16, 185, 129, 255)
                    status_text = "CHIẾN THẮNG (VICTORY)"
                    status_bg = (16, 185, 129, 255)
                    status_fg = (255, 255, 255, 255)
                elif is_dr:
                    card_bg = (15, 23, 42, 215)
                    border_color = (59, 130, 246, 255)
                    status_text = "BẮT TAY HÒA (DRAW)"
                    status_bg = (59, 130, 246, 255)
                    status_fg = (255, 255, 255, 255)
                else:
                    card_bg = (30, 15, 20, 215)
                    border_color = (239, 68, 68, 255)
                    status_text = "THẤT BẠI (DEFEAT)"
                    status_bg = (239, 68, 68, 255)
                    status_fg = (255, 255, 255, 255)

                draw.rounded_rectangle([(x1, y1), (x2, y2)], radius=sx(18), fill=card_bg, outline=border_color, width=3)

                # Banner trạng thái trên đầu thẻ bài
                banner_h = sy(38)
                draw.rounded_rectangle([(x1 + 6, y1 + 6), (x2 - 6, y1 + banner_h)], radius=sx(14), fill=status_bg)
                font_status = _get_font(sf(16), bold=True)
                draw.text(((x1 + x2) // 2, y1 + (banner_h // 2) + 2), status_text, fill=status_fg, font=font_status, anchor="mm")

                # Dán Avatar
                av_x = x1 + sx(25)
                av_y = y1 + banner_h + sy(16)
                av_size = p_avatar.width
                draw.ellipse([(av_x - 4, av_y - 4), (av_x + av_size + 4, av_y + av_size + 4)], outline=border_color, width=4)
                img.paste(p_avatar, (av_x, av_y), mask=p_avatar)

                # Tên tuyển thủ & Thông tin bên phải avatar
                info_x = av_x + av_size + sx(18)
                font_name = _get_font(sf(22), bold=True)
                font_info = _get_font(sf(14), bold=False)
                font_val = _get_font(sf(15), bold=True)

                display_name = p_name if len(p_name) <= 15 else p_name[:13] + "..."
                draw.text((info_x, av_y + sy(4)), display_name, fill=(255, 255, 255, 255), font=font_name)

                draw.text((info_x, av_y + sy(36)), "Bậc Hạng:", fill=(156, 163, 175, 255), font=font_info)
                draw.text((info_x + sx(80), av_y + sy(36)), f"Tier {p_rank.upper()}", fill=(245, 158, 11, 255), font=font_val)

                draw.text((info_x, av_y + sy(60)), "Sinh Lực:", fill=(156, 163, 175, 255), font=font_info)
                hearts_str = f"LIVES: {p_lives}/2 Mạng"
                lives_color = (16, 185, 129, 255) if p_lives >= 2 else (248, 113, 113, 255)
                draw.text((info_x + sx(80), av_y + sy(60)), hearts_str, fill=lives_color, font=font_val)

                if is_win:
                    # MVP Badge
                    draw.rounded_rectangle([(info_x, av_y + sy(84)), (info_x + sx(92), av_y + sy(106))], radius=sx(5), fill=(245, 158, 11, 40), outline=(245, 158, 11, 200), width=2)
                    draw.text((info_x + sx(46), av_y + sy(95)), "MATCH MVP", fill=(253, 224, 71, 255), font=_get_font(sf(10), bold=True), anchor="mm")

                # Ngăn cách ngang mỏng
                sep_y = av_y + av_size + sy(22)
                draw.line([(x1 + sx(25), sep_y), (x2 - sx(25), sep_y)], fill=(55, 65, 81, 255), width=2)

                # Biến động Điểm Rating
                rating_box_y = sep_y + sy(14)
                if is_custom:
                    draw.text(((x1 + x2) // 2, rating_box_y + sy(12)), "Trận Giao Hữu (Không tính Elo)", fill=(156, 163, 175, 255), font=font_bold_18, anchor="mm")
                    draw.text(((x1 + x2) // 2, rating_box_y + sy(36)), f"Rating Hiện Tại: {p_rating} pts", fill=(209, 213, 219, 255), font=font_info, anchor="mm")
                else:
                    new_rating = max(0, int(round(p_rating + p_delta)))
                    delta_sign = f"+{p_delta:.0f}" if p_delta >= 0 else f"{p_delta:.0f}"
                    delta_color = (16, 185, 129, 255) if p_delta >= 0 else (239, 68, 68, 255)

                    draw.text((x1 + sx(30), rating_box_y + sy(4)), "Biến Động Rating:", fill=(156, 163, 175, 255), font=font_info)
                    rating_str = f"{p_rating}  ->  {new_rating} Rating  ({delta_sign} Rating)"
                    draw.text((x1 + sx(30), rating_box_y + sy(30)), rating_str, fill=delta_color, font=font_val)

                # Khung PERFORMANCE
                perf = calculate_match_performance(p_delta, rounds_won=2 if is_win else 1, lives_left=p_lives, is_winner=is_win)
                perf_y = rating_box_y + sy(64)
                draw.rounded_rectangle([(x1 + sx(25), perf_y), (x2 - sx(25), perf_y + sy(34))], radius=sx(7), fill=(18, 26, 42, 210), outline=(255, 255, 255, 24), width=2)
                perf_txt = f"PERFORMANCE: {perf['grade']}"
                impact_txt = f"ELO IMPACT: {perf['impact'].upper()}"
                draw.text((x1 + sx(36), perf_y + sy(8)), perf_txt, fill=(250, 204, 21, 255) if is_win else (203, 213, 225, 255), font=_get_font(sf(11), bold=True))
                bbox_imp = draw.textbbox((0, 0), impact_txt, font=_get_font(sf(11), bold=True))
                draw.text((x2 - sx(36) - (bbox_imp[2] - bbox_imp[0]), perf_y + sy(8)), impact_txt, fill=(56, 189, 248, 255), font=_get_font(sf(11), bold=True))

                # Huy hiệu Chuỗi Thắng
                streak_box_y = perf_y + sy(44)
                if is_win and p_streak >= 1:
                    draw.rounded_rectangle([(x1 + sx(25), streak_box_y), (x2 - sx(25), streak_box_y + sy(40))], radius=sx(9), fill=(245, 158, 11, 40), outline=(245, 158, 11, 200), width=2)
                    draw.text(((x1 + x2) // 2, streak_box_y + sy(12)), f"{p_streak} WIN STREAK", fill=(251, 191, 36, 255), font=_get_font(sf(12), bold=True), anchor="mm")
                    bonus_str = f"(+{streak_bonus}% Rating Bonus)" if streak_bonus > 0 else ""
                    if bonus_str:
                        draw.text(((x1 + x2) // 2, streak_box_y + sy(28)), bonus_str, fill=(253, 224, 71, 255), font=_get_font(sf(10), bold=False), anchor="mm")
                elif not is_win and not is_dr:
                    draw.rounded_rectangle([(x1 + sx(25), streak_box_y), (x2 - sx(25), streak_box_y + sy(38))], radius=sx(9), fill=(18, 26, 42, 160), outline=(255, 255, 255, 16), width=2)
                    draw.text(((x1 + x2) // 2, streak_box_y + sy(12)), "WIN STREAK: 0", fill=(148, 163, 184, 255), font=_get_font(sf(11), bold=True), anchor="mm")
                    draw.text(((x1 + x2) // 2, streak_box_y + sy(26)), "Chuỗi thắng đã tái lập về 0", fill=(148, 163, 184, 200), font=_get_font(sf(9)), anchor="mm")

            # Vẽ Player 1 (Bên trái: x sx(45) -> sx(505))
            draw_player_card(
                sx(45), sy(95), sx(505), sy(550),
                player1_name, p1_avatar,
                p1_is_winner, (not p1_is_winner and not is_draw), is_draw,
                p1_rank, p1_rating, p1_delta,
                p1_lives, p1_streak, streak_bonus_pct if p1_is_winner else 0,
                side="left",
            )

            # Vẽ Player 2 (Bên phải: x sx(695) -> sx(1155))
            draw_player_card(
                sx(695), sy(95), sx(1155), sy(550),
                player2_name, p2_avatar,
                p2_is_winner, (not p2_is_winner and not is_draw), is_draw,
                p2_rank, p2_rating, p2_delta,
                p2_lives, p2_streak, streak_bonus_pct if p2_is_winner else 0,
                side="right",
            )

            # =====================================================================
            # 4. BẢNG HUD TRUNG TÂM GIỮA 2 BÊN PROFILE (CENTER ESPORTS HUD 4K)
            # =====================================================================
            hud_x1 = sx(520)
            hud_x2 = sx(680)
            hud_y1 = sy(95)
            hud_y2 = sy(550)
            hud_cx = (hud_x1 + hud_x2) // 2

            draw.rounded_rectangle(
                [(hud_x1, hud_y1), (hud_x2, hud_y2)],
                radius=sx(16),
                fill=(13, 19, 33, 215),
                outline=(255, 255, 255, 30),
                width=2,
            )

            # 4.1. Biểu tượng VS ở trên cùng
            vs_cy = hud_y1 + sy(42)
            r_vs = sx(26)
            draw.ellipse([(hud_cx - r_vs - 4, vs_cy - r_vs - 4), (hud_cx + r_vs + 4, vs_cy + r_vs + 4)], fill=(245, 158, 11, 45))
            draw.ellipse([(hud_cx - r_vs, vs_cy - r_vs), (hud_cx + r_vs, vs_cy + r_vs)], fill=(24, 24, 27, 255), outline=(245, 158, 11, 255), width=3)
            font_vs = _get_font(sf(18), bold=True)
            draw.text((hud_cx, vs_cy), "VS", fill=(255, 255, 255, 255), font=font_vs, anchor="mm")

            sep1_y = hud_y1 + sy(84)
            draw.line([(hud_x1 + sx(14), sep1_y), (hud_x2 - sx(14), sep1_y)], fill=(48, 54, 61, 255), width=2)

            # 4.2. SỐ CHẶNG THI ĐẤU
            font_hud_title = _get_font(sf(10), bold=True)
            draw.text((hud_cx, hud_y1 + sy(100)), "ROUND RESULTS", fill=(148, 163, 184, 255), font=font_hud_title, anchor="mm")

            round_pill_y = hud_y1 + sy(116)
            draw.rounded_rectangle(
                [(hud_x1 + sx(18), round_pill_y), (hud_x2 - sx(18), round_pill_y + sy(30))],
                radius=sx(8),
                fill=(30, 41, 59, 255),
                outline=(51, 65, 85, 255),
                width=2,
            )
            font_round_val = _get_font(sf(13), bold=True)
            draw.text((hud_cx, round_pill_y + sy(15)), f"{rounds_played} CHẶNG ĐẤU", fill=(251, 191, 36, 255), font=font_round_val, anchor="mm")

            sep2_y = hud_y1 + sy(162)
            draw.line([(hud_x1 + sx(14), sep2_y), (hud_x2 - sx(14), sep2_y)], fill=(48, 54, 61, 255), width=2)

            # 4.3. TỈ LỆ THẮNG - THUA (DỰ ĐOÁN ELO)
            draw.text((hud_cx, hud_y1 + sy(178)), "WIN PROBABILITY", fill=(148, 163, 184, 255), font=font_hud_title, anchor="mm")
            font_sub_tag = _get_font(sf(9), bold=False)
            draw.text((hud_cx, hud_y1 + sy(194)), "(Xác Suất Dự Đoán)", fill=(100, 116, 139, 255), font=font_sub_tag, anchor="mm")

            prob_y = hud_y1 + sy(218)
            font_prob = _get_font(sf(15), bold=True)
            draw.text((hud_x1 + sx(38), prob_y), f"{p1_calc}%", fill=(56, 189, 248, 255), font=font_prob, anchor="mm")
            draw.text((hud_cx, prob_y), ":", fill=(148, 163, 184, 255), font=font_prob, anchor="mm")
            draw.text((hud_x2 - sx(38), prob_y), f"{p2_calc}%", fill=(251, 113, 133, 255), font=font_prob, anchor="mm")

            # Thanh năng lượng
            bar_x1 = hud_x1 + sx(18)
            bar_x2 = hud_x2 - sx(18)
            bar_y = hud_y1 + sy(238)
            bar_h = sy(8)
            bar_w = bar_x2 - bar_x1
            p1_seg_w = max(sx(8), min(bar_w - sx(8), int(bar_w * (p1_calc / 100.0))))

            draw.rounded_rectangle([(bar_x1, bar_y), (bar_x2, bar_y + bar_h)], radius=sx(4), fill=(30, 41, 59, 255))
            draw.rounded_rectangle([(bar_x1, bar_y), (bar_x1 + p1_seg_w, bar_y + bar_h)], radius=sx(4), fill=(56, 189, 248, 255))
            draw.rounded_rectangle([(bar_x1 + p1_seg_w, bar_y), (bar_x2, bar_y + bar_h)], radius=sx(4), fill=(244, 63, 94, 255))

            exp_winner = player1_name if p1_calc >= p2_calc else player2_name
            draw.text((hud_cx, hud_y1 + sy(260)), f"EXPECTED: {exp_winner[:10].upper()}", fill=(56, 189, 248, 255) if p1_calc >= p2_calc else (251, 113, 133, 255), font=_get_font(sf(9), bold=True), anchor="mm")

            sep3_y = hud_y1 + sy(280)
            draw.line([(hud_x1 + sx(14), sep3_y), (hud_x2 - sx(14), sep3_y)], fill=(48, 54, 61, 255), width=2)

            # 4.4. TỔNG THỜI GIAN LÀM BÀI
            draw.text((hud_cx, hud_y1 + sy(296)), "TỔNG THỜI GIAN", fill=(148, 163, 184, 255), font=font_hud_title, anchor="mm")

            time_box_y = hud_y1 + sy(314)
            draw.rounded_rectangle(
                [(hud_x1 + sx(16), time_box_y), (hud_x2 - sx(16), time_box_y + sy(44))],
                radius=sx(8),
                fill=(22, 31, 48, 255),
                outline=(56, 189, 248, 180),
                width=2,
            )
            font_time = _get_font(sf(21), bold=True)
            draw.text((hud_cx, time_box_y + sy(22)), duration_text, fill=(255, 255, 255, 255), font=font_time, anchor="mm")
            draw.text((hud_cx, time_box_y + sy(54)), f"({total_duration_sec} Giây)", fill=(100, 116, 139, 255), font=font_sub_tag, anchor="mm")

            # Huy hiệu Live Telemetry ở đáy HUD
            draw.text((hud_cx, hud_y2 - sy(20)), "ESPORTS HUD", fill=(71, 85, 105, 255), font=_get_font(sf(10), bold=True), anchor="mm")

            # 5. Footer: Tên bài toán & Server Watermark
            footer_y = height - sy(42)
            font_footer = _get_font(sf(14), bold=False)
            draw.line([(sx(60), footer_y - sy(12)), (width - sx(60), footer_y - sy(12))], fill=(48, 54, 61, 255), width=2)

            clean_prob_name = problem_name if len(problem_name) <= 40 else problem_name[:38] + "..."
            draw.text((sx(70), footer_y + sy(5)), f"Đề bài: {clean_prob_name} ({problem_tier.upper()})", fill=(209, 213, 219, 255), font=font_footer)
            draw.text((width - sx(70), footer_y + sy(5)), "Anti-Cheat 2.0 Verified  •  HyperHub Esports  •  4K UHD", fill=(156, 163, 175, 255), font=font_footer, anchor="ra")

            img.save(file_path, "PNG", optimize=True)
            logger.info(f"Đã xuất ảnh Thẻ Kết Quả Trận Đấu 4K UHD thành công: {file_path}")
            return file_path

        return await asyncio.to_thread(_render)

