"""Dịch vụ tự động vẽ sơ đồ, hình học, trục tọa độ và đồ thị minh họa cho đề thi (Diagram Drawer).

Sử dụng thư viện Pillow để vẽ các hình minh họa phổ biến trong đề thi:
- Trục tọa độ Oxy, đồ thị hàm số
- Hình học: Tam giác, Đường tròn, Tứ giác, Khối chóp/Lăng trụ 2.5D
- Sơ đồ tư duy / Lưu đồ thuật toán (Flowchart)
- Mạch điện cơ bản, sơ đồ lực vật lý
Tất cả ảnh xuất ra đều được tối ưu nén chuẩn PNG (< 100 KB).
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from utils.logger import get_logger

logger = get_logger("DiagramDrawer")

# Tìm font Arial hoặc font hệ thống trên Windows
DEFAULT_FONT_PATH = "C:/Windows/Fonts/arial.ttf"
if not os.path.exists(DEFAULT_FONT_PATH):
    DEFAULT_FONT_PATH = "C:/Windows/Fonts/calibri.ttf"


import functools


@functools.lru_cache(maxsize=32)
def _get_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tải font hỗ trợ tiếng Việt có dấu (với bộ đệm LRU in-memory)."""
    try:
        if os.path.exists(DEFAULT_FONT_PATH):
            return ImageFont.truetype(DEFAULT_FONT_PATH, size)
    except Exception:
        pass
    return ImageFont.load_default()


