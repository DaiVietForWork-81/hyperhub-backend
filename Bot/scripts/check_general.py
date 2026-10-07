import sqlite3

conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
cur = conn.cursor()

cur.execute("""
    SELECT id, title, file_name, estimated_level
    FROM documents_archive
    WHERE subject = 'GENERAL' AND jump_url NOT LIKE '%discord.com%'
    ORDER BY id ASC
""")

rows = cur.fetchall()
with open("general_docs.txt", "w", encoding="utf-8") as f:
    for r in rows:
        f.write(f"ID {r[0]}: Title='{r[1]}' | File='{r[2]}' | Level='{r[3]}'\n")

print(f"Wrote {len(rows)} lines to general_docs.txt")
