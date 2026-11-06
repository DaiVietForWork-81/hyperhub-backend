from services.ai_detector import AIDetector
from services.anti_cheat import AntiCheatEngine, AntiCheatReport
"""Service xử lý cơ chế Đấu Trường Ranked 1:1 (Duel Arena), Hàng chờ Matchmaking, Hệ thống 2 Mạng và Sandbox Chấm Điểm."""

import asyncio
import datetime
import os
import random
import re
import shutil
import string
import tempfile
import time
from dataclasses import dataclass, field
import discord
from discord.ext import commands

from config.settings import settings
from database.database import async_session_factory
from database.repositories.user_repo import UserRepository
from judge.checker import OutputChecker
from judge.languages import get_language_by_alias
from judge.sandbox import CodeSandbox
from services.duel_problems import (
    DuelProblem,
    PROBLEM_BANK,
    get_div1_problem,
    get_problem_for_match,
)
from services.rank import (
    get_rank_badge,
    get_rank_by_rating,
    get_rank_index,
    get_rank_name,
)
from services.role_manager import RoleManager
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("DuelService")


def get_streak_bonus_pct(streak: int) -> int:
    """
    Trả về phần trăm điểm thưởng lũy tiến theo chuỗi thắng:
    - 5 chuỗi: +2% điểm
    - 10 chuỗi: +5% điểm
    - 20 chuỗi: +10% điểm
    - 30 trở lên: +15% điểm
    """
    if streak >= 30:
        return 15
    elif streak >= 20:
        return 10
    elif streak >= 10:
        return 5
    elif streak >= 5:
        return 2
    return 0


def calculate_ranked_rating_deltas(
    winner_rank: str,
    loser_rank: str,
    winner_rating: int,
    loser_rating: int,
    winner_lives: int = 2,
    rounds_played: int = 2,
    is_partial_win: bool = False,
    winner_streak: int = 0,
) -> tuple[int, int, str]:
    """
    Tính toán điểm rating thay đổi cho Người Thắng và Người Thua theo Phương án B (Cân bằng & Ổn định)
    kết hợp Performance & Độ dài trận đấu (Stamina Modifier: 5 -> 15 pts):
    
    1. Cơ số điểm theo chênh lệch Tier:
       - Cùng Tier: Base Win +60, Base Loss -60
       - Thắng người Hơn Tier (Kèo dưới lật kèo): Base Win +80, Thua người Hơn Tier: Base Loss -50
       - Thắng người Kém Tier (Kèo trên gặp kèo dưới): Base Win +50, Thua người Kém Tier: Base Loss -80

    2. Bonus chênh lệch Rating thực tế:
       - rating_diff = loser_rating - winner_rating
       - bonus = clamp(round(rating_diff / 25), -20, +20)

    3. Performance & Độ dài trận đấu (Stamina Modifier):
       - Trận tiêu chuẩn kết thúc sau 2 chặng.
       - Mỗi chặng kéo dài thêm (> 2 chặng) tạo biến động 5 pts (tối đa 15 pts):
         * Kèo dưới kéo dài trận: Thắng được +thêm (5-15 pts), Thua được -ít hơn (5-15 pts).
         * Kèo trên bị kéo dài trận: Thắng bị -bớt (5-15 pts), Thua bị -nặng hơn (5-15 pts).

    4. Tỷ lệ mạng bảo toàn:
       - 2 mạng (❤️❤️): 100%
       - 1 mạng (❤️): 75%

    5. Cơ chế Partial Win (Cả 2 đều làm sai, người đúng nhiều test hơn thắng):
       - Giảm trừ 50% - 85% số điểm tùy theo rank (chỉ nhận 15% - 50% điểm).
    """
    from services.rank import RANK_ORDER

    w_idx = RANK_ORDER.index(winner_rank) if winner_rank in RANK_ORDER else 0
    l_idx = RANK_ORDER.index(loser_rank) if loser_rank in RANK_ORDER else 0

    if l_idx > w_idx:
        # Người thắng đánh bại người HƠN TIER (Kèo dưới thắng)
        base_win = 80
        base_loss = 80
        matchup_desc = f"🔥 Kèo Dưới Lật Kèo ({winner_rank} vs {loser_rank})"
    elif l_idx < w_idx:
        # Người thắng đánh bại người KÉM TIER (Kèo trên thắng)
        base_win = 50
        base_loss = 50
        matchup_desc = f"⚔️ Kèo Trên Thắng Trận ({winner_rank} vs {loser_rank})"
    else:
        # CÙNG TIER
        base_win = 60
        base_loss = 60
        matchup_desc = f"⚖️ Đồng Hạng Cân Não (Cùng Tier {winner_rank})"

    # Bonus theo khoảng cách rating thực tế giữa 2 người
    rating_diff = loser_rating - winner_rating
    bonus = max(-20, min(20, round(rating_diff / 25)))

    # Performance / Độ dài trận đấu (Stamina Modifier: 5 -> 15 pts)
    extra_rounds = max(0, rounds_played - 2)
    stamina_pts = min(15, extra_rounds * 5)
    stamina_desc = ""

    if stamina_pts > 0:
        if l_idx > w_idx or (l_idx == w_idx and rating_diff > 50):
            # Kèo dưới thắng sau trận marathon -> Thưởng thêm stamina_pts
            win_pool = max(20, base_win + bonus + stamina_pts)
            loss_pool = max(20, base_loss + bonus + stamina_pts)
            stamina_desc = f" • ⏱️ Trận kéo dài {rounds_played} chặng (+{stamina_pts} pts kiên cường)"
        elif l_idx < w_idx or (l_idx == w_idx and rating_diff < -50):
            # Kèo trên thắng chật vật sau trận marathon -> Giảm bớt stamina_pts; Kèo dưới thua được giảm trừ
            win_pool = max(20, base_win + bonus - stamina_pts)
            loss_pool = max(20, base_loss + bonus - stamina_pts)
            stamina_desc = f" • ⏱️ Trận kéo dài {rounds_played} chặng ({-stamina_pts} pts chật vật)"
        else:
            win_pool = max(20, base_win + bonus)
            loss_pool = max(20, base_loss + bonus)
            stamina_desc = f" • ⏱️ Trận kéo dài {rounds_played} chặng"
    else:
        win_pool = max(20, base_win + bonus)
        loss_pool = max(20, base_loss + bonus)

    if winner_lives >= 2:
        winner_delta = int(round(win_pool * 1.0))
        lives_text = "100% (Bảo toàn 2 mạng ❤️❤️)"
    else:
        winner_delta = int(round(win_pool * 0.75))
        lives_text = "75% (Còn 1 mạng ❤️💔)"

    loser_delta = -int(round(loss_pool))

    partial_desc = ""
    if is_partial_win:
        # Cả 2 đều làm sai (không ai AC 100%), người đúng nhiều test hơn thắng
        # Giảm trừ 50% - 85% số điểm tùy theo rank (chỉ nhận 15% - 50%)
        reduction_ratio = 0.50 + (w_idx / 11.0) * 0.35  # 50% (T8) đến 85% (HT1)
        partial_multiplier = 1.0 - reduction_ratio
        winner_delta = max(5, int(round(winner_delta * partial_multiplier)))
        loser_delta = -max(5, int(round(abs(loser_delta) * partial_multiplier)))
        partial_desc = f" • 🥉 Giảm trừ {int(reduction_ratio * 100)}% điểm (Cả 2 đều chưa AC)"

    streak_desc = ""
    bonus_pct = get_streak_bonus_pct(winner_streak)
    if bonus_pct > 0:
        bonus_pts = int(round(winner_delta * (bonus_pct / 100.0)))
        winner_delta += bonus_pts
        streak_desc = f" • 🔥 Chuỗi {winner_streak} trận (+{bonus_pct}% = +{bonus_pts} pts)"

    return winner_delta, loser_delta, f"{matchup_desc} • {lives_text}{stamina_desc}{partial_desc}{streak_desc}"


@dataclass
class RoundHistoryItem:
    """Lưu trữ lịch sử kết quả của từng chặng đấu."""

    round_number: int
    problem_title: str
    problem_tier: str
    p1_passed: int
    p1_total: int
    p1_score: float
    p2_passed: int
    p2_total: int
    p2_score: float
    p1_lives_after: int
    p2_lives_after: int


class SurrenderConfirmView(discord.ui.View):
    """View xác nhận khi người chơi dùng lệnh .close để đầu hàng."""

    def __init__(self, duel_session: "DuelSession", player: discord.Member):
        super().__init__(timeout=30)
        self.duel_session = duel_session
        self.player = player

    @discord.ui.button(
        label="🏳️ Xác Nhận Đầu Hàng",
        style=discord.ButtonStyle.danger,
        custom_id="btn_confirm_surrender",
    )
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                "❌ Bạn không phải là người yêu cầu đầu hàng!", ephemeral=True
            )
            return
        await interaction.response.defer()
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await self.duel_session.handle_surrender(self.player)

    @discord.ui.button(
        label="❌ Hủy",
        style=discord.ButtonStyle.secondary,
        custom_id="btn_cancel_surrender",
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                "❌ Bạn không phải là người yêu cầu đầu hàng!", ephemeral=True
            )
            return
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.response.send_message(
            "✅ Đã hủy yêu cầu đầu hàng. Trận đấu tiếp tục!", ephemeral=True
        )


