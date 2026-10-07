from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

from database.moderation import ModerationRepository

log = logging.getLogger(__name__)


class BanScheduler:
    def __init__(self, bot: discord.Client, moderation: ModerationRepository):
        self.bot = bot
        self.moderation = moderation
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        await self.bot.wait_until_ready()

        rows = await self.moderation.get_scheduled_unbans()
        now = datetime.now(timezone.utc)

        for row in rows:
            end_time = datetime.fromisoformat(row["end_time"])
            if end_time <= now:
                await self._unban(dict(row))
            else:
                delay = (end_time - now).total_seconds()
                task = asyncio.create_task(self._schedule_unban(delay, dict(row)))
                self._tasks.append(task)

        if rows:
            log.info(
                "Scheduler loaded %s scheduled unbans, %s pending",
                len(rows), len(self._tasks),
            )

    async def schedule_ban(self, ban_data: dict) -> None:
        end_time = datetime.fromisoformat(ban_data["end_time"])
        now = datetime.now(timezone.utc)
        delay = (end_time - now).total_seconds()

        if delay > 0:
            task = asyncio.create_task(self._schedule_unban(delay, ban_data))
            self._tasks.append(task)

    async def _schedule_unban(self, delay: float, ban_data: dict) -> None:
        await asyncio.sleep(delay)
        await self._unban(ban_data)

    async def _unban(self, ban_data: dict) -> None:
        guild = self.bot.get_guild(int(ban_data["guild_id"]))

        if guild:
            try:
                user = discord.Object(id=int(ban_data["target_id"]))
                await guild.unban(user, reason="Temporary ban expired")
                log.info(
                    "Auto-unbanned %s (ID: %s) in %s",
                    ban_data["target_name"], ban_data["target_id"], guild.name,
                )
            except discord.NotFound:
                log.info("User %s already unbanned", ban_data["target_id"])
            except discord.Forbidden as exc:
                log.error("Missing permission to unban %s: %s", ban_data["target_id"], exc)
            except Exception:
                log.exception("Failed to auto-unban %s", ban_data["target_id"])
        else:
            log.warning(
                "Guild %s not found, removing unban schedule", ban_data["guild_id"]
            )

        await self.moderation.remove_scheduled_unban(ban_data["id"])

    async def cancel_all(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
