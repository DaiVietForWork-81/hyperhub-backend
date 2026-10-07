"""
services/backup_service.py
Dịch vụ tự động Sao lưu (Backup) và Khôi phục (Self-Healing Restore) Cơ sở dữ liệu bot.db và Kho đề thi.
- Sao lưu an toàn vào thư mục backups/ trong project (giữ 10 bản mới nhất).
- Tự động tải lên kênh Discord chỉ định (ID: 1544356764240183358).
- Tự động quét và khôi phục CSDL từ kênh Discord nếu bot bị mất dữ liệu lúc khởi động.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Optional

import discord
from discord.ext import commands

from config.settings import settings

logger = logging.getLogger("BackupService")

BACKUP_CHANNEL_ID = 1544356764240183358
PROJECT_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
BACKUP_DIR = PROJECT_ROOT / "backups"
PRIMARY_DB_PATH = PROJECT_ROOT / "bot.db"
SECONDARY_DB_PATH = PROJECT_ROOT / "data" / "bot.db"
PROBLEMS_JSON_PATH = PROJECT_ROOT / "data" / "ai_problems.json"
MAX_LOCAL_BACKUPS = 10


def compute_sha256(file_path: Path) -> str:
    """Tính mã băm SHA256 của file."""
    if not file_path.exists():
        return ""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_db_stats(db_path: Path) -> dict[str, Any]:
    """Đọc nhanh số lượng bản ghi chính từ CSDL SQLite."""
    stats = {"users": 0, "matches": 0, "submissions": 0}
    if not db_path.exists() or db_path.stat().st_size == 0:
        return stats
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        for tbl, key in [("users", "users"), ("duel_matches", "matches"), ("submissions", "submissions")]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                row = cursor.fetchone()
                if row:
                    stats[key] = row[0]
            except Exception:
                pass
        conn.close()
    except Exception as e:
        logger.warning(f"Lỗi đọc DB stats: {e}")
    return stats


class DatabaseBackupService:
    """Quản lý sao lưu định kỳ và khôi phục CSDL cho bot."""

    def __init__(self, channel_id: int = BACKUP_CHANNEL_ID):
        self.channel_id = channel_id
        self._backup_task: asyncio.Task | None = None
        self._loop_running: bool = False
        self._backup_lock: asyncio.Lock = asyncio.Lock()
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    def create_local_backup(self) -> tuple[Path, dict[str, Any]]:
        """
        Nén bot.db và ai_problems.json vào file zip an toàn.
        Sử dụng SQLite Online Backup API để tránh xung đột WAL mode.
        """
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_path = BACKUP_DIR / f"bot_backup_{timestamp}.zip"
        temp_db_path = BACKUP_DIR / f"temp_backup_{timestamp}.db"

        # 1. Snapshot SQLite bằng Backup API nếu DB tồn tại
        db_source = PRIMARY_DB_PATH if PRIMARY_DB_PATH.exists() else SECONDARY_DB_PATH
        if db_source.exists() and db_source.stat().st_size > 0:
            try:
                src_conn = sqlite3.connect(f"file:{db_source}?mode=ro", uri=True)
                dst_conn = sqlite3.connect(temp_db_path)
                src_conn.backup(dst_conn)
                dst_conn.close()
                src_conn.close()
            except Exception as e:
                logger.warning(f"Không thể dùng sqlite backup API: {e}, fallback copy thông thường")
                shutil.copy2(db_source, temp_db_path)
        else:
            logger.warning(f"Không tìm thấy file CSDL nguồn tại {db_source}")

        # 2. Đóng gói vào Zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if temp_db_path.exists():
                zf.write(temp_db_path, arcname="bot.db")
            if PROBLEMS_JSON_PATH.exists():
                zf.write(PROBLEMS_JSON_PATH, arcname="ai_problems.json")

        # Xóa temp db snapshot
        if temp_db_path.exists():
            try:
                temp_db_path.unlink()
            except Exception:
                pass

        # 3. Dọn dẹp giữ tối đa 10 bản backup cục bộ
        self._rotate_local_backups()

        # 4. Thu thập Metadata
        db_stats = get_db_stats(db_source) if db_source.exists() else {}
        prob_count = 0
        if PROBLEMS_JSON_PATH.exists():
            try:
                with open(PROBLEMS_JSON_PATH, "r", encoding="utf-8") as pf:
                    probs = json.load(pf)
                    prob_count = len(probs)
            except Exception:
                pass

        meta = {
            "timestamp": timestamp,
            "zip_path": str(zip_path),
            "size_bytes": zip_path.stat().st_size if zip_path.exists() else 0,
            "sha256": compute_sha256(zip_path),
            "user_count": db_stats.get("users", 0),
            "match_count": db_stats.get("matches", 0),
            "prob_count": prob_count,
        }
        logger.info(f"Đã tạo bản sao lưu cục bộ: {zip_path.name} ({meta['size_bytes'] / 1024:.1f} KB)")
        return zip_path, meta

    def _rotate_local_backups(self) -> None:
        """Giữ tối đa MAX_LOCAL_BACKUPS file zip mới nhất trong thư mục backups."""
        try:
            backups = sorted(
                [f for f in BACKUP_DIR.glob("bot_backup_*.zip") if f.is_file()],
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )
            for old_f in backups[MAX_LOCAL_BACKUPS:]:
                try:
                    old_f.unlink()
                    logger.info(f"Đã dọn dẹp bản sao lưu cũ: {old_f.name}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Lỗi xoay vòng bản sao lưu: {e}")

    async def upload_backup_to_discord(
        self, bot: commands.Bot, channel_id: int | None = None
    ) -> bool:
        """Tạo bản sao lưu cục bộ (Đã bỏ tải lên kênh Discord theo yêu cầu)."""
        async with self._backup_lock:
            zip_path, meta = await asyncio.to_thread(self.create_local_backup)
            return zip_path.exists()

    async def restore_latest_from_discord(
        self, bot: commands.Bot, channel_id: int | None = None
    ) -> bool:
        """
        Quét kênh Discord để tìm bản backup .zip mới nhất và tự động khôi phục.
        Được gọi tự động khi CSDL bị mất hoặc hỏng.
        """
        target_cid = channel_id or self.channel_id
        channel = bot.get_channel(target_cid)
        if not channel:
            try:
                channel = await bot.fetch_channel(target_cid)
            except Exception as e:
                logger.error(f"Không thể truy cập kênh backup {target_cid} để khôi phục: {e}")
                return False

        logger.info(f"Đang quét kênh #{channel.name} để tìm bản sao lưu CSDL mới nhất...")
        target_att: discord.Attachment | None = None
        target_msg: discord.Message | None = None

        try:
            async for msg in channel.history(limit=50):
                for att in msg.attachments:
                    if att.filename.endswith(".zip") and "backup" in att.filename.lower():
                        target_att = att
                        target_msg = msg
                        break
                if target_att:
                    break
        except Exception as e:
            logger.error(f"Lỗi khi đọc lịch sử tin nhắn kênh backup: {e}")
            return False

        if not target_att:
            logger.warning("Không tìm thấy file sao lưu .zip nào trong kênh Discord.")
            return False

        # Tải file backup về thư mục backups/
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        download_path = BACKUP_DIR / f"downloaded_{target_att.filename}"
        try:
            await target_att.save(str(download_path))
            logger.info(f"Đã tải bản backup từ Discord: {download_path.name} ({target_att.size} bytes)")
        except Exception as e:
            logger.error(f"Không thể tải file backup: {e}")
            return False

        # Giải nén và khôi phục các tệp
        success = False
        try:
            with zipfile.ZipFile(download_path, "r") as zf:
                namelist = zf.namelist()
                if "bot.db" in namelist:
                    zf.extract("bot.db", path=PROJECT_ROOT)
                    if SECONDARY_DB_PATH.parent.exists():
                        shutil.copy2(PRIMARY_DB_PATH, SECONDARY_DB_PATH)
                    logger.info("✅ Đã khôi phục thành công bot.db vào project root!")
                    success = True
                if "ai_problems.json" in namelist:
                    PROBLEMS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
                    zf.extract("ai_problems.json", path=PROBLEMS_JSON_PATH.parent)
                    logger.info("✅ Đã khôi phục thành công kho đề ai_problems.json!")
                    success = True

            # Kiểm tra tính toàn vẹn SQLite
            if PRIMARY_DB_PATH.exists():
                test_conn = sqlite3.connect(PRIMARY_DB_PATH)
                check = test_conn.execute("PRAGMA integrity_check").fetchone()
                test_conn.close()
                if check and check[0] == "ok":
                    logger.info("✨ Kiểm tra tính toàn vẹn SQLite CSDL sau khôi phục: OK 100%!")
                else:
                    logger.warning(f"Cảnh báo integrity check SQLite: {check}")
        except Exception as e:
            logger.error(f"Lỗi giải nén và khôi phục CSDL: {e}", exc_info=True)
            return False

        return success

    async def start_backup_loop(self, bot: commands.Bot, interval_hours: float = 6.0) -> None:
        """Vòng lặp tự động sao lưu CSDL định kỳ (mặc định 6 tiếng)."""
        await bot.wait_until_ready()
        if self._loop_running:
            logger.debug("Vòng lặp sao lưu CSDL đã đang chạy, bỏ qua lời gọi trùng lặp.")
            return
        self._loop_running = True
        interval_sec = max(60.0, interval_hours * 3600.0)
        logger.info(f"🔄 Khởi động vòng lặp sao lưu CSDL tự động (mỗi {interval_hours} giờ / lần)...")

        # Chờ 30 giây sau khởi động trước khi tạo bản sao lưu đầu tiên
        await asyncio.sleep(30)

        while not bot.is_closed():
            try:
                await asyncio.to_thread(self.create_local_backup)
            except Exception as e:
                logger.warning(f"Lỗi trong vòng lặp sao lưu CSDL: {e}")
            await asyncio.sleep(interval_sec)


backup_service = DatabaseBackupService()
