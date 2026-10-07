"""
cogs/doc_intake.py
Module Tiếp nhận, Quét an toàn, Phân loại và Thống kê Dung lượng Kho Đề Thi.
Đặc điểm:
- Kênh tiếp nhận chỉ hiển thị bảng thông báo/hướng dẫn gửi tài liệu của Bot.
- Hiển thị thời gian thực Tổng số lượng đề thi & Tổng dung lượng (MB / GB).
- Mọi tin nhắn của người dùng (file/link) tự động bị xóa sau khi nhận.
- Kết quả quét an toàn & phân loại được gửi RIÊNG TƯ (chỉ người nộp đọc được).
- Tự động chuyển tiếp và lưu trữ tài liệu vào Category tương ứng.
"""

from __future__ import annotations

import asyncio
import datetime
import io
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from services.antivirus_scanner import AntivirusScanner
from services.doc_service import DocumentAnalysisResult, DocumentService

# Import DocInspector Engine
try:
    from DocInspector import (
        DEFAULT_SUBMISSION_CHANNEL_ID,
        DEFAULT_TARGET_CATEGORY_ID,
        BotInspectorAdapter,
        CategoryDirectoryManager,
        ChannelComplianceValidator,
        InspectionReport,
        SubmissionRoutingResult,
    )
except ImportError:
    _project_root = Path(__file__).resolve().parent.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))
    from DocInspector import (
        DEFAULT_SUBMISSION_CHANNEL_ID,
        DEFAULT_TARGET_CATEGORY_ID,
        BotInspectorAdapter,
        CategoryDirectoryManager,
        ChannelComplianceValidator,
        InspectionReport,
        SubmissionRoutingResult,
    )

try:
    from DocInspector.hybrid_classifier import HybridExamClassifier
except ImportError:
    HybridExamClassifier = None

try:
    from cpp_core.bridge import fast_sha256
except ImportError:
    import hashlib
    def fast_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

# [ARCHIVED] PROBLEM_BANK — đã lưu trữ tại archived/duel_arena/services/duel_problems.py
PROBLEM_BANK: dict = {}

log = logging.getLogger(__name__)


