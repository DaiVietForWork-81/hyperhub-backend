"""
Bộ kiểm thử toàn diện 15 tình huống thực tế cho Hệ thống Multi-Agent Thẩm Định Đề Thi
(Reader 550B Thinking -> Deterministic Trap Auditor -> Independent Arbiter + Bản đồ GDPT 2018).
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from DocInspector.core import inspect_document
from DocInspector.models import ExamTrackTier, GradeLevel, Subject


def run_all_tests() -> None:
    cases = [
        # 1. Trường THPT Chuyên nhưng đề Thi thử Tốt nghiệp THPT -> THUONG, Lớp 12, Toán
        {
            "name": "Case 01: Trường THPT Chuyên ra đề Thi thử TN THPT",
            "file_name": "de_thi_thu_chuyen_phan_boi_chau.txt",
            "content": """
            SỞ GD&ĐT NGHỆ AN - TRƯỜNG THPT CHUYÊN PHAN BỘI CHÂU
            ĐỀ THI THỬ TỐT NGHIỆP THPT NĂM HỌC 2025 - 2026
            MÔN: TOÁN
            PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn.
            Câu 1: Cho hàm số y = x^3 - 3x + 2. Tìm cực trị của hàm số.
            A. 1  B. 2  C. 3  D. 4
            PHẦN II. Câu trắc nghiệm đúng sai.
            Câu 1: Trong không gian Oxyz, cho mặt cầu (S).
            """,
            "expect_subject": Subject.MATHEMATICS,
            "expect_grade": GradeLevel.GRADE_12,
            "expect_track": ExamTrackTier.THUONG,
        },
        # 2. Đề Học kỳ 1 môn KHTN Lớp 8 (tích hợp Lí - Hóa - Sinh) -> NATURAL_SCIENCE, Lớp 8
        {
            "name": "Case 02: Đề Học kỳ 1 môn Khoa học tự nhiên Lớp 8",
            "file_name": "de_hk1_khtn_8.txt",
            "content": """
            PHÒNG GD&ĐT QUẬN CẦU GIẤY
            ĐỀ KIỂM TRA HỌC KỲ 1 NĂM HỌC 2025 - 2026
            MÔN: KHOA HỌC TỰ NHIÊN - LỚP 8
            Câu 1: Khối lượng riêng của một chất được xác định bằng công thức nào?
            A. D = m/V   B. P = F/S   C. v = s/t   D. n = m/M
            Câu 2: Áp suất chất lỏng phụ thuộc vào yếu tố nào?
            A. Độ sâu   B. Diện tích   C. Khối lượng   D. Thể tích
            """,
            "expect_subject": Subject.NATURAL_SCIENCE,
            "expect_grade": GradeLevel.GRADE_8,
            "expect_track": ExamTrackTier.THUONG,
        },
        # 3. Kỳ thi tuyển sinh vào lớp 10 THPT (dành cho học sinh Lớp 9) -> GRADE_9, THUONG
        {
            "name": "Case 03: Tuyển sinh vào lớp 10 THPT công lập",
            "file_name": "de_tuyen_sinh_vao_lop_10_toan_ha_noi.txt",
            "content": """
            SỞ GIÁO DỤC VÀ ĐÀO TẠO HÀ NỘI
            KỲ THI TUYỂN SINH VÀO LỚP 10 THPT NĂM HỌC 2025 - 2026
            MÔN THI: TOÁN
            Bài 1: Cho biểu thức chứa căn bậc hai.
            Bài 2: Giải hệ phương trình và định lý Vi-ét.
            Bài 3: Cho đường tròn (O; R) và tứ giác nội tiếp ABCD.
            """,
            "expect_subject": Subject.MATHEMATICS,
            "expect_grade": GradeLevel.GRADE_9,
            "expect_track": ExamTrackTier.THUONG,
        },
        # 4. Tuyển sinh vào lớp 10 Chuyên -> GRADE_9, CHUYEN
        {
            "name": "Case 04: Tuyển sinh vào lớp 10 Chuyên Anh Hà Nội Amsterdam",
            "file_name": "Chuyen-anh-Ha-Noi-Amsterdam-2024-2025.txt",
            "content": """
            SỞ GIÁO DỤC VÀ ĐÀO TẠO HÀ NỘI
            KỲ THI TUYỂN SINH VÀO LỚP 10 THPT CHUYÊN NĂM HỌC 2024 - 2025
            MÔN THI: TIẾNG ANH (CHUYÊN)
            PART I. PHONETICS AND LEXICO-GRAMMAR
            Question 1: Choose the best option A, B, C or D.
            Question 2: Supply the correct form of the word in brackets.
            """,
            "expect_subject": Subject.ENGLISH,
            "expect_grade": GradeLevel.GRADE_9,
            "expect_track": ExamTrackTier.CHUYEN,
        },
        # 5. Đề Vật lí 12 có nhiều ký hiệu toán học (hàm số, đồ thị, tích phân) -> PHYSICS, GRADE_12
        {
            "name": "Case 05: Đề Vật lí 12 có nhiều từ vựng Toán học",
            "file_name": "de_kiem_tra_12.txt",
            "content": """
            SỞ GD&ĐT NAM ĐỊNH
            ĐỀ KIỂM TRA GIỮA HỌC KỲ 1 LỚP 12
            MÔN: VẬT LÍ
            Câu 1: Một vật dao động điều hòa theo phương trình x = 5cos(2pi*t) cm. Tìm giá trị lớn nhất của vận tốc và cực trị của hàm số vận tốc.
            A. 10pi cm/s   B. 5pi cm/s   C. 20 cm/s   D. 15 cm/s
            Câu 2: Cho đồ thị hàm số biểu diễn áp suất và thể tích của một lượng khí lí tưởng.
            A. 20 atm   B. 10 atm   C. 15 atm   D. 25 atm
            """,
            "expect_subject": Subject.PHYSICS,
            "expect_grade": GradeLevel.GRADE_12,
        },
        # 6. Đề Hóa học mất hoàn toàn tiêu đề Môn & Lớp -> Suy luận từ Ester, Carbohydrate, Pin Galvani -> CHEMISTRY, GRADE_12
        {
            "name": "Case 06: Đề khuyết tiêu đề -> Suy luận Hóa học Lớp 12 từ Ester & Pin Galvani",
            "file_name": "tai_lieu_quet_trang_2.txt",
            "content": """
            ĐỀ ÔN TẬP ĐỊNH KỲ
            PHẦN I. Câu trắc nghiệm nhiều phương án lựa chọn.
            Câu 1: Thủy phân hoàn toàn ester X có công thức phân tử C4H8O2 trong dung dịch NaOH đun nóng, thu được muối sodium acetate.
            A. C2H5OH   B. CH3OH   C. C3H7OH   D. C2H4(OH)2
            Câu 2: Chất nào sau đây thuộc loại polysaccharide và bị thủy phân tạo thành glucose?
            A. Tinh bột   B. Fructose   C. Saccharose   D. Methyl formate
            PHẦN II. Câu trắc nghiệm đúng sai.
            Câu 1: Cho các phát biểu về pin điện hóa Galvani Zn-Cu:
            a) Điện cực kẽm là anode.
            b) Điện cực đồng là cathode.
            """,
            "expect_subject": Subject.CHEMISTRY,
            "expect_grade": GradeLevel.GRADE_12,
        },
        # 7. Đề Toán mất tiêu đề Lớp -> Suy luận Lớp 11 từ Cấp số cộng, Cấp số nhân, Giới hạn dãy số
        {
            "name": "Case 07: Đề khuyết tiêu đề Lớp -> Suy luận Toán Lớp 11 từ Cấp số cộng & Giới hạn",
            "file_name": "de_kiem_tra_toan_hoc.txt",
            "content": """
            ĐỀ KIỂM TRA ĐỊNH KỲ MÔN TOÁN
            Câu 1: Cho cấp số cộng (u_n) có số hạng đầu u_1 = 3 và công sai d = 4. Tính u_5.
            A. 19   B. 15   C. 23   D. 16
            Câu 2: Cho cấp số nhân (v_n) có v_1 = 2 và công bội q = 3.
            A. 54   B. 18   C. 162   D. 24
            Câu 3: Tính giới hạn của dãy số lim (2n + 1)/(n + 3) và xét tính liên tục của hàm số liên tục tại x = 1.
            A. 2   B. 1   C. 0   D. 3
            """,
            "expect_subject": Subject.MATHEMATICS,
            "expect_grade": GradeLevel.GRADE_11,
        },
        # 8. Đề Sinh học mất tiêu đề Lớp -> Suy luận Lớp 12 từ Phiên mã, Dịch mã, Operon Lac, Hardy-Weinberg
        {
            "name": "Case 08: Đề khuyết tiêu đề Lớp -> Suy luận Sinh học Lớp 12 từ Operon Lac & Hardy-Weinberg",
            "file_name": "bai_tap_di_truyen.txt",
            "content": """
            BÀI TẬP ÔN TẬP CHƯƠNG I & II
            Câu 1: Trong cơ chế điều hòa hoạt động của operon Lac ở vi khuẩn E. coli, quá trình phiên mã và dịch mã diễn ra như thế nào khi môi trường có lactose?
            A. Protein ức chế bị bất hoạt   B. Gene điều hòa ngừng tổng hợp   C. Vùng khởi động bị khóa   D. ARN polymerase không bám được
            Câu 2: Một quần thể ngẫu phối đạt trạng thái cân bằng di truyền Hardy-Weinberg có tần số allele A = 0,6 và a = 0,4.
            A. 0,36 AA : 0,48 Aa : 0,16 aa   B. 0,6 AA : 0,4 aa   C. 0,25 AA : 0,50 Aa : 0,25 aa   D. 0,16 AA : 0,48 Aa : 0,36 aa
            """,
            "expect_subject": Subject.BIOLOGY,
            "expect_grade": GradeLevel.GRADE_12,
        },
        # 9. Môn Giáo dục kinh tế và pháp luật Lớp 11 -> ECONOMIC_LEGAL_EDU, GRADE_11
        {
            "name": "Case 09: Đề Giáo dục kinh tế và pháp luật Lớp 11 (Cấp 3)",
            "file_name": "de_gdkt_pl_11.txt",
            "content": """
            TRƯỜNG THPT NGUYỄN THỊ MINH KHAI
            ĐỀ KIỂM TRA CUỐI HỌC KỲ 1 LỚP 11
            MÔN: GIÁO DỤC KINH TẾ VÀ PHÁP LUẬT
            Câu 1: Trong nền kinh tế thị trường, cạnh tranh lành mạnh giữa các doanh nghiệp mang lại tác động nào sau đây?
            A. Thúc đẩy đổi mới công nghệ   B. Đầu cơ tích trữ   C. Gian lận thương mại   D. Thải chất độc ra môi trường
            Câu 2: Lạm phát vừa phải có mức tăng giá cả ở mức bao nhiêu?
            A. Một con số dưới 10%   B. Hai con số   C. Ba con số   D. Trên 1000%
            """,
            "expect_subject": Subject.ECONOMIC_LEGAL_EDU,
            "expect_grade": GradeLevel.GRADE_11,
        },
        # 10. Tài liệu Toán học tên file "Kĩ-Thuật-Kế-Hợp-Vách-Ngăn-và-Bó.pdf" (bản scan ít chữ) -> MATHEMATICS
        {
            "name": "Case 10: Tài liệu chuyên đề Toán Tổ hợp (Vách ngăn và Bó)",
            "file_name": "Kĩ-Thuật-Kế-Hợp-Vách-Ngăn-và-Bó.pdf",
            "content": """
            Chuyên đề tổ hợp: Kĩ thuật kết hợp vách ngăn và bó (Stars and Bars) giải các bài toán đếm và chia kẹo Euler.
            Bài 1: Có bao nhiêu cách chia 10 chiếc kẹo giống nhau cho 4 học sinh?
            """,
            "expect_subject": Subject.MATHEMATICS,
        },
    ]

    for idx, tc in enumerate(cases, 1):
        report = inspect_document(tc["content"].encode("utf-8"), file_name=tc["file_name"])
        print(
            f"[{idx:02d}/{len(cases):02d}] {tc['name']} -> "
            f"Subject={report.detected_subject.name}, Grade={report.grade_level.name}, "
            f"Track={report.exam_track.name} ({report.detailed_exam_track})"
        )
        assert report.detected_subject == tc["expect_subject"], (
            f"{tc['name']}: Expected subject {tc['expect_subject']}, got {report.detected_subject}"
        )
        if "expect_grade" in tc:
            assert report.grade_level == tc["expect_grade"], (
                f"{tc['name']}: Expected grade {tc['expect_grade']}, got {report.grade_level}"
            )
        if "expect_track" in tc:
            assert report.exam_track == tc["expect_track"], (
                f"{tc['name']}: Expected track {tc['expect_track']}, got {report.exam_track}"
            )

    print("\nALL 10 COMPREHENSIVE MULTI-AGENT EXAMINER TESTS PASSED 100%!")


if __name__ == "__main__":
    run_all_tests()
