# 🏆 Discord Competitive Programming Bot — Codeforces & Sandbox Judge (Full Tiếng Việt)

Hệ thống **Discord Bot Competitive Programming toàn diện** được xây dựng bằng **Python 3.11+**, `discord.py` 2.x, tích hợp trực tiếp với **Codeforces API**, hỗ trợ 2 chế độ thi đấu/luyện tập, chấm bài trong **Docker Sandbox cô lập an toàn**, tự động phân hạng 12 bậc rank (HT1 → T8) và đồng bộ Discord Roles tự động.

Toàn bộ thông báo, kết quả, bảng xếp hạng và hồ sơ người dùng đều được thiết kế **100% Rich Embed trực quan, đẹp mắt và hỗ trợ giao diện nút bấm tương tác hoàn toàn thay thế cho việc gõ lệnh thủ công**.

---

## 📑 Mục lục

1. [Tính năng nổi bật](#1-tính-năng-nổi-bật)
2. [Hệ thống 4 Kênh Chuyên biệt (Giao diện Tương tác)](#2-hệ-thống-4-kênh-chuyên-biệt-giao-diện-tương-tác)
3. [Cấu trúc 2 Chế độ làm bài (Mode 1 & Mode 2)](#3-cấu-trúc-2-chế-độ-làm-bài)
4. [Bảng Rank & Hệ thống Auto Roles](#4-bảng-rank--hệ-thống-auto-roles)
5. [Kiến trúc thư mục dự án](#5-kiến-trúc-thư-mục-dự-án)
6. [Yêu cầu hệ thống](#6-yêu-cầu-hệ-thống)
7. [Hướng dẫn cài đặt & Khởi động nhanh (Windows & Ubuntu)](#7-hướng-dẫn-cài-đặt--khởi-động-nhanh)
8. [Vận hành Server 24/7 với systemd (Ubuntu Live Server / Linux)](#8-vận-hành-server-247-với-systemd-ubuntu-live-server--linux)
9. [C++ Native Acceleration Engine (Tối ưu Thuật toán & AI)](#9-c-native-acceleration-engine-tối-ưu-thuật-toán--ai)
10. [Hướng dẫn tạo Discord Bot & Lấy IDs](#10-hướng-dẫn-tạo-discord-bot--lấy-ids)
11. [Cấu hình `.env`](#11-cấu-hình-env)
12. [Khởi chạy Docker Sandbox cho Judge](#12-khởi-chạy-docker-sandbox-cho-judge)
13. [Danh sách Lệnh & Giao diện Nút Bấm](#13-danh-sách-lệnh--giao-diện-nút-bấm)
14. [Cơ chế Chống gian lận & AI Detection](#14-cơ-chế-chống-gian-lận--ai-detection)
15. [Sao lưu và Khôi phục Database](#15-sao-lưu-và-khôi-phục-database)
16. [Troubleshooting & FAQ](#16-troubleshooting--faq)

---

## 1. Tính năng nổi bật

* 🌐 **Đồng bộ Codeforces Real-time (Mode 1):** Tự động quét submission của thành viên sau mỗi chu kỳ (30–60s), nhận diện các verdict (Accepted, WA, TLE, MLE, CE, RE, Hacked, v.v.), chống duplicate và không spam.
* ⚖️ **In-Discord Sandboxed Judge (Mode 2):** Nộp bài trực tiếp qua kênh `SUBMIT_ID` bằng nút bấm hoặc qua modal `/submit`, chạy trên Docker container cô lập ngắt mạng (`network_mode="none"`), kiểm tra hidden tests, edge cases, phân tích độ phức tạp thuật toán và AI code detection.
* 📚 **Trình duyệt 25 Contest / Trang tại `BAITAP_ID`:** Hỗ trợ lọc theo từng phân hạng **Div. 1, Div. 2, Div. 3, Div. 4 hoặc Tất cả**, phân trang mượt mà và menu thả xuống xem đề bài & nộp bài nhanh.
* 🔗 **Tự động hướng dẫn liên kết tại `CF_ID`:** Khi bot khởi động, tự động gửi bảng hướng dẫn và nút bấm liên kết, thí sinh chỉ cần bấm nút nhập Handle và làm theo hướng dẫn mà không cần gõ lệnh.
* 👑 **Phân hạng tự động 12 bậc (HT1 → T8):** Tự động thu hồi role rank cũ và gán role rank mới theo rating; tự động phát Embed chúc mừng thăng hạng vào kênh `UP_RANK`.
* 📊 **Tách bạch Rating, Score & Performance:** Điểm tích lũy bài tập (Score), Elo Rating tương đối và Contest Performance được tính toán theo chuẩn thuật toán của Codeforces.
* 🖼️ **Thiết kế Rich Embed Đa Dạng:** Sử dụng `LOGO_ID` thống nhất cho tất cả các Embed; ngoại lệ lệnh `/profile` sử dụng chính Avatar của thành viên kèm thanh tiến độ đồ họa (progress bar).
* 🛡️ **Bảo mật đa lớp:** Ngăn chặn fork-bomb, timeout nghiêm ngặt, khống chế RAM/CPU, chống nộp trùng lặp, bảo vệ thông tin `.env`, phân quyền `OWNER_ID` với log bypass rõ ràng.

---

## 2. Hệ thống 4 Kênh Chuyên biệt (Giao diện Tương tác)

Bot được thiết kế tối ưu hóa trải nghiệm người dùng với các kênh chuyên trách riêng biệt, không bắt buộc người dùng phải nhớ hay gõ các câu lệnh:

### 1. `CHON_ID` — Kênh Giải thích 2 Chế độ làm bài
* Chuyên biệt hiển thị bảng so sánh chi tiết giữa **Mode 1 (Codeforces Sync - 100% Điểm)** và **Mode 2 (Discord Sandbox - 90% Điểm)**.
* Cung cấp bảng đối chiếu các tiêu chí về nơi làm bài, tỷ lệ điểm thưởng, quy chuẩn bảo mật và cách tính rating.

### 2. `CF_ID` — Kênh Liên kết Tài khoản Codeforces (Không dùng lệnh)
* Khi khởi động, bot tự động hiển thị bảng hướng dẫn và cụm nút bấm tương tác:
  * **`[Liên kết tài khoản Codeforces 🔗]`**: Mở Popup Modal để thí sinh nhập Handle Codeforces.
  * **`[Kiểm tra trạng thái liên kết ℹ️]`**: Tra cứu xem tài khoản đã được xác minh thành công chưa.
  * **`[Hủy liên kết tài khoản ❌]`**: Hủy liên kết với Codeforces.
* Quy trình xác minh an toàn qua mã token bí mật (`CF-VERIFY-XXXXXX`) đặt tại First Name hoặc Organization trên Codeforces.

### 3. `SUBMIT_ID` — Trạm Nộp bài Giải trực tiếp (Thay cho lệnh)
* Cung cấp nút bấm **`[Nộp bài giải (Submit Code) 📝]`** và **`[Xem lịch sử bài nộp của tôi 📜]`**.
* Khi bấm nút, mở Form Popup Modal trực quan:
  * **Mã bài:** Ví dụ `1234A` hoặc `1700B`
  * **Ngôn ngữ:** `py`, `C++`, `cpp17`, `cpp20`, `java`, `rust`, `go`, `js`, `cs`
  * **Code:** `print("Hello world")`
* Chấm điểm tự động trong Docker Sandbox và trả về kết quả Rich Embed chi tiết ngay tại kênh.

### 4. `BAITAP_ID` — Danh mục Cuộc thi & Bài tập (25 Contest / Mục)
* Trình duyệt danh mục bài tập chuẩn Codeforces:
  * **Mỗi trang hiển thị đúng 25 contest** kèm trạng thái và link trực tiếp.
  * **Bộ lọc Phân hạng (Div):** Menu thả xuống chọn xem `Tất cả`, `Div. 1`, `Div. 2`, `Div. 3`, hoặc `Div. 4`.
  * **Menu chọn nhanh Contest:** Chọn 1 trong 25 contest để xem danh sách bài tập (Problem A, B, C...) kèm mức rating và rank yêu cầu.
  * **Hệ thống nút phân trang:** `⏮️ Đầu`, `◀️ Trước`, `Trang X/Y`, `Sau ▶️`, `Cuối ⏭️`.

---

## 3. Cấu trúc 2 Chế độ làm bài

| Chế độ | Nơi nộp bài | Tỷ lệ điểm thưởng | Cơ chế chấm & Đồng bộ |
| :--- | :--- | :---: | :--- |
| **MODE 1** *(Codeforces)* | Website [Codeforces.com](https://codeforces.com) | **100%** | Bot quét `user.status` từ Codeforces API mỗi 45s, tự động ghi nhận điểm và tính rating. |
| **MODE 2** *(In-Discord)* | Kênh `SUBMIT_ID` hoặc lệnh `/submit` | **90%** | Đề lấy từ CF, code chạy trong Docker Sandbox (ngắt mạng, hidden tests, AI detection). |

---

## 4. Bảng Rank & Hệ thống Auto Roles

Hệ thống tự động đồng bộ **duy nhất 1 Role Rank chính** cho thành viên theo các mốc Rating sau:

| Bậc Rank | Tên hiển thị (Tiếng Việt) | Khoảng Rating | Icon | Biến Role trong `.env` |
| :---: | :--- | :---: | :---: | :--- |
| **HT1** | High Tier 1 (Đại Kiện Tướng Huyền Thoại) | $\ge 3000$ | 👑 | `HT1_ROLE_ID` |
| **MT1** | Master Tier 1 (Bậc Thầy Quốc Tế) | $2600 - 2999$ | 💎 | `MT1_ROLE_ID` |
| **LT1** | Low Tier 1 (Ứng Viên Kiện Tướng) | $2400 - 2599$ | 💠 | `LT1_ROLE_ID` |
| **HT2** | High Tier 2 (Chuyên Gia Cao Cấp) | $2300 - 2399$ | 🔮 | `HT2_ROLE_ID` |
| **MT2** | Master Tier 2 (Chuyên Gia) | $2100 - 2299$ | 🎖️ | `MT2_ROLE_ID` |
| **LT2** | Low Tier 2 (Thực Tập Sinh Tài Năng) | $1900 - 2099$ | 🎗️ | `LT2_ROLE_ID` |
| **T3** | Tier 3 (Hiệp Sĩ Lập Trình) | $1600 - 1899$ | ⚔️ | `T3_ROLE_ID` |
| **T4** | Tier 4 (Chiến Binh) | $1400 - 1599$ | 🛡️ | `T4_ROLE_ID` |
| **T5** | Tier 5 (Lập Trình Viên Tinh Anh) | $1200 - 1399$ | 🏹 | `T5_ROLE_ID` |
| **T6** | Tier 6 (Học Viên) | $700 - 1199$ | 🥉 | `T6_ROLE_ID` |
| **T7** | Tier 7 (Tân Binh) | $400 - 699$ | 📜 | `T7_ROLE_ID` |
| **T8** | Tier 8 (Người Mới Bắt Đầu) | $< 400$ | 🌱 | `T8_ROLE_ID` |

> [!NOTE]
> Khi người dùng thăng hạng (ví dụ từ `T5` lên `T4`), bot sẽ thu hồi role `T5`, cấp role `T4` và gửi thông báo chúc mừng vào kênh `UP_RANK`.

---

## 5. Kiến trúc thư mục dự án (Monorepo: Bot & Web)

```text
Project/
├── run_bot.bat                   # 🚀 Script khởi chạy nhanh Discord Bot
├── run_web.bat                   # 🌐 Script khởi chạy nhanh Web Server
├── README.md                     # Tài liệu tổng quan Monorepo
│
├── Bot/                          # 🤖 TOÀN BỘ MÃ NGUỒN DISCORD BOT
│   ├── bot.py                    # Entrypoint khởi tạo Bot, Cogs, Auto Setup và Bot API Bridge
│   ├── bot.db                    # CSDL SQLite cục bộ (hỗ trợ cả PostgreSQL từ xa)
│   ├── requirements.txt          # Thư viện Python dành cho Bot
│   ├── .env                      # Cấu hình môi trường Discord Bot
│   ├── .env.example              # Mẫu cấu hình môi trường
│   ├── Dockerfile                # Dockerfile chạy Bot
│   ├── docker-compose.yml        # Docker Compose chạy Bot & Database
│   ├── cogs/                     # Các module tính năng Discord Slash Commands
│   ├── config/                   # Settings & Role mapping
│   ├── database/                 # SQLAlchemy models & Repositories
│   ├── services/                 # Duel, AI worker, API Bridge, Codeforces
│   ├── judge/                    # Trình chấm bài Sandbox & Languages
│   ├── cpp_core/                 # C++ Native Acceleration Engine
│   ├── music/                    # Hệ thống Voice & Music Player
│   ├── data/                     # Cache đề thi & dữ liệu bài tập
│   └── tests/                    # Toàn bộ Unit test suites
│
└── Web/                          # 🌐 NỀN TẢNG WEB & CẦU NỐI BOT BRIDGE
    ├── app.py                    # Web Server entry point (Dashboard & API Gateway)
    ├── web_config.py             # Cấu hình Web, BOT_API_URL, BOT_API_SECRET
    ├── bridge/                   # Cầu nối liên kết Bot <-> Web (Dual-Channel Bridge)
    │   ├── __init__.py
    │   └── bot_client.py         # BotBridgeClient (REST API + Direct DB fallback)
    ├── templates/                # Giao diện HTML Cyberpunk Dashboard
    ├── requirements.txt          # Thư viện Python dành cho Web
    └── README.md                 # Hướng dẫn chi tiết phát triển Web
```

---

## 6. Yêu cầu hệ thống

* **Python:** Phiên bản `3.11` trở lên (Khuyến nghị Python 3.11 hoặc 3.12).
* **Docker:** Đã cài đặt Docker Daemon (để chạy Sandbox chấm bài Mode 2 cô lập an toàn).
* **Hệ điều hành:** Linux (Ubuntu 20.04/22.04/24.04 LTS Live Server, Debian) hoặc Windows 10/11.
* **C++ Compiler (Tùy chọn, khuyến nghị):** `g++` (GCC), `clang++` hoặc MSVC `cl` để tự động kích hoạt C++ Native Acceleration Engine (nếu không có, bot vẫn tự động chạy 100% bằng Pure-Python Fallback).
* **Phần cứng tối thiểu:** 2 CPU Cores, 2 GB RAM (Khuyến nghị 4 GB RAM nếu chạy kèm Ollama AI Local).
* **GPU (Tùy chọn):** NVIDIA CUDA hoặc AMD ROCm (tự động phát hiện và tối ưu trong `services/hardware.py`).

---

## 7. Hướng dẫn cài đặt & Khởi động nhanh

### 🚀 Cách 1: Khởi động siêu tốc chỉ 1 lệnh (`python bot.py`) — Tự động cài đặt 100%

Nhờ tích hợp bộ tự động hóa thông minh ([utils/bootstrap.py](file:///d:/Project/utils/bootstrap.py)), bạn **chỉ cần duy nhất Python** có sẵn trên máy (hỗ trợ cả Windows và Linux/Ubuntu). Không cần chạy file `.bat` phức tạp!

Chỉ cần mở Terminal / Command Prompt và gõ duy nhất:
```bash
python bot.py
```

Tiến trình sẽ **tự động kiểm tra và thực hiện từ A-Z**:
1. **Kiểm tra & tự động cài đặt Packages:** Quét `requirements.txt`. Nếu máy bạn còn thiếu bất kỳ thư viện nào (`discord.py`, `sqlalchemy`, `aiohttp`, `docker`, v.v.), bot sẽ tự động gọi `pip install` để tải về ngay lập tức.
2. **Kiểm tra & tự động biên dịch C++ Engine:** Kiểm tra file C++ Shared Library (`native_core.so` / `native_core.dll`). Nếu chưa có và máy có compiler (`g++`, `clang++`, `cl.exe`), bot sẽ tự động biên dịch. Nếu máy không có C++ compiler, bot sẽ tự động kích hoạt **Pure-Python Fallback 100%** mà không báo bất kỳ lỗi nào.
3. **Kiểm tra Node.js (Tùy chọn):** Tự động phát hiện môi trường Node.js nếu có trên máy để sẵn sàng hỗ trợ sandbox chạy mã nguồn JavaScript/TypeScript.
4. **Tự động cấu hình `.env`:** Nếu chưa có file `.env`, bot sẽ tự động sao chép từ `.env.example` và nhắc nhở bạn điền `DISCORD_TOKEN`.
5. **Tự động tạo thư mục hệ thống:** Tạo sẵn các thư mục `data/`, `logs/`, `models/`, `backups/`.
6. **Khởi động Bot ngay lập tức:** Kết nối vào Discord và vận hành bình thường!

---

### 🐧 Cách 2: Tự động 1 lệnh trên Ubuntu Live Server (`setup_ubuntu.sh`)

Dành riêng cho máy chủ Ubuntu 20.04 / 22.04 / 24.04 LTS Live Server:
```bash
bash scripts/setup_ubuntu.sh
```
*Script sẽ tự động cài đặt `build-essential`, `g++`, `gcc`, `docker.io`, `ollama`, khởi tạo Python `venv`, cài `requirements.txt`, biên dịch C++ module `native_core.so`, build Docker Sandbox image và cấp quyền chạy nền.*

---

### 🛠️ Cách 3: Cài đặt thủ công từng bước (Manual Installation)

#### Bước 1: Clone kho mã nguồn
```bash
git clone <repository_url>
cd discord-cp-bot
```

#### Bước 2: Tạo môi trường ảo (Virtual Environment)
```bash
# Trên Linux/macOS:
python3 -m venv venv
source venv/bin/activate

# Trên Windows PowerShell:
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### Bước 3: Cài đặt các thư viện phụ thuộc
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Bước 4: Biên dịch C++ Native Engine (Tùy chọn)
```bash
python cpp_core/build.py
```
*(Nếu không có compiler C++, hệ thống sẽ tự động dùng Pure-Python Engine mà không phát sinh lỗi)*.

#### Bước 5: Chạy bộ kiểm thử tự động (Unit Tests)
```bash
python -m pytest tests/ -q
```
*(Toàn bộ 157 tests đều báo `passed`)*.

---

## 8. Vận hành Server 24/7 với systemd (Ubuntu Live Server / Linux)

Để bot hoạt động liên tục 24/7 trên máy chủ Linux mà không bị tắt khi bạn đóng terminal SSH, đồng thời tự động khởi động lại sau khi máy chủ reboot hoặc khi tiến trình gặp sự cố, bạn nên thiết lập **systemd service**:

### Bước 1: Sao chép file cấu hình service
File cấu hình mẫu đã được chuẩn bị sẵn tại `scripts/discord-bot.service`:
```bash
sudo cp scripts/discord-bot.service /etc/systemd/system/discord-bot.service
```

### Bước 2: Cập nhật đường dẫn thực tế trên máy chủ
Mở file cấu hình bằng `nano`:
```bash
sudo nano /etc/systemd/system/discord-bot.service
```
Kiểm tra và sửa đổi 3 dòng sau cho khớp với username và đường dẫn project của bạn:
```ini
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/Project
ExecStart=/home/ubuntu/Project/venv/bin/python bot.py
```
*(Lưu phím: `Ctrl + O`, `Enter`, thoát: `Ctrl + X`)*.

### Bước 3: Kích hoạt và khởi chạy Service
```bash
# Nạp lại cấu hình systemd daemon
sudo systemctl daemon-reload

# Kích hoạt service tự khởi động cùng máy chủ
sudo systemctl enable discord-bot

# Khởi chạy bot ngay lập tức
sudo systemctl start discord-bot
```

### Bước 4: Kiểm tra trạng thái và theo dõi Logs trực tiếp
```bash
# Xem trạng thái bot đang chạy:
sudo systemctl status discord-bot

# Xem nhật ký (logs) real-time trực tiếp:
journalctl -u discord-bot -f

# Khởi động lại bot (ví dụ sau khi sửa code hoặc sửa .env):
sudo systemctl restart discord-bot

# Dừng bot:
sudo systemctl stop discord-bot
```

> [!TIP]
> **Chạy ngầm đơn giản không cần quyền root (dùng `tmux`):**
> Nếu bạn không có quyền `sudo` trên server:
> ```bash
> tmux new -s cpbot
> ./venv/bin/python bot.py
> ```
> *Nhấn `Ctrl + B`, sau đó nhấn `D` để ngắt kết nối màn hình mà bot vẫn chạy. Để mở lại xem: gõ `tmux attach -t cpbot`.*

---

## 9. C++ Native Acceleration Engine (Tối ưu Thuật toán & AI)

Dự án tích hợp module **C++ Native Engine** (`cpp_core/`) chuẩn C++17 giao tiếp thông qua chuẩn C-ABI `extern "C"` và Python `ctypes`, mang lại hiệu năng cao vượt trội cho các tác vụ giải thuật và phân tích mã nguồn:

### ⚡ Các thuật toán được C++ tăng tốc:
1. **`calculate_shannon_entropy`:** Tính toán độ hỗn loạn ký tự Shannon Entropy $H = -\sum p_i \log_2(p_i)$ trong độ phức tạp $O(N)$ không cấp phát thêm bộ nhớ (Zero Allocation), phục vụ phân tích phong cách mã nguồn AI và phát hiện Prompt Slop.
2. **`fast_code_metrics`:** Quét toàn bộ mã nguồn trong duy nhất 1 lần duyệt buffer thô ($O(N)$ single pass), thống kê chính xác số dòng, mật độ chú thích (comment density), dòng trống và entropy đồng thời.
3. **`fast_token_compare`:** Trình so khớp token-by-token và so sánh số thực sai số epsilon cho **Output Checker** của Judge. Thay vì dùng `split()` tạo ra hàng vạn đối tượng chuỗi trong Python gây áp lực Garbage Collector, C++ dùng con trỏ chuỗi thô tăng tốc từ **20x - 50x**.
4. **`fast_levenshtein_similarity`:** Tính toán khoảng cách chỉnh sửa Levenshtein tối ưu bộ nhớ $O(\min(N, M))$ với DP 2 hàng, phục vụ so khớp trùng lặp mã nguồn và chống gian lận trong phòng 1:1 Ranked Duel.

### 🛡️ Cơ chế Dual-Mode Graceful Fallback:
- **Ưu tiên Shared Library C++:** Hệ thống tìm nạp `native_core.so` (trên Linux) hoặc `native_core.dll` (trên Windows).
- **Graceful Fallback 100%:** Nếu máy chủ chưa biên dịch C++, file `cpp_core/bridge.py` tự động chuyển đổi sang các hàm thuần Python tương ứng với cùng kiểu dữ liệu trả về. Bot không bao giờ crash vì thiếu compiler!
- **Biên dịch thủ công bất kỳ lúc nào:**
  ```bash
  python cpp_core/build.py
  ```

---

## 10. Hướng dẫn tạo Discord Bot & Lấy IDs

### 10.1. Tạo Bot trên Discord Developer Portal
1. Truy cập [Discord Developer Portal](https://discord.com/developers/applications).
2. Nhấn **New Application**, đặt tên cho Bot (ví dụ: `CP-Judge-Bot`).
3. Vào mục **Bot** ở thanh menu bên trái:
   * Nhấn **Reset Token** và sao chép mã Token dán vào `DISCORD_TOKEN` trong `.env`.
   * Bật **Privileged Gateway Intents**:
     * ✅ **SERVER MEMBERS INTENT** (Bắt buộc để gán Role tự động).
     * ✅ **MESSAGE CONTENT INTENT** (Bắt buộc để nhận diện lệnh và tương tác).
4. Vào mục **OAuth2 ➔ URL Generator**:
   * Scopes: chọn `bot`, `applications.commands`.
   * Bot Permissions: chọn `Administrator` (hoặc tối thiểu `Manage Roles`, `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History`).
   * Mời Bot vào máy chủ Discord của bạn.

### 10.2. Bật Chế độ Nhà phát triển (Developer Mode) để lấy ID
1. Mở Discord ➔ **Cài đặt người dùng (User Settings)** ➔ **Nâng cao (Advanced)** ➔ Bật **Developer Mode**.
2. **Lấy OWNER_ID:** Chuột phải vào Avatar/tên của bạn ➔ Chọn **Sao chép ID người dùng (Copy User ID)**.
3. **Lấy Channel IDs (`CHON_ID`, `BAITAP_ID`, `UP_RANK`, `CF_ID`, `SUBMIT_ID`):** Chuột phải vào từng kênh tương ứng ➔ Chọn **Sao chép ID kênh**.
4. **Lấy Role IDs (`HT1_ROLE_ID` → `T8_ROLE_ID`):** Vào Cài đặt Server ➔ Vai trò (Roles) ➔ Chuột phải vào từng Role ➔ Chọn **Sao chép ID vai trò**.

---

## 11. Cấu hình `.env`

Sao chép file mẫu:
```bash
cp .env.example .env
```

Mở `.env` và điền thông tin:

```env
# ==============================================================================
# XÁC THỰC DISCORD BOT
# ==============================================================================
DISCORD_TOKEN=dien_token_bot_discord_tai_day
OWNER_ID=123456789012345678

# ==============================================================================
# DANH SÁCH ID CÁC KÊNH DISCORD
# ==============================================================================
CHON_ID=123456789012345678      # Kênh giải thích 2 chế độ làm bài (Mode 1 & Mode 2)
BAITAP_ID=123456789012345678    # Kênh danh mục 25 contest/trang, bộ lọc Div 1/2/3/4
UP_RANK=123456789012345678      # Kênh phát thông báo chúc mừng thăng hạng Rank
CF_ID=123456789012345678        # Kênh tự động hướng dẫn & nút bấm liên kết Codeforces
SUBMIT_ID=123456789012345678    # Kênh nộp bài trực tiếp (Mã bài, Ngôn ngữ, Code) qua nút bấm

# Đường dẫn ảnh Logo của Bot (Hiển thị trên tất cả Embeds)
LOGO_ID=https://raw.githubusercontent.com/codeforces/images/master/logo.png

# ==============================================================================
# DISCORD RANK ROLES (12 BẬC TỰ ĐỘNG)
# ==============================================================================
HT1_ROLE_ID=111111111111111111
MT1_ROLE_ID=222222222222222222
LT1_ROLE_ID=333333333333333333

HT2_ROLE_ID=444444444444444444
MT2_ROLE_ID=555555555555555555
LT2_ROLE_ID=666666666666666666

T3_ROLE_ID=777777777777777777
T4_ROLE_ID=888888888888888888
T5_ROLE_ID=999999999999999999
T6_ROLE_ID=101010101010101010
T7_ROLE_ID=121212121212121212
T8_ROLE_ID=131313131313131313

# ==============================================================================
# CƠ SỞ DỮ LIỆU & CODEFORCES
# ==============================================================================
DATABASE_URL=sqlite+aiosqlite:///bot.db
CF_API_KEY=
CF_API_SECRET=
CF_SYNC_INTERVAL_SECONDS=45

# ==============================================================================
# TRÌNH CHẤM BÀI SANDBOX & GIỚI HẠN
# ==============================================================================
JUDGE_TIMEOUT=5
JUDGE_MEMORY_LIMIT=256
JUDGE_CPU_LIMIT=2
JUDGE_PIDS_LIMIT=64
DOCKER_SANDBOX_IMAGE=cp-sandbox:latest
USE_DOCKER_SANDBOX=true

MAX_CODE_LENGTH=65536
SUBMIT_COOLDOWN_SECONDS=15
AI_SUSPICION_THRESHOLD=65
LOG_LEVEL=INFO
```

---

## 12. Khởi chạy Docker Sandbox cho Judge

### Bước 1: Build Docker Sandbox Image
```bash
docker build -t cp-sandbox:latest -f judge/Dockerfile.sandbox .
```

### Bước 2: Khởi động Bot
```bash
python bot.py
```

*Khi bot khởi động, bot sẽ tự động thiết lập và gửi bảng điều khiển tương tác vào cả 4 kênh `CHON_ID`, `CF_ID`, `SUBMIT_ID`, và `BAITAP_ID`!*

---

## 13. Danh sách Lệnh & Giao diện Nút Bấm

### 🎮 Giao diện Tương tác tại 4 Kênh Cố định:
* **Kênh `CF_ID`:** Nút `[Liên kết tài khoản Codeforces 🔗]`, `[Kiểm tra trạng thái liên kết ℹ️]`, `[Hủy liên kết ❌]`.
* **Kênh `SUBMIT_ID`:** Nút `[Nộp bài giải (Submit Code) 📝]` mở form Modal nhập **Mã bài, Ngôn ngữ, Code** và nút `[Xem lịch sử bài nộp của tôi 📜]`.
* **Kênh `BAITAP_ID`:** Menu chọn Div 1/2/3/4, Menu chọn 25 contest, các nút phân trang `⏮️ Đầu`, `◀️ Trước`, `Sau ▶️`, `Cuối ⏭️`.
* **Kênh `CHON_ID`:** Bảng giải thích chi tiết luật chơi, điểm số và bảo mật giữa 2 Mode.

### 👤 Lệnh Slash Commands hỗ trợ:
* `/profile [user]`: Xem hồ sơ chi tiết (Avatar cá nhân, Rating, Rank, Tỷ lệ AC, thanh tiến độ đồ họa).
* `/rating`: Xem nhanh rating hiện tại và điểm cần để lên rank.
* `/leaderboard [sort_by]`: Bảng xếp hạng Server phân trang.
* `/problem <problem_id>`: Tra cứu bài tập và rank yêu cầu.
* `/help`: Hướng dẫn sử dụng và bảng 12 bậc rank.
* `/admin sync_cf` / `force_update_roles` / `reset_user` / `reload` / `view_logs`: Các lệnh quản trị dành riêng cho Owner.

---

## 14. Cơ chế Chống gian lận & AI Detection

1. **Docker Sandbox Isolation:** Ngắt toàn bộ kết nối mạng (`network_mode="none"`), giới hạn CPU, RAM, thời gian chạy, process tối đa (`pids_limit=64`) triệt tiêu nguy cơ Fork-bomb, user không đặc quyền.
2. **AI Suspicion Scoring (0–100):** Tự động phát hiện comment giải thích kiểu ChatGPT, docstring bất thường, markdown leaks để gắn cờ bài nộp và ghi log.
3. **C++ Shannon Entropy Scanner:** Đo độ hỗn loạn của chuỗi mã nguồn để phân biệt văn phong giải thích của LLM với phong cách code ngắn gọn của thí sinh CP.
4. **Phân tích độ phức tạp tĩnh:** Duyệt cây cú pháp AST cảnh báo thuật toán duyệt trâu $O(N^2), O(N^3)$ khi dữ liệu $N \ge 100,000$.

---

## 15. Sao lưu và Khôi phục Database

```bash
# Sao lưu SQLite
cp bot.db "backups/bot_backup_$(date +%Y%m%d_%H%M%S).db"

# Khôi phục
cp backups/bot_backup_YYYYMMDD_HHMMSS.db bot.db
```

---

## 16. Troubleshooting & FAQ

**Q: Làm sao để bot tự động đăng lại bảng điều khiển nếu kênh bị xóa tin nhắn?**  
*A: Bot Owner có thể dùng các lệnh `/post_mode_panel`, `/post_baitap_panel` hoặc khởi động lại bot, bot sẽ tự động kiểm tra và đăng lại nếu kênh trống.*

**Q: Khi thí sinh bấm nút Nộp bài tại `SUBMIT_ID`, kết quả hiển thị ở đâu?**  
*A: Kết quả chấm bài Sandbox chi tiết sẽ được gửi ngay tại kênh `SUBMIT_ID` dưới dạng Rich Embed trực quan.*

