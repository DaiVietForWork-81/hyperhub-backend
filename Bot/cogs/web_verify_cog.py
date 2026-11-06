"""Kênh #🔐・verify (Category 1534145110642524250) — Cấp mã xác minh đăng nhập Web Orbit (hiệu lực 5 phút, tạo mã mới tự hủy mã cũ)."""

from __future__ import annotations

import asyncio
import datetime
import secrets
import time
from typing import Any
import discord
from discord.ext import commands

from config.settings import settings
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("WebVerifyCog")

CODE_TTL_SECONDS = 300  # 5 phút (300 giây)
_TABLE_INITIALIZED = False

# Bộ nhớ đệm RAM tức thì cho mã xác minh (0ms latency)
MEMORY_VERIFY_CODES: dict[str, dict[str, Any]] = {}


async def ensure_web_verify_table(bot: commands.Bot) -> None:
    """Đảm bảo bảng web_verify_codes tồn tại trên cả SQLite local và Turso Cloud (chỉ chạy 1 lần)."""
    global _TABLE_INITIALIZED
    if _TABLE_INITIALIZED:
        return

    ddl = """
    CREATE TABLE IF NOT EXISTS web_verify_codes (
        discord_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        display_name TEXT NOT NULL,
        avatar_url TEXT NOT NULL,
        code TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL
    )
    """
    try:
        if hasattr(bot, "db") and bot.db:
            await bot.db.execute(ddl)
    except Exception as e:
        logger.debug(f"SQLite init web_verify_codes error: {e}")

    try:
        from database.turso_client import turso_db
        if turso_db.is_configured:
            await turso_db.execute(ddl)
            _TABLE_INITIALIZED = True
    except Exception as e:
        logger.debug(f"Turso init web_verify_codes error: {e}")


def generate_verify_code_instant(user: discord.abc.User) -> tuple[str, int, dict[str, Any]]:
    """Sinh mã 6 số mới tức thì trong RAM (<0.01ms) và hủy mã cũ ngay lập tức."""
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    now_sec = int(time.time())
    expires_at = now_sec + CODE_TTL_SECONDS

    uid_str = str(user.id)
    username = getattr(user, "name", uid_str)
    display_name = (
        getattr(user, "display_name", None)
        or getattr(user, "global_name", None)
        or username
    )
    avatar_url = (
        user.display_avatar.url
        if getattr(user, "display_avatar", None)
        else f"https://cdn.discordapp.com/embed/avatars/{int(user.id) % 5}.png"
    )

    record = {
        "discord_id": uid_str,
        "username": username,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "code": code,
        "created_at": now_sec,
        "expires_at": expires_at,
    }
    MEMORY_VERIFY_CODES[uid_str] = record
    return code, expires_at, record


async def persist_verify_code(bot: commands.Bot, record: dict[str, Any]) -> None:
    """Lưu mã 6 số xuống SQLite local & Turso Cloud (ghi đè hủy mã cũ)."""
    await ensure_web_verify_table(bot)

    uid_str = record["discord_id"]
    username = record["username"]
    display_name = record["display_name"]
    avatar_url = record["avatar_url"]
    code = record["code"]
    now_sec = record["created_at"]
    expires_at = record["expires_at"]
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    upsert_code_sql = """
    INSERT INTO web_verify_codes (discord_id, username, display_name, avatar_url, code, created_at, expires_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(discord_id) DO UPDATE SET
        username = excluded.username,
        display_name = excluded.display_name,
        avatar_url = excluded.avatar_url,
        code = excluded.code,
        created_at = excluded.created_at,
        expires_at = excluded.expires_at
    """
    params = (uid_str, username, display_name, avatar_url, code, now_sec, expires_at)

    # 1. Lưu trên Turso Cloud trước để Vercel đọc tức thì
    try:
        from database.turso_client import turso_db
        if turso_db.is_configured:
            await turso_db.execute(upsert_code_sql, *params)
            await turso_db.execute(
                """
                INSERT INTO linked_accounts (discord_id, username, global_name, avatar_url, email, verified, first_seen, last_seen, login_count)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, 1)
                ON CONFLICT(discord_id) DO UPDATE SET
                    username = excluded.username,
                    global_name = excluded.global_name,
                    avatar_url = excluded.avatar_url,
                    last_seen = excluded.last_seen
                """,
                int(uid_str),
                username,
                display_name,
                avatar_url,
                f"{username}@discord.orbit.vn",
                now_iso,
                now_iso,
            )
    except Exception as e_turso:
        logger.warning(f"Lỗi đồng bộ mã verify lên Turso Cloud: {e_turso}")

    # 2. Lưu trên SQLite local
    try:
        if hasattr(bot, "db") and bot.db:
            await bot.db.execute(upsert_code_sql, *params)
            await bot.db.execute(
                """
                INSERT INTO linked_accounts (discord_id, username, global_name, avatar_url, email, verified, first_seen, last_seen, login_count)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, 1)
                ON CONFLICT(discord_id) DO UPDATE SET
                    username = excluded.username,
                    global_name = excluded.global_name,
                    avatar_url = excluded.avatar_url,
                    last_seen = excluded.last_seen
                """,
                int(uid_str),
                username,
                display_name,
                avatar_url,
                f"{username}@discord.orbit.vn",
                now_iso,
                now_iso,
            )
    except Exception as e_local:
        logger.warning(f"Lỗi lưu mã verify vào SQLite: {e_local}")


