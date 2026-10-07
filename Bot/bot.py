"""Điểm khởi chạy chính và quản lý vòng đời Discord Competitive Programming Bot (100% Tiếng Việt)."""

import os
import sys
from pathlib import Path

# Xác định thư mục Bot và chuyển working directory sang Bot
ROOT_DIR = Path(__file__).parent.resolve()
BOT_DIR = ROOT_DIR / "Bot" if (ROOT_DIR / "Bot").exists() else ROOT_DIR
os.chdir(BOT_DIR)
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))
PROJECT_ROOT = BOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Đảm bảo UTF-8 an toàn cho console trên Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Kiểm tra & tự động chuẩn bị môi trường: pip packages, C++ engine, Node.js, .env
from utils.bootstrap import run_preflight_checks
run_preflight_checks()

import asyncio
import discord
from discord.ext import commands


from config.settings import settings
from pathlib import Path
from database.database import Database, close_db_engine, init_db
from database.cooldown import CooldownRepository
from database.moderation import ModerationRepository
from database.config import ConfigRepository
from services.ban_scheduler import BanScheduler
from utils import embeds
# [ARCHIVED] Ranked 1:1 Duel Worker — đã lưu trữ tại archived/duel_arena/
# from services.ai_worker import (
#     start_ollama_daemon,
#     stop_ollama_daemon,
#     problem_worker,
# )
from utils.embeds import error_embed
from utils.logger import setup_logger

# Khởi tạo bộ ghi log chuẩn có màu và xoay vòng file
logger = setup_logger(log_level=settings.LOG_LEVEL)

INITIAL_EXTENSIONS = [
    # [NOT FINISHED] Phân hệ Tạo Đề Thi AI — Lưu tại not_finished/exam_generator/ để sử dụng trong tương lai
    # "not_finished.exam_generator.cogs.check_token",
    # "not_finished.exam_generator.cogs.exam_generator_cog",
    # "not_finished.exam_generator.cogs.info_board_cog",
    "cogs.help",
    "cogs.admin",
    "cogs.server_defense",
    "cogs.doc_intake",          # Kênh nộp tài liệu — nhận file/link & phân loại
    "cogs.doc_search",          # Kênh tra cứu đề thi — tra cứu chi tiết & mô tả
    "cogs.link_scanner",        # Quét link an toàn
    "cogs.moderation",          # Lệnh kiểm duyệt
    "cogs.warnings",            # Hệ thống cảnh báo
    "cogs.rolemanager",         # Quản lý role
    "cogs.conflict_moderator",  # Giám sát xung đột AI
    "cogs.lists",               # Danh sách lệnh
    "cogs.exam_generator_cog",  # Tạo đề thi AI
    "cogs.info_board_cog",      # Sổ tay & bảng giá Gói Hyper
    "cogs.study_practice_cog",  # 🎯 Tính năng Học Tập & Luyện Đề (Chưa kích hoạt)
]


# Danh sách slash commands được phép tồn tại trên server (mọi lệnh khác bị gỡ khỏi tree).
# Cogs (panels, buttons, listeners) vẫn chạy bình thường — chỉ cắt mặt lệnh slash.
COMMAND_ALLOWLIST = {
    "reload", "status",
    "kick", "ban", "unban", "mute", "unmute", "reset",
    "warn", "deletewarn", "warntest",
}


def prune_tree_commands(bot) -> int:
    """Gỡ mọi slash command/group khỏi tree nếu không nằm trong COMMAND_ALLOWLIST.
    Trả về số lệnh còn lại. Chạy sau load/reload cogs, trước tree.sync()."""
    try:
        from discord import app_commands
        removed = 0
        for cmd in list(bot.tree.get_commands()):
            if isinstance(cmd, app_commands.Group):
                bot.tree.remove_command(cmd.name)
                removed += 1
            elif cmd.name not in COMMAND_ALLOWLIST:
                bot.tree.remove_command(cmd.name)
                removed += 1
        kept = len(bot.tree.get_commands())
        print(f"[prune] Đã gỡ {removed} lệnh ngoài allowlist, giữ lại {kept} lệnh.")
        return kept
    except Exception as e:
        print(f"[prune] Lỗi khi cắt slash commands: {e}")
        return 0


