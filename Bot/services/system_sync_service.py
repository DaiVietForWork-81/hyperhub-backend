"""Dịch vụ Đồng Bộ & Cập Nhật Hệ Thống HyperHub (System Sync & Updater Service).

Điều phối thông báo khởi động vào kênh Discord, kiểm tra cập nhật GitHub tự động,
đồng bộ hai chiều giữa Web Portal (Vercel) và Discord Bot, và cung cấp cơ chế
hot-reload / 1-click update tối ưu hóa toàn diện.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands
from config.settings import settings
from utils.permissions import is_admin_or_owner

logger = logging.getLogger("system_sync")

# Các đường dẫn Vercel chính thức
VERCEL_BASE_URL = "https://hyperhub-one.vercel.app"
VERCEL_VAULT_URL = "https://hyperhub-one.vercel.app/#vault"
VERCEL_ADMIN_URL = "https://hyperhub-one.vercel.app/#admin"
DEFAULT_SYNC_CHANNEL_ID = 1536199276273860638
GITHUB_REPO_URL = "https://github.com/DaiVietForWork-81/hyperhub-bot.git"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_git_cmd(args: List[str], timeout: float = 15.0) -> Optional[str]:
    """Chạy lệnh git an toàn trong thư mục gốc của bot."""
    git_bin = shutil.which("git")
    if not git_bin:
        return None
    try:
        res = subprocess.run(
            [git_bin] + args,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        if res.returncode == 0:
            return res.stdout.strip()
        logger.debug("Git command %s returned %d: %s", args, res.returncode, res.stderr)
        return None
    except Exception as e:
        logger.debug("Lỗi chạy lệnh git %s: %s", args, e)
        return None


class SystemSyncService:
    """Singleton quản lý thông báo, cập nhật GitHub và hot-reload bot."""

    def __init__(self) -> None:
        self.pending_update: Optional[Dict[str, Any]] = None
        self._last_notified_remote_hash: str = ""
        self._update_lock = asyncio.Lock()
        self._checker_started: bool = False
        self._last_check_time: float = 0.0

    # =========================================================================
    # 1. THÔNG TIN GIT & PHIÊN BẢN
    # =========================================================================

    async def get_current_git_info(self) -> Dict[str, str]:
        """Lấy thông tin phiên bản git hiện tại của bot."""
        def _get():
            short_hash = _run_git_cmd(["rev-parse", "--short", "HEAD"]) or "dev"
            full_hash = _run_git_cmd(["rev-parse", "HEAD"]) or "dev"
            commit_msg = _run_git_cmd(["log", "-1", "--pretty=format:%s (%cr)"]) or "Chưa rõ commit"
            branch = _run_git_cmd(["rev-parse", "--abbrev-ref", "HEAD"]) or "main"
            return {
                "hash": short_hash,
                "full_hash": full_hash,
                "commit_msg": commit_msg,
                "branch": branch,
            }
        return await asyncio.to_thread(_get)

    async def check_github_update(self) -> Dict[str, Any]:
        """Kiểm tra xem trên GitHub repo có commit mới hay không."""
        def _check():
            git_bin = shutil.which("git")
            if not git_bin:
                return {
                    "has_update": False,
                    "error": "Git không được cài đặt trên hệ thống máy chủ",
                    "local_hash": "unknown",
                    "remote_hash": "unknown",
                    "commits": [],
                }

            # Fetch origin main
            _run_git_cmd(["fetch", "origin", "main", "--quiet"], timeout=15.0)

            local_hash = _run_git_cmd(["rev-parse", "HEAD"]) or ""
            remote_hash = _run_git_cmd(["rev-parse", "origin/main"]) or ""
            short_local = local_hash[:8] if local_hash else "unknown"
            short_remote = remote_hash[:8] if remote_hash else "unknown"

            has_update = bool(local_hash and remote_hash and local_hash != remote_hash)
            commits: List[str] = []

            if has_update:
                raw_commits = _run_git_cmd(
                    ["log", "-n", "5", "--pretty=format:• [%h] %s (%cr)", f"{local_hash}..origin/main"]
                )
                if raw_commits:
                    commits = [c.strip() for c in raw_commits.split("\n") if c.strip()]

            return {
                "has_update": has_update,
                "local_hash": short_local,
                "remote_hash": short_remote,
                "full_local_hash": local_hash,
                "full_remote_hash": remote_hash,
                "commits": commits,
                "checked_at": int(time.time()),
            }

        result = await asyncio.to_thread(_check)
        self._last_check_time = time.time()
        if result.get("has_update"):
            self.pending_update = result
        else:
            self.pending_update = None
        return result

    # =========================================================================
    # 2. GỬI THÔNG BÁO KHỞI ĐỘNG VÀO KÊNH 1536199276273860638
    # =========================================================================

    async def send_startup_announcement(self, bot: commands.Bot) -> bool:
        """Gửi thông báo khởi động kèm link Vercel và hệ thống vào kênh đồng bộ."""
        await bot.wait_until_ready()
        await asyncio.sleep(2.0)  # Đợi nhẹ để API bridge và DB ổn định

        sync_channel_id = getattr(settings, "SYSTEM_SYNC_CHANNEL_ID", DEFAULT_SYNC_CHANNEL_ID)
        channel = bot.get_channel(sync_channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(sync_channel_id)
            except Exception as e:
                logger.warning("Không tìm thấy kênh đồng bộ hệ thống ID %s: %s", sync_channel_id, e)
                return False

        git_info = await self.get_current_git_info()
        ping_ms = round(bot.latency * 1000, 1) if hasattr(bot, "latency") else 0.0
        cogs_count = len(bot.extensions)
        cmds_count = len(bot.tree.get_commands())
        guilds_count = len(bot.guilds)

        embed = discord.Embed(
            title="🚀 ORBIT SYSTEM ONLINE & ĐỒNG BỘ DISCORD",
            description=(
                "**Hệ thống Discord Bot & Web Portal đã khởi động thành công và đồng bộ hai chiều!**\n"
                "Toàn bộ tài liệu, kiểm định AI/C++ và bảng điều khiển quản trị đã sẵn sàng phục vụ."
            ),
            color=0x10B981,  # Emerald Green
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name="🌐 Cổng Web Vercel Trực Tuyến",
            value=(
                f"• **Kho Đề & Tra Cứu:** [hyperhub-one.vercel.app/#vault]({VERCEL_VAULT_URL})\n"
                f"• **Bảng Quản Trị (Admin Hub):** [hyperhub-one.vercel.app/#admin]({VERCEL_ADMIN_URL})\n"
                f"• **Trang Chủ:** [{VERCEL_BASE_URL}]({VERCEL_BASE_URL})"
            ),
            inline=False,
        )

        embed.add_field(
            name="🤖 Trạng Thái Bot Discord",
            value=(
                f"• **Danh tính:** `{bot.user}` *(ID: `{bot.user.id if bot.user else 0}`)*\n"
                f"• **Độ trễ Gateway (Ping):** `{ping_ms} ms`\n"
                f"• **Máy chủ kết nối:** `{guilds_count}` Guild(s)"
            ),
            inline=True,
        )

        embed.add_field(
            name="📦 Mã Nguồn & Cấu Trúc",
            value=(
                f"• **Bản Git:** `{git_info['hash']}` ({git_info['branch']})\n"
                f"• **Modules (Cogs):** `{cogs_count}` modules\n"
                f"• **Slash Commands:** `{cmds_count}` lệnh trong allowlist"
            ),
            inline=True,
        )

        embed.add_field(
            name="⚙️ Hạ Tầng Đồng Bộ",
            value=(
                "• **Cơ sở dữ liệu:** Turso libSQL Cloud + SQLite FTS5 (Tiếng Việt không dấu)\n"
                "• **Lõi xử lý cao tốc:** C++ Native Core (Fast SHA-256 + Magic Header Guard)\n"
                "• **API Bridge:** Sẵn sàng kết nối Web qua Tunnel HTTPS & Ngrok"
            ),
            inline=False,
        )

        if git_info.get("commit_msg"):
            embed.set_footer(
                text=f"Git commit: {git_info['commit_msg']} • Orbit Ecosystem",
                icon_url=bot.user.display_avatar.url if bot.user else None,
            )

        view = SystemControlView()
        try:
            await channel.send(embed=embed, view=view)
            logger.info("✅ Đã gửi thông báo khởi động và link Vercel vào kênh #%s thành công!", sync_channel_id)
            return True
        except Exception as e:
            logger.error("Lỗi khi gửi thông báo khởi động vào kênh #%s: %s", sync_channel_id, e)
            return False

    # =========================================================================
    # 3. BACKGROUND TASK: GIÁM SÁT BẢN CẬP NHẬT GITHUB ĐỊNH KỲ
    # =========================================================================

    async def start_periodic_update_checker(self, bot: commands.Bot, interval_seconds: int = 300) -> None:
        """Vòng lặp kiểm tra cập nhật GitHub mỗi 5 phút trong nền (Zero CPU overhead)."""
        if self._checker_started:
            return
        self._checker_started = True

        await bot.wait_until_ready()
        logger.info("🔄 Khởi chạy vòng lặp giám sát cập nhật GitHub tự động (mỗi %ds)...", interval_seconds)

        while not bot.is_closed():
            try:
                await asyncio.sleep(interval_seconds)
                update_res = await self.check_github_update()
                if update_res.get("has_update"):
                    remote_hash = update_res.get("remote_hash", "")
                    if remote_hash and remote_hash != self._last_notified_remote_hash:
                        self._last_notified_remote_hash = remote_hash
                        await self.notify_github_update(bot, update_res)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Lỗi vòng lặp kiểm tra cập nhật GitHub: %s", e)
                await asyncio.sleep(60)

    async def notify_github_update(self, bot: commands.Bot, update_info: Dict[str, Any]) -> bool:
        """Gửi thông báo có bản cập nhật mới vào kênh đồng bộ."""
        sync_channel_id = getattr(settings, "SYSTEM_SYNC_CHANNEL_ID", DEFAULT_SYNC_CHANNEL_ID)
        channel = bot.get_channel(sync_channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(sync_channel_id)
            except Exception:
                return False

        commits = update_info.get("commits", [])
        commits_preview = "\n".join(commits[:5]) if commits else "• Cập nhật bản vá và tính năng mới nhất từ GitHub."

        embed = discord.Embed(
            title="🔔 PHÁT HIỆN BẢN CẬP NHẬT MỚI TỪ GITHUB!",
            description=(
                f"Đã phát hiện commit mới trên repository **hyperhub-bot** (nhánh `main`).\n"
                f"Hệ thống cho phép bạn **Cập Nhật Ngay** chỉ bằng 1 cú click chuột!"
            ),
            color=0xF59E0B,  # Amber
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(
            name="🏷️ Thông Tin Phiên Bản",
            value=(
                f"• Bản hiện tại : `{update_info.get('local_hash', 'unknown')}`\n"
                f"• Bản mới nhất : **`{update_info.get('remote_hash', 'unknown')}`**\n"
                f"• Kho lưu trữ  : [{GITHUB_REPO_URL}]({GITHUB_REPO_URL})"
            ),
            inline=False,
        )

        embed.add_field(
            name="📝 Nhật Ký Thay Đổi (Changelog)",
            value=f"```text\n{commits_preview}\n```",
            inline=False,
        )

        embed.add_field(
            name="⚡ Thao Tác Cập Nhật",
            value=(
                "• **Discord:** Nhấn nút **🚀 Cập Nhật Ngay** bên dưới.\n"
                f"• **Web Hub:** Mở [Admin Hub trên Web]({VERCEL_ADMIN_URL}) để cập nhật trực quan."
            ),
            inline=False,
        )

        view = SystemUpdateView()
        try:
            await channel.send(embed=embed, view=view)
            logger.info("📢 Đã gửi thông báo bản cập nhật mới (%s) vào kênh Discord!", update_info.get("remote_hash"))
            return True
        except Exception as e:
            logger.error("Lỗi khi gửi thông báo cập nhật vào Discord: %s", e)
            return False

    # =========================================================================
    # 4. QUY TRÌNH HOT-RELOAD TỐI ƯU HÓA TOÀN DIỆN (OPTIMIZED RELOAD)
    # =========================================================================

    async def perform_optimized_reload(self, bot: commands.Bot) -> Dict[str, Any]:
        """Thực thi hot-reload toàn diện bot, cogs, database, views và các kênh giao diện."""
        start_t = time.perf_counter()
        logger.info("⚡ [Smart Reload] Bắt đầu quy trình nạp lại toàn diện hệ thống...")

        # 1. Đồng bộ và cập nhật Schema Cơ sở dữ liệu
        db_ok = True
        try:
            from database.database import init_db
            await init_db()
        except Exception as e:
            db_ok = False
            logger.error("Lỗi init_db trong reload: %s", e)

        # 2. Hot-reload toàn bộ các Cogs với cơ chế AI Self-Healing
        target_cogs: List[str] = []
        try:
            from bot import INITIAL_EXTENSIONS
            target_cogs = list(INITIAL_EXTENSIONS)
        except Exception:
            pass

        for ext in list(bot.extensions.keys()):
            if ext not in target_cogs and not ext.startswith("not_finished."):
                target_cogs.append(ext)

        for arch in ["cogs.profile", "cogs.ranked_duel"]:
            if arch in target_cogs:
                target_cogs.remove(arch)

        reloaded: List[str] = []
        failed: List[str] = []

        for cog in target_cogs:
            try:
                if cog in bot.extensions:
                    await bot.reload_extension(cog)
                else:
                    await bot.load_extension(cog)
                reloaded.append(cog)
            except Exception as e:
                # Kích hoạt AI Local Self-Healing nếu reload gặp lỗi
                try:
                    from services.self_healer import SelfHealer
                    healed = await SelfHealer.try_heal_extension(cog, e)
                    if healed:
                        if cog in bot.extensions:
                            await bot.reload_extension(cog)
                        else:
                            await bot.load_extension(cog)
                        reloaded.append(f"{cog} (✨ Healed)")
                        continue
                except Exception as heal_e:
                    logger.warning("Self-Healing không thể vá lỗi cog %s: %s", cog, heal_e)
                failed.append(f"{cog} ({e})")

        # 3. Đăng ký lại các Persistent Views
        try:
            from cogs.doc_intake import DocumentIntakeControlView
            from cogs.link_scanner import LinkScannerControlView
            from cogs.exam_generator_cog import GenerateControlPanelView
            from cogs.info_board_cog import InfoBoardRefreshView

            bot.add_view(DocumentIntakeControlView())
            bot.add_view(LinkScannerControlView())
            bot.add_view(GenerateControlPanelView(bot))
            bot.add_view(InfoBoardRefreshView())
            bot.add_view(SystemControlView())
            bot.add_view(SystemUpdateView())
        except Exception as view_err:
            logger.debug("Lỗi đăng ký views trong reload: %s", view_err)

        # 4. Prune Slash commands & Đồng bộ Hash-based (Tránh 429 Rate Limit)
        synced_count = 0
        sync_note = "không đổi"
        try:
            from bot import prune_tree_commands
            prune_tree_commands(bot)
        except Exception as pe:
            logger.warning("Lỗi prune commands: %s", pe)

        try:
            cmd_sigs = sorted([f"{c.name}:{c.description}" for c in bot.tree.get_commands()])
            current_hash = hashlib.md5("".join(cmd_sigs).encode("utf-8")).hexdigest()
            hash_file = PROJECT_ROOT / "data" / ".tree_sync.hash"
            last_hash = hash_file.read_text("utf-8").strip() if hash_file.exists() else ""
            if current_hash != last_hash:
                synced = await bot.tree.sync()
                synced_count = len(synced)
                hash_file.parent.mkdir(parents=True, exist_ok=True)
                hash_file.write_text(current_hash, encoding="utf-8")
                sync_note = f"đã đồng bộ {synced_count} lệnh"
            else:
                synced_count = len(cmd_sigs)
                sync_note = "dùng cache (không đổi)"
        except Exception as se:
            logger.warning("Lỗi đồng bộ slash commands trong reload: %s", se)
            sync_note = f"lỗi ({se})"

        # 5. Làm mới tuần tự các kênh giao diện (Sequential Pipeline - Tiết kiệm CPU)
        channel_status: List[str] = []

        # 5.1. Kênh nộp tài liệu
        doc_cog = bot.get_cog("DocumentIntakeCog")
        intake_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
        if doc_cog and hasattr(doc_cog, "auto_setup_intake_channel") and intake_id > 0:
            try:
                await doc_cog.auto_setup_intake_channel(purge=False)
                channel_status.append(f"• <#{intake_id}>: Đã cập nhật Bảng Nộp Đề ✅")
            except Exception as e:
                channel_status.append(f"• <#{intake_id}>: Lỗi (`{e}`) ❌")

        # 5.2. Kênh tra cứu đề
        search_cog = bot.get_cog("DocumentSearch")
        search_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1553678782101979186)
        if search_cog and hasattr(search_cog, "auto_setup_search_channel") and search_id > 0:
            try:
                await search_cog.auto_setup_search_channel(purge=False)
                channel_status.append(f"• <#{search_id}>: Đã cập nhật Bảng Tra Cứu ✅")
            except Exception as e:
                channel_status.append(f"• <#{search_id}>: Lỗi (`{e}`) ❌")

        # 5.3. Kênh quét link
        link_cog = bot.get_cog("LinkScannerCog")
        scanner_id = getattr(settings, "LINK_SCANNER_CHANNEL_ID", 1546522680638054461)
        if link_cog and hasattr(link_cog, "auto_setup_scanner_channel") and scanner_id > 0:
            try:
                await link_cog.auto_setup_scanner_channel(purge=False)
                channel_status.append(f"• <#{scanner_id}>: Đã cập nhật Bảng Quét Link ✅")
            except Exception as e:
                channel_status.append(f"• <#{scanner_id}>: Lỗi (`{e}`) ❌")

        # 5.4. Kênh hướng dẫn admin
        help_cog = bot.get_cog("Help")
        if help_cog and hasattr(help_cog, "auto_setup_admin_guide"):
            try:
                await help_cog.auto_setup_admin_guide(purge=False)
                channel_status.append("• Kênh Hướng Dẫn Lệnh Admin: Đã cập nhật ✅")
            except Exception as e:
                channel_status.append(f"• Kênh Admin Guide: Lỗi (`{e}`) ❌")

        duration_ms = round((time.perf_counter() - start_t) * 1000, 1)
        logger.info("⚡ [Smart Reload] Hoàn tất hot-reload trong %sms! Thành công: %d/%d cogs.", duration_ms, len(reloaded), len(target_cogs))

        return {
            "success": len(failed) == 0,
            "duration_ms": duration_ms,
            "reloaded_cogs": reloaded,
            "failed_cogs": failed,
            "total_cogs": len(target_cogs),
            "database_ok": db_ok,
            "slash_commands": synced_count,
            "slash_note": sync_note,
            "channels": channel_status,
            "timestamp": int(time.time()),
        }

    # =========================================================================
    # 5. QUY TRÌNH CẬP NHẬT 1-CLICK TỪ GITHUB (APPLY SYSTEM UPDATE)
    # =========================================================================

    async def perform_system_update(self, bot: commands.Bot) -> Dict[str, Any]:
        """Kéo mã nguồn mới nhất từ GitHub, biên dịch (nếu cần), và thực thi hot-reload."""
        async with self._update_lock:
            start_t = time.perf_counter()
            logger.info("🚀 [1-Click Update] Bắt đầu quy trình cập nhật từ GitHub...")

            def _pull_git():
                git_bin = shutil.which("git")
                if not git_bin:
                    return False, "Không tìm thấy Git trên máy chủ"
                try:
                    # 1. Fetch
                    subprocess.run([git_bin, "fetch", "origin", "main"], cwd=PROJECT_ROOT, check=True, timeout=20)
                    # 2. Reset hard
                    subprocess.run([git_bin, "reset", "--hard", "origin/main"], cwd=PROJECT_ROOT, check=True, timeout=10)
                    # 3. Clean
                    subprocess.run([git_bin, "clean", "-fd"], cwd=PROJECT_ROOT, check=True, timeout=10)
                    new_hash = _run_git_cmd(["rev-parse", "--short", "HEAD"]) or "mới"
                    return True, new_hash
                except Exception as e:
                    return False, str(e)

            pull_ok, new_hash_or_err = await asyncio.to_thread(_pull_git)
            if not pull_ok:
                logger.error("Cập nhật GitHub thất bại: %s", new_hash_or_err)
                return {
                    "success": False,
                    "error": f"Lỗi kéo mã nguồn từ GitHub: {new_hash_or_err}",
                    "new_hash": None,
                }

            # Kiểm tra và biên dịch lại C++ nếu có compiler
            try:
                from utils.bootstrap import check_and_build_cpp_engine
                await asyncio.to_thread(check_and_build_cpp_engine)
            except Exception as cpp_e:
                logger.debug("Bỏ qua kiểm tra biên dịch C++: %s", cpp_e)

            # Thực thi hot-reload tối ưu
            reload_summary = await self.perform_optimized_reload(bot)

            # Đặt lại trạng thái pending update
            self.pending_update = None
            self._last_notified_remote_hash = ""

            duration_s = round(time.perf_counter() - start_t, 2)
            logger.info("🎉 [1-Click Update] Cập nhật thành công lên bản %s sau %ss!", new_hash_or_err, duration_s)

            # Gửi thông báo xác nhận thành công vào kênh Discord
            sync_channel_id = getattr(settings, "SYSTEM_SYNC_CHANNEL_ID", DEFAULT_SYNC_CHANNEL_ID)
            channel = bot.get_channel(sync_channel_id)
            if channel:
                try:
                    embed = discord.Embed(
                        title="🎉 CẬP NHẬT HỆ THỐNG THÀNH CÔNG!",
                        description=(
                            f"Bot đã đồng bộ thành công bản cập nhật mới nhất từ GitHub **({new_hash_or_err})**.\n"
                            f"Toàn bộ Cogs, giao diện và cơ sở dữ liệu đã được nạp lại trong `{duration_s}s`."
                        ),
                        color=0x10B981,
                        timestamp=discord.utils.utcnow(),
                    )
                    embed.add_field(
                        name="📦 Trạng Thái Cogs",
                        value=f"✅ Nạp lại **{len(reload_summary.get('reloaded_cogs', []))}/{reload_summary.get('total_cogs', 0)}** modules.",
                        inline=True,
                    )
                    embed.add_field(
                        name="⚡ Slash Commands",
                        value=f"{reload_summary.get('slash_commands', 0)} lệnh ({reload_summary.get('slash_note', 'sẵn sàng')}).",
                        inline=True,
                    )
                    if reload_summary.get("channels"):
                        embed.add_field(
                            name="📋 Các Kênh Giao Diện",
                            value="\n".join(reload_summary["channels"]),
                            inline=False,
                        )
                    view = SystemControlView()
                    await channel.send(embed=embed, view=view)
                except Exception as post_e:
                    logger.debug("Lỗi gửi thông báo xác nhận cập nhật: %s", post_e)

            return {
                "success": True,
                "new_hash": new_hash_or_err,
                "duration_seconds": duration_s,
                "reload_summary": reload_summary,
            }


# Singleton instance
system_sync_service = SystemSyncService()


# =============================================================================
# PERSISTENT VIEWS CHO CÁC NÚT BẤM DISCORD
# =============================================================================

class SystemControlView(discord.ui.View):
    """View bảng điều khiển hệ thống đính kèm dưới thông báo khởi động."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        # Thêm nút Link Vercel Vault
        self.add_item(
            discord.ui.Button(
                label="Kho Đề Web",
                url=VERCEL_VAULT_URL,
                style=discord.ButtonStyle.link,
                emoji="🌐",
            )
        )
        # Thêm nút Link Admin Hub
        self.add_item(
            discord.ui.Button(
                label="Admin Hub",
                url=VERCEL_ADMIN_URL,
                style=discord.ButtonStyle.link,
                emoji="👑",
            )
        )

    @discord.ui.button(
        label="Kiểm Tra Update",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
        custom_id="sys_check_update_btn",
    )
    async def check_update_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối quyền:** Bạn cần là Quản trị viên hoặc Bot Owner để sử dụng tính năng này.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        res = await system_sync_service.check_github_update()
        if res.get("has_update"):
            await interaction.followup.send(
                f"🔔 **Phát hiện bản cập nhật mới từ GitHub!**\n"
                f"• Bản hiện tại: `{res.get('local_hash')}`\n"
                f"• Bản mới nhất: **`{res.get('remote_hash')}`**\n"
                f"• Bạn có thể nhấn nút **Cập Nhật Ngay** tại thông báo trong kênh hoặc mở **Admin Hub** trên Web.",
                ephemeral=True,
            )
            # Kích hoạt thông báo công khai trong kênh nếu chưa có
            if interaction.client:
                await system_sync_service.notify_github_update(interaction.client, res)
        else:
            await interaction.followup.send(
                f"✅ **Hệ thống đã ở phiên bản mới nhất!**\n"
                f"• Commit: `{res.get('local_hash')}`\n"
                f"• Không có commit nào mới trên nhánh `main`.",
                ephemeral=True,
            )

    @discord.ui.button(
        label="Reload Nhanh",
        style=discord.ButtonStyle.primary,
        emoji="⚡",
        custom_id="sys_quick_reload_btn",
    )
    async def quick_reload_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối quyền:** Bạn cần là Quản trị viên hoặc Bot Owner để sử dụng tính năng này.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        summary = await system_sync_service.perform_optimized_reload(interaction.client)

        reloaded_cnt = len(summary.get("reloaded_cogs", []))
        total_cnt = summary.get("total_cogs", 0)
        ms = summary.get("duration_ms", 0)

        embed = discord.Embed(
            title="⚡ ĐÃ TỐI ƯU & NẠP LẠI TOÀN BỘ HỆ THỐNG",
            description=f"Thời gian thực thi: **{ms}ms** • Cogs: **{reloaded_cnt}/{total_cnt}** modules.",
            color=0x3B82F6,
        )
        if summary.get("channels"):
            embed.add_field(
                name="📋 Trạng Thái Kênh",
                value="\n".join(summary["channels"][:6]),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)


