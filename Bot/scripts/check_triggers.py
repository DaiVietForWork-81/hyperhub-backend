import sqlite3
conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
cur = conn.cursor()
cur.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name='documents_archive'")
for row in cur.fetchall():
    print(row[0])
conn.close()