class DuelEditorialFallbackView(discord.ui.View):
    """View hiển thị nút bấm xem lời giải & phân tích thuật toán khi thí sinh tắt DM."""

    def __init__(self, target_user: discord.Member, embeds: list[discord.Embed]):
        super().__init__(timeout=180)
        self.target_user = target_user
        self.embeds = embeds

    @discord.ui.button(
        label="📖 Xem Lời Giải & Phân Tích (Cá Nhân)",
        style=discord.ButtonStyle.primary,
        custom_id="btn_view_editorial_fallback",
    )
    async def view_editorial(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message(
                f"❌ Nút này chỉ dành riêng cho {self.target_user.mention}!", ephemeral=True
            )
            return
        await interaction.response.send_message(embeds=self.embeds[:10], ephemeral=True)


def detect_code_language(text: str) -> tuple[bool, str, str]:
    """
    Tự động nhận dạng xem một tin nhắn Discord là Code nộp bài hay Tin nhắn trò chuyện thông thường:
    - Nếu là code: Trả về (True, lang_alias, clean_code)
    - Nếu là tin nhắn chat bình thường: Trả về (False, "", "")
    """
    raw = text.strip()
    if not raw or len(raw) < 15:
        return False, "", ""

    # 1. Kiểm tra Markdown Code Blocks (```lang ... ```)
    code_block_match = re.search(r"```([a-zA-Z0-9_+#]*)\s*\n?([\s\S]*?)```", raw)
    if code_block_match:
        lang_tag = code_block_match.group(1).lower().strip()
        code_content = code_block_match.group(2).strip()
        if len(code_content) >= 10:
            if lang_tag in ["cpp", "c++", "cc", "cxx"]:
                return True, "cpp20", code_content
            elif lang_tag in ["py", "python", "python3", "pypy"]:
                return True, "python3", code_content
            elif lang_tag in ["java"]:
                return True, "java", code_content
            elif lang_tag in ["c"]:
                return True, "c", code_content
            elif lang_tag in ["pas", "pascal"]:
                return True, "pascal", code_content
            elif lang_tag in ["cs", "csharp"]:
                return True, "csharp", code_content
            elif lang_tag in ["rs", "rust"]:
                return True, "rust", code_content
            elif lang_tag in ["go", "golang"]:
                return True, "go", code_content
            elif lang_tag in ["js", "javascript", "ts", "typescript"]:
                return True, "javascript", code_content
            else:
                # Tự đoán ngôn ngữ từ nội dung trong code block
                return True, _guess_lang_from_content(code_content), code_content

    # 2. Kiểm tra mã nguồn gửi trực tiếp (Raw Code không dùng dấu ```)
    # Các dấu hiệu mạnh của C/C++
    cpp_signals = ["#include", "using namespace", "int main(", "std::", "cin >>", "cout <<", "ios_base::sync_with_stdio", "vector<"]
    # Các dấu hiệu mạnh của Python
    py_signals = ["import sys", "from sys import", "def solve(", "def main(", "sys.stdin.read", "sys.stdin.readline", "if __name__ =="]
    # Các dấu hiệu mạnh của Java
    java_signals = ["public class", "public static void main", "import java.util", "Scanner sc = new Scanner", "BufferedReader br"]
    # Các dấu hiệu của Pascal
    pas_signals = ["program ", "var ", "begin", "readln(", "writeln("]

    cpp_count = sum(1 for s in cpp_signals if s in raw)
    py_count = sum(1 for s in py_signals if s in raw)
    java_count = sum(1 for s in java_signals if s in raw)
    pas_count = sum(1 for s in pas_signals if s.lower() in raw.lower())

    if cpp_count >= 2 or ("#include" in raw and "main(" in raw):
        return True, "cpp20", raw
    if py_count >= 2 or ("def " in raw and "return" in raw and ":" in raw) or ("import " in raw and "sys.stdin" in raw):
        return True, "python3", raw
    if java_count >= 2 or ("public static void main" in raw):
        return True, "java", raw
    if pas_count >= 3 or ("begin" in raw.lower() and "end." in raw.lower()):
        return True, "pascal", raw

    # Nếu chỉ có 1 tín hiệu yếu nhưng có cấu trúc code nhiều dòng với ngoặc nhọn hoặc thụt lề
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if len(lines) >= 5:
        semicolon_count = sum(1 for line in lines if line.endswith(";"))
        if semicolon_count >= 3:
            return True, "cpp20", raw

    return False, "", ""


def _guess_lang_from_content(code: str) -> str:
    """Đoán ngôn ngữ lập trình từ nội dung chuỗi code."""
    if "#include" in code or "cin >>" in code or "std::" in code or "cout <<" in code:
        return "cpp20"
    if "def " in code or "import sys" in code or "print(" in code:
        return "python3"
    if "public class" in code or "System.out.println" in code:
        return "java"
    if "begin" in code.lower() and "end" in code.lower():
        return "pascal"
    return "cpp20"


class DuelSession:
    """Quản lý một phiên đấu 1:1 giữa hai thí sinh trong kênh riêng."""

    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        player1: discord.Member,
        player2: discord.Member,
        p1_ranked_rank: str,
        p1_ranked_rating: int,
        p2_ranked_rank: str,
        p2_ranked_rating: int,
        is_custom_match: bool = False,
        custom_tier: str | None = None,
    ):
        self.bot = bot
        self.guild = guild
        self.player1 = player1
        self.player2 = player2
        self.p1_ranked_rank = p1_ranked_rank
        self.p1_ranked_rating = p1_ranked_rating
        self.p2_ranked_rank = p2_ranked_rank
        self.p2_ranked_rating = p2_ranked_rating
        self.is_custom_match = is_custom_match
        self.custom_tier = custom_tier.upper() if custom_tier else None

        self.match_code = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=6)
        )
        self.channel: discord.TextChannel | None = None
        self.is_active = True

        # Hệ thống mạng sinh lực (2 mạng mỗi người)
        self.p1_lives = 2
        self.p2_lives = 2
        self.current_round = 1
        self.user_preferred_lang: dict[int, str] = {
            player1.id: "cpp",
            player2.id: "python",
        }

        self.current_problem: DuelProblem | None = None
        self.round_timer_task: asyncio.Task | None = None
        self.round_submissions: dict[int, dict] = {}
        self.history: list[RoundHistoryItem] = []
        # Track các bài đã dùng trong trận này để không lặp lại
        self.used_problem_ids: set[str] = set()
        self.problems_played: list[DuelProblem] = []

        # Trạng thái thi đấu: Chuẩn bị (15s chat tự do) & Tập trung (Giữ im lặng)
        self.in_prep_phase: bool = False
        self.focus_mode: bool = False
        self.both_failed_partial_win: bool = False

        # Hệ thống ghi nhật ký toàn diện (Telemetry & Match Transcript)
        self.round_started_at: datetime.datetime | None = None
        self.match_started_at: datetime.datetime = datetime.datetime.now(datetime.timezone.utc)
        self.chat_logs: list[dict] = []
        self.submission_details: list[dict] = []

        # Theo dõi tỉ lệ thắng động (Dynamic Win Probability Analytics)
        from services.special_roles import calculate_win_probability
        self.p1_start_prob, self.p2_start_prob = calculate_win_probability(
            self.p1_ranked_rating, self.p2_ranked_rating, 2, 2
        )
        self.p1_min_prob = self.p1_start_prob
        self.p2_min_prob = self.p2_start_prob
        self.p1_max_prob = self.p1_start_prob
        self.p2_max_prob = self.p2_start_prob
        self.had_two_vs_one: bool = False
        self.who_had_two_vs_one: int | None = None

        # Quản lý ẩn/hiện danh mục (Cộng đồng, Tài liệu, Voice chat) trong lúc thi Ranked
        self.categories_hidden: bool = False
        self.original_category_overwrites: dict[tuple[int, int], discord.PermissionOverwrite | None] = {}

    async def _hide_contestant_categories(self) -> None:
        """Ẩn các danh mục quy định (Cộng đồng, Tài liệu, Voice chat) đối với 2 thí sinh trong lúc thi Ranked."""
        if self.is_custom_match or self.categories_hidden:
            return

        hidden_cat_ids = getattr(
            settings,
            "RANKED_HIDDEN_CATEGORY_IDS",
            [1534147161091211414, 1534147951797080174, 1534148003701719070],
        )
        if not hidden_cat_ids:
            return

        import inspect

        for cat_id in hidden_cat_ids:
            try:
                category = None
                if hasattr(self.guild, "get_channel"):
                    category = self.guild.get_channel(cat_id)
                if not category and hasattr(self.guild, "fetch_channel"):
                    try:
                        res = self.guild.fetch_channel(cat_id)
                        category = await res if inspect.isawaitable(res) else res
                    except Exception:
                        category = None

                if not category:
                    continue

                for player in (self.player1, self.player2):
                    if not player or not hasattr(player, "id"):
                        continue
                    key = (cat_id, player.id)
                    # Lưu lại phân quyền ban đầu nếu có
                    if hasattr(category, "overwrites") and isinstance(category.overwrites, dict):
                        self.original_category_overwrites[key] = category.overwrites.get(player)

                    if hasattr(category, "set_permissions"):
                        res = category.set_permissions(
                            player,
                            view_channel=False,
                            connect=False,
                            read_messages=False,
                            reason=f"Ranked 1:1 #{self.match_code}: Ẩn danh mục trong lúc thi đấu",
                        )
                        if inspect.isawaitable(res):
                            await res

                    # Tự động ngắt kết nối voice nếu thí sinh đang ở trong kênh thuộc danh mục bị ẩn
                    if hasattr(player, "voice") and player.voice and getattr(player.voice, "channel", None):
                        v_ch = player.voice.channel
                        v_cat_id = getattr(v_ch, "category_id", None)
                        if v_cat_id == cat_id or getattr(v_ch, "id", None) == cat_id:
                            if hasattr(player, "move_to"):
                                try:
                                    res_mv = player.move_to(
                                        None,
                                        reason=f"Ranked 1:1 #{self.match_code}: Tự động ngắt kết nối voice chat",
                                    )
                                    if inspect.isawaitable(res_mv):
                                        await res_mv
                                except Exception as vm_err:
                                    logger.debug(f"Không thể ngắt kết nối voice của {getattr(player, 'display_name', player.id)}: {vm_err}")
            except Exception as cat_err:
                logger.warning(f"Lỗi khi ẩn danh mục {cat_id} cho trận #{self.match_code}: {cat_err}")

        self.categories_hidden = True
        logger.info(f"Đã ẩn các danh mục voice/tài liệu đối với 2 thí sinh trận #{self.match_code}")

    async def _restore_contestant_categories(self) -> None:
        """Khôi phục quyền truy cập các danh mục cho 2 thí sinh sau khi trận đấu Ranked kết thúc."""
        if not self.categories_hidden:
            return

        self.categories_hidden = False
        hidden_cat_ids = getattr(
            settings,
            "RANKED_HIDDEN_CATEGORY_IDS",
            [1534147161091211414, 1534147951797080174, 1534148003701719070],
        )

        import inspect

        for cat_id in hidden_cat_ids:
            try:
                category = None
                if hasattr(self.guild, "get_channel"):
                    category = self.guild.get_channel(cat_id)
                if not category and hasattr(self.guild, "fetch_channel"):
                    try:
                        res = self.guild.fetch_channel(cat_id)
                        category = await res if inspect.isawaitable(res) else res
                    except Exception:
                        category = None

                if not category:
                    continue

                for player in (self.player1, self.player2):
                    if not player or not hasattr(player, "id"):
                        continue
                    key = (cat_id, player.id)
                    orig_ow = self.original_category_overwrites.get(key)
                    if hasattr(category, "set_permissions"):
                        res = category.set_permissions(
                            player,
                            overwrite=orig_ow,
                            reason=f"Ranked 1:1 #{self.match_code}: Khôi phục danh mục sau khi kết thúc trận đấu",
                        )
                        if inspect.isawaitable(res):
                            await res
            except Exception as cat_err:
                logger.warning(f"Lỗi khi khôi phục danh mục {cat_id} cho trận #{self.match_code}: {cat_err}")

        logger.info(f"Đã khôi phục các danh mục voice/tài liệu cho 2 thí sinh trận #{self.match_code}")

    async def start(self) -> bool:
        """Khởi tạo kênh duel và bắt đầu trận đấu."""
        category_id = settings.CATEGORY_ID
        category = self.guild.get_channel(category_id) if category_id else None

        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.player1: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True
            ),
            self.player2: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, attach_files=True
            ),
            self.guild.me: discord.PermissionOverwrite(
                read_messages=True, send_messages=True, manage_channels=True
            ),
        }

        # Cấp quyền cho Admin và Giám Khảo nếu có cấu hình
        giam_khao_id = getattr(settings, "GIAM_KHAO_ROLE_ID", 0) or getattr(
            settings, "GIAM_KHAO", 0
        )
        if giam_khao_id > 0:
            gk_role = self.guild.get_role(giam_khao_id)
            if gk_role:
                overwrites[gk_role] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        channel_name = (
            f"🤝・custom-{self.match_code}"
            if self.is_custom_match
            else f"⚔️・duel-{self.match_code}"
        )
        try:
            if category and isinstance(category, discord.CategoryChannel):
                self.channel = await category.create_text_channel(
                    name=channel_name, overwrites=overwrites
                )
            else:
                self.channel = await self.guild.create_text_channel(
                    name=channel_name, overwrites=overwrites
                )
        except Exception as e:
            logger.error(f"Lỗi khi tạo kênh duel: {e}")
            await self._restore_contestant_categories()
            return False

        logger.info(
            f"Đã tạo kênh đấu {'Giao Hữu' if self.is_custom_match else 'Ranked 1:1'}: #{self.channel.name} cho {self.player1.display_name} vs {self.player2.display_name}"
        )

        # Ẩn các danh mục (Cộng đồng, Tài liệu, Voice chat) đối với 2 thí sinh trong lúc thi đấu Ranked
        if not self.is_custom_match:
            await self._hide_contestant_categories()

        try:
            from database.models import DuelMatch
            async with async_session_factory() as session:
                match_rec = DuelMatch(
                    match_code=self.match_code,
                    channel_id=self.channel.id if self.channel else 0,
                    player1_id=self.player1.id,
                    player2_id=self.player2.id,
                    p1_lives=2,
                    p2_lives=2,
                    current_round=1,
                    status="IN_PROGRESS",
                )
                session.add(match_rec)
                await session.commit()
        except Exception as e:
            logger.warning(f"Lỗi ghi nhận DuelMatch khi khởi tạo: {e}")

        # Gửi thông điệp mở đầu và bắt đầu chặng 1
        await self._send_intro_message()
        await asyncio.sleep(4)
        await self._start_round()
        return True

    async def _send_intro_message(self) -> None:
        """Gửi luật thi đấu, 2 mạng, lệnh trong ticket và danh sách ngôn ngữ hỗ trợ."""
        if not self.channel:
            return

        p1_badge = get_rank_badge(self.p1_ranked_rank)
        p2_badge = get_rank_badge(self.p2_ranked_rank)

        if self.is_custom_match:
            welcome_header = (
                f"Chào mừng hai đấu thủ đến với **Trận Đấu Giao Hữu (Custom Match)**!\n\n"
                f"🔴 **Đấu thủ 1:** {self.player1.mention} ({p1_badge} `{self.p1_ranked_rank}` • `{self.p1_ranked_rating} pts`)\n"
                f"🔵 **Đấu thủ 2:** {self.player2.mention} ({p2_badge} `{self.p2_ranked_rank}` • `{self.p2_ranked_rating} pts`)\n"
                f"🎯 **Độ khó đề bài đã chọn:** `⭐ Tier {self.custom_tier or 'T8'}`\n"
                f"🤝 **Chế độ Giao Hữu:** Không cộng/trừ điểm Elo rating, tự do so tài nâng cao tư duy!\n\n"
            )
            embed_title = f"🤝 TRẬN ĐẤU GIAO HỮU #{self.match_code.upper()} (TIER {self.custom_tier or 'T8'})"
            embed_color = 0x3498DB
        else:
            welcome_header = (
                f"Chào mừng hai đấu thủ đến với **Đấu Trường Ranked 1:1**!\n\n"
                f"🔴 **Đấu thủ 1:** {self.player1.mention} ({p1_badge} `{self.p1_ranked_rank}` • `{self.p1_ranked_rating} pts`)\n"
                f"🔵 **Đấu thủ 2:** {self.player2.mention} ({p2_badge} `{self.p2_ranked_rank}` • `{self.p2_ranked_rating} pts`)\n"
                f"📊 **Dự đoán tỉ lệ thắng ban đầu:** 🔴 {self.player1.display_name}: **{self.p1_start_prob}%** │ 🔵 {self.player2.display_name}: **{self.p2_start_prob}%**\n\n"
            )
            embed_title = f"⚔️ TRẬN ĐẤU RANKED 1:1 #{self.match_code.upper()}"
            embed_color = 0x3498DB

        desc = (
            welcome_header +
            f"### 📜 QUY TẮC THI ĐẤU & 2 MẠNG (HEARTS SYSTEM)\n"
            f"1. Mỗi đấu thủ khởi đầu với **2 Mạng (❤️ ❤️)**.\n"
            f"2. Mỗi bài toán là **1 chặng đấu**. Cả 2 người phải hoàn thành bài (hoặc hết giờ) thì mới sang chặng tiếp theo.\n"
            f"3. **Chấm bài tức thì:** Khi một người gửi bài trước, Bot sẽ chạy sandbox test trước và thông báo kết quả trong khi chờ đối thủ.\n"
            f"4. **Đánh giá chặng đấu**:\n"
            f"   • Người làm tốt hơn (tỷ lệ đúng chênh lệch `> 10%`) → Người thua bị **trừ 1 mạng (💔)**.\n"
            f"   • Nếu 2 bên ngang tài ngang sức (chênh lệch `≤ 10%`) → **Hòa chặng**, không ai bị trừ mạng.\n"
            f"5. **Nghỉ giải lao & Gợi ý:** Giữa các chặng có **15 giây nghỉ ngơi** kèm theo **1 gợi ý nhỏ** cho bài tiếp theo!\n"
            f"6. Trận đấu tiếp tục cho đến khi **1 trong 2 người còn 0 mạng**.\n\n"
            f"### ⌨️ CÁC CÂU LỆNH TRONG TICKET\n"
            f"• `.close` : Xin đầu hàng đối thủ (sẽ có nút xác nhận 🏳️)\n"
            f"• `.list` : Xem danh sách các bài/chặng mà 2 người đã làm và điểm số\n"
            f"• `.skip` : Bỏ qua chặng hiện tại, nhận mã code giải mẫu và sang chặng 2\n"
            f"• `.test` : *(Chỉ Bot Owner)* Đóng trận ngay và win test\n\n"
            f"### 💻 CÁC ĐUÔI FILE NGÔN NGỮ HỖ TRỢ (28 NGÔN NGỮ)\n"
            f"• **C/C++**: `.c`, `.cpp`, `.cc`, `.cxx`  •  **Python**: `.py`  •  **Java / Kotlin**: `.java`, `.kt`\n"
            f"• **Pascal**: `.pas`  •  **C# / F#**: `.cs`, `.fs`  •  **Rust / Go**: `.rs`, `.go`  •  **JS/TS**: `.js`, `.ts`\n"
            f"• **Khác**: `.rb`, `.php`, `.hs`, `.d`, `.scala`, `.pl`, `.sh`, `.swift`, `.nim`, `.zig`..."
        )

        embed = discord.Embed(
            title=embed_title,
            description=desc,
            color=embed_color,
        )
        embed.set_footer(text="Hệ Thống Đấu Trường Tự Động • Chuẩn bị phát đề bài...")
        await self.channel.send(
            content=f"{self.player1.mention} {self.player2.mention}", embed=embed
        )

    async def _start_round(self, problem: DuelProblem | None = None, prep_delay: bool = True) -> None:
        """Bắt đầu chặng đấu mới: Chọn đề bài, gửi Embed và bắt đầu đếm ngược thời gian."""
        if not self.channel or not self.is_active:
            return

        self.round_submissions.clear()
        # Hủy timer cũ nếu còn đang chạy
        if self.round_timer_task and not self.round_timer_task.done():
            self.round_timer_task.cancel()

        if self.is_custom_match and self.custom_tier:
            from services.duel_problems import get_problem_by_tier
            self.current_problem = problem or get_problem_by_tier(
                self.custom_tier, exclude_ids=self.used_problem_ids,
                round_index=self.current_round,
            )
        else:
            self.current_problem = problem or get_problem_for_match(
                self.p1_ranked_rank, self.p2_ranked_rank,
                exclude_ids=self.used_problem_ids,
                round_index=self.current_round,
            )
        # Đánh dấu bài này đã được dùng trong trận → không chọn lại
        if self.current_problem:
            self.used_problem_ids.add(self.current_problem.id)
            if self.current_problem not in self.problems_played:
                self.problems_played.append(self.current_problem)

        # Thông báo 15 giây chuẩn bị trước khi phát đề (cho phép trò chuyện tự do)
        if prep_delay:
            self.in_prep_phase = True
            self.focus_mode = False
            escalation_note = ""
            if self.current_round > 1:
                bonus_pct = round((self.current_round - 1) * 1.5, 1)
                escalation_note = f"• 🔥 **Áp lực đấu trường (Chặng {self.current_round}):** Độ khó tăng `+{bonus_pct}%` *(Thử thách leo thang!)*\n"

            prep_embed = discord.Embed(
                title=f"⏳ CHUẨN BỊ BƯỚC VÀO CHẶNG {self.current_round} (15 GIÂY)",
                description=(
                    f"Hai đấu thủ {self.player1.mention} và {self.player2.mention} có **15 giây chuẩn bị & trò chuyện tự do**!\n\n"
                    f"💬 *Trong 15 giây này, hai bạn có thể thoải mái nhắn tin trao đổi với nhau.*\n"
                    f"• **Thời gian làm bài:** `{self.current_problem.time_limit_minutes} phút`\n"
                    f"• **Gợi ý chặng này:** *{self.current_problem.hint}*\n"
                    f"{escalation_note}\n"
                    f"⚠️ **LƯU Ý:** Khi hết 15 giây, đề bài sẽ xuất hiện và hệ thống kích hoạt **Chế Độ Giữ Im Lặng** (mọi tin nhắn chat thông thường sẽ bị chặn và xóa ngay lập tức)!"
                ),
                color=0xF39C12,
            )
            try:
                await self.channel.send(embed=prep_embed)
            except discord.NotFound:
                logger.info(f"Kênh thi đấu #{self.match_code} đã bị đóng/xóa trên Discord. Dừng chặng đấu.")
                self.is_active = False
                if self.channel and self.channel.id in duel_service.active_sessions:
                    duel_service.active_sessions.pop(self.channel.id, None)
                return
            except Exception as e:
                logger.warning(f"Lỗi gửi prep_embed: {e}")
            await asyncio.sleep(15)
            if not self.is_active or not self.channel:
                return

        # Kích hoạt Chế Độ Giữ Im Lặng
        self.in_prep_phase = False
        self.focus_mode = True
        self.round_started_at = datetime.datetime.now(datetime.timezone.utc)
        self.chat_logs.append({
            "timestamp": self.round_started_at,
            "author_id": 0,
            "author_name": "SYSTEM",
            "type": "ROUND_START",
            "content": f"Bắt đầu Chặng {self.current_round}: Bài '{self.current_problem.name}' (Tier {self.current_problem.tier}, Giới hạn {self.current_problem.time_limit_minutes} phút)",
        })

        p1_hearts = "❤️" * self.p1_lives + "💔" * (2 - self.p1_lives)
        p2_hearts = "❤️" * self.p2_lives + "💔" * (2 - self.p2_lives)

        round_header = (
            f"## 🚨 ĐỀ BÀI CHẶNG {self.current_round} ĐÃ XUẤT HIỆN! CHẾ ĐỘ GIỮ IM LẶNG KÍCH HOẠT!\n"
            f"• {self.player1.mention}: **{p1_hearts}** ({self.p1_lives}/2 mạng)\n"
            f"• {self.player2.mention}: **{p2_hearts}** ({self.p2_lives}/2 mạng)\n"
            f"⏱️ **Thời gian làm bài:** `{self.current_problem.time_limit_minutes} phút`\n\n"
            f"🤫 **KHÔNG NHẮN TIN LÚC NÀY!** Mọi tin nhắn trò chuyện thông thường sẽ bị bot tự động xóa.\n"
            f"📤 **2 CÁCH NỘP CODE:**\n"
            f"  1️⃣ **Gửi file code:** Đính kèm file có đuôi `.cpp`, `.py`, `.java`, `.pas`, `.cs`, `.js`...\n"
            f"  2️⃣ **Dán code trực tiếp:** Gửi đoạn code vào kênh chat (dùng ```code``` hoặc raw code).\n"
            f"🔒 **BẢO MẬT TUYỆT ĐỐI:** Tin nhắn/file code sẽ **tự động xóa ngay lập tức** để đối thủ không thấy code!\n"
            f"⚠️ Mỗi người chỉ được nộp **1 LẦN DUY NHẤT** cho chặng này (nộp tiếp sẽ không tính).\n"
            f"*(Gõ `.list` để xem lịch sử, `.close` để đầu hàng)*"
        )

        try:
            problem_embeds = self.current_problem.render_embeds()
            await self.channel.send(content=round_header, embeds=problem_embeds)
        except discord.NotFound:
            logger.info(f"Kênh thi đấu #{self.match_code} đã bị đóng/xóa trên Discord. Tự động hủy phiên đấu.")
            self.is_active = False
            if self.round_timer_task and not self.round_timer_task.done():
                self.round_timer_task.cancel()
            if self.channel and self.channel.id in duel_service.active_sessions:
                duel_service.active_sessions.pop(self.channel.id, None)
            return
        except Exception as e:
            logger.warning(f"Lỗi khi gửi đề bài chặng {self.current_round}: {e}")

        duration_seconds = self.current_problem.time_limit_minutes * 60
        self.round_timer_task = asyncio.create_task(self._round_timer(duration_seconds))

    async def _round_timer(self, seconds: int) -> None:
        """Đếm ngược thời gian chặng đấu."""
        try:
            if seconds > 120:
                await asyncio.sleep(seconds - 120)
                if self.is_active and self.channel:
                    await self.channel.send(
                        "⚠️ **CÒN 2 PHÚT!** Hãy khẩn trương gửi file code để nộp bài trước khi hết giờ!"
                    )
                await asyncio.sleep(120)
            else:
                await asyncio.sleep(seconds)

            if self.is_active:
                await self._evaluate_round(timeout=True)
        except asyncio.CancelledError:
            pass

    async def _execute_and_grade_submission(
        self,
        author_id: int,
        lang_config,
        lang_alias: str,
        source_code: str,
        display_label: str,
        message: discord.Message,
    ) -> None:
        """Thực thi biên dịch và chấm mã nguồn qua Sandbox độc lập."""
        if not self.is_active or not self.current_problem or not self.channel:
            return

        # Ghi nhận ngôn ngữ lập trình của đấu thủ
        self.user_preferred_lang[author_id] = lang_alias

        # Kiểm tra quy định: Chỉ được nộp bài ĐÚNG 1 LẦN DUY NHẤT trong 1 chặng đấu
        if author_id in self.round_submissions:
            try:
                await message.delete()
            except Exception:
                pass
            await self.channel.send(
                f"⚠️ {message.author.mention} Bạn đã nộp bài cho **Chặng {self.current_round}** rồi! Mỗi đấu thủ chỉ được gửi bài **1 LẦN DUY NHẤT** trong mỗi chặng.",
                delete_after=10,
            )
            return

        # Tự động xóa tin nhắn/file nộp bài ngay lập tức để bảo mật chống copy code
        try:
            await message.delete()
        except Exception:
            pass

        status_msg = await self.channel.send(
            f"🔒 Đã nhận bài nộp của {message.author.mention} (`{display_label}`) *(đã tự động ẩn mã nguồn để chống sao chép)*. Đang chạy Sandbox chấm điểm..."
        )

        secret_tests = self.current_problem.secret_tests
        total_tests = len(secret_tests)
        passed_tests = 0
        verdict_str = "AC"

        temp_dir = tempfile.mkdtemp(prefix=f"duel_judge_{author_id}_{int(time.time() * 1000)}_")
        try:
            source_file = os.path.join(temp_dir, lang_config.source_filename)
            with open(source_file, "w", encoding="utf-8") as f:
                f.write(source_code)

            sandbox = CodeSandbox(
                timeout=settings.JUDGE_TIMEOUT,
                memory_limit_mb=settings.JUDGE_MEMORY_LIMIT,
            )

            # 0. Quét kiểm tra toàn diện tính liêm chính (Anti-Cheat 2.0: AI, Plagiarism, Rapid Paste)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            elapsed_sec = (now_utc - self.round_started_at).total_seconds() if self.round_started_at else 15.0
            solution_code = self.current_problem.solution_code if self.current_problem else None
            opponent = self.player2 if author_id == self.player1.id else self.player1
            opponent_sub = self.round_submissions.get(opponent.id, {})
            opponent_code = opponent_sub.get("source_code", None)

            ac_report = AntiCheatEngine.analyze_submission(
                source_code=source_code,
                lang=lang_config.name,
                time_elapsed_seconds=elapsed_sec,
                solution_code=solution_code,
                opponent_code=opponent_code,
            )

            if ac_report.is_cheating:
                async with async_session_factory() as session:
                    repo = UserRepository(session)
                    violation_count, banned_until, ban_duration_str = await repo.apply_ai_violation(author_id)

                cheat_reasons_str = "\n".join(f"• {r}" for r in ac_report.ai_reasons) or ac_report.summary
                ai_ban_embed = discord.Embed(
                    title="🚨 VI PHẠM QUY CHẾ THI ĐẤU (ANTI-CHEAT 2.0) — XỬ THUA NGAY LẬP TỨC",
                    description=(
                        f"{message.author.mention} đã bị hệ thống phát hiện **vi phạm nghiêm trọng quy chế liêm chính thi đấu**!\n\n"
                        f"🔍 **CHI TIẾT PHÁT HIỆN GIAN LẬN:**\n"
                        f"• {ac_report.summary}\n"
                        f"{cheat_reasons_str}\n\n"
                        f"⚖️ **HÌNH PHẠT THI HÀNH NGAY LẬP TỨC:**\n"
                        f"• ❌ **Kết quả trận đấu:** {message.author.mention} bị **XỬ THUA NGAY LẬP TỨC**!\n"
                        f"• 🏆 **Người chiến thắng:** {opponent.mention} được xử thắng toàn trận!\n"
                        f"• 🚫 **Cấm thi đấu (Lần {violation_count}):** Khóa quyền thi đấu Ranked & Freedom trong **{ban_duration_str}**.\n\n"
                        f"⚠️ *Nghiêm cấm mọi hành vi vi phạm quy chế để đảm bảo tính công bằng tuyệt đối cho đấu trường.*"
                    ),
                    color=0xE74C3C,
                )
                await self.channel.send(embed=ai_ban_embed)
                if author_id == self.player1.id:
                    self.p1_lives = 0
                else:
                    self.p2_lives = 0
                if self.round_timer_task and not self.round_timer_task.done():
                    self.round_timer_task.cancel()
                await self._finish_match()
                return

            test_case_details: list[dict] = []
            # 1. Biên dịch mã nguồn (nếu ngôn ngữ cần biên dịch)
            compile_res = await sandbox.compile_source(work_dir=temp_dir, lang=lang_config, time_limit=5.0)
            if not compile_res.success:
                passed_tests = 0
                verdict_str = "CE (Lỗi biên dịch)"
                ce_log = (compile_res.stderr or compile_res.stdout or "Compilation Failed")[:300]
                await self.channel.send(
                    f"⚠️ **Lỗi biên dịch (CE)** cho bài nộp của {message.author.mention}:\n```text\n{ce_log}\n```",
                    delete_after=15,
                )
            else:
                # 2. Chạy từng test case ẩn
                for idx, test in enumerate(secret_tests):
                    inp = test.get("input", "")
                    exp = str(test.get("output", "")).strip()

                    exec_res = await sandbox.execute_test(
                        work_dir=temp_dir,
                        lang=lang_config,
                        stdin_input=inp,
                        time_limit=2.0,
                    )
                    passed = False
                    if exec_res.status == "OK":
                        chk = OutputChecker.compare(actual=exec_res.stdout, expected=exp)
                        if chk.passed:
                            passed = True
                            passed_tests += 1

                    test_case_details.append({
                        "index": idx + 1,
                        "status": exec_res.status,
                        "time_seconds": round(exec_res.execution_time, 3),
                        "memory_mb": round(exec_res.memory_used_mb, 1),
                        "passed": passed,
                    })
        except Exception as e:
            logger.error(f"Lỗi ngoại lệ khi chấm bài Sandbox duel: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        percentage = (passed_tests / total_tests) * 100 if total_tests > 0 else 0.0
        if verdict_str != "CE (Lỗi biên dịch)":
            verdict_str = "AC" if percentage == 100 else f"{percentage:.0f}%"

        sub_record = {
            "round_number": self.current_round,
            "author_id": author_id,
            "author_name": message.author.display_name,
            "lang": lang_config.name,
            "source_code": source_code,
            "score": percentage,
            "passed": passed_tests,
            "total": total_tests,
            "verdict": verdict_str,
            "filename": display_label,
            "lang_alias": lang_alias,
            "elapsed_seconds": elapsed_sec,
            "submitted_at": now_utc,
            "anti_cheat": ac_report.to_dict(),
            "test_details": test_case_details,
        }
        self.round_submissions[author_id] = sub_record
        self.submission_details.append(sub_record)
        self.user_preferred_lang[author_id] = "python" if "py" in lang_alias else "cpp"

        opponent = self.player2 if author_id == self.player1.id else self.player1
        opponent_submitted = opponent.id in self.round_submissions

        if not opponent_submitted:
            await status_msg.edit(
                content=(
                    f"🔒 {message.author.mention} đã nộp bài thành công và hệ thống đã chấm xong ngầm! "
                    f"*(Kết quả đang được giữ bí mật 100% để đảm bảo tính công bằng)*.\n"
                    f"⏳ Đang chờ {opponent.mention} hoàn thành bài thi để so tài..."
                )
            )
        else:
            await status_msg.edit(
                content=(
                    f"🔒 {message.author.mention} đã nộp bài thành công và hệ thống đã chấm xong ngầm!\n"
                    f"🔔 Cả 2 đấu thủ đã hoàn thành bài thi! Đang tiến hành công bố kết quả đồng thời của cả 2 người..."
                )
            )
            if self.round_timer_task and not self.round_timer_task.done():
                self.round_timer_task.cancel()
            await self._evaluate_round(timeout=False)

    async def handle_code_submission(self, message: discord.Message) -> None:
        """Xử lý khi một thí sinh gửi file đính kèm code trong kênh duel."""
        if not self.is_active or not self.current_problem:
            return

        author_id = message.author.id
        if author_id not in (self.player1.id, self.player2.id):
            return

        if not message.attachments:
            return

        attachment = message.attachments[0]
        filename = attachment.filename.lower()

        extension_map = {
            ".cpp": "cpp20", ".cc": "cpp20", ".cxx": "cpp20", ".c": "c",
            ".py": "python3", ".java": "java", ".kt": "kotlin", ".cs": "csharp",
            ".pas": "pascal", ".rs": "rust", ".go": "go", ".js": "javascript",
            ".ts": "typescript", ".rb": "ruby", ".php": "php", ".hs": "haskell",
        }
        dot_ext = "." + filename.split(".")[-1] if "." in filename else ""
        lang_alias = extension_map.get(dot_ext)
        lang_config = get_language_by_alias(lang_alias) if lang_alias else None

        if not lang_config:
            await self.channel.send(
                f"⚠️ {message.author.mention} Đuôi file `{filename}` không được hỗ trợ! Vui lòng gửi file `.cpp`, `.py`, `.java`, `.pas`, v.v.",
                delete_after=10,
            )
            return

        max_bytes = self.current_problem.max_code_size_kb * 1024
        if attachment.size > max_bytes:
            await self.channel.send(
                f"⚠️ {message.author.mention} Kích thước file (`{attachment.size / 1024:.1f} KB`) vượt quá giới hạn cho phép (`≤ {self.current_problem.max_code_size_kb} KB`)!",
                delete_after=10,
            )
            return

        try:
            code_bytes = await attachment.read()
            source_code = code_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            await self.channel.send(f"❌ Lỗi khi đọc file code: {e}", delete_after=10)
            return

        self.chat_logs.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "author_id": author_id,
            "author_name": message.author.display_name,
            "type": "CODE_SUBMITTED",
            "content": f"Gửi file code: {filename} ({lang_config.name})",
        })

        await self._execute_and_grade_submission(
            author_id=author_id,
            lang_config=lang_config,
            lang_alias=lang_alias,
            source_code=source_code,
            display_label=filename,
            message=message,
        )

    async def handle_raw_text_submission(self, message: discord.Message) -> None:
        """Tự động phân biệt tin nhắn trò chuyện và mã nguồn nộp bài trực tiếp qua tin nhắn."""
        if not self.is_active or not self.current_problem or not self.channel:
            return

        author_id = message.author.id
        if author_id not in (self.player1.id, self.player2.id):
            return

        # 1. Nếu đang trong 15s chuẩn bị: cho phép hai người trò chuyện tự do!
        if self.in_prep_phase:
            self.chat_logs.append({
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "author_id": author_id,
                "author_name": message.author.display_name,
                "type": "15s_PREP_CHAT",
                "content": message.content,
            })
            return

        # 2. Nếu đang trong thời gian làm bài (focus_mode):
        is_code, lang_alias, clean_code = detect_code_language(message.content)
        if not is_code:
            # Là tin nhắn trò chuyện bình thường trong lúc làm bài -> Chặn và xóa ngay lập tức!
            self.chat_logs.append({
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
                "author_id": author_id,
                "author_name": message.author.display_name,
                "type": "SILENCED_CHAT_BLOCKED",
                "content": message.content,
            })
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await self.channel.send(
                    f"⚠️ {message.author.mention} **Không được nhắn tin lúc này!** Đang trong thời gian làm bài, chế độ Giữ Im Lặng đang bật. Chỉ gửi file code hoặc dán mã nguồn giải bài.",
                    delete_after=5,
                )
            except Exception:
                pass
            return

        # 3. Nếu là code hợp lệ:
        lang_config = get_language_by_alias(lang_alias)
        if not lang_config:
            try:
                await message.delete()
            except Exception:
                pass
            return

        self.chat_logs.append({
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "author_id": author_id,
            "author_name": message.author.display_name,
            "type": "CODE_SUBMITTED",
            "content": f"Dán code trực tiếp ({lang_config.name})",
        })

        await self._execute_and_grade_submission(
            author_id=author_id,
            lang_config=lang_config,
            lang_alias=lang_alias,
            source_code=clean_code,
            display_label=f"Paste ({lang_config.name})",
            message=message,
        )

    async def handle_close_command(self, message: discord.Message) -> None:
        """Xử lý lệnh .close: Yêu cầu đầu hàng đối thủ kèm nút xác nhận."""
        if not self.is_active or not self.channel:
            return

        author = message.author
        if author.id not in (self.player1.id, self.player2.id):
            await self.channel.send(
                f"⚠️ {author.mention} Chỉ thí sinh tham gia trận đấu này mới có thể dùng lệnh `.close`!",
                delete_after=10,
            )
            return

        view = SurrenderConfirmView(self, author)
        embed = discord.Embed(
            title="🏳️ XÁC NHẬN ĐẦU HÀNG TRẬN ĐẤU",
            description=(
                f"{author.mention}, bạn có chắc chắn muốn **ĐẦU HÀNG** đối thủ không?\n\n"
                f"⚠️ **Hệ quả**:\n"
                f"• Bạn sẽ bị xử thua trận đấu ngay lập tức và bị trừ điểm **-80 pts**.\n"
                f"• Đối thủ sẽ giành chiến thắng.\n"
                f"• Phòng thi đấu sẽ đóng lại sau 60 giây.\n\n"
                f"⏱️ *Vui lòng chọn nút bên dưới trong 30 giây.*"
            ),
            color=0xE74C3C,
        )
        await self.channel.send(embed=embed, view=view)

    async def handle_surrender(self, surrendering_player: discord.Member) -> None:
        """Xử lý khi thí sinh xác nhận đầu hàng."""
        if not self.is_active:
            return

        if self.round_timer_task and not self.round_timer_task.done():
            self.round_timer_task.cancel()

        if surrendering_player.id == self.player1.id:
            self.p1_lives = 0
        else:
            self.p2_lives = 0

        surrender_embed = discord.Embed(
            title="🏳️ ĐẦU HÀNG ĐƯỢC XÁC NHẬN",
            description=f"Thí sinh {surrendering_player.mention} đã chấp nhận **ĐẦU HÀNG**! Trận đấu kết thúc.",
            color=0xE74C3C,
        )
        await self.channel.send(embed=surrender_embed)
        await self._finish_match()

    async def handle_list_command(self, message: discord.Message) -> None:
        """Xử lý lệnh .list: Xem danh sách các bài/chặng mà mình và đối thủ đã làm."""
        if not self.channel:
            return

        p1_hearts = "❤️" * max(0, self.p1_lives) + "💔" * max(0, 2 - self.p1_lives)
        p2_hearts = "❤️" * max(0, self.p2_lives) + "💔" * max(0, 2 - self.p2_lives)

        desc = (
            f"### 📋 TIẾN TRÌNH TRẬN ĐẤU #{self.match_code.upper()}\n"
            f"• 🔴 {self.player1.mention}: **{p1_hearts}** ({self.p1_lives}/2 mạng)\n"
            f"• 🔵 {self.player2.mention}: **{p2_hearts}** ({self.p2_lives}/2 mạng)\n\n"
        )

        if not self.history:
            desc += "*Chưa có chặng đấu nào hoàn thành.*"
        else:
            desc += "### 🏆 CÁC CHẶNG ĐÃ THI ĐẤU:\n"
            for h in self.history:
                p1_h = "❤️" * max(0, h.p1_lives_after) + "💔" * max(
                    0, 2 - h.p1_lives_after
                )
                p2_h = "❤️" * max(0, h.p2_lives_after) + "💔" * max(
                    0, 2 - h.p2_lives_after
                )
                desc += (
                    f"**Chặng {h.round_number}: {h.problem_title}** (`{h.problem_tier}`)\n"
                    f"• {self.player1.display_name}: `{h.p1_score:.0f}%` ({h.p1_passed}/{h.p1_total} tests) → {p1_h}\n"
                    f"• {self.player2.display_name}: `{h.p2_score:.0f}%` ({h.p2_passed}/{h.p2_total} tests) → {p2_h}\n\n"
                )

        if self.is_active and self.current_problem:
            p1_done = (
                "✅ Đã nộp"
                if self.player1.id in self.round_submissions
                else "⏳ Đang làm..."
            )
            p2_done = (
                "✅ Đã nộp"
                if self.player2.id in self.round_submissions
                else "⏳ Đang làm..."
            )
            desc += (
                f"### 🎯 CHẶNG HIỆN TẠI (Chặng {self.current_round}):\n"
                f"• **Bài:** **{self.current_problem.name}** (`{self.current_problem.tier}`)\n"
                f"• {self.player1.mention}: {p1_done}\n"
                f"• {self.player2.mention}: {p2_done}\n"
            )

        embed = discord.Embed(
            title="📋 DANH SÁCH BÀI & KẾT QUẢ CỦA 2 ĐẤU THỦ",
            description=desc,
            color=0x3498DB,
        )
        embed.set_footer(
            text=f"Mã trận: #{self.match_code.upper()} • Gõ .list để cập nhật"
        )
        await self.channel.send(embed=embed)

    async def handle_test_command(self, message: discord.Message) -> None:
        """Xử lý lệnh .test: Chỉ Owner ID được dùng để đóng trận đấu ngay và win test."""
        if not self.is_active or not self.channel:
            return

        if message.author.id != settings.OWNER_ID and settings.OWNER_ID > 0:
            await self.channel.send(
                f"🚫 {message.author.mention} Lệnh `.test` chỉ dành riêng cho **Bot Owner** để kiểm thử hệ thống!",
                delete_after=10,
            )
            return

        if self.round_timer_task and not self.round_timer_task.done():
            self.round_timer_task.cancel()

        if message.author.id == self.player2.id:
            self.p1_lives = 0
            self.p2_lives = max(1, self.p2_lives)
        else:
            self.p2_lives = 0
            self.p1_lives = max(1, self.p1_lives)

        test_embed = discord.Embed(
            title="🧪 [TEST MODE] KÍCH HOẠT LỆNH .TEST TỪ BOT OWNER",
            description=(
                f"👑 Bot Owner ({message.author.mention}) đã kích hoạt lệnh `.test` kết thúc nhanh!\n"
                f"• Đóng trận đấu ngay lập tức.\n"
                f"• Xử lý luồng kết thúc, cộng/trừ điểm và đồng bộ role thử nghiệm."
            ),
            color=0x9B59B6,
        )
        await self.channel.send(embed=test_embed)
        await self._finish_match()

    async def handle_skip_command(self, message: discord.Message) -> None:
        """Xử lý lệnh .skip: Bỏ qua chặng hiện tại, cung cấp mã nguồn mẫu và chuyển sang chặng tiếp theo."""
        if not self.is_active or not self.channel:
            return

        author = message.author
        if author.id not in (
            self.player1.id,
            self.player2.id,
            getattr(settings, "OWNER_ID", 0),
        ):
            await self.channel.send(
                f"⚠️ {author.mention} Chỉ thí sinh trong phòng hoặc Bot Owner mới có quyền dùng lệnh `.skip`!",
                delete_after=10,
            )
            return

        if self.round_timer_task and not self.round_timer_task.done():
            self.round_timer_task.cancel()

        problem_name = self.current_problem.name if self.current_problem else "Bài Toán"
        problem_tier = self.current_problem.tier if self.current_problem else "Unknown"
        solution = (
            self.current_problem.solution_code
            if self.current_problem and self.current_problem.solution_code
            else "// Chưa có mã nguồn giải mẫu cho bài toán này."
        )

        # Lưu lịch sử chặng skipped
        if self.current_problem:
            self.history.append(
                RoundHistoryItem(
                    round_number=self.current_round,
                    problem_title=f"{problem_name} (⏩ Skipped)",
                    problem_tier=problem_tier,
                    p1_passed=len(self.current_problem.secret_tests),
                    p1_total=len(self.current_problem.secret_tests),
                    p1_score=100.0,
                    p2_passed=len(self.current_problem.secret_tests),
                    p2_total=len(self.current_problem.secret_tests),
                    p2_score=100.0,
                    p1_lives_after=self.p1_lives,
                    p2_lives_after=self.p2_lives,
                )
            )

        # Hủy timer của chặng hiện tại ngay lập tức khi skip
        if self.round_timer_task and not self.round_timer_task.done():
            self.round_timer_task.cancel()

        # Hướng dẫn tư duy giải thuật (Editorial) - Không hiện code đáp án thô
        editorial_content = (
            self.current_problem.editorial_text
            if self.current_problem
            else "🧠 Hãy xem lại các cấu trúc dữ liệu và thuật toán nền tảng phù hợp với bậc Tier này."
        )

        skip_desc = (
            f"Thí sinh {author.mention} đã yêu cầu **BỎ QUA CHẶNG {self.current_round}** (`{problem_name}`)!\n"
            f"Hai đấu thủ không bị trừ mạng và được chuyển thẳng sang chặng tiếp theo.\n\n"
            f"### 📖 HƯỚNG DẪN TƯ DUY & PHƯƠNG PHÁP GIẢI (EDITORIAL):\n"
            f"{editorial_content}\n\n"
            f"💡 *Hãy ghi nhớ các bước hướng dẫn trên để tự phân tích và làm bài ở các chặng tiếp theo!*"
        )

        skip_embed = discord.Embed(
            title=f"⏩ [SKIP CHẶNG {self.current_round}] {problem_name.upper()}",
            description=skip_desc,
            color=0x9B59B6,
        )
        skip_embed.set_footer(
            text=f"Mã trận: #{self.match_code.upper()} • Tự động chuyển sang chặng tiếp theo sau 15 giây"
        )
        try:
            await self.channel.send(embed=skip_embed)
        except Exception as e:
            logger.warning(f"Không thể gửi skip_embed: {e}")

        # Chuyển sang chặng kế tiếp: Khi dùng .skip -> Đề bài chặng sau tự động là Division 1 (Div. 1)
        self.current_round += 1
        next_problem = get_div1_problem()
        badge = get_rank_badge(next_problem.tier)
        skip_bonus_text = (
            f"\n\n🔥 **[Skip Mode - Division 1]:** Chặng tiếp theo tự động phát bài toán thuộc phân hạng **{next_problem.division}**: "
            f"{badge} **{next_problem.tier}** *({next_problem.rating_display})*!"
        )

        rest_embed = discord.Embed(
            title=f"☕ NGHỈ GIẢI LAO TRƯỚC CHẶNG {self.current_round} (15 GIÂY)",
            description=(
                f"Hai đấu thủ có **15 giây nghỉ ngơi** trước khi bước vào **Chặng {self.current_round}**!\n\n"
                f"🔍 **GỢI Ý NHỎ CHO CHẶNG TIẾP THEO:**\n"
                f"*{next_problem.hint}*{skip_bonus_text}\n\n"
                f"⏱️ *Chặng đấu sẽ tự động bắt đầu sau 15 giây...*"
            ),
            color=0xE74C3C,
        )
        try:
            await self.channel.send(embed=rest_embed)
        except Exception as e:
            logger.warning(f"Không thể gửi rest_embed: {e}")

        await asyncio.sleep(15)
        if self.is_active and self.channel:
            await self._start_round(problem=next_problem)

    async def _evaluate_round(self, timeout: bool = False) -> None:
        """So sánh kết quả chặng đấu giữa 2 thí sinh và cập nhật số mạng ❤️."""
        if not self.channel or not self.is_active:
            return

        total_tests = (
            len(self.current_problem.secret_tests) if self.current_problem else 5
        )
        p1_sub = self.round_submissions.get(
            self.player1.id, {"score": 0.0, "passed": 0, "total": total_tests, "verdict": "Chưa nộp"}
        )
        p2_sub = self.round_submissions.get(
            self.player2.id, {"score": 0.0, "passed": 0, "total": total_tests, "verdict": "Chưa nộp"}
        )

        p1_submitted = self.player1.id in self.round_submissions
        p2_submitted = self.player2.id in self.round_submissions

        s1 = p1_sub["score"]
        s2 = p2_sub["score"]
        diff = abs(s1 - s2)
        both_perfect = (s1 >= 99.9 and s2 >= 99.9 and p1_submitted and p2_submitted)

        if timeout and (not p1_submitted or not p2_submitted):
            # Xử thua chặng ngay lập tức cho người không nộp bài khi hết giờ (Quyết định A3)
            if not p1_submitted and not p2_submitted:
                self.p1_lives -= 1
                self.p2_lives -= 1
                round_result_desc = (
                    f"### ⏱️ HẾT GIỜ LÀM BÀI CHẶNG {self.current_round}!\n"
                    f"❌ Cả hai đấu thủ {self.player1.mention} và {self.player2.mention} đều **KHÔNG NỘP BÀI** trước khi hết giờ!\n"
                    f"⚖️ **Hình phạt:** Cả 2 người đều bị **XỬ THUA CHẶNG** và bị **trừ 1 mạng (💔)**.\n\n"
                )
            elif not p1_submitted and p2_submitted:
                self.p1_lives -= 1
                round_result_desc = (
                    f"### ⏱️ HẾT GIỜ LÀM BÀI CHẶNG {self.current_round}!\n"
                    f"❌ {self.player1.mention} **KHÔNG NỘP BÀI** trước khi hết giờ → Bị **XỬ THUA CHẶNG** và bị **trừ 1 mạng (💔)**!\n"
                    f"🏆 {self.player2.mention} đã nộp bài kịp thời và giành chiến thắng chặng này! ({p2_sub['score']:.1f}% - {p2_sub['passed']}/{total_tests} tests đúng).\n\n"
                )
            elif p1_submitted and not p2_submitted:
                self.p2_lives -= 1
                round_result_desc = (
                    f"### ⏱️ HẾT GIỜ LÀM BÀI CHẶNG {self.current_round}!\n"
                    f"❌ {self.player2.mention} **KHÔNG NỘP BÀI** trước khi hết giờ → Bị **XỬ THUA CHẶNG** và bị **trừ 1 mạng (💔)**!\n"
                    f"🏆 {self.player1.mention} đã nộp bài kịp thời và giành chiến thắng chặng này! ({p1_sub['score']:.1f}% - {p1_sub['passed']}/{total_tests} tests đúng).\n\n"
                )
        else:
            # Cả 2 đều đã nộp bài -> Công bố đồng thời kết quả của cả 2 người
            round_result_desc = (
                f"### 📊 KẾT QUẢ ĐỒNG THỜI CHẶNG ĐẤU SỐ {self.current_round}\n"
                f"• {self.player1.mention}: **{s1:.1f}%** ({p1_sub['passed']}/{total_tests} tests đúng) • Verdict: `{p1_sub.get('verdict', 'N/A')}`\n"
                f"• {self.player2.mention}: **{s2:.1f}%** ({p2_sub['passed']}/{total_tests} tests đúng) • Verdict: `{p2_sub.get('verdict', 'N/A')}`\n\n"
            )

            if both_perfect or diff <= 10.0:
                # Cả 2 bài đều đúng (hoặc hòa điểm) -> Tiếp tục Chặng 2 (hoặc chặng kế tiếp)
                round_result_desc += (
                    f"⚖️ **KẾT QUẢ: HÒA CHẶNG!** Cả 2 đối thủ đều làm bài chuẩn xác ngang tài ngang sức.\n"
                    f"➡️ Không ai bị trừ mạng! Trận đấu tự động tiếp tục bước sang **Chặng {self.current_round + 1}**!\n"
                )
            elif s1 > s2:
                self.p2_lives -= 1
                if s1 < 100.0 and s2 < 100.0:
                    self.both_failed_partial_win = True
                    round_result_desc += (
                        f"🏆 {self.player1.mention} đúng nhiều test hơn ({p1_sub['passed']}/{total_tests} vs {p2_sub['passed']}/{total_tests})!\n"
                        f"• {self.player2.mention} bị **trừ 1 mạng (💔)**.\n"
                        f"• ℹ️ *Cả 2 đối thủ đều chưa đạt AC 100% — nếu trận đấu kết thúc, điểm thắng sẽ được giảm trừ 50-85% theo quy định.*\n"
                    )
                else:
                    self.both_failed_partial_win = False
                    round_result_desc += f"🏆 {self.player1.mention} xuất sắc hơn! {self.player2.mention} bị **trừ 1 mạng (💔)**.\n"
            else:
                self.p1_lives -= 1
                if s1 < 100.0 and s2 < 100.0:
                    self.both_failed_partial_win = True
                    round_result_desc += (
                        f"🏆 {self.player2.mention} đúng nhiều test hơn ({p2_sub['passed']}/{total_tests} vs {p1_sub['passed']}/{total_tests})!\n"
                        f"• {self.player1.mention} bị **trừ 1 mạng (💔)**.\n"
                        f"• ℹ️ *Cả 2 đối thủ đều chưa đạt AC 100% — nếu trận đấu kết thúc, điểm thắng sẽ được giảm trừ 50-85% theo quy định.*\n"
                    )
                else:
                    self.both_failed_partial_win = False
                    round_result_desc += f"🏆 {self.player2.mention} xuất sắc hơn! {self.player1.mention} bị **trừ 1 mạng (💔)**.\n"

        # Lưu lịch sử
        if self.current_problem:
            self.history.append(
                RoundHistoryItem(
                    round_number=self.current_round,
                    problem_title=self.current_problem.name,
                    problem_tier=self.current_problem.tier,
                    p1_passed=p1_sub["passed"],
                    p1_total=total_tests,
                    p1_score=s1,
                    p2_passed=p2_sub["passed"],
                    p2_total=total_tests,
                    p2_score=s2,
                    p1_lives_after=self.p1_lives,
                    p2_lives_after=self.p2_lives,
                )
            )

        p1_hearts = "❤️" * max(0, self.p1_lives) + "💔" * max(0, (2 - self.p1_lives))
        p2_hearts = "❤️" * max(0, self.p2_lives) + "💔" * max(0, (2 - self.p2_lives))

        # Cập nhật tỉ lệ thắng động
        from services.special_roles import calculate_win_probability
        curr_p1_prob, curr_p2_prob = calculate_win_probability(
            self.p1_ranked_rating, self.p2_ranked_rating, self.p1_lives, self.p2_lives
        )
        self.p1_min_prob = min(self.p1_min_prob, curr_p1_prob)
        self.p2_min_prob = min(self.p2_min_prob, curr_p2_prob)
        self.p1_max_prob = max(self.p1_max_prob, curr_p1_prob)
        self.p2_max_prob = max(self.p2_max_prob, curr_p2_prob)

        if self.p1_lives == 2 and self.p2_lives == 1:
            self.had_two_vs_one = True
            self.who_had_two_vs_one = self.player1.id
        elif self.p2_lives == 2 and self.p1_lives == 1:
            self.had_two_vs_one = True
            self.who_had_two_vs_one = self.player2.id

        prob_info = f"\n• 📊 **Tỉ lệ thắng hiện tại:** {self.player1.display_name}: `{curr_p1_prob}%` │ {self.player2.display_name}: `{curr_p2_prob}%`" if not self.is_custom_match else ""

        round_result_desc += (
            f"\n**Tình trạng sinh lực hiện tại:**\n"
            f"• {self.player1.mention}: **{p1_hearts}** ({self.p1_lives}/2 mạng)\n"
            f"• {self.player2.mention}: **{p2_hearts}** ({self.p2_lives}/2 mạng)"
            f"{prob_info}\n"
        )

        embed = discord.Embed(
            title=f"⚔️ TỔNG KẾT CHẶNG {self.current_round}",
            description=round_result_desc,
            color=0x2ECC71 if (s1 > s2 or s2 > s1) else 0xE67E22,
        )
        try:
            await self.channel.send(embed=embed)
        except discord.NotFound:
            self.is_active = False
            if self.channel and self.channel.id in duel_service.active_sessions:
                duel_service.active_sessions.pop(self.channel.id, None)
            return

        # Kiểm tra điều kiện kết thúc trận đấu
        if self.p1_lives <= 0 or self.p2_lives <= 0:
            await self._finish_match()
        else:
            self.current_round += 1
            if self.is_custom_match and self.custom_tier:
                from services.duel_problems import get_problem_by_tier
                next_problem = get_problem_by_tier(
                    self.custom_tier,
                    exclude_ids=self.used_problem_ids,
                    round_index=self.current_round,
                )
            else:
                next_problem = get_problem_for_match(
                    self.p1_ranked_rank, self.p2_ranked_rank,
                    exclude_ids=self.used_problem_ids,
                    round_index=self.current_round,
                )
            # Kích hoạt 15 giây chuẩn bị & trò chuyện tự do giữa các chặng
            self.in_prep_phase = True
            self.focus_mode = False
            rest_escalation_note = ""
            if self.current_round > 1:
                bonus_pct = round((self.current_round - 1) * 1.5, 1)
                rest_escalation_note = f"\n🔥 **Áp lực leo thang (Chặng {self.current_round}):** Thử thách nâng cao, độ khó tăng `+{bonus_pct}%`!\n"

            rest_embed = discord.Embed(
                title=f"☕ NGHỈ GIẢI LAO & CHUẨN BỊ BƯỚC VÀO CHẶNG {self.current_round} (15 GIÂY)",
                description=(
                    f"Hai đấu thủ có **15 giây nghỉ ngơi và trò chuyện tự do** trước khi bước vào **Chặng {self.current_round}**!\n\n"
                    f"💬 *Trong 15 giây này, hai bạn có thể tự do nhắn tin trao đổi với nhau.*\n"
                    f"🔍 **GỢI Ý NHỎ CHO CHẶNG TIẾP THEO:**\n"
                    f"*{next_problem.hint}*\n"
                    f"{rest_escalation_note}\n"
                    f"⏱️ *Đề bài Chặng {self.current_round} sẽ tự động xuất hiện sau 15 giây...*"
                ),
                color=0x3498DB,
            )
            try:
                await self.channel.send(embed=rest_embed)
            except Exception as e:
                logger.warning(f"Lỗi gửi rest_embed: {e}")

            await asyncio.sleep(15)
            if self.is_active and self.channel:
                await self._start_round(problem=next_problem, prep_delay=False)

    def _archive_played_problems(self) -> None:
        """Tự động lưu trữ tất cả bài tập đã thi đấu trong trận vào PROBLEM_ARCHIVE_CHANNEL_ID (1548627763467128912)."""
        problems = list(self.problems_played)
        if not problems and self.current_problem:
            problems.append(self.current_problem)
        for p in problems:
            try:
                from services.problem_archive import ProblemArchiveService
                asyncio.create_task(
                    ProblemArchiveService.archive_problem(
                        self.bot,
                        {
                            "id": p.id,
                            "name": p.name,
                            "mode": "Ranked 1:1",
                            "tier": p.tier,
                            "division": p.division,
                            "rating": p.rating,
                            "time_limit": p.time_limit,
                            "memory_limit": p.memory_limit,
                            "statement": p.statement,
                            "input_format": p.input_format,
                            "output_format": p.output_format,
                            "constraints": p.constraints,
                            "editorial": p.editorial_text,
                            "sample_input": p.sample_input,
                            "sample_output": p.sample_output,
                            "solution_code": p.solution_cpp,
                            "solution_lang": "cpp",
                        },
                    )
                )
            except Exception as arc_e:
                logger.debug(f"Lỗi kích hoạt lưu trữ bài ranked {p.id}: {arc_e}")

    async def _finish_match(self) -> None:
        """Kết thúc trận đấu, tính điểm rating, cấp role ranked và vinh danh người thắng."""
        self.is_active = False

        # Khôi phục quyền truy cập các danh mục cho 2 thí sinh ngay khi kết thúc trận
        await self._restore_contestant_categories()

        if self.p1_lives > 0:
            winner = self.player1
            loser = self.player2
            winner_lives = self.p1_lives
            winner_id = self.player1.id
            loser_id = self.player2.id
            winner_old_rating = self.p1_ranked_rating
            loser_old_rating = self.p2_ranked_rating
            winner_old_rank = self.p1_ranked_rank
            loser_old_rank = self.p2_ranked_rank
        else:
            winner = self.player2
            loser = self.player1
            winner_lives = self.p2_lives
            winner_id = self.player2.id
            loser_id = self.player1.id
            winner_old_rating = self.p2_ranked_rating
            loser_old_rating = self.p1_ranked_rating
            winner_old_rank = self.p2_ranked_rank
            loser_old_rank = self.p1_ranked_rank

        rounds_played = len(self.history) if self.history else self.current_round

        # Kích hoạt lưu trữ kho đề bài đã thi đấu vào channel lưu trữ chung
        self._archive_played_problems()

        problems_to_show = list(self.problems_played)
        if not problems_to_show and self.current_problem:
            problems_to_show.append(self.current_problem)
        p_codes_str = ", ".join(f"`{p.id}`" for p in problems_to_show) if problems_to_show else "N/A"

        if self.is_custom_match:
            winner_delta = 0.0
            loser_delta = 0.0
            winner_new_rank = winner_old_rank
            loser_new_rank = loser_old_rank
            w_badge = get_rank_badge(winner_new_rank)
            l_badge = get_rank_badge(loser_new_rank)

            finish_desc = (
                f"## 🤝 {winner.mention} ĐÃ CHIẾN THẮNG TRẬN GIAO HỮU!\n\n"
                f"• 🥇 **Người chiến thắng:** {winner.mention}\n"
                f"  - Bậc Rank: {w_badge} `{winner_new_rank}`\n"
                f"  - Độ khó đã đấu: `⭐ Tier {self.custom_tier or 'T8'}`\n\n"
                f"• 💀 **Người thua cuộc:** {loser.mention}\n"
                f"  - Bậc Rank: {l_badge} `{loser_new_rank}`\n\n"
                f"• 📝 **Mã tra cứu bài thi:** {p_codes_str} (Dùng `/search <id>` để xem lại đề & đáp án)\n"
                f"• ⚖️ **Điểm số Elo:** Giữ nguyên (Trận đấu giao hữu không ảnh hưởng bảng xếp hạng).\n\n"
                f"⏱️ *Kênh thi đấu này sẽ tự động đóng sau 60 giây...*"
            )

            embed = discord.Embed(
                title=f"🤝 KẾT QUẢ TRẬN GIAO HỮU #{self.match_code.upper()}",
                description=finish_desc,
                color=0x3498DB,
            )
            if self.channel:
                await self.channel.send(embed=embed)

            await self._send_match_transcript(
                winner, loser, winner_delta, loser_delta, winner_new_rank, loser_new_rank,
                winner_streak=0, streak_bonus_pct=0
            )
            await self._send_private_match_editorial(
                winner, loser, winner_delta, loser_delta, winner_new_rank, loser_new_rank,
                winner_streak=0
            )
            asyncio.create_task(self._delayed_cleanup())
            return

        current_streak = 0
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u_win_pre = await repo.get_by_id(winner_id)
            if u_win_pre:
                current_streak = u_win_pre.ranked_streak or 0

        winner_delta, loser_delta, delta_details = calculate_ranked_rating_deltas(
            winner_rank=winner_old_rank,
            loser_rank=loser_old_rank,
            winner_rating=winner_old_rating,
            loser_rating=loser_old_rating,
            winner_lives=winner_lives,
            rounds_played=rounds_played,
            is_partial_win=self.both_failed_partial_win,
            winner_streak=current_streak,
        )
        winner_delta = float(winner_delta)
        loser_delta = float(loser_delta)

        # Cập nhật CSDL
        async with async_session_factory() as session:
            repo = UserRepository(session)
            u_winner = await repo.update_ranked_stats(
                discord_id=winner_id,
                rating_delta=winner_delta,
                is_winner=True,
                is_draw=False,
            )
            u_loser = await repo.update_ranked_stats(
                discord_id=loser_id,
                rating_delta=loser_delta,
                is_winner=False,
                is_draw=False,
            )

            winner_new_rank = get_rank_by_rating(u_winner.ranked_rating)
            loser_new_rank = get_rank_by_rating(u_loser.ranked_rating)

            u_winner.ranked_rank = winner_new_rank
            u_loser.ranked_rank = loser_new_rank

            # Đánh giá và cập nhật Hệ Thống 6 Danh Hiệu Động
            from services.special_roles import evaluate_match_special_roles
            winner_is_p1 = (winner_id == self.player1.id)
            w_start_prob = self.p1_start_prob if winner_is_p1 else self.p2_start_prob
            w_min_prob = self.p1_min_prob if winner_is_p1 else self.p2_min_prob
            l_start_prob = self.p2_start_prob if winner_is_p1 else self.p1_start_prob
            l_max_prob = self.p2_max_prob if winner_is_p1 else self.p1_max_prob
            loser_had_two = (self.who_had_two_vs_one == loser_id)

            sp_res = evaluate_match_special_roles(
                winner_prev_role=u_winner.special_role,
                winner_streak=u_winner.ranked_streak,
                winner_fortune_count=u_winner.special_fortune_count or 0,
                winner_outclassed_count=u_winner.special_outclassed_count or 0,
                winner_clutch_count=u_winner.special_clutch_count or 0,
                winner_is_doomed=bool(u_winner.is_doomed),
                winner_start_prob=w_start_prob,
                winner_min_prob=w_min_prob,
                loser_prev_role=u_loser.special_role,
                loser_streak=u_loser.ranked_streak,
                loser_fortune_count=u_loser.special_fortune_count or 0,
                loser_outclassed_count=u_loser.special_outclassed_count or 0,
                loser_clutch_count=u_loser.special_clutch_count or 0,
                loser_is_doomed=bool(u_loser.is_doomed),
                loser_start_prob=l_start_prob,
                loser_max_prob=l_max_prob,
                loser_had_two_lives_when_winner_one=loser_had_two,
            )

            u_winner.special_role = sp_res["winner_new_role"]
            u_winner.special_fortune_count = sp_res["winner_fortune_count"]
            u_winner.special_outclassed_count = sp_res["winner_outclassed_count"]
            u_winner.special_clutch_count = sp_res["winner_clutch_count"]
            u_winner.is_doomed = sp_res["winner_is_doomed"]

            u_loser.special_role = sp_res["loser_new_role"]
            u_loser.special_fortune_count = sp_res["loser_fortune_count"]
            u_loser.special_outclassed_count = sp_res["loser_outclassed_count"]
            u_loser.special_clutch_count = sp_res["loser_clutch_count"]
            u_loser.is_doomed = sp_res["loser_is_doomed"]

            await session.commit()

        # Đồng bộ Ranked Roles & Special Achievement Roles trên Discord
        await RoleManager.sync_ranked_user_roles(
            guild=self.guild,
            member=winner,
            old_rating=winner_old_rating,
            new_rating=u_winner.ranked_rating,
            old_rank=winner_old_rank,
            new_rank=winner_new_rank,
            bot=self.bot,
        )
        await RoleManager.sync_ranked_user_roles(
            guild=self.guild,
            member=loser,
            old_rating=loser_old_rating,
            new_rating=u_loser.ranked_rating,
            old_rank=loser_old_rank,
            new_rank=loser_new_rank,
            bot=self.bot,
        )
        await RoleManager.sync_special_achievement_roles(
            guild=self.guild,
            member=winner,
            active_role_key=u_winner.special_role,
            bot=self.bot,
        )
        await RoleManager.sync_special_achievement_roles(
            guild=self.guild,
            member=loser,
            active_role_key=u_loser.special_role,
            bot=self.bot,
        )

        w_badge = get_rank_badge(winner_new_rank)
        l_badge = get_rank_badge(loser_new_rank)
        new_streak = u_winner.ranked_streak
        bonus_pct = get_streak_bonus_pct(current_streak)
        streak_info = f" • 🔥 **Chuỗi:** `{new_streak} trận`" if new_streak > 1 else ""

        sp_notif_desc = ""
        if sp_res["notifications"]:
            sp_notif_desc = "\n\n### 🎖️ BIẾN ĐỘNG DANH HIỆU ĐẶC BIỆT:\n" + "\n".join(f"• {n}" for n in sp_res["notifications"])

        finish_desc = (
            f"## 🏆 {winner.mention} ĐÃ CHIẾN THẮNG TRẬN ĐẤU!\n\n"
            f"• 🥇 **Người chiến thắng:** {winner.mention}{streak_info}\n"
            f"  - Điểm thưởng: **+{winner_delta:.0f} pts** ({delta_details})\n"
            f"  - Rating Ranked: `⭐ {winner_old_rating} pts` → `⭐ {u_winner.ranked_rating} pts`\n"
            f"  - Bậc Rank: {w_badge} `{winner_new_rank}`\n\n"
            f"• 💀 **Người thua cuộc:** {loser.mention}\n"
            f"  - Điểm trừ: **{loser_delta:.0f} pts**\n"
            f"  - Rating Ranked: `⭐ {loser_old_rating} pts` → `⭐ {u_loser.ranked_rating} pts`\n"
            f"  - Bậc Rank: {l_badge} `{loser_new_rank}`\n\n"
            f"• 📝 **Mã tra cứu bài thi:** {p_codes_str} (Dùng `/search <id>` để tra cứu đề & đáp án)\n"
            f"{sp_notif_desc}\n\n"
            f"⏱️ *Kênh thi đấu này sẽ tự động đóng sau 60 giây...*"
        )

        embed = discord.Embed(
            title=f"⚔️ KẾT QUẢ CHUNG CUỘC TRẬN ĐẤU #{self.match_code.upper()}",
            description=finish_desc,
            color=0xF1C40F,
        )
        if self.channel:
            await self.channel.send(embed=embed)

        await self._broadcast_winner(
            winner, loser, winner_delta, loser_delta, winner_new_rank
        )
        await self._send_match_transcript(
            winner, loser, winner_delta, loser_delta, winner_new_rank, loser_new_rank,
            winner_streak=new_streak, streak_bonus_pct=bonus_pct
        )
        await self._send_private_match_editorial(
            winner, loser, winner_delta, loser_delta, winner_new_rank, loser_new_rank,
            winner_streak=new_streak
        )
        asyncio.create_task(self._delayed_cleanup())

    async def _send_private_match_editorial(
        self,
        winner: discord.Member,
        loser: discord.Member,
        winner_delta: float,
        loser_delta: float,
        winner_new_rank: str,
        loser_new_rank: str,
        winner_streak: int = 0,
    ) -> None:
        """
        Gửi kết quả, lịch sử và phân tích thuật toán (Editorial) kèm code mẫu chuẩn AC
        theo đúng ngôn ngữ lập trình mà từng đấu thủ đã sử dụng trong trận qua tin nhắn riêng (DM).
        Nếu đấu thủ tắt DM, gửi fallback nút bấm xem cá nhân trong kênh thi đấu trước khi đóng.
        """
        problems = list(self.problems_played)
        if not problems and self.current_problem:
            problems.append(self.current_problem)

        players_info = [
            (
                self.player1,
                winner.id == self.player1.id,
                winner_delta if winner.id == self.player1.id else loser_delta,
                winner_new_rank if winner.id == self.player1.id else loser_new_rank,
                self.p1_ranked_rating,
                self.p1_ranked_rank,
                self.player2,
            ),
            (
                self.player2,
                winner.id == self.player2.id,
                winner_delta if winner.id == self.player2.id else loser_delta,
                winner_new_rank if winner.id == self.player2.id else loser_new_rank,
                self.p2_ranked_rating,
                self.p2_ranked_rank,
                self.player1,
            ),
        ]

        for player, is_win, delta, new_rank, old_rating, old_rank, opponent in players_info:
            try:
                embeds_to_send: list[discord.Embed] = []
                user_lang = self.user_preferred_lang.get(player.id, "cpp")

                # Embed 1: Kết quả & Lịch sử riêng cho đấu thủ
                w_status = "🏆 **CHIẾN THẮNG!**" if is_win else "💀 **BẠI TRẬN!**"
                card_color = 0x2ECC71 if is_win else 0xE74C3C
                delta_str = f"{delta:+.0f} pts" if not self.is_custom_match else "Giao hữu (0 pts)"
                streak_str = f" • 🔥 Chuỗi thắng: `{winner_streak}`" if is_win and winner_streak > 1 else ""

                hist_lines = []
                for h in self.history:
                    p_score = h.p1_score if player.id == self.player1.id else h.p2_score
                    p_passed = h.p1_passed if player.id == self.player1.id else h.p2_passed
                    p_total = h.p1_total if player.id == self.player1.id else h.p2_total
                    p_lives = h.p1_lives_after if player.id == self.player1.id else h.p2_lives_after
                    verdict_icon = "✅ AC" if p_score >= 100.0 else ("⚠️ PARTIAL" if p_score > 0 else "❌ WA")
                    hist_lines.append(
                        f"• **Chặng {h.round_number}** - `{h.problem_title}`: {verdict_icon} "
                        f"({p_passed}/{p_total} tests - {p_score:.0f}%) | Mạng còn: `{p_lives}/2`"
                    )
                hist_text = "\n".join(hist_lines) if hist_lines else "• Không có dữ liệu chặng đấu."

                summary_embed = discord.Embed(
                    title=f"⚔️ KẾT QUẢ RIÊNG & LỊCH SỬ THI ĐẤU • TRẬN #{self.match_code.upper()}",
                    description=(
                        f"## {w_status}\n\n"
                        f"• 👤 **Đấu thủ:** {player.mention}\n"
                        f"• 🎯 **Đối thủ:** {opponent.display_name} *({get_rank_badge(old_rank)} `{old_rank}`)*\n"
                        f"• 📈 **Biến động Elo:** `{delta_str}` ({old_rating} pts → {new_rank}){streak_str}\n"
                        f"• 💻 **Ngôn ngữ bạn dùng:** `{user_lang.upper()}`\n\n"
                        f"### 📋 Lịch Sử Từng Chặng:\n{hist_text}\n\n"
                        f"*(Xem lời giải chi tiết và mã nguồn mẫu {user_lang.upper()} chuẩn AC ở bên dưới)*"
                    ),
                    color=card_color,
                    timestamp=datetime.datetime.now(datetime.timezone.utc),
                )
                if problems:
                    p_codes_str = ", ".join(f"`{p.id}`" for p in problems)
                    summary_embed.add_field(
                        name="📝 Mã Tra Cứu Đề Bài",
                        value=f"{p_codes_str}\n*(Sử dụng lệnh `/search <id>` để xem lại đề bài và code giải chuẩn)*",
                        inline=False,
                    )
                summary_embed.set_footer(text=f"Mã trận #{self.match_code.upper()} • HyperHub Ranked Arena")
                embeds_to_send.append(summary_embed)

                # Embeds cho từng bài toán đã đấu trong trận
                for idx, prob in enumerate(problems, 1):
                    sol_code, syntax = prob.get_solution_for_lang(user_lang)
                    if len(sol_code) > 1800:
                        sol_code = sol_code[:1750] + "\n// ... [Mã nguồn rút gọn để tối ưu hiển thị Discord] ..."

                    editorial_embed = discord.Embed(
                        title=f"📖 LỜI GIẢI & PHÂN TÍCH THUẬT TOÁN (CHẶNG {idx}): {prob.name}",
                        description=(
                            f"🏷️ **Bậc bài:** `{prob.tier}` • `{prob.division}` | **Rating:** `{prob.rating_display}`\n\n"
                            f"{prob.editorial_text}\n\n"
                            f"💻 **MÃ NGUỒN MẪU CHUẨN AC ({user_lang.upper()}):**\n"
                            f"```{syntax}\n{sol_code}\n```"
                        ),
                        color=0x3498DB,
                    )
                    editorial_embed.set_footer(text=f"Mã tra cứu: {prob.id} (Dùng /search {prob.id}) • Lời giải tự động theo ngôn ngữ {user_lang.upper()}")
                    embeds_to_send.append(editorial_embed)

                # Gửi qua Direct Message (DM)
                sent_dm = False
                try:
                    for chunk_idx in range(0, len(embeds_to_send), 10):
                        await player.send(embeds=embeds_to_send[chunk_idx:chunk_idx + 10])
                    sent_dm = True
                    logger.info(f"✅ Đã gửi DM riêng lời giải & phân tích cho {player.display_name}")
                except (discord.Forbidden, discord.HTTPException) as dme:
                    logger.info(f"Không thể gửi DM cho {player.display_name} (DM bị tắt): {dme}")

                # Fallback nếu tắt DM: Gửi nút bấm trong phòng đấu trước khi đóng
                if not sent_dm and self.channel:
                    try:
                        fb_view = DuelEditorialFallbackView(target_user=player, embeds=embeds_to_send)
                        await self.channel.send(
                            content=(
                                f"⚠️ {player.mention} Bạn đang **tắt tin nhắn riêng (DM)** nên bot không thể gửi bản phân tích thuật toán & code mẫu cá nhân! "
                                f"Bấm nút bên dưới để xem riêng ngay tại đây trước khi phòng tự đóng:"
                            ),
                            view=fb_view,
                        )
                    except Exception as fe:
                        logger.warning(f"Lỗi khi gửi fallback view cho {player.display_name}: {fe}")

            except Exception as pe:
                logger.error(f"Lỗi khi tạo editorial riêng cho {player.display_name}: {pe}", exc_info=True)

    def generate_transcript_text(
        self,
        winner: discord.Member,
        loser: discord.Member,
        winner_delta: float,
        loser_delta: float,
        winner_new_rank: str,
        loser_new_rank: str,
    ) -> str:
        """Tạo toàn bộ nội dung transcript văn bản (.txt) cho trận đấu."""
        lines: list[str] = []
        lines.append("=" * 80)
        lines.append("HYPERHUB COMPETITIVE PROGRAMMING - RANKED 1:1 MATCH TRANSCRIPT")
        lines.append("=" * 80)
        lines.append(f"Mã Trận Đấu       : #{self.match_code.upper()}")
        ch_name = self.channel.name if self.channel and hasattr(self.channel, "name") else "N/A"
        ch_id = self.channel.id if self.channel else 0
        lines.append(f"Kênh Thi Đấu      : #{ch_name} (ID: {ch_id})")
        lines.append(f"Thời Gian Bắt Đầu : {self.match_started_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        end_time = datetime.datetime.now(datetime.timezone.utc)
        lines.append(f"Thời Gian Kết Thúc: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        rounds_played = len(self.history) if self.history else self.current_round
        lines.append(f"Tổng Số Chặng     : {rounds_played} chặng")
        lines.append("")

        p1_delta_str = f"{winner_delta:+.0f}" if winner.id == self.player1.id else f"{loser_delta:+.0f}"
        p1_new_rank_str = winner_new_rank if winner.id == self.player1.id else loser_new_rank
        lines.append(f"ĐẤU THỦ 1 (P1): {self.player1.display_name} (ID: {self.player1.id})")
        lines.append(f"  • Bậc Rank Cũ   : {self.p1_ranked_rank} ({self.p1_ranked_rating} pts)")
        lines.append(f"  • Biến Động Elo : {p1_delta_str} pts -> Rank Mới: {p1_new_rank_str}")
        lines.append(f"  • Mạng Sinh Lực : {self.p1_lives}/2")
        lines.append("")

        p2_delta_str = f"{winner_delta:+.0f}" if winner.id == self.player2.id else f"{loser_delta:+.0f}"
        p2_new_rank_str = winner_new_rank if winner.id == self.player2.id else loser_new_rank
        lines.append(f"ĐẤU THỦ 2 (P2): {self.player2.display_name} (ID: {self.player2.id})")
        lines.append(f"  • Bậc Rank Cũ   : {self.p2_ranked_rank} ({self.p2_ranked_rating} pts)")
        lines.append(f"  • Biến Động Elo : {p2_delta_str} pts -> Rank Mới: {p2_new_rank_str}")
        lines.append(f"  • Mạng Sinh Lực : {self.p2_lives}/2")
        lines.append("")

        lines.append(f"🏆 NGƯỜI CHIẾN THẮNG: {winner.display_name} (ID: {winner.id})")
        lines.append(f"💀 NGƯỜI BẠI TRẬN   : {loser.display_name} (ID: {loser.id})")
        lines.append("")

        lines.append("=" * 80)
        lines.append("NHẬT KÝ TIN NHẮN & SỰ KIỆN TRONG KÊNH (CHAT & SYSTEM TELEMETRY)")
        lines.append("=" * 80)
        if not self.chat_logs:
            lines.append("(Không có tin nhắn nào được ghi nhận)")
        else:
            for item in self.chat_logs:
                ts = item["timestamp"].strftime("%H:%M:%S")
                author = item.get("author_name", "N/A")
                m_type = item.get("type", "CHAT")
                content = item.get("content", "")
                lines.append(f"[{ts}] [{m_type}] {author}: {content}")
        lines.append("")

        lines.append("=" * 80)
        lines.append("CHI TIẾT TỪNG CHẶNG ĐẤU & LỊCH SỬ CHẤM BÀI (SUBMISSION & JUDGING LOGS)")
        lines.append("=" * 80)
        if not self.submission_details:
            lines.append("(Không có bài nộp nào được lưu trữ)")
        else:
            rounds_map: dict[int, list[dict]] = {}
            for sub in self.submission_details:
                r_num = sub.get("round_number", 1)
                rounds_map.setdefault(r_num, []).append(sub)

            for r_num, subs in rounds_map.items():
                lines.append("-" * 80)
                lines.append(f"CHẶNG {r_num}")
                lines.append("-" * 80)
                for sub in subs:
                    lines.append(f">>> BÀI NỘP CỦA: {sub.get('author_name')} (ID: {sub.get('author_id')})")
                    lines.append(f"    • Ngôn ngữ         : {sub.get('lang')}")
                    lines.append(f"    • Thời gian nộp    : {sub.get('elapsed_seconds', 0.0):.1f}s sau khi mở đề")
                    lines.append(f"    • Kết quả chấm     : {sub.get('verdict')} ({sub.get('score', 0.0):.1f}% - {sub.get('passed', 0)}/{sub.get('total', 0)} tests đúng)")
                    ac = sub.get("anti_cheat", {})
                    lines.append(f"    • Anti-Cheat 2.0   : Mức rủi ro: {ac.get('risk_level', 'N/A')}")
                    lines.append(f"      - Điểm nghi vấn AI      : {ac.get('ai_score', 0.0):.1f}%")
                    lines.append(f"      - Đạo nhái giải mẫu     : {ac.get('plagiarism_solution_score', 0.0):.1f}%")
                    lines.append(f"      - Đạo nhái đối thủ      : {ac.get('plagiarism_opponent_score', 0.0):.1f}%")
                    lines.append(f"      - Dán code siêu tốc     : {'CÓ' if ac.get('is_rapid_paste') else 'KHÔNG'} ({ac.get('rapid_paste_details', '')})")
                    lines.append(f"      - Đánh giá tổng quan    : {ac.get('summary', '')}")
                    test_details = sub.get("test_details", [])
                    if test_details:
                        lines.append(f"    • Chi tiết từng Test Case:")
                        for td in test_details:
                            status_str = "PASS" if td.get("passed") else f"FAIL ({td.get('status')})"
                            lines.append(f"        Test #{td.get('index', 0)}: {status_str} [{td.get('time_seconds', 0):.3f}s, {td.get('memory_mb', 0):.1f}MB]")
                    lines.append(f"    • MÃ NGUỒN BÀI LÀM:")
                    lines.append(f"      ┌" + "─" * 70)
                    for code_line in sub.get("source_code", "").splitlines():
                        lines.append(f"      │ {code_line}")
                    lines.append(f"      └" + "─" * 70)
                    lines.append("")

        lines.append("=" * 80)
        lines.append("HẾT BẢN GHI NHẬT KÝ - HYPERHUB COMPETITIVE PROGRAMMING")
        lines.append("=" * 80)
        return "\n".join(lines)

    async def _send_match_transcript(
        self,
        winner: discord.Member,
        loser: discord.Member,
        winner_delta: float,
        loser_delta: float,
        winner_new_rank: str,
        loser_new_rank: str,
        winner_streak: int = 0,
        streak_bonus_pct: int = 0,
    ) -> str:
        """Tạo file transcript .txt và thẻ bài kết quả PNG, gửi vào phòng đấu hiện tại & kênh log chuyên dụng."""
        transcript_text = self.generate_transcript_text(
            winner, loser, winner_delta, loser_delta, winner_new_rank, loser_new_rank
        )
        os.makedirs("duel_transcripts", exist_ok=True)
        file_path = os.path.join("duel_transcripts", f"match_{self.match_code}.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        # Tạo Match Card PNG đồ họa Esports
        card_file_path = None
        try:
            from services.match_card import MatchCardGenerator

            p1_is_win = (winner.id == self.player1.id)
            p2_is_win = (winner.id == self.player2.id)
            p1_avatar_url = str(self.player1.display_avatar.url) if hasattr(self.player1, "display_avatar") else None
            p2_avatar_url = str(self.player2.display_avatar.url) if hasattr(self.player2, "display_avatar") else None

            p1_delta = winner_delta if p1_is_win else loser_delta
            p2_delta = winner_delta if p2_is_win else loser_delta

            # Tính tổng thời gian trận đấu
            total_duration_sec = 0
            if hasattr(self, "match_started_at") and self.match_started_at:
                try:
                    total_duration_sec = int(max(1, (datetime.datetime.now(datetime.timezone.utc) - self.match_started_at).total_seconds()))
                except Exception:
                    total_duration_sec = max(60, (len(self.history) if self.history else self.current_round) * 120)

            # Tính tỉ lệ thắng/thua theo bot tính toán từ rating, điểm test case và mạng sống
            p1_total_score = sum(h.p1_score for h in self.history) if self.history else (100.0 if p1_is_win else 0.0)
            p2_total_score = sum(h.p2_score for h in self.history) if self.history else (100.0 if p2_is_win else 0.0)
            score_sum = p1_total_score + p2_total_score
            expected_p1 = 1.0 / (1.0 + 10.0 ** ((self.p2_ranked_rating - self.p1_ranked_rating) / 400.0))

            if score_sum > 0:
                score_weight = p1_total_score / score_sum
                win_prob_p1 = (0.35 * expected_p1) + (0.45 * score_weight) + (0.20 * (self.p1_lives / max(1, self.p1_lives + self.p2_lives)))
            else:
                win_prob_p1 = (0.60 * expected_p1) + (0.40 * (self.p1_lives / max(1, self.p1_lives + self.p2_lives)))

            if p1_is_win:
                win_prob_p1 = max(win_prob_p1, 0.60)
            elif p2_is_win:
                win_prob_p1 = min(win_prob_p1, 0.40)

            p1_win_pct = round(max(10.0, min(90.0, win_prob_p1 * 100.0)), 1)
            p2_win_pct = round(100.0 - p1_win_pct, 1)

            card_file_path = await MatchCardGenerator.generate_match_card(
                match_code=self.match_code,
                player1_name=self.player1.display_name,
                player2_name=self.player2.display_name,
                p1_is_winner=p1_is_win,
                p2_is_winner=p2_is_win,
                is_draw=False,
                p1_rank=self.p1_ranked_rank,
                p2_rank=self.p2_ranked_rank,
                p1_rating=self.p1_ranked_rating,
                p2_rating=self.p2_ranked_rating,
                p1_delta=p1_delta,
                p2_delta=p2_delta,
                p1_lives=self.p1_lives,
                p2_lives=self.p2_lives,
                problem_tier=self.custom_tier or (self.current_problem.tier if self.current_problem else "T8"),
                problem_name=self.current_problem.name if self.current_problem else "Luyện tập thuật toán",
                rounds_played=len(self.history) if self.history else self.current_round,
                p1_avatar_url=p1_avatar_url,
                p2_avatar_url=p2_avatar_url,
                p1_streak=winner_streak if p1_is_win else 0,
                p2_streak=winner_streak if p2_is_win else 0,
                streak_bonus_pct=streak_bonus_pct,
                is_custom=self.is_custom_match,
                output_dir="duel_transcripts",
                p1_win_prob=p1_win_pct,
                p2_win_prob=p2_win_pct,
                total_duration_sec=total_duration_sec,
            )
        except Exception as e:
            logger.warning(f"Lỗi khi tạo ảnh thẻ kết quả Match Card: {e}")

        # 1. Gửi vào kênh thi đấu trước khi đóng
        if self.channel:
            try:
                files_to_send = [discord.File(file_path, filename=f"transcript_match_{self.match_code}.txt")]
                if card_file_path and os.path.exists(card_file_path):
                    files_to_send.append(discord.File(card_file_path, filename=f"card_{self.match_code}.png"))

                await self.channel.send(
                    content=(
                        f"📜 **NHẬT KÝ CHI TIẾT TRẬN ĐẤU & THẺ KẾT QUẢ (MATCH CARD & TRANSCRIPT):**\n"
                        f"File đính kèm bên dưới chứa đầy đủ thẻ bài kết quả đồ họa, lịch sử tin nhắn, code bài nộp của cả 2 bên và kết quả chấm bài chi tiết. "
                        f"Hai bạn vui lòng tải về trước khi phòng đấu tự động đóng sau 60 giây!"
                    ),
                    files=files_to_send,
                )
            except Exception as e:
                logger.warning(f"Lỗi khi gửi transcript vào kênh thi đấu: {e}")

        # 2. Gửi vào kênh log chuyên dụng DUEL_LOG_CHANNEL_ID (1536199276273860638)
        log_channel_id = getattr(settings, "DUEL_LOG_CHANNEL_ID", 1536199276273860638)
        log_channel = self.guild.get_channel(log_channel_id) if hasattr(self.guild, "get_channel") else None
        if log_channel and isinstance(log_channel, discord.TextChannel):
            rounds_played = len(self.history) if self.history else self.current_round
            p1_ac = "Bình thường"
            p2_ac = "Bình thường"
            for sub in self.submission_details:
                ac = sub.get("anti_cheat", {})
                if ac.get("is_cheating"):
                    if sub.get("author_id") == self.player1.id:
                        p1_ac = "🚨 Phát hiện gian lận!"
                    else:
                        p2_ac = "🚨 Phát hiện gian lận!"
                elif ac.get("risk_level") == "SUSPICIOUS":
                    if sub.get("author_id") == self.player1.id and "🚨" not in p1_ac:
                        p1_ac = "⚠️ Nghi vấn"
                    elif sub.get("author_id") == self.player2.id and "🚨" not in p2_ac:
                        p2_ac = "⚠️ Nghi vấn"

            log_title = f"🤝 NHẬT KÝ TRẬN GIAO HỮU • #{self.match_code.upper()}" if self.is_custom_match else f"📜 NHẬT KÝ TRẬN ĐẤU RANKED 1:1 • #{self.match_code.upper()}"
            if self.is_custom_match:
                match_res_text = (
                    f"🏆 **Người chiến thắng:** {winner.mention} *({winner_new_rank})*\n"
                    f"💀 **Người bại trận:** {loser.mention} *({loser_new_rank})*\n"
                    f"🎯 **Độ khó:** `⭐ Tier {self.custom_tier or 'T8'}` (Giao hữu không tính Elo)\n"
                )
            else:
                streak_log_str = f" [🔥 Chuỗi {winner_streak} trận]" if winner_streak > 1 else ""
                match_res_text = (
                    f"🏆 **Người chiến thắng:** {winner.mention} (`{winner_delta:+.0f} pts` → `{winner_new_rank}`){streak_log_str}\n"
                    f"💀 **Người bại trận:** {loser.mention} (`{loser_delta:+.0f} pts` → `{loser_new_rank}`)\n"
                )

            embed_log = discord.Embed(
                title=log_title,
                description=(
                    f"⚔️ **Cặp đối đầu:** {self.player1.mention} *({self.p1_ranked_rank})* **VS** {self.player2.mention} *({self.p2_ranked_rank})*\n"
                    f"{match_res_text}"
                    f"⏱️ **Số chặng đấu:** `{rounds_played} chặng` • **Mạng còn lại:** {self.player1.display_name} (`{self.p1_lives}/2`) | {self.player2.display_name} (`{self.p2_lives}/2`)\n\n"
                    f"🛡️ **Kiểm tra Anti-Cheat 2.0:**\n"
                    f"• {self.player1.display_name}: `{p1_ac}`\n"
                    f"• {self.player2.display_name}: `{p2_ac}`\n\n"
                    f"📁 *Toàn bộ mã nguồn bài nộp, tin nhắn trong phòng và lịch sử chấm test case được lưu trữ trong file đính kèm bên dưới.*"
                ),
                color=0x2ECC71 if winner.id == self.player1.id else 0x3498DB,
            )
            embed_log.set_footer(text=f"Mã trận #{self.match_code.upper()} • HyperHub Ranked Arena")
            embed_log.timestamp = datetime.datetime.now(datetime.timezone.utc)
            try:
                discord_file_log = discord.File(file_path, filename=f"transcript_match_{self.match_code}.txt")
                if card_file_path and os.path.exists(card_file_path):
                    discord_card_log = discord.File(card_file_path, filename=f"card_{self.match_code}.png")
                    embed_log.set_image(url=f"attachment://card_{self.match_code}.png")
                    await log_channel.send(embed=embed_log, files=[discord_file_log, discord_card_log])
                else:
                    await log_channel.send(embed=embed_log, file=discord_file_log)
                logger.info(f"Đã gửi transcript & card trận #{self.match_code} tới kênh log {log_channel_id}")
            except Exception as e:
                logger.warning(f"Lỗi khi gửi transcript tới kênh log channel {log_channel_id}: {e}")

        # 3. Cập nhật trạng thái DuelMatch trong CSDL
        try:
            from database.models import DuelMatch
            from sqlalchemy import select
            async with async_session_factory() as session:
                stmt = select(DuelMatch).where(DuelMatch.match_code == self.match_code)
                res = await session.execute(stmt)
                match_rec = res.scalar_one_or_none()
                if not match_rec:
                    match_rec = DuelMatch(
                        match_code=self.match_code,
                        channel_id=self.channel.id if self.channel else 0,
                        player1_id=self.player1.id,
                        player2_id=self.player2.id,
                    )
                    session.add(match_rec)
                match_rec.status = "FINISHED"
                match_rec.winner_id = winner.id
                match_rec.p1_lives = self.p1_lives
                match_rec.p2_lives = self.p2_lives
                match_rec.current_round = len(self.history) if self.history else self.current_round
                match_rec.p1_rating_delta = winner_delta if winner.id == self.player1.id else loser_delta
                match_rec.p2_rating_delta = winner_delta if winner.id == self.player2.id else loser_delta
                match_rec.finished_at = datetime.datetime.now(datetime.timezone.utc)
                await session.commit()
        except Exception as e:
            logger.warning(f"Lỗi cập nhật DuelMatch trong CSDL: {e}")

        return file_path

    async def _broadcast_winner(
        self,
        winner: discord.Member,
        loser: discord.Member,
        w_delta: float,
        l_delta: float,
        w_rank: str,
    ) -> None:
        """Gửi thông báo vinh danh người chiến thắng tại kênh WINNER_CHANNEL_ID."""
        winner_channel_id = getattr(settings, "WINNER_CHANNEL_ID", 0)
        if not winner_channel_id or winner_channel_id <= 0:
            return

        w_channel = self.guild.get_channel(winner_channel_id)
        if not w_channel or not isinstance(w_channel, discord.TextChannel):
            return

        w_badge = get_rank_badge(w_rank)
        w_name = get_rank_name(w_rank)

        embed = discord.Embed(
            title="🏆 VINH DANH CHIẾN THẮNG RANKED 1:1",
            description=(
                f"🎉 Xin chúc mừng {winner.mention} đã xuất sắc đánh bại {loser.mention} "
                f"trong trận đối đầu trực tiếp Ranked 1:1!\n\n"
                f"• 🎖️ **Bậc Rank hiện tại:** {w_badge} `{w_rank}` *({w_name})*\n"
                f"• ⭐ **Điểm cộng:** `+{w_delta:.0f} pts` (Đối thủ `{l_delta:.0f} pts`)\n"
                f"• ⚔️ **Mã trận:** `#{self.match_code.upper()}`"
            ),
            color=0xF1C40F,
        )
        embed.set_thumbnail(url=winner.display_avatar.url)

        problems_to_show = list(self.problems_played)
        if not problems_to_show and self.current_problem:
            problems_to_show.append(self.current_problem)
        if problems_to_show:
            p_codes_str = ", ".join(f"`{p.id}`" for p in problems_to_show)
            embed.add_field(
                name="📝 Mã Tra Cứu Đề Bài Thi Đấu",
                value=f"{p_codes_str}\n*(Sử dụng lệnh `/search <id>` để xem lại toàn bộ đề bài, phân tích và code mẫu)*",
                inline=False,
            )

        embed.set_footer(
            text="HyperHub Competitive Programming • Đấu Trường Ranked 1:1"
        )

        try:
            await w_channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"Không thể gửi thông báo vinh danh tới kênh winner: {e}")

    async def _delayed_cleanup(self) -> None:
        """Đợi 60 giây sau trận đấu rồi xóa kênh và xóa khỏi active_sessions."""
        await asyncio.sleep(60)
        try:
            await self._restore_contestant_categories()
        except Exception as e:
            logger.warning(f"Lỗi khi dọn dẹp danh mục ẩn: {e}")
        if self.channel:
            try:
                await self.channel.delete(
                    reason=f"Ranked 1:1 match #{self.match_code} finished."
                )
            except Exception as e:
                logger.warning(f"Lỗi khi xóa kênh duel #{self.channel.name}: {e}")


@dataclass
class QueueEntry:
    """Đại diện cho một thí sinh đang trong hàng chờ ghép trận."""

    discord_id: int
    guild_id: int
    channel_id: int
    freedom_rank: str
    freedom_rating: int
    ranked_rank: str
    ranked_rating: int
    joined_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class MatchmakingManager:
    """Quản lý hàng chờ và thuật toán ghép cặp Đấu Trường Ranked 1:1."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue: list[QueueEntry] = []
        self.active_sessions: dict[int, DuelSession] = {}  # channel_id -> DuelSession

    def is_in_queue(self, discord_id: int) -> bool:
        return any(entry.discord_id == discord_id for entry in self.queue)

    def remove_from_queue(self, discord_id: int) -> bool:
        for entry in self.queue:
            if entry.discord_id == discord_id:
                self.queue.remove(entry)
                return True
        return False

    def is_in_duel(self, discord_id: int) -> bool:
        return any(
            s.is_active and discord_id in (s.player1.id, s.player2.id)
            for s in self.active_sessions.values()
        )

    async def add_to_queue(
        self, member: discord.Member, channel: discord.TextChannel
    ) -> tuple[bool, discord.Embed, DuelSession | None]:
        """Thêm thí sinh vào hàng chờ và thực hiện ghép trận theo quy tắc: ±1 Tier (Trả về Embed)."""
        discord_id = member.id

        if self.is_in_duel(discord_id):
            embed = create_embed(
                title="⚠️ ĐANG TRONG TRẬN ĐẤU",
                description="Bạn đang trong một trận đấu Ranked 1:1 chưa kết thúc!",
                embed_type=EmbedType.WARNING,
                color=0xE74C3C,
            )
            return False, embed, None

        if self.is_in_queue(discord_id):
            embed = create_embed(
                title="ℹ️ ĐÃ Ở TRONG HÀNG CHỜ",
                description=(
                    "Bạn đã có mặt trong hàng chờ ghép trận Ranked 1:1 rồi!\n\n"
                    "• 🎯 **Phạm vi tìm kiếm:** Đối thủ có trình độ chênh lệch tối đa ±1 Tier.\n"
                    "• ⏱️ Vui lòng đợi trong giây lát, bot sẽ tự động tạo kênh thi đấu khi tìm thấy đối thủ."
                ),
                embed_type=EmbedType.INFO,
                color=0x3498DB,
            )
            return False, embed, None

        async with async_session_factory() as session:
            repo = UserRepository(session)
            user, _ = await repo.get_or_create(discord_id)

            freedom_rating = user.rating
            freedom_rank = user.rank
            ranked_rating = user.ranked_rating
            ranked_rank = user.ranked_rank

            # Kiểm tra thời gian nghỉ (Cooldown 5 phút = 300s) sau mỗi trận Ranked
            is_owner = bool(settings.OWNER_ID and discord_id == settings.OWNER_ID)
            if not is_owner:
                is_on_cd, rem_secs, rem_str = await repo.get_duel_cooldown(discord_id, cooldown_seconds=300)
                if is_on_cd:
                    embed = create_embed(
                        title="⏱️ THỜI GIAN NGHỈ NGƠI (COOLDOWN)",
                        description=(
                            f"Bạn vừa hoàn thành một trận đấu Ranked! Để bảo đảm thể lực và chống cày điểm spam, "
                            f"hệ thống yêu cầu nghỉ ngơi tối thiểu 5 phút sau mỗi ván đấu.\n\n"
                            f"• ⏳ **Thời gian nghỉ còn lại:** `{rem_str}`\n"
                            f"• 💡 *Gợi ý: Bạn có thể dùng `/custom_match` để thi đấu giao hữu không tính điểm với bạn bè trong lúc chờ!*"
                        ),
                        embed_type=EmbedType.WARNING,
                        color=0xF39C12,
                    )
                    return False, embed, None

        if freedom_rating < 400 and freedom_rank == "T8":
            embed = create_embed(
                title="🚫 ĐIỀU KIỆN MỞ KHÓA RANKED 1:1",
                description=(
                    "Bạn cần đạt tối thiểu **⭐ Bậc T7 (Freedom)** (Rating Freedom ≥ 400 pts) để tham gia Đấu Trường Ranked 1:1!\n\n"
                    "💡 *Hãy làm bài tại `#📋・contest` và nộp code tại `#📤・submit` để tích lũy điểm Freedom trước nhé!*"
                ),
                embed_type=EmbedType.ERROR,
                color=0xE74C3C,
            )
            return False, embed, None

        user_tier_idx = get_rank_index(ranked_rank)

        matched_entry: QueueEntry | None = None
        for entry in self.queue:
            if entry.discord_id == discord_id:
                continue
            entry_tier_idx = get_rank_index(entry.ranked_rank)
            if abs(user_tier_idx - entry_tier_idx) <= 1:
                matched_entry = entry
                break

        if matched_entry:
            self.queue.remove(matched_entry)
            opponent = member.guild.get_member(matched_entry.discord_id)

            if not opponent:
                self.queue.append(
                    QueueEntry(
                        discord_id=discord_id,
                        guild_id=member.guild.id,
                        channel_id=channel.id,
                        freedom_rank=freedom_rank,
                        freedom_rating=freedom_rating,
                        ranked_rank=ranked_rank,
                        ranked_rating=ranked_rating,
                    )
                )
                embed = create_embed(
                    title="🔍 ĐANG TÌM ĐỐI THỦ",
                    description="Đang tìm kiếm đối thủ phù hợp trong phạm vi ±1 Bậc Tier...",
                    embed_type=EmbedType.INFO,
                    color=0xF39C12,
                )
                return True, embed, None

            duel_session = DuelSession(
                bot=self.bot,
                guild=member.guild,
                player1=matched_entry.discord_id == member.id and opponent or member,
                player2=opponent if matched_entry.discord_id != member.id else member,
                p1_ranked_rank=ranked_rank,
                p1_ranked_rating=ranked_rating,
                p2_ranked_rank=matched_entry.ranked_rank,
                p2_ranked_rating=matched_entry.ranked_rating,
            )

            started = await duel_session.start()
            if started and duel_session.channel:
                self.active_sessions[duel_session.channel.id] = duel_session
                p1_badge = get_rank_badge(ranked_rank)
                p2_badge = get_rank_badge(matched_entry.ranked_rank)
                embed = create_embed(
                    title="⚔️ GHÉP TRẬN THÀNH CÔNG!",
                    description=(
                        f"Đã tìm thấy đối thủ xứng tầm!\n\n"
                        f"• 🔴 **Đấu thủ 1:** {member.mention} ({p1_badge} `{ranked_rank}` • `{ranked_rating} pts`)\n"
                        f"• 🔵 **Đấu thủ 2:** {opponent.mention} ({p2_badge} `{matched_entry.ranked_rank}` • `{matched_entry.ranked_rating} pts`)\n"
                        f"• 🏟️ **Kênh thi đấu:** {duel_session.channel.mention}\n\n"
                        f"🚀 *Đang chuyển hướng vào phòng đấu... Chúc hai bạn thi đấu xuất sắc!*"
                    ),
                    embed_type=EmbedType.SUCCESS,
                    color=0x2ECC71,
                )
                return True, embed, duel_session
            else:
                embed = create_embed(
                    title="❌ LỖI TẠO PHÒNG THI ĐẤU",
                    description="Đã xảy ra lỗi khi tạo phòng thi đấu. Vui lòng thử lại sau!",
                    embed_type=EmbedType.ERROR,
                    color=0xE74C3C,
                )
                return False, embed, None

        self.queue.append(
            QueueEntry(
                discord_id=discord_id,
                guild_id=member.guild.id,
                channel_id=channel.id,
                freedom_rank=freedom_rank,
                freedom_rating=freedom_rating,
                ranked_rank=ranked_rank,
                ranked_rating=ranked_rating,
            )
        )

        badge = get_rank_badge(ranked_rank)
        queue_count = len(self.queue)
        from services.rank import RANK_ORDER

        user_idx = get_rank_index(ranked_rank)
        min_idx = max(0, user_idx - 1)
        max_idx = min(len(RANK_ORDER) - 1, user_idx + 1)
        min_tier = RANK_ORDER[min_idx]
        max_tier = RANK_ORDER[max_idx]

        embed = create_embed(
            title="⏳ HÀNG CHỜ ĐẤU TRƯỜNG RANKED 1:1",
            description=(
                f"Đã ghi danh bạn vào hàng chờ ghép trận thành công!\n\n"
                f"• 👤 **Thí sinh:** {member.mention} ({badge} `{ranked_rank}` • `{ranked_rating} pts`)\n"
                f"• 🎯 **Phạm vi ghép:** Bậc `{min_tier}` ↔ `{max_tier}` (±1 Tier)\n"
                f"• 👥 **Số người trong hàng chờ:** `{queue_count}` thí sinh\n"
                f"• ⏱️ **Trạng thái:** Đang tự động quét tìm đối thủ...\n\n"
                f"💡 *Bạn có thể làm việc khác, Bot sẽ gửi thông báo và tag bạn ngay khi tìm thấy đối thủ!*"
            ),
            embed_type=EmbedType.INFO,
            color=0xF39C12,
        )
        return True, embed, None

    async def start_mock_duel_for_owner(
        self, owner_member: discord.Member, channel: discord.TextChannel
    ) -> tuple[bool, discord.Embed, DuelSession | None]:
        """Bỏ qua hàng chờ và tạo ngay một trận đấu Ranked 1:1 mô phỏng dành cho Owner để test hệ thống."""
        discord_id = owner_member.id

        if self.is_in_duel(discord_id):
            embed = create_embed(
                title="⚠️ ĐANG TRONG TRẬN ĐẤU",
                description="Bạn đang có một phiên đấu Ranked 1:1 chưa kết thúc!",
                embed_type=EmbedType.WARNING,
                color=0xE74C3C,
            )
            return False, embed, None

        # Xóa khỏi queue nếu đang ở trong queue
        self.remove_from_queue(discord_id)

        async with async_session_factory() as session:
            repo = UserRepository(session)
            user, _ = await repo.get_or_create(discord_id)
            ranked_rating = max(user.ranked_rating, 3000)
            ranked_rank = "HT1"

        mock_opponent = owner_member.guild.me

        # Khi Owner dùng .skip để tạo phòng đấu mô phỏng -> Đề bài luôn ở Bậc Rank cao nhất & khó nhất (HT1)
        duel_session = DuelSession(
            bot=self.bot,
            guild=owner_member.guild,
            player1=owner_member,
            player2=mock_opponent,
            p1_ranked_rank=ranked_rank,
            p1_ranked_rating=ranked_rating,
            p2_ranked_rank="HT1",
            p2_ranked_rating=3000,
        )

        started = await duel_session.start()
        if started and duel_session.channel:
            self.active_sessions[duel_session.channel.id] = duel_session
            p1_badge = get_rank_badge(ranked_rank)
            embed = create_embed(
                title="🚀 [TEST MODE] ĐÃ KÍCH HOẠT TRẬN ĐẤU MÔ PHỎNG (HẠNG CAO NHẤT HT1)",
                description=(
                    f"Đã bỏ qua thời gian chờ ghép trận cho **Bot Owner**!\n\n"
                    f"• 🔴 **Đấu thủ 1:** {owner_member.mention} ({p1_badge} `{ranked_rank}` • `{ranked_rating} pts`)\n"
                    f"• 🔵 **Đối thủ mô phỏng:** {mock_opponent.mention} (🤖 `Mock Bot Tester` • `3000 pts`)\n"
                    f"• 👑 **Độ Khó Đề Bài:** **Bậc Cao Nhất & Khó Nhất (👑 HT1 / Div. 1 - 3000+ pts)**\n"
                    f"• 🏟️ **Kênh thi đấu:** {duel_session.channel.mention}\n\n"
                    f"💡 *Các lệnh test trong ticket:* `.list` (xem chặng), `.skip` (nhận code mẫu C++ & bài HT1 tiếp theo), `.test` (đóng trận & thắng test), `.close` (đầu hàng)."
                ),
                embed_type=EmbedType.SUCCESS,
                color=0xE74C3C,
            )
            return True, embed, duel_session
        else:
            embed = create_embed(
                title="❌ LỖI KHỞI TẠO",
                description="Không thể tạo phòng đấu Ranked 1:1 mô phỏng. Vui lòng thử lại!",
                embed_type=EmbedType.ERROR,
                color=0xE74C3C,
            )
            return False, embed, None
