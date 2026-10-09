# 📚 TÀI LIỆU TỔNG HỢP CHI TIẾT TẤT CẢ CÁC HẠNG MỤC HỆ THỐNG HYPERHUB
> **Dự án:** Hệ sinh thái Học tập, Thi đấu & Quản lý Tài liệu Thi cử HyperHub  
> **Cấu trúc:** Discord Bot (Python / C++ Core) + Web Portal (React / TypeScript / Vite / Tailwind)  
> **Phiên bản triển khai:** Production trên Vercel ([https://hyperhub-one.vercel.app](https://hyperhub-one.vercel.app))

---

## MỤC LỤC
1. [HỆ THỐNG DISCORD BOT (BACKEND & ENGINE)](#1-hệ-thống-discord-bot-backend--engine)
   - 1.1. Cấu hình Vai trò & Khối lớp (Role System)
   - 1.2. Phân quyền Kênh & Khóa Chat (Channel Permissions)
   - 1.3. API Bridge Service (`services/api_bridge.py`)
   - 1.4. Động cơ phân tích tài liệu DocInspector (`DocInspector/`)
   - 1.5. Lõi tăng tốc C++ Native Engine (`cpp_core/`)
   - 1.6. Cơ sở dữ liệu SQLite & FTS5 Full-Text Search (`database/`)
   - 1.7. Hệ thống Nạp Google Drive an toàn (`services/gdrive_importer.py`)
   - 1.8. Quản lý kho lưu trữ tệp đề thi (Storage & Archive)
2. [HỆ THỐNG WEB PORTAL (FRONTEND & CLIENT)](#2-hệ-thống-web-portal-frontend--client)
   - 2.1. Phân quyền & Điều hướng Quản trị (Admin Access Control)
   - 2.2. Bảng điều khiển Quản trị viên (`src/components/AdminPanel.tsx`)
   - 2.3. Bảng điều khiển người dùng (`src/components/Dashboard.tsx`)
   - 2.4. Trạm nộp đề thông minh (`src/components/DocUploadZone.tsx`)
   - 2.5. Tủ sách cá nhân & Lưu đề yêu thích (`utils/bookmarkStorage.ts`)
   - 2.6. Xác thực Discord OAuth2 Bảo mật (`utils/discordAuth.ts`)
   - 2.7. Giao diện Trang chủ & Thành phần tương tác
3. [BẢO MẬT & PHÒNG THỦ MÃ NGUỒN (SECURITY HARDENING)](#3-bảo-mật--phòng-thủ-mã-nguồn-security-hardening)
4. [BẢNG TỔNG HỢP ENDPOINT REST API](#4-bảng-tổng-hợp-endpoint-rest-api)
5. [NHẬT KÝ NÂNG CẤP PHIÊN VẬN HÀNH (MỞ PUBLIC + HEADLESS + TIẾT KIỆM RAM)](#5-nhật-ký-nâng-cấp-phiên-vận-hành-mở-public--headless--tiết-kiệm-ram)

---

# 1. HỆ THỐNG DISCORD BOT (BACKEND & ENGINE)

### 1.1. Cấu hình Vai trò & Khối lớp (Role System)
- **Xóa bỏ triệt để 13 Role Tier cũ không còn sử dụng**:
  - `🏆RHT1` (`1541025570010431518`)
  - `👑 HT1 - Freedom` (`1534128842866950164`)
  - `💎MT1 - Freedom` (`1534128844880220211`)
  - `🏆LT1 - Freedom` (`1543471701373886525`)
  - `🔱HT2 - Freedom` (`1543471743086100591`)
  - `⚜️MT2 - Freedom` (`1543471762421973042`)
  - `🛡️LT2 - Freedom` (`1543471773885009960`)
  - `💠T3 - Freedom` (`1543471715420606474`)
  - `🔷T4 - Freedom` (`1543471785138458714`)
  - `🔶T5 - Freedom` (`1543471796458758144`)
  - `⭐T6 - Freedom` (`1543471811012861953`)
  - `⭐T7 - Freedom` (`1543471821603733605`)
  - `⭐T8 - Freedom` (`1543471838619901973`)
- **Tạo mới 7 Role Khối Lớp chuẩn học thuật** (cấu hình `hoist=True` để hiển thị thành danh mục riêng trên danh sách thành viên):
  - 🎓 `Lớp 12` | ID: `1556215389707309077` | Màu đỏ: `#EF4444`
  - 📚 `Lớp 11` | ID: `1556215396313473095` | Màu cam: `#F97316`
  - 📖 `Lớp 10` | ID: `1556215400549720064` | Màu hổ phách: `#F59E0B`
  - ✏️ `Lớp 9`  | ID: `1556215404865519647` | Màu lục: `#10B981`
  - 📐 `Lớp 8`  | ID: `1556215410595074058` | Màu cyan: `#06B6D4`
  - 🔬 `Lớp 7`  | ID: `1556215415212867654` | Màu lam: `#3B82F6`
  - 🌱 `Lớp 6`  | ID: `1556215419377942599` | Màu tím: `#8B5CF6`
- **Đổi tên Separator Role**: ID `1549766902652338177` thành `╭─── KHỐI LỚP ───╮`.
- **Hệ thống 5 Role Quản Trị Viên cao cấp**:
  1. `👑 Owner` (`1534128845198987438`)
  2. `👑 Co-Owner` (`1534132250088833024`)
  3. `⚡ Administrator` (`1532383529353089085`)
  4. `HyperHub (Role Bot)` (`1536308367231025252`)
  5. `🛡️ Moderator` (`1534146463246974995`)
  - Tài khoản Bot Owner: `1529864608813416449`.

---

### 1.2. Phân quyền Kênh & Khóa Chat (Channel Permissions)
- Áp dụng cấu hình quyền Overwrite trên toàn bộ 21 kênh thuộc 2 danh mục:
  - `1534147129197723749` (📢 THÔNG BÁO)
  - `1534147951797080174` (📚 TÀI LIỆU)
- **Cấm chat / Cấm tạo thread** đối với:
  - `@everyone` (`1532265330079174697`)
  - `🌱 Học sinh` (`1532397716598948050`)
  - `🧪 Test` (`1549053772553256973`)
- **Ngoại lệ bảo lưu quyền**:
  - Kênh `#📄・nộp-tài-liệu` (`1535278288828633138`): Cho phép học sinh gửi tin nhắn và đính kèm tệp để nộp đề thi.
  - Bot `HyperHub`: Cấp quyền `SEND_MESSAGES`, `ATTACH_FILES`, `EMBED_LINKS` để phát đề và forward tài liệu.

---

### 1.3. API Bridge Service (`services/api_bridge.py`)
- Dịch vụ HTTP REST Server nền tảng asynchronous aiohttp chạy ngầm cùng Bot.
- **Xác thực quyền Quản trị (`_verify_admin_access`)**:
  - Hỗ trợ Bearer Token từ Discord OAuth2 và Secret Key (`BOT_API_SECRET`).
  - Cache thông tin người dùng Discord với TTL 300 giây.
  - Tự động đối chiếu Guild Member, kiểm tra Owner ID, quyền Administrator hoặc sự hiện diện của 1 trong 5 Admin Roles.
- **Các Endpoint Quản Trị Mới**:
  - `GET /api/admin/check`: Kiểm tra quyền hạn quản trị viên.
  - `GET /api/admin/bans`: Đọc danh sách bị ban từ máy chủ Discord kèm User ID, tên, avatar, lý do.
  - `POST /api/admin/ban`: Cấm người dùng kèm lý do và số ngày xóa tin nhắn cũ (0 - 7 ngày).
  - `POST /api/admin/unban`: Gỡ cấm người dùng trên Discord.
  - `POST /api/admin/kick`: Kick thành viên khỏi máy chủ.
  - `POST /api/admin/timeout`: Timeout / Mute người dùng theo thời gian linh hoạt (lên đến 28 ngày) hoặc Unmute khi duration = 0.
  - `DELETE /api/admin/documents/{id}`: Xóa đề thi vĩnh viễn (xóa bản ghi CSDL, xóa file trên ổ cứng, xóa tin nhắn đăng tải trên Discord).
  - `PATCH /api/admin/documents/{id}`: Sửa tiêu đề, môn, lớp và **ghi chú đề thi (`notes`)**.
- **CORS Middleware nâng cao**: Cho phép các phương thức `GET, POST, OPTIONS, HEAD, DELETE, PATCH, PUT`.
- **Thêm trường `notes`**: Tích hợp trường ghi chú vào API lấy danh sách đề (`GET /api/documents`) và API phát đề ngẫu nhiên (`GET /api/documents/request_exam`).

---

### 1.4. Động cơ phân tích tài liệu DocInspector (`DocInspector/`)
- **Tự động nhận diện môn học, khối lớp và thể loại đề**:
  - 5 thể loại chuẩn: Đề Thường, Đề HSG, Đề Chuyên, Đề Quốc Tế, Đề Chung.
  - Bóc tách số câu hỏi, số trang, độ tin cậy.
- **Trích xuất thông tin học thuật nâng cao**:
  - Regex Năm học (`RE_ACADEMIC_YEAR`): Nhận diện các mẫu năm học `2024-2025`, `HK1 2024`, `Kì 1 năm 2025`, v.v.
  - Regex Trường / Sở GD&ĐT (`RE_SCHOOL_PROVINCE`): Nhận diện nguồn ra đề (Sở GD&ĐT, Trường THPT Chuyên...).
- **Tối ưu tiền xử lý OCR hình ảnh (`_preprocess_image_for_ocr`)**:
  - Pipeline xử lý thuần PIL: Chuyển grayscale, upscale ảnh quét có độ phân giải thấp, tăng độ tương phản (contrast boost x2.0), áp dụng bộ lọc Sharpen làm nét viền chữ, nhị phân hóa (adaptive threshold).
  - Cấu hình Tesseract OCR tối ưu: `--oem 3 --psm 6 -l vie+eng`.
- **Cơ chế Debounce Panel Updates**:
  - Đặt khoảng đệm 3 giây chống rate limit khi cập nhật bảng giao diện nộp bài `#📄・nộp-tài-liệu`.
- **Phát hiện trùng lặp thời gian thực**:
  - Băm SHA-256 nội dung tệp, đối chiếu trong CSDL, cảnh báo trùng lặp và tự động xóa tin nhắn cảnh báo sau 10 giây.

---

### 1.5. Lõi tăng tốc C++ Native Engine (`cpp_core/`)
- Biên dịch thư viện chia sẻ `native_core.dll` với GCC/G++ (`-O3 -shared -std=c++20`).
- **Hàm `fast_sha256`**:
  - Triển khai thuật toán mã băm mật mã học SHA-256 thuần C++ độc lập, không phụ thuộc OpenSSL, cho tốc độ băm tệp cực nhanh.
- **Hàm `fast_detect_magic_bytes`**:
  - Nhận dạng cấu trúc tệp qua header signature: PDF (`%PDF`), Office Open XML (`PK\x03\x04` - DOCX, XLSX, PPTX), OLE2 (`\xD0\xCF\x11\xE0` - DOC), PNG, JPEG, GIF, RAR, 7Z, MZ/PE, ELF.
- **Cầu nối Python C-ABI (`bridge.py`)**:
  - Đóng gói hàm gọi native và cung cấp cơ chế dự phòng (Python hashlib fallback) trong trường hợp môi trường không tải được DLL.

---

### 1.6. Cơ sở dữ liệu SQLite & FTS5 Full-Text Search (`database/`)
- Tệp cơ sở dữ liệu hoạt động chính: `D:\Project\Bot\data\bot.db`.
- **Bổ sung các trường dữ liệu mới cho bảng `documents_archive`**:
  - `notes TEXT`: Lưu trữ ghi chú của quản trị viên (đặc điểm nhận dạng, lưu ý đề thi).
  - `file_hash TEXT`: Lưu trữ mã SHA-256 phục vụ đối chiếu trùng lặp.
  - `raw_text TEXT`: Lưu trữ nội dung văn bản trích xuất (tối đa 50,000 ký tự).
- **Tối ưu hóa SQLite Engine PRAGMAs**:
  - `PRAGMA synchronous = NORMAL`: Tăng tốc độ ghi đĩa an toàn.
  - `PRAGMA cache_size = -64000`: Cấp phát 64MB RAM làm bộ đệm truy vấn.
  - `PRAGMA temp_store = MEMORY`: Xử lý bảng tạm và sắp xếp trực tiếp trên RAM.
- **Bảng ảo tìm kiếm FTS5 (`documents_fts`)**:
  - Cấu hình bộ phân tách từ `tokenize='unicode61 remove_diacritics 2'` cho phép tìm kiếm tiếng Việt không dấu (tìm "toan" vẫn ra "toán").
  - Triggers tự động: `doc_fts_insert`, `doc_fts_update`, `doc_fts_delete` đồng bộ thời gian thực với bảng `documents_archive`.

---

### 1.7. Hệ thống Nạp Google Drive an toàn (`services/gdrive_importer.py`)
- Nhận diện các liên kết Google Drive (tệp đơn hoặc thư mục chia sẻ).
- Phòng chống SSRF (CWE-918): Chỉ chấp nhận tên miền chính thức của Google (`drive.google.com`, `docs.google.com`).
- Tự động tải xuống luồng dữ liệu, chạy kiểm tra Magic Bytes và DocInspector 5 lớp trước khi lưu kho.

---

### 1.8. Quản lý kho lưu trữ tệp đề thi (Storage & Archive)
- Toàn bộ 176 đề thi đã được khôi phục nguyên vẹn tại thư mục vật lý `D:\Project\Bot\storage\uploads\`.
- Chuẩn hóa tác giả đề thi toàn hệ thống về tên tác giả thống nhất: `Dai VIET` (Discord ID: `1529864608813416449`).

---

# 2. HỆ THỐNG WEB PORTAL (FRONTEND & CLIENT)

### 2.1. Phân quyền & Điều hướng Quản trị (Admin Access Control)
- **Cơ chế xác thực quyền Admin tự động**:
  - Khi người dùng đăng nhập tài khoản Discord, Web gọi `GET /api/admin/check` kèm Bearer Token.
  - Nếu tài khoản sở hữu 1 trong 5 Role Admin hoặc là Server Owner: kích hoạt trạng thái `isAdmin = true`.
- **Ẩn hoàn toàn khối Offline và Cài đặt với người dùng thông thường**:
  - Khung "Discord Bot: Offline" và nút "Cài đặt" (Endpoint configuration) bị ẩn hoàn toàn với user bình thường, tránh gây tâm lý hoang mang khi bot bảo trì hoặc bị can thiệp trái phép.
  - Chỉ Admin mới nhìn thấy bảng chỉ báo trạng thái Bot và có quyền mở modal cấu hình server.
- **Nút điều hướng Admin**:
  - Tự động hiển thị nút `👑 Quản Trị (Admin)` kèm huy hiệu phân cấp trên thanh điều hướng bên trái khi `isAdmin = true`.

---

### 2.2. Bảng điều khiển Quản trị viên (`src/components/AdminPanel.tsx`)
- Thành phần giao diện quản trị toàn diện, tích hợp trực tiếp trong Dashboard:
- **Tab 1: Xử lý Kỷ luật & Cấm (Moderation)**:
  - Form kỷ luật thời gian thực:
    - Nhập Discord User ID của thành viên cần xử lý.
    - Chọn hành động: 🔨 Ban vĩnh viễn (kèm tùy chọn xóa tin nhắn 1-7 ngày), 👢 Kick khỏi server, 🔇 Timeout / Mute (tùy chọn 5p, 10p, 30p, 1h, 24h, 7 ngày, 28 ngày), 🔊 Unmute.
    - Nhập lý do kỷ luật.
  - Danh sách tài khoản bị cấm (Bans List):
    - Đọc dữ liệu trực tiếp từ Discord API.
    - Hiển thị avatar, tên người dùng, ID, lý do cấm.
    - Nút **Gỡ Cấm (Unban)** 1 chạm kèm xác nhận an toàn.
- **Tab 2: Quản lý Kho Đề Thi (Documents Management)**:
  - Thanh tìm kiếm và bộ lọc môn học trực quan.
  - Bảng danh sách đề thi hiển thị chi tiết ID, tiêu đề, tên file, kích thước, khối lớp, tác giả và ghi chú.
  - **Modal chỉnh sửa đề thi**:
    - Sửa tiêu đề đề thi.
    - Sửa môn học và khối lớp.
    - **Thêm / Chỉnh sửa Ghi chú đề thi (`notes`)**.
  - **Xóa đề thi vĩnh viễn**:
    - Cảnh báo xác nhận trước khi thực hiện.
    - Gọi API xóa đồng bộ CSDL SQLite, xóa tệp ổ cứng và xóa tin nhắn Discord.
    - Tự động làm mới danh sách đề thi trên giao diện ngay lập tức.

---

### 2.3. Bảng điều khiển người dùng (`src/components/Dashboard.tsx`)
- **Tab Trang Chính (Overview)**:
  - Thống kê kho đề, chuỗi học tập (Streak), đếm ngược kỳ thi lớn.
- **Tab Kho Đề (Vault)**:
  - Duyệt toàn bộ 176 tài liệu trong kho.
  - Bộ lọc kết hợp: Khối lớp (Lớp 12 -> Lớp 6), 5 Thể loại đề (Thường, HSG, Chuyên, Quốc tế, Chung), Môn học, Từ khóa mô tả, Lọc bản trùng lặp / độc bản.
  - **Hiển thị Ghi chú đề thi**: Thẻ đề thi tự động hiển thị khối `📝 Ghi chú: ...` màu vàng hổ phách khi đề có ghi chú từ Quản trị viên.
  - Tải xuống đề thi trực tiếp hoặc mở xem bài đăng gốc trên Discord.
- **Tab Lấy Đề (Get Exam)**:
  - Bốc đề thi ngẫu nhiên theo tiêu chí môn/lớp.
- **Tab Kho Nộp Đề (Submit Doc)**:
  - Trạm tiếp nhận tài liệu học sinh nộp lên hệ thống.

---

### 2.4. Trạm nộp đề thông minh (`src/components/DocUploadZone.tsx`)
- Kéo thả nộp tệp đề thi (PDF, DOCX) hoặc dán link Google Drive.
- Kiểm tra dung lượng (tối đa 25MB), xác thực định dạng trước khi gửi.
- Gọi trực tiếp API phân tích DocInspector, hiển thị kết quả phân loại môn/lớp/loại đề tức thì.

---

### 2.5. Tủ sách cá nhân & Lưu đề yêu thích (`utils/bookmarkStorage.ts`)
- Lưu trữ danh sách ID đề thi yêu thích vào LocalStorage của trình duyệt.
- Tự động phát Custom Event `hyperhub_bookmark_changed` để đồng bộ trạng thái nút ⭐ Bookmark trên toàn bộ giao diện.
- Chế độ lọc "Tủ Sách" xem riêng các đề thi đã đánh dấu.

---

### 2.6. Xác thực Discord OAuth2 Bảo mật (`utils/discordAuth.ts`)
- Đăng nhập bảo mật qua Discord Developer Portal Client ID `1536298634990325871`.
- CSRF Protection: Sinh mã State ngẫu nhiên bằng Web Crypto API chống tấn công giả mạo yêu cầu.
- Token Leakage Prevention: Tự động xóa access token khỏi URL hash ngay sau khi xử lý đăng nhập để tránh rò rỉ qua Referrer headers.
- Lưu trữ an toàn trong sessionStorage và đính kèm Bearer token vào API headers.

---

### 2.7. Giao diện Trang chủ & Thành phần tương tác
- `Navbar.tsx`: Thanh điều hướng thông minh tự ẩn khi cuộn xuống và hiện khi cuộn lên, liên kết SPA linh hoạt giữa Trang chủ và Bảng điều khiển Hub.
- `ExamCountdown.tsx`: Đồng hồ đếm ngược đến các kỳ thi tuyển sinh và tốt nghiệp.
- `ThemeToggle.tsx` & `useTheme.ts`: Chuyển đổi giao diện sáng/tối (Dark/Light Mode).
- `LofiPlayer.tsx`: Trình phát nhạc Lofi tập trung học tập.

---

# 3. BẢO MẬT & PHÒNG THỦ MÃ NGUỒN (SECURITY HARDENING)

| Loại Tấn Công / Rủi Ro | Mã Phân Loại | Biện Pháp Phòng Thủ Triển Khai Trong Hệ Thống |
| :--- | :--- | :--- |
| **Thực thi mã từ xa (RCE)** | CWE-434 | Chặn triệt để tệp nhị phân thực thi (`MZ`/PE, `ELF`, Java bytecode, PHP script, Shell shebang). |
| **Giả mạo loại tệp (Spoofing)** | CWE-434 | Kiểm tra Magic Bytes header bằng C++ Engine (`fast_detect_magic_bytes`) trước khi xử lý. |
| **Leo thang thư mục (Path Traversal)** | CWE-22 | Chuẩn hóa tên tệp, xóa bỏ ký tự điều khiển và chuỗi `..`, chỉ giữ lại tên tệp an toàn. |
| **Yêu cầu giả mạo phía máy chủ (SSRF)** | CWE-918 | Kiểm tra whitelist URL Google Drive nghiêm ngặt, chặn mọi URL trỏ về mạng nội bộ hoặc localhost. |
| **Lộ lọt thông tin mã nguồn** | CWE-209 | Bắt lỗi toàn cục, ẩn stack trace và mã lỗi nhạy cảm, chỉ trả về thông báo lỗi chuẩn hóa. |
| **Tấn công DoS / Brute-force** | CWE-799 | Giới hạn 120 req/phút/IP toàn hệ thống, 100 tệp/5 phút khi upload, 30 req/phút khi phát đề. |
| **Tài khoản rác / Spam bot** | - | Bắt buộc tài khoản Discord phải có email xác minh (`verified: true`) từ chính Discord API. |

---

# 4. BẢNG TỔNG HỢP ENDPOINT REST API

| Phương Thức | Đường Dẫn Endpoint | Quyền Hạn | Chức Năng Chi Tiết |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/status` | Public | Kiểm tra trạng thái Bot, độ trễ Ping, thời gian Uptime, số lượng máy chủ. |
| `GET` | `/api/leaderboard` | Public | Bảng xếp hạng thi đấu (Ranked & Freedom). |
| `GET` | `/api/documents` | Public | Lấy danh sách đề thi (hỗ trợ phân trang, tìm kiếm, lọc môn, lọc khối lớp, lấy notes). |
| `GET` | `/api/documents/stats` | Public | Thống kê số lượng đề thi độc bản và đề thi trùng lặp. |
| `GET` | `/api/documents/request_exam` | Public | Bốc đề ngẫu nhiên theo tiêu chí bộ lọc. |
| `GET` | `/api/documents/{id}/download` | Public | Tải trực tiếp tệp đề thi về máy. |
| `POST` | `/api/documents/upload` | Guest / User / Admin | Nộp tài liệu trực tiếp từ Web (khách ghi tên "Khách"), gọi DocInspector thẩm định. |
| `POST` | `/api/documents/import_gdrive` | User / Admin | Nạp tài liệu từ liên kết chia sẻ Google Drive. |
| `GET` | `/api/admin/check` | **Admin** | Xác thực quyền Quản trị viên của phiên đăng nhập hiện tại. |
| `GET` | `/api/admin/bans` | **Admin** | Đọc danh sách tài khoản bị cấm trên Discord Server. |
| `POST` | `/api/admin/ban` | **Admin** | Cấm thành viên khỏi Discord Server kèm lý do và số ngày xóa tin nhắn. |
| `POST` | `/api/admin/unban` | **Admin** | Gỡ cấm người dùng trên Discord Server. |
| `POST` | `/api/admin/kick` | **Admin** | Kick thành viên ra khỏi Discord Server. |
| `POST` | `/api/admin/timeout` | **Admin** | Khóa chat (Timeout/Mute) hoặc gỡ khóa chat (Unmute) cho thành viên. |
| `DELETE`| `/api/admin/documents/{id}` | **Admin** | Xóa vĩnh viễn đề thi (xóa trên CSDL SQLite, file trên ổ cứng, tin nhắn Discord). |
| `PATCH` | `/api/admin/documents/{id}` | **Admin** | Chỉnh sửa tiêu đề, môn học, khối lớp và **ghi chú đề thi (`notes`)**. |

---

> 🚀 **Địa chỉ truy cập Web:** [https://hyperhub-one.vercel.app](https://hyperhub-one.vercel.app)  
> 📁 **Tệp tài liệu này được lưu trữ tại:** `D:\Project\list.md`

---

# 5. NHẬT KÝ NÂNG CẤP PHIÊN VẬN HÀNH (MỞ PUBLIC + HEADLESS + TIẾT KIỆM RAM)

### 5.1. Chống chạy 2 Bot chồng nhau (lỗi bind port 8080 / WinError 10048)
- Thêm chốt single-instance trong `Bot/bot.py` (`_ensure_single_instance`):
  - Ghi PID vào `Bot/data/bot.lock`, tự xóa lock cũ khi PID đã chết.
  - Chốt phụ: thử kết nối `127.0.0.1:<BOT_API_PORT>` — port bị giữ thì từ chối khởi động, thoát mã 2 kèm hướng dẫn tắt bot cũ.
  - Đã kiểm chứng ngoài thực tế: 1 instance thừa khởi động đã bị từ chối đúng quy trình.
- `Bot/services/api_bridge.py` (`start`): bắt `OSError` khi bind thất bại, ghi log rõ nguyên nhân thay vì treo traceback.

### 5.2. Chế độ chạy ngầm Headless kiểu server (không còn cửa sổ CMD)
- `Bot/bot.py`: chuyển 2 lệnh `print()` sang logger + chặn stdout/stderr `None` khi chạy bằng `pythonw` (không crash khi không có console).
- Thêm `start_hidden.vbs`: bật Bot (`pythonw`, ẩn hoàn toàn) + Ngrok tunnel (giữ URL cố định), hỗ trợ tham số `botonly` để restart bot mà không nhân đôi tunnel.
- Tự chạy khi mở máy: shortcut `HyperHub.lnk` trong thư mục Startup (không cần quyền admin).
- Viết lại 3 file bat ASCII sạch (hết chữ lỗi font): `start_hyperhub.bat` (gọi ngầm), `stop_hyperhub.bat` (diệt cả tiến trình ẩn theo commandline `bot.py`), `restart_bot_only.bat` (giữ nguyên tunnel).

### 5.3. Sửa Web production gọi API toàn trượt (ngrok ERR_NGROK_6024)
- Nguyên nhân: trên HTTPS, web gọi `/api/*` qua Vercel Rewrite nhưng fetch phía server không gắn được header `ngrok-skip-browser-warning` nên ngrok free chặn bằng trang cảnh báo.
- Sửa `Web/src/utils/apiConfig.ts`: trên HTTPS gọi thẳng tunnel URL từ browser (mọi fetch đã kèm header, CORS backend cho phép sẵn). Khôi phục đọc override URL từ localStorage (`setCustomApiUrl` trước đây ghi mà không đọc).

### 5.4. Mở Web public — không cần đăng nhập vẫn vào được
- Bỏ màn hình khóa Hub khi bot offline (`hubLocked` luôn `false`); giữ banner offline + cổng riêng cho Bốc đề và Admin Hub.
- Backend `POST /api/documents/upload` chấp nhận khách (không token → tên `Khách`, id 0). Bốc đề (`request_exam`) và nạp Google Drive vẫn bắt verify email như cũ.
- Thông điệp rào cản trong `Dashboard.tsx` viết lại: xem/nộp đề không cần tài khoản, chỉ bốc đề mới cần Discord verify.

### 5.5. Kho lưu tạm offline + tự đồng bộ (IndexedDB Outbox)
- Mới `Web/src/utils/outbox.ts`: lưu đề (kể cả blob ≤ 25MB) vào IndexedDB khi bot offline hoặc rớt mạng giữa chừng.
- `DocUploadZone.tsx`: trạng thái `queued`, panel "Kho Lưu Tạm" (gửi ngay tất cả / xóa từng đề / đếm số lần thử lại), tự flush khi bot online trở lại, rớt mạng giữa flush thì dừng và giữ nguyên hàng đợi.
- `Dashboard.tsx`: phát hiện chuyển offline → online thì tự tải lại danh sách + thống kê, hiện toast xanh 8 giây.

### 5.6. Nộp nhiều file không giới hạn số lượng
- Web: bỏ `.slice(0, 15)`, nhãn đổi thành "Không giới hạn số tệp (mỗi tệp ≤ 25MB)".
- Lọc giữ nguyên: sai định dạng (chỉ PDF/DOCX/DOC/TXT) hoặc quá 25MB thì báo rõ tên file và bỏ qua, file đạt vẫn vào hàng đợi (trước đây lỗi lọc bị nuốt khi còn file hợp lệ).
- Backend: nâng rate-limit upload 15 → **100 tệp/5 phút/IP** (chống spam DocInspector).

### 5.7. Phân tích RAM + chế độ nhẹ + GPU-ready (model embedding MiniLM)
- Đo thực tế: bot **822MB** = import lib ~208MB + model MiniLM **~550MB** + runtime ~65MB; ngrok 84MB. Bóp arena onnxruntime không giảm (đã test: 643.1MB → 643.2MB) vì đó là trọng lượng thật của weights fp32.
- Chế độ RAM thấp: `EMBEDDING_ENABLED=false` trong `.env` → bỏ model, tìm kiếm dùng BM25/FTS (bot còn ~270MB, vừa VPS 512MB). Mặc định vẫn `true`.
- GPU-ready cho server sau này: `EMBEDDING_DEVICE=auto|cpu|cuda` (tự dùng GPU nếu có, không thì CPU), `EMBEDDING_GPU_MEM_GB=1.0` trần VRAM, lỗi/thiếu VRAM tự rớt về CPU. `requirements.txt` ghi chú đổi sang `onnxruntime-gpu` + CUDA trên server.
- Quyết định giữ model (không thay bằng LSA/TF-IDF hay API ngoài): đã đối chiếu và tư vấn đầy đủ trong phiên.

### 5.8. Link nhóm Messenger thật lên Web
- `CommunityChannels.tsx` (nút "Tham Gia Nhóm Messenger") và `data/platforms.ts`: thay link giả `AbY_HyperHub` / `YOUR_MESSENGER_URL` bằng `https://m.me/j/AbZngp-x0Ny92IWH/`.

### 5.9. Kiểm chứng + triển khai phiên này
- Tests: Bot 161 passed, DocInspector 34 passed, chunk archive 5 passed, `tsc -b` sạch, `vite build` thành công, API local + tunnel đều trả `HyperHub#0594`.
- Kho đề: 175 bản ghi archive, 121 chunks Discord; xóa file rác 0-byte trong `storage/uploads`; giữ 1 PDF 10.5MB làm cache (bản gốc đã nằm trên Discord).
- GitHub: backend `641ed82`, web `dd23715` — cả 2 repo sạch, không lọt `.env`/`.db`.
- ⏳ **Còn chờ người dùng**: double-click `start_hyperhub.bat` 1 lần để bật lại bot (môi trường chạy lệnh của agent tự diệt tiến trình con nên không thể khởi động bot từ xa).
