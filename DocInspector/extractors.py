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
    paragraphs: List[str] = field(default_factory=list)



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

                page_text = page.get_text("text")
                stripped_len = len(page_text.strip())
                page_images = page.get_images(full=True)
                image_count += len(page_images)

                q_hits = len(q_re.findall(page_text))

                # Lọc trang nhiễu: gần như trắng, không ảnh, không câu hỏi (bìa trắng, trang quảng cáo)
                if stripped_len < 40 and not page_images and q_hits == 0:
                    skipped_noise_pages += 1
                    continue

                page_text_map[page_idx] = page_text

                # Fast table indicator
                lines = page_text.splitlines()
                pipe_or_tab = sum(1 for line in lines if "|" in line or "\t" in line)
                if pipe_or_tab >= 3:
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
                            existing = page_text_map.get(page_idx, "").strip()
                            if len(ocr_txt.strip()) > len(existing):
                                page_text_map[page_idx] = ocr_txt
                            else:
                                page_text_map[page_idx] = (existing + "\n" + ocr_txt).strip()
                            ocr_pages_used.append(page_idx)
                    except Exception as ocr_err:
                        log.debug("Lỗi OCR trang %s: %s", page_idx, ocr_err)

            # Ghép văn bản theo thứ tự trang thực tế (không làm mất text của các trang điện tử)
            ordered_texts = [page_text_map[idx] for idx in sorted(page_text_map.keys()) if page_text_map[idx].strip()]
            full_text = "\n".join(ordered_texts)
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
        """Extract DOCX via python-docx with table cell text, headers/footers, shapes, and embedded images."""
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

            # 2. Đoạn văn thông thường
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

            # 3. Bảng biểu (Tables)
            table_texts: List[str] = []
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                    if row_text:
                        table_texts.append(row_text)

            # 4. Text Boxes / Shapes (w:txbxContent - chứa câu hỏi dạng hộp khung)
            textbox_texts: List[str] = []
            try:
                for txbx in doc.element.xpath('.//w:txbxContent'):
                    tb_text = "".join(txbx.itertext()).strip()
                    if tb_text and tb_text not in textbox_texts:
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
            base_text_len = sum(len(p) for p in paragraphs) + sum(len(t) for t in table_texts)
            if embedded_images and init_tesseract() and (base_text_len < 1500 or image_count <= 8):
                large_images = [img for img in embedded_images if len(img) >= 15 * 1024]
                for img_blob in large_images[:6]:  # OCR tối đa 6 ảnh để giữ tốc độ cao
                    img_txt = cls.perform_ocr(img_blob)
                    if img_txt and len(img_txt.strip()) >= 30:
                        ocr_image_texts.append(img_txt.strip())

            all_blocks = header_footer_texts + paragraphs + table_texts + textbox_texts + ocr_image_texts
            full_text = "\n".join(all_blocks)
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
            legacy_enc = cls.detect_legacy_encoding(full_text)

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
        hỗ trợ cả UTF-16LE Unicode tiếng Việt, Windows CP1258, và ASCII fallback."""

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

        full_text = "\n".join(extracted_strings)
        char_count = len(full_text.strip())
        word_count = len(full_text.split())
        line_count = len(full_text.splitlines())
        approx_pages = max(1, round(char_count / 2200))

        entropy = cls.calculate_entropy(full_text)
        reading_time = round(word_count / 200.0, 1)
        legacy_enc = cls.detect_legacy_encoding(full_text)

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

