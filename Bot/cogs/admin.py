"""Admin and Owner Operations Cog with 100% Vietnamese localization."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings, AI_MODEL_NAME
from database.database import async_session_factory, init_db
from database.repositories.user_repo import UserRepository
from services.role_manager import RoleManager
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger
from utils.permissions import is_admin_or_owner

logger = get_logger("AdminCog")


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path_size(p: str | Path) -> int:
    """Đo dung lượng file/thư mục (resolve theo project root, bỏ qua lỗi quyền)."""
    target = Path(p)
    if not target.is_absolute():
        target = PROJECT_ROOT / p
    try:
        if not target.exists():
            return 0
        if target.is_file():
            return target.stat().st_size
        total = 0
        for f in target.rglob("*"):
            try:
                if f.is_file() and not f.is_symlink():
                    total += f.stat().st_size
            except Exception:
                pass
        return total
    except Exception:
        return 0


def _fmt_bytes(b: int | float) -> str:
    if b >= 1024 ** 3:
        return f"{b / (1024 ** 3):.2f} GB"
    elif b >= 1024 ** 2:
        return f"{b / (1024 ** 2):.2f} MB"
    elif b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{int(b)} Bytes"


def get_system_storage_breakdown() -> dict[str, Any]:
    """Tính toán dung lượng lưu trữ thực tế từng phần của bot (MB / GB).

    Chạy hàm này trong thread riêng (asyncio.to_thread) vì rglob lên
    thư mục models/ nhiều GB có thể chặn event loop vài giây.
    """
    ai_problems_bytes = _path_size("data/ai_problems.json")
    db_bytes = sum(
        _path_size(p) for p in ("bot.db", "bot.db-wal", "bot.db-shm", "bot.db-journal")
    )
    kb_bytes = _path_size("data/knowledge_base")
    data_other_bytes = max(0, _path_size("data") - ai_problems_bytes - kb_bytes)
    logs_bytes = _path_size("logs")
    models_bytes = _path_size("models")
    ollama_bin_bytes = _path_size("ollama_bin")
    ffmpeg_bytes = _path_size("ffmpeg")
    cache_bytes = (
        _path_size("__pycache__") + _path_size(".pytest_cache") + _path_size(".ruff_cache")
    )
    bak_bytes = 0
    try:
        for f in PROJECT_ROOT.rglob("*.bak"):
            try:
                if f.is_file():
                    bak_bytes += f.stat().st_size
            except Exception:
                pass
    except Exception:
        pass
    project_total_bytes = _path_size(PROJECT_ROOT)

    parts = [
        ("ai_problems", "📑 Kho đề Ranked 1:1", ai_problems_bytes),
        ("database", "🗄️ Database SQLite", db_bytes),
        ("knowledge_base", "📚 Knowledge Base (RAG)", kb_bytes),
        ("data_other", "📁 Dữ liệu khác (data/)", data_other_bytes),
        ("logs", "📋 Logs", logs_bytes),
        ("models", "🤖 Models AI (models/)", models_bytes),
        ("ollama_bin", "🦙 Ollama portable", ollama_bin_bytes),
        ("ffmpeg", "🎵 FFmpeg", ffmpeg_bytes),
        ("caches", "🧹 Cache (pycache/pytest)", cache_bytes),
        ("backups", "💾 File backup (*.bak)", bak_bytes),
    ]
    parts_detail = [
        {"key": key, "label": label, "bytes": size, "human": _fmt_bytes(size)}
        for key, label, size in parts
    ]

    max_ai_limit_bytes = 128 * 1024 * 1024
    ai_percent = min(100.0, (ai_problems_bytes / max_ai_limit_bytes) * 100)
    data_total_bytes = ai_problems_bytes + db_bytes + kb_bytes + data_other_bytes

    return {
        "ai_problems_human": _fmt_bytes(ai_problems_bytes),
        "ai_problems_percent": f"{ai_percent:.1f}%",
        "db_human": _fmt_bytes(db_bytes + kb_bytes + data_other_bytes),
        "models_human": _fmt_bytes(models_bytes),
        "total_human": _fmt_bytes(data_total_bytes + models_bytes),
        "parts": parts_detail,
        "project_total_human": _fmt_bytes(project_total_bytes),
        "project_total_bytes": project_total_bytes,
    }


class AdminCog(commands.Cog, name="Admin"):
    """Các lệnh quản trị, bảo trì và kiểm soát máy chủ chỉ dành cho Owner và Admin."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="reload",
        description="[Admin/Owner] Reload toàn bộ bot, cogs, database và làm mới 5 kênh giao diện",
    )
    async def reload(self, interaction: discord.Interaction) -> None:
        """Lệnh reload duy nhất toàn diện hệ thống (Chỉ dành cho Administrator và Bot Owner)."""
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối truy cập:** Bạn cần có quyền **Quản trị viên (Administrator)** hoặc là **Bot Owner** để sử dụng lệnh `/reload`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # 1. Khởi tạo & cập nhật schema database
        try:
            await init_db()
        except Exception as e:
            logger.error(f"Lỗi khi init_db trong reload: {e}")

        # 2. Hot-reload toàn bộ các Cogs với cơ chế AI Local Auto-Healing
        target_cogs: list[str] = []
        try:
            from bot import INITIAL_EXTENSIONS
            target_cogs = list(INITIAL_EXTENSIONS)
        except Exception:
            pass

        for ext in list(self.bot.extensions.keys()):
            if ext not in target_cogs and not ext.startswith("not_finished."):
                target_cogs.append(ext)

        for arch in ["cogs.profile", "cogs.ranked_duel"]:
            if arch in target_cogs:
                target_cogs.remove(arch)

        reloaded = []
        failed = []

        for cog in target_cogs:
            try:
                if cog in self.bot.extensions:
                    await self.bot.reload_extension(cog)
                else:
                    await self.bot.load_extension(cog)
                reloaded.append(cog)
            except Exception as e:
                try:
                    from services.self_healer import SelfHealer
                    healed = await SelfHealer.try_heal_extension(cog, e)
                    if healed:
                        if cog in self.bot.extensions:
                            await self.bot.reload_extension(cog)
                        else:
                            await self.bot.load_extension(cog)
                        reloaded.append(f"{cog} *(✨ AI Healed)*")
                        continue
                except Exception as heal_e:
                    logger.warning(f"Self-Healing thất bại cho {cog}: {heal_e}")

                logger.error(f"Lỗi khi reload cog {cog}: {e}")
                failed.append(f"`{cog}` ({e})")

        # 3. Làm mới các kênh giao diện cố định
        channel_status = []

        # 3.1. Kênh #✅・accounts (CF_ID)
        cf_cog = self.bot.get_cog("Codeforces")
        if cf_cog and hasattr(cf_cog, "auto_setup_cf_channel") and settings.CF_ID > 0:
            try:
                await cf_cog.auto_setup_cf_channel()
                channel_status.append(f"• <#{settings.CF_ID}>: Đã cập nhật ✅")
            except Exception as e:
                channel_status.append(f"• <#{settings.CF_ID}>: Lỗi (`{e}`) ❌")

        # 3.2. Kênh #📤・mode (CHON_ID)
        mode_cog = self.bot.get_cog("Mode Selection")
        if (
            mode_cog
            and hasattr(mode_cog, "auto_setup_chon_channel")
            and settings.CHON_ID > 0
        ):
            try:
                await mode_cog.auto_setup_chon_channel()
                channel_status.append(
                    f"• <#{settings.CHON_ID}>: Đã cập nhật (6 Embeds Sổ Tay) ✅"
                )
            except Exception as e:
                channel_status.append(f"• <#{settings.CHON_ID}>: Lỗi (`{e}`) ❌")

        # 3.3. Kênh #📝・submit (SUBMIT_ID)
        submit_cog = self.bot.get_cog("Submission")
        if (
            submit_cog
            and hasattr(submit_cog, "auto_setup_submit_channel")
            and settings.SUBMIT_ID > 0
        ):
            try:
                await submit_cog.auto_setup_submit_channel()
                channel_status.append(f"• <#{settings.SUBMIT_ID}>: Đã cập nhật ✅")
            except Exception as e:
                channel_status.append(f"• <#{settings.SUBMIT_ID}>: Lỗi (`{e}`) ❌")

        # 3.4. Kênh #🏆・up-rank (UP_RANK)
        leaderboard_cog = self.bot.get_cog("Leaderboard")
        if (
            leaderboard_cog
            and hasattr(leaderboard_cog, "auto_setup_rank_channel")
            and settings.UP_RANK > 0
        ):
            try:
                await leaderboard_cog.auto_setup_rank_channel()
                channel_status.append(
                    f"• <#{settings.UP_RANK}>: Đã cập nhật (2 Embeds: Freedom & Ranked 1:1, 45p) ✅"
                )
            except Exception as e:
                channel_status.append(f"• <#{settings.UP_RANK}>: Lỗi (`{e}`) ❌")

        # 3.5. Kênh #📚・bai-tap (BAITAP_ID)
        contest_cog = self.bot.get_cog("Contests & Problems")
        if (
            contest_cog
            and hasattr(contest_cog, "auto_setup_baitap_channel")
            and settings.BAITAP_ID > 0
        ):
            try:
                await contest_cog.auto_setup_baitap_channel()
                channel_status.append(
                    f"• <#{settings.BAITAP_ID}>: Đã cập nhật (3 Embeds Catalog) ✅"
                )
            except Exception as e:
                channel_status.append(f"• <#{settings.BAITAP_ID}>: Lỗi (`{e}`) ❌")

        # 3.6. Kênh #📋・ranked (RANKED_CHANNEL_ID)
        ranked_cog = self.bot.get_cog("RankedDuelCog")
        if (
            ranked_cog
            and hasattr(ranked_cog, "_auto_setup_ranked_channel")
            and settings.RANKED_CHANNEL_ID > 0
        ):
            try:
                await ranked_cog._auto_setup_ranked_channel()
                channel_status.append(
                    f"• <#{settings.RANKED_CHANNEL_ID}>: Đã cập nhật (Đấu Trường 1:1) ✅"
                )
            except Exception as e:
                channel_status.append(
                    f"• <#{settings.RANKED_CHANNEL_ID}>: Lỗi (`{e}`) ❌"
                )

        # 3.7. Kênh #📤・nộp-tài-liệu (DOC_INTAKE_CHANNEL_ID)
        doc_cog = self.bot.get_cog("DocumentIntakeCog")
        intake_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
        if (
            doc_cog
            and hasattr(doc_cog, "auto_setup_intake_channel")
            and intake_id > 0
        ):
            try:
                await doc_cog.auto_setup_intake_channel(purge=True)
                channel_status.append(
                    f"• <#{intake_id}>: Đã dọn sạch & làm mới Bảng Nộp Đề ✅"
                )
            except Exception as e:
                channel_status.append(f"• <#{intake_id}>: Lỗi (`{e}`) ❌")

        # 3.8. Kênh #📄・tra-cứu (DOC_SEARCH_CHANNEL_ID)
        search_cog = self.bot.get_cog("DocumentSearch")
        search_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1553678782101979186)
        if (
            search_cog
            and hasattr(search_cog, "auto_setup_search_channel")
            and search_id > 0
        ):
            try:
                await search_cog.auto_setup_search_channel(purge=True)
                channel_status.append(
                    f"• <#{search_id}>: Đã dọn sạch & làm mới Bảng Tra Cứu ✅"
                )
            except Exception as e:
                channel_status.append(f"• <#{search_id}>: Lỗi (`{e}`) ❌")

        # 3.9. Kênh #🔍・kiểm-tra-link (LINK_SCANNER_CHANNEL_ID)
        link_cog = self.bot.get_cog("LinkScannerCog")
        scanner_id = getattr(settings, "LINK_SCANNER_CHANNEL_ID", 1546522680638054461)
        if (
            link_cog
            and hasattr(link_cog, "auto_setup_scanner_channel")
            and scanner_id > 0
        ):
            try:
                await link_cog.auto_setup_scanner_channel(purge=True)
                channel_status.append(
                    f"• <#{scanner_id}>: Đã dọn sạch & làm mới Bảng Quét Link ✅"
                )
            except Exception as e:
                channel_status.append(f"• <#{scanner_id}>: Lỗi (`{e}`) ❌")

        # 4. Cắt lệnh ngoài allowlist + đồng bộ Slash Commands CHỈ khi có thay đổi (tránh spam API)
        synced_count = 0
        sync_note = "không đổi"
        try:
            from bot import prune_tree_commands
            prune_tree_commands(self.bot)
        except Exception as pe:
            logger.warning(f"Lỗi khi cắt slash commands trong reload: {pe}")

        try:
            import hashlib
            cmd_sigs = sorted([f"{c.name}:{c.description}" for c in self.bot.tree.get_commands()])
            current_hash = hashlib.md5("".join(cmd_sigs).encode("utf-8")).hexdigest()
            hash_file = Path("data/.tree_sync.hash")
            last_hash = hash_file.read_text("utf-8").strip() if hash_file.exists() else ""
            if current_hash != last_hash:
                synced = await self.bot.tree.sync()
                synced_count = len(synced)
                hash_file.parent.mkdir(parents=True, exist_ok=True)
                hash_file.write_text(current_hash, encoding="utf-8")
                sync_note = f"đã đồng bộ {synced_count} lệnh"
            else:
                synced_count = len(cmd_sigs)
        except Exception as e:
            logger.error(f"Lỗi khi đồng bộ slash commands trong reload: {e}")
            sync_note = f"lỗi đồng bộ ({e})"

        # 5. Phản hồi kết quả bằng Rich Embed
        total_cogs = len(target_cogs)
        fields = [
            {
                "name": "📦 Cogs Hot-Reload",
                "value": f"✅ Đã tải lại thành công **{len(reloaded)}/{total_cogs}** modules.\n"
                + (f"❌ Thất bại: {', '.join(failed)}" if failed else "Không có lỗi."),
                "inline": False,
            },
            {
                "name": "⚡ Slash Commands Gateway",
                "value": f"Giữ **{synced_count}** lệnh trong allowlist ({sync_note}).",
                "inline": False,
            },
        ]

        if channel_status:
            fields.append(
                {
                    "name": "🖥️ Tự Động Làm Mới 6 Kênh Giao Diện",
                    "value": "\n".join(channel_status),
                    "inline": False,
                }
            )

        embed = create_embed(
            title="RELOAD TOÀN BỘ BOT THÀNH CÔNG! 🔄",
            description=f"Hệ thống đã được làm mới toàn diện theo yêu cầu của {interaction.user.mention}.",
            embed_type=EmbedType.SUCCESS,
            fields=fields,
            color=0x00B894,
            footer_text="Lệnh Quản Trị Duy Nhất • Hot Reload & Channel Refresh (Admin/Owner Only)",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Tự động sao lưu CSDL bot.db và kho đề cục bộ
        try:
            from services.backup_service import backup_service
            asyncio.create_task(asyncio.to_thread(backup_service.create_local_backup))
        except Exception as be:
            logger.warning(f"Lỗi khi kích hoạt sao lưu trong reload: {be}")

    @app_commands.command(
        name="setpts",
        description="[Admin/Owner] Thiết lập điểm Rating (pts) và Rank cho một hoặc nhiều thành viên",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(
                name="🌟 Freedom Mode (Contest & Sync)", value="freedom"
            ),
            app_commands.Choice(name="⚔️ Ranked 1:1 Mode (Đấu Trường)", value="ranked"),
        ]
    )
    @app_commands.describe(
        user="Thành viên Discord cần set điểm",
        number="Số điểm Rating (pts) mới (ví dụ: 1500, 2400...)",
        mode="Chế độ thi đấu cần set điểm: Freedom Mode hay Ranked 1:1",
        more_users="Tag thêm các thành viên khác cách nhau bằng dấu cách nếu muốn set hàng loạt (Tùy chọn)",
    )
    async def setpts(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        number: int,
        mode: str = "freedom",
        more_users: str | None = None,
    ) -> None:
        """Thiết lập điểm Rating (pts) trực tiếp và cập nhật Rank tương ứng (Admin / Owner only)."""
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối truy cập:** Bạn cần quyền Quản trị viên (Administrator) hoặc Bot Owner để dùng lệnh `/setpts`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        import re

        from services.rank import (
            RANK_BADGES,
            RANK_COLORS,
            RANK_TITLES,
            get_rank_by_rating,
        )

        # Thu thập danh sách thành viên cần cập nhật
        target_members = [user]
        if more_users and interaction.guild:
            user_ids = re.findall(r"<@!?(\d+)>|\b(\d{17,20})\b", more_users)
            for m_match in user_ids:
                raw_id = m_match[0] or m_match[1]
                if raw_id:
                    uid = int(raw_id)
                    if uid != user.id:
                        mem = interaction.guild.get_member(uid)
                        if mem and mem not in target_members:
                            target_members.append(mem)

        new_rank = get_rank_by_rating(number)
        badge = RANK_BADGES.get(new_rank, "⭐")
        title = RANK_TITLES.get(new_rank, new_rank)
        color = RANK_COLORS.get(new_rank, 0x00B894)

        is_ranked_mode = mode == "ranked"
        mode_title = "⚔️ Ranked 1:1 Mode" if is_ranked_mode else "🌟 Freedom Mode"

        updated_mentions = []
        async with async_session_factory() as session:
            user_repo = UserRepository(session)
            for mem in target_members:
                db_u, _ = await user_repo.get_or_create(mem.id)
                if is_ranked_mode:
                    old_rating = db_u.ranked_rating
                    old_rank = db_u.ranked_rank
                    db_u.ranked_rating = number
                    db_u.ranked_rank = new_rank
                    db_u.ranked_max_rating = max(db_u.ranked_max_rating, number)
                    await session.commit()
                    if interaction.guild:
                        await RoleManager.sync_ranked_user_roles(
                            guild=interaction.guild,
                            member=mem,
                            old_rating=old_rating,
                            new_rating=number,
                            old_rank=old_rank,
                            new_rank=new_rank,
                            bot=self.bot,
                        )
                else:
                    old_rating = db_u.rating
                    old_rank = db_u.rank
                    await user_repo.set_rating_and_rank(mem.id, number, new_rank)
                    if interaction.guild:
                        await RoleManager.sync_user_roles(
                            guild=interaction.guild,
                            member=mem,
                            old_rating=old_rating,
                            new_rating=number,
                            old_rank=old_rank,
                            new_rank=new_rank,
                            bot=self.bot,
                        )
                updated_mentions.append(f"• {mem.mention} (`{mem.display_name}`)")

        fields = [
            {
                "name": "📈 Điểm Rating (pts) Mới",
                "value": f"`⭐ {number:,} pts`",
                "inline": True,
            },
            {
                "name": "👑 Bậc Rank Tương Ứng",
                "value": f"{badge} **{new_rank}** *({title})*",
                "inline": True,
            },
            {
                "name": f"👥 Danh Sách Áp Dụng ({len(target_members)} thành viên)",
                "value": "\n".join(updated_mentions),
                "inline": False,
            },
            {
                "name": "⚡ Tự Động Cập Nhật",
                "value": "Đã lưu vào Cơ Sở Dữ Liệu và tự động cấp Discord Role tương ứng trên Server!",
                "inline": False,
            },
        ]

        embed = create_embed(
            title=f"THIẾT LẬP ĐIỂM {mode_title.upper()} THÀNH CÔNG! 🎉",
            description=f"Quản trị viên {interaction.user.mention} đã thiết lập điểm Rating ({mode_title}) mới cho các thành viên.",
            embed_type=EmbedType.SUCCESS,
            fields=fields,
            color=color,
            footer_text=f"Lệnh Quản Trị /setpts ({mode_title}) • Admin & Owner Only",
        )
        await interaction.followup.send(embed=embed)


    @app_commands.command(
        name="status",
        description="[Admin] Xem cấu hình bot, trạng thái hệ thống & sức khỏe các dịch vụ",
    )
    async def status(self, interaction: discord.Interaction) -> None:
        """Hiển thị cấu hình và sức khỏe hệ thống (chỉ Admin/Owner, không gọi AI nên luôn nhanh)."""
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối truy cập:** Bạn cần quyền **Quản trị viên (Administrator)** hoặc là **Bot Owner**.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            import sys
            import time
            import discord as _dc

            from bot import COMMAND_ALLOWLIST
            from services import api_bridge as _bridge

            bot = self.bot
            try:
                latency_ms = round(bot.latency * 1000, 1)
            except Exception:
                latency_ms = 0.0
            uptime_s = int(time.time() - _bridge.START_TIME)
            h, rem = divmod(uptime_s, 3600)
            m, s = divmod(rem, 60)

            guild = interaction.guild
            slash_kept = sorted(c.name for c in bot.tree.get_commands())
            cogs_loaded = sorted(bot.extensions.keys())

            db_size = "?"
            try:
                db_size = f"{os.path.getsize('data/bot.db') / (1024 * 1024):.1f} MB"
            except OSError:
                pass

            fields = [
                {
                    "name": "🤖 Bot & Kết Nối",
                    "value": (
                        f"• **Bot:** `{bot.user}` (ID `{bot.user.id if bot.user else '?'}`)\n"
                        f"• **Server:** `{guild.name if guild else '?'} ({len(bot.guilds)} guild)`\n"
                        f"• **Ping:** `{latency_ms} ms` • **Uptime:** `{h}h {m}m {s}s`\n"
                        f"• **API Bridge:** `http://{settings.BOT_API_HOST}:{settings.BOT_API_PORT}`"
                    ),
                    "inline": False,
                },
                {
                    "name": "⚙️ Cấu Hình Chính",
                    "value": (
                        f"• **Prefix:** đã tắt (slash-only) • **Slash giữ lại:** `{len(slash_kept)}` lệnh\n"
                        f"• **Cogs:** `{len(cogs_loaded)}` modules • **CSDL:** `{db_size}`\n"
                        f"• **Cooldown nộp bài:** `{settings.SUBMIT_COOLDOWN_SECONDS}s` • **CF sync:** `{settings.CF_SYNC_INTERVAL_SECONDS}s`\n"
                        f"• **Anti-raid/spam:** `{settings.ANTI_RAID_ENABLED}/{settings.ANTI_SPAM_ENABLED}` • **Log:** `{settings.LOG_LEVEL}`"
                    ),
                    "inline": False,
                },
                {
                    "name": "📌 Slash Đang Hoạt Động",
                    "value": " ".join(f"`/{n}`" for n in slash_kept) or "*trống*",
                    "inline": False,
                },
                {
                    "name": "🧩 Môi Trường",
                    "value": f"• **Python:** `{sys.version.split()[0]}` • **discord.py:** `{_dc.__version__}`",
                    "inline": False,
                },
            ]
            _ = COMMAND_ALLOWLIST  # giữ tham chiếu allowlist chính chủ
            embed = create_embed(
                title="TRẠNG THÁI & CẤU HÌNH BOT 🖥️",
                description=f"Kiểm tra lúc <t:{int(time.time())}:R> bởi {interaction.user.mention}.",
                embed_type=EmbedType.INFO,
                fields=fields,
                color=0x2ECC71,
                footer_text="HyperHub System Status • Admin Only",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Lỗi /status: {e}", exc_info=True)
            await interaction.followup.send("⚠️ Không thể lấy trạng thái lúc này (đã ghi log).", ephemeral=True)



    @app_commands.command(
        name="tha",
        description="[Owner Only] Ân xá và gỡ bỏ lệnh cấm thi đấu cho một thành viên",
    )
    @app_commands.describe(user="Thành viên cần được ân xá gỡ lệnh cấm thi đấu")
    async def tha(self, interaction: discord.Interaction, user: discord.Member) -> None:
        """Lệnh ân xá Slash Command /tha {user} dành riêng cho Bot Owner."""
        if interaction.user.id != settings.OWNER_ID:
            await interaction.response.send_message(
                "❌ **Từ chối quyền hạn:** Lệnh ân xá `/tha` chỉ dành riêng cho **Bot Owner**!",
                ephemeral=True,
            )
            return

        async with async_session_factory() as session:
            repo = UserRepository(session)
            await repo.pardon_user(user.id)

        embed = create_embed(
            title="🕊️ ÂN XÁ & GỠ CẤM THI ĐẤU THÀNH CÔNG",
            description=(
                f"Đã gỡ bỏ toàn bộ lệnh cấm thi đấu cho {user.mention} thành công!\n\n"
                f"• 👤 **Thí sinh:** {user.mention} (`{user.id}`)\n"
                f"• 🔓 **Trạng thái:** Đã mở khóa quyền tham gia **Đấu Trường Ranked 1:1** và **Freedom**.\n"
                f"• 👑 **Người thi hành ân xá:** {interaction.user.mention} *(Bot Owner)*\n\n"
                f"💡 *Chúc bạn thi đấu fair-play và đạt thành tích cao!*"
            ),
            embed_type=EmbedType.SUCCESS,
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="admin_list",
        description="[Admin/Owner] Thống kê số lượng đề bài Ranked 1:1 và tổng dung lượng dữ liệu (MB/GB)",
    )
    async def admin_list(self, interaction: discord.Interaction) -> None:
        """Hiển thị bảng thống kê số lượng đề bài Ranked 1:1 kèm tổng dung lượng MB/GB."""
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối truy cập:** Bạn cần có quyền **Quản trị viên (Administrator)** hoặc là **Bot Owner** để sử dụng lệnh này.",
                ephemeral=True,
            )
            return

        # Defer ngay lập tức để không bao giờ bị timeout Discord 3s.
        # Nếu event loop đang bận (> 3s) thì interaction đã hết hạn -> thoát êm.
        try:
            await interaction.response.defer(ephemeral=False)
        except discord.NotFound:
            logger.warning("[admin_list] Interaction hết hạn trước khi defer (10062).")
            return

        from services.duel_problems import PROBLEM_BANK

        total_count = len(PROBLEM_BANK)
        active_count = sum(1 for p in PROBLEM_BANK if getattr(p, "used_count", 0) < 3)
        retired_count = total_count - active_count

        # Tính toán dung lượng bất đồng bộ trong thread riêng
        storage = await asyncio.to_thread(get_system_storage_breakdown)

        # Đếm chi tiết từng Tier
        counts = {tier: sum(1 for p in PROBLEM_BANK if p.tier == tier) for tier in [
            "T8", "T7", "T6", "T5", "T4", "T3", "LT2", "MT2", "HT2", "LT1", "MT1", "HT1"
        ]}

        div4_total = counts["T8"] + counts["T7"] + counts["T6"]
        div3_total = counts["T5"] + counts["T4"] + counts["T3"]
        div2_total = counts["LT2"] + counts["MT2"] + counts["HT2"]
        div1_total = counts["LT1"] + counts["MT1"] + counts["HT1"]

        embed = create_embed(
            title="📋 THỐNG KÊ KHO ĐỀ BÀI RANKED 1:1 & DUNG LƯỢNG HỆ THỐNG",
            description=(
                f"📦 **Tổng số đề bài trong hệ thống:** **`{total_count}` bài**\n"
                f"• 🟢 **Đang sẵn sàng sử dụng (`< 3` lần):** `{active_count}` bài\n"
                f"• 🔴 **Đã về hưu (`= 3` lần):** `{retired_count}` bài\n\n"
                f"💾 **TỔNG DUNG LƯỢNG DỮ LIỆU TOÀN BỘ BOT:** **`{storage['total_human']}`**\n"
                f"• 📑 **Kho đề Ranked 1:1 (`ai_problems.json`):** `{storage['ai_problems_human']} / 128 MB` *({storage['ai_problems_percent']})*\n"
                f"• 🗄️ **Cơ sở dữ liệu SQLite & Cache (`bot.db` + `data/`):** `{storage['db_human']}`\n"
                f"• 🤖 **Bộ nhớ Mô hình AI Local (`models/`):** `{storage['models_human']}`\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"### 🟡 DIVISION 4 (`{div4_total}` bài • Rating 400 - 1000)\n"
                f"• ⭐ **T8:** `{counts['T8']}` | ⭐ **T7:** `{counts['T7']}` | ⭐ **T6:** `{counts['T6']}`\n\n"
                f"### 🔷 DIVISION 3 (`{div3_total}` bài • Rating 1250 - 1750)\n"
                f"• 🔷 **T5:** `{counts['T5']}` | 🔷 **T4:** `{counts['T4']}` | 🔷 **T3:** `{counts['T3']}`\n\n"
                f"### 🟣 DIVISION 2 (`{div2_total}` bài • Rating 2000 - 2350 • 3 Subtasks)\n"
                f"• 💎 **LT2:** `{counts['LT2']}` | 💎 **MT2:** `{counts['MT2']}` | 💎 **HT2:** `{counts['HT2']}`\n\n"
                f"### 🔴 DIVISION 1 (`{div1_total}` bài • Rating 2500 - 3000+ • 3 Subtasks)\n"
                f"• 👑 **LT1:** `{counts['LT1']}` | 👑 **MT1:** `{counts['MT1']}` | 👑 **HT1:** `{counts['HT1']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💡 *Mỗi đề được dùng tối đa 3 lần. Hệ thống tự động sinh bài mới khi kho cạn.*"
            ),
            embed_type=EmbedType.INFO,
            color=0x3498DB,
        )

        try:
            await interaction.followup.send(embed=embed)
        except discord.NotFound:
            logger.warning("[admin_list] Interaction hết hạn khi gửi followup (10062).")

    @app_commands.command(name="color", description="[Admin/Owner] Đổi màu chủ đề embed (VD: #9F7AEA)")
    @app_commands.describe(color="Mã màu #RRGGBB — để trống để xem màu hiện tại")
    async def color(self, interaction: discord.Interaction, color: str | None = None) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Bạn không có quyền sử dụng lệnh này.", ephemeral=True)
            return
        from utils import embeds, parsers
        current = embeds.get_theme_color()
        if not color:
            await interaction.response.send_message(
                embed=embeds.info(
                    f"Màu chủ đề hiện tại: `#{current:06X}`\n"
                    "Đổi màu: `/color #RRGGBB` (VD: `/color #9F7AEA`)",
                    title="Màu chủ đề",
                )
            )
            return
        value = parsers.parse_hex_color(color)
        if value is None:
            await interaction.response.send_message(
                embed=embeds.error("Định dạng màu không hợp lệ. VD: `#9F7AEA`, `9f7aea` hoặc `f8a`."),
                ephemeral=True,
            )
            return
        if hasattr(self.bot, "config"):
            await self.bot.config.set_embed_color(value)
        embeds.set_theme_color(value)
        embed = discord.Embed(
            title="Đã đổi màu chủ đề",
            description=f"Màu mới: `#{value:06X}`",
            color=value,
        )
        embeds.add_credit(embed, getattr(settings, "CREDIT", ""))
        embeds.attach_logo(embed)
        await interaction.response.send_message(embed=embed)



    @app_commands.command(
        name="auto_heal",
        description="[Admin] Kích hoạt AI Core quét & tự sửa lỗi cú pháp file",
    )
    @app_commands.describe(
        file_path="Đường dẫn tệp cần vá lỗi (Ví dụ: cogs/doc_intake.py hoặc bot.py)",
    )
    async def auto_heal(self, interaction: discord.Interaction, file_path: str) -> None:
        """Kích hoạt AI Core kiểm tra và sửa lỗi cú pháp trực tiếp theo yêu cầu."""
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ Bạn cần quyền Quản trị viên (Administrator) hoặc Bot Owner để dùng lệnh này!",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        from pathlib import Path
        from services.self_healer import SelfHealer

        p = Path(file_path)
        if not p.exists():
            await interaction.followup.send(f"❌ Không tìm thấy tệp `{file_path}`.", ephemeral=True)
            return

        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            await interaction.followup.send(f"❌ Không thể đọc tệp: `{e}`", ephemeral=True)
            return

        # Kiểm tra xem file có lỗi cú pháp không
        is_valid = SelfHealer.validate_python_code(content, str(p))
        if is_valid:
            await interaction.followup.send(
                f"✅ **Tệp `{p.name}` hoàn toàn hợp lệ!** Không phát hiện lỗi cú pháp nào.",
                ephemeral=True,
            )
            return

        # Thực hiện sửa bằng AI Core
        ai_model_name = AI_MODEL_NAME
        healed = await SelfHealer.heal_file(str(p), "Manual admin requested auto-heal", None)
        if healed:
            desc = (
                f"🤖 **Mô hình AI Core ({ai_model_name})** đã tự động sửa lỗi và ổn định tệp thành công!\n\n"
                f"• 📁 **Tệp đã xử lý:** `{p.name}`\n"
                f"• 🛡️ **Bảo toàn Embeds & UI:** Giữ nguyên 100% giao diện, logic và màu sắc.\n"
                f"• 💾 **Bản sao lưu dự phòng:** Đã lưu tại `{p.name}.bak`\n"
                f"• ✅ **Trạng thái:** Mã nguồn đã vượt qua kiểm tra cú pháp AST 100%!"
            )
            embed = create_embed(
                title="✨ AI CORE SELF-HEALING THÀNH CÔNG!",
                description=desc,
                embed_type=EmbedType.SUCCESS,
                color=0x2ECC71,
                footer_text=f"AI Core • {ai_model_name}",
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                f"⚠️ **Không thể tự động vá tệp `{p.name}`.** Vui lòng kiểm tra log chi tiết.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))


