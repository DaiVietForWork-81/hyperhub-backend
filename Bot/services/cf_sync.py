"""Mode 1 Codeforces submission synchronizer with failure rating penalties and 100% Vietnamese localization."""

import asyncio

import discord

from database.database import async_session_factory
from database.repositories.cf_repo import CFAccountRepository
from database.repositories.rating_repo import RatingRepository
from database.repositories.submission_repo import SubmissionRepository
from database.repositories.user_repo import UserRepository
from services.codeforces_api import CodeforcesAPIError, cf_api
from services.rank import get_rank_by_rating
from services.rating import RatingEngine
from services.role_manager import RoleManager
from utils.embeds import EmbedType, create_embed
from utils.logger import get_logger

logger = get_logger("CFSyncService")

# Codeforces verdicts mapping to Vietnamese, icons, and colors
CF_VERDICTS = {
    "OK": ("Chấp nhận (Accepted)", "🟢", 0x2ECC71),
    "WRONG_ANSWER": ("Kết quả sai (Wrong Answer)", "🔴", 0xE74C3C),
    "TIME_LIMIT_EXCEEDED": ("Vượt quá thời gian (TLE)", "🟠", 0xE67E22),
    "MEMORY_LIMIT_EXCEEDED": ("Vượt quá bộ nhớ (MLE)", "🟣", 0x9B59B6),
    "RUNTIME_ERROR": ("Lỗi thực thi (Runtime Error)", "💥", 0xC0392B),
    "COMPILATION_ERROR": ("Lỗi biên dịch (CE)", "🔘", 0x95A5A6),
    "CHALLENGED": ("Bị hack (Challenged)", "⚔️", 0xD35400),
    "SKIPPED": ("Bỏ qua (Skipped)", "⏭️", 0x7F8C8D),
    "REJECTED": ("Bị từ chối (Rejected)", "⛔", 0x7F8C8D),
}


