"""Dịch vụ quản lý Gói thành viên Hyper (Tier) và hạn mức Token hàng ngày.

Quản lý hạn mức Token theo 4 Gói (Free, Pro, Ultra, Elite), tự động nhận diện
Role từ Discord, khấu trừ token, hoàn 100% token khi có sự cố, và tự động reset lúc 00:00 UTC+7.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo
from typing import Any, Optional

import discord
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.database import async_session_factory
from database.models import ExamJob, UserTokenTier
from utils.logger import get_logger

logger = get_logger("UserTokenService")

# Múi giờ Việt Nam (UTC+7)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Định nghĩa hạn mức và cấu hình 4 Gói Hyper
TIER_SPECS = {
    "Elite": {
        "name": "Hyper Elite",
        "icon": "⚡",
        "role_id_attr": "ROLE_HYPER_ELITE_ID",
        "daily_tokens": 999_999,  # Vô hạn thực tế
        "is_unlimited": True,
        "priority": 0,
        "color": 0xFEE75C,  # Gold / Yellow
        "allow_to_length": True,
        "allow_max_ultra_mode": True,
    },
    "Ultra": {
        "name": "Hyper Ultra",
        "icon": "👑",
        "role_id_attr": "ROLE_HYPER_ULTRA_ID",
        "daily_tokens": 2800,
        "is_unlimited": False,
        "priority": 1,
        "color": 0xEB459E,  # Magenta / Fuchsia
        "allow_to_length": True,
        "allow_max_ultra_mode": True,
    },
    "Pro": {
        "name": "Hyper Pro",
        "icon": "🟣",
        "role_id_attr": "ROLE_HYPER_PRO_ID",
        "daily_tokens": 700,
        "is_unlimited": False,
        "priority": 2,
        "color": 0x9B59B6,  # Purple
        "allow_to_length": True,
        "allow_max_ultra_mode": True,
    },
    "Free": {
        "name": "Hyper Free",
        "icon": "🆓",
        "role_id_attr": "ROLE_HYPER_FREE_ID",
        "daily_tokens": 200,
        "is_unlimited": False,
        "priority": 3,
        "color": 0x5865F2,  # Blurple
        "allow_to_length": False,
        "allow_max_ultra_mode": False,
    },
}

# Điểm số độ dài
LENGTH_POINTS = {
    "Ngắn": 10,   # 2-3 trang
    "Vừa": 20,    # 4-6 trang
    "Dài": 35,    # 8-12 trang
    "To": 60,     # >15 trang (Pro+)
}

# Hệ số Chế độ AI
MODE_MULTIPLIERS = {
    "Lite": 1.0,
    "Flash": 1.5,
    "Pro": 2.0,
    "Max": 3.0,
    "Ultra": 4.0,
}

# Phân loại môn học và hệ số độ khó
SUBJECT_MULTIPLIERS = {
    "basic": 1.0,         # Phổ thông cơ bản
    "advanced": 1.2,      # Nâng cao / HSG / THPT Quốc gia / Lập trình cơ bản
    "international": 1.4, # IELTS 8.0, JLPT N1-N2, HSK 5-6, Olympic Tin/Toán
}


class UserTokenService:
    """Dịch vụ trung tâm điều phối và tính toán Token cho HyperHub."""

    @staticmethod
    def get_today_vn_str() -> str:
        """Trả về ngày hiện tại theo chuẩn YYYY-MM-DD theo giờ Việt Nam (UTC+7)."""
        return datetime.datetime.now(VN_TZ).strftime("%Y-%m-%d")

    @staticmethod
    def get_seconds_until_next_reset() -> int:
        """Tính số giây còn lại cho đến 00:00 UTC+7 ngày tiếp theo."""
        now = datetime.datetime.now(VN_TZ)
        tomorrow = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return max(0, int((tomorrow - now).total_seconds()))

    @classmethod
    def determine_tier_from_member(cls, member: discord.Member | None) -> str:
        """Nhận diện Tier của thành viên Discord dựa trên Role họ đang sở hữu."""
        if not member:
            return "Free"

        user_role_ids = {r.id for r in getattr(member, "roles", [])}

        elite_id = getattr(settings, "ROLE_HYPER_ELITE_ID", 0)
        ultra_id = getattr(settings, "ROLE_HYPER_ULTRA_ID", 0)
        pro_id = getattr(settings, "ROLE_HYPER_PRO_ID", 0)

        # Kiểm tra từ cấp cao nhất xuống
        if elite_id and elite_id in user_role_ids:
            return "Elite"
        if ultra_id and ultra_id in user_role_ids:
            return "Ultra"
        if pro_id and pro_id in user_role_ids:
            return "Pro"

        return "Free"

    @classmethod
    def classify_subject_difficulty(cls, subject_text: str) -> tuple[str, float]:
        """Tự động phân loại môn học để áp dụng hệ số độ khó chuẩn."""
        s = subject_text.lower()
        # Nhóm Quốc tế / Olympic / Chứng chỉ cao cấp
        international_keywords = [
            "ielts", "jlpt n1", "jlpt n2", "n1", "n2", "hsk 5", "hsk 6", "hsk5", "hsk6",
            "sat", "toefl", "olympic", "vnoi", "codeforces", "icpc", "usaco"
        ]
        if any(k in s for k in international_keywords):
            return "Quốc tế / Chuyên sâu (x1.4)", SUBJECT_MULTIPLIERS["international"]

        # Nhóm Nâng cao / HSG / Lập trình / Chuyên
        advanced_keywords = [
            "c++", "cpp", "python", "py", "java", "dsa", "cấu trúc dữ liệu", "thuật toán",
            "hsg", "chuyên", "thpt quốc gia", "đại học", "n3", "hsk 3", "hsk 4", "nâng cao"
        ]
        if any(k in s for k in advanced_keywords):
            return "Nâng cao / Chuyên đề (x1.2)", SUBJECT_MULTIPLIERS["advanced"]

        # Nhóm Phổ thông cơ bản
        return "Cơ bản / Phổ thông (x1.0)", SUBJECT_MULTIPLIERS["basic"]

    @classmethod
    def calculate_token_cost(
        cls, length: str, mode: str, subject: str
    ) -> tuple[int, dict[str, Any]]:
        """Tính toán chi phí token theo công thức chuẩn:

        Cost = Điểm_Độ_Dài * Hệ_Số_Chế_Độ * Hệ_Số_Môn_Học
        """
        base_points = LENGTH_POINTS.get(length, 10)
        mode_mult = MODE_MULTIPLIERS.get(mode, 1.0)
        subj_label, subj_mult = cls.classify_subject_difficulty(subject)

        raw_cost = base_points * mode_mult * subj_mult
        final_cost = int(round(raw_cost))

        return final_cost, {
            "base_points": base_points,
            "mode_mult": mode_mult,
            "subj_label": subj_label,
            "subj_mult": subj_mult,
            "final_cost": final_cost,
        }

    @classmethod
    async def get_or_sync_user_token(
        cls, discord_id: int, member: discord.Member | None = None
    ) -> dict[str, Any]:
        """Lấy thông tin token của user, đồng bộ role nếu có member, và reset nếu sang ngày mới."""
        today_str = cls.get_today_vn_str()

        # Xác định tier từ member nếu có
        detected_tier = cls.determine_tier_from_member(member) if member else None

        async with async_session_factory() as session:
            stmt = select(UserTokenTier).where(UserTokenTier.discord_id == discord_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                # Tạo bản ghi mới
                tier = detected_tier or "Free"
                daily_quota = TIER_SPECS[tier]["daily_tokens"]
                record = UserTokenTier(
                    discord_id=discord_id,
                    tier=tier,
                    daily_tokens=daily_quota,
                    used_tokens_today=0,
                    last_reset_date=today_str,
                    total_generated=0,
                )
                session.add(record)
                await session.commit()
                await session.refresh(record)
            else:
                updated = False
                # Nếu có thông tin member và tier thay đổi theo role -> Cập nhật tier
                if detected_tier and record.tier != detected_tier:
                    record.tier = detected_tier
                    record.daily_tokens = TIER_SPECS[detected_tier]["daily_tokens"]
                    updated = True

                # Kiểm tra sang ngày mới -> Reset used_tokens
                if record.last_reset_date != today_str:
                    record.used_tokens_today = 0
                    record.last_reset_date = today_str
                    updated = True

                if updated:
                    await session.commit()
                    await session.refresh(record)

            tier_meta = TIER_SPECS.get(record.tier, TIER_SPECS["Free"])
            is_unlimited = tier_meta["is_unlimited"]

            remaining = 999_999 if is_unlimited else max(0, record.daily_tokens - record.used_tokens_today)

            return {
                "discord_id": record.discord_id,
                "tier": record.tier,
                "tier_name": tier_meta["name"],
                "tier_icon": tier_meta["icon"],
                "color": tier_meta["color"],
                "daily_tokens": record.daily_tokens,
                "used_tokens_today": record.used_tokens_today,
                "remaining_tokens": remaining,
                "is_unlimited": is_unlimited,
                "total_generated": record.total_generated,
                "last_reset_date": record.last_reset_date,
                "allow_to_length": tier_meta["allow_to_length"],
                "allow_max_ultra_mode": tier_meta["allow_max_ultra_mode"],
            }

    @classmethod
    async def can_afford(
        cls, discord_id: int, cost: int, member: discord.Member | None = None
    ) -> tuple[bool, int, dict[str, Any]]:
        """Kiểm tra xem người dùng có đủ token để thực hiện yêu cầu không."""
        data = await cls.get_or_sync_user_token(discord_id, member)
        if data["is_unlimited"]:
            return True, 999_999, data
        has_enough = data["remaining_tokens"] >= cost
        return has_enough, data["remaining_tokens"], data

    @classmethod
    async def deduct_tokens(
        cls, discord_id: int, amount: int, member: discord.Member | None = None
    ) -> bool:
        """Khấu trừ token khi người dùng bắt đầu tiến trình sinh bài."""
        today_str = cls.get_today_vn_str()
        async with async_session_factory() as session:
            stmt = select(UserTokenTier).where(UserTokenTier.discord_id == discord_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                await cls.get_or_sync_user_token(discord_id, member)
                stmt = select(UserTokenTier).where(UserTokenTier.discord_id == discord_id)
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

            if not record:
                return False

            tier_meta = TIER_SPECS.get(record.tier, TIER_SPECS["Free"])
            if not tier_meta["is_unlimited"]:
                if record.last_reset_date != today_str:
                    record.used_tokens_today = 0
                    record.last_reset_date = today_str

                record.used_tokens_today += amount

            record.total_generated += 1
            await session.commit()
            logger.info(
                f"Đã trừ {amount} tokens của {discord_id} (Tier: {record.tier}). Tổng dùng hôm nay: {record.used_tokens_today}"
            )
            return True

    @classmethod
    async def refund_tokens(
        cls, discord_id: int, amount: int, reason: str = "Lỗi hệ thống"
    ) -> None:
        """Hoàn lại 100% token cho người dùng khi có lỗi hoặc sự cố."""
        async with async_session_factory() as session:
            stmt = select(UserTokenTier).where(UserTokenTier.discord_id == discord_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record:
                tier_meta = TIER_SPECS.get(record.tier, TIER_SPECS["Free"])
                if not tier_meta["is_unlimited"]:
                    record.used_tokens_today = max(0, record.used_tokens_today - amount)
                if record.total_generated > 0:
                    record.total_generated -= 1
                await session.commit()
                logger.info(
                    f"✨ Đã hoàn {amount} tokens cho {discord_id} do: {reason}. Còn lại: {record.daily_tokens - record.used_tokens_today}"
                )

    @staticmethod
    def render_progress_bar(used: int, total: int, length: int = 14) -> str:
        """Vẽ thanh tiến trình trực quan [████████░░░░] biểu thị token đã dùng."""
        if total <= 0:
            return "[`░`" * length + "]"
        ratio = min(1.0, max(0.0, used / total))
        filled = int(round(ratio * length))
        empty = length - filled
        return f"`[{'█' * filled}{'░' * empty}]`"

    @classmethod
    async def record_exam_job(
        cls,
        job_id: str,
        discord_id: int,
        thread_id: int,
        subject: str,
        style: str,
        length_tier: str,
        mode: str,
        output_format: str,
        token_cost: int,
    ) -> None:
        """Ghi nhận phiên tạo đề mới vào cơ sở dữ liệu."""
        async with async_session_factory() as session:
            job = ExamJob(
                job_id=job_id,
                discord_id=discord_id,
                thread_id=thread_id,
                subject=subject,
                style=style,
                length_tier=length_tier,
                mode=mode,
                output_format=output_format,
                token_cost=token_cost,
                status="IN_PROGRESS",
            )
            session.add(job)
            await session.commit()

    @classmethod
    async def update_exam_job(
        cls,
        job_id: str,
        status: str,
        exam_file_path: Optional[str] = None,
        solution_file_path: Optional[str] = None,
        database_msg_id: Optional[int] = None,
        checkpoint_data: Optional[str] = None,
        is_shuffled: Optional[bool] = None,
    ) -> None:
        """Cập nhật trạng thái, dữ liệu checkpoint và đường dẫn file của phiên tạo đề."""
        async with async_session_factory() as session:
            stmt = select(ExamJob).where(ExamJob.job_id == job_id)
            res = await session.execute(stmt)
            job = res.scalar_one_or_none()
            if job:
                job.status = status
                if exam_file_path:
                    job.exam_file_path = exam_file_path
                if solution_file_path:
                    job.solution_file_path = solution_file_path
                if database_msg_id:
                    job.database_msg_id = database_msg_id
                if checkpoint_data:
                    job.checkpoint_data = checkpoint_data
                if is_shuffled is not None:
                    job.is_shuffled = is_shuffled
                if status in ("COMPLETED", "CLOSED", "FAILED"):
                    job.completed_at = datetime.datetime.now(datetime.timezone.utc)
                await session.commit()

    @classmethod
    async def get_exam_job(cls, job_id: str) -> Optional[ExamJob]:
        """Lấy thông tin chi tiết một đề thi theo Job ID."""
        async with async_session_factory() as session:
            stmt = select(ExamJob).where(ExamJob.job_id == job_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    @classmethod
    async def search_exam_jobs(cls, query: str, limit: int = 5) -> list[ExamJob]:
        """Tìm kiếm các bộ đề thi trong cơ sở dữ liệu theo từ khóa môn học hoặc phong cách."""
        clean_q = f"%{query.strip()}%"
        async with async_session_factory() as session:
            stmt = (
                select(ExamJob)
                .where(
                    (ExamJob.subject.ilike(clean_q))
                    | (ExamJob.style.ilike(clean_q))
                    | (ExamJob.job_id.ilike(clean_q))
                )
                .where(ExamJob.status.in_(["COMPLETED", "CLOSED"]))
                .order_by(ExamJob.created_at.desc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            return list(res.scalars().all())

    @classmethod
    async def get_recent_jobs_by_user(
        cls, discord_id: int, limit: int = 5
    ) -> list[ExamJob]:
        """Lấy danh sách các đề thi đã tạo gần đây của người dùng."""
        async with async_session_factory() as session:
            stmt = (
                select(ExamJob)
                .where(ExamJob.discord_id == discord_id)
                .order_by(ExamJob.created_at.desc())
                .limit(limit)
            )
            res = await session.execute(stmt)
            return list(res.scalars().all())


# Khởi tạo instance toàn cục
user_token_service = UserTokenService()
