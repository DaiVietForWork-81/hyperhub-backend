"""
Master Command-Line Interface for DocInspector.
"TỰ NHIÊN - MINH BẠCH - KHÔNG DÙNG AI MÀ NGANG AI - TRAINING NHIỀU LẦN"
Commands:
  inspect   : Inspect a local PDF/Word file or Google Drive link with transparent audit trail
  train     : Run multi-epoch heuristic calibration across benchmark corpus ("TRAINING NHIỀU LẦN")
  benchmark : Evaluate current model accuracy on golden exam corpus
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Safe Unicode output for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .explainability import ExplainabilityEngine
from .smart_pipeline import SmartDocumentPipeline
from .trainer import DocInspectorTrainer


def cmd_inspect(args: argparse.Namespace) -> None:
    """Inspect a document from path or Google Drive link."""
    target = args.target
    print(f"🔄 Đang nạp và phân tích tài liệu: {target} ...")
    
    t0 = time.perf_counter()
    res = SmartDocumentPipeline.process(target)
    elapsed = (time.perf_counter() - t0) * 1000

    print("=" * 80)
    print(f"📄 TỆP: {res.file_name} [{res.source_type}]")
    print(f"⚡ THỜI GIAN: {elapsed:.2f} ms | GOOGLE DRIVE: {'CÓ' if res.is_google_drive else 'KHÔNG'}")
    print(f"🏷️  MÔN HỌC: {res.subject_label_vi} | LỚP: {res.grade_label_vi} | HỆ: {res.exam_track_label_vi}")
    print(f"❓ TỔNG SỐ CÂU: {res.total_questions} | KẾT LUẬN: {res.verdict_label_vi}")
    if res.is_spoofed:
        print(f"⚠️  CẢNH BÁO GIẢ MẠO: {res.dossier.spoof_audit}")
    print("=" * 80)

    if args.explain:
        print("\n" + res.to_markdown() + "\n")

    if args.json:
        print(res.export_json())

    if args.save_html:
        html_out = Path(args.save_html)
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Transparency Dossier: {res.file_name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #24292e; background: #fafbfc; }}
h1, h2, h3 {{ color: #0366d6; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; background: #fff; }}
th, td {{ border: 1px solid #e1e4e8; padding: 10px 12px; text-align: left; }}
th {{ background: #f6f8fa; }}
code {{ background: #f1f3f5; padding: 2px 6px; border-radius: 4px; font-size: 88%; }}
blockquote {{ border-left: 4px solid #f66a0a; margin: 0; padding-left: 16px; color: #735c0f; background: #fffbdd; padding: 8px 16px; border-radius: 4px; }}
.badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: bold; background: #28a745; color: #fff; }}
</style>
</head>
<body>
<h1>🔍 Hồ Sơ Bạch Hóa: {res.file_name}</h1>
<p><span class="badge">100% NON-AI HEURISTIC</span> <strong>Thời gian:</strong> {res.execution_time_ms:.2f} ms | <strong>Nguồn:</strong> {res.source_type}</p>
<pre style="white-space: pre-wrap; background: #f6f8fa; padding: 16px; border-radius: 6px;">{res.to_markdown()}</pre>
</body>
</html>"""
        html_out.write_text(html_content, encoding="utf-8")
        print(f"💾 Đã lưu báo cáo HTML minh bạch: {html_out.resolve()}")


def cmd_train(args: argparse.Namespace) -> None:
    """Run multi-epoch calibration and training harness."""
    trainer = DocInspectorTrainer()
    epochs = args.epochs or 5
    lr = args.lr or 0.08
    trainer.run_training(epochs=epochs, learning_rate=lr, verbose=True)


def cmd_benchmark(args: argparse.Namespace) -> None:
    """Run benchmark evaluation without altering weights."""
    trainer = DocInspectorTrainer()
    trainer.run_training(epochs=1, learning_rate=0.0, verbose=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DocInspector Master CLI — Natural, Transparent, Zero-AI Document Intelligence",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: inspect
    inspect_p = subparsers.add_parser("inspect", help="Inspect PDF, Word, or Google Drive link")
    inspect_p.add_argument("target", help="File path or Google Drive / Docs URL")
    inspect_p.add_argument("--explain", action="store_true", help="Print transparent audit evidence trail")
    inspect_p.add_argument("--json", action="store_true", help="Output full JSON payload")
    inspect_p.add_argument("--save-html", help="Path to save visual HTML audit dossier")

    # Subcommand: train
    train_p = subparsers.add_parser("train", help="Run multi-epoch calibration ('TRAINING NHIỀU LẦN')")
    train_p.add_argument("--epochs", type=int, default=5, help="Number of training epochs (default: 5)")
    train_p.add_argument("--lr", type=float, default=0.08, help="Heuristic learning rate (default: 0.08)")

    # Subcommand: benchmark
    benchmark_p = subparsers.add_parser("benchmark", help="Evaluate current model accuracy on corpus")

    args = parser.parse_args()

    if args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "train":
        cmd_train(args)
    elif args.command == "benchmark":
        cmd_benchmark(args)


if __name__ == "__main__":
    main()
