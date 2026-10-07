"""
services/anti_raid_service.py
Dịch vụ Phòng Thủ Toàn Diện: Chống Spam, Chống Raid Bot & Phong Tỏa Khẩn Cấp (Lockdown).

Tính năng:
1. Anti-Spam:
   - Message Flood (Tần suất dồn dập trong vài giây)
   - Duplicate Spam (Lặp đi lặp lại cùng nội dung)
   - Mass Mention (Ping @everyone, @here, hoặc ping > 4 thành viên trái phép)
   - Unauthorized Invite Spam (Spam link mời Discord server khác)
2. Anti-Raid:
   - Join Flood Detection (> 5 members/10s)
   - Unauthorized Bot Quarantine (Tự động Ban bot lạ không được mời bởi Owner)
   - Coordinated Raid Detection
   - Emergency Lockdown Mode (Khóa nhanh quyền gửi tin của @everyone)
   - Mass Purge (Tự động loại bỏ / Ban toàn bộ các tài khoản tham gia raid)
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import discord

from utils.logger import get_logger

log = get_logger("AntiRaidService")


@dataclass
class SpamViolation:
    violation_type: str  # "FLOOD", "DUPLICATE", "MASS_MENTION", "INVITE_SPAM"
    details: str
    action_taken: str  # "TIMEOUT", "DELETE", "WARN"
    timestamp: float = field(default_factory=time.time)


@dataclass
class RaidEvent:
    guild_id: int
    started_at: float
    trigger_reason: str
    involved_user_ids: list[int] = field(default_factory=list)
    purged_count: int = 0
    is_active: bool = True
    ended_at: Optional[float] = None


class AntiRaidService:
    """Hệ thống lõi phát hiện và xử lý Spam & Raid Bot tự động."""

    INVITE_REGEX = re.compile(
        r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9_-]+",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        # User message timestamps for flood detection: user_id -> deque of timestamps
        self._user_msg_times: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=20))
        # User message content hashes for duplicate detection: user_id -> deque of (hash, timestamp)
        self._user_msg_hashes: dict[int, deque[tuple[str, float]]] = defaultdict(lambda: deque(maxlen=10))
        # Guild join timestamps: guild_id -> deque of (user_id, is_bot, timestamp, account_age_seconds)
        self._guild_join_times: dict[int, deque[tuple[int, bool, float, float]]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        # Active Raid tracking: guild_id -> RaidEvent
        self._active_raids: dict[int, RaidEvent] = {}
        # Recent raid history: list of RaidEvent
        self._raid_history: list[RaidEvent] = []
        # Lockdown channels cache (to restore permissions properly)
        # guild_id -> dict[channel_id, original_overwrite_dict]
        self._lockdown_cache: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
        # Lockdown status: guild_id -> bool
        self._guild_lockdown_status: dict[int, bool] = defaultdict(bool)

        # Configurable thresholds
        self.flood_threshold: int = 5         # 5 messages
        self.flood_window_seconds: float = 4.0 # in 4 seconds
        self.duplicate_threshold: int = 3     # 3 identical messages
        self.duplicate_window_seconds: float = 12.0
        self.mass_mention_threshold: int = 4  # > 4 mentions
        self.join_flood_threshold: int = 5    # 5 joins
        self.join_flood_window_seconds: float = 10.0 # in 10 seconds

    # =========================================================================
    # 1. ANTI-SPAM PIPELINE
    # =========================================================================

    def check_message_spam(self, message: discord.Message) -> Optional[SpamViolation]:
        """
        Kiểm tra tin nhắn có vi phạm các tiêu chuẩn chống spam hay không.
        Trả về SpamViolation nếu phát hiện, ngược lại trả về None.
        """
        if not message.guild or message.author.bot:
            return None

        # Bỏ qua nếu tác giả là Quản trị viên
        member = message.guild.get_member(message.author.id)
        if member and member.guild_permissions.administrator:
            return None

        user_id = message.author.id
        now = time.time()
        content = (message.content or "").strip()

        # 1.1 Kiểm tra Mass Mention (@everyone, @here, hoặc > 4 mentions)
        if not (member and member.guild_permissions.mention_everyone):
            if message.mention_everyone:
                return SpamViolation(
                    violation_type="MASS_MENTION",
                    details="Đề cập @everyone / @here trái phép",
                    action_taken="TIMEOUT",
                )

        if len(message.mentions) > self.mass_mention_threshold:
            return SpamViolation(
                violation_type="MASS_MENTION",
                details=f"Đề cập quá nhiều thành viên ({len(message.mentions)} mentions)",
                action_taken="TIMEOUT",
            )

        # 1.2 Kiểm tra Invite Link Spam trái phép
        if self.INVITE_REGEX.search(content):
            return SpamViolation(
                violation_type="INVITE_SPAM",
                details="Gửi link mời Discord trái phép",
                action_taken="TIMEOUT",
            )

        # 1.3 Kiểm tra Message Flood (Gửi quá nhiều tin trong thời gian ngắn)
        user_times = self._user_msg_times[user_id]
        user_times.append(now)
        recent_count = sum(1 for t in user_times if now - t <= self.flood_window_seconds)
        if recent_count >= self.flood_threshold:
            return SpamViolation(
                violation_type="FLOOD",
                details=f"Gửi tin dồn dập ({recent_count} tin trong {self.flood_window_seconds}s)",
                action_taken="TIMEOUT",
            )

        # 1.4 Kiểm tra Duplicate Spam (Tin nhắn giống hệt nhau liên tiếp)
        if len(content) >= 3:
            h = hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()
            user_hashes = self._user_msg_hashes[user_id]
            user_hashes.append((h, now))
            dup_count = sum(1 for dh, dt in user_hashes if dh == h and now - dt <= self.duplicate_window_seconds)
            if dup_count >= self.duplicate_threshold:
                return SpamViolation(
                    violation_type="DUPLICATE",
                    details=f"Gửi lặp lại cùng một nội dung {dup_count} lần liên tiếp",
                    action_taken="TIMEOUT",
                )

        return None

    # =========================================================================
    # 2. ANTI-RAID PIPELINE
    # =========================================================================

    def record_member_join(self, member: discord.Member) -> tuple[bool, Optional[RaidEvent]]:
        """
        Ghi nhận thành viên mới join.
        Trả về (is_raid_triggered, raid_event).
        """
        guild_id = member.guild.id
        now = time.time()
        created_at_ts = member.created_at.replace(tzinfo=timezone.utc).timestamp()
        account_age = now - created_at_ts

        joins = self._guild_join_times[guild_id]
        joins.append((member.id, member.bot, now, account_age))

        # Đếm số lượng join trong window
        recent_joins = [
            (uid, is_b, t, age)
            for uid, is_b, t, age in joins
            if now - t <= self.join_flood_window_seconds
        ]

        # Nếu đang trong đợt raid sẵn có, nạp ID vào danh sách đối tượng raid
        if guild_id in self._active_raids and self._active_raids[guild_id].is_active:
            raid = self._active_raids[guild_id]
            if member.id not in raid.involved_user_ids:
                raid.involved_user_ids.append(member.id)
            return True, raid

        # Kiểm tra ngưỡng kích hoạt Raid
        if len(recent_joins) >= self.join_flood_threshold:
            # Phát hiện Join Flood
            involved_ids = [uid for uid, _, _, _ in recent_joins]
            raid_event = RaidEvent(
                guild_id=guild_id,
                started_at=now,
                trigger_reason=f"Phát hiện Join Flood ({len(recent_joins)} tài khoản gia nhập trong {self.join_flood_window_seconds:.0f}s)",
                involved_user_ids=involved_ids,
            )
            self._active_raids[guild_id] = raid_event
            self._raid_history.append(raid_event)
            log.warning(
                f"[ANTI-RAID TRIGGER] Guild {guild_id}: {raid_event.trigger_reason} | Targets: {len(involved_ids)}"
            )
            return True, raid_event

        return False, None

    def is_lockdown_active(self, guild_id: int) -> bool:
        """Kiểm tra server có đang ở trạng thái phong tỏa khẩn cấp hay không."""
        return self._guild_lockdown_status.get(guild_id, False)

    async def enable_lockdown(self, guild: discord.Guild, reason: str = "Phòng thủ Raid khẩn cấp") -> int:
        """
        Kích hoạt chế độ Phong Tỏa Khẩn Cấp (Lockdown Mode):
        Tạm thời khóa quyền SEND_MESSAGES của role @everyone trên các kênh chat công khai.
        Trả về số lượng kênh đã khóa.
        """
        guild_id = guild.id
        self._guild_lockdown_status[guild_id] = True
        locked_count = 0
        default_role = guild.default_role

        for channel in guild.text_channels:
            try:
                current_overwrite = channel.overwrites_for(default_role)
                # Lưu lại trạng thái cũ
                self._lockdown_cache[guild_id][channel.id] = {
                    "send_messages": current_overwrite.send_messages,
                    "send_messages_in_threads": current_overwrite.send_messages_in_threads,
                }
                # Khóa quyền gửi tin
                current_overwrite.send_messages = False
                current_overwrite.send_messages_in_threads = False
                await channel.set_permissions(default_role, overwrite=current_overwrite, reason=reason)
                locked_count += 1
            except Exception as e:
                log.debug(f"Không thể lockdown kênh {channel.name}: {e}")

        log.warning(f"[LOCKDOWN ENABLED] Guild {guild.name} ({guild.id}) - Đã khóa {locked_count} kênh text.")
        return locked_count

    async def disable_lockdown(self, guild: discord.Guild, reason: str = "Hết tình trạng báo động") -> int:
        """
        Hủy bỏ trạng thái Phong Tỏa:
        Khôi phục lại quyền SEND_MESSAGES ban đầu của @everyone trên các kênh đã khóa.
        """
        guild_id = guild.id
        self._guild_lockdown_status[guild_id] = False
        unlocked_count = 0
        default_role = guild.default_role
        cached = self._lockdown_cache.get(guild_id, {})

        for channel in guild.text_channels:
            try:
                if channel.id in cached:
                    orig = cached[channel.id]
                    overwrite = channel.overwrites_for(default_role)
                    overwrite.send_messages = orig.get("send_messages")
                    overwrite.send_messages_in_threads = orig.get("send_messages_in_threads")
                    await channel.set_permissions(default_role, overwrite=overwrite, reason=reason)
                    unlocked_count += 1
                else:
                    # Nếu không có cache, reset send_messages về None (kế thừa)
                    overwrite = channel.overwrites_for(default_role)
                    if overwrite.send_messages is False:
                        overwrite.send_messages = None
                        await channel.set_permissions(default_role, overwrite=overwrite, reason=reason)
                        unlocked_count += 1
            except Exception as e:
                log.debug(f"Không thể mở khóa kênh {channel.name}: {e}")

        self._lockdown_cache[guild_id].clear()
        if guild_id in self._active_raids:
            raid = self._active_raids[guild_id]
            raid.is_active = False
            raid.ended_at = time.time()

        log.info(f"[LOCKDOWN DISABLED] Guild {guild.name} ({guild.id}) - Đã mở khóa {unlocked_count} kênh text.")
        return unlocked_count

    async def purge_raid_entities(
        self,
        guild: discord.Guild,
        user_ids: list[int],
        action: str = "ban",
        reason: str = "Tài khoản liên quan đến đợt tấn công Raid",
    ) -> tuple[list[int], list[tuple[int, str]]]:
        """
        Xử lý loại bỏ hàng loạt các tài khoản tham gia đợt raid.
        Trả về (success_ids, failed_list).
        """
        success_ids: list[int] = []
        failed_list: list[tuple[int, str]] = []

        for uid in user_ids:
            try:
                member = guild.get_member(uid)
                if not member:
                    try:
                        member = await guild.fetch_member(uid)
                    except Exception:
                        member = None

                if member:
                    # Không chạm vào Administrator, Owner hoặc chính bot
                    if member == guild.owner or member.guild_permissions.administrator or member.id == guild.me.id:
                        continue

                    if action == "ban":
                        await member.ban(reason=reason, delete_message_days=1)
                    else:
                        await member.kick(reason=reason)
                else:
                    # Nếu không tìm thấy member (đã out), ban theo user ID nếu action là ban
                    if action == "ban":
                        await guild.ban(discord.Object(id=uid), reason=reason)

                success_ids.append(uid)
            except discord.Forbidden:
                failed_list.append((uid, "Thiếu quyền"))
            except Exception as e:
                failed_list.append((uid, str(e)))

            # Tránh Discord API rate-limit
            await asyncio.sleep(0.3)

        if guild.id in self._active_raids:
            self._active_raids[guild.id].purged_count += len(success_ids)

        log.warning(
            f"[RAID PURGE] Guild {guild.id}: Đã {action} thành công {len(success_ids)}/{len(user_ids)} đối tượng raid."
        )
        return success_ids, failed_list

    def get_recent_raids(self, limit: int = 5) -> list[RaidEvent]:
        """Lấy danh sách các đợt raid gần nhất."""
        return self._raid_history[-limit:]


# Singleton instance
anti_raid_service = AntiRaidService()