def format_bytes_to_human(size_bytes: int | float) -> str:
    """Chuyển đổi số bytes sang định dạng dung lượng dễ đọc (KB, MB, GB)."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{int(size_bytes)} Bytes"


class JumpButtonView(discord.ui.View):
    """View chứa nút bấm chuyển tiếp nhanh tới bài đăng trong thư mục phân loại."""

    def __init__(self, jump_url: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="📖 Xem Đề Trong Thư Mục",
                style=discord.ButtonStyle.link,
                url=jump_url,
                emoji="📂",
            )
        )


class SubmitDocModal(discord.ui.Modal, title="📤 Nộp Đường Dẫn Tài Liệu Đề Thi"):
    """Modal cho phép người dùng dán link Google Drive hoặc link học tập."""

    link_input = discord.ui.TextInput(
        label="Đường dẫn (Google Drive / Trang web học tập)",
        placeholder="https://drive.google.com/file/d/... hoặc https://...",
        required=True,
        max_length=500,
    )
    note_input = discord.ui.TextInput(
        label="Ghi chú về tài liệu (Tùy chọn)",
        placeholder="Ví dụ: Đề thi thử THPT QG 2026 môn Hóa trường Chuyên...",
        required=False,
        max_length=300,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, cog: DocumentIntakeCog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        raw_url = AntivirusScanner.normalize_url(self.link_input.value.strip())
        note = self.note_input.value.strip() or None

        if not interaction.guild:
            await interaction.followup.send("❌ Chỉ hỗ trợ gửi tài liệu trong máy chủ Discord.", ephemeral=True)
            return

        from services.gdrive_importer import is_valid_gdrive_url_or_id
        if is_valid_gdrive_url_or_id(raw_url):
            try:
                success, msg, embed, posted_msg = await self.cog.handle_gdrive_submission(
                    guild=interaction.guild,
                    author=interaction.user,
                    gdrive_url=raw_url,
                    note=note,
                )
                view = JumpButtonView(posted_msg.jump_url) if posted_msg else None
                if embed:
                    await interaction.followup.send(embed=embed, view=view, ephemeral=True)
                else:
                    await interaction.followup.send(msg, view=view, ephemeral=True)

                intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
                intake_ch = interaction.guild.get_channel(intake_channel_id)
                if intake_ch and isinstance(intake_ch, discord.TextChannel):
                    await self.cog.clean_intake_channel(intake_ch)
                return
            except Exception as ge:
                log.exception("Lỗi khi xử lý link Google Drive từ modal: %s", ge)
                await interaction.followup.send(f"❌ Lỗi kiểm định link Google Drive: `{ge}`", ephemeral=True)
                return

        try:
            report, routing, posted_msg = await self.cog.process_and_route(
                guild=interaction.guild,
                author=interaction.user,
                file_path_or_bytes=raw_url,
                note=note,
            )
            reply_text = routing.submission_reply_message
            # Thêm thông tin năm học và trường nếu có
            extra_info = ""
            if hasattr(report, 'academic_year') and report.academic_year:
                extra_info += f"\n📅 **Năm học:** `{report.academic_year}`"
            if hasattr(report, 'school_or_department') and report.school_or_department:
                extra_info += f"\n🏫 **Trường / Sở GD:** `{report.school_or_department}`"
            reply_text += extra_info

            view = JumpButtonView(posted_msg.jump_url) if posted_msg else None
            await interaction.followup.send(reply_text, view=view, ephemeral=True)

            # Dọn dẹp kênh nộp tài liệu và cập nhật bảng thống kê
            intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
            intake_ch = interaction.guild.get_channel(intake_channel_id)
            if intake_ch and isinstance(intake_ch, discord.TextChannel):
                await self.cog.clean_intake_channel(intake_ch)
        except Exception as e:
            log.exception("Lỗi khi xử lý link từ modal: %s", e)
            await interaction.followup.send(f"❌ Đã xảy ra lỗi khi xử lý liên kết: `{e}`", ephemeral=True)


class DocumentIntakeControlView(discord.ui.View):
    """Bảng điều khiển tương tác thường trực tại kênh nộp tài liệu."""

    def __init__(self, cog: DocumentIntakeCog | None = None):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="📤 Nộp Link / Google Drive",
        style=discord.ButtonStyle.primary,
        custom_id="btn_doc_intake_submit_link",
        emoji="🔗",
    )
    async def btn_submit_link(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.cog or interaction.client.get_cog("DocumentIntakeCog")
        if not cog:
            await interaction.response.send_message("❌ Hệ thống chưa sẵn sàng.", ephemeral=True)
            return
        await interaction.response.send_modal(SubmitDocModal(cog))

    @discord.ui.button(
        label="📊 Thống Kê Kho Đề & Dung Lượng",
        style=discord.ButtonStyle.success,
        custom_id="btn_doc_intake_stats",
        emoji="💾",
    )
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        cog = self.cog or interaction.client.get_cog("DocumentIntakeCog")
        if not cog:
            await interaction.response.send_message("❌ Hệ thống chưa sẵn sàng.", ephemeral=True)
            return
        embed = await cog.build_detailed_stats_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


class DocumentIntakeCog(commands.Cog):
    """Cog xử lý tiếp nhận tài liệu đề thi, tự động phân loại và thống kê dung lượng."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._setup_lock = asyncio.Lock()
        self._clean_lock = asyncio.Lock()
        self._panel_message_id: Optional[int] = None
        self._pending_panel_update: bool = False
        self._last_panel_update: float = 0.0

    async def _get_or_create_subject_channel(
        self, guild: discord.Guild, category_id: int, channel_slug: str, icon: str, subject_name: str
    ) -> discord.TextChannel | None:
        """Tìm kênh chuyên môn trong Category, hoặc tự động tạo nếu chưa có."""
        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            if hasattr(self.bot, "fetch_channel"):
                try:
                    category = await self.bot.fetch_channel(category_id)
                except Exception:
                    pass

        if not category or not isinstance(category, discord.CategoryChannel):
            log.warning("Không tìm thấy Category ID: %s", category_id)
            return None

        clean_slug = channel_slug.lower().replace(" ", "-")
        target_name = f"{icon}・{clean_slug}"

        for ch in category.text_channels:
            if clean_slug in ch.name.lower():
                return ch

        try:
            new_channel = await category.create_text_channel(
                name=target_name,
                topic=f"📚 Kho lưu trữ & phân loại đề thi môn {subject_name} được đóng góp tự động.",
                reason="Auto-created subject channel for document intake system",
            )
            log.info("Đã tạo kênh chuyên môn mới: #%s trong Category %s", new_channel.name, category.name)
            return new_channel
        except Exception as e:
            log.warning("Không thể tự động tạo kênh #%s: %s", target_name, e)
            intake_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
            valid_dest_channels = [
                ch for ch in category.text_channels
                if ch.id != intake_id
                and not any(k in ch.name.lower() for k in ["nop-tai-lieu", "nộp-tài-liệu", "tra-cuu", "verify-link", "bot-log"])
            ]
            if valid_dest_channels:
                return valid_dest_channels[0]
            return None

    async def handle_gdrive_submission(
        self,
        guild: discord.Guild,
        author: discord.User | discord.Member,
        gdrive_url: str,
        note: str | None = None,
    ) -> tuple[bool, str, discord.Embed | None, discord.Message | None]:
        """Quy trình tiếp nhận và kiểm định 5 lớp bảo mật cho link Google Drive."""
        from services.gdrive_importer import verify_and_import_gdrive
        author_name = getattr(author, "display_name", getattr(author, "name", "Thành viên"))
        author_mention = author.mention if hasattr(author, "mention") else f"<@{getattr(author, 'id', 0)}>"

        results = await asyncio.to_thread(verify_and_import_gdrive, gdrive_url, author_name, author.id)
        if not results:
            return False, "Không có phản hồi từ hệ thống kiểm định Google Drive.", None, None

        first_res = results[0]

        # 1. TRƯỜNG HỢP BỊ CHẶN BỞI CÁC LỚP BẢO MẬT
        if first_res.get("blocked"):
            err_msg = "Tài liệu hoặc liên kết không đáp ứng tiêu chuẩn an toàn của hệ thống."
            alert_embed = discord.Embed(
                title="⚠️ Tài Liệu Không Thể Tiếp Nhận",
                description=(
                    "Tệp hoặc liên kết Google Drive của bạn không đáp ứng tiêu chuẩn kiểm định an toàn của hệ thống.\n\n"
                    "Vui lòng đảm bảo bạn đang chia sẻ tài liệu học tập hợp lệ và đường liên kết có quyền xem công khai."
                ),
                color=0xE74C3C,
            )
            return False, err_msg, alert_embed, None

        # 2. TRƯỜNG HỢP TÀI LIỆU TRÙNG LẶP
        if first_res.get("is_duplicate"):
            dup_msg = first_res.get("message", "Tài liệu này đã tồn tại trong kho.")
            jump_url = first_res.get("jump_url")
            dup_embed = discord.Embed(
                title="🔁 Tài Liệu Trùng Lặp",
                description=f"{dup_msg}\n\n" + (f"🔗 **Bài đăng gốc:** {jump_url}" if jump_url else ""),
                color=0xE67E22,
            )
            return False, dup_msg, dup_embed, None

        # 3. TRƯỜNG HỢP TIẾP NHẬN THÀNH CÔNG
        success_items = [r for r in results if r.get("success")]
        if not success_items:
            err_msg = first_res.get("error", "Không thể nạp tệp từ Google Drive.")
            return False, err_msg, None, None

        category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)
        posted_msg = None

        for item in success_items:
            doc_id = item["id"]
            file_name = item["file_name"]
            subject = item["detected_subject"]
            grade = item["estimated_level"]
            exam_type = item["exam_type"]
            year = item.get("academic_year")
            school = item.get("school")
            saved_path = item.get("saved_path")
            q_cnt = item.get("question_count", 0)
            p_cnt = item.get("page_count", 1)

            # Bản đồ slug kênh môn học
            subject_channel_slugs = {
                "MATHEMATICS": ("toán-học", "📐", "Toán Học"),
                "LITERATURE": ("ngữ-văn", "📖", "Ngữ Văn"),
                "ENGLISH": ("tiếng-anh", "🇬🇧", "Tiếng Anh"),
                "PHYSICS": ("vật-lý", "⚡", "Vật Lý"),
                "CHEMISTRY": ("hóa-học", "🧪", "Hóa Học"),
                "BIOLOGY": ("sinh-học", "🧬", "Sinh Học"),
                "INFORMATICS": ("tin-học", "💻", "Tin Học"),
                "HISTORY": ("lịch-sử", "🏛️", "Lịch Sử"),
                "GEOGRAPHY": ("địa-lý", "🗺️", "Địa Lý"),
            }
            slug_info = subject_channel_slugs.get(subject.upper(), ("kho-đề-chung", "📚", subject))

            target_ch = await self._get_or_create_subject_channel(
                guild=guild,
                category_id=category_id,
                channel_slug=slug_info[0],
                icon=slug_info[1],
                subject_name=slug_info[2],
            )

            if target_ch and isinstance(target_ch, discord.TextChannel):
                post_content = (
                    f"📚 **[ĐỀ THI MỚI - TIẾP NHẬN TỪ GOOGLE DRIVE]**\n"
                    f"📄 **Tên tệp:** `{file_name}`\n"
                    f"📖 **Môn học:** `{slug_info[2]}` | 🎓 **Khối:** `{grade}` | 🏷️ **Loại đề:** `{exam_type}`\n"
                    f"📊 **Quy mô:** `{q_cnt}` câu • `{p_cnt}` trang\n"
                )
                if year:
                    post_content += f"📅 **Năm học:** `{year}`\n"
                if school:
                    post_content += f"🏫 **Nguồn / Trường:** `{school}`\n"
                post_content += f"👤 **Người gửi đóng góp:** {author_mention} (`{author_name}`)\n"
                if note:
                    post_content += f"📝 **Ghi chú:** {note}\n"
                post_content += f"✅ *Tài liệu đã được xác minh và tiếp nhận vào kho đề.*"

                try:
                    if saved_path and os.path.exists(saved_path) and os.path.getsize(saved_path) <= 25 * 1024 * 1024:
                        file_forward = discord.File(saved_path, filename=file_name)
                        posted_msg = await target_ch.send(content=post_content, file=file_forward)
                    else:
                        posted_msg = await target_ch.send(content=post_content)

                    # Cập nhật jump_url, channel_id, message_id vào DB
                    if posted_msg and hasattr(self.bot, "db"):
                        await self.bot.db.execute(
                            "UPDATE documents_archive SET jump_url = ?, channel_id = ?, message_id = ? WHERE id = ?",
                            posted_msg.jump_url,
                            target_ch.id,
                            posted_msg.id,
                            doc_id,
                        )
                except Exception as post_err:
                    log.warning("Lỗi gửi đề thi vào kênh môn học: %s", post_err)

        # Tạo Embed phản hồi riêng tư cho người nộp
        item = success_items[0]
        success_embed = discord.Embed(
            title="✅ Tiếp Nhận Tài Liệu Thành Công",
            description=(
                f"Đề thi từ Google Drive đã được xác minh và chuyển tiếp vào kênh môn học.\n\n"
                f"📄 **Tên tệp:** `{item['file_name']}`\n"
                f"📚 **Môn:** `{item['detected_subject']}` | 🎓 **Khối:** `{item['estimated_level']}` | 🏷️ **Phân loại:** `{item['exam_type']}`\n"
            ),
            color=0x2ECC71,
        )
        if posted_msg:
            success_embed.add_field(name="🔗 Bài đăng trên Discord", value=f"[Nhấn vào đây để xem đề]({posted_msg.jump_url})", inline=False)

        return True, "Tiếp nhận đề thi thành công!", success_embed, posted_msg

    async def get_storage_statistics(self) -> dict[str, Any]:
        """Tính toán tổng số đề thi và tổng dung lượng (MB / GB) trong toàn hệ thống."""
        stats = {
            "total_docs": 0,
            "total_doc_bytes": 0,
            "subject_breakdown": {},
            "cp_problems_count": len(PROBLEM_BANK),
            "cp_storage_bytes": 0,
            "grand_total_items": 0,
            "grand_total_bytes": 0,
        }

        # 1. Tính dung lượng kho đề CP Arena (data/ai_problems.json)
        ai_problems_path = Path("data/ai_problems.json")
        if ai_problems_path.exists():
            stats["cp_storage_bytes"] = ai_problems_path.stat().st_size

        # 2. Truy vấn cơ sở dữ liệu documents_archive
        if hasattr(self.bot, "db"):
            try:
                row_total = await self.bot.db.fetchone(
                    "SELECT COUNT(*), COALESCE(SUM(file_size_bytes), 0) FROM documents_archive"
                )
                if row_total:
                    stats["total_docs"] = row_total[0]
                    stats["total_doc_bytes"] = row_total[1]

                rows_by_sub = await self.bot.db.fetchall(
                    "SELECT subject, COUNT(*), COALESCE(SUM(file_size_bytes), 0) FROM documents_archive GROUP BY subject"
                )
                for r in rows_by_sub:
                    stats["subject_breakdown"][r[0]] = {
                        "count": r[1],
                        "bytes": r[2],
                    }
            except Exception as e:
                log.debug("Chưa thể truy vấn documents_archive: %s", e)

        stats["grand_total_items"] = stats["total_docs"] + stats["cp_problems_count"]
        stats["grand_total_bytes"] = stats["total_doc_bytes"] + stats["cp_storage_bytes"]
        return stats

    async def record_archived_document(
        self,
        res: DocumentAnalysisResult,
        author: discord.User | discord.Member,
        target_channel: discord.TextChannel,
        message: discord.Message,
    ) -> None:
        """Ghi nhận tài liệu mới vào cơ sở dữ liệu SQLite để thống kê dung lượng."""
        if not hasattr(self.bot, "db"):
            return

        try:
            file_bytes = int(res.file_size_mb * 1024 * 1024) if res.file_size_mb > 0 else len(res.summary.encode("utf-8"))
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

            await self.bot.db.execute(
                """
                INSERT INTO documents_archive (
                    subject, title, file_name, file_size_bytes, file_type,
                    estimated_level, question_count, page_count, author_id,
                    author_name, channel_id, message_id, jump_url, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                res.subject,
                res.title,
                os.path.basename(res.file_path) if res.file_path else "Link_Document",
                file_bytes,
                res.file_type,
                res.estimated_level,
                res.question_count,
                res.page_count,
                author.id,
                author.name,
                target_channel.id,
                message.id,
                message.jump_url,
                now_iso,
            )
            log.info("Đã lưu metadata đề thi '%s' (%s) vào documents_archive.", res.title, format_bytes_to_human(file_bytes))
            if hasattr(self.bot, "embedding_service") and self.bot.embedding_service:
                try:
                    last_row = await self.bot.db.fetchone(
                        "SELECT id FROM documents_archive WHERE message_id = ? ORDER BY id DESC LIMIT 1",
                        message.id,
                    )
                    if last_row:
                        asyncio.create_task(
                            self.bot.embedding_service.embed_and_save_document(
                                doc_id=last_row[0],
                                subject=res.subject,
                                title=res.title,
                                file_name=os.path.basename(res.file_path) if res.file_path else "Link_Document",
                                raw_text=None,
                            )
                        )
                except Exception as emb_e:
                    log.debug("Lỗi kích hoạt embedding cho tài liệu mới: %s", emb_e)
        except Exception as e:
            log.warning("Lỗi ghi nhận documents_archive: %s", e)

    async def record_inspection_report(
        self,
        report: InspectionReport,
        routing: SubmissionRoutingResult,
        author: discord.User | discord.Member,
        target_channel: discord.TextChannel,
        message: discord.Message,
        file_hash: Optional[str] = None,
        raw_text: Optional[str] = None,
    ) -> None:
        """Ghi nhận tài liệu mới từ DocInspector vào cơ sở dữ liệu SQLite để thống kê dung lượng."""
        if not hasattr(self.bot, "db"):
            return

        try:
            file_bytes = report.file_size_bytes or len(report.human_summary.encode("utf-8"))
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            subject_name = (
                report.detected_subject.value
                if hasattr(report.detected_subject, "value")
                else str(report.detected_subject)
            )

            _verdict = getattr(report.verdict, "value", str(report.verdict)) if getattr(report, "verdict", None) is not None else None
            _track = getattr(report.exam_track, "value", str(report.exam_track)) if getattr(report, "exam_track", None) is not None else None
            try:
                _conf = float(report.confidence_score) if getattr(report, "confidence_score", None) is not None else None
            except (TypeError, ValueError):
                _conf = None
            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO documents_archive (
                        subject, title, file_name, file_size_bytes, file_type,
                        estimated_level, question_count, page_count, author_id,
                        author_name, channel_id, message_id, jump_url, timestamp, file_hash, raw_text,
                        verdict, exam_track, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    subject_name,
                    report.file_name,
                    report.file_name,
                    file_bytes,
                    report.document_category.value if hasattr(report.document_category, "value") else "EXAM",
                    f"{report.grade_level_label_vi} ({report.exam_track_label_vi})",
                    len(report.pass2.questions) if hasattr(report, "pass2") and hasattr(report.pass2, "questions") else 0,
                    report.pass1.page_count if hasattr(report, "pass1") else 1,
                    author.id,
                    author.name,
                    target_channel.id,
                    message.id,
                    message.jump_url,
                    now_iso,
                    file_hash,
                    raw_text,
                    _verdict,
                    _track,
                    _conf,
                )
            except Exception:
                # DB cũ chưa migrate: chèn tương thích không kèm verdict/track/confidence
                await self.bot.db.execute(
                    """
                    INSERT INTO documents_archive (
                        subject, title, file_name, file_size_bytes, file_type,
                        estimated_level, question_count, page_count, author_id,
                        author_name, channel_id, message_id, jump_url, timestamp, file_hash, raw_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    subject_name,
                    report.file_name,
                    report.file_name,
                    file_bytes,
                    report.document_category.value if hasattr(report.document_category, "value") else "EXAM",
                    f"{report.grade_level_label_vi} ({report.exam_track_label_vi})",
                    len(report.pass2.questions) if hasattr(report, "pass2") and hasattr(report.pass2, "questions") else 0,
                    report.pass1.page_count if hasattr(report, "pass1") else 1,
                    author.id,
                    author.name,
                    target_channel.id,
                    message.id,
                    message.jump_url,
                    now_iso,
                    file_hash,
                    raw_text,
                )
            log.info("Đã lưu metadata đề thi '%s' (%s) vào documents_archive.", report.file_name, format_bytes_to_human(file_bytes))
            if hasattr(self.bot, "embedding_service") and self.bot.embedding_service:
                try:
                    last_row = await self.bot.db.fetchone(
                        "SELECT id FROM documents_archive WHERE message_id = ? ORDER BY id DESC LIMIT 1",
                        message.id,
                    )
                    if last_row:
                        asyncio.create_task(
                            self.bot.embedding_service.embed_and_save_document(
                                doc_id=last_row[0],
                                subject=subject_name,
                                title=report.file_name or "Tài liệu",
                                file_name=report.file_name or "document",
                                raw_text=raw_text,
                            )
                        )
                except Exception as emb_e:
                    log.debug("Lỗi kích hoạt embedding cho tài liệu mới: %s", emb_e)
        except Exception as e:
            log.warning("Lỗi ghi nhận documents_archive: %s", e)

    async def index_message_document(self, message: discord.Message) -> int:
        """
        Lập chỉ mục một tin nhắn có tệp đính kèm hoặc URL (từ Bot hoặc Admin/User)
        vào bảng documents_archive để phục vụ tra cứu.
        Trả về số lượng tài liệu mới được lập chỉ mục (0 nếu đã tồn tại).
        """
        if not hasattr(self.bot, "db"):
            return 0

        # Kiểm tra xem message_id này đã được lưu vào documents_archive chưa
        try:
            row = await self.bot.db.fetchone(
                "SELECT id FROM documents_archive WHERE message_id = ?",
                message.id,
            )
            if row:
                return 0
        except Exception:
            pass

        indexed_count = 0

        # 1. Quét tệp đính kèm (Attachments)
        if message.attachments:
            for att in message.attachments:
                ext = Path(att.filename).suffix.lower()
                if ext not in [".pdf", ".docx", ".doc", ".txt", ".cpp", ".py", ".zip", ".rar", ".7z", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                    continue

                try:
                    data = await att.read()
                    file_hash = fast_sha256(data) if data else None

                    # Kiểm tra trùng lặp bằng file_hash
                    if file_hash:
                        existing_hash = await self.bot.db.fetchone(
                            "SELECT id FROM documents_archive WHERE file_hash = ?",
                            file_hash,
                        )
                        if existing_hash:
                            continue

                    subject_name = "GENERAL"
                    level_str = "Tài liệu"
                    q_count = 0
                    file_type = ext.replace(".", "").upper()

                    # Phân loại bằng HybridExamClassifier
                    if HybridExamClassifier:
                        res = HybridExamClassifier.classify(data, file_name=att.filename)
                        subject_name = res.subject
                        if res.grade:
                            grade_str = f"Lớp {res.grade}"
                            lang_tag = f" • [{res.programming_language}]" if getattr(res, "programming_language", None) else ""
                            level_str = f"{grade_str} ({res.track}){lang_tag}"
                        else:
                            level_str = "Chung ( chung cho tất cả khối )"
                        q_count = res.question_count
                        file_type = res.raw_file_type

                    now_iso = message.created_at.isoformat()
                    author_name = message.author.display_name or message.author.name
                    if message.author.id == self.bot.user.id:
                        author_name = "Hệ thống (Bot)"

                    await self.bot.db.execute(
                        """
                        INSERT INTO documents_archive (
                            subject, title, file_name, file_size_bytes, file_type,
                            estimated_level, question_count, page_count, author_id,
                            author_name, channel_id, message_id, jump_url, timestamp, file_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        subject_name,
                        att.filename,
                        att.filename,
                        len(data),
                        file_type,
                        level_str,
                        q_count,
                        1,
                        message.author.id,
                        author_name,
                        message.channel.id,
                        message.id,
                        message.jump_url,
                        now_iso,
                        file_hash,
                    )
                    indexed_count += 1
                    log.info(
                        "Đã lập chỉ mục đề thi '%s' từ kênh #%s (Người gửi: %s, Môn: %s)",
                        att.filename, getattr(message.channel, 'name', 'N/A'), author_name, subject_name
                    )
                except Exception as e:
                    log.warning("Lỗi lập chỉ mục attachment %s trong tin nhắn %s: %s", att.filename, message.id, e)

        # 2. Quét liên kết URL nếu không có tệp đính kèm
        elif "http" in message.content:
            url_m = re.search(r"https?://[^\s]+", message.content)
            if url_m:
                raw_url = url_m.group(0)
                try:
                    subject_name = "GENERAL"
                    level_str = "Liên kết tài liệu"
                    q_count = 0
                    if HybridExamClassifier:
                        res = HybridExamClassifier.classify(message.content, file_name="online_link")
                        subject_name = res.subject
                        if res.grade:
                            grade_str = f"Lớp {res.grade}"
                            lang_tag = f" • [{res.programming_language}]" if getattr(res, "programming_language", None) else ""
                            level_str = f"{grade_str} ({res.track}){lang_tag}"
                        else:
                            level_str = "Chung ( chung cho tất cả khối )"
                        q_count = res.question_count

                    now_iso = message.created_at.isoformat()
                    author_name = message.author.display_name or message.author.name
                    if message.author.id == self.bot.user.id:
                        author_name = "Hệ thống (Bot)"

                    file_hash = fast_sha256(raw_url.encode("utf-8"))
                    await self.bot.db.execute(
                        """
                        INSERT INTO documents_archive (
                            subject, title, file_name, file_size_bytes, file_type,
                            estimated_level, question_count, page_count, author_id,
                            author_name, channel_id, message_id, jump_url, timestamp, file_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        subject_name,
                        raw_url[:120],
                        "URL Link",
                        len(message.content),
                        "URL",
                        level_str,
                        q_count,
                        1,
                        message.author.id,
                        author_name,
                        message.channel.id,
                        message.id,
                        message.jump_url,
                        now_iso,
                        file_hash,
                    )
                    indexed_count += 1
                except Exception as e:
                    log.warning("Lỗi lập chỉ mục URL trong tin nhắn %s: %s", message.id, e)

        return indexed_count

    async def sync_category_archive(self, guild: discord.Guild, limit_per_channel: int = 150) -> dict:
        """
        Quét và đồng bộ toàn bộ lịch sử các kênh trong Thư Mục Phân Loại (1534147951797080174).
        Bao gồm cả đề thi do Bot gửi và do Admin/User gửi trực tiếp.
        """
        category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)
        category = guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            if hasattr(self.bot, "fetch_channel"):
                try:
                    category = await self.bot.fetch_channel(category_id)
                except Exception:
                    pass

        if not category or not isinstance(category, discord.CategoryChannel):
            log.warning("Không tìm thấy Category %s để đồng bộ kho đề", category_id)
            return {"channels": 0, "scanned_messages": 0, "new_indexed": 0}

        total_scanned = 0
        new_indexed = 0
        channels_count = len(category.text_channels)

        log.info("Bắt đầu quét và đồng bộ kho đề từ %d kênh trong Category %s...", channels_count, category.name)

        for ch in category.text_channels:
            try:
                async for msg in ch.history(limit=limit_per_channel):
                    total_scanned += 1
                    if msg.attachments or "http" in msg.content:
                        cnt = await self.index_message_document(msg)
                        if cnt > 0:
                            new_indexed += cnt
                            try:
                                await msg.add_reaction("📌")
                            except Exception:
                                pass
            except Exception as ce:
                log.warning("Lỗi khi quét lịch sử kênh #%s: %s", ch.name, ce)

        # Rà soát và dọn dẹp các đề thi trong DB mà tin nhắn Discord đã bị Admin xóa (Prune dead entries)
        pruned_deleted = 0
        if hasattr(self.bot, "db"):
            try:
                db_docs = await self.bot.db.fetchall(
                    "SELECT id, channel_id, message_id, title FROM documents_archive WHERE message_id IS NOT NULL"
                )
                for d_id, ch_id, m_id, d_title in db_docs:
                    target_ch = guild.get_channel(ch_id)
                    if not target_ch:
                        await self.bot.db.execute("DELETE FROM documents_archive WHERE id = ?", d_id)
                        pruned_deleted += 1
                        continue
                    try:
                        await target_ch.fetch_message(m_id)
                    except discord.NotFound:
                        await self.bot.db.execute("DELETE FROM documents_archive WHERE id = ?", d_id)
                        pruned_deleted += 1
                        log.info("🗑️ [Prune] Đã đồng bộ xóa đề thi mồ côi '%s' (ID: %d) do tin nhắn đã bị xóa.", d_title, d_id)
                    except Exception:
                        pass
            except Exception as pe:
                log.warning("Lỗi khi rà soát đề thi bị xóa: %s", pe)

        # Rà soát và loại bỏ các bản ghi trùng lặp (Deduplication pass - Không đề xuất trùng lặp)
        pruned_duplicates = 0
        if hasattr(self.bot, "db"):
            try:
                dup_rows = await self.bot.db.fetchall(
                    """
                    SELECT id FROM documents_archive
                    WHERE id NOT IN (
                        SELECT MIN(id)
                        FROM documents_archive
                        GROUP BY COALESCE(file_hash, message_id, title)
                    )
                    """
                )
                if dup_rows:
                    pruned_duplicates = len(dup_rows)
                    dup_ids = [r[0] for r in dup_rows]
                    placeholders = ",".join("?" for _ in dup_ids)
                    await self.bot.db.execute(
                        f"DELETE FROM documents_archive WHERE id IN ({placeholders})",
                        *dup_ids,
                    )
                    log.info("🗑️ [Deduplicate] Đã xóa %d bản ghi đề thi trùng lặp khỏi kho lưu trữ.", pruned_duplicates)
            except Exception as de:
                log.debug("Bỏ qua lỗi deduplicate: %s", de)

        log.info(
            "Hoàn tất đồng bộ kho đề: Quét %d tin nhắn từ %d kênh, thêm mới %d tài liệu, gỡ %d đề thi đã xóa, loại bỏ %d đề trùng lặp.",
            total_scanned, channels_count, new_indexed, pruned_deleted, pruned_duplicates
        )
        return {
            "channels": channels_count,
            "scanned_messages": total_scanned,
            "new_indexed": new_indexed,
            "pruned_deleted": pruned_deleted,
            "pruned_duplicates": pruned_duplicates,
        }

    async def build_intake_panel_embeds(self) -> list[discord.Embed]:
        """Tạo 2 Embeds hướng dẫn nộp tài liệu chuẩn và bảng thống kê dung lượng kho đề."""
        stats = await self.get_storage_statistics()
        total_size_human = format_bytes_to_human(stats["grand_total_bytes"])
        total_docs_count = stats["grand_total_items"]

        # Embed 1: Hướng dẫn chi tiết cách thức nộp tài liệu
        guide_desc = (
            "Chào mừng bạn đến với **Trạm Tiếp Nhận & Phân Loại Đề Thi Tự Động**!\n"
            "Hệ thống ứng dụng công nghệ **DocInspector Engine** (< 25ms, 100% Deterministic) "
            "để tự động quét virus, nhận diện môn học, khối lớp, thể loại và lưu trữ vào đúng chuyên mục.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "### 🚀 CÁCH THỨC NỘP TÀI LIỆU VÀO KÊNH\n\n"
            "📂 **Cách 1: Gửi tệp đính kèm trực tiếp (Khuyên dùng)**\n"
            "> • **Kéo & thả** hoặc chọn gửi tệp (`.pdf`, `.docx`, `.doc`, `.txt`...) trực tiếp vào khung chat kênh này.\n"
            "> • 🔒 *Tin nhắn của bạn sẽ tự động được xóa ngay sau khi tiếp nhận để giữ kênh luôn sạch sẽ và bảo mật dữ liệu.*\n\n"
            "🔗 **Cách 2: Gửi liên kết / Google Drive**\n"
            "> • Dán trực tiếp đường link Google Drive (để chế độ công khai) hoặc link trang web học tập vào khung chat.\n"
            "> • Hoặc bấm nút **'🔗 Nộp Link / Google Drive'** bên dưới để mở Form nhập kèm ghi chú.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "### 🎯 QUY TRÌNH PHÂN LOẠI 4 CHIỀU TOÀN DIỆN\n"
            "Mỗi tài liệu gửi lên sẽ được hệ thống tự động thẩm định theo 4 tiêu chí:\n"
            "1. 📚 **Môn học:** Tự động phát hiện Toán, Tin, Lý, Hóa, Sinh, Văn, Anh, Sử - Địa, GDCD...\n"
            "2. 🎓 **Khối lớp:** Lớp 12, 11, 10, 9, 8, 7, 6, THCS, THPT, Đội tuyển/Olympic, Đại học.\n"
            "3. 🏷️ **Thể loại:** `thường` / `hsg` / `chuyên` *(Quy tắc: thường < hsg < chuyên, hsg là cấp độ dễ hơn chuyên)*.\n"
            "4. 🛡️ **4 Trạng thái thẩm định:**\n"
            "   • `Xác minh (thấy ổn)`: Đề thi chuẩn, nội dung và cấu trúc rõ ràng.\n"
            "   • `Chưa rõ ràng`: Nhận diện được đề nhưng chưa chắc chắn hoàn toàn (cần đối soát thêm).\n"
            "   • `Không rõ ràng`: Xem được đề nhưng không rõ năm/trường hoặc cấu trúc khuyết.\n"
            "   • `Không xác minh`: File lỗi/rỗng hoặc web chặn bot (*báo không rõ nguồn gốc*).\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📁 **Thư mục lưu trữ:** Sau khi kiểm tra thành công, tài liệu sẽ được tự động chuyển tiếp sang kênh tương ứng tại **Thư Mục Phân Loại** (<#1534147951797080174>).\n"
            "📩 **Phản hồi riêng tư:** Kết quả thẩm định và link nhảy tới bài đăng trong thư mục sẽ được gửi riêng cho bạn!"
        )

        embed_guide = discord.Embed(
            title="📤 HƯỚNG DẪN NỘP TÀI LIỆU & ĐỀ THI TỰ ĐỘNG",
            description=guide_desc,
            color=0x5865F2,
        )

        # Embed 2: Thống kê kho dữ liệu hiện tại
        stats_desc = (
            f"📊 **TỔNG QUAN KHO ĐỀ THI & DUNG LƯỢNG LƯU TRỮ HIỆN TẠI:**\n\n"
            f"• 📚 **Tổng số lượng đề & tài liệu:** `{total_docs_count:,} tài liệu`\n"
            f"• 💾 **Tổng dung lượng toàn bộ kho:** `{total_size_human}`\n"
            f"• 🏆 **Đề đấu trường CP Arena:** `{stats['cp_problems_count']:,} đề` ({format_bytes_to_human(stats['cp_storage_bytes'])})\n"
            f"• 📂 **Tài liệu các môn học:** `{stats['total_docs']:,} tệp` ({format_bytes_to_human(stats['total_doc_bytes'])})\n\n"
            "📑 **Định dạng được hỗ trợ:** `.pdf`, `.docx`, `.doc`, `.txt`, `.cpp`, `.py`\n"
            "🛡️ **An toàn:** Tự động lọc virus, mã độc, phishing và tệp giả mạo."
        )

        embed_stats = discord.Embed(
            title="📊 THỐNG KÊ KHO DỮ LIỆU & BẢO MẬT",
            description=stats_desc,
            color=0x2ECC71,
        )
        embed_stats.set_footer(text=f"DocInspector Engine • Sub-25ms Non-AI • Dung lượng hiện tại: {total_size_human}")

        return [embed_guide, embed_stats]

    async def build_intake_panel_embed(self) -> discord.Embed:
        """Tương thích ngược: trả về embed hướng dẫn đầu tiên."""
        embeds = await self.build_intake_panel_embeds()
        return embeds[0]

    async def build_detailed_stats_embed(self) -> discord.Embed:
        """Tạo Embed thống kê chi tiết dung lượng và số lượng từng môn học."""
        stats = await self.get_storage_statistics()
        total_size_human = format_bytes_to_human(stats["grand_total_bytes"])

        embed = discord.Embed(
            title="📊 THỐNG KÊ CHI TIẾT KHO ĐỀ & DUNG LƯỢNG",
            description=(
                f"💾 **Tổng dung lượng toàn bộ kho:** `{total_size_human}`\n"
                f"📚 **Tổng số lượng bài/tệp:** `{stats['grand_total_items']:,} tài liệu`\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x2ECC71,
        )

        embed.add_field(
            name="🏆 Đấu Trường Thuật Toán CP Arena",
            value=f"• Số bài: `{stats['cp_problems_count']:,} đề`\n• Dung lượng: `{format_bytes_to_human(stats['cp_storage_bytes'])}`",
            inline=False,
        )

        subject_icons = {
            "Tin Học": "💻",
            "Tiếng Anh": "🇬🇧",
            "Hóa Học": "🧪",
            "Sinh Học": "🧬",
            "Toán Học": "📐",
            "Vật Lý": "⚡",
            "Ngữ Văn": "📜",
            "Sử - Địa": "🌍",
            "Tổng Hợp": "📚",
        }

        breakdown = stats["subject_breakdown"]
        if breakdown:
            for sub, info in breakdown.items():
                icon = subject_icons.get(sub, "📁")
                human_sz = format_bytes_to_human(info["bytes"])
                embed.add_field(
                    name=f"{icon} {sub}",
                    value=f"`{info['count']} đề` • `{human_sz}`",
                    inline=True,
                )
        else:
            embed.add_field(
                name="📂 Tài Liệu Chuyên Môn",
                value="*Chưa có tài liệu nào được nộp vào database.*",
                inline=False,
            )

        embed.set_footer(text="Hệ Thống Tự Động Phân Loại Đề Thi • HyperHub")
        return embed

    async def clean_intake_channel(self, channel: discord.TextChannel) -> None:
        """Xóa tất cả tin nhắn trong kênh nộp tài liệu ngoại trừ bảng điều khiển chính thức."""
        async with self._clean_lock:
            try:
                # 1. Tìm bảng panel chính thức
                panel_msg = None
                if self._panel_message_id:
                    try:
                        panel_msg = await channel.fetch_message(self._panel_message_id)
                    except Exception:
                        panel_msg = None

                if not panel_msg:
                    async for m in channel.history(limit=50):
                        if m.author.id == self.bot.user.id and m.embeds:
                            if any("HƯỚNG DẪN NỘP TÀI LIỆU" in (e.title or "") for e in m.embeds):
                                panel_msg = m
                                self._panel_message_id = m.id
                                break

                # 2. Nếu không tìm thấy bảng panel nào, dựng lại toàn bộ
                if not panel_msg:
                    await self.auto_setup_intake_channel(purge=True)
                    return

                # 3. Xóa tất cả các tin nhắn khác (tin nhắn người gửi, bot thừa, attachment...)
                def is_not_panel(m: discord.Message) -> bool:
                    return m.id != panel_msg.id

                try:
                    await channel.purge(limit=100, check=is_not_panel)
                except Exception as pe:
                    log.debug("Lỗi khi purge kênh nộp tài liệu: %s", pe)
                    # Quét dọn fallback nếu purge gặp lỗi (ví dụ tin nhắn > 14 ngày)
                    try:
                        async for m in channel.history(limit=20):
                            if m.id != panel_msg.id:
                                try:
                                    await m.delete()
                                except Exception:
                                    pass
                    except Exception as he:
                        log.debug("Lỗi khi xóa từng tin nhắn còn sót: %s", he)

                # 4. Debounce: chỉ cập nhật bảng panel nếu đã qua >= 3 giây kể từ lần cập nhật trước
                import time as _time
                now = _time.monotonic()
                if now - self._last_panel_update >= 3.0:
                    try:
                        new_embeds = await self.build_intake_panel_embeds()
                        view = DocumentIntakeControlView(self)
                        await panel_msg.edit(embeds=new_embeds, view=view)
                        self._last_panel_update = now
                    except Exception as ee:
                        log.debug("Lỗi cập nhật bảng panel nộp tài liệu: %s", ee)
                else:
                    # Lên lịch cập nhật sau 3 giây nếu chưa có pending
                    if not self._pending_panel_update:
                        self._pending_panel_update = True
                        async def _delayed_panel_update():
                            await asyncio.sleep(3.0)
                            self._pending_panel_update = False
                            self._last_panel_update = _time.monotonic()
                            try:
                                new_embeds = await self.build_intake_panel_embeds()
                                view = DocumentIntakeControlView(self)
                                await panel_msg.edit(embeds=new_embeds, view=view)
                            except Exception:
                                pass
                        asyncio.create_task(_delayed_panel_update())

            except Exception as e:
                log.warning("Lỗi trong quá trình dọn dẹp kênh nộp tài liệu: %s", e)

    async def auto_setup_intake_channel(self, purge: bool = True) -> None:
        """Tự động kiểm tra, dọn dẹp và đăng bảng điều khiển tại kênh DOC_INTAKE_CHANNEL_ID."""
        await self.bot.wait_until_ready()
        async with self._setup_lock:
            intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
            channel = self.bot.get_channel(intake_channel_id)
            if not channel and hasattr(self.bot, "fetch_channel"):
                try:
                    channel = await self.bot.fetch_channel(intake_channel_id)
                except Exception:
                    pass

            if not channel or not isinstance(channel, discord.TextChannel):
                log.warning("Không tìm thấy kênh nộp tài liệu DOC_INTAKE_CHANNEL_ID: %s", intake_channel_id)
                return

            try:
                if purge:
                    try:
                        await channel.purge(limit=100)
                    except Exception as pe:
                        log.debug("Bỏ qua lỗi purge nhanh: %s", pe)
                    try:
                        async for m in channel.history(limit=50):
                            try:
                                await m.delete()
                            except Exception:
                                pass
                    except Exception:
                        pass

                embeds = await self.build_intake_panel_embeds()
                view = DocumentIntakeControlView(self)
                msg = await channel.send(embeds=embeds, view=view)
                self._panel_message_id = msg.id
                log.info("✅ Đã dọn sạch kênh và khởi tạo bảng hướng dẫn nộp tài liệu mới tại #%s (%s)", channel.name, channel.id)
            except Exception as e:
                log.warning("Lỗi khi tự động thiết lập kênh nộp tài liệu: %s", e)

    @app_commands.command(
        name="setup_intake",
        description="[Admin] Làm mới giao diện và bảng hướng dẫn tại Kênh Nộp Tài Liệu",
    )
    async def setup_intake_cmd(self, interaction: discord.Interaction) -> None:
        """Lệnh quản trị làm mới bảng hướng dẫn kênh nộp tài liệu."""
        if not interaction.user.guild_permissions.administrator and interaction.user.id != getattr(settings, "OWNER_ID", 0):
            await interaction.response.send_message("❌ Bạn không có quyền thực hiện lệnh này.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            await self.auto_setup_intake_channel(purge=True)
            intake_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
            await interaction.followup.send(f"✅ Đã làm mới thành công bảng hướng dẫn nộp tài liệu tại <#{intake_id}>!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi khi thiết lập kênh: `{e}`", ephemeral=True)

    async def process_and_route(
        self,
        guild: discord.Guild,
        author: discord.User | discord.Member,
        file_path_or_bytes: str | bytes,
        file_name: str | None = None,
        note: str | None = None,
    ) -> tuple[InspectionReport, SubmissionRoutingResult, Optional[discord.Message]]:
        """Xử lý thẩm định và tự động chuyển tiếp sang Thư mục phân loại theo 4 chiều."""
        from cpp_core.bridge import fast_sha256

        category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)
        intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)

        category = guild.get_channel(category_id)
        if not category and hasattr(self.bot, "fetch_channel"):
            try:
                category = await self.bot.fetch_channel(category_id)
            except Exception:
                pass

        category_channel_names = (
            [
                ch.name for ch in category.channels
                if isinstance(ch, discord.TextChannel)
                and ch.id != intake_channel_id
                and not any(x in ch.name.lower() for x in ["nop-tai-lieu", "nộp-tài-liệu", "tra-cuu", "tra-cứu", "verify-link", "bot-log"])
            ]
            if category and isinstance(category, discord.CategoryChannel)
            else None
        )

        author_mention = author.mention if hasattr(author, "mention") else f"<@{getattr(author, 'id', 0)}>"
        author_name = getattr(author, "display_name", getattr(author, "name", str(author)))

        # === CHỐNG NỘP TRÙNG LẶP (SHA-256 Duplicate Detection) ===
        file_hash = None
        if isinstance(file_path_or_bytes, bytes) and len(file_path_or_bytes) > 0:
            try:
                from cpp_core.bridge import fast_sha256
                file_hash = fast_sha256(file_path_or_bytes)
            except Exception:
                import hashlib
                file_hash = hashlib.sha256(file_path_or_bytes).hexdigest()
        elif isinstance(file_path_or_bytes, str) and os.path.exists(file_path_or_bytes):
            try:
                with open(file_path_or_bytes, "rb") as f:
                    raw = f.read()
                from cpp_core.bridge import fast_sha256
                file_hash = fast_sha256(raw)
            except Exception:
                import hashlib
                with open(file_path_or_bytes, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()

        if file_hash and hasattr(self.bot, "db"):
            try:
                existing = await self.bot.db.fetchone(
                    "SELECT jump_url, author_name, timestamp FROM documents_archive WHERE file_hash = ?",
                    file_hash,
                )
                if existing:
                    dup_jump = existing[0] or "N/A"
                    dup_author = existing[1] or "N/A"
                    dup_time = existing[2] or "N/A"
                    from DocInspector.models import SubmissionRoutingResult, InspectionReport as IR_Model
                    dup_routing = SubmissionRoutingResult(
                        is_blocked_or_unverifiable=True,
                        submission_reply_message=(
                            f"🔁 **TÀI LIỆU TRÙNG LẶP!**\n"
                            f"Tệp `{file_name or 'này'}` đã được nộp trước đó bởi **{dup_author}** vào `{dup_time}`.\n"
                            f"🔗 **Bài đăng gốc:** {dup_jump}\n\n"
                            f"*Hệ thống đã phát hiện trùng lặp bằng SHA-256 hash: `{file_hash[:16]}...`*"
                        ),
                    )
                    # Return a minimal dummy report for duplicates
                    from DocInspector.models import DocumentCategory, ExamType, Subject, GradeLevel
                    dup_report = IR_Model(
                        file_name=file_name or "duplicate",
                        file_path="duplicate",
                        file_size_bytes=len(file_path_or_bytes) if isinstance(file_path_or_bytes, bytes) else 0,
                        total_execution_time_ms=0.0,
                        document_category=DocumentCategory.GENERAL_DOCUMENT,
                        exam_type=ExamType.NOT_AN_EXAM,
                        detected_subject=Subject.GENERAL,
                        detected_language="DUPLICATE",
                        confidence_score=1.0,
                        grade_level=GradeLevel.UNKNOWN,
                        grade_level_label_vi="Trùng lặp",
                        is_spoofed_filename=False,
                        spoof_details=None,
                        human_summary=f"Tài liệu trùng lặp (SHA-256: {file_hash[:16]}...)",
                    )
                    return dup_report, dup_routing, None
            except Exception as e:
                log.debug("Lỗi kiểm tra trùng lặp SHA-256: %s", e)

        # Quét KỸ (deep=True): chấp nhận lâu hơn để chính xác tối đa
        report, routing = await asyncio.to_thread(
            BotInspectorAdapter.inspect_and_route_submission,
            file_path_or_bytes=file_path_or_bytes,
            category_channels=category_channel_names,
            category_id=category_id,
            submission_channel_id=intake_channel_id,
            file_name=file_name,
            author_mention=author_mention,
            author_name=author_name,
            deep=True,
        )

        posted_msg = None
        if not routing.is_blocked_or_unverifiable and category and isinstance(category, discord.CategoryChannel):
            target_ch = discord.utils.get(category.channels, name=routing.target_channel_name)
            if not target_ch or not isinstance(target_ch, discord.TextChannel):
                target_ch = await self._get_or_create_subject_channel(
                    guild=guild,
                    category_id=category_id,
                    channel_slug=routing.target_channel_name,
                    icon="📚",
                    subject_name=report.detected_subject.value if hasattr(report.detected_subject, "value") else str(report.detected_subject),
                )

            if target_ch and isinstance(target_ch, discord.TextChannel):
                post_content = routing.forwarded_post_message
                if author_mention not in post_content:
                    post_content += f"\n👤 **Người gửi đóng góp:** {author_mention} (`{author_name}`)"
                if note:
                    post_content += f"\n📝 **Ghi chú của người gửi:** {note}"

                if hasattr(report, 'academic_year') and report.academic_year:
                    post_content += f"\n📅 **Năm học:** `{report.academic_year}`"
                if hasattr(report, 'school_or_department') and report.school_or_department:
                    post_content += f"\n🏫 **Trường / Sở GD:** `{report.school_or_department}`"

                try:
                    if isinstance(file_path_or_bytes, bytes) and file_name:
                        file_forward = discord.File(io.BytesIO(file_path_or_bytes), filename=file_name)
                        posted_msg = await target_ch.send(content=post_content, file=file_forward)
                    elif isinstance(file_path_or_bytes, str) and file_path_or_bytes.startswith(("http://", "https://")):
                        post_content += f"\n🔗 **Link gốc:** {file_path_or_bytes}"
                        posted_msg = await target_ch.send(content=post_content)
                    elif isinstance(file_path_or_bytes, str) and os.path.exists(file_path_or_bytes):
                        file_forward = discord.File(file_path_or_bytes, filename=file_name or os.path.basename(file_path_or_bytes))
                        posted_msg = await target_ch.send(content=post_content, file=file_forward)
                except discord.HTTPException as he:
                    if getattr(he, "status", 0) == 413 or getattr(he, "code", 0) == 40005:
                        post_content += f"\n⚠️ *(Tệp '{file_name}' vượt quá dung lượng upload tối đa của Discord. Metadata và thẩm định đã được lưu an toàn.)*"
                        posted_msg = await target_ch.send(content=post_content)
                    else:
                        raise

                if posted_msg:
                    raw_text_for_db = None
                    if hasattr(report, 'pass1') and hasattr(report.pass1, 'raw_text'):
                        raw_text_for_db = report.pass1.raw_text[:50000] if report.pass1.raw_text else None
                    await self.record_inspection_report(report, routing, author, target_ch, posted_msg, file_hash=file_hash, raw_text=raw_text_for_db)

        return report, routing, posted_msg

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Tự động phát hiện và xử lý đề thi gửi vào kênh nộp đề hoặc các kênh thuộc Category."""
        if not message.guild or message.author == self.bot.user:
            return

        intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
        category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)

        # TRƯỜNG HỢP A: Kênh tiếp nhận tài liệu (1535278288828633138)
        if message.channel.id == intake_channel_id:
            # Nếu bot khác hoặc webhook nhắn vào kênh nộp tài liệu, xóa ngay lập tức
            if message.author.bot:
                try:
                    await message.delete()
                except Exception:
                    pass
                return

            has_attachment = len(message.attachments) > 0
            url_match = re.search(
                r"https?://[^\s]+|(?:(?:drive|docs)\.google\.com|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/[^\s]*",
                message.content,
            )

            # 1. Tin nhắn chat thông thường (không có file đính kèm, không chứa liên kết)
            if not has_attachment and not url_match:
                try:
                    await message.delete()
                except Exception:
                    pass

                dm_sent = True
                try:
                    await message.author.send(
                        "⚠️ **Kênh <#1535278288828633138> chỉ dành riêng để nộp tài liệu học tập & đề thi.**\n"
                        "Vui lòng gửi kèm tệp (`.pdf`, `.docx`, `.png`, `.jpg`...) hoặc đường dẫn Google Drive / web để hệ thống tự động phân loại!"
                    )
                except Exception:
                    dm_sent = False

                if not dm_sent:
                    try:
                        await message.channel.send(
                            f"⚠️ {message.author.mention}, vui lòng gửi tệp đính kèm (`.pdf`, `.docx`, `.png`, `.jpg`...) hoặc đường dẫn tài liệu học tập để hệ thống tiếp nhận và phân loại.",
                            delete_after=6.0,
                        )
                    except Exception:
                        pass

                # Dọn dẹp toàn bộ tin nhắn thừa trong kênh ngầm
                asyncio.create_task(self.clean_intake_channel(message.channel))
                return

            # 2. Xử lý khi có tệp đính kèm
            if has_attachment:
                # Đọc trước toàn bộ dữ liệu tệp đính kèm trước khi xóa tin nhắn
                loaded_attachments: list[tuple[str, bytes]] = []
                for att in message.attachments:
                    try:
                        data = await att.read()
                        loaded_attachments.append((att.filename, data))
                    except Exception as e:
                        log.warning("Không thể đọc attachment %s: %s", att.filename, e)

                # Xóa ngay tin nhắn nộp của người dùng để kênh luôn sạch sẽ
                try:
                    await message.delete()
                except Exception:
                    pass

                failed_notifications: list[tuple[str, JumpButtonView | None]] = []
                for file_name, file_bytes in loaded_attachments:
                    try:
                        report, routing, posted_msg = await self.process_and_route(
                            guild=message.guild,
                            author=message.author,
                            file_path_or_bytes=file_bytes,
                            file_name=file_name,
                        )

                        reply_text = routing.submission_reply_message
                        # Thêm thông tin năm học và trường nếu có
                        extra_info = ""
                        if hasattr(report, 'academic_year') and report.academic_year:
                            extra_info += f"\n📅 **Năm học:** `{report.academic_year}`"
                        if hasattr(report, 'school_or_department') and report.school_or_department:
                            extra_info += f"\n🏫 **Trường / Sở GD:** `{report.school_or_department}`"
                        reply_text += extra_info

                        view = JumpButtonView(posted_msg.jump_url) if posted_msg else None

                        try:
                            await message.author.send(reply_text, view=view)
                        except Exception:
                            failed_notifications.append((reply_text, view))

                        # Post thông báo trùng lặp vào kênh intake rồi xóa sau 10 giây
                        if 'TRÙNG LẶP' in (routing.submission_reply_message or ''):
                            try:
                                dup_embed = discord.Embed(
                                    title="🔁 Tài Liệu Trùng Lặp",
                                    description=(
                                        f"Tệp của **{message.author.display_name}** đã được nộp trước đó.\n"
                                        f"Chi tiết đã được gửi riêng tư.\n"
                                        f"*Tin nhắn này sẽ tự xóa sau 10 giây.*"
                                    ),
                                    color=0xE67E22,
                                )
                                dup_public_msg = await message.channel.send(embed=dup_embed)
                                await asyncio.sleep(10)
                                try:
                                    await dup_public_msg.delete()
                                except Exception:
                                    pass
                            except Exception:
                                pass
                    except Exception as e:
                        log.exception("Lỗi khi xử lý file nộp %s: %s", file_name, e)
                        err_text = f"❌ **Lỗi khi xử lý tệp '{file_name}':** `{e}`"
                        try:
                            await message.author.send(err_text)
                        except Exception:
                            failed_notifications.append((err_text, None))

                # Nếu người dùng tắt DM máy chủ, hiển thị thông báo tạm thời rồi tự xóa sau 25s
                for text, view in failed_notifications:
                    try:
                        await message.channel.send(
                            f"{message.author.mention}\n{text}",
                            view=view,
                            delete_after=25.0,
                        )
                    except Exception:
                        pass

                # Dọn dẹp tất cả tin nhắn thừa trong kênh ngầm (không làm lag người dùng)
                asyncio.create_task(self.clean_intake_channel(message.channel))
                return

            # 3. Xử lý khi gửi link URL / Google Drive trực tiếp trong chat
            if url_match:
                raw_url = AntivirusScanner.normalize_url(url_match.group(0))
                try:
                    await message.delete()
                except Exception:
                    pass

                from services.gdrive_importer import is_valid_gdrive_url_or_id
                if is_valid_gdrive_url_or_id(raw_url):
                    try:
                        success, msg, embed, posted_msg = await self.handle_gdrive_submission(
                            guild=message.guild,
                            author=message.author,
                            gdrive_url=raw_url,
                        )
                        view = JumpButtonView(posted_msg.jump_url) if posted_msg else None
                        try:
                            if embed:
                                await message.author.send(embed=embed, view=view)
                            else:
                                await message.author.send(msg, view=view)
                        except Exception:
                            try:
                                if embed:
                                    await message.channel.send(f"{message.author.mention}", embed=embed, view=view, delete_after=25.0)
                                else:
                                    await message.channel.send(f"{message.author.mention}\n{msg}", view=view, delete_after=25.0)
                            except Exception:
                                pass
                    except Exception as ge:
                        log.exception("Lỗi khi xử lý link Google Drive trong chat: %s", ge)
                        try:
                            await message.author.send(f"❌ Lỗi kiểm định link Google Drive: `{ge}`")
                        except Exception:
                            pass

                    asyncio.create_task(self.clean_intake_channel(message.channel))
                    return

                failed_url_notifications: list[tuple[str, JumpButtonView | None]] = []
                try:
                    report, routing, posted_msg = await self.process_and_route(
                        guild=message.guild,
                        author=message.author,
                        file_path_or_bytes=raw_url,
                    )

                    reply_text = routing.submission_reply_message
                    # Thêm thông tin năm học và trường nếu có
                    extra_info = ""
                    if hasattr(report, 'academic_year') and report.academic_year:
                        extra_info += f"\n📅 **Năm học:** `{report.academic_year}`"
                    if hasattr(report, 'school_or_department') and report.school_or_department:
                        extra_info += f"\n🏫 **Trường / Sở GD:** `{report.school_or_department}`"
                    reply_text += extra_info

                    view = JumpButtonView(posted_msg.jump_url) if posted_msg else None

                    try:
                        await message.author.send(reply_text, view=view)
                    except Exception:
                        failed_url_notifications.append((reply_text, view))

                    # Post thông báo trùng lặp vào kênh intake rồi xóa sau 10 giây
                    if 'TRÙNG LẶP' in (routing.submission_reply_message or ''):
                        try:
                            dup_embed = discord.Embed(
                                title="🔁 Tài Liệu Trùng Lặp",
                                description=(
                                    f"Tệp của **{message.author.display_name}** đã được nộp trước đó.\n"
                                    f"Chi tiết đã được gửi riêng tư.\n"
                                    f"*Tin nhắn này sẽ tự xóa sau 10 giây.*"
                                ),
                                color=0xE67E22,
                            )
                            dup_public_msg = await message.channel.send(embed=dup_embed)
                            await asyncio.sleep(10)
                            try:
                                await dup_public_msg.delete()
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception as e:
                    log.exception("Lỗi khi xử lý link nộp: %s", e)
                    err_text = f"❌ **Lỗi khi xử lý liên kết '{raw_url}':** `{e}`"
                    try:
                        await message.author.send(err_text)
                    except Exception:
                        failed_url_notifications.append((err_text, None))

                # Nếu người dùng tắt DM máy chủ, hiển thị thông báo tạm thời rồi tự xóa sau 25s
                for text, view in failed_url_notifications:
                    try:
                        await message.channel.send(
                            f"{message.author.mention}\n{text}",
                            view=view,
                            delete_after=25.0,
                        )
                    except Exception:
                        pass

                # Dọn dẹp tất cả tin nhắn thừa trong kênh ngầm (không làm lag người dùng)
                asyncio.create_task(self.clean_intake_channel(message.channel))
                return

        # TRƯỜNG HỢP B: Tin nhắn gửi trong các kênh thuộc Thư mục phân loại (1534147951797080174)
        channel_category_id = getattr(message.channel, "category_id", None)
        if channel_category_id == category_id and (message.attachments or "http" in message.content):
            # 1. Tự động lập chỉ mục đề thi (cả đề do Bot gửi và do Admin/User gửi trực tiếp)
            try:
                cnt = await self.index_message_document(message)
                if cnt > 0:
                    try:
                        await message.add_reaction("📌")
                    except Exception:
                        pass
            except Exception as ie:
                log.debug("Lỗi khi tự động lập chỉ mục tin nhắn trong Category: %s", ie)

            # 2. Nếu là người dùng gửi trực tiếp (Admin), kiểm tra thêm Channel Compliance
            if not message.author.bot:
                try:
                    target_data = None
                    file_name = None
                    if message.attachments:
                        att = message.attachments[0]
                        file_name = att.filename
                        target_data = await att.read()
                    else:
                        url_m = re.search(r"https?://[^\s]+", message.content)
                        if url_m:
                            target_data = url_m.group(0)

                    if target_data:
                        rep = await asyncio.to_thread(
                            BotInspectorAdapter.inspect_in_channel,
                            file_path_or_bytes=target_data,
                            channel_name=message.channel.name,
                            category_id=category_id,
                            file_name=file_name,
                        )
                        compliance = rep.channel_compliance
                        if compliance and not compliance.is_compliant:
                            warn_msg = (
                                f"⚠️ {message.author.mention}, tài liệu bạn vừa đăng có thể **sai chuyên mục kênh**!\n"
                                f"{compliance.warning_message}\n"
                                f"💡 *Khuyên dùng:* Hãy gửi tài liệu tại <#{intake_channel_id}> để hệ thống tự động phân loại chuẩn xác nhất!"
                            )
                            await message.channel.send(warn_msg, delete_after=15.0)
                except Exception as e:
                    log.debug("Lỗi khi kiểm tra compliance: %s", e)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """
        Tự động đồng bộ khi Admin/Staff xóa tin nhắn đề thi (Drama / Sai phạm / Yêu cầu gỡ bỏ).
        Xóa ngay lập tức khỏi bảng documents_archive và xóa cache tra cứu.
        """
        if not hasattr(self.bot, "db"):
            return

        try:
            row = await self.bot.db.fetchone(
                "SELECT id, subject, title, file_name, author_name FROM documents_archive WHERE message_id = ?",
                payload.message_id,
            )
            if row:
                doc_id, subj, title, fname, author = row
                await self.bot.db.execute("DELETE FROM documents_archive WHERE message_id = ?", payload.message_id)
                log.info(
                    "🗑️ [Auto-Sync Delete] Đã xóa đề thi '%s' (ID: %d, Môn: %s, Người nộp: %s) khỏi kho lưu trữ do tin nhắn đã bị xóa trên Discord.",
                    title or fname, doc_id, subj, author
                )

                # Xóa cache tra cứu trong cog DocumentSearch
                search_cog = self.bot.get_cog("DocumentSearch")
                if search_cog and hasattr(search_cog, "_search_cache"):
                    search_cog._search_cache.clear()

                # Cập nhật số liệu hiển thị tại bảng panel
                guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
                if guild:
                    intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
                    ch = guild.get_channel(intake_channel_id)
                    if ch and isinstance(ch, discord.TextChannel):
                        await self.clean_intake_channel(ch)
                    search_ch_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1553678782101979186)
                    sch = guild.get_channel(search_ch_id)
                    if sch and isinstance(sch, discord.TextChannel) and search_cog and hasattr(search_cog, "clean_search_channel"):
                        await search_cog.clean_search_channel(sch)
        except Exception as e:
            log.warning("Lỗi xử lý on_raw_message_delete trong doc_intake: %s", e)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        """Tự động đồng bộ khi Admin/Staff xóa hàng loạt tin nhắn (Bulk delete / Purge)."""
        if not hasattr(self.bot, "db") or not payload.message_ids:
            return

        try:
            placeholders = ",".join("?" for _ in payload.message_ids)
            rows = await self.bot.db.fetchall(
                f"SELECT id, title FROM documents_archive WHERE message_id IN ({placeholders})",
                *payload.message_ids,
            )
            if rows:
                await self.bot.db.execute(
                    f"DELETE FROM documents_archive WHERE message_id IN ({placeholders})",
                    *payload.message_ids,
                )
                log.info("🗑️ [Auto-Sync Bulk Delete] Đã xóa %d tài liệu khỏi kho lưu trữ.", len(rows))

                search_cog = self.bot.get_cog("DocumentSearch")
                if search_cog and hasattr(search_cog, "_search_cache"):
                    search_cog._search_cache.clear()

                guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
                if guild:
                    intake_channel_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
                    ch = guild.get_channel(intake_channel_id)
                    if ch and isinstance(ch, discord.TextChannel):
                        await self.clean_intake_channel(ch)
                    search_ch_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1553678782101979186)
                    sch = guild.get_channel(search_ch_id)
                    if sch and isinstance(sch, discord.TextChannel) and search_cog and hasattr(search_cog, "clean_search_channel"):
                        await search_cog.clean_search_channel(sch)
        except Exception as e:
            log.warning("Lỗi xử lý on_raw_bulk_message_delete: %s", e)

    async def dispatch_analysis_result_interaction(
        self,
        interaction: discord.Interaction,
        res: DocumentAnalysisResult,
    ) -> None:
        """Xử lý kết quả từ Modal hoặc Slash command với phản hồi Ephemeral."""
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Lệnh chỉ khả dụng trong Server Discord.", ephemeral=True)
            return

        category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)

        if not res.is_safe:
            desc = (
                f"⚠️ **Lý do từ chối:** {res.error_message or res.summary}\n\n"
                f"🛡️ *Hệ thống tự động phát hiện và chặn mọi liên kết/tệp độc hại để bảo vệ server.*"
            )
            embed = discord.Embed(
                title=f"{res.icon} CẢNH BÁO: TÀI LIỆU BỊ TỪ CHỐI BẢO MẬT",
                description=desc,
                color=0xE74C3C,
            )
            DocumentService.cleanup_file(res.file_path)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        target_channel = await self._get_or_create_subject_channel(
            guild=guild,
            category_id=category_id,
            channel_slug=res.channel_name,
            icon=res.icon,
            subject_name=res.subject,
        )
        if not target_channel:
            target_channel = interaction.channel

        archive_embed = discord.Embed(
            title=f"{res.icon} {res.title}",
            description=f"📄 **Tóm tắt nội dung:**\n> {res.summary}",
            color=res.color,
        )
        archive_embed.add_field(name="📚 Môn Học", value=f"**{res.icon} {res.subject}**", inline=True)
        archive_embed.add_field(name="📊 Cấp Độ Dự Kiến", value=f"`{res.estimated_level}`", inline=True)
        archive_embed.add_field(name="📑 Cấu Trúc Đề", value=f"`{res.question_count} câu hỏi` • `{res.page_count} trang`", inline=True)
        archive_embed.add_field(name="👤 Người Đóng Góp", value=interaction.user.mention, inline=True)
        archive_embed.add_field(
            name="💾 Dung Lượng Tệp",
            value=f"`{format_bytes_to_human(res.file_size_mb * 1024 * 1024)}` ({res.file_type})",
            inline=True,
        )
        if res.original_url:
            archive_embed.add_field(name="🔗 Liên Kết Gốc", value=f"[Nhấn vào đây để xem]({res.original_url})", inline=True)

        archive_embed.set_footer(text="Hệ Thống Phân Loại Đề Thi Tự Động • HyperHub CP Arena")

        discord_file = None
        if res.file_path and os.path.exists(res.file_path):
            file_name = os.path.basename(res.file_path)
            discord_file = discord.File(res.file_path, filename=file_name)

        if discord_file:
            posted_msg = await target_channel.send(embed=archive_embed, file=discord_file)
        else:
            posted_msg = await target_channel.send(embed=archive_embed)

        await self.record_archived_document(res, interaction.user, target_channel, posted_msg)
        DocumentService.cleanup_file(res.file_path)

        success_desc = (
            f"Cảm ơn {interaction.user.mention} đã đóng góp tài liệu cho kho đề chung!\n\n"
            f"• 📚 **Môn thi:** **{res.icon} {res.subject}**\n"
            f"• 📊 **Cấp độ:** `{res.estimated_level}`\n"
            f"• 💾 **Dung lượng:** `{format_bytes_to_human(res.file_size_mb * 1024 * 1024)}`\n"
            f"• 📂 **Đã lưu trữ tại:** {target_channel.mention}\n"
            f"• 🔗 **Xem trực tiếp bài đăng:** [Nhấn vào đây]({posted_msg.jump_url})\n\n"
            f"✨ *Tài liệu đã được quét an toàn và lưu trữ thành công trong thư mục!*"
        )
        success_embed = discord.Embed(
            title="🎉 NỘP & PHÂN LOẠI TÀI LIỆU THÀNH CÔNG!",
            description=success_desc,
            color=0x2ECC71,
        )
        view = JumpButtonView(posted_msg.jump_url)
        await interaction.followup.send(embed=success_embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    cog = DocumentIntakeCog(bot)
    await bot.add_cog(cog)
    bot.add_view(DocumentIntakeControlView(cog))
