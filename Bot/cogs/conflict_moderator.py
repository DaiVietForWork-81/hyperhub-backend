"""
cogs/conflict_moderator.py
Cog quản lý Giám Sát & Ngăn Chặn Xung Đột Tự Động (AI Conflict Moderator).

Tính năng:
- Lắng nghe tin nhắn trong Category ID được cấu hình.
- 99% tin nhắn bình thường đi qua Phễu lọc thông minh tốn 0% CPU.
- Khi phát hiện cãi vã thù địch leo thang:
  + Tự động xóa tin nhắn vi phạm.
  + Timeout (mute) cả 2 thành viên liên quan trong 5 phút.
  + Gửi thông báo công khai trong kênh kèm lý do chi tiết.
  + Nhắc nhở Moderators có thể dùng /unmute <@user> để gỡ phạt.
- Cung cấp Slash Commands quản lý: /conflict_config, /conflict_learn, /conflict_dict.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from services.conflict_detector import conflict_detector, lexicon
from utils.logger import get_logger
from utils.permissions import is_admin_or_owner

log = get_logger("ConflictModeratorCog")


class ConflictModeratorCog(commands.Cog):
    """Cog giám sát xung đột và tự động xử lý cãi vã / gây gổ bằng AI siêu nhẹ."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Cho phép ghi đè runtime nếu admin đổi cấu hình qua slash command
        self.monitored_category_id: int = int(
            getattr(settings, "CONFLICT_MONITOR_CATEGORY_ID", 0) or 0
        )
        self.mute_duration_minutes: int = int(
            getattr(settings, "CONFLICT_MUTE_DURATION_MINUTES", 5) or 5
        )
        self.active_model: str = str(
            getattr(settings, "CONFLICT_AI_MODEL", "qwen2.5:0.5b") or "qwen2.5:0.5b"
        )
