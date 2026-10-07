"""Đồ họa Infographic tạo ảnh so sánh 2 phương thức làm bài sắc nét, hiện đại bằng Pillow."""

import os

from PIL import Image, ImageDraw, ImageFont

from utils.logger import get_logger

logger = get_logger("ImageGenerator")


def get_default_font(
    size: int, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tìm font chữ hệ thống đẹp nhất trên Windows/Linux."""
    font_names = [
        "segoeui.ttf",
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "arial.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "tahoma.ttf",
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_mode_comparison_image(
    output_path: str = "assets/mode_comparison.png",
) -> str:
    """Tạo ảnh Infographic bảng so sánh 2 chế độ làm bài độ nét cao chuẩn Discord Dark Theme."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    width, height = 960, 520
    img = Image.new("RGBA", (width, height), (24, 25, 28, 255))
    draw = ImageDraw.Draw(img)

    # 1. Khung viền ngoài cùng bo tròn
    draw.rounded_rectangle(
        [(12, 12), (width - 12, height - 12)],
        radius=20,
        fill=(30, 31, 35, 255),
        outline=(50, 53, 60, 255),
        width=2,
    )

    # 2. Tiêu đề chính
    font_title = get_default_font(24, bold=True)
    font_sub = get_default_font(14, bold=False)
    font_col_title = get_default_font(18, bold=True)
    font_label = get_default_font(15, bold=False)
    font_val = get_default_font(15, bold=True)

    draw.text(
        (width // 2, 42),
        "SO SÁNH 2 PHƯƠNG THỨC LÀM BÀI",
        fill=(255, 255, 255, 255),
        font=font_title,
        anchor="mm",
    )
    draw.text(
        (width // 2, 70),
        "HYPER HUB COMPETITIVE PROGRAMMING ARENA • QUY CHẾ THI ĐẤU",
        fill=(160, 168, 185, 255),
        font=font_sub,
        anchor="mm",
    )

    # 3. Cột 1 Box: Codeforces Real Sync (Màu xanh dương)
    col1_left, col1_top, col1_right, col1_bottom = 35, 95, 465, 475
    draw.rounded_rectangle(
        [(col1_left, col1_top), (col1_right, col1_bottom)],
        radius=16,
        fill=(37, 39, 44, 255),
        outline=(30, 144, 255, 255),
        width=2,
    )
    # Header cột 1
    draw.rounded_rectangle(
        [(col1_left, col1_top), (col1_right, col1_top + 45)],
        radius=16,
        fill=(30, 144, 255, 40),
    )
    draw.text(
        ((col1_left + col1_right) // 2, col1_top + 23),
        "🌐 CÁCH 1: CODEFORCES SYNC",
        fill=(52, 152, 219, 255),
        font=font_col_title,
        anchor="mm",
    )

    # 4. Cột 2 Box: Discord Sandbox (Màu tím neon)
    col2_left, col2_top, col2_right, col2_bottom = 495, 95, 925, 475
    draw.rounded_rectangle(
        [(col2_left, col2_top), (col2_right, col2_bottom)],
        radius=16,
        fill=(37, 39, 44, 255),
        outline=(108, 92, 231, 255),
        width=2,
    )
    # Header cột 2
    draw.rounded_rectangle(
        [(col2_left, col2_top), (col2_right, col2_top + 45)],
        radius=16,
        fill=(108, 92, 231, 40),
    )
    draw.text(
        ((col2_left + col2_right) // 2, col2_top + 23),
        "⚖️ CÁCH 2: DISCORD SANDBOX",
        fill=(162, 155, 254, 255),
        font=font_col_title,
        anchor="mm",
    )

    # 5. Dữ liệu so sánh
    rows_cf = [
        ("Nơi nộp bài:", "Website Codeforces.com", (255, 255, 255)),
        ("Điểm thưởng:", "100% Score & Elo Chuẩn", (46, 204, 113)),
        ("Tốc độ chấm:", "Đồng bộ API mỗi 45s", (241, 196, 15)),
        ("Chẩn đoán lỗi:", "Chỉ hiện kết quả gốc", (220, 225, 235)),
        ("Chế độ thi:", "Tự động theo Codeforces", (220, 225, 235)),
        ("Ưu tiên sử dụng:", "Thi đấu chính quy & Contest", (52, 152, 219)),
    ]

    rows_dc = [
        ("Nơi nộp bài:", "Kênh #submit / /submit", (255, 255, 255)),
        ("Điểm thưởng:", "90% Score & Elo Đấu Trường", (230, 126, 34)),
        ("Tốc độ chấm:", "Siêu tốc tức thì 1 - 3 giây", (46, 204, 113)),
        ("Chẩn đoán lỗi:", "Chi tiết vị trí sai + Gợi ý fix", (162, 155, 254)),
        ("Chế độ thi:", "Tùy chọn Rated / Unrated", (220, 225, 235)),
        ("Ưu tiên sử dụng:", "Luyện tập & Phân tích lỗi", (162, 155, 254)),
    ]

    y = col1_top + 65
    for label, val, val_color in rows_cf:
        draw.text(
            (col1_left + 20, y), label, fill=(160, 168, 185, 255), font=font_label
        )
        draw.text((col1_left + 155, y), val, fill=val_color + (255,), font=font_val)
        draw.line(
            [(col1_left + 20, y + 36), (col1_right - 20, y + 36)],
            fill=(50, 53, 60, 120),
            width=1,
        )
        y += 52

    y = col2_top + 65
    for label, val, val_color in rows_dc:
        draw.text(
            (col2_left + 20, y), label, fill=(160, 168, 185, 255), font=font_label
        )
        draw.text((col2_left + 155, y), val, fill=val_color + (255,), font=font_val)
        draw.line(
            [(col2_left + 20, y + 36), (col2_right - 20, y + 36)],
            fill=(50, 53, 60, 120),
            width=1,
        )
        y += 52

    # 6. Chân ảnh (Footer)
    draw.text(
        (width // 2, 498),
        "Hyper Hub Competitive Programming System • Tự động ghi nhận & cấp Discord Role",
        fill=(120, 125, 140, 255),
        font=font_sub,
        anchor="mm",
    )

    img.save(output_path, "PNG", quality=100)
    logger.info(f"Đã tạo ảnh Infographic so sánh chế độ: {output_path}")
    return output_path
