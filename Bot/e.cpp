Phân Tách 2 Cột Lịch Sử Profile 4K & Hệ Thống Tra Cứu / Lưu Trữ Đề Bài (/search {id})
Tài liệu thiết kế kỹ thuật cho 2 tính năng trọng tâm:

Phân tách Panel 3 trên Thẻ Hồ Sơ Esports 4K (3840×2160): Chia khu vực thành 2 cột song song cân đối: Bên trái là Lịch sử Ranked 1:1 (⚔️ RANKED 1:1 RECENT MATCHES) và bên phải là Lịch sử Freedom (🌟 FREEDOM RECENT SUBMISSIONS). Hỗ trợ hiển thị đầy đủ 3 trận/bài gần nhất hoặc trạng thái rỗng (Empty State) sắc nét khi người chơi chưa có lịch sử.
Hệ thống Quản lý ID Thống nhất, Lưu trữ Kênh 1548627763467128912 & Lệnh /search {id}:
Mỗi khi hoàn thành một bài trong Freedom hoặc một chặng/trận Ranked, bot thông báo thông tin bài kèm Mã tra cứu (Problem ID) chung.
Tự động lưu trữ (archive) đề bài, ràng buộc, phân tích thuật toán (Editorial) và code mẫu chuẩn vào kênh ID 1548627763467128912.
Lệnh slash command /search {id} cho phép tra cứu ngay lập tức bất kỳ bài Freedom hoặc Ranked nào từ bộ nhớ, database và quét tin nhắn trong kênh 1548627763467128912.
User Review Required
IMPORTANT

Cấu trúc 2 cột Panel 3 trên ảnh 4K:
Chiều rộng khả dụng của khu vực phải: 
2390
 px
2390 px.
Cột trái (Ranked 1:1): Tọa độ 
X
=
1405
X=1405, Rộng 
1135
 px
1135 px, Cao 
800
 px
800 px. Hiển thị 3 thẻ trận đấu gần nhất (Kết quả VICTORY/DEFEAT, đối thủ, điểm Elo biến động, thời gian).
Cột phải (Freedom Mode): Tọa độ 
X
=
2570
X=2570, Rộng 
1135
 px
1135 px, Cao 
800
 px
800 px. Hiển thị 3 bài nộp gần nhất (Verdict ACCEPTED/WA, mã bài & tên bài, ngôn ngữ, điểm số, thời gian).
Cả 2 cột đều có thiết kế Empty State chuyên nghiệp với nút Call-to-Action tương ứng khi thí sinh chưa tham gia.
Hệ thống ID bài tập thống nhất:
Bài Freedom / Codeforces: Mã định dạng chuẩn như 1700A, 4A, 2251B (chuẩn hóa không phân biệt hoa thường).
Bài Ranked 1:1: Mã bài từ ngân hàng đề như PRB-T8-01, PRB-MT2-03, v.v.
Lệnh /search {id} tự động nhận diện và xử lý cả 2 loại ID.
Kênh lưu trữ tự động 1548627763467128912:
Khi một bài được nộp/thi đấu xong, bot tự động kiểm tra và lưu trữ nếu bài chưa tồn tại trong kênh (tránh spam lặp lại cùng một bài).
Mỗi bài được đăng với cấu trúc chuẩn [PROBLEM_ARCHIVE] ID: {id} giúp bot dễ dàng quét tìm lại khi cần.
Proposed Changes
1. Cấu hình & Cài đặt hệ thống
[MODIFY] 
config/settings.py
Bổ sung cấu hình PROBLEM_ARCHIVE_CHANNEL_ID:
python

PROBLEM_ARCHIVE_CHANNEL_ID: int = Field(
    default=1548627763467128912,
    description="Kênh lưu trữ đề bài, lời giải và code mẫu tự động sau mỗi bài Freedom/Ranked",
)
Cập nhật cả lớp Settings Pydantic và lớp dự phòng non-Pydantic fallback.
2. Dịch vụ Đồ họa Profile Card 4K
[MODIFY] 
services/profile_card.py
Mở rộng tham số hàm generate_profile_card:
Thêm recent_freedom: list[dict] | None = None.
Cập nhật cache_data để tính hash thông minh cho cả recent_freedom.
Thay đổi logic vẽ PANEL 3:
Tiêu đề chung: RECENT ACTIVITY & COMBAT AUDIT TRAIL (LỊCH SỬ ĐẤU TRƯỜNG & NỘP BÀI).
Cột Trái — Ranked 1:1:
Tiêu đề cột con: ⚔️ RANKED 1:1 RECENT MATCHES.
Nếu có trận đấu: Vẽ tối đa 3 thẻ trận với kích thước 
1135
×
220
 px
1135×220 px. Badge trạng thái (VICTORY xanh ngọc, DEFEAT đỏ, DRAW vàng), Elo delta to rõ (+28 Rating), tên đối thủ vs Opponent, thời gian và tag Anti-Cheat.
Nếu chưa có trận: Khung Empty State tối giản, icon ⚔️, thông báo "NO RANKED HISTORY" và nút "ENTER RANKED 1:1".
Cột Phải — Freedom Mode:
Tiêu đề cột con: 🌟 FREEDOM RECENT SUBMISSIONS.
Nếu có bài nộp: Vẽ tối đa 3 thẻ bài nộp với kích thước 
1135
×
220
 px
