"""
Tests cho 4 tính năng mới:
1. Editorial & Code Mẫu theo ngôn ngữ qua DM (với Fallback View khi tắt DM).
2. Chế độ Khán Giả (Spectator Mode) cho Đấu Trường 1:1.
3. Tự động Sao lưu & Tự phục hồi CSDL (Backup & Self-Healing Restore).
4. Huy hiệu Win Streak rực lửa trên Thẻ Profile 4K.
"""

import asyncio
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from services.backup_service import DatabaseBackupService, compute_sha256, get_db_stats
from services.duel_problems import DuelProblem
from services.duel_service import DuelEditorialFallbackView, DuelSession, MatchmakingManager
from services.profile_card import ProfileCardGenerator


# =====================================================================
# 1. TEST BACKUP & SELF-HEALING RESTORE SERVICE
# =====================================================================
def test_backup_sha256_and_stats(tmp_path: Path):
    db_file = tmp_path / "test_bot.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob')")
    conn.commit()
    conn.close()

    stats = get_db_stats(db_file)
    assert stats["users"] == 2

    sha = compute_sha256(db_file)
    assert len(sha) == 64


def test_backup_create_local_and_rotate(tmp_path: Path, monkeypatch):
    test_backup_dir = tmp_path / "backups"
    test_backup_dir.mkdir()
    test_db = tmp_path / "bot.db"
    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    monkeypatch.setattr("services.backup_service.BACKUP_DIR", test_backup_dir)
    monkeypatch.setattr("services.backup_service.PRIMARY_DB_PATH", test_db)
    monkeypatch.setattr("services.backup_service.SECONDARY_DB_PATH", tmp_path / "data" / "bot.db")
    monkeypatch.setattr("services.backup_service.PROBLEMS_JSON_PATH", tmp_path / "ai_problems.json")
    monkeypatch.setattr("services.backup_service.MAX_LOCAL_BACKUPS", 3)

    service = DatabaseBackupService(channel_id=123456789)

    # Tạo 4 file backup khác thời gian, kiểm tra rotation giữ 3 file mới nhất
    for i in range(4):
        f = test_backup_dir / f"bot_backup_20260912_12000{i}.zip"
        f.write_text("dummy")
    service._rotate_local_backups()

    backups = list(test_backup_dir.glob("bot_backup_*.zip"))
    assert len(backups) == 3

    # Kiểm tra create_local_backup tạo zip hợp lệ
    zip_path, meta = service.create_local_backup()
    assert zip_path.exists()
    assert meta["size_bytes"] > 0


@pytest.mark.asyncio
async def test_backup_restore_from_discord_mock(tmp_path: Path, monkeypatch):
    test_root = tmp_path / "project"
    test_root.mkdir()
    test_backup_dir = test_root / "backups"
    test_backup_dir.mkdir()
    primary_db = test_root / "bot.db"
    sec_dir = test_root / "data"
    sec_dir.mkdir()
    sec_db = sec_dir / "bot.db"

    # Tạo zip mẫu
    sample_db = tmp_path / "sample.db"
    conn = sqlite3.connect(sample_db)
    conn.execute("CREATE TABLE test (val TEXT)")
    conn.execute("INSERT INTO test VALUES ('restored_ok')")
    conn.commit()
    conn.close()

    sample_zip = tmp_path / "bot_backup_20260912_120000.zip"
    with zipfile.ZipFile(sample_zip, "w") as zf:
        zf.write(sample_db, arcname="bot.db")

    monkeypatch.setattr("services.backup_service.PROJECT_ROOT", test_root)
    monkeypatch.setattr("services.backup_service.BACKUP_DIR", test_backup_dir)
    monkeypatch.setattr("services.backup_service.PRIMARY_DB_PATH", primary_db)
    monkeypatch.setattr("services.backup_service.SECONDARY_DB_PATH", sec_db)

    service = DatabaseBackupService(channel_id=999)

    # Giả lập Discord message và attachment
    mock_att = MagicMock()
    mock_att.filename = "bot_backup_20260912_120000.zip"
    mock_att.size = sample_zip.stat().st_size

    async def mock_save(path_str):
        shutil.copy2(sample_zip, path_str)

    mock_att.save = AsyncMock(side_effect=mock_save)

    mock_msg = MagicMock()
    mock_msg.attachments = [mock_att]

    async def mock_history(limit=50):
        yield mock_msg

    mock_channel = MagicMock()
    mock_channel.name = "backup-log"
    mock_channel.history = mock_history

    mock_bot = MagicMock()
    mock_bot.get_channel.return_value = mock_channel

    success = await service.restore_latest_from_discord(mock_bot)
    assert success is True
    assert primary_db.exists()
    assert sec_db.exists()

    # Kiểm tra nội dung CSDL sau khi restore
    conn = sqlite3.connect(primary_db)
    row = conn.execute("SELECT val FROM test").fetchone()
    conn.close()
    assert row[0] == "restored_ok"


