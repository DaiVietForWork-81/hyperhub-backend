"""
Pedagogical Exam Health and Structural Quality Auditor.
Evaluates question completeness, duplicate options, answer key coverage,
and cognitive balance to assign a 100-point Quality Score and Letter Grade.
100% Deterministic, Zero AI.
"""

from __future__ import annotations

from typing import List

from .models import (
    CognitiveBreakdown,
    DocumentCategory,
    ExamType,
    ExtractedQuestion,
    Pass1Report,
    Pass2Report,
    PedagogicalQualityAudit,
    QualityGrade,
)


class QualityAuditor:
    """Audits pedagogical exam health, question consistency, and layout integrity."""

    @classmethod
    def audit_quality(
        cls,
        category: DocumentCategory,
        exam_type: ExamType,
        pass1: Pass1Report,
        pass2: Pass2Report,
    ) -> PedagogicalQualityAudit:
        """
        Computes the complete quality audit report for the document.
        """
        # If not an exam (e.g. contract or lesson plan), return appropriate baseline audit
        if category != DocumentCategory.EXAM_TEST or pass2.question_count == 0:
            if category == DocumentCategory.LESSON_PLAN:
                is_cv5512 = pass2.curriculum.has_cv_5512_structure
                score = 95.0 if is_cv5512 else 75.0
                grade = QualityGrade.GRADE_A_PLUS if is_cv5512 else QualityGrade.GRADE_B
                return PedagogicalQualityAudit(
                    overall_score=score,
                    grade=grade,
                    question_completeness_rate=1.0,
                    answer_coverage_rate=1.0,
                    duplicate_option_count=0,
                    missing_options_questions=[],
                    formatting_issues=[] if is_cv5512 else ["Chưa tối ưu đủ 4 hoạt động CV 5512"],
                    cognitive_balance_score=90.0,
                    summary_vi="Kế hoạch bài dạy giáo án sư phạm đạt chuẩn." if is_cv5512 else "Giáo án cần bổ sung tiến trình 5512.",
                )
            elif category == DocumentCategory.ADMIN_CONTRACT:
                return PedagogicalQualityAudit(
                    overall_score=90.0,
                    grade=QualityGrade.GRADE_A,
                    question_completeness_rate=1.0,
                    answer_coverage_rate=1.0,
                    duplicate_option_count=0,
                    missing_options_questions=[],
                    formatting_issues=[],
                    cognitive_balance_score=90.0,
                    summary_vi="Văn bản hành chính / Hợp đồng có cấu trúc pháp lý chuẩn mực.",
                )
            else:
                return PedagogicalQualityAudit(
                    overall_score=70.0,
                    grade=QualityGrade.GRADE_B,
                    question_completeness_rate=1.0,
                    answer_coverage_rate=1.0,
                    summary_vi="Tài liệu văn bản tổng quát không chứa cấu trúc đề thi.",
                )

        questions: List[ExtractedQuestion] = pass2.questions
        total_q = max(1, len(questions))

        missing_opts_q: List[int] = []
        dup_opt_count = 0
        answered_q_count = 0
        formatting_issues: List[str] = []

        # 1. Question Completeness & Option Duplication
        complete_mcq_count = 0
        for q in questions:
            if q.detected_answer:
                answered_q_count += 1

            if q.question_type == "MCQ_4":
                # Check option count: standard MCQ must have 4 options A, B, C, D
                if len(q.options) < 4:
                    missing_opts_q.append(q.question_index)
                else:
                    complete_mcq_count += 1

                # Check duplicate options (e.g. A and B having same text)
                vals = [v.strip().lower() for v in q.options.values() if v.strip()]
                if len(vals) != len(set(vals)):
                    dup_opt_count += 1
            else:
                complete_mcq_count += 1

        completeness_rate = complete_mcq_count / total_q
        answer_coverage_rate = answered_q_count / total_q if pass2.has_answer_keys else 0.0

        if missing_opts_q:
            formatting_issues.append(f"Có {len(missing_opts_q)} câu trắc nghiệm thiếu phương án (chưa đủ 4 lựa chọn A-D).")
        if dup_opt_count > 0:
            formatting_issues.append(f"Có {dup_opt_count} câu hỏi bị trùng lặp nội dung giữa các phương án lựa chọn.")
        if not pass2.has_answer_keys:
            formatting_issues.append("Đề thi chưa đính kèm bảng đáp án tra cứu.")

        # 2. Cognitive Balance Health (Golden ratio: 40% Nhận biết, 30% Thông hiểu, 20% Vận dụng, 10% Vận dụng cao)
        cb: CognitiveBreakdown = pass2.cognitive_breakdown
        total_cog = max(1, cb.recognition_count + cb.comprehension_count + cb.application_count + cb.high_application_count)
        
        # Penalize if 100% of questions are in one level
        max_level_ratio = max(cb.recognition_count, cb.comprehension_count, cb.application_count, cb.high_application_count) / total_cog
        if max_level_ratio > 0.85 and total_q > 5:
            cognitive_balance_score = 55.0
            formatting_issues.append("Ma trận đề thi bị lệch nặng về một cấp độ nhận thức duy nhất.")
        elif max_level_ratio > 0.65 and total_q > 5:
            cognitive_balance_score = 75.0
        else:
            cognitive_balance_score = 95.0

        # 3. Overall 100-Point Quality Score Computation
        # 35% Completeness + 30% Answer Key Coverage + 20% Cognitive Balance + 15% Text/Encoding Cleanliness
        cleanliness_score = 100.0
        if pass1.metrics.legacy_encoding_warning:
            cleanliness_score -= 30.0
            formatting_issues.append(pass1.metrics.legacy_encoding_warning)
        if pass1.is_scanned_pdf:
            cleanliness_score -= 40.0
            formatting_issues.append("File scan dạng ảnh chụp, độ rõ nét ký tự thấp.")

        score = (
            (completeness_rate * 35.0)
            + (answer_coverage_rate * 30.0)
            + (cognitive_balance_score * 0.20)
            + (cleanliness_score * 0.15)
        )
        score = round(max(0.0, min(100.0, score)), 1)

        # 4. Quality Grade Assignment
        if score >= 90.0:
            grade = QualityGrade.GRADE_A_PLUS
            summary_vi = "Đề thi xuất sắc (A+): Đầy đủ phương án A-D, đáp án đối chiếu 100%, ma trận phân hóa cân đối."
        elif score >= 80.0:
            grade = QualityGrade.GRADE_A
            summary_vi = "Đề thi chất lượng tốt (A): Cấu trúc câu hỏi rõ ràng, có đáp án và phân hóa hợp lý."
        elif score >= 65.0:
            grade = QualityGrade.GRADE_B
            summary_vi = "Đề thi mức khá (B): Có thể dùng tốt nhưng cần hoàn thiện thêm đáp án hoặc định dạng phương án."
        elif score >= 50.0:
            grade = QualityGrade.GRADE_C
            summary_vi = "Đề thi trung bình (C): Thiếu bảng đáp án hoặc một số câu hỏi chưa đủ 4 phương án."
        else:
            grade = QualityGrade.GRADE_D
            summary_vi = "Đề thi chất lượng kém (D): Lỗi cấu trúc nghiêm trọng, thiếu câu hỏi hoặc định dạng scan mờ."

        return PedagogicalQualityAudit(
            overall_score=score,
            grade=grade,
            question_completeness_rate=completeness_rate,
            answer_coverage_rate=answer_coverage_rate,
            duplicate_option_count=dup_opt_count,
            missing_options_questions=missing_opts_q[:10],
            formatting_issues=formatting_issues,
            cognitive_balance_score=cognitive_balance_score,
            summary_vi=summary_vi,
        )
