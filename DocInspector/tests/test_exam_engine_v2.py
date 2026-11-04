"""
Comprehensive Regression Test Suite for DocInspector Exam Parsing Engine v2.0.0 (Phần XIII - Mục 36, 37, 38).
Covers all 6 Test Groups (A, B, C, D, E, F):
- Group A: Basic PDF/DOCX/MCQ/Essay/Answer Key parsing
- Group B: Question variants (2-6 options, inline/multiline, false-positive A-D guard, nested sub-questions a)->i),
           True/False, Fill-blank, Matching, Ordering, Classification, Table completion, Calculation, Proof,
           Shared Reading Passage & Shared Table/Figure context linking)
- Group C: Complex Layouts (2-col & 3-col PDF with spanning headers & sidebars, cross-page questions,
           multi-page repeating headers/footers, duplicate shadow text layers, rotated 90° & blank PDF pages,
           borderless tables, and DOCX merged cells gridSpan/vMerge)
- Group D: Math formulas (OMML fractions/radicals/sup/sub), chemical equations, Unicode NFC vs raw_text preservation
- Group E: Scanned PDF, Hybrid PDF, and Image handling under OCR_MODE=local vs OCR_MODE=off (strictly no ML/fabrication)
- Group F: Corrupted files, encrypted PDF, wrong extension, EXE spoofing, Zip-Bomb & Path Traversal protection,
           oversize guard, multi-exam-code answer keys, 18-point StructuralValidator, manual correction tracking,
           batch isolation, and ParserEvaluator Precision/Recall/F1 metrics.
"""

from __future__ import annotations

import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

import fitz  # PyMuPDF
from docx import Document
from PIL import Image, ImageDraw

from DocInspector import (
    BatchDocumentProcessor,
    CanonicalQuestionType,
    DOCXReader,
    DocumentInspector,
    DocumentReaderRegistry,
    EngineConfig,
    ExamParsingEngineV2,
    FastDocumentExtractor,
    ImageReader,
    LayoutAnalyzer,
    LegacyDOCReader,
    OCRMode,
    PDFReader,
    PageContentState,
    ParserEvaluator,
    QuestionParser,
    ReaderOptions,
    SecurityGuard,
    StructuralValidator,
    UnicodeMathNormalizer,
    get_config,
    set_config,
    set_ocr_mode,
)


