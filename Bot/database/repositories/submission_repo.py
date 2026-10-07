"""Repository handling Submission records, deduplication, and submission history."""

import datetime
import inspect

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Submission


class SubmissionRepository:
    """Manages database operations for submissions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def exists_by_cf_id(self, cf_submission_id: int) -> bool:
        """Checks if a Codeforces submission ID has already been recorded (deduplication)."""
        stmt = select(func.count(Submission.id)).where(
            Submission.cf_submission_id == cf_submission_id
        )
        count = (await self.session.execute(stmt)).scalar() or 0
        return count > 0

    async def create_submission(
        self,
        discord_id: int,
        problem_id: str,
        mode: int,
        language: str,
        verdict: str,
        score: float = 0.0,
        execution_time: float = 0.0,
        memory: float = 0.0,
        tests_passed: int = 0,
        total_tests: int = 0,
        ai_suspicion_score: float = 0.0,
        cf_submission_id: int | None = None,
        contest_id: int | None = None,
        code_snippet: str | None = None,
        problem_name: str | None = None,
    ) -> Submission:
        """Records a new submission in the database."""
        sub = Submission(
            discord_id=discord_id,
            cf_submission_id=cf_submission_id,
            problem_id=problem_id.upper(),
            contest_id=contest_id,
            mode=mode,
            language=language,
            verdict=verdict,
            score=score,
            execution_time=execution_time,
            memory=memory,
            tests_passed=tests_passed,
            total_tests=total_tests,
            ai_suspicion_score=ai_suspicion_score,
            code_snippet=code_snippet,
            submitted_at=datetime.datetime.now(datetime.timezone.utc),
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def get_attempt_count(self, discord_id: int, problem_id: str) -> int:
        """Returns the number of prior attempts by a user on a given problem."""
        stmt = select(func.count(Submission.id)).where(
            Submission.discord_id == discord_id,
            Submission.problem_id == problem_id.upper(),
        )
        return (await self.session.execute(stmt)).scalar() or 0

    async def has_solved(self, discord_id: int, problem_id: str) -> bool:
        """Returns True if the user has at least one Accepted verdict on this problem."""
        stmt = select(func.count(Submission.id)).where(
            Submission.discord_id == discord_id,
            Submission.problem_id == problem_id.upper(),
            Submission.verdict.ilike("%Accepted%"),
        )
        count = (await self.session.execute(stmt)).scalar() or 0
        return count > 0

    async def get_user_submissions(
        self, discord_id: int, page: int = 1, per_page: int = 10
    ) -> tuple[list[Submission], int]:
        """Returns paginated submissions for a specific user."""
        count_stmt = select(func.count(Submission.id)).where(
            Submission.discord_id == discord_id
        )
        count_res = await self.session.execute(count_stmt)
        if inspect.iscoroutine(count_res):
            count_res = await count_res
        total_count = count_res.scalar() if hasattr(count_res, "scalar") else 0
        if inspect.iscoroutine(total_count):
            total_count = await total_count
        total_count = total_count or 0

        offset = (page - 1) * per_page
        stmt = (
            select(Submission)
            .where(Submission.discord_id == discord_id)
            .order_by(desc(Submission.submitted_at))
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        if inspect.iscoroutine(result):
            result = await result

        if hasattr(result, "scalars"):
            sc = result.scalars()
            if inspect.iscoroutine(sc):
                sc = await sc
            if hasattr(sc, "all"):
                items = sc.all()
                if inspect.iscoroutine(items):
                    items = await items
                return list(items), total_count
        return [], total_count
