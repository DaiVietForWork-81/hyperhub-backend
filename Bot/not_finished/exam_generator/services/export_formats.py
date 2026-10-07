"""Dịch vụ Xuất Bản Đa Định Dạng: Azota CSV, Quizizz, Anki Flashcards & LaTeX Source (Export Formats Engine).

Cung cấp các định dạng xuất khẩu chuyên nghiệp cho giáo viên và học sinh:
1. Azota CSV (`[Azota]_<Mon>_<JobId>.csv`): Tương thích 100% với hệ thống thi online Azota Việt Nam.
2. Quizizz CSV (`[Quizizz]_<Mon>_<JobId>.csv`): Nạp trực tiếp tạo game trắc nghiệm lớp học.
3. Anki Flashcards (`[Anki]_<Mon>_<JobId>.txt`): Bộ thẻ ghi nhớ TSV nạp thẳng vào phần mềm Anki.
4. LaTeX Source (`[LaTeX]_<Mon>_<JobId>.tex`): Mã nguồn LaTeX gói tiếng Việt chuẩn Overleaf.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger("ExportFormats")


class ExportFormatsService:
    """Bộ chuyển đổi và xuất bản đa định dạng cho bộ đề thi AI."""

    @staticmethod
    def _clean_option_text(opt: str) -> str:
        """Tách nhãn A, B, C, D khỏi nội dung phương án."""
        m = re.match(r"^[A-Da-d][\.\:\)\-]\s*(.*)$", opt.strip())
        return m.group(1).strip() if m else opt.strip()

    # =========================================================================
    # 1. AZOTA CSV EXPORTER
    # =========================================================================
    @classmethod
    def export_azota_csv(
        cls,
        metadata: dict[str, Any],
        content_blocks: list[dict[str, Any]],
        solution_blocks: list[dict[str, Any]],
        output_path: str,
    ) -> str:
        """Xuất file CSV chuẩn Azota (UTF-8-SIG chống lỗi font tiếng Việt trong Excel)."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sol_map = {str(s.get("number")): s for s in solution_blocks}

        headers = ["Câu", "Nội dung", "Phương án A", "Phương án B", "Phương án C", "Phương án D", "Đáp án đúng", "Giải thích"]

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for q in content_blocks:
                if q.get("type") != "question":
                    continue
                q_num = str(q.get("number", ""))
                sol = sol_map.get(q_num, {})
                options = q.get("options", [])

                opt_a = cls._clean_option_text(options[0]) if len(options) > 0 else ""
                opt_b = cls._clean_option_text(options[1]) if len(options) > 1 else ""
                opt_c = cls._clean_option_text(options[2]) if len(options) > 2 else ""
                opt_d = cls._clean_option_text(options[3]) if len(options) > 3 else ""

                correct_key = str(sol.get("correct_key", "")).strip().upper()
                explanation = str(sol.get("explanation", ""))
                if sol.get("common_mistakes"):
                    explanation += f" [Lưu ý bẫy tư duy: {sol.get('common_mistakes')}]"

                writer.writerow([
                    f"Câu {q_num}",
                    q.get("text", ""),
                    opt_a,
                    opt_b,
                    opt_c,
                    opt_d,
                    correct_key,
                    explanation,
                ])

        logger.info(f"📄 Đã xuất file Azota CSV tại: {output_path}")
        return output_path

    # =========================================================================
    # 2. QUIZIZZ CSV EXPORTER
    # =========================================================================
    @classmethod
    def export_quizizz_csv(
        cls,
        metadata: dict[str, Any],
        content_blocks: list[dict[str, Any]],
        solution_blocks: list[dict[str, Any]],
        output_path: str,
        default_time_seconds: int = 60,
    ) -> str:
        """Xuất file CSV chuẩn cấu trúc nạp Quizizz."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sol_map = {str(s.get("number")): s for s in solution_blocks}

        headers = [
            "Question Text", "Question Type",
            "Option 1", "Option 2", "Option 3", "Option 4",
            "Correct Answer", "Time in seconds",
        ]

        key_to_index = {"A": 1, "B": 2, "C": 3, "D": 4}

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for q in content_blocks:
                if q.get("type") != "question":
                    continue
                q_num = str(q.get("number", ""))
                sol = sol_map.get(q_num, {})
                options = q.get("options", [])
                if not options:
                    continue

                opt_1 = cls._clean_option_text(options[0]) if len(options) > 0 else ""
                opt_2 = cls._clean_option_text(options[1]) if len(options) > 1 else ""
                opt_3 = cls._clean_option_text(options[2]) if len(options) > 2 else ""
                opt_4 = cls._clean_option_text(options[3]) if len(options) > 3 else ""

                raw_key = str(sol.get("correct_key", "A")).strip().upper()
                correct_idx = key_to_index.get(raw_key, 1)

                writer.writerow([
                    q.get("text", ""),
                    "Multiple Choice",
                    opt_1,
                    opt_2,
                    opt_3,
                    opt_4,
                    correct_idx,
                    default_time_seconds,
                ])

        logger.info(f"🎮 Đã xuất file Quizizz CSV tại: {output_path}")
        return output_path

    # =========================================================================
    # 3. ANKI FLASHCARDS EXPORTER (TSV)
    # =========================================================================
    @classmethod
    def export_anki_deck(
        cls,
        metadata: dict[str, Any],
        content_blocks: list[dict[str, Any]],
        solution_blocks: list[dict[str, Any]],
        output_path: str,
    ) -> str:
        """Xuất bộ thẻ ghi nhớ Anki (TSV UTF-8 hỗ trợ HTML)."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sol_map = {str(s.get("number")): s for s in solution_blocks}

        subject = metadata.get("subject", "General")
        exam_code = metadata.get("exam_code", "HH-101")
        clean_tag = "".join(c for c in subject if c.isalnum() or c == "_")

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            # Header chỉ thị của Anki
            writer.writerow(["#separator:tab"])
            writer.writerow(["#html:true"])
            writer.writerow(["#tags column:3"])

            for q in content_blocks:
                if q.get("type") != "question":
                    continue
                q_num = str(q.get("number", ""))
                sol = sol_map.get(q_num, {})

                # Mặt trước (Front)
                front_parts = [f"<b>Câu {q_num}:</b> {q.get('text', '')}"]
                if q.get("options"):
                    front_parts.append("<br><br><b>Các lựa chọn:</b><br>")
                    for opt in q["options"]:
                        front_parts.append(f"• {opt}<br>")
                front_html = "".join(front_parts)

                # Mặt sau (Back)
                correct_key = sol.get("correct_key", "A")
                back_parts = [f"<b style='color:#2e7d32; font-size:1.2em;'>ĐÁP ÁN ĐÚNG: {correct_key}</b><br><br>"]
                if sol.get("explanation"):
                    back_parts.append(f"<b>Hướng dẫn giải:</b><br>{sol.get('explanation')}<br><br>")
                if sol.get("common_mistakes"):
                    back_parts.append(f"<b style='color:#d32f2f;'>Bẫy thường gặp:</b> {sol.get('common_mistakes')}")
                back_html = "".join(back_parts)

                tag_field = f"HyperHub_AI {clean_tag} {exam_code}"
                writer.writerow([front_html, back_html, tag_field])

        logger.info(f"🃏 Đã xuất bộ thẻ Anki tại: {output_path}")
        return output_path

    # =========================================================================
    # 4. LATEX SOURCE EXPORTER (.TEX)
    # =========================================================================
    @classmethod
    def export_latex_tex(
        cls,
        metadata: dict[str, Any],
        content_blocks: list[dict[str, Any]],
        solution_blocks: list[dict[str, Any]],
        output_path: str,
    ) -> str:
        """Xuất file mã nguồn LaTeX (.tex) chuẩn tiếng Việt gói Overleaf."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sol_map = {str(s.get("number")): s for s in solution_blocks}

        subject = metadata.get("subject", "Toán học")
        exam_title = metadata.get("exam_title", "KỲ THI ĐÁNH GIÁ NĂNG LỰC HYPERHUB")
        exam_code = metadata.get("exam_code", "HH-101")
        duration = metadata.get("duration", "90 phút")

        lines: list[str] = [
            r"\documentclass[12pt,a4paper]{article}",
            r"\usepackage[utf8]{vietnam}",
            r"\usepackage{amsmath,amssymb,amsfonts}",
            r"\usepackage{geometry}",
            r"\usepackage{enumitem}",
            r"\usepackage{xcolor}",
            r"\usepackage{tcolorbox}",
            r"\geometry{top=2cm,bottom=2cm,left=2cm,right=2cm}",
            r"\setlength{\parindent}{0pt}",
            r"\setlength{\parskip}{0.5em}",
            r"\begin{document}",
            "",
            r"% --- TIÊU ĐỀ ĐỀ THI ---",
            r"\begin{center}",
            rf"\textbf{{\large {exam_title.upper()}}}\\[0.3em]",
            rf"\textbf{{\large MÔN THI: {subject.upper()}}}\\[0.3em]",
            rf"\textit{{Thời gian làm bài: {duration} • Mã đề thi: {exam_code}}}",
            r"\end{center}",
            r"\hrule height 1pt",
            r"\vspace{1em}",
            "",
            r"% --- NỘI DUNG ĐỀ THI ---",
            r"\section*{PHẦN ĐỀ BÀI}",
        ]

        for q in content_blocks:
            if q.get("type") == "section_header":
                lines.append(f"\n\\subsection*{{{q.get('title', '')}}}")
                continue
            if q.get("type") != "question":
                continue

            q_num = q.get("number", "1")
            pts = q.get("points", "0.5 điểm")
            text = q.get("text", "")
            lines.append(f"\\textbf{{Câu {q_num}}} ({pts}): {text}")

            if q.get("options"):
                lines.append(r"\begin{enumerate}[label=\textbf{\Alph*.}]")
                for opt in q["options"]:
                    clean_opt = cls._clean_option_text(opt)
                    lines.append(f"  \\item {clean_opt}")
                lines.append(r"\end{enumerate}")
            lines.append(r"\vspace{0.5em}")

        # --- LỜI GIẢI VÀ ĐÁP ÁN ---
        lines.extend([
            "",
            r"\newpage",
            r"\section*{HƯỚNG DẪN GIẢI CHI TIẾT & BIỂU ĐIỂM}",
            r"\hrule height 1pt",
            r"\vspace{1em}",
        ])

        for sol in solution_blocks:
            s_num = sol.get("number", "1")
            is_mc = sol.get("is_multiple_choice", True)
            key = sol.get("correct_key", "")
            expl = sol.get("explanation", "")
            mistake = sol.get("common_mistakes", "")

            lines.append(r"\begin{tcolorbox}[colback=gray!5!white,colframe=blue!75!black,title=\textbf{Câu " + str(s_num) + r"}]")
            if is_mc and key:
                lines.append(f"\\textbf{{Đáp án đúng:}} \\textcolor{{red}}{{\\textbf{{{key}}}}}\\\\[0.5em]")
            lines.append(f"\\textbf{{Lời giải:}} {expl}\\\\[0.5em]")
            if mistake:
                lines.append(f"\\textbf{{Lưu ý bẫy học sinh:}} \\textcolor{{orange}}{{{mistake}}}\\\\[0.5em]")

            rubric = sol.get("rubric", [])
            if rubric:
                lines.append(r"\textbf{Biểu điểm:} \begin{itemize}")
                for item in rubric:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        lines.append(f"  \\item {item[0]}: \\textbf{{{item[1]}đ}}")
                lines.append(r"\end{itemize}")
            lines.append(r"\end{tcolorbox}")
            lines.append(r"\vspace{0.5em}")

        lines.append(r"\end{document}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"📜 Đã xuất file mã nguồn LaTeX tại: {output_path}")
        return output_path


# Singleton instance dùng chung
export_formats_service = ExportFormatsService()
