"""
Ultra-fast URL & Cloud Storage Resolver for DocInspector.
Handles Google Drive links, educational portals, and direct PDF/DOCX links.
Gracefully detects anti-bot protection, Cloudflare challenges, and login walls,
reporting 'không rõ nguồn gốc' whenever access is blocked.
100% Deterministic, Zero external heavy dependencies.
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


class UrlBlockedOrUnknownOriginError(Exception):
    """Raised when website blocks bot or requires private login."""
    def __init__(self, reason: str = "không rõ nguồn gốc", details: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.details = details or "Web chặn bot hoặc tài liệu riêng tư -> không rõ nguồn gốc"


@dataclass
class FetchedDocument:
    """Document stream and resolved metadata retrieved from URL."""
    content_bytes: bytes
    suggested_filename: str
    original_url: str
    resolved_url: str
    content_type: str
    is_google_drive: bool


class UrlDocumentFetcher:
    """Fetches documents from web links and cloud storage with anti-bot detection."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    RE_GDRIVE_ID = re.compile(
        r"(?:drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)|docs\.google\.com/(?:document|spreadsheets|presentation)/d/)([a-zA-Z0-9_-]{20,})",
    )

    RE_BOT_BLOCK_HTML = re.compile(
        r"(?i)(?:just\s+a\s+moment\.\.\.|attention\s+required!\s*\|\s*cloudflare|cf-browser-verification|"
        r"ddos-guard|verify\s+you\s+are\s+human|challenge-platform|access\s+denied|you\s+need\s+permission|"
        r"sign\s+in\s+to\s+continue|yêu\s*cầu\s*quyền\s*truy\s*cập|đăng\s*nhập\s*để\s*tiếp\s*tục|"
        r"bảo\s*vệ\s*chống\s*bot|bot\s*detection|enable\s*javascript\s*and\s*cookies)",
    )

    @classmethod
    def is_url(cls, target: str) -> bool:
        """Check if target string is an HTTP/HTTPS URL."""
        if not isinstance(target, str):
            return False
        clean = target.strip()
        return clean.startswith("http://") or clean.startswith("https://")

    @classmethod
    def fetch(cls, url: str, timeout_seconds: int = 15) -> FetchedDocument:
        """
        Download document content from URL or Google Drive.
        Raises UrlBlockedOrUnknownOriginError if web blocks bot.
        """
        clean_url = url.strip()
        gdrive_match = cls.RE_GDRIVE_ID.search(clean_url)

        if gdrive_match:
            file_id = gdrive_match.group(1)
            return cls._fetch_google_drive(file_id, clean_url, timeout_seconds)
        else:
            return cls._fetch_general_url(clean_url, timeout_seconds)

    @classmethod
    def _fetch_google_drive(cls, file_id: str, original_url: str, timeout: int) -> FetchedDocument:
        """Handles Google Drive file and Docs export links."""
        # Check if it was a Google Docs link -> export format docx
        if "docs.google.com/document" in original_url:
            download_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
            suggested_name = f"gdocs_{file_id[:8]}.docx"
        else:
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            suggested_name = f"gdrive_{file_id[:8]}.pdf"

        headers = {
            "User-Agent": cls.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf,*/*",
        }

        req = urllib.request.Request(download_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                content_disp = resp.headers.get("Content-Disposition", "")

                # Extract filename from Content-Disposition if present
                if "filename=" in content_disp:
                    fn_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp)
                    if fn_match:
                        suggested_name = fn_match.group(1).strip()

                # Check if Google Drive returned virus warning confirmation page
                if b"confirm=" in content or b"uc-download-link" in content:
                    confirm_match = re.search(rb'href="(/uc\?export=download[^"]+)"', content)
                    if confirm_match:
                        next_url = "https://drive.google.com" + confirm_match.group(1).decode("utf-8")
                        req2 = urllib.request.Request(next_url, headers=headers)
                        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                            content = resp2.read()

                # Check if it's an HTML page instead of PDF/DOCX (meaning private file, login required, or blocked)
                if content.startswith(b"<!DOCTYPE") or content.startswith(b"<html") or b"<body" in content[:300]:
                    html_text = content.decode("utf-8", errors="ignore")
                    if cls.RE_BOT_BLOCK_HTML.search(html_text) or "accounts.google.com" in html_text:
                        raise UrlBlockedOrUnknownOriginError(
                            reason="không rõ nguồn gốc",
                            details="Google Drive yêu cầu đăng nhập hoặc chặn bot truy cập -> không rõ nguồn gốc",
                        )

                # Validate magic bytes
                if not (content.startswith(b"%PDF-") or content.startswith(b"PK\x03\x04") or content.startswith(b"\xd0\xcf\x11\xe0")):
                    # Neither PDF nor DOCX nor DOC
                    raise UrlBlockedOrUnknownOriginError(
                        reason="không rõ nguồn gốc",
                        details="Google Drive không trả về file PDF/Word hợp lệ -> không rõ nguồn gốc",
                    )

                return FetchedDocument(
                    content_bytes=content,
                    suggested_filename=suggested_name,
                    original_url=original_url,
                    resolved_url=download_url,
                    content_type=content_type,
                    is_google_drive=True,
                )

        except urllib.error.HTTPError as e:
            # 403, 401, 429, 503
            raise UrlBlockedOrUnknownOriginError(
                reason="không rõ nguồn gốc",
                details=f"Google Drive từ chối kết nối (Mã lỗi HTTP {e.code}) -> không rõ nguồn gốc",
            )
        except urllib.error.URLError as e:
            raise UrlBlockedOrUnknownOriginError(
                reason="không rõ nguồn gốc",
                details=f"Không thể kết nối tới Google Drive ({e.reason}) -> không rõ nguồn gốc",
            )
        except UrlBlockedOrUnknownOriginError:
            raise
        except Exception as e:
            raise UrlBlockedOrUnknownOriginError(
                reason="không rõ nguồn gốc",
                details=f"Lỗi truy xuất tài liệu Google Drive ({str(e)}) -> không rõ nguồn gốc",
            )

    @classmethod
    def _fetch_general_url(cls, url: str, timeout: int) -> FetchedDocument:
        """Handles general educational portals, online test websites, and direct file URLs."""
        parsed = urllib.parse.urlparse(url)
        path_name = Path(parsed.path).name or "downloaded_document.pdf"
        
        headers = {
            "User-Agent": cls.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*",
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        }

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                content_disp = resp.headers.get("Content-Disposition", "")

                if "filename=" in content_disp:
                    fn_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp)
                    if fn_match:
                        path_name = fn_match.group(1).strip()

                # Check if website returned an anti-bot challenge or login page
                if content.startswith(b"<!DOCTYPE") or content.startswith(b"<html") or b"<body" in content[:300]:
                    html_text = content.decode("utf-8", errors="ignore")
                    if cls.RE_BOT_BLOCK_HTML.search(html_text):
                        raise UrlBlockedOrUnknownOriginError(
                            reason="không rõ nguồn gốc",
                            details="Website chặn bot (Cloudflare / Captcha / Tường lửa bảo vệ) -> không rõ nguồn gốc",
                        )

                # Check if content has valid document magic bytes
                is_pdf = content.startswith(b"%PDF-")
                is_docx = content.startswith(b"PK\x03\x04")
                is_doc = content.startswith(b"\xd0\xcf\x11\xe0")

                if not (is_pdf or is_docx or is_doc):
                    # If it's an HTML page on an educational site, it might be an article or web blocking
                    raise UrlBlockedOrUnknownOriginError(
                        reason="không rõ nguồn gốc",
                        details="Website không cung cấp trực tiếp file PDF/Word hoặc chặn bot tải về -> không rõ nguồn gốc",
                    )

                return FetchedDocument(
                    content_bytes=content,
                    suggested_filename=path_name,
                    original_url=url,
                    resolved_url=resp.geturl(),
                    content_type=content_type,
                    is_google_drive=False,
                )

        except urllib.error.HTTPError as e:
            # When server returns 403 Forbidden, 401 Unauthorized, etc.
            raise UrlBlockedOrUnknownOriginError(
                reason="không rõ nguồn gốc",
                details=f"Website chặn bot truy cập (Mã phản hồi HTTP {e.code}) -> không rõ nguồn gốc",
            )
        except urllib.error.URLError as e:
            raise UrlBlockedOrUnknownOriginError(
                reason="không rõ nguồn gốc",
                details=f"Không thể kết nối đến website ({e.reason}) -> không rõ nguồn gốc",
            )
        except UrlBlockedOrUnknownOriginError:
            raise
        except Exception as e:
            raise UrlBlockedOrUnknownOriginError(
                reason="không rõ nguồn gốc",
                details=f"Lỗi kết nối ({str(e)}) -> không rõ nguồn gốc",
            )
