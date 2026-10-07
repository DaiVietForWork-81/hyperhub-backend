import os
import sys
import glob
import time
import json
import sqlite3
import mimetypes
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv(r"D:\Project\Bot\.env")
token = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
if not token:
    print("ERROR: DISCORD_TOKEN not found in .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bot {token}",
}

DB_PATH = r"D:\Project\Bot\data\bot.db"
UPLOAD_DIR = r"D:\Project\Bot\storage\uploads"
GUILD_ID = "1532265330079174697"
CATEGORY_ID = "1534147951797080174"
INTAKE_CHANNEL_ID = "1535278288828633138"

CHANNELS = {
    "toan": ("1535307480781955203", "📚・tài-liệu-toán", "Toán Học"),
    "van": ("1535307379653218364", "📚・tài-liệu-văn", "Ngữ Văn"),
    "anh": ("1535307525782642739", "📚・tài-liệu-anh", "Tiếng Anh"),
    "ly": ("1535307619692970004", "📚・tài-liệu-lý", "Vật Lý"),
    "hoa": ("1535307566177984594", "📚・tài-liệu-hóa", "Hóa Học"),
    "sinh": ("1535307595563405373", "📚・tài-liệu-sinh", "Sinh Học"),
    "tin": ("1535307650907111615", "📚・tài-liệu-tin", "Tin Học"),
    "ls-dl": ("1535307699594461265", "📚・tài-liệu-ls-đl", "Lịch Sử - Địa Lý"),
    "chuyen": ("1553415911451394149", "📚・tài-liệu-chuyên", "Chuyên / Olympic"),
    "dgnl": ("1539595811934044221", "📚・tài-liệu-dgnl-12", "ĐGNL / ĐGTD"),
    "khac": ("1535307724408225852", "📚・tài-liệu-khác", "Tài Liệu Khác"),
}

def resolve_channel_and_subject(doc_id, subject, title, file_name, author_name):
    combined = f"{title or ''} {file_name or ''} {author_name or ''}".lower()

    if any(k in combined for k in ["đgnl", "dgnl", "đgtd", "dgtd", "đánh giá năng lực", "đánh giá tư duy", "tsa", "hsa"]):
        return "dgnl", "MATHEMATICS" if subject == "GENERAL" else subject

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

def classify_5_tiers(title, file_name, author_name):
    combined = f"{title or ''} {file_name or ''} {author_name or ''}".lower()

    if any(k in combined for k in [
        "quốc tế", "quoc te", "international", "amc", "ikmc", "kangaroo",
        "sasmo", "timo", "hkimo", "asmo", "simoc", "ielts", "toefl", "sat", "act"
    ]):
        return "quoc_te", "Đề Quốc Tế", "Kỳ thi chuẩn hóa hoặc Olympic quốc tế", "8.5"

    if any(k in combined for k in [
        "chuyên", "chuyen", "csp", "amsterdam", "khtn", "olympic", "olympiad", "gifted", "tst"
    ]):
        return "chuyen", "Đề Chuyên", "THPT Chuyên, tuyển sinh Chuyên & Olympic (độ khó cao nhất)", "9.0"

    if any(k in combined for k in [
        "hsg", "học sinh giỏi", "hoc sinh gioi", "bdhsg", "bồi dưỡng học sinh giỏi"
    ]):
        return "hsg", "Đề HSG", "Thi Học sinh giỏi các cấp (thường < hsg < chuyên)", "7.8"

    if any(k in combined for k in [
        "sổ tay", "cẩm nang", "chiến lược", "từ viết đúng", "lấy gốc", "start up", "phong tỏa",
        "tổng hợp", "đề cương", "de cuong", "lý thuyết", "ly thuyet", "ngữ pháp", "từ vựng",
        "idiom", "cloze", "writing task", "speaking", "pronunciation", "trios", "dẫn chứng",
        "giáo án", "kế hoạch"
    ]):
        return "chung", "Đề Chung", "Tài liệu lý thuyết / Đề cương tổng hợp", "5.5"

    return "thuong", "Đề Thường", "Đại trà / Thi tốt nghiệp THPT chuẩn Bộ GD&ĐT (độ khó thấp nhất)", "6.5"

def format_size(bytes_val):
    if not bytes_val:
        return "0 B"
    if bytes_val < 1024:
        return f"{bytes_val} B"
    if bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    return f"{bytes_val / (1024 * 1024):.1f} MB"

