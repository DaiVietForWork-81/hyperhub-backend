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
            title="👑 [1] SỔ TAY QUẢN TRỊ VIÊN & HỆ THỐNG ORBIT",
            description=(
                "### 🎯 KIẾN TRÚC & NGUYÊN TẮC VẬN HÀNH\n\n"
                "• **Kiến trúc Monorepo:** Bot Discord & Web API Bridge hoạt động song song tại cổng `8080`.\n"
                "• **Tìm kiếm siêu việt:** Kết hợp Lexical SQLite FTS5 (không dấu), Semantic Vector ONNX đa ngôn ngữ và SIMD C++ Native.\n"
                "• **Tự động sao lưu & Anti-Nuke:** ServerBackupService chụp snapshot cấu trúc server mỗi 6 giờ, tự động khôi phục khi có biến động.\n"
                "• **Quyền Admin & Owner:** Chủ server và Bot Owner có quyền thực thi toàn bộ lệnh quản trị, kick, ban, mute, reset, đồng bộ kho đề."
            ),
            embed_type=EmbedType.INFO,
            color=0xF1C40F,
            footer_text="Cẩm nang quản trị viên Orbit • Trang 1/3",
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
                "• `/status` : [Admin] Kiểm tra tình trạng sức khỏe hệ thống, ping, C++ Core & RAM.\n"
                "• `/reload` : [Admin/Owner] Nạp lại toàn bộ bot, cogs, CSDL và làm mới các kênh giao diện.\n"
                "• `/dongbokhode` : [Admin/Owner] Quét và đồng bộ toàn bộ tài liệu từ các kênh về CSDL.\n"
                "• `/gothailieu <id>` : [Admin] Gỡ tài liệu khỏi kho lưu trữ hệ thống.\n"
                "• `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`, `/reset` : Bộ lệnh kiểm duyệt kỷ luật thành viên.\n"
                "• `/warn`, `/deletewarn`, `/warntest` : Quản lý cảnh báo thành viên vi phạm.\n\n"
                "### 👤 LỆNH SLASH DÀNH CHO THÀNH VIÊN\n"
                "• `/timde <từ khóa>` : Tra cứu đề thi thông minh qua FTS5 & Semantic Vector.\n"
                "• `/layde <id>` : Tải đề thi trực tiếp theo mã ID.\n"
                "• `/timtailieu` : Mở giao diện tra cứu và nhận liên kết Web Portal.\n"
            )
        embed2 = create_embed(
            title="🛠️ [2] DANH SÁCH LỆNH SLASH COMMANDS HOẠT ĐỘNG",
            description=desc2,
            embed_type=EmbedType.INFO,
            color=0x3498DB,
            footer_text="Danh sách lệnh Slash Commands chuẩn • Trang 2/3",
        )

        embed3 = create_embed(
            title="🌐 [3] HỆ THỐNG KÊNH GIAO DIỆN & WEB PORTAL TỰ ĐỘNG",
            description=(
                "1. **`#📄・nộp-tài-liệu` (`DOC_INTAKE_CHANNEL_ID`)** : Nộp tài liệu học tập, bot tự động quét virus/spoof, phân loại khối lớp & môn học.\n"
                "2. **`#🔍・tra-cứu-tài-liệu` (`DOC_SEARCH_CHANNEL_ID`)** : Bảng hướng dẫn tra cứu kho đề thi chuyển tiếp trực tiếp sang Web Portal.\n"
                "3. **`#📄・verify-link` (`LINK_SCANNER_CHANNEL_ID`)** : Trạm kiểm tra URL an toàn, chống lừa đảo & mã độc.\n"
                "4. **`#help` (`ADMIN_GUIDE_CHANNEL_ID`)** : Panel cẩm nang lệnh Admin tự động làm mới khi khởi động bot.\n"
                "5. **`Web Portal`** : Cổng tra cứu kho tài liệu hiện đại tại `https://hyperhub-one.vercel.app/#vault` kết nối Bot API Bridge."
            ),
            embed_type=EmbedType.INFO,
            color=0x2ECC71,
            footer_text="Cấu trúc giao diện Orbit • Trang 3/3",
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
            footer_text="Orbit Admin • Tự động cập nhật khi bot khởi động",
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
            # 1. Kiểm tra xem panel admin guide đã có sẵn hay chưa
            existing_panel = None
            try:
                async for m in channel.history(limit=5):
                    if m.author == self.bot.user and m.embeds and "LỆNH QUẢN TRỊ" in (m.embeds[0].title or ""):
                        existing_panel = m
                        break
            except Exception:
                pass

            embeds = self.build_admin_guide_embeds()

            if existing_panel and not purge:
                await existing_panel.edit(embeds=embeds)
                logger.info(f"✅ Panel admin guide đã tồn tại, cập nhật nhẹ (0%% CPU) tại #{channel.name}")
                return

            if purge:
                try:
                    await channel.purge(limit=15)
                except Exception:
                    pass

            await channel.send(embeds=embeds)
            logger.info(f"✅ Đã đăng panel hướng dẫn lệnh admin mới tại #{channel.name} ({channel.id})")
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
