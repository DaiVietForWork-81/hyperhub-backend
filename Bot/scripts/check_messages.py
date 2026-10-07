import sqlite3
import requests
import os
import sys
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(r"D:\Project\Bot\.env")
token = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
headers = {"Authorization": f"Bot {token}"}

conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
c = conn.cursor()

c.execute("SELECT id, file_name, author_name, channel_id, message_id FROM documents_archive WHERE author_name LIKE '%tung1581%' LIMIT 1")
row = c.fetchone()
print("Tung1581 row:", row)
r = requests.get(f"https://discord.com/api/v10/channels/{row[3]}/messages/{row[4]}", headers=headers)
print("Discord author:", r.json().get("author"))

c.execute("SELECT id, file_name, author_name, channel_id, message_id FROM documents_archive WHERE author_name LIKE '%Tài Liệu Anh%' LIMIT 1")
row = c.fetchone()
print("\nTai Lieu Anh row:", row)
r = requests.get(f"https://discord.com/api/v10/channels/{row[3]}/messages/{row[4]}", headers=headers)
print("Discord author:", r.json().get("author"))
print("Discord content:", r.json().get("content")[:100] if r.json().get("content") else "")
