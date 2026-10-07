"""Problem fetcher extracting metadata, sample testcases, and constraints from Codeforces."""

import html
import re
from dataclasses import dataclass

import aiohttp

from database.database import async_session_factory
from database.repositories.problem_repo import ProblemRepository
from services.codeforces_api import cf_api
from utils.logger import get_logger

logger = get_logger("ProblemFetcher")


@dataclass
class ProblemData:
    id: str  # "1700A"
    contest_id: int
    index: str
    name: str
    rating: int | None
    time_limit: float
    memory_limit: int
    samples: list[tuple[str, str]]
    min_rank_required: str

    @property
    def sample_tests(self) -> list[tuple[str, str]]:
        return self.samples


class ProblemFetcher:
    """Retrieves and parses Codeforces problem statements and test suites."""

    @classmethod
    def parse_problem_id(cls, raw_id: str) -> tuple[int | None, str | None]:
        """Splits raw problem ID like '1700A' or '12345B1' into (contest_id, index)."""
        match = re.match(r"^(\d+)([A-Za-z0-9]+)$", raw_id.strip())
        if match:
            return int(match.group(1)), match.group(2).upper()
        return None, None

    @classmethod
    async def fetch_problem(cls, problem_id: str) -> ProblemData | None:
        """
        Fetches problem data from database cache or downloads directly from Codeforces.
        """
        contest_id, index = cls.parse_problem_id(problem_id)
        if not contest_id or not index:
            return None

        # Check DB Cache first
        async with async_session_factory() as session:
            repo = ProblemRepository(session)
            cached = await repo.get_problem(problem_id)
            if cached:
                # If cached, we can fetch live samples or use defaults
                samples = await cls._fetch_html_samples(contest_id, index)
                return ProblemData(
                    id=cached.id,
                    contest_id=cached.contest_id,
                    index=cached.index,
                    name=cached.name,
                    rating=cached.rating,
                    time_limit=cached.time_limit,
                    memory_limit=cached.memory_limit,
                    samples=samples,
                    min_rank_required=cached.min_rank_required,
                )

        # Fallback: Query Codeforces Problemset API
        try:
            p_data = await cf_api.get_problemset()
            problems = p_data.get("problems", [])
            for p in problems:
                if (
                    p.get("contestId") == contest_id
                    and p.get("index", "").upper() == index
                ):
                    name = p.get("name", f"Problem {problem_id}")
                    rating = p.get("rating", 1200)
                    tags = ", ".join(p.get("tags", []))

                    # Calculate required rank based on rating
                    min_rank = "T8"
                    if rating:
                        if rating >= 2400:
                            min_rank = "LT1"
                        elif rating >= 2100:
                            min_rank = "MT2"
                        elif rating >= 1900:
                            min_rank = "LT2"
                        elif rating >= 1600:
                            min_rank = "T3"
                        elif rating >= 1400:
                            min_rank = "T4"
                        elif rating >= 1200:
                            min_rank = "T5"
                        elif rating >= 700:
                            min_rank = "T6"
                        elif rating >= 400:
                            min_rank = "T7"

                    samples = await cls._fetch_html_samples(contest_id, index)

                    # Save to DB cache
                    async with async_session_factory() as session:
                        repo = ProblemRepository(session)
                        await repo.upsert_problem(
                            problem_id=problem_id,
                            contest_id=contest_id,
                            index=index,
                            name=name,
                            rating=rating,
                            tags=tags,
                            time_limit=2.0,
                            memory_limit=256,
                            min_rank_required=min_rank,
                        )

                    return ProblemData(
                        id=f"{contest_id}{index}".upper(),
                        contest_id=contest_id,
                        index=index,
                        name=name,
                        rating=rating,
                        time_limit=2.0,
                        memory_limit=256,
                        samples=samples,
                        min_rank_required=min_rank,
                    )
        except Exception as e:
            logger.error(f"Error fetching problem {problem_id}: {e}")

        return None

    @classmethod
    async def _fetch_html_samples(
        cls, contest_id: int, index: str
    ) -> list[tuple[str, str]]:
        """Extracts sample inputs and outputs by scraping public Codeforces problem page."""
        url = f"https://codeforces.com/contest/{contest_id}/problem/{index}"
        samples: list[tuple[str, str]] = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        inputs = re.findall(
                            r'<div class="input">[\s\S]*?<pre[^>]*>([\s\S]*?)</pre>',
                            text,
                        )
                        outputs = re.findall(
                            r'<div class="output">[\s\S]*?<pre[^>]*>([\s\S]*?)</pre>',
                            text,
                        )

                        for inp, out in zip(inputs, outputs):
                            if "test-example-line" in inp:
                                lines = re.findall(
                                    r'<div class="test-example-line[^"]*">([\s\S]*?)</div>',
                                    inp,
                                )
                                clean_inp = "\n".join(
                                    html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
                                    for line in lines
                                )
                            else:
                                clean_inp = html.unescape(
                                    re.sub(r"<br\s*/?>", "\n", inp)
                                )
                                clean_inp = html.unescape(
                                    re.sub(r"<[^>]+>", "", clean_inp)
                                ).strip()

                            if "test-example-line" in out:
                                lines = re.findall(
                                    r'<div class="test-example-line[^"]*">([\s\S]*?)</div>',
                                    out,
                                )
                                clean_out = "\n".join(
                                    html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
                                    for line in lines
                                )
                            else:
                                clean_out = html.unescape(
                                    re.sub(r"<br\s*/?>", "\n", out)
                                )
                                clean_out = html.unescape(
                                    re.sub(r"<[^>]+>", "", clean_out)
                                ).strip()

                            if clean_inp and clean_out:
                                samples.append((clean_inp, clean_out))
        except Exception as e:
            logger.warning(f"Could not scrape samples for {contest_id}{index}: {e}")

        return samples

    @classmethod
    async def get_equivalent_unrated_problem(
        cls, problem_id: str, rating: int | None = None
    ) -> ProblemData | None:
        """
        Tìm kiếm bài tập luyện tập tương đương cùng phân hạng độ khó (Rating / Tier)
        nhưng là một mã bài khác để chống gian lận (tránh xem code mẫu Unrated rồi nộp Rated).
        """
        r = rating or 800
        pid_clean = problem_id.strip().upper()

        # Bể bài tập mẫu phân loại theo từng mốc độ khó
        pool_by_rating = {
            800: ["4A", "71A", "231A", "282A", "158A", "112A", "263A", "50A"],
            1000: ["1A", "96A", "118A", "131A", "122A", "69A", "58A", "110A"],
            1200: ["4C", "455A", "189A", "466C", "492B", "339B", "479A"],
            1400: ["25A", "479C", "489C", "279B", "519B", "514A", "478B"],
            1600: ["580C", "1352C", "1360D", "1372B", "1374D", "1354B"],
            1800: ["1328C", "1360E", "1370C", "1374E1", "1365C", "1368B"],
            2000: ["1363C", "1367D", "1373D", "1366D", "1369D"],
            2200: ["1364D", "1365E", "1367F1", "1370E", "1375E"],
        }

        # Tìm mốc rating gần nhất
        closest_tier_r = min(pool_by_rating.keys(), key=lambda k: abs(k - r))
        candidates = pool_by_rating.get(closest_tier_r, ["4A", "71A"])

        # Chọn ứng viên khác với problem_id hiện tại
        chosen_id = None
        for cand in candidates:
            if cand != pid_clean:
                chosen_id = cand
                break

        if not chosen_id:
            chosen_id = "4A" if pid_clean != "4A" else "71A"

        # Tải dữ liệu bài tập tương đương
        eq_prob = await cls.fetch_problem(chosen_id)
        if eq_prob:
            return eq_prob

        # Fallback tạo nhanh ProblemData nếu không thể scrape
        return ProblemData(
            id=chosen_id,
            contest_id=int(chosen_id[:-1]) if chosen_id[:-1].isdigit() else 4,
            index=chosen_id[-1],
            name=f"Bài luyện tập tương đương ({r} pts)",
            rating=r,
            time_limit=2.0,
            memory_limit=256,
            samples=[],
            min_rank_required="T8",
        )
