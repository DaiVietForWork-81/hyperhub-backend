import requests
import os
import sys
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(r"D:\Project\Bot\.env")
token = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
headers = {"Authorization": f"Bot {token}"}
guild_id = "1532265330079174697"

r = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers)
if r.status_code == 200:
    roles = r.json()
    roles.sort(key=lambda x: x.get("position", 0), reverse=True)
    print(f"Total roles: {len(roles)}")
    for idx, role in enumerate(roles, 1):
        color_hex = f"#{role.get('color', 0):06X}" if role.get("color") else "Mặc định"
        hoist = "[Hiển thị riêng]" if role.get("hoist") else ""
        managed = "[Tích hợp/Bot]" if role.get("managed") else ""
        print(f"{idx:2d}. {role['name']} | ID: {role['id']} | Màu: {color_hex} {hoist} {managed}".strip())
else:
    print(f"Lỗi: {r.status_code} - {r.text}")
