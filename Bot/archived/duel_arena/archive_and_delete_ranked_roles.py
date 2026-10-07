"""
archive_and_delete_ranked_roles.py
Sao lưu toàn diện 12 Ranked Role (thuộc tính, màu sắc, vị trí, danh sách thành viên đang giữ role)
vào file JSON trong archived/duel_arena/, sau đó xóa các role này trên máy chủ Discord.
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

BACKUP_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_FILE = os.path.join(BACKUP_DIR, "ranked_roles_backup.json")

RANKED_ROLE_IDS = [
    getattr(settings, f"{t}_RANKED_ROLE_ID", 0)
    for t in ["HT1", "MT1", "LT1", "HT2", "MT2", "LT2", "T3", "T4", "T5", "T6", "T7", "T8"]
]
RANKED_ROLE_IDS = [rid for rid in RANKED_ROLE_IDS if rid > 0]

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    try:
        print(f"[1/4] Bot đã đăng nhập: {client.user} ({client.user.id})", flush=True)
        if not client.guilds:
            print("[LỖI] Bot không thuộc máy chủ nào!", flush=True)
            await client.close()
            return

        guild = client.guilds[0]
        print(f"[2/4] Máy chủ: '{guild.name}' (ID: {guild.id})", flush=True)

        # Lọc danh sách các role Ranked theo ID hoặc tên kết thúc bằng '- Ranked'
        target_roles = []
        for r in guild.roles:
            if r.id in RANKED_ROLE_IDS or "- Ranked" in r.name:
                target_roles.append(r)

        # Sắp xếp theo vị trí từ dưới lên để an toàn
        target_roles.sort(key=lambda r: r.position)

        print(f"      Tìm thấy {len(target_roles)} Role Ranked cần sao lưu & xóa:", flush=True)
        for r in target_roles:
            print(f"       - [{r.id}] {r.name} (vị trí: {r.position}, màu: {r.color})", flush=True)

        # 1. Thu thập dữ liệu sao lưu
        roles_data = []
        for r in target_roles:
            member_ids = [m.id for m in r.members]
            roles_data.append({
                "id": r.id,
                "name": r.name,
                "color": r.color.value,
                "hoist": r.hoist,
                "position": r.position,
                "permissions": r.permissions.value,
                "mentionable": r.mentionable,
                "member_ids": member_ids,
            })

        backup_payload = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "roles": roles_data,
        }

        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(backup_payload, f, ensure_ascii=False, indent=2)

        print(f"[3/4] ĐÃ SAO LƯU THÀNH CÔNG: {BACKUP_FILE}", flush=True)

        # 2. Xóa các role trên Discord
        print(f"[4/4] BẮT ĐẦU XÓA {len(target_roles)} ROLE RANKED TRÊN DISCORD...", flush=True)
        deleted_count = 0
        for r in target_roles:
            r_name = r.name
            r_id = r.id
            try:
                await r.delete(reason="Lưu trữ và xóa role Ranked theo yêu cầu người dùng")
                print(f"      [XÓA THÀNH CÔNG] {r_name} (ID: {r_id})", flush=True)
                deleted_count += 1
                await asyncio.sleep(0.5)
            except Exception as de:
                print(f"      [LỖI XÓA] {r_name} (ID: {r_id}): {de}", flush=True)

        print("=" * 60, flush=True)
        print(f"HOÀN TẤT: Đã sao lưu và xóa thành công {deleted_count}/{len(target_roles)} Role Ranked!", flush=True)
        print("=" * 60, flush=True)

    except Exception as e:
        import traceback
        print(f"[LỖI XỬ LÝ]: {e}", flush=True)
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    if not settings.DISCORD_TOKEN:
        print("[LỖI] DISCORD_TOKEN chưa được thiết lập trong .env!", flush=True)
        sys.exit(1)
    asyncio.run(client.start(settings.DISCORD_TOKEN))
