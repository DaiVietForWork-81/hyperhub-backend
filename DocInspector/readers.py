"""
Unified Input Abstraction Layer & Multi-Format Readers (Phần II, V, VI, XI, XII).
Provides deterministic, offline, security-hardened document readers:
- DocumentReader interface (supports, read)
- SecurityGuard (file size, page limit, magic bytes vs extension, ZIP-bomb & path traversal protection)
- UnicodeMathNormalizer (preserves raw_text + normalized_text, superscript/subscript, math/chemical symbols)
- OCRAdapter (strictly honors OCR_MODE=local vs OCR_MODE=off)
- PDFReader (per-page native + scan/hybrid + rotated + duplicate layer + blank page + tables + images)
- DOCXReader (sequential body paragraphs & tables, merged cells gridSpan/vMerge, structured OMML math, sup/sub, footnotes, hyperlinks, media assets)
- LegacyDOCReader (LibreOffice local converter with timeout & cleanup + OLE2 binary fallback with explicit warning)
- ImageReader (PNG, JPG, WEBP, BMP, GIF, TIFF with dimensions/orientation & OCRMode support)
- TextReader & BatchDocumentProcessor
100% Offline, Deterministic, Zero-LLM.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import EngineConfig, LegacyDocPolicy, OCRMode, get_config
from .layout_analyzer import LayoutAnalyzer
from .schema import (
    BlockKind,
    DocumentBlock,
    ImageAsset,
    PageContentState,
    PageLayout,
    ParseError,
    ParseWarning,
    SourceReference,
    StageTiming,
    TableCellModel,
    TableModel,
    WarningSeverity,
)

log = logging.getLogger("DocInspector.Readers")

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


# ============================================================================
# READER OPTIONS & OUTPUT CONTAINER
# ============================================================================

@dataclass
class ReaderOptions:
    """Tùy chọn truyền vào cho DocumentReader.read()."""
    file_name: str = "document"
    ocr_mode: Optional[OCRMode] = None
    max_pages: Optional[int] = None
    max_file_size_bytes: Optional[int] = None
    password: Optional[str] = None
    extract_images: bool = True
    extract_tables: bool = True
    detect_borderless_tables: bool = True


@dataclass
class ReaderOutput:
    """Kết quả chuẩn hóa từ bất kỳ DocumentReader nào."""
    file_name: str
    detected_format: str
    ocr_mode_used: str
    page_count: int = 0
    raw_text: str = ""
    normalized_text: str = ""
    pages: List[PageLayout] = field(default_factory=list)
    blocks: List[DocumentBlock] = field(default_factory=list)
    tables: List[TableModel] = field(default_factory=list)
    images: List[ImageAsset] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)
    footers: List[str] = field(default_factory=list)
    is_scanned: bool = False
    has_formulas: bool = False
    is_encrypted: bool = False
    is_corrupted: bool = False
    warnings: List[ParseWarning] = field(default_factory=list)
    errors: List[ParseError] = field(default_factory=list)
    stage_timings: StageTiming = field(default_factory=StageTiming)


# ============================================================================
# SECURITY & RESOURCE GUARD (Phần XI - Mục 31 & 32)
# ============================================================================

class SecurityGuard:
    """Kiểm định an toàn file, giới hạn tài nguyên, chống Zip-Bomb và Path Traversal."""

    @staticmethod
    def detect_magic_format(raw_bytes: bytes, file_name: str = "") -> Tuple[str, bool, Optional[str]]:
        """
        Nhận diện định dạng thực bằng Magic Bytes và đối chiếu với đuôi file.
        Trả về: (detected_format, is_spoofed, spoof_reason)
        """
        ext = os.path.splitext(file_name or "")[1].lower().lstrip(".")
        if not raw_bytes:
            return (ext.upper() if ext else "EMPTY"), False, None

        head = raw_bytes[:32]
        magic_fmt = "UNKNOWN"

        if head.startswith(b"%PDF-"):
            magic_fmt = "PDF"
        elif head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
            sample = raw_bytes[:4096]
            if b"word/" in sample or b"[Content_Types].xml" in sample:
                magic_fmt = "DOCX"
            elif b"xl/" in sample:
                magic_fmt = "XLSX"
            elif b"ppt/" in sample:
                magic_fmt = "PPTX"
            else:
                magic_fmt = "ZIP"
                try:
                    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
                        names = zf.namelist()
                        if any(n.startswith("word/") for n in names):
                            magic_fmt = "DOCX"
                        elif any(n.startswith("xl/") for n in names):
                            magic_fmt = "XLSX"
                        elif any(n.startswith("ppt/") for n in names):
                            magic_fmt = "PPTX"
                        elif "content.xml" in names:
                            magic_fmt = "ODT"
                except Exception:
                    pass
        elif head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            magic_fmt = "DOC"
        elif head.startswith(b"\x89PNG\r\n\x1a\n"):
            magic_fmt = "PNG"
        elif head.startswith(b"\xff\xd8\xff"):
            magic_fmt = "JPG"
        elif head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
            magic_fmt = "GIF"
        elif head.startswith(b"BM"):
            magic_fmt = "BMP"
        elif len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            magic_fmt = "WEBP"
        elif head.startswith(b"II*\x00") or head.startswith(b"MM\x00*"):
            magic_fmt = "TIFF"
        elif head.startswith(b"{\\rtf"):
            magic_fmt = "RTF"
        elif head.startswith(b"MZ"):
            magic_fmt = "EXE"

        # Kiểm tra giả mạo hoặc đặt sai đuôi file
        is_spoofed = False
        spoof_reason = None
        if magic_fmt == "EXE":
            is_spoofed = True
            spoof_reason = f"Phát hiện thực thi nhị phân MZ/PE giả mạo dưới tên '{file_name}'."
        elif ext and magic_fmt != "UNKNOWN":
            ext_map = {
                "pdf": {"PDF"},
                "docx": {"DOCX", "ZIP"},
                "doc": {"DOC", "DOCX", "RTF"},
                "png": {"PNG"},
                "jpg": {"JPG"},
                "jpeg": {"JPG"},
                "webp": {"WEBP"},
                "gif": {"GIF"},
                "bmp": {"BMP"},
                "tif": {"TIFF"},
                "tiff": {"TIFF"},
                "xlsx": {"XLSX", "ZIP"},
                "pptx": {"PPTX", "ZIP"},
                "odt": {"ODT", "ZIP"},
            }
            expected_set = ext_map.get(ext)
            if expected_set and magic_fmt not in expected_set:
                is_spoofed = True
                spoof_reason = f"Đuôi file là '.{ext}' nhưng chữ ký nhị phân thực tế là '{magic_fmt}'."

        if magic_fmt == "UNKNOWN" and ext:
            magic_fmt = ext.upper()

        return magic_fmt, is_spoofed, spoof_reason

    @staticmethod
    def validate_file_size(raw_bytes: bytes, config: EngineConfig, max_override: Optional[int] = None) -> Optional[ParseError]:
        limit = max_override or config.max_file_size_bytes
        if len(raw_bytes) > limit:
            return ParseError(
                code="FILE_TOO_LARGE",
                message=f"Kích thước tệp ({len(raw_bytes):,} bytes) vượt quá giới hạn an toàn ({limit:,} bytes).",
                stage="file_loading",
                recoverable=False,
            )
        return None

    @staticmethod
    def validate_zip_container(raw_bytes: bytes, config: EngineConfig) -> Tuple[bool, Optional[ParseError]]:
        """Kiểm tra gói ZIP/DOCX chống Zip-Bomb và Path Traversal trước khi giải nén."""
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
                infos = zf.infolist()
                if len(infos) > config.max_zip_members:
                    return False, ParseError(
                        code="ZIP_TOO_MANY_MEMBERS",
                        message=f"Tệp nén chứa {len(infos)} thành phần, vượt ngưỡng an toàn ({config.max_zip_members}).",
                        stage="file_loading",
                        recoverable=False,
                    )
                total_uncompressed = 0
                for info in infos:
                    fname = info.filename or ""
                    # Kiểm tra Path Traversal
                    norm_name = os.path.normpath(fname)
                    if fname.startswith(("/", "\\")) or ".." in norm_name.split(os.sep) or "../" in fname or "..\\" in fname:
                        return False, ParseError(
                            code="ZIP_PATH_TRAVERSAL",
                            message=f"Phát hiện đường dẫn nguy hiểm trong container: '{fname}'.",
                            stage="file_loading",
                            recoverable=False,
                        )
                    total_uncompressed += max(0, info.file_size)
                    if total_uncompressed > config.max_zip_uncompressed_bytes:
                        return False, ParseError(
                            code="ZIP_BOMB_UNCOMPRESSED_SIZE",
                            message=f"Tổng dung lượng giải nén vượt quá giới hạn an toàn ({config.max_zip_uncompressed_bytes:,} bytes).",
                            stage="file_loading",
                            recoverable=False,
                        )
                    comp_size = max(1, info.compress_size)
                    if info.file_size > 1024 * 1024 and (info.file_size / comp_size) > config.max_zip_compression_ratio:
                        return False, ParseError(
                            code="ZIP_BOMB_RATIO",
                            message=f"Tỷ lệ nén bất thường ({info.file_size / comp_size:.1f}x) tại '{fname}'.",
                            stage="file_loading",
                            recoverable=False,
                        )
            return True, None
        except zipfile.BadZipFile as e:
            return False, ParseError(
                code="CORRUPTED_ZIP_CONTAINER",
                message=f"Cấu trúc tệp DOCX/ZIP bị hỏng: {e}",
                stage="file_loading",
                recoverable=False,
            )
        except Exception as e:
            return False, ParseError(
                code="ZIP_INSPECTION_ERROR",
                message=f"Lỗi kiểm tra an toàn gói nén: {e}",
                stage="file_loading",
                recoverable=False,
            )


# ============================================================================
# CONTROLLED UNICODE & MATH NORMALIZER (Phần VI - Mục 20 & 21)
# ============================================================================

class UnicodeMathNormalizer:
    """
    Chuẩn hóa Unicode có kiểm soát:
    - Lưu cả raw_text và normalized_text riêng biệt.
    - Chuẩn hóa NFC cho tiếng Việt nhưng KHÔNG làm hỏng chỉ số trên/dưới (² ³ ₀ ₁),
      dấu trừ toán học, mũi tên phản ứng hóa học (→ ⇌ ↑ ↓) và công thức.
    - Nối dòng bị ngắt giữa câu có ngữ cảnh bảo vệ tiêu đề, phương án, bảng, công thức.
    """

    # Bảng ký tự điều khiển vô hình cần dọn dẹp nhưng giữ nguyên ký tự toán học/khoa học
    _ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")

    # Nhận diện dòng KHÔNG được phép nối vào dòng trước
    _DO_NOT_JOIN_NEXT_RE = re.compile(
        r"^\s*(?:"
        r"(?:câu(?:\s+hỏi)?|question|bài(?:\s+tập)?|problem|ví\s+dụ|chương|phần|part|section|mục)\s+(?:[IVX]+|\d+)\b"
        r"|(?:\([A-Fa-f]\)|[A-Fa-f][.:)])\s+"
        r"|(?:\([a-f]\)|[a-f][.)])\s+"
        r"|(?:\([ivx]+\)|[ivx]+[.)])\s+"
        r"|[-+•*▪▸]\s+"
        r"|\d{1,3}[.)]\s+"
        r"|\|"
        r"|(?:hình|bảng|figure|table|đáp\s+án|hướng\s+dẫn|lời\s+giải)\b"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def normalize_text(cls, raw_text: str, join_broken_lines: bool = True) -> str:
        """Chuẩn hóa văn bản có kiểm soát mà vẫn bảo toàn ký hiệu toán học & khoa học."""
        if not raw_text:
            return ""

        # 1. Chuẩn hóa xuống dòng
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

        # 2. Xóa ký tự zero-width / soft-hyphen vô hình
        text = cls._ZERO_WIDTH_RE.sub("", text)

        # 3. Chuẩn hóa NFC (NFC giữ nguyên ² ³ ₁ ₂ vì chúng không bị phân rã như NFKC!)
        text = unicodedata.normalize("NFC", text)

        # 4. Chuẩn hóa khoảng trắng ngang (giữ nguyên \t trong bảng không viền nếu có >= 2 tab)
        lines = text.split("\n")
        cleaned_lines: List[str] = []
        for ln in lines:
            if "\t" not in ln:
                # Giữ khoảng trắng >= 3 nếu là dòng căn cột bảng, ngược lại gộp khoảng trắng thừa
                if len(re.findall(r"\s{3,}", ln)) >= 2:
                    cleaned_lines.append(ln.rstrip())
                else:
                    cleaned_lines.append(re.sub(r"[ \f\v]+", " ", ln).strip())
            else:
                cleaned_lines.append(ln.rstrip())

        if not join_broken_lines:
            return "\n".join(cleaned_lines)

        # 5. Nối dòng bị ngắt vô tình giữa câu (Heuristic an toàn)
        merged: List[str] = []
        i = 0
        n = len(cleaned_lines)
        while i < n:
            curr = cleaned_lines[i]
            if not curr:
                if merged and merged[-1] != "":
                    merged.append("")
                i += 1
                continue

            # Kiểm tra xem có nên nối dòng tiếp theo vào dòng hiện tại không
            while i + 1 < n:
                nxt = cleaned_lines[i + 1]
                if not nxt:
                    break
                if cls._should_join_lines(curr, nxt):
                    # Nếu dòng hiện tại kết thúc bằng gạch nối từ bị cắt ngang (ví dụ: "phương-")
                    if re.search(r"[a-zA-ZÀ-ỹ]-$", curr) and re.match(r"^[a-zà-ỹ]", nxt):
                        curr = curr[:-1] + nxt
                    else:
                        curr = curr + " " + nxt
                    i += 1
                else:
                    break

            merged.append(curr)
            i += 1

        return "\n".join(merged).strip()

    @classmethod
    def _should_join_lines(cls, curr: str, nxt: str) -> bool:
        """Quyết định an toàn xem 2 dòng liên tiếp có phải là 1 câu bị ngắt dòng cứng do lề PDF hay không."""
        # Không nối nếu dòng hiện tại hoặc dòng kế là bảng, tiêu đề, phương án, mục lục...
        if "|" in curr or "|" in nxt or "\t" in curr or "\t" in nxt:
            return False
        if len(re.findall(r"\s{3,}", curr)) >= 2 or len(re.findall(r"\s{3,}", nxt)) >= 2:
            return False
        if cls._DO_NOT_JOIN_NEXT_RE.match(nxt) or cls._DO_NOT_JOIN_NEXT_RE.match(curr):
            return False
        # Không nối nếu dòng hiện tại kết thúc bằng dấu kết câu hoặc hai chấm
        if curr.endswith((".", "?", "!", ":", ";", "…", ")", "]")):
            return False
        # Không nối nếu dòng hiện tại ngắn (< 42 ký tự) - thường là tiêu đề hoặc dòng độc lập
        if len(curr) < 42:
            return False
        # Chỉ nối khi dòng tiếp theo bắt đầu bằng chữ thường tiếng Việt/Anh hoặc số/ký hiệu nối tiếp câu
        first_ch = nxt[0]
        if first_ch.islower() or first_ch in (",", ";"):
            return True
        return False


# ============================================================================
# LOCAL OCR ADAPTER (Phần I - Mục 1: Phân biệt rõ OCR cục bộ vs LLM, hỗ trợ OCR_MODE=off)
# ============================================================================

class OCRAdapter:
    """
    Bộ điều phối OCR cục bộ (Tesseract):
    - Không bao giờ gọi LLM hay dịch vụ đám mây.
    - Khi OCRMode.OFF: tắt hoàn toàn nhận dạng ký tự, giữ nguyên ImageAsset và gắn cờ cần xử lý thủ công.
    """

    TESS_CONFIG = r"--oem 3 --psm 6 -l vie+eng"

    @classmethod
    def is_ocr_enabled(cls, options: Optional[ReaderOptions] = None) -> bool:
        cfg = get_config()
        mode = options.ocr_mode if (options and options.ocr_mode is not None) else cfg.ocr_mode
        return mode == OCRMode.LOCAL

    @staticmethod
    def preprocess_image(img: "Image.Image") -> "Image.Image":
        """Tiền xử lý ảnh bằng PIL thuần túy trước khi đưa vào Tesseract."""
        if Image is None:
            return img
        work = img
        if work.mode != "L":
            work = work.convert("L")
        w, h = work.size
        if w > 0 and h > 0 and (w < 1000 or h < 1000):
            scale = min(2.5, max(1000.0 / w, 1000.0 / h, 1.5))
            work = work.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        if ImageEnhance is not None:
            work = ImageEnhance.Contrast(work).enhance(1.85)
        if ImageFilter is not None:
            work = work.filter(ImageFilter.SHARPEN)
        return work

    @classmethod
    def recognize_pil_image(
        cls,
        img: "Image.Image",
        options: Optional[ReaderOptions] = None,
        timeout_sec: int = 25,
    ) -> Tuple[str, str, Optional[str]]:
        """
        Thực thi OCR trên đối tượng PIL Image nếu OCR_MODE=local.
        Trả về: (ocr_text, ocr_status, warning_reason)
        ocr_status: "ocr_disabled" | "ocr_completed" | "ocr_empty" | "ocr_unavailable"
        """
        if not cls.is_ocr_enabled(options):
            return (
                "",
                "ocr_disabled",
                "OCR đang tắt theo cấu hình (OCR_MODE=off). Giữ nguyên hình ảnh gốc và đánh dấu cần kiểm tra thủ công.",
            )

        if pytesseract is None or Image is None:
            return (
                "",
                "ocr_unavailable",
                "Thư viện pytesseract hoặc Pillow chưa khả dụng trên môi trường cục bộ.",
            )

        try:
            proc_img = cls.preprocess_image(img)
        except Exception:
            proc_img = img

        try:
            txt = pytesseract.image_to_string(proc_img, config=cls.TESS_CONFIG, timeout=timeout_sec)
            txt = (txt or "").strip()
            if txt:
                return txt, "ocr_completed", None
            return "", "ocr_empty", "OCR cục bộ không nhận diện được ký tự rõ ràng từ ảnh."
        except Exception as e:
            return "", "ocr_unavailable", f"OCR cục bộ gặp lỗi hoặc quá thời gian: {e}"


# ============================================================================
# ABSTRACT DOCUMENT READER INTERFACE (Phần II - Mục 3)
# ============================================================================

class DocumentReader(ABC):
    """Giao diện chuẩn thống nhất cho mọi trình đọc định dạng tài liệu."""

    @abstractmethod
    def supports(self, source: bytes | str, detected_format: Optional[str] = None) -> bool:
        """Kiểm tra reader có hỗ trợ nguồn dữ liệu này không."""
        raise NotImplementedError

    @abstractmethod
    def read(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        """Trích xuất dữ liệu gốc, blocks, tables, images, pages và metadata."""
        raise NotImplementedError

    @staticmethod
    def _ensure_bytes(source: bytes | str) -> Tuple[bytes, str]:
        if isinstance(source, (bytes, bytearray)):
            return bytes(source), "memory_bytes"
        if isinstance(source, str) and os.path.exists(source):
            with open(source, "rb") as f:
                return f.read(), os.path.basename(source)
        if isinstance(source, str):
            return source.encode("utf-8", errors="replace"), "inline_string.txt"
        raise TypeError(f"Nguồn dữ liệu không hợp lệ: {type(source)}")


# ============================================================================
# PDF READER (Phần II - Mục 4.1 & 4.2: Native + Scanned/Hybrid + Rotated + Tables + Images)
# ============================================================================

class PDFReader(DocumentReader):
    """
    Trình đọc PDF đa chế độ:
    - Kiểm tra chất lượng từng trang độc lập (Native / Scanned / Hybrid / Duplicate Layer / Rotated / Blank).
    - Tái dựng thứ tự đọc 1-cột, 2-cột, 3-cột, khối tràn ngang và sidebar.
    - Trích xuất bảng thực tế (page.find_tables) + bảng không viền (borderless tables).
    - Trích xuất danh mục hình ảnh minh họa (ImageAsset) và tôn trọng chế độ OCR_MODE=off / local.
    """

    def supports(self, source: bytes | str, detected_format: Optional[str] = None) -> bool:
        if detected_format:
            return detected_format.upper() == "PDF"
        if isinstance(source, (bytes, bytearray)):
            return bytes(source[:5]).startswith(b"%PDF-")
        if isinstance(source, str):
            return source.lower().endswith(".pdf")
        return False

    def read(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        t0 = time.perf_counter()
        opts = options or ReaderOptions()
        cfg = get_config()
        ocr_mode = opts.ocr_mode if opts.ocr_mode is not None else cfg.ocr_mode

        raw_bytes, inferred_name = self._ensure_bytes(source)
        file_name = opts.file_name if opts.file_name != "document" else inferred_name

        out = ReaderOutput(
            file_name=file_name,
            detected_format="PDF",
            ocr_mode_used=ocr_mode.value,
        )
        out.stage_timings.file_loading_ms = (time.perf_counter() - t0) * 1000.0

        size_err = SecurityGuard.validate_file_size(raw_bytes, cfg, opts.max_file_size_bytes)
        if size_err:
            out.errors.append(size_err)
            out.is_corrupted = True
            return out

        if fitz is None:
            out.errors.append(
                ParseError(
                    code="PYMUPDF_MISSING",
                    message="Thư viện PyMuPDF (fitz) chưa được cài đặt để đọc PDF.",
                    stage="native_extraction",
                    recoverable=False,
                )
            )
            return out

        t_extract = time.perf_counter()
        try:
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
        except Exception as e:
            out.is_corrupted = True
            out.errors.append(
                ParseError(
                    code="CORRUPTED_PDF",
                    message=f"Không thể mở cấu trúc PDF (file lỗi hoặc bị cắt cụt): {e}",
                    stage="native_extraction",
                    recoverable=False,
                )
            )
            return out

        try:
            # Kiểm tra PDF bị khóa mật khẩu
            if getattr(doc, "is_encrypted", False):
                auth_ok = False
                try:
                    auth_ok = bool(doc.authenticate(opts.password or ""))
                except Exception:
                    auth_ok = False
                if not auth_ok:
                    out.is_encrypted = True
                    out.errors.append(
                        ParseError(
                            code="ENCRYPTED_PDF",
                            message="Tài liệu PDF được mã hóa bằng mật khẩu, không thể trích xuất nội dung.",
                            stage="native_extraction",
                            recoverable=False,
                        )
                    )
                    out.warnings.append(
                        ParseWarning(
                            code="ENCRYPTED_PDF",
                            message="Tệp PDF yêu cầu mật khẩu để mở.",
                            severity=WarningSeverity.ERROR,
                            requires_manual_review=True,
                        )
                    )
                    return out

            total_pages = len(doc)
            max_pages = min(total_pages, opts.max_pages or cfg.max_pages)
            out.page_count = total_pages
            if total_pages > max_pages:
                out.warnings.append(
                    ParseWarning(
                        code="PAGE_LIMIT_TRUNCATED",
                        message=f"Tài liệu có {total_pages} trang, vượt giới hạn xử lý ({max_pages} trang). Chỉ đọc {max_pages} trang đầu.",
                        severity=WarningSeverity.WARNING,
                    )
                )

            raw_page_texts: List[str] = []
            norm_page_texts: List[str] = []
            scanned_pages_count = 0
            block_seq = 0
            table_seq = 0
            image_seq = 0

            for page_idx in range(max_pages):
                page_num = page_idx + 1
                try:
                    page = doc[page_idx]
                except Exception as pe:
                    out.pages.append(
                        PageLayout(
                            page_number=page_num,
                            state=PageContentState.CORRUPTED_PAGE,
                            extraction_confidence=0.0,
                            layout_confidence=0.0,
                            warnings=[f"Lỗi đọc trang {page_num}: {pe}"],
                        )
                    )
                    out.errors.append(
                        ParseError(
                            code="CORRUPTED_PDF_PAGE",
                            message=f"Không thể đọc trang {page_num}: {pe}",
                            stage="native_extraction",
                            page=page_num,
                            recoverable=True,
                        )
                    )
                    continue

                rect = page.rect
                pw = float(rect.width) if rect else 595.0
                ph = float(rect.height) if rect else 842.0
                rotation_deg = int(getattr(page, "rotation", 0) or 0) % 360

                page_layout = PageLayout(
                    page_number=page_num,
                    width=pw,
                    height=ph,
                    rotation_deg=rotation_deg,
                )

                if rotation_deg in (90, 180, 270):
                    out.warnings.append(
                        ParseWarning(
                            code="ROTATED_PAGE",
                            message=f"Trang {page_num} bị xoay {rotation_deg}°.",
                            severity=WarningSeverity.INFO,
                            page=page_num,
                            reason="Thuộc tính /Rotate của trang PDF khác 0°.",
                            attempted_method="pymupdf_rotation_aware_extraction",
                        )
                    )
                    page_layout.warnings.append(f"Trang xoay {rotation_deg}°")

                # 1. Trích xuất danh sách hình ảnh trên trang
                page_image_assets: List[ImageAsset] = []
                if opts.extract_images:
                    try:
                        img_list = page.get_images(full=True)
                    except Exception:
                        img_list = []
                    for img_info in img_list:
                        image_seq += 1
                        xref = img_info[0]
                        img_w = int(img_info[2] or 0)
                        img_h = int(img_info[3] or 0)
                        img_ext = "PNG"
                        img_id = f"img_p{page_num:02d}_{image_seq:03d}"
                        asset = ImageAsset(
                            image_id=img_id,
                            page=page_num,
                            width=img_w,
                            height=img_h,
                            orientation_deg=rotation_deg,
                            image_format=img_ext,
                            ocr_status="not_processed",
                            source_ref=SourceReference(
                                file_name=file_name,
                                page=page_num,
                                image_id=img_id,
                                extraction_method="pdf_embedded_image",
                            ),
                        )
                        page_image_assets.append(asset)
                        out.images.append(asset)

                page_layout.image_count = len(page_image_assets)

                # 2. Trích xuất bảng native trên trang (page.find_tables)
                page_tables: List[TableModel] = []
                table_bboxes: List[Tuple[float, float, float, float]] = []
                if opts.extract_tables and hasattr(page, "find_tables"):
                    try:
                        tabs = page.find_tables()
                        found_tables = getattr(tabs, "tables", []) or []
                        for tf in found_tables:
                            rows_data = tf.extract()
                            if not rows_data or len(rows_data) < 2:
                                continue
                            cleaned_rows: List[List[str]] = []
                            for r in rows_data:
                                if not r:
                                    continue
                                row_cells = [re.sub(r"\s+", " ", (c or "").strip()) for c in r]
                                if any(row_cells):
                                    cleaned_rows.append(row_cells)
                            if len(cleaned_rows) < 2:
                                continue
                            col_cnt = max(len(r) for r in cleaned_rows)
                            if col_cnt < 2:
                                continue

                            table_seq += 1
                            tbl_id = f"tbl_p{page_num:02d}_{table_seq:03d}"
                            tbbox = tuple(float(v) for v in tf.bbox) if getattr(tf, "bbox", None) else None
                            if tbbox and len(tbbox) == 4:
                                table_bboxes.append(tbbox)

                            cell_models: List[TableCellModel] = []
                            for r_i, r_vals in enumerate(cleaned_rows):
                                for c_i, c_val in enumerate(r_vals):
                                    has_math = LayoutAnalyzer.contains_math_expression(c_val)
                                    if has_math:
                                        out.has_formulas = True
                                    cell_models.append(
                                        TableCellModel(
                                            cell_id=f"{tbl_id}_r{r_i}_c{c_i}",
                                            row_index=r_i,
                                            col_index=c_i,
                                            raw_text=c_val,
                                            text=c_val,
                                            is_header=(r_i == 0),
                                            contains_formula=has_math,
                                        )
                                    )
                            md_lines = [
                                "| " + " | ".join(cleaned_rows[0]) + " |",
                                "| " + " | ".join(["---"] * len(cleaned_rows[0])) + " |",
                            ]
                            for r_vals in cleaned_rows[1:]:
                                padded = r_vals + [""] * max(0, len(cleaned_rows[0]) - len(r_vals))
                                md_lines.append("| " + " | ".join(padded[: len(cleaned_rows[0])]) + " |")

                            t_model = TableModel(
                                table_id=tbl_id,
                                page=page_num,
                                row_count=len(cleaned_rows),
                                col_count=col_cnt,
                                headers=cleaned_rows[0],
                                cells=cell_models,
                                rows=cleaned_rows,
                                markdown="\n".join(md_lines),
                                bbox=tbbox,
                                is_borderless=False,
                                source_type="pdf_native_table",
                            )
                            page_tables.append(t_model)
                            out.tables.append(t_model)
                    except Exception as te:
                        log.debug("PDF find_tables warning on page %d: %s", page_num, te)

                page_layout.table_count = len(page_tables)

                # 3. Trích xuất các text blocks gốc với tọa độ
                try:
                    raw_blocks_fitz = page.get_text("blocks")
                except Exception:
                    raw_blocks_fitz = []

                tuple_blocks: List[Tuple[float, float, float, float, str, int]] = []
                for b in raw_blocks_fitz:
                    if len(b) >= 7:
                        tuple_blocks.append((float(b[0]), float(b[1]), float(b[2]), float(b[3]), str(b[4] or ""), int(b[6])))

                # Khử lớp văn bản trùng lặp (shadow / duplicate text layer)
                dedup_blocks, dup_removed, dup_warnings = LayoutAnalyzer.detect_and_remove_duplicate_blocks(
                    tuple_blocks, page_num
                )
                out.warnings.extend(dup_warnings)

                page_doc_blocks: List[DocumentBlock] = []
                native_char_count = 0

                for bx0, by0, bx1, by1, btext, btype in dedup_blocks:
                    if btype != 0:
                        continue
                    raw_blk_str = btext.strip("\r\n")
                    if not raw_blk_str.strip():
                        continue

                    # Kiểm tra xem block này có nằm trọn trong một bảng đã trích xuất không
                    in_table_id: Optional[str] = None
                    for t_idx, tbbox in enumerate(table_bboxes):
                        if LayoutAnalyzer._bbox_iou((bx0, by0, bx1, by1), tbbox) >= 0.70:
                            in_table_id = page_tables[t_idx].table_id
                            break

                    norm_blk_str = UnicodeMathNormalizer.normalize_text(raw_blk_str, join_broken_lines=True)
                    native_char_count += len(norm_blk_str)
                    has_math = LayoutAnalyzer.contains_math_expression(norm_blk_str)
                    if has_math:
                        out.has_formulas = True

                    kind = (
                        BlockKind.TABLE
                        if in_table_id
                        else LayoutAnalyzer.classify_block_kind(
                            norm_blk_str,
                            page_number=page_num,
                            bbox=(bx0, by0, bx1, by1),
                            page_width=pw,
                            page_height=ph,
                        )
                    )
                    block_seq += 1
                    blk_id = f"p{page_num:02d}_b{block_seq:03d}"
                    page_doc_blocks.append(
                        DocumentBlock(
                            block_id=blk_id,
                            kind=kind,
                            raw_text=raw_blk_str,
                            text=norm_blk_str,
                            page=page_num,
                            reading_order=block_seq,
                            bbox=(round(bx0, 2), round(by0, 2), round(bx1, 2), round(by1, 2)),
                            source_type="native_pdf",
                            table_id=in_table_id,
                            contains_math=has_math,
                        )
                    )

                # 4. Kiểm tra trang scan hoặc trang lai (Hybrid / Scanned PDF) theo TỪNG TRANG
                ocr_char_count = 0
                ocr_disabled_unprocessed = False
                is_page_sparse = native_char_count < cfg.min_native_chars_per_page and len(page_image_assets) > 0

                if is_page_sparse:
                    scanned_pages_count += 1
                    t_ocr = time.perf_counter()
                    if OCRAdapter.is_ocr_enabled(opts):
                        if Image is not None:
                            try:
                                pix = page.get_pixmap(dpi=220)
                                mode = "RGBA" if pix.alpha else "RGB"
                                pil_img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                                ocr_txt, ocr_status, ocr_warn = OCRAdapter.recognize_pil_image(pil_img, opts)
                                for asset in page_image_assets:
                                    asset.ocr_status = ocr_status
                                    asset.ocr_text = ocr_txt
                                    if ocr_status != "ocr_completed":
                                        asset.requires_manual_review = True
                                if ocr_txt:
                                    norm_ocr = UnicodeMathNormalizer.normalize_text(ocr_txt, join_broken_lines=True)
                                    ocr_char_count = len(norm_ocr)
                                    block_seq += 1
                                    blk_id = f"p{page_num:02d}_b{block_seq:03d}"
                                    page_doc_blocks.append(
                                        DocumentBlock(
                                            block_id=blk_id,
                                            kind=BlockKind.PARAGRAPH,
                                            raw_text=ocr_txt,
                                            text=norm_ocr,
                                            page=page_num,
                                            reading_order=block_seq,
                                            bbox=(0.0, 0.0, round(pw, 2), round(ph, 2)),
                                            source_type="local_ocr",
                                            image_id=page_image_assets[0].image_id if page_image_assets else None,
                                            contains_math=LayoutAnalyzer.contains_math_expression(norm_ocr),
                                        )
                                    )
                                elif ocr_warn:
                                    out.warnings.append(
                                        ParseWarning(
                                            code="LOW_QUALITY_SCAN_PAGE",
                                            message=f"Trang {page_num} là ảnh scan nhưng không trích xuất được văn bản rõ ràng.",
                                            severity=WarningSeverity.WARNING,
                                            page=page_num,
                                            reason=ocr_warn,
                                            attempted_method="local_tesseract_ocr",
                                            requires_manual_review=True,
                                        )
                                    )
                            except Exception as ocr_e:
                                out.warnings.append(
                                    ParseWarning(
                                        code="OCR_PAGE_ERROR",
                                        message=f"Lỗi khi chạy OCR cục bộ trên trang {page_num}: {ocr_e}",
                                        severity=WarningSeverity.WARNING,
                                        page=page_num,
                                        requires_manual_review=True,
                                    )
                                )
                    else:
                        # OCR_MODE = off: Không chạy bất kỳ model ML nào, giữ nguyên ImageAsset và gắn cờ thủ công
                        ocr_disabled_unprocessed = True
                        for asset in page_image_assets:
                            asset.ocr_status = "ocr_disabled"
                            asset.requires_manual_review = True
                        out.warnings.append(
                            ParseWarning(
                                code="OCR_DISABLED_UNPROCESSED_SCAN",
                                message=f"Trang {page_num} là trang ảnh scan nhưng OCR đang tắt (OCR_MODE=off). Đã giữ nguyên tài nguyên ảnh và đánh dấu cần kiểm tra thủ công.",
                                severity=WarningSeverity.WARNING,
                                page=page_num,
                                reason="Trang có dưới 35 ký tự văn bản gốc và chứa ảnh scan trong khi OCR_MODE=off.",
                                attempted_method="native_pdf_extraction_only",
                                requires_manual_review=True,
                            )
                        )
                    out.stage_timings.ocr_ms += (time.perf_counter() - t_ocr) * 1000.0

                # 5. Tái dựng thứ tự đọc trên trang (1/2/3 cột, spanning blocks, sidebar)
                t_layout = time.perf_counter()
                ordered_page_blocks, col_count, has_sidebar = LayoutAnalyzer.reconstruct_page_reading_order(
                    page_doc_blocks, pw, ph
                )
                out.stage_timings.layout_reconstruction_ms += (time.perf_counter() - t_layout) * 1000.0

                # 6. Phân loại trạng thái trang (PageContentState)
                page_state = LayoutAnalyzer.classify_page_state(
                    native_char_count=native_char_count,
                    ocr_char_count=ocr_char_count,
                    image_count=len(page_image_assets),
                    rotation_deg=rotation_deg,
                    duplicate_blocks_removed=dup_removed,
                    ocr_disabled_unprocessed_images=ocr_disabled_unprocessed,
                )
                if page_state == PageContentState.BLANK_PAGE:
                    out.warnings.append(
                        ParseWarning(
                            code="BLANK_PAGE_DETECTED",
                            message=f"Trang {page_num} là trang trắng (không có văn bản và hình ảnh).",
                            severity=WarningSeverity.INFO,
                            page=page_num,
                        )
                    )

                page_layout.state = page_state
                page_layout.column_count = col_count
                page_layout.has_sidebar = has_sidebar
                page_layout.native_char_count = native_char_count
                page_layout.ocr_char_count = ocr_char_count
                page_layout.block_ids = [b.block_id for b in ordered_page_blocks]
                if page_state in (PageContentState.SCANNED_IMAGE_ONLY, PageContentState.LOW_QUALITY_SCAN):
                    page_layout.extraction_confidence = 0.65 if ocr_char_count > 40 else 0.25
                elif page_state == PageContentState.BLANK_PAGE:
                    page_layout.extraction_confidence = 1.0
                else:
                    page_layout.extraction_confidence = 0.96

                out.pages.append(page_layout)
                out.blocks.extend(ordered_page_blocks)

                if ordered_page_blocks:
                    raw_page_texts.append(
                        f"--- [TRANG {page_num}] ---\n" + "\n".join(b.raw_text for b in ordered_page_blocks)
                    )
                elif page_state == PageContentState.BLANK_PAGE:
                    raw_page_texts.append(f"--- [TRANG {page_num} - TRANG TRẮNG] ---")

            # 7. Nhận diện Header/Footer lặp lại qua nhiều trang và bảng không viền
            t_post_layout = time.perf_counter()
            headers, footers = LayoutAnalyzer.detect_repeating_headers_footers(out.blocks, out.pages)
            out.headers = headers
            out.footers = footers

            if opts.detect_borderless_tables:
                borderless_tbls = LayoutAnalyzer.detect_borderless_tables(
                    out.blocks, existing_table_count=len(out.tables)
                )
                out.tables.extend(borderless_tbls)

            # Cập nhật lại reading_order toàn cục và xây dựng normalized_text (bỏ qua header/footer lặp lại nhưng vẫn giữ trong out.blocks)
            for global_idx, b in enumerate(out.blocks):
                b.reading_order = global_idx + 1

            for p in out.pages:
                p_blocks = [
                    b for b in out.blocks
                    if b.page == p.page_number and b.kind not in (BlockKind.HEADER, BlockKind.FOOTER, BlockKind.PAGE_NUMBER)
                ]
                if p_blocks:
                    norm_page_texts.append(
                        f"--- [TRANG {p.page_number}] ---\n" + "\n".join(b.text for b in p_blocks)
                    )

            out.stage_timings.layout_reconstruction_ms += (time.perf_counter() - t_post_layout) * 1000.0
            out.raw_text = "\n\n".join(raw_page_texts).strip()
            out.normalized_text = "\n\n".join(norm_page_texts).strip()
            out.is_scanned = scanned_pages_count > 0 and scanned_pages_count >= max(1, max_pages // 2)

        finally:
            try:
                doc.close()
            except Exception:
                pass

        out.stage_timings.native_extraction_ms = (
            (time.perf_counter() - t_extract) * 1000.0
            - out.stage_timings.ocr_ms
            - out.stage_timings.layout_reconstruction_ms
        )
        return out


# ============================================================================
# DOCX READER (Phần II - Mục 4.3: Sequential Paragraphs & Tables, Merged Cells, OMML, Sup/Sub)
# ============================================================================

class DOCXReader(DocumentReader):
    """
    Trình đọc DOCX bảo toàn cấu trúc tuần tự trong <w:body>:
    - Duyệt tuần tự đoạn văn (<w:p>) và bảng (<w:tbl>) theo đúng thứ tự xuất hiện.
    - Bảo toàn ô gộp ngang (w:gridSpan) và ô gộp dọc (w:vMerge).
    - Bảo toàn chỉ số trên/dưới (w:vertAlign superscript/subscript), in đậm/nghiêng/gạch chân, hyperlinks, footnotes.
    - Chuyển đổi công thức toán học OMML (<m:oMath>, <m:f>, <m:rad>, <m:sSup>, <m:sSub>) sang biểu diễn cấu trúc rõ ràng.
    - Trích xuất hình ảnh nhúng từ word/media/* và liên kết qua r:embed.
    """

    W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    M_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    WP_NS = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
    V_NS = "{urn:schemas-microsoft-com:vml}"

    def supports(self, source: bytes | str, detected_format: Optional[str] = None) -> bool:
        if detected_format and detected_format.upper() == "DOCX":
            return True
        if isinstance(source, str) and source.lower().endswith(".docx"):
            return True
        if isinstance(source, (bytes, bytearray)) and bytes(source[:4]) == b"PK\x03\x04":
            fmt, _, _ = SecurityGuard.detect_magic_format(bytes(source))
            return fmt == "DOCX"
        return False

    def read(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        t0 = time.perf_counter()
        opts = options or ReaderOptions()
        cfg = get_config()
        ocr_mode = opts.ocr_mode if opts.ocr_mode is not None else cfg.ocr_mode

        raw_bytes, inferred_name = self._ensure_bytes(source)
        file_name = opts.file_name if opts.file_name != "document" else inferred_name

        out = ReaderOutput(
            file_name=file_name,
            detected_format="DOCX",
            ocr_mode_used=ocr_mode.value,
        )
        out.stage_timings.file_loading_ms = (time.perf_counter() - t0) * 1000.0

        size_err = SecurityGuard.validate_file_size(raw_bytes, cfg, opts.max_file_size_bytes)
        if size_err:
            out.errors.append(size_err)
            out.is_corrupted = True
            return out

        zip_ok, zip_err = SecurityGuard.validate_zip_container(raw_bytes, cfg)
        if not zip_ok and zip_err:
            out.errors.append(zip_err)
            out.is_corrupted = True
            return out

        t_extract = time.perf_counter()
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zf:
                namelist = set(zf.namelist())
                if "word/document.xml" not in namelist:
                    out.is_corrupted = True
                    out.errors.append(
                        ParseError(
                            code="INVALID_DOCX_STRUCTURE",
                            message="Gói ZIP không chứa 'word/document.xml'.",
                            stage="native_extraction",
                            recoverable=False,
                        )
                    )
                    return out

                # 1. Đọc bảng ánh xạ relationships (rId -> target) để liên kết hình ảnh & hyperlinks
                rel_map: Dict[str, str] = {}
                if "word/_rels/document.xml.rels" in namelist:
                    try:
                        rels_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
                        for rel in rels_root:
                            r_id = rel.attrib.get("Id")
                            target = rel.attrib.get("Target")
                            if r_id and target:
                                rel_map[r_id] = target
                    except Exception:
                        pass

                # 2. Trích xuất hình ảnh trong word/media/*
                media_to_image_id: Dict[str, str] = {}
                img_seq = 0
                for name in sorted(namelist):
                    if name.startswith("word/media/"):
                        img_seq += 1
                        img_id = f"img_docx_{img_seq:03d}"
                        img_bytes = zf.read(name)
                        ext = os.path.splitext(name)[1].lstrip(".").upper() or "PNG"
                        w, h = 0, 0
                        if Image is not None:
                            try:
                                with Image.open(io.BytesIO(img_bytes)) as pil_im:
                                    w, h = pil_im.size
                            except Exception:
                                pass
                        asset = ImageAsset(
                            image_id=img_id,
                            page=1,
                            width=w,
                            height=h,
                            image_format=ext,
                            byte_size=len(img_bytes),
                            ocr_status="not_processed",
                            source_ref=SourceReference(
                                file_name=file_name,
                                page=1,
                                image_id=img_id,
                                extraction_method="docx_media",
                            ),
                        )
                        out.images.append(asset)
                        short_target = name[len("word/"):]  # "media/image1.png"
                        media_to_image_id[short_target] = img_id
                        media_to_image_id[name] = img_id

                # 3. Đọc Footnotes (nếu có)
                footnotes_map: Dict[str, str] = {}
                if "word/footnotes.xml" in namelist:
                    try:
                        fn_root = ET.fromstring(zf.read("word/footnotes.xml"))
                        for fn_elem in fn_root.iter(f"{self.W_NS}footnote"):
                            fn_id = fn_elem.attrib.get(f"{self.W_NS}id")
                            if fn_id and fn_id not in ("-1", "0"):
                                fn_texts = [t.text for t in fn_elem.iter(f"{self.W_NS}t") if t.text]
                                if fn_texts:
                                    footnotes_map[fn_id] = "".join(fn_texts).strip()
                    except Exception:
                        pass

                # 4. Đọc Headers và Footers
                for name in sorted(namelist):
                    if re.match(r"^word/header\d*\.xml$", name):
                        try:
                            h_root = ET.fromstring(zf.read(name))
                            h_txt = " ".join(t.text.strip() for t in h_root.iter(f"{self.W_NS}t") if t.text and t.text.strip())
                            if h_txt and h_txt not in out.headers:
                                out.headers.append(h_txt)
                        except Exception:
                            pass
                    elif re.match(r"^word/footer\d*\.xml$", name):
                        try:
                            f_root = ET.fromstring(zf.read(name))
                            f_txt = " ".join(t.text.strip() for t in f_root.iter(f"{self.W_NS}t") if t.text and t.text.strip())
                            if f_txt and f_txt not in out.footers:
                                out.footers.append(f_txt)
                        except Exception:
                            pass

                # 5. Duyệt tuần tự <w:body> trong word/document.xml
                doc_root = ET.fromstring(zf.read("word/document.xml"))
                body = doc_root.find(f"{self.W_NS}body")
                if body is None:
                    body = doc_root

                current_page = 1
                block_seq = 0
                table_seq = 0
                raw_chunks: List[str] = []
                norm_chunks: List[str] = []

                for child in body:
                    # Kiểm tra ngắt trang cứng trong phần tử
                    page_breaks = len(list(child.iter(f"{self.W_NS}lastRenderedPageBreak"))) + sum(
                        1 for br in child.iter(f"{self.W_NS}br") if br.attrib.get(f"{self.W_NS}type") == "page"
                    )

                    if child.tag == f"{self.W_NS}p":
                        p_raw, p_meta, p_images, p_has_math = self._extract_paragraph(
                            child, rel_map, media_to_image_id, footnotes_map
                        )
                        if p_has_math:
                            out.has_formulas = True
                        if p_raw.strip() or p_images:
                            p_norm = UnicodeMathNormalizer.normalize_text(p_raw, join_broken_lines=False)
                            kind = LayoutAnalyzer.classify_block_kind(
                                p_norm, page_number=current_page, style_meta=p_meta
                            )
                            if p_images and not p_norm.strip():
                                kind = BlockKind.IMAGE
                            block_seq += 1
                            blk_id = f"p{current_page:02d}_b{block_seq:03d}"
                            out.blocks.append(
                                DocumentBlock(
                                    block_id=blk_id,
                                    kind=kind,
                                    raw_text=p_raw,
                                    text=p_norm,
                                    page=current_page,
                                    reading_order=block_seq,
                                    source_type="native_docx",
                                    style_meta=p_meta,
                                    image_id=p_images[0] if p_images else None,
                                    contains_math=p_has_math or LayoutAnalyzer.contains_math_expression(p_norm),
                                )
                            )
                            if p_raw.strip():
                                raw_chunks.append(p_raw)
                                norm_chunks.append(p_norm)

                    elif child.tag == f"{self.W_NS}tbl":
                        table_seq += 1
                        tbl_id = f"tbl_p{current_page:02d}_{table_seq:03d}"
                        t_model, tbl_has_math = self._extract_table(
                            child, tbl_id, current_page, rel_map, media_to_image_id, footnotes_map
                        )
                        if tbl_has_math:
                            out.has_formulas = True
                        if t_model.row_count > 0:
                            out.tables.append(t_model)
                            block_seq += 1
                            blk_id = f"p{current_page:02d}_b{block_seq:03d}"
                            out.blocks.append(
                                DocumentBlock(
                                    block_id=blk_id,
                                    kind=BlockKind.TABLE,
                                    raw_text=t_model.markdown,
                                    text=t_model.markdown,
                                    page=current_page,
                                    reading_order=block_seq,
                                    source_type="native_docx_table",
                                    table_id=tbl_id,
                                    contains_math=tbl_has_math,
                                )
                            )
                            raw_chunks.append(t_model.markdown)
                            norm_chunks.append(t_model.markdown)

                    if page_breaks > 0:
                        current_page += page_breaks

                # Tổng hợp PageLayout cho DOCX
                estimated_pages = max(current_page, max(1, sum(len(c) for c in norm_chunks) // 2500))
                out.page_count = estimated_pages
                for p_num in range(1, estimated_pages + 1):
                    p_blks = [b.block_id for b in out.blocks if b.page == p_num]
                    out.pages.append(
                        PageLayout(
                            page_number=p_num,
                            width=595.0,
                            height=842.0,
                            state=PageContentState.NATIVE_TEXT,
                            column_count=1,
                            native_char_count=sum(len(b.text) for b in out.blocks if b.page == p_num),
                            image_count=len(out.images) if p_num == 1 else 0,
                            table_count=sum(1 for t in out.tables if t.page == p_num),
                            block_ids=p_blks,
                        )
                    )

                out.raw_text = "\n".join(raw_chunks).strip()
                out.normalized_text = "\n".join(norm_chunks).strip()

        except Exception as e:
            out.is_corrupted = True
            out.errors.append(
                ParseError(
                    code="DOCX_PARSE_ERROR",
                    message=f"Lỗi phân tích cấu trúc XML trong DOCX: {e}",
                    stage="native_extraction",
                    recoverable=False,
                )
            )

        out.stage_timings.native_extraction_ms = (time.perf_counter() - t_extract) * 1000.0
        return out

    def _extract_paragraph(
        self,
        p_elem: ET.Element,
        rel_map: Dict[str, str],
        media_to_image_id: Dict[str, str],
        footnotes_map: Dict[str, str],
    ) -> Tuple[str, Dict[str, Any], List[str], bool]:
        """Trích xuất văn bản, định dạng, công thức OMML và ảnh nhúng từ một phần tử <w:p>."""
        meta: Dict[str, Any] = {}
        images_found: List[str] = []
        has_math = False

        # Kiểm tra style đoạn văn (Heading, List...)
        pPr = p_elem.find(f"{self.W_NS}pPr")
        if pPr is not None:
            pStyle = pPr.find(f"{self.W_NS}pStyle")
            if pStyle is not None:
                style_val = pStyle.attrib.get(f"{self.W_NS}val", "")
                meta["style"] = style_val
                if "heading" in style_val.lower() or "title" in style_val.lower():
                    meta["is_heading"] = True
            numPr = pPr.find(f"{self.W_NS}numPr")
            if numPr is not None:
                meta["is_list_item"] = True
                ilvl = numPr.find(f"{self.W_NS}ilvl")
                if ilvl is not None:
                    meta["list_level"] = int(ilvl.attrib.get(f"{self.W_NS}val", "0") or 0)

        parts: List[str] = []
        bold_runs = 0
        total_runs = 0

        for child in p_elem:
            if child.tag == f"{self.W_NS}r":
                total_runs += 1
                r_txt, r_bold, r_imgs = self._extract_run(child, rel_map, media_to_image_id, footnotes_map)
                if r_bold:
                    bold_runs += 1
                if r_imgs:
                    images_found.extend(r_imgs)
                if r_txt:
                    parts.append(r_txt)
            elif child.tag == f"{self.W_NS}hyperlink":
                r_id = child.attrib.get(f"{self.R_NS}id")
                link_url = rel_map.get(r_id, "") if r_id else ""
                hl_texts: List[str] = []
                for sub_r in child.iter(f"{self.W_NS}r"):
                    rt, _, r_imgs = self._extract_run(sub_r, rel_map, media_to_image_id, footnotes_map)
                    if r_imgs:
                        images_found.extend(r_imgs)
                    if rt:
                        hl_texts.append(rt)
                hl_str = "".join(hl_texts)
                if hl_str and link_url and link_url not in hl_str:
                    parts.append(f"{hl_str} ({link_url})")
                elif hl_str:
                    parts.append(hl_str)
            elif child.tag in (f"{self.M_NS}oMath", f"{self.M_NS}oMathPara"):
                has_math = True
                math_str = self._extract_omml(child)
                if math_str:
                    parts.append(f" {math_str} ")

        if total_runs > 0 and bold_runs == total_runs:
            meta["is_bold"] = True

        full_p = "".join(parts)
        return full_p, meta, images_found, has_math

    def _extract_run(
        self,
        r_elem: ET.Element,
        rel_map: Dict[str, str],
        media_to_image_id: Dict[str, str],
        footnotes_map: Dict[str, str],
    ) -> Tuple[str, bool, List[str]]:
        """Trích xuất một <w:r> kèm superscript/subscript, footnote và ảnh nhúng."""
        is_bold = False
        vert_align = None
        rPr = r_elem.find(f"{self.W_NS}rPr")
        if rPr is not None:
            if rPr.find(f"{self.W_NS}b") is not None:
                is_bold = True
            va = rPr.find(f"{self.W_NS}vertAlign")
            if va is not None:
                vert_align = va.attrib.get(f"{self.W_NS}val")

        imgs: List[str] = []
        # Tìm blip ảnh nhúng
        for blip in r_elem.iter(f"{self.A_NS}blip"):
            embed_id = blip.attrib.get(f"{self.R_NS}embed")
            if embed_id and embed_id in rel_map:
                target = rel_map[embed_id].lstrip("/")
                img_id = media_to_image_id.get(target) or media_to_image_id.get(f"word/{target}")
                if img_id:
                    imgs.append(img_id)

        for imdata in r_elem.iter(f"{self.V_NS}imagedata"):
            embed_id = imdata.attrib.get(f"{self.R_NS}id")
            if embed_id and embed_id in rel_map:
                target = rel_map[embed_id].lstrip("/")
                img_id = media_to_image_id.get(target) or media_to_image_id.get(f"word/{target}")
                if img_id:
                    imgs.append(img_id)

        run_Verify: List[str] = []
        for sub in r_elem:
            if sub.tag == f"{self.W_NS}t" and sub.text:
                run_Verify.append(sub.text)
            elif sub.tag == f"{self.W_NS}tab":
                run_Verify.append("\t")
            elif sub.tag in (f"{self.W_NS}br", f"{self.W_NS}cr"):
                run_Verify.append("\n")
            elif sub.tag == f"{self.W_NS}footnoteReference":
                fn_id = sub.attrib.get(f"{self.W_NS}id")
                if fn_id and fn_id in footnotes_map:
                    run_Verify.append(f" [Chú thích {fn_id}: {footnotes_map[fn_id]}]")

        txt = "".join(run_Verify)
        if txt and vert_align == "superscript":
            txt = f"^{{{txt}}}" if len(txt) > 1 else f"^{txt}"
        elif txt and vert_align == "subscript":
            txt = f"_{{{txt}}}" if len(txt) > 1 else f"_{txt}"

        return txt, is_bold, imgs

    def _extract_omml(self, elem: ET.Element) -> str:
        """
        Chuyển đổi cây công thức toán học OMML (<m:oMath>) sang ký hiệu cấu trúc (LaTeX-like):
        - <m:f> -> \\frac{num}{den}
        - <m:rad> -> \\sqrt[deg]{base} hoặc \\sqrt{base}
        - <m:sSup> -> {base}^{sup}
        - <m:sSub> -> {base}_{sub}
        - <m:sSubSup> -> {base}_{sub}^{sup}
        - <m:nary> -> \\int / \\sum
        """
        tag = elem.tag
        if tag == f"{self.M_NS}t":
            return elem.text or ""
        if tag == f"{self.M_NS}f":
            num_el = elem.find(f"{self.M_NS}num")
            den_el = elem.find(f"{self.M_NS}den")
            num_s = self._extract_omml(num_el).strip() if num_el is not None else ""
            den_s = self._extract_omml(den_el).strip() if den_el is not None else ""
            return f"\\frac{{{num_s}}}{{{den_s}}}"
        if tag == f"{self.M_NS}rad":
            deg_el = elem.find(f"{self.M_NS}deg")
            base_el = elem.find(f"{self.M_NS}e")
            deg_s = self._extract_omml(deg_el).strip() if deg_el is not None else ""
            base_s = self._extract_omml(base_el).strip() if base_el is not None else ""
            if deg_s:
                return f"\\sqrt[{deg_s}]{{{base_s}}}"
            return f"\\sqrt{{{base_s}}}"
        if tag == f"{self.M_NS}sSup":
            base_el = elem.find(f"{self.M_NS}e")
            sup_el = elem.find(f"{self.M_NS}sup")
            base_s = self._extract_omml(base_el).strip() if base_el is not None else ""
            sup_s = self._extract_omml(sup_el).strip() if sup_el is not None else ""
            return f"{base_s}^{{{sup_s}}}"
        if tag == f"{self.M_NS}sSub":
            base_el = elem.find(f"{self.M_NS}e")
            sub_el = elem.find(f"{self.M_NS}sub")
            base_s = self._extract_omml(base_el).strip() if base_el is not None else ""
            sub_s = self._extract_omml(sub_el).strip() if sub_el is not None else ""
            return f"{base_s}_{{{sub_s}}}"
        if tag == f"{self.M_NS}sSubSup":
            base_el = elem.find(f"{self.M_NS}e")
            sub_el = elem.find(f"{self.M_NS}sub")
            sup_el = elem.find(f"{self.M_NS}sup")
            base_s = self._extract_omml(base_el).strip() if base_el is not None else ""
            sub_s = self._extract_omml(sub_el).strip() if sub_el is not None else ""
            sup_s = self._extract_omml(sup_el).strip() if sup_el is not None else ""
            return f"{base_s}_{{{sub_s}}}^{{{sup_s}}}"
        if tag == f"{self.M_NS}d":
            # Dấu ngoặc bao quanh (delimiter)
            inner = " , ".join(self._extract_omml(e).strip() for e in elem.findall(f"{self.M_NS}e"))
            return f"({inner})"

        return "".join(self._extract_omml(child) for child in elem)

    def _extract_table(
        self,
        tbl_elem: ET.Element,
        table_id: str,
        page_num: int,
        rel_map: Dict[str, str],
        media_to_image_id: Dict[str, str],
        footnotes_map: Dict[str, str],
    ) -> Tuple[TableModel, bool]:
        """Trích xuất bảng <w:tbl> bảo toàn ô gộp ngang (gridSpan), ô gộp dọc (vMerge), công thức và ảnh."""
        cells: List[TableCellModel] = []
        rows_matrix: List[List[str]] = []
        has_math_any = False

        # Theo dõi ô đang mở vMerge theo cột để cộng row_span
        active_vmerge_by_col: Dict[int, TableCellModel] = {}

        tr_list = tbl_elem.findall(f"{self.W_NS}tr")
        for r_idx, tr in enumerate(tr_list):
            row_values: List[str] = []
            col_cursor = 0
            for tc in tr.findall(f"{self.W_NS}tc"):
                tcPr = tc.find(f"{self.W_NS}tcPr")
                col_span = 1
                vmerge_state: Optional[str] = None  # None | "restart" | "continue"
                if tcPr is not None:
                    gs = tcPr.find(f"{self.W_NS}gridSpan")
                    if gs is not None:
                        try:
                            col_span = max(1, int(gs.attrib.get(f"{self.W_NS}val", "1")))
                        except ValueError:
                            col_span = 1
                    vm = tcPr.find(f"{self.W_NS}vMerge")
                    if vm is not None:
                        val = vm.attrib.get(f"{self.W_NS}val", "continue")
                        vmerge_state = "restart" if val == "restart" else "continue"

                # Trích xuất mọi đoạn văn trong ô bảng
                cell_paras: List[str] = []
                cell_imgs: List[str] = []
                cell_math = False
                for p in tc.findall(f"{self.W_NS}p"):
                    p_raw, _, p_imgs, p_m = self._extract_paragraph(
                        p, rel_map, media_to_image_id, footnotes_map
                    )
                    if p_m:
                        cell_math = True
                        has_math_any = True
                    if p_imgs:
                        cell_imgs.extend(p_imgs)
                    if p_raw.strip():
                        cell_paras.append(p_raw.strip())

                # Hỗ trợ bảng lồng nhau (nested table) bên trong ô
                for nested_tbl in tc.findall(f"{self.W_NS}tbl"):
                    nt_model, nt_m = self._extract_table(
                        nested_tbl, f"{table_id}_nested", page_num, rel_map, media_to_image_id, footnotes_map
                    )
                    if nt_m:
                        cell_math = True
                        has_math_any = True
                    if nt_model.rows:
                        nested_str = "; ".join(" / ".join(r) for r in nt_model.rows)
                        cell_paras.append(f"[Bảng con: {nested_str}]")

                raw_cell_text = "\n".join(cell_paras).strip()
                norm_cell_text = UnicodeMathNormalizer.normalize_text(raw_cell_text, join_broken_lines=False)

                if vmerge_state == "continue" and col_cursor in active_vmerge_by_col:
                    # Ô gộp dọc nối tiếp từ hàng trên
                    parent_cell = active_vmerge_by_col[col_cursor]
                    parent_cell.row_span += 1
                    if norm_cell_text:
                        parent_cell.text = (parent_cell.text + "\n" + norm_cell_text).strip()
                else:
                    cell_model = TableCellModel(
                        cell_id=f"{table_id}_r{r_idx}_c{col_cursor}",
                        row_index=r_idx,
                        col_index=col_cursor,
                        row_span=1,
                        col_span=col_span,
                        raw_text=raw_cell_text,
                        text=norm_cell_text,
                        is_header=(r_idx == 0),
                        contains_formula=cell_math or LayoutAnalyzer.contains_math_expression(norm_cell_text),
                        image_ids=cell_imgs,
                    )
                    cells.append(cell_model)
                    if vmerge_state == "restart":
                        active_vmerge_by_col[col_cursor] = cell_model
                    else:
                        active_vmerge_by_col.pop(col_cursor, None)

                display_val = norm_cell_text.replace("\n", " ")
                row_values.append(display_val)
                for _ in range(col_span - 1):
                    row_values.append("")
                col_cursor += col_span

            if any(v.strip() for v in row_values):
                rows_matrix.append(row_values)

        max_cols = max((len(r) for r in rows_matrix), default=0)
        md_lines: List[str] = []
        if rows_matrix and max_cols > 0:
            h_row = rows_matrix[0] + [""] * max(0, max_cols - len(rows_matrix[0]))
            md_lines.append("| " + " | ".join(h_row[:max_cols]) + " |")
            md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
            for r_vals in rows_matrix[1:]:
                padded = r_vals + [""] * max(0, max_cols - len(r_vals))
                md_lines.append("| " + " | ".join(padded[:max_cols]) + " |")

        return (
            TableModel(
                table_id=table_id,
                page=page_num,
                row_count=len(rows_matrix),
                col_count=max_cols,
                headers=rows_matrix[0] if rows_matrix else [],
                cells=cells,
                rows=rows_matrix,
                markdown="\n".join(md_lines),
                is_borderless=False,
                source_type="docx_native_table",
            ),
            has_math_any,
        )


# ============================================================================
# LEGACY DOC READER (Phần II - Mục 4.4: LibreOffice Converter + Safe Binary Fallback)
# ============================================================================

class LegacyDOCReader(DocumentReader):
    """
    Trình đọc định dạng .DOC cũ (OLE2 Compound Document):
    - Ưu tiên gọi bộ chuyển đổi LibreOffice cục bộ (soffice --headless --convert-to docx)
      với timeout chặt chẽ, kiểm tra exit code và dọn thư mục tạm an toàn.
    - Nếu máy không cài LibreOffice: phát cảnh báo rõ ràng (LEGACY_DOC_CONVERTER_MISSING)
      và dùng bộ trích xuất luồng văn bản nhị phân (UTF-16LE / CP1258) có kiểm soát.
    """

    SOFFICE_CANDIDATES = [
        "soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
    ]

    def supports(self, source: bytes | str, detected_format: Optional[str] = None) -> bool:
        if detected_format and detected_format.upper() in ("DOC", "DOC_OLE2"):
            return True
        if isinstance(source, (bytes, bytearray)) and bytes(source[:8]) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            return True
        if isinstance(source, str) and source.lower().endswith(".doc"):
            return True
        return False

    @classmethod
    def _find_soffice(cls) -> Optional[str]:
        for cand in cls.SOFFICE_CANDIDATES:
            found = shutil.which(cand) if not os.path.isabs(cand) else (cand if os.path.exists(cand) else None)
            if found:
                return found
        return None

    def read(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        t0 = time.perf_counter()
        opts = options or ReaderOptions()
        cfg = get_config()
        ocr_mode = opts.ocr_mode if opts.ocr_mode is not None else cfg.ocr_mode

        raw_bytes, inferred_name = self._ensure_bytes(source)
        file_name = opts.file_name if opts.file_name != "document" else inferred_name

        # Nếu file có đuôi .doc nhưng thực chất là DOCX (ZIP) hoặc RTF, định tuyến đúng reader
        magic_fmt, _, _ = SecurityGuard.detect_magic_format(raw_bytes, file_name)
        if magic_fmt == "DOCX":
            return DOCXReader().read(raw_bytes, opts)

        out = ReaderOutput(
            file_name=file_name,
            detected_format="DOC",
            ocr_mode_used=ocr_mode.value,
        )
        out.stage_timings.file_loading_ms = (time.perf_counter() - t0) * 1000.0

        size_err = SecurityGuard.validate_file_size(raw_bytes, cfg, opts.max_file_size_bytes)
        if size_err:
            out.errors.append(size_err)
            out.is_corrupted = True
            return out

        # Thử chuyển đổi bằng LibreOffice cục bộ nếu có
        soffice_bin = self._find_soffice()
        if soffice_bin and cfg.legacy_doc_policy in (
            LegacyDocPolicy.LIBREOFFICE_THEN_BINARY_FALLBACK,
            LegacyDocPolicy.LIBREOFFICE_STRICT,
        ):
            tmp_dir = tempfile.mkdtemp(prefix="docinspector_doc_")
            try:
                in_path = os.path.join(tmp_dir, "input.doc")
                out_path = os.path.join(tmp_dir, "input.docx")
                with open(in_path, "wb") as f:
                    f.write(raw_bytes)
                proc = subprocess.run(
                    [soffice_bin, "--headless", "--convert-to", "docx", "--outdir", tmp_dir, in_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=cfg.libreoffice_timeout_sec,
                    check=False,
                )
                if proc.returncode == 0 and os.path.exists(out_path):
                    with open(out_path, "rb") as f_converted:
                        docx_bytes = f_converted.read()
                    docx_out = DOCXReader().read(docx_bytes, opts)
                    docx_out.detected_format = "DOC"
                    docx_out.warnings.append(
                        ParseWarning(
                            code="LEGACY_DOC_CONVERTED_VIA_LIBREOFFICE",
                            message="Tệp .DOC cũ đã được chuyển đổi sang .DOCX cục bộ qua LibreOffice.",
                            severity=WarningSeverity.INFO,
                            attempted_method="libreoffice_headless_convert",
                        )
                    )
                    return docx_out
            except subprocess.TimeoutExpired:
                out.warnings.append(
                    ParseWarning(
                        code="LEGACY_DOC_CONVERSION_TIMEOUT",
                        message=f"Tiến trình chuyển đổi .DOC qua LibreOffice vượt quá {cfg.libreoffice_timeout_sec}s.",
                        severity=WarningSeverity.WARNING,
                        attempted_method="libreoffice_headless_convert",
                    )
                )
            except Exception as ce:
                out.warnings.append(
                    ParseWarning(
                        code="LEGACY_DOC_CONVERSION_FAILED",
                        message=f"Không thể chuyển đổi .DOC qua LibreOffice: {ce}",
                        severity=WarningSeverity.WARNING,
                        attempted_method="libreoffice_headless_convert",
                    )
                )
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            out.warnings.append(
                ParseWarning(
                    code="LEGACY_DOC_CONVERTER_MISSING",
                    message="Định dạng .DOC (OLE2) cần LibreOffice cục bộ để bảo toàn bảng biểu/công thức đầy đủ. Đã chuyển sang chế độ trích xuất văn bản nhị phân dự phòng.",
                    severity=WarningSeverity.WARNING,
                    reason="Không tìm thấy tiến trình 'soffice' (LibreOffice) trên hệ thống.",
                    attempted_method="ole2_binary_text_fallback",
                )
            )
            if cfg.legacy_doc_policy == LegacyDocPolicy.LIBREOFFICE_STRICT:
                out.errors.append(
                    ParseError(
                        code="LIBREOFFICE_REQUIRED_FOR_DOC",
                        message="Cấu hình yêu cầu LibreOffice để đọc file .DOC nhưng công cụ chưa được cài đặt.",
                        stage="native_extraction",
                        recoverable=False,
                    )
                )
                return out

        # Fallback trích xuất chuỗi UTF-16LE / CP1258 từ luồng nhị phân .DOC
        t_extract = time.perf_counter()
        raw_text = self._extract_ole2_text_streams(raw_bytes)
        norm_text = UnicodeMathNormalizer.normalize_text(raw_text, join_broken_lines=True)

        out.raw_text = raw_text
        out.normalized_text = norm_text
        out.page_count = max(1, len(norm_text) // 2500)
        out.has_formulas = LayoutAnalyzer.contains_math_expression(norm_text)

        paragraphs = [p.strip() for p in norm_text.split("\n") if p.strip()]
        for idx, p_str in enumerate(paragraphs):
            kind = LayoutAnalyzer.classify_block_kind(p_str, page_number=1)
            out.blocks.append(
                DocumentBlock(
                    block_id=f"p01_b{idx + 1:03d}",
                    kind=kind,
                    raw_text=p_str,
                    text=p_str,
                    page=1,
                    reading_order=idx + 1,
                    source_type="legacy_doc_binary_stream",
                    contains_math=LayoutAnalyzer.contains_math_expression(p_str),
                )
            )

        out.pages.append(
            PageLayout(
                page_number=1,
                state=PageContentState.NATIVE_TEXT if len(norm_text) >= 40 else PageContentState.CORRUPTED_PAGE,
                column_count=1,
                native_char_count=len(norm_text),
                extraction_confidence=0.72 if len(norm_text) >= 40 else 0.20,
                block_ids=[b.block_id for b in out.blocks],
                warnings=["Trích xuất từ luồng nhị phân .DOC dự phòng"],
            )
        )
        out.stage_timings.native_extraction_ms = (time.perf_counter() - t_extract) * 1000.0
        return out

    @staticmethod
    def _extract_ole2_text_streams(raw_bytes: bytes) -> str:
        """Trích xuất các đoạn văn bản tiếng Việt/Anh sạch từ luồng nhị phân OLE2 WordDocument."""
        chunks: List[str] = []
        # 1. Tìm các chuỗi UTF-16LE có độ dài >= 12 ký tự
        try:
            u16_text = raw_bytes.decode("utf-16le", errors="ignore")
            for m in re.finditer(r"[\w\sÀ-ỹ.,;:?!()\[\]\"'\-+*/=<>^%$#@&~`|\n\r\t]{14,}", u16_text):
                seg = m.group(0).strip()
                # Loại bỏ rác nhị phân (tỷ lệ chữ cái/số phải >= 50%)
                alnum = sum(1 for c in seg if c.isalnum())
                if len(seg) >= 14 and alnum / len(seg) >= 0.45:
                    if not re.search(r"(?:Root Entry|WordDocument|SummaryInformation|Normal\.dot|Microsoft Word)", seg):
                        chunks.append(seg)
        except Exception:
            pass

        # 2. Tìm thêm chuỗi CP1258 / Latin-1 nếu UTF-16LE ít kết quả
        if sum(len(c) for c in chunks) < 200:
            try:
                cp_text = raw_bytes.decode("cp1258", errors="ignore")
                for m in re.finditer(r"[a-zA-Z0-9\sÀ-ỹ.,;:?!()\[\]\"'\-+*/=]{20,}", cp_text):
                    seg = m.group(0).strip()
                    if not re.search(r"(?:Root Entry|WordDocument|SummaryInformation|Microsoft|Normal\.dot|Calibri|Times New Roman)", seg):
                        chunks.append(seg)
            except Exception:
                pass

        return "\n".join(chunks).strip()


