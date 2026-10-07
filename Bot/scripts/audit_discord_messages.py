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

bot_msg_ids = []
user_msg_ids = []
missing_msg_ids = []

for r in rows:
    doc_id, title, file_name, author_name, author_id, channel_id, message_id, jump_url = r
    if not channel_id or not message_id:
        missing_msg_ids.append(doc_id)
        continue
    
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}"
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        author = data.get("author", {})
        if str(author.get("id")) == bot_id:
            bot_msg_ids.append((doc_id, channel_id, message_id))
        else:
            user_msg_ids.append((doc_id, channel_id, message_id, author.get("username")))
    else:
        missing_msg_ids.append(doc_id)

print(f"Total: {len(rows)}")
print(f"Bot messages (can be edited/patched): {len(bot_msg_ids)}")
print(f"User messages (need to be re-posted by bot): {len(user_msg_ids)}")
print(f"Missing messages: {len(missing_msg_ids)}")
if user_msg_ids:
    print(f"Sample user messages: {user_msg_ids[:5]}")
