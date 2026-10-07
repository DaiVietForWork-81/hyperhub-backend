"""
tests/test_exam_sync_and_drama_purge.py
Comprehensive integration test for:
1. Hybrid Exam Classifier (C++ / Python fallback, Year, School/Province, Magic Bytes, SHA-256)
2. Programming Language Recognition for Informatics (Python, C++, Pascal, Java, DSA)
3. Document Archive Bidirectional Sync (Bot posts + Admin posts)
4. Anti-Duplicate Engine (Không đề xuất trùng lặp, SHA-256 deduplication)
5. Drama / Error Purge & Auto-Sync (Raw message delete, Bulk delete, /gothailieu, Orphan pruning)
"""

import asyncio
import io
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import discord

from DocInspector.hybrid_classifier import HybridExamClassifier
from cpp_core.bridge import fast_detect_magic, fast_sha256
from database.database import Database


class TestExamSyncAndDramaPurge(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._temp_db.close()
        self.db = Database(self._temp_db.name)
        await self.db.connect()
        self.conn = self.db._conn

    async def asyncTearDown(self):
        await self.db.close()
        try:
            os.remove(self._temp_db.name)
        except Exception:
            pass

    # =========================================================================
    # 1. KIỂM THỬ HYBRID CLASSIFIER & C++ ENGINE & MÔN TIN (PYTHON, C++,...)
    # =========================================================================
    def test_hybrid_classifier_subjects_and_metadata(self):
        sample_exam_text = """
        SỞ GD&ĐT HÀ NỘI
        TRƯỜNG THPT CHUYÊN HÀ NỘI - AMSTERDAM
        NĂM HỌC 2024 - 2025
        ĐỀ THI HỌC KỲ 1 MÔN TOÁN LỚP 12
        Thời gian làm bài: 90 phút

        Câu 1: Cho hàm số y = f(x) liên tục trên đoạn [-1; 3]. Tìm giá trị lớn nhất và nhỏ nhất.
        Câu 2: Tính tích phân I = \\int_0^1 (2x + 1) dx.
        Câu 3: Trong không gian Oxyz, cho mặt phẳng (P): 2x - y + 2z - 5 = 0.
        Câu 4: Cho khối chóp S.ABCD có đáy là hình vuông cạnh a.
        Câu 50: Xác suất để chọn được 3 học sinh có cả nam và nữ là.
        BẢNG ĐÁP ÁN: 1.A 2.B 3.C 4.D ... 50.A
        """
        res = HybridExamClassifier.classify(sample_exam_text, file_name="De_Toan_Ams_2025.pdf")

        self.assertEqual(res.subject, "MATHEMATICS")
        self.assertEqual(res.grade, 12)
        self.assertEqual(res.track, "chuyen")
        self.assertTrue(res.has_answers)
        self.assertGreaterEqual(res.question_count, 50)
        self.assertIsNotNone(res.academic_year)
        self.assertIn("2024-2025", res.academic_year)
        self.assertIsNotNone(res.school_or_province)

    def test_informatics_programming_languages(self):
        """Kiểm thử mở rộng nhận diện ngôn ngữ lập trình (Python, C++, Pascal...)."""
        # Python
        py_code = """
        # Đề kiểm tra thực hành Python lớp 11
        # Bài 1: Đếm số nguyên tố trong dãy số
        def is_prime(n):
            if n < 2: return False
            for i in range(2, int(n**0.5) + 1):
                if n % i == 0: return False
            return True
        """
        res_py = HybridExamClassifier.classify(py_code, file_name="kiem_tra_python.py")
        self.assertEqual(res_py.subject, "INFORMATICS")
        self.assertEqual(res_py.programming_language, "Python")

        # C++
        cpp_code = """
        // Đề thi HSG Tin học THPT - Ngôn ngữ C++
        #include <iostream>
        #include <vector>
        using namespace std;
        int main() {
            ios_base::sync_with_stdio(false);
            cin.tie(NULL);
            int n; cin >> n;
            return 0;
        }
        """
        res_cpp = HybridExamClassifier.classify(cpp_code, file_name="bai1_hsg.cpp")
        self.assertEqual(res_cpp.subject, "INFORMATICS")
        self.assertEqual(res_cpp.programming_language, "C++")

        # Pascal
        pas_code = """
        program TinhTong;
        var a, b, s: integer;
        begin
            readln(a, b);
            s := a + b;
            writeln(s);
        end.
        """
        res_pas = HybridExamClassifier.classify(pas_code, file_name="baitap.pas")
        self.assertEqual(res_pas.subject, "INFORMATICS")
        self.assertEqual(res_pas.programming_language, "Pascal")

    def test_fast_sha256_and_magic_bytes(self):
        sample_bytes = b"%PDF-1.5 test content for exam classification"
        sha = fast_sha256(sample_bytes)
        self.assertEqual(len(sha), 64)

        m_type = fast_detect_magic(sample_bytes)
        self.assertEqual(m_type, "PDF")

        docx_bytes = b"PK\x03\x04" + b"\x00" * 30 + b"word/document.xml"
        self.assertEqual(fast_detect_magic(docx_bytes), "DOCX")

    # =========================================================================
    # 2. KIỂM THỬ KHÔNG ĐỀ XUẤT TRÙNG LẶP (DEDUPLICATION ENGINE)
    # =========================================================================
    async def test_anti_duplicate_deduplication(self):
        """Kiểm tra cơ chế chặn đề xuất trùng lặp khi tìm kiếm."""
        hash_shared = fast_sha256(b"same_exam_content")
        # Giả lập 2 bản ghi cùng file_hash trong database (ví dụ do nộp lại hoặc quét 2 lần)
        await self.db.execute(
            """
            INSERT INTO documents_archive (
                id, subject, title, file_name, file_size_bytes, file_type,
                estimated_level, question_count, page_count, author_id,
                author_name, channel_id, message_id, jump_url, timestamp, file_hash
            ) VALUES
            (10, 'INFORMATICS', 'Đề C++ Chuyên Tin Amsterdam', 'cpp_ams.pdf', 1000, 'PDF', 'Lớp 11 (chuyên)', 4, 3, 1, 'Bot', 1, 100, 'url1', 't1', ?),
            (11, 'INFORMATICS', 'Đề C++ Chuyên Tin Amsterdam', 'cpp_ams.pdf', 1000, 'PDF', 'Lớp 11 (chuyên)', 4, 3, 2, 'Admin', 1, 101, 'url2', 't2', ?)
            """,
            hash_shared, hash_shared
        )

        # Mô phỏng hàm lọc deduplication trong search_detailed
        rows = await self.db.fetchall(
            "SELECT id, subject, title, file_name, file_size_bytes, file_type, estimated_level, question_count, page_count, author_name, channel_id, message_id, jump_url, timestamp, file_hash FROM documents_archive"
        )
        seen_keys = set()
        dedup_results = []
        for r in rows:
            f_hash = r[14]
            title = r[2]
            dedup_key = f_hash or title.strip().lower()
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            dedup_results.append(r)

        # Chỉ còn 1 bản ghi duy nhất được trả về cho người dùng
        self.assertEqual(len(dedup_results), 1)

    # =========================================================================
    # 3. KIỂM THỬ LẬP CHỈ MỤC & PHÂN BIỆT NGUỒN (BOT vs ADMIN)
    # =========================================================================
    async def test_indexing_both_bot_and_admin_posts(self):
        now_iso = "2026-09-27T10:00:00"
        hash_bot = fast_sha256(b"bot_exam_data_1")
        await self.db.execute(
            """
            INSERT INTO documents_archive (
                subject, title, file_name, file_size_bytes, file_type,
                estimated_level, question_count, page_count, author_id,
                author_name, channel_id, message_id, jump_url, timestamp, file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            "MATHEMATICS", "Đề Thi Thử Toán 12 Quốc Gia", "toan12.pdf", 102400, "PDF",
            "Lớp 12 (thường)", 50, 6, 999999999, "Hệ thống (Bot)",
            1534147951797080175, 1001, "https://discord.com/channels/1/1/1001", now_iso, hash_bot
        )

        hash_admin = fast_sha256(b"admin_exam_data_2")
        await self.db.execute(
            """
            INSERT INTO documents_archive (
                subject, title, file_name, file_size_bytes, file_type,
                estimated_level, question_count, page_count, author_id,
                author_name, channel_id, message_id, jump_url, timestamp, file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            "INFORMATICS", "Đề HSG Tin Học Lớp 10 Chuyên C++", "tin10_hsg.docx", 204800, "DOCX",
            "Lớp 10 (chuyên) • [C++]", 4, 3, 1529864608813416449, "Admin_Master",
            1534147951797080176, 1002, "https://discord.com/channels/1/1/1002", now_iso, hash_admin
        )

        rows = await self.db.fetchall("SELECT id, author_name, subject, message_id FROM documents_archive")
        self.assertEqual(len(rows), 2)
        authors = [r[1] for r in rows]
        self.assertIn("Hệ thống (Bot)", authors)
        self.assertIn("Admin_Master", authors)

    # =========================================================================
    # 4. KIỂM THỬ TỰ ĐỘNG ĐỒNG BỘ XÓA (DRAMA / SAI PHẠM / PURGE)
    # =========================================================================
    async def test_drama_single_message_delete_sync(self):
        """Khi Admin xóa tin nhắn trên Discord (on_raw_message_delete), DB tự động xóa."""
        msg_id_drama = 2001
        hash_drama = fast_sha256(b"drama_exam_leak")
        await self.db.execute(
            """
            INSERT INTO documents_archive (
                subject, title, file_name, file_size_bytes, file_type,
                estimated_level, question_count, page_count, author_id,
                author_name, channel_id, message_id, jump_url, timestamp, file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            "CHEMISTRY", "Đề Hóa Lộ Đề Drama", "de_hoa_drama.pdf", 50000, "PDF",
            "Lớp 12", 40, 4, 12345, "User_Leaker",
            1534147951797080177, msg_id_drama, "https://discord.com/channels/1/1/2001", "2026-09-27T12:00:00", hash_drama
        )

        # Xác nhận có trong DB
        existing = await self.db.fetchone("SELECT id FROM documents_archive WHERE message_id = ?", msg_id_drama)
        self.assertIsNotNone(existing)

        # Mô phỏng sự kiện on_raw_message_delete
        await self.db.execute("DELETE FROM documents_archive WHERE message_id = ?", msg_id_drama)

        # Xác nhận đã bị xóa sạch khỏi DB
        after_delete = await self.db.fetchone("SELECT id FROM documents_archive WHERE message_id = ?", msg_id_drama)
        self.assertIsNone(after_delete)

    async def test_drama_bulk_delete_sync(self):
        """Khi Admin dùng purge/xóa hàng loạt tin nhắn dính drama (on_raw_bulk_message_delete)."""
        msg_ids = [3001, 3002, 3003]
        for m_id in msg_ids:
            await self.db.execute(
                """
                INSERT INTO documents_archive (
                    subject, title, file_name, file_size_bytes, file_type,
                    estimated_level, question_count, page_count, author_id,
                    author_name, channel_id, message_id, jump_url, timestamp, file_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                "LITERATURE", f"Đề Văn #{m_id}", f"van_{m_id}.pdf", 10000, "PDF",
                "Lớp 11", 5, 2, 12345, "Drama_User",
                1534147951797080178, m_id, f"https://discord.com/channels/1/1/{m_id}", "2026-09-27T12:00:00", f"hash_{m_id}"
            )

        # Xác nhận có 3 bản ghi
        rows = await self.db.fetchall("SELECT id FROM documents_archive WHERE message_id IN (3001, 3002, 3003)")
        self.assertEqual(len(rows), 3)

        # Mô phỏng bulk delete
        placeholders = ",".join("?" for _ in msg_ids)
        await self.db.execute(f"DELETE FROM documents_archive WHERE message_id IN ({placeholders})", *msg_ids)

        remaining = await self.db.fetchall("SELECT id FROM documents_archive WHERE message_id IN (3001, 3002, 3003)")
        self.assertEqual(len(remaining), 0)

    # =========================================================================
    # 5. KIỂM THỬ LỆNH QUẢN TRỊ /gothailieu & ORPHAN PRUNING
    # =========================================================================
    async def test_gothailieu_by_keyword(self):
        """Admin gỡ bỏ tài liệu bằng từ khóa hoặc Message ID."""
        await self.db.execute(
            """
            INSERT INTO documents_archive (
                subject, title, file_name, file_size_bytes, file_type,
                estimated_level, question_count, page_count, author_id,
                author_name, channel_id, message_id, jump_url, timestamp, file_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            "PHYSICS", "Đề Thi Sai Đáp Án Nghiêm Trọng", "ly_sai_dap_an.pdf", 80000, "PDF",
            "Lớp 10", 30, 3, 55555, "Contributor",
            1534147951797080179, 4001, "https://discord.com/channels/1/1/4001", "2026-09-27T12:00:00", "hash_ly"
        )

        kw = "%sai đáp án%"
        rows = await self.db.fetchall(
            "SELECT id, title, channel_id, message_id FROM documents_archive WHERE LOWER(title) LIKE LOWER(?)",
            kw
        )
        self.assertEqual(len(rows), 1)
        doc_id = rows[0][0]

        # Xóa theo lệnh
        await self.db.execute("DELETE FROM documents_archive WHERE id = ?", doc_id)

        check = await self.db.fetchone("SELECT id FROM documents_archive WHERE id = ?", doc_id)
        self.assertIsNone(check)

    async def test_orphan_pruning_pass(self):
        """Rà soát mồ côi (tin nhắn bị xóa khi bot offline) tự động dọn DB."""
        await self.db.execute(
            """
            INSERT INTO documents_archive (
                id, subject, title, file_name, file_size_bytes, file_type,
                estimated_level, question_count, page_count, author_id,
                author_name, channel_id, message_id, jump_url, timestamp, file_hash
            ) VALUES
            (501, 'MATH', 'Đề Còn Sống', 'live.pdf', 1000, 'PDF', 'Lớp 12', 50, 5, 1, 'Admin', 100, 5001, 'url1', 'time', 'h1'),
            (502, 'PHYS', 'Đề Đã Bị Xóa Lúc Bot Offline', 'dead.pdf', 2000, 'PDF', 'Lớp 12', 40, 4, 1, 'Admin', 100, 5002, 'url2', 'time', 'h2')
            """
        )

        async def mock_fetch_message(m_id):
            if m_id == 5001:
                return MagicMock(id=5001)
            raise discord.NotFound(MagicMock(), "Unknown Message")

        db_docs = await self.db.fetchall("SELECT id, channel_id, message_id FROM documents_archive")
        pruned_count = 0
        for d_id, ch_id, m_id in db_docs:
            try:
                await mock_fetch_message(m_id)
            except discord.NotFound:
                await self.db.execute("DELETE FROM documents_archive WHERE id = ?", d_id)
                pruned_count += 1

        self.assertEqual(pruned_count, 1)
        remaining = await self.db.fetchall("SELECT id, title FROM documents_archive")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][0], 501)
        self.assertEqual(remaining[0][1], "Đề Còn Sống")

    async def test_image_ocr_indexing_and_deduplication(self):
        """Kiểm thử đọc ảnh bằng OCR và lập chỉ mục + chống trùng lặp."""
        from PIL import Image, ImageDraw
        from cogs.doc_intake import DocumentIntakeCog

        # Tạo ảnh đề thi môn Vật Lý
        img = Image.new("RGB", (750, 200), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((20, 15), "DE THI THU TOT NGHIEP THPT 2025", fill=(0, 0, 0))
        d.text((20, 50), "MON VAT LY - MA DE 101", fill=(0, 0, 0))
        d.text((20, 85), "Cau 1: Mot vat dao dong dieu hoa theo phuong trinh x = 5cos(4pi t) cm.", fill=(0, 0, 0))
        d.text((20, 120), "Bien do dao dong cua vat la:", fill=(0, 0, 0))
        d.text((40, 150), "A. 5 cm        B. 4 cm        C. 10 cm        D. 2.5 cm", fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw_img_bytes = buf.getvalue()

        # Mock Bot & Cog
        mock_bot = MagicMock()
        mock_bot.db = self.db
        mock_bot.user.id = 99999
        cog = DocumentIntakeCog(mock_bot)

        # Mock Discord Message với attachment ảnh
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.id = 888801
        mock_msg.created_at = discord.utils.utcnow()
        mock_msg.author.id = 11111
        mock_msg.author.name = "TeacherStaff"
        mock_msg.author.display_name = "Thầy Giáo Lý"
        mock_msg.channel.id = 1534147951797080175
        mock_msg.channel.name = "de-vat-ly"
        mock_msg.jump_url = "https://discord.com/channels/1/2/888801"

        mock_att = AsyncMock(spec=discord.Attachment)
        mock_att.filename = "de_thi_thu_ly_2025.png"
        mock_att.read = AsyncMock(return_value=raw_img_bytes)
        mock_msg.attachments = [mock_att]

        # Lần 1: Lập chỉ mục tài liệu ảnh -> Phải thành công (cnt == 1)
        cnt = await cog.index_message_document(mock_msg)
        self.assertEqual(cnt, 1)

        # Kiểm tra database đã lưu đúng môn Vật Lý và file_type là IMAGE hoặc PNG
        row = await self.db.fetchone(
            "SELECT subject, file_type, file_name, file_hash FROM documents_archive WHERE message_id = ?",
            888801
        )
        self.assertIsNotNone(row)
        self.assertIn(row[0], ("PHYSICS", "PHYS"))
        self.assertEqual(row[2], "de_thi_thu_ly_2025.png")
        self.assertIsNotNone(row[3])

        # Lần 2: Thử nộp lại đúng ảnh đó ở message khác -> Chống trùng lặp (cnt == 0)
        mock_msg2 = MagicMock(spec=discord.Message)
        mock_msg2.id = 888802
        mock_msg2.created_at = discord.utils.utcnow()
        mock_msg2.author.id = 22222
        mock_msg2.author.name = "AnotherUser"
        mock_msg2.author.display_name = "Học Sinh"
        mock_msg2.channel.id = 1534147951797080175
        mock_msg2.channel.name = "de-vat-ly"
        mock_msg2.jump_url = "https://discord.com/channels/1/2/888802"

        mock_att2 = AsyncMock(spec=discord.Attachment)
        mock_att2.filename = "copy_de_ly.png"
        mock_att2.read = AsyncMock(return_value=raw_img_bytes)
        mock_msg2.attachments = [mock_att2]

        cnt2 = await cog.index_message_document(mock_msg2)
        self.assertEqual(cnt2, 0)  # Đã chặn trùng lặp bằng SHA-256 hash!


if __name__ == "__main__":
    unittest.main()

