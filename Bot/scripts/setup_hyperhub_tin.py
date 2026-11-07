"""Thiết lập tự động toàn diện cho máy chủ HyperHub (Orbit cũ — CLB Tin Học & Đấu Trường Thi Đấu Tin Học).

Bao gồm:
1. 13 Role CLB Tin Học (Đồng Sáng Lập Orbit, Quản Lý HyperHub | Tin, Admin, Mod, Orbit Elite, Orbit Ultra,
   Tác Giả, Chuyên Tin, HSG Tin, Giỏi Tin, Khá Tin, Bình Thường, Học Sinh)
2. 12 Role Đấu Trường Thi Đấu Tin Học (👑 HT1 - Ranked ➔ ⭐ T8 - Ranked)
3. 6 Danh mục & 20 Kênh (Tích hợp nguyên bản Đấu Trường Thi Đấu Tin Học HyperHub:
   #✅・accounts, #📤・mode, #📋・contest, #📤・submit, #📋・ranked, #📋・winner, #✅・leaderboard
   cùng hệ thống kênh CLB Tin Học, Kho Đề Tin & Phòng Live Coding)
4. Tự động ghi ID các kênh thi đấu & 12 Role Ranked vào `Bot/.env` và `config.settings` để kích hoạt
   ngay lập tức hệ thống chấm bài Sandbox 17 ngôn ngữ, Codeforces Sync và Đấu Trường Ranked 1:1.

Cách chạy khi đã tạo server HyperHub và mời Bot vào:
    python scripts/setup_hyperhub_tin.py <guild_id>
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from scripts.setup_orbit_club import _get_token, api_req


RANKED_ROLES_SPEC = [
    {"key": "ht1", "env_ranked": "HT1_RANKED_ROLE_ID", "env_freedom": "HT1_FREEDOM_ROLE_ID", "name": "👑 HT1 - Ranked", "color": 0xFF0055},
    {"key": "mt1", "env_ranked": "MT1_RANKED_ROLE_ID", "env_freedom": "MT1_FREEDOM_ROLE_ID", "name": "💎 MT1 - Ranked", "color": 0xE91E63},
    {"key": "lt1", "env_ranked": "LT1_RANKED_ROLE_ID", "env_freedom": "LT1_FREEDOM_ROLE_ID", "name": "🏆 LT1 - Ranked", "color": 0x9C27B0},
    {"key": "ht2", "env_ranked": "HT2_RANKED_ROLE_ID", "env_freedom": "HT2_FREEDOM_ROLE_ID", "name": "🔱 HT2 - Ranked", "color": 0x673AB7},
    {"key": "mt2", "env_ranked": "MT2_RANKED_ROLE_ID", "env_freedom": "MT2_FREEDOM_ROLE_ID", "name": "⚜️ MT2 - Ranked", "color": 0x3F51B5},
    {"key": "lt2", "env_ranked": "LT2_RANKED_ROLE_ID", "env_freedom": "LT2_FREEDOM_ROLE_ID", "name": "🛡️ LT2 - Ranked", "color": 0x2196F3},
    {"key": "t3",  "env_ranked": "T3_RANKED_ROLE_ID",  "env_freedom": "T3_FREEDOM_ROLE_ID",  "name": "💠 T3 - Ranked",  "color": 0x00BCD4},
    {"key": "t4",  "env_ranked": "T4_RANKED_ROLE_ID",  "env_freedom": "T4_FREEDOM_ROLE_ID",  "name": "🔷 T4 - Ranked",  "color": 0x009688},
    {"key": "t5",  "env_ranked": "T5_RANKED_ROLE_ID",  "env_freedom": "T5_FREEDOM_ROLE_ID",  "name": "🔶 T5 - Ranked",  "color": 0x4CAF50},
    {"key": "t6",  "env_ranked": "T6_RANKED_ROLE_ID",  "env_freedom": "T6_FREEDOM_ROLE_ID",  "name": "⭐ T6 - Ranked",  "color": 0x8BC34A},
    {"key": "t7",  "env_ranked": "T7_RANKED_ROLE_ID",  "env_freedom": "T7_FREEDOM_ROLE_ID",  "name": "⭐ T7 - Ranked",  "color": 0xFFC107},
    {"key": "t8",  "env_ranked": "T8_RANKED_ROLE_ID",  "env_freedom": "T8_FREEDOM_ROLE_ID",  "name": "⭐ T8 - Ranked",  "color": 0x9E9E9E},
]


def _update_env_and_settings(updates: dict[str, str | int]) -> None:
    """Cập nhật các khóa cấu hình CP Arena / Ranked Duel vào Bot/.env và đối tượng settings đang chạy."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    remaining = {k: str(v) for k, v in updates.items() if v}
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        k = stripped.split("=", 1)[0].strip()
        if k in remaining:
            new_lines.append(f"{k}={remaining.pop(k)}")
        else:
            new_lines.append(line)

    if remaining:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append("# === HYPERHUB (ORBIT | TIN HỌC & CP ARENA) AUTO-GENERATED ===")
        for k, v in remaining.items():
            new_lines.append(f"{k}={v}")

    try:
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception:
        pass

    # Đồng bộ trực tiếp vào runtime settings nếu Bot đang chạy
    try:
        from config.settings import settings
        for k, v in updates.items():
            if hasattr(settings, k):
                try:
                    setattr(settings, k, int(v))
                except ValueError:
                    setattr(settings, k, v)
    except Exception:
        pass


