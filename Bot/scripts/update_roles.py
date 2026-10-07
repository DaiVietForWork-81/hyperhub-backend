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

# Danh sách role cần xóa
ROLES_TO_DELETE = [
    ("🏆RHT1", "1541025570010431518"),
    ("👑 HT1 - Freedom", "1534128842866950164"),
    ("💎MT1 - Freedom", "1534128844880220211"),
    ("🏆LT1 - Freedom", "1543471701373886525"),
    ("🔱HT2 - Freedom", "1543471743086100591"),
    ("⚜️MT2 - Freedom", "1543471762421973042"),
    ("🛡️LT2 - Freedom", "1543471773885009960"),
    ("💠T3 - Freedom", "1543471715420606474"),
    ("🔷T4 - Freedom", "1543471785138458714"),
    ("🔶T5 - Freedom", "1543471796458758144"),
    ("⭐T6 - Freedom", "1543471811012861953"),
    ("⭐T7 - Freedom", "1543471821603733605"),
    ("⭐T8 - Freedom", "1543471838619901973"),
]

# Đổi tên role separator nếu có
TIER_SEPARATOR_ID = "1549766902652338177"

# Danh sách role lớp cần tạo (từ Lớp 12 xuống Lớp 6)
NEW_ROLES = [
    {"name": "🎓 Lớp 12", "color": 0xEF4444, "hoist": True},  # Đỏ tươi
    {"name": "📚 Lớp 11", "color": 0xF97316, "hoist": True},  # Cam
    {"name": "📖 Lớp 10", "color": 0xF59E0B, "hoist": True},  # Vàng hổ phách
    {"name": "✏️ Lớp 9", "color": 0x10B981, "hoist": True},   # Ngọc lục bảo
    {"name": "📐 Lớp 8", "color": 0x06B6D4, "hoist": True},   # Cyan
    {"name": "🔬 Lớp 7", "color": 0x3B82F6, "hoist": True},   # Xanh lam
    {"name": "🌱 Lớp 6", "color": 0x8B5CF6, "hoist": True},   # Tím
]

print("=== 1. XÓA 13 ROLE TIER CŨ ===")
for name, r_id in ROLES_TO_DELETE:
    url = f"https://discord.com/api/v10/guilds/{guild_id}/roles/{r_id}"
    res = requests.delete(url, headers=headers)
    if res.status_code in (200, 204):
        print(f"✅ Đã xóa: {name} (ID: {r_id})")
    elif res.status_code == 404:
        print(f"ℹ️ Không tồn tại / Đã xóa trước đó: {name}")
    else:
        print(f"❌ Lỗi khi xóa {name}: {res.status_code} - {res.text}")
    time.sleep(0.5)

print("\n=== 2. ĐỔI TÊN SEPARATOR ROLE THÀNH '╭─── KHỐI LỚP ───╮' ===")
sep_url = f"https://discord.com/api/v10/guilds/{guild_id}/roles/{TIER_SEPARATOR_ID}"
res_sep = requests.patch(sep_url, headers=headers, json={"name": "╭─── KHỐI LỚP ───╮"})
if res_sep.status_code == 200:
    print("✅ Đã đổi tên separator role thành: ╭─── KHỐI LỚP ───╮")
else:
    print(f"Lỗi đổi tên separator: {res_sep.status_code} - {res_sep.text}")

print("\n=== 3. TẠO CÁC ROLE LỚP HỌC MỚI (Lớp 12 -> Lớp 6) ===")
create_url = f"https://discord.com/api/v10/guilds/{guild_id}/roles"
created_roles = []
for r in NEW_ROLES:
    payload = {
        "name": r["name"],
        "color": r["color"],
        "hoist": r["hoist"],
        "mentionable": True,
    }
    res = requests.post(create_url, headers=headers, json=payload)
    if res.status_code in (200, 201):
        data = res.json()
        print(f"✅ Đã tạo thành công: {data['name']} (ID: {data['id']})")
        created_roles.append(data)
    else:
        print(f"❌ Lỗi tạo {r['name']}: {res.status_code} - {res.text}")
    time.sleep(0.5)

print("\n=== HOÀN TẤT CẬP NHẬT ROLE DISCORD ===")
