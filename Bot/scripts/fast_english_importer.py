"""
scripts/fast_english_importer.py
Tải trực tiếp tốc độ cao toàn bộ các bộ đề thi THPT 2025, HSG, Chuyên Anh, Cambridge IELTS từ Google Drive vào Bot.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import time
from typing import Any
import requests

sys.stdout.reconfigure(encoding="utf-8")

# Setup đường dẫn
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.gdrive_importer import import_file_to_bot

CATALOG_FILE = r"C:\Users\Mk2012\.gemini\antigravity\brain\07c0ffdf-2152-4957-888b-b55a82c9002d\scratch\gdrive_all_english_docs.json"


def download_gdrive_file(file_id: str, dest_path: str) -> bool:
    """Tải tệp từ Google Drive với HTTP stream và xử lý bypass virus scan warning."""
    session = requests.Session()
    url = f"https://drive.google.com/uc?id={file_id}&export=download"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = session.get(url, headers=headers, stream=True, timeout=35)
        text_head = res.text[:2000] if not res.headers.get("content-type", "").startswith("application/") else ""
        if "confirm=" in text_head or "download_warning" in text_head:
            m = re.search(r'confirm=([0-9A-Za-z_-]+)', text_head)
            if m:
                confirm_token = m.group(1)
                res = session.get(
                    f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}",
                    headers=headers,
                    stream=True,
                    timeout=35,
                )
        if res.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
            return os.path.exists(dest_path) and os.path.getsize(dest_path) > 100
    except Exception as e:
        print(f"    [!] Lỗi mạng khi tải tệp {file_id}: {e}", flush=True)
    return False


def main():
    if not os.path.exists(CATALOG_FILE):
        print(f"[!] Không tìm thấy catalog {CATALOG_FILE}", flush=True)
        return

    with open(CATALOG_FILE, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    categories = catalog.get("categories", {})
    print("=======================================================", flush=True)
    print("BẮT ĐẦU TẢI & NẠP CÁC BỘ ĐỀ THI TIẾNG ANH CHỌN LỌC", flush=True)
    print("=======================================================\n", flush=True)

    # 1. Thu thập danh sách đề thi ưu tiên
    priority_queue: list[tuple[str, str, str]] = []  # (category_name, file_id, file_name)

    # A. 48 Mã đề THPT 2025 môn Tiếng Anh
    thpt_key = "ĐỀ TỐT NGHIỆP THPT MÔN TIẾNG ANH 2025 (48 MÃ ĐỀ)"
    if thpt_key in categories:
        for f in categories[thpt_key]:
            priority_queue.append((thpt_key, f["id"], f["name"]))

    # B. Đề chọn ĐTQG & HSG các tỉnh & Chuyên Anh
    for cat_name, file_list in categories.items():
        if cat_name == thpt_key:
            continue
        cat_upper = cat_name.upper()
        if any(term in cat_upper for term in ("HSG", "CHUYÊN", "CHUYEN", "ĐỀ", "OLYMPIC", "DHBB", "HÙNG VƯƠNG", "THI THỬ")):
            for f in file_list:
                fname = f["name"]
                if fname.lower().endswith((".pdf", ".docx", ".doc")):
                    priority_queue.append((cat_name, f["id"], fname))

    # C. Tài liệu cốt lõi (Word Form, Trios, Transformation, Cambridge IELTS)
    core_keys = ("ROOT", "WRITING", "LONGMAN WRITING", "TỔNG HỢP IDIOMS/COLLOCATIONS THI CHUYÊN ANH")
    for ck in core_keys:
        if ck in categories:
            for f in categories[ck]:
                fname = f["name"]
                if fname.lower().endswith((".pdf", ".docx", ".doc")):
                    priority_queue.append((ck, f["id"], fname))

    # Giới hạn mẻ ưu tiên đầu tiên: 80 tài liệu/đề thi
    queue_to_process = priority_queue[:80]
    print(f"[*] Đã chọn lọc {len(queue_to_process)} đề thi & tài liệu trọng tâm nhất để nạp vào Bot.", flush=True)

    temp_dir = tempfile.mkdtemp(prefix="fast_eng_")
    imported_count = 0
    duplicate_count = 0
    error_count = 0

    try:
        for idx, (cat_name, f_id, f_name) in enumerate(queue_to_process, start=1):
            print(f"\n[{idx}/{len(queue_to_process)}] 📂 {cat_name} -> {f_name}", flush=True)
            dest_file = os.path.join(temp_dir, f_name)

            ok = download_gdrive_file(f_id, dest_file)
            if not ok:
                print(f"    ⚠️ Không tải được tệp (có thể do quyền truy cập riêng tư).", flush=True)
                error_count += 1
                continue

            size_mb = round(os.path.getsize(dest_file) / 1024 / 1024, 2)
            print(f"    📥 Đã tải {size_mb} MB. Đang chạy DocInspector kiểm định...", flush=True)

            res = import_file_to_bot(
                file_path=dest_file,
                uploader_name=f"Tài Liệu Anh ({cat_name})",
            )

            if res.get("success"):
                imported_count += 1
                print(f"    ✅ ĐÃ NẠP THÀNH CÔNG: ID #{res['id']} | Môn: {res['detected_subject']} | Khối: {res['estimated_level']}", flush=True)
            elif res.get("is_duplicate"):
                duplicate_count += 1
                print(f"    🔁 TRÙNG LẶP: {f_name} (Đã có trong kho ID #{res['existing_id']})", flush=True)
            else:
                print(f"    ❌ LỖI: {res.get('error')}", flush=True)
                error_count += 1

            # Xóa file tạm
            if os.path.exists(dest_file):
                os.remove(dest_file)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n=======================================================", flush=True)
    print(f"HOÀN THÀNH TẢI ĐỀ THI TIẾNG ANH!", flush=True)
    print(f"  - Nạp mới thành công: {imported_count}", flush=True)
    print(f"  - Trùng lặp: {duplicate_count}", flush=True)
    print(f"  - Lỗi: {error_count}", flush=True)
    print("=======================================================", flush=True)


if __name__ == "__main__":
    main()
