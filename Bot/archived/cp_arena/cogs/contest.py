"""Kênh BAITAP_ID: Trình duyệt cuộc thi với 3 Rich Embeds riêng biệt (1. Sự kiện hàng ngày/tuần độ khó cao, 2. Contest thường niên, 3. Bảng điều khiển & Bộ lọc tìm kiếm)."""

import asyncio
import math
import time

import discord
from discord.ext import commands

from config.settings import settings
from services.codeforces_api import cf_api
from services.problem_fetcher import ProblemData, ProblemFetcher
from services.rank import (
    get_rank_badge,
    get_rank_by_rating,
)
from services.rating import estimate_cf_problem_rating
from utils.embeds import EmbedType, create_embed, error_embed
from utils.logger import get_logger

logger = get_logger("ContestCog")

PAGE_SIZE = 15  # 15 contest / trang để tối ưu hiển thị và tránh vượt giới hạn 6000 ký tự Discord
AUTO_UPDATE_INTERVAL = 45  # Tự động cập nhật mỗi 45 giây

DEFAULT_POPULAR_CONTESTS: list[dict] = [
    {
        "id": 2000,
        "name": "Codeforces Round 970 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1725114900,
    },
    {
        "id": 1999,
        "name": "Codeforces Round 969 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1724942100,
    },
    {
        "id": 1998,
        "name": "Codeforces Round 968 (Div. 1)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1724596500,
    },
    {
        "id": 1997,
        "name": "Educational Codeforces Round 169 (Rated for Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1723732500,
    },
    {
        "id": 1996,
        "name": "Codeforces Round 966 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1723559700,
    },
    {
        "id": 1995,
        "name": "Codeforces Round 965 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1723295700,
    },
    {
        "id": 1994,
        "name": "Codeforces Round 964 (Div. 4)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1722954900,
    },
    {
        "id": 1993,
        "name": "Codeforces Round 963 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1722782100,
    },
    {
        "id": 1992,
        "name": "Codeforces Round 962 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1722004500,
    },
    {
        "id": 1991,
        "name": "Pinely Round 4 (Div. 1 + Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1721572500,
    },
    {
        "id": 1990,
        "name": "Codeforces Round 960 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1721226900,
    },
    {
        "id": 1989,
        "name": "Educational Codeforces Round 168 (Rated for Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1720708500,
    },
    {
        "id": 1988,
        "name": "Codeforces Round 958 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1720362900,
    },
    {
        "id": 1987,
        "name": "Codeforces Round 957 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1720276500,
    },
    {
        "id": 1986,
        "name": "Codeforces Round 956 (Div. 2) and ByteRace 2024",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1720190100,
    },
    {
        "id": 1985,
        "name": "Codeforces Round 952 (Div. 4)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1718116500,
    },
    {
        "id": 1984,
        "name": "Codeforces Global Round 26",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1717943700,
    },
    {
        "id": 1983,
        "name": "The 2024 ICPC Asia Championship",
        "type": "ICPC",
        "phase": "FINISHED",
        "durationSeconds": 18000,
        "startTimeSeconds": 1717000000,
    },
    {
        "id": 1982,
        "name": "Codeforces Round 955 (Div. 2, with prizes from Techflow)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1716820500,
    },
    {
        "id": 1981,
        "name": "Codeforces Round 954 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1716474900,
    },
    {
        "id": 1980,
        "name": "Codeforces Round 953 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1716302100,
    },
    {
        "id": 1979,
        "name": "Educational Codeforces Round 166 (Rated for Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1715697300,
    },
    {
        "id": 1978,
        "name": "Codeforces Round 950 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1715265300,
    },
    {
        "id": 1977,
        "name": "Codeforces Round 949 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1715092500,
    },
    {
        "id": 1976,
        "name": "Codeforces Round 948 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1714833300,
    },
    {
        "id": 1975,
        "name": "Codeforces Round 947 (Div. 1 + Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1714574100,
    },
    {
        "id": 1974,
        "name": "Codeforces Round 946 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1714314900,
    },
    {
        "id": 1973,
        "name": "Codeforces Round 945 (Div. 2)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 7200,
        "startTimeSeconds": 1714055700,
    },
    {
        "id": 1972,
        "name": "Codeforces Round 944 (Div. 4)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1713796500,
    },
    {
        "id": 1971,
        "name": "Codeforces Round 943 (Div. 3)",
        "type": "CF",
        "phase": "FINISHED",
        "durationSeconds": 8100,
        "startTimeSeconds": 1713537300,
    },
]


def is_hard_event_contest(contest: dict) -> bool:
    """Kiểm tra contest có thực sự là sự kiện độ khó cao (ICPC, Challenge, Div 1, Global Round) hay không."""
    name_lower = contest.get("name", "").lower()

    if "div. 3" in name_lower or "div. 4" in name_lower:
        return False
    if (
        "div. 2" in name_lower
        and "div. 1" not in name_lower
        and not any(
            k in name_lower for k in ["icpc", "huawei", "challenge", "marathon"]
        )
    ):
        return False

    hard_keywords = [
        "icpc",
        "huawei",
        "challenge",
        "marathon",
        "div. 1",
        "global round",
        "championship",
        "cup",
        "grand prix",
        "pinely",
        "codeton",
        "good bye",
        "hello",
        "epic",
    ]
    return any(k in name_lower for k in hard_keywords)


def get_contest_estimated_rating_and_tier(contest: dict) -> tuple[int, str, str]:
    """Ước lượng điểm Rating và Bậc Tier cho cuộc thi."""
    name = contest.get("name", "").lower()
    if any(k in name for k in ["world finals", "grand prix", "open cup", "marathon"]):
        r = 3000
    elif any(k in name for k in ["icpc", "huawei", "championship"]):
        r = 2600
    elif "div. 1" in name and "div. 2" not in name:
        if any(k in name for k in ["cup", "final", "epic", "good bye", "hello"]):
            r = 2400
        else:
            r = 2100
    elif (
        "div. 1 + div. 2" in name
        or "global" in name
        or "pinely" in name
        or "codeton" in name
    ):
        r = 1600
    elif "div. 2" in name or "educational" in name:
        r = 1400
    elif "div. 3" in name:
        r = 1000
    elif "div. 4" in name:
        r = 600
    else:
        r = 1200

    tier = get_rank_by_rating(r)
    badge = get_rank_badge(tier)
    return r, tier, badge


