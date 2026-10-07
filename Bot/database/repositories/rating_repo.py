"""Repository for recording and querying Rating and Rank history logs."""

import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import RankHistory, RatingHistory


class RatingRepository:
    """Manages audit trails for ratings and ranks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_rating_change(
        self,
        discord_id: int,
        old_rating: int,
        new_rating: int,
        performance: float | None = None,
        contest_id: int | None = None,
        problem_id: str | None = None,
        reason: str = "Problem Solve",
    ) -> RatingHistory:
        """Records a rating alteration event."""
        log = RatingHistory(
            discord_id=discord_id,
            old_rating=old_rating,
            new_rating=new_rating,
            performance=performance,
            contest_id=contest_id,
            problem_id=problem_id,
            reason=reason,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def log_rank_change(
        self,
        discord_id: int,
        old_rank: str,
        new_rank: str,
        old_rating: int,
        new_rating: int,
    ) -> RankHistory:
        """Records a rank tier promotion or demotion."""
        log = RankHistory(
            discord_id=discord_id,
            old_rank=old_rank,
            new_rank=new_rank,
            old_rating=old_rating,
            new_rating=new_rating,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_user_rating_history(
        self, discord_id: int, limit: int = 15
    ) -> list[RatingHistory]:
        """Returns recent rating logs for a user."""
        stmt = (
            select(RatingHistory)
            .where(RatingHistory.discord_id == discord_id)
            .order_by(desc(RatingHistory.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_user_rank_history(
        self, discord_id: int, limit: int = 10
    ) -> list[RankHistory]:
        """Returns recent rank changes for a user."""
        stmt = (
            select(RankHistory)
            .where(RankHistory.discord_id == discord_id)
            .order_by(desc(RankHistory.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
