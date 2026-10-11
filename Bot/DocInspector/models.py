"""
Data models and Enums for DocInspector inspection reports.
Rich, production-grade schema with cognitive levels, grade levels,
curriculum alignment, and itemized question structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DocumentCategory(str, Enum):
    EXAM_TEST = "EXAM_TEST"                     # Đề thi / Đề kiểm tra
    LESSON_PLAN = "LESSON_PLAN"                 # Giáo án / Kế hoạch bài dạy (KHBD)
    THEORY_SYLLABUS = "THEORY_SYLLABUS"         # Tài liệu lý thuyết / Đề cương
    ADMIN_CONTRACT = "ADMIN_CONTRACT"           # Văn bản hành chính / Hợp đồng / Công văn
    SOURCE_CODE_DOC = "SOURCE_CODE_DOC"         # Tài liệu hướng dẫn lập trình / Code
    RESEARCH_PAPER = "RESEARCH_PAPER"           # Báo cáo / Nghiên cứu / Luận văn
    GENERAL_DOCUMENT = "GENERAL_DOCUMENT"       # Tài liệu tổng quát khác


class VerificationVerdict(str, Enum):
    """
    4-Tier Definitive Verification Status:
    - VERIFIED_OK: Xác minh (thấy ổn) - 100% khớp, cấu trúc & môn học rõ ràng, độ tin cậy cao
    - UNCERTAIN_MATCH: Chưa rõ ràng (là xác minh nhưng chưa chắc là đúng đề) - Có tín hiệu nhưng chưa chắc chắn hoặc là tài liệu lý thuyết/tham khảo
    - UNIDENTIFIED_EXAM: Không rõ ràng (xem được đề nhưng không biết là đề nào) - Nhận diện có đề thi/câu hỏi nhưng không rõ môn gì / từ khóa mờ nhạt
    - UNVERIFIABLE_FAILED: Không xác minh (là ko đc j hết) - File hỏng, rỗng, scan không OCR, mã hóa hoặc link bị chặn bot / không rõ nguồn gốc
    """
    VERIFIED_OK = "XAC_MINH"                     # Xác minh (thấy ổn)
    UNCERTAIN_MATCH = "CHUA_RO_RANG"             # Chưa rõ ràng (xác minh nhưng chưa chắc là đúng đề)
    UNIDENTIFIED_EXAM = "KO_RO_RANG"             # Không rõ ràng (xem được đề nhưng không biết là đề nào)
    UNVERIFIABLE_FAILED = "KO_XAC_MINH"         # Không xác minh (không được gì hết)


class ExamType(str, Enum):
    MCQ_STANDARD_4 = "MCQ_STANDARD_4"                     # Trắc nghiệm 4 lựa chọn (A, B, C, D)
    MCQ_TRUE_FALSE = "MCQ_TRUE_FALSE"                     # Trắc nghiệm Đúng / Sai
    MCQ_SHORT_ANSWER = "MCQ_SHORT_ANSWER"                 # Trắc nghiệm điền số / Trả lời ngắn (Chuẩn 2025)
    MOET_2025_COMBINED = "MOET_2025_COMBINED"             # Đề chuẩn Bộ GD&ĐT 2025 (3 phần kết hợp)
    COMPETITIVE_PROGRAMMING = "COMPETITIVE_PROGRAMMING"   # Chuyên Tin / Olympic Tin học (Time limit, INP/OUT)
    OLYMPIAD_ESSAY = "OLYMPIAD_ESSAY"                     # Đề Chuyên / Olympic Tự luận
    IELTS_TEST = "IELTS_TEST"                             # Bài thi IELTS (Passages 1-3, T/F/NG)
    TOEIC_TEST = "TOEIC_TEST"                             # Bài thi TOEIC (Part 1-7)
    SPECIALIZED_ENGLISH = "SPECIALIZED_ENGLISH"           # Chuyên Anh (Word formation, sentence transform)
    JLPT_TEST = "JLPT_TEST"                               # Tiếng Nhật JLPT (N1-N5)
    HSK_TEST = "HSK_TEST"                                 # Tiếng Trung HSK (1-6)
    TOPIK_TEST = "TOPIK_TEST"                             # Tiếng Hàn TOPIK
    TRKI_TEST = "TRKI_TEST"                               # Tiếng Nga TRKI (A1-C2)
    GENERAL_ESSAY = "GENERAL_ESSAY"                       # Tự luận phổ thông
    NOT_AN_EXAM = "NOT_AN_EXAM"                           # Không phải đề thi


class Subject(str, Enum):
    INFORMATICS = "INFORMATICS"                 # Tin học (Chuyên Tin, Thuật toán, Lập trình)
    MATHEMATICS = "MATHEMATICS"                 # Toán học (Chuyên Toán, THPT)
    PHYSICS = "PHYSICS"                         # Vật lý (Chuyên Lý, THPT)
    CHEMISTRY = "CHEMISTRY"                     # Hóa học (Chuyên Hóa, THPT)
    BIOLOGY = "BIOLOGY"                         # Sinh học (Chuyên Sinh, THPT)
    LITERATURE = "LITERATURE"                   # Ngữ văn (Chuyên Văn, THPT)
    ENGLISH = "ENGLISH"                         # Tiếng Anh (IELTS, Chuyên Anh, THPT)
    JAPANESE = "JAPANESE"                       # Tiếng Nhật (JLPT)
    CHINESE = "CHINESE"                         # Tiếng Trung (HSK)
    KOREAN = "KOREAN"                           # Tiếng Hàn (TOPIK)
    RUSSIAN = "RUSSIAN"                         # Tiếng Nga (TRKI)
    FRENCH = "FRENCH"                           # Tiếng Pháp
    HISTORY = "HISTORY"                         # Lịch sử
    GEOGRAPHY = "GEOGRAPHY"                     # Địa lý
    CIVIC_EDUCATION = "CIVIC_EDUCATION"         # GDCD / Kinh tế & Pháp luật
    NATURAL_SCIENCE = "NATURAL_SCIENCE"         # Khoa học tự nhiên
    GENERAL = "GENERAL"                         # Đa môn / Chung
    NON_ACADEMIC = "NON_ACADEMIC"               # Phi học thuật / Khác


class GradeLevel(str, Enum):
    GRADE_12 = "GRADE_12"                       # Lớp 12 / Ôn thi THPT Quốc Gia
    GRADE_11 = "GRADE_11"                       # Lớp 11
    GRADE_10 = "GRADE_10"                       # Lớp 10 / Tuyển sinh vào 10
    GRADE_9 = "GRADE_9"                         # Lớp 9 / Ôn thi vào 10
    GRADE_8 = "GRADE_8"                         # Lớp 8
    GRADE_7 = "GRADE_7"                         # Lớp 7
    GRADE_6 = "GRADE_6"                         # Lớp 6
    MIDDLE_SCHOOL = "MIDDLE_SCHOOL"             # THCS chung (Lớp 6, 7, 8, 9)
    HIGH_SCHOOL = "HIGH_SCHOOL"                 # THPT chung (Lớp 10, 11, 12)
    PRIMARY_SCHOOL = "PRIMARY_SCHOOL"           # Tiểu học (Lớp 1-5)
    OLYMPIAD_GIFTED = "OLYMPIAD_GIFTED"         # Học sinh giỏi Quốc Gia / Đội tuyển Chuyên
    UNIVERSITY = "UNIVERSITY"                   # Đại học / Cao đẳng
    GENERAL_ACADEMIC = "GENERAL_ACADEMIC"       # Phổ thông chung
    UNKNOWN = "UNKNOWN"                         # Không xác định


GRADE_LEVEL_VI_NAMES: Dict[GradeLevel, str] = {
    GradeLevel.GRADE_12: "Lớp 12 (THPT / Ôn thi ĐH)",
    GradeLevel.GRADE_11: "Lớp 11 (THPT)",
    GradeLevel.GRADE_10: "Lớp 10 (THPT / Tuyển sinh 10)",
    GradeLevel.GRADE_9: "Lớp 9 (THCS / Ôn thi vào 10)",
    GradeLevel.GRADE_8: "Lớp 8 (THCS)",
    GradeLevel.GRADE_7: "Lớp 7 (THCS)",
    GradeLevel.GRADE_6: "Lớp 6 (THCS)",
    GradeLevel.MIDDLE_SCHOOL: "Khối THCS (Lớp 6-9)",
    GradeLevel.HIGH_SCHOOL: "Khối THPT (Lớp 10-12)",
    GradeLevel.PRIMARY_SCHOOL: "Khối Tiểu học (Lớp 1-5)",
    GradeLevel.OLYMPIAD_GIFTED: "Đội tuyển HSG / Olympic",
    GradeLevel.UNIVERSITY: "Đại học / Cao đẳng",
    GradeLevel.GENERAL_ACADEMIC: "Phổ thông chung",
    GradeLevel.UNKNOWN: "Chung / Chưa rõ lớp",
}


class ExamTrackTier(str, Enum):
    """
    Phân loại cấp độ / thể loại đề thi (5 thể loại):
    THUONG   : Đề thường (đại trà, phổ thông, kiểm tra định kỳ, tốt nghiệp) - độ khó: thường < hsg < chuyên
    HSG      : Đề HSG (học sinh giỏi cấp trường, quận, huyện, tỉnh/TP - cấp độ trung gian, dễ hơn chuyên)
    CHUYEN   : Đề chuyên (trường THPT Chuyên, tuyển sinh 10 chuyên, Olympic Quốc gia - cấp độ cao nhất)
    QUOC_TE  : Đề quốc tế (kỳ thi quốc tế: IMO, IOI, IPhO, AMC, IKMC, SASMO, TIMO, SAT... cả tiếng Việt và quốc tế)
    CHUNG    : Đề chung (tài liệu lý thuyết, đề cương ôn tập tổng hợp, hoặc đề chung chung có thể gây hiểu lầm)
    """
    THUONG = "thuong"
    HSG = "hsg"
    CHUYEN = "chuyen"
    QUOC_TE = "quoc_te"
    CHUNG = "chung"


EXAM_TRACK_VI_NAMES: Dict[ExamTrackTier, str] = {
    ExamTrackTier.THUONG: "Đề thường",
    ExamTrackTier.HSG: "Đề HSG",
    ExamTrackTier.CHUYEN: "Đề chuyên",
    ExamTrackTier.QUOC_TE: "Đề quốc tế",
    ExamTrackTier.CHUNG: "Đề chung",
}



class CognitiveLevel(str, Enum):
    RECOGNITION = "RECOGNITION"                 # Nhận biết
    COMPREHENSION = "COMPREHENSION"             # Thông hiểu
    APPLICATION = "APPLICATION"                 # Vận dụng
    HIGH_APPLICATION = "HIGH_APPLICATION"       # Vận dụng cao


@dataclass
class CognitiveBreakdown:
    """Breakdown of estimated cognitive levels across all extracted questions."""
    recognition_count: int = 0
    comprehension_count: int = 0
    application_count: int = 0
    high_application_count: int = 0
    estimated_difficulty_index: float = 5.0  # 1.0 (very easy) to 10.0 (Olympiad hard)

    def to_dict(self) -> Dict[str, Any]:
        total = max(1, self.recognition_count + self.comprehension_count + self.application_count + self.high_application_count)
        return {
            "recognition": {
                "count": self.recognition_count,
                "percentage": round(self.recognition_count / total * 100, 1),
            },
            "comprehension": {
                "count": self.comprehension_count,
                "percentage": round(self.comprehension_count / total * 100, 1),
            },
            "application": {
                "count": self.application_count,
                "percentage": round(self.application_count / total * 100, 1),
            },
            "high_application": {
                "count": self.high_application_count,
                "percentage": round(self.high_application_count / total * 100, 1),
            },
            "difficulty_index": round(self.estimated_difficulty_index, 1),
        }


@dataclass
class ExtractedQuestion:
    """Detailed metadata for an individual parsed question."""
    question_index: int
    label: str
    prompt: str
    options: Dict[str, str] = field(default_factory=dict)
    sub_questions: List[str] = field(default_factory=list)
    question_type: str = "MCQ_4"
    cognitive_level: CognitiveLevel = CognitiveLevel.COMPREHENSION
    detected_answer: Optional[str] = None
    has_solution_text: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.question_index,
            "label": self.label,
            "prompt_preview": (self.prompt[:120] + "...") if len(self.prompt) > 120 else self.prompt,
            "options": self.options,
            "sub_questions": self.sub_questions,
            "question_type": self.question_type,
            "cognitive_level": self.cognitive_level.value,
            "detected_answer": self.detected_answer,
            "has_solution": self.has_solution_text,
        }


@dataclass
class TextMetrics:
    """Forensic metrics of document text."""
    word_count: int = 0
    char_count: int = 0
    line_count: int = 0
    paragraph_count: int = 0
    estimated_reading_time_minutes: float = 0.0
    lexical_density: float = 0.0
    entropy: float = 0.0
    legacy_encoding_warning: Optional[str] = None


@dataclass
class CurriculumAlignment:
    """Alignment with Vietnamese education curriculum books and standards."""
    series_detected: Optional[str] = None  # KNTT, Cánh Diều, Chân Trời Sáng Tạo, etc.
    moet_2025_compliant: bool = False      # Format with Part 1, 2, 3
    has_cv_5512_structure: bool = False    # Lesson plan 5512


@dataclass
class Pass1Report:
    """Pass 1: File integrity, Magic bytes, OCR status, Unicode Script."""
    raw_file_type: str
    magic_signature: str
    is_scanned_pdf: bool
    is_encrypted: bool
    page_count: int
    char_count: int
    primary_script: str
    detected_language: str
    metrics: TextMetrics = field(default_factory=TextMetrics)
    script_distribution: Dict[str, float] = field(default_factory=dict)
    raw_text: str = ""
    execution_time_ms: float = 0.0


@dataclass
class Pass2Report:
    """Pass 2: Structural & Layout pattern extraction."""
    question_count: int
    options_count: int
    detected_structure: str
    has_answer_keys: bool
    has_detailed_solutions: bool
    questions: List[ExtractedQuestion] = field(default_factory=list)
    cognitive_breakdown: CognitiveBreakdown = field(default_factory=CognitiveBreakdown)
    curriculum: CurriculumAlignment = field(default_factory=CurriculumAlignment)
    competitive_meta: Dict[str, Any] = field(default_factory=dict)
    specialized_features: List[str] = field(default_factory=list)
    candidate_exam_types: List[ExamType] = field(default_factory=list)
    grade_level: GradeLevel = GradeLevel.UNKNOWN
    execution_time_ms: float = 0.0


@dataclass
class SubTopicMatch:
    """Detailed chapter / sub-topic detected inside a subject."""
    topic_code: str
    topic_name_vi: str
    weight_score: float
    percentage: float
    detected_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic_code": self.topic_code,
            "topic_name_vi": self.topic_name_vi,
            "weight_score": round(self.weight_score, 1),
            "percentage": round(self.percentage, 1),
            "keywords_sample": self.detected_keywords[:5],
        }


class QualityGrade(str, Enum):
    GRADE_A_PLUS = "A+"                                 # 90 - 100: Xuất sắc
    GRADE_A = "A"                                       # 80 - 89: Tốt
    GRADE_B = "B"                                       # 65 - 79: Khá
    GRADE_C = "C"                                       # 50 - 64: Trung bình
    GRADE_D = "D"                                       # < 50: Kém / Lỗi cấu trúc


@dataclass
class PedagogicalQualityAudit:
    """Pedagogical Exam Health and Structural Quality Audit (0 - 100 Score)."""
    overall_score: float = 85.0
    grade: QualityGrade = QualityGrade.GRADE_A
    question_completeness_rate: float = 1.0             # Ratio of questions with all choices (A-D)
    answer_coverage_rate: float = 1.0                   # Ratio of questions with matched answer keys
    duplicate_option_count: int = 0
    missing_options_questions: List[int] = field(default_factory=list)
    formatting_issues: List[str] = field(default_factory=list)
    cognitive_balance_score: float = 85.0
    summary_vi: str = "Đề thi hoàn thiện, cấu trúc chuẩn mực"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 1),
            "grade": self.grade.value,
            "question_completeness_rate": round(self.question_completeness_rate * 100, 1),
            "answer_coverage_rate": round(self.answer_coverage_rate * 100, 1),
            "duplicate_option_count": self.duplicate_option_count,
            "missing_options_questions": self.missing_options_questions,
            "formatting_issues": self.formatting_issues,
            "cognitive_balance_score": round(self.cognitive_balance_score, 1),
            "summary_vi": self.summary_vi,
        }


@dataclass
class Pass3Report:
    """Pass 3: Deep Domain Lexical, Anti-Spoofing & Triple Validation."""
    subject_scores: Dict[str, float] = field(default_factory=dict)
    top_subject: Subject = Subject.GENERAL
    confidence: float = 0.0
    filename_spoofed: bool = False
    spoof_warning: Optional[str] = None
    evidence_terms: List[str] = field(default_factory=list)
    sub_topics: List[SubTopicMatch] = field(default_factory=list)
    triple_verification_status: str = "PASSED"
    triple_verification_score: float = 100.0
    execution_time_ms: float = 0.0


class DifficultyTier(str, Enum):
    TIER_1_BASIC = "TIER_1_BASIC"                       # Cơ bản / Tốt nghiệp THPT (1.0 - 4.5)
    TIER_2_MODERATE = "TIER_2_MODERATE"                 # Khá / Xét tuyển CĐ - ĐH (4.6 - 6.5)
    TIER_3_ADVANCED = "TIER_3_ADVANCED"                 # Giỏi / ĐH Top đầu (6.6 - 8.2)
    TIER_4_OLYMPIAD = "TIER_4_OLYMPIAD"                 # Xuất sắc / Chuyên sâu & Olympic HSG (8.3 - 10.0)


@dataclass
class DifficultyAssessment:
    """Comprehensive difficulty assessment of the document/exam."""
    score: float = 5.0                                  # 1.0 to 10.0
    tier: DifficultyTier = DifficultyTier.TIER_2_MODERATE
    tier_label_vi: str = "Mức 2: Khá (Xét tuyển ĐH)"
    recommended_duration_minutes: int = 60              # e.g., 50m, 90m, 180m
    pace_seconds_per_question: float = 90.0             # seconds per question
    target_audience: str = "Học sinh THPT"
    cognitive_balance: str = "Cân đối giữa lý thuyết và vận dụng"
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "tier": self.tier.value,
            "tier_label_vi": self.tier_label_vi,
            "recommended_duration_minutes": self.recommended_duration_minutes,
            "pace_seconds_per_question": round(self.pace_seconds_per_question, 1),
            "target_audience": self.target_audience,
            "cognitive_balance": self.cognitive_balance,
            "rationale": self.rationale,
        }


@dataclass
class ValidationCheck:
    """Single criteria check against user requirements."""
    rule_name: str
    description: str
    passed: bool
    expected: Any
    actual: Any
    severity: str = "ERROR"                             # "ERROR", "WARNING", "INFO"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "description": self.description,
            "passed": self.passed,
            "expected": str(self.expected),
            "actual": str(self.actual),
            "severity": self.severity,
        }


@dataclass
class UserRequirements:
    """User-specified criteria for qualification."""
    profile_name: str = "CUSTOM"
    target_subject: Optional[Subject] = None
    target_grade: Optional[GradeLevel] = None
    target_tier: Optional[DifficultyTier] = None
    min_difficulty: Optional[float] = None
    max_difficulty: Optional[float] = None
    min_questions: Optional[int] = None
    max_questions: Optional[int] = None
    min_quality_score: Optional[float] = None
    min_answer_coverage_percent: Optional[float] = None
    required_topics: List[str] = field(default_factory=list)
    require_answer_keys: bool = False
    require_detailed_solutions: bool = False
    allow_scanned_pdf: bool = True
    strict_anti_spoof: bool = True
    require_moet_2025: bool = False
    require_cv_5512: bool = False


@dataclass
class RequirementAuditResult:
    """Results of checking document against user requirements."""
    profile_applied: str
    is_eligible: bool                                   # True if passed all critical criteria
    status_label_vi: str = "ĐẠT YÊU CẦU"                # "ĐẠT YÊU CẦU" or "KHÔNG ĐẠT YÊU CẦU"
    passed_checks_count: int = 0
    failed_checks_count: int = 0
    checks: List[ValidationCheck] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_applied": self.profile_applied,
            "is_eligible": self.is_eligible,
            "status_label_vi": self.status_label_vi,
            "passed_checks_count": self.passed_checks_count,
            "failed_checks_count": self.failed_checks_count,
            "checks": [c.to_dict() for c in self.checks],
            "recommendations": self.recommendations,
        }


DEFAULT_SUBMISSION_CHANNEL_ID: str = "1535278288828633138"
DEFAULT_TARGET_CATEGORY_ID: str = "1534147951797080174"


@dataclass
class ChannelComplianceResult:
    """Evaluation result of document compliance with a specific channel."""
    channel_name: str
    channel_id: Optional[str] = None
    category_id: Optional[str] = None
    is_compliant: bool = True
    expected_subjects: List[Subject] = field(default_factory=list)
    actual_subject: Subject = Subject.GENERAL
    expected_grades: Optional[List[GradeLevel]] = None
    actual_grade: Optional[GradeLevel] = None
    suggested_channels: List[str] = field(default_factory=list)
    warning_message: Optional[str] = None
    bot_reply_formatted: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel_name": self.channel_name,
            "channel_id": self.channel_id,
            "category_id": self.category_id,
            "is_compliant": self.is_compliant,
            "expected_subjects": [s.value for s in self.expected_subjects],
            "actual_subject": self.actual_subject.value,
            "expected_grades": [g.value for g in self.expected_grades] if self.expected_grades else None,
            "actual_grade": self.actual_grade.value if self.actual_grade else None,
            "suggested_channels": self.suggested_channels,
            "warning_message": self.warning_message,
            "bot_reply_formatted": self.bot_reply_formatted,
        }


@dataclass
class SubmissionRoutingResult:
    """
    Result of ingesting a document or link from Submission Channel (1535278288828633138)
    and automatically classifying and routing to a target channel within Category (1534147951797080174).
    """
    submission_channel_id: str = DEFAULT_SUBMISSION_CHANNEL_ID
    target_category_id: str = DEFAULT_TARGET_CATEGORY_ID
    target_channel_name: str = "tai-lieu-chung"
    target_channel_id: Optional[str] = None
    detected_subject: Subject = Subject.GENERAL
    detected_subject_vi: str = "Tài liệu chung"
    detected_grade: GradeLevel = GradeLevel.UNKNOWN
    detected_grade_vi: str = "Chung / Chưa rõ lớp"
    exam_track: ExamTrackTier = ExamTrackTier.THUONG
    exam_track_label_vi: str = "thường"
    verdict: VerificationVerdict = VerificationVerdict.VERIFIED_OK
    verdict_label_vi: str = "Xác minh (thấy ổn)"
    is_blocked_or_unverifiable: bool = False
    routing_reason: str = ""
    submission_reply_message: str = ""
    forwarded_post_message: str = ""
    language_proficiency_band: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "submission_channel_id": self.submission_channel_id,
            "target_category_id": self.target_category_id,
            "target_channel_name": self.target_channel_name,
            "target_channel_id": self.target_channel_id,
            "detected_subject": self.detected_subject.value,
            "detected_subject_vi": self.detected_subject_vi,
            "detected_grade": self.detected_grade.value,
            "detected_grade_vi": self.detected_grade_vi,
            "exam_track": self.exam_track.value,
            "exam_track_label_vi": self.exam_track_label_vi,
            "verdict": self.verdict.value,
            "verdict_label_vi": self.verdict_label_vi,
            "is_blocked_or_unverifiable": self.is_blocked_or_unverifiable,
            "routing_reason": self.routing_reason,
            "language_proficiency_band": self.language_proficiency_band,
            "submission_reply_message": self.submission_reply_message,
            "forwarded_post_message": self.forwarded_post_message,
        }


@dataclass
class InspectionReport:
    """Universal Inspection Output - 100% Deterministic & Non-AI."""
    file_name: str
    file_path: str
    file_size_bytes: int
    total_execution_time_ms: float
    
    document_category: DocumentCategory
    exam_type: ExamType
    detected_subject: Subject
    detected_language: str
    confidence_score: float
    grade_level: GradeLevel
    grade_level_label_vi: str
    
    is_spoofed_filename: bool
    spoof_details: Optional[str]
    human_summary: str

    verdict: VerificationVerdict = VerificationVerdict.VERIFIED_OK
    verdict_label_vi: str = "Xác minh (thấy ổn)"
    verdict_rationale: str = ""

    exam_track: ExamTrackTier = ExamTrackTier.THUONG
    exam_track_label_vi: str = "thường"
    exam_track_rationale: str = ""
    language_proficiency_band: Optional[str] = None
    academic_year: Optional[str] = None
    school_or_department: Optional[str] = None
    programming_language: Optional[str] = None
    detailed_exam_track: Optional[str] = None
    
    difficulty_assessment: DifficultyAssessment = field(default_factory=DifficultyAssessment)
    quality_audit: PedagogicalQualityAudit = field(default_factory=PedagogicalQualityAudit)
    requirement_audit: Optional[RequirementAuditResult] = None
    channel_compliance: Optional[ChannelComplianceResult] = None
    
    pass1: Pass1Report = field(default_factory=lambda: Pass1Report("UNKNOWN", "", False, False, 0, 0, "", ""))
    pass2: Pass2Report = field(default_factory=lambda: Pass2Report(0, 0, "", False, False))
    pass3: Pass3Report = field(default_factory=lambda: Pass3Report())

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "total_execution_time_ms": round(self.total_execution_time_ms, 2),
            "verdict": self.verdict.value,
            "verdict_label_vi": self.verdict_label_vi,
            "verdict_rationale": self.verdict_rationale,
            "document_category": self.document_category.value,
            "exam_type": self.exam_type.value,
            "detected_subject": self.detected_subject.value,
            "exam_track": self.exam_track.value,
            "exam_track_label_vi": self.exam_track_label_vi,
            "exam_track_rationale": self.exam_track_rationale,
            "academic_year": self.academic_year,
            "school_or_department": self.school_or_department,
            "programming_language": self.programming_language,
            "detailed_exam_track": self.detailed_exam_track,
            "language_proficiency_band": self.language_proficiency_band,
            "detected_language": self.detected_language,
            "grade_level": self.grade_level.value,
            "grade_level_label_vi": self.grade_level_label_vi,
            "confidence_score": round(self.confidence_score, 4),
            "is_spoofed_filename": self.is_spoofed_filename,
            "spoof_details": self.spoof_details,
            "human_summary": self.human_summary,
            "difficulty_assessment": self.difficulty_assessment.to_dict(),
            "quality_audit": self.quality_audit.to_dict(),
            "pass1_technical": {
                "file_type": self.pass1.raw_file_type,
                "is_scanned_pdf": self.pass1.is_scanned_pdf,
                "page_count": self.pass1.page_count,
                "word_count": self.pass1.metrics.word_count,
                "char_count": self.pass1.char_count,
                "reading_time_min": round(self.pass1.metrics.estimated_reading_time_minutes, 1),
                "primary_script": self.pass1.primary_script,
                "detected_language": self.pass1.detected_language,
                "script_distribution": self.pass1.script_distribution,
                "legacy_encoding": self.pass1.metrics.legacy_encoding_warning,
                "time_ms": round(self.pass1.execution_time_ms, 2),
            },
            "pass2_structural": {
                "question_count": self.pass2.question_count,
                "options_count": self.pass2.options_count,
                "detected_structure": self.pass2.detected_structure,
                "grade_level": self.pass2.grade_level.value,
                "moet_2025_compliant": self.pass2.curriculum.moet_2025_compliant,
                "series_detected": self.pass2.curriculum.series_detected,
                "has_answer_keys": self.pass2.has_answer_keys,
                "has_detailed_solutions": self.pass2.has_detailed_solutions,
                "cognitive_breakdown": self.pass2.cognitive_breakdown.to_dict(),
                "competitive_meta": self.pass2.competitive_meta,
                "specialized_features": self.pass2.specialized_features,
                "questions_sample": [q.to_dict() for q in self.pass2.questions[:5]],
                "time_ms": round(self.pass2.execution_time_ms, 2),
            },
            "pass3_lexical_verification": {
                "top_subject": self.pass3.top_subject.value,
                "confidence": round(self.pass3.confidence, 4),
                "filename_spoofed": self.pass3.filename_spoofed,
                "spoof_warning": self.pass3.spoof_warning,
                "evidence_terms": self.pass3.evidence_terms[:12],
                "sub_topics": [t.to_dict() for t in self.pass3.sub_topics],
                "verification_status": self.pass3.triple_verification_status,
                "verification_score": self.pass3.triple_verification_score,
                "time_ms": round(self.pass3.execution_time_ms, 2),
            }
        }
        if self.requirement_audit:
            d["requirement_audit"] = self.requirement_audit.to_dict()
        if self.channel_compliance:
            d["channel_compliance"] = self.channel_compliance.to_dict()
        return d