class StaffConflictActionView(discord.ui.View):
    """View tương tác dành riêng cho Mod/Staff/Admin xử lý thủ công các vụ tranh chấp."""

    def __init__(
        self,
        guild_id: int,
        channel_id: int,
        involved_users: list[int],
        offending_message_ids: list[int],
        mute_minutes: int = 5,
    ) -> None:
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.involved_users = involved_users
        self.offending_message_ids = offending_message_ids
        self.mute_minutes = mute_minutes
        self._build_buttons()

    def _build_buttons(self) -> None:
        # Nút Mute từng đối tượng (tối đa 2 người)
        for idx, uid in enumerate(self.involved_users[:2], start=1):
            btn = discord.ui.Button(
                label=f"🔇 Mute P{idx} ({self.mute_minutes}p)",
                style=discord.ButtonStyle.danger,
                custom_id=f"staff_mute_p{idx}_{uid}",
            )
            btn.callback = self._create_mute_callback(uid, f"P{idx}")
            self.add_item(btn)

        # Nút Mute cả 2 nếu có từ 2 người trở lên
        if len(self.involved_users) >= 2:
            btn_all = discord.ui.Button(
                label=f"🔇 Mute Cả 2 ({self.mute_minutes}p)",
                style=discord.ButtonStyle.danger,
                custom_id="staff_mute_all",
            )
            btn_all.callback = self._mute_all_callback
            self.add_item(btn_all)

        # Nút Xóa các tin nhắn gây hấn
        if self.offending_message_ids:
            btn_purge = discord.ui.Button(
                label=f"🗑️ Xóa {len(self.offending_message_ids)} Tin Cãi Vã",
                style=discord.ButtonStyle.secondary,
                custom_id="staff_purge_msgs",
            )
            btn_purge.callback = self._purge_callback
            self.add_item(btn_purge)

        # Nút Bỏ qua / Đã xem
        btn_dismiss = discord.ui.Button(
            label="✅ Bỏ Qua / Đã Xử Lý",
            style=discord.ButtonStyle.success,
            custom_id="staff_dismiss_conflict",
        )
        btn_dismiss.callback = self._dismiss_callback
        self.add_item(btn_dismiss)

    def _check_permission(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member):
            return False
        owner_id = int(getattr(settings, "OWNER_ID", 0) or 0)
        if owner_id > 0 and interaction.user.id == owner_id:
            return True
        perms = interaction.user.guild_permissions
        return bool(perms.moderate_members or perms.manage_messages or perms.administrator)

    def _create_mute_callback(self, user_id: int, label: str):
        async def callback(interaction: discord.Interaction):
            if not self._check_permission(interaction):
                await interaction.response.send_message("❌ Chỉ Mod/Staff/Admin mới có quyền xử lý thao tác này.", ephemeral=True)
                return

            guild = interaction.guild
            member = guild.get_member(user_id) if guild else None
            if not member and guild and hasattr(guild, "fetch_member"):
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None

            if not member:
                await interaction.response.send_message(f"❌ Không tìm thấy thành viên <@{user_id}> trong Server.", ephemeral=True)
                return

            try:
                mute_until = timedelta(minutes=self.mute_minutes)
                await member.timeout(mute_until, reason=f"Mod {interaction.user} xử phạt sau tranh cãi / war")
                await self._finish_interaction(interaction, f"Đã timeout {member.mention} trong {self.mute_minutes} phút bởi {interaction.user.mention}.")
            except Exception as e:
                await interaction.response.send_message(f"❌ Không thể timeout {member.mention}: {e}", ephemeral=True)

        return callback

    async def _mute_all_callback(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ Chỉ Mod/Staff/Admin mới có quyền xử lý thao tác này.", ephemeral=True)
            return

        guild = interaction.guild
        muted_names = []
        mute_until = timedelta(minutes=self.mute_minutes)
        for uid in self.involved_users[:2]:
            member = guild.get_member(uid) if guild else None
            if not member and guild and hasattr(guild, "fetch_member"):
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None
            if member:
                try:
                    await member.timeout(mute_until, reason=f"Mod {interaction.user} xử phạt cãi vã 2 bên")
                    muted_names.append(member.mention)
                except Exception:
                    pass

        target_str = ", ".join(muted_names) if muted_names else "các đối tượng"
        await self._finish_interaction(interaction, f"Đã timeout {target_str} trong {self.mute_minutes} phút bởi {interaction.user.mention}.")

    async def _purge_callback(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ Chỉ Mod/Staff/Admin mới có quyền xử lý thao tác này.", ephemeral=True)
            return

        guild = interaction.guild
        channel = guild.get_channel(self.channel_id) if guild else None
        deleted_count = 0
        if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
            for mid in self.offending_message_ids:
                try:
                    msg = await channel.fetch_message(mid)
                    if msg:
                        await msg.delete()
                        deleted_count += 1
                except Exception:
                    pass

        await self._finish_interaction(interaction, f"Đã dọn dẹp {deleted_count} tin nhắn cãi vã tại {channel.mention if channel else f'<#{self.channel_id}>'} bởi {interaction.user.mention}.")

    async def _dismiss_callback(self, interaction: discord.Interaction):
        if not self._check_permission(interaction):
            await interaction.response.send_message("❌ Chỉ Mod/Staff/Admin mới có quyền xử lý thao tác này.", ephemeral=True)
            return

        await self._finish_interaction(interaction, f"Đã đánh dấu bỏ qua / đã giải quyết bởi {interaction.user.mention}.")

    async def _finish_interaction(self, interaction: discord.Interaction, note: str):
        for item in self.children:
            item.disabled = True
        if interaction.message:
            emb = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title="Báo cáo Xung Đột")
            emb.color = 0x2ECC71
            emb.add_field(name="🛡️ Kết Quả Xử Lý Của Staff", value=f"✅ {note}", inline=False)
            try:
                await interaction.response.edit_message(embed=emb, view=self)
            except Exception:
                await interaction.followup.send(f"✅ {note}", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ {note}", ephemeral=True)


class ConflictModeratorCog(commands.Cog):
    """Cog giám sát xung đột và cảnh báo kín cho Mod/Staff/Admin (AI KHÔNG can thiệp trực tiếp)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.monitored_category_id: int = int(
            getattr(settings, "CONFLICT_MONITOR_CATEGORY_ID", 0) or 0
        )
        self.mute_duration_minutes: int = int(
            getattr(settings, "CONFLICT_MUTE_DURATION_MINUTES", 5) or 5
        )
        self.active_model: str = str(
            getattr(settings, "CONFLICT_AI_MODEL", "qwen2.5:0.5b") or "qwen2.5:0.5b"
        )
        self.is_enabled: bool = True
        # AI tuyệt đối không can thiệp (không tự ý timeout, không tự xóa tin nhắn, không spam kênh chat)
        self.ai_intervention: bool = False
        # Gửi thông báo kín cho Staff
        self.notify_staff: bool = True
        self.staff_log_channel_id: int = int(
            getattr(settings, "CONFLICT_LOG_CHANNEL_ID", 0)
            or getattr(settings, "DUEL_LOG_CHANNEL_ID", 1536199276273860638)
            or 0
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Lắng nghe tin nhắn mới để phát hiện xung đột theo thời gian thực."""
        # 1. Bỏ qua tin nhắn không hợp lệ
        if not self.is_enabled:
            return
        if message.author.bot or message.webhook_id:
            return
        if not message.guild or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        # 2. Kiểm tra Category ID (Thư mục)
        if self.monitored_category_id > 0:
            channel_cat_id = getattr(message.channel, "category_id", None)
            if channel_cat_id != self.monitored_category_id:
                return

        # 3. Ghi nhận tin nhắn vào sliding window (tốn 0ms)
        conflict_detector.record_message(
            channel_id=message.channel.id,
            message_id=message.id,
            user_id=message.author.id,
            user_name=message.author.display_name,
            content=message.content,
        )

        # 4. TẦNG 1: Phễu lọc nhanh (Smart Fast Filter — 0% CPU)
        should_eval, candidate_users, records, score = conflict_detector.fast_filter(message.channel.id)
        if not should_eval:
            return

        # 5. TẦNG 2: Đánh giá ngữ cảnh khi có dấu hiệu đấu khẩu gay gắt
        eval_result = await conflict_detector.evaluate_conflict(
            channel_id=message.channel.id, model_name=self.active_model
        )
        if not eval_result.is_conflict or len(eval_result.involved_users) < 2:
            return

        # 6. AI KHÔNG CAN THIỆP TRỰC TIẾP — GỬI BÁO CÁO KÍN CHO MOD/STAFF/ADMIN
        await self._report_to_staff(message.guild, message.channel, eval_result)

    async def _report_to_staff(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel | discord.Thread,
        eval_result: Any,
    ) -> None:
        """
        Gửi báo cáo kín tới kênh Log riêng của Mod/Staff/Admin.
        TUYỆT ĐỐI KHÔNG can thiệp vào kênh chat của thành viên (Không timeout, không xóa tin, không gửi tin).
        """
        log.warning(
            "[ConflictModerator] PHÁT HIỆN XUNG ĐỘT tại kênh #%s: Users=%s | Báo cáo Mod/Staff",
            channel.name, eval_result.involved_users
        )

        if not self.notify_staff:
            return

        # Tìm kênh log chuyên dụng của Mod/Staff
        log_channel = None
        if self.staff_log_channel_id > 0:
            log_channel = guild.get_channel(self.staff_log_channel_id) or self.bot.get_channel(self.staff_log_channel_id)
        if not log_channel:
            # Fallback sang DUEL_LOG_CHANNEL_ID hoặc log_channel_id của settings
            fallback_id = getattr(settings, "DUEL_LOG_CHANNEL_ID", 1536199276273860638)
            log_channel = guild.get_channel(fallback_id) or self.bot.get_channel(fallback_id)

        if not log_channel or not isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            log.info("[ConflictModerator] Không tìm thấy kênh Log của Staff để gửi thông báo kín.")
            return

        # Trích xuất tên thành viên liên quan
        user_mentions = [f"<@{uid}>" for uid in eval_result.involved_users]
        user_str = ", ".join(user_mentions)

        embed = discord.Embed(
            title="🛡️ [STAFF ALERT] PHÁT HIỆN TRANH CÃI / WAR — CHỜ MOD XỬ LÝ",
            description=(
                f"Hệ thống phát hiện dấu hiệu cãi vã, công kích gay gắt tại kênh {channel.mention}.\n\n"
                "⚠️ **LƯU Ý:** AI **KHÔNG CAN THIỆP** vào kênh chat để tránh làm phiền thành viên. "
                "Quyền xem xét và quyết định xử phạt thuộc về **Mod / Staff / Admin**.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 **Kênh diễn ra:** {channel.mention} (`#{channel.name}`)\n"
                f"👥 **Thành viên liên quan:** {user_str}\n"
                f"🔥 **Mức độ nghiêm trọng:** `{eval_result.severity.upper()}`\n"
                f"📄 **Lý do AI nhận diện:** *{eval_result.reason}*\n"
                f"🗑️ **Tin nhắn gây hấn:** `{len(eval_result.offending_message_ids)} tin nhắn ghi nhận`\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "👇 **Thao tác nhanh cho Mod/Staff (Bấm nút bên dưới để thực thi):**"
            ),
            color=0xE67E22,
            timestamp=datetime.now(timezone.utc),
        )
        ai_tag = f"{self.active_model}" if eval_result.ai_used else "Smart Heuristic Engine"
        embed.set_footer(
            text=f"Staff Sentinel • {ai_tag} • Phân tích: {eval_result.evaluation_time_ms:.1f}ms • AI Không can thiệp"
        )

        view = StaffConflictActionView(
            guild_id=guild.id,
            channel_id=channel.id,
            involved_users=eval_result.involved_users,
            offending_message_ids=eval_result.offending_message_ids,
            mute_minutes=self.mute_duration_minutes,
        )

        try:
            await log_channel.send(embed=embed, view=view)
        except Exception as e:
            log.error("Không thể gửi báo cáo xung đột tới kênh log %s: %s", log_channel.id, e)

    # =========================================================================
    # SLASH COMMANDS QUẢN LÝ
    # =========================================================================

    @app_commands.command(name="conflict_config", description="Cấu hình AI Giám Sát & Báo Cáo Xung Đột Cho Mod/Staff")
    @app_commands.describe(
        category_id="ID Thư mục (Category ID) cần quét (nhập 0 để quét tất cả)",
        mute_minutes="Thời gian timeout đề xuất khi Mod bấm nút (phút, mặc định 5)",
        model="Mô hình AI sử dụng (VD: qwen2.5:0.5b, qwen2.5:1.5b)",
        notify_staff="Bật hoặc tắt gửi báo cáo kín cho Staff qua kênh Log",
        log_channel="Kênh text nhận báo cáo kín của Staff",
        enabled="Bật hoặc tắt toàn bộ hệ thống giám sát",
    )
    async def conflict_config(
        self,
        interaction: discord.Interaction,
        category_id: Optional[str] = None,
        mute_minutes: Optional[int] = None,
        model: Optional[str] = None,
        notify_staff: Optional[bool] = None,
        log_channel: Optional[discord.TextChannel] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Bạn không có quyền quản trị để thực hiện lệnh này.", ephemeral=True)
            return

        updates = []
        if category_id is not None:
            try:
                cat_int = int(category_id.strip())
                self.monitored_category_id = cat_int
                updates.append(f"• **Thư mục giám sát:** `{cat_int}`")
            except ValueError:
                await interaction.response.send_message("❌ Category ID không hợp lệ (phải là số nguyên).", ephemeral=True)
                return

        if mute_minutes is not None:
            if mute_minutes < 1 or mute_minutes > 1440:
                await interaction.response.send_message("❌ Thời gian mute phải từ 1 đến 1440 phút.", ephemeral=True)
                return
            self.mute_duration_minutes = mute_minutes
            updates.append(f"• **Thời gian Timeout đề xuất:** `{mute_minutes} phút`")

        if model is not None:
            self.active_model = model.strip()
            updates.append(f"• **Mô hình AI:** `{self.active_model}`")

        if notify_staff is not None:
            self.notify_staff = notify_staff
            st_str = "🟢 Bật" if notify_staff else "🔴 Tắt"
            updates.append(f"• **Báo cáo kín cho Staff:** {st_str}")

        if log_channel is not None:
            self.staff_log_channel_id = log_channel.id
            updates.append(f"• **Kênh Log của Staff:** {log_channel.mention}")

        if enabled is not None:
            self.is_enabled = enabled
            st_text = "🟢 Đang hoạt động" if enabled else "🔴 Đã tạm dừng"
            updates.append(f"• **Trạng thái:** {st_text}")

        cat_desc = f"<#{self.monitored_category_id}> (`{self.monitored_category_id}`)" if self.monitored_category_id > 0 else "`Tất cả các kênh`"
        log_desc = f"<#{self.staff_log_channel_id}>" if self.staff_log_channel_id > 0 else "`Mặc định Server Log`"

        embed = discord.Embed(
            title="⚙️ CẤU HÌNH GIÁM SÁT XUNG ĐỘT (CHUYỂN GIAO CHO MOD/STAFF)",
            description=(
                ("✅ **Đã cập nhật thành công các thiết lập:**\n" + "\n".join(updates) + "\n\n" if updates else "") +
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• **Trạng thái hệ thống:** {'🟢 Hoạt động' if self.is_enabled else '🔴 Tạm dừng'}\n"
                f"• **Chế độ can thiệp:** 🛡️ **AI KHÔNG CAN THIỆP TRỰC TIẾP**\n"
                f"  └ *Tự động Mute / Xóa tin nhắn:* ❌ **TẮT** (Chỉ Mod/Admin mới có quyền)\n"
                f"  └ *Can thiệp trong kênh chat:* ❌ **TẮT** (Không làm phiền cuộc trò chuyện)\n"
                f"• **Báo cáo kín cho Staff:** {'🟢 Bật' if self.notify_staff else '🔴 Tắt'}\n"
                f"• **Kênh Log nhận báo cáo:** {log_desc}\n"
                f"• **Thư mục giám sát:** {cat_desc}\n"
                f"• **Thời gian Timeout đề xuất:** `{self.mute_duration_minutes} phút`\n"
                f"• **Mô hình AI nhận diện:** `{self.active_model}`\n"
                f"• **Phễu lọc thông minh:** `Bật (99% tin nhắn thường tốn 0% CPU)`"
            ),
            color=0x2ECC71,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="conflict_learn", description="Dạy từ vựng lóng mới hoặc tra cứu tự động trên internet")
    @app_commands.describe(
        tu_khoa="Từ lóng hoặc cụm từ cần học",
        loai="Phân loại ngữ nghĩa của từ",
        y_nghia="Giải thích ý nghĩa (để trống nếu muốn tra cứu tự động từ internet)",
    )
    @app_commands.choices(
        loai=[
            app_commands.Choice(name="Chửi thề / đùa giỡn đời thường (Cho phép)", value="casual"),
            app_commands.Choice(name="Xúc phạm / khiêu khích thù địch (Xử phạt)", value="hostile"),
        ]
    )
    async def conflict_learn(
        self,
        interaction: discord.Interaction,
        tu_khoa: str,
        loai: Optional[app_commands.Choice[str]] = None,
        y_nghia: Optional[str] = None,
    ) -> None:
        if not is_admin_or_owner(interaction):
            await interaction.response.send_message("❌ Bạn không có quyền quản trị để thực hiện lệnh này.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        clean_word = tu_khoa.strip()

        # Nếu không cung cấp ý nghĩa -> Tra cứu tự động từ internet
        if not y_nghia:
            res = await conflict_detector.learn_slang_from_web(clean_word)
            learned_type = res.get("type", "casual")
            type_label = "🟢 Cho phép (Đùa giỡn/Casual)" if learned_type == "casual" else "🔴 Thù địch/Khiêu khích (Hostile)"
            embed = discord.Embed(
                title="🌐 HỌC TỪ LÓNG TỰ ĐỘNG TỪ INTERNET",
                description=(
                    f"• **Từ khóa:** `{clean_word}`\n"
                    f"• **Phân loại:** {type_label}\n"
                    f"• **Ý nghĩa nhận diện:** {res.get('meaning', 'N/A')}\n"
                    f"• **Nguồn:** `{res.get('source', 'Web Search')}`\n\n"
                    f"✅ *Đã tự động cập nhật vào cơ sở dữ liệu `data/conflict_lexicon.json`!*"
                ),
                color=0x3498DB,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        chosen_type = loai.value if loai else "casual"
        lexicon.add_learned_slang(clean_word, chosen_type, y_nghia)
        type_label = "🟢 Cho phép (Đùa giỡn/Casual)" if chosen_type == "casual" else "🔴 Thù địch/Khiêu khích (Hostile)"

        embed = discord.Embed(
            title="📚 ĐÃ HỌC TỪ VỰNG MỚI THÀNH CÔNG",
            description=(
                f"• **Từ khóa:** `{clean_word}`\n"
                f"• **Phân loại:** {type_label}\n"
                f"• **Ý nghĩa:** {y_nghia}\n\n"
                f"✅ *Từ vựng này đã được nạp vào bộ nhận diện ngôn ngữ của Bot!*"
            ),
            color=0x2ECC71,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="conflict_dict", description="Xem từ điển lóng và quy tắc nhận diện xung đột")
    async def conflict_dict(self, interaction: discord.Interaction) -> None:
        casual_sample = ", ".join(f"`{w}`" for w in list(lexicon.casual_banter)[:12])
        hostile_sample = ", ".join(f"`{w}`" for w in list(lexicon.hostile_triggers)[:12])
        learned_count = len(lexicon.learned_slang)

        embed = discord.Embed(
            title="📖 TỪ ĐIỂN LÓNG & QUY TẮC NHẬN DIỆN XUNG ĐỘT",
            description=(
                "Hệ thống phân biệt rõ giữa chửi đùa thân mật và gây gổ xúc phạm đối đầu:\n\n"
                f"🟢 **Từ ngữ đùa giỡn / than thở (Cho phép, {len(lexicon.casual_banter)} từ):**\n"
                f"{casual_sample}...\n\n"
                f"🔴 **Từ khóa thù địch / kích động (Cấm, {len(lexicon.hostile_triggers)} từ):**\n"
                f"{hostile_sample}...\n\n"
                f"🌐 **Từ lóng đã học từ internet/admin:** `{learned_count} cụm từ đã lưu`\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "💡 *Dùng `/conflict_learn` để dạy thêm từ mới hoặc tra cứu tự động.*"
            ),
            color=0x9B59B6,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConflictModeratorCog(bot))