# =====================================================================
# 2. TEST EDITORIAL & MULTI-LANGUAGE CODE MẪU
# =====================================================================
def test_duel_problem_solutions_by_lang():
    prob = DuelProblem(
        id="TEST_01",
        name="Thuật Toán Đếm Đảo",
        tier="T5",
        division="Div. 3",
        rating_display="T5 / 1300 pts",
        statement="Cho ma trận nhị phân kích thước N x M...",
        input_format="Dòng đầu gồm N, M...",
        output_format="In số lượng vùng...",
        constraints="1 <= N, M <= 1000",
        sample_input="3 3\n1 1 0\n0 1 0\n0 0 1",
        sample_output="2",
        hint="Sử dụng thuật toán BFS hoặc DFS kết hợp mảng đánh dấu visited.",
        solution_py="def solve():\n    pass",
        solution_cpp="#include <iostream>\nint main() { return 0; }",
    )

    # Test Python
    code_py, syn_py = prob.get_solution_for_lang("python")
    assert syn_py == "python"
    assert "def solve():" in code_py

    # Test C++
    code_cpp, syn_cpp = prob.get_solution_for_lang("cpp")
    assert syn_cpp == "cpp"
    assert "#include <iostream>" in code_cpp

    # Test Java
    code_java, syn_java = prob.get_solution_for_lang("java")
    assert syn_java == "java"
    assert "public class Main" in code_java

    # Test Pascal
    code_pas, syn_pas = prob.get_solution_for_lang("pascal")
    assert syn_pas == "pascal"
    assert "program Solution;" in code_pas

    # Test Editorial Text
    ed_text = prob.editorial_text
    assert "Ý TƯỞNG THUẬT TOÁN TRỌNG TÂM" in ed_text
    assert prob.hint in ed_text


@pytest.mark.asyncio
async def test_editorial_fallback_view():
    target_user = MagicMock(spec=discord.Member)
    target_user.id = 111
    target_user.mention = "<@111>"

    other_user = MagicMock(spec=discord.Member)
    other_user.id = 222

    sample_embed = discord.Embed(title="Editorial Chặng 1")
    view = DuelEditorialFallbackView(target_user=target_user, embeds=[sample_embed])

    # Case 1: Người khác bấm -> bị từ chối
    mock_inter_other = AsyncMock(spec=discord.Interaction)
    mock_inter_other.user = other_user
    mock_inter_other.response = AsyncMock()

    btn = view.children[0]
    await btn.callback(mock_inter_other)
    mock_inter_other.response.send_message.assert_called_once()
    args, kwargs = mock_inter_other.response.send_message.call_args
    assert "chỉ dành riêng" in args[0]

    # Case 2: Đúng target user bấm -> nhận embeds
    mock_inter_target = AsyncMock(spec=discord.Interaction)
    mock_inter_target.user = target_user
    mock_inter_target.response = AsyncMock()

    await btn.callback(mock_inter_target)
    mock_inter_target.response.send_message.assert_called_once()
    _, kwargs_target = mock_inter_target.response.send_message.call_args
    assert "embeds" in kwargs_target
    assert kwargs_target["embeds"][0].title == "Editorial Chặng 1"


@pytest.mark.asyncio
async def test_send_private_match_editorial_dm_and_fallback():
    bot = MagicMock()
    guild = MagicMock(spec=discord.Guild)
    p1 = AsyncMock(spec=discord.Member)
    p1.id = 1001
    p1.display_name = "PlayerOne"
    p1.mention = "<@1001>"

    p2 = AsyncMock(spec=discord.Member)
    p2.id = 1002
    p2.display_name = "PlayerTwo"
    p2.mention = "<@1002>"

    channel = AsyncMock(spec=discord.TextChannel)

    session = DuelSession(
        bot=bot,
        guild=guild,
        player1=p1,
        player2=p2,
        p1_ranked_rank="T6",
        p1_ranked_rating=1000,
        p2_ranked_rank="T6",
        p2_ranked_rating=1020,
    )
    session.channel = channel
    session.user_preferred_lang[1001] = "python"
    session.user_preferred_lang[1002] = "cpp"

    prob = DuelProblem(
        id="P1",
        name="Tháp Hà Nội",
        tier="T6",
        division="Div. 4",
        rating_display="T6 / 1000 pts",
        statement="Giải bài toán tháp Hà Nội...",
        input_format="1 số N",
        output_format="Số bước",
        constraints="1 <= N <= 20",
        sample_input="3",
        sample_output="7",
    )
    session.problems_played.append(prob)

    # P1 nhận DM thành công, P2 bị Forbidden (tắt DM) -> kích hoạt fallback view
    p1.send = AsyncMock()
    p2.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Cannot send DM"))

    await session._send_private_match_editorial(
        winner=p1,
        loser=p2,
        winner_delta=60.0,
        loser_delta=-60.0,
        winner_new_rank="T5",
        loser_new_rank="T7",
        winner_streak=3,
    )

    # P1 phải nhận được DM
    p1.send.assert_called_once()
    _, p1_kwargs = p1.send.call_args
    assert len(p1_kwargs["embeds"]) >= 2
    assert "CHIẾN THẮNG" in p1_kwargs["embeds"][0].description
    assert "PYTHON" in p1_kwargs["embeds"][1].description

    # P2 phải kích hoạt fallback tin nhắn trong channel
    channel.send.assert_called_once()
    _, ch_kwargs = channel.send.call_args
    assert isinstance(ch_kwargs["view"], DuelEditorialFallbackView)
    assert ch_kwargs["view"].target_user.id == p2.id


