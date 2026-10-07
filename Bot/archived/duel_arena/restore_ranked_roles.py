"""
restore_ranked_roles.py
Khôi phục lại toàn bộ 12 Role Ranked từ file JSON sao lưu (ranked_roles_backup.json)
kèm màu sắc, quyền hạn và tự động gán lại cho các thành viên từng sở hữu role.
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

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    try:
        print(f"[1/3] Bot đã đăng nhập: {client.user}", flush=True)

        if not os.path.exists(BACKUP_FILE):
            print(f"[LỖI] Không tìm thấy file sao lưu: {BACKUP_FILE}", flush=True)
            await client.close()
            return

        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            backup = json.load(f)

        guild_id = backup.get("guild_id")
        guild = client.get_guild(guild_id)
        if not guild and client.guilds:
            guild = client.guilds[0]

        if not guild:
            print(f"[LỖI] Không tìm thấy máy chủ ID {guild_id}", flush=True)
            await client.close()
            return

        print(f"[2/3] Máy chủ: '{guild.name}' (ID: {guild.id})", flush=True)
        print(f"[3/3] Đang khôi phục {len(backup.get('roles', []))} Role Ranked...", flush=True)

        created_roles = {}
        for r_data in backup.get("roles", []):
            r_name = r_data.get("name")
            existing = discord.utils.get(guild.roles, name=r_name)
            if existing:
                print(f"      [ĐÃ CÓ] Role '{r_name}' đã tồn tại (ID: {existing.id})", flush=True)
                new_role = existing
            else:
                new_role = await guild.create_role(
                    name=r_name,
                    color=discord.Color(r_data.get("color", 0)),
                    hoist=r_data.get("hoist", False),
                    permissions=discord.Permissions(r_data.get("permissions", 0)),
                    mentionable=r_data.get("mentionable", False),
                    reason="Khôi phục Role Ranked từ file sao lưu",
                )
                print(f"      [ĐÃ TẠO] {new_role.name} (ID mới: {new_role.id})", flush=True)
                await asyncio.sleep(0.5)

            created_roles[r_data.get("id")] = new_role.id

            # Gán lại role cho các thành viên cũ
            for mid in r_data.get("member_ids", []):
                member = guild.get_member(mid)
                if member:
                    try:
                        await member.add_roles(new_role, reason="Khôi phục role Ranked")
                    except Exception:
                        pass

        print("=" * 60, flush=True)
        print("HOÀN TẤT KHÔI PHỤC ROLE RANKED!", flush=True)
        print("Bảng ID Role mới được tạo:")
        for old_id, new_id in created_roles.items():
            print(f"  Old ID: {old_id} -> New ID: {new_id}")
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
