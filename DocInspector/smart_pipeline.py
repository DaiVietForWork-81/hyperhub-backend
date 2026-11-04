"""
Smart Unified Document Reading Pipeline for DocInspector.
"TỰ NHIÊN - MINH BẠCH - KHÔNG DÙNG AI MÀ NGANG AI - TRAINING NHIỀU LẦN"
Handles PDF (multi-column, math, tables), Word (.docx, OMML math), and Google Drive links.
Produces transparent audit trails and non-AI cognitive exam itemization.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .core import DocumentInspector
from .explainability import ExplainabilityEngine, TransparencyAuditDossier
from .extractors import ExtractedDocument, FastDocumentExtractor
from .gdrive_handler import GDriveDocumentHandler, ResolvedDocStream
from .models import (
    CognitiveBreakdown,
    DocumentCategory,
    ExtractedQuestion,
    GradeLevel,
    InspectionReport,
    Subject,
    VerificationVerdict,
)
from .question_parser import QuestionParser
from .schema import StandardizedDocument
from .structural_validator import ExamParsingEngineV2


@dataclass
class SmartPipelineResult:
    """End-to-end outcome of smart document parsing and inspection."""
    file_name: str
    source_type: str  # "PDF", "WORD", "GOOGLE_DRIVE", "GOOGLE_DOCS", "STREAM"
    is_google_drive: bool
    execution_time_ms: float
    report: InspectionReport
    dossier: TransparencyAuditDossier
    extracted_questions: List[ExtractedQuestion]
    total_questions: int
    subject_label_vi: str
    grade_label_vi: str
    exam_track_label_vi: str
    is_spoofed: bool
    verdict_label_vi: str
    file_hash: Optional[str] = None
    content_hash: Optional[str] = None
    quorum_arbitration: Optional[Dict[str, Any]] = None
    draft_dossier_markdown: Optional[str] = None
    standardized_document: Optional[StandardizedDocument] = None

    def to_markdown(self) -> str:
        """Return the transparent human-readable Markdown dossier."""
        return self.dossier.to_markdown()

    def get_draft_dossier_markdown(self) -> str:
        """Return the 3+1 Quorum Arbitration Draft Dossier."""
        return self.draft_dossier_markdown or self.dossier.to_markdown()

    def get_question_item(self, index: int) -> Optional[ExtractedQuestion]:
        """Retrieve question by 1-based index."""
        for q in self.extracted_questions:
            if q.question_index == index:
                return q
        return None

    def export_json(self) -> str:
        """Export report and dossier as structured JSON."""
        import json
        payload = {
            "meta": {
                "file_name": self.file_name,
                "source_type": self.source_type,
                "is_google_drive": self.is_google_drive,
                "execution_time_ms": self.execution_time_ms,
            },
            "inspection": self.report.to_dict(),
            "dossier": self.dossier.to_dict(),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)


class SmartDocumentPipeline:
    """
    Unified Non-AI Document Pipeline.
    Supports PDF, Word (.docx), Google Drive, and Google Docs links.
    """

    @classmethod
    def process(
        cls,
        source: Union[str, Path, bytes],
        file_name_hint: Optional[str] = None,
        explain: bool = True,
    ) -> SmartPipelineResult:
        """
        Main processing method.
        Automatically resolves Google Drive URLs, local paths, or in-memory streams.
        """
        t0 = time.perf_counter()

        # 1. Ingest document stream (resolve Google Drive if needed)
        stream = GDriveDocumentHandler.fetch_stream(source)
        content_bytes = stream.content
        resolved_name = file_name_hint or stream.filename

        # Determine source type
        if stream.is_google_drive:
            source_type = "GOOGLE_DOCS" if resolved_name.endswith(".docx") else "GOOGLE_DRIVE"
        elif resolved_name.lower().endswith(".pdf"):
            source_type = "PDF"
        elif resolved_name.lower().endswith((".docx", ".doc")):
            source_type = "WORD"
        else:
            source_type = "STREAM"

        # 2. Fast Non-AI Feature Extraction
        doc = FastDocumentExtractor.extract(content_bytes, file_name=resolved_name)

        # 3. Core 3-Pass Consensus Inspection (with calibrated weights)
        report = DocumentInspector.inspect(content_bytes, file_name=resolved_name)

        # 4. Generate Transparent Explainability Dossier
        dossier = ExplainabilityEngine.generate_dossier(report, raw_text=doc.full_text)

        # 5. Standardized v2.0.0 Document Schema & 18-Point Structural Validation
        std_doc = ExamParsingEngineV2().parse_document(
            content_bytes,
            file_name=resolved_name,
            subject=report.detected_subject.value,
        )
        report.standardized_document = std_doc

        total_time_ms = (time.perf_counter() - t0) * 1000

        return SmartPipelineResult(
            file_name=resolved_name,
            source_type=source_type,
            is_google_drive=stream.is_google_drive,
            execution_time_ms=round(total_time_ms, 2),
            report=report,
            dossier=dossier,
            extracted_questions=report.pass2.questions or [],
            total_questions=len(report.pass2.questions or []),
            subject_label_vi=report.detected_subject.value,
            grade_label_vi=report.grade_level_label_vi,
            exam_track_label_vi=report.exam_track_label_vi,
            is_spoofed=report.is_spoofed_filename,
            verdict_label_vi=report.verdict_label_vi,
            file_hash=report.file_hash,
            content_hash=report.content_hash,
            quorum_arbitration=report.quorum_arbitration,
            draft_dossier_markdown=report.draft_dossier_markdown,
            standardized_document=std_doc,
        )
