"""Hướng dẫn quản trị HyperHub (panel lệnh admin + cẩm nang owner)."""

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("HelpCog")

# Từ khóa nhận diện lệnh quản trị (khớp quy ước description "[Admin/Owner]..." toàn repo)
_ADMIN_HINT_KEYWORDS = ("admin", "owner", "quản trị", "moderator", "giám khảo")

def _flatten_app_command(cmd, prefix: str = "") -> list[tuple[str, str]]:
    """Trải phẳng lệnh/group thành [(tên đầy đủ, mô tả)]."""
    if isinstance(cmd, app_commands.Group):
        out: list[tuple[str, str]] = []
        for sub in cmd.commands:
            out.extend(_flatten_app_command(sub, f"{prefix}{cmd.name} "))
        return out
    return [(f"/{prefix}{cmd.name}", (cmd.description or "").strip())]

def _iter_server_commands(bot: commands.Bot) -> list[tuple[str, str, str]]:
    """Quét toàn bộ slash commands đã đăng ký → [(tên cog, /lệnh, mô tả)], không trùng."""
    ordered: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        for cog_name in sorted(bot.cogs):
            cog = bot.cogs[cog_name]
            for cmd in getattr(cog, "__cog_app_commands__", []):
                for qual, desc in _flatten_app_command(cmd):
                    if (qual, desc) not in seen:
                        seen.add((qual, desc))
                        ordered.append((cog_name, qual, desc))
        for cmd in bot.tree.get_commands():
            for qual, desc in _flatten_app_command(cmd):
                if (qual, desc) not in seen:
                    seen.add((qual, desc))
                    binding = getattr(cmd, "binding", None)
                    cname = type(binding).__name__ if binding else "Chung"
                    ordered.append((cname, qual, desc))
    except Exception as e:
        logger.warning(f"Không thể quét toàn bộ slash commands: {e}")
    return ordered

def _is_admin_command(qualified_name: str, description: str) -> bool:
    text = f"{qualified_name} {description}".lower()
    return any(k in text for k in _ADMIN_HINT_KEYWORDS)

def build_command_list_fields(bot: commands.Bot) -> list[dict]:
    """Tạo fields embed liệt kê ĐỘNG toàn bộ lệnh có trong server (tự khớp 100%)."""
    member_lines: list[str] = []
    admin_lines: list[str] = []
    for _cog, qual, desc in _iter_server_commands(bot):
        line = f"• `{qual}` : {desc}" if desc else f"• `{qual}`"
        if _is_admin_command(qual, desc):
            admin_lines.append(line)
        else:
            member_lines.append(line)

    def _chunk(title: str, lines: list[str]) -> list[dict]:
        if not lines:
            return []
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > 950:
                chunks.append("\n".join(current))
                current, current_len = [], 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return [
            {
                "name": title if len(chunks) == 1 else f"{title} ({i + 1}/{len(chunks)})",
                "value": c,
                "inline": False,
            }
            for i, c in enumerate(chunks)
        ]

    header = f"Tổng cộng **{len(member_lines) + len(admin_lines)}** lệnh slash đang hoạt động trên server."
    fields: list[dict] = [{"name": "📊 Tổng Quan", "value": header, "inline": False}]
    fields.extend(_chunk("👤 Lệnh Thành Viên", member_lines))
    fields.extend(_chunk("🛠️ Lệnh Quản Trị (Admin & Owner)", admin_lines))
    return fields

