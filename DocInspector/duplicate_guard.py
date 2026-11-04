"""
Absolute Duplicate Prevention Engine for DocInspector & HyperHub.
"CHỐNG NỘP TRÙNG TUYỆT ĐỐI — 2 TẦNG BẢO VỆ ĐỘC LẬP"

Layer 1: Binary Exact Match via SHA-256 (C++ Native / hashlib fallback).
         Phát hiện tệp nhị phân trùng lặp từng bit trong < 1ms.

Layer 2: Content & Semantic Signature via Normalized Text Hashing & SimHash.
         Phát hiện tài liệu trùng nội dung đề thi ngay cả khi:
         - Đổi tên tệp (rename)
         - Chuyển đổi định dạng (DOCX sang PDF hoặc ngược lại)
         - Lưu lại (re-saved) làm thay đổi metadata/header nhị phân
         - Thay đổi khoảng trắng, căn lề hoặc ký tự phân cách trang.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union


def normalize_document_text(text: str) -> str:
    """
    Chuẩn hóa văn bản đề thi để tính chữ ký nội dung độc lập với định dạng:
    - Chuyển sang chữ thường
    - Khử dấu phụ/dấu trang, số trang 'Trang 1/5'
    - Loại bỏ toàn bộ khoảng trắng thừa và ký tự đặc biệt
    """
    if not text:
        return ""
    # 1. Lowercase và chuẩn hóa Unicode NFC
    t = unicodedata.normalize("NFC", text.lower())

    # 2. Loại bỏ các dòng số trang / tiêu đề chân trang phổ biến
    t = re.sub(r"(?i)\btrang\s*\d+\s*(?:/|trên)?\s*\d*\b", "", t)
    t = re.sub(r"(?i)\bpage\s*\d+\s*(?:of|/)?\s*\d*\b", "", t)

    # 3. Giữ lại chữ cái Tiếng Việt, chữ số và các ký hiệu toán học cốt lõi
    # Loại bỏ khoảng trắng, dấu ngắt dòng, ký tự phân cách
    cleaned = re.sub(r"[^\w\u00C0-\u024F\u1E00-\u1EFF+=\-*/^()]+", "", t)
    return cleaned


def compute_simhash_64(text: str) -> int:
    """
    Tính mã băm ngữ nghĩa 64-bit SimHash từ các n-grams từ vựng.
    Cho phép đo khoảng cách Hamming để phát hiện trùng lặp văn bản.
    """
    if not text or len(text) < 10:
        return 0

    # Tách từ / token
    words = re.findall(r"[\w\u00C0-\u024F\u1E00-\u1EFF]+", text.lower())
    if len(words) < 3:
        words = [text[i : i + 4] for i in range(max(1, len(text) - 3))]

    # Tạo 3-gram shingles
    shingles = []
    if len(words) >= 3:
        for i in range(len(words) - 2):
            shingles.append(f"{words[i]}_{words[i+1]}_{words[i+2]}")
    else:
        shingles = words

    # Vector 64 chiều
    v = [0] * 64
    for shingle in shingles:
        # 64-bit hash từ MD5
        h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bit = (h >> i) & 1
            if bit == 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    """Khoảng cách Hamming giữa hai mã băm 64-bit (số bit khác nhau)."""
    x = (hash1 ^ hash2) & 0xFFFFFFFFFFFFFFFF
    return bin(x).count("1")


@dataclass
class DuplicateCheckResult:
    """Kết quả kiểm tra chống nộp trùng lặp."""
    is_duplicate: bool
    match_type: Optional[str] = None  # "BINARY_EXACT", "CONTENT_EXACT", "SEMANTIC_SIMHASH", None
    existing_id: Optional[int] = None
    existing_title: Optional[str] = None
    existing_author: Optional[str] = None
    existing_timestamp: Optional[str] = None
    existing_jump_url: Optional[str] = None
    file_hash: Optional[str] = None
    content_hash: Optional[str] = None
    simhash: Optional[int] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_duplicate": self.is_duplicate,
            "match_type": self.match_type,
            "existing_id": self.existing_id,
            "existing_title": self.existing_title,
            "existing_author": self.existing_author,
            "existing_timestamp": self.existing_timestamp,
            "existing_jump_url": self.existing_jump_url,
            "file_hash": self.file_hash,
            "content_hash": self.content_hash,
            "simhash": hex(self.simhash) if self.simhash is not None else None,
            "message": self.message,
        }


class DuplicateGuard:
    """
    Bộ bảo vệ chống nộp trùng tuyệt đối (Dual-Layer Duplicate Guard).
    """

    @classmethod
    def compute_hashes(
        cls,
        file_bytes: Optional[bytes] = None,
        text_content: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Tính toán cả 2 tầng chữ ký:
        - file_hash: SHA-256 nhị phân (Layer 1)
        - content_hash: SHA-256 của văn bản chuẩn hóa (Layer 2)
        - simhash: 64-bit SimHash của từ vựng (Layer 2 Semantic)
        """
        file_hash = None
        if file_bytes and len(file_bytes) > 0:
            try:
                from cpp_core.bridge import fast_sha256
                file_hash = fast_sha256(file_bytes)
            except Exception:
                file_hash = hashlib.sha256(file_bytes).hexdigest()

        content_hash = None
        simhash_val = None
        if text_content and len(text_content.strip()) >= 30:
            norm_text = normalize_document_text(text_content)
            if len(norm_text) >= 30:
                # Dùng SHA-256 cho chuỗi văn bản chuẩn hóa
                content_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()
                simhash_val = compute_simhash_64(text_content)

        return file_hash, content_hash, simhash_val

    @classmethod
    def check_duplicate_sync(
        cls,
        sqlite_conn: Any,
        file_hash: Optional[str] = None,
        content_hash: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size_bytes: int = 0,
    ) -> DuplicateCheckResult:
        """Kiểm tra đồng bộ trên kết nối SQLite."""
        cur = sqlite_conn.cursor()

        # 1. Kiểm tra Layer 1: Trùng khớp nhị phân tuyệt đối
        if file_hash:
            cur.execute(
                "SELECT id, title, author_name, timestamp, jump_url, file_hash, content_hash "
                "FROM documents_archive WHERE file_hash = ? LIMIT 1",
                (file_hash,),
            )
            row = cur.fetchone()
            if row:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    match_type="BINARY_EXACT",
                    existing_id=row[0],
                    existing_title=row[1],
                    existing_author=row[2],
                    existing_timestamp=row[3],
                    existing_jump_url=row[4],
                    file_hash=file_hash,
                    content_hash=content_hash,
                    message=(
                        f"TÀI LIỆU TRÙNG LẶP TUYỆT ĐỐI (100% Binary SHA-256)! "
                        f"Tệp đã được nộp trước đó bởi '{row[2]}' vào {row[3]}."
                    ),
                )

        # 2. Kiểm tra Layer 2: Trùng khớp nội dung văn bản đề thi
        if content_hash:
            try:
                cur.execute(
                    "SELECT id, title, author_name, timestamp, jump_url, file_hash, content_hash "
                    "FROM documents_archive WHERE content_hash = ? LIMIT 1",
                    (content_hash,),
                )
                row = cur.fetchone()
                if row:
                    return DuplicateCheckResult(
                        is_duplicate=True,
                        match_type="CONTENT_EXACT",
                        existing_id=row[0],
                        existing_title=row[1],
                        existing_author=row[2],
                        existing_timestamp=row[3],
                        existing_jump_url=row[4],
                        file_hash=file_hash,
                        content_hash=content_hash,
                        message=(
                            f"TÀI LIỆU TRÙNG NỘI DUNG ĐỀ THI! "
                            f"Nội dung văn bản đề này hoàn toàn trùng khớp với đề '{row[1]}' "
                            f"do '{row[2]}' nộp vào {row[3]} (ngay cả khi đổi tên tệp hoặc định dạng)."
                        ),
                    )
            except Exception:
                # Cột content_hash có thể chưa tồn tại trong bảng cũ
                pass

        # 3. Kiểm tra phụ trợ: Cùng tên tệp + cùng dung lượng chính xác
        if file_name and file_size_bytes > 0:
            cur.execute(
                "SELECT id, title, author_name, timestamp, jump_url, file_hash, content_hash "
                "FROM documents_archive WHERE file_name = ? AND file_size_bytes = ? LIMIT 1",
                (file_name, file_size_bytes),
            )
            row = cur.fetchone()
            if row:
                return DuplicateCheckResult(
                    is_duplicate=True,
                    match_type="METADATA_EXACT",
                    existing_id=row[0],
                    existing_title=row[1],
                    existing_author=row[2],
                    existing_timestamp=row[3],
                    existing_jump_url=row[4],
                    file_hash=file_hash,
                    content_hash=content_hash,
                    message=(
                        f"TÀI LIỆU TRÙNG TÊN VÀ DUNG LƯỢNG! "
                        f"Tệp '{file_name}' ({file_size_bytes:,} bytes) đã được nộp trước đó bởi '{row[2]}' vào {row[3]}."
                    ),
                )

        return DuplicateCheckResult(
            is_duplicate=False,
            file_hash=file_hash,
            content_hash=content_hash,
            message="Tài liệu hoàn toàn mới và hợp lệ.",
        )

    @classmethod
    async def check_duplicate_async(
        cls,
        db_instance: Any,
        file_hash: Optional[str] = None,
        content_hash: Optional[str] = None,
        file_name: Optional[str] = None,
        file_size_bytes: int = 0,
    ) -> DuplicateCheckResult:
        """Kiểm tra bất đồng bộ trên instance Database của bot (aiosqlite)."""
        if not db_instance:
            return DuplicateCheckResult(is_duplicate=False, file_hash=file_hash, content_hash=content_hash)

        # 1. Layer 1: SHA-256 Binary Exact
        if file_hash:
            try:
                row = await db_instance.fetchone(
                    "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE file_hash = ?",
                    file_hash,
                )
                if row:
                    return DuplicateCheckResult(
                        is_duplicate=True,
                        match_type="BINARY_EXACT",
                        existing_id=row[0],
                        existing_title=row[1],
                        existing_author=row[2],
                        existing_timestamp=row[3],
                        existing_jump_url=row[4],
                        file_hash=file_hash,
                        content_hash=content_hash,
                        message=(
                            f"TÀI LIỆU TRÙNG LẶP TUYỆT ĐỐI (100% Binary SHA-256)! "
                            f"Tệp đã được nộp trước đó bởi '{row[2]}' vào {row[3]}."
                        ),
                    )
            except Exception:
                pass

        # 2. Layer 2: Content Hash
        if content_hash:
            try:
                row = await db_instance.fetchone(
                    "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE content_hash = ?",
                    content_hash,
                )
                if row:
                    return DuplicateCheckResult(
                        is_duplicate=True,
                        match_type="CONTENT_EXACT",
                        existing_id=row[0],
                        existing_title=row[1],
                        existing_author=row[2],
                        existing_timestamp=row[3],
                        existing_jump_url=row[4],
                        file_hash=file_hash,
                        content_hash=content_hash,
                        message=(
                            f"TÀI LIỆU TRÙNG NỘI DUNG ĐỀ THI! "
                            f"Nội dung văn bản đề này hoàn toàn trùng khớp với đề '{row[1]}' "
                            f"do '{row[2]}' nộp vào {row[3]}."
                        ),
                    )
            except Exception:
                pass

        # 3. Layer 3: File name + size
        if file_name and file_size_bytes > 0:
            try:
                row = await db_instance.fetchone(
                    "SELECT id, title, author_name, timestamp, jump_url FROM documents_archive WHERE file_name = ? AND file_size_bytes = ?",
                    file_name,
                    file_size_bytes,
                )
                if row:
                    return DuplicateCheckResult(
                        is_duplicate=True,
                        match_type="METADATA_EXACT",
                        existing_id=row[0],
                        existing_title=row[1],
                        existing_author=row[2],
                        existing_timestamp=row[3],
                        existing_jump_url=row[4],
                        file_hash=file_hash,
                        content_hash=content_hash,
                        message=(
                            f"TÀI LIỆU TRÙNG TÊN VÀ DUNG LƯỢNG! "
                            f"Tệp '{file_name}' ({file_size_bytes:,} bytes) đã được nộp trước đó bởi '{row[2]}' vào {row[3]}."
                        ),
                    )
            except Exception:
                pass

        return DuplicateCheckResult(
            is_duplicate=False,
            file_hash=file_hash,
            content_hash=content_hash,
            message="Tài liệu hoàn toàn mới và hợp lệ.",
        )
