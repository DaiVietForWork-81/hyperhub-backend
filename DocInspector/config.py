"""
Centralized Configuration, Resource Limits, Security Policy, and OCR Mode Control
for DocInspector Parsing Engine.
100% Deterministic, Offline-First, Zero-LLM by Default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class OCRMode(str, Enum):
    """
    Chế độ OCR cục bộ:
    - OFF  : Tuyệt đối không gọi bất kỳ mô hình OCR/ML nào. Giữ nguyên image asset và đánh dấu cần xử lý thủ công.
    - LOCAL: Chỉ sử dụng OCR cục bộ trên máy (Tesseract local), không gọi mạng hay đám mây.
    """
    OFF = "off"
    LOCAL = "local"


class LegacyDocPolicy(str, Enum):
    """Chính sách xử lý file .DOC cũ (Word 97-2003 OLE2)."""
    AUTO = "auto"                                 # Thử chuyển đổi bằng LibreOffice cục bộ nếu có, fallback sang binary stream parser kèm cảnh báo
    CONVERTER_ONLY = "converter_only"             # Chỉ dùng trình chuyển đổi cục bộ (LibreOffice/soffice)
    BINARY_FALLBACK = "binary_fallback"           # Bóc tách chuỗi UTF-16LE/CP1258 trực tiếp từ OLE2 stream
    LIBREOFFICE_THEN_BINARY_FALLBACK = "auto"     # Alias tương thích
    LIBREOFFICE_STRICT = "converter_only"         # Alias tương thích


@dataclass
class EngineConfig:
    """
    Cấu hình tập trung cho toàn bộ bộ máy đọc và phân tích đề thi.
    Không phụ thuộc LLM, kiểm soát chặt chẽ tài nguyên và an toàn file.
    """
    # 1. Chế độ Offline & Cấm LLM mặc định
    strict_offline: bool = True
    allow_llm_enhancement: bool = False  # Mặc định False: cấm gọi Gemini/Ollama/LLM trong pipeline

    # 2. Cấu hình OCR cục bộ
    ocr_mode: OCRMode = OCRMode.LOCAL
    ocr_languages: str = "vie+eng"
    ocr_timeout_sec: int = 25
    ocr_render_dpi: int = 200
    ocr_deep_render_dpi: int = 250
    max_ocr_pages_fast: int = 8
    max_ocr_pages_deep: int = 25
    min_native_chars_per_page: int = 35

    # 3. Giới hạn tài nguyên (Resource Limits)
    max_file_size_bytes: int = 50 * 1024 * 1024        # 50 MB
    max_page_count: int = 500                          # Tối đa 500 trang/tài liệu
    max_pages: int = 500                               # Alias cho max_page_count
    max_rendered_page_pixels: int = 16_000_000         # ~4000x4000 pixels
    max_image_dimension: int = 3200                    # Giới hạn cạnh lớn nhất khi xử lý ảnh
    max_document_processing_time_sec: float = 60.0     # Timeout xử lý 1 tài liệu
    extraction_timeout_sec: int = 60                   # Alias timeout
    max_extraction_text_length: int = 5_000_000        # Tối đa 5 triệu ký tự
    max_table_nesting_depth: int = 4                   # Độ sâu bảng lồng nhau tối đa
    max_batch_size: int = 100                          # Số file tối đa trong 1 batch
    max_batch_workers: int = 4                         # Số luồng xử lý batch tối đa

    # 4. Giới hạn an toàn giải nén ZIP/DOCX (Chống Zip Bomb & Path Traversal)
    max_zip_uncompressed_bytes: int = 120 * 1024 * 1024  # 120 MB sau giải nén
    max_zip_entries: int = 2500                          # Tối đa 2500 file con trong gói DOCX/ZIP
    max_zip_members: int = 2500                          # Alias cho max_zip_entries
    max_zip_compression_ratio: float = 100.0             # Tỉ lệ nén tối đa cho phép

    # 5. Chính sách chuyển đổi DOC cũ
    legacy_doc_policy: LegacyDocPolicy = LegacyDocPolicy.AUTO
    legacy_doc_convert_timeout_sec: int = 15
    libreoffice_timeout_sec: int = 15

    # 6. Ngưỡng Confidence & Diagnostics
    high_confidence_threshold: float = 0.80
    medium_confidence_threshold: float = 0.55
    debug_diagnostics: bool = False
    schema_version: str = "2.0.0"
    supported_extensions: Tuple[str, ...] = (
        ".pdf", ".docx", ".doc", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".txt", ".md"
    )

    @classmethod
    def from_env(cls) -> "EngineConfig":
        """Đọc cấu hình từ biến môi trường (nếu có) với giá trị mặc định an toàn."""
        ocr_env = os.environ.get("DOCINSPECTOR_OCR_MODE", os.environ.get("OCR_MODE", "local")).strip().lower()
        ocr_mode = OCRMode.OFF if ocr_env in ("off", "0", "false", "none", "disabled") else OCRMode.LOCAL

        allow_llm = os.environ.get("DOCINSPECTOR_ALLOW_LLM", "0").strip().lower() in ("1", "true", "yes")
        strict_offline = os.environ.get("DOCINSPECTOR_STRICT_OFFLINE", "1").strip().lower() not in ("0", "false", "no")
        if strict_offline:
            allow_llm = False

        max_mb = int(os.environ.get("DOCINSPECTOR_MAX_FILE_MB", "50"))
        max_pages = int(os.environ.get("DOCINSPECTOR_MAX_PAGES", "500"))
        debug = os.environ.get("DOCINSPECTOR_DEBUG", "0").strip().lower() in ("1", "true", "yes")

        return cls(
            strict_offline=strict_offline,
            allow_llm_enhancement=allow_llm,
            ocr_mode=ocr_mode,
            max_file_size_bytes=max_mb * 1024 * 1024,
            max_page_count=max_pages,
            max_pages=max_pages,
            debug_diagnostics=debug,
        )


# Singleton cấu hình mặc định có thể đọc hoặc ghi đè trong runtime / test
DEFAULT_CONFIG: EngineConfig = EngineConfig.from_env()


def get_config() -> EngineConfig:
    """Trả về cấu hình hiện hành của Engine."""
    return DEFAULT_CONFIG


def set_config(cfg: EngineConfig) -> None:
    """Ghi đè cấu hình Engine hiện hành."""
    global DEFAULT_CONFIG
    DEFAULT_CONFIG = cfg


def set_ocr_mode(mode: OCRMode | str) -> None:
    """Bật/tắt chế độ OCR cục bộ ('off' hoặc 'local')."""
    global DEFAULT_CONFIG
    if isinstance(mode, str):
        m = mode.strip().lower()
        DEFAULT_CONFIG.ocr_mode = OCRMode.OFF if m in ("off", "0", "false", "none") else OCRMode.LOCAL
    else:
        DEFAULT_CONFIG.ocr_mode = mode
