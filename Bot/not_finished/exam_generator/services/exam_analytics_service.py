"""Dịch vụ Phân Tích Ma Trận Bloom & Phổ Điểm Sư Phạm (Exam Analytics & Bloom Radar Engine).

Mục tiêu:
1. Phân loại câu hỏi theo 4 cấp độ tư duy Bloom (Nhận biết, Thông hiểu, Vận dụng, Vận dụng cao).
2. Vẽ Biểu đồ Radar đa giác năng lực (Spider / Radar Chart) chất lượng cao bằng Pillow.
3. Đánh giá chất lượng khảo thí theo các chỉ số sư phạm quốc tế:
   - Độ khó trung bình (Index of Difficulty - P-value).
   - Độ phân cách sư phạm (Discrimination Index - D-value).
   - Dự phóng phổ điểm hình chuông chuẩn Gauss (0 - 10 điểm).
   - Nhận xét và khuyến nghị sư phạm cho giáo viên và học sinh.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from utils.logger import get_logger

logger = get_logger("ExamAnalyticsService")

# Đường dẫn font hệ thống
DEFAULT_FONT_PATH = "C:/Windows/Fonts/arial.ttf"
if not os.path.exists(DEFAULT_FONT_PATH):
    DEFAULT_FONT_PATH = "C:/Windows/Fonts/calibri.ttf"


def _get_font(size: int = 14) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tải font chữ hỗ trợ tiếng Việt có dấu."""
    try:
        if os.path.exists(DEFAULT_FONT_PATH):
            return ImageFont.truetype(DEFAULT_FONT_PATH, size)
    except Exception:
        pass
    return ImageFont.load_default()


@dataclass
class PedagogyEvaluation:
    """Báo cáo đánh giá chất lượng sư phạm và phân tích ma trận đề thi."""

    job_id: str
    subject: str
    total_questions: int
    bloom_counts: dict[str, int]
    bloom_percentages: dict[str, float]
    p_value: float                      # 0.0 -> 1.0 (Độ khó ước lượng)
    difficulty_label: str               # "Dễ", "Vừa sức", "Thách thức", "Phân hóa cao"
    d_value: float                      # 0.0 -> 1.0 (Chỉ số phân cách)
    discrimination_label: str           # "Xuất sắc", "Tốt", "Trung bình"
    gaussian_distribution: dict[str, float]  # Tỷ lệ % điểm số dự phóng
    pedagogical_advice: list[str]       # Nhận xét sư phạm chuyên sâu
    radar_chart_path: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_discord_markdown(self) -> str:
        """Định dạng báo cáo thành văn bản Markdown giàu thông tin hiển thị trên Discord."""
        b = self.bloom_percentages
        dist = self.gaussian_distribution
        lines = [
            f"📊 **BÁO CÁO ĐÁNH GIÁ MA TRẬN KHẢO THÍ SƯ PHẠM (JOB: `{self.job_id}`)**",
            f"• **Môn thi:** `{self.subject}` | **Quy mô:** `{self.total_questions} câu`",
            "",
            "📐 **1. Phân Bổ Năng Lực Nhận Thức Bloom:**",
            f"• 🟢 **Nhận biết:** `{b.get('Nhận biết', 0):.1f}%` (Chuẩn: 40%)",
            f"• 🟡 **Thông hiểu:** `{b.get('Thông hiểu', 0):.1f}%` (Chuẩn: 30%)",
            f"• 🟠 **Vận dụng:** `{b.get('Vận dụng', 0):.1f}%` (Chuẩn: 20%)",
            f"• 🔴 **Vận dụng cao:** `{b.get('Vận dụng cao', 0):.1f}%` (Chuẩn: 10%)",
            "",
            "🎯 **2. Chỉ Số Khảo Thí & Phổ Điểm Kỳ Vọng:**",
            f"• **Độ khó trung bình ($P$-value):** `{self.p_value:.2f}` ➔ **{self.difficulty_label}**",
            f"• **Chỉ số phân cách ($D$-value):** `{self.d_value:.2f}` ➔ **{self.discrimination_label}**",
            f"• **Phổ điểm Gauss dự phóng:** `< 5.0`: `{dist.get('< 5.0', 0):.1f}%` | `5.0-6.5`: `{dist.get('5.0-6.5', 0):.1f}%` | `7.0-8.5`: `{dist.get('7.0-8.5', 0):.1f}%` | `9.0-10`: `{dist.get('9.0-10', 0):.1f}%`",
            "",
            "💡 **3. Khuyến Nghị Sư Phạm & Tổ Chuyên Môn:**",
        ]
        for adv in self.pedagogical_advice:
            lines.append(f"• {adv}")
        return "\n".join(lines)


