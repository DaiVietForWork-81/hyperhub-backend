"""
restore_category_channels.py
Khôi phục lại toàn bộ danh mục và các kênh từ file sao lưu JSON (category_1534147796461162697_backup.json).
"""

import asyncio
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_DIR)

import discord
from config.settings import settings

CATEGORY_ID = 1534147796461162697
BACKUP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_FILE = os.path.join(BACKUP_DIR, f"category_{CATEGORY_ID}_backup.json")

intents = discord.Intents.default()
intents.guilds = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"[1/3] Bot kết nối thành công: {client.user}", flush=True)

    if not os.path.exists(BACKUP_FILE):
        print(f"[LỖI] Không tìm thấy tệp sao lưu: {BACKUP_FILE}", flush=True)
        await client.close()
        return

    with open(BACKUP_FILE, "r", encoding="utf-8") as f:
        backup = json.load(f)

    guild_id = backup.get("guild_id")
    guild = client.get_guild(guild_id)
    if not guild and client.guilds:
        guild = client.guilds[0]

    if not guild:
        print(f"[LỖI] Không tìm thấy máy chủ Discord ID {guild_id}", flush=True)
        await client.close()
        return

    print(f"[2/3] Máy chủ: '{guild.name}' (ID: {guild.id})", flush=True)

    # 1. Tìm hoặc tạo lại Category
    cat_name = backup.get("category_name", "・━━ ❓GIẢI ĐỀ/CÂU HỎI ━━・")
    cat = client.get_channel(CATEGORY_ID)
    if not cat:
        for c in guild.categories:
            if c.name == cat_name or c.id == CATEGORY_ID:
                cat = c
                break

    if not cat:
        print(f"      Tạo lại danh mục: {cat_name}...", flush=True)
        cat = await guild.create_category(
            name=cat_name,
            position=backup.get("category_position", 4),
            reason="Khôi phục danh mục từ bản sao lưu",
        )
        print(f"      Đã tạo danh mục mới: {cat.name} (ID mới: {cat.id})", flush=True)
    else:
        print(f"      Danh mục đã tồn tại: {cat.name} (ID: {cat.id})", flush=True)

    # 2. Tạo lại từng kênh
    print(f"[3/3] Đang khôi phục {len(backup.get('channels', []))} kênh...", flush=True)
    created_count = 0
    for ch_data in backup.get("channels", []):
        ch_name = ch_data.get("name")
        # Kiểm tra nếu kênh đã tồn tại
        existing = discord.utils.get(cat.channels, name=ch_name)
        if existing:
            print(f"      [BỎ QUA] Kênh '{ch_name}' đã tồn tại (ID: {existing.id})", flush=True)
            continue

        # Xây dựng overwrites
        overwrites = {}
        for ow in ch_data.get("overwrites", []):
            target = None
            if ow.get("target_type") == "role":
                target = guild.get_role(ow.get("target_id"))
            elif ow.get("target_type") == "member":
                target = guild.get_member(ow.get("target_id"))

            if target:
                allow_perm = discord.Permissions(ow.get("allow", 0))
                deny_perm = discord.Permissions(ow.get("deny", 0))
                overwrites[target] = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)

        try:
            new_ch = await guild.create_text_channel(
                name=ch_name,
                category=cat,
                topic=ch_data.get("topic"),
                slowmode_delay=ch_data.get("slowmode_delay", 0),
                nsfw=ch_data.get("nsfw", False),
                overwrites=overwrites,
                reason="Khôi phục kênh từ bản sao lưu",
            )
            print(f"      [ĐÃ TẠO] {new_ch.name} (ID mới: {new_ch.id})", flush=True)
            created_count += 1
            await asyncio.sleep(0.5)
        except Exception as ce:
            print(f"      [LỖI TẠO] {ch_name}: {ce}", flush=True)

    print("=" * 60, flush=True)
    print(f"HOÀN TẤT KHÔI PHỤC: {created_count} kênh đã được tạo lại!", flush=True)
    print("=" * 60, flush=True)
    await client.close()


if __name__ == "__main__":
    if not settings.DISCORD_TOKEN:
        print("[LỖI] DISCORD_TOKEN chưa được thiết lập trong .env!", flush=True)
        sys.exit(1)
    asyncio.run(client.start(settings.DISCORD_TOKEN))
