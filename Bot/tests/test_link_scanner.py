"""
tests/test_link_scanner.py
Kiểm thử toàn diện Hệ Thống Quét Virus, Mã Độc & Kênh Kiểm Tra Link (Antivirus & Link Scanner).
"""

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from config.settings import settings
from services.antivirus_scanner import AntivirusScanner, ThreatLevel, ThreatScanResult
from cogs.link_scanner import ScannerRateLimiter


class TestLinkScanner(unittest.TestCase):
    def setUp(self):
        self.rate_limiter = ScannerRateLimiter(max_uses=3, window_seconds=3600)

    # =========================================================================
    # 1. KIỂM THỬ HẠN MỨC RATE LIMITER (3 LẦN / 1 TIẾNG & OWNER BYPASS)
    # =========================================================================
    def test_rate_limiter_regular_user(self):
        user_id = 9876543210

        # Lần 1: Được phép
        allowed, retry_after, remaining = self.rate_limiter.check_quota(user_id)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 3)
        rem = self.rate_limiter.consume_quota(user_id)
        self.assertEqual(rem, 2)

        # Lần 2: Được phép
        allowed, retry_after, remaining = self.rate_limiter.check_quota(user_id)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 2)
        rem = self.rate_limiter.consume_quota(user_id)
        self.assertEqual(rem, 1)

        # Lần 3: Được phép
        allowed, retry_after, remaining = self.rate_limiter.check_quota(user_id)
        self.assertTrue(allowed)
        self.assertEqual(remaining, 1)
        rem = self.rate_limiter.consume_quota(user_id)
        self.assertEqual(rem, 0)

        # Lần 4: BỊ CHẶN (Hết hạn mức 3 lần)
        allowed, retry_after, remaining = self.rate_limiter.check_quota(user_id)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)
        self.assertEqual(remaining, 0)

    def test_rate_limiter_owner_bypass(self):
        # Thiết lập giả định OWNER_ID
        owner_id = 1529864608813416449
        with patch.object(settings, "OWNER_ID", owner_id):
            # Owner gọi liên tục 10 lần vẫn luôn được phép và remaining = 999
            for _ in range(10):
                allowed, retry_after, remaining = self.rate_limiter.check_quota(owner_id)
                self.assertTrue(allowed)
                self.assertEqual(retry_after, 0)
                self.assertEqual(remaining, 999)
                rem = self.rate_limiter.consume_quota(owner_id)
                self.assertEqual(rem, 999)

    # =========================================================================
    # 2. KIỂM THỬ CHUẨN HÓA VÀ BẢO VỆ URL (URL VALIDATION & THREAT DETECTION)
    # =========================================================================
    def test_url_normalization(self):
        # Tự động thêm https://
        self.assertEqual(
            AntivirusScanner.normalize_url("drive.google.com/file/d/abc"),
            "https://drive.google.com/file/d/abc",
        )
        # Loại bỏ markdown <...>
        self.assertEqual(
            AntivirusScanner.normalize_url("<https://codeforces.com>"),
            "https://codeforces.com",
        )
        # Loại bỏ backticks
        self.assertEqual(
            AntivirusScanner.normalize_url("`https://example.com/test`"),
            "https://example.com/test",
        )

    def test_ssrf_and_private_network(self):
        async def run():
            # Localhost
            r1 = await AntivirusScanner.scan_url("http://127.0.0.1:8080/admin", check_probe=False)
            self.assertFalse(r1.is_safe)
            self.assertEqual(r1.level, ThreatLevel.MALICIOUS)
            self.assertIn("SSRF", r1.threat_name)

            # Private IP (192.168.x.x)
            r2 = await AntivirusScanner.scan_url("http://192.168.1.1/router", check_probe=False)
            self.assertFalse(r2.is_safe)
            self.assertEqual(r2.level, ThreatLevel.MALICIOUS)

            # Private IP (10.x.x.x)
            r3 = await AntivirusScanner.scan_url("http://10.0.0.5/internal", check_probe=False)
            self.assertFalse(r3.is_safe)
            self.assertEqual(r3.level, ThreatLevel.MALICIOUS)

        asyncio.run(run())

    def test_malicious_domains_and_ip_loggers(self):
        async def run():
            # IP Logger Grabify
            r = await AntivirusScanner.scan_url("https://grabify.link/track_token", check_probe=False)
            self.assertFalse(r.is_safe)
            self.assertEqual(r.level, ThreatLevel.MALICIOUS)
            self.assertIn("IP Logger", r.threat_name)

            # IP Logger iplogger.org
            r2 = await AntivirusScanner.scan_url("https://iplogger.org/2test", check_probe=False)
            self.assertFalse(r2.is_safe)
            self.assertEqual(r2.level, ThreatLevel.MALICIOUS)

        asyncio.run(run())

    def test_dangerous_file_extensions_on_url(self):
        async def run():
            r1 = await AntivirusScanner.scan_url("https://example.com/downloads/setup.exe", check_probe=False)
            self.assertFalse(r1.is_safe)
            self.assertEqual(r1.level, ThreatLevel.MALICIOUS)

            r2 = await AntivirusScanner.scan_url("https://files.com/script.bat", check_probe=False)
            self.assertFalse(r2.is_safe)
            self.assertEqual(r2.level, ThreatLevel.MALICIOUS)

        asyncio.run(run())

    def test_url_shortener_suspicious(self):
        async def run():
            r = await AntivirusScanner.scan_url("https://bit.ly/random_short_link", check_probe=False)
            self.assertEqual(r.level, ThreatLevel.SUSPICIOUS)
            self.assertIn("Rút Gọn", r.threat_name)

        asyncio.run(run())

    def test_safe_url(self):
        async def run():
            r = await AntivirusScanner.scan_url("https://codeforces.com/contest/1800/problem/A", check_probe=False)
            self.assertTrue(r.is_safe)
            self.assertEqual(r.level, ThreatLevel.SAFE)

        asyncio.run(run())

    # =========================================================================
    # 3. KIỂM THỬ QUÉT TỆP NHỊ PHÂN & MAGIC BYTES (MALWARE DETECTION)
    # =========================================================================
    def test_disguised_pe_executable(self):
        # File .pdf nhưng chứa header MZ (Windows Portable Executable)
        fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200
        res = AntivirusScanner.scan_file_bytes(fake_pdf, "de_thi_toan.pdf")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.level, ThreatLevel.MALICIOUS)
        self.assertIn("Windows PE", res.threat_name)
        self.assertIn("PE_HEADER_DETECTED", res.indicators)

    def test_disguised_linux_elf_binary(self):
        # File .docx nhưng chứa header \x7fELF (Linux Executable)
        fake_docx = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 100
        res = AntivirusScanner.scan_file_bytes(fake_docx, "giao_an.docx")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.level, ThreatLevel.MALICIOUS)
        self.assertIn("Linux ELF", res.threat_name)

    def test_pdf_exploit_launch(self):
        # PDF chứa thẻ /Launch nguy hiểm
        malicious_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Action /S /Launch /F (cmd.exe) >>\nendobj\n"
        res = AntivirusScanner.scan_file_bytes(malicious_pdf, "de_thi.pdf")
        self.assertFalse(res.is_safe)
        self.assertEqual(res.level, ThreatLevel.MALICIOUS)
        self.assertIn("/Launch", res.threat_name)

    def test_clean_file(self):
        # File văn bản thuần sạch
        clean_text = "Đề thi học sinh giỏi Tin Học 2026. Bài 1: Cây phân đoạn Segment Tree.".encode("utf-8")
        res = AntivirusScanner.scan_file_bytes(clean_text, "de_tin.txt")
        self.assertTrue(res.is_safe)
        self.assertEqual(res.level, ThreatLevel.SAFE)
        self.assertIsNotNone(res.sha256)

    # =========================================================================
    # 4. KIỂM THỬ RISK SCORING VỚI THỐNG KÊ VIRUSTOTAL
    # =========================================================================
    def test_virustotal_risk_scoring(self):
        async def run():
            # Mock VirusTotal phát hiện độc hại: 2/70
            with patch.object(
                AntivirusScanner,
                "check_virustotal_url",
                new=AsyncMock(return_value={"safe": 65, "malicious": 2, "suspicious": 3, "total": 70}),
            ):
                with patch.object(settings, "VIRUSTOTAL_API_KEY", "dummy_vt_key"):
                    res = await AntivirusScanner.scan_url("https://example.com/test", check_probe=False)
                    self.assertFalse(res.is_safe)
                    self.assertEqual(res.level, ThreatLevel.MALICIOUS)
                    self.assertEqual(res.badge_emoji, "🔴")
                    self.assertIsNotNone(res.vt_stats)
                    self.assertEqual(res.vt_stats["malicious"], 2)
                    self.assertEqual(res.vt_stats["safe"], 65)

            # Mock VirusTotal chỉ có suspicious: 3/70
            with patch.object(
                AntivirusScanner,
                "check_virustotal_url",
                new=AsyncMock(return_value={"safe": 67, "malicious": 0, "suspicious": 3, "total": 70}),
            ):
                with patch.object(settings, "VIRUSTOTAL_API_KEY", "dummy_vt_key"):
                    res = await AntivirusScanner.scan_url("https://example.com/test2", check_probe=False)
                    self.assertEqual(res.level, ThreatLevel.SUSPICIOUS)
                    self.assertEqual(res.badge_emoji, "🟡")

            # Mock VirusTotal sạch 100%: 70/70
            with patch.object(
                AntivirusScanner,
                "check_virustotal_url",
                new=AsyncMock(return_value={"safe": 70, "malicious": 0, "suspicious": 0, "total": 70}),
            ):
                with patch.object(settings, "VIRUSTOTAL_API_KEY", "dummy_vt_key"):
                    res = await AntivirusScanner.scan_url("https://example.com/clean", check_probe=False)
                    self.assertTrue(res.is_safe)
                    self.assertEqual(res.level, ThreatLevel.SAFE)
                    self.assertEqual(res.badge_emoji, "🟢")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
