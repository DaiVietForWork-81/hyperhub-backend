"""Bộ khung nhân bản & thiết lập tự động 5 giây cho toàn bộ Hệ Sinh Thái CLB Chuyên Môn Orbit.

Hỗ trợ đầy đủ 10 phân khu CLB:
- toan  : Orbit | Toán (ID: 1567904557076316250)
- van   : Orbit | Văn
- anh   : Orbit | Anh
- ly    : Orbit | Lý
- hoa   : Orbit | Hóa
- sinh  : Orbit | Sinh
- lsdl  : Orbit | LS ĐL
- tin   : Orbit | Tin
- gdcd  : Orbit | GDCD
- trung : Orbit | Trung

Cách dùng nhanh khi có Server ID mới:
    python scripts/setup_orbit_club.py <ma_mon> <guild_id>
Ví dụ:
    python scripts/setup_orbit_club.py anh 1234567890123456789
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://discord.com/api/v10"

# Cấu hình chi tiết cho từng CLB Chuyên Môn thuộc Hệ Sinh Thái Orbit
CLUB_PRESETS: dict[str, dict] = {
    "toan": {
        "code": "toan",
        "short_name": "Toán",
        "full_subject": "Toán Học",
        "guild_name": "Orbit | Toán",
        "emoji": "📐",
        "color": 0xA855F7,
        "slug": "toán",
        "vdc_channel": "🧮・góc-chuyên-vđc",
        "topics_desc": "Đại số, Giải tích, Hình học, Tổ hợp - Xác suất (THCS • THPT • ĐGNL HSA/APT • HSG & Chuyên Toán)",
        "guild_id": "1567904557076316250",
        "managers_note": "Dai Viet (Owner Orbit) trực tiếp quản lý",
    },
    "van": {
        "code": "van",
        "short_name": "Văn",
        "full_subject": "Ngữ Văn",
        "guild_name": "Orbit | Văn",
        "emoji": "📜",
        "color": 0xF43F5E,
        "slug": "văn",
        "vdc_channel": "✒️・nghị-luận-chuyên-văn",
        "topics_desc": "Đọc hiểu văn bản mới, Nghị luận xã hội, Nghị luận văn học & Lý luận văn học (THCS • THPT • HSG & Chuyên Văn)",
        "guild_id": "",
        "managers_note": "Đang cập nhật Ban Quản Lý",
    },
    "anh": {
        "code": "anh",
        "short_name": "Anh",
        "full_subject": "Tiếng Anh",
        "guild_name": "Orbit | Anh",
        "emoji": "🇬🇧",
        "color": 0x3B82F6,
        "slug": "anh",
        "vdc_channel": "🎓・ielts-sat-chuyên-anh",
        "topics_desc": "Ngữ pháp, Từ vựng, Đọc hiểu THPT 2025, IELTS, SAT & Đề Chuyên Anh / HSG",
        "guild_id": "",
        "managers_note": "Dai Viet & Đồng Quản Lý điều hành",
    },
    "ly": {
        "code": "ly",
        "short_name": "Lý",
        "full_subject": "Vật Lý",
        "guild_name": "Orbit | Lý",
        "emoji": "⚡",
        "color": 0x06B6D4,
        "slug": "lý",
        "vdc_channel": "🔬・vật-lý-chuyên-sâu",
        "topics_desc": "Cơ học, Nhiệt học, Điện từ, Quang học & Vật lý hiện đại (THCS • THPT • ĐGNL • HSG & Chuyên Lý)",
        "guild_id": "",
        "managers_note": "Đang tuyển Quản Lý CLB (Quyền lợi: DeepSeek V4.1 Flash vô thời hạn)",
    },
    "hoa": {
        "code": "hoa",
        "short_name": "Hóa",
        "full_subject": "Hóa Học",
        "guild_name": "Orbit | Hóa",
        "emoji": "🧪",
        "color": 0x10B981,
        "slug": "hóa",
        "vdc_channel": "⚗️・hóa-chuyên-vđc",
        "topics_desc": "Hóa vô cơ, Hóa hữu cơ, Hóa đại cương & Bài toán thực tiễn chuẩn 2025 (THCS • THPT • HSG & Chuyên Hóa)",
        "guild_id": "",
        "managers_note": "Đang tuyển Quản Lý CLB (Quyền lợi: DeepSeek V4.1 Flash vô thời hạn)",
    },
    "sinh": {
        "code": "sinh",
        "short_name": "Sinh",
        "full_subject": "Sinh Học",
        "guild_name": "Orbit | Sinh",
        "emoji": "🧬",
        "color": 0x22C55E,
        "slug": "sinh",
        "vdc_channel": "🔬・di-truyền-sinh-chuyên",
        "topics_desc": "Sinh học tế bào, Di truyền học, Tiến hóa & Sinh thái học (THCS • THPT • ĐGNL • HSG & Chuyên Sinh)",
        "guild_id": "",
        "managers_note": "Đang tuyển Quản Lý CLB (Quyền lợi: DeepSeek V4.1 Flash vô thời hạn)",
    },
    "lsdl": {
        "code": "lsdl",
        "short_name": "LS ĐL",
        "full_subject": "Sử - Địa",
        "guild_name": "Orbit | LS ĐL",
        "emoji": "🌍",
        "color": 0xF59E0B,
        "slug": "sử-địa",
        "vdc_channel": "🗺️・chuyên-sâu-sử-địa",
        "topics_desc": "Lịch sử Việt Nam & Thế giới, Địa lý tự nhiên, kinh tế - xã hội & Atlat/Biểu đồ (THCS • THPT • HSG)",
        "guild_id": "",
        "managers_note": "Đang tuyển Quản Lý CLB (Quyền lợi: DeepSeek V4.1 Flash vô thời hạn)",
    },
    "tin": {
        "code": "tin",
        "short_name": "Tin",
        "full_subject": "Tin Học",
        "guild_name": "HyperHub | Orbit Tin Học",
        "emoji": "💻",
        "color": 0x6366F1,
        "slug": "tin",
        "vdc_channel": "🏆・thuật-toán-hsg-tin",
        "topics_desc": "Lập trình C++ / Python, Cấu trúc dữ liệu & Giải thuật, Đấu trường Competitive Programming (Codeforces & Ranked 1:1), Đề thi HSG Tin học & Chuyên Tin",
        "guild_id": "",
        "managers_note": "Ban Quản Lý Chuyên Tin / HyperHub",
    },
    "gdcd": {
        "code": "gdcd",
        "short_name": "GDCD",
        "full_subject": "GDKT & Pháp Luật",
        "guild_name": "Orbit | GDCD",
        "emoji": "⚖️",
        "color": 0xEC4899,
        "slug": "gdcd",
        "vdc_channel": "🏛️・tình-huống-pháp-luật",
        "topics_desc": "Giáo dục Kinh tế & Pháp luật, Xử lý tình huống thực tiễn & Ôn thi THPT / HSG",
        "guild_id": "",
        "managers_note": "Đang tuyển Quản Lý CLB (Quyền lợi: DeepSeek V4.1 Flash vô thời hạn)",
    },
    "trung": {
        "code": "trung",
        "short_name": "Trung",
        "full_subject": "Tiếng Trung",
        "guild_name": "Orbit | Trung",
        "emoji": "🏮",
        "color": 0xEF4444,
        "slug": "trung",
        "vdc_channel": "🀄・luyện-hsk-khối-d4",
        "topics_desc": "Hán ngữ giao tiếp, Ngữ pháp & Từ vựng HSK 1–6, Ôn thi THPT Tiếng Trung (Khối D4) & Chuyên Trung",
        "guild_id": "",
        "managers_note": "Đang tuyển Quản Lý CLB (Quyền lợi: DeepSeek V4.1 Flash vô thời hạn)",
    },
}


def _get_token() -> str:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DISCORD_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("DISCORD_TOKEN", "")


def api_req(token: str, method: str, path: str, payload=None, retries: int = 4):
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://orbit-psi-black.vercel.app, 1.0)",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        if e.code == 429 and retries > 0:
            try:
                retry_after = float(json.loads(err_body).get("retry_after", 1.5))
            except Exception:
                retry_after = 1.5
            time.sleep(retry_after + 0.25)
            return api_req(token, method, path, payload, retries - 1)
        return e.code, err_body
    except Exception as e:
        if retries > 0:
            time.sleep(1.0)
            return api_req(token, method, path, payload, retries - 1)
        return 500, str(e)


def build_desired_roles(club: dict) -> list[dict]:
    short = club["short_name"]
    emoji = club["emoji"]
    mod_perms = str(
        2 | 4 | 128 | 1024 | 2048 | 8192 | 16384 | 32768 | 65536
        | 4194304 | 8388608 | 16777216 | 134217728 | 268435456
        | 17179869184 | 1099511627776
    )
    return [
        {"key": "co_founder", "name": "👑 Đồng Sáng Lập Orbit", "color": 0xF59E0B, "hoist": True, "permissions": "8"},
        {"key": "club_manager", "name": f"{emoji} Quản Lý Orbit | {short}", "color": club["color"], "hoist": True, "permissions": "8"},
        {"key": "admin", "name": "🛡️ Admin", "color": 0xF43F5E, "hoist": True, "permissions": "8"},
        {"key": "mod", "name": "⚔️ Mod", "color": 0x10B981, "hoist": True, "permissions": mod_perms},
        {"key": "elite", "name": "⚜️ Orbit Elite", "color": 0xFBBF24, "hoist": True, "permissions": "0"},
        {"key": "ultra", "name": "⚡ Orbit Ultra", "color": 0xC084FC, "hoist": True, "permissions": "0"},
        {"key": "author", "name": "✍️ Tác Giả", "color": 0xFF4FCB, "hoist": True, "permissions": "0"},
        {"key": "chuyen", "name": f"🏆 Chuyên {short}", "color": 0xFB7185, "hoist": True, "permissions": "0"},
        {"key": "hsg", "name": f"🥇 HSG {short}", "color": 0xFB923C, "hoist": True, "permissions": "0"},
        {"key": "gioi", "name": f"💎 Giỏi {short}", "color": 0x38BDF8, "hoist": True, "permissions": "0"},
        {"key": "kha", "name": f"📘 Khá {short}", "color": 0x4ADE80, "hoist": True, "permissions": "0"},
        {"key": "binh_thuong", "name": "🌱 Bình Thường", "color": 0x94A3B8, "hoist": False, "permissions": "0"},
        {"key": "hoc_sinh", "name": "🎓 Học Sinh", "color": 0x60A5FA, "hoist": True, "permissions": "0"},
    ]


def setup_orbit_club_guild(club_code: str, guild_id: str) -> dict:
    club_code = club_code.lower().strip()
    if club_code in ("tin", "hyperhub"):
        from scripts.setup_hyperhub_tin import setup_hyperhub_guild
        return setup_hyperhub_guild(guild_id)
    if club_code not in CLUB_PRESETS:
        return {"ok": False, "error": f"Unknown club_code '{club_code}'. Valid: {list(CLUB_PRESETS.keys())}"}

    club = CLUB_PRESETS[club_code]
    short = club["short_name"]
    short_upper = short.upper()
    slug = club["slug"]
    emoji = club["emoji"]

    token = _get_token()
    if not token:
        return {"ok": False, "error": "Missing DISCORD_TOKEN"}

    st, guild = api_req(token, "GET", f"/guilds/{guild_id}")
    if st != 200:
        return {"ok": False, "status": st, "error": guild}

    _, bot_me = api_req(token, "GET", "/users/@me")
    bot_id = str(bot_me["id"])

    # 1. Đồng bộ 13 Roles
    st_r, existing_roles = api_req(token, "GET", f"/guilds/{guild_id}/roles")
    if st_r != 200 or not isinstance(existing_roles, list):
        return {"ok": False, "error": f"Failed to fetch roles: {st_r}"}

    desired_roles = build_desired_roles(club)

    def _norm(s: str) -> str:
        cleaned = s.strip().lower()
        for prefix in ("👑", "📐", "📜", "🇬🇧", "⚡", "🧪", "🧬", "🌍", "💻", "⚖️", "🏮", "🛡️", "⚔️", "⚜️", "✍️", "🏆", "🥇", "💎", "📘", "🌱", "🎓"):
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

    # 2. Đồng bộ 5 Danh mục & 13 Kênh
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
            "name": f"📌・THÔNG TIN CLB {short_upper}",
            "overwrites": readonly_overwrites,
            "channels": [
                {"key": "welcome", "name": "👋・chào-mừng", "type": 0, "overwrites": readonly_overwrites},
                {"key": "rules", "name": f"📜・luật-clb-{slug}", "type": 0, "overwrites": readonly_overwrites},
                {"key": "announcements", "name": "📢・thông-báo", "type": 0, "overwrites": readonly_overwrites},
                {"key": "role_info", "name": "🎭・thông-tin-role", "type": 0, "overwrites": readonly_overwrites},
            ],
        },
        {
            "name": f"{emoji}・THẢO LUẬN & GIẢI {short_upper}",
            "overwrites": [],
            "channels": [
                {"key": "chat", "name": "💭・chat-chung", "type": 0},
                {"key": "qa_subj", "name": f"{emoji}・hỏi-đáp-bài-tập", "type": 0},
                {"key": "vdc_subj", "name": club["vdc_channel"], "type": 0},
            ],
        },
        {
            "name": f"📚・KHO ĐỀ & TIỆN ÍCH {short_upper}",
            "overwrites": [],
            "channels": [
                {"key": "get_docs", "name": f"📥・kho-đề-{slug}", "type": 0, "overwrites": readonly_overwrites},
                {"key": "submit_docs", "name": f"📤・đóng-góp-đề-{slug}", "type": 0, "overwrites": readonly_overwrites},
                {"key": "bot_cmds", "name": "🤖・lệnh-bot", "type": 0},
            ],
        },
        {
            "name": "🎙️・PHÒNG TỰ HỌC & CHỮA ĐỀ",
            "overwrites": [],
            "channels": [
                {"key": "voice_study", "name": f"🎧・tự-học-{slug}", "type": 2},
                {"key": "voice_solve", "name": "📝・chữa-đề-nhóm", "type": 2},
            ],
        },
        {
            "name": f"🔒・BAN QUẢN LÝ CLB {short_upper}",
            "overwrites": staff_only_overwrites,
            "channels": [
                {"key": "staff_chat", "name": "🛡️・bàn-điều-hành", "type": 0, "overwrites": staff_only_overwrites},
            ],
        },
    ]

    chan_map: dict[str, str] = {}

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

    # Cập nhật kênh hệ thống / Community của Guild
    patch_guild_chans = {"name": club["guild_name"]}
    if chan_map.get("rules"):
        patch_guild_chans["rules_channel_id"] = chan_map["rules"]
    if chan_map.get("staff_chat"):
        patch_guild_chans["public_updates_channel_id"] = chan_map["staff_chat"]
    if chan_map.get("welcome"):
        patch_guild_chans["system_channel_id"] = chan_map["welcome"]
    api_req(token, "PATCH", f"/guilds/{guild_id}", patch_guild_chans)

    # Xóa kênh mặc định dư thừa
    keep_ids = set(chan_map.values())
    st_c2, all_chans_now = api_req(token, "GET", f"/guilds/{guild_id}/channels")
    if st_c2 == 200 and isinstance(all_chans_now, list):
        keep_cat_ids = {c.get("parent_id") for c in all_chans_now if str(c.get("id")) in keep_ids and c.get("parent_id")}
        for c in all_chans_now:
            cid = str(c["id"])
            cname = c.get("name", "").lower()
            if cid not in keep_ids and cid not in keep_cat_ids:
                if cname in ("general", "chung", "rules", "kênh chat", "kênh đàm thoại", "text channels", "voice channels", "kênh văn bản", "kênh thoại", "phòng chờ"):
                    api_req(token, "DELETE", f"/channels/{cid}")
                    time.sleep(0.2)

    # Tạo link mời vĩnh viễn tại kênh #👋・chào-mừng
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

    # Embeds chuẩn cho CLB
    _sync_panel(
        chan_map.get("rules"),
        [
            {
                "title": f"📜 NỘI QUY RIÊNG — CLB {club['guild_name'].upper()}",
                "description": (
                    f"Chào mừng bạn đến với **{club['guild_name']}** — Phân khu chuyên sâu về {club['topics_desc']} trực thuộc hệ sinh thái **Orbit | Vietnam**.\n\n"
                    "**1. Văn Hóa Học Thuật & Tôn Trọng**\n"
                    "• Không chê bai câu hỏi cơ bản; khuyến khích hướng dẫn tư duy giải quyết vấn đề từng bước.\n"
                    "• Nghiêm cấm công kích cá nhân, gây gổ, spam hoặc chia sẻ nội dung phản cảm (NSFW)/độc hại.\n\n"
                    "**2. Quy Chuẩn Khi Hỏi Bài & Thảo Luận**\n"
                    f"• Khi đăng bài tập tại <#{chan_map.get('qa_subj', '')}> hoặc <#{chan_map.get('vdc_subj', '')}>, vui lòng **chụp ảnh đề rõ nét, xoay thẳng chiều** và **nêu rõ khối lớp / hướng bạn đã thử**.\n"
                    "• Tuyệt đối **không nhờ giải hộ đề thi đang diễn ra trực tiếp** (gian lận thi cử).\n\n"
                    "**3. Chia Sẻ Đề Thi & Vinh Danh Tác Giả**\n"
                    f"• Khuyến khích đóng góp đề thi thử, đề trường/sở môn {short} tại **https://orbit-psi-black.vercel.app/#submit_doc** để nhận **Credit vĩnh viễn + 100 XP + Role ✍️ Tác Giả**."
                ),
                "color": club["color"],
                "footer": {"text": f"{club['guild_name']} • Kỷ luật tư duy tạo nên bứt phá"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("announcements"),
        [
            {
                "title": "🌌 HỆ SINH THÁI CÁC MẢNH GHÉP HỌC THUẬT ORBIT & QUYỀN LỢI",
                "description": (
                    "**Orbit** được tổ chức thành Máy chủ Trung tâm (**Orbit | Vietnam**) cùng hệ thống các CLB chuyên môn riêng biệt:\n\n"
                    "🪐 **CÁC MẢNH GHÉP CHUYÊN MÔN ORBIT:**\n"
                    "• **Orbit | Toán** • **Orbit | Văn** • **Orbit | Anh**\n"
                    "• **Orbit | Lý** • **Orbit | Hóa** • **Orbit | Sinh**\n"
                    "• **Orbit | LS ĐL** • **Orbit | Tin (HyperHub)** • **Orbit | GDCD** • **Orbit | Trung**\n\n"
                    "🎁 **ĐẶC QUYỀN DÀNH CHO BAN QUẢN LÝ & CỘNG TÁC VIÊN CỐT CÁN:**\n"
                    "• Được cấp quyền sử dụng **DeepSeek V4.1 Flash vô thời hạn** *(có hạn mức/ngày cực kỳ thoải mái, hiệu năng suy luận ngang ngửa Gemini / GPT Pro)* phục vụ học tập, giải bài và biên soạn chuyên đề.\n"
                    "• Đồng bộ trực tiếp với **Kho Đề Thi Orbit (`orbit-psi-black.vercel.app/#vault`)** miễn phí 100%."
                ),
                "color": 0x3B82F6,
                "footer": {"text": f"{club['guild_name']} • Liên hệ Đồng Sáng Lập hoặc Quản Lý CLB nếu bạn muốn ứng tuyển điều hành"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("role_info"),
        [
            {
                "title": f"🎭 HỆ THỐNG VAI TRÒ & CẤP BẬC NĂNG LỰC — {club['guild_name'].upper()}",
                "description": (
                    "👑 **ĐIỀU HÀNH & QUẢN TRỊ**\n"
                    f"• {_rm('co_founder', 'Đồng Sáng Lập Orbit')} — Sáng lập & định hướng toàn bộ hệ sinh thái Orbit.\n"
                    f"• {_rm('club_manager', f'Quản Lý Orbit | {short}')} — Phụ trách điều hành trực tiếp CLB {short} & chuyên môn học thuật.\n"
                    f"• {_rm('admin', 'Admin')} — Quản trị viên vận hành kỹ thuật & an ninh máy chủ.\n"
                    f"• {_rm('mod', 'Mod')} — Kiểm duyệt viên hỗ trợ thành viên & giữ trật tự thảo luận.\n\n"
                    "⚜️ **THÀNH VIÊN HOÀNG GIA & ĐÓNG GÓP**\n"
                    f"• {_rm('elite', 'Orbit Elite')} — Thành viên Hoàng Gia, có công lớn trong thành lập server & hưởng đặc quyền riêng biệt.\n"
                    f"• {_rm('ultra', 'Orbit Ultra')} — Thành viên Danh Dự, có công đóng góp xây dựng server (tương tự Elite với quy mô nhỏ hơn).\n"
                    f"• {_rm('author', '✍️ Tác Giả')} — Tự động cấp khi đóng góp đề thi/chuyên đề {short} lên Kho Đề Orbit.\n\n"
                    f"{emoji} **CẤP BẬC NĂNG LỰC {short_upper} & THÀNH VIÊN (Do Quản Lý CLB / Mod xét cấp)**\n"
                    f"• {_rm('chuyen', f'Chuyên {short}')} — Học sinh lớp/trường Chuyên {short} hoặc đội tuyển.\n"
                    f"• {_rm('hsg', f'HSG {short}')} — Đạt giải Học Sinh Giỏi {short} hoặc điểm thi thử xuất sắc.\n"
                    f"• {_rm('gioi', f'Giỏi {short}')} — Năng lực môn {short} vững vàng (8.4+).\n"
                    f"• {_rm('kha', f'Khá {short}')} — Nắm chắc nền tảng và vận dụng tốt (7.0+).\n"
                    f"• {_rm('binh_thuong', 'Bình Thường')} — Đang củng cố gốc & luyện tập tiến bộ mỗi ngày.\n"
                    f"• {_rm('hoc_sinh', 'Học Sinh')} — Role chính thức mặc định của mọi thành viên CLB."
                ),
                "color": 0xF59E0B,
                "footer": {"text": f"{club['guild_name']} • Liên hệ Quản Lý CLB / Mod hoặc đóng góp đề để nhận danh hiệu"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("get_docs"),
        [
            {
                "title": f"📥 KHO ĐỀ THI & CHUYÊN ĐỀ {short_upper}",
                "description": (
                    f"Truy cập toàn bộ đề thi môn **{club['full_subject']}** (THCS, THPT chuẩn cấu trúc 2025, ĐGNL và Đề HSG/Chuyên) trên Web Portal:\n\n"
                    "🌐 **Mở Kho Đề Trực Tuyến:** **https://orbit-psi-black.vercel.app/#vault**\n\n"
                    f"• **Thông báo tự động:** Mỗi khi có thành viên nộp đề **{club['full_subject']}** mới trên Web, Bot sẽ tự động đăng thông báo kèm liên kết tải ngay tại kênh này!\n"
                    f"• **Tra cứu nhanh bằng Bot tại** <#{chan_map.get('bot_cmds', '')}>: `/timde {short}`, `/layde <id>`, `/luyende`."
                ),
                "color": 0xFF4FCB,
                "footer": {"text": f"{club['guild_name']} • Học liệu mở miễn phí 100%"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("submit_docs"),
        [
            {
                "title": f"📤 ĐÓNG GÓP ĐỀ {short_upper} & NHẬN CREDIT TÁC GIẢ",
                "description": (
                    f"Chia sẻ đề thi thử môn **{club['full_subject']}** của trường/sở hoặc tài liệu chuyên đề lên hệ thống tại:\n\n"
                    "🌐 **Cổng nộp đề:** **https://orbit-psi-black.vercel.app/#submit_doc**\n\n"
                    "• **Điều kiện:** Chỉ cần liên kết tài khoản Discord (xác thực 2 bước qua kênh `#🔐・verify`).\n"
                    "• **Quyền lợi:** Hiển thị **Tên + Avatar Discord (Credit)** vĩnh viễn trên thẻ đề thi, tự động vinh danh tại <#"
                    + chan_map.get("get_docs", "")
                    + "> và nhận role "
                    + _rm("author", "✍️ Tác Giả")
                    + "."
                ),
                "color": 0x9B5CFF,
                "footer": {"text": f"{club['guild_name']} • Kho Đề Thi & Tài Liệu Học Tập Mở"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("welcome"),
        [
            {
                "title": f"{emoji} CHÀO MỪNG ĐẾN VỚI CLB {club['guild_name'].upper()}",
                "description": (
                    f"Chào mừng bạn gia nhập **{club['guild_name']}** — Nơi hội tụ những học sinh yêu thích môn **{club['full_subject']}**, cùng nhau chinh phục từ nền tảng SGK đến Vận dụng cao 9+, ĐGNL và HSG/Chuyên!\n\n"
                    "🧭 **BẮT ĐẦU NHANH:**\n"
                    f"1️⃣ Đọc kỹ nội quy tại <#{chan_map.get('rules', '')}>.\n"
                    f"2️⃣ Xem hệ thống cấp bậc năng lực tại <#{chan_map.get('role_info', '')}>.\n"
                    f"3️⃣ Giao lưu tại <#{chan_map.get('chat', '')}> hoặc gửi bài tập cần giải đáp tại <#{chan_map.get('qa_subj', '')}> & <#{chan_map.get('vdc_subj', '')}>.\n"
                    f"4️⃣ Tải đề & luyện đề tại <#{chan_map.get('get_docs', '')}> (**https://orbit-psi-black.vercel.app/#vault**)."
                ),
                "color": 0x60A5FA,
                "footer": {"text": f"{club['guild_name']} • Learn · Solve · Conquer"},
            }
        ],
    )

    _sync_panel(
        chan_map.get("bot_cmds"),
        [
            {
                "title": f"🤖 BẢNG LỆNH BOT — {club['guild_name'].upper()}",
                "description": (
                    "Gõ trực tiếp các lệnh Slash (`/`) tại kênh này:\n\n"
                    f"• `/timde <từ khóa>` — Tìm đề {short} (VD: `/timde {short} 12`, `/timde HSG {short}`).\n"
                    "• `/layde <id>` — Lấy file đề thi theo mã ID.\n"
                    "• `/luyende` — Bốc đề ngẫu nhiên để luyện tập."
                ),
                "color": 0x10B981,
                "footer": {"text": f"{club['guild_name']} • Đồng bộ trực tiếp với Orbit Web Hub"},
            }
        ],
    )

    # Cẩm nang vận hành dành riêng cho Quản Lý CLB tại #🛡️・bàn-điều-hành (Mục 3: Để các Quản lý tự chủ động vận hành)
    _sync_panel(
        chan_map.get("staff_chat"),
        [
            {
                "title": f"🛡️ SỔ TAY DÀNH CHO QUẢN LÝ CLB — {club['guild_name'].upper()}",
                "description": (
                    f"Kênh nội bộ dành riêng cho **Đồng Sáng Lập Orbit**, **Quản Lý Orbit | {short}**, **Admin** và **Mod**.\n\n"
                    "🎯 **1. QUYỀN TỰ CHỦ CỦA QUẢN LÝ CLB:**\n"
                    f"• Quản lý CLB có toàn quyền xét duyệt và gán các Role năng lực ({_rm('chuyen', f'Chuyên {short}')}, {_rm('hsg', f'HSG {short}')}, {_rm('gioi', f'Giỏi {short}')}, {_rm('kha', f'Khá {short}')}, {_rm('binh_thuong', 'Bình Thường')}) cho thành viên bằng cách **Chuột phải vào thành viên ➔ Vai trò (Roles)**.\n"
                    f"• Toàn quyền đăng thông báo chuyên đề, lịch chữa đề, sự kiện tại <#{chan_map.get('announcements', '')}> và tạo Chủ đề (Threads) giải bài tại <#{chan_map.get('qa_subj', '')}> / <#{chan_map.get('vdc_subj', '')}>.\n\n"
                    "⚡ **2. TỰ ĐỘNG HÓA ĐÃ KÍCH HOẠT SẴN:**\n"
                    f"• Thành viên mới vào CLB tự động nhận role {_rm('hoc_sinh', '🎓 Học Sinh')}.\n"
                    f"• Khi có thành viên nộp đề môn **{club['full_subject']}** trên Web (`orbit-psi-black.vercel.app/#submit_doc`), Bot tự động đăng thông báo đề mới vào <#{chan_map.get('get_docs', '')}> và tự động cấp role {_rm('author', '✍️ Tác Giả')} cho người nộp.\n\n"
                    "🛠️ **3. BỘ LỆNH KIỂM DUYỆT NHANH:**\n"
                    "• `/warn`, `/deletewarn`, `/mute`, `/unmute`, `/kick`, `/ban`, `/unban`."
                ),
                "color": 0xF59E0B,
                "footer": {"text": f"{club['guild_name']} • Bàn Điều Hành Nội Bộ Ban Quản Lý"},
            }
        ],
    )

    return {
        "ok": True,
        "club_code": club_code,
        "guild_id": guild_id,
        "guild_name": club["guild_name"],
        "invite_url": invite_url,
        "roles": role_map,
        "channels": chan_map,
    }


if __name__ == "__main__":
    code_arg = sys.argv[1] if len(sys.argv) > 1 else "toan"
    gid_arg = sys.argv[2] if len(sys.argv) > 2 else CLUB_PRESETS.get(code_arg, {}).get("guild_id", "1567904557076316250")
    res = setup_orbit_club_guild(code_arg, gid_arg)
    print(json.dumps(res, ensure_ascii=False, indent=2))
