"""Sổ tay thông tin, bảng giá và đặc quyền các Gói Orbit (Info Board Cog).

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

INFO_CHANNEL_ID = getattr(settings, "INFO_CHANNEL_ID", 1534148186942214226)
WELCOME_CHANNEL_ID = 1534148107712073788
SAPPHIRE_BOT_ID = 678344927997853742



class InfoBoardRefreshView(discord.ui.View):
    """View chứa nút bấm kiểm tra token nhanh từ kênh info."""

    def __init__(self):
        super().__init__(timeout=None)
        # Nút liên kết trực tiếp tới các nền tảng trong hệ sinh thái Orbit
        self.add_item(
            discord.ui.Button(
                label="Truy Cập Orbit Web Hub",
                url="https://orbit-psi-black.vercel.app/",
                style=discord.ButtonStyle.link,
                emoji="🌐",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Nhóm Messenger Orbit",
                url="https://m.me/j/AbZngp-x0Ny92IWH/",
                style=discord.ButtonStyle.link,
                emoji="💬",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Kho Tài Nguyên GitHub",
                url="https://github.com/DaiVietForWork-81",
                style=discord.ButtonStyle.link,
                emoji="📂",
            )
        )

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
    """Cog quản lý bảng thông tin Gói Orbit tại kênh #📄・info."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(InfoBoardRefreshView())

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Tự động kiểm tra và đăng bảng thông tin khi bot khởi động."""
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
                    "│ 📄・**tài-liệu-tham-khảo**\n"
                    "│ └─ Tài liệu, tài nguyên & nguồn học tập hữu ích\n"
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
            welcome_embed.set_image(url="https://orbit-psi-black.vercel.app/orbit_full.png")
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
            bot_msgs: list[discord.Message] = []
            async for msg in channel.history(limit=20):
                if self.bot.user and msg.author.id == self.bot.user.id:
                    bot_msgs.append(msg)

            # Xóa toàn bộ tin nhắn cũ nếu force, hoặc xóa các bản bị trùng lặp thừa (chỉ giữ lại 1 tin nhắn mới nhất để edit)
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

            # Embed 0: Giới Thiệu Thương Hiệu & Logo Mới Orbit
            e0 = discord.Embed(
                title="🌌 CHÀO MỪNG ĐẾN VỚI ORBIT • LEARN — CHILL — STUDY",
                description=(
                    "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    "　🪐 **HỆ SINH THÁI HỌC TẬP & CÔNG NGHỆ ORBIT**\n"
                    "　*Không Gian Học Tập • Thư Giãn Tập Trung • Ôn Luyện Hiệu Quả (Vietnam)*\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    "🌟 **Ý NGHĨA BIỂU TƯỢNG LOGO MỚI (ORBIT IDENTITY):**\n"
                    "• 🌙 **Vầng Trăng Khuyết (The Crescent):** Đại diện cho hành trình tích lũy tri thức không ngừng nghỉ. Mỗi ngày học hỏi là một bước tiến để hoàn thiện bản thân.\n"
                    "• 🪐 **Vòng Quỹ Đạo Đa Chiều (Orbital Ring):** Tượng trưng cho sự gắn kết cộng đồng, chu kỳ học tập tuần hoàn liên tục và khát vọng bứt phá trong kỷ nguyên công nghệ.\n"
                    "• 🎨 **Gam Màu Cosmic Neon (Purple & Rose Magenta):** Sự kết hợp hài hòa giữa chiều sâu tư duy (Tím Vũ Trụ) và nhiệt huyết, sáng tạo tuổi trẻ (Hồng Phát Quang).\n\n"
                    "🏛️ **4 TRỤ CỘT HỆ SINH THÁI TOÀN DIỆN:**\n"
                    "• 🌐 **Orbit Web Hub:** Nền tảng học tập, tra cứu đề thi, bảng xếp hạng và dashboard cá nhân hóa: https://orbit-psi-black.vercel.app/\n"
                    "• 🤖 **Orbit AI Generator:** Chuỗi 3 mô hình AI (`Qwen 3.5:4B` ➔ `Gemma 3:4B` ➔ `Qwen 2.5:0.5B`) tạo đề thi chuẩn cấu trúc in ấn.\n"
                    "• 📚 **Thư Viện Đề Thi Tự Động (Doc Intake):** Tự động quét mã hash SHA-256, nhận diện năm học, sở/trường ra đề và phân loại tài liệu vào kho lưu trữ.\n"
                    "• 🏆 **Sàn Đấu Thuật Toán (Competitive Hub):** Thi đấu 1:1, xếp hạng Codeforces và rèn luyện kỹ năng giải quyết bài toán Olympic."
                ),
                color=0xA855F7,
            )
            e0.set_thumbnail(url="https://orbit-psi-black.vercel.app/server_icon.png")
            e0.set_image(url="https://orbit-psi-black.vercel.app/orbit_full.png")
            e0.set_footer(text="Orbit Community | Vietnam")

            # Embed 1: Bảng 4 Gói Dịch Vụ
            e1 = discord.Embed(
                title="📚 SỔ TAY GÓI THÀNH VIÊN & NỀN TẢNG ORBIT AI GENERATOR",
                description=(
                    "Hệ thống tạo đề thi, bài tập và tài liệu học tập tự động ứng dụng chuỗi AI tiên tiến.\n"
                    "Cơ chế tự động kích hoạt gói dựa trên **Role Discord** do Ban Quản Trị cấp trực tiếp."
                ),
                color=0x5865F2,
            )

            e1.add_field(
                name="🆓 Orbit Free • Gói Mặc Định Miễn Phí",
                value=(
                    "• **Hạn mức:** `200 Tokens/ngày` (Tự động làm mới lúc 00:00 UTC+7)\n"
                    "• **Quy mô:** Tối đa cấp **Dài** (8–12 trang)\n"
                    "• **Chế độ:** Hỗ trợ `Lite`, `Flash`, `Pro`\n"
                    "• **Đối tượng:** Tất cả thành viên mới tham gia máy chủ."
                ),
                inline=False,
            )

            e1.add_field(
                name="🟣 Orbit Pro • Gói Nâng Cao",
                value=(
                    "• **Hạn mức:** `700 Tokens/ngày`\n"
                    "• **Quy mô:** Mở khóa cấp **To (>15 trang)** chuyên sâu\n"
                    "• **Chế độ:** Mở khóa chế độ `Max` và `Ultra` (phản biện chuyên sâu)\n"
                    "• **Ưu tiên:** Hàng đợi ưu tiên Cấp 2."
                ),
                inline=False,
            )

            e1.add_field(
                name="👑 Orbit Ultra • Gói Cao Cấp Nhất",
                value=(
                    "• **Hạn mức:** `2,800 Tokens/ngày` (Gấp 4 lần Gói Pro!)\n"
                    "• **Quy mô:** Không giới hạn số trang, mở full toàn bộ tính năng\n"
                    "• **Ưu tiên:** Hàng đợi ưu tiên Cấp 1, xử lý siêu tốc."
                ),
                inline=False,
            )

            e1.add_field(
                name="⚡ Orbit Elite • Đặc Quyền VVIP",
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
            e3.set_footer(text="Orbit AI Platform • Bấm nút bên dưới để kiểm tra số dư Token")

            if existing_msg is not None and not force:
                await existing_msg.edit(embeds=[e0, e1, e2, e3], view=InfoBoardRefreshView())
                logger.info("Đã cập nhật đồng bộ bộ 4 Embeds sổ tay thông tin Orbit tại #📄・info.")
            else:
                await channel.send(embeds=[e0, e1, e2, e3], view=InfoBoardRefreshView())
                logger.info("Đã gửi thành công bộ 4 Embeds sổ tay thông tin và giới thiệu Orbit tại #📄・info.")
        except Exception as e:
            logger.error(f"Lỗi khi gửi bảng thông tin: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoBoardCog(bot))
