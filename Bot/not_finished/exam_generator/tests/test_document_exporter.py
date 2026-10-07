"""Kiểm thử tự động cho DocumentExporter và DiagramDrawer.

Đảm bảo xuất 2 file riêng biệt [De_Thi] và [Huong_Dan_Giai] (DOCX & PDF),
kiểm tra dung lượng file nghiêm ngặt < 5MB và kiểm tra tính năng vẽ sơ đồ Pillow.
"""

import os
from pathlib import Path
import pytest
import docx
import fitz

try:
    from not_finished.exam_generator.services.document_exporter import document_exporter, MAX_FILE_BYTES
    from not_finished.exam_generator.services.diagram_drawer import diagram_drawer
except ImportError:
    from services.document_exporter import document_exporter, MAX_FILE_BYTES
    from services.diagram_drawer import diagram_drawer


class TestDocumentExporter:
    """Kiểm tra chức năng xuất bản tài liệu đề thi và hướng dẫn chấm."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, tmp_path):
        self.test_dir = str(tmp_path / "exam_test_output")
        Path(self.test_dir).mkdir(parents=True, exist_ok=True)
        yield
        # Cleanup handled by tmp_path

    def test_diagram_drawer_creates_valid_images(self):
        """Kiểm tra Pillow tạo đúng 3 dạng sơ đồ: Oxy, Tam giác, Flowchart."""
        oxy_path = os.path.join(self.test_dir, "oxy.png")
        tri_path = os.path.join(self.test_dir, "triangle.png")
        flow_path = os.path.join(self.test_dir, "flow.png")

        diagram_drawer.draw_coordinate_system(
            oxy_path, points=[(1, 2, "A"), (-2, 3, "B")]
        )
        assert os.path.exists(oxy_path)
        assert os.path.getsize(oxy_path) < 150 * 1024  # < 150 KB

        diagram_drawer.draw_geometric_triangle(tri_path, show_altitude=True)
        assert os.path.exists(tri_path)
        assert os.path.getsize(tri_path) < 150 * 1024

        diagram_drawer.draw_flowchart_block(
            flow_path, steps=["Start", "Nhập A", "Xử lý", "Kết thúc"]
        )
        assert os.path.exists(flow_path)
        assert os.path.getsize(flow_path) < 150 * 1024

    def test_export_all_creates_dual_files_under_5mb(self):
        """Kiểm tra xuất 2 bộ tài liệu riêng biệt định dạng Word và PDF, kích thước < 5MB."""
        oxy_path = os.path.join(self.test_dir, "oxy_diagram.png")
        diagram_drawer.draw_coordinate_system(oxy_path)

        metadata = {
            "job_id": "TEST-888",
            "subject": "Toán Học Lớp 12",
            "exam_code": "HH-888",
            "duration": "90 phút",
            "length_tier": "Vừa",
        }

        exam_data = {
            "questions": [
                {
                    "type": "section_header",
                    "title": "PHẦN I: TRẮC NGHIỆM KHÁCH QUAN",
                },
                {
                    "type": "question",
                    "number": "1",
                    "points": "0.5 điểm",
                    "text": "Tìm tập xác định của hàm số y = log2(x - 3).",
                    "options": ["A. (3; +∞)", "B. [3; +∞)", "C. (-∞; 3)", "D. R \\ {3}"],
                    "has_diagram": False,
                },
                {
                    "type": "section_header",
                    "title": "PHẦN II: TỰ LUẬN NÂNG CAO",
                },
                {
                    "type": "question",
                    "number": "2",
                    "points": "2.0 điểm",
                    "text": "Cho hàm số y = f(x) có đồ thị như hình vẽ bên dưới.",
                    "sub_items": [
                        {"label": "a", "text": "Tìm các khoảng đơn điệu của hàm số."},
                        {"label": "b", "text": "Tìm giá trị lớn nhất và nhỏ nhất trên đoạn [-1; 3]."},
                    ],
                    "has_diagram": True,
                },
            ],
            "solutions": [
                {
                    "number": "1",
                    "is_multiple_choice": True,
                    "correct_key": "A",
                    "explanation": "Điều kiện xác định: x - 3 > 0 <=> x > 3. Vậy D = (3; +∞).",
                    "common_mistakes": "Học sinh hay nhầm dấu ngoặc vuông [3; +∞).",
                    "rubric": [("Đặt điều kiện đúng", 0.25), ("Kết luận đúng tập xác định A", 0.25)],
                },
                {
                    "number": "2",
                    "is_multiple_choice": False,
                    "explanation": "Lời giải tự luận chi tiết từng bước cho ý a và b.",
                    "rubric": [("Xác định đạo hàm ý a", 1.0), ("Tính min max ý b", 1.0)],
                },
            ],
        }

        results = document_exporter.export_all(
            metadata=metadata,
            exam_data=exam_data,
            output_format="Both",
            output_dir=self.test_dir,
            diagram_paths=[oxy_path],
        )

        exam_files = results["exam_files"]
        sol_files = results["solution_files"]

        # 1. Kiểm tra tồn tại đủ cả 4 file (2 file Đề Thi DOCX+PDF và 2 file Lời Giải DOCX+PDF)
        assert len(exam_files) == 2
        assert len(sol_files) == 2

        # 2. Kiểm tra định dạng và dung lượng mỗi file < 5MB
        for file_path in exam_files + sol_files:
            assert os.path.exists(file_path), f"File {file_path} không tồn tại!"
            file_size = os.path.getsize(file_path)
            assert file_size > 0, f"File {file_path} bị rỗng!"
            assert file_size < MAX_FILE_BYTES, f"File {file_path} vượt quá 5MB ({file_size} bytes)!"

        # 3. Kiểm tra tính độc lập nội dung: Đề thi không được lộ đáp án trắc nghiệm
        exam_docx_path = [p for p in exam_files if p.endswith(".docx")][0]
        doc = docx.Document(exam_docx_path)
        full_exam_text = "\n".join([p.text for p in doc.paragraphs])
        assert "HƯỚNG DẪN GIẢI CHI TIẾT" not in full_exam_text
        assert "BẢNG ĐÁP ÁN TRẮC NGHIỆM" not in full_exam_text
        assert "Thang điểm (Rubric)" not in full_exam_text
        assert "Điều kiện xác định: x - 3 > 0" not in full_exam_text  # Không có lời giải
        assert "HyperHub AI Platform" in full_exam_text  # Đảm bảo watermark ẩn được chèn

        # 4. Kiểm tra watermark ẩn trong file PDF khi bôi đen trích xuất
        exam_pdf_path = [p for p in exam_files if p.endswith(".pdf")][0]
        pdf_doc = fitz.open(exam_pdf_path)
        pdf_text = "".join([page.get_text() for page in pdf_doc]).replace("\xa0", " ")
        assert "HyperHub AI" in pdf_text
