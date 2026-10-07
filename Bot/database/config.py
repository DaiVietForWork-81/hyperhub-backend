from __future__ import annotations

import logging
from datetime import datetime, timezone

from .database import Database

log = logging.getLogger(__name__)

EMBED_COLOR_KEY = "embed_color"


class ConfigRepository:
    """Quản lý cấu hình động: danh sách role moderation + màu chủ đề embed."""

    def __init__(self, db: Database):
        self.db = db
        self._mod_role_ids: set[int] | None = None

    async def get_mod_role_ids(self) -> set[int]:
        if self._mod_role_ids is None:
            rows = await self.db.fetchall("SELECT role_id FROM mod_roles")
            self._mod_role_ids = {row["role_id"] for row in rows}
        return set(self._mod_role_ids)

    async def add_mod_roles(self, role_ids: list[int], added_by: int) -> int:
        now = datetime.now(timezone.utc).isoformat()
        added = 0
        for rid in dict.fromkeys(role_ids):
            try:
                cursor = await self.db.connection.execute(
                    "INSERT OR IGNORE INTO mod_roles (role_id, added_by, added_at) "
                    "VALUES (?, ?, ?)",
                    (rid, added_by, now),
                )
                added += cursor.rowcount
            except Exception:
                log.exception("Không thể thêm role moderation %s", rid)
        await self.db.connection.commit()
        if added:
            self._mod_role_ids = None
        return added

    async def remove_mod_roles(self, role_ids: list[int]) -> int:
        removed = 0
        for rid in dict.fromkeys(role_ids):
            cursor = await self.db.connection.execute(
                "DELETE FROM mod_roles WHERE role_id = ?", (rid,)
            )
            removed += cursor.rowcount
        await self.db.connection.commit()
        if removed:
            self._mod_role_ids = None
        return removed

    async def get_embed_color(self) -> int | None:
        row = await self.db.fetchone(
            "SELECT value FROM bot_settings WHERE key = ?", EMBED_COLOR_KEY
        )
        if row is None:
            return None
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return None

    async def set_embed_color(self, color: int) -> None:
        await self.db.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            EMBED_COLOR_KEY,
            str(color),
        )
