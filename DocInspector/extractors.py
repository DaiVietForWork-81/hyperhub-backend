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

try:
    from .ai_extractor import AIDocumentEnhancer
except ImportError:
    try:
        from ai_extractor import AIDocumentEnhancer
    except Exception:
        AIDocumentEnhancer = None

from .config import OCRMode, get_config
from .layout_analyzer import LayoutAnalyzer

_TESSERACT_INITIALIZED = False
_TESSERACT_AVAILABLE = False

log = logging.getLogger(__name__)

# Cấu hình Tesseract tối ưu cho tài liệu học tập tiếng Việt
# --oem 3: LSTM engine (tốt nhất)
# --psm 6: Assume a single uniform block of text
# -l vie+eng: Vietnamese + English
# -c tessedit_parallel=0 -c omp_thread_limit=1: Chống ngốn CPU trên server 0.35 core
TESS_CONFIG = r'--oem 3 --psm 6 -l vie+eng -c tessedit_parallel=0 -c omp_thread_limit=1'


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
    footers: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)
    raw_unnormalized_text: str = ""
    pages_layout: List[Any] = field(default_factory=list)
    blocks: List[Any] = field(default_factory=list)
    tables: List[Any] = field(default_factory=list)
    images: List[Any] = field(default_factory=list)
    warnings: List[Any] = field(default_factory=list)



def _compute_otsu_threshold(histogram: List[int]) -> int:
    """Thuật toán phân ngưỡng Otsu (Otsu's binarization) thuần Python từ histogram ảnh.
    Tự động tìm ngưỡng tối ưu giữa nền và chữ dựa trên tối đa hóa phương sai liên lớp.
    Chạy siêu tốc ~0.05ms, xử lý hoàn hảo scan mờ, chói sáng hoặc nền xám."""
    total_pixels = sum(histogram)
    if total_pixels == 0:
        return 140

    current_max = 0.0
    threshold = 140
    sum_total = sum(i * histogram[i] for i in range(256))

    weight_background = 0
    sum_background = 0

    for t in range(256):
        weight_background += histogram[t]
        if weight_background == 0:
            continue
        weight_foreground = total_pixels - weight_background
        if weight_foreground == 0:
            break

        sum_background += t * histogram[t]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground

        variance = weight_background * weight_foreground * ((mean_background - mean_foreground) ** 2)
        if variance > current_max:
            current_max = variance
            threshold = t

    # Giới hạn ngưỡng trong khoảng an toàn [80, 210] tránh trắng hoặc đen toàn bộ
    return max(80, min(threshold, 210))


