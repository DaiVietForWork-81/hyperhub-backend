import os
import sqlite3
import re

DB_PATH = r"D:\Project\Bot\data\bot.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

CHANNELS = {
    "toan": ("1535307480781955203", "📚・tài-liệu-toán"),
    "van": ("1535307379653218364", "📚・tài-liệu-văn"),
    "anh": ("1535307525782642739", "📚・tài-liệu-anh"),
    "ly": ("1535307619692970004", "📚・tài-liệu-lý"),
    "hoa": ("1535307566177984594", "📚・tài-liệu-hóa"),
    "sinh": ("1535307595563405373", "📚・tài-liệu-sinh"),
    "tin": ("1535307650907111615", "📚・tài-liệu-tin"),
    "ls-dl": ("1535307699594461265", "📚・tài-liệu-ls-đl"),
    "chuyen": ("1553415911451394149", "📚・tài-liệu-chuyên"),
    "dgnl": ("1539595811934044221", "📚・tài-liệu-dgnl-12"),
    "khac": ("1535307724408225852", "📚・tài-liệu-khác"),
}

cur.execute("""
    SELECT id, subject, title, file_name, file_size_bytes, estimated_level, author_name
    FROM documents_archive
    WHERE jump_url NOT LIKE '%discord.com%'
    ORDER BY id ASC
""")
rows = cur.fetchall()

def resolve_target_channel(doc_id, subject, title, file_name, author_name):
    combined = f"{title or ''} {file_name or ''} {author_name or ''}".lower()
    
    # 1. ĐGNL / ĐGTD
    if any(k in combined for k in ["đgnl", "dgnl", "đgtd", "dgtd", "đánh giá năng lực", "đánh giá tư duy", "tsa", "hsa"]):
        return "dgnl", "MATHEMATICS" if subject == "GENERAL" else subject
        
    # 2. Check author_name discord channel mentions
    if "tài-liệu-toán" in author_name or "tai-lieu-toan" in author_name:
        return "toan", "MATHEMATICS"
    if "tài-liệu-văn" in author_name or "tai-lieu-van" in author_name:
        return "van", "LITERATURE"
    if "tài-liệu-anh" in author_name or "tai-lieu-anh" in author_name or "tài liệu anh" in combined:
        return "anh", "ENGLISH"
    if "tài-liệu-sinh" in author_name:
        return "sinh", "BIOLOGY"
    if "tài-liệu-tin" in author_name:
        return "tin", "INFORMATICS"
    if "tài-liệu-lý" in author_name or "tai-lieu-ly" in author_name:
        return "ly", "PHYSICS"
    if "tài-liệu-hóa" in author_name or "tai-lieu-hoa" in author_name:
        return "hoa", "CHEMISTRY"
        
    # 3. Check subject
    if subject == "MATHEMATICS":
        return "toan", "MATHEMATICS"
    elif subject == "LITERATURE":
        return "van", "LITERATURE"
    elif subject == "ENGLISH":
        return "anh", "ENGLISH"
    elif subject == "PHYSICS":
        return "ly", "PHYSICS"
    elif subject == "CHEMISTRY":
        return "hoa", "CHEMISTRY"
    elif subject == "BIOLOGY":
        return "sinh", "BIOLOGY"
    elif subject == "INFORMATICS":
        return "tin", "INFORMATICS"
    elif subject in ("HISTORY", "GEOGRAPHY"):
        return "ls-dl", subject
        
    # 4. Check keywords in title/filename
    if any(k in combined for k in ["toán", "toan", "đại số", "hình học", "giải tích"]):
        return "toan", "MATHEMATICS"
    if any(k in combined for k in ["văn", "ngữ văn", "nlxh", "nghị luận", "đọc hiểu"]):
        return "van", "LITERATURE"
    if any(k in combined for k in ["tiếng anh", "english", "ielts", "toeic", "cloze", "idiom", "grammar", "vocabulary", "writing", "speaking"]):
        return "anh", "ENGLISH"
    if any(k in combined for k in ["vật lí", "vật lý", "vat li", "vat ly"]):
        return "ly", "PHYSICS"
    if any(k in combined for k in ["hóa học", "hoa hoc"]):
        return "hoa", "CHEMISTRY"
    if any(k in combined for k in ["sinh học", "sinh hoc"]):
        return "sinh", "BIOLOGY"
    if any(k in combined for k in ["tin học", "python", "pascal", "c++", "thuật toán"]):
        return "tin", "INFORMATICS"
    if any(k in combined for k in ["lịch sử", "địa lý", "địa lí"]):
        return "ls-dl", "HISTORY"

    return "khac", "GENERAL"

stats = {}
updated_subjects = {}
for r in rows:
    ch_key, new_sub = resolve_target_channel(r[0], r[1], r[2], r[3], r[6])
    stats[ch_key] = stats.get(ch_key, 0) + 1
    updated_subjects[new_sub] = updated_subjects.get(new_sub, 0) + 1

print("Channel distribution:")
for k, cnt in sorted(stats.items(), key=lambda x: -x[1]):
    cid, cname = CHANNELS[k]
    cname_safe = cname.encode('ascii', 'replace').decode('ascii')
    print(f"  {k:6} ({cname_safe}): {cnt} docs")

print("\nResolved Subject distribution:")
for k, cnt in sorted(updated_subjects.items(), key=lambda x: -x[1]):
    print(f"  {k:12}: {cnt} docs")

conn.close()