async def handle_verify_button_interaction(interaction: discord.Interaction) -> None:
    """Xử lý cấp mã 6 số phản hồi tức thì (<100ms) khi người dùng bấm nút."""
    try:
        code, expires_at, record = generate_verify_code_instant(interaction.user)
        embed = create_embed(
            title="🔑 MÃ XÁC MINH ĐĂNG NHẬP WEB ORBIT",
            description=(
                f"Xin chào **{interaction.user.display_name}** (`@{interaction.user.name}`),\n"
                f"Dưới đây là mã xác minh đăng nhập cổng **Orbit Web** của riêng bạn:\n\n"
                f"```yaml\n{code}\n```\n"
                f"• ⏱️ **Thời hạn sử dụng:** Hết hạn <t:{expires_at}:R> (lúc <t:{expires_at}:T> — **5 phút**).\n"
                f"• 🔄 **Tự động hủy mã cũ:** Mọi mã bạn đã tạo trước đó đều đã bị vô hiệu hóa.\n"
                f"• 🌐 **Cách dùng:** Quay lại cửa sổ đăng nhập trên **https://orbit-psi-black.vercel.app** và điền mã **`{code}`** vào ô xác minh."
            ),
            embed_type=EmbedType.SUCCESS,
            color=0x10B981,
            footer_text="Bảo mật 2 lớp Orbit | Vietnam • Tuyệt đối không chia sẻ mã này cho người khác",
        )

        # Phản hồi trực tiếp cho người dùng và đồng bộ Turso/SQLite song song
        if not interaction.response.is_done():
            await asyncio.gather(
                interaction.response.send_message(embed=embed, ephemeral=True),
                persist_verify_code(interaction.client, record),
            )
        else:
            await asyncio.gather(
                interaction.followup.send(embed=embed, ephemeral=True),
                persist_verify_code(interaction.client, record),
            )
        logger.info(f"🔑 Đã cấp mã xác minh Web ({code}) cho {interaction.user} ({interaction.user.id})")
    except Exception as e:
        logger.error(f"Lỗi khi tạo mã verify web cho {interaction.user.id}: {e}")
        err_embed = create_embed(
            title="❌ KHÔNG THỂ TẠO MÃ XÁC MINH",
            description=f"Đã xảy ra lỗi khi khởi tạo mã xác minh: `{e}`. Vui lòng thử lại sau giây lát.",
            embed_type=EmbedType.ERROR,
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=err_embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=err_embed, ephemeral=True)
        except Exception:
            pass


