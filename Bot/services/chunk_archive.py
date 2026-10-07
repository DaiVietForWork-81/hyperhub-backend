"""
services/chunk_archive.py
Offload file đề thi lớn lên Discord: chẻ file thành các phần <= ARCHIVE_CHUNK_MB,
đăng vào kênh archive, ghép lại khi tải. Local về 0MB.
"""

from __future__ import annotations

import asyncio
import datetime
import io
import logging
import os
from typing import Any, Optional

import discord

from config.settings import settings

log = logging.getLogger("chunk_archive")

BOT_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 4 role Admin được thấy kênh chunks (đồng bộ với api_bridge.ADMIN_ROLE_IDS)
CHUNK_ADMIN_ROLE_IDS = {
    1534128845198987438,  # 👑 Owner
    1534132250088833024,  # 👑 Co-Owner
    1532383529353089085,  # ⚡ Administrator
    1534146463246974995,  # 🛡️ Moderator
}


async def lock_archive_channel(bot, channel) -> dict[str, Any]:
    """Khóa kênh archive: @everyone không thấy; chỉ bot + 4 role admin (+ guild owner mặc định)."""
    if channel is None or not isinstance(channel, discord.TextChannel):
        return {"success": False, "error": "Kênh archive không hợp lệ."}
    guild = channel.guild
    try:
        # 1. Chặn @everyone xem kênh
        await channel.set_permissions(
            guild.default_role,
            view_channel=False,
            send_messages=False,
            read_message_history=False,
            reason="Khóa kênh file-chunks: chỉ admin",
        )
        # 2. Mở cho 4 role admin
        opened = []
        for rid in CHUNK_ADMIN_ROLE_IDS:
            role = guild.get_role(int(rid))
            if role:
                try:
                    await channel.set_permissions(
                        role,
                        view_channel=True,
                        read_message_history=True,
                        send_messages=False,
                        reason="Mở kênh file-chunks cho admin",
                    )
                    opened.append(role.name)
                except Exception as e:
                    log.debug(f"Không mở quyền cho role {rid}: {e}")
        # 3. Đảm bảo chính bot luôn có quyền
        me = guild.me
        if me:
            try:
                await channel.set_permissions(
                    me,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                    reason="Bot cần đăng/đọc chunks",
                )
            except Exception as e:
                log.debug(f"Không set quyền bot: {e}")
        log.info(f"Đã khóa kênh #{channel.name}: @everyone ẩn, mở cho {opened}")
        return {"success": True, "channel_id": str(channel.id), "opened_roles": opened}
    except Exception as e:
        log.error(f"Lỗi khóa kênh archive: {e}")
        return {"success": False, "error": str(e)[:200]}


def get_chunk_size_limit() -> int:
    """Dung lượng tối đa mỗi phần (bytes).
    Đã đo thực tế trên server: 20MiB OK, 24MB 413. Chốt 20.000.000 bytes an toàn.
    Nâng ARCHIVE_CHUNK_MB sau khi boost Nitro và đo lại."""
    return 20 * 1000 * 1000


def split_bytes(data: bytes, chunk_size: int) -> list[bytes]:
    """Chẻ bytes thành các phần <= chunk_size (giữ nguyên thứ tự)."""
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]


async def get_or_create_archive_channel(bot) -> Optional[discord.TextChannel]:
    """Lấy kênh archive đã cấu hình, hoặc tự tạo #file-chunks trong thư mục tài liệu."""
    configured = int(getattr(settings, "CHUNK_ARCHIVE_CHANNEL_ID", 0) or 0)
    if configured:
        ch = bot.get_channel(configured)
        if not isinstance(ch, discord.TextChannel) and hasattr(bot, "fetch_channel"):
            try:
                ch = await bot.fetch_channel(configured)
            except Exception:
                ch = None
        if isinstance(ch, discord.TextChannel):
            await lock_archive_channel(bot, ch)
            return ch

    category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)
    category = bot.get_channel(category_id)
    if not category and hasattr(bot, "fetch_channel"):
        try:
            category = await bot.fetch_channel(category_id)
        except Exception:
            category = None

    found: Optional[discord.TextChannel] = None
    if category:
        for ch in getattr(category, "text_channels", []):
            if "file-chunks" in ch.name.lower() or "file_chunks" in ch.name.lower():
                found = ch
                break
        if found:
            await lock_archive_channel(bot, found)
            return found
        try:
            created = await category.create_text_channel(
                name="📦・file-chunks",
                topic="Kho lưu trữ các phần file đề thi chẻ nhỏ (tự động, không chat ở đây).",
                reason="Chunk archive for large exam files",
            )
            log.info(f"Đã tạo kênh archive chunks: #{created.name} ({created.id})")
            await lock_archive_channel(bot, created)
            return created
        except Exception as e:
            log.warning(f"Không thể tạo kênh file-chunks: {e}")

    # Fallback: kênh database
    fallback_id = getattr(settings, "DATABASE_ARCHIVE_CHANNEL_ID", 0)
    if fallback_id:
        ch = bot.get_channel(fallback_id)
        if isinstance(ch, discord.TextChannel):
            return ch
        try:
            ch = await bot.fetch_channel(fallback_id)
            if isinstance(ch, discord.TextChannel):
                return ch
        except Exception:
            pass
    return None


