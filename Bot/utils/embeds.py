"""Hệ thống tạo Discord Embed đồ họa siêu trực quan, sinh động với thanh đo, màu ANSI, tự động nhận diện file LOGO_ID cục bộ."""

import asyncio
import datetime
import os
import re
from enum import Enum
from typing import Any

import discord

from config.settings import settings


class EmbedType(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    RANK_UP = "rank_up"
    SUBMISSION = "submission"
    CONTEST = "contest"
    PROFILE = "profile"
    LEADERBOARD = "leaderboard"
    MODE_SELECT = "mode_select"
    JUDGE = "judge"


# Bảng mã màu sắc sống động (Vivid Palette)
EMBED_COLORS: dict[EmbedType, int] = {
    EmbedType.SUCCESS: 0x00B894,  # Xanh ngọc lục bảo tươi (Mint Green)
    EmbedType.ERROR: 0xD63031,  # Đỏ Ruby rực rỡ (Ruby Red)
    EmbedType.WARNING: 0xFDCB6E,  # Vàng cam rực rỡ (Mustard Gold)
    EmbedType.INFO: 0x0984E3,  # Xanh dương hoàng gia (Electron Blue)
    EmbedType.RANK_UP: 0xFFD700,  # Vàng kim nguyên chất (Pure Gold)
    EmbedType.SUBMISSION: 0x6C5CE7,  # Tím điện quang (Electric Purple)
    EmbedType.CONTEST: 0xE17055,  # Cam lửa sa mạc (Orange Flame)
    EmbedType.PROFILE: 0xFD79A8,  # Hồng tím nghệ thuật (Pico Pink)
    EmbedType.LEADERBOARD: 0xF1C40F,  # Vàng vinh danh (Sun Yellow)
    EmbedType.MODE_SELECT: 0x00CEC9,  # Xanh ngọc lam biển (Robin Egg)
    EmbedType.JUDGE: 0xA29BFE,  # Tím nhạt ánh bạc (Shy Lilac)
}

# Biểu tượng cảm xúc tiêu đề sinh động
EMBED_ICONS: dict[EmbedType, str] = {
    EmbedType.SUCCESS: "✨",
    EmbedType.ERROR: "💥",
    EmbedType.WARNING: "⚡",
    EmbedType.INFO: "💎",
    EmbedType.RANK_UP: "👑",
    EmbedType.SUBMISSION: "🚀",
    EmbedType.CONTEST: "🏆",
    EmbedType.PROFILE: "🌟",
    EmbedType.LEADERBOARD: "🥇",
    EmbedType.MODE_SELECT: "🎮",
    EmbedType.JUDGE: "⚖️",
}


def find_local_logo_path() -> str | None:
    """Tìm kiếm file ảnh logo trong thư mục gốc hoặc thư mục assets của bot (LOGO_ID.png, LOGO_ID.jpg...)."""
    candidates = [
        "LOGO_ID.png",
        "LOGO_ID.jpg",
        "LOGO_ID.jpeg",
        "LOGO_ID.webp",
        "LOGO_ID",
        "assets/LOGO_ID.png",
        "assets/LOGO_ID.jpg",
        "assets/logo.png",
        "assets/logo.jpg",
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            return c
    return None


def get_logo_file() -> discord.File | None:
    """Tạo đối tượng discord.File từ ảnh LOGO_ID cục bộ để đính kèm vào tin nhắn Discord."""
    path = find_local_logo_path()
    if path:
        ext = os.path.splitext(path)[1] or ".png"
        return discord.File(path, filename=f"LOGO_ID{ext}")
    return None


def get_logo_attachment_url() -> str | None:
    """Trả về URI 'attachment://LOGO_ID.ext' nếu tìm thấy file ảnh logo cục bộ."""
    path = find_local_logo_path()
    if path:
        ext = os.path.splitext(path)[1] or ".png"
        return f"attachment://LOGO_ID{ext}"
    return None


def generate_progress_bar(
    current: float, total: float, length: int = 12, style: str = "blocks"
) -> str:
    """Tạo thanh tiến độ đồ họa trực quan đa dạng kiểu dáng."""
    if total <= 0:
        return "`[░░░░░░░░░░░░]` **0%**"

    ratio = max(0.0, min(1.0, current / total))
    filled = int(round(length * ratio))
    percent = int(ratio * 100)

    if style == "blocks":
        bar = "▰" * filled + "▱" * (length - filled)
        return f"`[{bar}]` **{percent}%**"
    elif style == "solid":
        bar = "█" * filled + "░" * (length - filled)
        return f"`[{bar}]` **{percent}%**"
    elif style == "gradient":
        symbols = ["░", "▒", "▓", "█"]
        full_blocks = int(length * ratio)
        remainder = (length * ratio) - full_blocks
        sub_index = int(remainder * len(symbols))
        sub_char = (
            symbols[sub_index]
            if sub_index < len(symbols) and full_blocks < length
            else ""
        )
        bar = (
            "█" * full_blocks
            + sub_char
            + "░" * (length - full_blocks - (1 if sub_char else 0))
        )
        return f"`[{bar}]` **{percent}%**"
    else:
        bar = "■" * filled + "□" * (length - filled)
        return f"`[{bar}]` **{percent}%**"


def format_stat_box(title: str, value: str, subtext: str = "") -> str:
    """Định dạng ô thống kê nhỏ gọn, thẩm mỹ cao."""
    res = f"╭─ **{title}**\n│ ➔ `{value}`"
    if subtext:
        res += f" *({subtext})*"
    res += "\n╰────────────────"
    return res


def format_diff_code(status_type: str, text: str) -> str:
    """Tạo khối code diff có màu sắc sống động trên Discord."""
    prefix = (
        "+" if status_type == "success" else ("-" if status_type == "error" else "!")
    )
    return f"```diff\n{prefix} {text}\n```"


def wrap_in_border(content: str) -> str:
    """Removed - kept for backward compatibility."""
    return content


def create_embed(
    title: str,
    description: str | None = None,
    embed_type: EmbedType | str = EmbedType.INFO,
    fields: list[dict[str, Any]] | None = None,
    color: int | None = None,
    footer_text: str | None = None,
    custom_thumbnail: str | None = None,
    custom_image: str | None = None,
    author_name: str | None = None,
    author_icon: str | None = None,
    author_url: str | None = None,
    timestamp: datetime.datetime | None = None,
    is_profile: bool = False,
    user_avatar_url: str | None = None,
) -> discord.Embed:
    """
    Hàm khởi tạo Embed siêu trực quan, sinh động và bắt mắt:
    - Tự động nhận diện file ảnh LOGO_ID cục bộ trong thư mục bot.
    - Căn chỉnh thumbnail và icon 1:1 chuẩn xác.
    - Màu sắc rực rỡ, icon động lực.
    - Tự động bao bọc description trong khung border ╭━━━╮ / ╰━━━╯.
    """
    if isinstance(embed_type, str):
        try:
            embed_type = EmbedType(embed_type)
        except ValueError:
            embed_type = EmbedType.INFO

    selected_color = (
        color if color is not None else EMBED_COLORS.get(embed_type, 0x0984E3)
    )
    prefix_icon = EMBED_ICONS.get(embed_type, "")

    formatted_title = (
        f"{prefix_icon} {title}".strip()
        if prefix_icon and not title.startswith(prefix_icon)
        else title
    )

    # Description không border, giới hạn 4000 ký tự
    raw_desc = description or ""
    if len(raw_desc) > 4000:
        raw_desc = raw_desc[:3950] + "\n*... (Đã rút gọn)*"

    embed = discord.Embed(
        title=formatted_title,
        description=raw_desc,
        color=selected_color,
        timestamp=timestamp or datetime.datetime.now(datetime.timezone.utc),
    )

    # Tác giả (Author)
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon, url=author_url)

    # Thumbnail sinh động:
    local_logo_uri = get_logo_attachment_url()

    if is_profile and user_avatar_url:
        embed.set_thumbnail(url=user_avatar_url)
    elif custom_thumbnail:
        embed.set_thumbnail(url=custom_thumbnail)
    elif local_logo_uri:
        embed.set_thumbnail(url=local_logo_uri)
    elif settings.LOGO_ID and settings.LOGO_ID.startswith("http"):
        embed.set_thumbnail(url=settings.LOGO_ID)

    # Ảnh minh họa chính (Image)
    if custom_image:
        embed.set_image(url=custom_image)

    # Các trường thông tin (Fields)
    if fields:
        for field in fields:
            name = field.get("name", "—")
            value = field.get("value", "—")
            inline = field.get("inline", False)
            if name and value:
                embed.add_field(name=name, value=value, inline=inline)

    # Chân trang (Footer)
    footer = footer_text or "⚡ Đấu trường Lập trình Thi đấu • Codeforces System"
    icon = None
    if is_profile and user_avatar_url:
        icon = user_avatar_url
    elif local_logo_uri:
        icon = local_logo_uri
    elif settings.LOGO_ID and settings.LOGO_ID.startswith("http"):
        icon = settings.LOGO_ID

    embed.set_footer(text=footer, icon_url=icon)

    return embed


def success_embed(title: str, description: str, **kwargs) -> discord.Embed:
    return create_embed(
        title=title, description=description, embed_type=EmbedType.SUCCESS, **kwargs
    )


def error_embed(title: str, description: str, **kwargs) -> discord.Embed:
    return create_embed(
        title=title, description=description, embed_type=EmbedType.ERROR, **kwargs
    )


def warning_embed(title: str, description: str, **kwargs) -> discord.Embed:
    return create_embed(
        title=title, description=description, embed_type=EmbedType.WARNING, **kwargs
    )


def info_embed(title: str, description: str, **kwargs) -> discord.Embed:
    return create_embed(
        title=title, description=description, embed_type=EmbedType.INFO, **kwargs
    )


# ==================== HYPERHUB EMBED HELPERS ====================
HYPERHUB_COLOR = 0x9F7AEA
AURA_COLOR = 0x7C3AED
SUCCESS_COLOR = 0x34D399
ERROR_COLOR = 0xF87171
WARN_COLOR = 0xFBBF24
INFO_COLOR = 0x3B82F6

FOOTER_TEXT = "🌌 HYPERHUB MUSIC • LEARN • CHILL • CONNECT"
DIVIDER = "━" * 16

_THEME_COLOR = HYPERHUB_COLOR
_LOGO_URL = ""


def set_theme_color(color: int) -> None:
    """Cập nhật màu chủ đề (dùng bởi /color)."""
    global _THEME_COLOR
    _THEME_COLOR = int(color)


def get_theme_color() -> int:
    return _THEME_COLOR


def set_logo_url(url: str) -> None:
    """Cập nhật URL logo dán vào thumbnail của mọi embed."""
    global _LOGO_URL
    _LOGO_URL = (url or "").strip()


def attach_logo(embed: discord.Embed) -> None:
    """Dán logo vào thumbnail của embed nếu LOGO_URL đã được cấu hình."""
    if _LOGO_URL:
        embed.set_thumbnail(url=_LOGO_URL)


def add_credit(embed: discord.Embed, credit: str = "") -> None:
    import time
    now = int(time.time())
    ts = f"<t:{now}:f>"
    text = f"{credit} — {ts}" if credit else ts
    embed.set_footer(text=text)


def mod_success_embed(title: str, description: str = "", credit: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=SUCCESS_COLOR,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    add_credit(embed, credit)
    attach_logo(embed)
    return embed


def mod_error_embed(title: str, description: str = "", credit: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=ERROR_COLOR,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    add_credit(embed, credit)
    attach_logo(embed)
    return embed


def mod_warning_embed(title: str, description: str = "", credit: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=WARN_COLOR,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    add_credit(embed, credit)
    attach_logo(embed)
    return embed


def build_log_embed(
    action: str,
    target: str,
    moderator: str,
    reason: str,
    color: int = INFO_COLOR,
    extra: list[tuple[str, str]] | None = None,
    credit: str = "",
) -> discord.Embed:
    embed = discord.Embed(
        title=f"Moderation Log — {action}",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.add_field(name="Target", value=target, inline=False)
    embed.add_field(name="Moderator", value=moderator, inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    if extra:
        for name, value in extra:
            embed.add_field(name=name, value=value, inline=False)
    add_credit(embed, credit)
    attach_logo(embed)
    return embed


async def send_log(
    bot: discord.Client,
    guild: discord.Guild,
    embed: discord.Embed,
    settings: Any,
) -> None:
    log_ch_id = getattr(settings, "log_channel_id", None) or getattr(settings, "EEE_CHANNELS", None)
    if not log_ch_id:
        return
    channel = guild.get_channel(log_ch_id) or bot.get_channel(log_ch_id)
    if channel and isinstance(channel, discord.TextChannel):
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass


def base_embed(*, title: str | None = None, description: str | None = None, color: int | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color or _THEME_COLOR)
    embed.set_footer(text=FOOTER_TEXT)
    attach_logo(embed)
    return embed


def success(message: str, title: str = "✅ Thành công") -> discord.Embed:
    return base_embed(title=title, description=message, color=SUCCESS_COLOR)


def error(message: str, title: str = "❌ Lỗi") -> discord.Embed:
    return base_embed(title=title, description=message, color=ERROR_COLOR)


def warning(message: str, title: str = "⚠️ Cảnh báo") -> discord.Embed:
    return base_embed(title=title, description=message, color=WARN_COLOR)


def info(message: str, title: str = "🌌 HyperHub Music") -> discord.Embed:
    return base_embed(title=title, description=message)


def now_playing(track: Any, up_next: list, color: int = AURA_COLOR) -> discord.Embed:
    lines = [
        "🎵 **Now Playing**",
        DIVIDER,
        f"**{track.title}**",
        track.artist or "",
        "",
    ]
    if getattr(track, "requested_by", None):
        lines.append(f"👤 Requested by: <@{track.requested_by}>")
        lines.append("")
    lines.append("📋 **Up Next**")
    if up_next:
        lines.extend(f"{index}. **{item.title}**" for index, item in enumerate(up_next[:10], 1))
        if len(up_next) > 10:
            lines.append(f"... và {len(up_next) - 10} bài khác")
    else:
        lines.append("Hàng chờ trống 🎶")
    embed = base_embed(description="\n".join(lines), color=color)
    thumbnail = getattr(track, "thumbnail_url", None)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    return embed


def queue(current: Any, up_next: list) -> discord.Embed:
    if current is None:
        embed = base_embed(description="Hàng chờ đang trống 🎶")
        embed.title = "📋 Hàng chờ"
        return embed
    return now_playing(current, up_next, color=_THEME_COLOR)


# ============================================================
# MULTI-EMBED HELPERS
# ============================================================

MAX_EMBED_DESC = 4000
MAX_EMBED_FIELD_VALUE = 1024
MAX_EMBED_FIELDS = 25
# Giới hạn tin nhắn thường của Discord: 2000 ký tự/tin
MAX_PLAIN_MSG_LEN = 2000


def split_by_words(text: str, max_len: int = MAX_PLAIN_MSG_LEN) -> list[str]:
    """Chia text dài thành nhiều phần, mỗi phần tối đa max_len ký tự.

    Thứ tự ưu tiên điểm cắt (không bao giờ cắt giữa chừng một từ,
    trừ khi gặp từ đơn dài hơn max_len):
    1. Ranh giới đoạn văn (dòng trống)
    2. Ranh giới dòng (xuống dòng)
    3. Ranh giới từ (khoảng trắng)
    """
    if not text:
        return [""]
    if len(text) <= max_len:
        return [text]

    parts: list[str] = []

    def _push(chunk: str) -> None:
        chunk = chunk.strip("\n")
        if chunk.strip():
            parts.append(chunk)

    def _split_words(line: str) -> None:
        """Chia một dòng dài theo ranh giới từ."""
        current = ""
        for word in line.split(" "):
            if not word:
                continue
            candidate = f"{current} {word}".strip() if current else word
            if len(candidate) <= max_len:
                current = candidate
            else:
                if current:
                    _push(current)
                # Từ đơn dài hơn max_len -> cắt cứng (hiếm: URL/hash dài)
                while len(word) > max_len:
                    _push(word[:max_len])
                    word = word[max_len:]
                current = word
        if current:
            _push(current)

    current = ""
    for para in text.split("\n\n"):
        block = para.strip("\n")
        if not block:
            continue
        candidate = f"{current}\n\n{block}".strip("\n") if current else block
        if len(candidate) <= max_len:
            current = candidate
            continue
        # Đẩy phần đang dồn
        if current:
            _push(current)
            current = ""
        # Đoạn quá dài -> chia theo dòng
        if len(block) > max_len:
            sub_current = ""
            for line in block.split("\n"):
                line_candidate = f"{sub_current}\n{line}".strip("\n") if sub_current else line
                if len(line_candidate) <= max_len:
                    sub_current = line_candidate
                    continue
                if sub_current:
                    _push(sub_current)
                    sub_current = ""
                if len(line) > max_len:
                    _split_words(line)
                else:
                    sub_current = line
            current = sub_current
        else:
            current = block

    if current.strip():
        _push(current)

    return parts or [""]


async def send_long_text(
    channel,
    text: str,
    max_len: int = MAX_PLAIN_MSG_LEN,
    reply_to: discord.Message | None = None,
) -> None:
    """Gửi text dài dưới dạng nhiều tin nhắn thường, mỗi tin <= max_len ký tự. Hỗ trợ reply tin nhắn gốc."""
    chunks = split_by_words(text, max_len)
    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(0.6)
        if i == 0 and reply_to is not None:
            try:
                await reply_to.reply(chunk, mention_author=False)
                continue
            except Exception:
                pass
        await channel.send(chunk)



def split_long_text(text: str, max_len: int = MAX_EMBED_DESC) -> list[str]:
    """Chia text dài thành các phần nhỏ hơn max_len, cắt ở ranh giới từ/đoạn."""
    if len(text) <= max_len:
        return [text]
    
    parts = []
    current = ""
    
    # Ưu tiên cắt ở đoạn (double newline)
    paragraphs = text.split("\n\n")
    
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_len:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                parts.append(current)
            # Para quá dài -> cắt ở câu
            if len(para) > max_len:
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= max_len:
                        current += (" " if current else "") + sent
                    else:
                        if current:
                            parts.append(current)
                        current = sent
            else:
                current = para
    
    if current:
        parts.append(current)
    
    return parts


def create_multi_embeds(
    title: str,
    description: str,
    embed_type: EmbedType | str = EmbedType.INFO,
    color: int | None = None,
    footer_text: str | None = None,
) -> list[discord.Embed]:
    """
    Tạo nhiều embed từ text dài. Embed đầu có title, các embed sau chỉ có description.
    """
    if isinstance(embed_type, str):
        try:
            embed_type = EmbedType(embed_type)
        except ValueError:
            embed_type = EmbedType.INFO

    selected_color = color if color is not None else EMBED_COLORS.get(embed_type, 0x0984E3)
    prefix_icon = EMBED_ICONS.get(embed_type, "")
    
    base_title = f"{prefix_icon} {title}".strip() if prefix_icon else title
    
    parts = split_long_text(description, MAX_EMBED_DESC)
    embeds = []
    
    for i, part in enumerate(parts):
        if i == 0:
            embed = discord.Embed(
                title=base_title,
                description=part,
                color=selected_color,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
        else:
            # Embed tiếp theo không title, thêm indicator
            embed = discord.Embed(
                description=f"*... (tiếp)*\n\n{part}",
                color=selected_color,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
        
        footer = footer_text or "⚡ Đấu trường Lập trình Thi đấu • Codeforces System"
        if len(parts) > 1:
            footer += f" ({i+1}/{len(parts)})"
        embed.set_footer(text=footer)
        
        embeds.append(embed)
    
    return embeds


async def send_multi_embeds(
    channel_or_interaction: discord.TextChannel | discord.Interaction,
    title: str,
    description: str,
    embed_type: EmbedType | str = EmbedType.INFO,
    color: int | None = None,
    footer_text: str | None = None,
    ephemeral: bool = False,
) -> None:
    """Gửi nhiều embed tự động nếu content quá dài (giãn nhịp tránh rate-limit)."""
    embeds = create_multi_embeds(title, description, embed_type, color, footer_text)

    if isinstance(channel_or_interaction, discord.Interaction):
        if not channel_or_interaction.response.is_done():
            await channel_or_interaction.response.send_message(embed=embeds[0], ephemeral=ephemeral)
            for emb in embeds[1:]:
                await asyncio.sleep(0.6)
                await channel_or_interaction.followup.send(embed=emb, ephemeral=ephemeral)
        else:
            await channel_or_interaction.followup.send(embed=embeds[0], ephemeral=ephemeral)
            for emb in embeds[1:]:
                await asyncio.sleep(0.6)
                await channel_or_interaction.followup.send(embed=emb, ephemeral=ephemeral)
    else:
        await channel_or_interaction.send(embed=embeds[0])
        for emb in embeds[1:]:
            await asyncio.sleep(0.6)
            await channel_or_interaction.send(embed=emb)
