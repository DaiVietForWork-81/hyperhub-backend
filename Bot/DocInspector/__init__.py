"""
DocInspector - Non-AI Fast Universal Document & Exam Classifier
A deterministic, rule-based 3-pass inspection engine for PDF and Word files.
Zero AI required, zero API costs, sub-millisecond execution, 100% spoof-resistant.
"""

from .core import DocumentInspector, inspect_document
from .models import (
    CognitiveBreakdown,
    CognitiveLevel,
    DifficultyAssessment,
    DifficultyTier,
    DocumentCategory,
    ExamType,
    ExtractedQuestion,
    GradeLevel,
    InspectionReport,
    PedagogicalQualityAudit,
    QualityGrade,
    ChannelComplianceResult,
    RequirementAuditResult,
    Subject,
    SubTopicMatch,
    TextMetrics,
    UserRequirements,
    ValidationCheck,
    VerificationVerdict,
    ExamTrackTier,
    EXAM_TRACK_VI_NAMES,
    DEFAULT_SUBMISSION_CHANNEL_ID,
    DEFAULT_TARGET_CATEGORY_ID,
    SubmissionRoutingResult,
)
from .channel_manager import (
    BotInspectorAdapter,
    CategoryDirectoryManager,
    ChannelAutoDetector,
    ChannelComplianceValidator,
    ChannelProfile,
    ChannelRegistry,
)
from .quality_auditor import QualityAuditor
from .question_parser import QuestionParser
from .reporting import DocumentReporter
from .topic_detector import SubTopicDetector
from .track_classifier import ExamTrackClassifier
from .url_fetcher import FetchedDocument, UrlBlockedOrUnknownOriginError, UrlDocumentFetcher
from .validator import DifficultyAssessor, RequirementValidator
from .verification_engine import VerificationVerdictEvaluator

__version__ = "2.1.0"
__all__ = [
    "DocumentInspector",
    "inspect_document",
    "InspectionReport",
    "DocumentCategory",
    "ExamType",
    "Subject",
    "GradeLevel",
    "CognitiveLevel",
    "CognitiveBreakdown",
    "ExtractedQuestion",
    "TextMetrics",
    "DifficultyTier",
    "DifficultyAssessment",
    "ValidationCheck",
    "UserRequirements",
    "RequirementAuditResult",
    "QuestionParser",
    "DocumentReporter",
    "DifficultyAssessor",
    "RequirementValidator",
    "QualityAuditor",
    "QualityGrade",
    "PedagogicalQualityAudit",
    "SubTopicDetector",
    "SubTopicMatch",
    "UrlDocumentFetcher",
    "UrlBlockedOrUnknownOriginError",
    "FetchedDocument",
    "VerificationVerdict",
    "VerificationVerdictEvaluator",
    "ChannelProfile",
    "ChannelRegistry",
    "ChannelAutoDetector",
    "ChannelComplianceValidator",
    "BotInspectorAdapter",
    "ChannelComplianceResult",
    "CategoryDirectoryManager",
    "DEFAULT_TARGET_CATEGORY_ID",
    "DEFAULT_SUBMISSION_CHANNEL_ID",
    "SubmissionRoutingResult",
    "ExamTrackTier",
    "EXAM_TRACK_VI_NAMES",
    "ExamTrackClassifier",
]
