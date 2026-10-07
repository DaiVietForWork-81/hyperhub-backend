"""
cogs/doc_search.py
Module Tra cứu & Khai thác Kho Đề Thi Tự Động tại kênh 1553678782101979186.

Hỗ trợ 2 chế độ tra cứu thông minh:
1. 🎯 Tra Cứu Chi Tiết: Bộ lọc đa chiều gồm Môn học, Khối lớp, Thể loại (Thường, HSG, Chuyên).
2. 📝 Tra Cứu Theo Mô Tả: Nhập từ khóa / mô tả tự do, hỗ trợ thuật toán so khớp C++ Levenshtein và bóc tách thông minh.

Đặc tính:
- Kênh tra cứu chỉ duy trì 1 Bảng Điều Khiển cố định, tự động dọn sạch tin nhắn thừa.
- Toàn bộ kết quả tra cứu được gửi RIÊNG TƯ (Ephemeral) để tránh làm trôi bảng điều khiển.
- Hỗ trợ phân trang và nút Jump URL chuyển trực tiếp tới bài đăng gốc trong kho lưu trữ.
- Phản hồi tức thì < 50ms (chống lỗi 'Ứng dụng không phản hồi'), kèm bộ đệm RAM Cache.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings

log = logging.getLogger("doc_search")

# Danh sách môn học chuẩn (Sử dụng single-codepoint unicode emoji để tránh 400 Bad Request)
SUBJECT_OPTIONS = [
    ("Tất Cả Môn Học", "ALL", "📚"),
    ("Toán Học", "MATHEMATICS", "📐"),
    ("Tin Học (Tất Cả)", "INFORMATICS", "💻"),
    ("Tin Học: C / C++", "INFO_CPP", "⚡"),
    ("Tin Học: Python", "INFO_PYTHON", "🐍"),
    ("Tin Học: Pascal", "INFO_PASCAL", "📜"),
    ("Tin Học: Java", "INFO_JAVA", "☕"),
    ("Tin Học: Thuật Toán & CP", "INFO_DSA", "🏆"),
    ("Tin Học: CSDL & SQL", "INFO_SQL", "🗄️"),
    ("Tiếng Anh", "ENGLISH", "🔤"),
    ("Vật Lý", "PHYSICS", "⚡"),
    ("Hóa Học", "CHEMISTRY", "🧪"),
    ("Sinh Học", "BIOLOGY", "🧬"),
    ("Ngữ Văn", "LITERATURE", "📖"),
    ("Lịch Sử", "HISTORY", "🏛️"),
    ("Địa Lý", "GEOGRAPHY", "🌍"),
    ("Giáo Dục Công Dân", "CIVIC_EDUCATION", "⚖️"),
    ("Khoa Học Tự Nhiên", "NATURAL_SCIENCE", "🔬"),
    ("Tiếng Nhật", "JAPANESE", "🌸"),
    ("Tiếng Trung", "CHINESE", "🏮"),
    ("Tiếng Hàn", "KOREAN", "🍱"),
    ("Tiếng Pháp", "FRENCH", "🥐"),
]

# Danh sách khối lớp chuẩn (Single-codepoint standard emojis)
GRADE_OPTIONS = [
    ("Tất Cả Khối Lớp", "ALL", "🎓"),
    ("Lớp 12 / THPT Quốc Gia", "GRADE_12", "📕"),
    ("Lớp 11", "GRADE_11", "📗"),
    ("Lớp 10", "GRADE_10", "📘"),
    ("Khối THCS (Lớp 6-9)", "MIDDLE_SCHOOL", "🎒"),
    ("Đại Học / Cao Đẳng", "UNIVERSITY", "🏛️"),
    ("Chuyên / Olympic / HSG", "OLYMPIAD_GIFTED", "🏆"),
]

# Danh sách thể loại đề
TRACK_OPTIONS = [
    ("Tất Cả Thể Loại", "ALL", "🏷️"),
    ("Thường / Đại Trà / Tốt Nghiệp", "thường", "📘"),
    ("Học Sinh Giỏi (HSG Tỉnh / Quốc Gia)", "hsg", "🥈"),
    ("Chuyên / Olympic / Nâng Cao", "chuyên", "🥇"),
]

# Bộ từ điển đồng nghĩa & từ khóa nhận diện môn học tiếng Việt
SUBJECT_KEYWORDS_MAP: Dict[str, List[str]] = {
    "MATHEMATICS": ["toán", "toan", "math", "toán học", "toan hoc", "hình học", "hinh hoc", "đại số", "dai so", "giải tích", "giai tich"],
    "INFORMATICS": [
        "tin", "tin học", "tin hoc", "code", "lập trình", "lap trinh", "informatics", "it",
        "cpp", "c++", "con trỏ", "vector", "stl", "g++",
        "python", "py", "pip", "tkinter", "pygame",
        "pascal", "pas", "freepascal", "lazarus",
        "java", "jvm", "oop", "hướng đối tượng", "huong doi tuong",
        "thuật toán", "thuat toan", "dsa", "cấu trúc dữ liệu", "cau truc du lieu",
        "quy hoạch động", "quy hoach dong", "đồ thị", "do thi", "dijkstra",
        "segment tree", "fenwick", "trie", "dsu", "subtask", "time limit", "memory limit",
        "hsg tin", "chuyen tin", "chuyên tin", "tin học trẻ", "tin hoc tre",
        "olympic tin", "vnoi", "codeforces", "icpc", "sql", "csdl", "cơ sở dữ liệu"
    ],
    "ENGLISH": ["anh", "tiếng anh", "tieng anh", "english", "anh văn", "anh van", "ielts", "toeic", "wordform", "cloze"],
    "PHYSICS": ["lý", "ly", "vật lý", "vat ly", "vat li", "physics"],
    "CHEMISTRY": ["hóa", "hoa", "hóa học", "hoa hoc", "chemistry"],
    "BIOLOGY": ["sinh", "sinh học", "sinh hoc", "biology", "di truyền"],
    "LITERATURE": ["văn", "van", "ngữ văn", "ngu van", "literature", "nghị luận", "nghi luan"],
    "HISTORY": ["sử", "su", "lịch sử", "lich su", "history"],
    "GEOGRAPHY": ["địa", "dia", "địa lý", "dia ly", "geography"],
    "CIVIC_EDUCATION": ["gdcd", "công dân", "cong dan", "ktpl", "kinh tế pháp luật"],
    "NATURAL_SCIENCE": ["khtn", "khoa học tự nhiên", "khoa hoc tu nhien"],
    "JAPANESE": ["nhật", "nhat", "tiếng nhật", "tieng nhat", "japanese", "jlpt"],
    "CHINESE": ["trung", "tiếng trung", "tieng trung", "chinese", "hsk"],
    "KOREAN": ["hàn", "han", "tiếng hàn", "tieng han", "korean", "topik"],
    "RUSSIAN": ["nga", "tiếng nga", "tieng nga", "russian", "trki"],
    "FRENCH": ["pháp", "phap", "tiếng pháp", "tieng phap", "french", "delf"],
}

# Các từ phụ trợ / hư từ không dùng làm từ khóa tìm kiếm chính
STOP_WORDS = {
    "đề", "de", "đề thi", "de thi", "bài tập", "bai tap", "tài liệu", "tai lieu",
    "tìm", "tim", "cho", "của", "cua", "các", "cac", "về", "ve", "kiểm tra",
    "kiem tra", "ôn tập", "on tap", "file", "tệp", "tep", "link"
}


def format_bytes_to_human(size_bytes: int) -> str:
    """Chuyển đổi số bytes sang định dạng KB / MB / GB."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[min(i, len(units) - 1)]}"


