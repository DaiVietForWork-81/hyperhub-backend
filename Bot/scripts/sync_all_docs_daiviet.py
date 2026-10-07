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
BOT_ID = "1536298634990325871"
DAI_VIET_ID = 1529864608813416449
DAI_VIET_NAME = "Dai VIET"

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

def resolve_channel_and_subject(doc_id, subject, title, file_name):
    combined = f"{title or ''} {file_name or ''}".lower()

    if any(k in combined for k in ["đgnl", "dgnl", "đgtd", "dgtd", "đánh giá năng lực", "đánh giá tư duy", "tsa", "hsa"]):
        return "dgnl", "MATHEMATICS" if subject == "GENERAL" else subject

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
    if any(k in combined for k in ["tiếng anh", "english", "ielts", "toeic", "cloze", "idiom", "grammar", "vocabulary", "writing", "speaking", "part"]):
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

def classify_5_tiers(title, file_name):
    combined = f"{title or ''} {file_name or ''}".lower()

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
        return "hsg", "Đề HSG", "Thi Học sinh giỏi các cấp", "7.8"

    if any(k in combined for k in [
        "sổ tay", "cẩm nang", "chiến lược", "từ viết đúng", "lấy gốc", "start up", "phong tỏa",
        "tổng hợp", "đề cương", "de cuong", "lý thuyết", "ly thuyet", "ngữ pháp", "từ vựng",
        "idiom", "cloze", "writing task", "speaking", "pronunciation", "trios", "dẫn chứng",
        "giáo án", "kế hoạch"
    ]):
        return "chung", "Đề Chung", "Tài liệu lý thuyết / Đề cương tổng hợp", "5.5"

    return "thuong", "Đề Thường", "Đại trà / Thi tốt nghiệp THPT chuẩn Bộ GD&ĐT", "6.5"

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

