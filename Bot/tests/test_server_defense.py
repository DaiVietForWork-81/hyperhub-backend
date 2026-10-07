"""
tests/test_server_defense.py
Unit tests cho hệ thống Anti-Spam, Anti-Raid, Anti-Nuke & Server Backup / 100% Restoration.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from services.anti_raid_service import AntiRaidService, SpamViolation
from services.server_backup_service import ServerBackupService, TamperAction


@pytest.fixture
def anti_raid():
    svc = AntiRaidService()
    svc.flood_threshold = 5
    svc.flood_window_seconds = 4.0
    svc.duplicate_threshold = 3
    svc.duplicate_window_seconds = 12.0
    svc.mass_mention_threshold = 4
    svc.join_flood_threshold = 5
    svc.join_flood_window_seconds = 10.0
    return svc


@pytest.fixture
def backup_service(tmp_path):
    svc = ServerBackupService()
    svc.backup_dir = tmp_path
    svc.nuke_threshold = 2
    svc.nuke_window_seconds = 10.0
    return svc


# =============================================================================
# 1. TEST ANTI-SPAM
# =============================================================================

def test_anti_spam_normal_message(anti_raid):
    mock_guild = MagicMock()
    mock_member = MagicMock()
    mock_member.guild_permissions.administrator = False
    mock_member.guild_permissions.mention_everyone = False
    mock_guild.get_member.return_value = mock_member

    mock_msg = MagicMock()
    mock_msg.guild = mock_guild
    mock_msg.author.id = 12345
    mock_msg.author.bot = False
    mock_msg.content = "Xin chào mọi người!"
    mock_msg.mention_everyone = False
    mock_msg.mentions = []

    violation = anti_raid.check_message_spam(mock_msg)
    assert violation is None


def test_anti_spam_admin_bypass(anti_raid):
    mock_guild = MagicMock()
    mock_member = MagicMock()
    mock_member.guild_permissions.administrator = True
    mock_guild.get_member.return_value = mock_member

    mock_msg = MagicMock()
    mock_msg.guild = mock_guild
    mock_msg.author.id = 99999
    mock_msg.author.bot = False
    mock_msg.content = "https://discord.gg/malicious-link @everyone"
    mock_msg.mention_everyone = True
    mock_msg.mentions = [MagicMock() for _ in range(10)]

    violation = anti_raid.check_message_spam(mock_msg)
    assert violation is None  # Admin được bypass


def test_anti_spam_mass_mention(anti_raid):
    mock_guild = MagicMock()
    mock_member = MagicMock()
    mock_member.guild_permissions.administrator = False
    mock_member.guild_permissions.mention_everyone = False
    mock_guild.get_member.return_value = mock_member

    mock_msg = MagicMock()
    mock_msg.guild = mock_guild
    mock_msg.author.id = 12345
    mock_msg.author.bot = False
    mock_msg.content = "Dậy đi mọi người ơi"
    mock_msg.mention_everyone = True
    mock_msg.mentions = []

    violation = anti_raid.check_message_spam(mock_msg)
    assert violation is not None
    assert violation.violation_type == "MASS_MENTION"


def test_anti_spam_invite_link(anti_raid):
    mock_guild = MagicMock()
    mock_member = MagicMock()
    mock_member.guild_permissions.administrator = False
    mock_member.guild_permissions.mention_everyone = False
    mock_guild.get_member.return_value = mock_member

    mock_msg = MagicMock()
    mock_msg.guild = mock_guild
    mock_msg.author.id = 12345
    mock_msg.author.bot = False
    mock_msg.content = "Vào server này nhận Nitro free: https://discord.gg/xyz123"
    mock_msg.mention_everyone = False
    mock_msg.mentions = []

    violation = anti_raid.check_message_spam(mock_msg)
    assert violation is not None
    assert violation.violation_type == "INVITE_SPAM"


def test_anti_spam_message_flood(anti_raid):
    mock_guild = MagicMock()
    mock_member = MagicMock()
    mock_member.guild_permissions.administrator = False
    mock_member.guild_permissions.mention_everyone = False
    mock_guild.get_member.return_value = mock_member

    user_id = 77777

    # Gửi 4 tin nhắn đầu -> Chưa vượt ngưỡng 5
    for i in range(4):
        msg = MagicMock()
        msg.guild = mock_guild
        msg.author.id = user_id
        msg.author.bot = False
        msg.content = f"tin nhắn số {i}"
        msg.mention_everyone = False
        msg.mentions = []
        assert anti_raid.check_message_spam(msg) is None

    # Tin nhắn thứ 5 dồn dập -> Vi phạm FLOOD
    msg5 = MagicMock()
    msg5.guild = mock_guild
    msg5.author.id = user_id
    msg5.author.bot = False
    msg5.content = "tin nhắn số 5"
    msg5.mention_everyone = False
    msg5.mentions = []
    v = anti_raid.check_message_spam(msg5)
    assert v is not None
    assert v.violation_type == "FLOOD"


def test_anti_spam_duplicate(anti_raid):
    mock_guild = MagicMock()
    mock_member = MagicMock()
    mock_member.guild_permissions.administrator = False
    mock_member.guild_permissions.mention_everyone = False
    mock_guild.get_member.return_value = mock_member

    user_id = 88888

    # Gửi 2 tin giống hệt -> Chưa vi phạm
    for _ in range(2):
        msg = MagicMock()
        msg.guild = mock_guild
        msg.author.id = user_id
        msg.author.bot = False
        msg.content = "đây là tin nhắn lặp"
        msg.mention_everyone = False
        msg.mentions = []
        assert anti_raid.check_message_spam(msg) is None

    # Lặp lần thứ 3 -> Vi phạm DUPLICATE
    msg3 = MagicMock()
    msg3.guild = mock_guild
    msg3.author.id = user_id
    msg3.author.bot = False
    msg3.content = "đây là tin nhắn lặp"
    msg3.mention_everyone = False
    msg3.mentions = []
    v = anti_raid.check_message_spam(msg3)
    assert v is not None
    assert v.violation_type == "DUPLICATE"


# =============================================================================
# 2. TEST ANTI-RAID
# =============================================================================

def test_anti_raid_join_flood(anti_raid):
    mock_guild = MagicMock()
    mock_guild.id = 1111

    # 4 user join đầu -> Chưa kích hoạt raid
    for i in range(4):
        member = MagicMock()
        member.guild = mock_guild
        member.id = 100 + i
        member.bot = False
        member.created_at = datetime.now(timezone.utc)
        is_raid, event = anti_raid.record_member_join(member)
        assert is_raid is False
        assert event is None

    # User thứ 5 join trong 10s -> Kích hoạt Raid Alert
    member5 = MagicMock()
    member5.guild = mock_guild
    member5.id = 105
    member5.bot = False
    member5.created_at = datetime.now(timezone.utc)
    is_raid, event = anti_raid.record_member_join(member5)
    assert is_raid is True
    assert event is not None
    assert len(event.involved_user_ids) >= 5


@pytest.mark.asyncio
async def test_anti_raid_purge_entities(anti_raid):
    mock_guild = MagicMock()
    mock_guild.id = 1111
    mock_guild.owner.id = 9999
    mock_guild.me.id = 8888

    # Target members
    m1 = AsyncMock()
    m1.id = 101
    m1.guild_permissions.administrator = False
    m2 = AsyncMock()
    m2.id = 102
    m2.guild_permissions.administrator = False

    def get_member_side_effect(uid):
        if uid == 101:
            return m1
        if uid == 102:
            return m2
        return None

    mock_guild.get_member.side_effect = get_member_side_effect
    mock_guild.ban = AsyncMock()

    success, failed = await anti_raid.purge_raid_entities(
        mock_guild, [101, 102], action="ban", reason="Test Raid Purge"
    )
    assert len(success) == 2
    assert 101 in success
    assert 102 in success
    assert m1.ban.called
    assert m2.ban.called


# =============================================================================
# 3. TEST SERVER SNAPSHOT & 100% RESTORATION
# =============================================================================

@pytest.mark.asyncio
async def test_server_snapshot_creation(backup_service):
    mock_guild = MagicMock()
    mock_guild.id = 999999
    mock_guild.name = "Test CP Arena Server"

    # Mock Role
    mock_role = MagicMock()
    mock_role.id = 111
    mock_role.name = "Học sinh"
    mock_role.color.value = 0x3498DB
    mock_role.permissions.value = 1049600
    mock_role.position = 1
    mock_role.hoist = True
    mock_role.mentionable = True
    mock_role.is_default.return_value = False
    mock_role.managed = False
    mock_guild.roles = [mock_role]

    # Mock Category
    mock_cat = MagicMock()
    mock_cat.id = 222
    mock_cat.name = "・━━ 💬 CỘNG ĐỒNG ━━・"
    mock_cat.position = 0
    mock_cat.overwrites = {}
    mock_guild.categories = [mock_cat]

    # Mock Channel
    mock_ch = MagicMock(spec=discord.TextChannel)
    mock_ch.id = 333
    mock_ch.name = "chat-chung"
    mock_ch.category_id = 222
    mock_ch.category = mock_cat
    mock_ch.position = 0
    mock_ch.topic = "Kênh chat tự do"
    mock_ch.nsfw = False
    mock_ch.slowmode_delay = 0
    mock_ch.overwrites = {}
    mock_guild.channels = [mock_ch]

    snapshot = await backup_service.create_snapshot(mock_guild, note="Test backup")
    assert snapshot["guild_id"] == 999999
    assert snapshot["counts"]["categories"] == 1
    assert snapshot["counts"]["channels"] == 1
    assert snapshot["counts"]["roles"] == 1

    loaded = backup_service.load_latest_snapshot(999999)
    assert loaded is not None
    assert loaded["guild_name"] == "Test CP Arena Server"


def test_tamper_detection(backup_service):
    guild_id = 12345
    actor_id = 55555

    # Lần xóa đầu tiên -> Chưa đạt ngưỡng 2
    is_nuke, actions = backup_service.record_tamper_event(
        guild_id, "CHANNEL_DELETE", actor_id, 101, "kênh 1"
    )
    assert is_nuke is False

    # Lần xóa thứ 2 trong 10s -> Kích hoạt Nuke Attack
    is_nuke2, actions2 = backup_service.record_tamper_event(
        guild_id, "CHANNEL_DELETE", actor_id, 102, "kênh 2"
    )
    assert is_nuke2 is True
    assert len(actions2) == 2


@pytest.mark.asyncio
async def test_restore_server_structure(backup_service):
    mock_guild = MagicMock()
    mock_guild.id = 888888
    mock_guild.name = "Restore Server"

    # Snapshot data
    snapshot_data = {
        "guild_id": 888888,
        "categories": [
            {
                "id": 1001,
                "name": "Thư Mục Đã Bị Xóa",
                "position": 0,
                "overwrites": [],
            }
        ],
        "channels": [
            {
                "id": 2001,
                "name": "kênh-đã-bị-xóa",
                "type": "text",
                "category_name": "Thư Mục Đã Bị Xóa",
                "category_id": 1001,
                "position": 0,
                "overwrites": [],
            },
            {
                "id": 2002,
                "name": "kênh-bị-đổi-tên",
                "type": "text",
                "category_name": "Thư Mục Đã Bị Xóa",
                "category_id": 1001,
                "position": 1,
                "overwrites": [],
            },
        ],
    }

    # Hiện tại server mất Category 1001 và Kênh 2001, nhưng Kênh 2002 còn (bị đổi tên thành "nuked-by-hacker")
    recreated_cat = MagicMock(spec=discord.CategoryChannel)
    recreated_cat.id = 9901
    recreated_cat.name = "Thư Mục Đã Bị Xóa"

    existing_ch2 = AsyncMock(spec=discord.TextChannel)
    existing_ch2.id = 2002
    existing_ch2.name = "nuked-by-hacker"  # Kẻ xấu đã đổi tên
    existing_ch2.category_id = None       # Kẻ xấu đã rút khỏi category

    mock_guild.categories = []  # Đã bị xóa sạch
    mock_guild.channels = [existing_ch2]
    mock_guild.roles = []

    mock_guild.create_category = AsyncMock(return_value=recreated_cat)
    mock_guild.create_text_channel = AsyncMock()

    result = await backup_service.restore_server_structure(mock_guild, snapshot_data=snapshot_data)

    assert result["status"] == "success"
    report = result["report"]
    # Đã tạo lại category bị xóa
    assert report["categories_created"] == 1
    # Đã tạo lại kênh bị xóa
    assert report["channels_created"] == 1
    # Đã đổi lại tên cũ cho kênh bị hacker đổi tên
    assert report["channels_renamed"] == 1
    # Đã đưa kênh trở lại đúng Thư mục cha
    assert report["channels_reparented"] == 1
