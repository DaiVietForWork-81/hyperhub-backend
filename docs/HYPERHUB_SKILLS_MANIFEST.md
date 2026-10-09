# 🌌 BẢN ĐỒ KIẾN TRÚC SKILLS TỔNG HỢP CHO HYPERHUB (82 SKILLS REWORK)

Tài liệu này hệ thống hóa toàn bộ các tiêu chuẩn, mẫu thiết kế (design patterns) và quy chuẩn kỹ thuật được chọn lọc từ **82 Agent Skills** và áp dụng trực tiếp vào hệ sinh thái **HyperHub (Web Frontend + Discord Bot Backend + C++ Core + DocInspector)**.

---

## 🏛️ 1. FRONTEND ARCHITECTURE & UX REWORK (Web)
*Áp dụng từ: Vercel React Best Practices, Vercel Web Design Guidelines, UI/UX Pro Max, ibelick/ui-skills, Leonxlnx/taste-skill, PyModel/react-frontend-skills.*

| Tiêu chuẩn / Kỹ năng | Vấn đề trước đây | Giải pháp Rework Đã Áp Dụng |
| :--- | :---: | :--- |
| **Resilience & Fault Tolerance** | App sập thành màn hình trắng khi có lỗi React runtime | Tích hợp **`ErrorBoundary.tsx`** bao bọc toàn bộ ứng dụng, hiển thị thẻ Hologram cứu hộ với nút Tải Lại Trang và Về Trang Chủ. |
| **Feedback Loop (Toast System)** | Thao tác bookmark, nộp file chỉ báo inline hoặc im lặng | Triển khai **`ToastContext.tsx` & `useToast`** nổi góc phải (success, info, warning, error) có hiệu ứng trượt, tự đóng và đạt chuẩn a11y. |
| **Visual Loading States** | Spinner xoay tròn đơn điệu gây cảm giác chờ đợi lâu | Triển khai **Skeleton Shimmer Loader (6 cards)** với hiệu ứng quét sáng mượt mà (`.skeleton-shimmer`). |
| **Micro-Interactions & Depth** | Giao diện phẳng hoặc hiệu ứng chưa đồng nhất | Chuẩn hóa `.cosmic-card` với micro-lift `translateY(-2px)`, `.golden-hologram-card` cho khung bốc đề ngẫu nhiên. |
| **Accessibility & A11y** | Nút bấm chỉ có icon thiếu nhãn cho Screen Reader | Bổ sung `aria-label`, `role="status"` và cấu trúc semantic rõ ràng. |
| **Đồng bộ 7 Khối Lớp** | Màu sắc khối lớp rời rạc | Chuẩn hóa mã màu 7 Khối Lớp đồng bộ 100% với Discord Server Roles (Lớp 12 Đỏ, Lớp 11 Cam, Lớp 10 Vàng, Lớp 9 Lục, Lớp 8 Cyan, Lớp 7 Lam, Lớp 6 Tím). |

---

## ⚙️ 2. BACKEND & REST API STANDARDS (Bot Service)
*Áp dụng từ: FastAPI Official Skill, Sentry for AI / Monitoring, full-stack-skills/python-skills, Cloudflare Skills, Supabase Agent Skills.*

| Tiêu chuẩn / Kỹ năng | Giải pháp Rework Đã Áp Dụng |
| :--- | :--- |
| **RFC Health & Telemetry Probe** | Triển khai endpoint **`GET /api/health`** đo lường: <br>• SQLite query latency (`SELECT 1`)<br>• Trạng thái C++ Native DLL (`IS_NATIVE_ACCELERATED`, SHA-256 test, Magic Bytes test)<br>• Kết nối Discord Gateway & ping ms<br>• Trạng thái bảng FTS5 Full-Text Search. |
| **Rate Limit & Brute-Force Shield** | Middleware kiểm soát 120 req/phút/IP, bảo vệ tài nguyên máy chủ và chống DoS. |
| **Strict Multi-Layer URL Validation** | Chống SSRF khi import Google Drive với 5 lớp bảo mật (Auth -> Pre-probe -> Sandbox -> Antivirus -> DocInspector). |

---

## ⚡ 3. C++ NATIVE ENGINE & SQLITE HIGH-PERFORMANCE
*Áp dụng từ: Redis Agent Skills, C++20 Standard, SQLite FTS5 Engine, Cybersecurity Skills.*

| Tiêu chuẩn / Kỹ năng | Giải pháp Rework Đã Áp Dụng |
| :--- | :--- |
| **Zero-Dependency SHA-256 (C++)** | Triển khai hàm `fast_sha256` thuần C++20 trong `native_core.cpp`, tính hash nhị phân tốc độ cao để phát hiện tài liệu nộp trùng lặp tức thì mà không cần tải thư viện ngoài. |
| **Magic Bytes Header Sniffing** | Hàm `fast_detect_magic_bytes` kiểm tra chữ ký nhị phân trực tiếp (PDF, DOCX, ZIP, PNG, JPEG, PE...), ngăn chặn hoàn toàn kỹ thuật spoof extension. |
| **FTS5 Full-Text Search (Vietnamese)** | Bảng ảo `documents_fts` kích hoạt tokenizer `unicode61 remove_diacritics 2`, hỗ trợ tìm kiếm đề thi tiếng Việt không dấu siêu tốc. |
| **SQLite Engine Tuning** | Bổ sung PRAGMAs: `synchronous = NORMAL`, `cache_size = -64000` (64MB RAM cache), `temp_store = MEMORY`. |

---

## 🤖 4. DISCORD BOT RESILIENCE & INTERACTION DESIGN
*Áp dụng từ: sitne/discord-agent, TiramisuLabs Seyfert Skill, discord.py patterns.*

| Tiêu chuẩn / Kỹ năng | Giải pháp Rework Đã Áp Dụng |
| :--- | :--- |
| **Rate Limit Debounce** | Bộ điều hòa cập nhật bảng nộp tài liệu (`_last_panel_update` & `_pending_panel_update`) với khoảng thời gian tối thiểu 3.0s, tránh triệt để Discord Rate Limit (HTTP 429). |
| **Thông Báo Trùng Lặp Công Khai & Riêng Tư** | Tự động gửi DM chi tiết cho người nộp tài liệu trùng lặp, đồng thời phát thông báo ngắn gọn tại kênh intake và tự động xóa sau 10 giây để giữ kênh luôn sạch sẽ. |
| **Tự Động Bóc Tách Năm Học & Trường Ra Đề** | Bộ regex thông minh trích xuất tự động Năm học (`academic_year`) và Trường / Sở GD&ĐT (`school_or_department`) từ nội dung văn bản. |

---

## 📁 DANH MỤC THƯ MỤC SKILLS NỘI BỘ DỰ ÁN
* `Web/skills/web-design-engineer/`: Quy chuẩn thiết kế giao diện từ ConardLi/garden-skills.
* `Web/skills/ui-skills/`: Bộ thư viện component & design engineering từ ibelick/ui-skills.
* `Web/skills/ui-ux-pro-max/`: Hệ thống kiến trúc màu sắc, typography và layout UI/UX.
