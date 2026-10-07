import os
import sqlite3
import glob

DB_PATH = r"D:\Project\Bot\data\bot.db"
UPLOAD_DIR = r"D:\Project\Bot\storage\uploads"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
    SELECT id, subject, title, file_name, file_size_bytes, page_count, estimated_level, jump_url
    FROM documents_archive
    WHERE jump_url NOT LIKE '%discord.com%'
    ORDER BY id ASC
""")
rows = cur.fetchall()
print(f"Total documents to upload: {len(rows)}")

found_files = 0
missing_files = []
size_le_25mb = 0
size_gt_25mb = 0

for r in rows:
    doc_id, subject, title, file_name, size, pages, level, url = r
    # Check if exact file exists
    p1 = os.path.join(UPLOAD_DIR, file_name) if file_name else ""
    # Check if prefixed pattern exists e.g. {id}_*
    pattern = os.path.join(UPLOAD_DIR, f"{doc_id}_*")
    matches = glob.glob(pattern)
    
    file_path = None
    if p1 and os.path.exists(p1):
        file_path = p1
    elif matches:
        file_path = matches[0]
    
    if file_path:
        found_files += 1
        fsize = os.path.getsize(file_path)
        if fsize <= 25 * 1024 * 1024:
            size_le_25mb += 1
        else:
            size_gt_25mb += 1
    else:
        missing_files.append((doc_id, file_name))

print(f"Files found: {found_files}/{len(rows)}")
print(f"Size <= 25MB: {size_le_25mb}")
print(f"Size > 25MB: {size_gt_25mb}")
if missing_files:
    print(f"Missing files ({len(missing_files)}):", missing_files[:5])

# Distribution by subject
cur.execute("""
    SELECT subject, COUNT(*)
    FROM documents_archive
    WHERE jump_url NOT LIKE '%discord.com%'
    GROUP BY subject
    ORDER BY COUNT(*) DESC
""")
print("\nBy subject:")
for sub, cnt in cur.fetchall():
    print(f"  {sub}: {cnt}")

conn.close()