class CompetitiveProgrammingBot(commands.Bot):
    """Lớp Bot Discord điều phối hệ thống HyperHub (kho đề + web)."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True  # Bắt buộc để kiểm tra thành viên server & phân quyền
        intents.message_content = (
            True  # Bắt buộc để nhận diện nội dung tin nhắn và lệnh
        )

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        # HyperHub Services & Database initialization
        self.settings = settings
        self.db = Database(Path("data/bot.db"))
        self.cooldowns = CooldownRepository(self.db)
        self.moderation = ModerationRepository(self.db)
        self.config = ConfigRepository(self.db)
        self.scheduler = BanScheduler(self, self.moderation)
        self._cleanup_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        """Thực thi trong quá trình khởi động bot trước khi kết nối Gateway Discord."""
        # Kiểm tra CSDL bot.db có tồn tại hay không, nếu mất dữ liệu -> Tự động khôi phục từ Discord
        try:
            from services.backup_service import PRIMARY_DB_PATH, backup_service
            if not PRIMARY_DB_PATH.exists() or PRIMARY_DB_PATH.stat().st_size == 0:
                logger.warning("⚠️ Không tìm thấy tệp bot.db hoặc CSDL rỗng! Đang kích hoạt tự động khôi phục từ Discord...")
                restored = await backup_service.restore_latest_from_discord(self)
                if restored:
                    logger.info("✨ [Self-Healing] Đã tự động khôi phục CSDL bot.db từ bản sao lưu Discord thành công!")
        except Exception as re:
            logger.warning(f"[Self-Healing] Không thể tự động khôi phục CSDL từ Discord: {re}")

        logger.info("Đang khởi tạo cấu trúc bảng cơ sở dữ liệu...")
        await init_db()
        try:
            await self.db.connect()
            from services.embedding_service import DocumentEmbeddingService
            self.embedding_service = DocumentEmbeddingService.get_instance(self.db)
            self.embedding_service.start_background_sync()

            theme_color = await self.config.get_embed_color()
            if theme_color is not None:
                embeds.set_theme_color(theme_color)
            if getattr(settings, "LOGO_URL", ""):
                embeds.set_logo_url(settings.LOGO_URL)
        except Exception as e:
            logger.warning(f"Lỗi khởi tạo HyperHub Database: {e}")

        logger.info("Đang nạp các module Cogs...")
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info(f"Đã nạp thành công module: {ext}")
            except Exception as e:
                logger.warning(f"⚠️ Phát hiện lỗi khi nạp module {ext}: {e}. Đang kích hoạt AI Local Self-Healing...")
                try:
                    from services.self_healer import SelfHealer
                    healed = await SelfHealer.try_heal_extension(ext, e)
                    if healed:
                        await self.load_extension(ext)
                        logger.info(f"✨ [Self-Healing] AI Local đã tự động sửa lỗi và nạp thành công module {ext}!")
                        continue
                except Exception as heal_e:
                    logger.warning(f"[Self-Healing] Không thể tự động vá lỗi cho {ext}: {heal_e}")
                logger.error(f"Lỗi khi nạp module {ext}: {e}", exc_info=True)

        # [ARCHIVED] Ranked Duel Worker — đã lưu trữ tại archived/duel_arena/
        # self.loop.create_task(asyncio.to_thread(start_ollama_daemon))

        # Cắt slash commands ngoài allowlist + gỡ toàn bộ prefix commands (!...)
        prune_tree_commands(self)
        for cmd in list(self.commands):
            try:
                self.remove_command(cmd.name)
            except Exception:
                pass
        logger.info("Đã vô hiệu hóa toàn bộ prefix commands (chỉ dùng slash trong allowlist).")

        # Đồng bộ Slash Commands thông minh: chỉ gọi API Discord khi có lệnh mới/thay đổi
        import hashlib
        try:
            cmd_sigs = sorted([f"{cmd.name}:{cmd.description}" for cmd in self.tree.get_commands()])
            current_hash = hashlib.md5("".join(cmd_sigs).encode("utf-8")).hexdigest()
            hash_file = Path("data/.tree_sync.hash")
            last_hash = hash_file.read_text("utf-8").strip() if hash_file.exists() else ""

            if current_hash == last_hash:
                logger.info(
                    f"⚡ Slash Commands ({len(cmd_sigs)} lệnh) đã được đồng bộ trước đó, bỏ qua REST API sync để tăng tốc khởi động."
                )
            else:
                logger.info(
                    f"Đang đồng bộ {len(cmd_sigs)} lệnh Slash Commands với Discord REST API..."
                )
                synced = await self.tree.sync()
                hash_file.parent.mkdir(parents=True, exist_ok=True)
                hash_file.write_text(current_hash, encoding="utf-8")
                logger.info(f"✅ Đã đồng bộ thành công {len(synced)} lệnh Slash Commands.")
        except Exception as e:
            logger.warning(f"Lỗi khi kiểm tra/đồng bộ Slash Commands: {e}")

        # Đăng ký các Persistent Views để các nút bấm hoạt động vĩnh viễn không bao giờ timeout
        from cogs.doc_intake import DocumentIntakeControlView
        from cogs.link_scanner import LinkScannerControlView
        from cogs.exam_generator_cog import GenerateControlPanelView
        from cogs.info_board_cog import InfoBoardRefreshView

        self.add_view(DocumentIntakeControlView())
        self.add_view(LinkScannerControlView())
        self.add_view(GenerateControlPanelView(self))
        self.add_view(InfoBoardRefreshView())

        # Khởi chạy BanScheduler
        self.loop.create_task(self._start_ban_scheduler())
        self.loop.create_task(self._periodic_mod_cleanup())

        # Khởi chạy vòng lặp tự động sao lưu CSDL định kỳ (mỗi 6 tiếng)
        from services.backup_service import backup_service
        self.loop.create_task(backup_service.start_backup_loop(self))

        # Khởi chạy Bot & Web API Bridge (cho phép Web kết nối và tương tác thời gian thực)
        if getattr(settings, "BOT_API_ENABLED", True):
            try:
                from services.api_bridge import BotAPIBridge
                self.api_bridge = BotAPIBridge(self)
                self.loop.create_task(self.api_bridge.start())
            except Exception as bridge_err:
                logger.warning(f"Lỗi khởi chạy Bot API Bridge: {bridge_err}")

    async def _auto_setup_channels(self) -> None:
        """Tự động thiết lập và đăng bảng điều khiển giao diện tại các kênh cố định (Chạy song song tối ưu tốc độ)."""
        await self.wait_until_ready()
        logger.info("⚡ Bắt đầu tự động thiết lập các kênh giao diện song song (Parallel Pipeline)...")

        async def run_setup(name: str, coro, timeout: float = 30.0) -> None:
            try:
                await asyncio.wait_for(coro, timeout=timeout)
                logger.info(f"✅ Đã làm mới xong kênh: {name}")
            except Exception as e:
                logger.warning(
                    f"⚠️ Lỗi khi thiết lập kênh {name}: {type(e).__name__} ({e or 'Timeout'})"
                )

        tasks = []

        # 1/4. Document Intake & Classification
        doc_cog = self.get_cog("DocumentIntakeCog")
        if doc_cog and hasattr(doc_cog, "auto_setup_intake_channel"):
            tasks.append(run_setup("#doc-intake", doc_cog.auto_setup_intake_channel(purge=True)))

        # 2/4. Document Search & Discovery
        search_doc_cog = self.get_cog("DocumentSearch")
        if search_doc_cog and hasattr(search_doc_cog, "auto_setup_search_channel"):
            tasks.append(run_setup("#doc-search", search_doc_cog.auto_setup_search_channel(purge=True)))

        # 3/4. Link Scanner
        link_scanner_cog = self.get_cog("LinkScannerCog")
        if link_scanner_cog and hasattr(link_scanner_cog, "auto_setup_scanner_channel"):
            tasks.append(run_setup("#link-scanner", link_scanner_cog.auto_setup_scanner_channel(purge=True)))

        # 4/4. Admin Command Guide (kênh hướng dẫn lệnh admin)
        help_cog = self.get_cog("Help")
        if help_cog and hasattr(help_cog, "auto_setup_admin_guide"):
            tasks.append(run_setup("#admin-guide", help_cog.auto_setup_admin_guide(purge=True)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"⚡ Hoàn tất thiết lập toàn bộ {len(tasks)} kênh giao diện trong thời gian kỷ lục!")


    async def _start_ban_scheduler(self) -> None:
        await self.wait_until_ready()
        try:
            await self.scheduler.start()
        except Exception as e:
            logger.warning(f"Lỗi khi khởi chạy BanScheduler: {e}")

    async def _periodic_mod_cleanup(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self.moderation.cleanup_old_records(days=30)
            except Exception as e:
                logger.warning(f"Lỗi khi dọn dẹp moderation logs: {e}")
            await asyncio.sleep(86400)

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        """Ghi nhận lỗi sự kiện toàn cục."""
        logger.error(f"Lỗi không xử lý trong sự kiện '{event_method}'", exc_info=True)

    async def on_ready(self) -> None:
        """Kích hoạt khi bot kết nối thành công với Discord."""
        user_tag = f"{self.user.name}#{self.user.discriminator}" if self.user else "Bot"
        logger.info("==================================================")
        logger.info(
            f"🟢 Bot đã đăng nhập thành công: {user_tag} (ID: {self.user.id if self.user else 'Không rõ'})"
        )
        logger.info(f"🟢 Đang kết nối trên {len(self.guilds)} Máy chủ Discord.")
        logger.info(f"🟢 ID Bot Owner: {settings.OWNER_ID}")
        logger.info("==================================================")

        # Thiết lập trạng thái hoạt động trực quan
        activity = discord.Activity(
            type=discord.ActivityType.competing,
            name="Đấu trường Codeforces | /help",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

        # Khởi chạy cập nhật các kênh và tự động cấp Role Thành viên (Học sinh) trong background task
        asyncio.create_task(self._auto_setup_channels())
        asyncio.create_task(self._auto_assign_member_roles())

        # [ARCHIVED] AI Worker sinh đề Ranked — đã lưu trữ tại archived/duel_arena/
        # asyncio.create_task(problem_worker.start(self))

    async def _auto_assign_member_roles(self) -> None:
        """Tự động kiểm tra và cấp Role '🌱 Học sinh' (MEMBER_ROLE_ID) cho toàn bộ thành viên hiện có trên Server."""
        member_role_id = settings.MEMBER_ROLE_ID
        if not member_role_id or member_role_id <= 0:
            return

        await self.wait_until_ready()
        for guild in self.guilds:
            member_role = guild.get_role(member_role_id)
            if not member_role:
                logger.warning(
                    f"Không tìm thấy Role Thành viên (ID: {member_role_id}) trên server {guild.name}"
                )
                continue

            assigned_count = 0
            for member in guild.members:
                if not member.bot and member_role not in member.roles:
                    try:
                        await member.add_roles(
                            member_role,
                            reason="Tự động cấp Role Thành Viên Mặc Định (🌱 Học sinh)",
                        )
                        assigned_count += 1
                        await asyncio.sleep(0.5)  # Tránh chạm Rate Limit Discord API
                    except Exception as e:
                        logger.warning(
                            f"Không thể gán role học sinh cho {member} ({member.id}): {e}"
                        )

            if assigned_count > 0:
                logger.info(
                    f"✅ Đã tự động cấp Role '🌱 Học sinh' cho {assigned_count} thành viên trên Server {guild.name}."
                )

    async def close(self) -> None:
        """Xử lý đóng tiến trình và giải phóng tài nguyên an toàn khi tắt bot."""
        logger.info("Đang bắt đầu quá trình tắt bot an toàn...")

        # Đóng toàn bộ database và HTTP session
        try:
            await self.db.close()
        except Exception:
            pass
        await close_db_engine()
        await super().close()
        logger.info("Đã tắt bot và giải phóng tài nguyên hoàn tất.")

    async def on_member_join(self, member: discord.Member) -> None:
        """Tự động gán Role '🌱 Học sinh' (MEMBER_ROLE_ID) cho mọi thành viên mới vào server."""
        if member.bot:
            return

        roles_to_add = []

        # 1. Role Thành viên mặc định (🌱 Học sinh)
        if settings.MEMBER_ROLE_ID and settings.MEMBER_ROLE_ID > 0:
            member_role = member.guild.get_role(settings.MEMBER_ROLE_ID)
            if member_role and member_role not in member.roles:
                roles_to_add.append(member_role)

        if roles_to_add:
            try:
                await member.add_roles(
                    *roles_to_add,
                    reason="Tự động gán Role Thành Viên (🌱 Học sinh) & Rank T8 (Tân Binh) khi vào server",
                )
                logger.info(
                    f"Đã tự động gán {[r.name for r in roles_to_add]} cho thành viên mới: {member} (ID: {member.id})"
                )
            except discord.Forbidden:
                logger.error(
                    f"Thiếu quyền quản lý roles để gán cho {member} (ID: {member.id})"
                )
            except Exception as e:
                logger.error(f"Lỗi khi gán roles cho {member}: {e}", exc_info=True)


# Khởi tạo instance Bot
bot = CompetitiveProgrammingBot()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
) -> None:
    """Xử lý lỗi tập trung cho toàn bộ Slash Commands."""
    logger.error(
        f"Lỗi lệnh Slash /{interaction.command.name if interaction.command else 'Unknown'}: {error}"
    )

    if isinstance(error, discord.app_commands.CommandOnCooldown):
        msg = f"⏳ Bạn đang thao tác quá nhanh! Vui lòng thử lại sau `{error.retry_after:.1f}` giây."
    elif isinstance(error, discord.app_commands.MissingPermissions):
        msg = "❌ Bạn không đủ quyền hạn trên máy chủ để thực hiện lệnh này!"
    elif isinstance(error, discord.app_commands.CheckFailure):
        msg = "❌ Bạn không đáp ứng điều kiện để sử dụng lệnh này (Yêu cầu quyền Admin/Owner hoặc cấp bậc tương ứng)!"
    else:
        msg = f"❌ Đã xảy ra lỗi khi thực thi lệnh: `{error}`"

    embed = error_embed("LỖI THỰC THI LỆNH", msg)

    # Interaction có thể đã hết hạn (event loop bận > 3s, user spam click...).
    # Trường hợp này không gửi được nữa -> chỉ log, tránh spam lỗi 10062.
    try:
        if interaction.is_expired():
            logger.warning(
                f"Interaction /{interaction.command.name if interaction.command else 'Unknown'} "
                "đã hết hạn, bỏ qua thông báo lỗi."
            )
            return
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.NotFound as e:
        if getattr(e, "code", None) == 10062:
            logger.warning(
                f"Interaction /{interaction.command.name if interaction.command else 'Unknown'} "
                "unknown (10062), bỏ qua thông báo lỗi."
            )
        else:
            logger.error(f"Không thể gửi thông báo lỗi: {e}")
    except Exception as e:
        logger.error(f"Không thể gửi thông báo lỗi: {e}")


def main() -> None:
    """Hàm khởi chạy chính của tiến trình Bot."""
    token = settings.DISCORD_TOKEN
    if not token or token.strip() == "":
        logger.critical(
            "Không tìm thấy biến DISCORD_TOKEN trong cấu hình (.env). Bot không thể khởi động!"
        )
        sys.exit(1)

    try:
        bot.run(token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Đã nhận tín hiệu dừng (Ctrl+C). Bot đã tắt an toàn.")
    except discord.LoginFailure:
        logger.critical(
            "DISCORD_TOKEN không hợp lệ hoặc đã bị vô hiệu hóa! Vui lòng kiểm tra lại token trong file .env."
        )
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Lỗi nghiêm trọng khi chạy Bot: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Thoát tiến trình ngay lập tức trên 1 lần Ctrl+C mà không bị kẹt luồng nền
        os._exit(0)


if __name__ == "__main__":
    main()
