"""Repository handling User entity operations."""

import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.models import User


class UserRepository:
    """Encapsulates database operations for users."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, discord_id: int) -> User | None:
        """Fetches a user by Discord ID with CF account relation loaded."""
        stmt = select(User).where(User.discord_id == discord_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, discord_id: int) -> tuple[User, bool]:
        """Gets an existing user or creates a new one with default initial stats."""
        user = await self.get_by_id(discord_id)
        if user:
            return user, False

        user = User(
            discord_id=discord_id,
            rating=0,
            max_rating=0,
            rank="T8",
            is_retired=False,
            total_solved=0,
            total_submissions=0,
            accepted=0,
            wrong_answers=0,
            mode1_solved=0,
            mode2_solved=0,
            total_score=0.0,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            updated_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def update_stats(
        self,
        discord_id: int,
        is_accepted: bool,
        is_mode1: bool,
        score_delta: float = 0.0,
        rating_delta: int = 0,
        new_rank: str | None = None,
    ) -> User | None:
        """Atomically updates a user's submission metrics, score, rating, max rating, and rank."""
        user = await self.get_by_id(discord_id)
        if not user:
            user, _ = await self.get_or_create(discord_id)

        user.total_submissions += 1
        if is_accepted:
            user.accepted += 1
            user.total_solved += 1
            if is_mode1:
                user.mode1_solved += 1
            else:
                user.mode2_solved += 1
        else:
            user.wrong_answers += 1

        user.total_score = max(0.0, user.total_score + score_delta)
        user.rating = max(0, user.rating + rating_delta)
        user.max_rating = max(user.max_rating or 0, user.rating)

        if new_rank:
            user.rank = new_rank
            if new_rank == "RHT1":
                user.is_retired = True
        elif not user.is_retired and user.rank != "RHT1":
            from services.rank import get_rank_by_rating
            user.rank = get_rank_by_rating(user.rating)

        user.updated_at = datetime.datetime.now(datetime.timezone.utc)

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_rating_and_rank(
        self, discord_id: int, new_rating: int, new_rank: str
    ) -> User | None:
        """Updates user's rating and rank directly."""
        user = await self.get_by_id(discord_id)
        if not user:
            user, _ = await self.get_or_create(discord_id)

        user.rating = max(0, new_rating)
        user.max_rating = max(user.max_rating or 0, user.rating)
        user.rank = new_rank
        if new_rank == "RHT1":
            user.is_retired = True

        user.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def set_retired_status(
        self, discord_id: int, is_retired: bool
    ) -> User | None:
        """Cập nhật trạng thái giải nghệ (RHT1 / Retired) cho thành viên."""
        user = await self.get_by_id(discord_id)
        if not user:
            user, _ = await self.get_or_create(discord_id)

        user.is_retired = is_retired
        if is_retired and user.rank != "RHT1":
            user.rank = "RHT1"
        user.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_leaderboard(
        self,
        page: int = 1,
        per_page: int = 10,
        sort_by: str = "rating",
        include_retired: bool = False,
    ) -> tuple[list[User], int]:
        """Lấy danh sách người dùng trên bảng xếp hạng (Mặc định: KHÔNG tính thành viên đã giải nghệ RHT1)."""
        if sort_by == "overall":
            order_col = (User.rating + User.ranked_rating) / 2.0
            secondary_order = desc(User.rating)
        elif sort_by == "ranked":
            order_col = User.ranked_rating
            secondary_order = desc(User.ranked_wins)
        elif sort_by == "score":
            order_col = User.total_score
            secondary_order = desc(User.total_solved)
        else:
            order_col = User.rating
            secondary_order = desc(User.total_solved)

        base_filter = (
            [User.is_retired.is_(False), User.rank != "RHT1"]
            if not include_retired
            else []
        )
        # Chỉ hiển thị các Discord ID thật (Snowflake >= 16 chữ số)
        base_filter.append(User.discord_id >= 1000000000000000)
        if settings.OWNER_ID and settings.OWNER_ID > 0:
            base_filter.append(User.discord_id != settings.OWNER_ID)

        # Count total
        count_stmt = select(func.count(User.discord_id))
        if base_filter:
            count_stmt = count_stmt.where(*base_filter)
        total_count = (await self.session.execute(count_stmt)).scalar() or 0

        # Query page
        offset = (page - 1) * per_page
        stmt = select(User)
        if base_filter:
            stmt = stmt.where(*base_filter)
        stmt = (
            stmt.order_by(desc(order_col), secondary_order, User.discord_id)
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total_count

    async def get_user_standing(self, discord_id: int, sort_by: str = "rating") -> int:
        """Lấy thứ hạng hiện tại của một user trên bảng xếp hạng (1-based). Trả về 0 nếu chưa xếp hạng hoặc đã giải nghệ / Owner."""
        if settings.OWNER_ID and discord_id == settings.OWNER_ID:
            return 0

        user = await self.get_by_id(discord_id)
        if not user or user.is_retired or user.rank == "RHT1":
            return 0

        val = user.rating if sort_by == "rating" else user.total_score
        col = User.rating if sort_by == "rating" else User.total_score

        filter_conds = [
            col > val,
            User.is_retired.is_(False),
            User.rank != "RHT1",
        ]
        if settings.OWNER_ID and settings.OWNER_ID > 0:
            filter_conds.append(User.discord_id != settings.OWNER_ID)

        stmt = select(func.count(User.discord_id)).where(*filter_conds)
        ahead_count = (await self.session.execute(stmt)).scalar() or 0
        return ahead_count + 1

    async def update_ranked_stats(
        self,
        discord_id: int,
        rating_delta: float,
        is_winner: bool,
        is_draw: bool = False,
        new_rank: str | None = None,
    ) -> User:
        """Cập nhật điểm và thống kê Ranked 1:1 cho thí sinh."""
        user = await self.get_by_id(discord_id)
        if not user:
            user, _ = await self.get_or_create(discord_id)

        user.ranked_rating = max(0, int(round(user.ranked_rating + rating_delta)))
        if user.ranked_rating > user.ranked_max_rating:
            user.ranked_max_rating = user.ranked_rating

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        user.last_duel_at = now_utc

        if is_draw:
            user.ranked_draws += 1
        elif is_winner:
            user.ranked_wins += 1
            user.ranked_streak = (user.ranked_streak or 0) + 1
            user.ranked_max_streak = max(user.ranked_max_streak or 0, user.ranked_streak)
        else:
            user.ranked_losses += 1
            user.ranked_streak = 0

        if new_rank:
            user.ranked_rank = new_rank
        else:
            from services.rank import get_rank_by_rating
            user.ranked_rank = get_rank_by_rating(user.ranked_rating)

        user.updated_at = now_utc
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_duel_cooldown(
        self, discord_id: int, cooldown_seconds: int = 300
    ) -> tuple[bool, int, str]:
        """
        Kiểm tra xem người chơi có đang trong thời gian nghỉ (cooldown) giữa các trận Ranked không (mặc định 5 phút = 300s).
        Trả về: (is_on_cooldown, remaining_seconds, remaining_time_str)
        """
        user = await self.get_by_id(discord_id)
        if not user or not user.last_duel_at:
            return False, 0, ""

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        last_duel = user.last_duel_at
        if last_duel.tzinfo is None:
            last_duel = last_duel.replace(tzinfo=datetime.timezone.utc)

        cooldown_until = last_duel + datetime.timedelta(seconds=cooldown_seconds)
        if cooldown_until > now_utc:
            remaining_secs = int((cooldown_until - now_utc).total_seconds())
            mins, secs = divmod(remaining_secs, 60)
            time_str = f"{mins} phút {secs} giây" if mins > 0 else f"{secs} giây"
            return True, remaining_secs, time_str

        return False, 0, ""

    async def update_last_duel_at(self, discord_id: int) -> None:
        """Cập nhật mốc thời gian ván đấu vừa kết thúc."""
        user = await self.get_by_id(discord_id)
        if not user:
            user, _ = await self.get_or_create(discord_id)
        user.last_duel_at = datetime.datetime.now(datetime.timezone.utc)
        user.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.session.commit()

    async def apply_ai_violation(self, discord_id: int) -> tuple[int, datetime.datetime, str]:
        """
        Ghi nhận vi phạm gian lận AI và áp dụng hình phạt cấm thi đấu lũy tiến:
        - Lần 1: Cấm 1 tiếng
        - Lần 2: Cấm 3 tiếng
        - Lần 3: Cấm 1 ngày (24 tiếng)
        - Lần 4 trở đi: Cấm 3 ngày (72 tiếng)
        """
        user = await self.get_by_id(discord_id)
        if not user:
            user, _ = await self.get_or_create(discord_id)

        user.ai_violations = (user.ai_violations or 0) + 1
        now_utc = datetime.datetime.now(datetime.timezone.utc)

        if user.ai_violations == 1:
            duration = datetime.timedelta(hours=1)
            duration_str = "1 tiếng"
        elif user.ai_violations == 2:
            duration = datetime.timedelta(hours=3)
            duration_str = "3 tiếng"
        elif user.ai_violations == 3:
            duration = datetime.timedelta(days=1)
            duration_str = "1 ngày (24 tiếng)"
        else:
            duration = datetime.timedelta(days=3)
            duration_str = "3 ngày (72 tiếng)"

        user.banned_until = now_utc + duration
        user.updated_at = now_utc
        await self.session.commit()
        await self.session.refresh(user)
        return user.ai_violations, user.banned_until, duration_str

    async def pardon_user(self, discord_id: int) -> bool:
        """Lệnh ân xá: Gỡ bỏ hoàn toàn lệnh cấm thi đấu do gian lận AI."""
        user = await self.get_by_id(discord_id)
        if not user:
            return False

        user.banned_until = None
        user.updated_at = datetime.datetime.now(datetime.timezone.utc)
        await self.session.commit()
        await self.session.refresh(user)
        return True

    async def get_ban_status(self, discord_id: int) -> tuple[bool, int, str]:
        """
        Kiểm tra xem người dùng có đang trong thời gian bị cấm thi đấu hay không.
        Trả về: (is_banned, remaining_seconds, remaining_time_str)
        """
        user = await self.get_by_id(discord_id)
        if not user or not user.banned_until:
            return False, 0, ""

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        banned_until = user.banned_until
        if banned_until.tzinfo is None:
            banned_until = banned_until.replace(tzinfo=datetime.timezone.utc)

        if banned_until > now_utc:
            remaining_secs = int((banned_until - now_utc).total_seconds())
            hours, rem = divmod(remaining_secs, 3600)
            mins, secs = divmod(rem, 60)
            if hours > 24:
                days = hours // 24
                h = hours % 24
                time_str = f"{days} ngày {h} giờ {mins} phút"
            elif hours > 0:
                time_str = f"{hours} giờ {mins} phút {secs} giây"
            else:
                time_str = f"{mins} phút {secs} giây"
            return True, remaining_secs, time_str

        return False, 0, ""

    async def get_recent_duel_matches(self, discord_id: int, limit: int = 4) -> list[dict]:
        """
        Lấy danh sách các trận đấu gần đây của thí sinh từ bảng duel_matches.
        Trả về list dict chứa kết quả (WIN/LOSS/DRAW), rating delta, đối thủ, thời gian.
        """
        from database.models import DuelMatch
        stmt = (
            select(DuelMatch)
            .where(
                (DuelMatch.player1_id == discord_id) | (DuelMatch.player2_id == discord_id),
                DuelMatch.status == "FINISHED",
            )
            .order_by(desc(DuelMatch.finished_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        matches = result.scalars().all()

        recent_list = []
        for m in matches:
            is_p1 = (m.player1_id == discord_id)
            opponent_id = m.player2_id if is_p1 else m.player1_id
            delta = m.p1_rating_delta if is_p1 else m.p2_rating_delta

            if m.winner_id is None:
                outcome = "DRAW"
            elif m.winner_id == discord_id:
                outcome = "WIN"
            else:
                outcome = "LOSS"

            time_str = m.finished_at.strftime("%d/%m/%Y · %H:%M") if m.finished_at else "Vừa xong"
            recent_list.append({
                "match_code": m.match_code,
                "opponent_id": opponent_id,
                "outcome": outcome,
                "delta": delta,
                "rounds": m.current_round,
                "time_str": time_str,
            })
        return recent_list
