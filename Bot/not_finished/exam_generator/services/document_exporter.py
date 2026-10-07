"""Dịch vụ xuất bản 2 tài liệu độc lập: [De_Thi] và [Huong_Dan_Giai] (DOCX & PDF).

Đảm bảo:
1. Hai tài liệu hoàn toàn tách biệt:
   - File 1: [De_Thi] — Đề bài sạch, sẵn sàng in ấn cho học sinh làm bài.
   - File 2: [Huong_Dan_Giai] — Lời giải chi tiết, ma trận đề, biểu điểm chấm.
2. Hỗ trợ định dạng Microsoft Word (.docx) và PDF vector chuẩn sắc nét.
3. Dung lượng mỗi file cam kết nghiêm ngặt < 5MB.
4. Tích hợp sơ đồ minh họa được vẽ tự động qua DiagramDrawer.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import docx
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor
import fitz

from utils.logger import get_logger

logger = get_logger("DocumentExporter")

# Kích thước tối đa cho phép (5MB)
MAX_FILE_BYTES = 5 * 1024 * 1024

VN_FONT_PATH = "C:/Windows/Fonts/arial.ttf"
if not os.path.exists(VN_FONT_PATH):
    VN_FONT_PATH = "C:/Windows/Fonts/calibri.ttf"


def _set_cell_background(cell, fill_hex: str) -> None:
    """Tô màu nền cho ô bảng trong Word."""
    tc_pr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150) -> None:
    """Đặt lề padding trong ô bảng Word."""
    tc_pr = cell._element.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
INVISIBLE_WATERMARK_TEXT = " [Biên soạn độc quyền bởi HyperHub AI Platform • discord.gg/hyperhub]"


def _inject_invisible_watermark_docx(paragraph, watermark_text: str = INVISIBLE_WATERMARK_TEXT) -> None:
    """Chèn watermark ẩn kiểu Claude vào đoạn văn Word (vô hình khi nhìn/in, nhưng dính chữ khi copy-paste)."""
    try:
        r = paragraph.add_run(watermark_text)
        r.font.size = Pt(1)
        r.font.color.rgb = RGBColor(255, 255, 255)
        rPr = r._element.get_or_add_rPr()
        rPr.append(OxmlElement("w:vanish"))
    except Exception as e:
        logger.debug(f"Không thể chèn invisible watermark vào Word: {e}")


def _inject_invisible_watermark_pdf(
    page,
    point: fitz.Point,
    fontname: str = "f0",
    fontfile: str | None = None,
    watermark_text: str = INVISIBLE_WATERMARK_TEXT,
) -> None:
    """Chèn watermark ẩn vào PDF (render_mode=3: vô hình khi xem/in, nhưng hiển thị khi bôi đen copy ra ngoài)."""
    try:
        page.insert_text(
            point,
            watermark_text,
            fontsize=8,
            fontname=fontname,
            fontfile=fontfile or VN_FONT_PATH,
            render_mode=3,
        )
    except Exception as e:
        logger.debug(f"Không thể chèn invisible watermark vào PDF: {e}")


class DocumentExporter:
    """Bộ máy xuất bản tài liệu đề thi và hướng dẫn chấm điểm sư phạm."""

    @staticmethod
    def _wrap_text_lines(text: str, max_width_pts: float, fontsize: float = 9.5) -> list[str]:
        """Chia văn bản thành các dòng vừa vặn với độ rộng trang PDF mà không bị tràn."""
        lines: list[str] = []
        for para in text.split("\n"):
            if not para.strip():
                lines.append("")
                continue
            words = para.split(" ")
            cur_line = ""
            for w in words:
                candidate = f"{cur_line} {w}".strip()
                if fitz.get_text_length(candidate, fontname="helv", fontsize=fontsize) > max_width_pts:
                    if cur_line:
                        lines.append(cur_line)
                    cur_line = w
                else:
                    cur_line = candidate
            if cur_line:
                lines.append(cur_line)
        return lines

    # =========================================================================
    # 1. TẠO FILE WORD: [De_Thi].docx
    # =========================================================================
    @classmethod
    def generate_exam_docx(
        cls,
        metadata: dict[str, Any],
        content_blocks: list[dict[str, Any]],
        output_path: str,
        diagram_paths: list[str] | None = None,
    ) -> str:
        """Tạo file Đề Thi (.docx) chuẩn sư phạm, không có đáp án."""
        doc = Document()

        # Định dạng lề trang 20mm
        sections = doc.sections
        for s in sections:
            s.top_margin = Inches(0.8)
            s.bottom_margin = Inches(0.8)
            s.left_margin = Inches(0.8)
            s.right_margin = Inches(0.8)

        # Header Bảng 2 cột (Cơ quan ban hành / Tên kỳ thi)
        header_table = doc.add_table(rows=1, cols=2)
        header_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        header_table.autofit = False

        left_cell = header_table.cell(0, 0)
        right_cell = header_table.cell(0, 1)
        left_cell.width = Inches(3.2)
        right_cell.width = Inches(3.6)

        # Cột trái
        p_left = left_cell.paragraphs[0]
        p_left.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r1 = p_left.add_run("TRUNG TÂM KHẢO THÍ HYPERHUB\n")
        r1.bold = True
        r1.font.size = Pt(10)
        r2 = p_left.add_run(f"MÔN THI: {metadata.get('subject', 'TỔNG HỢP').upper()}\n")
        r2.bold = True
        r2.font.size = Pt(11)
        r2.font.color.rgb = RGBColor(0, 51, 102)
        r3 = p_left.add_run(f"Thời gian làm bài: {metadata.get('duration', '90 phút')}")
        r3.font.size = Pt(9.5)
        r3.italic = True

        # Cột phải
        p_right = right_cell.paragraphs[0]
        p_right.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r4 = p_right.add_run("KỲ THI ĐÁNH GIÁ NĂNG LỰC & CHẤT LƯỢNG\n")
        r4.bold = True
        r4.font.size = Pt(10.5)
        r5 = p_right.add_run(f"ĐỀ THI CHÍNH THỨC\n")
        r5.bold = True
        r5.font.size = Pt(12)
        r5.font.color.rgb = RGBColor(180, 0, 0)
        r6 = p_right.add_run(f"Mã đề: {metadata.get('exam_code', 'HH-101')} • {metadata.get('length_tier', 'Tiêu chuẩn')}")
        r6.font.size = Pt(9.5)

        doc.add_paragraph().paragraph_format.space_after = Pt(4)

        # Bảng thông tin thí sinh
        student_table = doc.add_table(rows=1, cols=4)
        student_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Họ và tên:", "", "Số báo danh:", ""]
        widths = [Inches(1.0), Inches(3.0), Inches(1.2), Inches(1.6)]
        for i, text in enumerate(headers):
            cell = student_table.cell(0, i)
            cell.width = widths[i]
            _set_cell_background(cell, "F2F4F7")
            p = cell.paragraphs[0]
            if text:
                r = p.add_run(text)
                r.bold = True
                r.font.size = Pt(9.5)

        # Lời dặn
        note_p = doc.add_paragraph()
        note_p.paragraph_format.space_before = Pt(8)
        note_p.paragraph_format.space_after = Pt(14)
        r_note = note_p.add_run("📌 Lưu ý: Thí sinh làm bài trực tiếp vào phiếu trả lời hoặc giấy thi. Không sử dụng tài liệu ngoài quy định.")
        r_note.italic = True
        r_note.font.size = Pt(9)
        r_note.font.color.rgb = RGBColor(90, 90, 90)

        # Kẻ đường phân cách
        div_p = doc.add_paragraph()
        div_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_div = div_p.add_run("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        r_div.font.color.rgb = RGBColor(200, 205, 215)
        div_p.paragraph_format.space_after = Pt(12)

        # Nội dung từng khối / câu hỏi
        diag_idx = 0
        for block in content_blocks:
            b_type = block.get("type", "question")
            if b_type == "section_header":
                sec_p = doc.add_paragraph()
                sec_p.paragraph_format.space_before = Pt(14)
                sec_p.paragraph_format.space_after = Pt(6)
                r_sec = sec_p.add_run(block.get("title", ""))
                r_sec.bold = True
                r_sec.font.size = Pt(12)
                r_sec.font.color.rgb = RGBColor(0, 70, 140)
            else:
                q_num = block.get("number", "")
                q_text = block.get("text", "")
                q_points = block.get("points", "")
                options = block.get("options", [])

                # Làm sạch nếu AI vô tình ghi các lựa chọn A, B, C, D vào trong text
                if options:
                    m_opt = re.search(r'(?:\n\s*|\s{2,})[A-D]\.\s+', q_text)
                    if m_opt and len(q_text[m_opt.start():]) < len(q_text) * 0.8:
                        q_text = q_text[:m_opt.start()].strip()

                qp = doc.add_paragraph()
                qp.paragraph_format.space_before = Pt(8)
                qp.paragraph_format.space_after = Pt(4)

                rq_num = qp.add_run(f"Câu {q_num}: ")
                rq_num.bold = True
                rq_num.font.size = Pt(11)

                if q_points:
                    rq_pts = qp.add_run(f"({q_points}) ")
                    rq_pts.italic = True
                    rq_pts.font.size = Pt(10)
                    rq_pts.font.color.rgb = RGBColor(120, 120, 120)

                rq_txt = qp.add_run(q_text)
                rq_txt.font.size = Pt(11)

                # Các ý trắc nghiệm (A, B, C, D)
                if options:
                    for opt in options:
                        op = doc.add_paragraph()
                        op.paragraph_format.left_indent = Inches(0.4)
                        op.paragraph_format.space_after = Pt(2)
                        ro = op.add_run(opt)
                        ro.font.size = Pt(10.5)

                # Các ý con (a, b, c) nếu tự luận
                sub_items = block.get("sub_items", [])
                if sub_items:
                    for sub in sub_items:
                        sp = doc.add_paragraph()
                        sp.paragraph_format.left_indent = Inches(0.3)
                        sp.paragraph_format.space_after = Pt(3)
                        r_sub_num = sp.add_run(f"{sub.get('label', '')}. ")
                        r_sub_num.bold = True
                        r_sub_num.font.size = Pt(10.5)
                        r_sub_txt = sp.add_run(sub.get("text", ""))
                        r_sub_txt.font.size = Pt(10.5)

                # Chèn sơ đồ minh họa nếu có
                if diagram_paths and diag_idx < len(diagram_paths) and block.get("has_diagram"):
                    d_path = diagram_paths[diag_idx]
                    diag_idx += 1
                    if os.path.exists(d_path):
                        img_p = doc.add_paragraph()
                        img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        img_p.paragraph_format.space_before = Pt(6)
                        img_p.paragraph_format.space_after = Pt(8)
                        img_p.add_run().add_picture(d_path, width=Inches(4.5))

        # Footer trang cuối
        doc.add_paragraph().paragraph_format.space_before = Pt(24)
        end_p = doc.add_paragraph()
        end_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_end = end_p.add_run("───── HẾT ─────\n(Cán bộ coi thi không giải thích gì thêm)")
        r_end.bold = True
        r_end.font.size = Pt(10.5)
        r_end.font.color.rgb = RGBColor(100, 100, 100)
        _inject_invisible_watermark_docx(end_p)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
        cls._verify_file_size(output_path)
        return output_path

    # =========================================================================
    # 2. TẠO FILE WORD: [Huong_Dan_Giai].docx
    # =========================================================================
    @classmethod
    def generate_solutions_docx(
        cls,
        metadata: dict[str, Any],
        solution_blocks: list[dict[str, Any]],
        output_path: str,
        radar_chart_path: Optional[str] = None,
        audio_script: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Tạo file Hướng Dẫn Giải Chi Tiết & Biểu Điểm Chấm (.docx)."""
        doc = Document()
        for s in doc.sections:
            s.top_margin = Inches(0.8)
            s.bottom_margin = Inches(0.8)
            s.left_margin = Inches(0.8)
            s.right_margin = Inches(0.8)

        # Header
        head_p = doc.add_paragraph()
        head_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_h1 = head_p.add_run("HỆ THỐNG GIÁO DỤC TRỰC TUYẾN HYPERHUB\n")
        r_h1.bold = True
        r_h1.font.size = Pt(11)
        r_h2 = head_p.add_run(f"HƯỚNG DẪN GIẢI CHI TIẾT & BIỂU ĐIỂM CHẤM\n")
        r_h2.bold = True
        r_h2.font.size = Pt(14)
        r_h2.font.color.rgb = RGBColor(16, 124, 65)  # Emerald green
        r_h3 = head_p.add_run(f"MÔN: {metadata.get('subject', 'TỔNG HỢP').upper()} • MÃ ĐỀ: {metadata.get('exam_code', 'HH-101')}")
        r_h3.font.size = Pt(10.5)
        r_h3.italic = True

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # Bảng đáp án trắc nghiệm nhanh (nếu có)
        quick_answers = [b for b in solution_blocks if b.get("is_multiple_choice")]
        if quick_answers:
            p_ans_title = doc.add_paragraph()
            p_ans_title.paragraph_format.space_before = Pt(10)
            p_ans_title.paragraph_format.space_after = Pt(4)
            r_at = p_ans_title.add_run("I. BẢNG ĐÁP ÁN TRẮC NGHIỆM NHANH")
            r_at.bold = True
            r_at.font.size = Pt(11.5)
            r_at.font.color.rgb = RGBColor(0, 51, 102)

            cols = min(len(quick_answers), 10)
            if cols > 0:
                tbl = doc.add_table(rows=2, cols=cols)
                tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                for i, q in enumerate(quick_answers[:cols]):
                    c0 = tbl.cell(0, i)
                    c1 = tbl.cell(1, i)
                    _set_cell_background(c0, "003366")
                    p0 = c0.paragraphs[0]
                    p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    r_c0 = p0.add_run(f"C{q.get('number', i+1)}")
                    r_c0.bold = True
                    r_c0.font.color.rgb = RGBColor(255, 255, 255)

                    _set_cell_background(c1, "F2F4F7")
                    p1 = c1.paragraphs[0]
                    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    r_c1 = p1.add_run(q.get("correct_key", "A"))
                    r_c1.bold = True
                    r_c1.font.color.rgb = RGBColor(180, 0, 0)

        # Bổ sung Kịch bản phần thi nghe (Listening Audio Script) nếu có
        l_script = audio_script or metadata.get("listening_script") or []
        if l_script:
            p_ls_title = doc.add_paragraph()
            p_ls_title.paragraph_format.space_before = Pt(14)
            p_ls_title.paragraph_format.space_after = Pt(4)
            r_lst = p_ls_title.add_run("🎧 KỊCH BẢN BÀI NGHE (LISTENING AUDIO TRANSCRIPT)")
            r_lst.bold = True
            r_lst.font.size = Pt(11.5)
            r_lst.font.color.rgb = RGBColor(0, 51, 102)

            tbl_ls = doc.add_table(rows=1, cols=1)
            tbl_ls.alignment = WD_TABLE_ALIGNMENT.CENTER
            c_ls = tbl_ls.cell(0, 0)
            _set_cell_background(c_ls, "F7F9FC")
            _set_cell_margins(c_ls, top=100, bottom=100, left=150, right=150)
            p_first = c_ls.paragraphs[0]
            p_first.paragraph_format.space_after = Pt(4)
            p_first.add_run("Kịch bản đối chiếu dẫn chứng phòng thi:").italic = True

            for turn in l_script:
                spk = turn.get("speaker", "Speaker")
                role = turn.get("role", "")
                txt = turn.get("text", "")
                pt = c_ls.add_paragraph()
                pt.paragraph_format.space_after = Pt(3)
                r_spk = pt.add_run(f"[{spk} ({role})]: ")
                r_spk.bold = True
                r_spk.font.size = Pt(9.5)
                r_spk.font.color.rgb = RGBColor(30, 70, 130)
                r_txt = pt.add_run(txt)
                r_txt.font.size = Pt(9.5)

        # Lời giải chi tiết từng câu
        p_detail_title = doc.add_paragraph()
        p_detail_title.paragraph_format.space_before = Pt(16)
        p_detail_title.paragraph_format.space_after = Pt(6)
        r_dt = p_detail_title.add_run("II. LỜI GIẢI CHI TIẾT & BIỂU ĐIỂM CHẤM TỪNG BƯỚC")
        r_dt.bold = True
        r_dt.font.size = Pt(11.5)
        r_dt.font.color.rgb = RGBColor(0, 51, 102)

        for sol in solution_blocks:
            q_num = sol.get("number", "")
            ans_key = sol.get("correct_key", "")
            explanation = sol.get("explanation", "")
            rubric = sol.get("rubric", [])

            qp = doc.add_paragraph()
            qp.paragraph_format.space_before = Pt(10)
            qp.paragraph_format.space_after = Pt(3)

            r_q = qp.add_run(f"Câu {q_num}: ")
            r_q.bold = True
            r_q.font.size = Pt(11)

            if ans_key:
                r_key = qp.add_run(f"Đáp án đúng: {ans_key}\n")
                r_key.bold = True
                r_key.font.color.rgb = RGBColor(16, 124, 65)

            # Khung giải thích
            exp_table = doc.add_table(rows=1, cols=1)
            exp_table.alignment = WD_TABLE_ALIGNMENT.CENTER
            exp_cell = exp_table.cell(0, 0)
            _set_cell_background(exp_cell, "F9FAFB")
            _set_cell_margins(exp_cell, top=120, bottom=120, left=180, right=180)

            ep = exp_cell.paragraphs[0]
            r_exp_title = ep.add_run("💡 Hướng dẫn giải chi tiết:\n")
            r_exp_title.bold = True
            r_exp_title.font.size = Pt(10)
            r_exp_title.font.color.rgb = RGBColor(40, 80, 140)

            r_exp_body = ep.add_run(explanation)
            r_exp_body.font.size = Pt(10)

            # Bẫy / Lưu ý nếu có
            trap = sol.get("common_mistakes", "")
            if trap:
                tp = exp_cell.add_paragraph()
                tp.paragraph_format.space_before = Pt(4)
                r_trap_title = tp.add_run("⚠️ Bẫy tư duy thường gặp: ")
                r_trap_title.bold = True
                r_trap_title.font.size = Pt(9.5)
                r_trap_title.font.color.rgb = RGBColor(180, 60, 0)
                r_trap_txt = tp.add_run(trap)
                r_trap_txt.font.size = Pt(9.5)

            # Thang điểm chi tiết (Rubric)
            if rubric:
                rp = exp_cell.add_paragraph()
                rp.paragraph_format.space_before = Pt(4)
                r_rb_title = rp.add_run("📊 Thang điểm (Rubric):\n")
                r_rb_title.bold = True
                r_rb_title.font.size = Pt(9.5)
                r_rb_title.font.color.rgb = RGBColor(80, 80, 80)
                for step_txt, pts in rubric:
                    step_p = exp_cell.add_paragraph()
                    step_p.paragraph_format.left_indent = Inches(0.2)
                    step_p.paragraph_format.space_after = Pt(1)
                    r_step = step_p.add_run(f"• {step_txt}: ")
                    r_step.font.size = Pt(9)
                    r_pts = step_p.add_run(f"+{pts} điểm")
                    r_pts.bold = True
                    r_pts.font.size = Pt(9)
                    r_pts.font.color.rgb = RGBColor(16, 124, 65)

        # Báo cáo đánh giá ma trận Bloom & Sư phạm nếu có
        actual_radar_path = radar_chart_path or metadata.get("radar_chart_path")
        if actual_radar_path and os.path.exists(actual_radar_path):
            doc.add_page_break()
            p_rep_title = doc.add_paragraph()
            p_rep_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_rep_title.paragraph_format.space_before = Pt(12)
            p_rep_title.paragraph_format.space_after = Pt(8)
            r_rep = p_rep_title.add_run("BÁO CÁO ĐÁNH GIÁ MA TRẬN KHẢO THÍ & PHỔ ĐIỂM SƯ PHẠM")
            r_rep.bold = True
            r_rep.font.size = Pt(13)
            r_rep.font.color.rgb = RGBColor(0, 51, 102)

            p_img = doc.add_paragraph()
            p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_img.paragraph_format.space_after = Pt(14)
            p_img.add_run().add_picture(actual_radar_path, width=Inches(4.5))

            pe_info = metadata.get("pedagogy_evaluation") or {}
            p_eval = doc.add_paragraph()
            r_ev_t = p_eval.add_run("📊 CHỈ SỐ KHẢO THÍ & ĐỘ PHÂN HÓA SƯ PHẠM:\n")
            r_ev_t.bold = True
            r_ev_t.font.size = Pt(11)
            r_ev_t.font.color.rgb = RGBColor(16, 124, 65)

            p_ev_body = doc.add_paragraph()
            p_ev_body.paragraph_format.left_indent = Inches(0.2)
            p_ev_body.add_run(f"• Độ khó ước lượng (P-value): {pe_info.get('p_value', 0.62)} ➔ {pe_info.get('difficulty_label', 'Vừa sức')}\n")
            p_ev_body.add_run(f"• Chỉ số phân cách (D-value): {pe_info.get('d_value', 0.42)} ➔ {pe_info.get('discrimination_label', 'Tốt')}\n")
            p_ev_body.add_run("• Đánh giá chung: Ma trận câu hỏi phân bố cân đối theo khung nhận thức Bloom chuẩn Bộ GD&ĐT.")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path)
        cls._verify_file_size(output_path)
        return output_path

    # =========================================================================
    # 3. TẠO FILE PDF VECTOR: [De_Thi].pdf
    # =========================================================================
    @classmethod
    def generate_exam_pdf(
        cls,
        metadata: dict[str, Any],
        content_blocks: list[dict[str, Any]],
        output_path: str,
        diagram_paths: list[str] | None = None,
    ) -> str:
        """Tạo file Đề Thi PDF chuẩn sắc nét vector (< 5MB)."""
        doc = fitz.open()
        page_width, page_height = 595, 842  # A4 size in points
        margin = 45

        page = doc.new_page(width=page_width, height=page_height)
        curr_y = margin

        # Header Box
        page.draw_rect(fitz.Rect(margin, curr_y, page_width - margin, curr_y + 65), color=(0.1, 0.2, 0.4), width=1.2)
        page.draw_line(fitz.Point(280, curr_y), fitz.Point(280, curr_y + 65), color=(0.1, 0.2, 0.4), width=1)

        # Trái
        page.insert_text(fitz.Point(margin + 10, curr_y + 18), "TRUNG TÂM KHẢO THÍ HYPERHUB", fontsize=10, fontname="f0", fontfile=VN_FONT_PATH)
        page.insert_text(fitz.Point(margin + 10, curr_y + 36), f"MÔN THI: {metadata.get('subject', 'TỔNG HỢP').upper()}", fontsize=11, fontname="f0", fontfile=VN_FONT_PATH)
        page.insert_text(fitz.Point(margin + 10, curr_y + 52), f"Thời gian làm bài: {metadata.get('duration', '90 phút')}", fontsize=9, fontname="f0", fontfile=VN_FONT_PATH)

        # Phải
        page.insert_text(fitz.Point(295, curr_y + 18), "KỲ THI ĐÁNH GIÁ NĂNG LỰC", fontsize=10, fontname="f0", fontfile=VN_FONT_PATH)
        page.insert_text(fitz.Point(295, curr_y + 36), "ĐỀ THI CHÍNH THỨC", fontsize=12, fontname="f0", fontfile=VN_FONT_PATH)
        page.insert_text(fitz.Point(295, curr_y + 52), f"Mã đề: {metadata.get('exam_code', 'HH-101')} • {metadata.get('length_tier', 'Tiêu chuẩn')}", fontsize=9, fontname="f0", fontfile=VN_FONT_PATH)

        curr_y += 80

        # Lưu ý
        page.insert_text(fitz.Point(margin, curr_y), "📌 Lưu ý: Thí sinh làm bài trực tiếp vào đề hoặc giấy thi. Không sử dụng tài liệu ngoài quy định.", fontsize=8.5, fontname="f0", fontfile=VN_FONT_PATH)
        curr_y += 15
        page.draw_line(fitz.Point(margin, curr_y), fitz.Point(page_width - margin, curr_y), color=(0.7, 0.7, 0.7), width=0.8)
        curr_y += 20

        diag_idx = 0
        for block in content_blocks:
            # Kiểm tra tràn trang -> Tự động ngắt trang
            if curr_y > page_height - 90:
                page = doc.new_page(width=page_width, height=page_height)
                curr_y = margin

            b_type = block.get("type", "question")
            if b_type == "section_header":
                curr_y += 8
                page.insert_text(fitz.Point(margin, curr_y), block.get("title", ""), fontsize=11.5, fontname="f0", fontfile=VN_FONT_PATH)
                curr_y += 18
            else:
                q_num = block.get("number", "")
                q_text = block.get("text", "")
                q_pts = block.get("points", "")
                options = block.get("options", [])

                # Làm sạch nếu AI vô tình ghi các lựa chọn A, B, C, D vào trong text
                if options:
                    m_opt = re.search(r'(?:\n\s*|\s{2,})[A-D]\.\s+', q_text)
                    if m_opt and len(q_text[m_opt.start():]) < len(q_text) * 0.8:
                        q_text = q_text[:m_opt.start()].strip()

                header_str = f"Câu {q_num}: "
                if q_pts:
                    header_str += f"({q_pts}) "

                # Vẽ nội dung câu hỏi (tự động chia dòng và sang trang)
                lines = cls._wrap_text_lines(header_str + q_text, max_width_pts=page_width - 2 * margin, fontsize=10)
                for line in lines:
                    if curr_y > page_height - 60:
                        page = doc.new_page(width=page_width, height=page_height)
                        curr_y = margin
                    page.insert_text(fitz.Point(margin, curr_y), line, fontsize=10, fontname="f0", fontfile=VN_FONT_PATH)
                    curr_y += 14
                curr_y += 4

                # Options trắc nghiệm
                for opt in block.get("options", []):
                    if curr_y > page_height - 60:
                        page = doc.new_page(width=page_width, height=page_height)
                        curr_y = margin
                    page.insert_text(fitz.Point(margin + 18, curr_y), opt, fontsize=9.5, fontname="f0", fontfile=VN_FONT_PATH)
                    curr_y += 16

                # Sub items tự luận
                for sub in block.get("sub_items", []):
                    if curr_y > page_height - 60:
                        page = doc.new_page(width=page_width, height=page_height)
                        curr_y = margin
                    sub_str = f"{sub.get('label', '')}. {sub.get('text', '')}"
                    page.insert_text(fitz.Point(margin + 14, curr_y), sub_str, fontsize=9.5, fontname="f0", fontfile=VN_FONT_PATH)
                    curr_y += 16

                # Chèn sơ đồ minh họa nếu có
                if diagram_paths and diag_idx < len(diagram_paths) and block.get("has_diagram"):
                    d_path = diagram_paths[diag_idx]
                    diag_idx += 1
                    if os.path.exists(d_path):
                        if curr_y > page_height - 180:
                            page = doc.new_page(width=page_width, height=page_height)
                            curr_y = margin
                        img_rect = fitz.Rect(margin + 40, curr_y, margin + 40 + 320, curr_y + 160)
                        page.insert_image(img_rect, filename=d_path)
                        curr_y += 175

                curr_y += 10

        # Footer đánh số trang
        total_pages = len(doc)
        for pno in range(total_pages):
            p = doc[pno]
            footer_str = f"HyperHub AI Generator • Trang {pno + 1}/{total_pages} • Mã đề: {metadata.get('exam_code', 'HH-101')}"
            p.insert_text(fitz.Point(margin, page_height - 25), footer_str, fontsize=8, fontname="f0", fontfile=VN_FONT_PATH)
            _inject_invisible_watermark_pdf(p, fitz.Point(margin, page_height - 12), fontname="f0")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        cls._verify_file_size(output_path)
        return output_path

    # =========================================================================
    # 4. TẠO FILE PDF VECTOR: [Huong_Dan_Giai].pdf
    # =========================================================================
    @classmethod
    def generate_solutions_pdf(
        cls,
        metadata: dict[str, Any],
        solution_blocks: list[dict[str, Any]],
        output_path: str,
        radar_chart_path: Optional[str] = None,
        audio_script: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Tạo file Hướng Dẫn Giải PDF chuẩn sắc nét vector (< 5MB)."""
        doc = fitz.open()
        page_width, page_height = 595, 842
        margin = 45

        page = doc.new_page(width=page_width, height=page_height)
        curr_y = margin

        # Header
        page.draw_rect(fitz.Rect(margin, curr_y, page_width - margin, curr_y + 55), color=(0.1, 0.5, 0.3), fill=(0.96, 0.98, 0.96), width=1.2)
        page.insert_text(fitz.Point(margin + 15, curr_y + 20), "HỆ THỐNG GIÁO DỤC TRỰC TUYẾN HYPERHUB", fontsize=9.5, fontname="f0", fontfile=VN_FONT_PATH)
        page.insert_text(fitz.Point(margin + 15, curr_y + 36), "HƯỚNG DẪN GIẢI CHI TIẾT & BIỂU ĐIỂM CHẤM", fontsize=12, fontname="f0", fontfile=VN_FONT_PATH)
        page.insert_text(fitz.Point(margin + 15, curr_y + 48), f"Môn: {metadata.get('subject', 'TỔNG HỢP').upper()} • Mã đề: {metadata.get('exam_code', 'HH-101')}", fontsize=8.5, fontname="f0", fontfile=VN_FONT_PATH)

        curr_y += 75

        # Bảng đáp án trắc nghiệm nhanh
        quick_answers = [b for b in solution_blocks if b.get("is_multiple_choice")]
        if quick_answers:
            page.insert_text(fitz.Point(margin, curr_y), "I. BẢNG ĐÁP ÁN TRẮC NGHIỆM NHANH", fontsize=11, fontname="f0", fontfile=VN_FONT_PATH)
            curr_y += 16
            ans_str = "  |  ".join([f"Câu {q.get('number', i+1)}: {q.get('correct_key', 'A')}" for i, q in enumerate(quick_answers[:10])])
            page.draw_rect(fitz.Rect(margin, curr_y - 10, page_width - margin, curr_y + 14), fill=(0.95, 0.96, 0.98), width=0.5)
            page.insert_text(fitz.Point(margin + 8, curr_y + 4), ans_str, fontsize=9, fontname="f0", fontfile=VN_FONT_PATH)
            curr_y += 32

        # Kịch bản bài nghe nếu có
        l_script = audio_script or metadata.get("listening_script") or []
        if l_script:
            if curr_y > page_height - 120:
                page = doc.new_page(width=page_width, height=page_height)
                curr_y = margin
            page.insert_text(fitz.Point(margin, curr_y), "🎧 KỊCH BẢN BÀI NGHE (LISTENING AUDIO TRANSCRIPT)", fontsize=11, fontname="f0", fontfile=VN_FONT_PATH)
            curr_y += 16
            for turn in l_script:
                spk = turn.get("speaker", "Speaker")
                txt = turn.get("text", "")
                t_lines = cls._wrap_text_lines(f"[{spk}]: {txt}", max_width_pts=page_width - 2 * margin - 16, fontsize=8.5)
                for tl in t_lines:
                    if curr_y > page_height - 40:
                        page = doc.new_page(width=page_width, height=page_height)
                        curr_y = margin
                    page.insert_text(fitz.Point(margin + 10, curr_y), tl, fontsize=8.5, fontname="f0", fontfile=VN_FONT_PATH)
                    curr_y += 12
                curr_y += 3
            curr_y += 10

        # Lời giải chi tiết
        page.insert_text(fitz.Point(margin, curr_y), "II. HƯỚNG DẪN GIẢI CHI TIẾT & RUBRIC THANG ĐIỂM", fontsize=11, fontname="f0", fontfile=VN_FONT_PATH)
        curr_y += 18

        for sol in solution_blocks:
            if curr_y > page_height - 110:
                page = doc.new_page(width=page_width, height=page_height)
                curr_y = margin

            q_num = sol.get("number", "")
            ans_key = sol.get("correct_key", "")
            exp_text = sol.get("explanation", "")

            title_str = f"Câu {q_num}: "
            if ans_key:
                title_str += f"Đáp án đúng: {ans_key}"
            page.insert_text(fitz.Point(margin, curr_y), title_str, fontsize=10, fontname="f0", fontfile=VN_FONT_PATH)
            curr_y += 14

            # Hộp giải thích (tự co giãn chiều cao theo độ dài văn bản)
            exp_lines = cls._wrap_text_lines(f"💡 Hướng dẫn giải: {exp_text}", max_width_pts=page_width - 2 * margin - 24, fontsize=9)
            box_height = max(38, len(exp_lines) * 13 + 14)
            if curr_y + box_height > page_height - 60:
                page = doc.new_page(width=page_width, height=page_height)
                curr_y = margin
            box_rect = fitz.Rect(margin + 8, curr_y, page_width - margin, curr_y + box_height)
            page.draw_rect(box_rect, fill=(0.98, 0.98, 0.99), color=(0.85, 0.88, 0.92), width=0.6)
            y_text = curr_y + 12
            for el in exp_lines:
                page.insert_text(fitz.Point(margin + 16, y_text), el, fontsize=9, fontname="f0", fontfile=VN_FONT_PATH)
                y_text += 13
            curr_y += box_height + 8

            # Rubric điểm
            rubric = sol.get("rubric", [])
            if rubric:
                for step_txt, pts in rubric:
                    if curr_y > page_height - 40:
                        page = doc.new_page(width=page_width, height=page_height)
                        curr_y = margin
                    page.insert_text(fitz.Point(margin + 20, curr_y), f"• {step_txt}  (+{pts} điểm)", fontsize=8.5, fontname="f0", fontfile=VN_FONT_PATH)
                    curr_y += 14
            curr_y += 8

        # Thêm trang Báo cáo Ma trận Bloom & Phổ điểm nếu có
        actual_radar = radar_chart_path or metadata.get("radar_chart_path")
        if actual_radar and os.path.exists(actual_radar):
            page_rep = doc.new_page(width=page_width, height=page_height)
            page_rep.draw_rect(fitz.Rect(margin, margin, page_width - margin, margin + 45), fill=(0.95, 0.97, 1.0), color=(0.2, 0.4, 0.8), width=1.0)
            page_rep.insert_text(fitz.Point(margin + 15, margin + 28), "BÁO CÁO ĐÁNH GIÁ MA TRẬN KHẢO THÍ & PHỔ ĐIỂM SƯ PHẠM", fontsize=11, fontname="f0", fontfile=VN_FONT_PATH)
            # Chèn ảnh radar
            img_rect = fitz.Rect(margin + 40, margin + 60, page_width - margin - 40, margin + 60 + 340)
            page_rep.insert_image(img_rect, filename=actual_radar)

            pe_info = metadata.get("pedagogy_evaluation") or {}
            page_rep.insert_text(fitz.Point(margin + 20, margin + 430), f"• Độ khó ước lượng (P-value): {pe_info.get('p_value', 0.62)} ({pe_info.get('difficulty_label', 'Vừa sức')})", fontsize=9.5, fontname="f0", fontfile=VN_FONT_PATH)
            page_rep.insert_text(fitz.Point(margin + 20, margin + 450), f"• Chỉ số phân cách (D-value): {pe_info.get('d_value', 0.42)} ({pe_info.get('discrimination_label', 'Tốt')})", fontsize=9.5, fontname="f0", fontfile=VN_FONT_PATH)
            page_rep.insert_text(fitz.Point(margin + 20, margin + 470), "• Đánh giá chung: Ma trận câu hỏi phân bố cân đối theo khung nhận thức Bloom chuẩn Bộ GD&ĐT.", fontsize=9, fontname="f0", fontfile=VN_FONT_PATH)

        total_pages = len(doc)
        for pno in range(total_pages):
            p = doc[pno]
            footer_str = f"HyperHub AI Generator • Lời giải • Trang {pno + 1}/{total_pages}"
            p.insert_text(fitz.Point(margin, page_height - 25), footer_str, fontsize=8, fontname="f0", fontfile=VN_FONT_PATH)
            _inject_invisible_watermark_pdf(p, fitz.Point(margin, page_height - 12), fontname="f0")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        cls._verify_file_size(output_path)
        return output_path

    # =========================================================================
    # 5. ĐIỀU PHỐI XUẤT BẢN THEO LỰA CHỌN (PDF / WORD / CẢ HAI)
    # =========================================================================
    @classmethod
    def export_all(
        cls,
        metadata: dict[str, Any],
        exam_data: dict[str, Any],
        output_format: str,
        output_dir: str,
        diagram_paths: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Xuất cả 2 bộ tài liệu [De_Thi] và [Huong_Dan_Giai] theo định dạng yêu cầu."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        job_id = metadata.get("job_id", "HH-001")
        clean_subject = "".join(c for c in metadata.get("subject", "De_Thi") if c.isalnum() or c in "_-")

        content_blocks = exam_data.get("questions", [])
        solution_blocks = exam_data.get("solutions", [])
        radar_p = metadata.get("radar_chart_path")
        l_script = metadata.get("listening_script") or exam_data.get("listening_script")

        result_files: dict[str, list[str]] = {
            "exam_files": [],
            "solution_files": [],
        }

        fmt = output_format.lower()

        # 1. Word (.docx)
        if fmt in ("word", "both", "all", "docx"):
            exam_docx = os.path.join(output_dir, f"[De_Thi]_{clean_subject}_{job_id}.docx")
            cls.generate_exam_docx(metadata, content_blocks, exam_docx, diagram_paths)
            result_files["exam_files"].append(exam_docx)

            sol_docx = os.path.join(output_dir, f"[Huong_Dan_Giai]_{clean_subject}_{job_id}.docx")
            cls.generate_solutions_docx(metadata, solution_blocks, sol_docx, radar_chart_path=radar_p, audio_script=l_script)
            result_files["solution_files"].append(sol_docx)

        # 2. PDF (.pdf)
        if fmt in ("pdf", "both", "all"):
            exam_pdf = os.path.join(output_dir, f"[De_Thi]_{clean_subject}_{job_id}.pdf")
            cls.generate_exam_pdf(metadata, content_blocks, exam_pdf, diagram_paths)
            result_files["exam_files"].append(exam_pdf)

            sol_pdf = os.path.join(output_dir, f"[Huong_Dan_Giai]_{clean_subject}_{job_id}.pdf")
            cls.generate_solutions_pdf(metadata, solution_blocks, sol_pdf, radar_chart_path=radar_p, audio_script=l_script)
            result_files["solution_files"].append(sol_pdf)

        # 3. Azota CSV (.csv)
        if fmt in ("azota", "csv", "all"):
            azota_file = os.path.join(output_dir, f"[Azota]_{clean_subject}_{job_id}.csv")
            try:
                from not_finished.exam_generator.services.export_formats import export_formats_service
            except ImportError:
                from services.export_formats import export_formats_service
            export_formats_service.export_azota_csv(metadata, content_blocks, solution_blocks, azota_file)
            result_files.setdefault("azota_files", []).append(azota_file)

        # 4. Quizizz CSV (.csv)
        if fmt in ("quizizz", "all"):
            quizizz_file = os.path.join(output_dir, f"[Quizizz]_{clean_subject}_{job_id}.csv")
            try:
                from not_finished.exam_generator.services.export_formats import export_formats_service
            except ImportError:
                from services.export_formats import export_formats_service
            export_formats_service.export_quizizz_csv(metadata, content_blocks, solution_blocks, quizizz_file)
            result_files.setdefault("quizizz_files", []).append(quizizz_file)

        # 5. Anki Flashcards (.txt)
        if fmt in ("anki", "flashcard", "all"):
            anki_file = os.path.join(output_dir, f"[Anki]_{clean_subject}_{job_id}.txt")
            try:
                from not_finished.exam_generator.services.export_formats import export_formats_service
            except ImportError:
                from services.export_formats import export_formats_service
            export_formats_service.export_anki_deck(metadata, content_blocks, solution_blocks, anki_file)
            result_files.setdefault("anki_files", []).append(anki_file)

        # 6. LaTeX Source (.tex)
        if fmt in ("latex", "tex", "all"):
            latex_file = os.path.join(output_dir, f"[LaTeX]_{clean_subject}_{job_id}.tex")
            try:
                from not_finished.exam_generator.services.export_formats import export_formats_service
            except ImportError:
                from services.export_formats import export_formats_service
            export_formats_service.export_latex_tex(metadata, content_blocks, solution_blocks, latex_file)
            result_files.setdefault("latex_files", []).append(latex_file)

        return result_files

    @staticmethod
    def _verify_file_size(file_path: str) -> None:
        """Kiểm tra và đảm bảo kích thước file nghiêm ngặt < 5MB."""
        if os.path.exists(file_path):
            size = os.path.getsize(file_path)
            if size > MAX_FILE_BYTES:
                logger.warning(
                    f"⚠️ Tệp {file_path} vượt quá giới hạn 5MB ({size / 1024 / 1024:.2f} MB)!"
                )
            else:
                logger.info(
                    f"✅ Đã tạo tệp {os.path.basename(file_path)}: {size / 1024:.1f} KB (< 5MB)"
                )


document_exporter = DocumentExporter()
