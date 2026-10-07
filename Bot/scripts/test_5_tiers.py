import os
import sqlite3
import re

DB_PATH = r"D:\Project\Bot\data\bot.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    SELECT id, title, file_name, author_name
    FROM documents_archive
    WHERE jump_url NOT LIKE '%discord.com%'
    ORDER BY id ASC
""")
rows = cur.fetchall()

def classify_5_tiers(title, file_name, author_name):
    combined = f"{title or ''} {file_name or ''} {author_name or ''}".lower()
    
    # 1. Đề Quốc Tế (IMO, AMC, Kangaroo, IKMC, SASMO, TIMO, SAT, IELTS, TOEFL, Quốc tế...)
    if any(k in combined for k in [
        "quốc tế", "quoc te", "international", "amc", "ikmc", "kangaroo", 
        "sasmo", "timo", "hkimo", "asmo", "simoc", "ielts", "toefl", "sat", "act"
    ]):
        return "quoc_te", "Đề Quốc Tế", "Tham gia các kỳ thi chuẩn hóa hoặc kỳ thi học sinh giỏi quốc tế"
        
    # 2. Đề Chuyên (Trường chuyên, thi vào chuyên, Olympic, Chuyên Sư Phạm, Ams...)
    if any(k in combined for k in [
        "chuyên", "chuyen", "csp", "amsterdam", "khtn", "olympic", "olympiad", "gifted", "tst"
    ]):
        return "chuyen", "Đề Chuyên", "Cấp độ nâng cao: Trường THPT Chuyên, tuyển sinh Chuyên & Olympic"

    # 3. Đề HSG (Học sinh giỏi cấp trường/huyện/tỉnh/thành phố)
    if any(k in combined for k in [
        "hsg", "học sinh giỏi", "hoc sinh gioi", "bdhsg", "bồi dưỡng học sinh giỏi"
    ]):
        return "hsg", "Đề HSG", "Cấp độ trung gian: Thi học sinh giỏi các cấp (dễ hơn đề Chuyên)"

    # 4. Đề Chung (Tài liệu lý thuyết, đề cương ôn tập tổng hợp, sổ tay, kiến thức nền tảng, dễ gây hiểu lầm)
    if any(k in combined for k in [
        "sổ tay", "cẩm nang", "chiến lược", "từ viết đúng", "lấy gốc", "start up", "phong tỏa",
        "tổng hợp", "đề cương", "de cuong", "lý thuyết", "ly thuyet", "ngữ pháp", "từ vựng",
        "idiom", "cloze", "writing task", "speaking", "pronunciation", "trios", "dẫn chứng",
        "giáo án", "kế hoạch"
    ]):
        return "chung", "Đề Chung", "Tài liệu học tập / Đề cương tổng hợp / Lý thuyết chung"

    # 5. Đề Thường (Đại trà, thi tốt nghiệp THPT, thi học kỳ, kiểm tra định kỳ)
    return "thuong", "Đề Thường", "Đề thi đại trà / Phổ thông / Thi tốt nghiệp THPT chuẩn GD&ĐT"

counts = {}
for r in rows:
    t_key, t_label, t_desc = classify_5_tiers(r[1], r[2], r[3])
    counts[t_label] = counts.get(t_label, 0) + 1

print("5-Tier Distribution for 147 documents:")
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    k_safe = k.encode('ascii', 'replace').decode('ascii')
    print(f"  {k_safe:15}: {v} docs")

conn.close()