# =====================================================================
# 3. TEST SPECTATOR MODE IN RANKED ARENA
# =====================================================================
@pytest.mark.asyncio
async def test_spectator_mode():
    from cogs.ranked_duel import RankedArenaView

    bot = MagicMock()
    matchmaker = MatchmakingManager(bot)
    view = RankedArenaView(matchmaker)

    spectator = MagicMock(spec=discord.Member)
    spectator.id = 9999
    spectator.display_name = "KhánGiả"

    inter = AsyncMock(spec=discord.Interaction)
    inter.user = spectator
    inter.response = AsyncMock()
    inter.followup = AsyncMock()

    spectate_btn = [c for c in view.children if getattr(c, "custom_id", None) == "btn_ranked_spectate_random"][0]

    # Case 1: Không có trận nào đang đấu
    await spectate_btn.callback(inter)
    inter.followup.send.assert_called_once()
    args, _ = inter.followup.send.call_args
    assert "không có trận đấu" in args[0]

    # Case 2: Có 1 trận đang đấu -> Cấp quyền read_messages=True, send_messages=False, add_reactions=False
    inter.followup.reset_mock()

    p1 = MagicMock(spec=discord.Member)
    p1.id = 101
    p1.display_name = "PlayerA"

    p2 = MagicMock(spec=discord.Member)
    p2.id = 102
    p2.display_name = "PlayerB"

    duel_channel = AsyncMock(spec=discord.TextChannel)
    duel_channel.mention = "<#777>"

    duel = DuelSession(
        bot=bot,
        guild=MagicMock(),
        player1=p1,
        player2=p2,
        p1_ranked_rank="T4",
        p1_ranked_rating=1500,
        p2_ranked_rank="T4",
        p2_ranked_rating=1520,
    )
    duel.channel = duel_channel
    duel.is_active = True
    matchmaker.active_sessions[777] = duel

    await spectate_btn.callback(inter)

    # Đảm bảo set_permissions được gọi với quyền xem nhưng cấm chat/react
    duel_channel.set_permissions.assert_called_once()
    perm_target, perm_kwargs = duel_channel.set_permissions.call_args
    assert perm_target[0] == spectator
    assert perm_kwargs.get("read_messages") is True
    assert perm_kwargs.get("send_messages") is False
    assert perm_kwargs.get("add_reactions") is False

    # Phản hồi embed chỉ dẫn
    inter.followup.send.assert_called_once()
    _, f_kwargs = inter.followup.send.call_args
    assert "CHẾ ĐỘ KHÁN GIẢ" in f_kwargs["embed"].title


# =====================================================================
# 4. TEST PROFILE CARD WITH WIN STREAK PILL (4K CARD)
# =====================================================================
@pytest.mark.asyncio
async def test_profile_card_with_win_streak():
    # Case 1: Thí sinh có chuỗi thắng ranked_streak = 5 (>= 2) kèm Special Role
    card_path = await ProfileCardGenerator.generate_profile_card(
        user_id=123456789,
        display_name="CodeMasterPro",
        avatar_url=None,
        joined_at_str="12/05/2024",
        standing=3,
        overall_pts=1325.0,
        freedom_tier="T5",
        freedom_rating=1200,
        ranked_tier="T4",
        ranked_rating=1450,
        ranked_streak=5,
        special_role="outclassed",
        force_refresh=True,
    )
    assert os.path.exists(card_path)
    assert os.path.getsize(card_path) > 10000

    # Case 2: Thí sinh có chuỗi thắng = 7 nhưng không có special role
    card_path2 = await ProfileCardGenerator.generate_profile_card(
        user_id=987654321,
        display_name="NoobHacker",
        avatar_url=None,
        joined_at_str="10/01/2024",
        standing=50,
        overall_pts=850.0,
        freedom_tier="T8",
        freedom_rating=800,
        ranked_tier="T7",
        ranked_rating=900,
        ranked_streak=7,
        special_role=None,
        force_refresh=True,
    )
    assert os.path.exists(card_path2)
    assert os.path.getsize(card_path2) > 10000
