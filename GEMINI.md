## Thư viện Skills dùng chung tại D:\Skills (mọi agent)

Máy có thư viện ~42.149 skills chuyên sâu tại `D:\Skills` (240 nguồn, 26 domain).
Skill tối thượng `/general` (Universal Master Orchestrator tổng hợp toàn bộ Web UI Master 6-in-1, Superpowers Lifecycle, Gemini AI SDK và router D:\Skills `sgeneral`) đã đăng ký sẵn, sử dụng thường trực và liên tục.

- Kích hoạt kỹ năng: Sử dụng `/general` (hoặc `sgeneral`) cho mọi task kỹ thuật, lập trình, tối ưu, đọc PDF/tài liệu, hoặc task đa lĩnh vực.
- Tìm skill nhanh: `node D:\Skills\tools\find-skill.mjs "tu khoa tieng Anh" --limit 5`
- Bản đồ 26 domain + quy tắc: đọc phần liên quan của `D:\Skills\SKILLS.md`
- Cache định hướng nhanh: `D:\Skills\CACHE.md`
- Nạp tối đa 3 skill/lần (cho task đơn lẻ), tối đa 5 skill khi orchestrate qua `/general`.
- KHÔNG đọc nguyên INDEX.md/index.json. Không tìm thấy skill thì làm trực tiếp, không bịa.
