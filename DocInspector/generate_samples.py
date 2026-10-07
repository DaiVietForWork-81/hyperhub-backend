"""
Sample Generator for DocInspector.
Creates realistic test documents (PDF, DOCX) covering multiple languages,
specialized exams, administrative contracts, lesson plans, and intentional spoofing.
"""

from __future__ import annotations

import os
from pathlib import Path
import fitz
from docx import Document


def create_pdf_with_text(output_path: Path, lines: list[str], fontfile: str = "C:/Windows/Fonts/arial.ttf") -> None:
    """Helper to generate a clean PDF with proper Unicode text."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size
    font = fitz.Font(fontfile=fontfile)
    
    y = 50
    tw = fitz.TextWriter(page.rect)
    for line in lines:
        if y > 800:
            tw.write_text(page)
            page = doc.new_page(width=595, height=842)
            tw = fitz.TextWriter(page.rect)
            y = 50
        tw.append((45, y), line, font=font, fontsize=10.5)
        y += 18
    tw.write_text(page)
    doc.save(str(output_path))
    doc.close()


def generate_all_samples(samples_dir: Path) -> None:
    samples_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------------
    # 1. SPOOFED FILE 1: ielts_reading_cambridge_18.pdf
    # Filename claims: IELTS Reading
    # Real Content: Vietnamese 12th Grade Mathematics Exam (Chuyên Toán / THPT)
    # ------------------------------------------------------------------------
    math_lines = [
        "SỞ GIÁO DỤC VÀ ĐÀO TẠO - KỲ THI THỬ TỐT NGHIỆP THPT NĂM 2026",
        "MÔN: TOÁN HỌC - Thời gian làm bài: 90 phút (Không kể thời gian phát đề)",
        "Mã đề thi: 104",
        "--------------------------------------------------------------------------------",
        "Câu 1: Cho hàm số y = f(x) có bảng biến thiên như sau. Tìm điểm cực trị của hàm số.",
        "A. x = 1        B. x = 2        C. x = -1        D. x = 0",
        "Câu 2: Họ nguyên hàm của hàm số f(x) = 3x^2 + 2x là:",
        "A. x^3 + x^2 + C    B. 6x + 2 + C    C. x^3 - x^2 + C    D. 3x^3 + x^2 + C",
        "Câu 3: Tính tích phân I = int_0^1 (2x + 1) dx có kết quả là:",
        "A. 1            B. 2            C. 3            D. 4",
        "Câu 4: Cho hình chóp S.ABCD có đáy ABCD là hình vuông cạnh a, SA vuông góc với đáy.",
        "Tính thể tích khối chóp S.ABCD biết SA = 2a.",
        "A. 2a^3/3       B. 2a^3         C. a^3/3        D. 4a^3/3",
        "Câu 5: Số phức z = 3 - 4i có môđun bằng bao nhiêu?",
        "A. 5            B. 25           C. 7            D. 1",
        "Câu 6: Đường tiệm cận ngang của đồ thị hàm số y = (2x - 1)/(x + 1) là:",
        "A. y = 2        B. y = -1       C. x = -1       D. x = 2",
        "Câu 7: Tìm giá trị lớn nhất và giá trị nhỏ nhất của hàm số trên đoạn [1; 3].",
        "A. Max = 10, Min = 2            B. Max = 8, Min = 1",
        "C. Max = 12, Min = 0            D. Max = 15, Min = -2",
        "Câu 8: Bất đẳng thức Cauchy-Schwarz áp dụng cho ba số thực dương x, y, z:",
        "A. (x+y+z)(1/x+1/y+1/z) >= 9    B. x+y+z >= 3xyz",
        "C. x^2+y^2+z^2 < xy+yz+zx       D. x+y >= 2",
        "Câu 9: Trong không gian Oxyz, phương trình mặt phẳng đi qua điểm M(1;2;3) có vectơ pháp tuyến:",
        "A. 2x + y - z - 1 = 0           B. x + y + z - 6 = 0",
        "C. 2x - y + z - 3 = 0           D. x - 2y + z = 0",
        "Câu 10: Cho cấp số cộng (u_n) có u_1 = 3 và công sai d = 5. Số hạng thứ 10 là:",
        "A. 48           B. 45           C. 53           D. 50",
        "--------------------------------------------------------------------------------",
        "HƯỚNG DẪN GIẢI CHI TIẾT VÀ BẢNG ĐÁP ÁN:",
        "1-A  2-A  3-B  4-A  5-A  6-A  7-A  8-A  9-B  10-A",
        "Lời giải chi tiết câu 4: Áp dụng công thức thể tích khối chóp V = 1/3 * B * h.",
        "Diện tích đáy hình vuông B = a^2. Chiều cao h = SA = 2a => V = 2a^3/3.",
    ]
    create_pdf_with_text(samples_dir / "ielts_reading_cambridge_18.pdf", math_lines)

    # ------------------------------------------------------------------------
    # 2. SPOOFED FILE 2: de_toan_chuyen_hsg.docx
    # Filename claims: Toán Chuyên (Math)
    # Real Content: Chuyên Tin học / Competitive Programming (C++ & Pascal)
    # ------------------------------------------------------------------------
    doc_tin = Document()
    doc_tin.add_heading("KỲ THI CHỌN HỌC SINH GIỎI QUỐC GIA - CHUYÊN TIN HỌC", level=1)
    doc_tin.add_paragraph("BÀI 1: TỔNG ĐOẠN CON LỚN NHẤT (SUBARR)")
    doc_tin.add_paragraph("Thời gian chạy: 1.0 giây")
    doc_tin.add_paragraph("Giới hạn bộ nhớ: 256 MB")
    doc_tin.add_paragraph("File vào: SUBARR.INP | File ra: SUBARR.OUT")
    doc_tin.add_paragraph(
        "Cho mảng A gồm N số nguyên. Hãy tìm một dãy con liên tiếp có tổng các phần tử lớn nhất. "
        "Thuật toán yêu cầu tối ưu độ phức tạp thời gian O(N log N) hoặc O(N) bằng quy hoạch động."
    )
    doc_tin.add_paragraph("Dữ liệu vào (SUBARR.INP):")
    doc_tin.add_paragraph("Dòng 1 chứa số nguyên N. Dòng 2 chứa N số nguyên A_1, A_2, ..., A_N.")
    doc_tin.add_paragraph("Dữ liệu ra (SUBARR.OUT):")
    doc_tin.add_paragraph("Ghi ra một số nguyên duy nhất là tổng lớn nhất tìm được.")
    doc_tin.add_paragraph("Ràng buộc dữ liệu & Subtasks:")
    doc_tin.add_paragraph("Subtask 1 (30% số điểm): N <= 1000.")
    doc_tin.add_paragraph("Subtask 2 (40% số điểm): N <= 10^5, thuật toán Segment Tree hoặc Chặt nhị phân.")
    doc_tin.add_paragraph("Subtask 3 (30% số điểm): N <= 10^6, thuật toán Kadane quy hoạch động.")
    doc_tin.add_paragraph(
        "Mã nguồn tham khảo (C++):\n"
        "#include <bits/stdc++.h>\n"
        "using namespace std;\n"
        "int main() {\n"
        "    ios_base::sync_with_stdio(false);\n"
        "    cin.tie(NULL);\n"
        "    // đọc file vào stdin/stdout\n"
        "    return 0;\n"
        "}"
    )
    doc_tin.save(str(samples_dir / "de_toan_chuyen_hsg.docx"))

    # ------------------------------------------------------------------------
    # 3. GENUINE FILE 3: de_chuyen_anh_quoc_gia.pdf
    # Specialized English Exam (Word Formation, Cloze Test, Sentence Transformation)
    # ------------------------------------------------------------------------
    eng_lines = [
        "MINISTRY OF EDUCATION AND TRAINING - NATIONAL ENGLISH OLYMPIAD",
        "SPECIALIZED ENGLISH EXAMINATION FOR GIFTED STUDENTS",
        "Time allowed: 180 minutes",
        "--------------------------------------------------------------------------------",
        "SECTION I: PHONETICS & PHONOLOGY",
        "Question 1: Mark the letter A, B, C, or D to indicate the word whose primary stress differs:",
        "A. photography     B. advantageous     C. atmospheric      D. electronic",
        "Question 2: Mark the letter A, B, C, or D whose underlined part differs in pronunciation:",
        "A. thorough        B. cough            C. rough            D. tough",
        "",
        "SECTION II: LEXICO-GRAMMAR & WORD FORMATION",
        "Part 1: Give the correct form of the words in brackets (Word Formation):",
        "1. The government took swift action to curb the (PRECEDE) ____________ economic crisis.",
        "2. His explanation was completely (COMPREHEND) ____________ to the general public.",
        "",
        "Part 2: Guided Cloze Test - Fill in each numbered blank with ONE suitable word:",
        "Global warming is one of the most pressing threats confronting humanity today...",
        "",
        "SECTION III: SENTENCE TRANSFORMATION",
        "Finish each of the following sentences so that it means exactly the same as the original sentence:",
        "1. It was not until the end of the meeting that he realized his grave mistake.",
        "-> Only at ___________________________________________________________",
        "2. The children were fascinated by the storyteller's vivid imagination.",
        "-> The children found _______________________________________________",
    ]
    create_pdf_with_text(samples_dir / "de_chuyen_anh_quoc_gia.pdf", eng_lines)

    # ------------------------------------------------------------------------
    # 4. GENUINE FILE 4: japanese_jlpt_n2_mondai.pdf
    # Japanese JLPT N2 Exam (Kana, Kanji, Dokkai, Bunpou)
    # ------------------------------------------------------------------------
    jp_lines = [
        "日本語能力試験 (JLPT) - N2 レベル模擬試験",
        "言語知識（文字・語彙・文法）・読解",
        "--------------------------------------------------------------------------------",
        "問題 1: 次の文章を読んで、後の問いに対する答えとして最もよいものを、1・2・3・4から一つ選びなさい。",
        "現代社会における情報技術の進歩は著しく、私たちの日常生活を大きく変革させました。",
        "特に人工知能の発展により、これまで人間しかできなかった作業が自動化されています。",
        "",
        "問い 1: 筆者が言いたいこととして、最も適切なものはどれか。",
        "1. 技術の発展により人間の仕事はすべて不要になる。",
        "2. 新しい技術に適応しながら共存していくことが求められている。",
        "3. 情報技術の発展は人間社会に悪影響のみをもたらす。",
        "4. 昔の生活様式に戻るべきである。",
        "",
        "問題 2: 次の文の（　）に入れるのに最もよいものを、1・2・3・4から一つ選びなさい。",
        "彼がそんな無責任なことを言う（　）がない。",
        "1. はず          2. わけ          3. つもり        4. こと",
        "--------------------------------------------------------------------------------",
        "正解と解説:",
        "問 1: 正解 2    問 2: 正解 1",
    ]
    create_pdf_with_text(
        samples_dir / "japanese_jlpt_n2_mondai.pdf",
        jp_lines,
        fontfile="C:/Windows/Fonts/msgothic.ttc",
    )

    # ------------------------------------------------------------------------
    # 5. GENUINE FILE 5: giao_an_vat_ly_12_cv5512.docx
    # Lesson Plan / Kế hoạch bài dạy chuẩn Công văn 5512 môn Vật lý
    # ------------------------------------------------------------------------
    doc_ga = Document()
    doc_ga.add_heading("KẾ HOẠCH BÀI DẠY (GIÁO ÁN THEO CÔNG VĂN 5512)", level=1)
    doc_ga.add_paragraph("MÔN: VẬT LÝ 12 - BÀI 1: DAO ĐỘNG ĐIỀU HÒA")
    doc_ga.add_paragraph("I. MỤC TIÊU BÀI HỌC:")
    doc_ga.add_paragraph(
        "1. Kiến thức: Học sinh nắm được định nghĩa dao động điều hòa, li độ, biên độ dao động, "
        "tần số góc, chu kỳ và bước sóng của con lắc lò xo và con lắc đơn."
    )
    doc_ga.add_paragraph(
        "2. Năng lực: Phát triển năng lực thực nghiệm vật lý, giải quyết bài toán dòng điện xoay chiều "
        "và dao động cơ học."
    )
    doc_ga.add_paragraph("II. THIẾT BỊ DẠY HỌC VÀ HỌC LIỆU:")
    doc_ga.add_paragraph("Bộ thí nghiệm con lắc lò xo, máy chiếu, phiếu học tập số 1.")
    doc_ga.add_paragraph("III. TIẾN TRÌNH DẠY HỌC:")
    doc_ga.add_paragraph("1. Hoạt động khởi động: Quan sát chuyển động của con lắc đồng hồ.")
    doc_ga.add_paragraph("2. Hoạt động hình thành kiến thức: Xây dựng phương trình vi phân dao động x = A cos(omega t + phi).")
    doc_ga.add_paragraph("3. Hoạt động luyện tập: Làm bài tập tính vận tốc cực đại và gia tốc cực đại.")
    doc_ga.add_paragraph("4. Hoạt động vận dụng: Giải thích hiện tượng cộng hưởng cơ học trong kỹ thuật cầu đường.")
    doc_ga.save(str(samples_dir / "giao_an_vat_ly_12_cv5512.docx"))

    # ------------------------------------------------------------------------
    # 6. GENUINE FILE 6: hop_dong_dich_vu_cntt.docx
    # Administrative Contract
    # ------------------------------------------------------------------------
    doc_hd = Document()
    doc_hd.add_paragraph("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    doc_hd.add_paragraph("Độc lập - Tự do - Hạnh phúc")
    doc_hd.add_paragraph("-----------------------------")
    doc_hd.add_heading("HỢP ĐỒNG DỊCH VỤ PHÁT TRIỂN PHẦN MỀM", level=1)
    doc_hd.add_paragraph("Số: 128/2026/HĐDV-TECH")
    doc_hd.add_paragraph("Căn cứ Bộ luật Dân sự nước Cộng hòa xã hội chủ nghĩa Việt Nam năm 2015.")
    doc_hd.add_paragraph("Hôm nay, ngày 26 tháng 09 năm 2026, chúng tôi gồm có:")
    doc_hd.add_paragraph("BÊN A (BÊN SỬ DỤNG DỊCH VỤ): CÔNG TY CỔ PHẦN CÔNG NGHỆ ALPHA")
    doc_hd.add_paragraph("BÊN B (BÊN CUNG CẤP DỊCH VỤ): CÔNG TY TNHH PHẦN MỀM BETA")
    doc_hd.add_paragraph("Hai bên thống nhất ký kết hợp đồng dịch vụ với các điều khoản như sau:")
    doc_hd.add_paragraph("Điều 1: Đối tượng của hợp đồng - Bên B cung cấp dịch vụ phát triển hệ thống kiểm tra văn bản DocInspector.")
    doc_hd.add_paragraph("Điều 2: Thời hạn thực hiện và bàn giao sản phẩm.")
    doc_hd.add_paragraph("Điều 3: Giá trị hợp đồng và phương thức thanh toán.")
    doc_hd.add_paragraph("Điều 4: Quyền và nghĩa vụ của Bên A và Bên B.")
    doc_hd.save(str(samples_dir / "hop_dong_dich_vu_cntt.docx"))

    # ------------------------------------------------------------------------
    # 7. GENUINE FILE 7: de_hoa_hoc_huu_co_thpt.pdf
    # High School Chemistry Exam (Este, peptit, amino axit, kim loại kiềm)
    # ------------------------------------------------------------------------
    chem_lines = [
        "BỘ GIÁO DỤC VÀ ĐÀO TẠO - ĐỀ THI TỐT NGHIỆP TRUNG HỌC PHỔ THÔNG",
        "MÔN: HÓA HỌC - Thời gian làm bài: 50 phút (40 câu trắc nghiệm)",
        "--------------------------------------------------------------------------------",
        "Câu 1: Hợp chất nào sau đây là este no, đơn chức, mạch hở?",
        "A. CH3COOC2H5       B. HCOOCH=CH2      C. CH3COOH         D. C2H5OH",
        "Câu 2: Thủy phân hoàn toàn chất béo gluxit trong dung dịch kiềm nóng gọi là phản ứng:",
        "A. Xà phòng hóa     B. Trùng ngưng     C. Este hóa        D. Nhiệt nhôm",
        "Câu 3: Chất nào sau đây là một amino axit có trong protein?",
        "A. Glyxin           B. Glucozơ         C. Saccarozơ       D. Ancol etylic",
        "Câu 4: Kim loại kiềm nào sau đây tan hoàn toàn trong nước ở nhiệt độ thường?",
        "A. Natri            B. Đồng            C. Sắt             D. Crôm",
        "Câu 5: Cho peptit Ala-Gly-Val tác dụng với dung dịch HCl dư. Số liên kết peptit là:",
        "A. 2                B. 3               C. 1               D. 4",
        "Câu 6: Áp dụng định luật bảo toàn e và bảo toàn khối lượng trong phản ứng oxi hóa khử.",
        "A. Tổng mol e cho = tổng mol e nhận    B. Khối lượng este tăng gấp đôi",
        "C. Dung dịch chuyển sang màu đỏ        D. Tạo kết tủa trắng",
        "--------------------------------------------------------------------------------",
        "BẢNG ĐÁP ÁN: 1-A  2-A  3-A  4-A  5-A  6-A",
    ]
    create_pdf_with_text(samples_dir / "de_hoa_hoc_huu_co_thpt.pdf", chem_lines)

    # ------------------------------------------------------------------------
    # 8. GENUINE FILE 8: de_sinh_hoc_di_truyen.docx
    # Biology Exam (ADN, ARN, Menđen, di truyền học quần thể, đột biến gen)
    # ------------------------------------------------------------------------
    doc_bio = Document()
    doc_bio.add_heading("ĐỀ THI HỌC SINH GIỎI TỈNH MÔN SINH HỌC LỚP 12", level=1)
    doc_bio.add_paragraph("Thời gian làm bài: 90 phút")
    doc_bio.add_paragraph("Câu 1: Quá trình tái bản ADN và phiên mã tổng hợp ARN diễn ra trong nhân tế bào.")
    doc_bio.add_paragraph("A. Theo nguyên tắc bán bảo tồn và bổ sung    B. Chỉ theo nguyên tắc giữ lại một nửa")
    doc_bio.add_paragraph("C. Không cần enzim ARN polimeraza            D. Diễn ra ở tế bào chất")
    doc_bio.add_paragraph("Câu 2: Đột biến gen thay thế một cặp nucleotit dẫn đến biến đổi cấu trúc phân tử protein.")
    doc_bio.add_paragraph("A. Làm thay đổi tối đa một axit amin         B. Làm thay đổi toàn bộ chuỗi polipeptit")
    doc_bio.add_paragraph("C. Không làm thay đổi phân tử ARN            D. Tăng số lượng nhiễm sắc thể")
    doc_bio.add_paragraph("Câu 3: Quy luật di truyền Menđen về phân ly độc lập áp dụng khi các cặp alen nằm trên các cặp nhiễm sắc thể khác nhau.")
    doc_bio.add_paragraph("A. Đúng                                      B. Sai")
    doc_bio.add_paragraph("Câu 4: Cấu trúc di truyền học quần thể cân bằng Hacđi-Vanbec thỏa mãn công thức p^2 + 2pq + q^2 = 1.")
    doc_bio.add_paragraph("A. Tần số alen không đổi qua các thế hệ     B. Kiểu hình lặn luôn chiếm ưu thế")
    doc_bio.add_paragraph("C. Xảy ra đột biến liên tục                  D. Chọn giống nhân tạo triệt để")
    doc_bio.save(str(samples_dir / "de_sinh_hoc_di_truyen.docx"))

    print(f"Generated 8 sample test documents in {samples_dir}")


if __name__ == "__main__":
    target = Path(__file__).parent / "samples"
    generate_all_samples(target)
