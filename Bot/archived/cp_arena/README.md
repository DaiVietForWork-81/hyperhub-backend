# Lưu trữ: Dự án Competitive Programming Arena (Ranked 1:1 & Freedom Mode)

Ngày lưu trữ: 2026-10-07
Lý do: Ngừng toàn bộ mảng thi đấu CP (ranked/freedom), tập trung vào kho đề + web.

## Nội dung đã chuyển vào đây

- `cogs/`: codeforces, submission, leaderboard, contest, mode_selector, search, music
  (toàn bộ slash commands thi đấu, panels kênh accounts/mode/submit/rank/contest)
- `services/`: cf_sync, codeforces_api, problem_fetcher, problem_archive, judge,
  ai_detector, rating (chấm Themis, sync Codeforces, tính rating)
- `judge/`: checker, languages, sandbox, static_analyzer, testcase_generator
- `tests/`: test_codeforces_api, test_judge_checker, test_judge_e2e, test_languages,
  test_multi_contest_simulation, test_problem_archive, test_rank, test_rating,
  test_mode_selector, test_ai_detector, test_ai_fairness

## Giữ lại ngoài này (dùng chung, KHÔNG lưu trữ)

- `services/rank.py`: ai_generator + admin vẫn dùng
- `services/problem_types.py`: ai_generator vẫn dùng
- `database/models.py`: giữ nguyên schema (dữ liệu xếp hạng cũ còn trong bot.db)

## Cách khôi phục (nếu cần)

1. Copy ngược các file về `Bot/cogs/`, `Bot/services/`, `Bot/judge/`, `Bot/tests/`.
2. Thêm lại vào `INITIAL_EXTENSIONS` trong `Bot/bot.py`.
3. Bỏ `prune_tree_commands` allowlist hoặc thêm lệnh vào `COMMAND_ALLOWLIST`.
4. Xem `archived/duel_arena/` cho phần Ranked Duel 1:1 đã lưu trước đó.