def find_local_file(doc_id: int, file_name: str) -> Optional[str]:
    """Tìm file local theo quy ước {id}_{file_name}."""
    upload_dir = os.path.join(BOT_BASE_DIR, "storage", "uploads")
    safe = (file_name or "").replace("..", "").strip()
    candidate = os.path.realpath(os.path.join(upload_dir, f"{doc_id}_{safe}"))
    if candidate.startswith(os.path.realpath(upload_dir) + os.sep) and os.path.isfile(candidate):
        return candidate
    return None


async def archive_document(bot, db, doc_id: int, delete_local: bool = True) -> dict[str, Any]:
    """Chẻ + đăng toàn bộ file của 1 đề lên kênh archive, ghi document_chunks, xóa local.
    Trả về dict tóm tắt {success, parts, total_bytes, ...}."""
    row = await db.fetchone(
        "SELECT id, file_name, file_size_bytes FROM documents_archive WHERE id = ?",
        doc_id,
    )
    if not row:
        return {"success": False, "error": f"Không tìm thấy đề thi #{doc_id}"}

    file_name = row[1] or f"doc_{doc_id}.bin"
    local_path = find_local_file(doc_id, file_name)
    if not local_path:
        # Đã offload trước đó?
        chk = await db.fetchone("SELECT COUNT(*) FROM document_chunks WHERE doc_id = ?", doc_id)
        if chk and chk[0] > 0:
            await db.execute("UPDATE documents_archive SET is_chunked = 1 WHERE id = ?", doc_id)
            return {"success": True, "parts": chk[0], "message": f"Đề #{doc_id} đã offload từ trước ({chk[0]} phần)."}
        return {"success": False, "error": f"Không tìm thấy file local của đề #{doc_id} và chưa có chunks."}

    with open(local_path, "rb") as f:
        data = f.read()
    if not data:
        return {"success": False, "error": f"File local của đề #{doc_id} rỗng."}

    chunk_size = get_chunk_size_limit()
    parts = split_bytes(data, chunk_size)
    del data

    channel = await get_or_create_archive_channel(bot)
    if not channel:
        return {"success": False, "error": "Không tìm thấy/tạo được kênh archive."}

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    uploaded = []
    try:
        for idx, part in enumerate(parts, start=1):
            part_name = f"{doc_id:05d}.part{idx:02d}of{len(parts):02d}.bin"
            msg = await channel.send(
                content=f"📦 `#{doc_id}` `{file_name}` — phần `{idx}/{len(parts)}`",
                file=discord.File(io.BytesIO(part), filename=part_name),
            )
            att = msg.attachments[0] if msg.attachments else None
            uploaded.append({
                "part_no": idx,
                "channel_id": channel.id,
                "message_id": msg.id,
                "file_name": part_name,
                "size_bytes": len(part),
                "cdn_url": att.url if att else None,
            })
            # Tránh rate limit gửi file
            if idx < len(parts):
                await asyncio.sleep(6)
    except Exception as e:
        log.error(f"Lỗi upload chunks đề #{doc_id}: {e}")
        return {"success": False, "error": f"Lỗi đăng chunks lên Discord: {e}", "uploaded_parts": len(uploaded)}

    for u in uploaded:
        await db.execute(
            """INSERT OR REPLACE INTO document_chunks
               (doc_id, part_no, channel_id, message_id, file_name, size_bytes, cdn_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            doc_id, u["part_no"], u["channel_id"], u["message_id"],
            u["file_name"], u["size_bytes"], u["cdn_url"], now_iso,
        )
    await db.execute("UPDATE documents_archive SET is_chunked = 1 WHERE id = ?", doc_id)

    total = sum(u["size_bytes"] for u in uploaded)
    if delete_local:
        try:
            os.remove(local_path)
        except OSError as e:
            log.warning(f"Không xóa được file local #{doc_id}: {e}")

    log.info(f"Đã offload đề #{doc_id} ({file_name}): {len(uploaded)} phần, {total} bytes.")
    return {"success": True, "parts": len(uploaded), "total_bytes": total, "channel_id": channel.id}


async def fetch_merged_bytes(bot, db, doc_id: int, session=None) -> tuple[bytes | None, str | None]:
    """Tải toàn bộ chunks và ghép lại. Trả về (bytes, error)."""
    import aiohttp

    rows = await db.fetchall(
        "SELECT part_no, channel_id, message_id, cdn_url, size_bytes FROM document_chunks WHERE doc_id = ? ORDER BY part_no",
        doc_id,
    )
    if not rows:
        return None, "Đề này chưa được offload (không có chunks)."

    close_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600))
        close_session = True

    try:
        merged = bytearray()
        total_expected = 0
        for part_no, channel_id, message_id, cdn_url, size_bytes in rows:
            total_expected += size_bytes or 0
            if total_expected > 1024 * 1024 * 1024:
                return None, "File quá lớn để ghép (>1GB)."
            url = cdn_url
            if not url:
                # Fallback: lấy lại URL từ message
                try:
                    ch = bot.get_channel(int(channel_id))
                    if not ch:
                        ch = await bot.fetch_channel(int(channel_id))
                    msg = await ch.fetch_message(int(message_id))
                    if msg.attachments:
                        url = msg.attachments[0].url
                except Exception as e:
                    return None, f"Không lấy được phần {part_no}: {e}"
            if not url:
                return None, f"Thiếu URL cho phần {part_no}."
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None, f"Tải phần {part_no} thất bại (HTTP {resp.status})."
                merged.extend(await resp.read())
        return bytes(merged), None
    except Exception as e:
        return None, f"Lỗi ghép file: {e}"
    finally:
        if close_session:
            try:
                await session.close()
            except Exception:
                pass