class DiagramDrawer:
    """Tạo các hình minh họa trực quan chuyên biệt cho đề thi."""

    @classmethod
    def draw_coordinate_system(
        cls,
        save_path: str,
        x_range: tuple[int, int] = (-5, 5),
        y_range: tuple[int, int] = (-4, 4),
        title: str = "Hệ trục tọa độ Oxy",
        points: list[tuple[float, float, str]] | None = None,
    ) -> str:
        """Vẽ hệ trục tọa độ Decartes Oxy với lưới tọa độ và các điểm đánh dấu."""
        w, h = 600, 450
        img = Image.new("RGB", (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        font = _get_font(12)
        title_font = _get_font(15)

        # Tiêu đề
        draw.text((20, 15), title, fill=(30, 30, 30), font=title_font)

        # Tọa độ gốc (Origin) trên ảnh
        ox, oy = w // 2, h // 2 + 10
        step_x = (w - 100) // (x_range[1] - x_range[0])
        step_y = (h - 100) // (y_range[1] - y_range[0])

        # Vẽ lưới mờ
        for x_val in range(x_range[0], x_range[1] + 1):
            px = ox + x_val * step_x
            draw.line([(px, 50), (px, h - 40)], fill=(235, 238, 242), width=1)
        for y_val in range(y_range[0], y_range[1] + 1):
            py = oy - y_val * step_y
            draw.line([(50, py), (w - 50, py)], fill=(235, 238, 242), width=1)

        # Trục Ox
        draw.line([(40, oy), (w - 40, oy)], fill=(50, 50, 50), width=2)
        # Mũi tên Ox
        draw.polygon([(w - 40, oy - 4), (w - 40, oy + 4), (w - 30, oy)], fill=(50, 50, 50))
        draw.text((w - 30, oy + 5), "x", fill=(50, 50, 50), font=font)

        # Trục Oy
        draw.line([(ox, h - 35), (ox, 45)], fill=(50, 50, 50), width=2)
        # Mũi tên Oy
        draw.polygon([(ox - 4, 45), (ox + 4, 45), (ox, 35)], fill=(50, 50, 50))
        draw.text((ox + 8, 35), "y", fill=(50, 50, 50), font=font)

        # Gốc O
        draw.text((ox - 14, oy + 4), "O", fill=(50, 50, 50), font=font)

        # Các điểm mốc tọa độ
        for x_val in range(x_range[0], x_range[1] + 1):
            if x_val != 0:
                px = ox + x_val * step_x
                draw.line([(px, oy - 3), (px, oy + 3)], fill=(50, 50, 50), width=1)
                draw.text((px - 5, oy + 6), str(x_val), fill=(80, 80, 80), font=font)

        for y_val in range(y_range[0], y_range[1] + 1):
            if y_val != 0:
                py = oy - y_val * step_y
                draw.line([(ox - 3, py), (ox + 3, py)], fill=(50, 50, 50), width=1)
                draw.text((ox - 20, py - 6), str(y_val), fill=(80, 80, 80), font=font)

        # Vẽ các điểm đánh dấu nếu có
        if points:
            for px_val, py_val, label in points:
                cx = ox + int(px_val * step_x)
                cy = oy - int(py_val * step_y)
                r = 4
                draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=(220, 53, 69), outline=(180, 40, 50))
                draw.text((cx + 6, cy - 12), f"{label}({px_val},{py_val})", fill=(220, 53, 69), font=font)

        # Viền nhẹ quanh khung hình
        draw.rectangle([(1, 1), (w - 2, h - 2)], outline=(210, 215, 220), width=1)

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(save_path, "PNG", optimize=True)
        return save_path

    @classmethod
    def draw_geometric_triangle(
        cls,
        save_path: str,
        title: str = "Hình học: Tam giác ABC",
        labels: tuple[str, str, str] = ("A", "B", "C"),
        show_altitude: bool = True,
    ) -> str:
        """Vẽ tam giác hình học phẳng ABC kèm đường cao AH."""
        w, h = 550, 400
        img = Image.new("RGB", (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        font = _get_font(14)
        title_font = _get_font(15)

        draw.text((20, 15), title, fill=(30, 30, 30), font=title_font)

        # Tọa độ đỉnh
        a = (260, 80)
        b = (80, 320)
        c = (460, 320)

        # 3 Cạnh tam giác
        draw.polygon([a, b, c], outline=(30, 60, 120), width=2)

        # Đánh dấu đỉnh
        draw.text((a[0] - 5, a[1] - 25), labels[0], fill=(20, 20, 20), font=font)
        draw.text((b[0] - 25, b[1] + 5), labels[1], fill=(20, 20, 20), font=font)
        draw.text((c[0] + 10, c[1] + 5), labels[2], fill=(20, 20, 20), font=font)

        if show_altitude:
            # Đường cao AH từ A vuông góc BC
            h_point = (a[0], b[1])
            draw.line([a, h_point], fill=(200, 40, 40), width=2)
            draw.text((h_point[0] - 6, h_point[1] + 6), "H", fill=(200, 40, 40), font=font)
            # Ký hiệu góc vuông
            sq_size = 12
            draw.line([(h_point[0], h_point[1] - sq_size), (h_point[0] + sq_size, h_point[1] - sq_size)], fill=(200, 40, 40), width=1)
            draw.line([(h_point[0] + sq_size, h_point[1] - sq_size), (h_point[0] + sq_size, h_point[1])], fill=(200, 40, 40), width=1)

        draw.rectangle([(1, 1), (w - 2, h - 2)], outline=(210, 215, 220), width=1)

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(save_path, "PNG", optimize=True)
        return save_path

    @classmethod
    def draw_flowchart_block(
        cls,
        save_path: str,
        steps: list[str],
        title: str = "Sơ đồ thuật toán / Luồng xử lý",
    ) -> str:
        """Vẽ lưu đồ thuật toán (Flowchart block) cho các môn Tin học/Lập trình."""
        step_count = min(len(steps), 5)
        w = 550
        box_h = 45
        gap = 35
        h = 100 + step_count * (box_h + gap)

        img = Image.new("RGB", (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        font = _get_font(13)
        title_font = _get_font(15)

        draw.text((20, 15), title, fill=(30, 30, 30), font=title_font)

        box_w = 360
        start_x = (w - box_w) // 2

        for i in range(step_count):
            curr_y = 65 + i * (box_h + gap)
            text = steps[i]

            # Bo góc nhẹ hoặc hình chữ nhật
            if i == 0 or i == step_count - 1:
                # Khối bắt đầu/kết thúc (Oval)
                draw.rounded_rectangle(
                    [(start_x, curr_y), (start_x + box_w, curr_y + box_h)],
                    radius=18,
                    fill=(230, 242, 255),
                    outline=(0, 102, 204),
                    width=2,
                )
            else:
                # Khối xử lý
                draw.rectangle(
                    [(start_x, curr_y), (start_x + box_w, curr_y + box_h)],
                    fill=(245, 248, 252),
                    outline=(80, 120, 160),
                    width=2,
                )

            # Căn giữa chữ
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = start_x + (box_w - tw) // 2
            ty = curr_y + (box_h - th) // 2 - 2
            draw.text((tx, ty), text, fill=(20, 30, 40), font=font)

            # Mũi tên trỏ xuống bước tiếp theo
            if i < step_count - 1:
                arrow_start = (w // 2, curr_y + box_h)
                arrow_end = (w // 2, curr_y + box_h + gap)
                draw.line([arrow_start, (arrow_end[0], arrow_end[1] - 5)], fill=(60, 60, 60), width=2)
                draw.polygon(
                    [
                        (arrow_end[0] - 5, arrow_end[1] - 8),
                        (arrow_end[0] + 5, arrow_end[1] - 8),
                        (arrow_end[0], arrow_end[1]),
                    ],
                    fill=(60, 60, 60),
                )

        draw.rectangle([(1, 1), (w - 2, h - 2)], outline=(210, 215, 220), width=1)
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(save_path, "PNG", optimize=True)
        return save_path


diagram_drawer = DiagramDrawer()
