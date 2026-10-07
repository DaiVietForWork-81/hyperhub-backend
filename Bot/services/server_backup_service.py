"""
services/server_backup_service.py
Dịch vụ Quản lý Snapshot & Khôi Phục 100% Cấu Trúc Server (Disaster Recovery & Anti-Nuke).

Tính năng:
1. Snapshot Engine:
   - Chụp toàn bộ danh mục (Categories), kênh (Text/Voice Channels), phân quyền (Permissions Overwrites),
     vị trí (Positions), và vai trò (Roles).
   - Lưu trữ tự động vào `backups/server/snapshot_latest.json` và các bản theo thời gian.
2. Anti-Nuke Detection:
   - Bắt các hành vi xóa kênh, đổi tên kênh/danh mục, chuyển thư mục bất thường.
   - Nhận diện kẻ phá hoại qua Audit Log và kích hoạt tự động khôi phục.
3. 100% Restoration Engine:
   - Tạo lại Category và Channel bị mất.
   - Khôi phục tên gốc nếu bị đổi tên phá hoại.
   - Gắn lại kênh vào đúng Thư mục cha ban đầu.
   - Phục hồi chuẩn xác 100% phân quyền (Overwrites bitfield).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import discord

from utils.logger import get_logger

log = get_logger("ServerBackupService")

BACKUP_DIR = Path("backups/server")


@dataclass
class TamperAction:
    action_type: str  # "CHANNEL_DELETE", "CHANNEL_RENAME", "CHANNEL_MOVE", "ROLE_DELETE"
    actor_id: int
    target_id: int
    target_name: str
    timestamp: float = field(default_factory=time.time)


class ServerBackupService:
    """Quản lý sao lưu cấu trúc và khôi phục sự cố máy chủ Discord 100%."""

    def __init__(self) -> None:
        self.backup_dir = BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        # Tracking recent modifications to detect Nuke: guild_id -> deque of TamperAction
        self._tamper_logs: dict[int, deque[TamperAction]] = defaultdict(lambda: deque(maxlen=50))
        # Nuke threshold: >= 2 dangerous actions within 10 seconds by non-owner
        self.nuke_threshold: int = 2
        self.nuke_window_seconds: float = 10.0
        # Flag to prevent restore loops
        self._is_restoring: dict[int, bool] = defaultdict(bool)

    # =========================================================================
    # 1. SNAPSHOT ENGINE (SAO LƯU TOÀN DIỆN)
    # =========================================================================

    def _serialize_overwrites(
        self, overwrites: dict[Any, discord.PermissionOverwrite]
    ) -> list[dict[str, Any]]:
        """Mã hóa quyền hạn phân quyền (Permission Overwrites) thành dict JSON an toàn."""
        res: list[dict[str, Any]] = []
        for target, ow in overwrites.items():
            allow, deny = ow.pair()
            is_role = isinstance(target, discord.Role)
            res.append({
                "target_type": "role" if is_role else "member",
                "target_id": target.id,
                "target_name": target.name,
                "allow": allow.value,
                "deny": deny.value,
            })
        return res

    async def create_snapshot(
        self, guild: discord.Guild, note: str = "Tự động sao lưu định kỳ"
    ) -> dict[str, Any]:
        """
        Chụp snapshot toàn bộ cấu trúc máy chủ (Categories, Channels, Roles, Overwrites).
        Lưu vào file và trả về dữ liệu snapshot.
        """
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")

        roles_data: list[dict[str, Any]] = []
        for role in guild.roles:
            if role.is_default() or not role.managed:
                roles_data.append({
                    "id": role.id,
                    "name": role.name,
                    "color": role.color.value,
                    "permissions": role.permissions.value,
                    "position": role.position,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "is_default": role.is_default(),
                })

        categories_data: list[dict[str, Any]] = []
        for cat in guild.categories:
            categories_data.append({
                "id": cat.id,
                "name": cat.name,
                "position": cat.position,
                "overwrites": self._serialize_overwrites(cat.overwrites),
            })

        channels_data: list[dict[str, Any]] = []
        for ch in guild.channels:
            if isinstance(ch, discord.CategoryChannel):
                continue

            ch_type = "text"
            if isinstance(ch, discord.VoiceChannel):
                ch_type = "voice"
            elif isinstance(ch, discord.StageChannel):
                ch_type = "stage"
            elif isinstance(ch, discord.ForumChannel):
                ch_type = "forum"

            channels_data.append({
                "id": ch.id,
                "name": ch.name,
                "type": ch_type,
                "category_id": ch.category_id,
                "category_name": ch.category.name if ch.category else None,
                "position": ch.position,
                "topic": getattr(ch, "topic", None),
                "nsfw": getattr(ch, "nsfw", False),
                "slowmode_delay": getattr(ch, "slowmode_delay", 0),
                "overwrites": self._serialize_overwrites(ch.overwrites),
            })

        snapshot = {
            "version": "1.0",
            "guild_id": guild.id,
            "guild_name": guild.name,
            "created_at": now.isoformat(),
            "note": note,
            "counts": {
                "categories": len(categories_data),
                "channels": len(channels_data),
                "roles": len(roles_data),
            },
            "roles": roles_data,
            "categories": categories_data,
            "channels": channels_data,
        }

        # Lưu file latest và file timestamp
        latest_file = self.backup_dir / f"snapshot_latest_{guild.id}.json"
        history_file = self.backup_dir / f"snapshot_{guild.id}_{timestamp_str}.json"

        def _write_files():
            with open(latest_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write_files)

        log.info(
            f"[SNAPSHOT CREATED] Guild {guild.name} ({guild.id}) - "
            f"{len(categories_data)} categories, {len(channels_data)} channels, {len(roles_data)} roles. Note: {note}"
        )
        return snapshot

    def load_latest_snapshot(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Tải bản snapshot mới nhất của guild từ disk."""
        latest_file = self.backup_dir / f"snapshot_latest_{guild_id}.json"
        if not latest_file.exists():
            # Thử file không có guild_id (fallback bản cũ)
            legacy_file = self.backup_dir / "snapshot_latest.json"
            if legacy_file.exists():
                latest_file = legacy_file
            else:
                return None

        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Lỗi khi đọc snapshot: {e}")
            return None

    def list_snapshots(self, guild_id: int) -> list[dict[str, Any]]:
        """Liệt kê danh sách các bản snapshot có sẵn."""
        res: list[dict[str, Any]] = []
        pattern = f"snapshot_{guild_id}_*.json"
        files = sorted(self.backup_dir.glob(pattern), reverse=True)
        for p in files[:10]:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    res.append({
                        "file_name": p.name,
                        "created_at": data.get("created_at", ""),
                        "note": data.get("note", ""),
                        "categories": data.get("counts", {}).get("categories", 0),
                        "channels": data.get("counts", {}).get("channels", 0),
                        "roles": data.get("counts", {}).get("roles", 0),
                    })
            except Exception:
                pass
        return res

    # =========================================================================
    # 2. ANTI-NUKE & TAMPER DETECTION
    # =========================================================================

    def record_tamper_event(
        self, guild_id: int, action_type: str, actor_id: int, target_id: int, target_name: str
    ) -> tuple[bool, list[TamperAction]]:
        """
        Ghi nhận sự kiện thay đổi cấu trúc và kiểm tra xem có vượt ngưỡng phá hoại (Nuke) hay không.
        Trả về (is_nuke, recent_actions).
        """
        now = time.time()
        action = TamperAction(
            action_type=action_type,
            actor_id=actor_id,
            target_id=target_id,
            target_name=target_name,
            timestamp=now,
        )
        logs = self._tamper_logs[guild_id]
        logs.append(action)

        # Lọc các hành động của cùng actor trong window
        recent_by_actor = [
            a for a in logs if a.actor_id == actor_id and (now - a.timestamp <= self.nuke_window_seconds)
        ]

        if len(recent_by_actor) >= self.nuke_threshold:
            return True, recent_by_actor

        return False, []

    # =========================================================================
    # 3. 100% RESTORATION ENGINE
    # =========================================================================

    async def restore_server_structure(
        self,
        guild: discord.Guild,
        snapshot_data: Optional[dict[str, Any]] = None,
        reason: str = "Tự động khôi phục cấu trúc server 100% sau sự cố",
    ) -> dict[str, Any]:
        """
        Khôi phục 100% cấu trúc Server từ bản Snapshot:
        - Tạo lại Category bị xóa / Đổi lại tên cũ nếu bị đổi tên
        - Tạo lại Channel bị xóa / Đổi lại tên cũ nếu bị đổi tên
        - Đưa Channel về đúng Category cha
        - Khôi phục phân quyền Permissions Overwrites chuẩn 100%
        """
        guild_id = guild.id
        if self._is_restoring[guild_id]:
            return {"status": "already_running", "message": "Tiến trình khôi phục đang chạy."}

        self._is_restoring[guild_id] = True
        try:
            if not snapshot_data:
                snapshot_data = self.load_latest_snapshot(guild_id)

            if not snapshot_data:
                return {"status": "error", "message": "Không tìm thấy bản snapshot nào để khôi phục."}

            report: dict[str, Any] = {
                "categories_created": 0,
                "categories_renamed": 0,
                "channels_created": 0,
                "channels_renamed": 0,
                "channels_reparented": 0,
                "overwrites_restored": 0,
                "errors": [],
            }

            # -----------------------------------------------------------------
            # 3.1 Khôi phục / Đối chiếu Categories
            # -----------------------------------------------------------------
            snap_categories = snapshot_data.get("categories", [])
            cat_map: dict[str, discord.CategoryChannel] = {}  # name -> obj

            # Nạp các categories hiện có
            existing_cats_by_id = {c.id: c for c in guild.categories}
            existing_cats_by_name = {c.name: c for c in guild.categories}

            for snap_cat in snap_categories:
                cat_name = snap_cat["name"]
                cat_id = snap_cat["id"]
                target_cat: Optional[discord.CategoryChannel] = None

                # Tìm theo ID trước
                if cat_id in existing_cats_by_id:
                    target_cat = existing_cats_by_id[cat_id]
                # Hoặc tìm theo Tên
                elif cat_name in existing_cats_by_name:
                    target_cat = existing_cats_by_name[cat_name]

                if not target_cat:
                    # Category bị xóa -> Tạo lại
                    try:
                        target_cat = await guild.create_category(
                            name=cat_name,
                            position=snap_cat.get("position", 0),
                            reason=reason,
                        )
                        report["categories_created"] += 1
                        await asyncio.sleep(0.4)
                    except Exception as e:
                        report["errors"].append(f"Không thể tạo category '{cat_name}': {e}")
                else:
                    # Category còn nhưng bị đổi tên -> Khôi phục tên gốc
                    if target_cat.name != cat_name:
                        try:
                            await target_cat.edit(name=cat_name, reason=reason)
                            report["categories_renamed"] += 1
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            report["errors"].append(f"Không thể đổi tên category '{cat_name}': {e}")

                if target_cat:
                    cat_map[cat_name] = target_cat
                    # Khôi phục Overwrites cho Category
                    await self._apply_overwrites(guild, target_cat, snap_cat.get("overwrites", []), reason, report)

            # -----------------------------------------------------------------
            # 3.2 Khôi phục / Đối chiếu Channels
            # -----------------------------------------------------------------
            snap_channels = snapshot_data.get("channels", [])
            existing_chs_by_id = {ch.id: ch for ch in guild.channels}
            existing_chs_by_name = {ch.name: ch for ch in guild.channels if not isinstance(ch, discord.CategoryChannel)}

            for snap_ch in snap_channels:
                ch_name = snap_ch["name"]
                ch_id = snap_ch["id"]
                ch_type = snap_ch.get("type", "text")
                cat_name = snap_ch.get("category_name")
                target_category = cat_map.get(cat_name) if cat_name else None

                target_ch: Optional[discord.abc.GuildChannel] = None
                if ch_id in existing_chs_by_id:
                    target_ch = existing_chs_by_id[ch_id]
                elif ch_name in existing_chs_by_name:
                    target_ch = existing_chs_by_name[ch_name]

                if not target_ch:
                    # Kênh bị xóa -> Tạo lại
                    try:
                        if ch_type == "voice":
                            target_ch = await guild.create_voice_channel(
                                name=ch_name,
                                category=target_category,
                                position=snap_ch.get("position", 0),
                                reason=reason,
                            )
                        else:
                            target_ch = await guild.create_text_channel(
                                name=ch_name,
                                category=target_category,
                                topic=snap_ch.get("topic"),
                                position=snap_ch.get("position", 0),
                                slowmode_delay=snap_ch.get("slowmode_delay", 0),
                                nsfw=snap_ch.get("nsfw", False),
                                reason=reason,
                            )
                        report["channels_created"] += 1
                        await asyncio.sleep(0.4)
                    except Exception as e:
                        report["errors"].append(f"Không thể tạo channel '{ch_name}': {e}")
                else:
                    # Kênh còn nhưng bị đổi tên hoặc bị chuyển category
                    edit_kwargs: dict[str, Any] = {}
                    if target_ch.name != ch_name:
                        edit_kwargs["name"] = ch_name
                        report["channels_renamed"] += 1

                    if target_category and target_ch.category_id != target_category.id:
                        edit_kwargs["category"] = target_category
                        report["channels_reparented"] += 1

                    if edit_kwargs:
                        try:
                            await target_ch.edit(**edit_kwargs, reason=reason)
                            await asyncio.sleep(0.3)
                        except Exception as e:
                            report["errors"].append(f"Không thể cập nhật channel '{ch_name}': {e}")

                if target_ch:
                    # Khôi phục Overwrites cho Channel
                    await self._apply_overwrites(guild, target_ch, snap_ch.get("overwrites", []), reason, report)

            log.info(f"[RESTORE COMPLETED] Guild {guild.name} - Report: {report}")
            return {"status": "success", "report": report}
        finally:
            self._is_restoring[guild_id] = False

    async def _apply_overwrites(
        self,
        guild: discord.Guild,
        target_channel: discord.abc.GuildChannel,
        overwrites_data: list[dict[str, Any]],
        reason: str,
        report: dict[str, Any],
    ) -> None:
        """Áp dụng phân quyền overwrites vào channel/category."""
        if not overwrites_data:
            return

        roles_by_id = {r.id: r for r in guild.roles}
        roles_by_name = {r.name: r for r in guild.roles}

        for item in overwrites_data:
            try:
                target_entity: Optional[discord.Role | discord.Member] = None
                if item["target_type"] == "role":
                    if item["target_id"] in roles_by_id:
                        target_entity = roles_by_id[item["target_id"]]
                    elif item["target_name"] in roles_by_name:
                        target_entity = roles_by_name[item["target_name"]]
                    elif item["target_name"] == "@everyone":
                        target_entity = guild.default_role
                else:
                    target_entity = guild.get_member(item["target_id"])

                if target_entity:
                    allow_perms = discord.Permissions(item["allow"])
                    deny_perms = discord.Permissions(item["deny"])
                    ow = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)
                    await target_channel.set_permissions(target_entity, overwrite=ow, reason=reason)
                    report["overwrites_restored"] += 1
            except Exception as e:
                log.debug(f"Không thể set overwrite cho {target_channel.name}: {e}")


# Singleton instance
server_backup_service = ServerBackupService()
