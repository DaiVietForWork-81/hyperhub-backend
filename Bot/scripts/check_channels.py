import os
import requests
from dotenv import load_dotenv

load_dotenv(r"D:\Project\Bot\.env")
token = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
headers = {"Authorization": f"Bot {token}"}
guild_id = "1532265330079174697"

r = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers)
if r.status_code == 200:
    channels = r.json()
    for c in channels:
        if c.get("type") == 0:  # GUILD_TEXT
            print(f"{c['id']} | parent: {c.get('parent_id')} | {c['name'].encode('ascii', 'replace').decode('ascii')}")
        elif c.get("type") == 4:  # GUILD_CATEGORY
            print(f"[CATEGORY] {c['id']} | {c['name'].encode('ascii', 'replace').decode('ascii')}")
else:
    print(r.status_code, r.text)