class HelpCog(commands.Cog, name="Help"):
    """Lệnh hướng dẫn sử dụng bot đầy đủ và danh sách ngôn ngữ hỗ trợ."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @classmethod
    def build_owner_help_embeds(cls, bot: commands.Bot | None = None) -> list[discord.Embed]:
        """Tạo bộ 3 Rich Embeds cẩm nang toàn diện dành riêng cho Bot Owner."""
        embed1 = create_embed(
            title="👑 [1] SỔ TAY QUẢN TRỊ VIÊN & LỆNH BÍ MẬT BOT OWNER",
            description=(
                "### 🎯 CÁC CÂU LỆNH PREFIX TRỰC TIẾP\n\n"
                "• **`.skip`** :\n"
                "  - **Khi ở ngoài ticket (Kênh `#📋・ranked`):** Bỏ qua hàng chờ tìm người, tự động ghép với `🤖 Bot Tester` và tạo ngay phòng đấu với **đề bài thuộc phân hạng đỉnh cao: Division 1 (👑 HT1 / Div. 1 - 3000+ pts)**.\n"
                "  - **Khi ở trong ticket (`#⚔️・duel-xxxxxx`):** Bỏ qua chặng hiện tại, xuất mã nguồn giải mẫu C++ chuẩn AC, gửi gợi ý và tự động phát **bài toán thuộc Division 1 (Div. 1: LT1, MT1, HT1)** cho chặng tiếp theo.\n\n"
                "• **`.test`** : *(Chỉ Bot Owner trong ticket)*\n"
                "  - Đóng ngay phòng đấu và xử thắng test cho Owner. ID Owner không bị tính vào BXH nhưng vẫn cập nhật điểm/role để kiểm thử.\n\n"
                "• **`.close`** :\n"
                "  - Yêu cầu đóng phòng đấu / đầu hàng (có bảng nút bấm xác nhận 🏳️ an toàn).\n\n"
                "• **`.list`** :\n"
                "  - Hiển thị bảng tổng kết chi tiết từng chặng: Tên bài, % điểm đúng của 2 đấu thủ, số mạng ❤️ còn lại.\n\n"
                "• **`.help`** :\n"
                "  - Gửi toàn bộ cẩm nang hướng dẫn hệ thống này vào tin nhắn riêng (DM) của Bot Owner."
            ),
            embed_type=EmbedType.INFO,
            color=0xF1C40F,
            footer_text="Cẩm nang bí mật dành riêng cho Bot Owner • Trang 1/3",
        )

        # Trang 2: liệt kê ĐỘNG toàn bộ lệnh trên server nếu có bot, fallback tĩnh nếu không
        if bot is not None:
            dyn_cmds = _iter_server_commands(bot)
            dyn_admin = [f"• `{q}` : {d}" for _c, q, d in dyn_cmds if _is_admin_command(q, d)]
            dyn_member = [f"• `{q}` : {d}" for _c, q, d in dyn_cmds if not _is_admin_command(q, d)]
            desc2 = (
                f"### 🛠️ LỆNH SLASH QUẢN TRỊ (ADMIN & OWNER) — {len(dyn_admin)} lệnh\n"
                + "\n".join(dyn_admin)
                + f"\n\n### 👤 LỆNH SLASH DÀNH CHO THÀNH VIÊN — {len(dyn_member)} lệnh\n"
                + "\n".join(dyn_member)
            )
        else:
            desc2 = (
                "### 🛠️ LỆNH SLASH QUẢN TRỊ (ADMIN & OWNER)\n"
                "• `/status` : [Admin] Kiểm tra trạng thái AI Core & các chỉ số sức khỏe của bot.\n"
                "• `/reload` : [Admin/Owner] Reload toàn bộ bot, cogs, CSDL và làm mới 6 kênh giao diện.\n"
                "• `/setpts <user> <number> [mode]` : [Admin/Owner] Thiết lập điểm Rating và Rank cho thành viên.\n"
                "• `/color <hex>` : [Admin/Owner] Thay đổi mã màu chủ đề embed mặc định của bot.\n"
                "• `/tha {user}` : [Owner Only] Ân xá và gỡ bỏ lệnh cấm thi đấu Ranked cho thành viên.\n"
                "• `/admin_list` : [Admin/Owner] Thống kê số lượng đề bài Ranked 1:1 và dung lượng hệ thống.\n"
                "• `/auto_heal <file>` : [Admin] Kích hoạt AI Core quét và tự động sửa lỗi cú pháp file.\n\n"
                "### 👤 LỆNH SLASH DÀNH CHO THÀNH VIÊN\n"
                "• `/check [user]` : Kiểm tra hạn mức Token hàng ngày, Gói Hyper và tiến trình sử dụng.\n"
                "• `/help` : Mở menu hướng dẫn sử dụng tương tác có nút bấm.\n\n"
                "💡 *Danh sách đầy đủ, tự động cập nhật theo server: dùng `/help` → nút **📌 Danh Sách Lệnh**.*"
            )
        embed2 = create_embed(
            title="🛠️ [2] DANH SÁCH LỆNH SLASH COMMANDS QUẢN TRỊ & THÀNH VIÊN",
            description=desc2,
            embed_type=EmbedType.INFO,
            color=0x3498DB,
            footer_text="Cẩm nang bí mật dành riêng cho Bot Owner • Trang 2/3",
        )

        embed3 = create_embed(
            title="🌐 [3] HỆ THỐNG 6 KÊNH GIAO DIỆN TỰ ĐỘNG (AUTO-SETUP)",
            description=(
                "1. **`#✅・accounts` (`CF_ID`)** : Xác minh tài khoản Codeforces tự động 3 bước qua bài nộp test code mẫu.\n"
                "2. **`#📤・mode` (`CHON_ID`)** : Sổ tay 6 Embeds toàn diện và Menu chọn 2 chế độ làm bài (Mode 1 / Mode 2).\n"
                "3. **`#📋・contest` (`BAITAP_ID`)** : Trình duyệt 3 Rich Embeds cuộc thi Codeforces + Tự động chuyển sang Chế độ Bảo trì khi CF API lỗi và tự khôi phục khi API mở lại.\n"
                "4. **`#📤・submit` (`SUBMIT_ID`)** : Trạm nộp bài Rated/Unrated mở Form Modal chấm Themis Multi-Test Sandbox.\n"
                "5. **`#✅・rank` (`UP_RANK`)** : Bảng xếp hạng Top 50 song song Freedom & Ranked (cập nhật 45s).\n"
                "6. **`#📋・ranked` (`RANKED_CHANNEL_ID`)** : Đấu trường Ranked 1:1, 2 Mạng ❤️, Matchmaking ±1 Tier, hàng chờ Embed."
            ),
            embed_type=EmbedType.INFO,
            color=0x2ECC71,
            footer_text="Cẩm nang bí mật dành riêng cho Bot Owner • Trang 3/3",
        )

        return [embed1, embed2, embed3]

    ADMIN_GUIDE_CHANNEL_ID = 1556246243749924945

    def build_admin_guide_embeds(self) -> list[discord.Embed]:
        """Dựng panel hướng dẫn các lệnh admin (lấy live từ tree, chỉ lệnh trong allowlist)."""
        try:
            from bot import COMMAND_ALLOWLIST
        except Exception:
            COMMAND_ALLOWLIST = set()
        lines: list[str] = []
        for _cog, qual, desc in _iter_server_commands(self.bot):
            name = qual.lstrip("/").split(" ")[0]
            if name in COMMAND_ALLOWLIST:
                lines.append(f"• `{qual}` : {desc}" if desc else f"• `{qual}`")
        if not lines:
            lines = ["• `/reload` • `/status` • `/kick` • `/ban` • `/unban` • `/mute` • `/unmute` • `/reset` • `/warn` • `/deletewarn` • `/warntest`"]
        embed = create_embed(
            title="👑 HƯỚNG DẪN LỆNH QUẢN TRỊ (ADMIN ONLY)",
            description=(
                "Các lệnh slash dành cho quản trị viên (Owner / Co-Owner / Administrator / Moderator):\n\n"
                + "\n".join(lines)
                + "\n\n⚠️ *Kênh này chỉ dành cho admin. Mọi thao tác kỷ luật cũng có thể thực hiện trên Web Admin Hub.*"
            ),
            embed_type=EmbedType.INFO,
            color=0xF1C40F,
            footer_text="HyperHub Admin • Tự động cập nhật khi bot khởi động",
        )
        return [embed]

    async def auto_setup_admin_guide(self, purge: bool = True) -> None:
        """Dọn kênh hướng dẫn admin và đăng panel lệnh mới nhất."""
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.ADMIN_GUIDE_CHANNEL_ID)
        if not channel and hasattr(self.bot, "fetch_channel"):
            try:
                channel = await self.bot.fetch_channel(self.ADMIN_GUIDE_CHANNEL_ID)
            except Exception:
                pass
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.warning(f"Không tìm thấy kênh admin guide: {self.ADMIN_GUIDE_CHANNEL_ID}")
            return
        try:
            if purge:
                try:
                    await channel.purge(limit=100)
                except Exception:
                    pass
                try:
                    async for m in channel.history(limit=50):
                        try:
                            await m.delete()
                        except Exception:
                            pass
                except Exception:
                    pass
            await channel.send(embeds=self.build_admin_guide_embeds())
            logger.info(f"✅ Đã đăng panel hướng dẫn lệnh admin tại #{channel.name} ({channel.id})")
        except Exception as e:
            logger.warning(f"Lỗi đăng panel admin guide: {e}")

    async def send_owner_help_dm(self) -> bool:
        """Gửi cẩm nang hướng dẫn qua tin nhắn riêng (DM) cho Owner ID."""
        owner_id = settings.OWNER_ID
        if not owner_id:
            logger.warning("Chưa cấu hình OWNER_ID trong settings.")
            return False

        try:
            owner = self.bot.get_user(owner_id)
            if not owner:
                owner = await self.bot.fetch_user(owner_id)
            if owner:
                embeds = self.build_owner_help_embeds(self.bot)
                await owner.send(embeds=embeds)
                return True
        except Exception as e:
            logger.error(f"Lỗi khi gửi tin nhắn riêng cho Owner (ID: {owner_id}): {e}")
        return False

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
