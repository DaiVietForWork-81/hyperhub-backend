from __future__ import annotations

import discord
from discord.ext import commands


def _extract_ids(text: str) -> list[int]:
    ids: list[int] = []
    for part in text.strip().split():
        clean = part.strip().replace("<@", "").replace(">", "").replace("!", "").replace("&", "")
        clean = clean.strip()
        if clean.isdigit():
            ids.append(int(clean))
    return ids


def parse_hex_color(text: str) -> int | None:
    """Chuyển '#RRGGBB', '0xRRGGBB' hoặc 'RRGGBB' thành int. Trả về None nếu không hợp lệ."""
    raw = text.strip().lstrip("#").lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6 or not all(ch in "0123456789abcdef" for ch in raw):
        return None
    return int(raw, 16)


async def parse_members(guild: discord.Guild, text: str) -> list[discord.Member]:
    ids = _extract_ids(text)
    members: list[discord.Member] = []
    for uid in ids:
        member = guild.get_member(uid)
        if member:
            members.append(member)
    return members


async def parse_users(
    bot: commands.Bot, guild: discord.Guild, text: str
) -> list[discord.User]:
    ids = _extract_ids(text)
    users: list[discord.User] = []
    for uid in ids:
        member = guild.get_member(uid)
        if member:
            users.append(member)
        else:
            try:
                user = await bot.fetch_user(uid)
                users.append(user)
            except (discord.NotFound, discord.HTTPException):
                continue
    return users


async def collect_members(
    guild: discord.Guild, first: discord.Member, additional: str | None
) -> list[discord.Member]:
    """Gộp target đầu + danh sách bổ sung, loại trùng."""
    targets = [first]
    if additional:
        seen = {t.id for t in targets}
        for m in await parse_members(guild, additional):
            if m.id not in seen:
                targets.append(m)
                seen.add(m.id)
    return targets


async def collect_users(
    bot: commands.Bot,
    guild: discord.Guild,
    first: discord.User,
    additional: str | None,
) -> list[discord.User]:
    """Gộp target đầu + danh sách bổ sung, loại trùng."""
    targets = [first]
    if additional:
        seen = {t.id for t in targets}
        for u in await parse_users(bot, guild, additional):
            if u.id not in seen:
                targets.append(u)
                seen.add(u.id)
    return targets