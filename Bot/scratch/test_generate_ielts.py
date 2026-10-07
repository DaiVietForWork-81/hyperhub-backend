"""Tạo thử đề thi mẫu IELTS Academic 8.0 bằng chuỗi AI và xuất file DOCX + PDF."""

import asyncio
import os
import sys
import time
from pathlib import Path

# Đảm bảo mã hóa UTF-8 cho console trên Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Đảm bảo đường dẫn gốc
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.exam_generator_service import exam_generator_service

async def progress_tracker(stage_text: str, progress: float):
    print(f"[{int(progress*100):3d}%] {stage_text}")

async def main():
    print("=" * 60)
    print("🚀 BẮT ĐẦU TẠO ĐỀ THI THỬ NGHIỆM: IELTS ACADEMIC BAND 8.0")
    print("=" * 60)
    start_time = time.time()

    job_id = "IELTS80"
    output_dir = os.path.join("scratch", "exports", "ielts_80")

    result = await exam_generator_service.generate_exam(
        job_id=job_id,
        subject="IELTS Academic 8.0 (Reading & Writing)",
        style="Đề thi chuẩn cấu trúc Academic Band 8.0: Đoạn văn học thuật C1-C2, các câu hỏi True/False/Not Given, Matching Information, Task 2 Essay Question & Hướng dẫn chấm chi tiết kèm bài mẫu Band 8.5",
        length_tier="Ngắn",
        mode="Lite",
        output_format="Both",
        output_dir=output_dir,
        progress_callback=progress_tracker,
    )

    elapsed = time.time() - start_time
    print("=" * 60)
    print(f"✨ HOÀN TẤT TRONG: {elapsed:.1f} giây")
    print("=" * 60)
    print("📁 Danh sách file Đề thi [De_Thi]:")
    for f in result.get("exam_files", []):
        size_kb = os.path.getsize(f) / 1024
        print(f"  • {f} ({size_kb:.1f} KB)")

    print("📁 Danh sách file Lời giải & Đáp án [Huong_Dan_Giai]:")
    for f in result.get("solution_files", []):
        size_kb = os.path.getsize(f) / 1024
        print(f"  • {f} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    asyncio.run(main())
