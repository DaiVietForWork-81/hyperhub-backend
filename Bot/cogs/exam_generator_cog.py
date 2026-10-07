"""Hệ thống tạo đề thi AI qua Ticket đàm thoại và lưu trữ kho đề (Exam Generator Cog).

Quản lý:
1. Bảng điều khiển ghim tại #📄・generate (ID: 1550896415046377615)
2. Mở Private Thread làm Ticket tạo đề
3. Đàm thoại 5 bước tương tác bằng tin nhắn chat
4. Tính toán token theo công thức chuẩn, trừ token và hoàn 100% nếu lỗi
5. Cập nhật tiến trình thời gian thực (real-time dynamic editing message)
6. Đóng gói 2 file độc lập [De_Thi] và [Huong_Dan_Giai] < 5MB
7. Nút [🔒 Đóng Ticket] lưu trữ tự động vào #database (ID: 1548627763467128912)
8. Bộ đếm 2 tiếng tự động đóng ticket và gửi file qua DM nếu người dùng quên
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import time
import uuid
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

try:
    from not_finished.exam_generator.services.document_exporter import document_exporter
    from not_finished.exam_generator.services.exam_blueprint_engine import (
        ExamBlueprintEngine,
        exam_blueprint_engine,
    )
    from not_finished.exam_generator.services.exam_generator_service import exam_generator_service
    from not_finished.exam_generator.services.exam_shuffler import exam_shuffler
    from not_finished.exam_generator.services.user_token_service import user_token_service
except ImportError:
    from services.document_exporter import document_exporter
    from services.exam_blueprint_engine import (
        ExamBlueprintEngine,
        exam_blueprint_engine,
    )
    from services.exam_generator_service import exam_generator_service
    from services.exam_shuffler import exam_shuffler
    from services.user_token_service import user_token_service
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("ExamGeneratorCog")

GENERATE_CHANNEL_ID = getattr(settings, "GENERATE_CHANNEL_ID", 1550896415046377615)
DATABASE_ARCHIVE_CHANNEL_ID = getattr(settings, "DATABASE_ARCHIVE_CHANNEL_ID", 1548627763467128912)

# Thư mục lưu trữ tạm thời các file đề thi
EXAM_EXPORTS_DIR = os.path.join("data", "generated_exams")


class CancelGenerationView(discord.ui.View):
    """View cho phép người dùng hủy an toàn tiến trình sinh bài và nhận hoàn 100% token."""

    def __init__(
        self,
        bot: commands.Bot,
        job_id: str,
        user_id: int,
        token_cost: int,
    ):
        super().__init__(timeout=1800)
        self.bot = bot
        self.job_id = job_id
        self.user_id = user_id
        self.token_cost = token_cost
        self.is_cancelled = False

    @discord.ui.button(
        label="Hủy & Hoàn 100% Token",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="hyper_cancel_gen_btn",
    )
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Chỉ người yêu cầu tạo đề hoặc Quản trị viên mới có thể hủy!",
                ephemeral=True,
            )
            return

        if self.is_cancelled:
            await interaction.response.send_message("⚠️ Tiến trình đã bị hủy trước đó!", ephemeral=True)
            return

        self.is_cancelled = True
        button.disabled = True
        button.label = "Đã Hủy"
        await interaction.response.edit_message(view=self)

        # Gửi tín hiệu hủy dịch vụ và hoàn token
        exam_generator_service.cancel_job(self.job_id)
        await user_token_service.refund_tokens(
            self.user_id, self.token_cost, reason=f"Người dùng hủy tiến trình ({self.job_id})"
        )
        await user_token_service.update_exam_job(job_id=self.job_id, status="CANCELLED")

        cancel_embed = discord.Embed(
            title="🛑 TIẾN TRÌNH ĐÃ ĐƯỢC HỦY AN TOÀN",
            description=(
                f"Đã dừng tiến trình tạo đề `{self.job_id}`.\n\n"
                f"💰 **Cam kết bồi hoàn:** Đã hoàn trả lại **100% ({self.token_cost} Tokens)** vào tài khoản của bạn!\n"
                f"Bạn có thể mở Ticket mới bất cứ lúc nào."
            ),
            color=0xED4245,
        )
        await interaction.followup.send(embed=cancel_embed)


class CloseTicketView(discord.ui.View):
    """View chứa nút bấm đóng ticket sau khi nhận đề thành công và nút xáo trộn mã đề."""

    def __init__(
        self,
        bot: commands.Bot,
        job_id: str,
        user_id: int,
        exam_files: list[str],
        solution_files: list[str],
        metadata: dict[str, Any],
        exam_data: Optional[dict[str, Any]] = None,
        output_dir: str = "",
        output_format: str = "Both",
        diagram_paths: Optional[list[str]] = None,
        audio_files: Optional[list[str]] = None,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.job_id = job_id
        self.user_id = user_id
        self.exam_files = list(exam_files)
        self.solution_files = list(solution_files)
        self.audio_files = list(audio_files or [])
        self.metadata = metadata
        self.exam_data = exam_data
        self.output_dir = output_dir
        self.output_format = output_format
        self.diagram_paths = diagram_paths or []
        self.is_closed = False
        self.shuffle_count = 0

    @discord.ui.button(
        label="Trộn Mã Đề (Mã 102, 103...)",
        style=discord.ButtonStyle.secondary,
        emoji="🔀",
        custom_id="hyper_shuffle_exam_btn",
    )
    async def shuffle_exam_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.is_closed:
            await interaction.response.send_message("⚠️ Ticket này đã đóng!", ephemeral=True)
            return

        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Chỉ người khởi tạo ticket hoặc Quản trị viên mới có thể trộn đề!",
                ephemeral=True,
            )
            return

        if not self.exam_data:
            job_rec = await user_token_service.get_exam_job(self.job_id)
            if job_rec and job_rec.checkpoint_data:
                try:
                    self.exam_data = json.loads(job_rec.checkpoint_data)
                except Exception:
                    pass

        if not self.exam_data:
            await interaction.response.send_message(
                "⚠️ Không tìm thấy dữ liệu cấu trúc đề để xáo trộn!", ephemeral=True
            )
            return

        await interaction.response.defer()
        self.shuffle_count += 1

        try:
            shuffled_data = exam_shuffler.shuffle_exam(self.exam_data)
            new_code = shuffled_data.get("metadata", {}).get("exam_code", f"HH-S{self.shuffle_count}")

            shuffled_meta = shuffled_data.get("metadata", {})
            shuffled_meta["job_id"] = f"{self.job_id}-{new_code}"

            shuffled_dir = os.path.join(self.output_dir, f"shuffled_{new_code}")
            os.makedirs(shuffled_dir, exist_ok=True)

            export_results = document_exporter.export_all(
                metadata=shuffled_meta,
                exam_data=shuffled_data,
                output_format=self.output_format,
                output_dir=shuffled_dir,
                diagram_paths=self.diagram_paths,
            )

            shuffled_exam_files = export_results.get("exam_files", [])
            shuffled_sol_files = export_results.get("solution_files", [])

            d_files = []
            for p in shuffled_exam_files + shuffled_sol_files:
                if os.path.exists(p):
                    d_files.append(discord.File(p))

            shuffled_embed = discord.Embed(
                title=f"🔀 ĐÃ TRỘN THÀNH CÔNG MÃ ĐỀ: {new_code}",
                description=(
                    f"• **Mã đề gốc:** `{self.metadata.get('exam_code', self.job_id)}` ➔ **Mã đề mới:** `{new_code}`\n"
                    f"• **Xáo trộn:** Hoán vị ngẫu nhiên câu hỏi & vị trí A, B, C, D tự nhiên.\n"
                    f"• **Đồng bộ:** Cập nhật 100% bảng đáp án đúng tương ứng tức thì.\n"
                    f"• **Chi phí:** `0 Token` *(Miễn phí đặc quyền)*\n\n"
                    "📄 Cả 2 file bản in `[De_Thi]` và `[Huong_Dan_Giai]` của mã mới đã sẵn sàng tải bên dưới!"
                ),
                color=0x9B59B6,
            )
            shuffled_embed.set_footer(text=f"HyperHub AI Exam Shuffler Engine • {new_code}")

            if d_files:
                await interaction.followup.send(embed=shuffled_embed, files=d_files)
            else:
                await interaction.followup.send(embed=shuffled_embed)

            # Cập nhật DB
            await user_token_service.update_exam_job(job_id=self.job_id, status="COMPLETED", is_shuffled=True)
            self.exam_files.extend(shuffled_exam_files)
            self.solution_files.extend(shuffled_sol_files)

        except Exception as shuf_err:
            logger.error(f"Lỗi khi xáo trộn mã đề cho {self.job_id}: {shuf_err}", exc_info=True)
            await interaction.followup.send(f"⚠️ Không thể trộn mã đề: `{shuf_err}`", ephemeral=True)

    @discord.ui.button(
        label="Đóng Ticket & Lưu Trữ Kho Đề",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="hyper_close_ticket_btn",
    )
    async def close_ticket_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.is_closed:
            await interaction.response.send_message("⚠️ Ticket này đang được đóng...", ephemeral=True)
            return

        # Chỉ người tạo ticket hoặc Admin mới được bấm đóng
        if interaction.user.id != self.user_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Chỉ người khởi tạo ticket hoặc Quản trị viên mới có thể đóng ticket này!",
                ephemeral=True,
            )
            return

        self.is_closed = True
        button.disabled = True
        await interaction.response.edit_message(view=self)

        await interaction.followup.send("📦 Đang sao lưu bộ đề vào kho dữ liệu `#database` và đóng ticket...")
        await self._archive_and_close(thread=interaction.channel, closed_by="user")

    async def _archive_and_close(
        self, thread: Any, closed_by: str = "user"
    ) -> None:
        """Lưu toàn bộ file sang kênh #database và lưu trạng thái."""
        db_channel = self.bot.get_channel(DATABASE_ARCHIVE_CHANNEL_ID)
        db_msg_id = None

        if db_channel and isinstance(db_channel, discord.TextChannel):
            try:
                # Chuẩn bị đính kèm các file
                d_files = []
                for p in self.exam_files + self.solution_files + self.audio_files:
                    if os.path.exists(p):
                        d_files.append(discord.File(p))

                embed = discord.Embed(
                    title=f"📚 [LƯU TRỮ KHO ĐỀ] {self.metadata.get('subject', 'Đề Thi')} • Mã {self.metadata.get('exam_code', self.job_id)}",
                    description=(
                        f"• **Người tạo:** <@{self.user_id}>\n"
                        f"• **Độ dài:** {self.metadata.get('length_tier', 'Tiêu chuẩn')}\n"
                        f"• **Thời gian đóng:** <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp())}:F>\n"
                        f"• **Phương thức đóng:** {'Người dùng chủ động đóng' if closed_by == 'user' else 'Tự động đóng sau 2 tiếng'}\n"
                    ),
                    color=0x2ECC71,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                embed.set_footer(text=f"Job ID: {self.job_id} • HyperHub AI Exam Platform")

                if d_files:
                    msg = await db_channel.send(embed=embed, files=d_files)
                    db_msg_id = msg.id
                else:
                    msg = await db_channel.send(embed=embed)
                    db_msg_id = msg.id

                logger.info(f"Đã lưu trữ bộ đề {self.job_id} vào #database ({db_msg_id})")
            except Exception as arc_err:
                logger.error(f"Lỗi khi lưu trữ bộ đề vào #database: {arc_err}")

        # Cập nhật trạng thái job trong SQLite
        await user_token_service.update_exam_job(
            job_id=self.job_id,
            status="CLOSED",
            database_msg_id=db_msg_id,
        )

        # Đóng hoặc khóa thread
        if isinstance(thread, discord.Thread):
            try:
                await thread.edit(locked=True, archived=True)
            except Exception as th_err:
                logger.warning(f"Không thể khóa/lưu trữ thread: {th_err}")


class GenerateControlPanelView(discord.ui.View):
    """View ghim vĩnh viễn trên kênh #📄・generate."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Bắt Đầu Tạo Đề (Mở Ticket)",
        style=discord.ButtonStyle.primary,
        emoji="📩",
        custom_id="hyper_open_ticket_btn",
    )
    async def open_ticket_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        user = interaction.user
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("⚠️ Lệnh chỉ khả dụng trong máy chủ!", ephemeral=True)
            return

        # Kiểm tra số dư token tối thiểu
        member_obj = guild.get_member(user.id) if isinstance(user, discord.User) else user
        token_data = await user_token_service.get_or_sync_user_token(user.id, member_obj)
        if not token_data["is_unlimited"] and token_data["remaining_tokens"] < 10:
            await interaction.response.send_message(
                f"❌ Bạn đã dùng hết hạn mức Token hôm nay (**{token_data['used_tokens_today']}/{token_data['daily_tokens']}** Tokens)!\n"
                f"⏳ Hạn mức sẽ tự động được làm mới sau: <t:{int(datetime.datetime.now(datetime.timezone.utc).timestamp() + user_token_service.get_seconds_until_next_reset())}:R> *(00:00 UTC+7)*.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("⚠️ Kênh này không hỗ trợ tạo Thread!", ephemeral=True)
            return

        # Tạo Private Thread cho người dùng
        thread_name = f"📝・tạo-đề-{user.display_name[:12]}"
        try:
            thread = await channel.create_thread(
                name=thread_name,
                auto_archive_duration=1440,
                type=discord.ChannelType.private_thread,
                reason=f"HyperHub AI Generator Ticket cho {user.name}",
            )
            await thread.add_user(user)
        except Exception as e:
            logger.error(f"Lỗi khi tạo private thread: {e}")
            await interaction.followup.send(f"❌ Không thể tạo Ticket riêng tư ({e}). Vui lòng kiểm tra quyền Bot!", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Đã khởi tạo Ticket tạo đề thành công! Hãy vào kênh <#{thread.id}> để bắt đầu.",
            ephemeral=True,
        )

        # Bắt đầu luồng đàm thoại 5 bước trong Ticket
        cog: Optional[ExamGeneratorCog] = self.bot.get_cog("ExamGenerator")
        if cog:
            self.bot.loop.create_task(cog.run_ticket_intake(thread, user, token_data))

    @discord.ui.button(
        label="Kiểm Tra Token",
        style=discord.ButtonStyle.secondary,
        emoji="💳",
        custom_id="hyper_check_token_btn",
    )
    async def check_token_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
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
        embed.set_footer(text="Dùng lệnh /check để xem chi tiết lịch sử")

        await interaction.response.send_message(embed=embed, ephemeral=True)


class ExamGeneratorCog(commands.Cog, name="ExamGenerator"):
    """Cog điều phối quy trình tiếp nhận Ticket và sinh đề thi AI."""

    exam_group = app_commands.Group(
        name="exam",
        description="Bộ công cụ khảo thí và đề thi AI HyperHub",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @exam_group.command(
        name="search",
        description="Tìm kiếm và tái sử dụng các bộ đề thi trong Kho Thư Viện Đề",
    )
    @app_commands.describe(query="Từ khóa môn học, phong cách hoặc mã Job ID")
    async def search_exam_bank(
        self, interaction: discord.Interaction, query: str
    ) -> None:
        """Tìm kiếm và hiển thị các đề thi trong kho dữ liệu #database."""
        await interaction.response.defer(ephemeral=True)

        results = await user_token_service.search_exam_jobs(query=query, limit=5)
        if not results:
            await interaction.followup.send(
                f"🔍 Không tìm thấy bộ đề nào khớp với từ khóa `{query}` trong Kho Thư Viện Đề!",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📚 KHO THƯ VIỆN ĐỀ THI • KẾT QUẢ: `{query}`",
            description=f"Tìm thấy **{len(results)}** bộ đề thi chất lượng cao trong hệ thống:",
            color=0x2ECC71,
        )

        for job in results:
            time_str = f"<t:{int(job.created_at.timestamp())}:d>" if job.created_at else "Gần đây"
            shuf_info = "🔀 Đã trộn" if job.is_shuffled else "📄 Bản chuẩn"
            desc_val = (
                f"• **Môn thi:** `{job.subject}` ({job.length_tier} - {job.mode})\n"
                f"• **Tác giả:** <@{job.discord_id}> • {time_str}\n"
                f"• **Trạng thái:** {job.status} • {shuf_info}\n"
            )
            if job.exam_file_path and os.path.exists(job.exam_file_path):
                desc_val += f"• **Tệp đề:** `{os.path.basename(job.exam_file_path)}`\n"
            if job.database_msg_id:
                desc_val += f"• **Kho lưu trữ:** Kênh <#{DATABASE_ARCHIVE_CHANNEL_ID}>\n"

            embed.add_field(
                name=f"📝 Mã: {job.job_id}",
                value=desc_val,
                inline=False,
            )

        embed.set_footer(text="HyperHub AI Exam Bank • Học tập & Tái tạo")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_load(self) -> None:
        """Đăng ký Persistent View khi cog nạp."""
        self.bot.add_view(GenerateControlPanelView(self.bot))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Kiểm tra và tự động ghim bảng điều khiển tại kênh #📄・generate."""
        await self.ensure_control_panel()

    async def ensure_control_panel(self) -> None:
        """Đảm bảo bảng điều khiển chính luôn hiện diện ở kênh tạo đề."""
        channel = self.bot.get_channel(GENERATE_CHANNEL_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            # Tìm xem đã có tin nhắn bảng điều khiển của Bot chưa
            async for msg in channel.history(limit=15):
                if msg.author.id == self.bot.user.id and msg.embeds:
                    if "TRẠM KHẢO THÍ & THIẾT KẾ ĐỀ THI AI" in (msg.embeds[0].title or ""):
                        return  # Đã có bảng điều khiển

            embed = discord.Embed(
                title="📄 TRẠM KHẢO THÍ & THIẾT KẾ ĐỀ THI AI • HYPERHUB",
                description=(
                    "Chào mừng bạn đến với **Nền Tảng Sinh Đề Thi & Tài Liệu Học Tập AI Tự Động**.\n\n"
                    "✨ **Đặc quyền & Tính năng vượt trội:**\n"
                    "• **Chuỗi AI Đa Tầng:** Gói Free sử dụng `Qwen 2.5:4B` siêu tốc; Gói Pro/Ultra sử dụng `Qwen 3.5:4B` tư duy sâu (*deep thinking*) ➔ `Gemma 3:4B` phản biện ➔ `Qwen 2.5:0.5B` chuẩn hóa.\n"
                    "• **Xuất 2 File Độc Lập:** `[De_Thi]` sạch in ấn + `[Huong_Dan_Giai]` lời giải & rubric thang điểm chi tiết.\n"
                    "• **Hỗ trợ Sơ đồ Minh họa:** Tự động vẽ hệ trục tọa độ Oxy, hình học, flowchart lưu đồ thuật toán.\n"
                    "• **Định dạng:** Tùy chọn Word (.docx chuẩn sư phạm) và PDF vector sắc nét (`< 5MB`).\n"
                    "• **Cam kết hoàn 100% Token:** Bồi hoàn lập tức nếu hệ thống gặp sự cố.\n\n"
                    "👉 Bấm nút **[📩 Bắt Đầu Tạo Đề (Mở Ticket)]** bên dưới để khởi tạo đề thi của riêng bạn!"
                ),
                color=0x5865F2,
            )
            embed.add_field(
                name="💎 4 Gói Dịch Vụ & Hạn Mức",
                value=(
                    "🆓 **Hyper Free:** 200 Tokens/ngày\n"
                    "🟣 **Hyper Pro:** 700 Tokens/ngày\n"
                    "👑 **Hyper Ultra:** 2,800 Tokens/ngày\n"
                    "⚡ **Hyper Elite:** Vô hạn (∞) Tokens"
                ),
                inline=False,
            )
            embed.set_footer(text="HyperHub AI Platform • /check để xem hạn mức của bạn")
            await channel.send(embed=embed, view=GenerateControlPanelView(self.bot))
            logger.info("Đã gửi bảng điều khiển tạo đề mới tại #📄・generate.")
        except Exception as e:
            logger.warning(f"Không thể kiểm tra/gửi bảng điều khiển tạo đề: {e}")

    # =========================================================================
    # LUỒNG ĐÀM THOẠI 5 BƯỚC TRONG TICKET
    # =========================================================================
    async def run_ticket_intake(
        self, thread: discord.Thread, user: discord.User | discord.Member, token_data: dict[str, Any]
    ) -> None:
        """Đàm thoại từng câu hỏi với người dùng qua tin nhắn văn bản."""
        job_id = f"EXAM-{uuid.uuid4().hex[:6].upper()}"

        def check_msg(m: discord.Message) -> bool:
            return m.channel.id == thread.id and m.author.id == user.id

        async def ask_question(prompt_embed: discord.Embed) -> Optional[str]:
            await thread.send(embed=prompt_embed)
            try:
                msg = await self.bot.wait_for("message", timeout=600.0, check=check_msg)
                return msg.content.strip()
            except asyncio.TimeoutError:
                await thread.send("⏰ Hết thời gian chờ phản hồi (10 phút). Ticket sẽ tự động đóng lại.")
                await thread.edit(locked=True, archived=True)
                return None

        # Chào mừng
        welcome_embed = discord.Embed(
            title=f"👋 Chào mừng {user.display_name} đến với Ticket Tạo Đề!",
            description=(
                f"**Mã phiên:** `{job_id}`\n"
                f"**Gói hiện tại:** {token_data['tier_icon']} **{token_data['tier_name']}** "
                f"*(Còn lại: **{token_data['remaining_tokens']}** Tokens)*\n\n"
                "Bot sẽ lần lượt hỏi bạn **5 câu hỏi** ngắn để thiết kế đề thi chuẩn xác nhất. "
                "Hãy gõ câu trả lời của bạn vào kênh chat này."
            ),
            color=0x5865F2,
        )
        await thread.send(embed=welcome_embed)

        # CÂU 1: MÔN HỌC / CHỨNG CHỈ
        e1 = discord.Embed(
            title="📌 Câu 1/5: Môn học hoặc Kỳ thi bạn muốn tạo đề là gì?",
            description=(
                "Hãy nhập tên môn học, chứng chỉ hoặc kỳ thi mong muốn:\n"
                "*(Ví dụ: `IELTS 8.0`, `JLPT N1`, `HSK 5`, `Lập trình C++`, `Python`, `Toán 12`, `Vật Lý 11`, `Olympic Tin học`...)*"
            ),
            color=0x3498DB,
        )
        subject_ans = await ask_question(e1)
        if not subject_ans:
            return

        # CÂU 2: PHONG CÁCH & YÊU CẦU CHI TIẾT
        e2 = discord.Embed(
            title="📌 Câu 2/5: Phong cách và Yêu cầu cụ thể của đề thi?",
            description=(
                "Hãy mô tả chi tiết hình thức bài kiểm tra:\n"
                "• Trắc nghiệm khách quan chuẩn 4 đáp án (A, B, C, D)\n"
                "• Tự luận chuyên sâu có phân hóa học sinh giỏi\n"
                "• Bài tập thực hành code có ví dụ mẫu & giải thích thuật toán\n"
                "• Hoặc bất kỳ yêu cầu riêng biệt nào của bạn..."
            ),
            color=0x3498DB,
        )
        style_ans = await ask_question(e2)
        if not style_ans:
            return

        # CÂU 3: ĐỘ DÀI
        allow_to = token_data["allow_to_length"]
        e3_desc = (
            "Chọn quy mô đề thi phù hợp nhu cầu của bạn:\n"
            "1️⃣ **Ngắn** (2–3 trang kèm đáp án) • Cơ bản: `10 pts`\n"
            "2️⃣ **Vừa** (4–6 trang kèm đáp án) • Cơ bản: `20 pts`\n"
            "3️⃣ **Dài** (8–12 trang kèm đáp án) • Cơ bản: `35 pts`\n"
        )
        if allow_to:
            e3_desc += "4️⃣ **To** (>15 trang kèm đáp án) • Cơ bản: `60 pts` *(Đặc quyền Pro/Ultra/Elite)*\n"
        else:
            e3_desc += "🔒 **To** (>15 trang): *Yêu cầu Gói Pro trở lên!*\n"
        e3_desc += "\n*(Hãy gõ `Ngắn`, `Vừa`, `Dài` hoặc số `1`, `2`, `3`)*"

        e3 = discord.Embed(title="📌 Câu 3/5: Bạn muốn độ dài đề thi như thế nào?", description=e3_desc, color=0x3498DB)
        length_ans = await ask_question(e3)
        if not length_ans:
            return

        # Chuẩn hóa độ dài
        length_tier = "Vừa"
        la = length_ans.lower()
        if "1" in la or "ngắn" in la or "ngan" in la:
            length_tier = "Ngắn"
        elif "2" in la or "vừa" in la or "vua" in la:
            length_tier = "Vừa"
        elif "3" in la or "dài" in la or "dai" in la:
            length_tier = "Dài"
        elif "4" in la or "to" in la:
            if allow_to:
                length_tier = "To"
            else:
                await thread.send("⚠️ Bạn đang ở Gói **Hyper Free** nên chưa thể tạo đề cấp **To (>15 trang)**. Hệ thống tự động chuyển sang cấp **Dài**!")
                length_tier = "Dài"

        # CÂU 4: CHẾ ĐỘ SINH BÀI
        allow_max_ultra = token_data["allow_max_ultra_mode"]
        e4_desc = (
            "Chọn chế độ AI để cân đối tốc độ và chiều sâu học thuật:\n"
            "⚡ **Lite** (x1.0) • Tạo nhanh, chi tiết cơ bản\n"
            "🚀 **Flash** (x1.5) • Cân bằng tốc độ & độ sâu phản biện\n"
            "🧠 **Pro** (x2.0) • Suy nghĩ sâu, phản biện 2 vòng logic\n"
        )
        if allow_max_ultra:
            e4_desc += (
                "🔥 **Max** (x3.0) • Toàn diện, câu hỏi phân hóa cực cao *(Pro+)*\n"
                "👑 **Ultra** (x4.0) • Đỉnh cao khảo thí, thẩm định đa tầng *(Pro+)*\n"
            )
        else:
            e4_desc += "🔒 **Max** & **Ultra**: *Yêu cầu Gói Pro trở lên!*\n"
        e4_desc += "\n*(Hãy gõ `Lite`, `Flash`, `Pro`)*"

        e4 = discord.Embed(title="📌 Câu 4/5: Bạn muốn chọn Chế độ AI nào?", description=e4_desc, color=0x3498DB)
        mode_ans = await ask_question(e4)
        if not mode_ans:
            return

        # Chuẩn hóa mode
        mode = "Pro"
        ma = mode_ans.lower()
        if "lite" in ma:
            mode = "Lite"
        elif "flash" in ma:
            mode = "Flash"
        elif "max" in ma:
            mode = "Max" if allow_max_ultra else "Pro"
        elif "ultra" in ma:
            mode = "Ultra" if allow_max_ultra else "Pro"
        else:
            mode = "Pro"

        # CÂU 5: ĐỊNH DẠNG FILE
        e5 = discord.Embed(
            title="📌 Câu 5/5: Định dạng file bạn muốn nhận?",
            description=(
                "Hãy chọn định dạng xuất bản:\n"
                "📄 **PDF** (Bản in vector sắc nét, sẵn sàng in)\n"
                "📝 **Word** (.docx chuẩn format sư phạm, dễ dàng chỉnh sửa)\n"
                "📦 **Both** (Nhận cả 2 định dạng Word và PDF)\n\n"
                "*(Hãy gõ `PDF`, `Word` hoặc `Both`)*"
            ),
            color=0x3498DB,
        )
        format_ans = await ask_question(e5)
        if not format_ans:
            return

        output_format = "Both"
        fa = format_ans.lower()
        if "pdf" in fa and "word" not in fa and "both" not in fa:
            output_format = "PDF"
        elif "word" in fa and "pdf" not in fa and "both" not in fa:
            output_format = "Word"
        else:
            output_format = "Both"

        # =====================================================================
        # TÍNH TOÁN TOKEN & XÁC NHẬN
        # =====================================================================
        final_cost, cost_details = user_token_service.calculate_token_cost(
            length=length_tier, mode=mode, subject=subject_ans
        )

        can_afford, remaining, _ = await user_token_service.can_afford(user.id, final_cost)
        if not can_afford:
            insufficient_embed = discord.Embed(
                title="❌ Không đủ Token để thực hiện!",
                description=(
                    f"Chi phí yêu cầu: **{final_cost}** Tokens\n"
                    f"Token khả dụng hiện tại: **{remaining}** Tokens\n\n"
                    f"💡 Hãy thử chọn độ dài ngắn hơn hoặc chế độ nhẹ hơn, hoặc liên hệ Quản trị viên để nâng cấp Gói Hyper!"
                ),
                color=0xED4245,
            )
            await thread.send(embed=insufficient_embed)
            return

        # Khấu trừ token và ghi nhận Job
        await user_token_service.deduct_tokens(user.id, final_cost)
        await user_token_service.record_exam_job(
            job_id=job_id,
            discord_id=user.id,
            thread_id=thread.id,
            subject=subject_ans,
            style=style_ans,
            length_tier=length_tier,
            mode=mode,
            output_format=output_format,
            token_cost=final_cost,
        )

        assigned_model = "Qwen 2.5:4B (Free)" if token_data.get("tier") == "Free" else "Qwen 3.5:4B (Pro/Ultra Deep Thinking)"

        confirm_embed = discord.Embed(
            title="🎯 Xác Nhận Thông Số & Khởi Chạy Pipeline AI",
            description=(
                f"• **Môn thi:** `{subject_ans}` ({cost_details['subj_label']})\n"
                f"• **Quy mô:** **{length_tier}** (Cơ bản: `{cost_details['base_points']} pts`)\n"
                f"• **Chế độ:** **{mode}** (Hệ số: `x{cost_details['mode_mult']}`)\n"
                f"• **Mô hình AI:** `{assigned_model}`\n"
                f"• **Định dạng:** `{output_format}`\n"
                f"• **Chi phí:** **{final_cost}** Tokens *(Đã trừ vào tài khoản)*\n"
                f"• **Token còn lại:** **{remaining - final_cost if not token_data['is_unlimited'] else '∞'}** Tokens\n\n"
                "🚀 *Hệ thống đang điều phối chuỗi AI... Vui lòng theo dõi tiến trình bên dưới!*"
            ),
            color=0x2ECC71,
        )
        await thread.send(embed=confirm_embed)

        # =====================================================================
        # TIẾN TRÌNH THỜI GIAN THỰC (DYNAMIC EDITING PROGRESS & CANCEL VIEW)
        # =====================================================================
        cancel_view = CancelGenerationView(
            bot=self.bot,
            job_id=job_id,
            user_id=user.id,
            token_cost=final_cost,
        )

        progress_embed = discord.Embed(
            title="⚙️ Tiến Trình Xử Lý AI (Đang Thực Thi)",
            description="`[0/4]` ⏳ Đang nạp mô hình vào bộ nhớ...",
            color=0xFEE75C,
        )
        progress_msg = await thread.send(embed=progress_embed, view=cancel_view)

        async def update_progress(stage_text: str, progress: float):
            if cancel_view.is_cancelled:
                return
            try:
                progress_embed.description = stage_text
                progress_embed.set_footer(text=f"Tiến độ: {int(progress * 100)}% • Chuỗi AI HyperHub")
                await progress_msg.edit(embed=progress_embed)
            except Exception as pe:
                logger.debug(f"Lỗi cập nhật tiến trình: {pe}")

        # Thư mục xuất file của phiên này
        job_output_dir = os.path.join(EXAM_EXPORTS_DIR, job_id)
        gen_start_time = time.time()

        try:
            gen_result = await exam_generator_service.generate_exam(
                job_id=job_id,
                subject=subject_ans,
                style=style_ans,
                length_tier=length_tier,
                mode=mode,
                output_format=output_format,
                output_dir=job_output_dir,
                progress_callback=update_progress,
                tier=token_data.get("tier", "Free"),
            )
        except Exception as gen_err:
            if cancel_view.is_cancelled:
                return  # Đã xử lý bồi hoàn ở CancelGenerationView

            logger.error(f"Sự cố khi sinh đề thi cho {job_id}: {gen_err}", exc_info=True)
            # HOÀN 100% TOKEN
            await user_token_service.refund_tokens(user.id, final_cost, reason=f"Lỗi sinh bài: {gen_err}")
            await user_token_service.update_exam_job(job_id=job_id, status="FAILED")

            error_embed = discord.Embed(
                title="⚠️ Sự Cố Trong Quá Trình Sinh Bài",
                description=(
                    f"Rất tiếc! Hệ thống gặp sự cố trong chuỗi xử lý AI: `{gen_err}`.\n\n"
                    f"✨ **Cam kết bồi hoàn:** Đã hoàn trả lại **100% ({final_cost} Tokens)** vào tài khoản của bạn!\n"
                    f"Bạn có thể mở Ticket mới để thử lại bất kỳ lúc nào."
                ),
                color=0xED4245,
            )
            await thread.send(embed=error_embed)
            return

        if cancel_view.is_cancelled:
            return

        # Vô hiệu hóa nút hủy khi đã hoàn thành
        cancel_view.is_cancelled = True
        for item in cancel_view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                item.label = "Đã Hoàn Thành"
        try:
            await progress_msg.edit(view=cancel_view)
        except Exception:
            pass

        # Kiểm tra cơ chế tự phục hồi & bồi hoàn 50% nếu thời gian chờ quá tải kéo dài (> 1 tiếng)
        gen_duration = time.time() - gen_start_time
        if gen_duration > 3600:
            refund_half = max(1, int(final_cost * 0.5))
            await user_token_service.refund_tokens(
                user.id, refund_half, reason=f"Bồi hoàn 50% do tiến trình kéo dài ({int(gen_duration // 60)} phút)"
            )
            delay_embed = discord.Embed(
                title="🎁 CHÍNH SÁCH BỒI HOÀN TRỄ HẠN THỜI GIAN",
                description=(
                    f"Do hệ thống điều phối chuỗi AI bị quá tải và mất nhiều thời gian hơn dự kiến ({int(gen_duration // 60)} phút),\n"
                    f"HyperHub đã tự động **hoàn lại 50% ({refund_half} Tokens)** vào tài khoản của bạn như một lời xin lỗi chân thành!"
                ),
                color=0xFEE75C,
            )
            await thread.send(embed=delay_embed)

        # =====================================================================
        # BẢN XEM TRƯỚC NHANH TRỰC TIẾP TRÊN DISCORD (INSTANT DISCORD PREVIEW)
        # =====================================================================
        exam_data = gen_result.get("exam_data", {})
        meta = gen_result.get("metadata", {})

        preview_embed = discord.Embed(
            title=f"📱 BẢN XEM TRƯỚC NHANH TRỰC TIẾP • {meta.get('exam_code', job_id)}",
            description=(
                f"• **Môn học:** `{subject_ans}`\n"
                f"• **Thời gian làm bài:** `{meta.get('duration', '90 phút')}`\n"
                f"• **Quy mô:** {length_tier} ({mode})\n"
                f"• **Tổng số câu hỏi:** {len([q for q in exam_data.get('questions', []) if q.get('type') != 'section_header'])} câu\n\n"
                f"📖 **Trích dẫn nội dung mẫu:**\n"
            ),
            color=0x3498DB,
        )

        q_count = 0
        for q in exam_data.get("questions", []):
            if q.get("type") == "question":
                q_text = q.get("text", "")[:180] + ("..." if len(q.get("text", "")) > 180 else "")
                opts = " | ".join(q.get("options", [])[:4])
                val = f"{q_text}"
                if opts:
                    val += f"\n*{opts}*"
                preview_embed.add_field(
                    name=f"Câu {q.get('number', '?')} ({q.get('points', '')})",
                    value=val,
                    inline=False,
                )
                q_count += 1
                if q_count >= 2:
                    break

        mc_keys = []
        for sol in exam_data.get("solutions", []):
            if sol.get("is_multiple_choice") or sol.get("correct_key"):
                mc_keys.append(f"{sol.get('number', '?')}.{sol.get('correct_key', '?')}")

        if mc_keys:
            key_str = " | ".join(mc_keys[:30])
            preview_embed.add_field(
                name="🔑 Bảng Đáp Án Nhanh (Click spoiler để mở xem)",
                value=f"|| {key_str} ||",
                inline=False,
            )

        # Báo cáo đánh giá ma trận sư phạm Bloom & Khảo thí
        pedagogy_eval = gen_result.get("pedagogy_evaluation")
        if pedagogy_eval and hasattr(pedagogy_eval, "to_discord_markdown"):
            preview_embed.add_field(
                name="📊 Đánh Giá Ma Trận Khảo Thí & Phổ Điểm Sư Phạm",
                value=pedagogy_eval.to_discord_markdown(),
                inline=False,
            )

        # Đính kèm ảnh Biểu đồ Radar đa giác năng lực Bloom nếu có
        radar_chart_path = gen_result.get("radar_chart_path")
        radar_file = None
        if radar_chart_path and os.path.exists(radar_chart_path):
            radar_file = discord.File(radar_chart_path, filename="bloom_radar.png")
            preview_embed.set_image(url="attachment://bloom_radar.png")

        if radar_file:
            await thread.send(embed=preview_embed, file=radar_file)
        else:
            await thread.send(embed=preview_embed)

        # =====================================================================
        # GỬI TRẢ CÁC FILE ĐỘC LẬP & TẠO NÚT ĐÓNG TICKET + TRỘN MÃ ĐỀ
        # =====================================================================
        exam_files = gen_result.get("exam_files", [])
        solution_files = gen_result.get("solution_files", [])
        audio_files = gen_result.get("audio_files", [])

        discord_files = []
        for p in exam_files + solution_files + audio_files:
            if os.path.exists(p):
                discord_files.append(discord.File(p))

        delivered_embed = discord.Embed(
            title=f"🎉 BỘ ĐỀ THI & LỜI GIẢI ĐÃ HOÀN TẤT • {job_id}",
            description=(
                f"Chào <@{user.id}>! Bộ đề của bạn đã được xuất bản thành công với các tài liệu riêng biệt:\n\n"
                f"📄 **1. File Đề Thi [De_Thi]:**\n"
                f"• Bản in sạch sẽ, sẵn sàng phát cho học sinh làm bài.\n"
                f"• Tuyệt đối không chứa đáp án hay thang điểm.\n\n"
                f"📝 **2. File Hướng Dẫn Giải [Huong_Dan_Giai]:**\n"
                f"• Lời giải chi tiết từng bước, ma trận Bloom, bẫy tư duy, biểu đồ khảo thí & rubric chấm điểm.\n\n"
                f"🔀 **Trộn mã đề ngẫu nhiên:**\n"
                f"• Bấm nút **[🔀 Trộn Mã Đề]** bên dưới để tạo ngay mã 102, 103... hoàn toàn miễn phí!\n\n"
                f"🔒 **Lưu ý đóng ticket:**\n"
                f"• Khi đã tải xong đề, bạn hãy bấm nút **[🔒 Đóng Ticket & Lưu Trữ Kho Đề]** bên dưới.\n"
                f"• Đề thi sẽ tự động được lưu vào kho lưu trữ `#database`.\n"
                f"• Nếu bạn không bấm đóng, sau **2 tiếng**, Bot sẽ tự động lưu vào `#database` và gửi riêng file qua **DM** cho bạn!"
            ),
            color=0x2ECC71,
        )

        if audio_files:
            delivered_embed.add_field(
                name="🎧 File Âm Thanh Nghe (Listening Audio Exam)",
                value="• Đã xuất file `.mp3` chất lượng cao với các giọng đọc phân vai (trẻ em, học sinh, sinh viên, giáo viên, giám khảo) chuẩn phòng thi!",
                inline=False,
            )

        close_view = CloseTicketView(
            bot=self.bot,
            job_id=job_id,
            user_id=user.id,
            exam_files=exam_files,
            solution_files=solution_files,
            metadata={
                "subject": subject_ans,
                "exam_code": meta.get("exam_code", f"HH-{job_id[-4:]}"),
                "length_tier": length_tier,
            },
            exam_data=exam_data,
            output_dir=job_output_dir,
            output_format=output_format,
            diagram_paths=gen_result.get("diagram_paths", []),
            audio_files=audio_files,
        )

        if discord_files:
            await thread.send(content=f"🔔 <@{user.id}>", embed=delivered_embed, files=discord_files, view=close_view)
        else:
            await thread.send(content=f"🔔 <@{user.id}>", embed=delivered_embed, view=close_view)

        # Cập nhật database
        await user_token_service.update_exam_job(
            job_id=job_id,
            status="COMPLETED",
            exam_file_path=exam_files[0] if exam_files else None,
            solution_file_path=solution_files[0] if solution_files else None,
        )

        # Kích hoạt bộ đếm thời gian tự động đóng sau 2 tiếng (7200 giây)
        self.bot.loop.create_task(
            self._auto_close_timer(
                thread=thread,
                user=user,
                close_view=close_view,
                exam_files=exam_files,
                solution_files=solution_files,
                audio_files=audio_files,
                job_id=job_id,
                subject=subject_ans,
            )
        )

    # =========================================================================
    # BỘ ĐẾM THỜI GIAN 2 TIẾNG TỰ ĐỘNG ĐÓNG & GỬI FILE QUA DM
    # =========================================================================
    async def _auto_close_timer(
        self,
        thread: discord.Thread,
        user: discord.User | discord.Member,
        close_view: CloseTicketView,
        exam_files: list[str],
        solution_files: list[str],
        job_id: str,
        subject: str,
        audio_files: Optional[list[str]] = None,
    ) -> None:
        """Đợi 2 tiếng. Nếu người dùng chưa đóng ticket -> Lưu trữ và gửi file qua DM."""
        await asyncio.sleep(7200)  # 2 tiếng = 7200 giây

        if close_view.is_closed:
            return  # Người dùng đã bấm đóng trước đó

        logger.info(f"Ticket {thread.id} ({job_id}) đã hết hạn 2 tiếng. Đang tự động đóng và gửi DM...")
        close_view.is_closed = True

        # Gửi file qua DM cho người dùng
        try:
            dm_files = []
            for p in exam_files + solution_files + (audio_files or []):
                if os.path.exists(p):
                    dm_files.append(discord.File(p))

            dm_embed = discord.Embed(
                title=f"📦 [TỰ ĐỘNG LƯU TRỮ] Bộ Đề Thi AI • {subject}",
                description=(
                    f"Chào **{user.display_name}**,\n"
                    f"Ticket tạo đề của bạn (`{job_id}`) đã tự động đóng sau **2 tiếng**.\n"
                    f"Bot đã sao lưu bộ đề vào kho dữ liệu của server và gửi đính kèm đầy đủ 2 file tại đây để bạn không bị thất lạc!"
                ),
                color=0x5865F2,
            )
            dm_embed.set_footer(text=f"Job ID: {job_id} • HyperHub AI Exam Platform")

            if dm_files:
                await user.send(embed=dm_embed, files=dm_files)
            else:
                await user.send(embed=dm_embed)
            logger.info(f"Đã gửi DM lưu trữ bộ đề {job_id} cho {user.id}")
        except Exception as dm_err:
            logger.warning(f"Không thể gửi DM cho {user.id} (DM có thể bị khóa): {dm_err}")

        # Lưu trữ vào #database và khóa thread
        await close_view._archive_and_close(thread=thread, closed_by="auto_timeout")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExamGeneratorCog(bot))
