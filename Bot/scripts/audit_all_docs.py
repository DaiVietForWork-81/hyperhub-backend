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
bot_id = "1536298634990325871"

conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
c = conn.cursor()

c.execute("SELECT id, title, file_name, author_name, author_id, channel_id, message_id, jump_url FROM documents_archive ORDER BY id ASC")
rows = c.fetchall()

upload_dir = r"D:\Project\Bot\storage\uploads"

bot_msg_count = 0
other_msg_count = 0
not_found_on_discord = 0
files_found_on_disk = 0
files_missing_on_disk = 0

for r in rows:
    doc_id, title, file_name, author_name, author_id, channel_id, message_id, jump_url = r
    
    # Check disk
    p1 = os.path.join(upload_dir, file_name) if file_name else ""
    pattern = os.path.join(upload_dir, f"{doc_id}_*")
    matches = glob.glob(pattern)
    on_disk = (p1 and os.path.exists(p1)) or len(matches) > 0
    if on_disk:
        files_found_on_disk += 1
    else:
        files_missing_on_disk += 1

print(f"Total rows in DB: {len(rows)}")
print(f"Files found on disk: {files_found_on_disk}, Missing on disk: {files_missing_on_disk}")
