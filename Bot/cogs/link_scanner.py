"""
cogs/link_scanner.py
Module Kênh Chuyên Dụng Kiểm Tra Link An Toàn & Quét Mã Độc (Channel 1546522680638054461).

Đặc điểm tính năng:
1. Giao diện: Bảng điều khiển thường trực (Embed + Button '🔍 Quét An Toàn Link' mở Modal).
2. Hạn mức: Mỗi member có 3 lần sử dụng / 1 tiếng (3600s sliding window).
   - Ngoại lệ: Bot Owner (OWNER_ID) không bị giới hạn số lần sử dụng.
3. Bảo mật: Kết quả kiểm tra trả về RIÊNG TƯ (Ephemeral - chỉ người bấm mới thấy).
4. Tự động dọn dẹp: Xóa mọi tin nhắn của người dùng trong kênh để kênh luôn gọn gàng 100%.
5. Slash command: /scan_link hỗ trợ kiểm tra nhanh ở mọi kênh.
"""

from __future__ import annotations

import asyncio
import collections
import datetime
import logging
import math
import os
import re
import time
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from services.antivirus_scanner import AntivirusScanner, ThreatLevel, ThreatScanResult

log = logging.getLogger(__name__)


class ScannerRateLimiter:
    """Quản lý hạn mức sử dụng (3 lần / 1 tiếng) cho mỗi người dùng."""

    def __init__(self, max_uses: int = 3, window_seconds: int = 3600):
        self.max_uses = max_uses
        self.window_seconds = window_seconds
        # user_id -> deque of timestamps
        self._records: dict[int, collections.deque[float]] = {}

    def _cleanup_old_records(self, user_id: int, now: float) -> None:
        if user_id not in self._records:
            return
        q = self._records[user_id]
        cutoff = now - self.window_seconds
        while q and q[0] <= cutoff:
            q.popleft()
        if not q:
            del self._records[user_id]

    def check_quota(self, user_id: int) -> tuple[bool, int, int]:
        """
        Kiểm tra xem người dùng còn lượt hay không.
        Trả về: (allowed, retry_after_seconds, remaining_quota)
        """
        # Bot Owner được miễn trừ hoàn toàn
        owner_id = int(getattr(settings, "OWNER_ID", 0) or 0)
        if owner_id > 0 and user_id == owner_id:
            return True, 0, 999

        now = time.time()
        self._cleanup_old_records(user_id, now)

        q = self._records.get(user_id)
        current_count = len(q) if q else 0

        if current_count >= self.max_uses:
            earliest = q[0]
            retry_after = max(1, int(self.window_seconds - (now - earliest)))
            return False, retry_after, 0

        remaining = self.max_uses - current_count
        return True, 0, remaining

    def consume_quota(self, user_id: int) -> int:
        """Ghi nhận 1 lần sử dụng và trả về số lượt còn lại."""
        owner_id = int(getattr(settings, "OWNER_ID", 0) or 0)
        if owner_id > 0 and user_id == owner_id:
            return 999

        now = time.time()
        self._cleanup_old_records(user_id, now)

        if user_id not in self._records:
            self._records[user_id] = collections.deque()

        self._records[user_id].append(now)
        remaining = max(0, self.max_uses - len(self._records[user_id]))
        return remaining


# Global singleton rate limiter
rate_limiter = ScannerRateLimiter(max_uses=3, window_seconds=3600)


