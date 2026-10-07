"""
cogs/server_defense.py
Cog Quản Trị & Phòng Thủ Toàn Diện: Anti-Spam, Anti-Raid, Anti-Nuke & Khôi Phục 100% Cấu Trúc Server.

Tính năng:
- Lắng nghe sự kiện tin nhắn để phát hiện và xử lý spam (flood, duplicate, mass ping, invite links).
- Lắng nghe thành viên gia nhập để chặn đứng đợt Join Flood, cách ly/ban bot lạ không được phép.
- Lắng nghe sự kiện xóa/đổi tên danh mục và kênh bất thường để phát hiện Nuke Attack và tự động khôi phục 100%.
- Cung cấp Slash Commands quản trị:
  + /backup_server: Chụp snapshot cấu trúc máy chủ ngay lập tức.
  + /restore_server: Khôi phục 100% cấu trúc máy chủ từ bản snapshot.
  + /backup_list: Xem danh sách các bản snapshot đã lưu.
  + /lockdown: Bật/Tắt chế độ phong tỏa khẩn cấp toàn server.
  + /raid_status: Xem trạng thái phòng thủ & lịch sử bảo mật.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.settings import settings
from services.anti_raid_service import anti_raid_service
from services.server_backup_service import server_backup_service
from utils.embeds import create_embed, EmbedType
from utils.logger import get_logger
from utils.permissions import is_admin_or_owner, is_owner_user

log = get_logger("ServerDefenseCog")


class ServerDefenseCog(commands.Cog):
    """Cog điều phối hệ thống phòng vệ máy chủ và phục hồi thảm họa 100%."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.anti_raid = anti_raid_service
        self.backup_service = server_backup_service
        # Bắt đầu task sao lưu định kỳ
        self.auto_backup_task.start()

    def cog_unload(self) -> None:
        self.auto_backup_task.cancel()

    @tasks.loop(hours=6.0)
    async def auto_backup_task(self) -> None:
        """Tự động tạo snapshot cấu trúc server định kỳ."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                await self.backup_service.create_snapshot(
                    guild, note="Tự động sao lưu định kỳ (Auto-Snapshot 6h)"
                )
            except Exception as e:
                log.warning(f"Lỗi khi tự động sao lưu guild {guild.name}: {e}")

    @auto_backup_task.before_loop
    async def before_auto_backup(self) -> None:
        await self.bot.wait_until_ready()
        # Chờ 30 giây sau khi bot khởi động rồi tạo snapshot đầu tiên nếu chưa có
        await asyncio.sleep(30)
        for guild in self.bot.guilds:
            latest = self.backup_service.load_latest_snapshot(guild.id)
            if not latest:
                try:
                    await self.backup_service.create_snapshot(
                        guild, note="Khởi tạo bản sao lưu Ground Truth đầu tiên"
                    )
                except Exception as e:
                    log.warning(f"Lỗi khi khởi tạo snapshot đầu tiên cho {guild.name}: {e}")

    # =========================================================================
    # 1. EVENT LISTENERS: ANTI-SPAM
    # =========================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Lắng nghe và chặn các hành vi Spam."""
        if not getattr(settings, "ANTI_SPAM_ENABLED", True):
            return
        if not message.guild or message.author.bot or message.webhook_id:
            return

        violation = self.anti_raid.check_message_spam(message)
        if not violation:
            return

        # Thực thi xử lý vi phạm
        member = message.guild.get_member(message.author.id)
        if not member:
            return

        try:
            # 1. Xóa tin nhắn spam
            await message.delete()
        except Exception:
            pass

        try:
            # 2. Timeout 10 phút (600s)
            await member.timeout(
                timedelta(minutes=10),
                reason=f"[Anti-Spam] {violation.details}",
            )
            log.warning(
                f"[SPAM TIMEOUT] {member} (ID: {member.id}) trong #{message.channel.name} | {violation.violation_type}: {violation.details}"
            )

            # 3. Gửi thông báo răn đe
            embed = discord.Embed(
                title="🛡️ PHÒNG THỦ: PHÁT HIỆN HÀNH VI SPAM",
                description=(
                    f"Thành viên {member.mention} đã bị **tạm khóa gửi tin 10 phút**.\n\n"
                    f"📌 **Hành vi vi phạm:** `{violation.details}`\n"
                    f"⚠️ **Hình thức xử lý:** Xóa tin nhắn + Timeout 10 phút\n"
                    f"💡 *Ban quản trị có thể dùng lệnh `/unmute` nếu đây là hiểu lầm.*"
                ),
                color=0xEF4444,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="HyperHub Auto-Defense • Anti-Spam Shield")
            await message.channel.send(embed=embed, delete_after=20)
        except Exception as e:
            log.error(f"Lỗi khi xử phạt spam user {member.id}: {e}")

    # =========================================================================
    # 2. EVENT LISTENERS: ANTI-RAID & UNAUTHORIZED BOT
    # =========================================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Lắng nghe thành viên và bot mới gia nhập để chống Raid."""
        if not getattr(settings, "ANTI_RAID_ENABLED", True):
            return

        guild = member.guild

        # 2.1 Xử lý Unauthorized Bot (Bot lạ không được phép)
        if member.bot:
            await asyncio.sleep(1.0)  # Đợi Discord ghi audit log
            try:
                inviter = None
                async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.bot_add):
                    if entry.target.id == member.id:
                        inviter = entry.user
                        break

                is_trusted = False
                if inviter:
                    if inviter.id == guild.owner_id or is_owner_user(inviter.id):
                        is_trusted = True

                if not is_trusted:
                    # Phát hiện bot ngoại lai trái phép!
                    await member.ban(
                        reason=f"[Anti-Raid] Bot ngoại lai trái phép được thêm bởi {inviter or 'Không rõ'}"
                    )
                    log.warning(
                        f"[UNAUTHORIZED BOT BANNED] Đã cấm bot {member} (ID: {member.id}) được thêm bởi {inviter}."
                    )

                    # Cảnh báo Owner
                    await self._alert_owner(
                        guild,
                        title="🚨 PHÁT HIỆN VÀ BAN BOT NGOẠI LAI TRÁI PHÉP",
                        description=(
                            f"Một tài khoản bot lạ đã được đưa vào server mà không có sự phê duyệt của Server Owner!\n\n"
                            f"🤖 **Bot bị cấm:** `{member}` (ID: `{member.id}`)\n"
                            f"👤 **Người mời:** {inviter.mention if inviter else 'Không xác định'} (ID: `{getattr(inviter, 'id', 'N/A')}`)\n"
                            f"🛡️ **Hành động:** Đã Ban bot ngay lập tức để bảo vệ server."
                        ),
                    )
                    return
            except Exception as e:
                log.error(f"Lỗi khi kiểm tra audit log bot_add: {e}")

        # 2.2 Theo dõi Join Flood
        is_raid, raid_event = self.anti_raid.record_member_join(member)
        if is_raid and raid_event:
            # Kích hoạt trạng thái phòng thủ khẩn cấp
            if not self.anti_raid.is_lockdown_active(guild.id):
                locked_count = await self.anti_raid.enable_lockdown(
                    guild, reason=raid_event.trigger_reason
                )

                # Loại bỏ toàn bộ tài khoản raid
                success_ids, failed_list = await self.anti_raid.purge_raid_entities(
                    guild,
                    raid_event.involved_user_ids,
                    action="ban",
                    reason=raid_event.trigger_reason,
                )

                # Báo động khẩn cấp tới Server Owner
                await self._alert_owner(
                    guild,
                    title="🚨 BÁO ĐỘNG KHẨN CẤP: ĐÃ ĐẨY LÙI ĐỢT RAID SERVER",
                    description=(
                        f"Hệ thống Anti-Raid đã kích hoạt chế độ phong tỏa khẩn cấp và loại bỏ các đối tượng raid!\n\n"
                        f"📊 **Nguyên nhân:** `{raid_event.trigger_reason}`\n"
                        f"🔒 **Số kênh chat đã phong tỏa tạm thời:** `{locked_count}` kênh\n"
                        f"🔨 **Số đối tượng raid đã xử lý:** `{len(success_ids)}` tài khoản\n"
                        f"💡 **Hướng xử lý tiếp theo:** Dùng lệnh `/lockdown trang_thai:tắt` khi tình hình đã ổn định."
                    ),
                )

    # =========================================================================
    # 3. EVENT LISTENERS: ANTI-NUKE & TAMPER DETECTION (AUTO-RESTORE 100%)
    # =========================================================================

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Phát hiện hành vi xóa kênh / danh mục bất thường."""
        if not getattr(settings, "ANTI_NUKE_AUTO_RESTORE", True):
            return
        guild = channel.guild
        if self.backup_service._is_restoring[guild.id]:
            return

        await asyncio.sleep(0.8)
        try:
            actor = None
            async for entry in guild.audit_logs(limit=2, action=discord.AuditLogAction.channel_delete):
                if entry.target.id == channel.id:
                    actor = entry.user
                    break

            # Nếu là Owner hoặc chính bot thì bỏ qua
            if not actor or actor.id == guild.owner_id or is_owner_user(actor.id) or actor.id == guild.me.id:
                return

            is_nuke, actions = self.backup_service.record_tamper_event(
                guild.id, "CHANNEL_DELETE", actor.id, channel.id, channel.name
            )
            if is_nuke:
                await self._handle_nuke_attack(
                    guild, actor, f"Xóa hàng loạt {len(actions)} kênh/thư mục trong thời gian ngắn"
                )
        except Exception as e:
            log.error(f"Lỗi kiểm tra channel delete: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        """Phát hiện hành vi đổi tên hoặc chuyển thư mục kênh hàng loạt."""
        if not getattr(settings, "ANTI_NUKE_AUTO_RESTORE", True):
            return
        guild = after.guild
        if self.backup_service._is_restoring[guild.id]:
            return

        # Kiểm tra nếu có sự thay đổi tên hoặc thay đổi category
        name_changed = before.name != after.name
        cat_changed = getattr(before, "category_id", None) != getattr(after, "category_id", None)

        if not (name_changed or cat_changed):
            return

        await asyncio.sleep(0.8)
        try:
            actor = None
            async for entry in guild.audit_logs(limit=2, action=discord.AuditLogAction.channel_update):
                if entry.target.id == after.id:
                    actor = entry.user
                    break

            if not actor or actor.id == guild.owner_id or is_owner_user(actor.id) or actor.id == guild.me.id:
                return

            is_nuke, actions = self.backup_service.record_tamper_event(
                guild.id, "CHANNEL_RENAME", actor.id, after.id, after.name
            )
            if is_nuke:
                await self._handle_nuke_attack(
                    guild, actor, f"Đổi tên/chuyển thư mục hàng loạt {len(actions)} kênh trong thời gian ngắn"
                )
        except Exception as e:
            log.error(f"Lỗi kiểm tra channel update: {e}")

    async def _handle_nuke_attack(self, guild: discord.Guild, attacker: discord.User | discord.Member, reason: str) -> None:
        """Xử lý triệt để đợt tấn công Nuke và tự động khôi phục cấu trúc 100%."""
        log.critical(f"[NUKE DETECTED] Kẻ phá hoại: {attacker} (ID: {attacker.id}) | Lý do: {reason}")

        # 1. Vô hiệu hóa kẻ phá hoại
        try:
            member = guild.get_member(attacker.id)
            if member:
                # Ban ngay kẻ phá hoại
                await member.ban(reason=f"[Anti-Nuke Defense] {reason}", delete_message_days=1)
                log.info(f"Đã BAN kẻ phá hoại {attacker} thành công.")
        except Exception as e:
            log.error(f"Không thể ban kẻ phá hoại: {e}")

        # 2. Tự động khôi phục 100% cấu trúc máy chủ
        restore_result = await self.backup_service.restore_server_structure(
            guild, reason=f"[Anti-Nuke Recovery] Tự động khôi phục sau đợt phá hoại của {attacker}"
        )

        # 3. Báo cáo khẩn cấp tới Server Owner
        report = restore_result.get("report", {})
        await self._alert_owner(
            guild,
            title="🛡️ BÁO ĐỘNG ANTI-NUKE: ĐÃ NGĂN CHẶN & TỰ ĐỘNG KHÔI PHỤC 100%",
            description=(
                f"Hệ thống phát hiện dấu hiệu phá hoại cấu trúc server (Nuke) và đã can thiệp tự động!\n\n"
                f"👤 **Đối tượng phá hoại:** `{attacker}` (ID: `{attacker.id}`) - **ĐÃ BỊ BAN**\n"
                f"⚠️ **Hành vi:** `{reason}`\n\n"
                f"🔄 **KẾT QUẢ TỰ ĐỘNG KHÔI PHỤC:**\n"
                f"• Danh mục (Categories) tạo lại: `{report.get('categories_created', 0)}`\n"
                f"• Danh mục đổi lại tên cũ: `{report.get('categories_renamed', 0)}`\n"
                f"• Kênh (Channels) tạo lại: `{report.get('channels_created', 0)}`\n"
                f"• Kênh đổi lại tên cũ: `{report.get('channels_renamed', 0)}`\n"
                f"• Kênh đưa về đúng Thư mục: `{report.get('channels_reparented', 0)}`\n"
                f"• Quyền hạn (Permissions) khôi phục: `{report.get('overwrites_restored', 0)}`"
            ),
        )

    async def _alert_owner(self, guild: discord.Guild, title: str, description: str) -> None:
        """Gửi cảnh báo bảo mật tới Server Owner và Bot Owner qua DM."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=0xDC2626,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=guild.icon.url if guild.icon else settings.LOGO_ID)
        embed.set_footer(text=f"Server: {guild.name} ({guild.id}) • HyperHub Defense Core")

        # Gửi DM tới Guild Owner
        try:
            if guild.owner:
                await guild.owner.send(embed=embed)
        except Exception:
            pass

        # Gửi DM tới Bot Owner nếu khác Guild Owner
        if settings.OWNER_ID and settings.OWNER_ID != guild.owner_id:
            try:
                bot_owner = self.bot.get_user(settings.OWNER_ID) or await self.bot.fetch_user(settings.OWNER_ID)
                if bot_owner:
                    await bot_owner.send(embed=embed)
            except Exception:
                pass

    # =========================================================================
    # 4. EMERGENCY & DEFENSE COMMANDS (PREFIX ! CHO QUẢN TRỊ VIÊN & OWNER)
    # =========================================================================

    @commands.command(name="backup_server")
    async def backup_server_cmd(self, ctx: commands.Context, *, note: Optional[str] = None) -> None:
        """[Admin/Owner] Chụp snapshot lưu trữ toàn bộ cấu trúc server ngay lập tức (!backup_server [ghi chú])."""
        if not (ctx.author.id == settings.OWNER_ID or (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator)):
            await ctx.send("❌ Bạn không có quyền thực hiện lệnh này.", delete_after=10)
            return

        guild = ctx.guild
        backup_note = note or f"Sao lưu thủ công bởi {ctx.author}"
        try:
            snapshot = await self.backup_service.create_snapshot(guild, note=backup_note)
            counts = snapshot.get("counts", {})
            embed = discord.Embed(
                title="💾 ĐÃ TẠO BẢN SAO LƯU CẤU TRÚC SERVER THÀNH CÔNG",
                description=(
                    f"Đã chụp toàn bộ dữ liệu cấu trúc của server **{guild.name}** an toàn 100%.\n\n"
                    f"📁 **Danh mục (Categories):** `{counts.get('categories', 0)}` mục\n"
                    f"💬 **Kênh (Channels):** `{counts.get('channels', 0)}` kênh (Text & Voice)\n"
                    f"🎭 **Vai trò (Roles):** `{counts.get('roles', 0)}` vai trò\n"
                    f"📝 **Ghi chú:** `{backup_note}`\n"
                    f"⏰ **Thời gian:** `{snapshot.get('created_at', '')}`\n\n"
                    f"🛡️ *Bản lưu này sẽ được sử dụng để tự động phục hồi nếu có sự cố xảy ra.*"
                ),
                color=0x10B981,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text="HyperHub Disaster Recovery • 100% Auto-Restore")
            await ctx.send(embed=embed)
        except Exception as e:
            log.exception("Lỗi khi tạo snapshot")
            await ctx.send(f"❌ Đã xảy ra lỗi khi tạo snapshot: {e}")

    @commands.command(name="restore_server")
    async def restore_server_cmd(self, ctx: commands.Context) -> None:
        """[Admin/Owner] Khôi phục 100% cấu trúc server từ bản snapshot (!restore_server)."""
        if not (ctx.author.id == settings.OWNER_ID or (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator)):
            await ctx.send("❌ Bạn không có quyền thực hiện lệnh này.", delete_after=10)
            return

        guild = ctx.guild
        latest = self.backup_service.load_latest_snapshot(guild.id)
        if not latest:
            await ctx.send("❌ Không tìm thấy bản snapshot nào của server này. Hãy dùng `!backup_server` trước.")
            return

        msg = await ctx.send("⏳ **Đang tiến hành đối chiếu và khôi phục 100% cấu trúc máy chủ...** Vui lòng đợi trong giây lát!")
        res = await self.backup_service.restore_server_structure(
            guild,
            snapshot_data=latest,
            reason=f"Khôi phục cấu trúc thủ công bởi {ctx.author}",
        )
        if res.get("status") == "error":
            await msg.edit(content=f"❌ Lỗi khôi phục: {res.get('message')}")
            return

        report = res.get("report", {})
        embed = discord.Embed(
            title="✅ HOÀN TẤT KHÔI PHỤC CẤU TRÚC SERVER 100%",
            description=(
                f"Đã khôi phục hoàn chỉnh cấu trúc server theo bản sao lưu `{latest.get('created_at')}`.\n\n"
                f"📊 **CHI TIẾT KẾT QUẢ ĐỒNG BỘ:**\n"
                f"• 📁 Danh mục tạo mới lại: **{report.get('categories_created', 0)}**\n"
                f"• ✏️ Danh mục đổi lại tên gốc: **{report.get('categories_renamed', 0)}**\n"
                f"• 💬 Kênh tạo mới lại: **{report.get('channels_created', 0)}**\n"
                f"• ✏️ Kênh đổi lại tên gốc: **{report.get('channels_renamed', 0)}**\n"
                f"• 🔄 Kênh gắn lại đúng Thư mục: **{report.get('channels_reparented', 0)}**\n"
                f"• 🔐 Quyền Overwrites phục hồi: **{report.get('overwrites_restored', 0)}**\n\n"
                f"🎉 *Toàn bộ cấu trúc danh mục, kênh và phân quyền đã chuẩn xác 100%!*"
            ),
            color=0x3B82F6,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="HyperHub Disaster Recovery • Hoàn tất")
        await msg.edit(content=None, embed=embed)

    @commands.command(name="backup_list")
    async def backup_list_cmd(self, ctx: commands.Context) -> None:
        """[Admin/Owner] Xem danh sách các bản snapshot cấu trúc server đã lưu (!backup_list)."""
        if not (ctx.author.id == settings.OWNER_ID or (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator)):
            await ctx.send("❌ Bạn không có quyền thực hiện lệnh này.", delete_after=10)
            return

        guild = ctx.guild
        snaps = self.backup_service.list_snapshots(guild.id)
        if not snaps:
            await ctx.send("📁 Hiện chưa có bản snapshot nào. Hãy dùng `!backup_server` để tạo.")
            return

        embed = discord.Embed(
            title=f"📋 DANH SÁCH BẢN SAO LƯU CẤU TRÚC ({len(snaps)} bản)",
            color=0x6366F1,
            timestamp=datetime.now(timezone.utc),
        )
        for i, s in enumerate(snaps[:10], 1):
            embed.add_field(
                name=f"#{i}. {s['file_name']}",
                value=(
                    f"⏰ Thời gian: `{s['created_at']}`\n"
                    f"📊 Quy mô: `{s['categories']}` thư mục, `{s['channels']}` kênh, `{s['roles']}` roles\n"
                    f"📝 Ghi chú: *{s['note'] or 'Không có'}*"
                ),
                inline=False,
            )
        embed.set_footer(text="HyperHub Server Defense • Backups Registry")
        await ctx.send(embed=embed)

    @commands.command(name="lockdown")
    async def lockdown_cmd(self, ctx: commands.Context, trang_thai: str = "on", *, ly_do: Optional[str] = None) -> None:
        """[Admin/Owner] Bật hoặc tắt phong tỏa khẩn cấp (!lockdown on/off [lý do])."""
        if not (ctx.author.id == settings.OWNER_ID or (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator)):
            await ctx.send("❌ Bạn không có quyền thực hiện lệnh này.", delete_after=10)
            return

        guild = ctx.guild
        action_reason = ly_do or f"Thực hiện bởi {ctx.author}"
        tt_lower = trang_thai.strip().lower()

        if tt_lower in ("on", "enable", "bat", "bật"):
            count = await self.anti_raid.enable_lockdown(guild, reason=action_reason)
            embed = discord.Embed(
                title="🔒 ĐÃ KÍCH HOẠT CHẾ ĐỘ PHONG TỎA KHẨN CẤP (LOCKDOWN)",
                description=(
                    f"Toàn bộ quyền gửi tin nhắn của `@everyone` đã bị **tạm khóa** trên **{count}** kênh chat.\n\n"
                    f"👤 **Người điều hành:** {ctx.author.mention}\n"
                    f"📝 **Lý do:** `{action_reason}`\n\n"
                    f"💡 *Khi tình hình an toàn, dùng `!lockdown off` để mở lại.*"
                ),
                color=0xEF4444,
                timestamp=datetime.now(timezone.utc),
            )
        else:
            count = await self.anti_raid.disable_lockdown(guild, reason=action_reason)
            embed = discord.Embed(
                title="🔓 ĐÃ HỦY BỎ PHONG TỎA — MÁY CHỦ TRỞ LẠI BÌNH THƯỜNG",
                description=(
                    f"Đã mở khóa và khôi phục quyền gửi tin nhắn trên **{count}** kênh chat.\n\n"
                    f"👤 **Người điều hành:** {ctx.author.mention}\n"
                    f"📝 **Lý do:** `{action_reason}`"
                ),
                color=0x10B981,
                timestamp=datetime.now(timezone.utc),
            )

        embed.set_footer(text="HyperHub Emergency Defense Shield")
        await ctx.send(embed=embed)

    @commands.command(name="raid_status")
    async def raid_status_cmd(self, ctx: commands.Context) -> None:
        """[Admin/Owner] Xem trạng thái phòng vệ tự động (!raid_status)."""
        if not (ctx.author.id == settings.OWNER_ID or (isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator)):
            await ctx.send("❌ Bạn không có quyền thực hiện lệnh này.", delete_after=10)
            return

        guild = ctx.guild
        is_locked = self.anti_raid.is_lockdown_active(guild.id)
        recent_raids = self.anti_raid.get_recent_raids(limit=3)
        latest_snap = self.backup_service.load_latest_snapshot(guild.id)

        embed = discord.Embed(
            title="🛡️ TRUNG TÂM BẢO MẬT & PHÒNG THỦ MÁY CHỦ",
            description="Báo cáo trạng thái các phân hệ phòng vệ tự động theo thời gian thực.",
            color=0x3B82F6,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="1. Anti-Spam Shield",
            value=(
                f"• Trạng thái: `🟢 ĐANG BẢO VỆ`\n"
                f"• Ngưỡng flood: `{self.anti_raid.flood_threshold}` tin/{self.anti_raid.flood_window_seconds}s\n"
                f"• Ngưỡng duplicate: `{self.anti_raid.duplicate_threshold}` lần\n"
                f"• Mass Ping: Chặn `@everyone`/`@here` & >{self.anti_raid.mass_mention_threshold} mentions\n"
                f"• Hình phạt: Xóa tin + Timeout 10 phút"
            ),
            inline=False,
        )
        embed.add_field(
            name="2. Anti-Raid & Quarantine",
            value=(
                f"• Trạng thái: `🟢 ĐANG BẢO VỆ`\n"
                f"• Ngưỡng Join Flood: `{self.anti_raid.join_flood_threshold}` user/{self.anti_raid.join_flood_window_seconds}s\n"
                f"• Bot ngoại lai trái phép: `Tự động BAN ngay lập tức`\n"
                f"• Phong tỏa khẩn cấp (Lockdown): {'🔴 ĐANG BẬT' if is_locked else '⚪ BÌNH THƯỜNG'}"
            ),
            inline=False,
        )
        embed.add_field(
            name="3. Anti-Nuke & Disaster Recovery",
            value=(
                f"• Trạng thái: `🟢 ĐANG BẢO VỆ`\n"
                f"• Tự động khôi phục 100%: `{'BẬT' if getattr(settings, 'ANTI_NUKE_AUTO_RESTORE', True) else 'TẮT'}`\n"
                f"• Bản snapshot gần nhất: `{latest_snap.get('created_at', 'Chưa có') if latest_snap else 'Chưa có'}`\n"
                f"• Chu kỳ tự động sao lưu: Mỗi `{getattr(settings, 'BACKUP_AUTO_INTERVAL_HOURS', 6)}` tiếng"
            ),
            inline=False,
        )
        if recent_raids:
            raid_lines = []
            for r in recent_raids:
                raid_lines.append(
                    f"• `{datetime.fromtimestamp(r.started_at).strftime('%H:%M:%S')}`: {r.trigger_reason} (Đã xử lý: {r.purged_count})"
                )
            embed.add_field(name="🚨 Đợt Raid gần nhất", value="\n".join(raid_lines), inline=False)
        else:
            embed.add_field(name="🚨 Lịch sử Raid gần nhất", value="Chưa ghi nhận sự cố nào gần đây.", inline=False)

        embed.set_footer(text="HyperHub Auto-Defense System")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerDefenseCog(bot))
