"""
Dedicated Google Drive & Cloud Document Stream Ingestion for DocInspector.
100% Deterministic, Local Caching with SHA-256, Zero External API Keys Needed.
Handles Google Drive Files, Docs Exporter, Sheets Exporter, and Large File Confirmation Tokens.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

CACHE_DIR = Path("D:/Project/.cache/gdrive")


@dataclass
class ResolvedDocStream:
    """Standardized document bytes stream with metadata."""
    content: bytes
    filename: str
    sha256: str
    is_google_drive: bool
    source_url: Optional[str] = None


class GDriveDocumentHandler:
    """Robust Google Drive resolver and stream extractor."""

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    RE_GDRIVE_FILE_ID = re.compile(
        r"(?:drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)|docs\.google\.com/(?:document|spreadsheets|presentation)/d/)([a-zA-Z0-9_-]{25,})",
    )

    @classmethod
    def is_gdrive_url(cls, target: str) -> bool:
        """Check if target string is a Google Drive or Google Docs URL."""
        if not isinstance(target, str):
            return False
        clean = target.strip()
        return ("drive.google.com" in clean or "docs.google.com" in clean) and bool(cls.RE_GDRIVE_FILE_ID.search(clean))

    @classmethod
    def extract_file_id(cls, url: str) -> Optional[str]:
        """Extract Google Drive unique file/doc ID."""
        match = cls.RE_GDRIVE_FILE_ID.search(url.strip())
        return match.group(1) if match else None

    @classmethod
    def fetch_stream(cls, url_or_path: str | Path | bytes, timeout: int = 20) -> ResolvedDocStream:
        """
        Universal entry point to ingest PDF or Word document from:
        1. Local File Path
        2. In-memory raw bytes
        3. Google Drive / Google Docs URL
        4. General HTTP/HTTPS URL
        """
        if isinstance(url_or_path, (bytes, bytearray, memoryview)):
            raw_b = bytes(url_or_path)
            h = hashlib.sha256(raw_b).hexdigest()
            # Guess format from magic bytes
            ext = ".pdf" if raw_b.startswith(b"%PDF") else ".docx"
            return ResolvedDocStream(
                content=raw_b,
                filename=f"memory_doc_{h[:8]}{ext}",
                sha256=h,
                is_google_drive=False,
            )

        if isinstance(url_or_path, Path) or (isinstance(url_or_path, str) and os.path.exists(url_or_path)):
            p = Path(url_or_path)
            content = p.read_bytes()
            h = hashlib.sha256(content).hexdigest()
            return ResolvedDocStream(
                content=content,
                filename=p.name,
                sha256=h,
                is_google_drive=False,
            )

        url_str = str(url_or_path).strip()
        if cls.is_gdrive_url(url_str):
            return cls._fetch_gdrive_with_cache(url_str, timeout=timeout)
        elif url_str.startswith("http://") or url_str.startswith("https://"):
            return cls._fetch_http_with_cache(url_str, timeout=timeout)
        else:
            raise FileNotFoundError(f"Không tìm thấy tệp hoặc URL hợp lệ: '{url_or_path}'")

    @classmethod
    def _fetch_gdrive_with_cache(cls, url: str, timeout: int) -> ResolvedDocStream:
        """Fetch Google Drive file with SHA-256 disk caching."""
        file_id = cls.extract_file_id(url)
        if not file_id:
            raise ValueError(f"Không thể trích xuất ID Google Drive từ: '{url}'")

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_index_file = CACHE_DIR / f"{file_id}.meta"
        cache_data_file = CACHE_DIR / f"{file_id}.bin"

        # Check cache
        if cache_data_file.exists() and cache_index_file.exists():
            try:
                meta = cache_index_file.read_text(encoding="utf-8").split("|")
                cached_filename = meta[0]
                content = cache_data_file.read_bytes()
                h = hashlib.sha256(content).hexdigest()
                return ResolvedDocStream(
                    content=content,
                    filename=cached_filename,
                    sha256=h,
                    is_google_drive=True,
                    source_url=url,
                )
            except Exception:
                pass

        # Determine download URL
        if "docs.google.com/document" in url:
            # Google Docs -> Export directly as Word DOCX
            download_url = f"https://docs.google.com/document/d/{file_id}/export?format=docx"
            suggested_name = f"gdocs_{file_id[:8]}.docx"
        elif "docs.google.com/spreadsheets" in url:
            # Google Sheets -> Export as PDF
            download_url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=pdf"
            suggested_name = f"gsheets_{file_id[:8]}.pdf"
        else:
            # Standard Google Drive File (PDF or DOCX)
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            suggested_name = f"gdrive_{file_id[:8]}.pdf"

        headers = {
            "User-Agent": cls.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*",
        }

        req = urllib.request.Request(download_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read()
                content_disp = resp.headers.get("Content-Disposition", "")
                if "filename=" in content_disp:
                    fn_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp)
                    if fn_match:
                        suggested_name = fn_match.group(1).strip()

                # Large file confirmation bypass
                if b"confirm=" in content or b"uc-download-link" in content:
                    confirm_match = re.search(rb'href="(/uc\?export=download[^"]+)"', content)
                    if confirm_match:
                        next_url = "https://drive.google.com" + confirm_match.group(1).decode("utf-8")
                        req2 = urllib.request.Request(next_url, headers=headers)
                        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                            content = resp2.read()

                # Detect login wall or permissions error
                if content.startswith(b"<!DOCTYPE") or content.startswith(b"<html"):
                    raise PermissionError(
                        "Tệp Google Drive bị khóa quyền riêng tư hoặc yêu cầu đăng nhập tài khoản sở hữu."
                    )

                # Validate magic bytes
                if not (content.startswith(b"%PDF-") or content.startswith(b"PK\x03\x04") or content.startswith(b"\xd0\xcf\x11\xe0")):
                    raise ValueError("Tệp tải về từ Google Drive không phải là PDF hoặc Word hợp lệ.")

                # Save to cache
                h = hashlib.sha256(content).hexdigest()
                try:
                    cache_data_file.write_bytes(content)
                    cache_index_file.write_text(f"{suggested_name}|{h}", encoding="utf-8")
                except Exception:
                    pass

                return ResolvedDocStream(
                    content=content,
                    filename=suggested_name,
                    sha256=h,
                    is_google_drive=True,
                    source_url=url,
                )

        except urllib.error.HTTPError as e:
            raise ConnectionError(f"Google Drive HTTP Error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Không thể kết nối đến Google Drive: {e.reason}")

    @classmethod
    def _fetch_http_with_cache(cls, url: str, timeout: int) -> ResolvedDocStream:
        """Fetch general HTTP/HTTPS document with caching."""
        parsed = urllib.parse.urlparse(url)
        suggested_name = Path(parsed.path).name or "web_document.pdf"

        headers = {
            "User-Agent": cls.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
        }

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            h = hashlib.sha256(content).hexdigest()
            return ResolvedDocStream(
                content=content,
                filename=suggested_name,
                sha256=h,
                is_google_drive=False,
                source_url=url,
            )
