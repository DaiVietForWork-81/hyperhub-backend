"""
Difficulty Assessor and User Requirements Qualification Engine.
Allows users to evaluate documents against strict customizable criteria,
difficulty targets, and pedagogical standards.
100% Deterministic, Zero AI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import (
    DifficultyAssessment,
    DifficultyTier,
    DocumentCategory,
    ExamType,
    GradeLevel,
    InspectionReport,
    Pass1Report,
    Pass2Report,
    Pass3Report,
    RequirementAuditResult,
    Subject,
    UserRequirements,
    ValidationCheck,
)


class DifficultyAssessor:
    """Calculates comprehensive difficulty index and workload metrics."""

    @classmethod
    def assess(
        cls,
        category: DocumentCategory,
        exam_type: ExamType,
        subject: Subject,
        pass1: Pass1Report,
        pass2: Pass2Report,
        pass3: Pass3Report,
    ) -> DifficultyAssessment:
        """
        Synthesize multi-pass signals into a standardized difficulty score (1.0 to 10.0),
        audience tier, and recommended testing duration.
        """
        # Non-exams have baseline difficulty 1.0 - 2.0
        if category in [DocumentCategory.ADMIN_CONTRACT, DocumentCategory.LESSON_PLAN, DocumentCategory.GENERAL_DOCUMENT]:
            return DifficultyAssessment(
                score=2.0,
                tier=DifficultyTier.TIER_1_BASIC,
                tier_label_vi="Văn bản hành chính / Kế hoạch sư phạm",
                recommended_duration_minutes=0,
                pace_seconds_per_question=0.0,
                target_audience="Giáo viên / Cán bộ quản lý / Doanh nghiệp",
                cognitive_balance="Văn bản quy phạm hành chính hoặc tài liệu giảng dạy",
                rationale="Tài liệu không phải bài thi đánh giá năng lực học sinh.",
            )

        # Baseline difficulty from Pass 2 cognitive breakdown
        raw_score = pass2.cognitive_breakdown.estimated_difficulty_index

        # Adjust for Competitive Programming & Olympiads
        if exam_type == ExamType.COMPETITIVE_PROGRAMMING:
            raw_score = max(8.8, min(10.0, raw_score + 2.5))
        elif exam_type in [ExamType.OLYMPIAD_ESSAY, ExamType.SPECIALIZED_ENGLISH]:
            raw_score = max(8.0, min(9.8, raw_score + 1.8))
        elif pass2.grade_level == GradeLevel.OLYMPIAD_GIFTED:
            raw_score = max(8.5, min(10.0, raw_score + 2.0))
        elif pass2.grade_level == GradeLevel.GRADE_12:
            raw_score = max(4.5, min(8.5, raw_score))

        # Clamp between 1.0 and 10.0
        final_score = round(max(1.0, min(10.0, raw_score)), 1)

        # Map to Difficulty Tier
        if final_score <= 4.5:
            tier = DifficultyTier.TIER_1_BASIC
            tier_vi = "Mức 1: Cơ bản (Tốt nghiệp THPT / Xét tốt nghiệp)"
            audience = "Học sinh đại trà ôn tập thi Tốt nghiệp THPT"
        elif final_score <= 6.5:
            tier = DifficultyTier.TIER_2_MODERATE
            tier_vi = "Mức 2: Khá (Xét tuyển Cao đẳng - Đại học tiêu chuẩn)"
            audience = "Học sinh khá xét tuyển Đại học các khối truyền thống"
        elif final_score <= 8.2:
            tier = DifficultyTier.TIER_3_ADVANCED
            tier_vi = "Mức 3: Giỏi (Xét tuyển Đại học Top đầu / Trường chuyên)"
            audience = "Học sinh giỏi xét tuyển các trường Đại học trọng điểm"
        else:
            tier = DifficultyTier.TIER_4_OLYMPIAD
            tier_vi = "Mức 4: Xuất sắc (Chuyên sâu & Olympic Học sinh giỏi)"
            audience = "Đội tuyển Olympic / Học sinh giỏi Chuyên / ICPC / VNOI"

        # Recommended testing duration
        q_count = max(1, pass2.question_count)
        if exam_type == ExamType.COMPETITIVE_PROGRAMMING:
            duration = 180  # 3 hours for CP
        elif exam_type in [ExamType.OLYMPIAD_ESSAY, ExamType.SPECIALIZED_ENGLISH]:
            duration = 150  # 2.5 hours
        elif subject == Subject.MATHEMATICS and q_count >= 30:
            duration = 90   # 90 mins for standard 50-MCQ Math
        elif subject in [Subject.PHYSICS, Subject.CHEMISTRY, Subject.BIOLOGY] and q_count >= 25:
            duration = 50   # 50 mins for KHTN
        elif exam_type == ExamType.IELTS_TEST:
            duration = 60
        elif exam_type == ExamType.TOEIC_TEST:
            duration = 120
        elif exam_type == ExamType.JLPT_TEST:
            duration = 105
        else:
            duration = max(45, min(120, round(q_count * 1.8)))

        pace = round((duration * 60.0) / q_count, 1)

        # Cognitive balance analysis
        cb = pass2.cognitive_breakdown
        total_cog = max(1, cb.recognition_count + cb.comprehension_count + cb.application_count + cb.high_application_count)
        p_high = cb.high_application_count / total_cog
        p_rec = cb.recognition_count / total_cog
        p_app = cb.application_count / total_cog

        if p_high >= 0.25:
            balance = "Nặng về phân hóa cao (Vận dụng cao chiếm tỷ trọng lớn >= 25%)"
        elif p_rec >= 0.50:
            balance = "Thiên về nhận biết lý thuyết căn bản (>= 50%)"
        elif (p_app + p_high) >= 0.50:
            balance = "Thiên về bài tập tính toán và vận dụng thực hành (>= 50%)"
        else:
            balance = "Ma trận đề thi cân đối chuẩn sư phạm theo cấu trúc phân hóa"

        rationale = (
            f"Đề thi được tính điểm {final_score}/10 dựa trên {q_count} câu hỏi, "
            f"phân bổ {cb.recognition_count} Nhận biết, {cb.comprehension_count} Thông hiểu, "
            f"{cb.application_count} Vận dụng, {cb.high_application_count} Vận dụng cao."
        )

        return DifficultyAssessment(
            score=final_score,
            tier=tier,
            tier_label_vi=tier_vi,
            recommended_duration_minutes=duration,
            pace_seconds_per_question=pace,
            target_audience=audience,
            cognitive_balance=balance,
            rationale=rationale,
        )


class RequirementValidator:
    """Validates an InspectionReport against user-specified requirements."""

    PRESET_PROFILES: Dict[str, UserRequirements] = {
        # Đề thi tốt nghiệp THPT chuẩn Bộ GD&ĐT
        "thpt_graduation": UserRequirements(
            profile_name="THPT_GRADUATION",
            min_difficulty=3.5,
            max_difficulty=6.5,
            require_answer_keys=True,
            allow_scanned_pdf=False,
            strict_anti_spoof=True,
        ),
        # Đề thi phân hóa Đại học Top đầu
        "university_top": UserRequirements(
            profile_name="UNIVERSITY_TOP",
            min_difficulty=6.6,
            max_difficulty=8.5,
            target_tier=DifficultyTier.TIER_3_ADVANCED,
            require_answer_keys=True,
            allow_scanned_pdf=False,
            strict_anti_spoof=True,
        ),
        # Đề thi Olympic / Đội tuyển Chuyên
        "olympiad": UserRequirements(
            profile_name="OLYMPIAD_GIFTED",
            min_difficulty=8.0,
            max_difficulty=10.0,
            target_tier=DifficultyTier.TIER_4_OLYMPIAD,
            strict_anti_spoof=True,
        ),
        # Thẩm định Giáo án chuẩn CV 5512
        "cv5512": UserRequirements(
            profile_name="CV5512_LESSON_PLAN",
            require_cv_5512=True,
            strict_anti_spoof=True,
        ),
        # Đề thi chuẩn format mới Bộ GD&ĐT 2025
        "moet_2025": UserRequirements(
            profile_name="MOET_2025_NEW_FORMAT",
            require_moet_2025=True,
            require_answer_keys=True,
            strict_anti_spoof=True,
        ),
        # Chế độ kiểm định an ninh nghiêm ngặt
        "strict_security": UserRequirements(
            profile_name="STRICT_SECURITY",
            strict_anti_spoof=True,
            allow_scanned_pdf=False,
            require_answer_keys=True,
        ),
    }

    @classmethod
    def get_preset(cls, name: str) -> Optional[UserRequirements]:
        """Fetch a preset requirement profile by name."""
        return cls.PRESET_PROFILES.get(name.lower())

    @classmethod
    def load_from_json(cls, json_path: Union[str, Path]) -> UserRequirements:
        """Load custom user requirements from a JSON file."""
        p = Path(json_path)
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        req = UserRequirements(
            profile_name=data.get("profile_name", "CUSTOM_USER_CONFIG"),
            min_difficulty=data.get("min_difficulty"),
            max_difficulty=data.get("max_difficulty"),
            min_questions=data.get("min_questions"),
            max_questions=data.get("max_questions"),
            require_answer_keys=data.get("require_answer_keys", False),
            require_detailed_solutions=data.get("require_detailed_solutions", False),
            allow_scanned_pdf=data.get("allow_scanned_pdf", True),
            strict_anti_spoof=data.get("strict_anti_spoof", True),
            require_moet_2025=data.get("require_moet_2025", False),
            require_cv_5512=data.get("require_cv_5512", False),
        )

        if "target_subject" in data and data["target_subject"]:
            req.target_subject = Subject[data["target_subject"].upper()]
        if "target_grade" in data and data["target_grade"]:
            req.target_grade = GradeLevel[data["target_grade"].upper()]
        if "target_tier" in data and data["target_tier"]:
            req.target_tier = DifficultyTier[data["target_tier"].upper()]

        return req

    @classmethod
    def validate(
        cls,
        report: InspectionReport,
        requirements: UserRequirements,
    ) -> RequirementAuditResult:
        """
        Executes complete verification of an inspection report against requirements.
        """
        checks: List[ValidationCheck] = []
        recommendations: List[str] = []

        # 1. Anti-Spoofing Check
        if requirements.strict_anti_spoof:
            is_passed = not report.is_spoofed_filename
            checks.append(ValidationCheck(
                rule_name="ANTI_SPOOF_CHECK",
                description="Tên file phải phản ánh đúng nội dung thực tế bên trong",
                passed=is_passed,
                expected="Không giả mạo tên file",
                actual=report.spoof_details if report.is_spoofed_filename else "Tên file hợp lệ",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append("Đổi tên file về đúng môn học và định dạng thực tế để tránh nhầm lẫn.")

        # 2. Target Subject Check
        if requirements.target_subject is not None:
            is_passed = (report.detected_subject == requirements.target_subject)
            checks.append(ValidationCheck(
                rule_name="SUBJECT_MATCH",
                description=f"Môn học bắt buộc phải là {requirements.target_subject.value}",
                passed=is_passed,
                expected=requirements.target_subject.value,
                actual=report.detected_subject.value,
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append(f"Tài liệu thuộc môn {report.detected_subject.value}, không thỏa mãn yêu cầu môn {requirements.target_subject.value}.")

        # 3. Target Grade Level Check
        if requirements.target_grade is not None:
            is_passed = (report.grade_level == requirements.target_grade)
            checks.append(ValidationCheck(
                rule_name="GRADE_LEVEL_MATCH",
                description=f"Khối lớp bắt buộc phải là {requirements.target_grade.value}",
                passed=is_passed,
                expected=requirements.target_grade.value,
                actual=report.grade_level.value,
                severity="WARNING",
            ))
            if not is_passed:
                recommendations.append(f"Khối lớp phát hiện ({report.grade_level.value}) không khớp mục tiêu ({requirements.target_grade.value}).")

        # 4. Difficulty Bounds Check
        diff_score = report.difficulty_assessment.score
        if requirements.min_difficulty is not None:
            is_passed = (diff_score >= requirements.min_difficulty)
            checks.append(ValidationCheck(
                rule_name="MIN_DIFFICULTY_THRESHOLD",
                description=f"Độ khó tối thiểu yêu cầu >= {requirements.min_difficulty}",
                passed=is_passed,
                expected=f">= {requirements.min_difficulty}",
                actual=f"{diff_score}",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append(f"Độ khó đề thi ({diff_score}/10) thấp hơn mức yêu cầu ({requirements.min_difficulty}). Cần bổ sung câu hỏi phân hóa/vận dụng cao.")

        if requirements.max_difficulty is not None:
            is_passed = (diff_score <= requirements.max_difficulty)
            checks.append(ValidationCheck(
                rule_name="MAX_DIFFICULTY_THRESHOLD",
                description=f"Độ khó tối đa cho phép <= {requirements.max_difficulty}",
                passed=is_passed,
                expected=f"<= {requirements.max_difficulty}",
                actual=f"{diff_score}",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append(f"Độ khó đề thi ({diff_score}/10) vượt quá ngưỡng cho phép ({requirements.max_difficulty}). Cần giảm bớt câu hỏi phức tạp.")

        # 5. Difficulty Tier Check
        if requirements.target_tier is not None:
            is_passed = (report.difficulty_assessment.tier == requirements.target_tier)
            checks.append(ValidationCheck(
                rule_name="DIFFICULTY_TIER_MATCH",
                description=f"Phân hạng độ khó yêu cầu phải là {requirements.target_tier.value}",
                passed=is_passed,
                expected=requirements.target_tier.value,
                actual=report.difficulty_assessment.tier.value,
                severity="ERROR",
            ))

        # 6. Question Count Bounds
        q_count = report.pass2.question_count
        if requirements.min_questions is not None:
            is_passed = (q_count >= requirements.min_questions)
            checks.append(ValidationCheck(
                rule_name="MIN_QUESTIONS_COUNT",
                description=f"Số lượng câu hỏi tối thiểu >= {requirements.min_questions}",
                passed=is_passed,
                expected=f">= {requirements.min_questions}",
                actual=f"{q_count} câu",
                severity="ERROR",
            ))

        if requirements.max_questions is not None:
            is_passed = (q_count <= requirements.max_questions)
            checks.append(ValidationCheck(
                rule_name="MAX_QUESTIONS_COUNT",
                description=f"Số lượng câu hỏi tối đa <= {requirements.max_questions}",
                passed=is_passed,
                expected=f"<= {requirements.max_questions}",
                actual=f"{q_count} câu",
                severity="ERROR",
            ))

        # 7. Answer Keys Requirement
        if requirements.require_answer_keys:
            is_passed = report.pass2.has_answer_keys
            checks.append(ValidationCheck(
                rule_name="REQUIRE_ANSWER_KEYS",
                description="Bắt buộc phải có bảng đáp án đính kèm",
                passed=is_passed,
                expected="Có bảng đáp án",
                actual="Có" if is_passed else "Không tìm thấy đáp án",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append("Đề thi chưa có bảng đáp án. Cần đính kèm ma trận đáp án ở cuối văn bản.")

        # 8. Detailed Solutions Requirement
        if requirements.require_detailed_solutions:
            is_passed = report.pass2.has_detailed_solutions
            checks.append(ValidationCheck(
                rule_name="REQUIRE_DETAILED_SOLUTIONS",
                description="Bắt buộc phải có lời giải / hướng dẫn giải chi tiết",
                passed=is_passed,
                expected="Có lời giải chi tiết",
                actual="Có" if is_passed else "Không có lời giải chi tiết",
                severity="WARNING",
            ))
            if not is_passed:
                recommendations.append("Nên bổ sung hướng dẫn giải chi tiết cho các câu hỏi vận dụng.")

        # 9. Scanned PDF Ban
        if not requirements.allow_scanned_pdf:
            is_passed = not report.pass1.is_scanned_pdf
            checks.append(ValidationCheck(
                rule_name="NO_SCANNED_PDF",
                description="Không chấp nhận file PDF scan dạng ảnh chụp chất lượng thấp",
                passed=is_passed,
                expected="PDF dạng Vector text",
                actual="PDF ảnh Scan" if report.pass1.is_scanned_pdf else "Vector text",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append("File là PDF scan ảnh. Cần chạy OCR hoặc thay thế bằng văn bản điện tử gốc.")

        # 10. MOET 2025 Format Requirement
        if requirements.require_moet_2025:
            is_passed = report.pass2.curriculum.moet_2025_compliant
            checks.append(ValidationCheck(
                rule_name="MOET_2025_COMPLIANCE",
                description="Bắt buộc phải tuân theo cấu trúc định dạng chuẩn Bộ GD&ĐT 2025 (Phần I, II, III)",
                passed=is_passed,
                expected="Chuẩn Bộ GD&ĐT 2025",
                actual="Chuẩn 2025" if is_passed else "Định dạng truyền thống",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append("Cần tái cấu trúc đề thi thành 3 phần: Phần I (Trắc nghiệm nhiều lựa chọn), Phần II (Đúng/Sai), Phần III (Trả lời ngắn).")

        # 11. CV 5512 Lesson Plan Requirement
        if requirements.require_cv_5512:
            is_passed = report.pass2.curriculum.has_cv_5512_structure
            checks.append(ValidationCheck(
                rule_name="CV5512_LESSON_PLAN_COMPLIANCE",
                description="Bắt buộc phải có tiến trình dạy học theo Công văn 5512",
                passed=is_passed,
                expected="Chuẩn Công văn 5512",
                actual="Đạt chuẩn 5512" if is_passed else "Chưa đúng chuẩn 5512",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append("Kế hoạch bài dạy cần có đủ 4 hoạt động: Khởi động, Hình thành kiến thức, Luyện tập, Vận dụng.")

        # 12. Pedagogical Quality Score Minimum
        if requirements.min_quality_score is not None:
            q_score = report.quality_audit.overall_score
            is_passed = (q_score >= requirements.min_quality_score)
            checks.append(ValidationCheck(
                rule_name="MIN_QUALITY_SCORE",
                description=f"Điểm chất lượng sư phạm tối thiểu >= {requirements.min_quality_score}/100",
                passed=is_passed,
                expected=f">= {requirements.min_quality_score} điểm",
                actual=f"{q_score} điểm (Hạng {report.quality_audit.grade.value})",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append(f"Điểm chất lượng ({q_score}) chưa đạt chuẩn. Kiểm tra lại tính hoàn thiện của các câu hỏi hoặc đáp án.")

        # 13. Answer Coverage Rate
        if requirements.min_answer_coverage_percent is not None:
            cov_pct = report.quality_audit.answer_coverage_rate * 100.0
            is_passed = (cov_pct >= requirements.min_answer_coverage_percent)
            checks.append(ValidationCheck(
                rule_name="MIN_ANSWER_COVERAGE_RATE",
                description=f"Tỷ lệ câu hỏi có đáp án đối chiếu >= {requirements.min_answer_coverage_percent}%",
                passed=is_passed,
                expected=f">= {requirements.min_answer_coverage_percent}%",
                actual=f"{cov_pct:.1f}%",
                severity="ERROR",
            ))
            if not is_passed:
                recommendations.append(f"Tỷ lệ phủ đáp án ({cov_pct:.1f}%) quá thấp. Cần cung cấp đầy đủ đáp án cho tất cả câu hỏi.")

        # 14. Required Sub-Topics
        if requirements.required_topics:
            detected_topic_names = [t.topic_name_vi.lower() for t in report.pass3.sub_topics] + [t.topic_code.lower() for t in report.pass3.sub_topics]
            missing_topics = []
            for req_t in requirements.required_topics:
                if not any(req_t.lower() in dt for dt in detected_topic_names):
                    missing_topics.append(req_t)

            is_passed = len(missing_topics) == 0
            checks.append(ValidationCheck(
                rule_name="REQUIRED_SUB_TOPICS",
                description=f"Bắt buộc phải chứa các chuyên đề: {', '.join(requirements.required_topics)}",
                passed=is_passed,
                expected=", ".join(requirements.required_topics),
                actual="Đủ chuyên đề" if is_passed else f"Thiếu: {', '.join(missing_topics)}",
                severity="WARNING",
            ))
            if not is_passed:
                recommendations.append(f"Đề thi còn thiếu các chuyên đề trọng tâm: {', '.join(missing_topics)}.")

        # Aggregate Result
        passed_count = sum(1 for c in checks if c.passed)
        failed_count = sum(1 for c in checks if not c.passed)

        # Critical error check
        has_critical_error = any(not c.passed and c.severity == "ERROR" for c in checks)
        is_eligible = not has_critical_error

        status_vi = "ĐẠT YÊU CẦU" if is_eligible else "KHÔNG ĐẠT YÊU CẦU"

        return RequirementAuditResult(
            profile_applied=requirements.profile_name,
            is_eligible=is_eligible,
            status_label_vi=status_vi,
            passed_checks_count=passed_count,
            failed_checks_count=failed_count,
            checks=checks,
            recommendations=recommendations,
        )