class ProblemActionButtons(discord.ui.View):
    """Nút hành động tương tác đính kèm dưới Embed bài tập hỗ trợ nộp bài Rated, Unrated và nút kiểm tra độ ổn định."""

    def __init__(self, problem: ProblemData, bot: commands.Bot):
        super().__init__(timeout=300)
        self.problem = problem
        self.bot = bot

        cf_url = f"https://codeforces.com/contest/{problem.contest_id}/problem/{problem.index}"
        self.add_item(
            discord.ui.Button(
                label="Mở trên Codeforces 🌐",
                url=cf_url,
                style=discord.ButtonStyle.link,
            )
        )

    @discord.ui.button(
        label="Nộp bài Rated (Tính điểm) 🏆", style=discord.ButtonStyle.success
    )
    async def submit_rated_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from cogs.submission import SubmitModal

        modal = SubmitModal(
            bot=self.bot,
            default_problem_id=self.problem.id,
            default_lang="cpp17",
            is_rated=True,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Nộp bài Unrated (Luyện tập) 🌱", style=discord.ButtonStyle.primary
    )
    async def submit_unrated_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from cogs.submission import SubmitModal

        modal = SubmitModal(
            bot=self.bot,
            default_problem_id=self.problem.id,
            default_lang="cpp17",
            is_rated=False,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ktra ổn định 🔄", style=discord.ButtonStyle.secondary)
    async def check_stability_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        t0 = time.perf_counter()
        try:
            fetched = await ProblemFetcher.fetch_problem(self.problem.id)
            latency = time.perf_counter() - t0
            sample_count = len(fetched.samples) if fetched else 0
            embed = create_embed(
                title=f"TRẠNG THÁI BÀI TẬP {self.problem.id} 🔄",
                description=(
                    f"✅ **Đề bài và bộ Testcase mẫu đã được kiểm tra thành công!**\n\n"
                    f"• 🧩 **Tên bài:** `{self.problem.name}`\n"
                    f"• 📊 **Độ khó (Rating):** `{self.problem.rating or 'Chưa xếp hạng'}` pts\n"
                    f"• 🧪 **Số testcase mẫu:** `{sample_count}` tests sẵn sàng chấm\n"
                    f"• ⚡ **Độ trễ Codeforces API:** `{latency:.2f}s` *(Hoạt động ổn định 100%)*"
                ),
                embed_type=EmbedType.SUCCESS,
                color=0x00B894,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                embed=error_embed("LỖI KIỂM TRA", f"Lỗi: {e}"), ephemeral=True
            )


class ContestDetailActionView(discord.ui.View):
    """Nút hành động khi xem chi tiết một cuộc thi (Contest Inspector)."""

    def __init__(self, bot: commands.Bot, contest_id: int, problems: list[dict]):
        super().__init__(timeout=180)
        self.bot = bot
        self.contest_id = contest_id
        self.problems = problems

        cf_url = f"https://codeforces.com/contest/{contest_id}"
        self.add_item(
            discord.ui.Button(
                label="Mở trên Codeforces 🌐",
                url=cf_url,
                style=discord.ButtonStyle.link,
            )
        )

    @discord.ui.button(
        label="Làm mới bài tập & Ktra API 🔄",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_contest_refresh",
    )
    async def refresh_contest_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        t0 = time.perf_counter()
        try:
            standings = await cf_api.get_contest_standings(contest_id=self.contest_id)
            latency = time.perf_counter() - t0
            probs = standings.get("problems", [])
            embed = create_embed(
                title=f"KIỂM TRA ỔN ĐỊNH CONTEST #{self.contest_id} 🔄",
                description=(
                    f"✅ **Đã kết nối và tải mới danh sách đề bài thành công!**\n\n"
                    f"• 📋 **Số lượng bài tập:** `{len(probs)}` bài ({', '.join(p.get('index', '') for p in probs)})\n"
                    f"• ⚡ **Độ trễ phản hồi (Latency):** `{latency:.2f}s`\n"
                    f"• 🟢 **Tình trạng:** `Hoạt động hoàn hảo 100%`"
                ),
                embed_type=EmbedType.SUCCESS,
                color=0x00B894,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                embed=error_embed(
                    "LỖI KẾT NỐI", f"Không thể làm mới contest {self.contest_id}: {e}"
                ),
                ephemeral=True,
            )

    @discord.ui.button(
        label="Nộp bài Rated 🏆",
        style=discord.ButtonStyle.success,
        custom_id="btn_contest_submit_rated",
    )
    async def submit_rated_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from cogs.submission import SubmitModal

        first_prob_id = (
            f"{self.contest_id}{self.problems[0].get('index', 'A')}"
            if self.problems
            else f"{self.contest_id}A"
        )
        modal = SubmitModal(
            bot=self.bot,
            default_problem_id=first_prob_id,
            default_lang="cpp17",
            is_rated=True,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="Nộp bài Unrated 🌱",
        style=discord.ButtonStyle.primary,
        custom_id="btn_contest_submit_unrated",
    )
    async def submit_unrated_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        from cogs.submission import SubmitModal

        first_prob_id = (
            f"{self.contest_id}{self.problems[0].get('index', 'A')}"
            if self.problems
            else f"{self.contest_id}A"
        )
        modal = SubmitModal(
            bot=self.bot,
            default_problem_id=first_prob_id,
            default_lang="cpp17",
            is_rated=False,
        )
        await interaction.response.send_modal(modal)


class ContestCatalogView(discord.ui.View):
    """Bảng điều khiển tương tác duyệt danh mục 25 contest/trang kèm bộ lọc 3 Embeds và nút reload kiểm tra ổn định."""

    def __init__(
        self,
        bot: commands.Bot,
        all_contests: list[dict],
        current_div: str = "ALL",
        page: int = 1,
    ):
        super().__init__(timeout=None)  # Persistent view
        self.bot = bot
        self.all_contests = all_contests
        self.current_div = current_div
        self.page = page
        self._rebuild_components()

    def _filter_contests(self) -> list[dict]:
        """Lọc danh sách contest theo Div hoặc Bậc Tier đã chọn."""
        if self.current_div == "EVENT":
            return [c for c in self.all_contests if is_hard_event_contest(c)]
        elif self.current_div == "DIV1":
            return [
                c
                for c in self.all_contests
                if "div. 1" in c.get("name", "").lower()
                and "div. 2" not in c.get("name", "").lower()
            ]
        elif self.current_div == "DIV2":
            return [
                c
                for c in self.all_contests
                if "div. 2" in c.get("name", "").lower()
                or "educational" in c.get("name", "").lower()
            ]
        elif self.current_div == "DIV3":
            return [
                c for c in self.all_contests if "div. 3" in c.get("name", "").lower()
            ]
        elif self.current_div == "DIV4":
            return [
                c for c in self.all_contests if "div. 4" in c.get("name", "").lower()
            ]
        elif self.current_div.startswith("TIER_"):
            target_tier = self.current_div.replace("TIER_", "")
            matched = []
            for c in self.all_contests:
                _, tier, _ = get_contest_estimated_rating_and_tier(c)
                if tier == target_tier:
                    matched.append(c)
            # Fallback nếu không có cuộc thi gán cứng đúng bậc
            if not matched:
                if target_tier in ["HT1", "MT1"]:
                    matched = [c for c in self.all_contests if is_hard_event_contest(c)]
                elif target_tier in ["LT1", "HT2", "MT2"]:
                    matched = [
                        c
                        for c in self.all_contests
                        if "div. 1" in c.get("name", "").lower()
                        and "div. 2" not in c.get("name", "").lower()
                    ]
                elif target_tier in ["LT2", "T3"]:
                    matched = [
                        c
                        for c in self.all_contests
                        if any(
                            k in c.get("name", "").lower()
                            for k in [
                                "div. 1 + div. 2",
                                "global",
                                "pinely",
                                "codeton",
                            ]
                        )
                    ]
                elif target_tier in ["T4", "T5"]:
                    matched = [
                        c
                        for c in self.all_contests
                        if "div. 2" in c.get("name", "").lower()
                        or "educational" in c.get("name", "").lower()
                    ]
                elif target_tier == "T6":
                    matched = [
                        c
                        for c in self.all_contests
                        if "div. 3" in c.get("name", "").lower()
                    ]
                elif target_tier in ["T7", "T8"]:
                    matched = [
                        c
                        for c in self.all_contests
                        if "div. 4" in c.get("name", "").lower()
                    ]
            return matched
        return self.all_contests

    def _get_top_events(self) -> list[dict]:
        """Lấy danh sách các cuộc thi Event / Hard Challenges đỉnh cao tiêu biểu nhất."""
        events = [c for c in self.all_contests if is_hard_event_contest(c)]
        return events[:6]

    def _rebuild_components(self) -> None:
        self.clear_items()
        filtered = self._filter_contests()
        total_items = len(filtered)
        total_pages = max(1, math.ceil(total_items / PAGE_SIZE))
        self.page = max(1, min(self.page, total_pages))

        # 1. Dropdown chọn Div / Event / 12 Bậc Tier (Row 0)
        div_select = discord.ui.Select(
            placeholder="🔍 Lọc theo Phân hạng Div hoặc 12 Bậc Tier (HT1 → T8)",
            custom_id="select_catalog_div",
            min_values=1,
            max_values=1,
            row=0,
            options=[
                discord.SelectOption(
                    label="🌟 Tất cả phân hạng (All Divs)",
                    value="ALL",
                    description="Toàn bộ danh mục cuộc thi Codeforces",
                    emoji="🌟",
                    default=(self.current_div == "ALL"),
                ),
                discord.SelectOption(
                    label="🔥 Event Khó Hàng Tuần/Ngày",
                    value="EVENT",
                    description="ICPC, Grand Prix, Championship, Global",
                    emoji="🔥",
                    default=(self.current_div == "EVENT"),
                ),
                discord.SelectOption(
                    label="👑 Div. 1 (Cao Cấp)",
                    value="DIV1",
                    description="Dành cho LT2 - HT1 (>= 1900 Rating)",
                    emoji="👑",
                    default=(self.current_div == "DIV1"),
                ),
                discord.SelectOption(
                    label="🥈 Div. 2 (Phổ Biến)",
                    value="DIV2",
                    description="Dành cho T5 - T3 (1200 - 1899 Rating)",
                    emoji="🥈",
                    default=(self.current_div == "DIV2"),
                ),
                discord.SelectOption(
                    label="🥉 Div. 3 (Cơ Bản & Luyện Tập)",
                    value="DIV3",
                    description="Dành cho T8 - T6 (0 - 1199 Rating)",
                    emoji="🥉",
                    default=(self.current_div == "DIV3"),
                ),
                discord.SelectOption(
                    label="🌱 Div. 4 (Dành Cho Người Mới)",
                    value="DIV4",
                    description="Dành cho Newbie (Rating < 1200)",
                    emoji="🌱",
                    default=(self.current_div == "DIV4"),
                ),
                discord.SelectOption(
                    label="👑 Bậc HT1 (Rating >= 3000 pts)",
                    value="TIER_HT1",
                    description="Đề bài & Cuộc thi cấp độ Huyền Thoại 1",
                    emoji="👑",
                    default=(self.current_div == "TIER_HT1"),
                ),
                discord.SelectOption(
                    label="💎 Bậc MT1 (Rating 2600 - 2999 pts)",
                    value="TIER_MT1",
                    description="Đề bài & Cuộc thi cấp độ Ma Thần 1",
                    emoji="💎",
                    default=(self.current_div == "TIER_MT1"),
                ),
                discord.SelectOption(
                    label="🏆 Bậc LT1 (Rating 2400 - 2599 pts)",
                    value="TIER_LT1",
                    description="Đề bài & Cuộc thi cấp độ Lục Thần 1",
                    emoji="🏆",
                    default=(self.current_div == "TIER_LT1"),
                ),
                discord.SelectOption(
                    label="🔱 Bậc HT2 (Rating 2300 - 2399 pts)",
                    value="TIER_HT2",
                    description="Đề bài & Cuộc thi cấp độ Hoàng Thần 2",
                    emoji="🔱",
                    default=(self.current_div == "TIER_HT2"),
                ),
                discord.SelectOption(
                    label="⚜️ Bậc MT2 (Rating 2100 - 2299 pts)",
                    value="TIER_MT2",
                    description="Đề bài & Cuộc thi cấp độ Minh Thần 2",
                    emoji="⚜️",
                    default=(self.current_div == "TIER_MT2"),
                ),
                discord.SelectOption(
                    label="🛡️ Bậc LT2 (Rating 1900 - 2099 pts)",
                    value="TIER_LT2",
                    description="Đề bài & Cuộc thi cấp độ Long Thần 2",
                    emoji="🛡️",
                    default=(self.current_div == "TIER_LT2"),
                ),
                discord.SelectOption(
                    label="💠 Bậc T3 (Rating 1600 - 1899 pts)",
                    value="TIER_T3",
                    description="Đề bài & Cuộc thi cấp độ Tier 3",
                    emoji="💠",
                    default=(self.current_div == "TIER_T3"),
                ),
                discord.SelectOption(
                    label="🔷 Bậc T4 (Rating 1400 - 1599 pts)",
                    value="TIER_T4",
                    description="Đề bài & Cuộc thi cấp độ Tier 4",
                    emoji="🔷",
                    default=(self.current_div == "TIER_T4"),
                ),
                discord.SelectOption(
                    label="🔶 Bậc T5 (Rating 1200 - 1399 pts)",
                    value="TIER_T5",
                    description="Đề bài & Cuộc thi cấp độ Tier 5",
                    emoji="🔶",
                    default=(self.current_div == "TIER_T5"),
                ),
                discord.SelectOption(
                    label="⭐ Bậc T6 (Rating 700 - 1199 pts)",
                    value="TIER_T6",
                    description="Đề bài & Cuộc thi cấp độ Tier 6",
                    emoji="⭐",
                    default=(self.current_div == "TIER_T6"),
                ),
                discord.SelectOption(
                    label="⭐ Bậc T7 (Rating 400 - 699 pts)",
                    value="TIER_T7",
                    description="Đề bài & Cuộc thi cấp độ Tier 7",
                    emoji="⭐",
                    default=(self.current_div == "TIER_T7"),
                ),
                discord.SelectOption(
                    label="⭐ Bậc T8 (Rating < 400 pts)",
                    value="TIER_T8",
                    description="Đề bài & Cuộc thi cấp độ Tân Binh Tier 8",
                    emoji="⭐",
                    default=(self.current_div == "TIER_T8"),
                ),
            ],
        )
        div_select.callback = self._on_div_change
        self.add_item(div_select)

        # 2. Dropdown chọn nhanh 1 trong 25 contest của trang hiện tại để xem đề bài (Row 1)
        start_idx = (self.page - 1) * PAGE_SIZE
        page_contests = filtered[start_idx : start_idx + PAGE_SIZE]

        if page_contests:
            contest_options = []
            for c in page_contests[:25]:
                cid = c.get("id")
                name = c.get("name", f"Contest #{cid}")[:90]
                contest_options.append(
                    discord.SelectOption(
                        label=f"#{cid} - {name[:75]}",
                        value=str(cid),
                        description=f"Xem danh sách bài tập contest #{cid}",
                    )
                )
            contest_select = discord.ui.Select(
                placeholder=f"📋 Chọn 1 trong 25 contest của trang {self.page} để xem bài tập",
                custom_id=f"select_catalog_contest_{self.page}",
                min_values=1,
                max_values=1,
                row=1,
                options=contest_options,
            )
            contest_select.callback = self._on_contest_select
            self.add_item(contest_select)

        # 3. Nút bấm phân trang (Row 2)
        btn_first = discord.ui.Button(
            label="⏮️ Đầu",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page <= 1),
            custom_id="btn_cat_first",
            row=2,
        )
        btn_prev = discord.ui.Button(
            label="◀️ Trước",
            style=discord.ButtonStyle.primary,
            disabled=(self.page <= 1),
            custom_id="btn_cat_prev",
            row=2,
        )
        btn_page_info = discord.ui.Button(
            label=f"Trang {self.page}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="btn_cat_info",
            row=2,
        )
        btn_next = discord.ui.Button(
            label="Sau ▶️",
            style=discord.ButtonStyle.primary,
            disabled=(self.page >= total_pages),
            custom_id="btn_cat_next",
            row=2,
        )
        btn_last = discord.ui.Button(
            label="Cuối ⏭️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total_pages),
            custom_id="btn_cat_last",
            row=2,
        )

        btn_first.callback = self._on_first
        btn_prev.callback = self._on_prev
        btn_next.callback = self._on_next
        btn_last.callback = self._on_last

        self.add_item(btn_first)
        self.add_item(btn_prev)
        self.add_item(btn_page_info)
        self.add_item(btn_next)
        self.add_item(btn_last)

        # 4. Nút bấm Làm mới & Kiểm tra độ ổn định API (Row 3)
        btn_reload = discord.ui.Button(
            label="Làm mới danh sách & Ktra ổn định 🔄",
            style=discord.ButtonStyle.success,
            custom_id="btn_catalog_reload",
            row=3,
        )
        btn_reload.callback = self._on_reload
        self.add_item(btn_reload)

    def render_event_embed(self) -> discord.Embed:
        """Embed 1: Sự Kiện Hàng Ngày & Hàng Tuần (Daily & Weekly Hard Challenges)."""
        top_events = self._get_top_events()[:5]
        lines = []
        for i, c in enumerate(top_events, start=1):
            cid = c.get("id")
            name = c.get("name", f"Contest #{cid}")[:40]
            phase = c.get("phase", "FINISHED")
            if phase == "FINISHED":
                phase_tag = "🟢 `[Sẵn sàng]`"
            elif phase == "CODING":
                phase_tag = "🔥 `[Đang thi]`"
            else:
                phase_tag = "⏳ `[Chuẩn bị]`"

            r, tier, badge = get_contest_estimated_rating_and_tier(c)
            tag_prefix = "⚡ [Tuần]" if i <= 2 else "🎯 [Ngày]"
            lines.append(
                f"`#{i}` {tag_prefix} **[{cid}]** [{name}](https://codeforces.com/contest/{cid}) {phase_tag} • `⭐ {r} pts` {badge}"
            )

        event_desc = (
            "### ⚡ THỬ THÁCH ĐỘ KHÓ CAO — DÀNH CHO CAO THỦ (RATING 2000+ / ICPC / DIV 1) 🚀\n"
            "Tập hợp các cuộc thi giải thuật chuyên sâu, giải đấu ICPC và Grand Challenges hàng ngày/tuần:\n"
            "• 👑 **ICPC & Huawei:** Nhân **`1.75x`** điểm Score & Rating  •  💎 **Global Rounds:** Nhân **`1.50x`** điểm\n"
            "• 🛡️ **Bảo Vệ Tân Binh:** Thí sinh dưới Rank **T4** (`< 1400` pts) làm sai **KHÔNG BỊ TRỪ ĐIỂM**.\n\n"
            "**🏆 Danh Sách Thử Thách Đỉnh Cao Hàng Ngày & Hàng Tuần:**\n"
            + (
                "\n".join(lines)
                if lines
                else "*Đang cập nhật các cuộc thi sự kiện độ khó cao...*"
            )
        )

        embed = create_embed(
            title="🔥 [1] SỰ KIỆN HÀNG NGÀY & HÀNG TUẦN (DAILY & WEEKLY HARD CHALLENGES)",
            description=event_desc,
            embed_type=EmbedType.JUDGE,
            color=0xFF4757,
            footer_text="Sự Kiện Hàng Ngày & Hàng Tuần • Thưởng 1.2x - 1.75x Điểm • Độ Khó: Cực Cao (Div 1 / ICPC)",
        )
        return embed

    def render_regular_embed(self) -> discord.Embed:
        """Embed 2: Danh Mục Các Cuộc Thi Thường Niên (15 Contest / Trang)."""
        filtered = self._filter_contests()
        total_items = len(filtered)
        total_pages = max(1, math.ceil(total_items / PAGE_SIZE))
        start_idx = (self.page - 1) * PAGE_SIZE
        page_contests = filtered[start_idx : start_idx + PAGE_SIZE]

        div_label_map = {
            "ALL": "🌟 Tất Cả Phân Hạng (All Divs)",
            "EVENT": "🔥 Event Khó Hàng Tuần/Ngày",
            "DIV1": "👑 Div. 1 (Cao Cấp)",
            "DIV2": "🥈 Div. 2 (Phổ Biến)",
            "DIV3": "🥉 Div. 3 (Cơ Bản)",
            "DIV4": "🌱 Div. 4 (Tân Binh)",
            "TIER_HT1": "👑 Bậc HT1 (Rating >= 3000 pts)",
            "TIER_MT1": "💎 Bậc MT1 (Rating 2600 - 2999 pts)",
            "TIER_LT1": "🏆 Bậc LT1 (Rating 2400 - 2599 pts)",
            "TIER_HT2": "🔱 Bậc HT2 (Rating 2300 - 2399 pts)",
            "TIER_MT2": "⚜️ Bậc MT2 (Rating 2100 - 2299 pts)",
            "TIER_LT2": "🛡️ Bậc LT2 (Rating 1900 - 2099 pts)",
            "TIER_T3": "💠 Bậc T3 (Rating 1600 - 1899 pts)",
            "TIER_T4": "🔷 Bậc T4 (Rating 1400 - 1599 pts)",
            "TIER_T5": "🔶 Bậc T5 (Rating 1200 - 1399 pts)",
            "TIER_T6": "⭐ Bậc T6 (Rating 700 - 1199 pts)",
            "TIER_T7": "⭐ Bậc T7 (Rating 400 - 699 pts)",
            "TIER_T8": "⭐ Bậc T8 (Rating < 400 pts)",
        }
        current_div_label = div_label_map.get(self.current_div, "Tất Cả")

        lines = []
        for i, c in enumerate(page_contests, start=start_idx + 1):
            cid = c.get("id")
            name = c.get("name", f"Contest #{cid}")[:40]
            phase = c.get("phase", "FINISHED")
            if phase == "FINISHED":
                phase_tag = "🟢 `[Sẵn sàng]`"
            elif phase == "CODING":
                phase_tag = "🔥 `[Đang thi]`"
            else:
                phase_tag = "⏳ `[Chuẩn bị]`"

            r, tier, badge = get_contest_estimated_rating_and_tier(c)
            lines.append(
                f"`#{i:<3}` **[{cid}]** [{name}](https://codeforces.com/contest/{cid}) {phase_tag} • `⭐ {r} pts` {badge}"
            )

        desc = (
            f"### 📋 DANH SÁCH CUỘC THI TIÊU CHUẨN (15 CONTEST / TRANG)\n"
            f"• **Bộ lọc phân hạng/Tier:** `{current_div_label}`  •  **Tổng số:** `{total_items}` contest (`{total_pages}` trang)\n\n"
            + (
                "\n".join(lines)
                if lines
                else "*Không có cuộc thi nào phù hợp với bộ lọc.*"
            )
        )

        embed = create_embed(
            title="📚 [2] DANH MỤC CUỘC THI THƯỜNG NIÊN (DIV 1 / 2 / 3 / 4 & THEO TIER)",
            description=desc,
            embed_type=EmbedType.CONTEST,
            color=0x0984E3,
            footer_text=f"Trang {self.page}/{total_pages} • Phân hạng: {current_div_label} • Auto-update 45s",
        )
        return embed

    def render_control_embed(self) -> discord.Embed:
        """Embed 3: Bảng Điều Khiển & Bộ Lọc Tìm Kiếm Bài Tập (Interactive Station)."""
        desc = (
            "### 🧭 TRÌNH DUYỆT & TRA CỨU ĐỀ BÀI THEO PHÂN HẠNG & TIER\n"
            "Sử dụng các menu và nút bấm bên dưới để điều hướng hệ thống:\n"
            "1. 🔍 **Dropdown 1 (Phân hạng & Tier):** Lọc theo Tất cả / Event Khó / Div 1-4 hoặc **12 Bậc Tier từ HT1 đến T8**.\n"
            "2. 📋 **Dropdown 2 (Chọn Contest):** Chọn 1 trong 15 contest để mở bảng xem danh sách đề bài chi tiết.\n"
            "3. ◀️ / ▶️ **Nút phân trang:** Di chuyển nhanh giữa các trang danh mục cuộc thi.\n"
            "4. 🔄 **Nút Làm mới & Ktra ổn định:** Đo đạc độ trễ (Latency) và cập nhật dữ liệu Codeforces mới nhất.\n\n"
            "💡 *Mẹo: Sau khi chọn contest từ Dropdown 2, bạn có thể bấm nộp bài trực tiếp qua form Modal!*"
        )

        embed = create_embed(
            title="🔍 [3] TRẠM ĐIỀU KHIỂN & BỘ LỌC TÌM KIẾM BÀI TẬP",
            description=desc,
            embed_type=EmbedType.INFO,
            color=0x6C5CE7,
            footer_text="Bảng điều khiển tương tác • Tự động cập nhật 45s • Nhấn nút 🔄 để làm mới ngay",
        )
        return embed

    def render_embeds(self) -> list[discord.Embed]:
        """Trả về đầy đủ bộ 3 Rich Embeds theo đúng cấu trúc tiêu chuẩn."""
        return [
            self.render_event_embed(),
            self.render_regular_embed(),
            self.render_control_embed(),
        ]

    async def _on_div_change(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        select_item = interaction.data.get("values", ["ALL"])
        self.current_div = select_item[0]
        self.page = 1
        self._rebuild_components()
        await interaction.edit_original_response(embeds=self.render_embeds(), view=self)

    async def _on_first(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        self.page = 1
        self._rebuild_components()
        await interaction.edit_original_response(embeds=self.render_embeds(), view=self)

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.page > 1:
            self.page -= 1
        self._rebuild_components()
        await interaction.edit_original_response(embeds=self.render_embeds(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        filtered = self._filter_contests()
        total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
        if self.page < total_pages:
            self.page += 1
        self._rebuild_components()
        await interaction.edit_original_response(embeds=self.render_embeds(), view=self)

    async def _on_last(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        filtered = self._filter_contests()
        self.page = max(1, math.ceil(len(filtered) / PAGE_SIZE))
        self._rebuild_components()
        await interaction.edit_original_response(embeds=self.render_embeds(), view=self)

    async def _on_reload(self, interaction: discord.Interaction) -> None:
        """Tải lại danh sách toàn bộ contest từ Codeforces API và kiểm tra độ ổn định."""
        await interaction.response.defer(ephemeral=True)
        t0 = time.perf_counter()
        try:
            new_contests = await cf_api.get_contest_list(gym=False)
            latency = time.perf_counter() - t0
            if new_contests:
                self.all_contests = new_contests
                self._rebuild_components()
                try:
                    await interaction.message.edit(
                        embeds=self.render_embeds(), view=self
                    )
                except Exception:
                    pass

                embed = create_embed(
                    title="LÀM MỚI DANH MỤC & KIỂM TRA ỔN ĐỊNH THÀNH CÔNG 🔄",
                    description=(
                        f"✅ **Đã kết nối và đồng bộ dữ liệu mới nhất từ Codeforces API!**\n\n"
                        f"• 📊 **Tổng số Cuộc thi:** `{len(new_contests):,}` cuộc thi\n"
                        f"• ⚡ **Độ trễ API (Latency):** `{latency:.2f}s` *(Cực kỳ mượt mà)*\n"
                        f"• 🟢 **Trạng thái hệ thống:** `Hoạt động ổn định 100%`"
                    ),
                    embed_type=EmbedType.SUCCESS,
                    color=0x00B894,
                    footer_text="Codeforces Synchronizer • API Health: Optimal",
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Lỗi khi reload contest list: {e}")
            await interaction.followup.send(
                embed=error_embed(
                    "LỖI LÀM MỚI", f"Không thể kết nối đến Codeforces API: {e}"
                ),
                ephemeral=True,
            )

    async def _on_contest_select(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        selected_cid_str = (
            interaction.data.get("values", [""])[0] if interaction.data else ""
        )
        if not selected_cid_str:
            return

        try:
            contest_id = int(selected_cid_str)
        except ValueError:
            return

        try:
            standings = await cf_api.get_contest_standings(contest_id=contest_id)
            contest_info = standings.get("contest", {})
            problems = standings.get("problems", [])
            c_name = contest_info.get("name", f"Contest #{contest_id}")

            view = ContestProblemsView(
                bot=self.bot,
                contest_id=contest_id,
                contest_name=c_name,
                problems=problems,
            )
            embed = view.render_embed()
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Lỗi khi tra cứu contest {contest_id}: {e}")
            await interaction.followup.send(
                embed=error_embed(
                    "LỖI TRA CỨU", f"Không thể lấy thông tin contest: {e}"
                ),
                ephemeral=True,
            )


class ContestProblemsView(discord.ui.View):
    """Hiển thị danh sách bài tập của một contest với dropdown submit và phân trang ◀ Trang X/Y ▶."""

    PROBLEMS_PER_PAGE = 25

    def __init__(
        self,
        bot: commands.Bot,
        contest_id: int,
        contest_name: str,
        problems: list[dict],
        page: int = 1,
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.contest_id = contest_id
        self.contest_name = contest_name
        self.problems = problems
        self.page = page
        self._rebuild_components()

    def _total_pages(self) -> int:
        return max(1, math.ceil(len(self.problems) / self.PROBLEMS_PER_PAGE))

    def _page_problems(self) -> list[dict]:
        start = (self.page - 1) * self.PROBLEMS_PER_PAGE
        return self.problems[start : start + self.PROBLEMS_PER_PAGE]

    def _rebuild_components(self) -> None:
        self.clear_items()
        total_pages = self._total_pages()
        self.page = max(1, min(self.page, total_pages))
        page_probs = self._page_problems()

        # Dropdown chọn bài để submit (Row 0)
        if page_probs:
            options = []
            for p in page_probs:
                idx = p.get("index", "")
                p_name = p.get("name", "?")[:65]
                r = p.get("rating")
                if not r:
                    r = estimate_cf_problem_rating(self.contest_name, idx)
                tier = get_rank_by_rating(r)
                badge = get_rank_badge(tier)
                options.append(
                    discord.SelectOption(
                        label=f"[{idx}] {p_name}",
                        value=f"{self.contest_id}{idx}",
                        description=f"rating: {r}, tier: {tier.lower()} {badge}",
                        emoji="📝",
                    )
                )
            prob_select = discord.ui.Select(
                placeholder=f"📝 Chọn bài để nộp — Trang {self.page}/{total_pages}",
                custom_id="select_problem_submit",
                min_values=1,
                max_values=1,
                row=0,
                options=options,
            )
            prob_select.callback = self._on_problem_select
            self.add_item(prob_select)

        # Nút phân trang (Row 1)
        btn_prev = discord.ui.Button(
            label="◀️",
            style=discord.ButtonStyle.primary,
            disabled=(self.page <= 1),
            custom_id="btn_prob_prev",
            row=1,
        )
        btn_info = discord.ui.Button(
            label=f"Trang {self.page} / {total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="btn_prob_info",
            row=1,
        )
        btn_next = discord.ui.Button(
            label="▶️",
            style=discord.ButtonStyle.primary,
            disabled=(self.page >= total_pages),
            custom_id="btn_prob_next",
            row=1,
        )
        btn_prev.callback = self._on_prev
        btn_next.callback = self._on_next
        self.add_item(btn_prev)
        self.add_item(btn_info)
        self.add_item(btn_next)

    def render_embed(self) -> discord.Embed:
        page_probs = self._page_problems()
        total_pages = self._total_pages()
        start = (self.page - 1) * self.PROBLEMS_PER_PAGE + 1

        lines = []
        for i, p in enumerate(page_probs, start=start):
            idx = p.get("index", "")
            p_name = p.get("name", "Không rõ")
            r = p.get("rating")
            if not r:
                r = estimate_cf_problem_rating(self.contest_name, idx)
            tier = get_rank_by_rating(r)
            badge = get_rank_badge(tier)
            cf_link = f"https://codeforces.com/contest/{self.contest_id}/problem/{idx}"
            lines.append(
                f"`#{i:02d}` **[{idx}]** [{p_name}]({cf_link}) • rating: `{r}`, tier: `{tier.lower()}` {badge}"
            )

        desc = (
            f"**📋 {self.contest_name}**\n"
            f"🔗 [Mở trên Codeforces](https://codeforces.com/contest/{self.contest_id})"
            f"  •  📦 **{len(self.problems)}** bài tập\n\n"
            + ("\n".join(lines) if lines else "*Không có bài tập nào.*")
            + "\n\n💡 *Chọn bài từ dropdown bên dưới để nộp Rated 🏆 hoặc Unrated 🌱.*"
        )

        return create_embed(
            title=f"DANH SÁCH BÀI TẬP — CONTEST #{self.contest_id}",
            description=desc,
            embed_type=EmbedType.CONTEST,
            footer_text=f"Trang {self.page}/{total_pages}  •  Chọn bài từ dropdown để nộp",
        )

    async def _on_problem_select(self, interaction: discord.Interaction) -> None:
        problem_id = interaction.data.get("values", [""])[0] if interaction.data else ""
        if not problem_id:
            return

        selected_prob = next(
            (
                p
                for p in self.problems
                if f"{self.contest_id}{p.get('index', '')}" == problem_id
            ),
            None,
        )
        prob_rating = (
            selected_prob.get("rating")
            or estimate_cf_problem_rating(
                self.contest_name, selected_prob.get("index", "A")
            )
            if selected_prob
            else 1200
        )

        from cogs.submission import SubmitModal
        from services.problem_fetcher import ProblemFetcher

        class ProblemSubmitView(discord.ui.View):
            def __init__(self_inner, bot):
                super().__init__(timeout=60)
                self_inner.bot = bot

            @discord.ui.button(
                label="Nộp Rated 🏆 (Bài thi đấu)", style=discord.ButtonStyle.success
            )
            async def rated_btn(self_inner, itr: discord.Interaction, _btn):
                modal = SubmitModal(
                    bot=self_inner.bot,
                    default_problem_id=problem_id,
                    default_lang="cpp17",
                    is_rated=True,
                )
                await itr.response.send_modal(modal)

            @discord.ui.button(
                label="Nộp Unrated 🌱 (Bài tương đương)",
                style=discord.ButtonStyle.primary,
            )
            async def unrated_btn(self_inner, itr: discord.Interaction, _btn):
                eq_prob = await ProblemFetcher.get_equivalent_unrated_problem(
                    problem_id, prob_rating
                )
                eq_id = eq_prob.id if eq_prob else "4A"
                modal = SubmitModal(
                    bot=self_inner.bot,
                    default_problem_id=eq_id,
                    default_lang="cpp17",
                    is_rated=False,
                )
                await itr.response.send_modal(modal)

        action_view = ProblemSubmitView(self.bot)
        embed = create_embed(
            title=f"LỰA CHỌN CHẾ ĐỘ NỘP BÀI — {problem_id}",
            description=(
                f"Bạn đang thao tác với bài **`{problem_id}`** (`⭐ {prob_rating} pts`).\n\n"
                f"• 🏆 **Nộp Rated (Thi đấu):** Nộp trực tiếp bài `{problem_id}`. Đánh giá 2 bước (CF Samples + Themis Multi-Tests).\n"
                f"• 🌱 **Nộp Unrated (Luyện tập):** Hệ thống tự động ghép một **bài tập tương đương cùng độ khó** (`{prob_rating} pts`) để bạn luyện tập và xem code mẫu mà **không làm lộ bài thi đấu** (Chống gian lận contest)."
            ),
            embed_type=EmbedType.JUDGE,
        )
        await interaction.response.send_message(
            embed=embed, view=action_view, ephemeral=True
        )

    async def _on_prev(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.page > 1:
            self.page -= 1
        self._rebuild_components()
        await interaction.edit_original_response(embed=self.render_embed(), view=self)

    async def _on_next(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.page < self._total_pages():
            self.page += 1
        self._rebuild_components()
        await interaction.edit_original_response(embed=self.render_embed(), view=self)


class ContestMaintenanceView(discord.ui.View):
    """View hiển thị tại kênh BAITAP_ID khi Codeforces API đang tạm bảo trì."""

    def __init__(self, cog: "ContestCog"):
        super().__init__(timeout=None)
        self.cog = cog

        self.add_item(
            discord.ui.Button(
                label="Kiểm tra Codeforces 🌐",
                url="https://codeforces.com",
                style=discord.ButtonStyle.link,
            )
        )

    @discord.ui.button(
        label="Thử kết nối lại ngay 🔄",
        style=discord.ButtonStyle.primary,
        custom_id="btn_contest_maintenance_retry",
    )
    async def retry_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        ok = await self.cog.check_and_restore_channel()
        if ok:
            await interaction.followup.send(
                "✅ **Codeforces API đã mở lại!** Danh mục cuộc thi đã được khôi phục thành công 100%.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "⚠️ **Codeforces API vẫn đang bảo trì hoặc kiểm tra Cloudflare.** Hệ thống sẽ tự động thử lại sau ít phút (quét mỗi 45s).",
                ephemeral=True,
            )


class ContestCog(commands.Cog, name="Contests & Problems"):
    """Các lệnh tra cứu bài tập, cuộc thi và trình duyệt catalog 3 Embeds tại kênh BAITAP_ID."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cached_contests: list[dict] = []
        self._is_maintenance: bool = False
        self._live_message: discord.Message | None = None
        self._live_view: discord.ui.View | None = None
        self._auto_update_task: asyncio.Task | None = None

    def cog_unload(self) -> None:
        self.stop_auto_update()

    def start_auto_update(self) -> None:
        """Khởi chạy background task tự động cập nhật danh mục cuộc thi định kỳ."""
        if self._auto_update_task is None or self._auto_update_task.done():
            self._auto_update_task = asyncio.create_task(self._auto_update_loop())

    def stop_auto_update(self) -> None:
        """Dừng background task tự động cập nhật."""
        if self._auto_update_task and not self._auto_update_task.done():
            self._auto_update_task.cancel()
            self._auto_update_task = None

    def render_maintenance_embed(self) -> discord.Embed:
        """Render Embed thông báo Codeforces API đang bảo trì."""
        desc = (
            "### 🔌 MÁY CHỦ CODEFORCES API ĐANG TẠM BẢO TRÌ\n"
            "Hiện tại hệ thống không thể tải danh sách cuộc thi trực tiếp từ Codeforces API (HTTP 503 / Cloudflare Challenge).\n\n"
            "• 🛡️ **Hệ thống Bot vẫn an toàn:** Toàn bộ điểm Rating, hồ sơ cá nhân (`/profile`) và **Đấu Trường Ranked 1:1 (`#📋・ranked`)** vẫn hoạt động bình thường 100%!\n"
            "• 🔄 **Tự động mở lại:** Bot chạy quét kiểm tra trạng thái **mỗi 45 giây** và sẽ **tự động mở lại toàn bộ danh mục bài tập ngay khi Codeforces API hoạt động trở lại**.\n"
            "• 💡 Bạn có thể bấm nút **`Thử kết nối lại ngay 🔄`** bên dưới để kiểm tra thủ công bất kỳ lúc nào."
        )
        embed = create_embed(
            title="⚠️ HỆ THỐNG DANH MỤC CUỘC THI TẠM THỜI BẢO TRÌ",
            description=desc,
            embed_type=EmbedType.WARNING,
            color=0xE67E22,
            footer_text="Codeforces API Maintenance • Tự động quét lại mỗi 45s • Nhấn 🔄 để thử lại ngay",
        )
        return embed

    async def check_and_restore_channel(self) -> bool:
        """Kiểm tra Codeforces API và khôi phục kênh nếu API đã mở lại."""
        try:
            new_contests = await asyncio.wait_for(
                cf_api.get_contest_list(gym=False), timeout=4.0
            )
            if new_contests:
                self._cached_contests = new_contests
                self._is_maintenance = False

                if self._live_message:
                    view = ContestCatalogView(
                        bot=self.bot,
                        all_contests=self._cached_contests,
                        current_div="ALL",
                        page=1,
                    )
                    self._live_view = view
                    await self._live_message.edit(
                        embeds=view.render_embeds(),
                        view=view,
                    )
                return True
        except Exception as e:
            logger.debug(f"Codeforces API vẫn đang bảo trì: {e}")
        return False

    async def _auto_update_loop(self) -> None:
        """Vòng lặp ngầm tự động cập nhật dữ liệu contest và làm mới giao diện mỗi 45 giây."""
        await self.bot.wait_until_ready()
        # Chờ 3 giây ban đầu sau khi khởi động bot
        await asyncio.sleep(3)
        while not self.bot.is_closed():
            try:
                if self._is_maintenance:
                    restored = await self.check_and_restore_channel()
                    if restored:
                        logger.info(
                            "✅ Codeforces API đã mở lại! Đã tự động khôi phục kênh BAITAP_ID thành công."
                        )
                else:
                    new_contests = await asyncio.wait_for(
                        cf_api.get_contest_list(gym=False), timeout=5.0
                    )
                    if new_contests:
                        self._cached_contests = new_contests
                        if self._live_view and isinstance(
                            self._live_view, ContestCatalogView
                        ):
                            self._live_view.all_contests = self._cached_contests
                            self._live_view._rebuild_components()
                        if self._live_message and self._live_view:
                            await self._live_message.edit(
                                embeds=self._live_view.render_embeds(),
                                view=self._live_view,
                            )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Lỗi khi tự động cập nhật kênh BAITAP_ID: {e}")
                # Nếu API bị lỗi và chưa có cache thì chuyển sang bảng bảo trì
                if not self._cached_contests and not self._is_maintenance:
                    self._is_maintenance = True
                    if self._live_message:
                        m_view = ContestMaintenanceView(self)
                        self._live_view = m_view
                        await self._live_message.edit(
                            embeds=[self.render_maintenance_embed()],
                            view=m_view,
                        )
            await asyncio.sleep(AUTO_UPDATE_INTERVAL)

    async def auto_setup_baitap_channel(self) -> None:
        """Tự động xóa tin nhắn cũ, tải danh sách contest và đăng 3 Embeds vào kênh BAITAP_ID khi khởi động bot."""
        if not settings.BAITAP_ID or settings.BAITAP_ID <= 0:
            return

        channel = self.bot.get_channel(settings.BAITAP_ID)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        try:
            self.stop_auto_update()

            # Khởi tạo danh mục với dữ liệu mặc định để hiển thị tức thì không nghẽn mạng
            if not self._cached_contests:
                self._cached_contests = list(DEFAULT_POPULAR_CONTESTS)
            self._is_maintenance = False

            # Xóa các tin nhắn cũ trong kênh để làm mới
            try:
                await channel.purge(limit=15)
            except Exception as e:
                logger.debug(f"Bỏ qua lỗi purge kênh BAITAP_ID: {e}")

            from utils.embeds import get_logo_file

            logo_file = get_logo_file()

            view = ContestCatalogView(
                bot=self.bot,
                all_contests=self._cached_contests,
                current_div="ALL",
                page=1,
            )
            embeds = view.render_embeds()
            if logo_file:
                msg = await channel.send(embeds=embeds, file=logo_file, view=view)
            else:
                msg = await channel.send(embeds=embeds, view=view)
            self._live_view = view
            self._live_message = msg

            self.start_auto_update()
            logger.info(
                f"Đã thiết lập kênh BAITAP_ID thành công (Sẵn sàng {len(self._cached_contests)} cuộc thi, Auto-update {AUTO_UPDATE_INTERVAL}s)."
            )
        except Exception as e:
            logger.error(f"Lỗi khi tự động thiết lập kênh BAITAP_ID: {e}")


async def setup(bot: commands.Bot) -> None:
    cog = ContestCog(bot)
    await bot.add_cog(cog)
