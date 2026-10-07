#!/usr/bin/env bash
# ==============================================================================
# download_model.sh -- Tải mô hình AI vào thư mục models/ trên Linux/Ubuntu Server
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  [AI] TẢI MÔ HÌNH CHO UBUNTU / LINUX SERVER"
echo "============================================================"

# Kiểm tra Python 3
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "[LỖI] Không tìm thấy Python! Vui lòng cài đặt: sudo apt install python3"
    exit 1
fi

# Chạy tải model với cờ UTF-8
$PYTHON_CMD -X utf8 download_model.py

echo ""
echo "Hoàn tất! Model đã được lưu trữ an toàn trong thư mục models/."
