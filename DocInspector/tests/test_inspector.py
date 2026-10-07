"""
Unit test suite for DocInspector.
Tests 100% deterministic accuracy, spoof detection, and latency thresholds.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from DocInspector.core import DocumentInspector
from DocInspector.models import DocumentCategory, ExamType, Subject, VerificationVerdict


class TestDocInspector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples_dir = Path(__file__).parent.parent / "samples"
        if not cls.samples_dir.exists() or not list(cls.samples_dir.glob("*")):
            from DocInspector.generate_samples import generate_all_samples
            generate_all_samples(cls.samples_dir)

    def test_spoofed_ielts_is_actually_math(self):
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        
        self.assertEqual(report.document_category, DocumentCategory.EXAM_TEST)
        self.assertEqual(report.detected_subject, Subject.MATHEMATICS)
        self.assertEqual(report.exam_type, ExamType.MCQ_STANDARD_4)
        self.assertTrue(report.is_spoofed_filename)
        self.assertIn("ielts", report.spoof_details.lower())
        self.assertIn("mathematics", report.spoof_details.lower())
        self.assertTrue(report.pass2.has_answer_keys)
        self.assertGreaterEqual(report.pass2.question_count, 10)
        self.assertEqual(report.pass3.triple_verification_status, "PASSED_TRIPLE_CONSENSUS_100%")

    def test_spoofed_math_is_actually_competitive_programming(self):
        f = self.samples_dir / "de_toan_chuyen_hsg.docx"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.document_category, DocumentCategory.EXAM_TEST)
        self.assertEqual(report.detected_subject, Subject.INFORMATICS)
        self.assertEqual(report.exam_type, ExamType.COMPETITIVE_PROGRAMMING)
        self.assertTrue(report.is_spoofed_filename)
        self.assertIn("toan", report.spoof_details.lower())
        self.assertIn("informatics", report.spoof_details.lower())
        self.assertIn("time_limit", report.pass2.competitive_meta)
        self.assertIn("memory_limit", report.pass2.competitive_meta)

    def test_specialized_english(self):
        f = self.samples_dir / "de_chuyen_anh_quoc_gia.pdf"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.document_category, DocumentCategory.EXAM_TEST)
        self.assertEqual(report.detected_subject, Subject.ENGLISH)
        self.assertEqual(report.exam_type, ExamType.SPECIALIZED_ENGLISH)
        self.assertFalse(report.is_spoofed_filename)

    def test_japanese_jlpt(self):
        f = self.samples_dir / "japanese_jlpt_n2_mondai.pdf"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.detected_language, "JAPANESE")
        self.assertEqual(report.detected_subject, Subject.JAPANESE)
        self.assertEqual(report.exam_type, ExamType.JLPT_TEST)
        self.assertFalse(report.is_spoofed_filename)

    def test_lesson_plan_cv5512(self):
        f = self.samples_dir / "giao_an_vat_ly_12_cv5512.docx"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.document_category, DocumentCategory.LESSON_PLAN)
        self.assertEqual(report.detected_subject, Subject.PHYSICS)
        self.assertFalse(report.is_spoofed_filename)

    def test_admin_contract(self):
        f = self.samples_dir / "hop_dong_dich_vu_cntt.docx"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.document_category, DocumentCategory.ADMIN_CONTRACT)
        self.assertFalse(report.is_spoofed_filename)

    def test_chemistry_exam(self):
        f = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.document_category, DocumentCategory.EXAM_TEST)
        self.assertEqual(report.detected_subject, Subject.CHEMISTRY)
        self.assertFalse(report.is_spoofed_filename)

    def test_biology_exam(self):
        f = self.samples_dir / "de_sinh_hoc_di_truyen.docx"
        report = DocumentInspector.inspect(f)

        self.assertEqual(report.document_category, DocumentCategory.EXAM_TEST)
        self.assertEqual(report.detected_subject, Subject.BIOLOGY)
        self.assertFalse(report.is_spoofed_filename)

    def test_execution_speed_latency(self):
        """All inspection runs must execute in under 500ms per document (sub-second Non-AI)."""
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        self.assertLess(report.total_execution_time_ms, 500.0)

    def test_json_export_structure(self):
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        d = report.to_dict()
        self.assertIn("pass1_technical", d)
        self.assertIn("pass2_structural", d)
        self.assertIn("pass3_lexical_verification", d)
        self.assertEqual(d["is_spoofed_filename"], True)

    def test_cognitive_levels_and_difficulty(self):
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        cb = report.pass2.cognitive_breakdown
        self.assertGreater(cb.recognition_count + cb.comprehension_count + cb.application_count + cb.high_application_count, 0)
        self.assertGreaterEqual(cb.estimated_difficulty_index, 1.0)
        self.assertLessEqual(cb.estimated_difficulty_index, 10.0)

    def test_html_and_csv_reports(self):
        from DocInspector.reporting import DocumentReporter
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        
        test_html = self.samples_dir / "test_report.html"
        test_csv = self.samples_dir / "test_summary.csv"

        hp = DocumentReporter.generate_html_report(report, test_html)
        self.assertTrue(hp.exists())
        self.assertGreater(hp.stat().st_size, 500)

        cp = DocumentReporter.export_batch_csv([report], test_csv)
        self.assertTrue(cp.exists())
        self.assertGreater(cp.stat().st_size, 50)

        # Cleanup test exports
        test_html.unlink(missing_ok=True)
        test_csv.unlink(missing_ok=True)


    def test_difficulty_assessment(self):
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        diff = report.difficulty_assessment
        self.assertGreaterEqual(diff.score, 1.0)
        self.assertLessEqual(diff.score, 10.0)
        self.assertIn("Mức", diff.tier_label_vi)
        self.assertGreater(diff.recommended_duration_minutes, 0)
        self.assertGreater(diff.pace_seconds_per_question, 0.0)

    def test_user_requirements_qualification(self):
        from DocInspector.validator import RequirementValidator
        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        f_spoofed = self.samples_dir / "ielts_reading_cambridge_18.pdf"

        req_thpt = RequirementValidator.get_preset("thpt_graduation")

        # Chemistry exam should meet THPT graduation requirements
        rep_chem = DocumentInspector.inspect(f_chem, requirements=req_thpt)
        self.assertIsNotNone(rep_chem.requirement_audit)
        self.assertTrue(rep_chem.requirement_audit.is_eligible)
        self.assertEqual(rep_chem.requirement_audit.status_label_vi, "ĐẠT YÊU CẦU")

        # Spoofed file must FAIL strict anti-spoofing in THPT graduation
        rep_spoofed = DocumentInspector.inspect(f_spoofed, requirements=req_thpt)
        self.assertIsNotNone(rep_spoofed.requirement_audit)
        self.assertFalse(rep_spoofed.requirement_audit.is_eligible)
        self.assertEqual(rep_spoofed.requirement_audit.status_label_vi, "KHÔNG ĐẠT YÊU CẦU")
        self.assertGreater(len(rep_spoofed.requirement_audit.recommendations), 0)


    def test_sub_topic_detection(self):
        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report = DocumentInspector.inspect(f_chem)
        self.assertGreater(len(report.pass3.sub_topics), 0)
        topic_codes = [t.topic_code for t in report.pass3.sub_topics]
        self.assertIn("CHEM_ORGANIC_ESTERS_LIPIDS", topic_codes)
        self.assertGreater(report.pass3.sub_topics[0].percentage, 0.0)

    def test_quality_health_audit(self):
        f = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        report = DocumentInspector.inspect(f)
        qa = report.quality_audit
        self.assertGreaterEqual(qa.overall_score, 0.0)
        self.assertLessEqual(qa.overall_score, 100.0)
        self.assertIn(qa.grade.value, ["A+", "A", "B", "C", "D"])
        self.assertGreaterEqual(qa.question_completeness_rate, 0.0)
        self.assertGreaterEqual(qa.answer_coverage_rate, 0.0)

    def test_url_detector_and_bot_block_unknown_origin(self):
        from unittest.mock import MagicMock, patch
        from DocInspector.url_fetcher import UrlBlockedOrUnknownOriginError, UrlDocumentFetcher
        import urllib.error

        # 1. Test URL pattern detection
        self.assertTrue(UrlDocumentFetcher.is_url("https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OIvE2up00/view"))
        self.assertTrue(UrlDocumentFetcher.is_url("http://hocmai.vn/de-thi-toan-thpt-2025.pdf"))
        self.assertFalse(UrlDocumentFetcher.is_url("C:\\Users\\admin\\Documents\\de_toan.pdf"))

        # 2. Simulate Cloudflare / Anti-bot challenge response
        bot_challenge_html = b"""
        <html>
        <head><title>Attention Required! | Cloudflare</title></head>
        <body>
            <h2>Please verify you are human</h2>
            <div class="cf-browser-verification">Just a moment...</div>
        </body>
        </html>
        """

        mock_resp = MagicMock()
        mock_resp.read.return_value = bot_challenge_html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            report = DocumentInspector.inspect("https://protected-site.edu.vn/de-thi-vip.pdf")
            self.assertEqual(report.confidence_score, 0.0)
            self.assertTrue(report.is_spoofed_filename)
            self.assertIn("không rõ nguồn gốc", report.human_summary.lower())

        # 3. Simulate HTTP 403 Forbidden
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 403, "Forbidden", {}, None)):
            report = DocumentInspector.inspect("https://secret-bank.edu.vn/private_test.pdf")
            self.assertEqual(report.confidence_score, 0.0)
            self.assertIn("không rõ nguồn gốc", report.human_summary.lower())

    def test_url_fetch_valid_pdf_stream(self):
        from unittest.mock import MagicMock, patch

        # Read actual PDF bytes from local sample
        pdf_path = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        mock_resp = MagicMock()
        mock_resp.read.return_value = pdf_bytes
        mock_resp.headers = {"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="online_test_math.pdf"'}
        mock_resp.geturl.return_value = "https://cdn.school.vn/files/online_test_math.pdf"
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            report = DocumentInspector.inspect("https://cdn.school.vn/files/online_test_math.pdf")
            self.assertEqual(report.document_category, DocumentCategory.EXAM_TEST)
            self.assertEqual(report.detected_subject, Subject.MATHEMATICS)
            self.assertGreater(report.pass2.question_count, 0)
            self.assertEqual(report.pass3.triple_verification_status, "PASSED_TRIPLE_CONSENSUS_100%")

    def test_verdict_case_1_verified_ok(self):
        f = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report = DocumentInspector.inspect(f)
        self.assertEqual(report.verdict, VerificationVerdict.VERIFIED_OK)
        self.assertEqual(report.verdict_label_vi, "Xác minh (thấy ổn)")
        self.assertIn("XÁC MINH (THẤY ỔN)", report.verdict_rationale)

    def test_verdict_case_2_uncertain_match(self):
        # Academic text about chemistry formulas without questions or exam structure
        content = (
            "TÀI LIỆU LÝ THUYẾT VÀ BÀI TẬP TỰ LUYỆN:\n"
            "Este là hợp chất hữu cơ sinh ra khi thay nhóm OH ở axit cacboxylic bằng nhóm OR. "
            "Lipit là este phức tạp bao gồm chất béo, sáp, photpholipit."
        ).encode("utf-8")
        report = DocumentInspector.inspect(content, file_name="ly_thuyet_hoa.txt")
        self.assertEqual(report.verdict, VerificationVerdict.UNCERTAIN_MATCH)
        self.assertEqual(report.verdict_label_vi, "Chưa rõ ràng (là xác minh nhưng chưa chắc là đúng đề)")
        self.assertIn("CHƯA RÕ RÀNG", report.verdict_rationale)

    def test_verdict_case_3_unidentified_exam(self):
        # Unmistakable exam structure with questions and choices, but zero subject keywords
        content = (
            "ĐỀ THI KIỂM TRA ĐÁNH GIÁ NĂNG LỰC TƯ DUY TỔNG HỢP\n"
            "Thời gian làm bài: 45 phút\n\n"
            "Câu 1: Hình nào sau đây phù hợp với quy luật tiếp theo của dãy hình mẫu?\n"
            "A. Hình tròn màu xanh\n"
            "B. Hình vuông màu đỏ\n"
            "C. Hình tam giác màu vàng\n"
            "D. Hình ngôi sao năm cánh\n\n"
            "Câu 2: Số tiếp theo trong dãy số quy luật là số nào?\n"
            "A. 100\n"
            "B. 120\n"
            "C. 150\n"
            "D. 200\n\n"
            "BẢNG ĐÁP ÁN: 1.A 2.B"
        ).encode("utf-8")
        report = DocumentInspector.inspect(content, file_name="de_thi_logic_iq.txt")
        self.assertEqual(report.verdict, VerificationVerdict.UNIDENTIFIED_EXAM)
        self.assertEqual(report.verdict_label_vi, "Không rõ ràng (xem được đề nhưng không biết là đề nào)")
        self.assertIn("KHÔNG RÕ RÀNG", report.verdict_rationale)

    def test_verdict_case_4_unverifiable_failed(self):
        from unittest.mock import patch
        import urllib.error

        # 4a: Blocked URL
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 403, "Forbidden", {}, None)):
            report_url = DocumentInspector.inspect("https://secret.edu.vn/blocked.pdf")
            self.assertEqual(report_url.verdict, VerificationVerdict.UNVERIFIABLE_FAILED)
            self.assertEqual(report_url.verdict_label_vi, "Không xác minh (là ko đc j hết)")
            self.assertIn("KHÔNG XÁC MINH", report_url.verdict_rationale)

        # 4b: Empty file stream
        report_empty = DocumentInspector.inspect(b"", file_name="empty_test.pdf")
        self.assertEqual(report_empty.verdict, VerificationVerdict.UNVERIFIABLE_FAILED)
        self.assertEqual(report_empty.verdict_label_vi, "Không xác minh (là ko đc j hết)")
        self.assertIn("KHÔNG XÁC MINH", report_empty.verdict_rationale)

    def test_channel_auto_detector(self):
        from DocInspector.channel_manager import ChannelAutoDetector

        p_math = ChannelAutoDetector.detect_channel_profile("de-on-thi-mon-toan-12")
        self.assertIn(Subject.MATHEMATICS, p_math.allowed_subjects)

        p_tin = ChannelAutoDetector.detect_channel_profile("#chuyen-tin-hsg-quoc-gia")
        self.assertIn(Subject.INFORMATICS, p_tin.allowed_subjects)

        p_khtn = ChannelAutoDetector.detect_channel_profile("khoa-hoc-tu-nhien-thcs")
        self.assertIn(Subject.PHYSICS, p_khtn.allowed_subjects)
        self.assertIn(Subject.CHEMISTRY, p_khtn.allowed_subjects)
        self.assertIn(Subject.BIOLOGY, p_khtn.allowed_subjects)

        p_giaoan = ChannelAutoDetector.detect_channel_profile("#giao-an-cv5512")
        self.assertEqual(p_giaoan.required_category, DocumentCategory.LESSON_PLAN)

        p_wild = ChannelAutoDetector.detect_channel_profile("#tai-lieu-tong-hop")
        self.assertTrue(p_wild.is_wildcard)

    def test_channel_compliance_matching(self):
        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report = DocumentInspector.inspect(f_chem, channel="#de-hoa")
        self.assertIsNotNone(report.channel_compliance)
        self.assertTrue(report.channel_compliance.is_compliant)
        self.assertIn("HỢP LỆ VÀ ĐÚNG KÊNH", report.channel_compliance.bot_reply_formatted)

    def test_channel_compliance_mismatch_and_suggestions(self):
        # Post Chemistry exam into Math channel #de-toan
        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report = DocumentInspector.inspect(f_chem, channel="#de-toan")
        self.assertIsNotNone(report.channel_compliance)
        self.assertFalse(report.channel_compliance.is_compliant)
        self.assertIn("de-hoa", report.channel_compliance.suggested_channels)
        self.assertIn("CẢNH BÁO ĐĂNG SAI KÊNH", report.channel_compliance.warning_message)
        self.assertIn("SAI KÊNH #de-toan", report.human_summary)

    def test_bot_inspector_adapter_in_channel(self):
        from DocInspector.channel_manager import BotInspectorAdapter

        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report = BotInspectorAdapter.inspect_in_channel(f_chem, channel_name="de-hoa")
        self.assertEqual(report.detected_subject, Subject.CHEMISTRY)
        self.assertTrue(report.channel_compliance.is_compliant)


    def test_category_folder_and_directory_manager(self):
        from DocInspector.channel_manager import (
            DEFAULT_TARGET_CATEGORY_ID,
            CategoryDirectoryManager,
            BotInspectorAdapter,
        )

        cat_id = "1534147951797080174"
        self.assertEqual(DEFAULT_TARGET_CATEGORY_ID, cat_id)
        self.assertTrue(CategoryDirectoryManager.is_target_category(1534147951797080174))
        self.assertTrue(CategoryDirectoryManager.is_target_category("1534147951797080174"))
        self.assertFalse(CategoryDirectoryManager.is_target_category("999999999999999999"))

        # Test tree formatting
        channels = ["de-toan", "chuyen-tin", "khoa-hoc-tu-nhien", "tai-lieu-chung"]
        tree = CategoryDirectoryManager.format_category_tree(channels, category_name="Kho Đề THPT", category_id=cat_id)
        self.assertIn("1534147951797080174", tree)
        self.assertIn("Toán học", tree)
        self.assertIn("Tin học", tree)
        self.assertIn("Khoa học tự nhiên", tree)

        # Test inspection inside category
        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        report_ok = BotInspectorAdapter.inspect_in_channel(f_chem, channel_name="de-hoa", category_id=cat_id)
        self.assertEqual(report_ok.channel_compliance.category_id, cat_id)
        self.assertTrue(report_ok.channel_compliance.is_compliant)

        # Test mismatch inside category
        report_mismatch = BotInspectorAdapter.inspect_in_channel(f_chem, channel_name="de-toan", category_id=cat_id)
        self.assertEqual(report_mismatch.channel_compliance.category_id, cat_id)
        self.assertFalse(report_mismatch.channel_compliance.is_compliant)
        self.assertIn("1534147951797080174", report_mismatch.channel_compliance.bot_reply_formatted)
        self.assertIn("de-hoa", report_mismatch.channel_compliance.suggested_channels)


    def test_exam_track_classification_thuong_hsg_chuyen(self):
        from DocInspector.models import ExamTrackTier
        from DocInspector.channel_manager import ChannelProfile

        # 1. Chuyên Tin / Olympic CP must be 'chuyen'
        f_tin = self.samples_dir / "de_toan_chuyen_hsg.docx"
        rep_chuyen = DocumentInspector.inspect(f_tin)
        self.assertEqual(rep_chuyen.exam_track, ExamTrackTier.CHUYEN)
        self.assertEqual(rep_chuyen.exam_track_label_vi, "chuyên")

        # 2. Regular exam must be 'thuong'
        f_chem = self.samples_dir / "de_hoa_hoc_huu_co_thpt.pdf"
        rep_chem = DocumentInspector.inspect(f_chem)
        self.assertEqual(rep_chem.exam_track, ExamTrackTier.THUONG)
        self.assertEqual(rep_chem.exam_track_label_vi, "thường")

        # 3. International exam (tiếng Việt hoặc quốc tế: IKMC, Kangaroo, SASMO, IMO, TIMO, SAT)
        from DocInspector.track_classifier import ExamTrackClassifier
        from DocInspector.models import DifficultyAssessment, DifficultyTier, Pass1Report, Pass2Report, Pass3Report, DocumentCategory, ExamType
        dummy_p1 = Pass1Report("PDF", "", False, False, 5, 1200, "VI", "LATIN")
        dummy_p2 = Pass2Report(25, 100, "MCQ", False, False)
        dummy_p3 = Pass3Report()
        diff_base = DifficultyAssessment(score=7.0, tier=DifficultyTier.TIER_3_ADVANCED)

        # 3a. Quốc tế bằng tiếng Việt
        tr_quoc_te_vi, lbl_qt_vi, _ = ExamTrackClassifier.classify(
            raw_text="Kỳ thi Toán quốc tế Kangaroo IKMC 2025 - Bản dịch Tiếng Việt chính thức dành cho học sinh Việt Nam.",
            filename="De_Thi_Toan_Quoc_Te_Kangaroo_IKMC_2025_Tieng_Viet.pdf",
            category=DocumentCategory.EXAM_TEST,
            exam_type=ExamType.MCQ_STANDARD_4,
            subject=Subject.MATHEMATICS,
            pass1=dummy_p1, pass2=dummy_p2, pass3=dummy_p3, diff=diff_base,
        )
        self.assertEqual(tr_quoc_te_vi, ExamTrackTier.QUOC_TE)
        self.assertEqual(lbl_qt_vi, "quốc tế")

        # 3b. Quốc tế bằng tiếng Anh (IMO / SASMO / TIMO / SAT)
        tr_quoc_te_en, lbl_qt_en, _ = ExamTrackClassifier.classify(
            raw_text="International Mathematical Olympiad IMO Shortlist Problems with Solutions.",
            filename="IMO_Shortlist_Problems.pdf",
            category=DocumentCategory.EXAM_TEST,
            exam_type=ExamType.MCQ_STANDARD_4,
            subject=Subject.MATHEMATICS,
            pass1=dummy_p1, pass2=dummy_p2, pass3=dummy_p3, diff=diff_base,
        )
        self.assertEqual(tr_quoc_te_en, ExamTrackTier.QUOC_TE)
        self.assertEqual(lbl_qt_en, "quốc tế")

        # 4. Đề chung (tài liệu ôn tập tổng hợp / đề cương / lý thuyết dễ gây hiểu lầm)
        tr_chung, lbl_chung, _ = ExamTrackClassifier.classify(
            raw_text="Tài liệu tổng hợp kiến thức và đề cương ôn tập chung cho tất cả các khối.",
            filename="Tai_Lieu_Tong_Hop_Kien_Thuc_Va_De_Cuong_Chung.pdf",
            category=DocumentCategory.THEORY_SYLLABUS,
            exam_type=ExamType.NOT_AN_EXAM,
            subject=Subject.GENERAL,
            pass1=dummy_p1, pass2=Pass2Report(0, 0, "NONE", False, False), pass3=dummy_p3, diff=diff_base,
        )
        self.assertEqual(tr_chung, ExamTrackTier.CHUNG)
        self.assertEqual(lbl_chung, "chung")

        # 5. Track-restricted channel mismatch (e.g. #chuyen-toan rejects 'thuong' exams)
        ch_chuyen = ChannelProfile(
            channel_name="chuyen-toan",
            allowed_subjects=[Subject.MATHEMATICS],
            allowed_tracks=[ExamTrackTier.CHUYEN],
        )
        f_math = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        rep_mismatch_track = DocumentInspector.inspect(f_math, channel=ch_chuyen)
        self.assertFalse(rep_mismatch_track.channel_compliance.is_compliant)
        self.assertIn("CẢNH BÁO THỂ LOẠI", rep_mismatch_track.channel_compliance.warning_message)
        self.assertIn("chuyen-toan", rep_mismatch_track.channel_compliance.bot_reply_formatted)


    def test_submission_channel_ingestion_and_routing(self):
        from DocInspector.channel_manager import (
            DEFAULT_SUBMISSION_CHANNEL_ID,
            DEFAULT_TARGET_CATEGORY_ID,
            CategoryDirectoryManager,
            BotInspectorAdapter,
        )
        from DocInspector.models import VerificationVerdict, ExamTrackTier, GradeLevel

        sub_id = "1535278288828633138"
        cat_id = "1534147951797080174"
        self.assertEqual(DEFAULT_SUBMISSION_CHANNEL_ID, sub_id)
        self.assertEqual(DEFAULT_TARGET_CATEGORY_ID, cat_id)

        # 1. Math Grade 12 document submitted into 1535278288828633138 -> Routes to #toan-12
        f_math = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        rep_m, route_m = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=f_math,
            submission_channel_id=sub_id,
            category_id=cat_id,
        )
        self.assertEqual(route_m.submission_channel_id, sub_id)
        self.assertEqual(route_m.target_category_id, cat_id)
        self.assertEqual(route_m.target_channel_name, "toan-12")
        self.assertEqual(route_m.detected_subject, Subject.MATHEMATICS)
        self.assertEqual(route_m.detected_grade, GradeLevel.GRADE_12)
        self.assertFalse(route_m.is_blocked_or_unverifiable)
        self.assertIn("1535278288828633138", route_m.submission_reply_message)
        self.assertIn("1534147951797080174", route_m.submission_reply_message)
        self.assertIn("toan-12", route_m.submission_reply_message)
        self.assertIn("Lớp 12", route_m.submission_reply_message)

        # Fallback to #de-toan when category has only generic channels
        _, route_fallback = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=f_math,
            category_channels=["de-toan", "chuyen-tin", "tai-lieu-chung"],
            submission_channel_id=sub_id,
            category_id=cat_id,
        )
        self.assertEqual(route_fallback.target_channel_name, "de-toan")

        # 2. Competitive programming submitted into 1535278288828633138 -> Routes to #chuyen-tin
        f_tin = self.samples_dir / "de_toan_chuyen_hsg.docx"
        rep_t, route_t = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=f_tin,
            submission_channel_id=sub_id,
            category_id=cat_id,
        )
        self.assertEqual(route_t.target_channel_name, "chuyen-tin")
        self.assertEqual(route_t.detected_subject, Subject.INFORMATICS)
        self.assertEqual(route_t.exam_track, ExamTrackTier.CHUYEN)
        self.assertIn("chuyen-tin", route_t.submission_reply_message)

        # 3. Lesson plan CV 5512 submitted into 1535278288828633138 -> Routes to #giao-an-5512
        f_lp = self.samples_dir / "giao_an_vat_ly_12_cv5512.docx"
        rep_lp, route_lp = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=f_lp,
            submission_channel_id=sub_id,
            category_id=cat_id,
        )
        self.assertEqual(route_lp.target_channel_name, "giao-an-5512")
        self.assertIn("giao-an-5512", route_lp.submission_reply_message)

        # 4. Blocked URL submitted into 1535278288828633138 -> Flags blocked, does not forward
        rep_blk, route_blk = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes="https://example.com/blocked-exam.pdf",
            submission_channel_id=sub_id,
            category_id=cat_id,
        )
        self.assertTrue(route_blk.is_blocked_or_unverifiable)
        self.assertEqual(route_blk.verdict, VerificationVerdict.UNVERIFIABLE_FAILED)
        self.assertEqual(route_blk.forwarded_post_message, "")
        self.assertIn("KHÔNG RÕ NGUỒN GỐC", route_blk.submission_reply_message)
        self.assertIn("1535278288828633138", route_blk.submission_reply_message)


    def test_grade_level_classification_and_channel_routing(self):
        """Verifies grade level detection (Grade 6 to 12) and grade-specific channel routing & compliance."""
        from DocInspector.models import GradeLevel, GRADE_LEVEL_VI_NAMES
        from DocInspector.channel_manager import ChannelProfile, ChannelComplianceValidator, CategoryDirectoryManager

        # 1. Inspect Grade 12 Math file
        f_math12 = self.samples_dir / "ielts_reading_cambridge_18.pdf"
        rep_12 = DocumentInspector.inspect(f_math12)
        self.assertEqual(rep_12.grade_level, GradeLevel.GRADE_12)
        self.assertIn("Lớp 12", rep_12.grade_level_label_vi)

        # 2. Inspect Grade 12 Physics Lesson Plan
        f_lp12 = self.samples_dir / "giao_an_vat_ly_12_cv5512.docx"
        rep_lp = DocumentInspector.inspect(f_lp12)
        self.assertEqual(rep_lp.grade_level, GradeLevel.GRADE_12)

        # 3. Direct posting in #toan-12 -> Compliant
        comp_ok = ChannelComplianceValidator.validate(rep_12, "toan-12")
        self.assertTrue(comp_ok.is_compliant)
        self.assertEqual(comp_ok.actual_grade, GradeLevel.GRADE_12)
        self.assertIn("Lớp 12", comp_ok.bot_reply_formatted)

        # 4. Channel with different grade (e.g. #toan-10) -> Warning
        ch_toan10 = ChannelProfile(
            channel_name="toan-10",
            allowed_subjects=[Subject.MATHEMATICS],
            allowed_grades=[GradeLevel.GRADE_10],
        )
        comp_mismatch = ChannelComplianceValidator.validate(rep_12, ch_toan10)
        self.assertFalse(comp_mismatch.is_compliant)
        self.assertIn("CẢNH BÁO KHỐI LỚP", comp_mismatch.warning_message)
        self.assertEqual(comp_mismatch.actual_grade, GradeLevel.GRADE_12)
        self.assertIn("toan-10", comp_mismatch.bot_reply_formatted)

        # 5. Routing test: Grade 12 Math prefers #toan-12 over #toan-10 and #de-toan
        route = CategoryDirectoryManager.route_submission(
            report=rep_12,
            category_channels=["toan-10", "toan-11", "toan-12", "de-toan", "tai-lieu-chung"],
        )
        self.assertEqual(route.target_channel_name, "toan-12")
        self.assertEqual(route.detected_grade, GradeLevel.GRADE_12)
        self.assertIn("Lớp 12", route.submission_reply_message)


    def test_word_formation_worksheets_and_language_proficiency_scales(self):
        """Verifies exercise/worksheet recognition and 5-language proficiency bands."""
        from DocInspector.channel_manager import BotInspectorAdapter
        from DocInspector.core import get_language_proficiency_scale
        from DocInspector.models import DocumentCategory, ExamType, ExamTrackTier, GradeLevel, VerificationVerdict

        # 1. Test Word Formation worksheet (must NOT be GENERAL_DOCUMENT or 2.0/10)
        wf_text = """BÀI TẬP WORD FORMATION TIẾNG ANH
