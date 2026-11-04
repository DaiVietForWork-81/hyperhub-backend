# Orbit Upgrade — Kế hoạch triển khai (2026-11-03)

> **Trạng thái:** Đang thực thi bởi agent (user đã giao toàn quyền: "bạn đi").
> Từng bước có checkbox; cập nhật khi xong.

**Mục tiêu:** Đưa hệ sinh thái Orbit (`D:\Project`) về trạng thái nhất quán, sạch, được kiểm chứng — hoàn tất rebrand Orbit, chốt việc dở, dọn rác, cập nhật docs. Sau đó nâng cấp thư viện `D:\Skills` (phase 2).

**Bối cảnh thực tế (đã xác minh 03/11):**
- Brand chuẩn hiện tại: **Orbit | Vietnam** (bot repo rebrand 30/10, web repo 02/11 "Orbit Hub", web URL `orbit-psi-black.vercel.app`).
- 3 repo lồng nhau: root = `hyperhub-backend` (track Bot/ + DocInspector/ + docs/ + .agents/), `Bot/` = `hyperhub-bot`, `Web/` = `Hyperhub` (root ignore Web/).
- Tình trạng: Web repo sạch; Bot repo dở 5 file (+544/−10); root repo dở 96 mục (Bot sync, DocInspector v2 ~30 file, skills ~35 mục, docs…).
- Kiểm chứng nền: Bot tests 236 passed/1 failed (fail = edge-tts 403 từ mạng, trong `not_finished/`); DocInspector 74 passed/1 skipped; Web build pass.

**Ràng buộc bất biến:**
- Giữ nguyên stack & kiến trúc 3 repo. **Không push GitHub** (chờ user xác nhận — push Web sẽ trigger Vercel deploy).
- Không đổi tên file `.bat/.vbs` (shortcut Startup phụ thuộc) — chỉ sửa nội dung text bên trong.
- Giữ nguyên khóa localStorage/custom-event `hyperhub_*`, URL/ID thật (repo name `hyperhub-bot`, domain legacy trong allowlist, Discord IDs, invite links).
- Chỉ đổi chuỗi hiển thị/comment/docstring branding. Không đụng logic nghiệp vụ.
- Mọi thay đổi phải chạy lại test/build tương ứng trước khi commit.

---

## T1 — Rebrand nốt tàn dư HyperHub (source code)

**Files:**
- `main.py` — banner, docstring, messages
- `Bot/bot.py` — docstring, comment "HyperHub Services", logger msg, thread prefix `HyperHubWorker`
- `Bot/utils/embeds.py` — hằng số `HYPERHUB_COLOR` → `ORBIT_COLOR` (grep usages trước)
- `Bot/utils/bootstrap.py` — text hiển thị (GIỮ env var `HYPERHUB_UPDATED_RESTARTED`, repo URL `hyperhub-bot` vì là tên thật)
- `Web/src/utils/apiConfig.ts` — comment header + line 36 (giữ nguyên mọi logic/khóa)
- `Web/src/components/Dashboard.tsx` — comment line 1460 (giữ nguyên khóa `hyperhub_*`)
- `Web/src/components/AdminPanel.tsx` — chuỗi mô tả commit (đổi "hyperhub-bot" → "repo Bot" hoặc giữ — quyết định khi xem)
- `Web/app.py` — docstring đầu file
- `start_hyperhub.bat`, `stop_hyperhub.bat`, `restart_bot_only.bat`, `start_hidden.vbs` — text hiển thị → Orbit

**Steps:**
- [ ] 1. Grep usages `HYPERHUB_COLOR` → nếu chỉ trong embeds.py, rename + cập nhật comment.
- [ ] 2. Sửa từng file, chỉ chuỗi branding.
- [ ] 3. Verify: `python -m pytest -q` (Bot — đảm bảo không vỡ), `python -m py_compile main.py` + `Web/app.py`, `npm run build` (Web).
- [ ] 4. Commit: Bot repo (gộp T2), Web repo riêng, `main.py` để chung commit root T4.

## T2 — Chốt nốt việc dở ở Bot repo (5 file + rebrand)

**Files:** `cogs/info_board_cog.py` (+79), `services/api_bridge.py` (+459), `services/antivirus_scanner.py`, `scripts/bulk_upload_to_discord.py`, `services/system_sync_service.py` (+ rebrand T1 files).

