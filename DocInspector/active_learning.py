"""
Active Learning & Continuous Calibration Engine for DocInspector.
"TRAINING LIÊN TỤC TỪ PHẢN HỒI NGƯỜI DÙNG"
Collects corrections/feedback from users or Discord moderators,
stores them into active_learning_samples.json, and executes incremental calibration epochs.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Subject
from .trainer import DocInspectorTrainer, GoldenExamAnnotation, SAMPLES_DIR

FEEDBACK_SAMPLES_FILE = Path("D:/Project/DocInspector/active_learning_samples.json")


@dataclass
class UserCorrectionFeedback:
    """Feedback submitted by a user or moderator."""
    file_name: str
    corrected_subject: str
    previous_subject: str
    timestamp: float
    user_name: str = "Anonymous"
    notes: str = ""
    text_snippet: str = ""


class ActiveLearningEngine:
    """Manages online learning and incremental calibration from user feedback."""

    @classmethod
    def load_feedback_samples(cls) -> List[UserCorrectionFeedback]:
        """Load all accumulated active learning feedback samples."""
        if not FEEDBACK_SAMPLES_FILE.exists():
            return []
        try:
            data = json.loads(FEEDBACK_SAMPLES_FILE.read_text(encoding="utf-8"))
            return [UserCorrectionFeedback(**item) for item in data]
        except Exception:
            return []

    @classmethod
    def record_feedback(
        cls,
        file_name: str,
        corrected_subject: str,
        previous_subject: str,
        user_name: str = "User",
        notes: str = "",
        text_snippet: str = "",
        auto_retrain: bool = True,
    ) -> Dict[str, Any]:
        """
        Record user correction and optionally trigger an incremental 1-epoch calibration.
        """
        feedbacks = cls.load_feedback_samples()
        entry = UserCorrectionFeedback(
            file_name=file_name,
            corrected_subject=corrected_subject.upper(),
            previous_subject=previous_subject.upper(),
            timestamp=time.time(),
            user_name=user_name,
            notes=notes,
            text_snippet=text_snippet[:1000],
        )
        feedbacks.append(entry)

        FEEDBACK_SAMPLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        FEEDBACK_SAMPLES_FILE.write_text(
            json.dumps([asdict(f) for f in feedbacks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        retrain_result = None
        if auto_retrain:
            retrain_result = cls.trigger_incremental_training()

        return {
            "status": "RECORDED",
            "total_feedbacks": len(feedbacks),
            "entry": asdict(entry),
            "retrain_metrics": retrain_result,
        }

    @classmethod
    def trigger_incremental_training(cls) -> Optional[Dict[str, Any]]:
        """Run 1 fast epoch of calibration including both default corpus and user corrections."""
        feedbacks = cls.load_feedback_samples()
        trainer = DocInspectorTrainer()

        # Update training weights directly based on feedback
        # Penalize false positive, boost true subject
        state = trainer.state
        for fb in feedbacks[-5:]:  # Look at recent corrections
            target_s = fb.corrected_subject
            prev_s = fb.previous_subject
            if target_s in state.subject_weight_multipliers:
                state.subject_weight_multipliers[target_s] = min(
                    2.8, state.subject_weight_multipliers[target_s] + 0.12
                )
            if prev_s in state.subject_weight_multipliers:
                state.subject_weight_multipliers[prev_s] = max(
                    0.3, state.subject_weight_multipliers[prev_s] - 0.08
                )

        state.last_trained_timestamp = time.time()
        state.total_epochs_trained += 1
        trainer.save_state()

        # Run 1 validation cycle
        metrics = trainer.run_training(epochs=1, learning_rate=0.03, verbose=False)
        return asdict(metrics[0]) if metrics else None
