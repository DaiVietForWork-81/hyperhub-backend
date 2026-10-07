# 🚀 HyperHub • Competitive Programming & Learning Ecosystem

> **LEARN • CHILL • CONNECT**  
> Nền tảng học thuật, thi đấu thuật toán sinh tồn 1:1, thư viện tài liệu toàn diện và không gian kết nối cộng đồng học tập Việt Nam.

---

## ⚡ HƯỚNG DẪN KHỞI CHẠY NHANH (QUICK START)

Khởi chạy trung tâm điều phối toàn hệ thống chỉ với **1 lệnh duy nhất** từ thư mục gốc:

```powershell
python main.py
```

Trình quản lý sẽ hiển thị menu tương tác 3 chế độ:

```text
============================================================
              HYPERHUB SYSTEM CONTROLLER                    
============================================================
 [1]  Khởi chạy Discord Bot (Độc lập)
 [2]  Khởi chạy Giao diện Web (Landing Page & API Bridge)
 [3]  Khởi chạy Đồng thời CẢ HAI (Bot + Web Server)
 [0]  Thoát
============================================================
```

- **Lựa chọn [1]:** Khởi động riêng Discord Bot (với Sandbox chấm bài 1:1, hệ thống Elo, tính năng học tập & giải trí).
- **Lựa chọn [2]:** Khởi động riêng Web Server tại cổng `5000`.
  - 🌐 Mở trình duyệt truy cập: **`http://localhost:5000`** hoặc **`http://127.0.0.1:5000`**
- **Lựa chọn [3]:** Khởi động đồng thời cả Bot và Web trên 2 luồng song song.

---

## 🛠️ YÊU CẦU MÔI TRƯỜNG (PREREQUISITES)

- **Python:** Phiên bản 3.10 trở lên.
- **Node.js:** Phiên bản 18+ (Dành cho việc chỉnh sửa và build Frontend React/Vite trong `Web/`).
- **Thư viện Python cần thiết:**
  ```powershell
  pip install -r Bot/requirements.txt
  pip install -r Web/requirements.txt
  ```

---

## 📁 CẤU TRÚC THƯ MỤC DỰ ÁN

```text
d:\Project/
├── main.py                  # Điểm khởi chạy trung tâm (Interactive Launcher)
├── README.md                # Tài liệu hướng dẫn này
├── .gitignore               # Bộ lọc bảo mật Git (loại trừ secrets, database, node_modules)
│
├── Bot/                     # Nguồn Discord Bot HyperHub
│   ├── bot.py               # File chạy chính của bot
│   ├── cogs/                # Các phân hệ lệnh (Đấu trường 1:1, Pomodoro, Học tập, Music,...)
│   ├── judge/               # Trình Sandbox chấm thuật toán mili-giây
│   ├── config/              # Cấu hình hệ thống bot
│   └── requirements.txt     # Danh sách thư viện Python của Bot
│
└── Web/                     # Nền tảng Web độc lập HyperHub
    ├── app.py               # Web Server Aiohttp & Multi-channel API Gateway (Port 5000)
    ├── package.json         # Cấu hình npm & dependencies Vite + React 19 + Tailwind v4
    ├── src/                 # Mã nguồn React Frontend (SPA)
    │   ├── components/      # Các component (Hero, HowItWorks, ArenaPreview, FAQ, LofiPlayer,...)
    │   ├── hooks/           # useTheme (Dark/Light mode)
    │   ├── styles/          # globals.css (Cosmic text aura, fluid scaling, light/dark themes)
    │   └── data/            # Cấu hình site, danh sách môn học, đội ngũ phát triển
    ├── dist/                # Bản build sản xuất tối ưu hóa (được app.py phục vụ trực tiếp)
    └── requirements.txt     # Danh sách thư viện Python của Web
```

---

## 🌟 TÍNH NĂNG NỔI BẬT

1. **Giao Diện Web Hiện Đại (Cyberpunk & Clean Glass Slate):**
   - Hỗ trợ chuyển đổi chế độ **Sáng / Tối (Dark & Light Mode)** với nút Sun/Moon trên Navbar.
   - Hiệu ứng **Aura phát sáng + Dòng chảy cực quang bên trong chữ** (`HyperHub`, `LEARN • CHILL • CONNECT`).
   - Lộ trình 4 chặng **"Cách Hoạt Động"** với hiệu ứng **Zoom Card** mượt mà khi hover/chọn.
   - Trình phát nhạc **Lofi Chill Lounge** tích hợp Web Audio API phát hợp âm thư giãn học tập.
   - Thanh menu thông minh tự động trượt xuống khi con trỏ chuột đến gần đỉnh màn hình.
   - Tự động co giãn theo mọi tỷ lệ màn hình (Zoom 75% - 150%, chia đôi màn hình hay toàn màn hình).

2. **Đấu Trường Sinh Tồn 1:1 (Discord Bot & Web):**
   - Đấu trực tiếp trong phòng riêng biệt với cơ chế sinh tồn 2 mạng sống (❤️❤️).
   - Sandbox chấm code C++ / Python siêu tốc mili-giây.
   - Tự động cấp Rank Role Discord tương ứng theo điểm Elo.

3. **Hỗ Trợ Đa Môn Học:**
   - Không chỉ dành cho chuyên Tin: Hỗ trợ tài liệu và trao đổi học tập cho Toán, Ngữ Văn, Tiếng Anh, Vật Lý, Hóa Học, Sinh Học, Lịch Sử, Địa Lý, Ngoại Ngữ.

---

## 🌐 KẾT NỐI VÀ LIÊN KẾT TÊN MIỀN (CUSTOM DOMAIN)

- **Triển khai qua VPS:** Cấu hình bản ghi A trỏ về IP của VPS và dùng Nginx / Caddy reverse proxy vào cổng `5000`.
- **Triển khai qua Vercel:** Kết nối repo GitHub với Vercel, trỏ bản ghi A về `76.76.21.21` và CNAME `cname.vercel-dns.com`.
- **Triển khai trực tiếp từ máy cá nhân:** Sử dụng Cloudflare Tunnel (`cloudflared tunnel --url http://localhost:5000`) để có HTTPS miễn phí mà không cần mở port modem.

---

## 👥 ĐỘI NGŨ HYPERHUB
- **Dai Viet** • Owner & Founder
- **Lê Minh** • Co-Founder
- **GithubZ** • Co-Founder
- **Nguyễn Duy** • Co-Founder
- **Nguyễn Khải** • Admin