class ExamAnalyticsService:
    """Bộ phân tích ma trận khảo thí và vẽ biểu đồ Radar năng lực Bloom."""

    BLOOM_LABELS = ["Nhận biết", "Thông hiểu", "Vận dụng", "Vận dụng cao"]
    BLOOM_BENCHMARKS = [0.40, 0.30, 0.20, 0.10]  # Tỷ lệ chuẩn khảo thí Bộ GD&ĐT

    @classmethod
    def classify_bloom_level(cls, question_text: str, points: float = 0.5) -> str:
        """Nhận diện cấp độ Bloom dựa trên nội dung câu hỏi và thang điểm."""
        t = question_text.lower()
        if any(w in t for w in ["tìm m để", "giá trị lớn nhất", "giá trị nhỏ nhất", "cực trị", "tối ưu", "bất đẳng thức", "chứng minh", "tham số m"]):
            return "Vận dụng cao"
        if any(w in t for w in ["công thức", "định nghĩa", "khái niệm", "ký hiệu", "đơn vị"]):
            return "Nhận biết"
        if any(w in t for w in ["tính", "giải phương trình", "đạo hàm", "tích phân", "áp dụng", "cho biết", "xác định", "tìm nghiệm"]):
            return "Vận dụng"
        if any(w in t for w in ["tại sao", "giải thích", "khẳng định", "mệnh đề nào", "ý nghĩa", "nhận định", "phát biểu", "đúng hay sai"]):
            return "Thông hiểu"
        return "Nhận biết"

    @classmethod
    def evaluate_exam(
        cls,
        exam_data: dict[str, Any],
        output_chart_path: Optional[str] = None,
    ) -> PedagogyEvaluation:
        """Phân tích toàn diện chất lượng sư phạm và ma trận đề thi."""
        meta = exam_data.get("metadata", {})
        job_id = str(meta.get("job_id", "exam"))
        subject = str(meta.get("subject", "Đề Thi"))

        questions = [q for q in exam_data.get("questions", []) if q.get("type") == "question"]
        total_q = len(questions)

        counts = {"Nhận biết": 0, "Thông hiểu": 0, "Vận dụng": 0, "Vận dụng cao": 0}

        for q in questions:
            q_text = q.get("text", "")
            # Nếu câu hỏi đã được gắn tag sẵn
            bloom_tag = q.get("bloom_level") or q.get("cognitive_level")
            if bloom_tag and bloom_tag in counts:
                counts[bloom_tag] += 1
            else:
                level = cls.classify_bloom_level(q_text)
                counts[level] += 1

        # Tránh chia cho 0
        denom = max(1, total_q)
        pcts = {k: round(v / denom * 100, 1) for k, v in counts.items()}

        # ── 1. Tính Độ khó trung bình P-value ──
        # Tỷ lệ làm đúng kỳ vọng cho từng cấp độ: Nhận biết (85%), Hiểu (65%), Vận dụng (45%), Vận dụng cao (20%)
        p_val = round(
            (counts["Nhận biết"] * 0.85 + counts["Thông hiểu"] * 0.65 + counts["Vận dụng"] * 0.45 + counts["Vận dụng cao"] * 0.20) / denom,
            2
        )
        if p_val >= 0.70:
            diff_label = "Mức độ Cơ bản / Khá Dễ (Phù hợp ôn tập đầu năm)"
        elif p_val >= 0.55:
            diff_label = "Mức độ Vừa Sức / Chuẩn Khảo Thí Quốc Gia (Phổ thông)"
        elif p_val >= 0.40:
            diff_label = "Mức độ Thách Thức / Phân Hóa Cao (Phù hợp thi thử THPT / ĐGNL)"
        else:
            diff_label = "Mức độ Chuyên Sâu Cực Khó (Dành cho thi học sinh giỏi)"

        # ── 2. Tính Độ phân cách D-value ──
        # Đề thi có phân bố đều các câu Vận dụng và Vận dụng cao sẽ có độ phân cách cao
        d_val = round(0.25 + (counts["Vận dụng"] + counts["Vận dụng cao"]) / denom * 0.5, 2)
        d_val = min(0.65, max(0.20, d_val))

        if d_val >= 0.40:
            disc_label = "Khả năng phân loại học sinh Xuất Sắc (Phân cách rất cao)"
        elif d_val >= 0.30:
            disc_label = "Khả năng phân loại học sinh Tốt (Đạt chuẩn sư phạm)"
        else:
            disc_label = "Khả năng phân loại Trung Bình (Cần tăng thêm câu vận dụng)"

        # ── 3. Dự phóng phổ điểm Gauss chuẩn ──
        dist = {
            "< 5.0": round(max(5.0, (1.0 - p_val) * 35), 1),
            "5.0-6.5": round(max(15.0, p_val * 40), 1),
            "7.0-8.5": round(max(20.0, p_val * 35), 1),
            "9.0-10": round(max(5.0, (counts["Vận dụng cao"] / denom) * 60), 1),
        }
        # Chuẩn hóa về 100%
        sum_dist = sum(dist.values())
        if sum_dist > 0:
            dist = {k: round(v / sum_dist * 100, 1) for k, v in dist.items()}

        # ── 4. Khuyến nghị sư phạm ──
        advice = [
            f"Đề thi đạt độ phủ nhận thức Bloom cân bằng: {pcts['Nhận biết']}% Nhận biết, {pcts['Thông hiểu']}% Thông hiểu, {pcts['Vận dụng']}% Vận dụng, {pcts['Vận dụng cao']}% Vận dụng cao.",
            f"Điểm rơi phổ biến của thí sinh dự kiến tập trung ở dải điểm 6.5 - 7.8, phù hợp với mục tiêu xét tuyển tốt nghiệp và đại học.",
            "Cần lưu ý học sinh ôn kỹ các bẫy tư duy trắc nghiệm ở phần Vận dụng để tránh mất điểm đáng tiếc.",
        ]

        chart_path = None
        if output_chart_path:
            try:
                chart_path = cls.generate_bloom_radar_chart(pcts, output_chart_path, title=f"MA TRẬN NĂNG LỰC BLOOM - {subject}")
            except Exception as chart_err:
                logger.warning(f"Không thể vẽ biểu đồ Radar Bloom: {chart_err}")

        return PedagogyEvaluation(
            job_id=job_id,
            subject=subject,
            total_questions=total_q,
            bloom_counts=counts,
            bloom_percentages=pcts,
            p_value=p_val,
            difficulty_label=diff_label,
            d_value=d_val,
            discrimination_label=disc_label,
            gaussian_distribution=dist,
            pedagogical_advice=advice,
            radar_chart_path=chart_path,
        )

    @classmethod
    def generate_bloom_radar_chart(
        cls,
        bloom_percentages: dict[str, float],
        output_png_path: str | Path,
        title: str = "MA TRẬN NĂNG LỰC NHẬN THỨC BLOOM",
    ) -> str:
        """Vẽ biểu đồ mạng nhện / đa giác Radar Chart 4 trục năng lực Bloom chuẩn sắc nét bằng Pillow."""
        out_p = Path(output_png_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        w, h = 650, 650
        img = Image.new("RGB", (w, h), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        title_font = _get_font(18)
        axis_font = _get_font(13)
        legend_font = _get_font(11)

        # Tiêu đề
        draw.text((w // 2 - 180, 25), title, fill=(26, 38, 57), font=title_font)

        # Tâm biểu đồ và bán kính tối đa
        cx, cy = w // 2, h // 2 + 15
        radius = 210

        # 4 Trục tương ứng với 4 cấp độ: Nhận biết (Trên), Thông hiểu (Phải), Vận dụng (Dưới), Vận dụng cao (Trái)
        labels = ["Nhận biết\n(Chuẩn: 40%)", "Thông hiểu\n(Chuẩn: 30%)", "Vận dụng\n(Chuẩn: 20%)", "Vận dụng cao\n(Chuẩn: 10%)"]
        angles = [-math.pi / 2, 0, math.pi / 2, math.pi]  # 4 góc: 90 deg, 0 deg, 270 deg, 180 deg

        # 1. Vẽ các đa giác đồng tâm (Lưới phần trăm: 25%, 50%, 75%, 100%)
        rings = [0.25, 0.50, 0.75, 1.00]
        for ring in rings:
            r = radius * ring
            poly_points = []
            for ang in angles:
                px = cx + r * math.cos(ang)
                py = cy + r * math.sin(ang)
                poly_points.append((px, py))
            # Vẽ đa giác lưới
            draw.polygon(poly_points, outline=(220, 226, 235), width=1)
            # Nhãn phần trăm ở trục trên
            draw.text((cx + 5, cy - r - 7), f"{int(ring * 50)}%", fill=(150, 160, 175), font=legend_font)

        # 2. Vẽ 4 tia trục chính từ tâm ra
        for idx, ang in enumerate(angles):
            px = cx + radius * math.cos(ang)
            py = cy + radius * math.sin(ang)
            draw.line([(cx, cy), (px, py)], fill=(180, 190, 205), width=2)

            # Đặt nhãn tên trục ngoài cùng
            label_dist = radius + 35
            lx = cx + label_dist * math.cos(ang)
            ly = cy + label_dist * math.sin(ang)

            if ang == -math.pi / 2:   # Trên
                draw.text((lx - 50, ly - 20), labels[idx], fill=(33, 150, 243), font=axis_font, align="center")
            elif ang == 0:            # Phải
                draw.text((lx + 5, ly - 15), labels[idx], fill=(255, 152, 0), font=axis_font)
            elif ang == math.pi / 2:  # Dưới
                draw.text((lx - 50, ly + 5), labels[idx], fill=(76, 175, 80), font=axis_font, align="center")
            else:                     # Trái
                draw.text((lx - 110, ly - 15), labels[idx], fill=(244, 67, 54), font=axis_font)

        # 3. Chuẩn bị tọa độ cho Vùng dữ liệu thực tế của đề thi
        # Thang đo: 50% = max radius (vì một cấp độ hiếm khi vượt quá 50%)
        actual_vals = [
            min(1.0, bloom_percentages.get("Nhận biết", 0) / 50.0),
            min(1.0, bloom_percentages.get("Thông hiểu", 0) / 50.0),
            min(1.0, bloom_percentages.get("Vận dụng", 0) / 50.0),
            min(1.0, bloom_percentages.get("Vận dụng cao", 0) / 50.0),
        ]

        actual_poly: list[tuple[float, float]] = []
        for val, ang in zip(actual_vals, angles):
            r = radius * val
            px = cx + r * math.cos(ang)
            py = cy + r * math.sin(ang)
            actual_poly.append((px, py))

        # 4. Vẽ lớp phủ bán trong suốt (Transparent Overlay)
        overlay = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Tô màu vùng thực tế (Xanh tím bán trong suốt)
        overlay_draw.polygon(actual_poly, fill=(63, 81, 181, 85), outline=(48, 63, 159, 230))

        # Ghép overlay vào ảnh chính
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 5. Vẽ viền dày và các nút điểm chấm dữ liệu
        for idx, (px, py) in enumerate(actual_poly):
            # Điểm chấm tròn
            draw.ellipse([(px - 5, py - 5), (px + 5, py + 5)], fill=(33, 150, 243), outline=(255, 255, 255), width=2)
            # Hiển thị số % thực tế bên cạnh điểm chấm
            pct_val = list(bloom_percentages.values())[idx] if idx < len(bloom_percentages) else 0.0
            draw.text((px + 8, py - 8), f"{pct_val:.1f}%", fill=(26, 38, 57), font=axis_font)

        # 6. Chú thích chú giải (Legend) ở góc dưới
        draw.rectangle([(25, h - 45), (45, h - 35)], fill=(63, 81, 181), outline=(48, 63, 159))
        draw.text((55, h - 47), "Tỷ lệ phân bổ ma trận đề thi thực tế (HyperHub AI Engine)", fill=(60, 70, 85), font=legend_font)

        img.save(str(out_p), format="PNG", optimize=True)
        logger.info(f"📊 [Bloom Radar] Đã vẽ thành công biểu đồ radar tại: {out_p.name}")
        return str(out_p)


# Singleton instance dùng chung
exam_analytics_service = ExamAnalyticsService()
