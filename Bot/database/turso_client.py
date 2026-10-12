"""Async Turso libSQL Cloud Database Client for HyperHub.

Kết nối trực tiếp tới Turso qua HTTP v2 Pipeline bằng aiohttp.
Tối ưu cho gói Turso Free (5GB Storage, 10M Writes, 500M Reads).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import aiohttp

from config.settings import settings

logger = logging.getLogger("TursoClient")


class TursoClient:
    """Client kết nối tới Turso libSQL Database qua HTTP v2 pipeline."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        raw_url = (database_url or settings.TURSO_DATABASE_URL or "").strip()
        # Chuẩn hóa URL sang HTTPS
        if raw_url.startswith("libsql://"):
            raw_url = raw_url.replace("libsql://", "https://")
        elif not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = f"https://{raw_url}"
        self.base_url = raw_url.rstrip("/")
        self.auth_token = (auth_token or settings.TURSO_AUTH_TOKEN or "").strip()
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.auth_token)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=15.0),
                headers={
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _format_args(self, args: Tuple[Any, ...] | List[Any]) -> List[Dict[str, Any]]:
        formatted = []
        for a in args:
            if a is None:
                formatted.append({"type": "null"})
            elif isinstance(a, bool):
                formatted.append({"type": "integer", "value": "1" if a else "0"})
            elif isinstance(a, int):
                formatted.append({"type": "integer", "value": str(a)})
            elif isinstance(a, float):
                formatted.append({"type": "float", "value": a})
            else:
                formatted.append({"type": "text", "value": str(a)})
        return formatted

    async def execute(
        self, sql: str, *args: Any
    ) -> Tuple[int, Optional[int]]:
        """Thực thi một câu lệnh SQL. Trả về (affected_rows, last_insert_rowid)."""
        if not self.is_configured:
            return 0, None

        session = await self._get_session()
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": self._format_args(args),
                    },
                },
                {"type": "close"},
            ]
        }

        url = f"{self.base_url}/v2/pipeline"
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("Turso execute failed (%s): %s", resp.status, text[:200])
                    return 0, None
                data = await resp.json()
                res = data.get("results", [{}])[0].get("response", {}).get("result", {})
                affected = res.get("affected_row_count", 0)
                last_id = res.get("last_insert_rowid")
                return affected, int(last_id) if last_id is not None else None
        except Exception as e:
            logger.debug("Lỗi kết nối Turso execute: %s", e)
            return 0, None

    async def fetchall(
        self, sql: str, *args: Any
    ) -> List[Dict[str, Any]]:
        """Truy vấn danh sách bản ghi dưới dạng List of Dict."""
        if not self.is_configured:
            return []

        session = await self._get_session()
        payload = {
            "requests": [
                {
                    "type": "execute",
                    "stmt": {
                        "sql": sql,
                        "args": self._format_args(args),
                    },
                },
                {"type": "close"},
            ]
        }

        url = f"{self.base_url}/v2/pipeline"
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                res = data.get("results", [{}])[0].get("response", {}).get("result", {})
                cols = [c.get("name") for c in res.get("cols", [])]
                rows_data = res.get("rows", [])
                output = []
                for row in rows_data:
                    row_dict = {}
                    for idx, col_name in enumerate(cols):
                        val_obj = row[idx] if idx < len(row) else {}
                        v_type = val_obj.get("type")
                        val = val_obj.get("value")
                        if v_type == "null":
                            row_dict[col_name] = None
                        elif v_type == "integer":
                            row_dict[col_name] = int(val) if val is not None else None
                        elif v_type == "float":
                            row_dict[col_name] = float(val) if val is not None else None
                        else:
                            row_dict[col_name] = val
                    output.append(row_dict)
                return output
        except Exception as e:
            logger.debug("Lỗi kết nối Turso fetchall: %s", e)
            return []

    async def fetchone(
        self, sql: str, *args: Any
    ) -> Optional[Dict[str, Any]]:
        rows = await self.fetchall(sql, *args)
        return rows[0] if rows else None


# Singleton Turso instance
turso_db = TursoClient()
