"""
Unit & Integration Tests for Smart Pipeline, Explainability, and Multi-Epoch Trainer.
Tests natural, transparent, non-AI document intelligence and training loops.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from DocInspector.core import DocumentInspector
from DocInspector.explainability import ExplainabilityEngine, TransparencyAuditDossier
from DocInspector.gdrive_handler import GDriveDocumentHandler
from DocInspector.models import GradeLevel, Subject
from DocInspector.smart_pipeline import SmartDocumentPipeline
from DocInspector.trainer import (
    DEFAULT_BENCHMARK_CORPUS,
    DocInspectorTrainer,
    HISTORY_PATH,
    WEIGHTS_PATH,
)

SAMPLES_DIR = Path("D:/Project/DocInspector/samples")


class TestSmartPipelineAndTrainer(unittest.TestCase):
    """Test suite for Smart Document Pipeline, Explainability, and Training Harness."""

    def test_01_explainability_dossier_generation(self):
        """Verify that an explainability dossier is properly constructed with evidence tokens."""
        sample_chem = SAMPLES_DIR / "de_hoa_hoc_huu_co_thpt.pdf"
        self.assertTrue(sample_chem.exists(), "Sample chem file must exist")

        rep = DocumentInspector.inspect(str(sample_chem))
        dossier = ExplainabilityEngine.generate_dossier(rep)

        self.assertIsInstance(dossier, TransparencyAuditDossier)
        self.assertEqual(dossier.subject_trail.chosen_subject, Subject.CHEMISTRY)
        self.assertGreater(dossier.subject_trail.top_score, 0.0)
        self.assertGreaterEqual(len(dossier.subject_trail.evidence_tokens), 1)

        # Check markdown presentation
        md = dossier.to_markdown()
        self.assertIn("HỒ SƠ BẠCH HÓA", md)
        self.assertIn("Hóa học", md)
        self.assertIn("Bảng trọng số từ khóa", md)

    def test_02_gdrive_url_detection_and_id_extraction(self):
        """Verify Google Drive and Docs URL detection and ID parsing."""
        gdrive_url = "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view?usp=sharing"
        gdocs_url = "https://docs.google.com/document/d/1cE2Z_sample_doc_id_999888777/edit"
        fake_url = "https://example.com/normal.pdf"

        self.assertTrue(GDriveDocumentHandler.is_gdrive_url(gdrive_url))
        self.assertTrue(GDriveDocumentHandler.is_gdrive_url(gdocs_url))
        self.assertFalse(GDriveDocumentHandler.is_gdrive_url(fake_url))

        fid = GDriveDocumentHandler.extract_file_id(gdrive_url)
        self.assertEqual(fid, "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

    def test_03_multi_epoch_training_loop(self):
        """Verify the multi-epoch training harness runs, adjusts weights, and logs history."""
        trainer = DocInspectorTrainer()
        epochs_to_run = 3
        history = trainer.run_training(epochs=epochs_to_run, learning_rate=0.05, verbose=False)

        self.assertEqual(len(history), epochs_to_run)
        self.assertTrue(WEIGHTS_PATH.exists(), "calibration_weights.json must be saved")
        self.assertTrue(HISTORY_PATH.exists(), "training_history.json must be saved")

        # Verify weights JSON structure
        calib_data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
        self.assertIn("subject_weight_multipliers", calib_data)
        self.assertGreater(len(calib_data["subject_weight_multipliers"]), 5)

        # Verify history JSON structure
        hist_data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(hist_data), epochs_to_run)
        self.assertIn("total_loss", hist_data[0])

    def test_04_smart_pipeline_end_to_end_pdf(self):
        """Verify end-to-end processing of PDF via SmartDocumentPipeline."""
        sample_pdf = SAMPLES_DIR / "de_hoa_hoc_huu_co_thpt.pdf"
        result = SmartDocumentPipeline.process(str(sample_pdf))

        self.assertEqual(result.source_type, "PDF")
        self.assertFalse(result.is_google_drive)
        self.assertEqual(result.report.detected_subject, Subject.CHEMISTRY)
        self.assertGreater(result.total_questions, 0)
        self.assertIsNotNone(result.dossier)
        self.assertIn("HỒ SƠ BẠCH HÓA", result.to_markdown())

    def test_05_smart_pipeline_end_to_end_word(self):
        """Verify end-to-end processing of Word DOCX via SmartDocumentPipeline."""
        sample_docx = SAMPLES_DIR / "de_sinh_hoc_di_truyen.docx"
        result = SmartDocumentPipeline.process(str(sample_docx))

        self.assertEqual(result.source_type, "WORD")
        self.assertFalse(result.is_google_drive)
        self.assertEqual(result.report.detected_subject, Subject.BIOLOGY)
        self.assertGreater(result.total_questions, 0)
        self.assertIsNotNone(result.dossier)

    def test_06_anti_spoofing_in_pipeline(self):
        """Verify that spoofed files are caught and transparently explained in dossier."""
        sample_spoof = SAMPLES_DIR / "ielts_reading_cambridge_18.pdf"
        result = SmartDocumentPipeline.process(str(sample_spoof))

        self.assertTrue(result.is_spoofed, "File should be flagged as spoofed")
        self.assertEqual(result.report.detected_subject, Subject.MATHEMATICS)
        md = result.to_markdown()
        self.assertIn("CẢNH BÁO GIẢ MẠO TÊN TỆP", md)


if __name__ == "__main__":
    unittest.main()
