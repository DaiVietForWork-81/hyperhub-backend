"""Repository for cached Problems and Contests."""

import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Contest, Problem


class ProblemRepository:
    """Manages cached problems and contests."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_problem(self, problem_id: str) -> Problem | None:
        stmt = select(Problem).where(Problem.id == problem_id.upper())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_problem(
        self,
        problem_id: str,
        contest_id: int,
        index: str,
        name: str,
        rating: int | None = None,
        div: str | None = None,
        tags: str | None = None,
        time_limit: float = 2.0,
        memory_limit: int = 256,
        min_rank_required: str = "T8",
    ) -> Problem:
        """Saves or updates problem metadata in cache."""
        prob = await self.get_problem(problem_id)
        if prob:
            prob.contest_id = contest_id
            prob.index = index
            prob.name = name
            prob.rating = rating
            prob.div = div
            prob.tags = tags
            prob.time_limit = time_limit
            prob.memory_limit = memory_limit
            prob.min_rank_required = min_rank_required
            prob.cached_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            prob = Problem(
                id=problem_id.upper(),
                contest_id=contest_id,
                index=index,
                name=name,
                rating=rating,
                div=div,
                tags=tags,
                time_limit=time_limit,
                memory_limit=memory_limit,
                min_rank_required=min_rank_required,
                cached_at=datetime.datetime.now(datetime.timezone.utc),
            )
            self.session.add(prob)

        await self.session.commit()
        await self.session.refresh(prob)
        return prob

    async def get_contest(self, contest_id: int) -> Contest | None:
        stmt = select(Contest).where(Contest.id == contest_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_contest(
        self,
        contest_id: int,
        name: str,
        writers: str | None = None,
        rating: int | None = None,
        div: str | None = None,
        min_rank_required: str = "T8",
        phase: str = "FINISHED",
        start_time: datetime.datetime | None = None,
    ) -> Contest:
        """Saves or updates contest metadata."""
        contest = await self.get_contest(contest_id)
        if contest:
            contest.name = name
            contest.writers = writers
            contest.rating = rating
            contest.div = div
            contest.min_rank_required = min_rank_required
            contest.phase = phase
            contest.start_time = start_time
        else:
            contest = Contest(
                id=contest_id,
                name=name,
                writers=writers,
                rating=rating,
                div=div,
                min_rank_required=min_rank_required,
                phase=phase,
                start_time=start_time,
            )
            self.session.add(contest)

        await self.session.commit()
        await self.session.refresh(contest)
        return contest

    async def list_recent_contests(self, limit: int = 10) -> list[Contest]:
        """Returns the most recent contests."""
        stmt = select(Contest).order_by(Contest.id.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_problems_by_contest(self, contest_id: int) -> list[Problem]:
        """Returns all problems for a given contest."""
        stmt = (
            select(Problem)
            .where(Problem.contest_id == contest_id)
            .order_by(Problem.index.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