def find_file_path(doc_id, file_name):
    p1 = os.path.join(UPLOAD_DIR, file_name) if file_name else ""
    if p1 and os.path.exists(p1):
        return p1
    pattern = os.path.join(UPLOAD_DIR, f"{doc_id}_*")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    return None

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, subject, title, file_name, file_size_bytes, estimated_level,
               question_count, page_count, author_name, author_id
        FROM documents_archive
        WHERE jump_url NOT LIKE '%discord.com%'
        ORDER BY id ASC
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"==================================================")
    print(f"HYPERHUB BULK UPLOAD TO DISCORD: {total} DOCUMENTS")
    print(f"==================================================")

    success_count = 0
    fail_count = 0

    for idx, row in enumerate(rows, start=1):
        doc_id, subject, title, file_name, size, level, questions, pages, author_name, author_id = row

        file_path = find_file_path(doc_id, file_name)
        if not file_path:
            print(f"[{idx}/{total}] SKIP ID {doc_id}: File not found on disk")
            fail_count += 1
            continue

        actual_size = os.path.getsize(file_path)
        ch_key, resolved_sub = resolve_channel_and_subject(doc_id, subject, title, file_name, author_name)
        target_ch_id, target_ch_name, target_sub_vi = CHANNELS[ch_key]
        tier_key, tier_label, tier_desc, diff_score = classify_5_tiers(title, file_name, author_name)

        author_display = author_name
        if author_id and author_id > 0:
            author_display = f"<@{author_id}> (`{author_name}`)"

        # Soạn tin nhắn chuẩn HyperHub
        post_content = (
            f"📁 **[TÀI LIỆU ĐÃ PHÂN LOẠI | THƯ MỤC `{CATEGORY_ID}`]**\n"
            f"*(Chuyển tiếp tự động từ Kênh Nộp Tài Liệu: <#{INTAKE_CHANNEL_ID}>)*\n"
            f"👤 **Người đóng góp:** {author_display}\n"
            f"• Tệp / Link: `{file_name}`\n"
            f"• Môn học: **{target_sub_vi}**\n"
            f"• Khối lớp: **{level or 'Chung / Chưa rõ lớp'}**\n"
            f"• Thể loại: **{tier_label}** ({tier_desc})\n"
            f"• Độ khó: **{diff_score}/10**\n"
            f"• Cấu trúc: `{pages or 1} trang` | `{format_size(actual_size)}`\n"
            f"• Trạng thái kiểm định: **Đã lưu trữ an toàn trong HyperHub Vault ✅**"
        )

        url = f"https://discord.com/api/v10/channels/{target_ch_id}/messages"
        posted_msg = None

        # Gửi kèm tệp nếu <= 25MB (26,214,400 bytes)
        max_upload_size = 25 * 1024 * 1024
        if actual_size <= max_upload_size:
            clean_fn = os.path.basename(file_path)
            # Remove any id prefix if present e.g. 100_
            if clean_fn.startswith(f"{doc_id}_"):
                clean_fn = clean_fn[len(str(doc_id)) + 1:]
            if not clean_fn:
                clean_fn = file_name or "de_thi.pdf"

            mime_type, _ = mimetypes.guess_type(clean_fn)
            mime_type = mime_type or "application/octet-stream"

            for retry in range(4):
                try:
                    with open(file_path, "rb") as fp:
                        files = {
                            "files[0]": (clean_fn, fp, mime_type),
                        }
                        data = {
                            "payload_json": json.dumps({"content": post_content}),
                        }
                        resp = requests.post(url, headers=HEADERS, data=data, files=files, timeout=60)
                except Exception as ex:
                    print(f"[{idx}/{total}] ID {doc_id} Request error: {ex}, retrying...")
                    time.sleep(2)
                    continue

                if resp.status_code in (200, 201):
                    posted_msg = resp.json()
                    break
                elif resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 2.0)
                    print(f"[{idx}/{total}] Rate limited! Sleeping {retry_after + 0.5:.1f}s...")
                    time.sleep(float(retry_after) + 0.5)
                elif resp.status_code == 413:
                    # File slightly over Discord payload boundary -> fallback text-only post
                    print(f"[{idx}/{total}] ID {doc_id} HTTP 413 payload too large, posting metadata with Vault link...")
                    break
                else:
                    print(f"[{idx}/{total}] ID {doc_id} Discord error {resp.status_code}: {resp.text[:100]}")
                    break

        # Nếu file > 25MB hoặc bị 413: Gửi tin nhắn Embed/Text kèm chú thích tải từ Web Portal
        if not posted_msg:
            post_content_large = (
                post_content + "\n"
                f"⚠️ *(Tệp `{file_name}` dung lượng {format_size(actual_size)} (> 25MB). Tệp đã được lưu trữ an toàn trên máy chủ HyperHub và có thể tải trực tiếp trên Web Portal hoặc qua lệnh /tim_de)*"
            )
            for retry in range(4):
                resp = requests.post(
                    url,
                    headers={**HEADERS, "Content-Type": "application/json"},
                    json={"content": post_content_large},
                    timeout=30,
                )
                if resp.status_code in (200, 201):
                    posted_msg = resp.json()
                    break
                elif resp.status_code == 429:
                    retry_after = resp.json().get("retry_after", 2.0)
                    time.sleep(float(retry_after) + 0.5)
                else:
                    break

        if posted_msg:
            msg_id = posted_msg["id"]
            channel_id = posted_msg["channel_id"]
            jump_url = f"https://discord.com/channels/{GUILD_ID}/{channel_id}/{msg_id}"

            # Cập nhật SQLite ngay lập tức
            cur.execute("""
                UPDATE documents_archive
                SET channel_id = ?, message_id = ?, jump_url = ?, subject = ?
                WHERE id = ?
            """, (int(channel_id), int(msg_id), jump_url, resolved_sub, doc_id))
            conn.commit()

            success_count += 1
            safe_text = f"[{idx}/{total}] OK ID {doc_id} -> #{target_ch_name} ({tier_label}) | msg_id={msg_id}"
            try:
                print(safe_text)
            except Exception:
                print(safe_text.encode("ascii", "replace").decode("ascii"))
        else:
            fail_count += 1
            safe_err = f"[{idx}/{total}] FAILED ID {doc_id} ({file_name[:30]})"
            try:
                print(safe_err)
            except Exception:
                print(safe_err.encode("ascii", "replace").decode("ascii"))

        # Giữ nhịp độ an toàn để không bị Discord rate limit (1.2s/msg)
        time.sleep(1.2)

    conn.close()
    print("==================================================")
    print(f"COMPLETED BULK UPLOAD: {success_count}/{total} SUCCESS, {fail_count} FAILED")
    print("==================================================")

if __name__ == "__main__":
    main()
