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
                title="🌌 CHÀO MỪNG ĐẾN VỚI ORBIT • LEARN — CHILL — STUDY",
                description=(
                    "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "　🪐 **HỆ SINH THÁI HỌC TẬP & CÔNG NGHỆ ORBIT**\n"
                    "　*Không Gian Học Tập • Thư Giãn Tập Trung • Ôn Luyện Hiệu Quả (Vietnam)*\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🌟 **Ý NGHĨA BIỂU TƯỢNG ORBIT:**\n"
                    "• 🌙 **Vầng Trăng Khuyết (The Crescent):** Đại diện cho hành trình tích lũy tri thức không ngừng nghỉ. Mỗi ngày học hỏi là một bước tiến để hoàn thiện bản thân.\n"
                    "• 🪐 **Vòng Quỹ Đạo Đa Chiều (Orbital Ring):** Tượng trưng cho sự gắn kết cộng đồng, chu kỳ học tập tuần hoàn liên tục và khát vọng bứt phá trong kỷ nguyên công nghệ.\n"
                    "• 🎨 **Gam Màu Cosmic Neon (Purple & Rose Magenta):** Sự kết hợp hài hòa giữa chiều sâu tư duy (Tím Vũ Trụ) và nhiệt huyết, sáng tạo tuổi trẻ (Hồng Phát Quang).\n\n"
                    "🏛️ **4 TRỤ CỘT HỆ SINH THÁI TOÀN DIỆN:**\n"
                    "• 🌐 **Orbit Web Hub (https://orbit-psi-black.vercel.app/):** Nền tảng học tập trung tâm tích hợp Kho Đề Thi, Nộp Đề Trực Tuyến, Diễn Đàn Discord Forum Sync, Phòng Tự Học Pomodoro & Bảng Xếp Hạng Học Giả.\n"
                    "• 📚 **Thư Viện Đề Thi Tự Động (Doc Vault):** Lưu trữ 184+ đề thi THPT/THCS chuẩn form Bộ GD&ĐT 2025, kiểm định chống trùng lặp đa tầng, hỗ trợ đọc PDF & làm đề bấm giờ trực tuyến.\n"
                    "• 💡 **Diễn Đàn Thảo Luận Đồng Bộ (Forum 2-Way Sync):** Kênh thảo luận cộng đồng trên `💡・diễn-đàn` được đồng bộ 2 chiều tức thì với giao diện Web hiện đại.\n"
                    "• ⏱️ **Phòng Tự Học & Chuỗi Ngày Học (Streak):** Không gian tập trung cao độ, đồng bộ thời gian tự học, check-in chuỗi ngày học liên tục và tích lũy XP học thuật."
                ),
                color=0xA855F7,
            )
            e0.set_footer(text="Orbit Community | Vietnam")

            e1 = discord.Embed(
                title="🗺️ SƠ ĐỒ ĐIỀU HƯỚNG CÁC KÊNH TRONG MÁY CHỦ",
                description=(
                    "Để trải nghiệm tốt nhất tại máy chủ **Orbit**, bạn có thể khám phá theo các khu vực chức năng sau:\n\n"
                    "📌 **KHU VỰC THÔNG TIN (CHÍNH THỨC):**\n"
                    "• <#1532628139249893397> : Nội quy máy chủ & văn hóa ứng xử.\n"
                    "• <#1534148107712073788> : Cổng chào đón tân học giả tham gia Orbit.\n"
                    "• <#1534148186942214226> : Cẩm nang toàn diện hệ sinh thái & tính năng.\n"
                    "• <#1534545282497253566> : Chi tiết hệ thống phân quyền & vai trò (Roles).\n\n"
                    "📚 **KHU VỰC TÀI LIỆU & ĐỀ THI:**\n"
                    "• <#1567532842617937931> : Cổng tra cứu, tải về & làm đề thi trực tiếp trên Web Hub.\n"
                    "• <#1535278288828633138> : Cổng hướng dẫn nộp đề & ghi nhận credit đóng góp vĩnh viễn trên Web Hub.\n\n"
                    "💬 **KHU VỰC CỘNG ĐỒNG:**\n"
                    "• <#1532265332545425561> : Kênh trò chuyện tự do, kết nối học tập.\n"
                    "• <#1535557885721841744> : Diễn đàn học thuật, hỏi đáp bài tập, ôn thi (Đồng bộ 2 chiều với Web).\n"
                    "• <#1535558236957188176> : Tra cứu lệnh bot & tiện ích hệ thống.\n\n"
                    "🎙️ **KHU VỰC VOICE CHAT & TỰ HỌC:**\n"
                    "• <#1535557467260461076> : Phòng học bài với nền nhạc lofi chill 24/7.\n"
                    "• <#1535557505948590181> / <#1535557542049226763> : Phòng học nhóm & tự học tập trung (Focus)."
                ),
                color=0x3B82F6,
            )
            e1.set_footer(text="✦ Orbit • Learn · Chill · Connect · Enjoy")

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
