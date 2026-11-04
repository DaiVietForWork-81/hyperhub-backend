# 🌌 Orbit | Vietnam — Discord Bot & Hybrid Cloud Bridge

Hệ thống **Discord Bot học thuật & quản trị kho đề thi thông minh** của cộng đồng **Orbit | Vietnam**, xây dựng trên **Python 3.11+**, `discord.py` 2.x, kết hợp **SQLite FTS5 (`unicode61`) + C++ Native Core** và đồng bộ 2 chiều theo thời gian thực với **Turso Cloud (libSQL)** cùng **Vercel Serverless Web Platform**.

- **Web Platform (24/7):** https://orbit-psi-black.vercel.app
- **Máy chủ Discord chính:** `Orbit | Vietnam` (Guild ID: `1532265330079174697`)
- **Chế độ vận hành:** Zero-AI / Tiết kiệm RAM (100% thuật toán xác định + SQLite FTS5 + Turso Cloud Sync)

---

## 🏗️ 1. Kiến trúc Hybrid Cloud (Bot ↔ Turso Cloud ↔ Vercel)

Để đảm bảo **Web luôn hoạt động 24/7 kể cả khi máy chạy Bot tắt** và **giảm tối đa tải băng thông/CPU cho máy chạy Bot**:

```text
 Discord Gateway ◄──► Orbit Discord Bot (Bot/bot.py + API Bridge :8080)
                              │
         Write-Through Cache  │  Telemetry & RPC Queue (mỗi 2.5s - 20s)
         + Background Prewarm ▼
                      Turso Cloud (libSQL)
           (documents_archive, study_profiles,
            bot_kv_store, bot_rpc_queue, linked_accounts)
                              ▲
                              │
               Vercel Serverless (Web/api/index.js)
                     + Vercel Edge CDN Cache
```

### Những việc Bot thực hiện:
1. **Tiếp nhận & Thẩm định Đề thi (`cogs/doc_intake.py` + `DocInspector`):**
   - Quét file PDF/DOCX nộp qua kênh Discord hoặc từ Web Upload Portal.
   - Bóc tách văn bản (`raw_text`), câu hỏi trắc nghiệm (`Câu 1..50`), bảng đáp án, nhận diện môn học, khối lớp (`10/11/12/THPT`), trường/sở GD&ĐT và chống trùng lặp bằng SHA-256.
2. **Tra cứu & Luyện đề trực tiếp trên Discord (`cogs/doc_search.py`, `cogs/study_practice_cog.py`):**
   - Tìm kiếm toàn văn tốc độ cao qua SQLite FTS5 (`documents_fts`).
   - Lệnh `/luyende` (bốc đề & luyện trắc nghiệm trên Discord) và `/chuoi` (điểm danh nhận `+50 XP`, duy trì chuỗi ngày học `🔥 Streak` đồng bộ 100% với Web).
3. **Đồng bộ Thương hiệu & Logo Tự động (`bot.py`):**
   - Tự động đặt trạng thái `Watching Orbit | Vietnam`.
   - Tự động đồng bộ tên máy chủ Discord thành `Orbit | Vietnam`.
   - Tự động kiểm tra mã băm SHA-256 của `LOGO_ID.png` khi khởi động: nếu phát hiện logo mới, tự động cập nhật **Avatar của Bot** và **Icon của Máy chủ Discord** (lưu dấu tại `.logo_synced_hash` để tránh rate-limit).
4. **Write-Through Cache & Pre-warm cho Vercel (`services/api_bridge.py`):**
   - Tự động đẩy ngầm link Discord CDN (`doc_cdn_{id}`) và `raw_text` của kho đề lên Turso Cloud theo từng lô nhỏ để Vercel Edge CDN phục vụ đọc/tải PDF và làm đề 24/7 mà không tốn băng thông máy cá nhân.

---

## ⚡ 2. Hướng dẫn Khởi chạy Nhanh

### Khởi chạy Discord Bot + API Bridge (Cổng `8080`):
```powershell
cd d:\Project\Bot
python bot.py
```
Hoặc dùng script tại thư mục gốc:
```powershell
.\start_hyperhub.bat
```

### Dừng Bot an toàn:
```powershell
.\stop_hyperhub.bat
```

---

## 📁 3. Cấu trúc Thư mục `Bot/`

```text
Bot/
├── bot.py                        # Entrypoint Discord Bot, tự đồng bộ Logo/Tên Server & nạp Cogs
├── LOGO_ID.png                   # Logo thương hiệu chuẩn Orbit | Vietnam (1024x1024)
├── requirements.txt              # Thư viện Python của Bot
├── cogs/
│   ├── doc_intake.py             # Tiếp nhận, thẩm định 3+1 và lưu trữ đề thi
│   ├── doc_search.py             # Tìm kiếm đề thi FTS5 & điều hướng kho đề
│   ├── study_practice_cog.py     # Luyện đề (/luyende) & Chuỗi ngày học (/chuoi)
│   ├── exam_generator_cog.py     # Công cụ khảo thí & ngân hàng đề
│   ├── info_board_cog.py         # Bảng thông tin máy chủ Orbit | Vietnam
│   ├── server_defense.py         # Bảo vệ máy chủ, chống raid/spam
│   ├── link_scanner.py           # Quét link độc hại
│   ├── admin.py                  # Lệnh quản trị máy chủ
│   └── help.py                   # Cẩm nang hướng dẫn lệnh
├── services/
│   ├── api_bridge.py             # HTTP API (:8080) + Turso Relay Loop + Pre-warm Cache
│   ├── system_sync_service.py    # Thông báo khởi động & đồng bộ Git commit
│   ├── gdrive_importer.py        # Nhập đề từ Google Drive
│   └── backup_service.py         # Sao lưu cấu trúc máy chủ & CSDL
├── database/
│   ├── database.py               # Quản lý SQLite cục bộ (WAL + FTS5)
│   └── turso_client.py           # Client đồng bộ bất đồng bộ với Turso Cloud (libSQL)
├── config/
│   └── settings.py               # Đọc cấu hình từ .env
└── utils/
    ├── embeds.py                 # Bộ khung Rich Embed chuẩn Orbit | Vietnam
    └── logger.py                 # Ghi nhật ký hệ thống (logs/bot.log)
```

---

## 🔐 4. Cấu hình `.env` chính

| Biến | Giải thích |
| :--- | :--- |
| `DISCORD_TOKEN` | Token hoạt động của Bot Discord |
| `OWNER_ID` | Discord ID của chủ sở hữu hệ thống |
| `GUILD_ID` | ID máy chủ Discord chính (`1532265330079174697`) |
| `TURSO_DATABASE_URL` | URL kết nối Turso Cloud (`https://...turso.io`) |
| `TURSO_AUTH_TOKEN` | Token xác thực Turso Cloud |
| `BOT_API_HOST` / `BOT_API_PORT` | Địa chỉ và cổng API Bridge cục bộ (mặc định `0.0.0.0:8080`) |
| `BOT_API_SECRET` | Khóa bảo mật xác thực giữa Web và Bot |
| `EMBEDDING_ENABLED` | `false` (Mặc định tắt nạp model ONNX để tiết kiệm RAM, dùng 100% FTS5) |
