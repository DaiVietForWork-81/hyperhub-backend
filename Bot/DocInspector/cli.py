"""
Command-Line Interface (CLI) for DocInspector.
Fast, beautiful terminal inspection for PDF, DOCX, and DOC files.
Supports User Requirements Evaluation, Difficulty Assessment,
Parallel Batch Processing, HTML Visual Dossier, and CSV Export.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Ensure safe utf-8 printing on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .core import DocumentInspector
from .models import (
    DifficultyTier,
    GradeLevel,
    InspectionReport,
    Subject,
    UserRequirements,
)
from .reporting import DocumentReporter
from .url_fetcher import UrlDocumentFetcher
from .validator import RequirementValidator


def print_single_report(report: InspectionReport, as_json: bool = False, detailed: bool = False) -> None:
    """Print an inspection report nicely formatted to stdout."""
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return

    separator = "=" * 80
    thin_sep = "-" * 80

    print(separator)
    print(f" 📄 FILE: {report.file_name} ({report.file_size_bytes:,} bytes)")
    print(f" ⚡ TỔNG THỜI GIAN KIỂM TRA: {report.total_execution_time_ms:.2f} ms (100% NON-AI)")
    print(separator)

    # 4-Tier Verification Verdict Status Banner
    v_icon = {
        "XAC_MINH": "✅",
        "CHUA_RO_RANG": "⚠️",
        "KO_RO_RANG": "❓",
        "KO_XAC_MINH": "🚫",
    }.get(report.verdict.value, "ℹ️")

    print(f" ⭐ KẾT LUẬN XÁC MINH: {v_icon} [{report.verdict_label_vi.upper()}]")
    if detailed or report.verdict.value != "XAC_MINH":
        for line in report.verdict_rationale.splitlines():
            print(f"    {line}")
    print(thin_sep)

    # Human Summary & Category
    print(f" ▶ PHÂN LOẠI    : {report.document_category.value}")
    print(f" ▶ MÔN HỌC      : {report.detected_subject.value}")
    print(f" ▶ THỂ LOẠI     : {report.exam_track_label_vi.upper()} ({report.exam_track_rationale})")
    print(f" ▶ DẠNG ĐỀ THI  : {report.exam_type.value}")
    print(f" ▶ KHỐI LỚP     : {report.grade_level.value}")
    print(f" ▶ NGÔN NGỮ     : {report.detected_language}")
    print(f" ▶ ĐỘ TIN CẬY   : {report.confidence_score * 100:.1f}% (Điểm đối soát 3 lần: {report.pass3.triple_verification_score:.1f}/100)")
    print(f" ▶ TÓM TẮT      : {report.human_summary}")
    print(thin_sep)

    # Channel Compliance Banner (if channel context was provided)
    if report.channel_compliance:
        cc = report.channel_compliance
        cat_info = f" (Thư mục: {cc.category_id})" if cc.category_id else ""
        if cc.is_compliant:
            print(f" 📡 KIỂM DUYỆT KÊNH: ✅ ĐÚNG KÊNH [#{cc.channel_name}{cat_info}] (Môn {report.detected_subject.value} được phép)")
        else:
            print(f" 📡 KIỂM DUYỆT KÊNH: 🚨 SAI KÊNH [#{cc.channel_name}{cat_info}]!")
            print(f"    • {cc.warning_message}")
            if cc.suggested_channels:
                print(f"    👉 Gợi ý: Hãy gửi bài sang kênh #{', #'.join(cc.suggested_channels)}")
        print(thin_sep)

    # Difficulty & Workload Assessment
    diff = report.difficulty_assessment
    print(f" 🎯 ĐÁNH GIÁ ĐỘ KHÓ & TẢI TRỌNG LÀM BÀI:")
    print(f"   • Điểm độ khó: {diff.score}/10 | {diff.tier_label_vi}")
    print(f"   • Thời gian làm bài gợi ý: {diff.recommended_duration_minutes} phút (~{diff.pace_seconds_per_question:.0f}s / câu)")
    print(f"   • Đối tượng phù hợp: {diff.target_audience}")
    print(f"   • Cân đối ma trận: {diff.cognitive_balance}")

    # Pedagogical Health & Quality Audit
    qa = report.quality_audit
    print(thin_sep)
    print(f" 🩺 KIỂM ĐỊNH CHẤT LƯỢNG SƯ PHẠM (PEDAGOGICAL QUALITY AUDIT):")
    print(f"   • Điểm chất lượng: {qa.overall_score}/100 | Xếp loại: Hạng {qa.grade.value}")
    print(f"   • Độ hoàn thiện câu hỏi: {qa.question_completeness_rate * 100:.1f}% | Phủ đáp án: {qa.answer_coverage_rate * 100:.1f}%")
    print(f"   • Đánh giá: {qa.summary_vi}")
    if qa.formatting_issues:
        print(f"   • Vấn đề phát hiện ({len(qa.formatting_issues)}):")
        for iss in qa.formatting_issues[:3]:
            print(f"     - {iss}")

    # User Requirements Audit (if applicable)
    if report.requirement_audit:
        audit = report.requirement_audit
        status_symbol = "✅ ĐẠT YÊU CẦU" if audit.is_eligible else "❌ KHÔNG ĐẠT YÊU CẦU"
        print(thin_sep)
        print(f" 📋 THẨM ĐỊNH YÊU CẦU NGƯỜI DÙNG [{audit.profile_applied}]: {status_symbol}")
        print(f"   • Tiêu chí: {audit.passed_checks_count} Đạt / {audit.failed_checks_count} Không đạt")
        for c in audit.checks:
            mark = "✔" if c.passed else f"✘ ({c.severity})"
            print(f"     [{mark}] {c.rule_name}: {c.description} (Kỳ vọng: {c.expected} | Thực tế: {c.actual})")
        if audit.recommendations:
            print("   💡 Khuyến nghị điều chỉnh:")
            for r in audit.recommendations:
                print(f"     - {r}")

    print(thin_sep)

    # 3-Pass Details
    print(" 🔍 QUY TRÌNH KIỂM TRA 3 LẦN (3-PASS VERIFICATION):")
    
    # Pass 1
    p1 = report.pass1
    print(f"   [Lần 1: Kỹ thuật & Ký tự] ({p1.execution_time_ms:.2f} ms)")
    print(f"     • Định dạng thực: {p1.raw_file_type} (Magic: {p1.magic_signature})")
    print(f"     • Quy mô: {p1.page_count} trang | {p1.metrics.word_count:,} từ | {p1.char_count:,} ký tự | Đọc: ~{p1.metrics.estimated_reading_time_minutes:.1f} phút")
    print(f"     • Hệ chữ chính: {p1.primary_script} -> Ngôn ngữ: {p1.detected_language} | Entropy: {p1.metrics.entropy:.2f} bits")
    if p1.metrics.legacy_encoding_warning:
        print(f"     • ⚠️ {p1.metrics.legacy_encoding_warning}")

    # Pass 2
    p2 = report.pass2
    print(f"   [Lần 2: Cấu trúc & Định dạng] ({p2.execution_time_ms:.2f} ms)")
    print(f"     • Cấu trúc: {p2.detected_structure}")
    print(f"     • Câu hỏi: {p2.question_count} câu | {p2.options_count} phương án | Đáp án/giải: {p2.has_answer_keys}")
    if p2.question_count > 0:
        cb = p2.cognitive_breakdown
        print(f"     • Phân bổ nhận thức: Nhận biết ({cb.recognition_count}) | Thông hiểu ({cb.comprehension_count}) | Vận dụng ({cb.application_count}) | Vận dụng cao ({cb.high_application_count})")
    if p2.specialized_features:
        print(f"     • Đặc trưng nhận diện: {', '.join(p2.specialized_features)}")
    if p2.competitive_meta:
        print(f"     • Tham số Chuyên Tin: {p2.competitive_meta}")

    # Pass 3
    p3 = report.pass3
    print(f"   [Lần 3: Ngữ nghĩa chuyên sâu & Đối soát] ({p3.execution_time_ms:.2f} ms)")
    print(f"     • Trạng thái 3 lần kiểm tra: {p3.triple_verification_status}")
    if p3.evidence_terms:
        print(f"     • Bằng chứng từ khóa: {', '.join(p3.evidence_terms[:8])}")
    if p3.sub_topics:
        print(f"     • Chuyên đề / Chương phát hiện ({len(p3.sub_topics)}):")
        for st in p3.sub_topics[:3]:
            print(f"       - {st.topic_name_vi} ({st.percentage:.1f}%)")

    # Anti-spoofing alert
    if report.is_spoofed_filename:
        print(thin_sep)
        print(" 🚨 ⚠️ PHÁT HIỆN TÊN FILE GIẢ MẠO / LỪA ĐẢO:")
        print(f"    {report.spoof_details}")

    # Detailed question preview
    if detailed and p2.questions:
        print(thin_sep)
        print(f" 📝 BÓC TÁCH CHI TIẾT CÂU HỎI (Hiển thị 5 câu đầu):")
        for q in p2.questions[:5]:
            ans_str = f" [Đáp án: {q.detected_answer}]" if q.detected_answer else ""
            print(f"   • {q.label}: ({q.cognitive_level.value}){ans_str}")
            print(f"     Đề: {q.prompt[:90]}{'...' if len(q.prompt) > 90 else ''}")
            if q.options:
                opt_str = " | ".join(f"{k}. {v}" for k, v in list(q.options.items())[:4])
                print(f"     Lựa chọn: {opt_str}")

    print(separator)
    print()


def scan_directory(dir_path: Path, recursive: bool = False) -> List[Path]:
    """Find all supported files in a directory."""
    extensions = {".pdf", ".docx", ".doc", ".txt"}
    files: List[Path] = []
    
    walker = dir_path.rglob("*") if recursive else dir_path.glob("*")
    for p in walker:
        if p.is_file() and p.suffix.lower() in extensions:
            files.append(p)
    return sorted(files)


def build_requirements(args: argparse.Namespace) -> Optional[UserRequirements]:
    """Build or load UserRequirements from CLI flags."""
    req: Optional[UserRequirements] = None

    if args.profile:
        req = RequirementValidator.get_preset(args.profile)
        if not req:
            print(f"Warning: Unknown profile '{args.profile}'. Falling back to default.", file=sys.stderr)
            req = UserRequirements(profile_name=args.profile.upper())

    if args.config:
        req = RequirementValidator.load_from_json(args.config)

    # Command line flag overrides
    if args.require_subject:
        if not req:
            req = UserRequirements(profile_name="CUSTOM_CLI")
        req.target_subject = Subject[args.require_subject.upper()]

    if args.min_diff is not None:
        if not req:
            req = UserRequirements(profile_name="CUSTOM_CLI")
        req.min_difficulty = args.min_diff

    if args.max_diff is not None:
        if not req:
            req = UserRequirements(profile_name="CUSTOM_CLI")
        req.max_difficulty = args.max_diff

    if args.require_tier:
        if not req:
            req = UserRequirements(profile_name="CUSTOM_CLI")
        req.target_tier = DifficultyTier[args.require_tier.upper()]

    if args.require_answers:
        if not req:
            req = UserRequirements(profile_name="CUSTOM_CLI")
        req.require_answer_keys = True

    if args.require_no_scan:
        if not req:
            req = UserRequirements(profile_name="CUSTOM_CLI")
        req.allow_scanned_pdf = False

    return req


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="DocInspector",
        description="Non-AI Fast Universal Document & Exam Classifier (3-Pass Verification Pipeline)",
    )
    parser.add_argument(
        "target",
        type=str,
        help="Path to a PDF/DOCX file or a folder of documents to inspect.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format.",
    )
    parser.add_argument(
        "-d", "--detailed",
        action="store_true",
        help="Print itemized question breakdown and forensic metrics in terminal.",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Scan directories recursively.",
    )
    parser.add_argument(
        "--html",
        type=str,
        default=None,
        help="Export audit report to interactive standalone HTML file.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Export batch inspection results to CSV file.",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Number of parallel worker threads for directory batch scan (default: 4).",
    )

    # User Requirements & Qualification flags
    parser.add_argument(
        "--profile",
        type=str,
        choices=["thpt_graduation", "university_top", "olympiad", "cv5512", "moet_2025", "strict_security"],
        default=None,
        help="Apply pre-configured qualification requirements profile.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON file specifying custom qualification requirements.",
    )
    parser.add_argument(
        "--require-subject",
        type=str,
        default=None,
        help="Enforce document must belong to a specific subject (e.g. MATHEMATICS, INFORMATICS, ENGLISH).",
    )
    parser.add_argument(
        "--require-tier",
        type=str,
        choices=["TIER_1_BASIC", "TIER_2_MODERATE", "TIER_3_ADVANCED", "TIER_4_OLYMPIAD"],
        default=None,
        help="Enforce difficulty tier requirement.",
    )
    parser.add_argument(
        "--min-diff",
        type=float,
        default=None,
        help="Enforce minimum required difficulty score (1.0 - 10.0).",
    )
    parser.add_argument(
        "--max-diff",
        type=float,
        default=None,
        help="Enforce maximum allowed difficulty score (1.0 - 10.0).",
    )
    parser.add_argument(
        "--require-answers",
        action="store_true",
        help="Require that document contains answer keys.",
    )
    parser.add_argument(
        "--require-no-scan",
        action="store_true",
        help="Reject documents that are low-quality scanned image PDFs.",
    )
    parser.add_argument(
        "-c", "--channel",
        type=str,
        default=None,
        help="Designate Discord / Telegram / Forum channel (e.g. #de-toan, #chuyen-tin, #khtn) to verify subject routing.",
    )
    parser.add_argument(
        "--category", "--category-id",
        type=str,
        default="1534147951797080174",
        help="Designate Discord category / folder ID (default: 1534147951797080174).",
    )
    parser.add_argument(
        "--track",
        type=str,
        choices=["thuong", "hsg", "chuyen"],
        default=None,
        help="Filter or enforce exam track: thuong (đại trà), hsg (học sinh giỏi - dễ hơn chuyên), chuyen (chuyên sâu/Olympic).",
    )

    args = parser.parse_args()
    target_arg = args.target.strip()
    requirements = build_requirements(args)

    # Check if target is a web URL or Google Drive link
    if UrlDocumentFetcher.is_url(target_arg):
        report = DocumentInspector.inspect(target_arg, requirements=requirements, channel=args.channel, category_id=args.category)
        print_single_report(report, as_json=args.json, detailed=args.detailed)
        if args.html:
            hp = DocumentReporter.generate_html_report(report, args.html)
            print(f"✅ Đã xuất báo cáo thẩm định HTML: {hp}")
        if args.csv:
            cp = DocumentReporter.export_batch_csv([report], args.csv)
            print(f"✅ Đã xuất bảng CSV: {cp}")
        return

    target_path = Path(args.target)

    if not target_path.exists():
        print(f"Error: Target path '{args.target}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if target_path.is_file():
        report = DocumentInspector.inspect(target_path, requirements=requirements, channel=args.channel, category_id=args.category)
        print_single_report(report, as_json=args.json, detailed=args.detailed)
        if args.html:
            hp = DocumentReporter.generate_html_report(report, args.html)
            print(f"✅ Đã xuất báo cáo thẩm định HTML: {hp}")
        if args.csv:
            cp = DocumentReporter.export_batch_csv([report], args.csv)
            print(f"✅ Đã xuất bảng CSV: {cp}")
    elif target_path.is_dir():
        files = scan_directory(target_path, recursive=args.recursive)
        if not files:
            print(f"No PDF or DOCX documents found in '{target_path}'.", file=sys.stderr)
            sys.exit(0)

        total_files = len(files)
        total_time_start = time.perf_counter()
        reports: List[InspectionReport] = []

        if not args.json:
            prof_msg = f" [Hồ sơ: {requirements.profile_name}]" if requirements else ""
            ch_msg = f" [Kênh: #{args.channel}]" if args.channel else ""
            cat_msg = f" [Thư mục: {args.category}]" if args.category else ""
            print(f"\n🚀 Đang quét song song {total_files} tài liệu (workers={args.workers}){prof_msg}{ch_msg}{cat_msg} trong: {target_path}\n")

        # Parallel batch processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_file = {executor.submit(DocumentInspector.inspect, f, None, requirements, args.channel, args.category): f for f in files}
            for future in concurrent.futures.as_completed(future_to_file):
                try:
                    rep = future.result()
                    reports.append(rep)
                    if not args.json:
                        print_single_report(rep, as_json=False, detailed=args.detailed)
                except Exception as e:
                    f = future_to_file[future]
                    print(f"Error inspecting {f.name}: {e}", file=sys.stderr)

        total_duration_ms = (time.perf_counter() - total_time_start) * 1000.0

        if args.json:
            out_list = [r.to_dict() for r in reports]
            print(json.dumps(out_list, ensure_ascii=False, indent=2))
        else:
            avg_time = total_duration_ms / max(1, total_files)
            print("=" * 80)
            print(f"✅ HOÀN TẤT QUÉT BATCH SONG SONG: {total_files} file")
            print(f"⏱️ Tổng thời gian: {total_duration_ms:.2f} ms | Trung bình: {avg_time:.2f} ms / file")
            spoofed_count = sum(1 for r in reports if r.is_spoofed_filename)
            if spoofed_count > 0:
                print(f"🚨 Đã bắt và vạch trần {spoofed_count} file giả mạo tên!")

            # 4-Tier Verification Verdict Breakdown
            v_ok = sum(1 for r in reports if r.verdict.value == "XAC_MINH")
            v_uncertain = sum(1 for r in reports if r.verdict.value == "CHUA_RO_RANG")
            v_unidentified = sum(1 for r in reports if r.verdict.value == "KO_RO_RANG")
            v_failed = sum(1 for r in reports if r.verdict.value == "KO_XAC_MINH")

            print(f" 📊 THỐNG KÊ 4 TRẠNG THÁI XÁC MINH:")
            print(f"   • ✅ Xác minh (thấy ổn)                              : {v_ok}/{total_files} file")
            print(f"   • ⚠️ Chưa rõ ràng (xác minh nhưng chưa chắc đúng đề) : {v_uncertain}/{total_files} file")
            print(f"   • ❓ Không rõ ràng (xem được đề nhưng ko biết đề nào): {v_unidentified}/{total_files} file")
            print(f"   • 🚫 Không xác minh (không được gì hết)              : {v_failed}/{total_files} file")

            if args.channel:
                ch_ok = sum(1 for r in reports if r.channel_compliance and r.channel_compliance.is_compliant)
                print(f" 📡 Kiểm duyệt theo kênh [#{args.channel}]: {ch_ok}/{total_files} file ĐÚNG KÊNH.")

            if requirements:
                eligible_count = sum(1 for r in reports if r.requirement_audit and r.requirement_audit.is_eligible)
                print(f"🎯 Kết quả thẩm định theo hồ sơ [{requirements.profile_name}]: {eligible_count}/{total_files} file ĐẠT YÊU CẦU.")
            print("=" * 80)

        if args.csv:
            cp = DocumentReporter.export_batch_csv(reports, args.csv)
            print(f"✅ Đã xuất bảng tổng hợp CSV: {cp}")
        if args.html and reports:
            hp = DocumentReporter.generate_html_report(reports[0], args.html)
            print(f"✅ Đã xuất báo cáo thẩm định HTML cho file đầu tiên: {hp}")


if __name__ == "__main__":
    main()
