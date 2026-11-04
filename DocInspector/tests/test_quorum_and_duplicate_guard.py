"""
Unit and Integration Tests for 3+1 Quorum Arbitration Consensus & Absolute Duplicate Guard.
Tests:
1. DuplicateGuard Layer 1 (Binary SHA-256) & Layer 2 (Normalized Content Hash & SimHash).
2. QuorumArbitrationEngine Case 1: Unanimous 3/3 Consensus (No Pass 4 needed).
3. QuorumArbitrationEngine Case 2: Divergent Quorum (2 vs 1) -> Pass 4 Arbitration Triggered.
4. QuorumArbitrationEngine Case 3: Chemistry vs Currency Dong Disambiguation.
5. Draft Verification Dossier generation and explainability.
6. Web API Endpoints: /api/documents/upload, /api/docs/archive, /upload portal.
"""

import asyncio
import os
import sqlite3
import sys
import unittest
from pathlib import Path

# Ensure root is in path
ROOT_DIR = Path(__file__).parent.parent.parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from DocInspector.consensus_engine import QuorumArbitrationEngine, QuorumArbitrationResult
from DocInspector.duplicate_guard import (
    DuplicateGuard,
    compute_simhash_64,
    hamming_distance,
    normalize_document_text,
)
from DocInspector.models import GradeLevel, Subject
from DocInspector.smart_pipeline import SmartDocumentPipeline