class LinkScanModal(discord.ui.Modal, title="🔍 Quét An Toàn Đường Dẫn / Virus"):
    """Modal nhập đường dẫn cần quét an toàn."""

    url_input = discord.ui.TextInput(
        label="Đường dẫn (URL) cần kiểm tra",
        placeholder="https://example.com/file hoặc drive.google.com/file/d/...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.short,
    )

    def __init__(self, cog: LinkScannerCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        user_id = interaction.user.id
        raw_url = self.url_input.value.strip()

        allowed, retry_after, remaining = rate_limiter.check_quota(user_id)
        if not allowed:
            mins = math.ceil(retry_after / 60)
            embed = discord.Embed(
                title="⏳ BẠN ĐÃ HẾT LƯỢT KIỂM TRA",
                description=(
                    f"Mỗi thành viên có **3 lượt kiểm tra mỗi 1 tiếng**.\n\n"
                    f"• Bạn đã sử dụng hết lượt trong khung giờ này.\n"
                    f"• Lượt quét kế tiếp sẽ hồi phục sau: **{mins} phút** (khoảng <t:{int(time.time() + retry_after)}:R>).\n\n"
                    f"🛡️ *Hạn chế này nhằm chống spam và bảo vệ tài nguyên quét an toàn cho server.*"
                ),
                color=0xE67E22,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Quét an toàn URL
        scan_res = await AntivirusScanner.scan_url(raw_url, check_probe=True)

        # Trừ 1 lượt sử dụng
        new_remaining = rate_limiter.consume_quota(user_id)

        # Xây dựng Embed báo cáo chi tiết
        embed = self.cog.build_scan_report_embed(interaction.user, scan_res, new_remaining)
        await interaction.followup.send(embed=embed, ephemeral=True)


class LinkScannerControlView(discord.ui.View):
    """Bảng điều khiển tương tác thường trực tại kênh 1546522680638054461."""

    def __init__(self, cog: LinkScannerCog | None = None):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="🔍 Quét An Toàn Link",
        style=discord.ButtonStyle.primary,
        custom_id="btn_scan_link_safety",
        emoji="🛡️",
    )
    async def btn_scan(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.cog or interaction.client.get_cog("LinkScannerCog")
        if not cog:
            await interaction.response.send_message("❌ Hệ thống kiểm tra link chưa sẵn sàng.", ephemeral=True)
            return

        # Kiểm tra trước hạn mức của user trước khi mở modal
        allowed, retry_after, remaining = rate_limiter.check_quota(interaction.user.id)
        if not allowed:
            mins = math.ceil(retry_after / 60)
            embed = discord.Embed(
                title="⏳ BẠN ĐÃ HẾT LƯỢT KIỂM TRA",
                description=(
                    f"Mỗi thành viên có **3 lượt kiểm tra mỗi 1 tiếng**.\n\n"
                    f"• Bạn hiện đang có **0/3 lượt** khả dụng.\n"
                    f"• Lượt quét kế tiếp sẽ hồi phục sau: **{mins} phút** (khoảng <t:{int(time.time() + retry_after)}:R>)."
                ),
                color=0xE67E22,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.send_modal(LinkScanModal(cog))

    @discord.ui.button(
        label="📊 Xem Hạn Mức Cá Nhân",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_scan_link_quota",
        emoji="⏱️",
    )
    async def btn_quota(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        owner_id = int(getattr(settings, "OWNER_ID", 0) or 0)
        is_owner = owner_id > 0 and interaction.user.id == owner_id

        allowed, retry_after, remaining = rate_limiter.check_quota(interaction.user.id)
        if is_owner:
            quota_text = "👑 **Bot Owner:** `Không giới hạn số lần quét`"
        elif not allowed:
            mins = math.ceil(retry_after / 60)
            quota_text = f"❌ **Hết lượt:** `0/3 lượt` (Hồi phục sau {mins} phút)"
        else:
            quota_text = f"✅ **Lượt khả dụng:** `{remaining}/3 lượt` (Khung giờ 1 tiếng)"

        embed = discord.Embed(
            title="⏱️ HẠN MỨC QUÉT LINK AN TOÀN",
            description=(
                f"Xin chào {interaction.user.mention},\n\n"
                f"{quota_text}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• **Quy định:** Mỗi thành viên được quét tối đa 3 lần trong mỗi 1 tiếng.\n"
                f"• **Mục đích:** Đảm bảo độ ổn định và phòng chống lạm dụng băng thông kiểm tra.\n"
                f"• **Bảo mật:** Toàn bộ kết quả quét đều được gửi riêng tư (chỉ mình bạn thấy)."
            ),
            color=0x3498DB,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LinkScannerCog(commands.Cog):
    """Cog quản lý kênh kiểm tra link an toàn và quét virus đường dẫn."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def build_control_panel_embed(self) -> discord.Embed:
        """Tạo Embed bảng điều khiển thường trực tại kênh 1546522680638054461."""
        desc = (
            "Chào mừng bạn đến với **Trạm Kiểm Tra & Quét An Toàn Đường Dẫn Tự Động**!\n\n"
            "Trước khi click vào một đường dẫn lạ hoặc tải tệp tài liệu, bạn có thể sử dụng trạm này "
            "để kiểm tra xem liên kết đó có **an toàn hay dính virus, mã độc, lừa đảo (phishing)**.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ **CÁC TÍNH NĂNG BẢO VỆ CHÍNH:**\n"
            "• 🦠 **Phát hiện Virus & Trojan:** Quét tệp thực thi ẩn danh, mã độc ngụy trang.\n"
            "• 🎣 **Chống Phishing & Scam:** Phát hiện website mạo danh tài khoản, fake Nitro.\n"
            "• 🕵️ **Chặn IP Logger:** Nhận diện và cảnh báo các liên kết thu thập thông tin cá nhân.\n"
            "• 📁 **Kiểm tra File:** Tự động phát hiện macro nguy hại và khai thác lỗ hổng.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⏱️ **Hạn mức sử dụng:** Mỗi thành viên có **3 lượt kiểm tra / 1 tiếng**.\n"
            "🔒 **Bảo mật tuyệt đối:** Kết quả quét được gửi **RIÊNG TƯ (chỉ mình bạn đọc được)**.\n\n"
            "💡 *Hãy nhấn nút **'🛡️ Quét An Toàn Link'** bên dưới để bắt đầu kiểm tra!*"
        )
        embed = discord.Embed(
            title="🛡️ TRẠM KIỂM TRA ĐƯỜNG DẪN & AN TOÀN LIÊN KẾT",
            description=desc,
            color=0x3498DB,
        )
        embed.set_footer(text="HyperHub Security Shield • Hệ Thống Phòng Chống Mã Độc Đa Tầng")
        return embed

    def build_scan_report_embed(
        self,
        user: discord.User | discord.Member,
        res: ThreatScanResult,
        remaining_quota: int,
    ) -> discord.Embed:
        """Tạo Embed báo cáo kết quả quét an toàn chi tiết."""
        owner_id = int(getattr(settings, "OWNER_ID", 0) or 0)
        is_owner = owner_id > 0 and user.id == owner_id

        if is_owner:
            quota_str = "👑 Bot Owner (Không giới hạn)"
        else:
            quota_str = f"`{remaining_quota}/3 lượt` (khung giờ 1 tiếng)"

        clean_url = (res.url or "N/A")
        if len(clean_url) > 100:
            clean_url = clean_url[:97] + "..."

        # Box VirusTotal thống kê trực quan
        vt_box = ""
        if res.vt_stats:
            s = res.vt_stats.get("safe", 0)
            m = res.vt_stats.get("malicious", 0)
            sp = res.vt_stats.get("suspicious", 0)
            tot = res.vt_stats.get("total", 70)
            vt_box = (
                "```text\n"
                "┌─────────────────────────┐\n"
                f"│  Safe       {s:>3}/{tot:<3}     │\n"
                f"│  Malicious  {m:>3}/{tot:<3}     │\n"
                f"│  Suspicious {sp:>3}/{tot:<3}     │\n"
                "└─────────────────────────┘\n"
                "```\n"
            )

        embed = discord.Embed(
            title=f"{res.badge_emoji} KẾT QUẢ KIỂM TRA: {res.level_label}",
            description=(
                f"🔗 **URL:** `{clean_url}`\n"
                f"📊 **Đánh giá:** **{res.level_label}**\n"
                f"🎯 **Điểm rủi ro (Risk Score):** `{res.risk_score}/100`\n\n"
                f"{vt_box}"
                f"📄 **Chi tiết phân tích:**\n> {res.summary}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=res.color_hex,
        )

        embed.add_field(name="🛡️ Trạng Thái", value=f"**{res.level_label}**", inline=True)
        embed.add_field(name="⏱️ Hạn Mức Cá Nhân", value=quota_str, inline=True)

        # CHỈ HIỂN THỊ CHI TIẾT KẾT QUẢ ĐÁNG NGHI NẾU URL CÓ VẤN ĐỀ
        if res.level in (ThreatLevel.MALICIOUS, ThreatLevel.SUSPICIOUS) and res.details:
            field_name = (
                "🚫 Chi Tiết Mối Đe Dọa Đã Phát Hiện"
                if res.level == ThreatLevel.MALICIOUS
                else "⚠️ Dấu Hiệu Đáng Ngờ Đã Phát Hiện"
            )
            details_formatted = "\n".join(f"• {d}" for d in res.details[:8])
            embed.add_field(
                name=field_name,
                value=details_formatted,
                inline=False,
            )

        # Khuyến nghị
        if res.level == ThreatLevel.MALICIOUS:
            embed.add_field(
                name="⚠️ Khuyến Nghị Bảo Mật",
                value="🔴 **TUYỆT ĐỐI KHÔNG CLICK HOẶC TẢI VỀ!** Liên kết này có dấu hiệu mã độc hoặc lừa đảo rõ ràng.",
                inline=False,
            )
        elif res.level == ThreatLevel.SUSPICIOUS:
            embed.add_field(
                name="⚠️ Khuyến Nghị Bảo Mật",
                value="🟡 Hãy cẩn trọng khi truy cập. Không nhập mật khẩu hoặc thông tin cá nhân vào trang web này.",
                inline=False,
            )
        elif res.level == ThreatLevel.SAFE:
            embed.add_field(
                name="✨ Khuyến Nghị Bảo Mật",
                value="🟢 Liên kết an toàn, không phát hiện dấu hiệu nguy hiểm đã biết.",
                inline=False,
            )
        else:
            embed.add_field(
                name="ℹ️ Khuyến Nghị Bảo Mật",
                value="⚪ Chưa có đầy đủ đánh giá bảo mật. Cần thận trọng khi mở liên kết.",
                inline=False,
            )

        embed.set_footer(
            text=f"HyperHub Antivirus Engine • Thời gian quét: {res.scan_time_ms:.1f}ms • Chỉ gửi cho bạn"
        )
        return embed

    async def auto_setup_scanner_channel(self, purge: bool = True) -> None:
        """Tự động dọn dẹp tin nhắn cũ và đăng Bảng Điều Khiển mới tại kênh LINK_SCANNER_CHANNEL_ID."""
        await self.bot.wait_until_ready()
        channel_id = getattr(settings, "LINK_SCANNER_CHANNEL_ID", 1546522680638054461)
        channel = self.bot.get_channel(channel_id)
        if not channel and hasattr(self.bot, "fetch_channel"):
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                pass

        if not channel or not isinstance(channel, discord.TextChannel):
            log.warning("Không tìm thấy kênh kiểm tra link LINK_SCANNER_CHANNEL_ID: %s", channel_id)
            return

        try:
            if purge:
                try:
                    await channel.purge(limit=50)
                except Exception as pe:
                    log.debug("Bỏ qua lỗi purge nhanh: %s", pe)
                try:
                    async for m in channel.history(limit=50):
                        try:
                            await m.delete()
                        except Exception:
                            pass
                except Exception:
                    pass

            panel_embed = self.build_control_panel_embed()
            view = LinkScannerControlView(self)
            await channel.send(embed=panel_embed, view=view)
            log.info("✅ Đã dọn sạch kênh và khởi tạo bảng điều khiển kiểm tra link mới tại #%s", channel.name)
        except Exception as e:
            log.warning("Lỗi khi thiết lập kênh kiểm tra link: %s", e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Tự động dọn dẹp tin nhắn thường của người dùng tại kênh kiểm tra link."""
        if message.author.bot or not message.guild:
            return

        channel_id = getattr(settings, "LINK_SCANNER_CHANNEL_ID", 1546522680638054461)
        if message.channel.id != channel_id:
            return

        # Xóa tin nhắn người dùng để giữ kênh gọn gàng
        try:
            await message.delete()
        except Exception:
            pass

        # Nhắc nhở người dùng sử dụng nút bấm
        try:
            await message.channel.send(
                f"💡 {message.author.mention}, để kiểm tra link an toàn và nhận kết quả riêng tư (chỉ mình bạn thấy), "
                f"vui lòng nhấn nút **'🛡️ Quét An Toàn Link'** trên bảng điều khiển ở trên!",
                delete_after=7.0,
            )
        except Exception:
            pass

async def setup(bot: commands.Bot) -> None:
    cog = LinkScannerCog(bot)
    await bot.add_cog(cog)
    bot.add_view(LinkScannerControlView(cog))
