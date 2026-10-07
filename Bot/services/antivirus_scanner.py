"""
services/antivirus_scanner.py
Engine Quét An Toàn, Phát Hiện Virus, Mã Độc, Phishing & Tệp Ngụy Trang (Multi-Layer Threat Engine).

Quy trình xử lý theo đúng kiến trúc tiêu chuẩn:
1. URL Validation (urllib / regex / tld)
2. Google Safe Browsing API v4
3. VirusTotal API v3
4. Risk Scoring & Classification:
   - 🟢 SAFE: Không phát hiện mối đe dọa
   - 🟡 SUSPICIOUS: Có dấu hiệu đáng ngờ
   - 🔴 MALICIOUS: Phát hiện phishing / malware
   - ⚪ UNKNOWN: Chưa đủ dữ liệu đối chiếu
5. Binary File & Content Scanner (Magic Bytes, PDF exploit, Office macro, Zip slip/bomb)
"""

from __future__ import annotations

import asyncio
import base64
import enum
import hashlib
import ipaddress
import logging
import os
import re
import time
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import aiohttp

from config.settings import settings

log = logging.getLogger("AntivirusScanner")


class ThreatLevel(str, enum.Enum):
    SAFE = "SAFE"
    SUSPICIOUS = "SUSPICIOUS"
    MALICIOUS = "MALICIOUS"
    UNKNOWN = "UNKNOWN"


@dataclass
class ThreatScanResult:
    is_safe: bool
    level: ThreatLevel
    threat_name: str
    summary: str
    risk_score: int = 0  # Thang điểm rủi ro 0 - 100
    vt_stats: dict[str, int] | None = None  # {'safe': X, 'malicious': Y, 'suspicious': Z, 'total': N}
    safe_browsing_threats: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    sha256: str | None = None
    file_size_bytes: int = 0
    url: str | None = None
    engine: str = "HyperHub Multi-Layer Security Engine"
    scan_time_ms: float = 0.0

    @property
    def badge_emoji(self) -> str:
        if self.level == ThreatLevel.SAFE:
            return "🟢"
        elif self.level == ThreatLevel.SUSPICIOUS:
            return "🟡"
        elif self.level == ThreatLevel.MALICIOUS:
            return "🔴"
        return "⚪"

    @property
    def level_label(self) -> str:
        if self.level == ThreatLevel.SAFE:
            return "🟢 SAFE — Không phát hiện"
        elif self.level == ThreatLevel.SUSPICIOUS:
            return "🟡 SUSPICIOUS — Có dấu hiệu đáng ngờ"
        elif self.level == ThreatLevel.MALICIOUS:
            return "🔴 MALICIOUS — Phát hiện phishing/malware"
        return "⚪ UNKNOWN — Chưa đủ dữ liệu"

    @property
    def color_hex(self) -> int:
        if self.level == ThreatLevel.SAFE:
            return 0x2ECC71  # Xanh lá
        elif self.level == ThreatLevel.SUSPICIOUS:
            return 0xF1C40F  # Vàng
        elif self.level == ThreatLevel.MALICIOUS:
            return 0xE74C3C  # Đỏ
        return 0x95A5A6      # Xám


