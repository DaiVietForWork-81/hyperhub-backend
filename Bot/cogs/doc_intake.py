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
    """View chứa nút bấm chuyển tiếp nhanh tới Kho Đề Web (không tiết lộ kênh lưu trữ nội bộ)."""

    def __init__(self, jump_url: str | None = None):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="🌐 Xem Trong Kho Đề Web",
                style=discord.ButtonStyle.link,
                url="https://orbit-psi-black.vercel.app/#vault",
                emoji="📚",
            )
        )


class FeedbackModal(discord.ui.Modal, title="Góp Ý Chỉnh Sửa Phân Loại Đề"):
    corrected_subj = discord.ui.TextInput(
        label="Môn học / Phân loại chính xác",
        placeholder="Ví dụ: TOÁN HỌC, VẬT LÝ, HÓA HỌC, TIẾNG ANH, TIN HỌC...",
        max_length=50,
        required=True,
    )
    notes = discord.ui.TextInput(
        label="Ghi chú chi tiết (Khối lớp / Loại đề)",
        placeholder="Ví dụ: Đề thi thử THPT môn Vật lí lớp 12...",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, file_name: str, prev_subject: str):
        super().__init__()
        self.file_name = file_name
        self.prev_subject = prev_subject

    async def on_submit(self, interaction: discord.Interaction):
        try:
            from DocInspector.active_learning import ActiveLearningEngine
            ActiveLearningEngine.record_feedback(
                file_name=self.file_name,
                corrected_subject=self.corrected_subj.value.strip(),
                previous_subject=self.prev_subject,
                user_name=interaction.user.display_name,
                notes=self.notes.value.strip() if self.notes.value else "",
                auto_retrain=True,
            )
            await interaction.response.send_message(
                f"✅ **ĐÃ GHI NHẬN GÓP Ý PHÂN LOẠI!**\n"
                f"Cảm ơn bạn đã xác nhận thông tin phân loại môn **{self.corrected_subj.value.upper()}**.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Lỗi ghi nhận: `{e}`", ephemeral=True)


class DocInspectorAuditView(discord.ui.View):
    """View cung cấp nút bấm Góp ý phân loại tài liệu."""

    def __init__(self, report: Any):
        super().__init__(timeout=None)
        self.report = report

    @discord.ui.button(label="🔄 Góp Ý Phân Loại", style=discord.ButtonStyle.secondary, custom_id="doc_feedback_btn")
    async def open_feedback_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        fn = getattr(self.report, "file_name", "document")
        subj = getattr(self.report, "detected_subject", None)
        prev_s = subj.name if hasattr(subj, "name") else str(subj)
        modal = FeedbackModal(file_name=fn, prev_subject=prev_s)
        await interaction.response.send_modal(modal)


