import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM documents_archive")
total = c.fetchone()[0]

c.execute("SELECT COUNT(*) FROM documents_archive WHERE jump_url LIKE '%discord.com%'")
discord_cnt = c.fetchone()[0]

c.execute("SELECT DISTINCT author_name, author_id, COUNT(*) FROM documents_archive GROUP BY author_name, author_id")
authors = c.fetchall()

print(f"Total documents: {total}")
print(f"Already have discord.com jump_url: {discord_cnt}")
print(f"Authors:")
for a in authors:
    print(f"  {a[0]} (ID: {a[1]}): {a[2]} docs")

c.execute("SELECT id, title, channel_id, message_id, jump_url, author_name FROM documents_archive LIMIT 5")
print("\nSample docs:")
for row in c.fetchall():
    print(row)