def build_post_content(file_name, target_sub_vi, level, tier_label, tier_desc, diff_score, pages, actual_size):
    return (
        f"📁 **[TÀI LIỆU ĐÃ PHÂN LOẠI | THƯ MỤC `{CATEGORY_ID}`]**\n"
        f"*(Chuyển tiếp tự động từ Kênh Nộp Tài Liệu: <#{INTAKE_CHANNEL_ID}>)*\n"
        f"👤 **Người đóng góp:** <@{DAI_VIET_ID}> (`{DAI_VIET_NAME}`)\n"
        f"• Tệp / Link: `{file_name}`\n"
        f"• Môn học: **{target_sub_vi}**\n"
        f"• Khối lớp: **{level or 'Chung / Chưa rõ lớp'}**\n"
        f"• Thể loại: **{tier_label}** ({tier_desc})\n"
        f"• Độ khó: **{diff_score}/10**\n"
        f"• Cấu trúc: `{pages or 1} trang` | `{format_size(actual_size)}`\n"
        f"• Trạng thái kiểm định: **Đã lưu trữ an toàn trong HyperHub Vault ✅**"
    )

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Đồng bộ tác giả thành Dai VIET trong DB
    print("[1/3] Cập nhật tác giả toàn bộ tài liệu thành 'Dai VIET' trong Database...")
    cur.execute("""
        UPDATE documents_archive
        SET author_name = ?, author_id = ?
    """, (DAI_VIET_NAME, DAI_VIET_ID))
    conn.commit()
    print(" -> Đã cập nhật tác giả 100% trong Database.")

    # 2. Truy vấn danh sách toàn bộ 176 tài liệu
    cur.execute("""
        SELECT id, subject, title, file_name, file_size_bytes, estimated_level,
               question_count, page_count, channel_id, message_id
        FROM documents_archive
        ORDER BY id ASC
    """)
    rows = cur.fetchall()
    total = len(rows)

    print(f"\n[2/3] Bắt đầu đồng bộ và tải lên Discord cho {total} tài liệu...")
    print("=" * 60)

    patched_count = 0
    uploaded_count = 0
    error_count = 0

    for idx, row in enumerate(rows, start=1):
        doc_id, subject, title, file_name, size, level, questions, pages, old_ch_id, old_msg_id = row

        file_path = find_file_path(doc_id, file_name)
        if not file_path:
            print(f"[{idx}/{total}] CẢNH BÁO: Không tìm thấy tệp ID {doc_id} trên đĩa!")
            error_count += 1
            continue

        actual_size = os.path.getsize(file_path)
        ch_key, resolved_sub = resolve_channel_and_subject(doc_id, subject, title, file_name)
        target_ch_id, target_ch_name, target_sub_vi = CHANNELS[ch_key]
        tier_key, tier_label, tier_desc, diff_score = classify_5_tiers(title, file_name)

        post_content = build_post_content(
            file_name=file_name,
            target_sub_vi=target_sub_vi,
            level=level,
            tier_label=tier_label,
            tier_desc=tier_desc,
            diff_score=diff_score,
            pages=pages,
            actual_size=actual_size,
        )

        # Kiểm tra xem tin nhắn cũ có tồn tại trên Discord và do Bot đăng không
        is_bot_msg = False
        if old_ch_id and old_msg_id:
            check_url = f"https://discord.com/api/v10/channels/{old_ch_id}/messages/{old_msg_id}"
            try:
                c_resp = requests.get(check_url, headers=HEADERS, timeout=10)
                if c_resp.status_code == 200:
                    msg_data = c_resp.json()
                    author_id_str = str(msg_data.get("author", {}).get("id"))
                    if author_id_str == BOT_ID:
                        is_bot_msg = True
            except Exception:
                pass

        # Trường hợp 1: Tin nhắn do Bot đăng -> Cập nhật nội dung (PATCH)
        if is_bot_msg:
            patch_url = f"https://discord.com/api/v10/channels/{old_ch_id}/messages/{old_msg_id}"
            for retry in range(4):
                try:
                    p_resp = requests.patch(
                        patch_url,
                        headers={**HEADERS, "Content-Type": "application/json"},
                        json={"content": post_content},
                        timeout=15,
                    )
                    if p_resp.status_code == 200:
                        patched_count += 1
                        jump_url = f"https://discord.com/channels/{GUILD_ID}/{old_ch_id}/{old_msg_id}"
                        cur.execute("""
                            UPDATE documents_archive
                            SET subject = ?, jump_url = ?
                            WHERE id = ?
                        """, (resolved_sub, jump_url, doc_id))
                        conn.commit()
                        print(f"[{idx}/{total}] ✅ PATCHED ID {doc_id} -> #{target_ch_name} (Tác giả: Dai VIET)")
                        break
                    elif p_resp.status_code == 429:
                        r_after = p_resp.json().get("retry_after", 2.0)
                        time.sleep(float(r_after) + 0.5)
                    else:
                        print(f"[{idx}/{total}] PATCH lỗi {p_resp.status_code}, sẽ gửi mới...")
                        is_bot_msg = False
                        break
                except Exception as ex:
                    time.sleep(1.5)
            if is_bot_msg:
                time.sleep(0.8)
                continue

        # Trường hợp 2: Tin nhắn chưa có, bị xóa, hoặc do user khác gửi -> Tải lên mới kèm tệp
        clean_fn = os.path.basename(file_path)
        if clean_fn.startswith(f"{doc_id}_"):
            clean_fn = clean_fn[len(str(doc_id)) + 1:]
        if not clean_fn:
            clean_fn = file_name or "tai_lieu.pdf"

        mime_type, _ = mimetypes.guess_type(clean_fn)
        mime_type = mime_type or "application/octet-stream"

        upload_url = f"https://discord.com/api/v10/channels/{target_ch_id}/messages"
        posted_msg = None

        if actual_size <= 25 * 1024 * 1024:
            for retry in range(4):
                try:
                    with open(file_path, "rb") as fp:
                        files = {
                            "files[0]": (clean_fn, fp, mime_type),
                        }
                        data = {
                            "payload_json": json.dumps({"content": post_content}),
                        }
                        resp = requests.post(upload_url, headers=HEADERS, data=data, files=files, timeout=60)
                except Exception as ex:
                    time.sleep(2)
                    continue

                if resp.status_code in (200, 201):
                    posted_msg = resp.json()
                    break
                elif resp.status_code == 429:
                    r_after = resp.json().get("retry_after", 2.0)
                    time.sleep(float(r_after) + 0.5)
                elif resp.status_code == 413:
                    break
                else:
                    break

        # Nếu file lớn hơn 25MB hoặc bị 413 -> Gửi bài thông báo tải từ Web Portal
        if not posted_msg:
            post_content_large = (
                post_content + "\n"
                f"⚠️ *(Tệp `{file_name}` dung lượng {format_size(actual_size)} (> 25MB). Tệp đã được lưu trữ an toàn trên máy chủ HyperHub và có thể tải trực tiếp trên Web Portal hoặc qua lệnh /tim_de)*"
            )
            for retry in range(4):
                try:
                    resp = requests.post(
                        upload_url,
                        headers={**HEADERS, "Content-Type": "application/json"},
                        json={"content": post_content_large},
                        timeout=30,
                    )
                    if resp.status_code in (200, 201):
                        posted_msg = resp.json()
                        break
                    elif resp.status_code == 429:
                        r_after = resp.json().get("retry_after", 2.0)
                        time.sleep(float(r_after) + 0.5)
                    else:
                        break
                except Exception:
                    time.sleep(2)

        if posted_msg:
            new_msg_id = int(posted_msg["id"])
            new_ch_id = int(posted_msg["channel_id"])
            jump_url = f"https://discord.com/channels/{GUILD_ID}/{new_ch_id}/{new_msg_id}"

            cur.execute("""
                UPDATE documents_archive
                SET channel_id = ?, message_id = ?, jump_url = ?, subject = ?
                WHERE id = ?
            """, (new_ch_id, new_msg_id, jump_url, resolved_sub, doc_id))
            conn.commit()

            uploaded_count += 1
            print(f"[{idx}/{total}] 🚀 UPLOADED ID {doc_id} -> #{target_ch_name} | msg_id={new_msg_id} (Tác giả: Dai VIET)")
        else:
            error_count += 1
            print(f"[{idx}/{total}] ❌ THẤT BẠI ID {doc_id}: Không thể gửi tin nhắn lên Discord")

        # Nghỉ nhẹ 1.2s tránh Rate Limit Discord
        time.sleep(1.2)

    conn.close()
    print("=" * 60)
    print(f"[3/3] HOÀN TẤT ĐỒNG BỘ: {patched_count} cập nhật, {uploaded_count} tải mới, {error_count} lỗi / {total} tổng.")
    print("Toàn bộ tài liệu trên Discord & Database hiện có tác giả: Dai VIET ✅")
    print("=" * 60)

if __name__ == "__main__":
    main()