Give the correct form of the word in brackets:
1. She was ________ (amaze) by the wonderful scenery.
2. The rapid ________ (develop) of industry has brought many changes.
3. He is an ________ (experience) teacher who has worked for 20 years.
4. We should protect our ________ (environment) from pollution.
5. Her sudden ________ (appear) surprised everyone at the meeting.

ĐÁP ÁN:
1. amazed
2. development
3. experienced
4. environment
5. appearance
"""
        rep_wf, route_wf = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=wf_text.encode("utf-8"),
            file_name="PDF_Bai_tap_wordform.docx.pdf",
            author_mention="@Dai Viet",
            author_name="Dai Viet",
        )
        self.assertEqual(rep_wf.detected_subject, Subject.ENGLISH)
        self.assertEqual(rep_wf.document_category, DocumentCategory.EXAM_TEST)
        self.assertEqual(rep_wf.exam_type, ExamType.SPECIALIZED_ENGLISH)
        self.assertEqual(rep_wf.verdict, VerificationVerdict.VERIFIED_OK)
        self.assertGreater(rep_wf.pass2.question_count, 0)
        self.assertGreaterEqual(rep_wf.difficulty_assessment.score, 5.0)
        self.assertNotEqual(rep_wf.difficulty_assessment.tier_label_vi, "Văn bản hành chính / Kế hoạch sư phạm")
        self.assertEqual(route_wf.target_channel_name, "tieng-anh")
        self.assertIn("@Dai Viet", route_wf.forwarded_post_message)
        self.assertIn("@Dai Viet", route_wf.submission_reply_message)
        self.assertIn("IELTS", route_wf.forwarded_post_message)

        # 2. Test 5-language proficiency scale matrix
        scales_expected = {
            Subject.ENGLISH: ("IELTS 4.0 -> 5.5", "IELTS 6.5 -> 8.0+", "IELTS 4.0 -> 6.5"),
            Subject.CHINESE: ("HSK 1 -> 4", "HSK 5 -> 9", "HSK 1 -> 9"),
            Subject.JAPANESE: ("JLPT N5 -> N3", "JLPT N2 -> N1", "JLPT N5 -> N1"),
            Subject.KOREAN: ("TOPIK 1 -> 3", "TOPIK 4 -> 6", "TOPIK 1 -> 6"),
            Subject.RUSSIAN: ("TRKI A1 -> B1", "TRKI B2 -> C2", "TRKI A1 -> C1"),
        }
        for subj, (exp_thuong, exp_chuyen, exp_chung) in scales_expected.items():
            act_thuong = get_language_proficiency_scale(subj, ExamTrackTier.THUONG, GradeLevel.GRADE_12)
            act_chuyen = get_language_proficiency_scale(subj, ExamTrackTier.CHUYEN, GradeLevel.GRADE_12)
            act_chung = get_language_proficiency_scale(subj, ExamTrackTier.THUONG, GradeLevel.UNKNOWN)
            self.assertEqual(act_thuong, exp_thuong, f"Failed thuong for {subj}")
            self.assertEqual(act_chuyen, exp_chuyen, f"Failed chuyen for {subj}")
            self.assertEqual(act_chung, exp_chung, f"Failed chung for {subj}")

        # 3. Test Russian TRKI routing
        ru_text = """ТЕСТ ПО РУССКОМУ ЯЗЫКУ (ТРКИ)
Задание 1. Выберите правильный вариант.
1. Вчера мы ходили в театр.
2. Он хорошо говорит по-русски.
"""
        rep_ru, route_ru = BotInspectorAdapter.inspect_and_route_submission(
            file_path_or_bytes=ru_text.encode("utf-8"),
            file_name="de_thi_tieng_nga_trki.pdf",
            author_mention="@Dai Viet",
            author_name="Dai Viet",
        )
        self.assertEqual(rep_ru.detected_subject, Subject.RUSSIAN)
        self.assertEqual(route_ru.target_channel_name, "tieng-nga")
        self.assertIn("TRKI", route_ru.submission_reply_message)


if __name__ == "__main__":
    unittest.main()




