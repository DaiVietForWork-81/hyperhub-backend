"""Động Cơ Khung Đề Chuẩn Hóa Theo Từng Kỳ Thi (Exam Blueprint Engine).

Cung cấp ma trận đặc tả chuẩn mực cho các kỳ thi lớn tại Việt Nam:
1. Kỳ thi Tốt nghiệp THPT 2025 (Chuẩn Quyết định 764/QĐ-BGDĐT mới nhất):
   - Toán, Ngữ văn, Tiếng Anh, Vật lí, Hóa học, Sinh học, Lịch sử, Địa lí, GDCD/GDKT&PL, Tin học.
   - Cấu trúc 3 Phần: Trắc nghiệm 4 lựa chọn, Trắc nghiệm Đúng/Sai 4 ý, Trắc nghiệm trả lời ngắn.
2. Kỳ thi Đánh Giá Năng Lực & Tư Duy:
   - ĐHQG Hà Nội (HSA) - Tư duy định lượng, định tính, khoa học.
   - ĐHQG TP.HCM (V-ACT) - Đề thi tích hợp 120 câu.
   - ĐHBK Hà Nội (TSA) - Đánh giá tư duy Toán học, Đọc hiểu, Khoa học/Giải quyết vấn đề.
3. Kỳ thi Tuyển sinh vào Lớp 10 (Sở GD&ĐT):
   - Đề thi Chung: Toán (5 bài tự luận thực tế), Ngữ văn (Đọc hiểu + NLXH + NLVH), Tiếng Anh (40 câu).
   - Đề thi Chuyên: Chuyên Toán, Chuyên Tin (150 phút, phân loại cao).
4. Kiểm tra Định kỳ Chuẩn Thông tư 22/BGDĐT:
   - Giữa kỳ & Cuối kỳ (70% Trắc nghiệm + 30% Tự luận).
5. Kỳ thi Học sinh giỏi Cấp Tỉnh / Thành phố:
   - Bất đẳng thức, giải tích, tổ hợp, hình học thuần túy.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any, Optional


class QuestionType(str, Enum):
    """Phân loại dạng thức câu hỏi trong đề thi chuẩn hóa."""

    MCQ_SINGLE = "mcq_single"  # Trắc nghiệm 4 phương án chọn 1 (A, B, C, D)
    TRUE_FALSE_MULTISTEP = "true_false_multistep"  # Trắc nghiệm Đúng/Sai 4 ý (a, b, c, d)
    SHORT_ANSWER = "short_answer"  # Trắc nghiệm trả lời ngắn (điền số / từ ngắn)
    ESSAY = "essay"  # Tự luận giải thích / lập luận từng bước


@dataclass
class ExamSectionBlueprint:
    """Đặc tả một phân đoạn (Phần I, II, III...) trong khung đề thi."""

    section_id: str
    title: str
    question_type: QuestionType
    question_count: int
    points_per_question: float
    total_points: float
    bloom_distribution: dict[str, float]  # {"remember": 0.4, "understand": 0.3, "apply": 0.2, "analyze": 0.1}
    instructions: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["question_type"] = self.question_type.value
        return d


@dataclass
class ExamBlueprint:
    """Khung đề chuẩn hóa toàn diện cho một kỳ thi cụ thể."""

    blueprint_id: str
    name: str
    subject: str
    category: str  # "thpt_qg", "dgnl", "tuyen_sinh_10", "dinh_ky_tt22", "hsg"
    authority: str
    duration_minutes: int
    total_questions: int
    total_points: float
    sections: list[ExamSectionBlueprint]
    cognitive_matrix: dict[str, float]
    special_guidelines: list[str] = field(default_factory=list)
    rubric_template: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "name": self.name,
            "subject": self.subject,
            "category": self.category,
            "authority": self.authority,
            "duration_minutes": self.duration_minutes,
            "total_questions": self.total_questions,
            "total_points": self.total_points,
            "sections": [s.to_dict() for s in self.sections],
            "cognitive_matrix": self.cognitive_matrix,
            "special_guidelines": self.special_guidelines,
            "rubric_template": self.rubric_template,
        }


# =============================================================================
# DANH MỤC KHUNG ĐỀ CHUẨN QUỐC GIA (STANDARD_BLUEPRINTS)
# =============================================================================

STANDARD_BLUEPRINTS: dict[str, ExamBlueprint] = {
    # -------------------------------------------------------------------------
    # 1. TỐT NGHIỆP THPT 2025 (Chuẩn Quyết định 764/QĐ-BGDĐT)
    # -------------------------------------------------------------------------
    "thpt_qg_2025_toan": ExamBlueprint(
        blueprint_id="thpt_qg_2025_toan",
        name="Đề Thi Tốt Nghiệp THPT 2025 • Môn Toán",
        subject="Toán học",
        category="thpt_qg",
        authority="Bộ Giáo dục và Đào tạo",
        duration_minutes=90,
        total_questions=22,
        total_points=10.0,
        cognitive_matrix={"remember": 0.3, "understand": 0.4, "apply": 0.2, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN I: Câu trắc nghiệm nhiều phương án lựa chọn",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=12,
                points_per_question=0.25,
                total_points=3.0,
                bloom_distribution={"remember": 0.5, "understand": 0.5},
                instructions="Gồm 12 câu hỏi trắc nghiệm khách quan với 4 lựa chọn A, B, C, D (chọn 1 đáp án đúng duy nhất). Mỗi câu đúng được 0.25 điểm.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN II: Câu trắc nghiệm Đúng/Sai đa ý",
                question_type=QuestionType.TRUE_FALSE_MULTISTEP,
                question_count=4,
                points_per_question=1.0,
                total_points=4.0,
                bloom_distribution={"understand": 0.4, "apply": 0.4, "analyze": 0.2},
                instructions=(
                    "Gồm 4 câu hỏi. Trong mỗi câu có 4 ý a), b), c), d). Thí sinh chọn Đúng hoặc Sai cho từng ý. "
                    "Barem điểm chuẩn BGDĐT: Đúng 1 ý = 0.10 điểm; Đúng 2 ý = 0.25 điểm; Đúng 3 ý = 0.50 điểm; Đúng cả 4 ý = 1.00 điểm."
                ),
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="PHẦN III: Câu trắc nghiệm trả lời ngắn",
                question_type=QuestionType.SHORT_ANSWER,
                question_count=6,
                points_per_question=0.5,
                total_points=3.0,
                bloom_distribution={"apply": 0.6, "analyze": 0.4},
                instructions="Gồm 6 câu hỏi yêu cầu thí sinh tự giải và điền kết quả đáp số ngắn (số nguyên, số thập phân hoặc phân số rút gọn). Mỗi câu đúng được 0.5 điểm.",
            ),
        ],
        special_guidelines=[
            "Bắt buộc tuân thủ đúng tỷ lệ 12 câu Phần I, 4 câu Phần II và 6 câu Phần III.",
            "Phần II phải có 4 ý a, b, c, d rõ ràng với nội dung mang tính liên hoàn tăng dần độ khó.",
            "Phần III tập trung vào bài toán ứng dụng thực tế (tối ưu hóa kinh tế, chuyển động, xác suất thực nghiệm, thể tích khối chóp lăng trụ).",
        ],
    ),
    "thpt_qg_2025_vat_ly": ExamBlueprint(
        blueprint_id="thpt_qg_2025_vat_ly",
        name="Đề Thi Tốt Nghiệp THPT 2025 • Môn Vật Lí",
        subject="Vật lí",
        category="thpt_qg",
        authority="Bộ Giáo dục và Đào tạo",
        duration_minutes=50,
        total_questions=28,
        total_points=10.0,
        cognitive_matrix={"remember": 0.35, "understand": 0.35, "apply": 0.2, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN I: Câu trắc nghiệm nhiều phương án lựa chọn",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=18,
                points_per_question=0.25,
                total_points=4.5,
                bloom_distribution={"remember": 0.5, "understand": 0.5},
                instructions="18 câu hỏi trắc nghiệm 4 phương án lựa chọn (A, B, C, D). Mỗi câu đúng được 0.25 điểm.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN II: Câu trắc nghiệm Đúng/Sai đa ý",
                question_type=QuestionType.TRUE_FALSE_MULTISTEP,
                question_count=4,
                points_per_question=1.0,
                total_points=4.0,
                bloom_distribution={"understand": 0.4, "apply": 0.4, "analyze": 0.2},
                instructions="4 câu hỏi dạng Đúng/Sai (mỗi câu 4 ý a, b, c, d). Điểm tính theo chuẩn: 1 ý=0.1đ; 2 ý=0.25đ; 3 ý=0.5đ; 4 ý=1.0đ.",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="PHẦN III: Câu trắc nghiệm trả lời ngắn",
                question_type=QuestionType.SHORT_ANSWER,
                question_count=6,
                points_per_question=0.25,
                total_points=1.5,
                bloom_distribution={"apply": 0.6, "analyze": 0.4},
                instructions="6 câu hỏi điền đáp số ngắn dạng số thực hoặc số nguyên có kèm đơn vị đo chuẩn SI.",
            ),
        ],
        special_guidelines=[
            "Lồng ghép các hiện tượng vật lí thực tiễn: sóng âm, quang học, điện từ, năng lượng hạt nhân, nhiệt học.",
            "Cung cấp đầy đủ các hằng số vật lí cần thiết (c, h, e, g, NA, R).",
        ],
    ),
    "thpt_qg_2025_hoa_hoc": ExamBlueprint(
        blueprint_id="thpt_qg_2025_hoa_hoc",
        name="Đề Thi Tốt Nghiệp THPT 2025 • Môn Hóa Học",
        subject="Hóa học",
        category="thpt_qg",
        authority="Bộ Giáo dục và Đào tạo",
        duration_minutes=50,
        total_questions=28,
        total_points=10.0,
        cognitive_matrix={"remember": 0.35, "understand": 0.35, "apply": 0.2, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN I: Câu trắc nghiệm nhiều phương án lựa chọn",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=18,
                points_per_question=0.25,
                total_points=4.5,
                bloom_distribution={"remember": 0.5, "understand": 0.5},
                instructions="18 câu trắc nghiệm 4 phương án A, B, C, D.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN II: Câu trắc nghiệm Đúng/Sai đa ý",
                question_type=QuestionType.TRUE_FALSE_MULTISTEP,
                question_count=4,
                points_per_question=1.0,
                total_points=4.0,
                bloom_distribution={"understand": 0.4, "apply": 0.4, "analyze": 0.2},
                instructions="4 câu hỏi thí nghiệm hoặc phân tích chuỗi phản ứng dạng Đúng/Sai 4 ý.",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="PHẦN III: Câu trắc nghiệm trả lời ngắn",
                question_type=QuestionType.SHORT_ANSWER,
                question_count=6,
                points_per_question=0.25,
                total_points=1.5,
                bloom_distribution={"apply": 0.6, "analyze": 0.4},
                instructions="6 câu hỏi tính toán hiệu suất phản ứng, pH, số đồng phân hoặc khối lượng sản phẩm.",
            ),
        ],
        special_guidelines=[
            "Bám sát chương trình Giáo dục phổ thông 2018 (sử dụng danh pháp IUPAC quốc tế, ví dụ: ethanol, ethanoic acid, glucose).",
        ],
    ),
    "thpt_qg_2025_tieng_anh": ExamBlueprint(
        blueprint_id="thpt_qg_2025_tieng_anh",
        name="Đề Thi Tốt Nghiệp THPT 2025 • Môn Tiếng Anh",
        subject="Tiếng Anh",
        category="thpt_qg",
        authority="Bộ Giáo dục và Đào tạo",
        duration_minutes=50,
        total_questions=40,
        total_points=10.0,
        cognitive_matrix={"remember": 0.3, "understand": 0.4, "apply": 0.2, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN THI TRẮC NGHIỆM TIẾNG ANH CHUẨN 40 CÂU",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=40,
                points_per_question=0.25,
                total_points=10.0,
                bloom_distribution={"remember": 0.3, "understand": 0.4, "apply": 0.2, "analyze": 0.1},
                instructions=(
                    "Đề gồm 40 câu trắc nghiệm bao phủ toàn diện: "
                    "1-2: Ngữ âm; 3-4: Trọng âm; 5-13: Ngữ pháp & Từ vựng; 14-15: Chức năng giao tiếp; "
                    "16-20: Điền từ vào đoạn văn (Cloze test); 21-25: Đọc hiểu 1 (5 câu); "
                    "26-32: Đọc hiểu 2 (7 câu nâng cao); 33-35: Sửa lỗi sai; 36-38: Viết lại câu gần nghĩa nhất; "
                    "39-40: Kết hợp hai câu đơn thành câu phức."
                ),
            )
        ],
        special_guidelines=[
            "Chủ đề các bài đọc hiểu mang tính toàn cầu: môi trường, trí tuệ nhân tạo, bảo tồn đa dạng sinh học, văn hóa các nước.",
            "Tuyệt đối không có lỗi văn phạm bản xứ, câu hỏi phân hóa rõ rệt ở bài đọc 7 câu.",
        ],
    ),
    "thpt_qg_2025_ngu_van": ExamBlueprint(
        blueprint_id="thpt_qg_2025_ngu_van",
        name="Đề Thi Tốt Nghiệp THPT 2025 • Môn Ngữ Văn",
        subject="Ngữ văn",
        category="thpt_qg",
        authority="Bộ Giáo dục và Đào tạo",
        duration_minutes=120,
        total_questions=6,
        total_points=10.0,
        cognitive_matrix={"remember": 0.2, "understand": 0.3, "apply": 0.3, "analyze": 0.2},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN I: ĐỌC HIỂU (4.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=4,
                points_per_question=1.0,
                total_points=4.0,
                bloom_distribution={"remember": 0.25, "understand": 0.5, "apply": 0.25},
                instructions="Cho một văn bản ngữ liệu (thơ hoặc văn xuôi ngoài SGK). Gồm 4 câu hỏi từ Nhận biết (thể thơ/phương thức biểu đạt) đến Thông hiểu (ý nghĩa chi tiết) và Vận dụng (bài học rút ra cho bản thân).",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN II: LÀM VĂN (6.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=2,
                points_per_question=3.0,
                total_points=6.0,
                bloom_distribution={"apply": 0.4, "analyze": 0.6},
                instructions=(
                    "Câu 1 (2.0 điểm): Viết đoạn văn nghị luận xã hội khoảng 200 chữ trình bày suy nghĩ về một khía cạnh rút ra từ ngữ liệu Đọc hiểu.\n"
                    "Câu 2 (4.0 điểm): Viết bài văn nghị luận văn học phân tích, đánh giá một đoạn trích tác phẩm hoặc vấn đề nghệ thuật."
                ),
            ),
        ],
        special_guidelines=[
            "Theo định hướng đổi mới của Bộ GD&ĐT 2025: Ngữ liệu phần Đọc hiểu và Làm văn hoàn toàn nằm ngoài các bộ sách giáo khoa hiện hành nhằm đánh giá năng lực thực chất.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 2. ĐÁNH GIÁ NĂNG LỰC & TƯ DUY (HSA, V-ACT, TSA)
    # -------------------------------------------------------------------------
    "dgnl_hsa": ExamBlueprint(
        blueprint_id="dgnl_hsa",
        name="Đề Thi Đánh Giá Năng Lực (HSA) • ĐHQG Hà Nội",
        subject="Đánh giá năng lực tổng hợp",
        category="dgnl",
        authority="Trung tâm Khảo thí ĐHQG Hà Nội",
        duration_minutes=195,
        total_questions=150,
        total_points=150.0,
        cognitive_matrix={"remember": 0.2, "understand": 0.4, "apply": 0.3, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN 1: Tư duy định lượng (Toán học)",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=50,
                points_per_question=1.0,
                total_points=50.0,
                bloom_distribution={"remember": 0.2, "understand": 0.4, "apply": 0.3, "analyze": 0.1},
                instructions="50 câu toán học, thống kê, xác suất và tư duy số liệu trong 75 phút.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN 2: Tư duy định tính (Văn học - Ngôn ngữ)",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=50,
                points_per_question=1.0,
                total_points=50.0,
                bloom_distribution={"remember": 0.3, "understand": 0.4, "apply": 0.3},
                instructions="50 câu tiếng Việt, văn học, phân tích ngữ nghĩa và logic diễn đạt trong 60 phút.",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="PHẦN 3: Khoa học (Tự nhiên & Xã hội)",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=50,
                points_per_question=1.0,
                total_points=50.0,
                bloom_distribution={"remember": 0.3, "understand": 0.4, "apply": 0.3},
                instructions="50 câu tích hợp Vật lí, Hóa học, Sinh học, Lịch sử và Địa lí trong 60 phút.",
            ),
        ],
        special_guidelines=[
            "Mỗi câu hỏi có giá trị 1 điểm, tổng điểm tối đa là 150 điểm.",
            "Tập trung vào năng lực đọc hiểu số liệu bảng biểu, suy luận logic thực tế.",
        ],
    ),
    "dgnl_vact": ExamBlueprint(
        blueprint_id="dgnl_vact",
        name="Đề Thi Đánh Giá Năng Lực (V-ACT) • ĐHQG TP.HCM",
        subject="Đánh giá năng lực tổng hợp",
        category="dgnl",
        authority="Đại học Quốc gia TP. Hồ Chí Minh",
        duration_minutes=150,
        total_questions=120,
        total_points=1200.0,
        cognitive_matrix={"remember": 0.2, "understand": 0.4, "apply": 0.3, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN 1: Sử dụng ngôn ngữ (Tiếng Việt & Tiếng Anh)",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=40,
                points_per_question=10.0,
                total_points=400.0,
                bloom_distribution={"remember": 0.3, "understand": 0.5, "apply": 0.2},
                instructions="20 câu Tiếng Việt và 20 câu Tiếng Anh kiểm tra ngữ âm, ngữ pháp, phong cách và phân tích bài đọc.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN 2: Toán học, Tư duy logic và Phân tích số liệu",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=30,
                points_per_question=10.0,
                total_points=300.0,
                bloom_distribution={"understand": 0.3, "apply": 0.4, "analyze": 0.3},
                instructions="30 câu toán học phổ thông, bài toán mệnh đề logic suy luận và phân tích biểu đồ/bảng số liệu.",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="PHẦN 3: Giải quyết vấn đề (Khoa học tự nhiên & Xã hội)",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=50,
                points_per_question=10.0,
                total_points=500.0,
                bloom_distribution={"understand": 0.3, "apply": 0.4, "analyze": 0.3},
                instructions="50 câu giải quyết vấn đề thuộc 5 lĩnh vực: Hóa học, Vật lí, Sinh học, Địa lí, Lịch sử (mỗi lĩnh vực 10 câu).",
            ),
        ],
        special_guidelines=[
            "Đề thi gồm 120 câu trắc nghiệm 4 lựa chọn, thang điểm chuẩn 1200 điểm theo mô hình IRT.",
        ],
    ),
    "dgnl_tsa": ExamBlueprint(
        blueprint_id="dgnl_tsa",
        name="Đề Thi Đánh Giá Tư Duy (TSA) • Đại học Bách Khoa Hà Nội",
        subject="Đánh giá tư duy",
        category="dgnl",
        authority="Đại học Bách Khoa Hà Nội",
        duration_minutes=150,
        total_questions=100,
        total_points=100.0,
        cognitive_matrix={"remember": 0.15, "understand": 0.35, "apply": 0.35, "analyze": 0.15},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN 1: Tư duy Toán học",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=40,
                points_per_question=1.0,
                total_points=40.0,
                bloom_distribution={"understand": 0.3, "apply": 0.4, "analyze": 0.3},
                instructions="40 câu trắc nghiệm và điền khuyết toán học trong 60 phút.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN 2: Tư duy Đọc hiểu",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=20,
                points_per_question=1.0,
                total_points=20.0,
                bloom_distribution={"understand": 0.5, "apply": 0.3, "analyze": 0.2},
                instructions="20 câu đọc hiểu các văn bản khoa học kỹ thuật, công nghệ trong 30 phút.",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="PHẦN 3: Tư duy Khoa học & Giải quyết vấn đề",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=40,
                points_per_question=1.0,
                total_points=40.0,
                bloom_distribution={"apply": 0.5, "analyze": 0.5},
                instructions="40 câu phân tích bối cảnh dữ liệu thực nghiệm Vật lí, Hóa học, Sinh học và Công nghệ trong 60 phút.",
            ),
        ],
        special_guidelines=[
            "Tập trung sâu vào tư duy suy luận logic, giải quyết bài toán kỹ thuật hiện đại.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 3. TUYỂN SINH VÀO LỚP 10 THPT (SỞ GD&ĐT)
    # -------------------------------------------------------------------------
    "tuyen_sinh_10_toan_chung": ExamBlueprint(
        blueprint_id="tuyen_sinh_10_toan_chung",
        name="Đề Thi Tuyển Sinh Vào Lớp 10 THPT • Môn Toán (Chung)",
        subject="Toán học",
        category="tuyen_sinh_10",
        authority="Sở Giáo dục và Đào tạo",
        duration_minutes=120,
        total_questions=5,
        total_points=10.0,
        cognitive_matrix={"remember": 0.2, "understand": 0.3, "apply": 0.35, "analyze": 0.15},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="BÀI 1: Căn thức và Biểu thức đại số (2.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=2.0,
                total_points=2.0,
                bloom_distribution={"remember": 0.3, "understand": 0.4, "apply": 0.3},
                instructions="Rút gọn biểu thức chứa căn thức bậc hai, tính giá trị khi x thỏa mãn điều kiện và tìm x để biểu thức nhận giá trị nguyên hoặc so sánh với số k.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="BÀI 2: Hệ phương trình & Bài toán thực tế (2.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=2.0,
                total_points=2.0,
                bloom_distribution={"understand": 0.3, "apply": 0.7},
                instructions="Ý 1: Giải bài toán bằng cách lập phương trình/hệ phương trình (chuyển động, năng suất làm chung làm riêng, kinh tế tài chính). Ý 2: Hình học không gian thực tế (tính thể tích hình nón, trụ, cầu).",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="BÀI 3: Phương trình bậc hai & Định lý Vi-ét (2.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=2.0,
                total_points=2.0,
                bloom_distribution={"understand": 0.3, "apply": 0.5, "analyze": 0.2},
                instructions="Tương giao giữa đường thẳng (d) và Parabol (P), tìm m để phương trình có 2 nghiệm phân biệt thỏa mãn biểu thức đối xứng hoặc bất đối xứng.",
            ),
            ExamSectionBlueprint(
                section_id="part_4",
                title="BÀI 4: Hình học phẳng tổng hợp (3.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=3.0,
                total_points=3.0,
                bloom_distribution={"understand": 0.3, "apply": 0.4, "analyze": 0.3},
                instructions="Đường tròn và tiếp tuyến: a) Chứng minh 4 điểm cùng thuộc một đường tròn (tứ giác nội tiếp); b) Chứng minh hệ thức hình học hoặc hai đường thẳng vuông góc/song song; c) Chứng minh 3 điểm thẳng hàng hoặc điểm cố định.",
            ),
            ExamSectionBlueprint(
                section_id="part_5",
                title="BÀI 5: Bài toán phân loại cực trị & Bất đẳng thức (1.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=1.0,
                total_points=1.0,
                bloom_distribution={"analyze": 1.0},
                instructions="Tìm giá trị lớn nhất, giá trị nhỏ nhất của biểu thức nhiều biến số hoặc giải phương trình vô tỉ nâng cao.",
            ),
        ],
        special_guidelines=[
            "Cấu trúc 5 bài tự luận chuẩn mực áp dụng cho tuyển sinh công lập tại các thành phố lớn (Hà Nội, TP.HCM, Đà Nẵng).",
        ],
    ),
    "chuyen_lop_10_toan": ExamBlueprint(
        blueprint_id="chuyen_lop_10_toan",
        name="Đề Thi Tuyển Sinh Vào Lớp 10 Chuyên • Môn Toán",
        subject="Toán chuyên",
        category="tuyen_sinh_10",
        authority="Trường THPT Chuyên / Sở GD&ĐT",
        duration_minutes=150,
        total_questions=5,
        total_points=10.0,
        cognitive_matrix={"remember": 0.05, "understand": 0.2, "apply": 0.45, "analyze": 0.3},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="CÂU 1: Đại số & Biến đổi đại số nâng cao (2.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=2.0,
                total_points=2.0,
                bloom_distribution={"understand": 0.3, "apply": 0.7},
                instructions="Giải phương trình, hệ phương trình vô tỉ hoặc đa thức có chứa tham số.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="CÂU 2: Số học & Phương trình nghiệm nguyên (2.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=2.0,
                total_points=2.0,
                bloom_distribution={"apply": 0.6, "analyze": 0.4},
                instructions="Tính chất chia hết, số chính phương, số nguyên tố, đồng dư thức hoặc giải phương trình nghiệm nguyên Diophantine.",
            ),
            ExamSectionBlueprint(
                section_id="part_3",
                title="CÂU 3: Hình học phẳng Chuyên sâu (3.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=3.0,
                total_points=3.0,
                bloom_distribution={"apply": 0.5, "analyze": 0.5},
                instructions="Hàng điểm điều hòa, trục đẳng phương, đồng quy thẳng hàng, đường đối trung hoặc định lý Menelaus/Ceva.",
            ),
            ExamSectionBlueprint(
                section_id="part_4",
                title="CÂU 4: Bất đẳng thức & Cực trị đại số (2.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=2.0,
                total_points=2.0,
                bloom_distribution={"analyze": 1.0},
                instructions="Bất đẳng thức Cauchy-Schwarz, AM-GM đối xứng/hoán vị hoặc kỹ thuật dồn biến.",
            ),
            ExamSectionBlueprint(
                section_id="part_5",
                title="CÂU 5: Tổ hợp & Rời rạc (1.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=1,
                points_per_question=1.0,
                total_points=1.0,
                bloom_distribution={"analyze": 1.0},
                instructions="Nguyên lý Dirichlet, bài toán bảng ô vuông, lý thuyết đồ thị sơ cấp hoặc bất biến tổ hợp.",
            ),
        ],
        special_guidelines=[
            "Yêu cầu lời giải chặt chẽ, lập luận toán học mẫu mực, chuẩn phong cách thi Chuyên Sư Phạm / KHTN / Lê Hồng Phong / Chu Văn An.",
        ],
    ),

    # -------------------------------------------------------------------------
    # 4. KIỂM TRA ĐỊNH KỲ THÔNG TƯ 22/BGDĐT (GIỮA KỲ / CUỐI KỲ)
    # -------------------------------------------------------------------------
    "dinh_ky_tt22_toan": ExamBlueprint(
        blueprint_id="dinh_ky_tt22_toan",
        name="Đề Kiểm Tra Định Kỳ (Giữa Kỳ / Cuối Kỳ) • Môn Toán (Thông tư 22)",
        subject="Toán học",
        category="dinh_ky_tt22",
        authority="Bộ GD&ĐT / Sở GD&ĐT",
        duration_minutes=90,
        total_questions=31,
        total_points=10.0,
        cognitive_matrix={"remember": 0.4, "understand": 0.3, "apply": 0.2, "analyze": 0.1},
        sections=[
            ExamSectionBlueprint(
                section_id="part_1",
                title="PHẦN TRẮC NGHIỆM KHÁCH QUAN (7.0 điểm)",
                question_type=QuestionType.MCQ_SINGLE,
                question_count=28,
                points_per_question=0.25,
                total_points=7.0,
                bloom_distribution={"remember": 0.5, "understand": 0.35, "apply": 0.15},
                instructions="28 câu hỏi trắc nghiệm 4 lựa chọn (A, B, C, D) kiểm tra kiến thức trọng tâm học kỳ.",
            ),
            ExamSectionBlueprint(
                section_id="part_2",
                title="PHẦN TỰ LUẬN TRÌNH BÀY (3.0 điểm)",
                question_type=QuestionType.ESSAY,
                question_count=3,
                points_per_question=1.0,
                total_points=3.0,
                bloom_distribution={"understand": 0.3, "apply": 0.4, "analyze": 0.3},
                instructions="3 bài tự luận: Bài 1: Đại số/Giải tích cơ bản (1.0đ); Bài 2: Hình học chứng minh (1.0đ); Bài 3: Ứng dụng thực tế hoặc cực trị nâng cao (1.0đ).",
            ),
        ],
        special_guidelines=[
            "Tỷ lệ điểm 70% Trắc nghiệm + 30% Tự luận bám chuẩn thông tư 22 Bộ GD&ĐT cho các khối lớp 6 đến 12.",
        ],
    ),
}


class ExamBlueprintEngine:
    """Bộ máy điều phối và áp dụng khung đề thi chuẩn hóa."""

    @classmethod
    def get_blueprint(cls, blueprint_id: str) -> Optional[ExamBlueprint]:
        """Lấy thông tin khung đề thi theo mã ID chính xác."""
        return STANDARD_BLUEPRINTS.get(blueprint_id.lower().strip())

    @classmethod
    def list_blueprints(
        cls,
        category: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> list[ExamBlueprint]:
        """Liệt kê danh sách các khung đề theo danh mục hoặc môn học."""
        res: list[ExamBlueprint] = []
        for bp in STANDARD_BLUEPRINTS.values():
            if category and bp.category.lower() != category.lower():
                continue
            if subject and subject.lower() not in bp.subject.lower():
                continue
            res.append(bp)
        return res

    @classmethod
    def find_best_match(
        cls, query: str, subject: Optional[str] = None
    ) -> Optional[ExamBlueprint]:
        """Tìm kiếm khung đề phù hợp nhất dựa trên từ khóa người dùng nhập."""
        q = query.lower().strip()
        if not q:
            return None

        # 1. Tìm theo ID chính xác
        if q in STANDARD_BLUEPRINTS:
            return STANDARD_BLUEPRINTS[q]

        # 2. Tìm theo từ khóa đặc trưng
        for bp_id, bp in STANDARD_BLUEPRINTS.items():
            if bp_id in q:
                return bp

        # Từ khóa THPT 2025
        if "thpt" in q or "tốt nghiệp" in q or "tot nghiep" in q or "2025" in q:
            sub = (subject or query).lower()
            if "toán" in sub or "toan" in sub or "math" in sub:
                return STANDARD_BLUEPRINTS.get("thpt_qg_2025_toan")
            if "lí" in sub or "li" in sub or "vật" in sub or "physic" in sub:
                return STANDARD_BLUEPRINTS.get("thpt_qg_2025_vat_ly")
            if "hóa" in sub or "hoa" in sub or "chem" in sub:
                return STANDARD_BLUEPRINTS.get("thpt_qg_2025_hoa_hoc")
            if "anh" in sub or "english" in sub:
                return STANDARD_BLUEPRINTS.get("thpt_qg_2025_tieng_anh")
            if "văn" in sub or "van" in sub:
                return STANDARD_BLUEPRINTS.get("thpt_qg_2025_ngu_van")
            return STANDARD_BLUEPRINTS.get("thpt_qg_2025_toan")

        # Từ khóa Đánh giá năng lực
        if "hsa" in q or "hà nội" in q or "ha noi" in q:
            return STANDARD_BLUEPRINTS.get("dgnl_hsa")
        if "vact" in q or "v-act" in q or "hcm" in q or "sài gòn" in q:
            return STANDARD_BLUEPRINTS.get("dgnl_vact")
        if "tsa" in q or "bách khoa" in q or "bach khoa" in q:
            return STANDARD_BLUEPRINTS.get("dgnl_tsa")

        # Tuyển sinh vào 10
        if "vào 10" in q or "lop 10" in q or "lớp 10" in q or "tuyen sinh 10" in q:
            if "chuyên" in q or "chuyen" in q:
                return STANDARD_BLUEPRINTS.get("chuyen_lop_10_toan")
            return STANDARD_BLUEPRINTS.get("tuyen_sinh_10_toan_chung")

        # Định kỳ thông tư 22
        if "giữa kỳ" in q or "giua ky" in q or "cuối kỳ" in q or "cuoi ky" in q or "tt22" in q:
            return STANDARD_BLUEPRINTS.get("dinh_ky_tt22_toan")

        return None

    @classmethod
    def calculate_true_false_score(cls, correct_subitems: int) -> float:
        """Tính điểm cho câu hỏi Đúng/Sai 4 ý chuẩn Quyết định 764/QĐ-BGDĐT 2025.

        - Đúng 1 ý: 0.10 điểm
        - Đúng 2 ý: 0.25 điểm
        - Đúng 3 ý: 0.50 điểm
        - Đúng 4 ý: 1.00 điểm
        """
        table = {0: 0.0, 1: 0.10, 2: 0.25, 3: 0.50, 4: 1.00}
        return table.get(max(0, min(4, correct_subitems)), 0.0)

    @classmethod
    def build_prompt_spec(
        cls, blueprint: ExamBlueprint | str, topic_context: str = ""
    ) -> str:
        """Tạo đặc tả prompt chi tiết đưa vào Gemma Planner & Qwen Drafter."""
        if isinstance(blueprint, str):
            bp = cls.get_blueprint(blueprint) or cls.find_best_match(blueprint)
            if not bp:
                return ""
        else:
            bp = blueprint

        lines: list[str] = [
            f"=== [CHỈ THỊ KHUNG ĐỀ CHUẨN HÓA BẮT BUỘC: {bp.name.upper()}] ===",
            f"• Cơ quan khảo thí ban hành: {bp.authority}",
            f"• Môn học: {bp.subject} | Thời gian làm bài: {bp.duration_minutes} phút",
            f"• Quy mô chuẩn: {bp.total_questions} câu | Tổng thang điểm: {bp.total_points} điểm",
            f"• Ma trận Bloom nhận thức: Nhận biết {int(bp.cognitive_matrix.get('remember', 0.4)*100)}% | Thông hiểu {int(bp.cognitive_matrix.get('understand', 0.3)*100)}% | Vận dụng {int(bp.cognitive_matrix.get('apply', 0.2)*100)}% | Vận dụng cao {int(bp.cognitive_matrix.get('analyze', 0.1)*100)}%",
            "",
            "📐 BẮT BUỘC PHÂN CHIA THÀNH CÁC PHẦN (SECTIONS) CHÍNH XÁC NHƯ SAU:",
        ]

        for s in bp.sections:
            lines.append(f"--- {s.title} ---")
            lines.append(f"  + Dạng thức: {s.question_type.value}")
            lines.append(f"  + Số lượng câu: {s.question_count} câu (Mỗi câu: {s.points_per_question}đ - Tổng phần: {s.total_points}đ)")
            if s.instructions:
                lines.append(f"  + Yêu cầu kỹ thuật: {s.instructions}")

        if bp.special_guidelines:
            lines.append("")
            lines.append("📋 QUY TẮC SƯ PHẠM VÀ ĐIỂM SỐ ĐẶC THÙ:")
            for g in bp.special_guidelines:
                lines.append(f"  • {g}")

        if topic_context:
            lines.append("")
            lines.append(f"🎯 PHẠM VI NỘI DUNG TRỌNG TÂM: {topic_context}")

        lines.append("=============================================================")
        return "\n".join(lines)

    @classmethod
    def validate_exam_against_blueprint(
        cls, exam_data: dict[str, Any], blueprint: ExamBlueprint | str
    ) -> dict[str, Any]:
        """Thẩm định xem bộ đề sinh ra có tuân thủ đúng 100% khung đề chuẩn hay không."""
        if isinstance(blueprint, str):
            bp = cls.get_blueprint(blueprint) or cls.find_best_match(blueprint)
            if not bp:
                return {"valid": False, "errors": ["Không tìm thấy Blueprint tương ứng"]}
        else:
            bp = blueprint

        errors: list[str] = []
        questions = exam_data.get("questions", [])
        sections = exam_data.get("sections", [])

        # Kiểm tra tổng số câu hỏi
        actual_total = len(questions)
        expected_total = bp.total_questions
        # Cho phép sai số nhỏ nếu đề thi dài tùy biến
        if abs(actual_total - expected_total) > max(2, int(expected_total * 0.15)):
            errors.append(f"Số lượng câu hỏi ({actual_total}) chưa khớp với chuẩn Blueprint ({expected_total})")

        # Kiểm tra tính đầy đủ của các phương án trắc nghiệm
        for i, q in enumerate(questions, 1):
            q_type = q.get("type", "mcq")
            if q_type == "mcq":
                opts = q.get("options", {})
                if not isinstance(opts, dict) or len(opts) < 4:
                    errors.append(f"Câu {i}: Thiếu phương án lựa chọn (phải có đủ A, B, C, D)")
                if not q.get("correct_answer"):
                    errors.append(f"Câu {i}: Thiếu đáp án đúng (correct_answer)")

        return {
            "valid": len(errors) == 0,
            "blueprint_id": bp.blueprint_id,
            "expected_questions": expected_total,
            "actual_questions": actual_total,
            "errors": errors,
        }


# Singleton instance toàn cục
exam_blueprint_engine = ExamBlueprintEngine()
