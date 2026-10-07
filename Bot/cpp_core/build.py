#!/usr/bin/env python3
"""
cpp_core/build.py
Tự động phát hiện C++ Compiler và biên dịch Shared Library (native_core.so / native_core.dll).
Hỗ trợ:
- Linux / Ubuntu: g++, clang++
- Windows: MinGW g++, Clang++, MSVC cl.exe
- Graceful Notification: Nếu không có compiler, thông báo rõ ràng sẽ dùng Pure Python Engine.
"""

import os
import shutil
import subprocess
import sys

# Đảm bảo in UTF-8 không bị lỗi mã trang trên Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(SCRIPT_DIR, "native_core.cpp")
COMPILER_DIR = os.path.join(SCRIPT_DIR, "compiler")
PORTABLE_COMPILER_URL = "https://github.com/skeeto/w64devkit/releases/download/v1.23.0/w64devkit-1.23.0.zip"


def download_portable_compiler() -> str | None:
    """
    Tự động tải bộ C++ Compiler siêu nhẹ (w64devkit - GCC 14 C++17/20, ~73MB)
    trực tiếp vào thư mục cpp_core/compiler của dự án nếu môi trường Windows chưa có compiler.
    """
    if sys.platform != "win32":
        return None

    import urllib.request
    import zipfile

    os.makedirs(COMPILER_DIR, exist_ok=True)
    zip_path = os.path.join(SCRIPT_DIR, "compiler_temp.zip")

    print("=" * 60)
    print("   ⬇️  DỰ ÁN ĐANG TỰ ĐỘNG TẢI TRÌNH BIÊN DỊCH C++ VÀO DỰ ÁN")
    print("=" * 60)
    print(f"Nguồn tải: {PORTABLE_COMPILER_URL}")
    print(f"Thư mục lưu trữ nội bộ: {COMPILER_DIR}")
    print("[*] Vui lòng đợi trong giây lát để tải và giải nén compiler...")

    try:
        req = urllib.request.Request(
            PORTABLE_COMPILER_URL,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=180) as resp, open(zip_path, "wb") as out_f:
            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(1024 * 1024 * 2)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    print(f"\r[+] Tiến trình tải: {downloaded/(1024*1024):.1f}/{total_size/(1024*1024):.1f} MB ({pct}%)", end="", flush=True)

        print("\n[*] Đang giải nén compiler vào cpp_core/compiler...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(COMPILER_DIR)

        if os.path.isfile(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass

        # Tìm g++.exe vừa giải nén
        candidates = [
            os.path.join(COMPILER_DIR, "w64devkit", "bin", "g++.exe"),
            os.path.join(COMPILER_DIR, "bin", "g++.exe"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                print(f"[+] Cài đặt compiler nội bộ thành công: {c}")
                return c
        return None
    except Exception as e:
        print(f"\n[!] Không thể tải tự động compiler: {e}")
        print("[i] Hệ thống sẽ tiếp tục sử dụng Pure-Python Fallback Engine.")
        if os.path.isfile(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass
        return None


def find_compiler(auto_download: bool = True) -> tuple[str | None, str]:
    """Tìm trình biên dịch C++ khả dụng trên hệ thống hoặc tải về dự án."""
    # 1. Thử các lệnh trong PATH
    candidates = ["g++", "clang++", "c++"]
    if sys.platform == "win32":
        candidates.append("cl")

    for cmd in candidates:
        path = shutil.which(cmd)
        if path:
            return path, cmd

    # 2. Kiểm tra bộ Portable Compiler có sẵn ngay trong thư mục project cpp_core/compiler
    if sys.platform == "win32":
        local_candidates = [
            os.path.join(COMPILER_DIR, "w64devkit", "bin", "g++.exe"),
            os.path.join(COMPILER_DIR, "bin", "g++.exe"),
        ]
        for p in local_candidates:
            if os.path.isfile(p):
                return p, "g++"

    # 3. Trên Windows: Thử tìm trong các đường dẫn cài đặt MinGW/MSYS2 phổ biến
    if sys.platform == "win32":
        extra_windows_paths = [
            r"C:\msys64\ucrt64\bin\g++.exe",
            r"C:\msys64\mingw64\bin\g++.exe",
            r"C:\MinGW\bin\g++.exe",
            r"C:\Program Files\LLVM\bin\clang++.exe",
        ]
        for p in extra_windows_paths:
            if os.path.isfile(p):
                return p, "g++" if "g++" in p else "clang++"

    # 4. Nếu chưa có trên Windows: Tự động tải Portable Compiler vào project
    if auto_download and sys.platform == "win32":
        downloaded = download_portable_compiler()
        if downloaded and os.path.isfile(downloaded):
            return downloaded, "g++"

    return None, ""


def build(strict: bool = False, auto_download_compiler: bool = True) -> bool:
    """Biên dịch native_core thành shared library."""
    print("=" * 60)
    print("   [*] BIEN DICH C++ NATIVE ACCELERATION ENGINE")
    print("=" * 60)
    print(f"File ma nguon: {SOURCE_FILE}")

    if not os.path.isfile(SOURCE_FILE):
        print(f"[-] Loi: Khong tim thay file {SOURCE_FILE}")
        return False

    compiler_path, compiler_type = find_compiler(auto_download=auto_download_compiler)
    if not compiler_path:
        print("[!] [C++ Native Core] Khong tim thay C++ Compiler (g++, clang++, hoac cl.exe) tren he thong.")
        print("[i] Bot se tu dong su dung Pure-Python Fallback Engine voi day du 100% tinh nang.")
        if strict:
            return False
        return True

    print(f"[+] Da phat hien compiler: {compiler_path} ({compiler_type})")

    # Xác định tên file đầu ra
    if sys.platform == "win32":
        out_file = os.path.join(SCRIPT_DIR, "native_core.dll")
    else:
        out_file = os.path.join(SCRIPT_DIR, "native_core.so")

    # Xây dựng câu lệnh biên dịch
    if compiler_type == "cl":
        cmd = [
            compiler_path,
            "/O2",
            "/LD",
            "/std:c++17",
            SOURCE_FILE,
            f"/Fe:{out_file}",
        ]
    else:
        cmd = [
            compiler_path,
            "-O3",
            "-std=c++17",
            "-shared",
        ]
        if sys.platform != "win32":
            cmd.append("-fPIC")
        cmd.extend([SOURCE_FILE, "-o", out_file])

    print(f"Dang bien dich: {' '.join(cmd)}")
    build_env = os.environ.copy()
    compiler_bin_dir = os.path.dirname(compiler_path)
    if compiler_bin_dir:
        build_env["PATH"] = compiler_bin_dir + os.pathsep + build_env.get("PATH", "")

    try:
        res = subprocess.run(
            cmd,
            cwd=SCRIPT_DIR,
            env=build_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if res.returncode == 0 and os.path.isfile(out_file):
            size_kb = os.path.getsize(out_file) / 1024.0
            print(f"[+] Bien dich thanh cong: {out_file} ({size_kb:.1f} KB)")
            # Kiểm tra nạp thử bằng ctypes
            import ctypes
            try:
                lib = ctypes.CDLL(out_file)
                print("[+] Da kiem tra nap Shared Library bang ctypes thanh cong!")
            except Exception as e:
                print(f"[!] Canh bao nap ctypes: {e}")
            return True
        else:
            print(f"[-] Bien dich that bai voi ma loi {res.returncode}:")
            print(res.stderr or res.stdout)
            print("[i] He thong se chuyen sang dung Pure-Python Engine.")
            return False if strict else True
    except Exception as e:
        print(f"[-] Ngoai le khi bien dich: {e}")
        print("[i] He thong se chuyen sang dung Pure-Python Engine.")
        return False if strict else True


if __name__ == "__main__":
    is_strict = "--strict" in sys.argv
    success = build(strict=is_strict)
    sys.exit(0 if success else 1)