def setup_hyperhub_guild(guild_id: str) -> dict:
    """Thiết lập trọn gói máy chủ HyperHub (CLB Tin Học + Đấu Trường Thi Đấu Tin Học)."""
    token = _get_token()
    if not token:
        return {"ok": False, "error": "Missing DISCORD_TOKEN"}

    st, guild = api_req(token, "GET", f"/guilds/{guild_id}")
    if st != 200:
        return {"ok": False, "status": st, "error": guild}

    _, bot_me = api_req(token, "GET", "/users/@me")
    bot_id = str(bot_me["id"])

    # 1. Đồng bộ 13 Role CLB Tin Học + 12 Role Thi Đấu Ranked (tổng 25 Roles)
    st_r, existing_roles = api_req(token, "GET", f"/guilds/{guild_id}/roles")
    if st_r != 200 or not isinstance(existing_roles, list):
        return {"ok": False, "error": f"Failed to fetch roles: {st_r}"}

    mod_perms = str(
        2 | 4 | 128 | 1024 | 2048 | 8192 | 16384 | 32768 | 65536
        | 4194304 | 8388608 | 16777216 | 134217728 | 268435456
        | 17179869184 | 1099511627776
    )

    club_roles = [
        {"key": "co_founder", "name": "👑 Đồng Sáng Lập Orbit", "color": 0xF59E0B, "hoist": True, "permissions": "8"},
        {"key": "club_manager", "name": "💻 Quản Lý HyperHub | Tin", "color": 0x6366F1, "hoist": True, "permissions": "8"},
        {"key": "admin", "name": "🛡️ Admin", "color": 0xF43F5E, "hoist": True, "permissions": "8"},
        {"key": "mod", "name": "⚔️ Mod", "color": 0x10B981, "hoist": True, "permissions": mod_perms},
        {"key": "elite", "name": "⚜️ Orbit Elite", "color": 0xFBBF24, "hoist": True, "permissions": "0"},
        {"key": "ultra", "name": "⚡ Orbit Ultra", "color": 0xC084FC, "hoist": True, "permissions": "0"},
        {"key": "author", "name": "✍️ Tác Giả", "color": 0xFF4FCB, "hoist": True, "permissions": "0"},
        {"key": "chuyen", "name": "🏆 Chuyên Tin", "color": 0xFB7185, "hoist": True, "permissions": "0"},
        {"key": "hsg", "name": "🥇 HSG Tin", "color": 0xFB923C, "hoist": True, "permissions": "0"},
        {"key": "gioi", "name": "💎 Giỏi Tin", "color": 0x38BDF8, "hoist": True, "permissions": "0"},
        {"key": "kha", "name": "📘 Khá Tin", "color": 0x4ADE80, "hoist": True, "permissions": "0"},
    ]
    cp_roles = [
        {"key": r["key"], "name": r["name"], "color": r["color"], "hoist": True, "permissions": "0"}
        for r in RANKED_ROLES_SPEC
    ]
    tail_roles = [
        {"key": "binh_thuong", "name": "🌱 Bình Thường", "color": 0x94A3B8, "hoist": False, "permissions": "0"},
        {"key": "hoc_sinh", "name": "🎓 Học Sinh", "color": 0x60A5FA, "hoist": True, "permissions": "0"},
    ]
    desired_roles = club_roles + cp_roles + tail_roles

    def _norm(s: str) -> str:
        cleaned = s.strip().lower()
        for prefix in ("👑", "💻", "🛡️", "⚔️", "⚜️", "⚡", "✍️", "🏆", "🥇", "💎", "📘", "🌱", "🎓", "🔱", "💠", "🔷", "🔶", "⭐"):
            cleaned = cleaned.replace(prefix, "").strip()
        return cleaned

    role_map: dict[str, str] = {}
    for r_spec in desired_roles:
        target_norm = _norm(r_spec["name"])
        matched = next(
            (er for er in existing_roles if _norm(er["name"]) == target_norm or er["name"].strip().lower() == r_spec["name"].lower()),
            None,
        )
        if matched:
            role_id = str(matched["id"])
            api_req(
                token,
                "PATCH",
                f"/guilds/{guild_id}/roles/{role_id}",
                {
                    "name": r_spec["name"],
                    "color": r_spec["color"],
                    "hoist": r_spec["hoist"],
                    "permissions": r_spec["permissions"],
                    "mentionable": True,
                },
            )
            role_map[r_spec["key"]] = role_id
        else:
            st_cr, created = api_req(
                token,
                "POST",
                f"/guilds/{guild_id}/roles",
                {
                    "name": r_spec["name"],
                    "color": r_spec["color"],
                    "hoist": r_spec["hoist"],
                    "permissions": r_spec["permissions"],
                    "mentionable": True,
                },
            )
            if st_cr in (200, 201) and isinstance(created, dict):
                role_map[r_spec["key"]] = str(created["id"])
            time.sleep(0.25)

    pos_payload = []
    base_pos = len(desired_roles) + 2
    for idx, r_spec in enumerate(desired_roles):
        rid = role_map.get(r_spec["key"])
        if rid:
            pos_payload.append({"id": rid, "position": base_pos - idx})
    if pos_payload:
        api_req(token, "PATCH", f"/guilds/{guild_id}/roles", pos_payload)

    # 2. Đồng bộ 6 Danh mục & 20 Kênh (Đấu Trường Thi Đấu Tin Học + CLB Tin Học)
    st_c, existing_chans = api_req(token, "GET", f"/guilds/{guild_id}/channels")
    if st_c != 200 or not isinstance(existing_chans, list):
        return {"ok": False, "error": f"Failed to fetch channels: {st_c}"}

    VIEW_CHANNEL = 1024
    SEND_MESSAGES = 2048
    CREATE_PUBLIC_THREADS = 34359738368
    SEND_MESSAGES_IN_THREADS = 274877906944

    readonly_overwrites = [
        {
            "id": guild_id,
            "type": 0,
            "allow": str(VIEW_CHANNEL),
            "deny": str(SEND_MESSAGES | CREATE_PUBLIC_THREADS | SEND_MESSAGES_IN_THREADS),
        }
    ]
    for k in ("co_founder", "club_manager", "admin", "mod"):
        if role_map.get(k):
            readonly_overwrites.append(
                {
                    "id": role_map[k],
                    "type": 0,
                    "allow": str(VIEW_CHANNEL | SEND_MESSAGES | CREATE_PUBLIC_THREADS | SEND_MESSAGES_IN_THREADS),
                    "deny": "0",
                }
            )

    staff_only_overwrites = [
        {
            "id": guild_id,
            "type": 0,
            "allow": "0",
            "deny": str(VIEW_CHANNEL),
        }
    ]
    for k in ("co_founder", "club_manager", "admin", "mod"):
        if role_map.get(k):
            staff_only_overwrites.append(
                {
                    "id": role_map[k],
                    "type": 0,
                    "allow": str(VIEW_CHANNEL | SEND_MESSAGES),
                    "deny": "0",
                }
            )

    STRUCTURE = [
        {
            "key": "cat_info",
            "name": "📌・THÔNG TIN HYPERHUB",
            "overwrites": readonly_overwrites,
            "channels": [
                {"key": "welcome", "name": "👋・chào-mừng", "type": 0, "overwrites": readonly_overwrites},
                {"key": "rules", "name": "📜・luật-hyperhub", "type": 0, "overwrites": readonly_overwrites},
                {"key": "announcements", "name": "📢・thông-báo", "type": 0, "overwrites": readonly_overwrites},
                {"key": "role_info", "name": "🎭・thông-tin-role", "type": 0, "overwrites": readonly_overwrites},
            ],
        },
        {
            "key": "cat_arena",
            "name": "⚔️・ĐẤU TRƯỜNG THI ĐẤU TIN HỌC",
            "overwrites": readonly_overwrites,
            "channels": [
                {"key": "cf_accounts", "name": "✅・accounts", "type": 0, "overwrites": readonly_overwrites},
                {"key": "cp_mode", "name": "📤・mode", "type": 0, "overwrites": readonly_overwrites},
                {"key": "cp_contest", "name": "📋・contest", "type": 0, "overwrites": readonly_overwrites},
                {"key": "cp_submit", "name": "📤・submit", "type": 0, "overwrites": readonly_overwrites},
                {"key": "cp_ranked", "name": "📋・ranked", "type": 0, "overwrites": readonly_overwrites},
                {"key": "cp_winner", "name": "📋・winner", "type": 0, "overwrites": readonly_overwrites},
                {"key": "cp_leaderboard", "name": "✅・leaderboard", "type": 0, "overwrites": readonly_overwrites},
            ],
        },
        {
            "key": "cat_discuss",
            "name": "💻・THẢO LUẬN & THUẬT TOÁN",
            "overwrites": [],
            "channels": [
                {"key": "chat", "name": "💭・chat-chung", "type": 0},
                {"key": "qa_subj", "name": "💻・hỏi-đáp-code", "type": 0},
                {"key": "vdc_subj", "name": "🏆・thuật-toán-hsg-tin", "type": 0},
            ],
        },
        {
            "key": "cat_vault",
            "name": "📚・KHO ĐỀ & TIỆN ÍCH TIN",
            "overwrites": [],
            "channels": [
                {"key": "get_docs", "name": "📥・kho-đề-tin", "type": 0, "overwrites": readonly_overwrites},
                {"key": "submit_docs", "name": "📤・đóng-góp-đề-tin", "type": 0, "overwrites": readonly_overwrites},
                {"key": "bot_cmds", "name": "🤖・lệnh-bot", "type": 0},
            ],
        },
        {
            "key": "cat_voice",
            "name": "🎙️・PHÒNG LIVE CODING & CHỮA ĐỀ",
            "overwrites": [],
            "channels": [
                {"key": "voice_study", "name": "🎧・live-coding", "type": 2},
                {"key": "voice_solve", "name": "📝・chữa-đề-thuật-toán", "type": 2},
            ],
        },
        {
            "key": "cat_staff",
            "name": "🔒・BAN QUẢN LÝ HYPERHUB",
            "overwrites": staff_only_overwrites,
            "channels": [
                {"key": "staff_chat", "name": "🛡️・bàn-điều-hành", "type": 0, "overwrites": staff_only_overwrites},
            ],
        },
    ]

    chan_map: dict[str, str] = {}
    cat_map: dict[str, str] = {}

    def _find_chan(name: str, ctype: int):
        n_clean = name.split("・")[-1].strip().lower()
        for c in existing_chans:
            if c.get("type") == ctype:
                c_clean = c.get("name", "").split("・")[-1].strip().lower()
                if c_clean == n_clean or c.get("name", "").strip().lower() == name.lower():
                    return c
        return None

    for cat_idx, cat_spec in enumerate(STRUCTURE):
        cat_obj = _find_chan(cat_spec["name"], 4)
        if cat_obj:
            cat_id = str(cat_obj["id"])
            api_req(
                token,
                "PATCH",
                f"/channels/{cat_id}",
                {
                    "name": cat_spec["name"],
                    "position": cat_idx,
                    "permission_overwrites": cat_spec["overwrites"],
                },
            )
        else:
            st_cat, created_cat = api_req(
                token,
                "POST",
                f"/guilds/{guild_id}/channels",
                {
                    "name": cat_spec["name"],
                    "type": 4,
                    "position": cat_idx,
                    "permission_overwrites": cat_spec["overwrites"],
                },
            )
            cat_id = str(created_cat["id"]) if st_cat in (200, 201) and isinstance(created_cat, dict) else None
            time.sleep(0.25)

        if cat_id:
            cat_map[cat_spec["key"]] = cat_id

        for ch_idx, ch_spec in enumerate(cat_spec["channels"]):
            ch_obj = _find_chan(ch_spec["name"], ch_spec["type"])
            payload = {
                "name": ch_spec["name"],
                "type": ch_spec["type"],
                "parent_id": cat_id,
                "position": ch_idx,
            }
            if "overwrites" in ch_spec:
                payload["permission_overwrites"] = ch_spec["overwrites"]

            if ch_obj:
                ch_id = str(ch_obj["id"])
                api_req(token, "PATCH", f"/channels/{ch_id}", payload)
                chan_map[ch_spec["key"]] = ch_id
            else:
                st_ch, created_ch = api_req(token, "POST", f"/guilds/{guild_id}/channels", payload)
                if st_ch in (200, 201) and isinstance(created_ch, dict):
                    chan_map[ch_spec["key"]] = str(created_ch["id"])
                time.sleep(0.25)

    # Cập nhật tên Server & Kênh hệ thống
    guild_title = "HyperHub | Orbit Tin Học"
    patch_guild_chans = {"name": guild_title}
    if chan_map.get("rules"):
        patch_guild_chans["rules_channel_id"] = chan_map["rules"]
    if chan_map.get("staff_chat"):
        patch_guild_chans["public_updates_channel_id"] = chan_map["staff_chat"]
    if chan_map.get("welcome"):
        patch_guild_chans["system_channel_id"] = chan_map["welcome"]
    api_req(token, "PATCH", f"/guilds/{guild_id}", patch_guild_chans)

    # Dọn các kênh mặc định dư thừa
    keep_ids = set(chan_map.values())
    st_c2, all_chans_now = api_req(token, "GET", f"/guilds/{guild_id}/channels")
    if st_c2 == 200 and isinstance(all_chans_now, list):
        keep_cat_ids = set(cat_map.values()) | {
            c.get("parent_id") for c in all_chans_now if str(c.get("id")) in keep_ids and c.get("parent_id")
        }
        for c in all_chans_now:
            cid = str(c["id"])
            cname = c.get("name", "").lower()
            if cid not in keep_ids and cid not in keep_cat_ids:
                if cname in ("general", "chung", "rules", "kênh chat", "kênh đàm thoại", "text channels", "voice channels", "kênh văn bản", "kênh thoại", "phòng chờ"):
                    api_req(token, "DELETE", f"/channels/{cid}")
                    time.sleep(0.2)

    # Tạo link mời vĩnh viễn tại #👋・chào-mừng
    invite_url = ""
    if chan_map.get("welcome"):
        st_inv, inv_data = api_req(
            token,
            "POST",
            f"/channels/{chan_map['welcome']}/invites",
            {"max_age": 0, "max_uses": 0, "unique": False},
        )
        if st_inv in (200, 201) and isinstance(inv_data, dict) and inv_data.get("code"):
            invite_url = f"https://discord.gg/{inv_data['code']}"

    # 3. Tự động lưu ID các kênh Đấu Trường & 12 Role Ranked vào Bot/.env và runtime settings
    env_updates: dict[str, str | int] = {
        "CATEGORY_ID": cat_map.get("cat_arena", "0"),
        "CF_ID": chan_map.get("cf_accounts", "0"),
        "CHON_ID": chan_map.get("cp_mode", "0"),
        "BAITAP_ID": chan_map.get("cp_contest", "0"),
        "SUBMIT_ID": chan_map.get("cp_submit", "0"),
        "RANKED_CHANNEL_ID": chan_map.get("cp_ranked", "0"),
        "WINNER_CHANNEL_ID": chan_map.get("cp_winner", "0"),
        "UP_RANK": chan_map.get("cp_leaderboard", "0"),
        "PROBLEM_ARCHIVE_CHANNEL_ID": chan_map.get("get_docs", "0"),
    }
    for r_spec in RANKED_ROLES_SPEC:
        rid = role_map.get(r_spec["key"], "0")
        if rid and rid != "0":
            env_updates[r_spec["env_ranked"]] = rid
            env_updates[r_spec["env_freedom"]] = rid

    _update_env_and_settings(env_updates)

    # 4. Đồng bộ các bảng thông tin cố định của CLB Tin Học & HyperHub
    def _sync_panel(ch_id: str | None, embeds: list):
        if not ch_id:
            return
        st_m, msgs = api_req(token, "GET", f"/channels/{ch_id}/messages?limit=20")
        bot_msgs = [m for m in (msgs if st_m == 200 and isinstance(msgs, list) else []) if str(m.get("author", {}).get("id")) == bot_id]
        if bot_msgs:
            target = bot_msgs[0]
            for extra in bot_msgs[1:]:
                api_req(token, "DELETE", f"/channels/{ch_id}/messages/{extra['id']}")
                time.sleep(0.2)
            api_req(token, "PATCH", f"/channels/{ch_id}/messages/{target['id']}", {"content": "", "embeds": embeds, "attachments": []})
        else:
            api_req(token, "POST", f"/channels/{ch_id}/messages", {"content": "", "embeds": embeds})
        time.sleep(0.25)

    def _rm(key: str, fallback: str) -> str:
        rid = role_map.get(key)
        return f"<@&{rid}>" if rid else f"**{fallback}**"

    _sync_panel(
        chan_map.get("rules"),
        [
            {
                "title": "📜 NỘI QUY HYPERHUB — CLB TIN HỌC & ĐẤU TRƯỜNG THUẬT TOÁN",
                "description": (
                    "Chào mừng bạn đến với **HyperHub | Orbit Tin Học** — Máy chủ CLB Tin Học & Đấu Trường Lập Trình Thi Đấu (Competitive Programming) trực thuộc hệ sinh thái **Orbit | Vietnam**.\n\n"
                    "**1. Tinh Thần Fair-Play Trong Thi Đấu Thuật Toán**\n"
                    f"• Tuyệt đối **nghiêm cấm sử dụng AI sinh code** (ChatGPT, Claude, DeepSeek, Copilot...) hoặc sao chép code trong các trận đấu **Ranked 1:1** tại <#{chan_map.get('cp_ranked', '')}>.\n"
                    "• Hệ thống **Anti-Cheat 2.0 (AST & Static Analyzer)** tự động quét mọi bài nộp. Vi phạm sẽ bị hủy kết quả, trừ Elo hoặc khóa quyền thi đấu.\n\n"
                    "**2. Văn Hóa Thảo Luận & Hỏi Đáp Code**\n"
                    f"• Khi hỏi bài tại <#{chan_map.get('qa_subj', '')}> hoặc <#{chan_map.get('vdc_subj', '')}>, hãy gửi kèm **Đề bài / Link bài + Ý tưởng đã thử + Code trong khối ` ```cpp ` hoặc ` ```py `**.\n"
                    "• Không nhờ giải hộ các cuộc thi đang diễn ra trực tiếp (Codeforces Live Round, VNOJ, HSG đang thi).\n\n"
                    "**3. Đóng Góp Đề Thi Tin Học & Vinh Danh Tác Giả**\n"
                    "• Chia sẻ đề thi HSG Tin Học, Chuyên Tin, Olympic 30/4, Duyên Hải Bắc Bộ tại **https://orbit-psi-black.vercel.app/#submit_doc** để nhận **Credit vĩnh viễn + 100 XP + Role ✍️ Tác Giả**."
                ),
                "color": 0x6366F1,
                "footer": {"text": "HyperHub | Orbit Tin Học • Fair-Play · Algorithms · Mastery"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("announcements"),
        [
            {
                "title": "⚔️ KHÔI PHỤC ĐẤU TRƯỜNG THI ĐẤU TIN HỌC HYPERHUB & HỆ SINH THÁI ORBIT",
                "description": (
                    "**HyperHub** chính thức vận hành song hành 2 phân hệ: **CLB Học Thuật Tin Học (Orbit | Tin)** và **Đấu Trường Lập Trình Thi Đấu (CP Arena & Ranked Duel 1:1)**!\n\n"
                    "🔥 **ĐẤU TRƯỜNG THI ĐẤU TIN HỌC (CP ARENA):**\n"
                    f"• <#{chan_map.get('cf_accounts', '')}> — Liên kết tài khoản **Codeforces** tự động trong 60 giây.\n"
                    f"• <#{chan_map.get('cp_mode', '')}> — Sổ tay toàn diện 6 Embeds & Chọn chế độ **Freedom Mode** / **Ranked 1:1**.\n"
                    f"• <#{chan_map.get('cp_contest', '')}> — Danh mục cuộc thi Codeforces phân loại theo Div.1–Div.4 & 12 Bậc Tier.\n"
                    f"• <#{chan_map.get('cp_submit', '')}> — Trạm nộp code chấm trực tiếp bằng **Sandbox 17 ngôn ngữ** (C++17/20/23, Python, PyPy, Java, Rust, Go, Pascal...).\n"
                    f"• <#{chan_map.get('cp_ranked', '')}> — Sảnh ghép trận đối kháng **1v1 thời gian thực** (Hệ thống 2 mạng ❤️❤️ & Dynamic Elo).\n"
                    f"• <#{chan_map.get('cp_leaderboard', '')}> — Bảng xếp hạng Top 50 Freedom & Ranked 1:1 cập nhật tự động.\n\n"
                    "🎁 **ĐẶC QUYỀN BAN QUẢN LÝ CLB ORBIT:**\n"
                    "• Quản lý các phân khu CLB Orbit được cấp **DeepSeek V4.1 Flash vô thời hạn** *(ngang Gemini / GPT Pro)* phục vụ nghiên cứu và biên soạn chuyên đề."
                ),
                "color": 0x3B82F6,
                "footer": {"text": "HyperHub | Orbit Tin Học • Đấu Trường Thuật Toán & Kho Đề Chuyên Tin"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("role_info"),
        [
            {
                "title": "🎭 HỆ THỐNG VAI TRÒ CLB TIN HỌC & 12 BẬC RANK THI ĐẤU HYPERHUB",
                "description": (
                    "👑 **ĐIỀU HÀNH & QUẢN TRỊ**\n"
                    f"• {_rm('co_founder', 'Đồng Sáng Lập Orbit')} • {_rm('club_manager', 'Quản Lý HyperHub | Tin')} • {_rm('admin', 'Admin')} • {_rm('mod', 'Mod')}\n\n"
                    "⚜️ **THÀNH VIÊN HOÀNG GIA & ĐÓNG GÓP**\n"
                    f"• {_rm('elite', 'Orbit Elite')} • {_rm('ultra', 'Orbit Ultra')} • {_rm('author', '✍️ Tác Giả')}\n\n"
                    "💻 **DANH HIỆU HỌC THUẬT TIN HỌC**\n"
                    f"• {_rm('chuyen', '🏆 Chuyên Tin')} • {_rm('hsg', '🥇 HSG Tin')} • {_rm('gioi', '💎 Giỏi Tin')} • {_rm('kha', '📘 Khá Tin')} • {_rm('binh_thuong', '🌱 Bình Thường')} • {_rm('hoc_sinh', '🎓 Học Sinh')}\n\n"
                    "⚔️ **12 BẬC RANK ĐẤU TRƯỜNG THI ĐẤU TIN HỌC (TỰ ĐỘNG THĂNG HẠNG THEO RATING PTS)**\n"
                    f"• **Tier 1 (Đỉnh Cao — Div.1):** {_rm('ht1', '👑 HT1')} (`3000+ pts`) • {_rm('mt1', '💎 MT1')} (`2600+`) • {_rm('lt1', '🏆 LT1')} (`2250+`)\n"
                    f"• **Tier 2 (Cao Thủ — Div.2):** {_rm('ht2', '🔱 HT2')} (`1950+`) • {_rm('mt2', '⚜️ MT2')} (`1700+`) • {_rm('lt2', '🛡️ LT2')} (`1450+`)\n"
                    f"• **Tier 3–5 (Thực Chiến — Div.3):** {_rm('t3', '💠 T3')} (`1200+`) • {_rm('t4', '🔷 T4')} (`950+`) • {_rm('t5', '🔶 T5')} (`750+`)\n"
                    f"• **Tier 6–8 (Khởi Đầu — Div.4):** {_rm('t6', '⭐ T6')} (`550+`) • {_rm('t7', '⭐ T7')} (`400+` — Mở khóa Ranked 1:1) • {_rm('t8', '⭐ T8')} (`0+`)"
                ),
                "color": 0xF59E0B,
                "footer": {"text": "HyperHub | Orbit Tin Học • Nộp bài tại #submit hoặc đấu 1v1 tại #ranked để thăng hạng tự động"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("get_docs"),
        [
            {
                "title": "📥 KHO ĐỀ THI CHUYÊN TIN, HSG TIN HỌC & LƯU TRỮ BÀI TẬP",
                "description": (
                    "Truy cập toàn bộ đề thi môn **Tin Học** (Đề thi HSG Tỉnh/Quốc gia, Olympic 30/4, Duyên Hải Bắc Bộ, Tuyển sinh Chuyên Tin & THPT) trên Web Portal:\n\n"
                    "🌐 **Mở Kho Đề Trực Tuyến:** **https://orbit-psi-black.vercel.app/#vault**\n\n"
                    "• **Tra cứu đề bài & Editorial CP Arena:** Gõ `/search <mã_bài>` (VD: `/search 1700A`, `/search PRB-T8-01`).\n"
                    "• **Tra cứu đề thi trường/sở:** Gõ `/timde Tin`, `/layde <id>`, `/luyende`."
                ),
                "color": 0xFF4FCB,
                "footer": {"text": "HyperHub | Orbit Tin Học • Kho Đề Chuyên Tin & Problem Archive"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("submit_docs"),
        [
            {
                "title": "📤 ĐÓNG GÓP ĐỀ THI TIN HỌC & NHẬN ROLE TÁC GIẢ",
                "description": (
                    "Chia sẻ đề thi HSG Tin Học, đề Chuyên Tin hoặc tài liệu Cấu trúc dữ liệu & Giải thuật tại:\n\n"
                    "🌐 **Cổng nộp đề:** **https://orbit-psi-black.vercel.app/#submit_doc**\n\n"
                    "• Hiển thị **Tên + Avatar Discord (Credit)** vĩnh viễn trên thẻ đề và tự động nhận role "
                    + _rm("author", "✍️ Tác Giả")
                    + "."
                ),
                "color": 0x9B5CFF,
                "footer": {"text": "HyperHub | Orbit Tin Học • Kho Đề Thi & Tài Liệu Học Tập Mở"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("welcome"),
        [
            {
                "title": "💻 CHÀO MỪNG ĐẾN VỚI HYPERHUB | ORBIT TIN HỌC",
                "description": (
                    "Chào mừng bạn gia nhập **HyperHub** — Ngôi nhà chung của cộng đồng **Lập Trình Thi Đấu (Competitive Programming)** và **CLB Học Thuật Tin Học Orbit**!\n\n"
                    "🧭 **LỘ TRÌNH BẮT ĐẦU NHANH:**\n"
                    f"1️⃣ Đọc nội quy & quy tắc Anti-Cheat tại <#{chan_map.get('rules', '')}>.\n"
                    f"2️⃣ Liên kết tài khoản Codeforces tại <#{chan_map.get('cf_accounts', '')}> và chọn chế độ thi đấu tại <#{chan_map.get('cp_mode', '')}>.\n"
                    f"3️⃣ Duyệt danh mục bài tập tại <#{chan_map.get('cp_contest', '')}>, nộp code chấm trực tiếp tại <#{chan_map.get('cp_submit', '')}> hoặc so tài 1v1 tại <#{chan_map.get('cp_ranked', '')}>.\n"
                    f"4️⃣ Tải đề Chuyên Tin / HSG Tin Học tại <#{chan_map.get('get_docs', '')}> (**https://orbit-psi-black.vercel.app/#vault**)."
                ),
                "color": 0x6366F1,
                "footer": {"text": "HyperHub | Orbit Tin Học • Code · Compete · Conquer"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("bot_cmds"),
        [
            {
                "title": "🤖 BẢNG LỆNH BOT — HYPERHUB & ĐẤU TRƯỜNG TIN HỌC",
                "description": (
                    "**⚔️ LỆNH THI ĐẤU TIN HỌC (CP ARENA & DUEL 1:1):**\n"
                    "• `/profile [user]` — Xem hồ sơ Competitive Programming, điểm Rating (pts), Rank và lịch sử AC.\n"
                    "• `/search <id>` — Tra cứu đề bài, thuật toán (Editorial) và code mẫu AC theo mã bài (`1700A`, `PRB-T8-01`...).\n"
                    "• `/view [id]` — Chế độ Khán Giả: Theo dõi trực tiếp các trận đấu Ranked 1:1 đang diễn ra.\n"
                    "• Trong phòng đấu 1v1 (`#⚔️・duel-xxxxxx`): Gửi trực tiếp file code (`.cpp`, `.py`, `.java`...) hoặc gõ `.list`, `.test`, `.close`.\n\n"
                    "**📚 LỆNH KHO ĐỀ & LUYỆN TẬP:**\n"
                    "• `/timde <từ khóa>` — Tìm đề thi Tin Học / HSG / Chuyên Tin.\n"
                    "• `/layde <id>` — Tải file đề thi theo mã ID.\n"
                    "• `/luyende` — Bốc đề ngẫu nhiên rèn phản xạ."
                ),
                "color": 0x10B981,
                "footer": {"text": "HyperHub | Orbit Tin Học • Hệ thống chấm tự động 17 ngôn ngữ"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("staff_chat"),
        [
            {
                "title": "🛡️ SỔ TAY BAN QUẢN LÝ — HYPERHUB | ORBIT TIN HỌC",
                "description": (
                    "Kênh điều hành nội bộ dành riêng cho **Đồng Sáng Lập Orbit**, **Quản Lý HyperHub | Tin**, **Admin** và **Mod**.\n\n"
                    "🎯 **1. CƠ CHẾ TỰ ĐỘNG HÓA ĐẤU TRƯỜNG CP ARENA:**\n"
                    f"• Toàn bộ 6 trạm tương tác (<#{chan_map.get('cf_accounts', '')}>, <#{chan_map.get('cp_mode', '')}>, <#{chan_map.get('cp_contest', '')}>, <#{chan_map.get('cp_submit', '')}>, <#{chan_map.get('cp_ranked', '')}>, <#{chan_map.get('cp_leaderboard', '')}>) đã được gắn ID tự động vào `.env` và Bot tự động khởi tạo bảng điều khiển.\n"
                    "• 12 Role Ranked (`👑 HT1 - Ranked` ➔ `⭐ T8 - Ranked`) được Bot **tự động cấp & nâng hạng** khi thành viên tăng điểm Rating.\n"
                    "• Quản lý có thể dùng lệnh `/setup_mode` bất kỳ lúc nào để làm mới 6 Embeds Sổ Tay Đấu Trường.\n\n"
                    "⚡ **2. QUYỀN TỰ CHỦ XÉT DUYỆT ROLE HỌC THUẬT:**\n"
                    f"• Quản lý CLB chủ động xét cấp các role {_rm('chuyen', '🏆 Chuyên Tin')}, {_rm('hsg', '🥇 HSG Tin')}, {_rm('gioi', '💎 Giỏi Tin')}, {_rm('kha', '📘 Khá Tin')} cho thành viên.\n"
                    "• Thành viên đóng góp đề Tin Học trên Web sẽ được Bot tự động cấp role "
                    + _rm("author", "✍️ Tác Giả")
                    + " và đăng thông báo vào <#"
                    + chan_map.get("get_docs", "")
                    + ">."
                ),
                "color": 0xF59E0B,
                "footer": {"text": "HyperHub | Orbit Tin Học • Bàn Điều Hành Nội Bộ"},
            }
        ],
    )

    return {
        "ok": True,
        "club_code": "tin",
        "guild_id": guild_id,
        "guild_name": guild_title,
        "invite_url": invite_url,
        "roles": role_map,
        "categories": cat_map,
        "channels": chan_map,
        "cp_arena_env": env_updates,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python scripts/setup_hyperhub_tin.py <guild_id>")
        sys.exit(1)
    gid = sys.argv[1].strip()
    res = setup_hyperhub_guild(gid)
    print(json.dumps(res, ensure_ascii=False, indent=2))
