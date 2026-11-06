"""Kênh SUBMIT_ID: Bảng điều khiển nộp bài giải trực tiếp (Mode 2 Sandbox) hỗ trợ Rated, Unrated và Mục Event / Hot Challenges (100% Tiếng Việt)."""

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import settings
from database.database import async_session_factory
from database.repositories.submission_repo import SubmissionRepository
from services.judge import JudgeService
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("SubmissionCog")

LANGUAGE_CHOICES = [
    # ── 1. Top 5 Ngôn Ngữ Trọng Tâm Hàng Đầu ──
    app_commands.Choice(name="1. C++ (GNU++17)", value="cpp17"),
    app_commands.Choice(name="1. C++ (GNU++20)", value="cpp20"),
    app_commands.Choice(name="1. C++ (GNU++23)", value="cpp23"),
    app_commands.Choice(name="2. Python (CPython 3.x)", value="python3"),
    app_commands.Choice(name="3. PyPy (PyPy 3.x)", value="pypy3"),
    app_commands.Choice(name="4. Java (Java 17+)", value="java"),
    app_commands.Choice(name="5. C (GCC 17/11)", value="c"),
    # ── 2. 5 Ngôn Ngữ Phổ Biến (Ít Dùng Hơn) ──
    app_commands.Choice(name="6. C# (.NET)", value="csharp"),
    app_commands.Choice(name="7. Kotlin (Kotlin/JVM)", value="kotlin"),
    app_commands.Choice(name="8. Rust (rustc 2021)", value="rust"),
    app_commands.Choice(name="9. Go (Golang)", value="go"),
    app_commands.Choice(name="10. Pascal (Free Pascal)", value="pascal"),
    # ── 3. Các Ngôn Ngữ Mở Rộng & Lua ──
    app_commands.Choice(name="Lua (Lua 5.4 / LuaJIT)", value="lua"),
    app_commands.Choice(name="JavaScript (Node.js)", value="javascript"),
    app_commands.Choice(name="Swift", value="swift"),
    app_commands.Choice(name="Ruby", value="ruby"),
    app_commands.Choice(name="D (DMD/LDC)", value="d"),
    app_commands.Choice(name="Scala (Scala/JVM)", value="scala"),
    app_commands.Choice(name="Haskell (GHC)", value="haskell"),
]