class WebVerifyControlView(discord.ui.View):
    """Bảng nút bấm cố định tại kênh #🔐・verify (Persistent View)."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Mở Cổng Orbit Web 🌐",
                style=discord.ButtonStyle.link,
                url="https://orbit-psi-black.vercel.app",
            )
        )

    @discord.ui.button(
        label="Lấy Mã Đăng Nhập Web (5 Phút) 🔑",
        style=discord.ButtonStyle.success,
        custom_id="btn_get_web_verify_code",
    )
    async def get_code_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await handle_verify_button_interaction(interaction)


class WebVerifyCog(commands.Cog, name="WebVerify"):
    """Quản lý kênh #🔐・verify cấp mã xác minh đăng nhập Web Orbit (hiệu lực 5 phút)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def build_verify_channel_embed() -> discord.Embed:
        return create_embed(
            title="🔐 XÁC MINH & LẤY MÃ ĐĂNG NHẬP CỔNG WEB — ORBIT | VIETNAM",
            description=(
                "Để bảo vệ tài khoản thành viên và đồng bộ quyền lợi chính chủ giữa **Discord Server** ↔ **Orbit Web Hub** "
                "(Credit Tác giả đóng góp đề, Kho Đề Thực Chiến & Diễn Đàn 2 chiều), vui lòng thực hiện **2 bước** sau:\n\n"
                "### 🧭 QUY TRÌNH ĐĂNG NHẬP TRÊN WEB (2 BƯỚC):\n"
                "1️⃣ **Bước 1 — Xác minh & Liên kết tài khoản Discord:**\n"
                "• Truy cập **https://orbit-psi-black.vercel.app** và bấm nút **Xác minh & Liên kết tài khoản Discord** (ủy quyền chính chủ qua cổng Discord OAuth2).\n\n"
                "2️⃣ **Bước 2 — Lấy & Nhập Mã Xác Minh 5 Phút:**\n"
                "• Bấm vào nút **`Lấy Mã Đăng Nhập Web (5 Phút) 🔑`** màu xanh bên dưới.\n"
                "• Bot sẽ trả về cho riêng bạn một **mã xác minh gồm 6 chữ số** (chỉ mình bạn nhìn thấy).\n"
                "• Điền mã 6 số đó vào ô yêu cầu trên trang Web để hoàn tất đăng nhập!\n\n"
                "### 🛡️ QUY TẮC BẢO MẬT MÃ XÁC MINH:\n"
                "• ⏳ **Hiệu lực 5 phút:** Mỗi mã chỉ có giá trị trong vòng **5 phút (300 giây)** kể từ thời điểm tạo và chỉ dùng **1 lần duy nhất**.\n"
                "• 🔄 **Ấn tạo mã mới sẽ hủy mã cũ:** Nếu bạn bấm nút lấy mã mới, mã cũ trước đó sẽ **tự động bị hủy bỏ ngay lập tức**."
            ),
            embed_type=EmbedType.INFO,
            color=0xA855F7,
            footer_text="Orbit | Vietnam • Hệ thống xác thực 2 bước Discord ↔ Web Portal",
        )

    async def auto_setup_verify_channel(self, purge: bool = False) -> None:
        """Tự động đăng hoặc cập nhật bảng lấy mã xác minh tại kênh #🔐・verify."""
        await ensure_web_verify_table(self.bot)

        ch_id = getattr(settings, "WEB_VERIFY_CHANNEL_ID", 1568268605085454416)
        if not ch_id or ch_id <= 0:
            return

        channel = self.bot.get_channel(ch_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(ch_id)
            except Exception as e:
                logger.warning(f"Không tìm thấy kênh WEB_VERIFY_CHANNEL_ID ({ch_id}): {e}")
                return

        if not isinstance(channel, discord.TextChannel):
            return

        embed = self.build_verify_channel_embed()
        view = WebVerifyControlView()

        try:
            if purge:
                try:
                    await channel.purge(limit=20)
                except Exception:
                    pass

            existing_bot_msgs: list[discord.Message] = []
            async for m in channel.history(limit=15):
                if self.bot.user and m.author.id == self.bot.user.id:
                    existing_bot_msgs.append(m)

            if existing_bot_msgs:
                target_msg = existing_bot_msgs[0]
                for extra in existing_bot_msgs[1:]:
                    try:
                        await extra.delete()
                    except Exception:
                        pass
                await target_msg.edit(content="", embed=embed, view=view, attachments=[])
                logger.info(f"✅ Đã cập nhật bảng lấy mã xác minh Web tại #{channel.name} ({channel.id})")
            else:
                await channel.send(embed=embed, view=view)
                logger.info(f"✅ Đã đăng mới bảng lấy mã xác minh Web tại #{channel.name} ({channel.id})")
        except Exception as e:
            logger.error(f"Lỗi khi thiết lập kênh #verify ({ch_id}): {e}")


async def setup(bot: commands.Bot) -> None:
    bot.add_view(WebVerifyControlView())
    await bot.add_cog(WebVerifyCog(bot))
