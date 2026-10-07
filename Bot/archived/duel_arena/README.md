# Lưu Trữ: Phân Hệ Đấu Trường Sinh Tồn 1:1 (Ranked & Random Duel Arena)

Thư mục này lưu trữ toàn bộ mã nguồn của tính năng **Đấu Trường Đối Kháng 1:1 (Ranked Duel, Random Duel, Matchmaking & Anti-Cheat)** của HyperHub Bot.

> [!NOTE]
> Các file trong thư mục này **không bị xóa** mà được lưu trữ an toàn, độc lập để dự án gọn gàng và tập trung vào các tính năng Freedom / AI Assistant. Bất kỳ lúc nào bạn muốn mở lại Đấu trường 1:1, chỉ cần làm theo hướng dẫn khôi phục bên dưới.

---

## 📁 Danh Sách File Đã Lưu Trữ

### 1. Cogs (Lệnh Discord)
- `cogs/ranked_duel.py`: Cog quản lý sảnh chờ thi đấu 1:1, ghép trận Ranked/Random, hàng đợi Matchmaking, lệnh `/spectate` theo dõi trận đấu.

### 2. Services (Dịch Vụ & Thuật Toán)
- `services/duel_service.py`: Quản lý phiên đấu `DuelSession`, máy trạng thái trận đấu (State Machine), logic chấm điểm sandbox thời gian thực và quản lý `MatchmakingManager`.
- `services/duel_problems.py`: Kho bài tập mẫu (`PROBLEM_BANK`) phân theo Tier từ T8 đến HT1.
- `services/anti_cheat.py`: Động cơ Anti-Cheat 2.0 phát hiện gian lận code, copy-paste, kiểm tra telemetry và tính trung thực.
- `services/match_card.py`: Kết xuất ảnh đồ họa PNG tóm tắt kết quả trận đấu 1:1.
- `services/ai_problem_upgrader.py`: Bộ kiểm duyệt và nâng cấp độ khó bài tập thi đấu tự động.
- `services/ai_worker.py`: Tiến trình chạy nền tự động soạn sẵn bài tập cho các bậc Rank.
- `services/problem_factory.py`: Bộ sinh và tổng hợp đề thi thuật toán.
- `services/profile_card.py`: Bộ vẽ thẻ hồ sơ Esports 4K UHD hiển thị chỉ số Ranked 1:1 và Freedom.

### 3. Tests (Bộ Kiểm Thử)
- `tests/test_ranked_duel.py`: Unit tests cho luồng ghép trận và thi đấu.
- `tests/test_ranked_category_hide.py`: Test quyền ẩn/hiện danh mục phòng đấu.
- `tests/test_spectator_view_command.py`: Test xem trực tiếp trận đấu.
- `tests/test_custom_match_and_streak.py`: Test chuỗi thắng và trận giao hữu.
- `tests/test_high_tier_problems_and_escalation.py`: Test bài tập cấp cao Div. 1 & 2.
- `tests/test_profile_card.py`: Test kết xuất ảnh hồ sơ.
- `tests/test_new_features.py`: Test các tính năng bổ trợ thi đấu.
- `tests/test_ai_worker.py`: Test worker chạy nền.
- `tests/test_anti_cheat_and_history.py`: Test phát hiện gian lận và lịch sử đấu.
- `tests/test_self_healer.py`: Test tự sửa lỗi cho duel session.
- `tests/test_special_roles_and_cache.py`: Test các role danh hiệu đấu trường.

### 4. Dữ Liệu & Bản Sao Lưu Cấu Hình (Backups & Restore Scripts)
- `ranked_roles_backup.json`: Sao lưu thuộc tính 12 Role Ranked (tên, màu sắc, quyền, vị trí, danh sách thành viên sở hữu).
- `restore_ranked_roles.py`: Script 1-click tự động tạo lại 12 Role Ranked và gán lại cho các thành viên.
- `category_1534147796461162697_backup.json`: Sao lưu cấu hình 8 kênh Discord trong danh mục Giải Đề/Câu Hỏi.
- `restore_category_channels.py`: Script 1-click tự động tạo lại danh mục và 8 kênh Discord.
- `duel_database_backup.json`: Sao lưu toàn bộ 42 lịch sử trận đấu `duel_matches` và 7 hồ sơ chỉ số Ranked từ CSDL `bot.db`.

---

## 🔄 Hướng Dẫn Khôi Phục (Kích Hoạt Lại Đấu Trường 1:1)

Khi bạn muốn sử dụng lại tính năng Đấu trường, chỉ cần thực hiện các bước sau:

### 1. Khôi phục Role Ranked trên Discord:
```bash
python archived/duel_arena/restore_ranked_roles.py
```

### 2. Khôi phục các kênh Discord:
```bash
python archived/duel_arena/restore_category_channels.py
```

### 3. Di chuyển lại mã nguồn về dự án:
Chạy đoạn mã Python sau từ thư mục `Bot/`:
```python
import shutil, os

BOT = os.path.abspath(".")
ARC = os.path.join(BOT, "archived", "duel_arena")

for root, dirs, files in os.walk(ARC):
    for f in files:
        if f.endswith((".json", ".md", ".py")) and root == ARC: continue
        src = os.path.join(root, f)
        rel = os.path.relpath(src, ARC)
        dst = os.path.join(BOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Restored: {rel}")
```

### 4. Bỏ comment trong `bot.py` và `.env`:
- Mở `bot.py` và bỏ dấu comment `#` ở các dòng liên quan đến `ranked_duel` và `problem_worker`.
- Mở `.env` và bỏ comment các dòng `*_RANKED_ROLE_ID`.

### 5. Khởi động lại Bot:
```bash
python bot.py
```
Toàn bộ hệ thống Đấu Trường 1:1 sẽ hoạt động trở lại nguyên vẹn!

