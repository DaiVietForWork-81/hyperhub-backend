"""
download_model.py
Tự động khởi chạy Ollama Portable và tải các model AI vào models/ trong project (0 MB trên ổ C:):
1. qwen3.5:4b (Model chính: AI Core, Problem Generator & Solver)
2. gemma3:4b (Model thẩm định: Verifier, Logic & Length Enhancer)
3. qwen3.5:2b (Model dự phòng: Backup Generator)
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config.settings import (
    settings,
    AI_MODEL_NAME,
    AI_BACKUP_MODEL_NAME,
    AI_VERIFIER_MODEL_NAME,
)

PROJECT_DIR = os.path.abspath(os.path.dirname(__file__))
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
OLLAMA_BIN_DIR = os.path.join(PROJECT_DIR, "ollama_bin")

TARGET_MODELS = {
    "1": (AI_MODEL_NAME, "Model chính: Soạn đề, sinh code & giải thuật (AI Core / Generator)"),
    "2": (AI_VERIFIER_MODEL_NAME, "Model thẩm định: Kiểm tra logic, nâng cấp độ dài & test case biên"),
    "3": (AI_BACKUP_MODEL_NAME, "Model dự phòng: Nhẹ máy, thay thế khi cần (Backup Core)"),
}

os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["OLLAMA_MODELS"] = MODELS_DIR
os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"


def find_ollama_executable() -> str | None:
    """Tìm binary ollama: ưu tiên ollama_bin/, AppData Windows, sau đó đến PATH."""
    local_app_data = os.environ.get("LOCALAPPDATA", r"C:\Users\Mk2012\AppData\Local")
    candidates = [
        os.path.join(OLLAMA_BIN_DIR, "ollama"),
        os.path.join(OLLAMA_BIN_DIR, "ollama.exe"),
        os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            if sys.platform != "win32":
                try:
                    mode = os.stat(c).st_mode
                    os.chmod(c, mode | 0o755)
                except Exception:
                    pass
            return c
    return shutil.which("ollama")


OLLAMA_EXE = find_ollama_executable()


def is_server_ready():
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            return res.status == 200
    except Exception:
        return False


def pull_single_model(model_name: str, desc: str):
    print("\n" + "=" * 65)
    print(f"  [BẮT ĐẦU TẢI] Model: {model_name}")
    print(f"  [CHỨC NĂNG]  {desc}")
    print(f"  [NƠI LƯU]    {MODELS_DIR} (0 MB trên ổ C:)")
    print("=" * 65 + "\n")

    env = os.environ.copy()
    env["OLLAMA_MODELS"] = MODELS_DIR
    env["OLLAMA_HOST"] = "127.0.0.1:11434"

    try:
        pull_proc = subprocess.run([OLLAMA_EXE, "pull", model_name], env=env)
        if pull_proc.returncode == 0:
            print(f"\n[OK] Tải thành công model '{model_name}' vào project!")
            return True
        else:
            print(f"\n[!] Lỗi khi tải '{model_name}' (Mã lỗi: {pull_proc.returncode})")
            return False
    except KeyboardInterrupt:
        print(f"\n[!] Người dùng hủy tải model '{model_name}'.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Tải model AI cho HyperHub Bot")
    parser.add_argument("models", nargs="*", help="Tên model cụ thể cần tải (vd: qwen3.5:4b gemma3:4b)")
    parser.add_argument("--all", action="store_true", help="Tải toàn bộ cả 3 model")
    args = parser.parse_args()

    print("=" * 65)
    print("   TRÌNH QUẢN LÝ & TẢI MÔ HÌNH AI HYPERHUB (PORTABLE OLLAMA)")
    print(f"   Thư mục lưu trữ: {MODELS_DIR} (Ổ đĩa D:)")
    print(f"   Đường dẫn Ollama: {OLLAMA_EXE or 'Chưa tìm thấy'}")
    print("=" * 65)

    if not OLLAMA_EXE:
        print("[LỖI] Không tìm thấy Ollama!")
        print("  - Vui lòng cài đặt Ollama hoặc sao chép ollama.exe vào thư mục ollama_bin/")
        sys.exit(1)

    # Đảm bảo Ollama server đang chạy với biến OLLAMA_MODELS trỏ vào project
    server_proc = None
    if not is_server_ready():
        print("[1/2] Đang khởi chạy Ollama Server nền trỏ vào thư mục models/...")
        env = os.environ.copy()
        env["OLLAMA_MODELS"] = MODELS_DIR
        env["OLLAMA_HOST"] = "127.0.0.1:11434"

        popen_kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        elif sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        server_proc = subprocess.Popen([OLLAMA_EXE, "serve"], env=env, **popen_kwargs)

        for _ in range(30):
            if is_server_ready():
                break
            time.sleep(1.0)

    if not is_server_ready():
        print("[LỖI] Không thể kết nối hoặc khởi động Ollama Server!")
        sys.exit(1)

    print("[2/2] Ollama Server đã sẵn sàng!\n")

    models_to_download = []

    if args.all:
        models_to_download = [
            (AI_MODEL_NAME, TARGET_MODELS["1"][1]),
            (AI_VERIFIER_MODEL_NAME, TARGET_MODELS["2"][1]),
            (AI_BACKUP_MODEL_NAME, TARGET_MODELS["3"][1]),
        ]
    elif args.models:
        for m in args.models:
            desc = "Model theo yêu cầu tham số"
            for k, (name, d) in TARGET_MODELS.items():
                if m == name:
                    desc = d
                    break
            models_to_download.append((m, desc))
    else:
        print("DANH SÁCH MÔ HÌNH HỆ THỐNG:")
        print(f"  [1] {TARGET_MODELS['1'][0]:<15} - {TARGET_MODELS['1'][1]}")
        print(f"  [2] {TARGET_MODELS['2'][0]:<15} - {TARGET_MODELS['2'][1]}")
        print(f"  [3] {TARGET_MODELS['3'][0]:<15} - {TARGET_MODELS['3'][1]}")
        print("  [4] Tải TẤT CẢ 3 model trên")
        print("  [0] Thoát\n")

        try:
            choice = input("Nhập lựa chọn của bạn (1-4) [Mặc định 1]: ").strip() or "1"
        except EOFError:
            choice = "1"

        if choice == "1":
            models_to_download.append(TARGET_MODELS["1"])
        elif choice == "2":
            models_to_download.append(TARGET_MODELS["2"])
        elif choice == "3":
            models_to_download.append(TARGET_MODELS["3"])
        elif choice == "4":
            models_to_download = [TARGET_MODELS["1"], TARGET_MODELS["2"], TARGET_MODELS["3"]]
        else:
            print("[INFO] Đã hủy tiến trình.")
            sys.exit(0)

    for m_name, m_desc in models_to_download:
        pull_single_model(m_name, m_desc)

    print("\n" + "=" * 65)
    print("  [HOÀN TẤT] Quá trình tải kết thúc!")
    print("=" * 65)


if __name__ == "__main__":
    main()
