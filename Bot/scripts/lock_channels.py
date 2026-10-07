import requests
import os
import sys
import time
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv(r"D:\Project\Bot\.env")
token = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
headers = {"Authorization": f"Bot {token}"}
guild_id = "1532265330079174697"

CAT_1_ID = "1534147129197723749"
CAT_2_ID = "1534147951797080174"
EXCLUDED_CHANNEL_ID = "1535278288828633138"  # Kênh nộp tài liệu

# Các role cần khóa chat (chỉ xem, không được gửi tin nhắn)
ROLE_EVERYONE_ID = "1532265330079174697"
ROLE_HOC_SINH_ID = "1532397716598948050"
ROLE_TEST_ID = "1549053772553256973"

# Bot role cần đảm bảo CÓ QUYỀN gửi tin nhắn và đính kèm tệp
ROLE_BOT_MAIN_ID = "1536308367231025252"
ROLE_BOT_MANAGED_ID = "1536308166927716446"
ROLE_ADMIN_ID = "1532383529353089085"

# Discord Permissions Bitfield:
# VIEW_CHANNEL: 1 << 10 = 0x400 (1024)
# SEND_MESSAGES: 1 << 11 = 0x800 (2048)
# SEND_MESSAGES_IN_THREADS: 1 << 38 = 0x4000000000 (274877906944)
# CREATE_PUBLIC_THREADS: 1 << 35 = 0x800000000 (34359738368)
# CREATE_PRIVATE_THREADS: 1 << 36 = 0x1000000000 (68719476736)
# ATTACH_FILES: 1 << 15 = 0x8000 (32768)
# READ_MESSAGE_HISTORY: 1 << 16 = 0x10000 (65536)

# Deny chat = SEND_MESSAGES | SEND_MESSAGES_IN_THREADS | CREATE_PUBLIC_THREADS | CREATE_PRIVATE_THREADS
DENY_CHAT_BITS = (1 << 11) | (1 << 38) | (1 << 35) | (1 << 36)
# Allow read = VIEW_CHANNEL | READ_MESSAGE_HISTORY
ALLOW_READ_BITS = (1 << 10) | (1 << 16)
# Allow bot = VIEW_CHANNEL | READ_MESSAGE_HISTORY | SEND_MESSAGES | ATTACH_FILES | (1 << 14) (EMBED_LINKS)
ALLOW_BOT_BITS = (1 << 10) | (1 << 16) | (1 << 11) | (1 << 15) | (1 << 14)

r = requests.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers)
channels = r.json()

target_channels = []
for c in channels:
    c_id = str(c.get("id"))
    p_id = str(c.get("parent_id"))
    # Category hoặc channel nằm trong 2 category
    if c_id in (CAT_1_ID, CAT_2_ID) or p_id in (CAT_1_ID, CAT_2_ID):
        target_channels.append(c)

print(f"Tổng số kênh trong 2 thư mục: {len(target_channels)}")
for c in target_channels:
    c_id = str(c.get("id"))
    c_name = c.get("name")
    c_type = c.get("type")
    is_cat = (c_type == 4)
    print(f"[{'DANH MỤC' if is_cat else 'KÊNH'}] {c_name} (ID: {c_id})")

def set_channel_permission(ch_id, overwrite_id, allow_bits, deny_bits, target_type=0):
    url = f"https://discord.com/api/v10/channels/{ch_id}/permissions/{overwrite_id}"
    payload = {
        "id": overwrite_id,
        "type": target_type,  # 0 for role, 1 for member
        "allow": str(allow_bits),
        "deny": str(deny_bits),
    }
    res = requests.put(url, headers=headers, json=payload)
    return res.status_code

print("\n=== THIẾT LẬP KHÓA CHAT CHO CÁC KÊNH ===")

for c in target_channels:
    c_id = str(c.get("id"))
    c_name = c.get("name")
    
    # BỎ QUA kênh tiếp nhận tài liệu (1535278288828633138)
    if c_id == EXCLUDED_CHANNEL_ID:
        print(f"\n⭐ BỎ QUA (Không khóa): Kênh tiếp nhận tài liệu #{c_name} ({c_id})")
        # Đảm bảo học sinh và everyone ĐƯỢC CHAT và GỬI TỆP ở kênh này:
        set_channel_permission(c_id, ROLE_EVERYONE_ID, (1 << 10) | (1 << 11) | (1 << 15) | (1 << 16), 0)
        set_channel_permission(c_id, ROLE_HOC_SINH_ID, (1 << 10) | (1 << 11) | (1 << 15) | (1 << 16), 0)
        continue

    print(f"\n🔒 Đang khóa chat: #{c_name} ({c_id})...")

    # 1. Khóa @everyone: Chỉ cho xem, cấm chat
    st1 = set_channel_permission(c_id, ROLE_EVERYONE_ID, ALLOW_READ_BITS, DENY_CHAT_BITS)
    # 2. Khóa 🌱 Học sinh: Chỉ cho xem, cấm chat
    st2 = set_channel_permission(c_id, ROLE_HOC_SINH_ID, ALLOW_READ_BITS, DENY_CHAT_BITS)
    # 3. Khóa 🧪 Test: Chỉ cho xem, cấm chat
    st3 = set_channel_permission(c_id, ROLE_TEST_ID, ALLOW_READ_BITS, DENY_CHAT_BITS)
    # 4. Cấp quyền ĐẦY ĐỦ cho Bot HyperHub để gửi tài liệu
    st4 = set_channel_permission(c_id, ROLE_BOT_MAIN_ID, ALLOW_BOT_BITS, 0)
    st5 = set_channel_permission(c_id, ROLE_BOT_MANAGED_ID, ALLOW_BOT_BITS, 0)

    print(f" -> Kết quả: @everyone={st1}, Học sinh={st2}, Test={st3}, Bot={st4}")
    time.sleep(0.4)

print("\n=== HOÀN TẤT KHÓA CHAT CHO 2 THƯ MỤC (TRỪ #📄・nộp-tài-liệu) ===")
