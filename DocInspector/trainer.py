"""
Multi-Epoch Heuristic Calibration & Training Harness for DocInspector.
"TRAINING NHIỀU LẦN - TỰ ĐỘNG HIỆU CHUẨN TRỌNG SỐ THUẬT TOÁN - ZERO AI COST"
Runs multiple training epochs across a golden benchmark corpus to optimize
lexical weights, confidence thresholds, and layout sensitivity parameters.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .core import DocumentInspector
from .models import DocumentCategory, GradeLevel, InspectionReport, Subject
from .signatures import SUBJECT_LEXICONS

WEIGHTS_PATH = Path("D:/Project/DocInspector/calibration_weights.json")
HISTORY_PATH = Path("D:/Project/DocInspector/training_history.json")
SAMPLES_DIR = Path("D:/Project/DocInspector/samples")


@dataclass
class GoldenExamAnnotation:
    """Ground truth annotation for a benchmark exam file."""
    file_name: str
    expected_subject: Subject
    expected_category: DocumentCategory
    expected_grade: Optional[GradeLevel]
    expected_min_questions: int
    expected_is_spoofed: bool
    notes: str = ""


# Standard Benchmark Corpus Ground Truth Definitions
DEFAULT_BENCHMARK_CORPUS: List[GoldenExamAnnotation] = [
    GoldenExamAnnotation(
        file_name="de_chuyen_anh_quoc_gia.pdf",
        expected_subject=Subject.ENGLISH,
        expected_category=DocumentCategory.EXAM_TEST,
        expected_grade=GradeLevel.OLYMPIAD_GIFTED,
        expected_min_questions=1,
        expected_is_spoofed=False,
        notes="Đề thi HSG Quốc gia môn Tiếng Anh",
    ),
    GoldenExamAnnotation(
        file_name="de_hoa_hoc_huu_co_thpt.pdf",
        expected_subject=Subject.CHEMISTRY,
        expected_category=DocumentCategory.EXAM_TEST,
        expected_grade=GradeLevel.GRADE_12,
        expected_min_questions=4,
        expected_is_spoofed=False,
        notes="Đề Hóa học hữu cơ THPT",
    ),
    GoldenExamAnnotation(
        file_name="de_sinh_hoc_di_truyen.docx",
        expected_subject=Subject.BIOLOGY,
        expected_category=DocumentCategory.EXAM_TEST,
        expected_grade=GradeLevel.GRADE_12,
        expected_min_questions=3,
        expected_is_spoofed=False,
        notes="Đề Sinh học di truyền DOCX",
    ),
    GoldenExamAnnotation(
        file_name="de_toan_chuyen_hsg.docx",
        expected_subject=Subject.INFORMATICS,  # Content is actually Informatics HSG (anti-spoof test)
        expected_category=DocumentCategory.EXAM_TEST,
        expected_grade=GradeLevel.OLYMPIAD_GIFTED,
        expected_min_questions=1,
        expected_is_spoofed=True,
        notes="Tệp giả mạo tên toán nhưng ruột là Chuyên Tin",
    ),
    GoldenExamAnnotation(
        file_name="giao_an_vat_ly_12_cv5512.docx",
        expected_subject=Subject.PHYSICS,
        expected_category=DocumentCategory.LESSON_PLAN,
        expected_grade=GradeLevel.GRADE_12,
        expected_min_questions=0,
        expected_is_spoofed=False,
        notes="Giáo án Kế hoạch bài dạy CV 5512 Vật lý",
    ),
    GoldenExamAnnotation(
        file_name="hop_dong_dich_vu_cntt.docx",
        expected_subject=Subject.NON_ACADEMIC,
        expected_category=DocumentCategory.ADMIN_CONTRACT,
        expected_grade=GradeLevel.UNKNOWN,
        expected_min_questions=0,
        expected_is_spoofed=False,
        notes="Hợp đồng pháp lý không thuộc học thuật",
    ),
    GoldenExamAnnotation(
        file_name="ielts_reading_cambridge_18.pdf",
        expected_subject=Subject.MATHEMATICS,  # Content is actually Math (anti-spoof test)
        expected_category=DocumentCategory.EXAM_TEST,
        expected_grade=GradeLevel.GRADE_12,
        expected_min_questions=8,
        expected_is_spoofed=True,
        notes="Tệp giả mạo IELTS nhưng ruột là Toán THPT",
    ),
    GoldenExamAnnotation(
        file_name="japanese_jlpt_n2_mondai.pdf",
        expected_subject=Subject.JAPANESE,
        expected_category=DocumentCategory.EXAM_TEST,
        expected_grade=GradeLevel.GENERAL_ACADEMIC,
        expected_min_questions=4,
        expected_is_spoofed=False,
        notes="Đề thi Tiếng Nhật JLPT N2",
    ),
]


@dataclass
class EpochMetrics:
    """Performance metrics evaluated during a single training epoch."""
    epoch_index: int
    subject_accuracy: float
    category_accuracy: float
    spoof_accuracy: float
    question_pass_rate: float
    total_loss: float
    duration_ms: float
    weight_adjustments_count: int = 0


@dataclass
class CalibrationState:
    """Trained / Calibrated weights structure."""
    version: str = "2.0.0"
    last_trained_timestamp: float = 0.0
    total_epochs_trained: int = 0
    final_loss: float = 0.0
    subject_weight_multipliers: Dict[str, float] = field(default_factory=dict)
    keyword_boosts: Dict[str, float] = field(default_factory=dict)
    confidence_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "subject_min_score": 3.0,
        "high_confidence_margin": 12.0,
        "spoof_divergence_ratio": 0.35,
    })


class DocInspectorTrainer:
    """
    Multi-Epoch Heuristic Trainer for DocInspector.
    Executes multiple training cycles, backpropagating heuristic corrections
    into keyword weight tables and decision parameters.
    """

    def __init__(self, corpus: Optional[List[GoldenExamAnnotation]] = None):
        self.corpus = corpus or DEFAULT_BENCHMARK_CORPUS
        self.state = self._load_or_init_state()
        self.history: List[EpochMetrics] = []

    @classmethod
    def _load_or_init_state(cls) -> CalibrationState:
        """Load persistent calibration state or initialize fresh."""
        if WEIGHTS_PATH.exists():
            try:
                data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
                return CalibrationState(
                    version=data.get("version", "2.0.0"),
                    last_trained_timestamp=data.get("last_trained_timestamp", 0.0),
                    total_epochs_trained=data.get("total_epochs_trained", 0),
                    final_loss=data.get("final_loss", 0.0),
                    subject_weight_multipliers=data.get("subject_weight_multipliers", {}),
                    keyword_boosts=data.get("keyword_boosts", {}),
                    confidence_thresholds=data.get("confidence_thresholds", {}),
                )
            except Exception:
                pass

        # Fresh default multipliers
        mults = {subj: 1.0 for subj in SUBJECT_LEXICONS}
        return CalibrationState(subject_weight_multipliers=mults)

    def save_state(self) -> None:
        """Save current calibration state to disk."""
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self.state)
        WEIGHTS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def save_history(self) -> None:
        """Save epoch-by-epoch training logs to disk."""
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(e) for e in self.history]
        HISTORY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def run_training(self, epochs: int = 5, learning_rate: float = 0.08, verbose: bool = True) -> List[EpochMetrics]:
        """
        Execute multi-epoch training and parameter tuning loop.
        """
        if verbose:
            print("=" * 80)
            print(f"🚀 BẮT ĐẦU QUÁ TRÌNH TRAINING ĐA EPOCH (MULTI-EPOCH CALIBRATION ENGINE)")
            print(f"   Số tệp mẫu Benchmark: {len(self.corpus)} | Số Epochs huấn luyện: {epochs}")
            print(f"   Mục tiêu: Đạt chuẩn AI mà 100% Thuật toán minh bạch, $0 API Cost")
            print("=" * 80)

        for epoch in range(1, epochs + 1):
            t_start = time.perf_counter()
            correct_subjects = 0
            correct_categories = 0
            correct_spoofs = 0
            passed_questions = 0
            adjustments = 0

            # 1. Run inference across entire corpus
            for item in self.corpus:
                file_path = SAMPLES_DIR / item.file_name
                if not file_path.exists():
                    continue

                report = DocumentInspector.inspect(str(file_path))

                # Subject evaluation
                is_subj_correct = (report.detected_subject == item.expected_subject)
                if is_subj_correct:
                    correct_subjects += 1
                else:
                    # Heuristic Gradient Correction:
                    # Penalize wrongly predicted subject multiplier, boost ground truth subject
                    wrong_subj = report.detected_subject.name
                    target_subj = item.expected_subject.name
                    
                    curr_wrong = self.state.subject_weight_multipliers.get(wrong_subj, 1.0)
                    self.state.subject_weight_multipliers[wrong_subj] = max(0.4, curr_wrong - learning_rate)

                    curr_target = self.state.subject_weight_multipliers.get(target_subj, 1.0)
                    self.state.subject_weight_multipliers[target_subj] = min(2.5, curr_target + learning_rate * 1.5)
                    adjustments += 1

                # Category evaluation
                if report.document_category == item.expected_category:
                    correct_categories += 1

                # Anti-Spoof evaluation
                if report.is_spoofed_filename == item.expected_is_spoofed:
                    correct_spoofs += 1
                else:
                    # Tune spoof divergence ratio
                    if not report.is_spoofed_filename and item.expected_is_spoofed:
                        self.state.confidence_thresholds["spoof_divergence_ratio"] *= 0.95
                        adjustments += 1

                # Question Itemization evaluation
                q_count = report.pass2.question_count if hasattr(report.pass2, "question_count") else 0
                if q_count >= item.expected_min_questions:
                    passed_questions += 1

            total_items = max(1, len(self.corpus))
            s_acc = correct_subjects / total_items
            c_acc = correct_categories / total_items
            sp_acc = correct_spoofs / total_items
            q_acc = passed_questions / total_items

            # Multi-objective Loss Function
            loss = 1.0 - (0.45 * s_acc + 0.25 * c_acc + 0.20 * sp_acc + 0.10 * q_acc)
            duration_ms = (time.perf_counter() - t_start) * 1000

            metrics = EpochMetrics(
                epoch_index=epoch,
                subject_accuracy=round(s_acc * 100, 1),
                category_accuracy=round(c_acc * 100, 1),
                spoof_accuracy=round(sp_acc * 100, 1),
                question_pass_rate=round(q_acc * 100, 1),
                total_loss=round(loss, 4),
                duration_ms=round(duration_ms, 1),
                weight_adjustments_count=adjustments,
            )
            self.history.append(metrics)

            if verbose:
                bar_len = 20
                filled = int(round(bar_len * (1.0 - loss)))
                bar = "█" * filled + "░" * (bar_len - filled)
                print(
                    f"Epoch {epoch:2d}/{epochs:2d} [{bar}] "
                    f"Loss: {loss:.4f} | "
                    f"Subj Acc: {metrics.subject_accuracy:5.1f}% | "
                    f"Spoof Acc: {metrics.spoof_accuracy:5.1f}% | "
                    f"Adj: {adjustments:2d} | "
                    f"{duration_ms:5.1f}ms"
                )

        # Update final state
        self.state.last_trained_timestamp = time.time()
        self.state.total_epochs_trained += epochs
        self.state.final_loss = self.history[-1].total_loss if self.history else 0.0

        self.save_state()
        self.save_history()

        if verbose:
            print("-" * 80)
            final = self.history[-1]
            print(f"✨ HOÀN TẤT HUẤN LUYỆN: Loss cuối cùng = {final.total_loss:.4f}")
            print(f"   - Độ chính xác Môn học: {final.subject_accuracy}%")
            print(f"   - Độ chính xác Phân loại: {final.category_accuracy}%")
            print(f"   - Độ chính xác Chống giả mạo: {final.spoof_accuracy}%")
            print(f"   - Tệp trọng số tối ưu đã lưu: '{WEIGHTS_PATH}'")
            print("=" * 80)

        return self.history
