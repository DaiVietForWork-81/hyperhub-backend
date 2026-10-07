#!/usr/bin/env python3
"""HyperHub Ecosystem Unified Launcher.

Cung cấp menu khởi chạy nhanh cho toàn bộ hệ sinh thái HyperHub:
[1] Discord Bot (Bot/bot.py)
[2] Web Platform (Web/app.py) -> http://localhost:5000
[3] Cả Hai (Chạy song song Bot & Web với cơ chế giám sát và dọn dẹp tiến trình an toàn)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Đảm bảo UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.resolve()
BOT_DIR = PROJECT_ROOT / "Bot"
WEB_DIR = PROJECT_ROOT / "Web"

BOT_ENTRY = BOT_DIR / "bot.py"
WEB_ENTRY = WEB_DIR / "app.py"

SUBPROCESS_ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def print_banner() -> None:
    """In giao diện banner phong cách HyperHub."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                 HYPERHUB ECOSYSTEM LAUNCHER                  ║
║                     LEARN • CODE • CHILL                     ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner.strip())


def run_bot() -> int:
    """Khởi chạy Discord Bot độc lập."""
    print("\n🤖 Đang khởi chạy Discord Bot...")
    if not BOT_ENTRY.exists():
        print(f"❌ Không tìm thấy file: {BOT_ENTRY}")
        return 1
    try:
        res = subprocess.run([sys.executable, str(BOT_ENTRY)], cwd=str(BOT_DIR), env=SUBPROCESS_ENV)
        return res.returncode
    except KeyboardInterrupt:
        print("\n👋 Đã tắt Discord Bot.")
        return 0


def run_web() -> int:
    """Khởi chạy Web Platform độc lập."""
    print("\n🌐 Đang khởi chạy HyperHub Web Platform...")
    if not WEB_ENTRY.exists():
        print(f"❌ Không tìm thấy file: {WEB_ENTRY}")
        return 1
    try:
        res = subprocess.run([sys.executable, str(WEB_ENTRY)], cwd=str(WEB_DIR), env=SUBPROCESS_ENV)
        return res.returncode
    except KeyboardInterrupt:
        print("\n👋 Đã tắt Web Platform.")
        return 0


def run_both() -> int:
    """Khởi chạy đồng thời cả Bot và Web trong các tiến trình riêng biệt."""
    print("\n🚀 Đang khởi chạy đồng thời [1] Discord Bot & [2] Web Platform...")
    
    if not BOT_ENTRY.exists() or not WEB_ENTRY.exists():
        print("❌ Kiểm tra thất bại: Thiếu file bot.py hoặc app.py.")
        return 1

    processes: list[subprocess.Popen] = []

    try:
        # Khởi chạy Bot
        print(" -> Đang khởi động Discord Bot...")
        bot_proc = subprocess.Popen([sys.executable, str(BOT_ENTRY)], cwd=str(BOT_DIR), env=SUBPROCESS_ENV)
        processes.append(bot_proc)

        # Nghỉ 1 giây để Bot chuẩn bị socket bridge trước khi Web kết nối
        time.sleep(1)

        # Khởi chạy Web
        print(" -> Đang khởi động Web Platform (http://localhost:5000)...")
        web_proc = subprocess.Popen([sys.executable, str(WEB_ENTRY)], cwd=str(WEB_DIR), env=SUBPROCESS_ENV)
        processes.append(web_proc)

        print("\n" + "=" * 62)
        print(" ✅ CẢ 2 DỊCH VỤ ĐANG HOẠT ĐỘNG SONG SONG!")
        print(" 👉 Web:     http://localhost:5000 hoặc http://127.0.0.1:5000")
        print(" 👉 Bot:     Đang kết nối Discord Gateway & Bridge Port 8080")
        print(" ℹ️  Nhấn Ctrl+C bất cứ lúc nào để dừng an toàn cả 2 dịch vụ.")
        print("=" * 62 + "\n")

        # Giám sát vòng đời 2 tiến trình
        while True:
            all_dead = True
            for proc in processes:
                if proc.poll() is None:
                    all_dead = False
                    break
            if all_dead:
                print("ℹ️ Toàn bộ các tiến trình đã kết thúc.")
                break
            time.sleep(0.5)

        return 0

    except KeyboardInterrupt:
        print("\n\n🛑 Nhận tín hiệu dừng (Ctrl+C). Đang tắt Bot & Web...")
        for proc in processes:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

        # Chờ tối đa 3 giây cho graceful shutdown
        time.sleep(1)

        for proc in processes:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        print("✅ Đã dừng an toàn toàn bộ hệ sinh thái HyperHub.")
        return 0


def interactive_menu() -> None:
    """Hiển thị menu tương tác."""
    print_banner()
    print("Vui lòng chọn chế độ khởi chạy:")
    print("  [1] Discord Bot       (Bot/bot.py)")
    print("  [2] Web Platform      (Web/app.py -> http://localhost:5000)")
    print("  [3] Cả Hai (Bot + Web song song)")
    print("  [0] Thoát")
    print("-" * 64)

    try:
        choice = input("👉 Nhập lựa chọn của bạn [1/2/3/0]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Đã thoát.")
        sys.exit(0)

    if choice == "1":
        sys.exit(run_bot())
    elif choice == "2":
        sys.exit(run_web())
    elif choice == "3":
        sys.exit(run_both())
    elif choice in ("0", "q", "quit", "exit"):
        print("👋 Tạm biệt!")
        sys.exit(0)
    else:
        print(f"❌ Lựa chọn '{choice}' không hợp lệ. Vui lòng chọn 1, 2, 3 hoặc 0.")
        sys.exit(1)


def main() -> None:
    """Xử lý tham số dòng lệnh hoặc mở menu tương tác."""
    args = sys.argv[1:]

    if not args:
        interactive_menu()
        return

    arg = args[0].lower().strip()
    if arg in ("1", "bot", "--bot", "-b"):
        sys.exit(run_bot())
    elif arg in ("2", "web", "--web", "-w"):
        sys.exit(run_web())
    elif arg in ("3", "both", "all", "--both", "--all", "-a"):
        sys.exit(run_both())
    elif arg in ("--help", "-h", "help"):
        print_banner()
        print("Cách sử dụng: python main.py [tùy_chọn]\n")
        print("Tùy chọn:")
        print("  1, --bot    : Chạy riêng Discord Bot")
        print("  2, --web    : Chạy riêng Web Platform (cổng 5000)")
        print("  3, --both   : Chạy đồng thời cả Bot và Web")
        print("  (không tham số): Mở menu tương tác để chọn")
        sys.exit(0)
    else:
        print(f"❌ Tham số '{arg}' không hợp lệ. Dùng 'python main.py --help' để xem hướng dẫn.")
        sys.exit(1)


if __name__ == "__main__":
    main()
