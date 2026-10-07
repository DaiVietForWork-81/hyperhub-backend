"""
scripts/batch_gdrive_import.py
Script quét và nạp tự động toàn bộ danh sách link Google Drive lịch sử từ các kênh Discord vào Bot.
Tối ưu hóa: Lọc trực tiếp các tệp PDF/Word/Đề thi, bỏ qua tệp âm thanh/nén, hỗ trợ resume từ checkpoint.
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

sys.stdout.reconfigure(encoding="utf-8")

# Setup đường dẫn
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from services.gdrive_importer import import_file_to_bot

LINKS_FILE = r"C:\Users\Mk2012\.gemini\antigravity\brain\07c0ffdf-2152-4957-888b-b55a82c9002d\scratch\clean_gdrive_links.json"
REPORT_FILE = r"C:\Users\Mk2012\.gemini\antigravity\brain\07c0ffdf-2152-4957-888b-b55a82c9002d\scratch\import_report.json"

VALID_EXTS = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt")


def download_single_or_folder(url: str, dest_dir: str) -> list[str]:
    """Tải tệp hoặc thư mục từ Google Drive bằng gdown, chỉ lọc lấy tài liệu PDF/Word."""
    import gdown

    downloaded_files = []
    is_folder = "folder" in url or "/folders/" in url

    try:
        if is_folder:
            # 1. Quét danh sách file trong folder mà không tải dữ liệu nặng
            items = gdown.download_folder(url, skip_download=True, quiet=True, use_cookies=False)
            if not items:
                return []

            # 2. Lọc chỉ lấy các tệp đề thi & tài liệu học tập PDF/Word
            doc_items = [
                it for it in items
                if any(it.path.lower().endswith(ext) for ext in VALID_EXTS)
                or (not any(it.path.lower().endswith(ext) for ext in ('.zip', '.rar', '.mp3', '.m4a', '.wav', '.png', '.jpg', '.jpeg')) and '.' not in it.path[-5:])
            ]
            print(f"    📂 Quét thư mục: tìm thấy {len(items)} tệp -> Lọc {len(doc_items)} tệp tài liệu PDF/Word.", flush=True)

            # Ưu tiên các đề thi & sách cốt lõi nếu thư mục quá lớn (> 80 tệp)
            if len(doc_items) > 80:
                priority_keywords = (
                    "THPT", "TỐT NGHIỆP", "ĐỀ", "ĐỀ", "DE", "ĐÁP ÁN", "DAP AN",
                    "HSG", "CHUYÊN", "CHUYEN", "CAMBRIDGE", "IELTS", "READING", "SPEAKING",
                    "WORD FORM", "TRANSFORMATION", "TRIOS", "IDIOM", "CLOZE", "LONGMAN", "WRITING"
                )
                p_items = [it for it in doc_items if any(kw in it.path.upper() for kw in priority_keywords)]
                other_items = [it for it in doc_items if it not in p_items]
                doc_items = (p_items + other_items)[:120]
                print(f"    ⭐ Ưu tiên chọn lọc {len(doc_items)} đề thi & sách trọng tâm nhất để tải nhanh.", flush=True)

            # 3. Tải từng tệp tài liệu vào dest_dir
            for it in doc_items:
                fname = os.path.basename(it.path)
                # Bỏ qua nếu là file âm thanh hoặc zip
                if any(fname.lower().endswith(bad) for bad in ('.zip', '.rar', '.mp3', '.m4a', '.wav')):
                    continue
                target_path = os.path.join(dest_dir, fname)
                try:
                    f_out = gdown.download(id=it.id, output=target_path, quiet=True, use_cookies=False)
                    if f_out and os.path.exists(f_out) and os.path.getsize(f_out) > 0:
                        downloaded_files.append(f_out)
                except Exception as fe:
                    print(f"      [!] Bỏ qua tệp tải lỗi: {fname} ({fe})", flush=True)
        else:
            file_out = gdown.download(url=url, output=os.path.join(dest_dir, ""), quiet=True, use_cookies=False)
            if file_out and os.path.exists(file_out) and os.path.getsize(file_out) > 0:
                downloaded_files.append(file_out)
            else:
                # Fallback: Thử dạng folder
                items = gdown.download_folder(url, skip_download=True, quiet=True, use_cookies=False)
                if items:
                    for it in items:
                        fname = os.path.basename(it.path)
                        if any(fname.lower().endswith(ext) for ext in VALID_EXTS):
                            target_path = os.path.join(dest_dir, fname)
                            try:
                                f_out = gdown.download(id=it.id, output=target_path, quiet=True, use_cookies=False)
                                if f_out and os.path.exists(f_out):
                                    downloaded_files.append(f_out)
                            except Exception:
                                pass
    except Exception as e:
        err_msg = str(e)
        if "Permission denied" in err_msg or "Cannot retrieve file url" in err_msg or "404" in err_msg or "Only the owner" in err_msg:
            raise PermissionError(f"Link không công khai hoặc bị giới hạn quyền truy cập: {err_msg}")
        raise e

    return downloaded_files


def main():
    if not os.path.exists(LINKS_FILE):
        print(f"[!] Không tìm thấy tệp {LINKS_FILE}", flush=True)
        return

    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        links = json.load(f)

    print("=======================================================", flush=True)
    print(f"BẮT ĐẦU NẠP TỰ ĐỘNG {len(links)} LINK GOOGLE DRIVE TỪ DISCORD (OPTIMIZED)", flush=True)
    print("=======================================================\n", flush=True)

    # Đọc report hiện có để resume
    processed_indices = set()
    report = {
        "total_links": len(links),
        "success_files": 0,
        "duplicate_files": 0,
        "permission_denied_links": 0,
        "error_links": 0,
        "details": [],
    }

    if os.path.exists(REPORT_FILE):
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as rf:
                old_report = json.load(rf)
                if isinstance(old_report.get("details"), list):
                    report = old_report
                    for d in report["details"]:
                        if d.get("status") in ("SUCCESS", "PERMISSION_DENIED", "ERROR", "EMPTY"):
                            processed_indices.add(d.get("index"))
            print(f"[*] Tìm thấy checkpoint: Đã hoàn thành {len(processed_indices)}/{len(links)} link trước đó. Tiếp tục từ các link còn lại...\n", flush=True)
        except Exception as re_err:
            print(f"[!] Không thể đọc checkpoint: {re_err}", flush=True)

    start_time = time.time()

    for idx, item in enumerate(links, start=1):
        if idx in processed_indices:
            continue

        url = item["clean_url"]
        ch_name = item["channel_name"]
        author = item["author_name"]
        print(f"\n[{idx}/{len(links)}] Kênh #{ch_name} | Người gửi: {author}", flush=True)
        print(f"    URL: {url}", flush=True)

        temp_dir = tempfile.mkdtemp(prefix="gdrive_batch_")
        link_detail = {
            "index": idx,
            "url": url,
            "channel": ch_name,
            "author": author,
            "timestamp": item.get("timestamp"),
            "files": [],
            "status": "pending",
        }

        try:
            downloaded = download_single_or_folder(url, temp_dir)
            if not downloaded:
                print("    ⚠️ Không tải được tệp tài liệu nào từ link này.", flush=True)
                link_detail["status"] = "EMPTY"
                report["error_links"] += 1
            else:
                print(f"    📥 Đã tải {len(downloaded)} tệp tài liệu. Đang kiểm định & nạp vào Bot...", flush=True)
                for fpath in downloaded:
                    fname = os.path.basename(fpath)
                    res = import_file_to_bot(fpath, uploader_name=f"{author} (Discord #{ch_name})")
                    if res.get("success"):
                        report["success_files"] += 1
                        print(f"      ✅ ĐÃ NẠP: ID #{res['id']} - {fname} ({res['detected_subject']} • {res['estimated_level']})", flush=True)
                        link_detail["files"].append({"file": fname, "id": res["id"], "status": "IMPORTED"})
                    elif res.get("is_duplicate"):
                        report["duplicate_files"] += 1
                        print(f"      🔁 TRÙNG LẶP: {fname} (Trùng ID #{res['existing_id']})", flush=True)
                        link_detail["files"].append({"file": fname, "existing_id": res["existing_id"], "status": "DUPLICATE"})
                    elif res.get("skipped"):
                        print(f"      ⏭️ BỎ QUA: {fname} ({res.get('reason')})", flush=True)
                        link_detail["files"].append({"file": fname, "status": "SKIPPED"})
                    else:
                        print(f"      ❌ LỖI TỆP: {fname} ({res.get('error')})", flush=True)
                        link_detail["files"].append({"file": fname, "status": "FILE_ERROR", "error": res.get("error")})

                link_detail["status"] = "SUCCESS"

        except PermissionError as pe:
            print(f"    🔒 RIÊNG TƯ / KHÔNG TRUY CẬP ĐƯỢC: {pe}", flush=True)
            link_detail["status"] = "PERMISSION_DENIED"
            report["permission_denied_links"] += 1
        except Exception as e:
            print(f"    ❌ LỖI: {e}", flush=True)
            link_detail["status"] = "ERROR"
            link_detail["error"] = str(e)
            report["error_links"] += 1
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        report["details"].append(link_detail)
        processed_indices.add(idx)

        # Lưu checkpoint sau mỗi link
        with open(REPORT_FILE, "w", encoding="utf-8") as rf:
            json.dump(report, rf, ensure_ascii=False, indent=2)

    total_time = round(time.time() - start_time, 1)
    report["elapsed_seconds"] = total_time

    with open(REPORT_FILE, "w", encoding="utf-8") as rf:
        json.dump(report, rf, ensure_ascii=False, indent=2)

    print(f"\n=======================================================", flush=True)
    print(f"HOÀN THÀNH BATCH IMPORT TRONG {total_time} GIÂY!", flush=True)
    print(f"  - Tệp mới nạp thành công: {report['success_files']}", flush=True)
    print(f"  - Tệp trùng lặp: {report['duplicate_files']}", flush=True)
    print(f"  - Link không công khai (Private): {report['permission_denied_links']}", flush=True)
    print(f"  - Link lỗi khác: {report['error_links']}", flush=True)
    print(f"=======================================================", flush=True)


if __name__ == "__main__":
    main()
