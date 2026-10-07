from __future__ import annotations

from datetime import datetime
from .database import Database

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    try:
        VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
    except Exception:
        VN_TZ = timezone(timedelta(hours=7))
except ImportError:
    VN_TZ = timezone(timedelta(hours=7))



class CooldownRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def now_vn() -> datetime:
        return datetime.now(VN_TZ)

    @staticmethod
    def is_new_day(last_change: datetime, now: datetime) -> bool:
        return last_change.date() < now.date()

    async def can_change(self, user_id: int) -> tuple[bool, datetime | None]:
        row = await self.db.fetchone(
            "SELECT last_change_text FROM user_cooldowns WHERE user_id = ?",
            user_id,
        )
        if row is None:
            return True, None
        last_change = datetime.fromisoformat(row["last_change_text"])
        if last_change.tzinfo is None:
            last_change = last_change.replace(tzinfo=VN_TZ)
        return self.is_new_day(last_change, self.now_vn()), last_change

    async def record_change(self, user_id: int) -> None:
        now = self.now_vn().isoformat(timespec="seconds")
        await self.db.execute(
            """
            INSERT INTO user_cooldowns (user_id, last_change_text)
            VALUES (?, ?)
            ON CONFLICT (user_id) DO UPDATE SET last_change_text = excluded.last_change_text
            """,
            user_id,
            now,
        )