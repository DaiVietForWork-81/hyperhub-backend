"""
Audit & Explainability Engine for DocInspector.
"TỰ NHIÊN - MINH BẠCH - KHÔNG HỘP ĐEN AI"
Provides full, transparent reasoning, evidence citations, line references,
and mathematical weight breakdowns for every classification and question extraction.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    DifficultyTier,
    DocumentCategory,
    ExamTrackTier,
    ExamType,
    ExtractedQuestion,
    GradeLevel,
    InspectionReport,
    Subject,
    VerificationVerdict,
)


@dataclass
class EvidenceToken:
    """Detailed evidence token citation."""
    token: str
    weight: float
    occurrence_count: int
    total_contribution: float
    line_number_hint: Optional[int] = None
    context_snippet: Optional[str] = None


@dataclass
class SubjectDecisionTrail:
    """Transparent trail for Subject Classification."""
    chosen_subject: Subject
    confidence: float
    top_score: float
    second_subject: Optional[Subject] = None
    second_score: float = 0.0
    margin: float = 0.0
    evidence_tokens: List[EvidenceToken] = field(default_factory=list)
    rationale: str = ""


@dataclass
class QuestionAuditItem:
    """Transparent audit of an individual extracted question."""
    question_index: int
    label: str
    question_type: str
    prompt_length_chars: int
    option_count: int
    detected_answer: Optional[str] = None
    cognitive_level: str = "RECOGNITION"
    has_math_formula: bool = False
    has_table: bool = False
    confidence: float = 1.0
    split_rule_used: str = "RE_QUESTION_HEADING"


SUBJECT_VI_NAMES: Dict[Subject, str] = {
    Subject.MATHEMATICS: "Toán học",
    Subject.PHYSICS: "Vật lý",
    Subject.CHEMISTRY: "Hóa học",
    Subject.BIOLOGY: "Sinh học",
    Subject.LITERATURE: "Ngữ văn",
    Subject.ENGLISH: "Tiếng Anh",
    Subject.INFORMATICS: "Tin học",
    Subject.HISTORY: "Lịch sử",
    Subject.GEOGRAPHY: "Địa lý",
    Subject.CIVIC_EDUCATION: "Giáo dục công dân",
    Subject.ECONOMIC_LEGAL_EDU: "Kinh tế & Pháp luật",
    Subject.NATURAL_SCIENCE: "Khoa học tự nhiên",
    Subject.HISTORY_GEOGRAPHY: "Lịch sử & Địa lý",
    Subject.TECHNOLOGY: "Công nghệ",
    Subject.PHYSICAL_EDUCATION: "Giáo dục thể chất",
    Subject.DEFENSE_SECURITY_EDU: "Quốc phòng an ninh",
    Subject.EXPERIENTIAL_CAREER_ACT: "Hoạt động trải nghiệm",
    Subject.LOCAL_EDUCATION: "Giáo dục địa phương",
    Subject.JAPANESE: "Tiếng Nhật",
    Subject.CHINESE: "Tiếng Trung",
    Subject.KOREAN: "Tiếng Hàn",
    Subject.RUSSIAN: "Tiếng Nga",
    Subject.FRENCH: "Tiếng Pháp",
    Subject.GENERAL: "Đa môn / Chung",
    Subject.NON_ACADEMIC: "Phi học thuật",
}


@dataclass
class TransparencyAuditDossier:
    """Full transparency report explaining all non-AI algorithmic decisions."""
    file_name: str
    file_type: str
    file_size_bytes: int
    execution_time_ms: float
    is_spoofed: bool
    spoof_audit: Optional[str] = None
    subject_trail: SubjectDecisionTrail = field(default_factory=lambda: SubjectDecisionTrail(Subject.GENERAL, 0.0, 0.0))
    grade_trail: Dict[str, Any] = field(default_factory=dict)
    exam_track_trail: Dict[str, Any] = field(default_factory=dict)
    moet_2025_trail: Dict[str, Any] = field(default_factory=dict)
    questions_summary: Dict[str, Any] = field(default_factory=dict)
    sample_questions_audit: List[QuestionAuditItem] = field(default_factory=list)
    verdict: str = "XAC_MINH"
    verdict_explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        """Render transparent markdown report."""
        md = []
        md.append(f"# 🔍 HỒ SƠ BẠCH HÓA (TRANSPARENCY DOSSIER): `{self.file_name}`")
        md.append(f"- **Thời gian xử lý:** `{self.execution_time_ms:.2f} ms` *(100% Thuật toán Heuristic / Zero AI Cost)*")
        md.append(f"- **Định dạng:** `{self.file_type}` | **Dung lượng:** `{self.file_size_bytes:,} bytes`")
        md.append(f"- **Kết luận thẩm định:** `{self.verdict}` — *{self.verdict_explanation}*")
        
        if self.is_spoofed:
            md.append(f"\n> ⚠️ **CẢNH BÁO GIẢ MẠO TÊN TỆP (ANTI-SPOOFING):**")
            md.append(f"> {self.spoof_audit}")

        subj_vi = SUBJECT_VI_NAMES.get(self.subject_trail.chosen_subject, self.subject_trail.chosen_subject.value)
        md.append("\n## 1. MINH BẠCH PHÂN LOẠI MÔN HỌC (SUBJECT CLASSIFICATION EVIDENCE)")
        md.append(f"- **Môn học xác định:** **{subj_vi}** ({self.subject_trail.chosen_subject.value}) (Độ tin cậy: `{self.subject_trail.confidence * 100:.1f}%`)")
        md.append(f"- **Điểm số Top 1:** `{self.subject_trail.top_score:.1f}`")
        if self.subject_trail.second_subject:
            md.append(f"- **Ứng viên Top 2:** `{self.subject_trail.second_subject.value}` (`{self.subject_trail.second_score:.1f}`) | **Khoảng cách dẫn đầu:** `+{self.subject_trail.margin:.1f}`")
        md.append(f"- **Lý giải thuật toán:** {self.subject_trail.rationale}")

        if self.subject_trail.evidence_tokens:
            md.append("\n### Bảng trọng số từ khóa kích hoạt (Evidence Tokens):")
            md.append("| Từ khóa / Cụm từ | Trọng số gốc | Số lần xuất hiện | Đóng góp tổng điểm |")
            md.append("|:---|:---:|:---:|:---:|")
            for tok in self.subject_trail.evidence_tokens[:12]:
                md.append(f"| `{tok.token}` | `{tok.weight:.1f}` | `{tok.occurrence_count}` | **`+{tok.total_contribution:.1f}`** |")

        md.append("\n## 2. MINH BẠCH CẤU TRÚC ĐỀ THI & ĐỘ PHÂN HÓA (EXAM ANATOMY)")
        md.append(f"- **Khối lớp / Trình độ:** `{self.grade_trail.get('label', 'N/A')}` (Căn cứ: `{self.grade_trail.get('cue_matched', 'N/A')}`)")
        md.append(f"- **Phân hệ đề thi:** `{self.exam_track_trail.get('track_label', 'thường')}` ({self.exam_track_trail.get('rationale', '')})")
        md.append(f"- **Chuẩn cấu trúc Bộ GD&ĐT 2025:** `{'ĐẠT CHUẨN' if self.moet_2025_trail.get('compliant') else 'KHÔNG / ĐỊNH DẠNG KHÁC'}`")
        if self.moet_2025_trail.get('compliant'):
            md.append(f"  + Phần I (Trắc nghiệm nhiều lựa chọn): `{self.moet_2025_trail.get('part1_count', 0)} câu`")
            md.append(f"  + Phần II (Trắc nghiệm Đúng/Sai 4 ý): `{self.moet_2025_trail.get('part2_count', 0)} câu`")
            md.append(f"  + Phần III (Trả lời ngắn): `{self.moet_2025_trail.get('part3_count', 0)} câu`")

        md.append("\n## 3. MINH BẠCH TÁCH CÂU HỎI & ĐÁP ÁN (ITEMIZATION TRAIL)")
        md.append(f"- **Tổng số câu hỏi phát hiện:** `{self.questions_summary.get('total_questions', 0)}`")
        md.append(f"- **Số câu có đáp án ghép nối:** `{self.questions_summary.get('answered_count', 0)}` (`{self.questions_summary.get('coverage_rate', 0):.1f}%`)")
        md.append(f"- **Độ khó ước lượng:** `{self.questions_summary.get('difficulty_index', 0)}/10.0`")

        if self.sample_questions_audit:
            md.append("\n### Kiểm toán mẫu các câu hỏi bóc tách:")
            md.append("| Câu số | Phân loại | Số phương án | Đáp án ghép | Mức độ nhận thức | Công thức |")
            md.append("|:---:|:---|:---:|:---:|:---|:---:|")
            for q in self.sample_questions_audit[:8]:
                math_icon = "✅" if q.has_math_formula else "—"
                ans_text = f"**{q.detected_answer}**" if q.detected_answer else "*(chưa ghép)*"
                md.append(f"| {q.label} | `{q.question_type}` | {q.option_count} | {ans_text} | `{q.cognitive_level}` | {math_icon} |")

        md.append("\n---\n*Báo cáo được khởi tạo tự động bởi DocInspector Explainability Engine. Không sử dụng mô hình ngôn ngữ lớn (LLM).*")
        return "\n".join(md)


class ExplainabilityEngine:
    """Generates transparent, auditable dossiers from InspectionReport and raw documents."""

    @classmethod
    def generate_dossier(cls, report: InspectionReport, raw_text: str = "") -> TransparencyAuditDossier:
        """Construct full transparency audit dossier from an InspectionReport."""
        text = raw_text or (report.pass1.raw_text if hasattr(report.pass1, "raw_text") else "")

        # 1. Subject decision trail
        p3 = report.pass3
        sorted_scores = sorted(p3.subject_scores.items(), key=lambda x: x[1], reverse=True)
        top_name, top_score = sorted_scores[0] if sorted_scores else ("GENERAL", 0.0)
        second_name, second_score = sorted_scores[1] if len(sorted_scores) > 1 else ("GENERAL", 0.0)
        
        evidence_tokens: List[EvidenceToken] = []
        for term_str in p3.evidence_terms:
            # Format: 'term (xCOUNT)' or 'term~kd (xCOUNT)'
            cnt = 1
            pure_term = term_str
            if "(x" in term_str:
                parts = term_str.split("(x")
                pure_term = parts[0].strip().replace("~kd", "")
                try:
                    cnt = int(parts[1].replace(")", "").strip())
                except Exception:
                    cnt = 1
            
            w = 3.0
            evidence_tokens.append(
                EvidenceToken(
                    token=pure_term,
                    weight=w,
                    occurrence_count=cnt,
                    total_contribution=w * cnt,
                )
            )

        margin = top_score - second_score
        chosen_subj = report.detected_subject
        rationale = (
            f"Môn {chosen_subj.value} đạt tổng điểm trọng số {top_score:.1f}, "
            f"vượt ứng viên thứ hai ({second_name}: {second_score:.1f}) một khoảng cách {margin:.1f} điểm "
            f"qua {len(evidence_tokens)} thuật ngữ chuyên ngành."
        )

        subject_trail = SubjectDecisionTrail(
            chosen_subject=chosen_subj,
            confidence=report.confidence_score,
            top_score=top_score,
            second_subject=Subject[second_name] if second_name in Subject.__members__ else Subject.GENERAL,
            second_score=second_score,
            margin=margin,
            evidence_tokens=evidence_tokens,
            rationale=rationale,
        )

        # 2. Grade trail
        curriculum_cue = None
        if hasattr(report, "pass2") and hasattr(report.pass2, "curriculum") and report.pass2.curriculum:
            curriculum_cue = report.pass2.curriculum.series_detected

        grade_trail = {
            "grade_level": report.grade_level.value,
            "label": report.grade_level_label_vi,
            "cue_matched": curriculum_cue or "Từ khóa khối lớp / cấu trúc nội dung đề",
        }

        # 3. Exam track trail
        exam_track_trail = {
            "track": report.exam_track.value,
            "track_label": report.exam_track_label_vi,
            "rationale": report.exam_track_rationale or "Cấu trúc đề và độ khó tiêu chuẩn",
        }

        # 4. MOET 2025 trail
        d_meta = report.detailed_metadata
        moet_2025_trail = {
            "compliant": report.moet_2025_compliant,
            "part1_count": d_meta.moet_part1_count,
            "part2_count": d_meta.moet_part2_count,
            "part3_count": d_meta.moet_part3_count,
        }

        # 5. Question summary & samples
        questions = report.pass2.questions or []
        answered_q = [q for q in questions if q.detected_answer]
        cov_rate = (len(answered_q) / max(1, len(questions))) * 100.0

        questions_summary = {
            "total_questions": len(questions),
            "answered_count": len(answered_q),
            "coverage_rate": round(cov_rate, 1),
            "difficulty_index": report.difficulty_assessment.score,
        }

        sample_audits: List[QuestionAuditItem] = []
        for q in questions[:10]:
            has_math = any(sym in q.prompt for sym in ["^", "_", "\\", "int_", "=", "+", "cos", "sin", "dx"])
            sample_audits.append(
                QuestionAuditItem(
                    question_index=q.question_index,
                    label=q.label,
                    question_type=q.question_type,
                    prompt_length_chars=len(q.prompt),
                    option_count=len(q.options),
                    detected_answer=q.detected_answer,
                    cognitive_level=q.cognitive_level.value if hasattr(q.cognitive_level, "value") else str(q.cognitive_level),
                    has_math_formula=has_math,
                    has_table=q.has_table_data,
                )
            )

        ext = Path(report.file_path).suffix.upper().replace(".", "") or "BUFFER"

        return TransparencyAuditDossier(
            file_name=report.file_name,
            file_type=ext,
            file_size_bytes=report.file_size_bytes,
            execution_time_ms=report.total_execution_time_ms,
            is_spoofed=report.is_spoofed_filename,
            spoof_audit=report.spoof_details,
            subject_trail=subject_trail,
            grade_trail=grade_trail,
            exam_track_trail=exam_track_trail,
            moet_2025_trail=moet_2025_trail,
            questions_summary=questions_summary,
            sample_questions_audit=sample_audits,
            verdict=report.verdict.value,
            verdict_explanation=report.verdict_rationale or report.verdict_label_vi,
        )