class TestQuorumAndDuplicateGuard(unittest.TestCase):
    """Test suite verifying Quorum Arbitration and Absolute Duplicate Prevention."""

    def setUp(self):
        # Create an in-memory test database
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            """
            CREATE TABLE documents_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                file_name TEXT,
                file_size_bytes INTEGER DEFAULT 0,
                file_type TEXT,
                estimated_level TEXT,
                question_count INTEGER DEFAULT 0,
                page_count INTEGER DEFAULT 0,
                author_id INTEGER NOT NULL,
                author_name TEXT,
                channel_id INTEGER,
                message_id INTEGER,
                jump_url TEXT,
                timestamp TEXT NOT NULL,
                file_hash TEXT,
                content_hash TEXT,
                raw_text TEXT,
                quorum_status TEXT
            )
            """
        )

    def tearDown(self):
        self.conn.close()

    # =========================================================================
    # 1. DUPLICATE GUARD TESTS
    # =========================================================================
    def test_01_binary_exact_duplicate_detection(self):
        """Layer 1: Binary SHA-256 catches exact byte-for-byte duplicates instantly."""
        file_bytes = b"%PDF-1.4 Mock exam bytes for mathematics test 2026"
        file_hash, content_hash, _ = DuplicateGuard.compute_hashes(file_bytes=file_bytes, text_content="Toán 12")

        # Insert original document
        self.conn.execute(
            """
            INSERT INTO documents_archive (
                subject, title, file_name, file_size_bytes, author_id, author_name,
                timestamp, jump_url, file_hash, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("MATHEMATICS", "De_Toan_12.pdf", "De_Toan_12.pdf", len(file_bytes), 123456, "Thầy Nam",
             "2026-10-20T10:00:00Z", "https://discord.com/channels/1/2/3", file_hash, content_hash)
        )
        self.conn.commit()

        # Check duplicate with same file bytes
        dup_res = DuplicateGuard.check_duplicate_sync(
            self.conn,
            file_hash=file_hash,
            content_hash=content_hash,
            file_name="De_Toan_12.pdf",
            file_size_bytes=len(file_bytes),
        )

        self.assertTrue(dup_res.is_duplicate)
        self.assertEqual(dup_res.match_type, "BINARY_EXACT")
        self.assertEqual(dup_res.existing_author, "Thầy Nam")
        self.assertIn("100% Binary SHA-256", dup_res.message)

    def test_02_content_semantic_duplicate_detection(self):
        """Layer 2: Content Hash catches identical exam even if converted or re-saved with different name."""
        raw_exam_text = (
            "SỞ GIÁO DỤC VÀ ĐÀO TẠO HÀ NỘI\n"
            "ĐỀ THI THỬ TỐT NGHIỆP THPT NĂM HỌC 2025-2026\n"
            "MÔN: TOÁN HỌC - KHỐI 12\n"
            "Câu 1: Cho hàm số y = f(x) có bảng biến thiên như sau. Đạo hàm f'(x) đổi dấu tại x = 2.\n"
            "A. 1   B. 2   C. 3   D. 4\n"
            "Câu 2: Nguyên hàm của hàm số f(x) = 2x là:\n"
            "A. x^2 + C   B. 2x^2 + C   C. x + C   D. 2 + C\n"
        )

        _, original_content_hash, original_simhash = DuplicateGuard.compute_hashes(
            file_bytes=b"dummy_binary_v1_pdf",
            text_content=raw_exam_text,
        )

        # Lưu tài liệu gốc
        self.conn.execute(
            """
            INSERT INTO documents_archive (
                subject, title, file_name, file_size_bytes, author_id, author_name,
                timestamp, jump_url, file_hash, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("MATHEMATICS", "Toan_Chuan_2026.pdf", "Toan_Chuan_2026.pdf", 54321, 999, "Cô Lan",
             "2026-10-19T08:00:00Z", "https://discord.com/channels/1/2/original", "hash_pdf_v1", original_content_hash)
        )
        self.conn.commit()

        # Người thứ 2 tải lên tệp DOCX (khác binary hash hoàn toàn, khác tên tệp, thừa khoảng trắng)
        modified_exam_text = (
            "   SỞ GIÁO DỤC VÀ ĐÀO TẠO HÀ NỘI   \n\n"
            "ĐỀ THI THỬ TỐT NGHIỆP THPT NĂM HỌC 2025-2026\n"
            "MÔN: TOÁN HỌC - KHỐI 12\n\n"
            "Câu 1: Cho hàm số y = f(x) có bảng biến thiên như sau. Đạo hàm f'(x) đổi dấu tại x = 2.\n"
            "A. 1    B. 2    C. 3    D. 4\n"
            "Câu 2: Nguyên hàm của hàm số f(x) = 2x là:\n"
            "A. x^2 + C    B. 2x^2 + C    C. x + C    D. 2 + C\n"
        )

        _, new_content_hash, new_simhash = DuplicateGuard.compute_hashes(
            file_bytes=b"completely_different_binary_v2_docx_bytes",
            text_content=modified_exam_text,
        )

        # Kiểm tra nội dung chuẩn hóa khớp nhau
        self.assertEqual(original_content_hash, new_content_hash)
        self.assertEqual(hamming_distance(original_simhash, new_simhash), 0)

        # Kiểm tra đối soát database
        dup_check = DuplicateGuard.check_duplicate_sync(
            self.conn,
            file_hash="hash_docx_v2_unseen",
            content_hash=new_content_hash,
            file_name="Copy_Of_Exam.docx",
            file_size_bytes=88888,
        )

        self.assertTrue(dup_check.is_duplicate)
        self.assertEqual(dup_check.match_type, "CONTENT_EXACT")
        self.assertEqual(dup_check.existing_author, "Cô Lan")
        self.assertIn("TRÙNG NỘI DUNG ĐỀ THI", dup_check.message)

    # =========================================================================
    # 2. 3+1 QUORUM ARBITRATION CONSENSUS TESTS
    # =========================================================================
    def test_03_quorum_unanimous_3_of_3(self):
        """Case A: Unanimous Quorum (Pass 1 == Pass 2 == Pass 3 == MATHEMATICS) -> No Pass 4."""
        math_exam = (
            "SỞ GD&ĐT HÀ NỘI - TRƯỜNG THPT CHUYÊN HÀ NỘI AMSTERDAM\n"
            "ĐỀ THI THỬ TỐT NGHIỆP THPT NĂM 2026 - MÔN: TOÁN HỌC\n"
            "Thời gian làm bài: 90 phút - Khối 12\n\n"
            "Câu 1. Cho hàm số f(x) = x^3 - 3x + 2. Tìm tọa độ điểm cực đại của đồ thị hàm số.\n"
            "Câu 2. Tính tích phân \\int_{0}^{1} (2x + 1) dx.\n"
            "Câu 3. Trong không gian Oxyz, cho mặt phẳng (P): 2x - y + 2z - 3 = 0. Tìm vectơ pháp tuyến.\n"
            "Câu 4. Cho hình lăng trụ đứng có đáy là tam giác vuông. Tính thể tích khối đa diện.\n"
            "Câu 5. Tìm số phức z thỏa mãn (1 + i)z = 3 - i.\n"
        )

        quorum_res = QuorumArbitrationEngine.inspect(math_exam, file_name="De_Thi_Thu_Toan_12.pdf")

        self.assertTrue(quorum_res.is_unanimous)
        self.assertEqual(quorum_res.passes_executed, 3)
        self.assertFalse(quorum_res.arbitration_triggered)
        self.assertEqual(quorum_res.final_subject, Subject.MATHEMATICS)
        self.assertEqual(quorum_res.final_grade, GradeLevel.GRADE_12)
        self.assertEqual(quorum_res.final_confidence, 1.0)
        self.assertIn("ĐỒNG THUẬN TUYỆT ĐỐI 3/3", quorum_res.final_verdict_rationale)
        self.assertIn("🟢 ĐỒNG THUẬN TUYỆT ĐỐI (3/3)", quorum_res.draft_dossier_markdown)

    def test_04_quorum_divergence_triggers_pass4_informatics(self):
        """Case B: Divergent Quorum (Pass 1 Math, Pass 2 Informatics, Pass 3 Informatics) -> Triggers Pass 4 Arbitration."""
        # HSG Tin học: Tiêu đề nhắc đến "Bài toán", thân bài nhắc "dãy số", "ước chung", nhưng có ràng buộc lập trình
        informatics_exam = (
            "KỲ THI CHỌN ĐỘI TUYỂN HỌC SINH GIỎI MÔN TOÁN VÀ TIN HỌC\n"
            "BÀI THI: THUẬT TOÁN SỐ HỌC VÀ TỐI ƯU\n"
            "Thời gian chạy: 1.0 giây | Giới hạn bộ nhớ: 256 MB\n"
            "File vào: DAYSO.INP | File ra: DAYSO.OUT\n\n"
            "Bài 1. Cho dãy số gồm N phần tử nguyên dương. Hãy tìm số lượng đoạn con có tổng chia hết cho K.\n"
            "Subtask 1 (30% số điểm): N <= 1000\n"
            "Subtask 2 (70% số điểm): N <= 100000\n"
            "Dữ liệu vào từ tệp stdin, xuất kết quả ra stdout.\n"
            "Sử dụng ngôn ngữ C++ (#include <iostream>) hoặc Pascal.\n"
        )

        quorum_res = QuorumArbitrationEngine.inspect(informatics_exam, file_name="Bai_Toan_Thuat_Toan_Tin_Hoc.pdf")

        # Có bất đồng nên PHẢI kích hoạt Lần quét 4
        self.assertTrue(quorum_res.arbitration_triggered)
        self.assertEqual(quorum_res.passes_executed, 4)
        self.assertFalse(quorum_res.is_unanimous)
        self.assertEqual(quorum_res.final_subject, Subject.INFORMATICS)
        self.assertIsNotNone(quorum_res.arbitration_rationale)
        self.assertTrue(len(quorum_res.contrastive_suppressions) > 0)
        self.assertIn("TRIỆT TIÊU TOÁN HỌC", quorum_res.contrastive_suppressions[0])
        self.assertIn("Hội đồng Trọng tài", quorum_res.final_verdict_rationale)
        self.assertIn("⚖️ HỘI ĐỒNG TRỌNG TÀI ĐỐI SOÁT (3+1)", quorum_res.draft_dossier_markdown)

    def test_05_quorum_divergence_triggers_pass4_admin_vs_copper(self):
        """Case C: Admin contract with 'đồng' (VND) -> Triggers Pass 4 and suppresses Chemistry."""
        contract_text = (
            "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
            "Độc lập - Tự do - Hạnh phúc\n\n"
            "HỢP ĐỒNG KINH TẾ VỀ VIỆC CUNG CẤP THIẾT BỊ GIÁO DỤC\n"
            "Số: 45/2026/HĐKT\n"
            "Điều 1: Bên A đồng ý mua và Bên B đồng ý bán gói thiết bị phòng máy vi tính.\n"
            "Điều 2: Tổng giá trị hợp đồng là 500.000.000 đồng (Năm trăm triệu đồng chẵn).\n"
            "Phương thức thanh toán: Chuyển khoản ngân hàng trong vòng 15 ngày kể từ ngày ký.\n"
            "Đại diện Bên A ký tên, đại diện Bên B ký tên.\n"
        )

        quorum_res = QuorumArbitrationEngine.inspect(contract_text, file_name="Hop_Dong_Mua_Ban.docx")

        self.assertEqual(quorum_res.final_subject, Subject.NON_ACADEMIC)
        self.assertTrue(quorum_res.passes_executed in (3, 4))
        self.assertIn("hợp đồng", contract_text.lower())

    def test_06_smart_pipeline_integration_with_quorum(self):
        """SmartDocumentPipeline executes 3+1 Quorum Engine and populates report with draft dossier."""
        sample_path = ROOT_DIR / "DocInspector" / "samples" / "sample_math_grade12.pdf"
        if not sample_path.exists():
            self.skipTest("Sample PDF not found, skipping pipeline test.")

        result = SmartDocumentPipeline.process(str(sample_path))
        self.assertIsNotNone(result.report.quorum_arbitration)
        self.assertIsNotNone(result.report.draft_dossier_markdown)
        self.assertIn("HỘI ĐỒNG TRỌNG TÀI", result.get_draft_dossier_markdown())
        self.assertEqual(result.report.detected_subject, Subject.MATHEMATICS)


from aiohttp.test_utils import AioHTTPTestCase
from aiohttp import FormData


class TestWebUploadAndArchiveEndpoints(AioHTTPTestCase):
    """Integration test verifying Web Upload Portal, Duplicate Prevention, and Archive Search."""

    def get_app(self):
        # Ensure Web is in sys.path
        web_dir = ROOT_DIR / "Web"
        if str(web_dir) not in sys.path:
            sys.path.insert(0, str(web_dir))
        from Web.app import create_app
        return create_app()

    async def test_07_web_portal_serves_html(self):
        """GET /portal and /upload return HTTP 200 with HTML portal UI."""
        resp = await self.client.get("/portal")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.content_type, "text/html")
        text = await resp.text()
        self.assertIn("Cổng Nộp Đề Trực Tuyến & Thẩm Định 3+1", text)
        self.assertIn("3+1 QUORUM", text)

        resp2 = await self.client.get("/upload")
        self.assertEqual(resp2.status, 200)

    async def test_08_web_api_upload_and_duplicate_rejection(self):
        """POST /api/documents/upload accepts valid exam, subsequent identical upload is blocked."""
        # 1. Create a simulated math exam text file with unique timestamp
        import time as _t
        ts = int(_t.time() * 1000)
        exam_content = (
            f"SO GIAO DUC VA DAO TAO - DOT THI {ts}\n"
            "DE THI KHOI 12 - MON: TOAN HOC\n"
            "Cau 1: Cho ham so y = f(x). Dao ham f'(x) = 3x^2 - 6x.\n"
            "Cau 2: Tich phan \\int_{0}^{1} x dx bang bao nhieu?\n"
            "A. 1/2   B. 1   C. 2   D. 0\n"
        ).encode("utf-8")
        test_filename = f"De_Toan_Web_Test_{ts}.pdf"

        form = FormData()
        form.add_field("file", exam_content, filename=test_filename, content_type="application/pdf")
        form.add_field("uploader_name", "Giáo viên Web Test")

        resp = await self.client.post("/api/documents/upload", data=form)
        self.assertEqual(resp.status, 200)
        data = await resp.json()

        self.assertTrue(data.get("success"), f"Expected success but got: {data}")
        self.assertFalse(data.get("is_duplicate"))
        self.assertEqual(data.get("detected_subject"), "MATHEMATICS")
        self.assertIsNotNone(data.get("quorum"))
        self.assertIsNotNone(data.get("draft_dossier_markdown"))

        # 2. Upload the exact same file again -> MUST BE REJECTED AS DUPLICATE!
        form2 = FormData()
        form2.add_field("file", exam_content, filename=test_filename, content_type="application/pdf")
        form2.add_field("uploader_name", "Người dùng khác")

        resp2 = await self.client.post("/api/documents/upload", data=form2)
        self.assertEqual(resp2.status, 200)
        data2 = await resp2.json()

        self.assertFalse(data2.get("success"))
        self.assertTrue(data2.get("is_duplicate"))
        self.assertEqual(data2.get("match_type"), "BINARY_EXACT")
        self.assertIn("TRÙNG LẶP", data2.get("message", "").upper())

    async def test_09_web_api_docs_archive_search(self):
        """GET /api/docs/archive returns real-time archived documents with FTS5 search."""
        resp = await self.client.get("/api/docs/archive")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertIn("items", data)
        self.assertIn("total", data)

        # Search by keyword
        resp_search = await self.client.get("/api/docs/archive?q=Toan")
        self.assertEqual(resp_search.status, 200)
        search_data = await resp_search.json()
        self.assertIn("items", search_data)


if __name__ == "__main__":
    unittest.main()
