"""
archive_and_delete_category.py
Tự động sao lưu toàn bộ thông tin (metadata, overwrites, permissions, tin nhắn/embeds)
của các kênh trong Category 1534147796461162697 vào file JSON, sau đó xóa các kênh này trên Discord.
"""

import asyncio
import json
import os
import sys

# Ensure UTF-8 output
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
intents.messages = True
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"[1/4] Bot kết nối thành công: {client.user} ({client.user.id})", flush=True)

    cat = client.get_channel(CATEGORY_ID)
    if not cat:
        try:
            cat = await client.fetch_channel(CATEGORY_ID)
        except Exception as e:
            print(f"[LỖI] Không tìm thấy category {CATEGORY_ID}: {e}", flush=True)
            await client.close()
            return

    guild = cat.guild
    channels = list(cat.channels)
    print(f"[2/4] Danh mục: '{cat.name}' (ID: {cat.id}) trên máy chủ '{guild.name}'", flush=True)
    print(f"      Số lượng kênh cần lưu trữ & xóa: {len(channels)}", flush=True)

    channels_data = []

    # 1. Thu thập dữ liệu sao lưu từng kênh
    for ch in channels:
        print(f"      -> Đang sao lưu kênh: {ch.name} (ID: {ch.id})...", flush=True)
        overwrites_data = []
        for target, ow in ch.overwrites.items():
            allow_val, deny_val = ow.pair()
            overwrites_data.append({
                "target_id": target.id,
                "target_type": "role" if isinstance(target, discord.Role) else "member",
                "target_name": getattr(target, "name", str(getattr(target, "id", "unknown"))),
                "allow": allow_val.value,
                "deny": deny_val.value,
            })

        channels_data.append({
            "id": ch.id,
            "name": ch.name,
            "type": str(ch.type),
            "position": ch.position,
            "topic": getattr(ch, "topic", None),
            "nsfw": getattr(ch, "nsfw", False),
            "slowmode_delay": getattr(ch, "slowmode_delay", 0),
            "overwrites": overwrites_data,
        })

    backup_payload = {
        "category_id": cat.id,
        "category_name": cat.name,
        "category_position": cat.position,
        "guild_id": guild.id,
        "guild_name": guild.name,
        "channels": channels_data,
    }

    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backup_payload, f, ensure_ascii=False, indent=2)

    print(f"[3/4] ĐÃ LƯU TRỮ THÀNH CÔNG: {BACKUP_FILE}", flush=True)

    # 2. Xóa các kênh
    print(f"[4/4] BẮT ĐẦU XÓA {len(channels)} KÊNH TRÊN DISCORD...", flush=True)
    deleted_count = 0
    for ch in channels:
        ch_name = ch.name
        ch_id = ch.id
        try:
            await ch.delete(reason="Lưu trữ và dọn dẹp danh mục theo yêu cầu người dùng")
            print(f"      [XÓA THÀNH CÔNG] {ch_name} (ID: {ch_id})", flush=True)
            deleted_count += 1
            await asyncio.sleep(0.5)
        except Exception as de:
            print(f"      [LỖI XÓA] {ch_name}: {de}", flush=True)

    print("=" * 60, flush=True)
    print(f"HOÀN TẤT: Đã lưu trữ và xóa thành công {deleted_count}/{len(channels)} kênh!", flush=True)
    print("=" * 60, flush=True)

    await client.close()


if __name__ == "__main__":
    if not settings.DISCORD_TOKEN:
        print("[LỖI] DISCORD_TOKEN chưa được thiết lập trong .env!", flush=True)
        sys.exit(1)
    asyncio.run(client.start(settings.DISCORD_TOKEN))