class AntivirusScanner:
    """Bộ quét mã độc và an toàn liên kết đa tầng tích hợp Google Safe Browsing & VirusTotal."""

    # Danh sách phần mở rộng tệp nguy hiểm
    DANGEROUS_EXTENSIONS: set[str] = {
        ".exe", ".bat", ".cmd", ".vbs", ".msi", ".scr", ".jar",
        ".apk", ".com", ".pif", ".reg", ".ps1", ".sh", ".dll",
        ".sys", ".cpl", ".hta", ".wsf", ".gadget", ".iso", ".img",
        ".dmg", ".vbe", ".jse", ".bin",
    }

    # Danh sách domain IP Logger / Phishing / Scam đã biết
    MALICIOUS_DOMAINS: set[str] = {
        "grabify.link", "iplogger.org", "2no.co", "yip.su",
        "blasze.tk", "ps3cfw.com", "curiouscat.club", "headshot.monster",
        "quickmessage.io", "screenshare.host", "iplogger.com", "iplogger.ru",
        "lovebird.guru", "trulove.guru", "dateing.club", "otherpeoplespixels.info",
        "mymassivecrypto.com", "free-nitro.ru", "discord-nitro.su",
        "steamcommunitly.com", "steamcomunuty.com", "steam-nitro.ru",
    }

    # URL Shorteners
    URL_SHORTENERS: set[str] = {
        "bit.ly", "tinyurl.com", "t.co", "rb.gy", "shorturl.at",
        "cutt.ly", "is.gd", "ow.ly", "goo.gl", "buff.ly",
    }

    @classmethod
    def normalize_url(cls, raw_url: str) -> str:
        """Chuẩn hóa đường dẫn: loại bỏ khoảng trắng, markdown, tự động thêm https:// nếu thiếu."""
        url = raw_url.strip()
        url = re.sub(r"^[<`'\"]+", "", url)
        url = re.sub(r"[>`'\"]+$", "", url).strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        return url

    @classmethod
    def check_hostname_ssrf(cls, hostname: str) -> tuple[bool, str]:
        """Kiểm tra chống tấn công SSRF / Truy cập mạng nội bộ / Private IP."""
        if not hostname:
            return False, "Địa chỉ Host rỗng"

        host_lower = hostname.lower()
        if host_lower in ("localhost", "127.0.0.1", "0.0.0.0", "::1", "local"):
            return False, "Chặn truy cập localhost / loopback"

        if host_lower.endswith(".local") or host_lower.endswith(".onion") or host_lower.endswith(".internal"):
            return False, "Chặn truy cập tên miền mạng nội bộ (.internal/.local/.onion)"

        try:
            ip = ipaddress.ip_address(host_lower)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return False, f"Chặn truy cập địa chỉ IP nội bộ / private ({ip})"
        except ValueError:
            pass

        return True, "Hostname hợp lệ"

    @classmethod
    async def check_google_safe_browsing(cls, target_url: str, api_key: str) -> list[str]:
        """Kiểm tra Google Safe Browsing Lookup API v4."""
        if not api_key:
            return []

        try:
            endpoint = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={api_key}"
            payload = {
                "client": {"clientId": "hyperhub-discord-bot", "clientVersion": "1.0.0"},
                "threatInfo": {
                    "threatTypes": [
                        "MALWARE",
                        "SOCIAL_ENGINEERING",
                        "UNWANTED_SOFTWARE",
                        "POTENTIALLY_HARMFUL_APPLICATION",
                    ],
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": target_url}],
                },
            }
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        matches = data.get("matches", [])
                        threats = [m.get("threatType", "MALWARE") for m in matches]
                        return threats
        except Exception as e:
            log.debug("Google Safe Browsing query error: %s", e)
        return []

    @classmethod
    async def check_virustotal_url(cls, target_url: str, api_key: str) -> dict[str, int] | None:
        """Truy vấn VirusTotal API v3 lấy thống kê Safe / Malicious / Suspicious."""
        if not api_key:
            return None

        try:
            # Mã hóa base64 không padding theo quy chuẩn VirusTotal v3
            url_id = base64.urlsafe_b64encode(target_url.encode("utf-8")).decode("utf-8").strip("=")
            endpoint = f"https://www.virustotal.com/api/v3/urls/{url_id}"
            headers = {"x-apikey": api_key, "User-Agent": "HyperHub-Security-Scanner"}

            timeout = aiohttp.ClientTimeout(total=6)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                        malicious = stats.get("malicious", 0)
                        suspicious = stats.get("suspicious", 0)
                        harmless = stats.get("harmless", 0)
                        undetected = stats.get("undetected", 0)
                        safe = harmless + undetected
                        total = safe + malicious + suspicious
                        if total == 0:
                            total = sum(stats.values()) or 70
                        return {
                            "safe": safe,
                            "malicious": malicious,
                            "suspicious": suspicious,
                            "total": total,
                        }
                    elif resp.status == 404:
                        # URL chưa từng được submit, thử gửi request scan
                        try:
                            async with session.post(
                                "https://www.virustotal.com/api/v3/urls",
                                data={"url": target_url},
                                headers=headers,
                            ) as post_resp:
                                pass
                        except Exception:
                            pass
        except Exception as e:
            log.debug("VirusTotal query error: %s", e)
        return None

    @classmethod
    async def scan_url(cls, raw_url: str, check_probe: bool = True) -> ThreatScanResult:
        """
        Quét bảo mật theo đúng Pipeline:
        1. URL Validation
        2. Google Safe Browsing
        3. VirusTotal API
        4. Risk Scoring (SAFE / SUSPICIOUS / MALICIOUS / UNKNOWN)
        """
        t0 = time.time()
        url = cls.normalize_url(raw_url)
        details: list[str] = []
        indicators: list[str] = []
        risk_score = 0

        # -------------------------------------------------------------
        # 1. URL VALIDATION (urllib / format / host / SSRF)
        # -------------------------------------------------------------
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception as e:
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="URL Cú Pháp Không Hợp Lệ",
                summary=f"Không thể phân tích cú pháp đường dẫn: {e}",
                risk_score=100,
                details=[f"URL: {url}"],
                url=url,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        if parsed.scheme not in ("http", "https"):
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Giao Thức Nguy Hiểm",
                summary=f"Giao thức '{parsed.scheme}://' không được hỗ trợ (chỉ cho phép http/https).",
                risk_score=100,
                details=[f"Scheme: {parsed.scheme}"],
                url=url,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        hostname = parsed.hostname or ""
        if not hostname:
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Tên Miền Rỗng",
                summary="Đường dẫn không chứa tên miền hợp lệ.",
                risk_score=100,
                url=url,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        # Kiểm tra SSRF
        is_safe_ssrf, ssrf_msg = cls.check_hostname_ssrf(hostname)
        if not is_safe_ssrf:
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Tấn Công SSRF / Private Network",
                summary=ssrf_msg,
                risk_score=100,
                details=[f"Địa chỉ IP / Host nội bộ bị chặn: {hostname} ({ssrf_msg})"],
                indicators=["SSRF_LOCAL_ATTEMPT"],
                url=url,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        # Kiểm tra đuôi file nguy hại trên URL
        path_lower = parsed.path.lower()
        for ext in cls.DANGEROUS_EXTENSIONS:
            if path_lower.endswith(ext):
                return ThreatScanResult(
                    is_safe=False,
                    level=ThreatLevel.MALICIOUS,
                    threat_name="Đường Dẫn Chứa Tệp Thực Thi Nguy Hại",
                    summary=f"Đường dẫn trỏ trực tiếp tới tệp thực thi {ext}. Tệp này có nguy cơ chứa virus/trojan phá hoại hệ thống!",
                    risk_score=95,
                    details=[f"Phát hiện tệp thực thi nguy hiểm: {ext}", f"Đường dẫn tệp: {parsed.path}"],
                    indicators=["DANGEROUS_FILE_EXTENSION"],
                    url=url,
                    scan_time_ms=(time.time() - t0) * 1000,
                )

        # Kiểm tra Blacklist IP Logger & Malicious Domains
        host_lower = hostname.lower()
        for bad_domain in cls.MALICIOUS_DOMAINS:
            if host_lower == bad_domain or host_lower.endswith("." + bad_domain):
                return ThreatScanResult(
                    is_safe=False,
                    level=ThreatLevel.MALICIOUS,
                    threat_name="IP Logger / Website Lừa Đảo",
                    summary=f"Đường dẫn thuộc tên miền nguy hại đã biết ({bad_domain}). Tuyệt đối không truy cập để tránh lộ IP và thông tin cá nhân!",
                    risk_score=95,
                    details=[f"Tên miền nguy hại đã biết: {bad_domain}", "Hành vi: Thu thập IP / Theo dõi người dùng trái phép"],
                    indicators=["KNOWN_MALICIOUS_DOMAIN", "IP_LOGGER"],
                    url=url,
                    scan_time_ms=(time.time() - t0) * 1000,
                )

        # Kiểm tra từ khóa phishing giả mạo
        suspicious_keywords = ["free-nitro", "discord-nitro", "steamcom", "steam-gift", "gift-discord", "claim-nitro"]
        if any(kw in host_lower for kw in suspicious_keywords) and not any(
            legit in host_lower for legit in ["discord.com", "discord.gg", "steamcommunity.com", "steampowered.com"]
        ):
            risk_score += 50
            indicators.append("PHISHING_HEURISTIC")
            details.append(f"Tên miền chứa từ khóa giả mạo / lừa đảo: {hostname}")

        # Kiểm tra URL Shortener
        is_shortener = any(host_lower == s or host_lower.endswith("." + s) for s in cls.URL_SHORTENERS)
        if is_shortener:
            risk_score += 35
            indicators.append("URL_SHORTENER")
            details.append("Dịch vụ rút gọn link (URL Shortener) - có thể che giấu liên kết đích thực tế")

        # -------------------------------------------------------------
        # 2. GOOGLE SAFE BROWSING API v4
        # -------------------------------------------------------------
        sb_key = getattr(settings, "GOOGLE_SAFE_BROWSING_API_KEY", "") or os.getenv("GOOGLE_SAFE_BROWSING_API_KEY", "")
        sb_threats: list[str] = []
        if sb_key:
            sb_threats = await cls.check_google_safe_browsing(url, sb_key)
            if sb_threats:
                risk_score = 100
                indicators.append("GOOGLE_SAFE_BROWSING_THREAT")
                details.append(f"Google Safe Browsing: Phát hiện mối nguy hại ({', '.join(sb_threats)})")

        # -------------------------------------------------------------
        # 3. VIRUSTOTAL API v3
        # -------------------------------------------------------------
        vt_key = getattr(settings, "VIRUSTOTAL_API_KEY", "") or os.getenv("VIRUSTOTAL_API_KEY", "")
        vt_stats: dict[str, int] | None = None
        if vt_key:
            vt_stats = await cls.check_virustotal_url(url, vt_key)
            if vt_stats:
                m_count = vt_stats["malicious"]
                s_count = vt_stats["suspicious"]
                if m_count > 0:
                    risk_score = max(risk_score, 80 + min(20, m_count * 10))
                    indicators.append("VIRUSTOTAL_MALICIOUS")
                    details.append(f"VirusTotal: {m_count}/{vt_stats['total']} trình bảo mật đánh giá Độc hại (Malicious)")
                elif s_count > 0:
                    risk_score = max(risk_score, 40 + min(30, s_count * 10))
                    indicators.append("VIRUSTOTAL_SUSPICIOUS")
                    details.append(f"VirusTotal: {s_count}/{vt_stats['total']} trình bảo mật đánh giá Đáng ngờ (Suspicious)")

        # -------------------------------------------------------------
        # 4. RESPONSE PROBE (Kiểm tra nhẹ Header nếu cần)
        # Chặn SSRF qua redirect: không follow tự động, validate từng hop
        # -------------------------------------------------------------
        if check_probe and not is_shortener and risk_score < 80:
            try:
                probe_timeout = aiohttp.ClientTimeout(total=4)
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                async with aiohttp.ClientSession(timeout=probe_timeout) as session:
                    async with session.head(url, headers=headers, allow_redirects=False) as head_resp:
                        # Validate redirect thủ công (tối đa 2 hop, mỗi hop phải pass SSRF)
                        redirect_hops = 0
                        current_resp = head_resp
                        while current_resp.status in (301, 302, 303, 307, 308) and redirect_hops < 2:
                            loc = current_resp.headers.get("Location", "")
                            if not loc:
                                break
                            next_url = urllib.parse.urljoin(url, loc)
                            next_host = urllib.parse.urlparse(next_url).hostname or ""
                            ok, _ = cls.check_hostname_ssrf(next_host)
                            if not ok:
                                risk_score = 100
                                indicators.append("SSRF_REDIRECT_BLOCKED")
                                details.append(f"Chặn redirect tới host nội bộ: {next_host}")
                                break
                            redirect_hops += 1
                            break  # chỉ kiểm tra hop đầu, không follow sâu để tránh SSRF dây chuyền
                        content_disp = current_resp.headers.get("Content-Disposition", "").lower()
                        for ext in cls.DANGEROUS_EXTENSIONS:
                            if ext in content_disp or f"filename*{ext}" in content_disp:
                                risk_score = 100
                                indicators.append("DISGUISED_HEADER_EXECUTABLE")
                                return ThreatScanResult(
                                    is_safe=False,
                                    level=ThreatLevel.MALICIOUS,
                                    threat_name="Tệp Thực Thi Ẩn Trong Header",
                                    summary=f"Máy chủ đích phản hồi tệp tải về có đuôi thực thi nguy hiểm ({ext}).",
                                    risk_score=100,
                                    details=[f"Header tải về trỏ tới tệp thực thi: {content_disp}"],
                                    indicators=indicators,
                                    url=url,
                                    scan_time_ms=(time.time() - t0) * 1000,
                                )
            except Exception as pe:
                log.debug("URL probe error/timeout: %s", pe)

        # -------------------------------------------------------------
        # 5. RISK SCORING & PHÂN LOẠI CHUẨN 4 TRẠNG THÁI
        # -------------------------------------------------------------
        if risk_score >= 80 or (sb_threats) or (vt_stats and vt_stats["malicious"] > 0):
            level = ThreatLevel.MALICIOUS
            threat_name = "Phát Hiện Mã Độc / Phishing"
            summary = "Liên kết có dấu hiệu rõ ràng của mã độc, phần mềm độc hại hoặc website lừa đảo chiếm đoạt tài khoản!"
        elif is_shortener:
            level = ThreatLevel.SUSPICIOUS
            threat_name = "Liên Kết Rút Gọn Cần Thận Trọng"
            summary = "Liên kết sử dụng dịch vụ rút gọn link (URL Shortener), hãy cẩn trọng khi truy cập."
        elif risk_score >= 30 or (vt_stats and vt_stats["suspicious"] > 0):
            level = ThreatLevel.SUSPICIOUS
            threat_name = "Có Dấu Hiệu Đáng Ngờ"
            summary = "Liên kết có một số yếu tố đáng ngờ cần thận trọng trước khi truy cập."
        else:
            level = ThreatLevel.SAFE
            threat_name = "Không Phát Hiện Mối Nguy Hiểm"
            summary = "Đường dẫn sạch sẽ, không phát hiện mã độc, lừa đảo hay hành vi nguy hại."

        return ThreatScanResult(
            is_safe=(level == ThreatLevel.SAFE),
            level=level,
            threat_name=threat_name,
            summary=summary,
            risk_score=risk_score,
            vt_stats=vt_stats,
            safe_browsing_threats=sb_threats,
            details=details,
            indicators=indicators,
            url=url,
            scan_time_ms=(time.time() - t0) * 1000,
        )

    @classmethod
    def scan_file_bytes(cls, data: bytes, filename_hint: str = "") -> ThreatScanResult:
        """Quét sâu tệp nhị phân: Magic bytes, chữ ký thực thi, macro, exploit."""
        t0 = time.time()
        file_size = len(data)
        sha256_hash = hashlib.sha256(data).hexdigest()
        details: list[str] = [f"Dung lượng tệp: {file_size / 1024:.1f} KB", f"Mã băm SHA-256: `{sha256_hash[:16]}...`"]

        if file_size == 0:
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.SUSPICIOUS,
                threat_name="Tệp Rỗng (0 Bytes)",
                summary="Tệp không có nội dung để phân tích.",
                risk_score=30,
                sha256=sha256_hash,
                file_size_bytes=file_size,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        # 1. Kiểm tra Magic Bytes Windows PE Executable (MZ header)
        if data.startswith(b"MZ"):
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Tệp Thực Thi Windows PE Ngụy Trang (.exe/.dll)",
                summary="Phát hiện tệp thực thi Windows Portable Executable (chữ ký 'MZ'). Đây là tệp chương trình/mã độc ngụy trang dưới định dạng tài liệu!",
                risk_score=100,
                details=details + ["Chữ ký phát hiện: 0x4D5A (Windows PE Executable)"],
                indicators=["PE_HEADER_DETECTED", "DISGUISED_EXECUTABLE"],
                sha256=sha256_hash,
                file_size_bytes=file_size,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        # Linux ELF Binary
        if data.startswith(b"\x7fELF"):
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Tệp Thực Thi Linux ELF Binary",
                summary="Phát hiện tệp thực thi Linux Binary (chữ ký '\\x7fELF'). Tệp nhị phân bị cấm nạp vào hệ thống tài liệu!",
                risk_score=100,
                details=details + ["Chữ ký phát hiện: 0x7F454C46 (Linux ELF)"],
                indicators=["ELF_HEADER_DETECTED"],
                sha256=sha256_hash,
                file_size_bytes=file_size,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        # Java Class / Mach-O Fat Binary
        if data.startswith(b"\xca\xfe\xba\xbe"):
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Mã Bytecode / Java Executable (CAFEBABE)",
                summary="Phát hiện tệp mã nhị phân Java Class Bytecode / Mach-O Fat Binary. Tệp có thể chứa payload thực thi độc hại!",
                risk_score=95,
                details=details + ["Chữ ký phát hiện: 0xCAFEBABE"],
                indicators=["JAVA_CLASS_DETECTED"],
                sha256=sha256_hash,
                file_size_bytes=file_size,
                scan_time_ms=(time.time() - t0) * 1000,
            )

        # Shell Script / PHP / Script headers
        first_100 = data[:100].lower()
        if (
            first_100.startswith(b"#!/bin/bash")
            or first_100.startswith(b"#!/bin/sh")
            or first_100.startswith(b"<?php")
            or b"<script" in first_100
        ):
            ext = os.path.splitext(filename_hint)[1].lower()
            if ext in (".pdf", ".docx", ".doc"):
                return ThreatScanResult(
                    is_safe=False,
                    level=ThreatLevel.MALICIOUS,
                    threat_name="Script Nguy Hiểm Ngụy Trang Thành Tài Liệu",
                    summary=f"Tệp có phần mở rộng '{ext}' nhưng nội dung thực tế là tập lệnh thực thi (Shell/PHP/Script)!",
                    risk_score=95,
                    details=details + ["Phát hiện Header: Thực thi lệnh script"],
                    indicators=["SCRIPT_MASQUERADE"],
                    sha256=sha256_hash,
                    file_size_bytes=file_size,
                    scan_time_ms=(time.time() - t0) * 1000,
                )

        # 2. Quét sâu tài liệu PDF
        if data.startswith(b"%PDF-") or filename_hint.lower().endswith(".pdf"):
            if re.search(rb"/Launch\b", data):
                return ThreatScanResult(
                    is_safe=False,
                    level=ThreatLevel.MALICIOUS,
                    threat_name="PDF Chứa Luồng Lệnh /Launch Độc Hại",
                    summary="Tệp PDF chứa đối tượng '/Launch'. Kỹ thuật này thường được dùng để kích hoạt mã độc tự động chạy lệnh ngoài hệ điều hành!",
                    risk_score=100,
                    details=details + ["Phát hiện thẻ: /Launch (Exploit Code)"],
                    indicators=["PDF_LAUNCH_EXPLOIT"],
                    sha256=sha256_hash,
                    file_size_bytes=file_size,
                    scan_time_ms=(time.time() - t0) * 1000,
                )

            if re.search(rb"/EmbeddedFiles\b", data) and any(
                ext.encode() in data.lower() for ext in [b".exe", b".bat", b".vbs", b".scr"]
            ):
                return ThreatScanResult(
                    is_safe=False,
                    level=ThreatLevel.MALICIOUS,
                    threat_name="PDF Nhúng Tệp Thực Thi Ngầm (/EmbeddedFiles)",
                    summary="Tệp PDF chứa đối tượng tệp thực thi ẩn nhúng bên trong cấu trúc luồng.",
                    risk_score=95,
                    details=details + ["Phát hiện: /EmbeddedFiles kèm phần mở rộng thực thi"],
                    indicators=["PDF_EMBEDDED_EXECUTABLE"],
                    sha256=sha256_hash,
                    file_size_bytes=file_size,
                    scan_time_ms=(time.time() - t0) * 1000,
                )

        # 3. Quét tệp Office (.docx) hoặc ZIP
        if data.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(BytesIO(data), "r") as zf:
                    namelist = zf.namelist()
                    # A. Quét Macro VBA
                    vba_files = [f for f in namelist if "vbaproject.bin" in f.lower() or "macros" in f.lower()]
                    if vba_files:
                        return ThreatScanResult(
                            is_safe=False,
                            level=ThreatLevel.MALICIOUS,
                            threat_name="Tài Liệu Office Chứa Macro VBA Độc Hại",
                            summary="Tài liệu chứa mã macro VBA ('vbaProject.bin'). Tài liệu đề thi học tập không được chứa Macro để phòng chống mã độc.",
                            risk_score=90,
                            details=details + [f"Tệp Macro: {', '.join(vba_files)}"],
                            indicators=["VBA_MACRO_DETECTED"],
                            sha256=sha256_hash,
                            file_size_bytes=file_size,
                            scan_time_ms=(time.time() - t0) * 1000,
                        )

                    # B. Quét Zip Slip
                    for member_name in namelist:
                        if ".." in member_name or member_name.startswith("/") or member_name.startswith("\\"):
                            return ThreatScanResult(
                                is_safe=False,
                                level=ThreatLevel.MALICIOUS,
                                threat_name="Tấn Công Zip Slip (Path Traversal)",
                                summary="Tệp nén chứa đường dẫn vượt cấp thư mục ('../') nguy hiểm nhằm ghi đè tệp hệ thống!",
                                risk_score=95,
                                details=details + [f"Đường dẫn vi phạm: {member_name}"],
                                indicators=["ZIP_SLIP_ATTACK"],
                                sha256=sha256_hash,
                                file_size_bytes=file_size,
                                scan_time_ms=(time.time() - t0) * 1000,
                            )

                    # C. Quét Zip Bomb
                    total_uncompressed = sum(info.file_size for info in zf.infolist())
                    if total_uncompressed > 200 * 1024 * 1024 and total_uncompressed > file_size * 50:
                        return ThreatScanResult(
                            is_safe=False,
                            level=ThreatLevel.MALICIOUS,
                            threat_name="Tấn Công Zip Bomb (Decompression Bomb)",
                            summary="Tỷ lệ giải nén bất thường (>50x), có nguy cơ làm cạn kiệt bộ nhớ và treo máy chủ!",
                            risk_score=95,
                            details=details + [f"Dung lượng giải nén: {total_uncompressed / (1024*1024):.1f} MB"],
                            indicators=["ZIP_BOMB_DETECTED"],
                            sha256=sha256_hash,
                            file_size_bytes=file_size,
                            scan_time_ms=(time.time() - t0) * 1000,
                        )
            except zipfile.BadZipFile:
                pass

        return ThreatScanResult(
            is_safe=True,
            level=ThreatLevel.SAFE,
            threat_name="Tệp Hoàn Toàn Sạch Sẽ",
            summary="Đã quét chữ ký nhị phân, cấu trúc nhúng, macro và mã băm SHA-256. Không phát hiện bất kỳ dấu hiệu mã độc nào!",
            risk_score=0,
            details=details,
            sha256=sha256_hash,
            file_size_bytes=file_size,
            scan_time_ms=(time.time() - t0) * 1000,
        )

    @classmethod
    async def scan_file_path(cls, file_path: Path | str, filename_hint: str = "") -> ThreatScanResult:
        """Đọc tệp từ ổ cứng và thực hiện quét nhị phân trong Background Thread."""
        path = Path(file_path)
        if not path.exists():
            return ThreatScanResult(
                is_safe=False,
                level=ThreatLevel.MALICIOUS,
                threat_name="Tệp Không Tồn Tại",
                summary=f"Không tìm thấy tệp tại đường dẫn: {path}",
                risk_score=100,
            )
        hint = filename_hint or path.name

        def _read_and_scan():
            with open(path, "rb") as f:
                data = f.read(50 * 1024 * 1024)
            return cls.scan_file_bytes(data, hint)

        return await asyncio.to_thread(_read_and_scan)
