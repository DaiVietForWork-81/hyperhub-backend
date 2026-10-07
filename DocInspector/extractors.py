"""
Ultra-fast file stream and text extractors for PDF and Word files.
Zero AI, native binary parsing via PyMuPDF and python-docx.
Enhanced with text entropy, word metrics, font statistics, and metadata.
"""

from __future__ import annotations

import collections
import io
import logging
import math
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from docx import Document
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from cpp_core.bridge import calculate_entropy as cpp_entropy, fast_detect_magic as cpp_detect_magic
except ImportError:
    try:
        import sys
        _b_path = Path(__file__).resolve().parent.parent / "Bot"
        if str(_b_path) not in sys.path:
            sys.path.insert(0, str(_b_path))
        from cpp_core.bridge import calculate_entropy as cpp_entropy, fast_detect_magic as cpp_detect_magic
    except Exception:
        cpp_entropy = None
        cpp_detect_magic = None

_TESSERACT_INITIALIZED = False
_TESSERACT_AVAILABLE = False

log = logging.getLogger(__name__)

# Cấu hình Tesseract tối ưu cho tài liệu học tập tiếng Việt
# --oem 3: LSTM engine (tốt nhất)
# --psm 6: Assume a single uniform block of text
# -l vie+eng: Vietnamese + English
TESS_CONFIG = r'--oem 3 --psm 6 -l vie+eng'


def init_tesseract() -> bool:
    """Khởi tạo và kiểm tra đường dẫn Tesseract-OCR cùng tessdata tiếng Việt."""
    global _TESSERACT_INITIALIZED, _TESSERACT_AVAILABLE
    if _TESSERACT_INITIALIZED:
        return _TESSERACT_AVAILABLE

    _TESSERACT_INITIALIZED = True
    if pytesseract is None:
        _TESSERACT_AVAILABLE = False
        return False

    candidate_bins = [
        os.environ.get("TESSERACT_PATH"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract"),
    ]
    tess_bin = None
    for b in candidate_bins:
        if b and os.path.exists(b):
            tess_bin = b
            break

    if tess_bin:
        pytesseract.pytesseract.tesseract_cmd = tess_bin
        tessdata_candidates = [
            os.environ.get("TESSDATA_PREFIX"),
            r"D:\Project\Bot\data\tessdata",
            r"C:\Program Files\Tesseract-OCR\tessdata",
        ]
        for td in tessdata_candidates:
            if td and os.path.exists(td):
                os.environ["TESSDATA_PREFIX"] = td
                break
        _TESSERACT_AVAILABLE = True
    else:
        _TESSERACT_AVAILABLE = False

    return _TESSERACT_AVAILABLE


@dataclass
class ExtractedDocument:
    """Raw parsed content and metadata from the document file."""
    full_text: str
    page_count: int
    char_count: int
    word_count: int
    line_count: int
    paragraph_count: int
    table_count: int
    image_count: int
    is_scanned_pdf: bool
    is_encrypted: bool
    raw_type: str
    magic_signature: str
    entropy: float = 0.0
    reading_time_minutes: float = 0.0
    legacy_encoding_warning: Optional[str] = None
    meta_properties: Dict[str, Any] = field(default_factory=dict)
    headers: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)



def _preprocess_image_for_ocr(img: "Image.Image") -> "Image.Image":
    """Tiền xử lý ảnh để cải thiện chất lượng OCR (ổn định với scan mờ/nhiễu)."""
    from PIL import ImageFilter, ImageEnhance

    # 1. Chuyển sang grayscale
    if img.mode != 'L':
        img = img.convert('L')

    # 2. Tăng kích thước nếu ảnh quá nhỏ (Tesseract cần >= 300 DPI)
    w, h = img.size
    if w < 1000 or h < 1000:
        scale = max(1000 / w, 1000 / h, 1.5)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # 2b. Khử nhiễu muối-tiêu trước khi tăng tương phản (ổn định scan xấu)
    try:
        img = img.filter(ImageFilter.MedianFilter(size=3))
    except Exception:
        pass

    # 3. Tăng độ tương phản
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(2.0)

    # 4. Sharpen nhẹ để làm rõ chữ
    img = img.filter(ImageFilter.SHARPEN)

    # 5. Threshold để nhị phân hóa (chuyển về trắng đen)
    # Dùng phương pháp adaptive threshold đơn giản qua point()
    threshold = 160  # pixels darker than this become black
    img = img.point(lambda x: 0 if x < threshold else 255, '1')
    img = img.convert('L')  # convert back to grayscale for tesseract

    return img