class SearchResultPaginationView(discord.ui.View):
    """View phân trang kết quả tra cứu đề thi (Ephemeral)."""

    def __init__(
        self,
        results: List[dict],
        search_title: str,
        user_id: int,
        page_size: int = 5,
    ) -> None:
        super().__init__(timeout=180)
        self.results = results
        self.search_title = search_title
        self.user_id = user_id
        self.page_size = page_size
        self.current_page = 0
        self.total_pages = max(1, math.ceil(len(results) / page_size))
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current_page <= 0
        self.next_btn.disabled = self.current_page >= self.total_pages - 1
        self.page_indicator.label = f"Trang {self.current_page + 1}/{self.total_pages}"

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🔎 KẾT QUẢ: {self.search_title}",
            description=f"Tìm thấy tổng cộng **{len(self.results)}** tài liệu phù hợp trong kho lưu trữ.",
            color=0x3498DB,
        )

        start = self.current_page * self.page_size
        end = min(start + self.page_size, len(self.results))
        page_items = self.results[start:end]

        if not page_items:
            embed.description = "❌ Không tìm thấy tài liệu nào khớp với tiêu chuẩn yêu cầu."
            return embed

        for idx, item in enumerate(page_items, start=start + 1):
            title = item.get("title") or item.get("file_name") or "Tài liệu học tập"
            level = item.get("estimated_level", "Không xác định")
            size_str = format_bytes_to_human(item.get("file_size_bytes", 0))
            author = item.get("author_name", "Ẩn danh")
            jump_url = item.get("jump_url")
            timestamp = (item.get("timestamp") or "")[:10]

            source_icon = "🤖" if ("bot" in author.lower() or "hệ thống" in author.lower()) else "👤"
            link_part = f" • [🔗 Xem Bài Đăng Gốc]({jump_url})" if jump_url else ""
            val = (
                f"• **Phân loại:** `{level}` | **Dung lượng:** `{size_str}`\n"
                f"• **Người đăng:** {source_icon} **{author}** ({timestamp}){link_part}"
            )
            embed.add_field(name=f"#{idx}. {title}", value=val, inline=False)

        embed.set_footer(
            text="Hệ Thống Tra Cứu Kho Đề Thi Tự Động • HyperHub CP Arena",
            icon_url="https://assets.codeforces.com/favicon-96x96.png",
        )
        return embed

    @discord.ui.button(label="◀ Trang Trước", style=discord.ButtonStyle.secondary, custom_id="search_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên phiên tra cứu của người khác.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Trang 1/1", style=discord.ButtonStyle.primary, disabled=True, custom_id="search_page")
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Trang Sau ▶", style=discord.ButtonStyle.secondary, custom_id="search_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên phiên tra cứu của người khác.", ephemeral=True)
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)