1135×220 px. Badge Verdict (ACCEPTED xanh lá, WRONG ANSWER đỏ, TIME LIMIT cam), Mã bài & tên bài 1700A • Problem Name, ngôn ngữ C++20, điểm số +100 pts, thời gian nộp.
Nếu chưa có bài nộp: Khung Empty State tối giản, icon 📜, thông báo "NO FREEDOM SUBMISSIONS" và nút "SUBMIT PROBLEM".
[MODIFY] 
cogs/profile.py
Truy vấn SubmissionRepository.get_user_submissions(target_user.id, page=1, per_page=3).
Chuyển đổi dữ liệu thành danh sách dict recent_freedom gồm: problem_id, verdict, language, score, execution_time, memory, mode, time_str.
Truyền recent_freedom=recent_freedom vào ProfileCardGenerator.generate_profile_card.
3. Dịch vụ Lưu Trữ & Tra Cứu Đề Bài
[NEW] 
services/problem_archive.py
Tạo lớp ProblemArchiveService:
archive_problem(bot: commands.Bot, problem_data: dict) -> discord.Message | None:
Định dạng bài đăng lưu trữ với header chuẩn: [PROBLEM_ARCHIVE] ID: {problem_id}.
Nội dung: Tên bài, Chế độ (Freedom / Ranked 1:1), Bậc Tier / Rating, Giới hạn Time/Memory, Đề bài (Statement), Input/Output, Ràng buộc, Phân tích giải thuật (Editorial) và Code mẫu chuẩn AC (C++/Python).
Quản lý tập hợp _archived_ids: set[str] trong bộ nhớ và file cache để không gửi lặp lại bài đã lưu trữ.
search_problem(bot: commands.Bot, query_id: str) -> dict | None:
Chuẩn hóa mã ID: xóa khoảng trắng, chữ in hoa (vd: 1700a -> 1700A, rnk-01 -> RNK-01).
Bước 1 — Tìm trong kho đề Ranked: Kiểm tra PROBLEM_BANK / data/ai_problems.json.
Bước 2 — Tìm trong kho đề Freedom / CF: Kiểm tra cơ sở dữ liệu Problem và ProblemFetcher.fetch_problem(id).
Bước 3 — Quét kênh lưu trữ 1548627763467128912: Nếu cần tra cứu bài cũ hoặc lấy link lưu trữ, quét lịch sử tin nhắn trong kênh theo cú pháp ID: {query_id}.
Trả về đối tượng đầy đủ gồm: metadata bài toán, đề bài, thuật toán, code mẫu và link trực tiếp đến tin nhắn lưu trữ trên Discord (nếu có).
[NEW] 
cogs/search.py
Đăng ký lệnh Slash Command /search:
Tham số: id: str (Mã bài tập cần tra cứu, ví dụ: 1700A, PRB-T8-01, 4A).
Giao diện phản hồi Rich Embed chuyên nghiệp:
Embed 1: Thông tin tổng quan, Tên bài, Bậc Tier/Rating, Chế độ thi đấu, Giới hạn & Toàn văn đề bài + Test ví dụ.
Embed 2 (hoặc Tab/Nút chuyển): Phân tích thuật toán chuyên sâu (Editorial) & Mã nguồn mẫu chuẩn AC.
Có kèm link jump đến tin nhắn lưu trữ trong kênh 1548627763467128912.
4. Tích Hợp Thông Báo Hoàn Thành Bài Freedom & Ranked
[MODIFY] 
services/judge.py
Khi hoàn thành chấm một bài Freedom (Mode 2 Sandbox) trong judge_submission:
Bổ sung thông tin mã tra cứu ID bài vào Embed kết quả gửi cho thí sinh:

📝 Mã Tra Cứu (Problem ID): `{problem.id}`
💡 Bạn có thể dùng lệnh `/search {problem.id}` bất cứ lúc nào để xem lại đề, thuật toán và code mẫu!
Tự động gọi ProblemArchiveService.archive_problem(...) để lưu trữ bài vào kênh 1548627763467128912.
[MODIFY] 
services/duel_service.py
Khi kết thúc chặng hoặc toàn bộ trận đấu Ranked 1:1 trong _send_individual_summaries_and_editorials:
Đảm bảo trong mỗi Embed gửi cho đấu thủ hiển thị rõ:

📝 Mã Tra Cứu (Problem ID): `{prob.id}`
💡 Dùng lệnh `/search {prob.id}` để tra cứu lại toàn bộ đề bài, thuật toán và code mẫu!
Tự động gọi ProblemArchiveService.archive_problem(...) để lưu trữ bài toán vào kênh 1548627763467128912.
[MODIFY] 
bot.py
Thêm cogs.search vào danh diện nạp Cogs ban đầu.
Verification Plan
Automated Tests
Chạy toàn bộ test suite hiện có:
powershell

python -m pytest
Tạo file test mới 
tests/test_profile_and_search.py
:
Kiểm thử kết xuất Profile Card 4K với cấu trúc 2 cột mới:
Case 1: Người chơi mới (0 trận Ranked, 0 bài Freedom) -> Kiểm tra cả 2 Empty State xuất hiện đúng chuẩn.
Case 2: Người chơi có cả 3 trận Ranked và 3 bài Freedom -> Kiểm tra tất cả các thẻ card được vẽ sắc nét, đúng tọa độ.
Case 3: Người chơi chỉ có bài Freedom mà chưa đấu Ranked (hoặc ngược lại).
Kiểm thử ProblemArchiveService:
Định dạng nội dung bài đăng lưu trữ chuẩn [PROBLEM_ARCHIVE] ID: <ID>.
Chống trùng lặp bài đã lưu trữ.
Tìm kiếm bài theo ID (Ranked ID và Freedom CF ID).
Kiểm thử lệnh /search:
Tìm bài tồn tại trả về embed hợp lệ.
Tìm bài không tồn tại trả về thông báo lỗi thân thiện.
Manual Verification
Render ảnh mẫu 4K ra thư mục artifacts và kiểm tra trực quan độ cân xứng của 2 cột Panel 3.