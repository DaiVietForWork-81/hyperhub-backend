"""
services/media_processor.py
Multimedia Processor Service - OCR, PDF, Word, Wikipedia, Google Drive, Discord attachments.
Trích xuất text từ: ảnh (OCR), PDF, Word, Wikipedia, Google Drive, Discord attachments.
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

from config.settings import settings
from services.knowledge_base import kb
from utils.logger import get_logger

logger = get_logger("MediaProcessor")

# ============================================================
# OPTIONAL IMPORTS (graceful degradation)
# ============================================================

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False
    logger.warning("pytesseract/PIL không cài đặt - OCR ảnh sẽ không hoạt động")

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    logger.warning("PyMuPDF (fitz) không cài đặt - PDF processing sẽ hạn chế")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber không cài đặt - PDF text extraction sẽ hạn chế")

try:
    from docx import Document
    from docx.oxml.ns import qn
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    logger.warning("python-docx không cài đặt - Word processing sẽ không hoạt động")

try:
    import wikipedia
    HAS_WIKIPEDIA = True
except ImportError:
    HAS_WIKIPEDIA = False
    logger.warning("wikipedia package không cài đặt - Wikipedia search sẽ không hoạt động")

# Google Drive API (optional)
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.oauth2.service_account import Credentials
    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False
    logger.warning("Google Drive API packages không cài đặt - GDrive integration sẽ không hoạt động")


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class MediaResult:
    """Kết quả xử lý media."""
    success: bool
    text: str = ""
    source_type: str = ""  # 'image', 'pdf', 'docx', 'wikipedia', 'gdrive', 'discord_attachment'
    source_path: str = ""
    error: str = ""
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ============================================================
# MEDIA PROCESSOR CLASS
# ============================================================

class MediaProcessor:
    """Xử lý đa phương tiện: OCR, PDF, Word, Wikipedia, GDrive, Discord attachments."""
    
    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "bot_media"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Tesseract path config (Cross-platform)
        if HAS_TESSERACT:
            if os.name == 'nt':
                possible_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                    r"C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe".format(os.getenv('USERNAME', '')),
                ]
                for p in possible_paths:
                    if os.path.exists(p):
                        pytesseract.pytesseract.tesseract_cmd = p
                        break
            else:
                # Linux / Ubuntu / macOS
                found_tess = shutil.which("tesseract")
                if found_tess:
                    pytesseract.pytesseract.tesseract_cmd = found_tess
                else:
                    for p in ["/usr/bin/tesseract", "/usr/local/bin/tesseract", "/usr/bin/tesseract-ocr"]:
                        if os.path.exists(p):
                            pytesseract.pytesseract.tesseract_cmd = p
                            break
    
    # ========================================================
    # IMAGE OCR
    # ========================================================
    
    def ocr_image(self, image_path: str, lang: str = "vie+eng") -> MediaResult:
        """OCR ảnh bằng Tesseract."""
        if not HAS_TESSERACT:
            return MediaResult(False, error="pytesseract/PIL không cài đặt", source_type="image", source_path=image_path)
        
        try:
            img = Image.open(image_path)
            # Resize if too large
            max_dim = 4000
            if max(img.size) > max_dim:
                ratio = max_dim / max(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.Resampling.LANCZOS)
            
            text = pytesseract.image_to_string(img, lang=lang, config='--psm 6')
            text = re.sub(r'\n\s*\n', '\n\n', text).strip()
            
            return MediaResult(
                success=True,
                text=text,
                source_type="image",
                source_path=image_path,
                metadata={"lang": lang, "size": img.size}
            )
        except Exception as e:
            return MediaResult(False, error=f"OCR lỗi: {e}", source_type="image", source_path=image_path)
    
    def ocr_image_bytes(self, image_bytes: bytes, lang: str = "vie+eng") -> MediaResult:
        """OCR từ bytes ảnh."""
        if not HAS_TESSERACT:
            return MediaResult(False, error="pytesseract/PIL không cài đặt", source_type="image")
        
        try:
            img = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(img, lang=lang, config='--psm 6')
            text = re.sub(r'\n\s*\n', '\n\n', text).strip()
            
            return MediaResult(
                success=True,
                text=text,
                source_type="image",
                metadata={"lang": lang, "size": img.size}
            )
        except Exception as e:
            return MediaResult(False, error=f"OCR bytes lỗi: {e}", source_type="image")
    
    # ========================================================
    # PDF PROCESSING
    # ========================================================
    
    def extract_pdf_text(self, pdf_path: str) -> MediaResult:
        """Trích xuất text từ PDF (ưu tiên pdfplumber, fallback fitz)."""
        text_parts = []
        images_ocr = []
        
        # Try pdfplumber first (better text extraction)
        if HAS_PDFPLUMBER:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for i, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(f"--- Trang {i+1} ---\n{page_text}")
                        
                        # Extract images from page for OCR
                        if HAS_FITZ:
                            pass  # Will handle with fitz below
            except Exception as e:
                logger.warning(f"pdfplumber error: {e}")
        
        # Use PyMuPDF for images + fallback text
        if HAS_FITZ:
            try:
                doc = fitz.open(pdf_path)
                for i, page in enumerate(doc):
                    if not text_parts or i >= len(text_parts):
                        page_text = page.get_text()
                        if page_text.strip():
                            if i < len(text_parts):
                                text_parts[i] = f"--- Trang {i+1} ---\n{page_text}"
                            else:
                                text_parts.append(f"--- Trang {i+1} ---\n{page_text}")
                    
                    # Extract images for OCR
                    if HAS_TESSERACT:
                        images = page.get_images(full=True)
                        for img_idx, img in enumerate(images):
                            xref = img[0]
                            try:
                                pix = fitz.Pixmap(doc, xref)
                                if pix.n < 5:  # GRAY or RGB
                                    img_bytes = pix.tobytes("png")
                                    ocr_result = self.ocr_image_bytes(img_bytes)
                                    if ocr_result.success and ocr_result.text.strip():
                                        images_ocr.append(f"--- Hình ảnh trang {i+1}, img {img_idx+1} ---\n{ocr_result.text}")
                                pix = None
                            except Exception:
                                pass
                doc.close()
            except Exception as e:
                logger.warning(f"PyMuPDF error: {e}")
        
        # Combine text + OCR results
        full_text = "\n\n".join(filter(None, text_parts + images_ocr))
        full_text = re.sub(r'\n{3,}', '\n\n', full_text).strip()
        
        if not full_text:
            return MediaResult(False, error="Không trích xuất được text từ PDF", source_type="pdf", source_path=pdf_path)
        
        return MediaResult(
            success=True,
            text=full_text,
            source_type="pdf",
            source_path=pdf_path,
            metadata={"pages": len(text_parts), "images_ocr": len(images_ocr)}
        )
    
    def extract_pdf_bytes(self, pdf_bytes: bytes) -> MediaResult:
        """Extract PDF từ bytes."""
        if HAS_FITZ:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                text_parts = []
                for page in doc:
                    text = page.get_text()
                    if text.strip():
                        text_parts.append(text)
                doc.close()
                full_text = "\n\n".join(text_parts).strip()
                if full_text:
                    return MediaResult(True, text=full_text, source_type="pdf", metadata={"pages": len(text_parts)})
            except Exception as e:
                return MediaResult(False, error=f"PDF bytes error: {e}", source_type="pdf")
        return MediaResult(False, error="Không trích xuất được PDF", source_type="pdf")
    
    # ========================================================
    # WORD DOCUMENT PROCESSING
    # ========================================================
    
    def extract_docx(self, docx_path: str) -> MediaResult:
        """Trích xuất text + ảnh từ Word document."""
        if not HAS_DOCX:
            return MediaResult(False, error="python-docx không cài đặt", source_type="docx", source_path=docx_path)
        
        try:
            doc = Document(docx_path)
            text_parts = []
            images_ocr = []
            
            # Extract text
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)
            
            # Extract tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text for cell in row.cells)
                    if row_text.strip():
                        text_parts.append(row_text)
            
            # Extract images for OCR
            if HAS_TESSERACT:
                for rel in doc.part.rels.values():
                    if "image" in rel.target_ref:
                        try:
                            img_bytes = rel.target_part.blob
                            ocr_result = self.ocr_image_bytes(img_bytes)
                            if ocr_result.success and ocr_result.text.strip():
                                images_ocr.append(ocr_result.text)
                        except Exception:
                            pass
            
            full_text = "\n\n".join(filter(None, text_parts + images_ocr))
            full_text = re.sub(r'\n{3,}', '\n\n', full_text).strip()
            
            return MediaResult(
                success=True,
                text=full_text,
                source_type="docx",
                source_path=docx_path,
                metadata={"paragraphs": len(text_parts), "images_ocr": len(images_ocr)}
            )
        except Exception as e:
            return MediaResult(False, error=f"DOCX error: {e}", source_type="docx", source_path=docx_path)
    
    def extract_docx_bytes(self, docx_bytes: bytes) -> MediaResult:
        """Extract DOCX từ bytes."""
        if not HAS_DOCX:
            return MediaResult(False, error="python-docx không cài đặt", source_type="docx")
        try:
            doc = Document(io.BytesIO(docx_bytes))
            text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
            full_text = "\n\n".join(text_parts).strip()
            return MediaResult(True, text=full_text, source_type="docx", metadata={"paragraphs": len(text_parts)})
        except Exception as e:
            return MediaResult(False, error=f"DOCX bytes error: {e}", source_type="docx")
    
    # ========================================================
    # WIKIPEDIA
    # ========================================================
    
    def search_wikipedia(self, query: str, lang: str = "vi", max_results: int = 5) -> list[dict[str, str]]:
        """Tìm kiếm Wikipedia."""
        if not HAS_WIKIPEDIA:
            return []
        
        try:
            wikipedia.set_lang(lang)
            results = wikipedia.search(query, results=max_results)
            detailed = []
            for title in results:
                try:
                    page = wikipedia.page(title, auto_suggest=False)
                    summary = page.summary[:500]
                    detailed.append({
                        "title": title,
                        "url": page.url,
                        "summary": summary,
                    })
                except Exception:
                    continue
            return detailed
        except Exception as e:
            logger.warning(f"Wikipedia search error: {e}")
            return []
    
    def get_wikipedia_page(self, title: str, lang: str = "vi") -> MediaResult:
        """Lấy toàn bộ nội dung trang Wikipedia."""
        if not HAS_WIKIPEDIA:
            return MediaResult(False, error="wikipedia package không cài đặt", source_type="wikipedia")
        
        try:
            wikipedia.set_lang(lang)
            page = wikipedia.page(title, auto_suggest=False)
            return MediaResult(
                success=True,
                text=f"# {page.title}\n\n{page.content}",
                source_type="wikipedia",
                source_path=page.url,
                metadata={"title": page.title, "url": page.url, "categories": page.categories}
            )
        except wikipedia.DisambiguationError as e:
            return MediaResult(False, error=f"Trang định danh nhiều nghĩa: {e.options[:5]}", source_type="wikipedia")
        except wikipedia.PageError:
            return MediaResult(False, error="Trang không tồn tại", source_type="wikipedia")
        except Exception as e:
            return MediaResult(False, error=f"Wikipedia error: {e}", source_type="wikipedia")
    
    def wikipedia_search_and_learn(self, query: str, max_pages: int = 3) -> dict[str, Any]:
        """Tìm kiếm Wikipedia và ingest vào KB."""
        results = self.search_wikipedia(query, max_results=max_pages)
        if not results:
            return {"success": False, "error": "Không tìm thấy trang Wikipedia"}
        
        ingested = 0
        for r in results:
            page_result = self.get_wikipedia_page(r["title"])
            if page_result.success:
                kb.ingest_text(page_result.text, f"Wiki: {r['title']}", source_type="wikipedia", source_path=r["url"])
                ingested += 1
        
        return {"success": ingested > 0, "ingested": ingested}
    
    # ========================================================
    # GOOGLE DRIVE
    # ========================================================
    
    def _get_gdrive_service(self):
        """Khởi tạo Google Drive service (cần service account JSON)."""
        if not HAS_GDRIVE:
            return None
        
        creds_path = getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON", None)
        if not creds_path or not os.path.exists(creds_path):
            return None
        
        try:
            creds = Credentials.from_service_account_file(
                creds_path,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.warning(f"GDrive auth error: {e}")
            return None
    
    def extract_gdrive_file(self, file_id_or_url: str) -> MediaResult:
        """Trích xuất file từ Google Drive (doc, sheet, pdf, image)."""
        service = self._get_gdrive_service()
        if not service:
            return MediaResult(False, error="Google Drive API chưa cấu hình", source_type="gdrive")
        
        # Extract file ID from URL or use directly
        file_id = file_id_or_url
        if "drive.google.com" in file_id_or_url:
            parsed = urlparse(file_id_or_url)
            if "/file/d/" in parsed.path:
                file_id = parsed.path.split("/file/d/")[1].split("/")[0]
            elif "id=" in parsed.query:
                file_id = parse_qs(parsed.query).get("id", [file_id])[0]
        
        try:
            # Get file metadata
            file_meta = service.files().get(fileId=file_id, fields="id,name,mimeType,size").execute()
            mime_type = file_meta.get("mimeType", "")
            name = file_meta.get("name", file_id)
            
            # Export Google Docs/Sheets/Slides
            export_mimes = {
                "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            }
            
            if mime_type in export_mimes:
                request = service.files().export_media(fileId=file_id, mimeType=export_mimes[mime_type])
                content = request.execute()
                if mime_type == "application/vnd.google-apps.document":
                    return self.extract_docx_bytes(content)
                else:
                    return MediaResult(False, error=f"Loại file chưa hỗ trợ export: {mime_type}", source_type="gdrive")
            
            # Download binary files
            elif mime_type.startswith("image/"):
                request = service.files().get_media(fileId=file_id)
                content = request.execute()
                return self.ocr_image_bytes(content)
            
            elif mime_type == "application/pdf":
                request = service.files().get_media(fileId=file_id)
                content = request.execute()
                return self.extract_pdf_bytes(content)
            
            else:
                return MediaResult(False, error=f"MIME type chưa hỗ trợ: {mime_type}", source_type="gdrive")
                
        except Exception as e:
            return MediaResult(False, error=f"GDrive error: {e}", source_type="gdrive")
    
    # ========================================================
    # DISCORD ATTACHMENTS
    # ========================================================
    
    async def process_discord_attachment(self, attachment) -> MediaResult:
        """Xử lý attachment từ Discord message."""
        filename = attachment.filename.lower()
        content_type = attachment.content_type or ""
        
        # Download attachment
        try:
            data = await attachment.read()
        except Exception as e:
            return MediaResult(False, error=f"Download attachment failed: {e}", source_type="discord_attachment")
        
        # Image
        if filename.endswith(('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff')) or content_type.startswith('image/'):
            return self.ocr_image_bytes(data)
        
        # PDF
        elif filename.endswith('.pdf') or content_type == 'application/pdf':
            return self.extract_pdf_bytes(data)
        
        # Word
        elif filename.endswith('.docx') or content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            return self.extract_docx_bytes(data)
        
        # Text files
        elif filename.endswith(('.txt', '.md', '.py', '.json', '.yaml', '.yml')) or content_type.startswith('text/'):
            try:
                text = data.decode('utf-8', errors='ignore')
                return MediaResult(True, text=text, source_type="text_file", metadata={"filename": attachment.filename})
            except Exception:
                return MediaResult(False, error="Không decode được text file", source_type="discord_attachment")
        
        return MediaResult(False, error=f"Loại file chưa hỗ trợ: {filename}", source_type="discord_attachment")
    
    # ========================================================
    # UNIFIED PROCESSING
    # ========================================================
    
    async def process_file(self, file_path: str) -> MediaResult:
        """Xử lý file thống nhất theo extension."""
        path = Path(file_path)
        if not path.exists():
            return MediaResult(False, error="File không tồn tại", source_type="file", source_path=file_path)
        
        ext = path.suffix.lower()
        
        if ext in {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}:
            return self.ocr_image(file_path)
        elif ext == '.pdf':
            return self.extract_pdf_text(file_path)
        elif ext == '.docx':
            return self.extract_docx(file_path)
        elif ext in {'.txt', '.md', '.py', '.json', '.yaml', '.yml'}:
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
                return MediaResult(True, text=text, source_type="text", source_path=file_path)
            except Exception as e:
                return MediaResult(False, error=f"Read text error: {e}", source_type="text", source_path=file_path)
        
        return MediaResult(False, error=f"Định dạng không hỗ trợ: {ext}", source_type="file", source_path=file_path)
    
    async def process_url(self, url: str) -> MediaResult:
        """Xử lý URL: Wikipedia, Google Drive, trang web thường."""
        parsed = urlparse(url)
        
        # Wikipedia
        if 'wikipedia.org' in parsed.netloc:
            title_match = re.search(r'/wiki/([^#?]+)', parsed.path)
            if title_match:
                title = urllib.parse.unquote(title_match.group(1)).replace('_', ' ')
                return self.get_wikipedia_page(title)
        
        # Google Drive
        if 'drive.google.com' in parsed.netloc:
            return self.extract_gdrive_file(url)
        
        # Generic web page - fetch and extract text
        return await self.fetch_web_page(url)
    
    async def fetch_web_page(self, url: str) -> MediaResult:
        """Fetch và extract text từ trang web."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as res:
                html = res.read().decode("utf-8", errors="ignore")
            
            # Extract main content
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<aside[^>]*>.*?</aside>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()[:50000]
            
            return MediaResult(True, text=text, source_type="web", source_path=url)
        except Exception as e:
            return MediaResult(False, error=f"Web fetch error: {e}", source_type="web", source_path=url)