def format_rich_exam_metadata(report: Any) -> str:
    """Định dạng siêu dữ liệu đề thi chi tiết qua 4 bước kiểm tra tránh hiểu lầm."""
    extra = ""
    if hasattr(report, 'detailed_exam_track') and report.detailed_exam_track:
        extra += f"\n📌 **Loại đề:** `{report.detailed_exam_track}`"
    if hasattr(report, 'grade_level_label_vi') and report.grade_level_label_vi:
        extra += f"\n🎓 **Khối lớp:** `{report.grade_level_label_vi}`"
    if hasattr(report, 'academic_year') and report.academic_year:
        extra += f"\n📅 **Năm học:** `{report.academic_year}`"
    if hasattr(report, 'school_or_department') and report.school_or_department:
        extra += f"\n🏫 **Trường / Sở GD:** `{report.school_or_department}`"

    meta = getattr(report, 'detailed_metadata', None)
    if meta:
        if getattr(meta, 'duration_minutes', None):
            extra += f"\n⏱️ **Thời gian làm bài:** `{meta.duration_minutes} phút`"
        if getattr(meta, 'exam_code', None):
            extra += f"\n🔢 **Mã đề:** `{meta.exam_code}`"
        if getattr(meta, 'exam_period', None):
            extra += f"\n📋 **Kỳ thi:** `{meta.exam_period}`"
        if getattr(meta, 'total_score', None):
            extra += f"\n🎯 **Thang điểm:** `{meta.total_score} điểm`"

        p1 = getattr(meta, 'moet_part1_count', 0)
        p2 = getattr(meta, 'moet_part2_count', 0)
        p3 = getattr(meta, 'moet_part3_count', 0)
        if p1 or p2 or p3:
            extra += f"\n📊 **Cấu trúc 2025:** `Phần I: {p1}c` | `Phần II: {p2}c` | `Phần III: {p3}c`"

        topic_dist = getattr(meta, 'topic_distribution', None)
        if topic_dist and isinstance(topic_dist, dict):
            top_topics = sorted(topic_dist.items(), key=lambda x: x[1], reverse=True)[:3]
            if top_topics:
                top_str = ", ".join(f"{k} ({v})" for k, v in top_topics)
                extra += f"\n🏷️ **Chuyên đề chính:** `{top_str}`"

    return extra


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
            reply_text = (routing.submission_reply_message or "") + format_rich_exam_metadata(report)

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
    """Bảng điều khiển tương tác thường trực tại kênh nộp tài liệu (chuyển tiếp lên Web Portal)."""

    def __init__(self, cog: DocumentIntakeCog | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        # Nút chuyển tiếp trực tiếp sang Web Portal để nộp tài liệu
        self.add_item(
            discord.ui.Button(
                label="🌐 Mở Web Đóng Góp Đề Thi",
                url="https://orbit-psi-black.vercel.app/#vault",
                style=discord.ButtonStyle.link,
                emoji="📤",
                row=0,
            )
        )
        self.add_item(
            discord.ui.Button(
                label="🚀 Mở Bảng Điều Khiển (Hub)",
                url="https://orbit-psi-black.vercel.app/hub",
                style=discord.ButtonStyle.link,
                emoji="✨",
                row=0,
            )
        )

    @discord.ui.button(
        label="📊 Thống Kê Kho Đề & Dung Lượng",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_doc_intake_stats",
        emoji="💾",
        row=1,
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
        self._sync_turso_task: Optional[asyncio.Task] = None

    async def cog_load(self) -> None:
        """Khởi động task nền tự động đồng bộ đề thi đang chờ từ Turso Cloud."""
        self._sync_turso_task = asyncio.create_task(self._turso_pending_sync_loop())

    async def cog_unload(self) -> None:
        if self._sync_turso_task and not self._sync_turso_task.done():
            self._sync_turso_task.cancel()

    async def _turso_pending_sync_loop(self) -> None:
        """Chu kỳ 45 giây: Đồng bộ đề thi từ Turso Cloud + Gửi toàn bộ file đã list về Cloud Model (550B) để đọc và phân tích sâu."""
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)  # Chờ 5s cho bot hoàn tất kết nối Discord
        while not self.bot.is_closed():
            try:
                await self.sync_pending_turso_documents()
            except Exception as e:
                log.debug("Lỗi trong vòng lặp sync Turso: %s", e)
            try:
                await self.run_45s_batch_cloud_analysis()
            except Exception as e:
                log.debug("Lỗi trong vòng lặp phân tích lô 45 giây: %s", e)
            await asyncio.sleep(45)  # Cứ 45 giây gom và phân tích toàn bộ file đã list

    async def run_45s_batch_cloud_analysis(self) -> int:
        """
        Cứ 45 giây: Tổng hợp tất cả các file mà Bot đã list/thu thập được (trong hàng đợi 45s
        hoặc trong documents_archive chưa qua bước thẩm định sâu) để gửi về Model 550B đọc & phân loại.
        """
        from DocInspector.cloud_verifier import CloudExamVerifier
        from database.turso_client import turso_db

        # 1. Rà soát các file mới được list trong SQLite local chưa có nhãn CLOUD_DEEP_VERIFIED
        if hasattr(self.bot, "db"):
            try:
                unverified_rows = await self.bot.db.fetchall(
                    """
                    SELECT id, file_name, COALESCE(raw_text, ''), subject, estimated_level
                    FROM documents_archive
                    WHERE (quorum_status IS NULL OR quorum_status NOT IN ('CLOUD_DEEP_VERIFIED', 'UNANIMOUS_3_3'))
                    ORDER BY id DESC
                    LIMIT 12
                    """
                )
                for r_id, r_fname, r_text, r_subj, r_lvl in unverified_rows:
                    CloudExamVerifier.enqueue_for_45s_batch(
                        doc_id=r_id,
                        file_name=r_fname or f"doc_{r_id}.pdf",
                        raw_text=r_text or f"Tài liệu: {r_fname}",
                        metadata={"source": "sqlite", "old_subject": r_subj, "old_level": r_lvl},
                    )
            except Exception as e:
                log.debug("Bỏ qua quét SQLite trong chu kỳ 45s: %s", e)

        # 2. Rà soát các file mới trên Turso Cloud
        if turso_db.is_configured:
            try:
                turso_rows = await turso_db.fetchall(
                    """
                    SELECT id, file_name, COALESCE(raw_text, '') AS raw_text, subject, estimated_level
                    FROM documents_archive
                    WHERE (verdict IS NULL OR verdict != 'CLOUD_DEEP_VERIFIED')
                    ORDER BY id DESC
                    LIMIT 12
                    """
                )
                for tr in turso_rows:
                    t_id = tr.get("id")
                    t_fname = tr.get("file_name") or f"doc_{t_id}.pdf"
                    t_text = tr.get("raw_text") or f"Tài liệu: {t_fname}"
                    if t_id:
                        CloudExamVerifier.enqueue_for_45s_batch(
                            doc_id=t_id,
                            file_name=t_fname,
                            raw_text=t_text,
                            metadata={"source": "turso"},
                        )
            except Exception as e:
                log.debug("Bỏ qua quét Turso trong chu kỳ 45s: %s", e)

        # 3. Đẩy toàn bộ lô đã gom trong 45s qua lên Model 550B (timeout < 60s/file)
        completed = await asyncio.to_thread(CloudExamVerifier.flush_45s_batch, 16)
        if not completed:
            return 0

        updated_count = 0
        for item in completed:
            doc_id = item.get("doc_id")
            v = item.get("verified") or {}
            new_subj = str(v.get("subject") or "").upper()
            new_grade = str(v.get("grade_level") or "").strip()
            new_detailed = str(v.get("detailed_exam_track") or "").strip()
            new_track = str(v.get("exam_track") or "").upper()
            new_school = v.get("school_or_department")
            new_year = v.get("academic_year")

            est_level = new_grade
            if new_detailed and new_detailed not in est_level:
                est_level = f"{new_grade} ({new_detailed})" if new_grade else new_detailed

            subj_to_set = new_subj if (new_subj and new_subj != "GENERAL") else ""

            if isinstance(doc_id, int) or (isinstance(doc_id, str) and doc_id.isdigit()):
                num_id = int(doc_id)
                if hasattr(self.bot, "db"):
                    try:
                        await self.bot.db.execute(
                            """
                            UPDATE documents_archive
                            SET subject = COALESCE(NULLIF(?, ''), subject),
                                estimated_level = COALESCE(NULLIF(?, ''), estimated_level),
                                exam_track = COALESCE(NULLIF(?, ''), exam_track),
                                school_or_department = COALESCE(NULLIF(?, ''), school_or_department),
                                academic_year = COALESCE(NULLIF(?, ''), academic_year),
                                quorum_status = 'CLOUD_DEEP_VERIFIED',
                                verdict = 'CLOUD_DEEP_VERIFIED'
                            WHERE id = ?
                            """,
                            subj_to_set,
                            est_level,
                            new_track,
                            new_school if (new_school and str(new_school).lower() != "null") else "",
                            new_year if (new_year and str(new_year).lower() != "null") else "",
                            num_id,
                        )
                    except Exception:
                        pass

                if turso_db.is_configured:
                    try:
                        await turso_db.execute(
                            """
                            UPDATE documents_archive
                            SET subject = COALESCE(NULLIF(?, ''), subject),
                                estimated_level = COALESCE(NULLIF(?, ''), estimated_level),
                                exam_track = COALESCE(NULLIF(?, ''), exam_track),
                                school_or_department = COALESCE(NULLIF(?, ''), school_or_department),
                                academic_year = COALESCE(NULLIF(?, ''), academic_year),
                                verdict = 'CLOUD_DEEP_VERIFIED'
                            WHERE id = ?
                            """,
                            subj_to_set,
                            est_level,
                            new_track,
                            new_school if (new_school and str(new_school).lower() != "null") else "",
                            new_year if (new_year and str(new_year).lower() != "null") else "",
                            num_id,
                        )
                    except Exception:
                        pass
                updated_count += 1

        if updated_count > 0:
            log.info("✅ [Chu kỳ 45s] Đã đọc & cập nhật phân loại chuyên sâu cho %d tài liệu.", updated_count)
        return updated_count

    async def sync_pending_turso_documents(self) -> int:
        """Đồng bộ các đề thi nộp từ Web lúc Bot offline từ Turso Cloud sang các kênh Discord."""
        from database.turso_client import turso_db
        if not turso_db.is_configured:
            return 0

        pending_docs = await turso_db.fetchall(
            """
            SELECT id, subject, title, file_name, file_size_bytes, file_type,
                   estimated_level, question_count, page_count, author_id, author_name,
                   timestamp, file_hash, academic_year, school_or_department,
                   moet_2025_compliant, moet_part1_count, moet_part2_count, moet_part3_count,
                   has_answer_keys, has_detailed_solutions, file_content_base64
            FROM documents_archive
            WHERE queue_status = 'pending_bot'
            ORDER BY id ASC
            LIMIT 10
            """
        )

        if not pending_docs:
            return 0

        synced_count = 0
        guilds = self.bot.guilds
        if not guilds:
            return 0
        guild = guilds[0]
        category_id = getattr(settings, "DOC_CATEGORY_ID", 1534147951797080174)

        # Danh mục môn học chuẩn GDPT 2018 (Đầy đủ Cấp 2 & Cấp 3)
        subject_channel_slugs = {
            # --- CẤP 2 (THCS) ---
            "NATURAL_SCIENCE": ("khoa-học-tự-nhiên", "🔬", "Khoa học tự nhiên (Cấp 2)"),
            "KHTN": ("khoa-học-tự-nhiên", "🔬", "Khoa học tự nhiên (Cấp 2)"),
            "HISTORY_GEOGRAPHY": ("lịch-sử-địa-lý", "🗺️", "Lịch sử và Địa lý (Cấp 2)"),
            "LS_DL": ("lịch-sử-địa-lý", "🗺️", "Lịch sử và Địa lý (Cấp 2)"),
            "CIVIC_EDUCATION": ("giáo-dục-công-dân", "⚖️", "Giáo dục công dân (Cấp 2)"),
            "GDCD": ("giáo-dục-công-dân", "⚖️", "Giáo dục công dân (Cấp 2)"),
            "TECHNOLOGY": ("công-nghệ", "⚙️", "Công nghệ"),
            "CONG_NGHE": ("công-nghệ", "⚙️", "Công nghệ"),
            "PHYSICAL_EDUCATION": ("thể-chất", "🏃", "Giáo dục thể chất"),
            "THE_CHAT": ("thể-chất", "🏃", "Giáo dục thể chất"),
            # --- CẤP 3 (THPT) BẮT BUỘC & TỰ CHỌN ---
            "ECONOMIC_LEGAL_EDU": ("gdkt-pl", "📊", "Giáo dục kinh tế và pháp luật (Cấp 3)"),
            "GDKT_PL": ("gdkt-pl", "📊", "Giáo dục kinh tế và pháp luật (Cấp 3)"),
            "DEFENSE_SECURITY_EDU": ("gdqp-an", "🛡️", "Giáo dục quốc phòng và an ninh (Cấp 3)"),
            "GDQP_AN": ("gdqp-an", "🛡️", "Giáo dục quốc phòng và an ninh (Cấp 3)"),
            "EXPERIENTIAL_CAREER_ACT": ("hđtn-hn", "🧭", "Hoạt động trải nghiệm, hướng nghiệp (Cấp 3)"),
            "HDTN_HN": ("hđtn-hn", "🧭", "Hoạt động trải nghiệm, hướng nghiệp (Cấp 3)"),
            "LOCAL_EDUCATION": ("gd-địa-phương", "🏛️", "Nội dung giáo dục địa phương (Cấp 3)"),
            "GDDP": ("gd-địa-phương", "🏛️", "Nội dung giáo dục địa phương (Cấp 3)"),
            "VAT_LY": ("vật-lí", "⚡", "Vật lí"),
            "PHYSICS": ("vật-lí", "⚡", "Vật lí"),
            "HOA_HOC": ("hóa-học", "🧪", "Hóa học"),
            "CHEMISTRY": ("hóa-học", "🧪", "Hóa học"),
            "SINH_HOC": ("sinh-học", "🧬", "Sinh học"),
            "BIOLOGY": ("sinh-học", "🧬", "Sinh học"),
            "LICH_SU": ("lịch-sử", "📜", "Lịch sử"),
            "HISTORY": ("lịch-sử", "📜", "Lịch sử"),
            "DIA_LY": ("địa-lí", "🌏", "Địa lí"),
            "GEOGRAPHY": ("địa-lí", "🌏", "Địa lí"),
            # --- XUYÊN SUỐT CẢ 2 CẤP ---
            "TOAN": ("toán-học", "📐", "Toán"),
            "MATHEMATICS": ("toán-học", "📐", "Toán"),
            "NGU_VAN": ("ngữ-văn", "📖", "Ngữ văn"),
            "LITERATURE": ("ngữ-văn", "📖", "Ngữ văn"),
            "TIENG_ANH": ("tiếng-anh", "🇬🇧", "Ngoại ngữ 1 (Tiếng Anh)"),
            "ENGLISH": ("tiếng-anh", "🇬🇧", "Ngoại ngữ 1 (Tiếng Anh)"),
            "TIN_HOC": ("tin-học", "💻", "Tin học"),
            "INFORMATICS": ("tin-học", "💻", "Tin học"),
        }

        import base64
        import io

        for doc in pending_docs:
            doc_id = doc.get("id")
            subject = str(doc.get("subject") or "GENERAL").upper()
            title = doc.get("title") or doc.get("file_name") or "Đề thi"
            file_name = doc.get("file_name") or f"de_thi_{doc_id}.pdf"
            author_name = doc.get("author_name") or "Khách (Web)"
            grade = doc.get("estimated_level") or "Chung"
            q_cnt = doc.get("question_count") or 0
            p_cnt = doc.get("page_count") or 1
            academic_year = doc.get("academic_year")
            school = doc.get("school_or_department")
            is_moet_2025 = bool(doc.get("moet_2025_compliant"))
            has_ans = bool(doc.get("has_answer_keys"))
            has_sol = bool(doc.get("has_detailed_solutions"))
            raw_b64 = doc.get("file_content_base64")

            slug_info = subject_channel_slugs.get(subject, ("kho-đề-chung", "📚", subject))
            target_ch = await self._get_or_create_subject_channel(
                guild=guild,
                category_id=category_id,
                channel_slug=slug_info[0],
                icon=slug_info[1],
                subject_name=slug_info[2],
            )

            if target_ch and isinstance(target_ch, discord.TextChannel):
                embed = discord.Embed(
                    title=f"📥 [ĐỀ THI MỚI - TỰ ĐỘNG TỪ WEB] {title[:200]}",
                    description=(
                        f"✨ *Đề thi nộp qua Web Dashboard trong lúc Bot offline, hệ thống tự động đồng bộ hóa.*\\n\\n"
                        f"👤 **Người nộp:** `{author_name}`\\n"
                        f"📖 **Môn học:** `{slug_info[2]}` | 🎓 **Khối:** `{grade}`\\n"
                        f"📊 **Quy mô:** `{q_cnt}` câu • `{p_cnt}` trang\\n"
                    ),
                    color=0x9B59B6,
                )
                if academic_year:
                    embed.add_field(name="📅 Năm học", value=f"`{academic_year}`", inline=True)
                if school:
                    embed.add_field(name="🏫 Nguồn / Trường", value=f"`{school}`", inline=True)
                if is_moet_2025:
                    p1 = doc.get("moet_part1_count") or 0
                    p2 = doc.get("moet_part2_count") or 0
                    p3 = doc.get("moet_part3_count") or 0
                    embed.add_field(
                        name="✨ Chuẩn Bộ GD&ĐT 2025",
                        value=f"✅ Đạt chuẩn (Phần I: {p1}, Phần II: {p2}, Phần III: {p3})",
                        inline=False,
                    )
                badges = []
                if has_ans:
                    badges.append("📝 Có đáp án")
                if has_sol:
                    badges.append("✨ Lời giải chi tiết")
                if badges:
                    embed.add_field(name="🏷️ Phụ lục", value=" • ".join(badges), inline=True)

                embed.add_field(
                    name="🔗 Truy cập Kho Đề Web",
                    value="[Mở Web Dashboard](https://orbit-psi-black.vercel.app/#vault)",
                    inline=False,
                )

                # Chuẩn bị tệp đính kèm thật từ base64 nếu có
                discord_file: discord.File | None = None
                if raw_b64:
                    try:
                        clean_b64 = raw_b64.split(",", 1)[1] if "," in raw_b64 else raw_b64
                        file_bytes = base64.b64decode(clean_b64)
                        discord_file = discord.File(io.BytesIO(file_bytes), filename=file_name)
                    except Exception as b64_err:
                        log.warning("Lỗi giải mã base64 file #%s: %s", doc_id, b64_err)

                try:
                    send_kwargs: dict[str, Any] = {"embed": embed}
                    if discord_file:
                        send_kwargs["file"] = discord_file

                    posted_msg = await target_ch.send(**send_kwargs)
                    if posted_msg:
                        # Cập nhật trạng thái và giải phóng file_content_base64 trong Turso để bảo toàn 5GB storage
                        await turso_db.execute(
                            """UPDATE documents_archive 
                               SET queue_status = 'synced_discord', channel_id = ?, message_id = ?, jump_url = ?, file_content_base64 = NULL 
                               WHERE id = ?""",
                            target_ch.id,
                            posted_msg.id,
                            posted_msg.jump_url,
                            doc_id,
                        )
                        if hasattr(self.bot, "db"):
                            try:
                                await self.bot.db.execute(
                                    """
                                    INSERT INTO documents_archive (
                                        subject, title, file_name, file_size_bytes, file_type,
                                        estimated_level, question_count, page_count, author_id,
                                        author_name, channel_id, message_id, jump_url, timestamp,
                                        file_hash, raw_text, academic_year, school_or_department
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    subject, title, file_name, doc.get("file_size_bytes", 0), doc.get("file_type", "PDF"),
                                    grade, q_cnt, p_cnt, doc.get("author_id", 0),
                                    author_name, target_ch.id, posted_msg.id, posted_msg.jump_url,
                                    doc.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    doc.get("file_hash"), "", academic_year, school
                                )
                            except Exception:
                                pass
                        synced_count += 1
                        log.info("Đã tự động đồng bộ đề thi #%s (%s) kèm tệp thật từ Turso Cloud sang Discord thành công!", doc_id, title)
                except Exception as post_err:
                    log.warning("Lỗi khi gửi đề từ Turso sang Discord: %s", post_err)
        return synced_count

    async def _get_or_create_subject_channel(
        self, guild: discord.Guild, category_id: int, channel_slug: str, icon: str, subject_name: str
    ) -> discord.TextChannel | None:
        """Lưu trữ tài liệu vào kênh lưu trữ chuyên biệt (#database), không tự sinh kênh môn học rác trong Category Tài Liệu."""
        db_archive_id = getattr(settings, "DATABASE_ARCHIVE_CHANNEL_ID", 1548627763467128912)
        archive_ch = guild.get_channel(db_archive_id)
        if archive_ch and isinstance(archive_ch, discord.TextChannel):
            return archive_ch
        if hasattr(self.bot, "fetch_channel"):
            try:
                ch = await self.bot.fetch_channel(db_archive_id)
                if isinstance(ch, discord.TextChannel):
                    return ch
            except Exception:
                pass
        intake_id = getattr(settings, "DOC_INTAKE_CHANNEL_ID", 1535278288828633138)
        ch_intake = guild.get_channel(intake_id)
        return ch_intake if isinstance(ch_intake, discord.TextChannel) else None

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
        ai_problems_path = Path(__file__).resolve().parent.parent / "data" / "ai_problems.json"
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
        content_hash: Optional[str] = None,
        quorum_status: Optional[str] = None,
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

            c_hash = content_hash or getattr(report, "content_hash", None)
            q_status = quorum_status
            if not q_status and hasattr(report, "quorum_arbitration") and report.quorum_arbitration:
                q_status = "UNANIMOUS_3_3" if report.quorum_arbitration.get("is_unanimous") else "ARBITRATION_3_PLUS_1"

            try:
                await self.bot.db.execute(
                    """
                    INSERT INTO documents_archive (
                        subject, title, file_name, file_size_bytes, file_type,
                        estimated_level, question_count, page_count, author_id,
                        author_name, channel_id, message_id, jump_url, timestamp, file_hash, content_hash, raw_text,
                        verdict, exam_track, confidence, academic_year, school_or_department, quorum_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    c_hash,
                    raw_text,
                    _verdict,
                    _track,
                    _conf,
                    getattr(report, "academic_year", None),
                    getattr(report, "school_or_department", None),
                    q_status,
                )
            except Exception:
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
                    # DB cũ nhất
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

            # Đồng bộ sang Turso libSQL Cloud Database để Web Vault cập nhật tức thì
            try:
                from database.turso_client import turso_db
                if turso_db.is_configured:
                    turso_sql = """
                        INSERT INTO documents_archive (
                            subject, title, file_name, file_size_bytes, file_type,
                            estimated_level, question_count, page_count, author_id,
                            author_name, channel_id, message_id, jump_url, timestamp,
                            file_hash, raw_text, notes, academic_year, school_or_department,
                            verdict, exam_track, confidence, moet_2025_compliant,
                            moet_part1_count, moet_part2_count, moet_part3_count,
                            has_answer_keys, has_detailed_solutions, queue_status,
                            client_pre_parsed, created_via
                        ) VALUES (
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?
                        )
                    """
                    p1_cnt = getattr(report, "moet_part1_count", 0) or 0
                    p2_cnt = getattr(report, "moet_part2_count", 0) or 0
                    p3_cnt = getattr(report, "moet_part3_count", 0) or 0
                    is_m25 = 1 if getattr(report, "moet_2025_compliant", False) else 0
                    has_ans = 1 if getattr(report, "has_answer_keys", False) else 0
                    has_sol = 1 if getattr(report, "has_detailed_solutions", False) else 0
                    acad_yr = getattr(report, "academic_year", None)
                    sch_dept = getattr(report, "school_or_department", None)

                    await turso_db.execute(
                        turso_sql,
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
                        raw_text[:50000] if raw_text else "",
                        report.human_summary,
                        acad_yr,
                        sch_dept,
                        _verdict or "XAC_MINH",
                        _track or "NOT_AN_EXAM",
                        _conf or 0.95,
                        is_m25,
                        p1_cnt,
                        p2_cnt,
                        p3_cnt,
                        has_ans,
                        has_sol,
                        "synced_discord",
                        0,
                        "discord",
                    )
            except Exception as te:
                log.debug("Lỗi mirror đề thi sang Turso Cloud: %s", te)
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

        # 1. Quét tệp đính kèm (Attachments) — hỗ trợ gửi nhiều tệp cùng lúc (miễn mỗi tệp <= 25MB)
        if message.attachments:
            for att in message.attachments:
                if att.size and att.size > 25 * 1024 * 1024:
                    continue
                ext = Path(att.filename).suffix.lower()
                if ext not in [".pdf", ".docx", ".doc", ".txt", ".cpp", ".py", ".zip", ".rar", ".7z", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
                    continue

                try:
                    data = await att.read()
                    if len(data) > 25 * 1024 * 1024:
                        continue
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
                    raw_text_extracted = ""

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
                        raw_text_extracted = getattr(res, "raw_text", "") or ""

                    now_iso = message.created_at.isoformat()
                    author_name = message.author.display_name or message.author.name
                    if message.author.id == self.bot.user.id:
                        author_name = "Hệ thống (Bot)"

                    await self.bot.db.execute(
                        """
                        INSERT INTO documents_archive (
                            subject, title, file_name, file_size_bytes, file_type,
                            estimated_level, question_count, page_count, author_id,
                            author_name, channel_id, message_id, jump_url, timestamp, file_hash, raw_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        raw_text_extracted[:50000] if raw_text_extracted else "",
                    )
                    try:
                        from DocInspector.cloud_verifier import CloudExamVerifier
                        last_row = await self.bot.db.fetchone(
                            "SELECT id FROM documents_archive WHERE file_hash = ? ORDER BY id DESC LIMIT 1",
                            file_hash,
                        )
                        if last_row and raw_text_extracted:
                            CloudExamVerifier.enqueue_for_45s_batch(
                                doc_id=last_row[0],
                                file_name=att.filename,
                                raw_text=raw_text_extracted,
                            )
                    except Exception:
                        pass
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
                        try:
                            from database.turso_client import turso_db
                            if turso_db.is_configured:
                                await turso_db.execute("DELETE FROM documents_archive WHERE id = ?", d_id)
                        except Exception:
                            pass
                        pruned_deleted += 1
                        continue
                    try:
                        await target_ch.fetch_message(m_id)
                    except discord.NotFound:
                        await self.bot.db.execute("DELETE FROM documents_archive WHERE id = ?", d_id)
                        try:
                            from database.turso_client import turso_db
                            if turso_db.is_configured:
                                await turso_db.execute("DELETE FROM documents_archive WHERE id = ?", d_id)
                        except Exception:
                            pass
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
                    try:
                        from database.turso_client import turso_db
                        if turso_db.is_configured:
                            await turso_db.execute(
                                f"DELETE FROM documents_archive WHERE id IN ({placeholders})",
                                *dup_ids,
                            )
                    except Exception:
                        pass
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
        """Tạo Embed hướng dẫn nộp tài liệu chuẩn và thống kê kho đề gọn gàng."""
        stats = await self.get_storage_statistics()
        total_size_human = format_bytes_to_human(stats["grand_total_bytes"])
        total_docs_count = stats["grand_total_items"]

        guide_desc = (
            "Đóng góp đề thi & tài liệu học tập trực tiếp trên **Orbit Web Portal** để nhận vinh danh tác giả.\n\n"
            "🌐 **Cổng nộp đề trực tuyến:** **https://orbit-psi-black.vercel.app/#submit_doc**\n\n"
            "**Quyền lợi khi đóng góp (Chỉ cần liên kết tài khoản Discord, không cần xác minh email):**\n"
            "• 👤 **Vinh danh Credit:** Tên & Avatar Discord hiển thị trực tiếp trên thẻ đề thi.\n"
            "• ✍️ **Danh hiệu chính thức:** Tự động cấp role <@&1534128847157461034> trên máy chủ.\n\n"
            f"📊 **Trạng thái kho hiện tại:** `{total_docs_count:,} tài liệu` (`{total_size_human}`) • "
            "Hỗ trợ `.pdf`, `.docx`, `.doc`, `.txt` & Google Drive."
        )

        embed_guide = discord.Embed(
            title="📤 TRẠM ĐÓNG GÓP ĐỀ THI & TÀI LIỆU HỌC TẬP",
            description=guide_desc,
            color=0x9B5CFF,
        )
        embed_guide.set_footer(text="Orbit | Vietnam • Kho Đề Thi & Tài Liệu Học Tập Mở")

        return [embed_guide]

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
                f"💾 **Tổng dung lượng kho:** `{total_size_human}`\n"
                f"📚 **Tổng số lượng tài liệu:** `{stats['grand_total_items']:,} đề thi`\n"
            ),
            color=0x2ECC71,
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
                value="*Chưa có tài liệu nào được lưu trữ.*",
                inline=False,
            )

        embed.set_footer(text="Orbit | Vietnam • Thống kê Kho Đề Thi")
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
                            if any(("NỘP" in (e.title or "").upper() or "ĐÓNG GÓP" in (e.title or "").upper() or "HƯỚNG DẪN" in (e.title or "").upper()) for e in m.embeds):
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
                # 1. Kiểm tra xem bảng panel của Bot đã có sẵn trong kênh hay chưa
                existing_panel = None
                try:
                    async for m in channel.history(limit=5):
                        if m.author == self.bot.user and m.embeds and any(k in (m.embeds[0].title or "").upper() for k in ("NỘP", "ĐÓNG GÓP", "HƯỚNG DẪN")):
                            existing_panel = m
                            break
                except Exception:
                    pass

                embeds = await self.build_intake_panel_embeds()
                view = DocumentIntakeControlView(self)

                if existing_panel and not purge:
                    await existing_panel.edit(embeds=embeds, view=view)
                    self._panel_message_id = existing_panel.id
                    log.info("✅ Bảng hướng dẫn nộp tài liệu đã tồn tại, cập nhật nhẹ (0%% CPU) tại #%s", channel.name)
                    return

                if purge:
                    try:
                        await channel.purge(limit=15)
                    except Exception:
                        pass

                msg = await channel.send(embeds=embeds, view=view)
                self._panel_message_id = msg.id
                log.info("✅ Đã khởi tạo bảng hướng dẫn nộp tài liệu mới tại #%s (%s)", channel.name, channel.id)
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
                            f"🔗 **Bài đăng gốc:** {dup_jump}"
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

        # === CHỐNG NỘP TRÙNG LAYER 2: CHỮ KÝ NỘI DUNG ĐỀ THI (CONTENT HASH) ===
        if getattr(report, "content_hash", None) and hasattr(self.bot, "db"):
            try:
                existing_content = await self.bot.db.fetchone(
                    "SELECT jump_url, author_name, timestamp, title FROM documents_archive WHERE content_hash = ?",
                    report.content_hash,
                )
                if existing_content:
                    dup_jump = existing_content[0] or "N/A"
                    dup_author = existing_content[1] or "N/A"
                    dup_time = existing_content[2] or "N/A"
                    dup_title = existing_content[3] or "N/A"
                    routing.is_blocked_or_unverifiable = True
                    routing.submission_reply_message = (
                        f"🔁 **TÀI LIỆU TRÙNG NỘI DUNG ĐỀ THI!**\n"
                        f"Nội dung văn bản đề này hoàn toàn trùng khớp với đề **{dup_title}** đã được nộp trước đó bởi **{dup_author}** vào `{dup_time}`.\n"
                        f"🔗 **Bài đăng gốc:** {dup_jump}"
                    )
                    report.human_summary = f"Tài liệu trùng nội dung đề thi với bài đăng của {dup_author}"
                    return report, routing, None
            except Exception as e:
                log.debug("Lỗi kiểm tra trùng nội dung Layer 2: %s", e)

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

                post_content += format_rich_exam_metadata(report)


                try:
                    audit_view = DocInspectorAuditView(report)
                    if isinstance(file_path_or_bytes, bytes) and file_name:
                        file_forward = discord.File(io.BytesIO(file_path_or_bytes), filename=file_name)
                        posted_msg = await target_ch.send(content=post_content, file=file_forward, view=audit_view)
                    elif isinstance(file_path_or_bytes, str) and file_path_or_bytes.startswith(("http://", "https://")):
                        post_content += f"\n🔗 **Link gốc:** {file_path_or_bytes}"
                        posted_msg = await target_ch.send(content=post_content, view=audit_view)
                    elif isinstance(file_path_or_bytes, str) and os.path.exists(file_path_or_bytes):
                        file_forward = discord.File(file_path_or_bytes, filename=file_name or os.path.basename(file_path_or_bytes))
                        posted_msg = await target_ch.send(content=post_content, file=file_forward, view=audit_view)
                except discord.HTTPException as he:
                    if getattr(he, "status", 0) == 413 or getattr(he, "code", 0) == 40005:
                        post_content += f"\n⚠️ *(Tệp '{file_name}' vượt quá dung lượng upload tối đa của Discord. Metadata và thẩm định đã được lưu an toàn.)*"
                        posted_msg = await target_ch.send(content=post_content, view=audit_view)
                    else:
                        raise

                if posted_msg:
                    raw_text_for_db = None
                    if hasattr(report, 'pass1') and hasattr(report.pass1, 'raw_text'):
                        raw_text_for_db = report.pass1.raw_text[:50000] if report.pass1.raw_text else None
                    q_status = "UNANIMOUS_3_3" if (getattr(report, "quorum_arbitration", None) and report.quorum_arbitration.get("is_unanimous")) else "ARBITRATION_3_PLUS_1"
                    await self.record_inspection_report(
                        report, routing, author, target_ch, posted_msg,
                        file_hash=file_hash,
                        raw_text=raw_text_for_db,
                        content_hash=getattr(report, "content_hash", None),
                        quorum_status=q_status,
                    )

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
            # Xóa ngay lập tức mọi tin nhắn gửi vào kênh nộp tài liệu (chỉ nộp trên Web)
            try:
                await message.delete()
            except Exception:
                pass

            if not message.author.bot:
                warn_text = (
                    f"⚠️ {message.author.mention}, nộp tài liệu hiện đã chuyển hoàn toàn lên **Orbit Web Portal** (không nộp trên Bot nữa).\n"
                    f"👉 Vui lòng truy cập **https://orbit-psi-black.vercel.app/#vault** để nộp đề thi & tài liệu trực tuyến nhé!"
                )
                try:
                    await message.channel.send(warn_text, delete_after=7.0)
                except Exception:
                    pass

            asyncio.create_task(self.clean_intake_channel(message.channel))
            return

        # TRƯỜNG HỢP B: Tin nhắn gửi trong các kênh thuộc Thư mục phân loại (1534147951797080174)
        channel_category_id = getattr(message.channel, "category_id", None)
        doc_search_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1567532842617937931)
        if channel_category_id == category_id and message.channel.id not in (intake_channel_id, doc_search_id) and (message.attachments or "http" in message.content):
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

            # 2. Nếu là người dùng gửi trực tiếp (Admin), kiểm tra thêm Channel Compliance cho tất cả tệp (mỗi tệp <= 25MB)
            if not message.author.bot:
                try:
                    targets_to_check: list[tuple[bytes | str, Optional[str]]] = []
                    if message.attachments:
                        for att in message.attachments:
                            if att.size and att.size > 25 * 1024 * 1024:
                                continue
                            targets_to_check.append((await att.read(), att.filename))
                    else:
                        for url_m in re.finditer(r"https?://[^\s]+", message.content):
                            targets_to_check.append((url_m.group(0), None))

                    for target_data, file_name in targets_to_check:
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
                                f"⚠️ {message.author.mention}, tài liệu `{file_name or 'liên kết'}` bạn vừa đăng có thể **sai chuyên mục kênh**!\n"
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
                try:
                    from database.turso_client import turso_db
                    if turso_db.is_configured:
                        await turso_db.execute("DELETE FROM documents_archive WHERE id = ? OR message_id = ?", doc_id, payload.message_id)
                except Exception:
                    pass
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

        archive_embed.set_footer(text="Hệ Thống Phân Loại Đề Thi Tự Động • Orbit")

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