class DescriptionSearchModal(discord.ui.Modal, title="📝 TRA CỨU ĐỀ THI THEO MÔ TẢ"):
    """Modal nhập mô tả hoặc từ khóa tự do để tìm kiếm đề thi."""

    query = discord.ui.TextInput(
        label="Nội dung mô tả hoặc từ khóa cần tìm",
        style=discord.TextStyle.paragraph,
        placeholder="Ví dụ: đề thi thử toán 12 chuyên amsterdam hk1, đề tin thuật toán đồ thị, đề tốt nghiệp anh 2024...",
        required=True,
        min_length=2,
        max_length=200,
    )

    def __init__(self, cog: DocumentSearchCog) -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            # Trả lời tức thì để chống timeout 3s của Discord
            await interaction.response.defer(ephemeral=True)
            query_text = self.query.value.strip()

            results = await self.cog.search_by_description(query_text)
            if not results:
                embed_empty = discord.Embed(
                    title="🔍 KHÔNG TÌM THẤY TÀI LIỆU",
                    description=(
                        f"Không tìm thấy tài liệu nào khớp với mô tả: **\"{query_text}\"**\n\n"
                        f"💡 *Mẹo tìm kiếm:*\n"
                        f"• Thử tìm với từ khóa ngắn gọn hơn (ví dụ: `toán 12`, `chuyên ams`, `tin học`).\n"
                        f"• Sử dụng chế độ **🎯 Tra Cứu Chi Tiết** để lọc chính xác theo từng môn học."
                    ),
                    color=0xE74C3C,
                )
                await interaction.followup.send(embed=embed_empty, ephemeral=True)
                return

            view = SearchResultPaginationView(
                results=results,
                search_title=f"Mô tả: \"{query_text}\"",
                user_id=interaction.user.id,
            )
            await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)
        except Exception as e:
            log.error("Lỗi xử lý DescriptionSearchModal: %s", e, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Có lỗi xảy ra khi tìm kiếm: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Có lỗi xảy ra khi tìm kiếm: {e}", ephemeral=True)


class DetailedSearchFilterView(discord.ui.View):
    """View tương tác chọn bộ lọc đa chiều (Môn học, Khối lớp, Thể loại)."""

    def __init__(self, cog: DocumentSearchCog, user_id: int) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.selected_subject: str = "ALL"
        self.selected_grade: str = "ALL"
        self.selected_track: str = "ALL"

        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        # 1. Dropdown chọn Môn học
        subject_select = discord.ui.Select(
            placeholder="📚 Bước 1: Chọn Môn Học Cần Tìm...",
            min_values=1,
            max_values=1,
            custom_id="select_search_subject",
            row=0,
        )
        for name, val, emoji in SUBJECT_OPTIONS[:25]:
            subject_select.add_option(
                label=name,
                value=val,
                emoji=emoji,
                default=(val == self.selected_subject),
            )
        subject_select.callback = self._on_subject_select
        self.add_item(subject_select)

        # 2. Dropdown chọn Khối lớp
        grade_select = discord.ui.Select(
            placeholder="🎓 Bước 2: Chọn Khối Lớp...",
            min_values=1,
            max_values=1,
            custom_id="select_search_grade",
            row=1,
        )
        for name, val, emoji in GRADE_OPTIONS:
            grade_select.add_option(
                label=name,
                value=val,
                emoji=emoji,
                default=(val == self.selected_grade),
            )
        grade_select.callback = self._on_grade_select
        self.add_item(grade_select)

        # 3. Dropdown chọn Thể loại
        track_select = discord.ui.Select(
            placeholder="🏷️ Bước 3: Chọn Thể Loại (Thường / HSG / Chuyên)...",
            min_values=1,
            max_values=1,
            custom_id="select_search_track",
            row=2,
        )
        for name, val, emoji in TRACK_OPTIONS:
            track_select.add_option(
                label=name,
                value=val,
                emoji=emoji,
                default=(val == self.selected_track),
            )
        track_select.callback = self._on_track_select
        self.add_item(track_select)

        # 4. Nút bấm thực hiện tìm kiếm
        submit_btn = discord.ui.Button(
            label="🔎 Thực Hiện Tra Cứu",
            style=discord.ButtonStyle.success,
            emoji="🚀",
            custom_id="btn_submit_detailed_search",
            row=3,
        )
        submit_btn.callback = self.submit_search
        self.add_item(submit_btn)

    def build_status_embed(self) -> discord.Embed:
        """Tạo embed phản hồi trực quan theo các giá trị đang chọn."""
        subj_name = next((s[0] for s in SUBJECT_OPTIONS if s[1] == self.selected_subject), self.selected_subject)
        grade_name = next((g[0] for g in GRADE_OPTIONS if g[1] == self.selected_grade), self.selected_grade)
        track_name = next((t[0] for t in TRACK_OPTIONS if t[1] == self.selected_track), self.selected_track)

        embed = discord.Embed(
            title="🎯 BỘ LỌC TRA CỨU ĐỀ THI CHI TIẾT",
            description=(
                "Vui lòng chọn các tiêu chí bên dưới theo nhu cầu của bạn, "
                "sau đó nhấn nút **'🔎 Thực Hiện Tra Cứu'** để lấy tài liệu:\n\n"
                f"• 📚 **Môn học đang chọn:** `{subj_name}`\n"
                f"• 🎓 **Khối lớp đang chọn:** `{grade_name}`\n"
                f"• 🏷️ **Thể loại đang chọn:** `{track_name}`\n\n"
                f"*(Bạn có thể thay đổi bất kỳ mục nào phía dưới rồi nhấn Tra Cứu)*"
            ),
            color=0x2ECC71,
        )
        embed.set_footer(text="HyperHub CP Arena • Bộ Lọc Siêu Tốc")
        return embed

    async def _on_subject_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên phiên của người khác.", ephemeral=True)
            return
        self.selected_subject = interaction.data["values"][0]  # type: ignore
        self._build_components()
        await interaction.response.edit_message(embed=self.build_status_embed(), view=self)

    async def _on_grade_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên phiên của người khác.", ephemeral=True)
            return
        self.selected_grade = interaction.data["values"][0]  # type: ignore
        self._build_components()
        await interaction.response.edit_message(embed=self.build_status_embed(), view=self)

    async def _on_track_select(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên phiên của người khác.", ephemeral=True)
            return
        self.selected_track = interaction.data["values"][0]  # type: ignore
        self._build_components()
        await interaction.response.edit_message(embed=self.build_status_embed(), view=self)

    async def submit_search(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên phiên của người khác.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True)
            results = await self.cog.search_detailed(
                subject=self.selected_subject,
                grade=self.selected_grade,
                track=self.selected_track,
            )

            subj_name = next((s[0] for s in SUBJECT_OPTIONS if s[1] == self.selected_subject), self.selected_subject)
            grade_name = next((g[0] for g in GRADE_OPTIONS if g[1] == self.selected_grade), self.selected_grade)
            track_name = next((t[0] for t in TRACK_OPTIONS if t[1] == self.selected_track), self.selected_track)
            criteria_str = f"{subj_name} • {grade_name} • {track_name}"

            if not results:
                embed_empty = discord.Embed(
                    title="🔍 KHÔNG TÌM THẤY TÀI LIỆU",
                    description=(
                        f"Không có tài liệu nào thỏa mãn đồng thời các tiêu chí:\n"
                        f"• **Môn học:** `{subj_name}`\n"
                        f"• **Khối lớp:** `{grade_name}`\n"
                        f"• **Thể loại:** `{track_name}`\n\n"
                        f"💡 *Gợi ý:* Hãy thử chọn **'Tất Cả'** cho Khối lớp hoặc Thể loại để mở rộng phạm vi tìm kiếm!"
                    ),
                    color=0xE67E22,
                )
                await interaction.followup.send(embed=embed_empty, ephemeral=True)
                return

            view = SearchResultPaginationView(
                results=results,
                search_title=criteria_str,
                user_id=interaction.user.id,
            )
            await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)
        except Exception as e:
            log.error("Lỗi submit DetailedSearchFilterView: %s", e, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)


class DocumentSearchControlView(discord.ui.View):
    """Bảng điều khiển cố định tại kênh Tra cứu (1553678782101979186)."""

    def __init__(self, cog: DocumentSearchCog) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="🎯 Tra Cứu Chi Tiết",
        style=discord.ButtonStyle.primary,
        emoji="🔍",
        custom_id="btn_doc_search_detail",
    )
    async def btn_detail(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            view = DetailedSearchFilterView(self.cog, interaction.user.id)
            await interaction.response.send_message(
                embed=view.build_status_embed(),
                view=view,
                ephemeral=True,
            )
        except Exception as e:
            log.error("Lỗi khi mở tra cứu chi tiết: %s", e, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)

    @discord.ui.button(
        label="📝 Tra Cứu Theo Mô Tả",
        style=discord.ButtonStyle.secondary,
        emoji="💬",
        custom_id="btn_doc_search_desc",
    )
    async def btn_desc(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            modal = DescriptionSearchModal(self.cog)
            await interaction.response.send_modal(modal)
        except Exception as e:
            log.error("Lỗi khi mở modal mô tả: %s", e, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)

    @discord.ui.button(
        label="📊 Thống Kê Kho Đề",
        style=discord.ButtonStyle.secondary,
        emoji="📈",
        custom_id="btn_doc_search_stats",
    )
    async def btn_stats(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            await interaction.response.defer(ephemeral=True)
            stats = await self.cog.get_stats()
            embed = discord.Embed(
                title="📊 THỐNG KÊ KHO TÀI LIỆU & ĐỀ THI",
                description=(
                    f"• 📚 **Tổng số lượng đề thi:** `{stats['total_items']:,}` tệp\n"
                    f"• 💾 **Tổng dung lượng kho:** `{format_bytes_to_human(stats['total_bytes'])}`\n"
                    f"• ⚡ **Tốc độ tra cứu:** `< 1ms` (Chỉ mục SQLite & C++ Native Engine)\n\n"
                    f"**Top môn học có nhiều đề thi nhất:**"
                ),
                color=0x9B59B6,
            )

            for s in stats["top_subjects"][:8]:
                s_name = s.get("subject") or "Chưa phân loại"
                embed.add_field(
                    name=f"{s_name}",
                    value=f"`{s['count']} tài liệu` • `{format_bytes_to_human(s['size'])}`",
                    inline=True,
                )

            embed.set_footer(text="Kho Học Liệu Mở • HyperHub CP Arena")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            log.error("Lỗi xem thống kê: %s", e, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)

    @discord.ui.button(
        label="🔄 Đồng Bộ Kho Đề",
        style=discord.ButtonStyle.success,
        emoji="📥",
        custom_id="btn_doc_search_sync",
    )
    async def btn_sync(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try:
            if not interaction.user.guild_permissions.manage_guild and interaction.user.id != getattr(settings, "OWNER_ID", 0):
                await interaction.response.send_message("❌ Chỉ Quản trị viên (Admin) mới có quyền kích hoạt quét & đồng bộ toàn bộ kho đề.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            doc_intake_cog = self.cog.bot.get_cog("DocumentIntakeCog")
            if not doc_intake_cog or not hasattr(doc_intake_cog, "sync_category_archive"):
                await interaction.followup.send("❌ Phân hệ tiếp nhận chưa sẵn sàng.", ephemeral=True)
                return

            sync_res = await doc_intake_cog.sync_category_archive(interaction.guild)
            self.cog._search_cache.clear()

            embed = discord.Embed(
                title="✅ ĐỒNG BỘ KHO ĐỀ THI HOÀN TẤT!",
                description=(
                    f"Hệ thống đã quét toàn bộ lịch sử các kênh chuyên môn trong Thư Mục Phân Loại:\n\n"
                    f"• 📂 **Số kênh đã rà soát:** `{sync_res.get('channels', 0)}` kênh\n"
                    f"• 💬 **Tổng số tin nhắn quét:** `{sync_res.get('scanned_messages', 0)}` tin nhắn\n"
                    f"• 📥 **Tài liệu mới lập chỉ mục:** `{sync_res.get('new_indexed', 0)}` đề thi\n"
                    f"• 🗑️ **Đề thi đã gỡ bỏ (Drama / Xóa bài):** `{sync_res.get('pruned_deleted', 0)}` đề thi\n\n"
                    f"✨ *Mọi đề thi do **Bot** hoặc **Admin** gửi đều đã sẵn sàng để tra cứu!*"
                ),
                color=0x2ECC71,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            if interaction.channel and isinstance(interaction.channel, discord.TextChannel):
                await self.cog.clean_search_channel(interaction.channel)
        except Exception as e:
            log.error("Lỗi khi bấm nút đồng bộ kho đề: %s", e, exc_info=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Có lỗi xảy ra: {e}", ephemeral=True)


class DocumentSearchCog(commands.Cog, name="DocumentSearch"):
    """Cog quản lý Trạm Tra Cứu và Khai Thác Đề Thi."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._panel_message_id: Optional[int] = None
        self._setup_lock = asyncio.Lock()
        self._clean_lock = asyncio.Lock()
        # In-memory search cache: query -> (timestamp, results)
        self._search_cache: Dict[str, Tuple[float, List[dict]]] = {}

    async def get_stats(self) -> dict:
        """Lấy số liệu thống kê kho đề từ SQLite."""
        if not hasattr(self.bot, "db"):
            return {"total_items": 0, "total_bytes": 0, "top_subjects": []}

        try:
            row = await self.bot.db.fetchone(
                "SELECT COUNT(*), COALESCE(SUM(file_size_bytes), 0) FROM documents_archive"
            )
            total_items = row[0] if row else 0
            total_bytes = row[1] if row else 0

            sub_rows = await self.bot.db.fetchall(
                """
                SELECT subject, COUNT(*), COALESCE(SUM(file_size_bytes), 0)
                FROM documents_archive
                GROUP BY subject
                ORDER BY COUNT(*) DESC
                """
            )
            top_subjects = [
                {"subject": r[0], "count": r[1], "size": r[2]}
                for r in sub_rows
            ]
            return {
                "total_items": total_items,
                "total_bytes": total_bytes,
                "top_subjects": top_subjects,
            }
        except Exception as e:
            log.warning("Lỗi truy vấn thống kê kho đề: %s", e)
            return {"total_items": 0, "total_bytes": 0, "top_subjects": []}

    async def search_detailed(
        self,
        subject: str = "ALL",
        grade: str = "ALL",
        track: str = "ALL",
        limit: int = 50,
    ) -> List[dict]:
        """Tra cứu theo bộ lọc có cấu trúc."""
        if not hasattr(self.bot, "db"):
            return []

        where_clauses = []
        params = []

        if subject and subject.upper() != "ALL":
            s_up = subject.upper()
            if s_up == "INFO_CPP":
                where_clauses.append(
                    "(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC') AND "
                    "(LOWER(title) LIKE '%c++%' OR LOWER(title) LIKE '%cpp%' OR LOWER(file_name) LIKE '%.cpp%' "
                    "OR LOWER(file_name) LIKE '%c++%' OR LOWER(estimated_level) LIKE '%c++%' OR LOWER(estimated_level) LIKE '%cpp%'))"
                )
            elif s_up == "INFO_PYTHON":
                where_clauses.append(
                    "(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC') AND "
                    "(LOWER(title) LIKE '%python%' OR LOWER(title) LIKE '%.py%' OR LOWER(file_name) LIKE '%.py%' "
                    "OR LOWER(file_name) LIKE '%python%' OR LOWER(estimated_level) LIKE '%python%'))"
                )
            elif s_up == "INFO_PASCAL":
                where_clauses.append(
                    "(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC') AND "
                    "(LOWER(title) LIKE '%pascal%' OR LOWER(file_name) LIKE '%.pas%' "
                    "OR LOWER(estimated_level) LIKE '%pascal%'))"
                )
            elif s_up == "INFO_JAVA":
                where_clauses.append(
                    "(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC') AND "
                    "(LOWER(title) LIKE '%java%' OR LOWER(file_name) LIKE '%.java%' "
                    "OR LOWER(estimated_level) LIKE '%java%'))"
                )
            elif s_up == "INFO_DSA":
                where_clauses.append(
                    "(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC') AND "
                    "(LOWER(title) LIKE '%thuật toán%' OR LOWER(title) LIKE '%quy hoạch động%' "
                    "OR LOWER(title) LIKE '%đồ thị%' OR LOWER(title) LIKE '%dsa%' OR LOWER(title) LIKE '%cp%' "
                    "OR LOWER(estimated_level) LIKE '%chuyên%' OR LOWER(estimated_level) LIKE '%hsg%'))"
                )
            elif s_up == "INFO_SQL":
                where_clauses.append(
                    "(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC') AND "
                    "(LOWER(title) LIKE '%sql%' OR LOWER(title) LIKE '%csdl%' OR LOWER(title) LIKE '%cơ sở dữ liệu%' "
                    "OR LOWER(estimated_level) LIKE '%sql%'))"
                )
            elif s_up in ("INFORMATICS", "INFO"):
                where_clauses.append("(UPPER(subject) IN ('INFORMATICS', 'INFO', 'TIN HỌC'))")
            elif s_up in ("MATHEMATICS", "MATH"):
                where_clauses.append("(UPPER(subject) IN ('MATHEMATICS', 'MATH', 'TOÁN HỌC', 'TOÁN'))")
            elif s_up in ("PHYSICS", "PHYS"):
                where_clauses.append("(UPPER(subject) IN ('PHYSICS', 'PHYS', 'VẬT LÝ', 'VẬT LÍ'))")
            elif s_up in ("CHEMISTRY", "CHEM"):
                where_clauses.append("(UPPER(subject) IN ('CHEMISTRY', 'CHEM', 'HÓA HỌC', 'HÓA'))")
            elif s_up in ("BIOLOGY", "BIO"):
                where_clauses.append("(UPPER(subject) IN ('BIOLOGY', 'BIO', 'SINH HỌC', 'SINH'))")
            elif s_up in ("ENGLISH", "ENG"):
                where_clauses.append("(UPPER(subject) IN ('ENGLISH', 'ENG', 'TIẾNG ANH'))")
            elif s_up in ("LITERATURE", "LIT"):
                where_clauses.append("(UPPER(subject) IN ('LITERATURE', 'LIT', 'NGỮ VĂN', 'VĂN'))")
            elif s_up in ("HISTORY", "HIST"):
                where_clauses.append("(UPPER(subject) IN ('HISTORY', 'HIST', 'LỊCH SỬ', 'SỬ'))")
            elif s_up in ("GEOGRAPHY", "GEO"):
                where_clauses.append("(UPPER(subject) IN ('GEOGRAPHY', 'GEO', 'ĐỊA LÝ', 'ĐỊA LÍ', 'ĐỊA'))")
            elif s_up in ("CIVIC_EDUCATION", "GDCD"):
                where_clauses.append("(UPPER(subject) IN ('CIVIC_EDUCATION', 'GDCD', 'GIÁO DỤC CÔNG DÂN'))")
            elif s_up in ("NATURAL_SCIENCE", "KHTN"):
                where_clauses.append("(UPPER(subject) IN ('NATURAL_SCIENCE', 'KHTN', 'KHOA HỌC TỰ NHIÊN'))")
            else:
                where_clauses.append("(UPPER(subject) = UPPER(?) OR LOWER(subject) LIKE ?)")
                params.extend([subject, f"%{subject.lower()}%"])

        if grade and grade.upper() != "ALL":
            if grade == "GRADE_12":
                where_clauses.append("(LOWER(estimated_level) LIKE '%12%' OR LOWER(title) LIKE '%12%')")
            elif grade == "GRADE_11":
                where_clauses.append("(LOWER(estimated_level) LIKE '%11%' OR LOWER(title) LIKE '%11%')")
            elif grade == "GRADE_10":
                where_clauses.append("(LOWER(estimated_level) LIKE '%10%' OR LOWER(title) LIKE '%10%')")
            elif grade == "MIDDLE_SCHOOL":
                where_clauses.append("(LOWER(estimated_level) LIKE '%thcs%' OR LOWER(estimated_level) LIKE '%cấp 2%' OR LOWER(title) LIKE '%thcs%')")
            elif grade == "UNIVERSITY":
                where_clauses.append("(LOWER(estimated_level) LIKE '%đại học%' OR LOWER(title) LIKE '%đại học%')")
            elif grade == "OLYMPIAD_GIFTED":
                where_clauses.append("(LOWER(estimated_level) LIKE '%chuyên%' OR LOWER(estimated_level) LIKE '%hsg%' OR LOWER(estimated_level) LIKE '%olympic%')")
            else:
                where_clauses.append("(LOWER(estimated_level) LIKE ? OR LOWER(title) LIKE ?)")
                g_kw = f"%{grade.lower()}%"
                params.extend([g_kw, g_kw])

        if track and track.upper() != "ALL":
            where_clauses.append("(LOWER(estimated_level) LIKE ? OR LOWER(title) LIKE ?)")
            t_kw = f"%{track.lower()}%"
            params.extend([t_kw, t_kw])

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"""
            SELECT id, subject, title, file_name, file_size_bytes, file_type,
                   estimated_level, question_count, page_count, author_name,
                   channel_id, message_id, jump_url, timestamp, file_hash
            FROM documents_archive
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(limit * 2)

        try:
            rows = await self.bot.db.fetchall(sql, *params)
            results = []
            seen_keys = set()
            for r in rows:
                doc = {
                    "id": r[0],
                    "subject": r[1],
                    "title": r[2],
                    "file_name": r[3],
                    "file_size_bytes": r[4],
                    "file_type": r[5],
                    "estimated_level": r[6],
                    "question_count": r[7],
                    "page_count": r[8],
                    "author_name": r[9],
                    "channel_id": r[10],
                    "message_id": r[11],
                    "jump_url": r[12],
                    "timestamp": r[13],
                    "file_hash": r[14] if len(r) > 14 else None,
                }
                # Cơ chế chống đề xuất trùng lặp (Deduplication)
                dedup_key = doc["file_hash"] or (doc["title"] or doc["file_name"] or "").strip().lower()
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                results.append(doc)
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            log.warning("Lỗi tra cứu chi tiết: %s", e)
            return []

    @staticmethod
    def _sanitize_fts_query(q: str) -> str:
        """Chuyển chuỗi tìm kiếm thành FTS5 query an toàn và hỗ trợ prefix search."""
        import re
        words = re.findall(r'[\w\u00C0-\u024F\u1E00-\u1EFF]+', q)
        if not words:
            return ''
        return ' '.join(f'"{w}"*' for w in words)

    async def search_by_description(self, query: str, limit: int = 50) -> List[dict]:
        """
        Tra cứu siêu việt đa tầng (Super Search):
        1. Lexical BM25 qua SQLite FTS5 (Unicode không dấu)
        2. Semantic Vector Embedding qua mô hình đa ngôn ngữ ONNX & SIMD C++
        3. Reciprocal Rank Fusion (RRF) kết hợp kết quả chuẩn xác tuyệt đối
        4. Fallback mờ Levenshtein nếu truy vấn quá đặc thù/sai chính tả
        """
        if not hasattr(self.bot, "db") or not query:
            return []

        # Check in-memory cache
        cache_key = query.lower().strip()
        now = time.monotonic()
        if cache_key in self._search_cache:
            cached_time, cached_res = self._search_cache[cache_key]
            if now - cached_time < 60.0:
                return cached_res

        # === HYBRID SUPER SEARCH (BM25 Lexical + Semantic Vector RRF) ===
        try:
            # 1. BM25 Lexical Ranking (FTS5)
            fts_query = self._sanitize_fts_query(query)
            bm25_hits: dict[int, tuple[int, dict]] = {}  # doc_id -> (rank_index, doc_dict)
            if fts_query:
                fts_rows = await self.bot.db.fetchall(
                    """SELECT d.id, d.subject, d.title, d.file_name, d.file_size_bytes, d.file_type,
                              d.estimated_level, d.question_count, d.page_count, d.author_name,
                              d.channel_id, d.message_id, d.jump_url, d.timestamp, d.file_hash,
                              f.rank
                       FROM documents_fts f
                       JOIN documents_archive d ON d.id = f.rowid
                       WHERE documents_fts MATCH ?
                       ORDER BY f.rank
                       LIMIT 30""",
                    fts_query,
                )
                if fts_rows:
                    for rank_idx, r in enumerate(fts_rows):
                        d_id = r[0]
                        bm25_hits[d_id] = (
                            rank_idx,
                            {
                                "id": r[0],
                                "subject": r[1],
                                "title": r[2],
                                "file_name": r[3],
                                "file_size_bytes": r[4],
                                "file_type": r[5],
                                "estimated_level": r[6],
                                "question_count": r[7],
                                "page_count": r[8],
                                "author_name": r[9],
                                "channel_id": r[10],
                                "message_id": r[11],
                                "jump_url": r[12],
                                "timestamp": r[13],
                                "file_hash": r[14] if len(r) > 14 else None,
                            },
                        )

            # 2. Semantic Vector Ranking (ONNX Embedding via C++ SIMD)
            semantic_hits: dict[int, tuple[int, float]] = {}  # doc_id -> (rank_index, score)
            if hasattr(self.bot, "embedding_service") and self.bot.embedding_service:
                try:
                    sem_results = await self.bot.embedding_service.search_semantic(query, limit=30, min_score=0.25)
                    for rank_idx, (d_id, sem_score) in enumerate(sem_results):
                        semantic_hits[d_id] = (rank_idx, sem_score)
                except Exception as sem_err:
                    log.debug("Semantic search error: %s", sem_err)

            # 3. Reciprocal Rank Fusion (RRF)
            all_candidate_ids = set(bm25_hits.keys()) | set(semantic_hits.keys())
            if len(all_candidate_ids) >= 1:
                # Nếu có ứng viên ngữ nghĩa mà chưa có trong bm25_hits, truy vấn DB để lấy metadata
                missing_doc_ids = [did for did in semantic_hits if did not in bm25_hits]
                if missing_doc_ids:
                    placeholders = ",".join("?" * len(missing_doc_ids))
                    missing_rows = await self.bot.db.fetchall(
                        f"""SELECT id, subject, title, file_name, file_size_bytes, file_type,
                                   estimated_level, question_count, page_count, author_name,
                                   channel_id, message_id, jump_url, timestamp, file_hash
                            FROM documents_archive
                            WHERE id IN ({placeholders})""",
                        *missing_doc_ids,
                    )
                    for r in missing_rows:
                        bm25_hits[r[0]] = (
                            999,  # rank_idx ngoài BM25
                            {
                                "id": r[0],
                                "subject": r[1],
                                "title": r[2],
                                "file_name": r[3],
                                "file_size_bytes": r[4],
                                "file_type": r[5],
                                "estimated_level": r[6],
                                "question_count": r[7],
                                "page_count": r[8],
                                "author_name": r[9],
                                "channel_id": r[10],
                                "message_id": r[11],
                                "jump_url": r[12],
                                "timestamp": r[13],
                                "file_hash": r[14] if len(r) > 14 else None,
                            },
                        )

                # Tính điểm RRF
                scored_candidates = []
                for d_id in all_candidate_ids:
                    if d_id not in bm25_hits:
                        continue
                    doc_data = dict(bm25_hits[d_id][1])
                    bm25_rank = bm25_hits[d_id][0]
                    sem_rank, sem_raw_score = semantic_hits.get(d_id, (999, 0.0))

                    # Trọng số RRF: BM25 (k=60) + Semantic (k=60, boost 1.3)
                    bm25_component = (1.0 / (60.0 + bm25_rank)) if bm25_rank < 100 else 0.0
                    sem_component = (1.3 / (60.0 + sem_rank)) if sem_rank < 100 else 0.0

                    rrf_score = (bm25_component + sem_component) * 1000.0
                    doc_data["score"] = round(rrf_score, 2)
                    doc_data["semantic_similarity"] = round(sem_raw_score, 3) if sem_raw_score > 0 else None
                    scored_candidates.append(doc_data)

                # Sắp xếp theo điểm RRF giảm dần và khử trùng lặp
                scored_candidates.sort(key=lambda x: x["score"], reverse=True)
                seen_keys = set()
                deduped = []
                for cand in scored_candidates:
                    dedup_key = cand.get("file_hash") or (cand.get("title") or cand.get("file_name") or "").strip().lower()
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        deduped.append(cand)

                if len(deduped) >= 2:
                    self._search_cache[cache_key] = (now, deduped[:limit])
                    return deduped[:limit]
        except Exception as hybrid_err:
            log.debug("Hybrid search error: %s", hybrid_err)

        q_lower = query.lower().strip()
        # Loại bỏ các từ phụ trợ (stopwords), nếu tất cả đều là stopword thì giữ lại raw_tokens
        raw_tokens = re.findall(r"\w+", q_lower)
        tokens = [t for t in raw_tokens if t not in STOP_WORDS]
        if not tokens:
            tokens = raw_tokens
        if not tokens:
            return []

        # 1. Bóc tách môn học dựa trên từ điển đồng nghĩa
        detected_subjects = set()
        for subj, keywords in SUBJECT_KEYWORDS_MAP.items():
            for kw in keywords:
                pattern = r"(?:^|\s)" + re.escape(kw) + r"(?:$|\s)"
                if re.search(pattern, q_lower):
                    detected_subjects.add(subj)
                    break

        # 2. Bóc tách khối lớp
        detected_grades = []
        for g in ["12", "11", "10", "9", "8", "7", "6"]:
            if re.search(r"(?:^|\s|lớp|lop|k)" + g + r"(?:$|\s)", q_lower):
                detected_grades.append(g)

        # 3. Bóc tách thể loại chuyên / HSG
        is_chuyen = bool(re.search(r"\b(chuyên|chuyen|olympic|hsg|nâng cao|nang cao)\b", q_lower))

        try:
            # Query cơ sở dữ liệu
            sql = """
                SELECT id, subject, title, file_name, file_size_bytes, file_type,
                       estimated_level, question_count, page_count, author_name,
                       channel_id, message_id, jump_url, timestamp, file_hash
                FROM documents_archive
                ORDER BY id DESC
                LIMIT 400
            """
            rows = await self.bot.db.fetchall(sql)
            if not rows:
                return []

            # Thử nạp hàm C++ Levenshtein nếu có
            fast_levenshtein = None
            try:
                from cpp_core.bridge import fast_levenshtein_similarity
                fast_levenshtein = fast_levenshtein_similarity
            except Exception:
                pass

            # Phát hiện ngôn ngữ lập trình trong câu truy vấn
            prog_languages = ["python", "c++", "cpp", "pascal", "java", "sql", "dsa"]
            query_langs = [pl for pl in prog_languages if pl in q_lower]

            scored_items = []

            for r in rows:
                doc_dict = {
                    "id": r[0],
                    "subject": r[1],
                    "title": r[2],
                    "file_name": r[3],
                    "file_size_bytes": r[4],
                    "file_type": r[5],
                    "estimated_level": r[6],
                    "question_count": r[7],
                    "page_count": r[8],
                    "author_name": r[9],
                    "channel_id": r[10],
                    "message_id": r[11],
                    "jump_url": r[12],
                    "timestamp": r[13],
                    "file_hash": r[14] if len(r) > 14 else None,
                }

                subj_upper = (doc_dict["subject"] or "").upper()
                level_lower = (doc_dict["estimated_level"] or "").lower()
                title_lower = (doc_dict["title"] or "").lower()
                fname_lower = (doc_dict["file_name"] or "").lower()

                # Mở rộng text đối sánh bao gồm cả các tên tiếng Việt của môn học đó
                subject_synonyms_str = " ".join(SUBJECT_KEYWORDS_MAP.get(subj_upper, []))
                subj_str = (doc_dict["subject"] or "").lower()
                text_to_match = f"{title_lower} {fname_lower} {subj_str} {subject_synonyms_str} {level_lower}"

                score = 0.0

                # Match môn học từ query
                if subj_upper in detected_subjects:
                    score += 120.0

                # Match khối lớp từ query
                for g in detected_grades:
                    if g in level_lower or g in title_lower or g in fname_lower:
                        score += 60.0

                # Match ngôn ngữ lập trình đặc biệt (Python, C++, Pascal, Java...)
                for ql in query_langs:
                    if ql in text_to_match or ql in fname_lower:
                        score += 90.0

                # Match thể loại chuyên / hsg
                if is_chuyen and ("chuyên" in level_lower or "hsg" in level_lower or "olympic" in level_lower or "chuyên" in title_lower):
                    score += 50.0

                # Match cụm từ đầy đủ
                if q_lower in text_to_match:
                    score += 80.0

                # Token match (các từ có nghĩa còn lại sau khi bỏ stop words)
                for t in tokens:
                    if t in text_to_match:
                        score += 25.0

                # C++ Levenshtein similarity on title
                if fast_levenshtein and len(q_lower) >= 4:
                    try:
                        sim = fast_levenshtein(q_lower, title_lower[:80])
                        if sim > 0.35:
                            score += sim * 40.0
                    except Exception:
                        pass

                if score > 0:
                    scored_items.append((score, doc_dict))

            scored_items.sort(key=lambda x: x[0], reverse=True)

            # Cơ chế chống đề xuất trùng lặp (Deduplication)
            seen_keys = set()
            final_res = []
            for _, doc in scored_items:
                dedup_key = doc.get("file_hash") or (doc.get("title") or doc.get("file_name") or "").strip().lower()
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                final_res.append(doc)
                if len(final_res) >= limit:
                    break

            # Lưu cache
            self._search_cache[cache_key] = (now, final_res)
            return final_res

        except Exception as e:
            log.warning("Lỗi tra cứu theo mô tả: %s", e)
            return []

    async def build_search_panel_embed(self) -> discord.Embed:
        """Bảng chuyển hướng tra cứu lên Web Portal (tra cứu Discord đã ngừng)."""
        stats = await self.get_stats()
        embed = discord.Embed(
            title="🔍 TRA CỨU KHO ĐỀ THI — LÊN WEB PORTAL",
            description=(
                "Kho học liệu hiện có **{items:,}** đề thi (`{size}`) "
                "đã được phân loại và thẩm định.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "📌 **Muốn tra cứu, lọc và tải đề thi, vui lòng lên Web:**\n"
                "👉 **https://hyperhub-one.vercel.app/#vault**\n\n"
                "Trên Web bạn có thể lọc theo **Môn học**, **Khối lớp**, **Thể loại**, "
                "tìm theo **từ khóa / trường / năm học** và tải đề trực tiếp.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ *Tra cứu ngay trong Discord đã ngừng hoạt động — mọi thao tác tìm đề thực hiện trên Web.*"
            ).format(
                items=stats["total_items"],
                size=format_bytes_to_human(stats["total_bytes"]),
            ),
            color=0x3498DB,
        )
        embed.set_footer(
            text="HyperHub Web Portal • Tra cứu & Tải đề trên Web",
        )
        return embed

    async def clean_search_channel(self, channel: discord.TextChannel) -> None:
        """Dọn dẹp sạch tin nhắn rác trong kênh tra cứu, chỉ giữ lại duy nhất 1 Bảng Panel."""
        async with self._clean_lock:
            try:
                panel_msg: Optional[discord.Message] = None
                if self._panel_message_id:
                    try:
                        panel_msg = await channel.fetch_message(self._panel_message_id)
                    except Exception:
                        panel_msg = None

                if not panel_msg:
                    async for m in channel.history(limit=50):
                        if m.author == self.bot.user and m.embeds:
                            first_embed = m.embeds[0]
                            if first_embed.title and (
                                "TRẠM TRA CỨU & KHAI THÁC" in first_embed.title
                                or "LÊN WEB PORTAL" in first_embed.title
                            ):
                                panel_msg = m
                                self._panel_message_id = m.id
                                break

                # Bulk delete
                def is_not_panel(m: discord.Message) -> bool:
                    return panel_msg is None or m.id != panel_msg.id

                try:
                    await channel.purge(limit=100, check=is_not_panel)
                except Exception as pe:
                    log.debug("Lỗi purge kênh tra cứu: %s", pe)

                # Individual sweep
                try:
                    async for m in channel.history(limit=50):
                        if panel_msg and m.id != panel_msg.id:
                            try:
                                await m.delete()
                            except Exception:
                                pass
                except Exception:
                    pass

                # Cập nhật panel (không gắn nút tra cứu — chuyển hẳn lên Web)
                if panel_msg:
                    embed = await self.build_search_panel_embed()
                    await panel_msg.edit(embed=embed, view=None)

            except Exception as e:
                log.warning("Lỗi dọn dẹp kênh tra cứu: %s", e)

    async def auto_setup_search_channel(self, purge: bool = True) -> None:
        """Tự động kiểm tra, xóa tin nhắn cũ và đăng Bảng Điều Khiển mới tại DOC_SEARCH_CHANNEL_ID (1553678782101979186)."""
        await self.bot.wait_until_ready()
        async with self._setup_lock:
            search_channel_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1553678782101979186)
            channel = self.bot.get_channel(search_channel_id)
            if not channel and hasattr(self.bot, "fetch_channel"):
                try:
                    channel = await self.bot.fetch_channel(search_channel_id)
                except Exception:
                    pass

            if not channel or not isinstance(channel, discord.TextChannel):
                log.warning("Không tìm thấy kênh tra cứu DOC_SEARCH_CHANNEL_ID: %s", search_channel_id)
                return

            try:
                if purge:
                    try:
                        await channel.purge(limit=100)
                    except Exception as pe:
                        log.debug("Bỏ qua lỗi purge nhanh: %s", pe)
                    # Quét dọn các tin nhắn cũ (> 14 ngày)
                    try:
                        async for m in channel.history(limit=50):
                            try:
                                await m.delete()
                            except Exception:
                                pass
                    except Exception:
                        pass

                embed = await self.build_search_panel_embed()
                new_msg = await channel.send(embed=embed)
                self._panel_message_id = new_msg.id
                log.info("✅ Đã dọn sạch kênh và tạo mới Bảng Chuyển Hướng Tra Cứu Web tại #%s (%s)", channel.name, channel.id)
            except Exception as e:
                log.warning("Lỗi thiết lập kênh tra cứu: %s", e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Xử lý tin nhắn nhắn vào kênh tra cứu (xóa ngay và thông báo hướng dẫn)."""
        if not message.guild or message.author == self.bot.user:
            return

        search_channel_id = getattr(settings, "DOC_SEARCH_CHANNEL_ID", 1553678782101979186)
        if message.channel.id == search_channel_id:
            try:
                await message.delete()
            except Exception:
                pass

            if not message.author.bot:
                try:
                    warn = (
                        f"⚠️ {message.author.mention}, tra cứu đề thi đã chuyển hẳn lên **Web Portal**.\n"
                        f"Vui lòng truy cập 👉 **https://hyperhub-one.vercel.app/#vault** để tìm và tải đề thi!"
                    )
                    await message.channel.send(warn, delete_after=7.0)
                except Exception:
                    pass

            await self.clean_search_channel(message.channel)

    @app_commands.command(
        name="timtailieu",
        description="Tra cứu nhanh tài liệu học tập & đề thi trong kho lưu trữ của Server",
    )
    @app_commands.describe(
        mo_ta="Mô tả hoặc từ khóa cần tìm (Ví dụ: đề toán 12 chuyên ams hk1)",
        mon_hoc="Môn học cụ thể cần lọc",
    )
    @app_commands.choices(
        mon_hoc=[
            app_commands.Choice(name="📐 Toán Học", value="MATHEMATICS"),
            app_commands.Choice(name="💻 Tin Học / Lập Trình", value="INFORMATICS"),
            app_commands.Choice(name="🔤 Tiếng Anh", value="ENGLISH"),
            app_commands.Choice(name="⚡ Vật Lý", value="PHYSICS"),
            app_commands.Choice(name="🧪 Hóa Học", value="CHEMISTRY"),
            app_commands.Choice(name="🧬 Sinh Học", value="BIOLOGY"),
            app_commands.Choice(name="📖 Ngữ Văn", value="LITERATURE"),
            app_commands.Choice(name="🏛️ Lịch Sử", value="HISTORY"),
            app_commands.Choice(name="🌍 Địa Lý", value="GEOGRAPHY"),
            app_commands.Choice(name="⚖️ Giáo Dục Công Dân", value="CIVIC_EDUCATION"),
        ]
    )
    async def timtailieu_slash(
        self,
        interaction: discord.Interaction,
        mo_ta: Optional[str] = None,
        mon_hoc: Optional[str] = None,
    ) -> None:
        """Slash command tra cứu tài liệu học tập."""
        await interaction.response.defer(ephemeral=True)

        if mo_ta:
            results = await self.search_by_description(mo_ta)
            search_title = f"Mô tả: \"{mo_ta}\""
        elif mon_hoc:
            results = await self.search_detailed(subject=mon_hoc)
            search_title = f"Môn học: {mon_hoc}"
        else:
            # Mặc định lấy danh sách tài liệu mới nhất
            results = await self.search_detailed(limit=20)
            search_title = "Tài Liệu Mới Nhất Trong Kho"

        if not results:
            embed_empty = discord.Embed(
                title="🔍 KHÔNG TÌM THẤY TÀI LIỆU",
                description="Không tìm thấy tài liệu nào khớp với yêu cầu của bạn.",
                color=0xE74C3C,
            )
            await interaction.followup.send(embed=embed_empty, ephemeral=True)
            return

        view = SearchResultPaginationView(
            results=results,
            search_title=search_title,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    @app_commands.command(
        name="dongbokhode",
        description="[Admin] Quét và đồng bộ toàn bộ đề thi do Bot & Admin gửi trong các kênh chuyên môn",
    )
    async def cmd_dongbokhode(self, interaction: discord.Interaction) -> None:
        """Slash command đồng bộ kho đề."""
        if not interaction.user.guild_permissions.manage_guild and interaction.user.id != getattr(settings, "OWNER_ID", 0):
            await interaction.response.send_message("❌ Chỉ Quản trị viên (Admin) mới có quyền thực hiện lệnh này.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        doc_intake_cog = self.bot.get_cog("DocumentIntakeCog")
        if not doc_intake_cog or not hasattr(doc_intake_cog, "sync_category_archive"):
            await interaction.followup.send("❌ Phân hệ tiếp nhận chưa sẵn sàng.", ephemeral=True)
            return

        sync_res = await doc_intake_cog.sync_category_archive(interaction.guild)
        self._search_cache.clear()

        embed = discord.Embed(
            title="✅ ĐỒNG BỘ KHO ĐỀ THI HOÀN TẤT!",
            description=(
                f"• 📂 **Số kênh đã rà soát:** `{sync_res.get('channels', 0)}` kênh\n"
                f"• 💬 **Tổng số tin nhắn quét:** `{sync_res.get('scanned_messages', 0)}` tin nhắn\n"
                f"• 📥 **Tài liệu mới lập chỉ mục:** `{sync_res.get('new_indexed', 0)}` đề thi\n"
                f"• 🗑️ **Đề thi đã gỡ bỏ (Drama / Xóa bài):** `{sync_res.get('pruned_deleted', 0)}` đề thi\n\n"
                f"✨ *Mọi đề thi do **Bot** hoặc **Admin** gửi đều đã sẵn sàng để tra cứu!*"
            ),
            color=0x2ECC71,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="gothailieu",
        description="[Admin] Gỡ bỏ đề thi khỏi kho tra cứu và xóa tin nhắn gốc (khi dính drama hoặc đề lỗi)",
    )
    @app_commands.describe(
        tu_khoa="Tên tệp, tiêu đề hoặc Message ID của đề thi cần gỡ bỏ",
        xoa_tin_nhan_goc="Có xóa luôn tin nhắn gốc trong kênh chuyên môn hay không (Mặc định: Có)",
    )
    async def cmd_gothailieu(
        self,
        interaction: discord.Interaction,
        tu_khoa: str,
        xoa_tin_nhan_goc: bool = True,
    ) -> None:
        """Lệnh gỡ bỏ tài liệu khẩn cấp cho Admin/Staff khi có drama hoặc đề thi bị lỗi."""
        if not interaction.user.guild_permissions.manage_guild and interaction.user.id != getattr(settings, "OWNER_ID", 0):
            await interaction.response.send_message("❌ Chỉ Quản trị viên (Admin/Staff) mới có quyền thực hiện lệnh này.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        if not hasattr(self.bot, "db"):
            await interaction.followup.send("❌ Cơ sở dữ liệu chưa sẵn sàng.", ephemeral=True)
            return

        kw = f"%{tu_khoa.strip()}%"
        msg_id_match = int(tu_khoa.strip()) if tu_khoa.strip().isdigit() else 0
        rows = await self.bot.db.fetchall(
            """
            SELECT id, subject, title, file_name, channel_id, message_id, author_name
            FROM documents_archive
            WHERE LOWER(title) LIKE LOWER(?) OR LOWER(file_name) LIKE LOWER(?) OR message_id = ?
            LIMIT 10
            """,
            kw, kw, msg_id_match,
        )

        if not rows:
            await interaction.followup.send(f"❌ Không tìm thấy tài liệu nào khớp với từ khóa: `{tu_khoa}`", ephemeral=True)
            return

        removed_docs = []
        for r in rows:
            doc_id, subj, title, fname, ch_id, m_id, author = r
            await self.bot.db.execute("DELETE FROM documents_archive WHERE id = ?", doc_id)

            msg_deleted = False
            if xoa_tin_nhan_goc and interaction.guild and ch_id and m_id:
                ch = interaction.guild.get_channel(ch_id)
                if ch and isinstance(ch, discord.TextChannel):
                    try:
                        orig_msg = await ch.fetch_message(m_id)
                        await orig_msg.delete()
                        msg_deleted = True
                    except Exception:
                        pass

            del_status = "[Đã xóa tin nhắn gốc]" if msg_deleted else ""
            removed_docs.append(f"• **{title or fname}** (Môn: `{subj}`, Người đăng: `{author}`) {del_status}")

        self._search_cache.clear()

        embed = discord.Embed(
            title="🗑️ ĐÃ GỠ BỎ TÀI LIỆU KHỎI KHO TRA CỨU!",
            description=(
                f"Đã gỡ bỏ thành công **{len(removed_docs)}** tài liệu theo yêu cầu của {interaction.user.mention}:\n\n"
                + "\n".join(removed_docs) +
                "\n\n✨ *Kho tra cứu và thống kê dung lượng đã được đồng bộ sạch sẽ.*"
            ),
            color=0xE74C3C,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        if interaction.channel and isinstance(interaction.channel, discord.TextChannel):
            await self.clean_search_channel(interaction.channel)


async def setup(bot: commands.Bot) -> None:
    cog = DocumentSearchCog(bot)
    await bot.add_cog(cog)
    bot.add_view(DocumentSearchControlView(cog))
