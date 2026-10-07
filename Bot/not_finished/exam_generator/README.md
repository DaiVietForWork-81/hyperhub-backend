# 📦 Phân Hệ Tạo Đề Thi AI (AI Exam Generator Platform) — Trạng Thái: [Not Finished]

> [!NOTE]
> Phân hệ này đang ở trạng thái **[Not Finished]** để bảo lưu an toàn cho tương lai sử dụng.
> Lõi Bot chính thức chỉ nạp các tính năng production. Khi bạn sẵn sàng đưa tính năng Tạo Đề vào hoạt động, hãy xem hướng dẫn kích hoạt ở mục cuối tài liệu này.

---

## 🌟 Tổng Quan Kiến Trúc

Phân hệ tạo đề thi AI HyperHub là giải pháp khảo thí học tập toàn diện, tích hợp:
1. **Kiến Trúc Phân Luồng Tư Duy Gemma - Qwen (Hybrid Thinking Pipeline):**
   - **Gemma 3:4B (Thinking ON - Planner):** Lập Bản thiết kế tổng thể (Exam Blueprint) và ma trận nhận thức Bloom (40-30-20-10).
   - **Qwen 3.5:4B / 2.5:4B (Thinking OFF - Drafter):** Soạn thảo thần tốc toàn bộ đề thi và đáp án JSON chuẩn.
   - **Gemma 3:4B (Thinking ON - Auditor):** Hội đồng thẩm định khảo thí đối chiếu và sửa lỗi logic/công thức.
   - **Qwen 2.5:0.5B (Thinking OFF - Cleaner):** Quét chính tả và chuẩn hóa cú pháp.
   - **Khóa đơn nhiệm phần cứng `_MODEL_MUTEX`:** Đảm bảo chỉ 1 mô hình nạp trong VRAM/RAM tại một thời điểm, dỡ RAM ngay (`keep_alive=0`) sau khi hoàn thành bước.

2. **Điều Phối Tài Nguyên Lai Thông Minh (RAM + GPU / RAM + CPU):**
   - **RAM + GPU:** Tự động phát hiện GPU rời (VRAM $\ge 1.2\text{GB}$). Offload tối đa các lớp mô hình vào VRAM, phần dôi dư chạy trên System RAM.
   - **RAM + CPU:** Khi không có GPU hoặc khi VRAM quá tải, tự động chuyển đổi sang CPU đa luồng kết hợp bộ nhớ RAM khả dụng mà không làm gián đoạn hay crash tiến trình.

3. **Bộ Khung Đề Chuẩn Hóa Quốc Gia (Exam Blueprint Engine):**
   - **Tốt nghiệp THPT 2025 (Chuẩn Quyết định 764/QĐ-BGDĐT):** Đầy đủ môn Toán (12 MCQ + 4 Đúng/Sai 4 ý + 6 Điền ngắn), Tiếng Anh (40 câu), Văn (Đọc hiểu + Làm văn), KHTN (Lý, Hóa, Sinh), KHXH (Sử, Địa, GDCD), Tin học.
   - **Đánh Giá Năng Lực & Đánh Giá Tư Duy:** HSA (ĐHQG Hà Nội), V-ACT (ĐHQG TP.HCM), TSA (ĐHBK Hà Nội).
   - **Tuyển Sinh Lớp 10:** Đề chung 5 bài tự luận chuẩn Sở GD&ĐT, đề Chuyên Toán/Tin 150 phút.
   - **Kiểm Tra Định Kỳ Thông Tư 22/BGDĐT:** Giữa kỳ & Cuối kỳ (70% Trắc nghiệm + 30% Tự luận).

4. **Trộn Mã Đề Tự Nhiên (Natural Exam Shuffler):**
   - Trộn ngẫu nhiên câu hỏi và hoán vị đáp án A, B, C, D; tự động đồng bộ lại bảng đáp án đúng (`correct_key`), chi phí 0 Token.

5. **Đóng Gói Kép & Bản Quyền Ẩn (Dual Exporter & Invisible Watermark):**
   - Xuất song song 2 tệp riêng biệt: `[De_Thi]` và `[Huong_Dan_Giai]` cho cả Word (.docx) và PDF (.pdf) với kích thước $< 5\text{MB}$.
   - Nhúng bản quyền tàng hình: Khi bôi đen copy-paste sẽ tự động hiện watermark thương hiệu.

---

## 📁 Cấu Trúc Thư Mục

```
not_finished/exam_generator/
├── README.md                           # Tài liệu kiến trúc và hướng dẫn
├── cogs/
│   ├── exam_generator_cog.py           # Cog Discord quản lý Ticket và đàm thoại tạo đề
│   ├── check_token.py                  # Lệnh Slash /check kiểm tra hạn mức Token & Gói
│   └── info_board_cog.py               # Bảng thông tin tự động tại kênh #info
├── services/
│   ├── exam_blueprint_engine.py        # Động cơ khung đề thi chuẩn hóa quốc gia
│   ├── exam_generator_service.py       # Pipeline AI 4 bước, Mutex và Governor
│   ├── exam_shuffler.py                # Thuật toán trộn đề tự nhiên 0 token
│   ├── document_exporter.py            # Xuất bản Word/PDF & đóng dấu ẩn
│   ├── diagram_drawer.py               # Bộ vẽ hình học, đồ thị và lưu đồ khoa học
│   └── user_token_service.py           # Quản lý 4 Gói (Free, Pro, Ultra, Elite) & Reset 00:00
├── tests/
│   ├── test_exam_blueprint_engine.py   # Unit test khung đề chuẩn
│   ├── test_exam_generator_service.py  # Unit test pipeline AI & RAM+GPU/CPU
│   ├── test_exam_shuffler.py           # Unit test trộn đề
│   ├── test_document_exporter.py       # Unit test xuất file
│   └── test_token_service.py           # Unit test token và tier
└── data/
    └── generated_exams/                # Thư mục lưu trữ tạm các file xuất bản
```

---

## 🧪 Cách Chạy Kiểm Thử Độc Lập

Bạn có thể chạy toàn bộ 24 bài kiểm thử của phân hệ này bất cứ lúc nào bằng lệnh:

```powershell
python -m pytest not_finished/exam_generator/tests/ -v
```

---

## 🚀 Hướng Dẫn Kích Hoạt (Đưa Vào Sử Dụng Trong Tương Lai)

Khi bạn muốn đưa tính năng tạo đề thi vào hoạt động chính thức trên Bot Discord:

1. Mở tệp [`bot.py`](file:///d:/Project/Bot/bot.py).
2. Tìm đến danh sách `INITIAL_EXTENSIONS` và bỏ chú thích 3 dòng sau:
   ```python
   "not_finished.exam_generator.cogs.exam_generator_cog",
   "not_finished.exam_generator.cogs.check_token",
   "not_finished.exam_generator.cogs.info_board_cog",
   ```
3. Khởi động lại Bot:
   ```powershell
   python bot.py
   ```
Toàn bộ các kênh `#generate` và `#info` sẽ lập tức tự động ghim giao diện điều khiển và phục vụ người dùng server!