class SubmitModal(discord.ui.Modal):
    """Form Modal nhập thông tin nộp bài giải hỗ trợ tùy chọn Rated, Unrated và Event."""

    def __init__(
        self,
        bot: commands.Bot,
        default_problem_id: str = "",
        default_lang: str = "cpp17",
        is_rated: bool = True,
        is_event: bool = False,
    ):
        if is_event:
            modal_title = "Nộp bài Event / Hot Challenge 🔥"
        elif is_rated:
            modal_title = "Nộp bài thi đấu (Rated 🏆)"
        else:
            modal_title = "Nộp bài luyện tập (Unrated 🌱)"

        super().__init__(title=modal_title)
        self.bot = bot
        self.is_rated = is_rated
        self.is_event = is_event

        self.problem_input = discord.ui.TextInput(
            label="Mã bài tập (Ví dụ: 1234A hoặc 1700B)",
            placeholder="Ví dụ: 2251A hoặc 1700A",
            default=default_problem_id,
            required=True,
            max_length=16,
        )
        self.add_item(self.problem_input)

        self.lang_input = discord.ui.TextInput(
            label="Ngôn ngữ (C++, Python, PyPy, Java, C...)",
            placeholder="cpp, py, pypy, java, c, cs, kt, rs, go, js, pas...",
            default=default_lang,
            required=True,
            max_length=20,
        )
        self.add_item(self.lang_input)

        self.code_input = discord.ui.TextInput(
            label="Mã nguồn (Source Code)",
            style=discord.TextStyle.paragraph,
            placeholder='Ví dụ: print("Hello world")',
            required=True,
            max_length=4000,
        )
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        contest_cog = self.bot.get_cog("ContestCog")
        if contest_cog and getattr(contest_cog, "_is_maintenance", False):
            await interaction.response.send_message(
                "🔴 **Chế độ Freedom đang tạm đóng do Codeforces API đang bảo trì!**\n"
                "Bot sẽ tự động mở lại chế độ Freedom ngay khi Codeforces API hoạt động trở lại. Bạn có thể tham gia Đấu Trường Ranked 1:1 trong thời gian này!",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        judge_service = JudgeService(self.bot)

        result = await judge_service.judge_submission(
            user=interaction.user,
            problem_id=self.problem_input.value.strip(),
            language_alias=self.lang_input.value.strip(),
            code=self.code_input.value,
            is_rated=self.is_rated,
            guild=interaction.guild,
        )

        embeds_list = [result.embed]
        if hasattr(result, "analysis_embed") and result.analysis_embed:
            embeds_list.append(result.analysis_embed)

        await interaction.followup.send(embeds=embeds_list, ephemeral=True)


class SubmitChannelControlView(discord.ui.View):
    """Bảng điều khiển nút bấm cố định tại kênh SUBMIT_ID hỗ trợ Nộp bài Rated và Nộp bài Unrated."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot

    @discord.ui.button(
        label="Nộp bài Rated (Thi đấu) 🏆",
        style=discord.ButtonStyle.success,
        custom_id="btn_submit_rated_open",
        row=0,
    )
    async def submit_rated_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        modal = SubmitModal(bot=self.bot, is_rated=True, is_event=False)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Nộp bài Unrated (Luyện tập) 🌱",
        style=discord.ButtonStyle.primary,
        custom_id="btn_submit_unrated_open",
        row=0,
    )
    async def submit_unrated_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        modal = SubmitModal(bot=self.bot, is_rated=False, is_event=False)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Xem lịch sử nộp bài 📜",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_submit_history_view",
        row=1,
    )
    async def view_history_click(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        async with async_session_factory() as session:
            repo = SubmissionRepository(session)
            submissions, total = await repo.get_user_submissions(
                interaction.user.id, page=1, per_page=8
            )

        if total == 0:
            embed = create_embed(
                title="LỊCH SỬ NỘP BÀI",
                description="ℹ️ Bạn chưa có lượt nộp bài nào trên hệ thống.",
                embed_type=EmbedType.INFO,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        total_pages = max(1, (total + 7) // 8)
        lines = []
        for s in submissions:
            dt_str = s.submitted_at.strftime("%d/%m %H:%M")
            mode_badge = "🌐 Mode 1" if s.mode == 1 else "⚖️ Mode 2"
            verdict_icon = (
                "🟢" if "Accepted" in s.verdict or "Chấp nhận" in s.verdict else "🔴"
            )
            lines.append(
                f"`#{s.id:<4}` `[{dt_str}]` `{mode_badge}` **{s.problem_id}** • {verdict_icon} `{s.verdict}` • `{s.execution_time:.2f}s` • `{s.memory:.1f}MB` • `+{s.score} pts`"
            )

        embed = create_embed(
            title=f"LỊCH SỬ NỘP BÀI — {interaction.user.display_name.upper()}",
            description="\n".join(lines),
            embed_type=EmbedType.SUBMISSION,
            footer_text=f"Trang 1/{total_pages} • Tổng cộng {total} lượt nộp",
        )

        view = SubmissionHistoryPaginator(
            user=interaction.user, page=1, total_pages=total_pages
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class SubmissionHistoryPaginator(discord.ui.View):
    """Bảng điều khiển phân trang duyệt lịch sử các lần nộp bài."""

    def __init__(
        self, user: discord.User | discord.Member, page: int, total_pages: int
    ):
        super().__init__(timeout=120)
        self.user = user
        self.page = page
        self.total_pages = total_pages
        self._update_button_states()

    def _update_button_states(self) -> None:
        self.first_btn.disabled = self.page <= 1
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= self.total_pages
        self.last_btn.disabled = self.page >= self.total_pages

    async def _fetch_and_render_page(self, interaction: discord.Interaction) -> None:
        async with async_session_factory() as session:
            repo = SubmissionRepository(session)
            submissions, total = await repo.get_user_submissions(
                self.user.id, page=self.page, per_page=8
            )

        if not submissions:
            embed = create_embed(
                title="LỊCH SỬ NỘP BÀI",
                description="Chưa có dữ liệu bài nộp nào.",
                embed_type=EmbedType.INFO,
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return

        lines = []
        for s in submissions:
            dt_str = s.submitted_at.strftime("%d/%m %H:%M")
            mode_badge = "🌐 Mode 1 (CF)" if s.mode == 1 else "⚖️ Mode 2 (Bot)"
            verdict_icon = (
                "🟢" if "Accepted" in s.verdict or "Chấp nhận" in s.verdict else "🔴"
            )
            lines.append(
                f"`#{s.id:<4}` `[{dt_str}]` `{mode_badge}` **{s.problem_id}** • {verdict_icon} `{s.verdict}` • `{s.execution_time:.2f}s` • `{s.memory:.1f}MB` • `+{s.score} pts`"
            )

        embed = create_embed(
            title=f"LỊCH SỬ NỘP BÀI — {self.user.display_name.upper()}",
            description="\n".join(lines),
            embed_type=EmbedType.SUBMISSION,
            footer_text=f"Trang {self.page}/{self.total_pages} • Tổng cộng {total} lượt nộp",
        )
        self._update_button_states()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = 1
        await self._fetch_and_render_page(interaction)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.page > 1:
            self.page -= 1
        await self._fetch_and_render_page(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if self.page < self.total_pages:
            self.page += 1
        await self._fetch_and_render_page(interaction)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = self.total_pages
        await self._fetch_and_render_page(interaction)


class SubmissionCog(commands.Cog, name="Submissions"):
    """Quản lý trạm nộp bài giải trực tiếp tại kênh SUBMIT_ID và lịch sử bài làm."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @classmethod
    def build_submit_channel_embed(cls) -> discord.Embed:
        """Tạo Rich Embed hướng dẫn nộp bài cố định tại kênh SUBMIT_ID."""
        fields = [
            {
                "name": "🏆 Nộp bài Rated (Thi Đấu & Event):",
                "value": (
                    "• **Tính điểm & Đánh giá 2 bước:** Tính điểm Score và tăng/giảm Rating (pts) theo phong độ thi đấu.\n"
                    "• **Tự động nhận diện Event:** Tự động nhân **`1.2x - 1.75x`** điểm cho bài ICPC / Global / Championship và **bảo vệ Tân Binh dưới T4** không bị trừ điểm.\n"
                    "• **Quy trình 2 bước:** Kiểm tra `≥ 50%` testcases → Đánh giá thứ hạng BXH Contest tương ứng."
                ),
                "inline": False,
            },
            {
                "name": "🌱 Nộp bài Unrated (Luyện Tập & Phân Tích Chuyên Sâu):",
                "value": (
                    "• **Không ảnh hưởng điểm:** Thử nghiệm giải thuật tự do, không thay đổi Rating và Score.\n"
                    "• **📖 Code Mẫu Chuẩn:** Tự động tạo mã nguồn mẫu tham khảo chuẩn theo ngôn ngữ bạn nộp.\n"
                    "• **🔍 Phân tích chi tiết:**\n"
                    "  - *Nếu làm sai:* Chỉ ra từng lỗi sai cụ thể (tràn số, testcase fail, lỗi I/O, trường hợp biên).\n"
                    "  - *Nếu làm đúng:* Phân tích sâu các điểm tối ưu thuật toán, bộ nhớ, Fast I/O và Clean Code."
                ),
                "inline": False,
            },
            {
                "name": "📝 Định dạng mã bài Codeforces:",
                "value": (
                    "• **Mã bài chuẩn:** Gồm `ID Contest` + `Chữ cái bài` (Ví dụ: `2251A`, `1700A`, `4A`).\n"
                    "• Tra cứu mã bài tại kênh <#{BAITAP_ID}>."
                ),
                "inline": False,
            },
            {
                "name": "💻 Ngôn ngữ lập trình được hỗ trợ (17 Ngôn Ngữ):",
                "value": (
                    "• **🌟 Top 5 Trọng tâm:** `C++` (17/20/23), `Python` (CPython 3.x), `PyPy` (3.x JIT), `Java` (17+ OpenJDK), `C` (GCC 17/11).\n"
                    "• **⚡ 5 Ngôn ngữ Phổ biến:** `C#` (.NET), `Kotlin` (JVM), `Rust` (rustc), `Go`, `Pascal` (Free Pascal).\n"
                    "• **🌐 Mở rộng & Khác:** `Lua` (5.4/LuaJIT), `JavaScript` (Node.js), `Swift`, `Ruby`, `D` (DMD), `Scala`, `Haskell` (GHC)."
                ),
                "inline": False,
            },
            {
                "name": "⏱️ Thời gian chờ giữa các lần nộp bài (Cooldown):",
                "value": (
                    "• **Rank `⭐ T8 ➔ 🔷 T4`:** Giãn cách **10 phút** sau mỗi bài nộp.\n"
                    "• **Rank `🔷 T3 ➔ 👑 HT1`:** Giãn cách **5 phút** sau mỗi bài nộp.\n"
                    "• *Quy định áp dụng sau khi hoàn thành bài nộp (Đúng hay Sai đều tính để tránh spam).* "
                ),
                "inline": False,
            },
        ]

        baitap_id = settings.BAITAP_ID
        for f in fields:
            f["value"] = f["value"].replace("{BAITAP_ID}", str(baitap_id))

        embed = create_embed(
            title="TRẠM NỘP BÀI GIẢI TRỰC TIẾP — MODE 2 SANDBOX 📝",
            description="Lựa chọn phương thức nộp bài bên dưới (**🏆 Nộp bài Rated** hoặc **🌱 Nộp bài Unrated**) để bắt đầu.",
            embed_type=EmbedType.JUDGE,
            fields=fields,
            color=0x6C5CE7,
            footer_text="Hệ thống chấm bài Docker Sandbox an toàn • Mode 2 In-Discord Judge",
        )
        return embed

    async def auto_setup_submit_channel(self) -> None:
        """Tự động xóa tin nhắn cũ và đăng bảng nộp bài vào kênh SUBMIT_ID khi bot khởi động."""
        if not settings.SUBMIT_ID or settings.SUBMIT_ID <= 0:
            return

        channel = self.bot.get_channel(settings.SUBMIT_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            # Xóa các tin nhắn cũ trong kênh để làm mới hoàn toàn
            try:
                await channel.purge(limit=50)
            except Exception:
                pass

            from utils.embeds import get_logo_file

            embed = self.build_submit_channel_embed()
            view = SubmitChannelControlView(self.bot)
            logo_file = get_logo_file()
            if logo_file:
                await channel.send(embed=embed, file=logo_file, view=view)
            else:
                await channel.send(embed=embed, view=view)
            logger.info("Đã làm mới và đăng bảng nộp bài trực tiếp vào kênh SUBMIT_ID.")
        except Exception as e:
            logger.error(f"Lỗi khi tự động đăng bảng SUBMIT_ID: {e}")


async def setup(bot: commands.Bot) -> None:
    cog = SubmissionCog(bot)
    await bot.add_cog(cog)
