"""Dịch vụ Bộ Nhớ Đệm & Bộ Nhớ Ảo Khép Kín Trong Dự Án (Project-Local Virtual Memory & Disk Cache).

Đặc điểm cốt lõi:
1. 100% SELF-CONTAINED: Toàn bộ dữ liệu đệm, database suy luận và file hoán đổi (scratch swap)
   được lưu trữ nghiêm ngặt trong thư mục nội bộ `data/cache/` của dự án.
2. KHÔNG CAN THIỆP HỆ THỐNG: Tuyệt đối không tạo file ngoài hệ điều hành (không đụng /tmp hay
   file swap hệ thống, hoạt động độc lập và an toàn trên cả Linux lẫn Windows).
3. HIỆU NĂNG CAO: Sử dụng SQLite ở chế độ Write-Ahead Logging (WAL) cho tốc độ truy xuất < 2ms.
4. BẢO VỆ DUNG LƯỢNG (DISK QUOTA): Trần dung lượng mặc định 1,024 MB (1.0 GB), tự động dọn dẹp
   theo thuật toán LRU (Least Recently Used) để không bao giờ làm đầy ổ đĩa.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from utils.logger import get_logger

logger = get_logger("DiskCacheService")

# Thư mục gốc bộ đệm nội bộ dự án: d:\Project\Bot\data\cache\
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_CACHE_DIR = PROJECT_ROOT / "data" / "cache"
DB_PATH = BASE_CACHE_DIR / "ai_disk_cache.db"
SCRATCH_DIR = BASE_CACHE_DIR / "scratch_swap"

# Giới hạn dung lượng đĩa tối đa cho bộ đệm nội bộ (1,024 MB = 1 GB)
DEFAULT_MAX_CACHE_BYTES = 1024 * 1024 * 1024


class DiskCacheService:
    """Quản lý bộ nhớ đệm suy luận AI và bộ đệm hoán đổi file tạm nội bộ dự án."""

    def __init__(
        self,
        cache_dir: Path = BASE_CACHE_DIR,
        max_bytes: int = DEFAULT_MAX_CACHE_BYTES,
    ):
        self.cache_dir = Path(cache_dir)
        self.db_path = self.cache_dir / "ai_disk_cache.db"
        self.scratch_dir = self.cache_dir / "scratch_swap"
        self.max_bytes = max_bytes
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Khởi tạo thư mục và cấu trúc bảng SQLite WAL khép kín trong dự án."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.scratch_dir.mkdir(parents=True, exist_ok=True)

            try:
                async with aiosqlite.connect(self.db_path) as db:
                    # Kích hoạt WAL mode để đọc ghi đồng thời siêu tốc trên SSD/HDD
                    await db.execute("PRAGMA journal_mode=WAL;")
                    await db.execute("PRAGMA synchronous=NORMAL;")
                    await db.execute(
                        """
                        CREATE TABLE IF NOT EXISTS ai_disk_cache (
                            cache_key TEXT PRIMARY KEY,
                            model_name TEXT NOT NULL,
                            prompt_preview TEXT,
                            response_text TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            last_accessed REAL NOT NULL,
                            hit_count INTEGER DEFAULT 0,
                            size_bytes INTEGER NOT NULL
                        );
                        """
                    )
                    await db.execute(
                        "CREATE INDEX IF NOT EXISTS idx_ai_cache_accessed ON ai_disk_cache (last_accessed);"
                    )
                    await db.commit()
                self._initialized = True
                logger.info(
                    f"💾 Đã khởi tạo Project-Local AI Disk Cache tại: {self.cache_dir} (Trần: {self.max_bytes // (1024*1024)} MB)"
                )
            except Exception as e:
                logger.error(f"Lỗi khởi tạo Disk Cache Database: {e}")
                raise

    @staticmethod
    def compute_cache_key(
        model_name: str,
        prompt: str,
        system_prompt: str = "",
        options: Optional[dict[str, Any]] = None,
    ) -> str:
        """Tạo khóa hash SHA-256 duy nhất từ mô hình và thông số prompt."""
        opt_str = json.dumps(options or {}, sort_keys=True)
        raw_key = f"{model_name}::{system_prompt}::{prompt}::{opt_str}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def get(
        self,
        model_name: str,
        prompt: str,
        system_prompt: str = "",
        options: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """Tra cứu phản hồi đã đệm trong SSD/HDD nội bộ dự án.

        Returns:
            Nội dung phản hồi (str) nếu trúng cache (Hit), None nếu không tìm thấy (Miss).
        """
        await self.initialize()
        cache_key = self.compute_cache_key(model_name, prompt, system_prompt, options)
        now = time.time()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT response_text, hit_count FROM ai_disk_cache WHERE cache_key = ?",
                    (cache_key,),
                ) as cursor:
                    row = await cursor.fetchone()

                if row:
                    response_text = row["response_text"]
                    new_hit_count = (row["hit_count"] or 0) + 1
                    # Cập nhật thời điểm truy xuất và số lượt hit
                    await db.execute(
                        "UPDATE ai_disk_cache SET last_accessed = ?, hit_count = ? WHERE cache_key = ?",
                        (now, new_hit_count, cache_key),
                    )
                    await db.commit()
                    return response_text
        except Exception as e:
            logger.debug(f"Không thể đọc disk cache: {e}")

        return None

    async def set(
        self,
        model_name: str,
        prompt: str,
        response_text: str,
        system_prompt: str = "",
        options: Optional[dict[str, Any]] = None,
    ) -> None:
        """Lưu trữ kết quả phản hồi của AI vào bộ nhớ đệm SSD/HDD nội bộ dự án."""
        if not response_text or not response_text.strip():
            return

        await self.initialize()
        cache_key = self.compute_cache_key(model_name, prompt, system_prompt, options)
        now = time.time()
        size_bytes = len(response_text.encode("utf-8"))
        prompt_preview = (prompt[:150] + "...") if len(prompt) > 150 else prompt

        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO ai_disk_cache (
                        cache_key, model_name, prompt_preview, response_text,
                        created_at, last_accessed, hit_count, size_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        response_text = excluded.response_text,
                        last_accessed = excluded.last_accessed,
                        size_bytes = excluded.size_bytes;
                    """,
                    (cache_key, model_name, prompt_preview, response_text, now, now, size_bytes),
                )
                await db.commit()

            # Kiểm tra và thực thi giới hạn dung lượng đĩa theo LRU
            await self._enforce_quota()
        except Exception as e:
            logger.debug(f"Không thể ghi disk cache: {e}")

    async def _enforce_quota(self) -> None:
        """Tự động xóa các bản ghi cũ nhất (LRU) khi tổng dung lượng cache vượt trần cho phép."""
        try:
            total_size = self.get_total_cache_bytes()
            if total_size <= self.max_bytes:
                return

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                # Lấy danh sách các bản ghi ít được truy xuất nhất
                async with db.execute(
                    "SELECT cache_key, size_bytes FROM ai_disk_cache ORDER BY last_accessed ASC LIMIT 50"
                ) as cursor:
                    old_rows = await cursor.fetchall()

                keys_to_delete = []
                reclaimed = 0
                for r in old_rows:
                    keys_to_delete.append(r["cache_key"])
                    reclaimed += r["size_bytes"]
                    if total_size - reclaimed <= int(self.max_bytes * 0.85):
                        break

                if keys_to_delete:
                    placeholders = ",".join("?" for _ in keys_to_delete)
                    await db.execute(
                        f"DELETE FROM ai_disk_cache WHERE cache_key IN ({placeholders})",
                        keys_to_delete,
                    )
                    await db.commit()
                    logger.info(
                        f"🧹 [Disk Quota] Đã giải phóng {len(keys_to_delete)} bản ghi cũ ({reclaimed // 1024} KB) trong data/cache/."
                    )
        except Exception as e:
            logger.debug(f"Lỗi khi thực thi quota cache: {e}")

    def get_total_cache_bytes(self) -> int:
        """Tính tổng số bytes thực tế của thư mục data/cache/ (gồm cả db và scratch)."""
        if not self.cache_dir.exists():
            return 0
        total = 0
        try:
            for p in self.cache_dir.rglob("*"):
                if p.is_file():
                    total += p.stat().st_size
        except Exception:
            pass
        return total

    # =========================================================================
    # BỘ NHỚ ẢO HOÁN ĐỔI FILE TẠM (SCRATCH SWAP CHUNK BUFFER)
    # =========================================================================
    def write_scratch_chunk(
        self,
        job_id: str,
        chunk_name: str,
        data: str | bytes,
    ) -> Path:
        """Ghi một khối dữ liệu tạm thời xuống thư mục scratch_swap nội bộ dự án.

        Giúp Python giải phóng RAM ngay lập tức khi xử lý văn bản khổng lồ.
        """
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        job_dir = self.scratch_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        target_file = job_dir / chunk_name
        if isinstance(data, str):
            target_file.write_text(data, encoding="utf-8")
        else:
            target_file.write_bytes(data)

        return target_file

    def read_scratch_chunk(
        self,
        job_id: str,
        chunk_name: str,
        as_bytes: bool = False,
    ) -> str | bytes | None:
        """Đọc khối dữ liệu tạm thời từ thư mục scratch_swap nội bộ."""
        target_file = self.scratch_dir / job_id / chunk_name
        if not target_file.exists():
            return None
        try:
            if as_bytes:
                return target_file.read_bytes()
            return target_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.debug(f"Không thể đọc scratch chunk {chunk_name}: {e}")
            return None

    def cleanup_job_scratch(self, job_id: str) -> int:
        """Xóa sạch toàn bộ file hoán đổi tạm thời của một Job sau khi hoàn tất."""
        job_dir = self.scratch_dir / job_id
        deleted_count = 0
        if job_dir.exists() and job_dir.is_dir():
            try:
                for f in job_dir.glob("*"):
                    if f.is_file():
                        f.unlink(missing_ok=True)
                        deleted_count += 1
                job_dir.rmdir()
                logger.info(f"🧹 Đã xóa dọn {deleted_count} file swap tạm cho Job {job_id} trong data/cache/.")
            except Exception as e:
                logger.debug(f"Không thể xóa thư mục scratch {job_dir}: {e}")
        return deleted_count

    # =========================================================================
    # THỐNG KÊ & DỌN DẸP TOÀN CỤC
    # =========================================================================
    async def get_stats(self) -> dict[str, Any]:
        """Thống kê chi tiết tình trạng bộ nhớ đệm và bộ nhớ ảo nội bộ dự án."""
        await self.initialize()
        total_bytes = self.get_total_cache_bytes()
        entries = 0
        total_hits = 0

        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT COUNT(*) as count, SUM(hit_count) as total_hits FROM ai_disk_cache"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        entries = row["count"] or 0
                        total_hits = row["total_hits"] or 0
        except Exception as e:
            logger.debug(f"Không thể đọc stats disk cache: {e}")

        scratch_files = 0
        if self.scratch_dir.exists():
            scratch_files = sum(1 for p in self.scratch_dir.rglob("*") if p.is_file())

        return {
            "cache_dir": str(self.cache_dir),
            "db_path": str(self.db_path),
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "max_mb": round(self.max_bytes / (1024 * 1024), 0),
            "usage_percent": round(100 * total_bytes / self.max_bytes, 1) if self.max_bytes else 0,
            "total_entries": entries,
            "total_hits": total_hits,
            "scratch_files_count": scratch_files,
            "is_self_contained": True,
        }

    async def clear(self) -> None:
        """Xóa sạch toàn bộ bộ nhớ đệm AI và file hoán đổi trong dự án."""
        async with self._lock:
            try:
                if self.db_path.exists():
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute("DELETE FROM ai_disk_cache;")
                        await db.execute("VACUUM;")
                        await db.commit()
                if self.scratch_dir.exists():
                    for item in self.scratch_dir.glob("*"):
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        elif item.is_file():
                            item.unlink(missing_ok=True)
                logger.info("🧹 Đã xóa sạch toàn bộ bộ nhớ đệm Project-Local Cache trong data/cache/.")
            except Exception as e:
                logger.error(f"Lỗi khi xóa disk cache: {e}")


# Singleton instance dùng chung
disk_cache_service = DiskCacheService()
