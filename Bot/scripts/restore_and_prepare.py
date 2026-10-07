import sqlite3
import os
import glob
import sys
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(r"D:\Project\Bot\.env")
token = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
headers = {"Authorization": f"Bot {token}"}

conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
c = conn.cursor()

upload_dir = r"D:\Project\Bot\storage\uploads"
os.makedirs(upload_dir, exist_ok=True)

c.execute("SELECT id, file_name, channel_id, message_id FROM documents_archive ORDER BY id ASC")
rows = c.fetchall()

restored = 0
already_present = 0
cannot_restore = 0

for r in rows:
    doc_id, file_name, channel_id, message_id = r
    
    # Check if already on disk
    p1 = os.path.join(upload_dir, file_name) if file_name else ""
    matches = glob.glob(os.path.join(upload_dir, f"{doc_id}_*"))
    if (p1 and os.path.exists(p1)) or matches:
        already_present += 1
        continue
    
    # Try restore from Discord
    if channel_id and message_id:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            atts = data.get("attachments", [])
            if atts:
                att_url = atts[0]["url"]
                dl_resp = requests.get(att_url, timeout=30)
                if dl_resp.status_code == 200:
                    dest = os.path.join(upload_dir, f"{doc_id}_{file_name or atts[0]['filename']}")
                    with open(dest, "wb") as f:
                        f.write(dl_resp.content)
                    print(f"Restored ID {doc_id}: {file_name} ({len(dl_resp.content)} bytes)")
                    restored += 1
                    continue
    
    cannot_restore += 1
    print(f"Could not restore ID {doc_id}: {file_name}")

print(f"\nSummary:")
print(f"Already present: {already_present}")
print(f"Restored from Discord: {restored}")
print(f"Cannot restore: {cannot_restore}")
print(f"Total available now: {already_present + restored} / {len(rows)}")
