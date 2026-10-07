"""
services/doc_service.py
Hệ thống Tiếp Nhận, Quét An Toàn, Đệm Ổ Cứng và Phân Loại Môn Học Tự Động cho Đề Thi.
Hỗ trợ: PDF, Word (.docx), Link Google Drive, Link Web học tập.
Tối ưu hóa: Stream trực tiếp xuống ổ cứng, xử lý qua Background Thread (Zero RAM overhead).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import shutil
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

from services.antivirus_scanner import AntivirusScanner, ThreatLevel

log = logging.getLogger(__name__)

TEMP_DOC_DIR = Path("data/doc_temp")
TEMP_DOC_DIR.mkdir(parents=True, exist_ok=True)

# Danh sách phần mở rộng tệp bị cấm / nguy hại
DANGEROUS_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".vbs", ".msi", ".scr", ".jar",
    ".apk", ".com", ".pif", ".reg", ".ps1", ".sh", ".dll",
}

# Danh sách từ khóa phân loại môn học
SUBJECT_KEYWORDS: dict[str, dict[str, Any]] = {
    "Tin Học": {
        "icon": "💻",
        "channel_name": "đề-tin",
        "color": 0x3498DB,
        "keywords": [
            "subtask", "time limit", "memory limit", "c++", "python", "pascal",
            "quy hoạch động", "đồ thị", "cây phân đoạn", "segment tree", "dijkstra",
            "testcase", "mảng", "thuật toán", "algorithm", "competitive programming",
            "stdin", "stdout", "input:", "output:", "ràng buộc", "giới hạn thời gian",
            "bài 1:", "bài 2:", "bài 3:", "codeforces", "vnoi", "tin học trẻ",
            "hsg tin", "olympic tin học", "quicksort", "binary search"
        ],
        "weight": 1.2,
    },
    "Tiếng Anh": {
        "icon": "🇬🇧",
        "channel_name": "đề-anh",
        "color": 0xE74C3C,
        "keywords": [
            "mark the letter a, b, c, or d", "mark the letter a, b, c, d",
            "choose the word whose underlined part", "choose the word that differs from",
            "closest in meaning", "opposite in meaning", "reading comprehension",
            "read the following passage", "which of the following is true",
            "grammatical error", "best combines each pair of sentences",
            "pronunciation", "stress pattern", "vocabulary", "english test",
            "question 1:", "question 2:", "question 3:", "idiom", "phrasal verb"
        ],
        "weight": 1.3,
    },
    "Hóa Học": {
        "icon": "🧪",
        "channel_name": "đề-hóa",
        "color": 0x9B59B6,
        "keywords": [
            "dung dịch", "kết tủa", "phản ứng", "mol", "axit", "bazo", "hóa trị",
            "kim loại", "phi kim", "este", "ancol", "amin", "peptit", "glucozo",
            "điện phân", "oxi hóa", "khử", "phương trình hóa học", "khối lượng mol",
            "h2so4", "hcl", "naoh", "cacl2", "fe", "cu", "al", "khí co2", "h2o",
            "chất rắn", "đồng phân", "nồng độ mol", "hsg hóa", "thpt qg hóa"
        ],
        "weight": 1.2,
    },
    "Sinh Học": {
        "icon": "🧬",
        "channel_name": "đề-sinh",
        "color": 0x2ECC71,
        "keywords": [
            "adn", "arn", "marn", "tarn", "nst", "nhiễm sắc thể", "alen", "gen",
            "quần thể", "tế bào", "nguyên phân", "giảm phân", "đột biến", "di truyền",
            "quang hợp", "hô hấp", "hệ sinh thái", "chuỗi thức ăn", "bậc dinh dưỡng",
            "lai một cặp tính trạng", "menden", "kiểu gen", "kiểu hình", "giao tử",
            "mARN", "enzim", "tARN", "hsg sinh"
        ],
        "weight": 1.2,
    },
    "Toán Học": {
        "icon": "📐",
        "channel_name": "đề-toán",
        "color": 0xF1C40F,
        "keywords": [
            "đạo hàm", "tích phân", "nguyên hàm", "hàm số", "tiệm cận", "cực trị",
            "hình chóp", "hình lăng trụ", "thể tích khối", "tọa độ không gian",
            "vectơ", "mặt phẳng", "phương trình đường thẳng", "nghiệm nguyên",
            "bất đẳng thức", "tam thức bậc hai", "lượng giác", "logarit", "mũ",
            "số phức", "xác suất", "tổ hợp", "chỉnh hợp", "dãy số", "cấp số cộng",
            "hsg toán", "olympic toán"
        ],
        "weight": 1.1,
    },
    "Vật Lý": {
        "icon": "⚡",
        "channel_name": "đề-lý",
        "color": 0xE67E22,
        "keywords": [
            "dao động điều hòa", "con lắc đơn", "con lắc lò xo", "sóng cơ",
            "giao thoa sóng", "sóng âm", "dòng điện xoay chiều", "mạch rlc",
            "cảm ứng điện từ", "quang học", "thấu kính", "vận tốc", "gia tốc",
            "lực ma sát", "công suất", "tần số", "chu kỳ", "bước sóng",
            "tụ điện", "cuộn cảm", "hạt nhân", "phóng xạ", "hsg lý"
        ],
        "weight": 1.1,
    },
    "Ngữ Văn": {
        "icon": "📜",
        "channel_name": "đề-văn",
        "color": 0x1ABC9C,
        "keywords": [
            "đọc hiểu văn bản", "nghị luận xã hội", "nghị luận văn học", "tác giả",
            "tác phẩm", "nhân vật", "đoạn trích", "thông điệp rút ra", "cảm nhận của anh/chị",
            "phân tích vẻ đẹp", "bài thơ", "truyện ngắn", "nghệ thuật", "ngữ liệu",
            "ngữ văn", "hsg văn"
        ],
        "weight": 1.2,
    },
    "Lịch Sử & Địa Lý": {
        "icon": "🌍",
        "channel_name": "đề-sử-địa",
        "color": 0xD35400,
        "keywords": [
            "chiến dịch", "cách mạng tháng tám", "kháng chiến", "hiệp định",
            "thực dân", "đế quốc", "địa hình", "khí hậu", "sông ngòi", "đồng bằng",
            "khoáng sản", "dân số", "chuyển dịch cơ cấu", "kinh tế vùng", "biển đảo"
        ],
        "weight": 1.1,
    },
}


@dataclass
class DocumentAnalysisResult:
    is_safe: bool
    subject: str
    icon: str
    channel_name: str
    color: int
    title: str
    summary: str
    estimated_level: str
    question_count: int
    page_count: int
    file_type: str
    file_path: str | None = None
    original_url: str | None = None
    file_size_mb: float = 0.0
    error_message: str | None = None


class DocumentService:
    """Dịch vụ xử lý tài liệu, kiểm tra an toàn và phân loại môn học."""

    @staticmethod
    def is_safe_url(url_str: str) -> tuple[bool, str]:
        """Kiểm tra URL an toàn: chống SSRF, cấm IP private, cấm extension độc hại."""
        try:
            parsed = urllib.parse.urlparse(url_str.strip())
            if parsed.scheme not in ("http", "https"):
                return False, "Chỉ hỗ trợ đường dẫn http:// hoặc https://"

            hostname = parsed.hostname
            if not hostname:
                return False, "Địa chỉ web không hợp lệ"

            # Kiểm tra IP Private / Localhost
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
                    return False, "Không được phép truy cập địa chỉ IP nội bộ / private"
            except ValueError:
                if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
                    return False, "Không được phép truy cập localhost"

            # Kiểm tra extension trong URL
            path_lower = parsed.path.lower()
            for ext in DANGEROUS_EXTENSIONS:
                if path_lower.endswith(ext):
                    return False, f"Liên kết chứa tệp thực thi/nguy hại không an toàn ({ext})"

            return True, "URL An Toàn"
        except Exception as e:
            return False, f"Lỗi kiểm tra URL: {e}"

    @classmethod
    async def download_to_disk(
        cls, url_or_attachment: str, filename_hint: str = "document"
    ) -> tuple[Path | None, float, str | None]:
        """Tải file dạng chunked stream trực tiếp xuống ổ cứng (data/doc_temp/), không tốn RAM."""
        ext = os.path.splitext(filename_hint)[1].lower()
        if not ext:
            if "drive.google.com" in url_or_attachment or "docs.google.com" in url_or_attachment:
                ext = ".pdf"
            else:
                ext = ".tmp"

        temp_file = TEMP_DOC_DIR / f"doc_{int(time.time())}_{os.urandom(4).hex()}{ext}"

        # Xử lý link Google Drive download
        target_url = url_or_attachment
        if "drive.google.com" in url_or_attachment:
            file_id_match = re.search(r"/d/([a-zA-Z0-9_-]+)", url_or_attachment)
            if not file_id_match:
                file_id_match = re.search(r"id=([a-zA-Z0-9_-]+)", url_or_attachment)
            if file_id_match:
                file_id = file_id_match.group(1)
                target_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        try:
            timeout = aiohttp.ClientTimeout(total=60, sock_read=30)
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(target_url, headers=headers, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return None, 0.0, f"Không thể tải tệp (Mã phản hồi HTTP {resp.status})"

                    total_bytes = 0
                    with open(temp_file, "wb") as f:
                        async for chunk in resp.content.iter_chunked(65536):
                            f.write(chunk)
                            total_bytes += len(chunk)
                            if total_bytes > 100 * 1024 * 1024:  # Giới hạn 100MB
                                return None, 0.0, "Kích thước tệp vượt quá giới hạn 100MB"

            size_mb = total_bytes / (1024 * 1024)
            return temp_file, size_mb, None
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            return None, 0.0, f"Lỗi khi tải tệp xuống ổ cứng: {e}"

    @classmethod
    def _extract_text_from_file_sync(cls, file_path: Path) -> tuple[str, int, str]:
        """Trích xuất text từ tệp trên ổ cứng trong ThreadPool."""
        ext = file_path.suffix.lower()
        extracted_text = ""
        page_count = 1
        file_type = ext.upper().replace(".", "")

        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(file_path)
                page_count = len(doc)
                # Đọc 1-3 trang đầu tiên
                pages_to_read = min(3, page_count)
                for i in range(pages_to_read):
                    extracted_text += doc[i].get_text() + "\n"
                doc.close()
            except Exception:
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(file_path))
                    page_count = len(reader.pages)
                    pages_to_read = min(3, page_count)
                    for i in range(pages_to_read):
                        extracted_text += (reader.pages[i].extract_text() or "") + "\n"
                except Exception as e:
                    extracted_text = f"Lỗi đọc PDF: {e}"

        elif ext in (".docx", ".doc"):
            try:
                import docx
                doc = docx.Document(file_path)
                paras = [p.text for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n".join(paras[:50])
                page_count = max(1, len(paras) // 10)
            except Exception as e:
                extracted_text = f"Lỗi đọc Word: {e}"

        elif ext in (".txt", ".py", ".cpp", ".c", ".java", ".json", ".md"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    extracted_text = f.read(5000)
            except Exception as e:
                extracted_text = f"Lỗi đọc text: {e}"

        return extracted_text, page_count, file_type

    @classmethod
    async def extract_text_from_file(cls, file_path: Path) -> tuple[str, int, str]:
        """Bọc hàm trích xuất text trong asyncio.to_thread để không chặn Event Loop."""
        return await asyncio.to_thread(cls._extract_text_from_file_sync, file_path)

    @classmethod
    async def fetch_web_page_text(cls, url: str) -> tuple[str, str]:
        """Tải và trích xuất nội dung văn bản từ một trang web học tập."""
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return "", f"HTTP {resp.status}"
                    html = await resp.text(errors="ignore")

            title_m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_m.group(1).strip() if title_m else "Web Document"

            # Bỏ tag HTML
            clean_text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<style.*?</style>", " ", clean_text, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<[^>]+>", " ", clean_text)
            clean_text = " ".join(clean_text.split())[:4000]

            return clean_text, title
        except Exception as e:
            return "", str(e)

    @classmethod
    def classify_subject(cls, text: str, title_hint: str = "") -> dict[str, Any]:
        """Phân loại môn học dựa trên tần suất từ khóa trọng số và phân tích ngữ nghĩa."""
        combined_text = (title_hint + " " + text).lower()

        scores: dict[str, float] = {}
        for subject, info in SUBJECT_KEYWORDS.items():
            score = 0.0
            for kw in info["keywords"]:
                count = combined_text.count(kw.lower())
                if count > 0:
                    score += count * info["weight"]
            scores[subject] = score

        best_subject = max(scores, key=scores.get) if scores else "Tin Học"
        best_score = scores.get(best_subject, 0.0)

        # Nếu điểm quá thấp hoặc không khớp, fallback kiểm tra tiếng Anh
        if best_score < 2.0:
            words = re.findall(r"\b[a-zA-Z]+\b", text)
            if len(words) > 50:
                best_subject = "Tiếng Anh"
            else:
                best_subject = "Tổng Hợp / Khác"

        # Dự đoán cấp độ
        level = "THPT / Luyện Thi"
        if any(w in combined_text for w in ["olympic", "vnoi", "quốc gia", "hsgqg", "vnoi cup"]):
            level = "🏆 Olympic / HSG Quốc Gia"
        elif any(w in combined_text for w in ["hsg tỉnh", "chuyên", "hsg"]):
            level = "🥇 Học Sinh Giỏi (HSG Tỉnh/Thành phố)"
        elif any(w in combined_text for w in ["thpt quốc gia", "thpt qg", "thi thử tốt nghiệp"]):
            level = "🎓 Luyện Thi Tốt Nghiệp THPT"
        elif any(w in combined_text for w in ["lớp 10", "lớp 11", "lớp 12"]):
            level = "📚 Ôn Tập Kiểm Tra Theo Khối"

        # Đếm số câu hỏi (ví dụ: Câu 1, Bài 1, Question 1)
        q_matches = re.findall(r"(?:câu|bài|question)\s+(\d+)", combined_text)
        question_count = len(set(q_matches)) if q_matches else 0

        subj_info = SUBJECT_KEYWORDS.get(best_subject, {
            "icon": "📚",
            "channel_name": "đề-tổng-hợp",
            "color": 0x34495E,
        })

        return {
            "subject": best_subject,
            "icon": subj_info["icon"],
            "channel_name": subj_info["channel_name"],
            "color": subj_info["color"],
            "level": level,
            "question_count": question_count,
            "score": best_score,
        }

    @classmethod
    async def process_document(
        cls,
        url_or_file: str,
        filename_hint: str = "document",
        is_web_url: bool = False,
    ) -> DocumentAnalysisResult:
        """Xử lý toàn diện tài liệu: Tải ổ cứng -> Trích xuất -> Phân loại -> Trả về kết quả."""
        # 1. Kiểm tra an toàn URL nếu là link
        if is_web_url or url_or_file.startswith("http"):
            url_scan = await AntivirusScanner.scan_url(url_or_file, check_probe=False)
            if not url_scan.is_safe:
                return DocumentAnalysisResult(
                    is_safe=False,
                    subject="Không an toàn",
                    icon="🚫",
                    channel_name="canh-bao",
                    color=0xE74C3C,
                    title=f"Cảnh báo: {url_scan.threat_name}",
                    summary=f"Liên kết bị chặn vì lý do an ninh: {url_scan.summary}",
                    estimated_level="N/A",
                    question_count=0,
                    page_count=0,
                    file_type="UNKNOWN",
                    error_message=url_scan.threat_name,
                )

        temp_path: Path | None = None
        extracted_text = ""
        page_count = 1
        file_type = "WEB"
        file_size_mb = 0.0
        title_hint = filename_hint

        # 2. Xử lý tải xuống ổ cứng nếu là file hoặc Google Drive
        if not is_web_url or "drive.google.com" in url_or_file or "docs.google.com" in url_or_file:
            temp_path, file_size_mb, err = await cls.download_to_disk(url_or_file, filename_hint)
            if err or not temp_path:
                return DocumentAnalysisResult(
                    is_safe=False,
                    subject="Lỗi tải tệp",
                    icon="❌",
                    channel_name="loi",
                    color=0xE74C3C,
                    title="Không thể tải tài liệu",
                    summary=f"Lỗi: {err or 'Không thể lưu tệp xuống ổ cứng'}",
                    estimated_level="N/A",
                    question_count=0,
                    page_count=0,
                    file_type="UNKNOWN",
                    error_message=err,
                )

            # Quét sâu chữ ký nhị phân, magic bytes, macro & exploit tệp tải về
            file_scan = await AntivirusScanner.scan_file_path(temp_path, filename_hint)
            if not file_scan.is_safe:
                cls.cleanup_file(str(temp_path))
                return DocumentAnalysisResult(
                    is_safe=False,
                    subject="Mã độc bị chặn",
                    icon="🚫",
                    channel_name="canh-bao",
                    color=0xE74C3C,
                    title=f"Phát hiện mối đe dọa: {file_scan.threat_name}",
                    summary=file_scan.summary,
                    estimated_level="N/A",
                    question_count=0,
                    page_count=0,
                    file_type="MALICIOUS",
                    error_message=f"{file_scan.threat_name} (SHA-256: {file_scan.sha256[:12] if file_scan.sha256 else 'N/A'})",
                )

            extracted_text, page_count, file_type = await cls.extract_text_from_file(temp_path)
        else:
            # Là trang web HTML thông thường
            extracted_text, title_hint = await cls.fetch_web_page_text(url_or_file)
            file_type = "WEB URL"

        # 3. Phân loại môn học
        classification = cls.classify_subject(extracted_text, title_hint)

        # 4. Trích xuất tên đề
        title = title_hint
        first_lines = [line.strip() for line in extracted_text.splitlines() if len(line.strip()) > 5]
        if first_lines:
            for l in first_lines[:3]:
                if any(w in l.lower() for w in ["đề", "kỳ thi", "kiểm tra", "test", "bài tập", "olympic", "hsg"]):
                    title = l[:100]
                    break

        summary_snip = extracted_text.replace("\n", " ").strip()[:300]
        if len(summary_snip) >= 300:
            summary_snip += "..."

        return DocumentAnalysisResult(
            is_safe=True,
            subject=classification["subject"],
            icon=classification["icon"],
            channel_name=classification["channel_name"],
            color=classification["color"],
            title=title,
            summary=summary_snip or "Không có văn bản tóm tắt trích xuất được.",
            estimated_level=classification["level"],
            question_count=classification["question_count"],
            page_count=page_count,
            file_type=file_type,
            file_path=str(temp_path) if temp_path else None,
            original_url=url_or_file if url_or_file.startswith("http") else None,
            file_size_mb=file_size_mb,
        )

    @staticmethod
    def cleanup_file(file_path: str | None) -> None:
        """Xóa an toàn tệp tạm sau khi đã đăng lên Discord."""
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log.warning(f"Không thể xóa file tạm {file_path}: {e}")