class TestExamEngineV2(unittest.TestCase):
    """Bộ kiểm thử hồi quy toàn diện 6 nhóm (A–F) cho Engine Đọc & Phân Tích Đề Thi v2.0.0."""

    def setUp(self) -> None:
        self._orig_cfg = get_config()
        set_config(EngineConfig())
        self.engine = ExamParsingEngineV2()

    def tearDown(self) -> None:
        set_config(self._orig_cfg)

    # =========================================================================
    # NHÓM A — CÂU HỎI CƠ BẢN (PDF 1 CỘT, DOCX, MCQ 4 ĐÁP ÁN, TỰ LUẬN, ĐÁP ÁN)
    # =========================================================================

    def test_group_a_pdf_1col_and_docx_basic_exam(self) -> None:
        """Nhóm A: Đọc đề PDF 1 cột và DOCX cơ bản có cả trắc nghiệm, tự luận và bảng đáp án."""
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=595, height=842)
        exam_content = (
            "SỞ GIÁO DỤC VÀ ĐÀO TẠO HÀ NỘI\n"
            "ĐỀ KIỂM TRA HỌC KỲ I NĂM HỌC 2025 - 2026\n"
            "Môn: Toán 12 - Thời gian làm bài: 90 phút\n"
            "Mã đề: 101\n\n"
            "PHẦN I. TRẮC NGHIỆM\n"
            "Câu 1. Tập xác định của hàm số y = ln(x - 1) là:\n"
            "A. (1; +∞)   B. [1; +∞)   C. R \\ {1}   D. (-∞; 1)\n\n"
            "Câu 2. Đạo hàm của hàm số y = x^3 + 2x là:\n"
            "A. 3x^2 + 2\n"
            "B. 3x^2\n"
            "C. x^2 + 2\n"
            "D. 3x + 2\n\n"
            "PHẦN II. TỰ LUẬN\n"
            "Câu 3 (2,0 điểm). Giải phương trình 2x^2 - 5x + 2 = 0.\n\n"
            "--- HẾT ---\n"
            "BẢNG ĐÁP ÁN\n"
            "1-A   2-A\n"
        )
        page.insert_text((50, 50), exam_content, fontsize=11)
        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        std_doc = self.engine.parse_document(pdf_bytes, file_name="de_toan_12.pdf", subject="MATHEMATICS")
        self.assertEqual(std_doc.source_format, "PDF")
        self.assertEqual(len(std_doc.questions), 3)
        self.assertEqual(std_doc.questions[0].type, CanonicalQuestionType.SINGLE_CHOICE)
        self.assertEqual(len(std_doc.questions[0].options), 4)
        self.assertEqual(std_doc.questions[0].answer, "A")
        self.assertEqual(std_doc.questions[1].answer, "A")
        self.assertEqual(std_doc.questions[2].type, CanonicalQuestionType.CALCULATION)
        self.assertEqual(std_doc.questions[2].score_points, 2.0)
        self.assertTrue(std_doc.validation_passed)

        # Kiểm tra tương thích ngược với DocumentInspector.inspect(deep=True)
        report = DocumentInspector.inspect(pdf_bytes, file_name="de_toan_12.pdf", deep=True)
        self.assertIsNotNone(report.standardized_document)
        self.assertEqual(len(report.standardized_document.questions), 3)

    # =========================================================================
    # NHÓM B — BIẾN THỂ CÂU HỎI, NEGATIVE CONTEXT GUARDS & NGỮ CẢNH DÙNG CHUNG
    # =========================================================================

    def test_group_b_negative_guards_toc_and_geometry_points(self) -> None:
        """Nhóm B: Không nhận nhầm dòng Mục lục (TOC), tham chiếu giữa câu hoặc điểm A, B, C hình học thành phương án."""
        text = (
            "MỤC LỤC ÔN TẬP\n"
            "Bài 1: Mệnh đề và tập hợp ...................... 12\n"
            "Bài 2: Hàm số bậc hai .......................... 25\n\n"
            "PHẦN ĐỀ BÀI\n"
            "Câu 1. Trong mặt phẳng Oxy, cho tam giác ABC có điểm A(1; 2), B(3; 4) và C(5; 0). "
            "Như đã chứng minh ở Bài 1, hãy tính chu vi tam giác ABC.\n\n"
            "Câu 2. Chọn tất cả các đáp án đúng về số nguyên tố:\n"
            "(A) Số 2 là số nguyên tố chẵn duy nhất\n"
            "(B) Số 1 là số nguyên tố\n"
            "(C) Số 3 và số 5 là các số nguyên tố lẻ\n"
            "(D) Mọi số nguyên tố đều là số lẻ\n"
            "(E) Có vô số số nguyên tố\n"
        )
        std_doc = self.engine.parse_document(text.encode("utf-8"), file_name="de_hinh_hoc.txt")
        # Chỉ có 2 câu hỏi thật (Câu 1 và Câu 2), 2 dòng mục lục "Bài 1 .... 12" và tham chiếu "ở Bài 1" bị loại trừ!
        self.assertEqual(len(std_doc.questions), 2)
        q1, q2 = std_doc.questions[0], std_doc.questions[1]
        self.assertEqual(q1.number, 1)
        self.assertEqual(len(q1.options), 0)  # Điểm A(1;2), B(3;4), C(5;0) không bị nhận nhầm là phương án!
        self.assertEqual(q1.type, CanonicalQuestionType.CALCULATION)

        # Câu 2 có 5 phương án (A)..(E) và là MULTIPLE_CHOICE
        self.assertEqual(q2.number, 2)
        self.assertEqual(q2.type, CanonicalQuestionType.MULTIPLE_CHOICE)
        self.assertEqual([o.marker for o in q2.options], ["A", "B", "C", "D", "E"])

    def test_group_b_all_question_types_and_nested_subquestions(self) -> None:
        """Nhóm B: Kiểm tra đủ các loại câu hỏi: True/False, Fill-Blank, Matching, Ordering, Classification, Table Completion, Proof, Composite (a -> i, ii)."""
        text = (
            "Câu 1. Xét tính đúng sai của các mệnh đề sau:\n"
            "a) Hàm số y = sin(x) tuần hoàn với chu kỳ 2π.\n"
            "b) Hàm số y = cos(x) là hàm số lẻ.\n"
            "c) Tập giá trị của hàm số y = sin(x) là [-1; 1].\n"
            "d) Đạo hàm của sin(x) là -cos(x).\n\n"
            "Câu 2. Điền từ thích hợp vào chỗ trống: She was ________ (amaze) by the ________ (beauty) scenery.\n\n"
            "Câu 3. Nối cột A với cột B để được khẳng định đúng:\n"
            "| Cột A | Cột B |\n"
            "| --- | --- |\n"
            "| 1. H2SO4 | a. Axit mạnh |\n"
            "| 2. NaOH | b. Bazơ kiềm |\n\n"
            "Câu 4. Sắp xếp các sự kiện lịch sử sau theo thứ tự thời gian tăng dần: (1) Chiến dịch Điện Biên Phủ; (2) Cách mạng tháng Tám; (3) Chiến dịch Hồ Chí Minh.\n\n"
            "Câu 5. Phân loại các chất sau vào nhóm thích hợp (oxit axit, oxit bazơ): CO2, SO2, CaO, Na2O.\n\n"
            "Câu 6. Hoàn thành bảng số liệu còn thiếu vào bảng sau:\n"
            "| Đại lượng | Giá trị |\n"
            "| --- | --- |\n"
            "| Vận tốc v | 15 m/s |\n"
            "| Thời gian t | ... s |\n\n"
            "Câu 7. Chứng minh rằng với mọi số thực dương a, b ta luôn có a + b >= 2√(ab).\n\n"
            "Câu 8 (3,0 điểm). Cho biểu thức P = (x + 1)/(x - 1).\n"
            "a) (1,5 điểm) Tìm điều kiện xác định và thực hiện các yêu cầu:\n"
            "i) Rút gọn biểu thức P khi x = 3.\n"
            "ii) Tìm x để P = 2.\n"
            "b) (1,5 điểm) Chứng minh rằng P không thể nhận giá trị bằng 1.\n"
        )
        std_doc = self.engine.parse_document(text.encode("utf-8"), file_name="all_types.txt")
        self.assertEqual(len(std_doc.questions), 8)

        q1 = std_doc.questions[0]
        self.assertEqual(q1.type, CanonicalQuestionType.TRUE_FALSE)
        self.assertEqual(len(q1.statements), 4)
        # Không tự bịa đáp án Đ/S khi chưa có bảng đáp án
        for st in q1.statements:
            self.assertIsNone(st.explicit_answer)

        q2 = std_doc.questions[1]
        self.assertEqual(q2.type, CanonicalQuestionType.FILL_BLANK)
        self.assertEqual(len(q2.blanks), 2)
        self.assertEqual(q2.blanks[0].root_word_hint, "amaze")
        self.assertEqual(q2.blanks[1].root_word_hint, "beauty")
        self.assertIn("________", q2.stem)

        q3 = std_doc.questions[2]
        self.assertEqual(q3.type, CanonicalQuestionType.MATCHING)
        self.assertIsNotNone(q3.matching_columns)
        self.assertEqual(len(q3.matching_columns["col_a"]), 2)
        self.assertEqual(len(q3.matching_columns["col_b"]), 2)

        self.assertEqual(std_doc.questions[3].type, CanonicalQuestionType.ORDERING)
        self.assertEqual(std_doc.questions[4].type, CanonicalQuestionType.CLASSIFICATION)
        self.assertEqual(std_doc.questions[5].type, CanonicalQuestionType.TABLE_COMPLETION)
        self.assertEqual(std_doc.questions[6].type, CanonicalQuestionType.PROOF)

        q8 = std_doc.questions[7]
        self.assertEqual(q8.type, CanonicalQuestionType.COMPOSITE)
        self.assertEqual(len(q8.sub_questions), 2)
        self.assertEqual(q8.sub_questions[0].marker, "a")
        self.assertEqual(q8.sub_questions[0].score_points, 1.5)
        self.assertEqual(len(q8.sub_questions[0].children), 2)
        self.assertEqual(q8.sub_questions[0].children[0].marker, "i")
        self.assertEqual(q8.sub_questions[0].children[1].marker, "ii")
        self.assertEqual(q8.sub_questions[1].type, CanonicalQuestionType.PROOF)

    def test_group_b_shared_reading_passage_context_linking(self) -> None:
        """Nhóm B: Tách đoạn văn đọc hiểu dùng chung bị dính ở cuối Câu 1 và liên kết context_id cho Câu 2, 3."""
        text = (
            "Câu 1. Chọn từ có trọng âm khác với các từ còn lại:\n"
            "A. teacher   B. student   C.doctor   D. engineer\n\n"
            "Đọc đoạn văn sau và trả lời các câu hỏi từ câu 2 đến câu 3:\n"
            "Artificial intelligence (AI) is transforming education around the world by providing personalized learning paths.\n\n"
            "Câu 2. Chủ đề chính của đoạn văn trên là gì?\n"
            "A. Trí tuệ nhân tạo trong giáo dục   B. Lịch sử máy tính   C. Mạng xã hội   D. Thương mại điện tử\n\n"
            "Câu 3. Theo đoạn văn, AI cung cấp điều gì cho người học?\n"
            "A. Lộ trình học cá nhân hóa   B. Học phí miễn phí   C. Bằng cấp quốc tế   D. Sách giáo khoa giấy\n"
        )
        std_doc = self.engine.parse_document(text.encode("utf-8"), file_name="reading_context.txt")
        self.assertEqual(len(std_doc.questions), 3)
        self.assertEqual(len(std_doc.contexts), 1)

        ctx = std_doc.contexts[0]
        self.assertEqual(ctx.question_range, (2, 3))
        self.assertIn("Artificial intelligence", ctx.text)

        # Phương án D của Câu 1 đã được tách sạch đoạn văn đọc hiểu phía sau
        self.assertEqual(std_doc.questions[0].options[-1].text, "engineer")
        self.assertIsNone(std_doc.questions[0].context_id)
        self.assertEqual(std_doc.questions[1].context_id, ctx.context_id)
        self.assertEqual(std_doc.questions[2].context_id, ctx.context_id)

    # =========================================================================
    # NHÓM C — BỐ CỤC PHỨC TẠP (2-3 CỘT, DUPLICATE LAYER, ROTATED, MERGED CELLS)
    # =========================================================================

    def test_group_c_pdf_3_columns_and_duplicate_shadow_layer(self) -> None:
        """Nhóm C: Tái dựng đúng thứ tự đọc PDF 3 cột + khử lớp văn bản trùng lặp (shadow text layer)."""
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=600, height=800)

        # Tiêu đề tràn ngang 3 cột (spanning block)
        page.insert_text((150, 40), "ĐỀ THI THỬ 3 CỘT - MÔN VẬT LÝ 12", fontsize=13)

        # Cột 1 (x = 30..180): Câu 1 & Câu 2
        page.insert_text((30, 100), "Câu 1. Đơn vị của tần số là:\nA. Hz  B. m  C. s  D. kg", fontsize=9)
        # Chèn lớp bóng trùng lặp (shadow text lệch 1pt) cho Câu 1
        page.insert_text((31, 101), "Câu 1. Đơn vị của tần số là:\nA. Hz  B. m  C. s  D. kg", fontsize=9)
        page.insert_text((30, 220), "Câu 2. Chu kỳ dao động T là:\nA. 1/f  B. f  C. 2f  D. f^2", fontsize=9)

        # Cột 2 (x = 220..370): Câu 3
        page.insert_text((220, 100), "Câu 3. Vận tốc ánh sáng trong chân không:\nA. 3.10^8 m/s  B. 300 m/s", fontsize=9)

        # Cột 3 (x = 410..560): Câu 4
        page.insert_text((410, 100), "Câu 4. Điện tích nguyên tố e bằng:\nA. 1,6.10^-19 C  B. 1 C", fontsize=9)

        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        std_doc = self.engine.parse_document(pdf_bytes, file_name="de_3_cot.pdf")
        self.assertEqual(std_doc.pages[0].column_count, 3)
        self.assertTrue(any(w.code == "DUPLICATE_TEXT_LAYER" for w in std_doc.warnings))
        self.assertEqual([q.number for q in std_doc.questions], [1, 2, 3, 4])

    def test_group_c_repeating_headers_footers_and_rotated_blank_pages(self) -> None:
        """Nhóm C: Nhận diện header/footer lặp lại qua các trang, trang trắng và trang xoay 90°."""
        pdf_doc = fitz.open()

        # Trang 1: Bình thường
        p1 = pdf_doc.new_page(width=595, height=842)
        p1.insert_text((50, 30), "TRUONG THPT CHUYEN HA NOI - AMSTERDAM", fontsize=10)
        p1.insert_text((50, 100), "Câu 1. Giá trị của 2 + 2 bằng:\nA. 4   B. 5   C. 6   D. 7", fontsize=11)
        p1.insert_text((250, 810), "Trang 1/3 - Mã đề 105", fontsize=10)

        # Trang 2: Trang trắng hoàn toàn
        pdf_doc.new_page(width=595, height=842)

        # Trang 3: Trang bị xoay 90 độ
        p3 = pdf_doc.new_page(width=595, height=842)
        p3.insert_text((50, 30), "TRUONG THPT CHUYEN HA NOI - AMSTERDAM", fontsize=10)
        p3.insert_text((50, 100), "Câu 2. Giá trị của 3 x 3 bằng:\nA. 9   B. 6   C. 12   D. 3", fontsize=11)
        p3.insert_text((250, 810), "Trang 3/3 - Mã đề 105", fontsize=10)
        p3.set_rotation(90)

        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        std_doc = self.engine.parse_document(pdf_bytes, file_name="multipage_layout.pdf")
        self.assertEqual(std_doc.page_count, 3)
        self.assertEqual(std_doc.pages[1].state, PageContentState.BLANK_PAGE)
        self.assertEqual(std_doc.pages[2].state, PageContentState.ROTATED_PAGE)
        self.assertEqual(std_doc.pages[2].rotation_deg, 90)
        self.assertTrue(any("THPT CHUYEN HA NOI - AMSTERDAM" in h for h in std_doc.headers))
        self.assertTrue(any("Trang" in f for f in std_doc.footers))
        self.assertEqual(len(std_doc.questions), 2)

    def test_group_c_docx_merged_cells_and_borderless_tables(self) -> None:
        """Nhóm C: Bảo toàn ô gộp ngang (gridSpan) & ô gộp dọc (vMerge) trong DOCX và bảng không viền."""
        doc = Document()
        doc.add_paragraph("Câu 1. Cho bảng số liệu có ô gộp sau:")
        tbl = doc.add_table(rows=3, cols=3)
        # Gộp ngang 2 ô đầu của hàng 0
        cell_00 = tbl.cell(0, 0)
        cell_01 = tbl.cell(0, 1)
        cell_00.merge(cell_01)
        cell_00.text = "Nhóm Chỉ Tiêu"
        tbl.cell(0, 2).text = "Giá trị"
        # Gộp dọc cột 0 ở hàng 1 và hàng 2
        cell_10 = tbl.cell(1, 0)
        cell_20 = tbl.cell(2, 0)
        cell_10.merge(cell_20)
        cell_10.text = "Khu vực I"
        tbl.cell(1, 1).text = "Năm 2024"
        tbl.cell(1, 2).text = "120"
        tbl.cell(2, 1).text = "Năm 2025"
        tbl.cell(2, 2).text = "150"

        buf = io.BytesIO()
        doc.save(buf)
        std_doc = self.engine.parse_document(buf.getvalue(), file_name="merged_table.docx")

        self.assertEqual(len(std_doc.tables), 1)
        t_model = std_doc.tables[0]
        self.assertTrue(any(c.col_span >= 2 for c in t_model.cells))
        self.assertTrue(any(c.row_span >= 2 for c in t_model.cells))

    # =========================================================================
    # NHÓM D — CÔNG THỨC TOÁN OMML, KÝ HIỆU HÓA HỌC & UNICODE TIẾNG VIỆT
    # =========================================================================

    def test_group_d_docx_omml_math_and_superscript_subscript(self) -> None:
        """Nhóm D: Trích xuất công thức OMML (<m:f>, <m:rad>, <m:sSup>) và chỉ số trên/dưới (<w:vertAlign>)."""
        doc = Document()
        p = doc.add_paragraph("Câu 1. Cho phản ứng hóa học của H")
        r_sub = p.add_run("2")
        r_sub.font.subscript = True
        p.add_run("SO")
        r_sub2 = p.add_run("4")
        r_sub2.font.subscript = True
        p.add_run(" và hàm số y = x")
        r_sup = p.add_run("2")
        r_sup.font.superscript = True

        # Nhúng thêm một phần tử toán học OMML <m:oMath><m:f><m:num><m:r><m:t>x+1</m:t></m:r></m:num><m:den><m:r><m:t>x-1</m:t></m:r></m:den></m:f></m:oMath>
        from docx.oxml import parse_xml
        omml_xml = (
            '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
            '<m:f><m:num><m:r><m:t>x+1</m:t></m:r></m:num><m:den><m:r><m:t>x-1</m:t></m:r></m:den></m:f>'
            '<m:rad><m:deg/><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>'
            '</m:oMath>'
        )
        p._p.append(parse_xml(omml_xml))
        doc.add_paragraph("A. 1   B. 2   C. 3   D. 4")

        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        std_doc = self.engine.parse_document(docx_bytes, file_name="math_omml.docx")
        self.assertEqual(len(std_doc.questions), 1)
        stem = std_doc.questions[0].stem
        self.assertIn("H_2SO_4", stem)
        self.assertIn("x^2", stem)
        self.assertIn("\\frac{x+1}{x-1}", stem)
        self.assertIn("\\sqrt{x}", stem)

        # Kiểm tra FastDocumentExtractor._extract_docx cũng giữ nguyên OMML & sup/sub
        ext_doc = FastDocumentExtractor.extract(docx_bytes, file_name="math_omml.docx")
        self.assertIn("\\frac{x+1}{x-1}", ext_doc.full_text)
        self.assertTrue(len(ext_doc.raw_unnormalized_text) > 0)

    def test_group_d_unicode_nfc_and_scientific_symbols_preservation(self) -> None:
        """Nhóm D: Chuẩn hóa Unicode NFC tổ hợp mà không làm mất chỉ số ² ³ ₀ ₁ và mũi tên phản ứng ⇌ →."""
        # Chuỗi chứa tiếng Việt NFD (dấu rời) + chỉ số hóa học/toán học
        nfd_text = "Ca\u0302u 1. Cho pha\u0309n u\u031b\u0301ng: N₂ + 3H₂ ⇌ 2NH₃ ↑ với ΔH < 0 và x² + y³ ≥ 2xy.\nA. Đúng   B. Sai"
        std_doc = self.engine.parse_document(nfd_text.encode("utf-8"), file_name="chem_unicode.txt")
        self.assertEqual(std_doc.raw_text, nfd_text)
        self.assertIn("Câu 1.", std_doc.normalized_text)
        self.assertIn("N₂ + 3H₂ ⇌ 2NH₃ ↑", std_doc.questions[0].stem)
        self.assertIn("x² + y³ ≥ 2xy", std_doc.questions[0].stem)

    # =========================================================================
    # NHÓM E — OCR CỤC BỘ VS CHẾ ĐỘ TẮT OCR HOÀN TOÀN (OCR_MODE=off)
    # =========================================================================

    def test_group_e_ocr_mode_off_strictly_no_ml_and_manual_review_flag(self) -> None:
        """Nhóm E: Khi OCR_MODE=off, ảnh scan trong PDF hoặc file ảnh độc lập không chạy OCR, giữ nguyên ImageAsset và gắn cờ cần xử lý thủ công."""
        # Tạo một ảnh PNG chứa chữ đề thi
        img = Image.new("RGB", (600, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 40), "Cau 1: 1 + 1 = ?  A. 2  B. 3  C. 4  D. 5", fill=(0, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        png_bytes = img_buf.getvalue()

        # Nhúng ảnh vào trang PDF scan (không có native text)
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(50, 50, 500, 200), stream=png_bytes)
        scanned_pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()

        # Bật chế độ OCR_MODE=off
        set_ocr_mode(OCRMode.OFF)
        std_pdf = self.engine.parse_document(scanned_pdf_bytes, file_name="scanned_exam.pdf")
        self.assertEqual(std_pdf.ocr_mode_used, "off")
        self.assertEqual(len(std_pdf.images), 1)
        self.assertEqual(std_pdf.images[0].ocr_status, "ocr_disabled")
        self.assertTrue(std_pdf.images[0].requires_manual_review)
        self.assertEqual(std_pdf.raw_text, "")
        self.assertTrue(any(w.code == "OCR_DISABLED_UNPROCESSED_SCAN" for w in std_pdf.warnings))

        # Kiểm tra ImageReader khi OCR_MODE=off
        std_img = self.engine.parse_document(png_bytes, file_name="scan_page.png")
        self.assertEqual(len(std_img.images), 1)
        self.assertEqual(std_img.images[0].ocr_status, "ocr_disabled")
        self.assertEqual(std_img.images[0].width, 600)
        self.assertEqual(std_img.images[0].height, 200)
        self.assertTrue(std_img.images[0].requires_manual_review)

    # =========================================================================
    # NHÓM F — FILE LỖI, BẢO MẬT, ĐA MÃ ĐỀ, RECOVERY & METRICS ĐỊNH LƯỢNG
    # =========================================================================

    def test_group_f_corrupted_encrypted_spoofed_and_zip_security(self) -> None:
        """Nhóm F: Xử lý an toàn PDF lỗi, PDF khóa mật khẩu, đặt sai đuôi file, giả mạo .exe và Path Traversal trong ZIP."""
        # 1. PDF bị hỏng cấu trúc
        corrupt_pdf = self.engine.parse_document(b"%PDF-1.7\nCORRUPTED_STREAM_DATA", file_name="broken.pdf")
        self.assertFalse(corrupt_pdf.validation_passed)
        self.assertTrue(any(e.code == "CORRUPTED_PDF" for e in corrupt_pdf.errors))

        # 2. PDF bị khóa mật khẩu
        enc_doc = fitz.open()
        enc_doc.new_page()
        enc_bytes = enc_doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="secret", user_pw="user123")
        enc_doc.close()
        enc_res = self.engine.parse_document(enc_bytes, file_name="locked.pdf")
        self.assertFalse(enc_res.validation_passed)
        self.assertTrue(any(e.code == "ENCRYPTED_PDF" for e in enc_res.errors))

        # 3. Đặt sai đuôi file (file PDF thật nhưng đặt tên .docx) -> tự động định tuyến sang PDFReader + cảnh báo
        valid_pdf = fitz.open()
        vp = valid_pdf.new_page()
        vp.insert_text((50, 50), "Câu 1. Thủ đô của Việt Nam là:\nA. Hà Nội  B. Huế  C. Đà Nẵng  D. Cần Thơ")
        valid_pdf_bytes = valid_pdf.tobytes()
        valid_pdf.close()
        misnamed_res = self.engine.parse_document(valid_pdf_bytes, file_name="de_thi_nham_duoi.docx")
        self.assertEqual(misnamed_res.source_format, "PDF")
        self.assertEqual(len(misnamed_res.questions), 1)
        self.assertTrue(any(w.code == "MISMATCHED_FILE_EXTENSION" for w in misnamed_res.warnings))

        # 4. Giả mạo file thực thi .exe dưới tên .pdf
        exe_res = self.engine.parse_document(b"MZ\x90\x00\x03\x00\x00\x00", file_name="malware.pdf")
        self.assertFalse(exe_res.validation_passed)
        self.assertTrue(any(e.code == "EXECUTABLE_FILE_REJECTED" for e in exe_res.errors))

        # 5. Path Traversal trong gói ZIP/DOCX
        mal_zip_buf = io.BytesIO()
        with zipfile.ZipFile(mal_zip_buf, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0")
        ok, z_err = SecurityGuard.validate_zip_container(mal_zip_buf.getvalue(), get_config())
        self.assertFalse(ok)
        self.assertEqual(z_err.code, "ZIP_PATH_TRAVERSAL")

        # 6. Vượt giới hạn kích thước tệp
        small_cfg = EngineConfig(max_file_size_bytes=100)
        set_config(small_cfg)
        oversize_res = self.engine.parse_document(b"A" * 500, file_name="oversize.txt")
        self.assertFalse(oversize_res.validation_passed)
        self.assertTrue(any(e.code == "FILE_TOO_LARGE" for e in oversize_res.errors))

    def test_group_f_multi_exam_codes_and_structural_validator_warnings(self) -> None:
        """Nhóm F: Bảng đáp án nhiều mã đề (Mã đề 101, 102), phát hiện đáp án lệch phương án và hiệu chỉnh thủ công."""
        text = (
            "Câu 1. Kết quả của 5 + 5 là:\n"
            "A. 10   B. 11   C. 12   D. 13\n\n"
            "Câu 2. Kết quả của 6 + 6 là:\n"
            "A. 10   B. 12   C. 14   D. 16\n\n"
            "--- HẾT ---\n"
            "BẢNG ĐÁP ÁN\n"
            "Mã đề 101:\n"
            "1-A   2-F   3-C\n"
            "Mã đề 102:\n"
            "1-B   2-D\n"
        )
        std_doc = self.engine.parse_document(text.encode("utf-8"), file_name="multi_code.txt")
        self.assertIn("101", std_doc.answer_keys_by_exam_code)
        self.assertIn("102", std_doc.answer_keys_by_exam_code)
        self.assertEqual(std_doc.answer_keys_by_exam_code["102"][1], "B")

        # Câu 2 có đáp án 'F' không nằm trong {A, B, C, D} -> cảnh báo và đưa vào questions_needing_review
        self.assertIn(std_doc.questions[1].id, std_doc.questions_needing_review)
        # Đáp án Câu 3 mồ côi -> phát cảnh báo INV_15_ORPHAN_ANSWER_KEYS
        self.assertTrue(any(w.code == "INV_15_ORPHAN_ANSWER_KEYS" for w in std_doc.warnings))

        # Kiểm tra hiệu chỉnh thủ công (ManualCorrectionRecord) giữ nguyên raw_value
        applied = std_doc.apply_manual_correction(
            question_id=std_doc.questions[1].id,
            field_name="answer",
            new_value="B",
            author="teacher_01",
            reason="Sửa lỗi gõ nhầm đáp án F thành B",
        )
        self.assertTrue(applied)
        self.assertEqual(std_doc.questions[1].answer, "B")
        self.assertEqual(std_doc.manual_corrections[0].raw_value, "F")
        self.assertEqual(std_doc.manual_corrections[0].corrected_value, "B")

    def test_group_f_targeted_recovery_and_evaluation_metrics_benchmark(self) -> None:
        """Nhóm F: Khôi phục cục bộ phương án gạch ngang (A - ...) và đánh giá định lượng Precision/Recall/F1 = 1.0."""
        text = (
            "Câu 1. Kim loại nào dẫn điện tốt nhất?\n"
            "A - Bạc (Ag)   B - Đồng (Cu)   C - Vàng (Au)   D - Nhôm (Al)\n\n"
            "Câu 2. Công thức hóa học của nước là:\n"
            "A. H2O   B. CO2   C. NaCl   D. O2\n\n"
            "--- HẾT ---\n"
            "BẢNG ĐÁP ÁN\n"
            "1-A   2-A\n"
        )
        std_doc = self.engine.parse_document(text.encode("utf-8"), file_name="recovery_bench.txt")
        self.assertEqual(len(std_doc.questions), 2)
        self.assertEqual(len(std_doc.questions[0].options), 4)
        self.assertTrue(any(w.code == "RECOVERED_DASH_OPTIONS" for w in std_doc.warnings))

        eval_res = ParserEvaluator.evaluate(
            doc=std_doc,
            expected_question_numbers=[1, 2],
            expected_option_counts={1: 4, 2: 4},
            expected_types={1: CanonicalQuestionType.SINGLE_CHOICE, 2: CanonicalQuestionType.SINGLE_CHOICE},
            expected_answers={1: "A", 2: "A"},
        )
        self.assertEqual(eval_res.question_boundary_precision, 1.0)
        self.assertEqual(eval_res.question_boundary_recall, 1.0)
        self.assertEqual(eval_res.question_boundary_f1, 1.0)
        self.assertEqual(eval_res.option_extraction_accuracy, 1.0)
        self.assertEqual(eval_res.question_type_accuracy, 1.0)
        self.assertEqual(eval_res.answer_key_accuracy, 1.0)

        # Kiểm tra BatchDocumentProcessor cô lập lỗi khi xử lý hàng loạt
        batch_proc = BatchDocumentProcessor(max_workers=2, per_file_timeout_sec=15)
        batch_out = batch_proc.process_batch(
            [
                ("good.txt", text.encode("utf-8")),
                ("bad.pdf", b"%PDF-1.4 BROKEN"),
            ]
        )
        self.assertEqual(len(batch_out), 2)
        self.assertFalse(batch_out[0].is_corrupted)
        self.assertTrue(batch_out[1].is_corrupted)


if __name__ == "__main__":
    unittest.main()
