"""Kiểm thử tự động cho ExamAnalyticsService (Phân tích ma trận khảo thí & Biểu đồ Radar Bloom)."""

import os
import tempfile
from PIL import Image

try:
    from not_finished.exam_generator.services.exam_analytics_service import (
        PedagogyEvaluation,
        exam_analytics_service,
    )
except ImportError:
    from services.exam_analytics_service import (
        PedagogyEvaluation,
        exam_analytics_service,
    )


def test_classify_bloom_level():
    """Kiểm tra độ chính xác phân loại cấp độ tư duy nhận thức Bloom."""
    assert exam_analytics_service.classify_bloom_level("Tìm m để hàm số đạt cực đại tại x = 1") == "Vận dụng cao"
    assert exam_analytics_service.classify_bloom_level("Tính giá trị của biểu thức P = a + b") == "Vận dụng"
    assert exam_analytics_service.classify_bloom_level("Khẳng định nào sau đây là đúng về đồ thị hàm số?") == "Thông hiểu"
    assert exam_analytics_service.classify_bloom_level("Công thức tính diện tích hình tròn bán kính R là gì?") == "Nhận biết"


def test_evaluate_exam_metrics():
    """Kiểm tra tính toán các chỉ số khảo thí sư phạm (P-value, D-value, Gauss)."""
    exam_data = {
        "metadata": {
            "job_id": "TEST-JOB-001",
            "subject": "Toán 12",
        },
        "questions": [
            {"type": "question", "number": "1", "text": "Công thức nghiệm phương trình bậc hai là gì?"},
            {"type": "question", "number": "2", "text": "Mệnh đề nào sau đây đúng về hàm đồng biến?"},
            {"type": "question", "number": "3", "text": "Tính tích phân I = int(x * dx)"},
            {"type": "question", "number": "4", "text": "Tìm m để phương trình có 3 nghiệm phân biệt và đạt giá trị lớn nhất"},
        ],
    }

    eval_res: PedagogyEvaluation = exam_analytics_service.evaluate_exam(exam_data)

    # 1. Số lượng câu hỏi
    assert eval_res.total_questions == 4

    # 2. Phân bổ ma trận Bloom
    assert eval_res.bloom_counts["Nhận biết"] == 1
    assert eval_res.bloom_counts["Thông hiểu"] == 1
    assert eval_res.bloom_counts["Vận dụng"] == 1
    assert eval_res.bloom_counts["Vận dụng cao"] == 1
    assert eval_res.bloom_percentages["Nhận biết"] == 25.0

    # 3. Chỉ số P-value và D-value nằm trong khoảng hợp lệ
    assert 0.0 <= eval_res.p_value <= 1.0
    assert 0.20 <= eval_res.d_value <= 0.65
    assert len(eval_res.difficulty_label) > 0
    assert len(eval_res.discrimination_label) > 0

    # 4. Phổ điểm Gauss dự phóng
    assert "< 5.0" in eval_res.gaussian_distribution
    assert "9.0-10" in eval_res.gaussian_distribution
    assert round(sum(eval_res.gaussian_distribution.values())) in (99, 100, 101)

    # 5. Khuyến nghị sư phạm
    assert len(eval_res.pedagogical_advice) >= 2

    # 6. Format Discord Markdown
    md = eval_res.to_discord_markdown()
    assert "BÁO CÁO ĐÁNH GIÁ MA TRẬN KHẢO THÍ SƯ PHẠM" in md
    assert "Nhận biết" in md
    assert "Gauss" in md


def test_generate_bloom_radar_chart():
    """Kiểm tra render file ảnh Biểu đồ Radar đa giác Bloom chuẩn xác bằng Pillow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chart_file = os.path.join(tmp_dir, "test_bloom_radar.png")

        bloom_pcts = {
            "Nhận biết": 40.0,
            "Thông hiểu": 30.0,
            "Vận dụng": 20.0,
            "Vận dụng cao": 10.0,
        }

        out_path = exam_analytics_service.generate_bloom_radar_chart(
            bloom_percentages=bloom_pcts,
            output_png_path=chart_file,
            title="MA TRẬN NĂNG LỰC TOÁN 12",
        )

        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 1000

        # Kiểm tra tính toàn vẹn của file ảnh PNG
        with Image.open(out_path) as img:
            assert img.format == "PNG"
            assert img.size == (650, 650)
