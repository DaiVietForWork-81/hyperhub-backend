#!/usr/bin/env bash
# ==============================================================================
# scripts/setup_ubuntu.sh -- Script Tự Động Cài Đặt và Tối Ưu Cho Ubuntu Server
# Hỗ trợ: Ubuntu 20.04 / 22.04 / 24.04 LTS (x86_64 / ARM64)
# ==============================================================================
set -e

# Màu sắc thông báo
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}==============================================================================${NC}"
echo -e "${GREEN}   🚀 KHỞI TẠO VÀ TỐI ƯU HÓA DISCORD CP BOT CHO UBUNTU LIVE SERVER${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo -e "Thư mục dự án: ${BLUE}$SCRIPT_DIR${NC}\n"

# 1. Cập nhật apt và cài đặt các gói hệ thống cần thiết
echo -e "${YELLOW}[1/6] Cập nhật hệ thống và cài đặt dependencies (apt)...${NC}"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    gcc \
    g++ \
    curl \
    git \
    ffmpeg \
    libopus0 \
    tesseract-ocr \
    tesseract-ocr-vie \
    docker.io \
    pciutils

# 2. Cấu hình quyền Docker & GPU (render, video) cho user hiện tại
echo -e "\n${YELLOW}[2/6] Thiết lập dịch vụ Docker và cấp quyền phần cứng GPU...${NC}"
sudo systemctl enable --now docker
echo -e "Cấp quyền truy cập Docker và GPU (render, video) cho user ${BLUE}$USER${NC}..."
sudo usermod -aG docker,render,video "$USER" || sudo usermod -aG docker "$USER"
echo -e "${GREEN}✅ Đã cấp quyền docker và render/video.${NC}"

# Kiểm tra card đồ họa AMD trên hệ thống
if lspci | grep -Ei 'vga|3d|display' | grep -qi 'amd\|radeon'; then
    echo -e "${CYAN}🔍 Phát hiện card đồ họa AMD Radeon trên máy chủ!${NC}"
    echo -e "  - Với AMD đời mới (RX 6000/7000/ROCm): Ollama sẽ tự động kích hoạt ROCm tăng tốc."
    echo -e "  - Nếu dùng card AMD phổ thông cần ép phiên bản ROCm, bạn có thể điền vào .env:"
    echo -e "    ${YELLOW}HSA_OVERRIDE_GFX_VERSION=10.3.0${NC} (cho RX 6000) hoặc ${YELLOW}11.0.0${NC} (cho RX 7000)"
    echo -e "  - Với card AMD cũ (VRAM <= 2GB): Bot sẽ tự động chạy CPU fallback an toàn để chống lỗi rác chữ."
fi

# 3. Kiểm tra hoặc cài đặt Ollama (cho AI Local / Qwen)
echo -e "\n${YELLOW}[3/6] Kiểm tra dịch vụ Ollama...${NC}"
if command -v ollama &>/dev/null; then
    echo -e "${GREEN}✅ Ollama đã được cài đặt sẵn tại: $(which ollama)${NC}"
else
    echo -e "Đang tự động cài đặt Ollama cho Linux (tự động nhận diện NVIDIA CUDA & AMD ROCm)..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo -e "${GREEN}✅ Đã cài đặt Ollama thành công!${NC}"
fi

# 4. Thiết lập môi trường ảo Python
echo -e "\n${YELLOW}[4/6] Khởi tạo Python Virtual Environment (venv)...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✅ Đã tạo thư mục venv.${NC}"
fi

echo "Đang nâng cấp pip và cài đặt thư viện Python từ requirements.txt..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
echo -e "${GREEN}✅ Cài đặt dependencies thành công!${NC}"

# 5. Biên dịch C++ Native Acceleration Engine (native_core.so)
echo -e "\n${YELLOW}[5/7] Biên dịch C++ Native Acceleration Engine...${NC}"
./venv/bin/python3 cpp_core/build.py || python3 cpp_core/build.py || echo -e "${YELLOW}⚠️ Tiếp tục với Pure-Python Fallback.${NC}"

# 6. Build Docker Sandbox Image cho trình chấm Mode 2
echo -e "\n${YELLOW}[6/7] Build Docker Sandbox Image (cp-sandbox:latest)...${NC}"
if [ -f "judge/Dockerfile.sandbox" ]; then
    sudo docker build -t cp-sandbox:latest -f judge/Dockerfile.sandbox .
    echo -e "${GREEN}✅ Đã build image cp-sandbox:latest thành công!${NC}"
else
    echo -e "${RED}⚠️ Không tìm thấy judge/Dockerfile.sandbox!${NC}"
fi

# 7. Kiểm tra file cấu hình .env
echo -e "\n${YELLOW}[7/7] Kiểm tra file cấu hình .env...${NC}"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠️ Đã sao chép .env.example thành .env. Vui lòng mở file .env để điền DISCORD_TOKEN và các ID kênh!${NC}"
    fi
else
    echo -e "${GREEN}✅ File .env đã tồn tại.${NC}"
fi

# Tạo sẵn các thư mục lưu trữ
mkdir -p data logs models backups

echo -e "\n${CYAN}==============================================================================${NC}"
echo -e "${GREEN}   ✨ HOÀN TẤT THIẾT LẬP MÔI TRƯỜNG TRÊN UBUNTU SERVER!${NC}"
echo -e "${CYAN}==============================================================================${NC}"
echo -e "\n${YELLOW}Các bước tiếp theo:${NC}"
echo -e "1. Chỉnh sửa cấu hình:         ${BLUE}nano .env${NC}"
echo -e "2. Tải mô hình AI vào models/: ${BLUE}./venv/bin/python download_model.py${NC}"
echo -e "3. Chạy thử nghiệm Bot:        ${BLUE}./venv/bin/python bot.py${NC}"
echo -e "4. Cài đặt chạy nền 24/7:      Xem file ${BLUE}scripts/discord-bot.service${NC}\n"
