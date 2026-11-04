"""
DocInspector - Non-AI Fast Universal Document & Exam Classifier
A deterministic, rule-based 3-pass inspection engine for PDF and Word files.
Zero AI required, zero API costs, sub-millisecond execution, 100% spoof-resistant.
"""

from .core import DocumentInspector, inspect_document
from .extractors import ExtractedDocument, FastDocumentExtractor
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
from .config import EngineConfig, LegacyDocPolicy, OCRMode, get_config, set_ocr_mode, set_config
from .schema import (
    AnswerKeyEntry,
    BlankSlot,
    BlockKind,
    CanonicalQuestionType,
    DocumentBlock,
    DocumentConfidenceSummary,
    ImageAsset,
    ManualCorrectionRecord,
    OptionItem,
    PageContentState,
    PageLayout,
    ParseError,
    ParseWarning,
    QuestionConfidence,
    QuestionGroup,
    SharedContext,
    SourceReference,
    StageTiming,
    StandardizedDocument,
    StandardizedQuestion,
    StatementItem,
    SubQuestionNode,
    TableCellModel,
    TableModel,
    WarningSeverity,
)
from .layout_analyzer import LayoutAnalyzer
from .readers import (
    BatchDocumentProcessor,
    DOCXReader,
    DocumentReader,
    DocumentReaderRegistry,
    ImageReader,
    LegacyDOCReader,
    OCRAdapter,
    PDFReader,
    ReaderOptions,
    ReaderOutput,
    SecurityGuard,
    TextReader,
    UnicodeMathNormalizer,
)
from .context_linker import ContextLinker
from .structural_validator import (
    EvaluationBenchmarkResult,
    ExamParsingEngineV2,
    ParserEvaluator,
    StructuralValidator,
    TargetedQuestionRecovery,
)

__version__ = "2.2.0"
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
