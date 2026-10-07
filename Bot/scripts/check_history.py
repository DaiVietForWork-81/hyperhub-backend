import sqlite3

conn = sqlite3.connect(r"D:\Project\Bot\data\bot.db")
cur = conn.cursor()
cur.execute("SELECT title, subject, channel_id FROM documents_archive WHERE jump_url LIKE '%discord.com%'")
ch_map = {
    1535307480781955203: "toan",
    1535307379653218364: "van",
    1535307525782642739: "anh",
    1535307619692970004: "ly",
    1535307566177984594: "hoa",
    1535307595563405373: "sinh",
    1535307650907111615: "tin",
    1535307699594461265: "ls-dl",
    1553415911451394149: "chuyen",
    1539595811934044221: "dgnl",
    1535307724408225852: "khac",
}
for r in cur.fetchall():
    ch = ch_map.get(r[2], str(r[2]))
    t = r[0].encode("ascii", "replace").decode("ascii")[:45]
    print(f"{ch:7} | {r[1]:12} | {t}")
