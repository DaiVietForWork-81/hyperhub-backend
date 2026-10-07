from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import Database

log = logging.getLogger(__name__)


class ModerationRepository:
    def __init__(self, db: Database):
        self.db = db

    async def log_kick(
        self, target_id: int, target_name: str,
        moderator_id: int, moderator_name: str, reason: str,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO kick_logs (target_id, target_name, moderator_id, moderator_name, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            target_id, target_name, moderator_id, moderator_name,
            reason, datetime.now(timezone.utc).isoformat(),
        )

    async def get_kick_logs(self) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM kick_logs ORDER BY id DESC")

    async def log_mute(
        self, target_id: int, target_name: str,
        moderator_id: int, moderator_name: str, reason: str, duration: int,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO mute_logs (target_id, target_name, moderator_id, moderator_name, reason, duration, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            target_id, target_name, moderator_id, moderator_name,
            reason, duration, datetime.now(timezone.utc).isoformat(),
        )

    async def get_mute_logs(self) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM mute_logs ORDER BY id DESC")

    async def log_ban(
        self, target_id: int, target_name: str,
        moderator_id: int, moderator_name: str, reason: str,
        is_temporary: bool, duration: int | None, start_time: str, end_time: str | None,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO ban_logs (target_id, target_name, moderator_id, moderator_name, reason, is_temporary, duration, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            target_id, target_name, moderator_id, moderator_name, reason,
            int(is_temporary), duration, start_time, end_time,
        )

    async def get_ban_logs(self) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM ban_logs ORDER BY id DESC")

    async def schedule_unban(
        self, target_id: int, target_name: str, guild_id: int,
        moderator_id: int, moderator_name: str, reason: str,
        start_time: str, end_time: str,
    ) -> int:
        cursor = await self.db.connection.execute(
            """
            INSERT INTO scheduled_unbans (target_id, target_name, guild_id, moderator_id, moderator_name, reason, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (target_id, target_name, guild_id, moderator_id, moderator_name,
             reason, start_time, end_time),
        )
        await self.db.connection.commit()
        return cursor.lastrowid

    async def get_scheduled_unbans(self) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM scheduled_unbans")

    async def remove_scheduled_unban(self, entry_id: int) -> None:
        await self.db.execute("DELETE FROM scheduled_unbans WHERE id = ?", entry_id)

    async def log_warn(
        self, target_id: int, target_name: str,
        moderator_id: int, moderator_name: str, reason: str,
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO warn_logs (target_id, target_name, moderator_id, moderator_name, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            target_id, target_name, moderator_id, moderator_name,
            reason, datetime.now(timezone.utc).isoformat(),
        )

    async def get_warn_logs(self) -> list[Any]:
        return await self.db.fetchall("SELECT * FROM warn_logs ORDER BY id DESC")

    async def get_warn_logs_for_user(self, target_id: int) -> list[Any]:
        return await self.db.fetchall(
            "SELECT * FROM warn_logs WHERE target_id = ? ORDER BY id ASC", target_id
        )

    async def delete_warn(self, warn_id: int) -> bool:
        cursor = await self.db.connection.execute(
            "DELETE FROM warn_logs WHERE id = ?", (warn_id,)
        )
        await self.db.connection.commit()
        return cursor.rowcount > 0

    async def get_warn_count(self, target_id: int) -> int:
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS cnt FROM warn_logs WHERE target_id = ?", target_id
        )
        return row["cnt"] if row else 0

    async def get_warn_counts(self, target_ids: list[int]) -> dict[int, int]:
        """Đếm số cảnh cáo cho nhiều user trong 1 query."""
        if not target_ids:
            return {}
        placeholders = ", ".join("?" * len(target_ids))
        rows = await self.db.fetchall(
            f"SELECT target_id, COUNT(*) AS cnt FROM warn_logs "
            f"WHERE target_id IN ({placeholders}) GROUP BY target_id",
            *target_ids,
        )
        return {row["target_id"]: row["cnt"] for row in rows}

    async def reset_all_logs(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in ("kick_logs", "mute_logs", "ban_logs", "warn_logs"):
            cursor = await self.db.connection.execute(f"DELETE FROM {table}")
            counts[table] = cursor.rowcount
        await self.db.connection.commit()
        return counts

    async def cleanup_old_records(self, days: int = 30) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        kicked_cursor = await self.db.connection.execute(
            "DELETE FROM kick_logs WHERE timestamp < ?", (cutoff,)
        )
        ban_cursor = await self.db.connection.execute(
            "DELETE FROM ban_logs WHERE start_time < ?", (cutoff,)
        )
        warn_cursor = await self.db.connection.execute(
            "DELETE FROM warn_logs WHERE timestamp < ?", (cutoff,)
        )
        await self.db.connection.commit()

        kicked, banned, warned = (
            kicked_cursor.rowcount, ban_cursor.rowcount, warn_cursor.rowcount
        )
        if kicked or banned or warned:
            log.info(
                "Cleaned up %s kick(s), %s ban(s), %s warning(s) older than %s days",
                kicked, banned, warned, days,
            )