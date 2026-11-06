"""Sổ tay thông tin và sơ đồ điều hướng hệ sinh thái Orbit (Info Board Cog).

Tự động ghim và duy trì bảng thông tin tại kênh #🔗・info (ID: 1534148186942214226):
- Giới thiệu hệ sinh thái Orbit & 4 trụ cột học tập
- Sơ đồ điều hướng các kênh chức năng trong máy chủ
- Nút truy cập nhanh Orbit Web Hub, Kho Đề Thi và Diễn Đàn
"""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("InfoBoardCog")

INFO_CHANNEL_ID = getattr(settings, "INFO_CHANNEL_ID", 1534148186942214226)
WELCOME_CHANNEL_ID = 1534148107712073788
SAPPHIRE_BOT_ID = 678344927997853742

WEB_URL = "https://orbit-psi-black.vercel.app/"
VAULT_URL = "https://orbit-psi-black.vercel.app/#vault"
FORUM_URL = "https://orbit-psi-black.vercel.app/#forum"


class InfoBoardRefreshView(discord.ui.View):
    """View chứa các nút liên kết nhanh tới nền tảng Web Orbit từ kênh info."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Truy Cập Orbit Web Hub",
                url=WEB_URL,
                style=discord.ButtonStyle.link,
                emoji="🌐",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Kho Đề Thi Trực Tuyến",
                url=VAULT_URL,
                style=discord.ButtonStyle.link,
                emoji="📚",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Diễn Đàn Thảo Luận",
                url=FORUM_URL,
                style=discord.ButtonStyle.link,
                emoji="💡",
            )
        )


class InfoBoardCog(commands.Cog, name="InfoBoard"):
    """Cog quản lý bảng thông tin hệ sinh thái Orbit tại kênh #🔗・info."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(InfoBoardRefreshView())

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Tự động kiểm tra và đồng bộ bảng thông tin khi bot khởi động."""
        await self.ensure_info_board()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Tự động chuyển đổi tin nhắn chào mừng từ Sapphire (nếu còn chữ HyperHub) sang thương hiệu Orbit."""
        if message.channel.id != WELCOME_CHANNEL_ID:
            return
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        has_hyper = "hyperhub" in (message.content or "").lower()
        if not has_hyper:
            for emb in message.embeds:
                if "hyperhub" in ((emb.title or "") + (emb.description or "") + (emb.footer.text if emb.footer and emb.footer.text else "")).lower():
                    has_hyper = True
                    break

        if not has_hyper:
            return

        try:
            new_content = (message.content or "").replace("HyperHub", "Orbit").replace("HYPERHUB", "ORBIT")
            welcome_embed = discord.Embed(
                title="💜 WELCOME TO THE ORBIT",
                description=(
                    "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "　✨ **LEARN • CHILL • CONNECT**\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🌌 **Orbit** là nơi bạn có thể học cùng mọi người, tập trung một mình với nhạc chill, tìm tài liệu, giao lưu và giải trí sau những giờ học.\n\n"
                    "╭─ 🧭・**BẮT ĐẦU TẠI ĐÂY** ─────╮\n"
                    "│ 📜・**rules**\n"
                    "│ └─ Nội quy & quy định của Orbit\n"
                    "│ 🔗・**info**\n"
                    "│ └─ Thông tin, hướng dẫn & giới thiệu server\n"
                    "│ 🎭・**role-info**\n"
                    "│ └─ Thông tin & ý nghĩa của các role\n"
                    "╰────────────────────────────╯\n\n"
                    "╭─ 📡・**TIN TỨC & CẬP NHẬT** ──╮\n"
                    "│ 📢・**announcements**\n"
                    "│ └─ Thông báo quan trọng từ Orbit\n"
                    "│ 🆕・**updates**\n"
                    "│ └─ Tin tức, thay đổi & cập nhật mới\n"
                    "╰────────────────────────────╯\n\n"
                    "╭─ 💬・**CỘNG ĐỒNG** ───────────╮\n"
                    "│ 💭・**chat-tổng**\n"
                    "│ └─ Trò chuyện, giao lưu & làm quen\n"
                    "│ 💡・**diễn-đàn**\n"
                    "│ └─ Đặt câu hỏi, thảo luận & chia sẻ ý tưởng\n"
                    "│ 📸・**media**\n"
                    "│ └─ Chia sẻ ảnh, video & những khoảnh khắc thú vị\n"
                    "╰────────────────────────────╯\n\n"
                    "╭─ 📚・**HỌC TẬP** ─────────────╮\n"
                    "│ 📥・**lấy-tài-liệu**\n"
                    "│ └─ Tra cứu & tải đề thi trực tuyến trên Web Hub\n"
                    "│ 📄・**nộp-tài-liệu**\n"
                    "│ └─ Đóng góp đề thi & nhận vinh danh Credit\n"
                    "╰────────────────────────────╯\n\n"
                    "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "　🌙 **STUDY WHEN YOU WANT**\n"
                    "　🎧 **CHILL WHEN YOU NEED**\n"
                    "　💜 **CONNECT WHEN YOU'RE READY**\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "> ✦ **Rất vui khi có bạn ở đây!**\n"
                    "> Khám phá Orbit và tìm cho mình một góc riêng nhé. 🌌"
                ),
                color=0xA855F7,
            )
            welcome_embed.set_author(name="✦ O R B I T ✦")
            welcome_embed.set_footer(text="✦ Orbit • Learn · Chill · Connect · Enjoy")

            await message.channel.send(
                content=new_content,
                embed=welcome_embed,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
            await message.delete()
        except Exception as e:
            logger.warning(f"Không thể chuyển đổi tin nhắn chào mừng sang Orbit: {e}")

    @app_commands.command(
        name="refresh_info",
        description="[Admin] Làm mới và đăng lại bảng thông tin tại kênh #🔗・info",
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_info_cmd(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Bạn cần quyền Administrator!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self.ensure_info_board(force=True)
        await interaction.followup.send(f"✅ Đã cập nhật thành công bảng thông tin tại <#{INFO_CHANNEL_ID}>!", ephemeral=True)

    async def ensure_info_board(self, force: bool = False) -> None:
        """Đảm bảo bảng thông tin luôn hiện diện đẹp mắt tại kênh #🔗・info (không gắn logo/thumbnail)."""
        channel = self.bot.get_channel(INFO_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            bot_msgs: list[discord.Message] = []
            async for msg in channel.history(limit=20):
                if self.bot.user and msg.author.id == self.bot.user.id:
                    bot_msgs.append(msg)

            existing_msg: Optional[discord.Message] = None
            if force:
                for m in bot_msgs:
                    try:
                        await m.delete()
                    except Exception:
                        pass
            elif bot_msgs:
                existing_msg = bot_msgs[0]
                for extra_m in bot_msgs[1:]:
                    try:
                        await extra_m.delete()
                    except Exception:
                        pass

            e0 = discord.Embed(
                title="🌌 CHÀO MỪNG ĐẾN VỚI ORBIT | VIETNAM",
                description=(
                    "**Orbit** là không gian học tập, chia sẻ đề thi thực chiến và kết nối cộng đồng học sinh — sinh viên Việt Nam (**Learn • Chill • Connect**).\n\n"
                    "🏛️ **4 TRỤ CỘT HỆ SINH THÁI ORBIT (100% MIỄN PHÍ):**\n"
                    "• 🌐 **Orbit Web Hub (`orbit-psi-black.vercel.app`)** — Trung tâm tra cứu kho đề, nộp đề vinh danh tác giả, diễn đàn học thuật và phòng tự học Pomodoro.\n"
                    "• 📚 **Kho Đề Thi Thực Chiến (Doc Vault)** — Hơn 184+ đề thi THPT/THCS/HSG/Chuyên chuẩn Bộ GD&ĐT 2025, đọc PDF và bấm giờ làm bài trực tiếp.\n"
                    "• 💡 **Diễn Đàn Học Thuật 2 Chiều** — Thảo luận bài tập, hỏi đáp & chia sẻ kiến thức đồng bộ tức thì giữa Web và <#1535557885721841744>.\n"
                    "• ⏱️ **Phòng Tự Học & Vinh Danh Tác Giả** — Không gian tập trung Pomodoro 25/5 và vinh danh Học Giả đóng góp đề thi."
                ),
                color=0xA855F7,
            )
            e0.set_footer(text="Orbit | Vietnam • Hệ Sinh Thái Học Tập & Kho Đề Thi Mở")

            e1 = discord.Embed(
                title="🗺️ SƠ ĐỒ ĐIỀU HƯỚNG CÁC KÊNH CHÍNH",
                description=(
                    "📌 **THÔNG TIN & ĐỊNH HƯỚNG**\n"
                    "• <#1532628139249893397> — Nội quy máy chủ & văn hóa ứng xử.\n"
                    "• <#1534148186942214226> — Giới thiệu hệ sinh thái & sơ đồ máy chủ.\n"
                    "• <#1534545282497253566> — Hệ thống vai trò, danh hiệu & đặc quyền.\n"
                    "• <#1534148289450741770> / <#1535557678615756903> — Thông báo & cập nhật mới nhất.\n\n"
                    "📚 **KHO ĐỀ THI & HỌC THUẬT**\n"
                    "• <#1567532842617937931> — Cổng tra cứu, xem trước & tải đề thi trên Web Hub.\n"
                    "• <#1535278288828633138> — Đóng góp đề thi, nhận **Credit vĩnh viễn + Role ✍️ Tác giả**.\n"
                    "• <#1544204803016630302> — Tổng hợp lộ trình ôn tập & tài liệu trọng tâm.\n\n"
                    "💬 **CỘNG ĐỒNG & TIỆN ÍCH**\n"
                    "• <#1532265332545425561> — Trò chuyện chung & giao lưu thành viên.\n"
                    "• <#1535557885721841744> — Diễn đàn hỏi đáp bài tập & chia sẻ kinh nghiệm ôn thi.\n"
                    "• <#1535558236957188176> — Khu vực sử dụng lệnh Slash Commands của Bot.\n"
                    "• <#1546522680638054461> — Trạm kiểm tra độ an toàn của đường dẫn (URL).\n\n"
                    "🎙️ **PHÒNG TỰ HỌC & VOICE**\n"
                    "• <#1535557467260461076> • <#1535557505948590181> • <#1535557542049226763>"
                ),
                color=0x3B82F6,
            )
            e1.set_footer(text="Orbit | Vietnam • Nhấn các nút bên dưới để mở nhanh Web Portal")

            if existing_msg is not None and not force:
                await existing_msg.edit(embeds=[e0, e1], view=InfoBoardRefreshView())
                logger.info("Đã cập nhật đồng bộ bộ 2 Embeds thông tin Orbit tại #🔗・info.")
            else:
                await channel.send(embeds=[e0, e1], view=InfoBoardRefreshView())
                logger.info("Đã gửi thành công bộ 2 Embeds thông tin Orbit tại #🔗・info.")
        except Exception as e:
            logger.error(f"Lỗi khi gửi bảng thông tin: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoBoardCog(bot))