**Steps:**
- [ ] 1. Skim diff 2 file lớn để hiểu nội dung → viết message chuẩn.
- [ ] 2. Verify: pytest Bot (đã pass với working tree này — chạy lại sau rebrand edits).
- [ ] 3. Commit (1–2 commit logic, vd: `feat(bridge): ...` + `refactor(brand): ...`).

## T3 — Chốt DocInspector v2 (root repo)

**Files:** 7 modified + 21 new (`smart_pipeline.py`, `consensus_engine.py`, `trainer.py`, `ai_extractor.py`, `layout_analyzer.py`, … + 4 test files).

**Steps:**
- [ ] 1. Xem nhanh vài file mới (docstring) để viết message; kiểm tra `training_history.json`/`calibration_weights.json`/`*.csv`/`*.html` có nên commit không (artifacts → cân nhắc gitignore).
- [ ] 2. Verify: `python -m pytest -q` trong `DocInspector/` (đã 74 passed).
- [ ] 3. Commit: `feat(inspector): ...`.

## T4 — Root repo: dọn & sync

**Steps:**
- [ ] 1. `.gitignore` root: bổ sung ignore cho local-only sau khi ngó nhanh: `HyperHub-Web/`, `web-test/`, `KhoaHoc/`, `Skills/backup-agent-skills/`, `.taste-skill/`, `omi-models.txt` (quyết định từng mục: commit hay ignore).
- [ ] 2. `git rm package.json package-lock.json` (vestigial npm root, không script nào dùng).
- [ ] 3. Commit A — sync Bot/ theo hyperhub-bot (sau T2): `chore(sync): Bot/ theo hyperhub-bot ...`.
- [ ] 4. Commit B — DocInspector v2 (T3).
- [ ] 5. Commit C — skills refresh `.agents/skills` (xóa lucian-uxui/ui-motion-web, thêm ~30 skills) + `AGENTS.md`, `GEMINI.md`, `docs/` gồm plan này.
- [ ] 6. Commit D — cleanup (rm npm root + .gitignore edits + main.py rebrand).

## T5 — Cleanup máy cục bộ

- [ ] 1. `D:\Project\bot.db` (131KB orphan, git-ignored): kiểm tra nhanh user/tables → xóa nếu đúng là DB test cũ (list.md nói đã xóa nhưng còn).
- [ ] 2. Kiểm tra `Bot/data/bot.db` (DB chính) — không đụng.

## T6 — Test edge-tts chịu lỗi mạng (nice-to-have)

- [ ] 1. `Bot/not_finished/exam_generator/tests/test_listening_exam_service.py`: khi service ngoài chặn (403/timeout) → `pytest.skip` kèm lý do thay vì fail cứng.
- [ ] 2. Verify: chạy riêng file test đó.

## T7 — Docs overhaul

- [ ] 1. `README.md` root: viết lại theo Orbit | Vietnam hiện tại (hybrid cloud Bot↔Turso↔Vercel, 3 repo, cách chạy thật, tính năng web mới: Hub/forum/courses). Ngắn gọn, đúng thực tế.
- [ ] 2. `list.md`: cập nhật tiêu đề + thêm mục "7. Phiên nâng cấp 2026-11-03" (tóm tắt việc đã làm phiên này).
- [ ] 3. Kiểm tra `Web/README.md` còn đúng không (chỉ sửa nếu lệch nặng).

## T8 — Kiểm chứng tổng & bàn giao

- [ ] 1. Chạy full: Bot pytest, DocInspector pytest, `npm run build`, `python main.py --help`, `py_compile` các file sửa.
- [ ] 2. `git status` cả 3 repo — kỳ vọng sạch (trừ mục cố ý ignore/local).
- [ ] 3. Cache update + log-skill (`general`, `brainstorming`, `writing-plans`).
- [ ] 4. Báo cáo user: việc đã làm, bằng chứng, việc còn lại (push?, Bot/DocInspector cũ, ngrok legacy…).

---

## Ghi chú quyết định
- `Bot/DocInspector/` (bản cũ, thiếu file v2): KHÔNG đụng phiên này — cần xác nhận deployment bot có self-contained không.
- ngrok trong `start_hidden.vbs`: giữ (chưa rõ còn dùng cho AdminPanel allowlist hay không).
- Tên file `start_hyperhub.bat` v.v.: giữ tên, chỉ sửa text.
- CRLF/LF: không thêm `.gitattributes` phiên này (tránh churn lớn); ghi chú lại.