class FastDocumentExtractor:
    """High-speed binary extractor with forensic document profiling."""

    MAGIC_SIGNATURES = {
        b"%PDF-": "PDF",
        b"PK\x03\x04": "DOCX",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "DOC",
        b"\x89PNG": "IMAGE",
        b"\xff\xd8\xff": "IMAGE",
        b"GIF8": "IMAGE",
        b"BM": "IMAGE",
    }

    @classmethod
    def perform_ocr(cls, img_data_or_path: bytes | Path | str) -> str:
        """Thực hiện OCR tiếng Việt + tiếng Anh từ dữ liệu ảnh bằng Tesseract Engine."""
        if not init_tesseract():
            return ""

        try:
            if isinstance(img_data_or_path, (str, Path)):
                img = Image.open(str(img_data_or_path))
            else:
                img = Image.open(io.BytesIO(img_data_or_path))

            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Tối ưu kích thước: giới hạn cạnh lớn nhất <= 2500px để OCR nhanh
            max_dim = 2500
            w, h = img.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

            # Tiền xử lý ảnh để tăng chất lượng OCR
            try:
                processed_img = _preprocess_image_for_ocr(img)
            except Exception as prep_err:
                log.debug("OCR preprocessing failed, using original: %s", prep_err)
                processed_img = img

            try:
                text = pytesseract.image_to_string(
                    processed_img, config=TESS_CONFIG, timeout=30
                ).strip()
            except Exception:
                try:
                    text = pytesseract.image_to_string(processed_img, lang="eng").strip()
                except Exception:
                    text = ""

            return text
        except Exception:
            return ""

    @staticmethod
    def calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of the text character distribution (C++ accelerated)."""
        if not text:
            return 0.0
        if cpp_entropy is not None:
            try:
                return round(cpp_entropy(text), 3)
            except Exception:
                pass
        counts = collections.Counter(text)
        total = len(text)
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
        return round(entropy, 3)

    @staticmethod
    def detect_legacy_encoding(text: str) -> Optional[str]:
        """Detect presence of legacy TCVN3 or VNI-Windows mojibake."""
        # TCVN3 distinctive characters: ¸, µ, ¶, ·, ¹, â, ª, «, ¬, ­, ®, ¯, ±
        tcvn3_chars = sum(1 for c in text if c in "¸µ¶·¹ª«¬®¯±")
        if tcvn3_chars >= 15:
            return "CẢNH BÁO: Phát hiện ký tự mã hóa cũ TCVN3 (Font .VN...)"
        return None

    @classmethod
    def get_magic_type(cls, file_bytes: bytes) -> Tuple[str, str]:
        """Detect true format by magic bytes using C++ Native Engine (with fallback)."""
        if cpp_detect_magic is not None and len(file_bytes) >= 4:
            try:
                native_type = cpp_detect_magic(file_bytes[:2048])
                if native_type == "PDF":
                    sig = file_bytes[:8].decode("ascii", errors="ignore").strip()
                    return "PDF", sig
                elif native_type in ("DOCX", "ZIP"):
                    return "DOCX", "ZIP_OPENXML"
                elif native_type == "DOC_OLE2":
                    return "DOC", "OLE_COMPOUND"
                elif native_type in ("EXE_PE", "ELF"):
                    return "MALICIOUS_BINARY", native_type
                elif native_type in ("PNG", "JPEG", "GIF", "WEBP", "BMP"):
                    return "IMAGE", native_type
            except Exception:
                pass

        if file_bytes.startswith(b"%PDF-"):
            sig = file_bytes[:8].decode("ascii", errors="ignore").strip()
            return "PDF", sig
        elif file_bytes.startswith(b"PK\x03\x04"):
            return "DOCX", "ZIP_OPENXML"
        elif file_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return "DOC", "OLE_COMPOUND"
        elif file_bytes.startswith(b"MZ") or file_bytes.startswith(b"\x7fELF"):
            return "MALICIOUS_BINARY", "SUSPICIOUS_EXECUTABLE"
        elif file_bytes.startswith(b"\x89PNG"):
            return "IMAGE", "PNG"
        elif file_bytes.startswith(b"\xff\xd8\xff"):
            return "IMAGE", "JPEG"
        elif file_bytes.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP":
            return "IMAGE", "WEBP"
        elif file_bytes.startswith(b"BM"):
            return "IMAGE", "BMP"
        elif file_bytes.startswith(b"GIF87a") or file_bytes.startswith(b"GIF89a"):
            return "IMAGE", "GIF"
        return "UNKNOWN", "UNKNOWN"

    @classmethod
    def extract(cls, file_path_or_bytes: str | Path | bytes, file_name: str = "", deep: bool = False) -> ExtractedDocument:
        """Main extraction entrypoint supporting file path or raw bytes.
        deep=True: quét kỹ toàn bộ trang + OCR nhiều trang (chậm hơn nhưng chính xác hơn)."""
        if isinstance(file_path_or_bytes, (str, Path)):
            path = Path(file_path_or_bytes)
            with open(path, "rb") as f:
                raw_bytes = f.read()
            actual_name = path.name
        else:
            raw_bytes = file_path_or_bytes
            actual_name = file_name or "stream_document"

        detected_type, magic_sig = cls.get_magic_type(raw_bytes)

        ext = Path(actual_name).suffix.lower()
        if detected_type == "UNKNOWN" and ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            detected_type = "IMAGE"
            magic_sig = ext.replace(".", "").upper()

        if detected_type == "PDF":
            return cls._extract_pdf(raw_bytes, magic_sig, deep=deep)
        elif detected_type == "DOCX":
            return cls._extract_docx(raw_bytes, magic_sig)
        elif detected_type == "DOC":
            return cls._extract_legacy_doc(raw_bytes, magic_sig)
        elif detected_type == "IMAGE":
            return cls._extract_image(raw_bytes, magic_sig)
        else:
            # Fallback for plain text
            try:
                text = raw_bytes.decode("utf-8", errors="ignore")
                words = len(text.split())
                lines = len(text.splitlines())
                paras = [p.strip() for p in text.split("\n\n") if p.strip()]
                return ExtractedDocument(
                    full_text=text,
                    page_count=1,
                    char_count=len(text),
                    word_count=words,
                    line_count=lines,
                    paragraph_count=len(paras),
                    table_count=0,
                    image_count=0,
                    is_scanned_pdf=False,
                    is_encrypted=False,
                    raw_type="PLAIN_TEXT",
                    magic_signature="RAW_TEXT",
                    entropy=cls.calculate_entropy(text),
                    reading_time_minutes=round(words / 200.0, 1),
                    paragraphs=paras,
                )
            except Exception:
                return ExtractedDocument(
                    full_text="",
                    page_count=0,
                    char_count=0,
                    word_count=0,
                    line_count=0,
                    paragraph_count=0,
                    table_count=0,
                    image_count=0,
                    is_scanned_pdf=False,
                    is_encrypted=False,
                    raw_type="BINARY_UNKNOWN",
                    magic_signature="UNKNOWN",
                )

    # Regex nhận diện câu hỏi trên từng trang (chấm relevance, không dấu cũng ăn)
    _RE_PAGE_QUESTION = None

    @classmethod
    def _page_question_regex(cls):
        import re as _re
        if cls._RE_PAGE_QUESTION is None:
            cls._RE_PAGE_QUESTION = _re.compile(r"(?i)\b(câu|cau|bài|bai|question)\s+\d+")
        return cls._RE_PAGE_QUESTION

    @classmethod
    def _extract_pdf(cls, raw_bytes: bytes, magic_sig: str, deep: bool = False) -> ExtractedDocument:
        """Extract PDF via PyMuPDF with page metrics and image counting.
        deep=True: đọc toàn bộ trang + OCR chọn lọc tới 10 trang relevant nhất.
        Luôn lọc trang nhiễu (trắng/quảng cáo) để tín hiệu phân loại sạch hơn."""
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        page_count = len(doc)
        is_encrypted = doc.is_encrypted

        if is_encrypted and not doc.authenticate(""):
            return ExtractedDocument(
                full_text="",
                page_count=page_count,
                char_count=0,
                word_count=0,
                line_count=0,
                paragraph_count=0,
                table_count=0,
                image_count=0,
                is_scanned_pdf=False,
                is_encrypted=True,
                raw_type="PDF",
                magic_signature=magic_sig,
            )

        text_pages: List[str] = []
        image_count = 0
        table_count = 0
        skipped_noise_pages = 0
        # (page_index, relevance_score, needs_ocr, page_obj)
        ocr_candidates: List[tuple] = []

        MAX_SAMPLE_PAGES = 30
        if deep or page_count <= MAX_SAMPLE_PAGES:
            # Quét kỹ: đọc toàn bộ trang để không sót bằng chứng phân loại
            pages_to_process = list(doc)
        else:
            # Quét nhanh: 20 trang đầu + 10 trang cuối để bóc tách siêu tốc (chứa 100% đề, năm học, trường, đáp án)
            sample_indices = set(range(20)).union(set(range(max(20, page_count - 10), page_count)))
            pages_to_process = [doc[idx] for idx in sorted(sample_indices) if idx < page_count]

        q_re = cls._page_question_regex()
        for page in pages_to_process:
            page_text = page.get_text("text")
            stripped_len = len(page_text.strip())
            page_images = page.get_images(full=True)
            image_count += len(page_images)

            q_hits = len(q_re.findall(page_text))

            # Lọc trang nhiễu: gần như trắng, không ảnh, không câu hỏi (bìa trắng, trang quảng cáo)
            if stripped_len < 40 and not page_images and q_hits == 0:
                skipped_noise_pages += 1
                continue

            text_pages.append(page_text)

            # Fast table indicator
            lines = page_text.splitlines()
            pipe_or_tab = sum(1 for line in lines if "|" in line or "\t" in line)
            if pipe_or_tab >= 3:
                table_count += 1

            # Chấm relevance để OCR chọn lọc: câu hỏi > nội dung dày > có ảnh
            relevance = 3 * min(q_hits, 10) + min(stripped_len / 200.0, 15.0) + (5.0 if page_images else 0.0)
            try:
                page_idx = page.number
            except Exception:
                page_idx = -1
            ocr_candidates.append((page_idx, relevance, stripped_len < 200, page))

        full_text = "\n".join(text_pages)
        char_count = len(full_text.strip())
        word_count = len(full_text.split())
        line_count = len(full_text.splitlines())

        # Scanned PDF check
        is_scanned_pdf = (page_count > 0) and (char_count < 45 * page_count) and (image_count >= page_count)

        ocr_pages_used: List[int] = []
        if is_scanned_pdf and init_tesseract():
            ocr_pages: List[str] = []
            max_ocr_pages = 10 if deep else 3
            ocr_dpi = 200 if deep else 150
            # OCR đúng trang đáng tiền nhất (relevance cao + đang thiếu text), không cào bừa từ đầu
            ocr_candidates.sort(key=lambda t: t[1], reverse=True)
            for page_idx, _rel, needs_ocr, page in ocr_candidates:
                if len(ocr_pages) >= max_ocr_pages:
                    break
                if not needs_ocr:
                    continue
                try:
                    # DPI 150: đủ nét cho Tesseract nhưng render nhanh gấp ~1.8x so với 200
                    pix = page.get_pixmap(dpi=ocr_dpi)
                    img_bytes = pix.tobytes("png")
                    page_text = cls.perform_ocr(img_bytes)
                    if page_text and len(page_text.strip()) >= 20:
                        ocr_pages.append(page_text)
                        if page_idx >= 0:
                            ocr_pages_used.append(page_idx)
                except Exception:
                    pass
            if ocr_pages:
                full_text = "\n".join(ocr_pages)
                char_count = len(full_text.strip())
                word_count = len(full_text.split())
                line_count = len(full_text.splitlines())

        paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

        meta = {}
        if doc.metadata:
            meta = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "producer": doc.metadata.get("producer", ""),
            }
        meta["processed_pages"] = len(pages_to_process) - skipped_noise_pages
        meta["skipped_noise_pages"] = skipped_noise_pages
        meta["ocr_pages_used"] = sorted(ocr_pages_used)

        entropy = cls.calculate_entropy(full_text)
        reading_time = round(word_count / 200.0, 1)
        legacy_enc = cls.detect_legacy_encoding(full_text)

        return ExtractedDocument(
            full_text=full_text,
            page_count=page_count,
            char_count=char_count,
            word_count=word_count,
            line_count=line_count,
            paragraph_count=len(paragraphs),
            table_count=table_count,
            image_count=image_count,
            is_scanned_pdf=is_scanned_pdf,
            is_encrypted=False,
            raw_type="PDF",
            magic_signature=magic_sig,
            entropy=entropy,
            reading_time_minutes=reading_time,
            legacy_encoding_warning=legacy_enc,
            meta_properties=meta,
            paragraphs=paragraphs,
        )

    @classmethod
    def _extract_docx(cls, raw_bytes: bytes, magic_sig: str) -> ExtractedDocument:
        """Extract DOCX via python-docx with table cell text and properties."""
        file_stream = io.BytesIO(raw_bytes)
        doc = Document(file_stream)

        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        table_texts: List[str] = []
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                if row_text:
                    table_texts.append(row_text)

        full_text = "\n".join(paragraphs + table_texts)
        char_count = len(full_text.strip())
        word_count = len(full_text.split())
        line_count = len(full_text.splitlines())

        approx_pages = max(1, round(char_count / 2200))

        meta = {}
        if hasattr(doc, "core_properties"):
            cp = doc.core_properties
            meta = {
                "title": cp.title or "",
                "author": cp.author or "",
                "created": str(cp.created) if cp.created else "",
                "revision": cp.revision or 1,
            }

        entropy = cls.calculate_entropy(full_text)
        reading_time = round(word_count / 200.0, 1)
        legacy_enc = cls.detect_legacy_encoding(full_text)

        return ExtractedDocument(
            full_text=full_text,
            page_count=approx_pages,
            char_count=char_count,
            word_count=word_count,
            line_count=line_count,
            paragraph_count=len(paragraphs),
            table_count=len(doc.tables),
            image_count=0,
            is_scanned_pdf=False,
            is_encrypted=False,
            raw_type="DOCX",
            magic_signature=magic_sig,
            entropy=entropy,
            reading_time_minutes=reading_time,
            legacy_encoding_warning=legacy_enc,
            meta_properties=meta,
            paragraphs=paragraphs,
        )

    @classmethod
    def _extract_legacy_doc(cls, raw_bytes: bytes, magic_sig: str) -> ExtractedDocument:
        """Extract text from legacy Word .doc binary stream without external tools."""
        printable_ascii = re.findall(b"[\x20-\x7e\t\n\r]{4,}", raw_bytes)
        extracted_strings = [s.decode("latin-1", errors="ignore") for s in printable_ascii]
        full_text = "\n".join(extracted_strings)
        char_count = len(full_text.strip())
        word_count = len(full_text.split())
        line_count = len(full_text.splitlines())
        approx_pages = max(1, round(char_count / 2200))

        entropy = cls.calculate_entropy(full_text)
        reading_time = round(word_count / 200.0, 1)

        return ExtractedDocument(
            full_text=full_text,
            page_count=approx_pages,
            char_count=char_count,
            word_count=word_count,
            line_count=line_count,
            paragraph_count=len(extracted_strings),
            table_count=0,
            image_count=0,
            is_scanned_pdf=False,
            is_encrypted=False,
            raw_type="DOC",
            magic_signature=magic_sig,
            entropy=entropy,
            reading_time_minutes=reading_time,
            paragraphs=extracted_strings,
        )

    @classmethod
    def _extract_image(cls, raw_bytes: bytes, magic_sig: str) -> ExtractedDocument:
        """Extract text from image files (PNG, JPG, WEBP, BMP, GIF) via OCR."""
        ocr_text = cls.perform_ocr(raw_bytes)
        char_count = len(ocr_text.strip())
        word_count = len(ocr_text.split())
        line_count = len(ocr_text.splitlines())
        paragraphs = [p.strip() for p in ocr_text.split("\n\n") if p.strip()]
        entropy = cls.calculate_entropy(ocr_text)
        reading_time = round(word_count / 200.0, 1)

        return ExtractedDocument(
            full_text=ocr_text,
            page_count=1,
            char_count=char_count,
            word_count=word_count,
            line_count=line_count,
            paragraph_count=len(paragraphs),
            table_count=0,
            image_count=1,
            is_scanned_pdf=False,
            is_encrypted=False,
            raw_type="IMAGE",
            magic_signature=magic_sig,
            entropy=entropy,
            reading_time_minutes=reading_time,
            legacy_encoding_warning=None,
            meta_properties={"image_format": magic_sig},
            paragraphs=paragraphs,
        )

