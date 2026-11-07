"""Kịch bản thiết lập tự động toàn diện máy chủ CLB Toán: Orbit | Toán (ID: 1567904557076316250).

Bao gồm:
- Hệ thống 13 Roles chuẩn theo yêu cầu (từ Đồng Sáng Lập Orbit -> Học Sinh).
- Cấu trúc Kênh tinh gọn, chuyên biệt cho CLB Toán (Thông tin, Thảo luận Toán, Kho đề, Phòng tự học, Nội bộ BQT).
- Bộ Embeds đồng bộ phong cách Orbit (không gắn logo/thumbnail): Nội quy riêng CLB Toán, Giới thiệu hệ sinh thái đa CLB Orbit & quyền lợi DeepSeek V4.1 Flash, Bảng Role, Kho đề & Đóng góp đề.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

MATH_GUILD_ID = "1567904557076316250"
API_BASE = "https://discord.com/api/v10"


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


# Danh sách 13 Roles chuẩn của CLB Toán (theo thứ tự từ cao xuống thấp)
DESIRED_ROLES = [
    {
        "key": "co_founder",
        "name": "👑 Đồng Sáng Lập Orbit",
        "color": 0xF59E0B,
        "hoist": True,
        "permissions": "8",  # Administrator
    },
    {
        "key": "math_manager",
        "name": "📐 Quản Lý Orbit | Toán",
        "color": 0xA855F7,
        "hoist": True,
        "permissions": "8",  # Administrator
    },
    {
        "key": "admin",
        "name": "🛡️ Admin",
        "color": 0xF43F5E,
        "hoist": True,
        "permissions": "8",  # Administrator
    },
    {
        "key": "mod",
        "name": "⚔️ Mod",
        "color": 0x10B981,
        "hoist": True,
        # Kick(2) + Ban(4) + ManageChannels(16) + ViewAuditLog(128) + ViewChannel(1024) + SendMessages(2048)
        # + ManageMessages(8192) + EmbedLinks(16384) + AttachFiles(32768) + ReadHistory(65536)
        # + MuteMembers(4194304) + DeafenMembers(8388608) + MoveMembers(16777216) + ManageNicknames(134217728)
        # + ManageThreads(17179869184) + ModerateMembers(1099511627776)
        "permissions": str(2 | 4 | 128 | 1024 | 2048 | 8192 | 16384 | 32768 | 65536 | 4194304 | 8388608 | 16777216 | 134217728 | 17179869184 | 1099511627776),
    },
    {
        "key": "elite",
        "name": "⚜️ Orbit Elite",
        "color": 0xFBBF24,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "ultra",
        "name": "⚡ Orbit Ultra",
        "color": 0xC084FC,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "author",
        "name": "✍️ Tác Giả",
        "color": 0xFF4FCB,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "chuyen_toan",
        "name": "🏆 Chuyên Toán",
        "color": 0xFB7185,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "hsg_toan",
        "name": "🥇 HSG Toán",
        "color": 0xFB923C,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "gioi_toan",
        "name": "💎 Giỏi Toán",
        "color": 0x38BDF8,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "kha_toan",
        "name": "📘 Khá Toán",
        "color": 0x4ADE80,
        "hoist": True,
        "permissions": "0",
    },
    {
        "key": "binh_thuong",
        "name": "🌱 Bình Thường",
        "color": 0x94A3B8,
        "hoist": False,
        "permissions": "0",
    },
    {
        "key": "hoc_sinh",
        "name": "🎓 Học Sinh",
        "color": 0x60A5FA,
        "hoist": True,
        "permissions": "0",
    },
]


def setup_orbit_math_guild(guild_id: str = MATH_GUILD_ID) -> dict:
    token = _get_token()
    if not token:
        return {"ok": False, "error": "Missing DISCORD_TOKEN"}

    st, guild = api_req(token, "GET", f"/guilds/{guild_id}")
    if st != 200:
        return {"ok": False, "status": st, "error": guild}

    _, bot_me = api_req(token, "GET", "/users/@me")
    bot_id = str(bot_me["id"])

    # 1. Đồng bộ Roles
    st_r, existing_roles = api_req(token, "GET", f"/guilds/{guild_id}/roles")
    if st_r != 200 or not isinstance(existing_roles, list):
        return {"ok": False, "error": f"Failed to fetch roles: {st_r}"}

    def _norm(s: str) -> str:
        # Bỏ emoji đầu để so khớp linh hoạt
        cleaned = s.strip().lower()
        for prefix in ("👑", "📐", "🛡️", "⚔️", "⚜️", "⚡", "✍️", "🏆", "🥇", "💎", "📘", "🌱", "🎓"):
            cleaned = cleaned.replace(prefix, "").strip()
        return cleaned

    role_map: dict[str, str] = {}
    for r_spec in DESIRED_ROLES:
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

    # Sắp xếp thứ tự Role từ cao xuống thấp
    pos_payload = []
    base_pos = len(DESIRED_ROLES) + 2
    for idx, r_spec in enumerate(DESIRED_ROLES):
        rid = role_map.get(r_spec["key"])
        if rid:
            pos_payload.append({"id": rid, "position": base_pos - idx})
    if pos_payload:
        api_req(token, "PATCH", f"/guilds/{guild_id}/roles", pos_payload)

    # 2. Cấu trúc Categories & Channels tinh gọn cho CLB Toán
    st_c, existing_chans = api_req(token, "GET", f"/guilds/{guild_id}/channels")
    if st_c != 200 or not isinstance(existing_chans, list):
        return {"ok": False, "error": f"Failed to fetch channels: {st_c}"}

    # Quyền hạn cơ bản
    VIEW_CHANNEL = 1024
    SEND_MESSAGES = 2048
    CREATE_PUBLIC_THREADS = 34359738368
    SEND_MESSAGES_IN_THREADS = 274877906944

    readonly_overwrites = [
        {
            "id": guild_id,  # @everyone
            "type": 0,
            "allow": str(VIEW_CHANNEL),
            "deny": str(SEND_MESSAGES | CREATE_PUBLIC_THREADS | SEND_MESSAGES_IN_THREADS),
        }
    ]
    for k in ("co_founder", "math_manager", "admin", "mod"):
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
            "id": guild_id,  # @everyone
            "type": 0,
            "allow": "0",
            "deny": str(VIEW_CHANNEL),
        }
    ]
    for k in ("co_founder", "math_manager", "admin", "mod"):
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
            "name": "📌・THÔNG TIN CLB TOÁN",
            "overwrites": readonly_overwrites,
            "channels": [
                {"key": "welcome", "name": "👋・chào-mừng", "type": 0, "overwrites": readonly_overwrites},
                {"key": "rules", "name": "📜・luật-clb-toán", "type": 0, "overwrites": readonly_overwrites},
                {"key": "announcements", "name": "📢・thông-báo", "type": 0, "overwrites": readonly_overwrites},
                {"key": "role_info", "name": "🎭・thông-tin-role", "type": 0, "overwrites": readonly_overwrites},
            ],
        },
        {
            "name": "📐・THẢO LUẬN & GIẢI TOÁN",
            "overwrites": [],
            "channels": [
                {"key": "chat", "name": "💭・chat-chung", "type": 0},
                {"key": "qa_math", "name": "📐・hỏi-đáp-bài-tập", "type": 0},
                {"key": "vdc_math", "name": "🧮・góc-chuyên-vđc", "type": 0},
            ],
        },
        {
            "name": "📚・KHO ĐỀ & TIỆN ÍCH TOÁN",
            "overwrites": [],
            "channels": [
                {"key": "get_docs", "name": "📥・kho-đề-toán", "type": 0, "overwrites": readonly_overwrites},
                {"key": "submit_docs", "name": "📤・đóng-góp-đề-toán", "type": 0, "overwrites": readonly_overwrites},
                {"key": "bot_cmds", "name": "🤖・lệnh-bot", "type": 0},
            ],
        },
        {
            "name": "🎙️・PHÒNG TỰ HỌC & CHỮA ĐỀ",
            "overwrites": [],
            "channels": [
                {"key": "voice_study", "name": "🎧・tự-học-toán", "type": 2},
                {"key": "voice_solve", "name": "📝・chữa-đề-nhóm", "type": 2},
            ],
        },
        {
            "name": "🔒・BAN QUẢN LÝ CLB TOÁN",
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

    # Cập nhật kênh hệ thống / Community của Guild sang bộ kênh mới trước khi xóa kênh mặc định
    patch_guild_chans = {}
    if chan_map.get("rules"):
        patch_guild_chans["rules_channel_id"] = chan_map["rules"]
    if chan_map.get("staff_chat"):
        patch_guild_chans["public_updates_channel_id"] = chan_map["staff_chat"]
    if chan_map.get("welcome"):
        patch_guild_chans["system_channel_id"] = chan_map["welcome"]
    if patch_guild_chans:
        api_req(token, "PATCH", f"/guilds/{guild_id}", patch_guild_chans)

    # Xóa các kênh mặc định dư thừa của Discord (như "general", "rules", "Kênh Chat", "Kênh đàm thoại") nếu không nằm trong danh sách
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

    # 3. Đăng / Cập nhật các Embed chuẩn cho CLB Toán (không gắn logo/thumbnail)
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
        time.sleep(0.3)

    # Embed 1: Luật riêng của CLB Toán (#📜・luật-clb-toán)
    rules_embeds = [
        {
            "title": "📜 NỘI QUY RIÊNG — CLB ORBIT | TOÁN",
            "description": (
                "Chào mừng bạn đến với **Orbit | Toán** — Phân khu chuyên sâu về Toán học (THCS • THPT • ĐGNL HSA/APT • HSG & Chuyên Toán) trực thuộc hệ sinh thái **Orbit | Vietnam**.\n\n"
                "**1. Văn Hóa Học Thuật & Tôn Trọng**\n"
                "• Không chê bai câu hỏi cơ bản; khuyến khích hướng dẫn tư duy từng bước thay vì chỉ đưa đáp số.\n"
                "• Nghiêm cấm công kích cá nhân, gây gổ, spam hoặc chia sẻ nội dung phản cảm (NSFW)/độc hại.\n\n"
                "**2. Quy Chuẩn Khi Hỏi Bài & Thảo Luận Toán**\n"
                "• Khi đăng bài tập tại <#"
                + chan_map.get("qa_math", "")
                + "> hoặc <#"
                + chan_map.get("vdc_math", "")
                + ">, vui lòng **chụp ảnh đề rõ nét, xoay thẳng chiều** hoặc gõ công thức rõ ràng và **nêu rõ khối lớp / hướng bạn đã thử**.\n"
                "• Tuyệt đối **không nhờ giải hộ đề thi đang diễn ra trực tiếp** (gian lận thi cử).\n\n"
                "**3. Chia Sẻ Đề Thi & Vinh Danh Tác Giả**\n"
                "• Khuyến khích đóng góp đề thi thử, đề trường/sở, chuyên đề Toán tại **https://orbit-psi-black.vercel.app/#submit_doc** để nhận **Credit vĩnh viễn + 100 XP + Role ✍️ Tác Giả**."
            ),
            "color": 0xA855F7,
            "footer": {"text": "Orbit | Toán • Kỷ luật tư duy tạo nên bứt phá"},
        }
    ]
    _sync_panel(chan_map.get("rules"), rules_embeds)

    # Embed 2: Thông báo hệ thống phân mảnh Orbit & Quyền lợi (#📢・thông-báo)
    ann_embeds = [
        {
            "title": "🌌 HỆ SINH THÁI CÁC MẢNH GHÉP HỌC THUẬT ORBIT & QUYỀN LỢI",
            "description": (
                "**Orbit** được tổ chức thành Máy chủ Trung tâm (**Orbit | Vietnam**) cùng hệ thống các CLB chuyên môn riêng biệt:\n\n"
                "🪐 **CÁC MẢNH GHÉP CHUYÊN MÔN ORBIT:**\n"
                "• **Orbit | Toán** *(Máy chủ hiện tại — Trực thuộc quản lý trung tâm)*\n"
                "• **Orbit | Văn** • **Orbit | Anh** • **Orbit | Lý** • **Orbit | Hóa**\n"
                "• **Orbit | Sinh** • **Orbit | Sử - Địa (LS ĐL)** • **Orbit | Tin (HyperHub)**\n"
                "• **Orbit | GDCD** • **Orbit | Trung**\n\n"
                "🎁 **ĐẶC QUYỀN DÀNH CHO BAN QUẢN LÝ & CỘNG TÁC VIÊN CỐT CÁN:**\n"
                "• Được cấp quyền sử dụng **DeepSeek V4.1 Flash vô thời hạn** *(có hạn mức/ngày cực kỳ thoải mái, hiệu năng suy luận Toán & Khoa học ngang ngửa Gemini / GPT Pro)* phục vụ học tập, giải toán và biên soạn chuyên đề.\n"
                "• Đồng bộ trực tiếp với **Kho Đề Thi Orbit (`orbit-psi-black.vercel.app/#vault`)** miễn phí 100%."
            ),
            "color": 0x3B82F6,
            "footer": {"text": "Orbit | Toán • Liên hệ Đồng Sáng Lập hoặc Quản Lý Orbit | Toán nếu bạn muốn ứng tuyển quản lý phân khu"},
        }
    ]
    _sync_panel(chan_map.get("announcements"), ann_embeds)

    # Embed 3: Thông tin Role (#🎭・thông-tin-role)
    def _rm(key: str, fallback: str) -> str:
        rid = role_map.get(key)
        return f"<@&{rid}>" if rid else f"**{fallback}**"

    role_embeds = [
        {
            "title": "🎭 HỆ THỐNG VAI TRÒ & CẤP BẬC NĂNG LỰC — ORBIT | TOÁN",
            "description": (
                "👑 **ĐIỀU HÀNH & QUẢN TRỊ**\n"
                f"• {_rm('co_founder', 'Đồng Sáng Lập Orbit')} — Sáng lập & định hướng toàn bộ hệ sinh thái Orbit.\n"
                f"• {_rm('math_manager', 'Quản Lý Orbit | Toán')} — Phụ trách điều hành trực tiếp CLB Toán & chuyên môn học thuật.\n"
                f"• {_rm('admin', 'Admin')} — Quản trị viên vận hành kỹ thuật & an ninh máy chủ.\n"
                f"• {_rm('mod', 'Mod')} — Kiểm duyệt viên hỗ trợ thành viên & giữ trật tự thảo luận.\n\n"
                "⚜️ **THÀNH VIÊN HOÀNG GIA & ĐÓNG GÓP**\n"
                f"• {_rm('elite', 'Orbit Elite')} — Thành viên Hoàng Gia, có công lớn trong thành lập server & hưởng đặc quyền riêng biệt.\n"
                f"• {_rm('ultra', 'Orbit Ultra')} — Thành viên Danh Dự, có công đóng góp xây dựng server (tương tự Elite với quy mô nhỏ hơn).\n"
                f"• {_rm('author', '✍️ Tác Giả')} — Dành cho thành viên đóng góp đề thi/chuyên đề Toán lên Kho Đề Orbit.\n\n"
                "📐 **CẤP BẬC NĂNG LỰC TOÁN HỌC & THÀNH VIÊN**\n"
                f"• {_rm('chuyen_toan', 'Chuyên Toán')} — Học sinh lớp/trường Chuyên Toán hoặc đội tuyển Toán.\n"
                f"• {_rm('hsg_toan', 'HSG Toán')} — Đạt giải Học Sinh Giỏi Toán hoặc điểm thi thử xuất sắc (9.4+).\n"
                f"• {_rm('gioi_toan', 'Giỏi Toán')} — Năng lực Giải tích / Hình học / Tổ hợp vững vàng (8.4+).\n"
                f"• {_rm('kha_toan', 'Khá Toán')} — Nắm chắc nền tảng và vận dụng tốt (7.0+).\n"
                f"• {_rm('binh_thuong', 'Bình Thường')} — Đang củng cố gốc & luyện tập tiến bộ mỗi ngày.\n"
                f"• {_rm('hoc_sinh', 'Học Sinh')} — Role chính thức mặc định của mọi thành viên CLB Toán."
            ),
            "color": 0xF59E0B,
            "footer": {"text": "Orbit | Toán • Tích cực giải bài & đóng góp đề để nâng cấp danh hiệu Toán học"},
        }
    ]
    _sync_panel(chan_map.get("role_info"), role_embeds)

    # Embed 4: Kho Đề Toán (#📥・kho-đề-toán)
    get_docs_embeds = [
        {
            "title": "📥 KHO ĐỀ THI & CHUYÊN ĐỀ TOÁN HỌC",
            "description": (
                "Truy cập toàn bộ đề thi Toán THCS, THPT chuẩn cấu trúc 2025 (3 phần: Trắc nghiệm — Đúng/Sai — Trả lời ngắn), ĐGNL HSA/APT và Đề HSG/Chuyên Toán trên Web Portal:\n\n"
                "🌐 **Mở Kho Đề Toán:** **https://orbit-psi-black.vercel.app/#vault**\n\n"
                "• **Xem trước PDF & Bốc đề ngẫu nhiên:** Miễn phí 100%, không cần xác minh email.\n"
                "• **Tra cứu nhanh bằng Bot tại** <#"
                + chan_map.get("bot_cmds", "")
                + ">: `/timde Toán`, `/layde <id>`, `/luyende`."
            ),
            "color": 0xFF4FCB,
            "footer": {"text": "Orbit | Toán • Học liệu mở miễn phí 100%"},
        }
    ]
    _sync_panel(chan_map.get("get_docs"), get_docs_embeds)

    # Embed 5: Đóng góp đề Toán (#📤・đóng-góp-đề-toán)
    submit_docs_embeds = [
        {
            "title": "📤 ĐÓNG GÓP ĐỀ TOÁN & NHẬN CREDIT TÁC GIẢ",
            "description": (
                "Chia sẻ đề thi thử Toán của trường/sở hoặc tài liệu chuyên đề lên hệ thống tại:\n\n"
                "🌐 **Cổng nộp đề:** **https://orbit-psi-black.vercel.app/#submit_doc**\n\n"
                "• **Điều kiện:** Chỉ cần liên kết tài khoản Discord (xác thực 2 bước qua kênh `#🔐・verify`).\n"
                "• **Quyền lợi:** Hiển thị **Tên + Avatar Discord (Credit)** vĩnh viễn trên thẻ đề thi và nhận role "
                + _rm("author", "✍️ Tác Giả")
                + "."
            ),
            "color": 0x9B5CFF,
            "footer": {"text": "Orbit | Toán • Kho Đề Thi & Tài Liệu Học Tập Mở"},
        }
    ]
    _sync_panel(chan_map.get("submit_docs"), submit_docs_embeds)

    # Embed 6: Chào mừng (#👋・chào-mừng)
    welcome_embeds = [
        {
            "title": "📐 CHÀO MỪNG ĐẾN VỚI CLB ORBIT | TOÁN",
            "description": (
                "Chào mừng bạn gia nhập **Orbit | Toán** — Nơi hội tụ những học sinh yêu Toán, cùng nhau chinh phục từ nền tảng SGK đến Vận dụng cao 9+, ĐGNL và HSG/Chuyên Toán!\n\n"
                "🧭 **BẮT ĐẦU NHANH:**\n"
                f"1️⃣ Đọc kỹ nội quy tại <#{chan_map.get('rules', '')}>.\n"
                f"2️⃣ Xem hệ thống cấp bậc năng lực Toán tại <#{chan_map.get('role_info', '')}>.\n"
                f"3️⃣ Giao lưu tại <#{chan_map.get('chat', '')}> hoặc gửi bài tập cần giải đáp tại <#{chan_map.get('qa_math', '')}> & <#{chan_map.get('vdc_math', '')}>.\n"
                f"4️⃣ Tải đề & luyện đề Toán tại <#{chan_map.get('get_docs', '')}> (**https://orbit-psi-black.vercel.app/#vault**)."
            ),
            "color": 0x60A5FA,
            "footer": {"text": "Orbit | Toán • Learn · Solve · Conquer"},
        }
    ]
    _sync_panel(chan_map.get("welcome"), welcome_embeds)

    # Embed 7: Lệnh Bot (#🤖・lệnh-bot)
    bot_cmd_embeds = [
        {
            "title": "🤖 BẢNG LỆNH BOT — ORBIT | TOÁN",
            "description": (
                "Gõ trực tiếp các lệnh Slash (`/`) tại kênh này:\n\n"
                "• `/timde <từ khóa>` — Tìm đề Toán (VD: `/timde Hàm số 12`, `/timde HSG Toán 9`).\n"
                "• `/layde <id>` — Lấy file đề thi theo mã ID.\n"
                "• `/luyende` — Bốc đề Toán ngẫu nhiên để luyện tập."
            ),
            "color": 0x10B981,
            "footer": {"text": "Orbit | Toán • Đồng bộ trực tiếp với Orbit Web Hub"},
        }
    ]
    _sync_panel(chan_map.get("bot_cmds"), bot_cmd_embeds)

    # 4. Tự động cấp role "🎓 Học Sinh" cho các thành viên hiện có trong server (trừ bot)
    hoc_sinh_role_id = role_map.get("hoc_sinh")
    if hoc_sinh_role_id:
        st_mem, members = api_req(token, "GET", f"/guilds/{guild_id}/members?limit=100")
        if st_mem == 200 and isinstance(members, list):
            for m in members:
                u = m.get("user", {})
                if not u.get("bot") and hoc_sinh_role_id not in m.get("roles", []):
                    api_req(token, "PUT", f"/guilds/{guild_id}/members/{u['id']}/roles/{hoc_sinh_role_id}")
                    time.sleep(0.2)

    return {"ok": True, "roles": role_map, "channels": chan_map}


if __name__ == "__main__":
    res = setup_orbit_math_guild(MATH_GUILD_ID)
    print(json.dumps(res, ensure_ascii=False, indent=2))
