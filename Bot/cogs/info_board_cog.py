"""Sổ tay thông tin, bảng giá và đặc quyền các Gói Hyper (Info Board Cog).

Tự động ghim và duy trì bảng thông tin thẩm mỹ cao tại kênh #📄・info (ID: 1550896576636129320):
- Chi tiết 4 Gói: Free, Pro, Ultra, Elite
- Bảng công thức tính Token và mốc benchmark
- Chuỗi pipeline AI 3 model và quy trình xuất 2 file độc lập
- Hướng dẫn nhận gói (Admin cấp Role trực tiếp trên server)
"""

from __future__ import annotations

import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("InfoBoardCog")

INFO_CHANNEL_ID = getattr(settings, "INFO_CHANNEL_ID", 1550896576636129320)


class InfoBoardRefreshView(discord.ui.View):
    """View chứa nút bấm kiểm tra token nhanh từ kênh info."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Kiểm Tra Token Của Bạn",
        style=discord.ButtonStyle.primary,
        emoji="💳",
        custom_id="hyper_info_check_token_btn",
    )
    async def check_token_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        try:
            from not_finished.exam_generator.services.user_token_service import user_token_service
        except ImportError:
            from services.user_token_service import user_token_service

        user = interaction.user
        member_obj = interaction.guild.get_member(user.id) if interaction.guild else None
        token_data = await user_token_service.get_or_sync_user_token(user.id, member_obj)
        secs_left = user_token_service.get_seconds_until_next_reset()
        reset_unix = int(datetime.datetime.now(datetime.timezone.utc).timestamp() + secs_left)

        if token_data["is_unlimited"]:
            bar = "`[██████████████]` *(Không giới hạn)*"
            rem = "Vô hạn (**∞**)"
        else:
            bar = user_token_service.render_progress_bar(
                token_data["used_tokens_today"], token_data["daily_tokens"]
            )
            rem = f"**{token_data['remaining_tokens']}** / **{token_data['daily_tokens']}**"

        embed = discord.Embed(
            title=f"{token_data['tier_icon']} Thông Tin Token • {user.display_name}",
            color=token_data["color"],
        )
        embed.add_field(name="💎 Gói", value=f"**{token_data['tier_name']}**", inline=True)
        embed.add_field(name="⚡ Còn lại", value=rem, inline=True)
        embed.add_field(name="📊 Tiến trình", value=f"{bar}\nĐã dùng: **{token_data['used_tokens_today']}** tk", inline=False)
        embed.add_field(name="⏳ Reset", value=f"<t:{reset_unix}:R> *(00:00 UTC+7)*", inline=True)
        embed.set_footer(text="Dùng lệnh /check ở bất kỳ đâu để xem chi tiết")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class InfoBoardCog(commands.Cog, name="InfoBoard"):
    """Cog quản lý bảng thông tin Gói Hyper tại kênh #📄・info."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(InfoBoardRefreshView())

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Tự động kiểm tra và đăng bảng thông tin khi bot khởi động."""
        await self.ensure_info_board()

    @app_commands.command(
        name="refresh_info",
        description="[Admin] Làm mới và đăng lại bảng thông tin tại kênh #📄・info",
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_info_cmd(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Bạn cần quyền Administrator!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self.ensure_info_board(force=True)
        await interaction.followup.send("✅ Đã cập nhật thành công bảng thông tin tại <#1550896576636129320>!", ephemeral=True)

    async def ensure_info_board(self, force: bool = False) -> None:
        """Đảm bảo bảng thông tin luôn hiện diện đẹp mắt tại kênh #📄・info."""
        channel = self.bot.get_channel(INFO_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            if not force:
                async for msg in channel.history(limit=15):
                    if msg.author.id == self.bot.user.id and msg.embeds:
                        if "SỔ TAY GÓI THÀNH VIÊN" in (msg.embeds[0].title or ""):
                            return  # Đã có bảng thông tin

            # Xóa các tin nhắn cũ nếu force
            if force:
                async for msg in channel.history(limit=10):
                    if msg.author.id == self.bot.user.id:
                        try:
                            await msg.delete()
                        except Exception:
                            pass

            # Embed 1: Bảng 4 Gói Dịch Vụ
            e1 = discord.Embed(
                title="📚 SỔ TAY GÓI THÀNH VIÊN & NỀN TẢNG HYPERHUB AI GENERATOR",
                description=(
                    "Hệ thống tạo đề thi, bài tập và tài liệu học tập tự động ứng dụng chuỗi AI tiên tiến.\n"
                    "Cơ chế tự động kích hoạt gói dựa trên **Role Discord** do Ban Quản Trị cấp trực tiếp."
                ),
                color=0x5865F2,
            )

            e1.add_field(
                name="🆓 Hyper Free • Gói Mặc Định Miễn Phí",
                value=(
                    "• **Hạn mức:** `200 Tokens/ngày` (Tự động làm mới lúc 00:00 UTC+7)\n"
                    "• **Quy mô:** Tối đa cấp **Dài** (8–12 trang)\n"
                    "• **Chế độ:** Hỗ trợ `Lite`, `Flash`, `Pro`\n"
                    "• **Đối tượng:** Tất cả thành viên mới tham gia máy chủ."
                ),
                inline=False,
            )

            e1.add_field(
                name="🟣 Hyper Pro • Gói Nâng Cao",
                value=(
                    "• **Hạn mức:** `700 Tokens/ngày`\n"
                    "• **Quy mô:** Mở khóa cấp **To (>15 trang)** chuyên sâu\n"
                    "• **Chế độ:** Mở khóa chế độ `Max` và `Ultra` (phản biện chuyên sâu)\n"
                    "• **Ưu tiên:** Hàng đợi ưu tiên Cấp 2."
                ),
                inline=False,
            )

            e1.add_field(
                name="👑 Hyper Ultra • Gói Cao Cấp Nhất",
                value=(
                    "• **Hạn mức:** `2,800 Tokens/ngày` (Gấp 4 lần Gói Pro!)\n"
                    "• **Quy mô:** Không giới hạn số trang, mở full toàn bộ tính năng\n"
                    "• **Ưu tiên:** Hàng đợi ưu tiên Cấp 1, xử lý siêu tốc."
                ),
                inline=False,
            )

            e1.add_field(
                name="⚡ Hyper Elite • Đặc Quyền VVIP",
                value=(
                    "• **Hạn mức:** `Vô hạn (∞) Tokens`\n"
                    "• **Đặc quyền:** VVIP Priority hàng đầu, tự do khai thác mọi tính năng\n"
                    "• **Đối tượng:** Dành riêng cho Ban Quản Trị và Đối Tác Chiến Lược."
                ),
                inline=False,
            )

            # Embed 2: Công Thức & Bảng Chi Phí Token
            e2 = discord.Embed(
                title="💰 BẢNG TÍNH TOÁN CHI PHÍ TOKEN MINH BẠCH",
                description=(
                    "Hệ thống tính toán chi phí token theo công thức chuẩn xác tuyệt đối:\n"
                    "```\n"
                    "Chi Phí = Điểm Độ Dài × Hệ Số Chế Độ × Hệ Số Môn Học\n"
                    "```"
                ),
                color=0x9B59B6,
            )

            e2.add_field(
                name="📏 1. Điểm Độ Dài (Base Points)",
                value=(
                    "• **Ngắn (2–3 trang):** `10 pts`\n"
                    "• **Vừa (4–6 trang):** `20 pts`\n"
                    "• **Dài (8–12 trang):** `35 pts`\n"
                    "• **To (>15 trang):** `60 pts` *(Pro trở lên)*"
                ),
                inline=True,
            )

            e2.add_field(
                name="⚡ 2. Hệ Số Chế Độ (Mode)",
                value=(
                    "• **Lite:** `x1.0` *(Tạo nhanh)*\n"
                    "• **Flash:** `x1.5` *(Cân bằng)*\n"
                    "• **Pro:** `x2.0` *(Suy nghĩ sâu)*\n"
                    "• **Max:** `x3.0` *(Cực cao - Pro+)*\n"
                    "• **Ultra:** `x4.0` *(Đỉnh cao - Pro+)*"
                ),
                inline=True,
            )

            e2.add_field(
                name="🎯 3. Hệ Số Môn Học",
                value=(
                    "• **Cơ bản (x1.0):** Toán, Lý, Hóa, Sinh, Sử, Địa, GDCD...\n"
                    "• **Nâng cao (x1.2):** Lập trình C++, Python, Chuyên đề HSG...\n"
                    "• **Quốc tế (x1.4):** IELTS 8.0, JLPT N1-N2, HSK 5-6, SAT..."
                ),
                inline=False,
            )

            e2.add_field(
                name="📊 Ví Dụ Benchmark Thực Tế",
                value=(
                    "• **Free (200 tk/ngày):** Đề IELTS 8.0 + Dài (35) + Pro (2.0) = `98 ≈ 100 tk` ➔ **Dùng đúng 2 lần/ngày**!\n"
                    "• **Pro (700 tk/ngày):** Đề IELTS 8.0 + To (60) + Ultra (4.0) = `336 ≈ 350 tk` ➔ **Dùng đúng 2 lần/ngày**!\n"
                    "• **Ultra (2,800 tk/ngày):** Đề IELTS 8.0 To Ultra (350 tk) ➔ **Dùng đúng 8 lần/ngày**!"
                ),
                inline=False,
            )

            # Embed 3: Quy trình AI & Cam kết chất lượng
            e3 = discord.Embed(
                title="🛡️ QUY TRÌNH XUẤT BẢN & CAM KẾT CHẤT LƯỢNG",
                description=(
                    "• **Chuỗi AI 3 Model Phối Hợp:** `Qwen 3.5:4B` soạn thảo ➔ `Gemma 3:4B` phản biện logic 2 vòng ➔ `Qwen 2.5:0.5B` quét chính tả.\n"
                    "• **Xuất 2 File Riêng Biệt:** Luôn tách rời `[De_Thi]` (sạch in ấn) và `[Huong_Dan_Giai]` (lời giải & thang điểm).\n"
                    "• **Tự Động Vẽ Hình:** Hỗ trợ sơ đồ Oxy, hình học, lưu đồ code chuẩn vector.\n"
                    "• **Dung Lượng Nhẹ:** Cả PDF và Word cam kết nghiêm ngặt `< 5MB`.\n"
                    "• **Cam Kết Hoàn 100% Token:** Bất kỳ sự cố gián đoạn nào sẽ được tự động bồi hoàn 100% token lập tức.\n"
                    "• **Lưu Trữ Kho Đề:** Khi đóng Ticket, đề thi sẽ tự động được lưu trữ vào kênh `#database`."
                ),
                color=0x2ECC71,
            )
            e3.set_footer(text="HyperHub AI Platform • Bấm nút bên dưới để kiểm tra số dư Token")

            await channel.send(embeds=[e1, e2, e3], view=InfoBoardRefreshView())
            logger.info("Đã gửi thành công bộ 3 Embeds sổ tay thông tin tại #📄・info.")
        except Exception as e:
            logger.error(f"Lỗi khi gửi bảng thông tin: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoBoardCog(bot))