# Singleton instance
media_processor = MediaProcessor()

# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

async def process_attachment(attachment) -> MediaResult:
    return await media_processor.process_discord_attachment(attachment)

async def process_file(file_path: str) -> MediaResult:
    return await media_processor.process_file(file_path)

async def process_url(url: str) -> MediaResult:
    return await media_processor.process_url(url)

async def ocr_image(image_path: str, lang: str = "vie+eng") -> MediaResult:
    return media_processor.ocr_image(image_path, lang)

def search_wikipedia(query: str, lang: str = "vi", max_results: int = 5) -> list[dict[str, str]]:
    return media_processor.search_wikipedia(query, lang, max_results)

def get_wikipedia_page(title: str, lang: str = "vi") -> MediaResult:
    return media_processor.get_wikipedia_page(title, lang)

def wikipedia_search_and_learn(query: str, max_pages: int = 3) -> dict[str, Any]:
    return media_processor.wikipedia_search_and_learn(query, max_pages)

def extract_gdrive(file_id_or_url: str) -> MediaResult:
    return media_processor.extract_gdrive_file(file_id_or_url)

async def process_file(file_path: str) -> MediaResult:
    return await media_processor.process_file(file_path)

async def process_url(url: str) -> MediaResult:
    return await media_processor.process_url(url)

async def ocr_image(image_path: str, lang: str = "vie+eng") -> MediaResult:
    return media_processor.ocr_image(image_path, lang)