def _preprocess_image_for_ocr(img: "Image.Image") -> "Image.Image":
    """Tiền xử lý ảnh để cải thiện chất lượng OCR (ổn định với scan mờ/nhiễu/chói)."""
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

    # 5. Phân ngưỡng thích ứng Otsu (Adaptive Threshold) để nhị phân hóa
    try:
        hist = img.histogram()
        threshold = _compute_otsu_threshold(hist)
    except Exception:
        threshold = 150
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
        """Thực hiện OCR tiếng Việt + tiếng Anh từ dữ liệu ảnh bằng Tesseract Engine (tôn trọng OCR_MODE=off)."""
        if get_config().ocr_mode == OCRMode.OFF:
            return ""
        if not init_tesseract():
            return ""

        try:
            if isinstance(img_data_or_path, (str, Path)):
                img = Image.open(str(img_data_or_path))
            else:
                img = Image.open(io.BytesIO(img_data_or_path))

            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Tối ưu kích thước: giới hạn cạnh lớn nhất <= 3200px để OCR rõ nét nhưng không tràn RAM
            max_dim = 3200
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

            text = ""
            try:
                text = pytesseract.image_to_string(
                    processed_img, config=TESS_CONFIG, timeout=30
                ).strip()
            except Exception:
                try:
                    text = pytesseract.image_to_string(processed_img, lang="eng").strip()
                except Exception:
                    text = ""

            # Nếu PSM 6 ra quá ít chữ (< 60 ký tự) hoặc bố cục đề thi 2-3 cột bị nén,
            # tự động thử lại với PSM 3 (Fully automatic page segmentation)
            if len(text) < 60 or (len(text) < 200 and not re.search(r"(?i)\b(câu|bài|question)\s+\d+", text)):
                try:
                    psm3_config = r'--oem 3 --psm 3 -l vie+eng -c tessedit_parallel=0 -c omp_thread_limit=1'
                    alt_text = pytesseract.image_to_string(processed_img, config=psm3_config, timeout=30).strip()
                    if len(alt_text) > len(text):
                        text = alt_text
                except Exception:
                    pass

            return text
        except Exception:
            return ""
        finally:
            try:
                if 'img' in locals() and img:
                    img.close()
            except Exception:
                pass
            try:
                if 'processed_img' in locals() and processed_img and processed_img is not img:
                    processed_img.close()
            except Exception:
                pass

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

    # Bảng ánh xạ TCVN3 (ABC / .VnTime) sang Unicode dựng sẵn chuẩn NFC
    _TCVN3_MAP = str.maketrans({
        "¡": "Ă", "¢": "Â", "£": "Ê", "¤": "Ô", "¥": "Ơ", "¦": "Ư", "§": "Đ",
        "¨": "ă", "©": "â", "ª": "ê", "«": "ô", "¬": "ơ", "\xad": "ư", "®": "đ",
        "µ": "à", "¶": "ả", "·": "ã", "¸": "á", "¹": "ạ",
        "»": "ằ", "¼": "ẳ", "½": "ẵ", "¾": "ắ", "Æ": "ặ",
        "Ç": "ầ", "È": "ẩ", "É": "ẫ", "Ê": "ấ", "Ë": "ậ",
        "Ì": "è", "Î": "ẻ", "Ï": "ẽ", "Ð": "é", "Ñ": "ẹ",
        "Ò": "ề", "Ó": "ể", "Ô": "ễ", "Õ": "ế", "Ö": "ệ",
        "×": "ì", "Ø": "ỉ", "Ü": "ĩ", "Ý": "í", "Þ": "ị",
        "ß": "ò", "á": "ỏ", "â": "õ", "ã": "ó", "ä": "ọ",
        "å": "ồ", "æ": "ổ", "ç": "ỗ", "è": "ố", "é": "ộ",
        "ê": "ờ", "ë": "ở", "ì": "ỡ", "í": "ớ", "î": "ợ",
        "ï": "ù", "ñ": "ủ", "ò": "ũ", "ó": "ú", "ô": "ụ",
        "õ": "ừ", "ö": "ử", "÷": "ữ", "ø": "ứ", "ù": "ự",
        "ú": "ỳ", "û": "ỷ", "ü": "ỹ", "ý": "ý", "þ": "ỵ",
    })

    # Bảng ánh xạ ký tự toán học / vật lý / hóa học từ vùng Private Use Area (Symbol / Wingdings / MathType)
    _SYMBOL_PUA_MAP = str.maketrans({
        "\uf020": " ", "\uf02b": "+", "\uf02d": "-", "\uf03d": "=",
        "\uf0b1": "±", "\uf0b4": "×", "\uf0b8": "÷", "\uf0d6": "√",
        "\uf0a5": "∞", "\uf0a3": "≤", "\uf0b3": "≥", "\uf0b9": "≠",
        "\uf0bb": "≈", "\uf0ae": "→", "\uf0ac": "←", "\uf0ab": "↔",
        "\uf0db": "⇔", "\uf0de": "⇒", "\uf0dc": "⇐", "\uf0ce": "∈",
        "\uf0cf": "∉", "\uf0cc": "⊂", "\uf0cd": "⊆", "\uf0c7": "∩",
        "\uf0c8": "∪", "\uf0c6": "∅", "\uf022": "∀", "\uf024": "∃",
        "\uf044": "Δ", "\uf057": "Ω", "\uf070": "π", "\uf061": "α",
        "\uf062": "β", "\uf067": "γ", "\uf064": "δ", "\uf065": "ε",
        "\uf06c": "λ", "\uf06d": "μ", "\uf072": "ρ", "\uf073": "σ",
        "\uf074": "τ", "\uf066": "φ", "\uf077": "ω", "\uf0b0": "°",
        "\uf0d0": "∠", "\uf05e": "⊥", "\uf0b7": "•", "\u200b": "",
        "\ufeff": "",
    })

    @staticmethod
    def detect_legacy_encoding(text: str) -> Optional[str]:
        """Detect presence of legacy TCVN3 or VNI-Windows mojibake."""
        tcvn3_chars = sum(1 for c in text if c in "¸µ¶·¹ª«¬®¯±¾»¼½ÆÇÈÉËÌÎÏÐÑÒÓÕÖ×ØÜÞßäåæçëìîïñö÷øþ")
        if tcvn3_chars >= 12:
            return "CẢNH BÁO: Phát hiện ký tự mã hóa cũ TCVN3 (Font .VN...) — Đã tự động chuyển đổi sang Unicode"
        return None

    @classmethod
    def normalize_exam_text(cls, text: str) -> Tuple[str, Optional[str]]:
        """Chuẩn hóa văn bản đề thi toàn diện:
        1. Tự động phát hiện và chuyển mã TCVN3 (.VnTime) sang Unicode chuẩn.
        2. Khử ký tự Private Use Area (Symbol/MathType) sang ký hiệu Toán/Lý/Hóa Unicode.
        3. Chuẩn hóa tổ hợp dấu tiếng Việt NFD -> NFC.
        4. Dọn khoảng trắng thừa nhưng bảo toàn cấu trúc dòng và bảng Markdown."""
        if not text:
            return "", None

        import unicodedata

        legacy_warning: Optional[str] = None
        # Kiểm tra mật độ ký tự đặc trưng TCVN3 (không trùng với tiếng Việt Unicode mở rộng \u1ea0-\u1ef9)
        tcvn3_exclusive = sum(1 for c in text if c in "¸µ¶·¹ª«¬®¾»¼½ÆÇÈÉËÌÎÏÐÑÒÓÕÖ×ØÜÞßäåæçëìîïñö÷øþ\xad")
        unicode_viet_ext = sum(1 for c in text if "\u1ea0" <= c <= "\u1ef9")
        if tcvn3_exclusive >= 12 and unicode_viet_ext < tcvn3_exclusive * 0.25:
            legacy_warning = "CẢNH BÁO: Phát hiện ký tự mã hóa cũ TCVN3 (Font .VN...) — Đã tự động chuyển đổi sang Unicode"
            text = text.translate(cls._TCVN3_MAP)

        # Chuyển đổi ký tự PUA (Symbol font / MathType) và xóa zero-width chars
        text = text.translate(cls._SYMBOL_PUA_MAP)

        # Chuẩn hóa Unicode tổ hợp (NFD / CP1258 combining marks) về dựng sẵn (NFC)
        text = unicodedata.normalize("NFC", text)

        # Chuẩn hóa dòng: loại bỏ khoảng trắng thừa cuối dòng và gộp >=3 dòng trống liên tiếp
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text, legacy_warning

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
                try:
                    raw_text = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    raw_text = raw_bytes.decode("latin-1", errors="ignore")
                text, norm_warning = cls.normalize_exam_text(raw_text)
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
                    legacy_encoding_warning=norm_warning or cls.detect_legacy_encoding(raw_text),
                    paragraphs=paras,
                    raw_unnormalized_text=raw_text,
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

    @staticmethod
    def _merge_region_blocks(blocks: List[Any]) -> List[str]:
        """Sắp xếp các block trong cùng 1 vùng/cột theo dòng ngang (lượng tử hóa y 4pt)
        và ghép các mảnh văn bản ngắn nằm trên cùng 1 hàng ngang (ví dụ: 4 đáp án A B C D ngang hàng)."""
        if not blocks:
            return []
        # Sắp xếp theo dòng (y làm tròn mỗi 4pt) rồi từ trái qua phải (x0)
        sorted_b = sorted(blocks, key=lambda b: (round(b[1] / 4.0), b[0]))
        merged_lines: List[str] = []
        cur_y0 = sorted_b[0][1]
        cur_x1 = sorted_b[0][2]
        cur_text = sorted_b[0][4].strip()

        for b in sorted_b[1:]:
            b_text = b[4].strip()
            if not b_text:
                continue
            same_row = (
                abs(b[1] - cur_y0) <= 4.0
                and b[0] >= cur_x1 - 8.0
                and "\n" not in cur_text
                and "\n" not in b_text
                and not cur_text.startswith("|")
                and not b_text.startswith("|")
            )
            if same_row:
                cur_text = f"{cur_text}   {b_text}"
                cur_x1 = max(cur_x1, b[2])
            else:
                merged_lines.append(cur_text)
                cur_y0 = b[1]
                cur_x1 = b[2]
                cur_text = b_text
        if cur_text:
            merged_lines.append(cur_text)
        return merged_lines

    @classmethod
    def _extract_page_text_layout_aware(cls, page: fitz.Page) -> Tuple[str, int]:
        """Trích xuất văn bản có nhận diện bố cục đề thi thông minh:
        1. Khử triệt để hiện tượng trộn lẫn chữ giữa Cột 1 và Cột 2 ở đề thi 2-3 cột.
        2. Bóc tách ma trận bảng biểu (Tables) sang định dạng Markdown chuẩn và khử trùng lặp chữ trong bảng.
        3. Bảo toàn tiêu đề trang (header banner), chân trang (footer), đáp án ngang hàng và công thức toán."""
        tab_count = 0
        table_bboxes: List[Tuple[float, float, float, float]] = []
        synthetic_table_blocks: List[Tuple[float, float, float, float, str, int, int]] = []

        # 1. Chỉ gọi TableFinder khi trang thực sự có nét vẽ khung bảng (>= 4 vector drawings) để tăng tốc 3-5x
        should_find_tables = True
        try:
            drawings = page.get_drawings()
            should_find_tables = len(drawings) >= 4
        except Exception:
            should_find_tables = True

        if should_find_tables:
            try:
                tabs = page.find_tables()
                if tabs and hasattr(tabs, "tables") and tabs.tables:
                    for tab in tabs.tables:
                        try:
                            extracted = tab.extract()
                            if extracted and len(extracted) >= 1:
                                col_count = max(len(r) for r in extracted)
                                if col_count > 0:
                                    tab_count += 1
                                    md_rows = []
                                    headers = [str(c or "").replace("\n", " ").strip() for c in extracted[0]]
                                    headers += [""] * (col_count - len(headers))
                                    md_rows.append("| " + " | ".join(headers) + " |")
                                    md_rows.append("| " + " | ".join(["---"] * col_count) + " |")
                                    for row in extracted[1:]:
                                        cells = [str(c or "").replace("\n", " ").strip() for c in row]
                                        cells += [""] * (col_count - len(cells))
                                        md_rows.append("| " + " | ".join(cells) + " |")
                                    md_str = "\n".join(md_rows)
                                    if hasattr(tab, "bbox") and tab.bbox:
                                        tb = tuple(float(v) for v in tab.bbox)
                                        table_bboxes.append(tb)
                                        synthetic_table_blocks.append((tb[0], tb[1], tb[2], tb[3], md_str, -1, 0))
                                    else:
                                        synthetic_table_blocks.append((0.0, 99999.0, 500.0, 99999.0, md_str, -1, 0))
                        except Exception:
                            pass
            except Exception:
                pass

        # 2. Lấy blocks kèm cờ bảo toàn khoảng trắng, từ nối và chữ ghép
        flags = (
            getattr(fitz, "TEXT_PRESERVE_WHITESPACE", 0)
            | getattr(fitz, "TEXT_DEHYPHENATE", 0)
            | getattr(fitz, "TEXT_PRESERVE_LIGATURES", 0)
        )
        try:
            raw_blocks = page.get_text("blocks", flags=flags)
        except Exception:
            try:
                raw_blocks = page.get_text("blocks")
            except Exception:
                return page.get_text("text"), tab_count

        # Lọc bỏ các text_block nằm gọn bên trong vùng bảng đã được bóc tách sang Markdown (chống nhân đôi chữ)
        text_blocks = []
        for b in raw_blocks:
            if len(b) < 7 or b[6] != 0 or not b[4].strip():
                continue
            if table_bboxes:
                cx = (b[0] + b[2]) / 2.0
                cy = (b[1] + b[3]) / 2.0
                in_table = any(
                    (tb[0] - 3.0 <= cx <= tb[2] + 3.0) and (tb[1] - 3.0 <= cy <= tb[3] + 3.0)
                    for tb in table_bboxes
                )
                if in_table:
                    continue
            text_blocks.append(b)

        # Khử các lớp văn bản trùng lặp (shadow text / duplicate text layer) trên cùng một trang
        if len(text_blocks) > 1:
            tuple_b = [(float(b[0]), float(b[1]), float(b[2]), float(b[3]), str(b[4]), int(b[6])) for b in text_blocks]
            dedup_t, _, _ = LayoutAnalyzer.detect_and_remove_duplicate_blocks(tuple_b, getattr(page, "number", 0) + 1)
            text_blocks = [(b[0], b[1], b[2], b[3], b[4], 0, b[5]) for b in dedup_t]

        text_blocks.extend(synthetic_table_blocks)

        if not text_blocks:
            fallback = page.get_text("text")
            return fallback, tab_count

        rect = page.rect
        w, h = rect.width, rect.height
        mid_x = w / 2.0
        tol = w * 0.05

        headers, footers, body = [], [], []
        for b in text_blocks:
            is_hdr_cue = bool(re.search(r"(?i)\b(?:sở|so|bộ|bo|trường|truong|đề\s*thi|bài\s*thi|kỳ\s*thi|nam\s*hoc|năm\s*học)\b", b[4]))
            is_ftr_cue = bool(re.search(r"(?i)\b(?:hết|het|trang\s*\d|page\s*\d|thí\s*sinh)\b", b[4]))
            # Header banner: ở 25% phía trên và (phủ ngang qua trục giữa hoặc có từ khóa tiêu đề)
            if b[1] < h * 0.25 and (is_hdr_cue or (b[0] < mid_x * 0.75 and b[2] > mid_x * 1.25)):
                headers.append(b)
            # Footer banner: ở 15% phía dưới (hoặc có từ khóa hết/trang/thí sinh)
            elif b[1] > h * 0.85 and (is_ftr_cue or (b[0] < mid_x * 0.75 and b[2] > mid_x * 1.25) or b[1] > h * 0.92):
                footers.append(b)
            else:
                body.append(b)

        # Spanning blocks ở giữa (ví dụ: đoạn văn đọc hiểu hoặc bảng Markdown phủ ngang trang giữa 2 cột)
        spanning = [b for b in body if (b[0] < mid_x * 0.75 and b[2] > mid_x * 1.25) or b[4].startswith("|")]
        col_blocks = [b for b in body if b not in spanning]

        # Kiểm tra bố cục 3 cột trước
        t1, t2 = w / 3.0, 2.0 * w / 3.0
        tol3 = w * 0.04
        c3_left = [b for b in col_blocks if b[2] <= t1 + tol3]
        c3_mid = [b for b in col_blocks if b[0] >= t1 - tol3 and b[2] <= t2 + tol3]
        c3_right = [b for b in col_blocks if b[0] >= t2 - tol3]
        if (
            len(c3_left) >= 1
            and len(c3_mid) >= 1
            and len(c3_right) >= 1
            and len(c3_left) + len(c3_mid) + len(c3_right) == len(col_blocks)
        ):
            ordered_3col = (
                cls._merge_region_blocks(headers)
                + cls._merge_region_blocks(c3_left)
                + cls._merge_region_blocks(c3_mid)
                + cls._merge_region_blocks(c3_right)
                + cls._merge_region_blocks(footers)
            )
            return "\n".join(ordered_3col), tab_count

        left = [b for b in col_blocks if b[2] <= mid_x + tol and b[0] < mid_x]
        right = [b for b in col_blocks if b[0] >= mid_x - tol and b[2] > mid_x]

        is_2col = len(left) >= 2 and len(right) >= 2

        if not is_2col:
            # Trang 1 cột đơn: sắp xếp theo dòng ngang và ghép các mảnh cùng hàng
            res_text = "\n".join(cls._merge_region_blocks(text_blocks))
            return res_text, tab_count

        # Bố cục 2 cột: Sắp xếp headers -> band-by-band (cột trái rồi cột phải) -> footers
        spanning.sort(key=lambda b: b[1])
        ordered_chunks = cls._merge_region_blocks(headers)

        if spanning:
            # Cắt dọc trang thành các phân đoạn (bands) ngăn cách bởi các spanning blocks
            cuts = [0.0] + [s[1] for s in spanning] + [h]
            for idx in range(len(spanning) + 1):
                y_top = cuts[idx]
                y_bot = cuts[idx + 1]
                b_left = [b for b in left if y_top <= b[1] < y_bot]
                b_right = [b for b in right if y_top <= b[1] < y_bot]
                ordered_chunks.extend(cls._merge_region_blocks(b_left))
                ordered_chunks.extend(cls._merge_region_blocks(b_right))
                if idx < len(spanning):
                    ordered_chunks.append(spanning[idx][4].strip())
        else:
            ordered_chunks.extend(cls._merge_region_blocks(left))
            ordered_chunks.extend(cls._merge_region_blocks(right))

        ordered_chunks.extend(cls._merge_region_blocks(footers))

        res_text = "\n".join(ordered_chunks)
        return res_text, tab_count

    @classmethod
    def _extract_pdf(cls, raw_bytes: bytes, magic_sig: str, deep: bool = False) -> ExtractedDocument:
        """Extract PDF via PyMuPDF with page metrics and image counting.
        deep=True: đọc toàn bộ trang + OCR chọn lọc tới 10 trang relevant nhất.
        Luôn lọc trang nhiễu (trắng/quảng cáo) để tín hiệu phân loại sạch hơn."""
        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        try:
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

            page_text_map: Dict[int, str] = {}
            image_count = 0
            table_count = 0
            skipped_noise_pages = 0
            # (page_index, relevance_score, page_obj)
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
                try:
                    page_idx = page.number
                except Exception:
                    page_idx = len(page_text_map)

                page_text, page_tab_cnt = cls._extract_page_text_layout_aware(page)
                table_count += page_tab_cnt
                stripped_len = len(page_text.strip())
                page_images = page.get_images(full=True)
                image_count += len(page_images)

                q_hits = len(q_re.findall(page_text))

                # Lọc trang nhiễu: gần như trắng, không ảnh, không câu hỏi (bìa trắng, trang quảng cáo)
                if stripped_len < 40 and not page_images and q_hits == 0:
                    skipped_noise_pages += 1
                    continue

                page_text_map[page_idx] = page_text

                # Fast table indicator bổ sung
                lines = page_text.splitlines()
                pipe_or_tab = sum(1 for line in lines if "|" in line or "\t" in line)
                if pipe_or_tab >= 3 and page_tab_cnt == 0:
                    table_count += 1

                # Trang cần OCR khi: thiếu text (< 150 ký tự) VÀ (có ảnh hoặc trang ngắn bất thường)
                needs_ocr = (stripped_len < 150) and (bool(page_images) or stripped_len < 30)
                relevance = 3 * min(q_hits, 10) + min(stripped_len / 200.0, 15.0) + (10.0 if page_images else 0.0)
                if needs_ocr:
                    # Ưu tiên trang đầu và trang cuối (chứa tiêu đề đề thi, thông tin trường, đáp án)
                    if page_idx <= 1:
                        relevance += 20.0
                    elif page_idx >= page_count - 2:
                        relevance += 12.0
                    ocr_candidates.append((page_idx, relevance, page))

            # Thực hiện OCR theo từng trang thiếu chữ (Per-Page Hybrid OCR)
            ocr_pages_used: List[int] = []
            if ocr_candidates and init_tesseract():
                # Sắp xếp các trang cần OCR theo mức độ ưu tiên
                ocr_candidates.sort(key=lambda t: t[1], reverse=True)
                max_ocr_pages = 25 if deep else 8
                ocr_dpi = 250 if deep else 200

                for page_idx, _rel, page in ocr_candidates[:max_ocr_pages]:
                    try:
                        pix = page.get_pixmap(dpi=ocr_dpi)
                        img_bytes = pix.tobytes("png")
                        del pix
                        ocr_txt = cls.perform_ocr(img_bytes)
                        del img_bytes
                        if ocr_txt and len(ocr_txt.strip()) >= 20:
                            if AIDocumentEnhancer is not None and AIDocumentEnhancer.is_available() and deep:
                                try:
                                    enhanced_txt = AIDocumentEnhancer.clean_noisy_ocr_text(ocr_txt)
                                    if enhanced_txt and len(enhanced_txt.strip()) >= 20:
                                        ocr_txt = enhanced_txt
                                except Exception as ai_e:
                                    log.debug("AI OCR cleanup fallback: %s", ai_e)

                            existing = page_text_map.get(page_idx, "").strip()
                            if len(ocr_txt.strip()) > len(existing):
                                page_text_map[page_idx] = ocr_txt
                            else:
                                page_text_map[page_idx] = (existing + "\n" + ocr_txt).strip()
                            ocr_pages_used.append(page_idx)
                    except Exception as ocr_err:
                        log.debug("Lỗi OCR trang %s: %s", page_idx, ocr_err)

            # Ghép văn bản theo thứ tự trang thực tế và chuẩn hóa TCVN3 / Symbol PUA / Unicode NFC
            ordered_texts = [page_text_map[idx] for idx in sorted(page_text_map.keys()) if page_text_map[idx].strip()]
            raw_full_text = "\n".join(ordered_texts)
            full_text, norm_warning = cls.normalize_exam_text(raw_full_text)
            char_count = len(full_text.strip())
            word_count = len(full_text.split())
            line_count = len(full_text.splitlines())

            # Scanned PDF check: nếu đa số trang thiếu text native và có ảnh
            low_native_count = sum(1 for p_idx, _, _ in ocr_candidates)
            is_scanned_pdf = (page_count > 0) and (low_native_count >= max(1, page_count // 2)) and (image_count >= page_count // 2)

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
            legacy_enc = norm_warning or cls.detect_legacy_encoding(raw_full_text)

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
                raw_unnormalized_text=raw_full_text,
            )
        finally:
            try:
                doc.close()
            except Exception:
                pass
            if len(raw_bytes) > 2 * 1024 * 1024:
                import gc
                gc.collect()

    @classmethod
    def _extract_docx(cls, raw_bytes: bytes, magic_sig: str) -> ExtractedDocument:
        """Extract DOCX via python-docx preserving exact sequential order of paragraphs & tables,
        OMML math formulas inside both paragraphs and table cells, headers/footers, shapes, and embedded images."""
        file_stream = io.BytesIO(raw_bytes)
        try:
            doc = Document(file_stream)

            # 1. Trích xuất Header & Footer (chứa tên trường, sở GD, mã đề, năm học)
            header_footer_texts: List[str] = []
            for section in doc.sections:
                try:
                    for h_p in section.header.paragraphs:
                        ht = h_p.text.strip()
                        if ht and ht not in header_footer_texts:
                            header_footer_texts.append(ht)
                except Exception:
                    pass
                try:
                    for f_p in section.footer.paragraphs:
                        ft = f_p.text.strip()
                        if ft and ft not in header_footer_texts:
                            header_footer_texts.append(ft)
                except Exception:
                    pass

            # 2. Hàm trích xuất phần tử XML (w:p) bảo toàn cả văn bản (<w:t>), chỉ số trên/dưới (vertAlign) và công thức toán OMML (<m:f>, <m:rad>, <m:sSup>, <m:sSub>)
            def _extract_omml_node(m_node) -> str:
                tag = m_node.tag.split("}")[-1] if "}" in m_node.tag else m_node.tag
                if tag == "t":
                    return m_node.text or ""
                if tag == "f":
                    num_s, den_s = "", ""
                    for ch in m_node.iterchildren():
                        ctag = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
                        if ctag == "num":
                            num_s = _extract_omml_node(ch).strip()
                        elif ctag == "den":
                            den_s = _extract_omml_node(ch).strip()
                    return f"\\frac{{{num_s}}}{{{den_s}}}" if (num_s or den_s) else ""
                if tag == "rad":
                    deg_s, base_s = "", ""
                    for ch in m_node.iterchildren():
                        ctag = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
                        if ctag == "deg":
                            deg_s = _extract_omml_node(ch).strip()
                        elif ctag == "e":
                            base_s = _extract_omml_node(ch).strip()
                    return f"\\sqrt[{deg_s}]{{{base_s}}}" if deg_s else f"\\sqrt{{{base_s}}}"
                if tag == "sSup":
                    base_s, sup_s = "", ""
                    for ch in m_node.iterchildren():
                        ctag = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
                        if ctag == "e":
                            base_s = _extract_omml_node(ch).strip()
                        elif ctag == "sup":
                            sup_s = _extract_omml_node(ch).strip()
                    return f"{base_s}^{{{sup_s}}}" if len(sup_s) > 1 else f"{base_s}^{sup_s}"
                if tag == "sSub":
                    base_s, sub_s = "", ""
                    for ch in m_node.iterchildren():
                        ctag = ch.tag.split("}")[-1] if "}" in ch.tag else ch.tag
                        if ctag == "e":
                            base_s = _extract_omml_node(ch).strip()
                        elif ctag == "sub":
                            sub_s = _extract_omml_node(ch).strip()
                    return f"{base_s}_{{{sub_s}}}" if len(sub_s) > 1 else f"{base_s}_{sub_s}"
                return "".join(_extract_omml_node(ch) for ch in m_node.iterchildren())

            def _extract_xml_math_aware(xml_elem) -> str:
                chunks: List[str] = []
                try:
                    for child in xml_elem.iterchildren():
                        ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                        if ctag in ("oMath", "oMathPara"):
                            om = _extract_omml_node(child).strip()
                            if om:
                                chunks.append(f" {om} ")
                        elif ctag == "r":
                            vert = None
                            r_parts: List[str] = []
                            for rch in child.iterchildren():
                                rtag = rch.tag.split("}")[-1] if "}" in rch.tag else rch.tag
                                if rtag == "rPr":
                                    for pr in rch.iterchildren():
                                        ptag = pr.tag.split("}")[-1] if "}" in pr.tag else pr.tag
                                        if ptag == "vertAlign":
                                            for k, v in pr.attrib.items():
                                                if k.endswith("val"):
                                                    vert = v
                                elif rtag == "t" and rch.text:
                                    r_parts.append(rch.text)
                                elif rtag == "tab":
                                    r_parts.append(" ")
                                elif rtag in ("br", "cr"):
                                    r_parts.append("\n")
                            r_str = "".join(r_parts)
                            if r_str and vert == "superscript":
                                r_str = f"^{{{r_str}}}" if len(r_str) > 1 else f"^{r_str}"
                            elif r_str and vert == "subscript":
                                r_str = f"_{{{r_str}}}" if len(r_str) > 1 else f"_{r_str}"
                            chunks.append(r_str)
                        else:
                            for node in child.iter():
                                tag = node.tag
                                if tag.endswith('}t') or tag in ('t', 'w:t', 'm:t'):
                                    if node.text:
                                        chunks.append(node.text)
                                elif tag.endswith('}tab') or tag in ('tab', 'w:tab'):
                                    chunks.append(" ")
                                elif tag.endswith(('}br', '}cr')) or tag in ('br', 'w:br', 'cr', 'w:cr'):
                                    chunks.append("\n")
                    return "".join(chunks).strip()
                except Exception:
                    return ""

            def _format_table_xml_to_markdown(tbl_elem) -> str:
                rows_data = []
                for tr in tbl_elem.iterchildren():
                    if not tr.tag.endswith('tr'):
                        continue
                    row_cells = []
                    for tc in tr.iterchildren():
                        if not tc.tag.endswith('tc'):
                            continue
                        cell_paras = []
                        for p in tc.iterchildren():
                            if p.tag.endswith('p'):
                                pt = _extract_xml_math_aware(p)
                                if pt:
                                    cell_paras.append(pt)
                        cell_str = " ".join(cell_paras).replace("\n", " ").strip()
                        row_cells.append(cell_str)
                    if row_cells:
                        rows_data.append(row_cells)
                if not rows_data:
                    return ""
                col_count = max(len(r) for r in rows_data)
                if col_count == 0:
                    return ""
                md_lines = []
                headers = rows_data[0] + [""] * (col_count - len(rows_data[0]))
                md_lines.append("| " + " | ".join(headers) + " |")
                md_lines.append("| " + " | ".join(["---"] * col_count) + " |")
                for row in rows_data[1:]:
                    cells = row + [""] * (col_count - len(row))
                    md_lines.append("| " + " | ".join(cells) + " |")
                return "\n".join(md_lines)

            # 3. Duyệt tuần tự doc.element.body để giữ nguyên vị trí Bảng biểu nằm xen kẽ giữa các Câu hỏi
            sequential_body_blocks: List[str] = []
            paragraphs: List[str] = []
            table_texts: List[str] = []
            try:
                for child in doc.element.body.iterchildren():
                    if child.tag.endswith('p'):
                        p_txt = _extract_xml_math_aware(child)
                        if p_txt:
                            paragraphs.append(p_txt)
                            sequential_body_blocks.append(p_txt)
                    elif child.tag.endswith('tbl'):
                        t_md = _format_table_xml_to_markdown(child)
                        if t_md:
                            table_texts.append(t_md)
                            sequential_body_blocks.append(t_md)
            except Exception:
                # Fallback nếu cấu trúc XML bất thường
                paragraphs = [_extract_xml_math_aware(p._p) for p in doc.paragraphs if _extract_xml_math_aware(p._p)]
                for table in doc.tables:
                    t_md = _format_table_xml_to_markdown(table._tbl)
                    if t_md:
                        table_texts.append(t_md)
                sequential_body_blocks = paragraphs + table_texts

            # 4. Text Boxes / Shapes (w:txbxContent - chứa câu hỏi dạng hộp khung)
            textbox_texts: List[str] = []
            try:
                for txbx in doc.element.xpath('.//w:txbxContent'):
                    tb_text = _extract_xml_math_aware(txbx)
                    if tb_text and tb_text not in textbox_texts and tb_text not in paragraphs:
                        textbox_texts.append(tb_text)
            except Exception:
                pass

            # 5. Đếm và trích xuất ảnh nhúng (Embedded Images) + OCR nếu cần
            embedded_images: List[bytes] = []
            try:
                for rel in doc.part.rels.values():
                    rel_type = getattr(rel, "reltype", "").lower()
                    target_ref = getattr(rel, "target_ref", "").lower()
                    if "image" in rel_type or "image" in target_ref or target_ref.endswith((".png", ".jpg", ".jpeg", ".bmp", ".webp")):
                        img_part = getattr(rel, "target_part", None)
                        if img_part and hasattr(img_part, "blob") and img_part.blob:
                            embedded_images.append(img_part.blob)
            except Exception:
                pass
            image_count = len(embedded_images)

            # OCR ảnh nhúng nếu đề thi chụp câu hỏi dạng ảnh (hoặc ít text native)
            ocr_image_texts: List[str] = []
            base_text_len = sum(len(p) for p in sequential_body_blocks)
            if embedded_images and init_tesseract() and (base_text_len < 1500 or image_count <= 8):
                large_images = [img for img in embedded_images if len(img) >= 15 * 1024]
                for img_blob in large_images[:6]:  # OCR tối đa 6 ảnh để giữ tốc độ cao
                    img_txt = cls.perform_ocr(img_blob)
                    if img_txt and len(img_txt.strip()) >= 30:
                        ocr_image_texts.append(img_txt.strip())

            all_blocks = header_footer_texts + sequential_body_blocks + textbox_texts + ocr_image_texts
            raw_full_text = "\n".join(all_blocks)
            full_text, norm_warning = cls.normalize_exam_text(raw_full_text)
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
            if header_footer_texts:
                meta["headers_extracted"] = len(header_footer_texts)
            if textbox_texts:
                meta["textboxes_extracted"] = len(textbox_texts)
            if ocr_image_texts:
                meta["ocr_images_processed"] = len(ocr_image_texts)

            entropy = cls.calculate_entropy(full_text)
            reading_time = round(word_count / 200.0, 1)
            legacy_enc = norm_warning or cls.detect_legacy_encoding(raw_full_text)

            return ExtractedDocument(
                full_text=full_text,
                page_count=approx_pages,
                char_count=char_count,
                word_count=word_count,
                line_count=line_count,
                paragraph_count=len(paragraphs) + len(textbox_texts),
                table_count=len(doc.tables),
                image_count=image_count,
                is_scanned_pdf=False,
                is_encrypted=False,
                raw_type="DOCX",
                magic_signature=magic_sig,
                entropy=entropy,
                reading_time_minutes=reading_time,
                legacy_encoding_warning=legacy_enc,
                meta_properties=meta,
                headers=header_footer_texts,
                paragraphs=paragraphs + textbox_texts,
                raw_unnormalized_text=raw_full_text,
            )
        finally:
            try:
                file_stream.close()
            except Exception:
                pass
            if len(raw_bytes) > 2 * 1024 * 1024:
                import gc
                gc.collect()

    @classmethod
    def _extract_legacy_doc(cls, raw_bytes: bytes, magic_sig: str) -> ExtractedDocument:
        """Trích xuất văn bản từ tệp nhị phân Word .doc (Word 97-2003 OLE2)
        hỗ trợ cả UTF-16LE Unicode tiếng Việt, Windows CP1258, TCVN3 và ASCII fallback."""

        # 1. Trích xuất UTF-16LE (Word 97-2003 lưu text Unicode dạng UTF-16LE)
        utf16_candidates: List[str] = []
        utf16_pattern = re.compile(b'(?:[\x20-\x7e\xa0-\xff][\x00\x01\x02\x03\x1e\x1f]){4,}')
        for m in utf16_pattern.finditer(raw_bytes):
            chunk = m.group(0)
            if len(chunk) % 2 != 0:
                chunk = chunk[:-1]
            try:
                decoded = chunk.decode("utf-16le", errors="ignore")
                cleaned = "".join(c for c in decoded if c.isprintable() or c in "\n\r\t").strip()
                if len(cleaned) >= 4 and any(c.isalnum() for c in cleaned):
                    if not any(noise in cleaned for noise in ("WordDocument", "Root Entry", "CompObj", "SummaryInformation")):
                        utf16_candidates.append(cleaned)
            except Exception:
                pass

        # 2. Trích xuất CP1258 (Windows-1258 tiếng Việt 8-bit)
        cp1258_candidates: List[str] = []
        cp1258_pattern = re.compile(b'[\x20-\x7e\x80-\xff\t\n\r]{4,}')
        for m in cp1258_pattern.finditer(raw_bytes):
            chunk = m.group(0)
            try:
                decoded = chunk.decode("cp1258", errors="ignore").strip()
                if len(decoded) >= 4 and any(c.isalnum() for c in decoded):
                    if not any(noise in decoded for noise in ("WordDocument", "Root Entry", "CompObj", "SummaryInformation")):
                        cp1258_candidates.append(decoded)
            except Exception:
                pass

        # 3. So sánh chọn nguồn chất lượng nhất (dựa trên ký tự tiếng Việt có dấu & độ dài)
        vi_chars = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
        utf16_vi_count = sum(sum(1 for c in s.lower() if c in vi_chars) for s in utf16_candidates)
        cp1258_vi_count = sum(sum(1 for c in s.lower() if c in vi_chars) for s in cp1258_candidates)

        if utf16_vi_count > 0 or len("".join(utf16_candidates)) >= len("".join(cp1258_candidates)):
            extracted_strings = utf16_candidates if utf16_candidates else cp1258_candidates
        else:
            extracted_strings = cp1258_candidates if cp1258_candidates else utf16_candidates

        # 4. Fallback ASCII nếu không bóc tách được Unicode/CP1258
        if not extracted_strings:
            printable_ascii = re.findall(b"[\x20-\x7e\t\n\r]{4,}", raw_bytes)
            extracted_strings = [s.decode("latin-1", errors="ignore").strip() for s in printable_ascii if s.decode("latin-1", errors="ignore").strip()]

        raw_full_text = "\n".join(extracted_strings)
        full_text, norm_warning = cls.normalize_exam_text(raw_full_text)
        char_count = len(full_text.strip())
        word_count = len(full_text.split())
        line_count = len(full_text.splitlines())
        approx_pages = max(1, round(char_count / 2200))

        entropy = cls.calculate_entropy(full_text)
        reading_time = round(word_count / 200.0, 1)
        legacy_enc = norm_warning or cls.detect_legacy_encoding(raw_full_text)

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
            legacy_encoding_warning=legacy_enc,
            paragraphs=extracted_strings,
            raw_unnormalized_text=raw_full_text,
        )

    @classmethod
    def _extract_image(cls, raw_bytes: bytes, magic_sig: str) -> ExtractedDocument:
        """Extract text from image files (PNG, JPG, WEBP, BMP, GIF) via OCR."""
        ocr_text = cls.perform_ocr(raw_bytes)
        if AIDocumentEnhancer is not None and AIDocumentEnhancer.is_available() and len(ocr_text.strip()) >= 30:
            try:
                enhanced_text = AIDocumentEnhancer.clean_noisy_ocr_text(ocr_text)
                if enhanced_text and len(enhanced_text.strip()) >= len(ocr_text.strip()) * 0.6:
                    ocr_text = enhanced_text
            except Exception:
                pass
        ocr_text, norm_warning = cls.normalize_exam_text(ocr_text)
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
            legacy_encoding_warning=norm_warning,
            meta_properties={"image_format": magic_sig},
            paragraphs=paragraphs,
        )