# ============================================================================
# IMAGE READER (Phần II - Mục 4.5: PNG, JPG, WEBP, BMP, GIF, TIFF)
# ============================================================================

class ImageReader(DocumentReader):
    """
    Trình đọc hình ảnh đề thi/tài liệu:
    - Giữ nguyên kích thước gốc, hướng ảnh (EXIF orientation), định dạng và liên kết nguồn.
    - Tôn trọng tuyệt đối chế độ OCR_MODE=off vs OCR_MODE=local.
    """

    SUPPORTED_FORMATS = {"PNG", "JPG", "JPEG", "WEBP", "BMP", "GIF", "TIFF", "TIF"}

    def supports(self, source: bytes | str, detected_format: Optional[str] = None) -> bool:
        if detected_format and detected_format.upper() in self.SUPPORTED_FORMATS:
            return True
        if isinstance(source, str):
            ext = os.path.splitext(source)[1].lower().lstrip(".")
            return ext.upper() in self.SUPPORTED_FORMATS
        if isinstance(source, (bytes, bytearray)):
            fmt, _, _ = SecurityGuard.detect_magic_format(bytes(source))
            return fmt in self.SUPPORTED_FORMATS
        return False

    def read(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        t0 = time.perf_counter()
        opts = options or ReaderOptions()
        cfg = get_config()
        ocr_mode = opts.ocr_mode if opts.ocr_mode is not None else cfg.ocr_mode

        raw_bytes, inferred_name = self._ensure_bytes(source)
        file_name = opts.file_name if opts.file_name != "document" else inferred_name
        magic_fmt, _, _ = SecurityGuard.detect_magic_format(raw_bytes, file_name)

        out = ReaderOutput(
            file_name=file_name,
            detected_format=magic_fmt if magic_fmt != "UNKNOWN" else "IMAGE",
            ocr_mode_used=ocr_mode.value,
            page_count=1,
            is_scanned=True,
        )
        out.stage_timings.file_loading_ms = (time.perf_counter() - t0) * 1000.0

        size_err = SecurityGuard.validate_file_size(raw_bytes, cfg, opts.max_file_size_bytes)
        if size_err:
            out.errors.append(size_err)
            out.is_corrupted = True
            return out

        if Image is None:
            out.errors.append(
                ParseError(
                    code="PILLOW_MISSING",
                    message="Thư viện Pillow (PIL) chưa được cài đặt để đọc hình ảnh.",
                    stage="native_extraction",
                    recoverable=False,
                )
            )
            return out

        try:
            pil_img = Image.open(io.BytesIO(raw_bytes))
            w, h = pil_img.size
            img_fmt = (pil_img.format or magic_fmt or "PNG").upper()
            orientation_deg = 0
            try:
                exif = pil_img.getexif()
                if exif and 274 in exif:
                    orient_tag = exif[274]
                    orient_map = {3: 180, 6: 90, 8: 270}
                    orientation_deg = orient_map.get(orient_tag, 0)
            except Exception:
                pass
        except Exception as e:
            out.is_corrupted = True
            out.errors.append(
                ParseError(
                    code="CORRUPTED_IMAGE",
                    message=f"Không thể giải mã tệp hình ảnh: {e}",
                    stage="native_extraction",
                    recoverable=False,
                )
            )
            return out

        t_ocr = time.perf_counter()
        ocr_txt, ocr_status, ocr_warn = OCRAdapter.recognize_pil_image(pil_img, opts)
        out.stage_timings.ocr_ms = (time.perf_counter() - t_ocr) * 1000.0

        img_id = "img_p01_001"
        asset = ImageAsset(
            image_id=img_id,
            page=1,
            width=w,
            height=h,
            bbox=(0.0, 0.0, float(w), float(h)),
            orientation_deg=orientation_deg,
            image_format=img_fmt,
            byte_size=len(raw_bytes),
            ocr_status=ocr_status,
            ocr_text=ocr_txt,
            requires_manual_review=(ocr_status != "ocr_completed"),
            source_ref=SourceReference(
                file_name=file_name,
                page=1,
                image_id=img_id,
                bbox=(0.0, 0.0, float(w), float(h)),
                extraction_method="image_reader",
            ),
        )
        out.images.append(asset)

        if ocr_warn:
            out.warnings.append(
                ParseWarning(
                    code="OCR_DISABLED_UNPROCESSED_SCAN" if ocr_status == "ocr_disabled" else "IMAGE_OCR_WARNING",
                    message=ocr_warn,
                    severity=WarningSeverity.WARNING,
                    page=1,
                    reason=ocr_warn,
                    attempted_method="ocr_adapter",
                    requires_manual_review=(ocr_status != "ocr_completed"),
                )
            )

        norm_txt = UnicodeMathNormalizer.normalize_text(ocr_txt, join_broken_lines=True) if ocr_txt else ""
        out.raw_text = ocr_txt
        out.normalized_text = norm_txt
        out.has_formulas = LayoutAnalyzer.contains_math_expression(norm_txt)

        blk = DocumentBlock(
            block_id="p01_b001",
            kind=BlockKind.PARAGRAPH if norm_txt else BlockKind.IMAGE,
            raw_text=ocr_txt,
            text=norm_txt,
            page=1,
            reading_order=1,
            bbox=(0.0, 0.0, float(w), float(h)),
            source_type="local_ocr" if norm_txt else "unrecognized_image",
            image_id=img_id,
            contains_math=out.has_formulas,
        )
        out.blocks.append(blk)

        out.pages.append(
            PageLayout(
                page_number=1,
                width=float(w),
                height=float(h),
                rotation_deg=orientation_deg,
                state=PageContentState.SCANNED_IMAGE_ONLY if norm_txt else PageContentState.LOW_QUALITY_SCAN,
                column_count=1,
                ocr_char_count=len(norm_txt),
                image_count=1,
                extraction_confidence=0.80 if len(norm_txt) >= 30 else 0.20,
                block_ids=["p01_b001"],
            )
        )
        return out


# ============================================================================
# TEXT / MARKDOWN / CSV / RTF READER
# ============================================================================

class TextReader(DocumentReader):
    """Trình đọc các tệp văn bản thuần (TXT, MD, CSV, RTF, HTML)."""

    SUPPORTED_FORMATS = {"TXT", "MD", "CSV", "TSV", "RTF", "HTML", "HTM", "XML", "JSON"}

    def supports(self, source: bytes | str, detected_format: Optional[str] = None) -> bool:
        if detected_format and detected_format.upper() in self.SUPPORTED_FORMATS:
            return True
        if isinstance(source, str) and not os.path.exists(source):
            return True
        if isinstance(source, str):
            ext = os.path.splitext(source)[1].lower().lstrip(".").upper()
            return ext in self.SUPPORTED_FORMATS
        return False

    def read(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        t0 = time.perf_counter()
        opts = options or ReaderOptions()
        cfg = get_config()
        ocr_mode = opts.ocr_mode if opts.ocr_mode is not None else cfg.ocr_mode

        raw_bytes, inferred_name = self._ensure_bytes(source)
        file_name = opts.file_name if opts.file_name != "document" else inferred_name

        out = ReaderOutput(
            file_name=file_name,
            detected_format="TXT",
            ocr_mode_used=ocr_mode.value,
            page_count=1,
        )
        out.stage_timings.file_loading_ms = (time.perf_counter() - t0) * 1000.0

        size_err = SecurityGuard.validate_file_size(raw_bytes, cfg, opts.max_file_size_bytes)
        if size_err:
            out.errors.append(size_err)
            out.is_corrupted = True
            return out

        t_extract = time.perf_counter()
        text = ""
        for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "windows-1252", "latin-1"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        norm_text = UnicodeMathNormalizer.normalize_text(text, join_broken_lines=False)
        out.raw_text = text
        out.normalized_text = norm_text
        out.has_formulas = LayoutAnalyzer.contains_math_expression(norm_text)

        paragraphs = [p for p in re.split(r"\n\s*\n", norm_text) if p.strip()]
        if not paragraphs and norm_text.strip():
            paragraphs = [norm_text.strip()]

        for idx, p_str in enumerate(paragraphs):
            kind = LayoutAnalyzer.classify_block_kind(p_str, page_number=1)
            out.blocks.append(
                DocumentBlock(
                    block_id=f"p01_b{idx + 1:03d}",
                    kind=kind,
                    raw_text=p_str,
                    text=p_str,
                    page=1,
                    reading_order=idx + 1,
                    source_type="native_text",
                    contains_math=LayoutAnalyzer.contains_math_expression(p_str),
                )
            )

        if opts.detect_borderless_tables:
            out.tables.extend(LayoutAnalyzer.detect_borderless_tables(out.blocks))

        out.pages.append(
            PageLayout(
                page_number=1,
                state=PageContentState.NATIVE_TEXT if norm_text.strip() else PageContentState.BLANK_PAGE,
                column_count=1,
                native_char_count=len(norm_text),
                table_count=len(out.tables),
                block_ids=[b.block_id for b in out.blocks],
            )
        )
        out.stage_timings.native_extraction_ms = (time.perf_counter() - t_extract) * 1000.0
        return out


# ============================================================================
# UNIFIED READER REGISTRY & BATCH PROCESSOR (Phần II & XII)
# ============================================================================

class DocumentReaderRegistry:
    """Bộ định tuyến chọn đúng DocumentReader dựa trên Magic Bytes và phần mở rộng."""

    def __init__(self) -> None:
        self._readers: List[DocumentReader] = [
            PDFReader(),
            DOCXReader(),
            LegacyDOCReader(),
            ImageReader(),
            TextReader(),
        ]

    def register_reader(self, reader: DocumentReader) -> None:
        self._readers.insert(0, reader)

    def read_any(self, source: bytes | str, options: Optional[ReaderOptions] = None) -> ReaderOutput:
        opts = options or ReaderOptions()
        raw_bytes, inferred_name = DocumentReader._ensure_bytes(source)
        if opts.file_name == "document":
            opts.file_name = inferred_name

        magic_fmt, is_spoofed, spoof_reason = SecurityGuard.detect_magic_format(raw_bytes, opts.file_name)

        # Chặn ngay thực thi nhị phân giả mạo (.exe)
        if magic_fmt == "EXE":
            out = ReaderOutput(
                file_name=opts.file_name,
                detected_format="EXE",
                ocr_mode_used=(opts.ocr_mode or get_config().ocr_mode).value,
                is_corrupted=True,
            )
            out.errors.append(
                ParseError(
                    code="EXECUTABLE_FILE_REJECTED",
                    message=spoof_reason or "Từ chối xử lý tệp thực thi nhị phân.",
                    stage="file_loading",
                    recoverable=False,
                )
            )
            return out

        selected_reader: Optional[DocumentReader] = None
        for r in self._readers:
            if r.supports(raw_bytes, detected_format=magic_fmt):
                selected_reader = r
                break

        if selected_reader is None:
            selected_reader = TextReader()

        res = selected_reader.read(raw_bytes, opts)
        if is_spoofed and spoof_reason:
            res.warnings.insert(
                0,
                ParseWarning(
                    code="MISMATCHED_FILE_EXTENSION",
                    message=spoof_reason,
                    severity=WarningSeverity.WARNING,
                    reason="Chữ ký Magic Bytes khác với đuôi mở rộng của tên file.",
                    attempted_method="magic_bytes_routing",
                ),
            )
        return res


class BatchDocumentProcessor:
    """
    Bộ xử lý hàng loạt (Batch Processing - Phần XII - Mục 33, 35):
    - Cô lập trạng thái giữa các tài liệu (một file lỗi không làm sập cả batch).
    - Hỗ trợ giới hạn concurrency, timeout mỗi file, callback tiến độ và cờ hủy (cancel_event).
    """

    def __init__(self, max_workers: Optional[int] = None, per_file_timeout_sec: Optional[int] = None) -> None:
        cfg = get_config()
        self.max_workers = max_workers or cfg.max_batch_workers
        self.per_file_timeout_sec = per_file_timeout_sec or cfg.extraction_timeout_sec
        self.registry = DocumentReaderRegistry()

    def process_batch(
        self,
        items: List[Tuple[str, bytes | str]],
        options: Optional[ReaderOptions] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[ReaderOutput]:
        results: List[ReaderOutput] = []
        total = len(items)

        for idx, (fname, src) in enumerate(items):
            if is_cancelled and is_cancelled():
                break
            if progress_callback:
                progress_callback(idx + 1, total, fname)

            item_opts = ReaderOptions(
                file_name=fname,
                ocr_mode=options.ocr_mode if options else None,
                max_pages=options.max_pages if options else None,
                max_file_size_bytes=options.max_file_size_bytes if options else None,
            )

            try:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(self.registry.read_any, src, item_opts)
                    out = fut.result(timeout=self.per_file_timeout_sec)
                    results.append(out)
            except FuturesTimeoutError:
                err_out = ReaderOutput(
                    file_name=fname,
                    detected_format="TIMEOUT",
                    ocr_mode_used=(item_opts.ocr_mode or get_config().ocr_mode).value,
                    is_corrupted=True,
                )
                err_out.errors.append(
                    ParseError(
                        code="FILE_PROCESSING_TIMEOUT",
                        message=f"Quá thời gian xử lý ({self.per_file_timeout_sec}s) cho tệp '{fname}'.",
                        stage="batch_execution",
                        recoverable=False,
                    )
                )
                results.append(err_out)
            except Exception as e:
                err_out = ReaderOutput(
                    file_name=fname,
                    detected_format="ERROR",
                    ocr_mode_used=(item_opts.ocr_mode or get_config().ocr_mode).value,
                    is_corrupted=True,
                )
                err_out.errors.append(
                    ParseError(
                        code="BATCH_ITEM_FAILURE",
                        message=f"Lỗi cô lập khi xử lý '{fname}': {e}",
                        stage="batch_execution",
                        recoverable=False,
                    )
                )
                results.append(err_out)

        return results
