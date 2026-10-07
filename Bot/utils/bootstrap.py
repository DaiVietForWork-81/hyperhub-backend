"""
utils/bootstrap.py
Pre-flight Environment & Dependency Bootstrapper.

Tự động kiểm tra và chuẩn bị toàn diện môi trường trước khi bot khởi động:
1. Kiểm tra và tự động cài đặt các thư viện Python từ requirements.txt nếu bị thiếu.
2. Kiểm tra và tự động biên dịch C++ Native Acceleration Engine (cpp_core).
3. Kiểm tra môi trường Node.js (hỗ trợ JavaScript/TypeScript Sandbox).
4. Tự động khởi tạo file .env từ .env.example (nếu chưa có).
5. Tạo sẵn các thư mục cần thiết: data/, logs/, models/, backups/.
"""

import importlib.util
import os
import shutil
import subprocess
import sys

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REQUIREMENTS_FILE = os.path.join(PROJECT_DIR, "requirements.txt")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")
ENV_EXAMPLE_FILE = os.path.join(PROJECT_DIR, ".env.example")
CPP_CORE_DIR = os.path.join(PROJECT_DIR, "cpp_core")
BUNDLED_CPP_BIN = os.path.join(PROJECT_DIR, "cpp_core", "compiler", "w64devkit", "bin")
BUNDLED_NODE_BIN = os.path.join(PROJECT_DIR, "bin", "node")


def setup_bundled_toolchains() -> None:
    """Tự động nạp các toolchain ngôn ngữ nội bộ (C/C++ GCC/G++, Node.js) vào PATH dự án."""
    extra_paths = []
    if os.path.isdir(BUNDLED_CPP_BIN):
        extra_paths.append(BUNDLED_CPP_BIN)
    if os.path.isdir(BUNDLED_NODE_BIN):
        extra_paths.append(BUNDLED_NODE_BIN)

    if extra_paths:
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(extra_paths + [current_path])


def _is_module_installed(module_name: str) -> bool:
    """Kiểm tra nhanh xem một module Python đã được cài đặt chưa."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


def check_and_install_python_packages() -> None:
    """
    Kiểm tra danh sách các gói Python cốt lõi.
    Nếu phát hiện thiếu gói nào, tự động gọi pip install -r requirements.txt.
    """
    # Bản đồ kiểm tra: Tên gói -> Module import thực tế
    critical_modules = [
        "discord",
        "sqlalchemy",
        "aiosqlite",
        "aiohttp",
        "pydantic",
        "dotenv",
        "docker",
        "tabulate",
        "psutil",
    ]

    missing = [m for m in critical_modules if not _is_module_installed(m)]

    if missing:
        print("=" * 70)
        print("   📦 PHÁT HIỆN THIẾU THƯ VIỆN PYTHON CẦN THIẾT")
        print("=" * 70)
        print(f"[-] Các module chưa có: {', '.join(missing)}")
        if os.path.isfile(REQUIREMENTS_FILE):
            print("[*] Đang tự động chạy: pip install -r requirements.txt...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                res = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE],
                    check=True,
                )
                print("[+] Đã tự động cài đặt toàn bộ thư viện Python thành công!")
            except Exception as e:
                print(f"[!] Cảnh báo khi cài đặt pip: {e}")
                print("[!] Bạn có thể thử cài thủ công bằng: pip install -r requirements.txt")
        else:
            print(f"[!] Không tìm thấy file {REQUIREMENTS_FILE}")
    else:
        # Tất cả các gói cơ bản đã có sẵn
        pass


def check_and_build_cpp_engine() -> None:
    """
    Kiểm tra xem C++ Shared Library (native_core.so / native_core.dll) đã tồn tại chưa.
    Nếu chưa, tự động gọi script build để biên dịch nếu máy có compiler.
    """
    if sys.platform == "win32":
        lib_name = "native_core.dll"
    else:
        lib_name = "native_core.so"

    lib_path = os.path.join(CPP_CORE_DIR, lib_name)
    if not os.path.isfile(lib_path):
        build_script = os.path.join(CPP_CORE_DIR, "build.py")
        if os.path.isfile(build_script):
            try:
                # Import trực tiếp hàm build để chạy nội bộ siêu nhanh
                sys.path.insert(0, CPP_CORE_DIR)
                from build import build as run_cpp_build
                run_cpp_build(strict=False)
            except Exception as e:
                print(f"[!] Không thể tự động build C++ core: {e}. Sử dụng Pure-Python Fallback.")
            finally:
                if CPP_CORE_DIR in sys.path:
                    sys.path.remove(CPP_CORE_DIR)


def check_nodejs_environment() -> None:
    """
    Kiểm tra Node.js trên hệ thống (phục vụ chạy JavaScript/TypeScript Sandbox).
    """
    node_path = shutil.which("node")
    if node_path:
        try:
            res = subprocess.run(
                [node_path, "-v"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = res.stdout.strip() if res.returncode == 0 else ""
            print(f"[+] Phát hiện Node.js ({version}): Sẵn sàng hỗ trợ Sandbox JavaScript/TypeScript.")
        except Exception:
            pass
    else:
        # Không bắt buộc, chỉ log thông tin
        pass


def check_filesystem_and_env() -> None:
    """
    Tạo các thư mục lưu trữ cần thiết và kiểm tra file cấu hình .env.
    """
    for folder in ["data", "logs", "models", "backups"]:
        folder_path = os.path.join(PROJECT_DIR, folder)
        os.makedirs(folder_path, exist_ok=True)

    if not os.path.isfile(ENV_FILE):
        if os.path.isfile(ENV_EXAMPLE_FILE):
            shutil.copyfile(ENV_EXAMPLE_FILE, ENV_FILE)
            print("=" * 70)
            print("   ⚠️  ĐÃ TỰ ĐỘNG KHỞI TẠO FILE CẤU HÌNH .env")
            print("=" * 70)
            print("[!] Đã sao chép .env.example thành .env.")
            print("[!] Vui lòng mở file .env để điền DISCORD_TOKEN trước khi bot có thể kết nối Discord!")
            print("=" * 70)


def run_preflight_checks() -> None:
    """
    Hàm entrypoint thực thi toàn bộ quy trình kiểm tra & tự động chuẩn bị.
    Được gọi ngay dòng đầu tiên của bot.py.
    """
    # 1. Tích hợp Toolchains nội bộ (C++, Node.js)
    setup_bundled_toolchains()

    # 2. Thư mục và file .env
    check_filesystem_and_env()

    # 3. Cài đặt thư viện Python nếu bị thiếu
    check_and_install_python_packages()

    # 4. Biên dịch C++ Native Engine nếu chưa có
    check_and_build_cpp_engine()

    # 5. Kiểm tra Node.js
    check_nodejs_environment()