class CFSubmissionSyncService:
    """Tự động quét và đồng bộ các bài nộp từ Codeforces theo chu kỳ."""

    def __init__(self, bot: discord.Client, poll_interval_seconds: int = 45):
        self.bot = bot
        self.interval = poll_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._sync_loop())
            logger.info(
                f"Dịch vụ đồng bộ Mode 1 Codeforces đã khởi động (chu kỳ {self.interval}s)."
            )

    def stop(self) -> None:
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
            logger.info("Dịch vụ đồng bộ Mode 1 Codeforces đã dừng.")

    async def _sync_loop(self) -> None:
        await self.bot.wait_until_ready()
        while self._running:
            try:
                await self._poll_all_users()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Lỗi không mong muốn trong vòng lặp đồng bộ CF: {e}", exc_info=True
                )

            await asyncio.sleep(self.interval)

    async def _poll_all_users(self) -> None:
        """Quét tất cả các tài khoản Codeforces đã xác minh trong CSDL."""
        async with async_session_factory() as session:
            repo = CFAccountRepository(session)
            accounts = await repo.get_all_verified()

        for account in accounts:
            try:
                ok = await self._process_user_submissions(
                    account.discord_id, account.cf_handle
                )
                if not ok:
                    # Codeforces API đang gặp 503 / Cloudflare -> Tạm dừng lượt quét này
                    break
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(
                    f"Lỗi khi xử lý bài nộp cho handle {account.cf_handle}: {e}"
                )

    async def _process_user_submissions(self, discord_id: int, handle: str) -> bool:
        """Gọi Codeforces API và ghi nhận bài nộp mới nếu có. Trả về False nếu Codeforces đang 503/bảo trì."""
        try:
            submissions = await cf_api.get_user_submissions(handle=handle, count=25)
        except CodeforcesAPIError as e:
            if "503" in str(e) or "Cloudflare" in str(e):
                logger.warning(
                    "⚠️ Codeforces API đang tạm bảo trì hoặc bật kiểm tra Cloudflare (HTTP 503). Tạm hoãn lượt quét này (sẽ tự động thử lại sau 45s)."
                )
                return False
            logger.warning(
                f"Lỗi API Codeforces khi lấy bài nộp cho handle {handle}: {e}"
            )
            return True

        if not submissions:
            return True

        for sub in reversed(submissions):  # Xử lý theo thứ tự từ cũ đến mới
            sub_id = sub.get("id")
            verdict_raw = sub.get("verdict")

            # Bỏ qua khi bài đang chấm
            if not sub_id or verdict_raw == "TESTING":
                continue

            problem_data = sub.get("problem", {})
            contest_id = problem_data.get("contestId")
            index = problem_data.get("index", "")
            problem_name = problem_data.get("name", "Không rõ")
            problem_rating = problem_data.get("rating", 1200)
            passed_test_count = sub.get("passedTestCount", 0)
            problem_id = f"{contest_id}{index}" if contest_id and index else index

            if not problem_id:
                continue

            async with async_session_factory() as session:
                sub_repo = SubmissionRepository(session)
                user_repo = UserRepository(session)
                cf_repo = CFAccountRepository(session)
                rating_repo = RatingRepository(session)

                # Kiểm tra chống duplicate
                if await sub_repo.exists_by_cf_id(sub_id):
                    continue

                verdict_name, emoji, color = CF_VERDICTS.get(
                    verdict_raw, (verdict_raw or "Không xác định", "❓", 0x95A5A6)
                )
                is_accepted = verdict_raw == "OK"
                already_solved = await sub_repo.has_solved(discord_id, problem_id)

                is_event, event_mult, event_tag = (
                    RatingEngine.get_event_bonus_multiplier(
                        problem_name=problem_name, problem_rating=problem_rating
                    )
                )

                score_earned = 0.0
                rating_delta = 0
                old_rating = 0
                new_rating = 0
                old_rank = "T8"
                new_rank = "T8"

                user, _ = await user_repo.get_or_create(discord_id)
                old_rating = user.rating
                old_rank = user.rank
                new_rating = old_rating
                new_rank = old_rank

                test_ratio = (
                    (passed_test_count / max(1, passed_test_count + 1))
                    if not is_accepted
                    else 1.0
                )

                if is_accepted and not already_solved:
                    # Tính điểm thưởng Mode 1 (100% có nhân hệ số Event) và rating delta tăng
                    score_earned = RatingEngine.calculate_problem_score(
                        problem_rating, is_mode1=True, event_multiplier=event_mult
                    )
                    rating_delta = RatingEngine.calculate_problem_rating_delta(
                        user_rating=old_rating,
                        problem_rating=problem_rating,
                        is_mode1=True,
                        event_multiplier=event_mult,
                    )
                    new_rating = old_rating + rating_delta
                    new_rank = get_rank_by_rating(new_rating)

                    # Cập nhật thông số thí sinh
                    await user_repo.update_stats(
                        discord_id=discord_id,
                        is_accepted=True,
                        is_mode1=True,
                        score_delta=score_earned,
                        rating_delta=rating_delta,
                        new_rank=new_rank,
                    )

                    # Ghi nhật ký rating
                    await rating_repo.log_rating_change(
                        discord_id=discord_id,
                        old_rating=old_rating,
                        new_rating=new_rating,
                        problem_id=problem_id,
                        reason=f"Giải đúng bài trên Codeforces Mode 1 ({event_tag if is_event else '85% Điểm (Giảm 15%)'})",
                    )
                elif not is_accepted:
                    # Trừ điểm phong độ khi làm sai trên Codeforces (có xét tỷ lệ test và bảo vệ tân binh)
                    rating_delta = RatingEngine.calculate_problem_rating_penalty(
                        user_rating=old_rating,
                        problem_rating=problem_rating,
                        is_mode1=True,
                        is_event=is_event,
                        tests_passed_ratio=test_ratio,
                    )
                    new_rating = max(0, old_rating + rating_delta)
                    new_rank = get_rank_by_rating(new_rating)

                    score_earned = RatingEngine.calculate_problem_score_penalty(
                        problem_rating=problem_rating, is_mode1=True
                    )

                    await user_repo.update_stats(
                        discord_id=discord_id,
                        is_accepted=False,
                        is_mode1=True,
                        score_delta=score_earned,
                        rating_delta=rating_delta,
                        new_rank=new_rank,
                    )

                    await rating_repo.log_rating_change(
                        discord_id=discord_id,
                        old_rating=old_rating,
                        new_rating=new_rating,
                        problem_id=problem_id,
                        reason=f"Làm sai ({verdict_name}) trên Codeforces - Trừ phong độ",
                    )
                else:
                    # Đã từng giải đúng trước đó
                    await user_repo.update_stats(
                        discord_id=discord_id,
                        is_accepted=True,
                        is_mode1=True,
                        score_delta=0.0,
                        rating_delta=0,
                    )

                # Lưu bản ghi bài nộp
                time_consumed_ms = sub.get("timeConsumedMillis", 0)
                memory_consumed_bytes = sub.get("memoryConsumedBytes", 0)

                await sub_repo.create_submission(
                    discord_id=discord_id,
                    problem_id=problem_id,
                    problem_name=problem_name,
                    language=sub.get("programmingLanguage", "Không rõ"),
                    verdict=verdict_name,
                    score=score_earned,
                    execution_time=round(time_consumed_ms / 1000.0, 2),
                    memory=round(memory_consumed_bytes / (1024 * 1024), 1),
                    tests_passed=sub.get("passedTestCount", 0),
                    total_tests=sub.get("passedTestCount", 0),
                    cf_submission_id=sub_id,
                    contest_id=contest_id,
                    mode=1,
                )

                await cf_repo.update_last_submission_id(discord_id, sub_id)

            # Đồng bộ role và gửi thông báo
            await self._notify_and_sync_role(
                discord_id=discord_id,
                handle=handle,
                problem_id=problem_id,
                problem_name=problem_name,
                contest_id=contest_id,
                language=sub.get("programmingLanguage", "Không rõ"),
                verdict_name=verdict_name,
                emoji=emoji,
                color=color,
                score_earned=score_earned,
                is_accepted=is_accepted,
                old_rating=old_rating,
                new_rating=new_rating,
                old_rank=old_rank,
                new_rank=new_rank,
            )

    async def _notify_and_sync_role(
        self,
        discord_id: int,
        handle: str,
        problem_id: str,
        problem_name: str,
        contest_id: int | None,
        language: str,
        verdict_name: str,
        emoji: str,
        color: int,
        score_earned: float,
        is_accepted: bool,
        old_rating: int,
        new_rating: int,
        old_rank: str,
        new_rank: str,
    ) -> None:
        """Gửi Rich Embed thông báo kết quả và kích hoạt đồng bộ Role Discord."""
        user_discord: discord.User | None = self.bot.get_user(discord_id)
        if not user_discord:
            try:
                user_discord = await self.bot.fetch_user(discord_id)
            except Exception:
                pass

        user_mention = user_discord.mention if user_discord else f"@{handle}"

        fields = [
            {
                "name": "👤 Thí sinh",
                "value": f"{user_mention} (`{handle}`)",
                "inline": True,
            },
            {
                "name": "🧩 Bài tập",
                "value": f"[{problem_id} - {problem_name}](https://codeforces.com/contest/{contest_id}/problem/{problem_id[-1] if problem_id else 'A'})",
                "inline": True,
            },
            {"name": "💻 Ngôn ngữ", "value": f"`{language}`", "inline": True},
            {
                "name": "📊 Kết quả",
                "value": f"**{emoji} {verdict_name}**",
                "inline": True,
            },
            {
                "name": "🎯 Điểm thưởng Score (Mode 1)",
                "value": f"`+{score_earned}` pts" if score_earned > 0 else "`+0` pts",
                "inline": True,
            },
        ]

        if new_rating != old_rating:
            delta_val = new_rating - old_rating
            if delta_val > 0:
                fields.append(
                    {
                        "name": "📈 Điểm Rating Tăng",
                        "value": f"`{old_rating}` ➔ **`{new_rating}`** (`+{delta_val}` pts) 🚀",
                        "inline": True,
                    }
                )
            else:
                fields.append(
                    {
                        "name": "📉 Điểm Rating Bị Trừ",
                        "value": f"`{old_rating}` ➔ **`{new_rating}`** (`{delta_val}` pts) *(Trừ phong độ)*",
                        "inline": True,
                    }
                )
        else:
            fields.append(
                {
                    "name": "📈 Điểm Rating",
                    "value": f"`{old_rating}` pts *(Không đổi)*",
                    "inline": True,
                }
            )

        embed = create_embed(
            title=f"MODE 1: KẾT QUẢ NỘP BÀI CODEFORCES — {verdict_name.upper()}",
            description="Hệ thống vừa tự động đồng bộ kết quả nộp bài từ **Codeforces API**.",
            embed_type=EmbedType.SUBMISSION,
            fields=fields,
            color=color,
            footer_text="Codeforces Synchronizer • Đã cập nhật rating và xếp hạng",
        )

        # Đồng bộ roles trên tất cả các guild (Không spam kênh CF_ID)

        # Đồng bộ roles trên tất cả các guild
        for guild in self.bot.guilds:
            member = guild.get_member(discord_id)
            if member:
                await RoleManager.sync_user_roles(
                    guild=guild,
                    member=member,
                    old_rating=old_rating,
                    new_rating=new_rating,
                    old_rank=old_rank,
                    new_rank=new_rank,
                    bot=self.bot,
                )
        return True


# Alias tương thích
CFSyncService = CFSubmissionSyncService