class SystemUpdateView(discord.ui.View):
    """View đính kèm khi phát hiện bản cập nhật mới từ GitHub."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Mở Admin Hub",
                url=VERCEL_ADMIN_URL,
                style=discord.ButtonStyle.link,
                emoji="👑",
            )
        )

    @discord.ui.button(
        label="Cập Nhật Ngay",
        style=discord.ButtonStyle.success,
        emoji="🚀",
        custom_id="sys_apply_update_btn",
    )
    async def apply_update_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối quyền:** Bạn cần là Quản trị viên hoặc Bot Owner để cập nhật mã nguồn.",
                ephemeral=True,
            )
            return

        button.disabled = True
        button.label = "Đang Cập Nhật..."
        await interaction.response.edit_message(view=self)

        res = await system_sync_service.perform_system_update(interaction.client)
        if res.get("success"):
            await interaction.followup.send(
                f"🎉 **Cập nhật thành công lên bản `{res.get('new_hash')}`!**\n"
                f"Hệ thống đã tự động kéo mã nguồn từ GitHub và hot-reload toàn bộ bot.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ **Cập nhật thất bại:** {res.get('error')}",
                ephemeral=True,
            )
            button.disabled = False
            button.label = "Cập Nhật Ngay"
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(
        label="Chỉ Reload",
        style=discord.ButtonStyle.secondary,
        emoji="⚡",
        custom_id="sys_quick_reload_upd_btn",
    )
    async def quick_reload_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message(
                "❌ **Từ chối quyền:** Bạn cần là Quản trị viên hoặc Bot Owner để sử dụng tính năng này.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        summary = await system_sync_service.perform_optimized_reload(interaction.client)
        await interaction.followup.send(
            f"⚡ Đã nạp lại **{len(summary.get('reloaded_cogs', []))}/{summary.get('total_cogs', 0)}** cogs trong `{summary.get('duration_ms')}ms`.",
            ephemeral=True,
        )
