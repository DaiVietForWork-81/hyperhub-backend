"""Declarative SQLAlchemy Models representing users, Codeforces accounts, submissions, problems, and ratings."""

import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


class User(Base):
    """Represents a Discord member participating in the Competitive Programming platform."""

    __tablename__ = "users"

    discord_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    codeforces_handle: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # Freedom Mode Stats
    rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[str] = mapped_column(String(16), default="T8", nullable=False)

    # Ranked 1:1 Mode Stats
    ranked_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranked_max_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranked_rank: Mapped[str] = mapped_column(String(16), default="T8", nullable=False)
    ranked_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranked_losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranked_draws: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranked_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ranked_max_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_duel_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_violations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    banned_until: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Dynamic Special Titles & Achievements
    special_role: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    special_fortune_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    special_outclassed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    special_clutch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_doomed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_retired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    total_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_submissions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wrong_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode1_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode2_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    cf_account: Mapped[Optional["CFAccount"]] = relationship(
        "CFAccount", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    submissions: Mapped[list["Submission"]] = relationship(
        "Submission", back_populates="user", cascade="all, delete-orphan"
    )
    rating_history: Mapped[list["RatingHistory"]] = relationship(
        "RatingHistory", back_populates="user", cascade="all, delete-orphan"
    )
    rank_history: Mapped[list["RankHistory"]] = relationship(
        "RankHistory", back_populates="user", cascade="all, delete-orphan"
    )


class CFAccount(Base):
    """Codeforces account linking and ownership verification records."""

    __tablename__ = "cf_accounts"

    discord_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), primary_key=True
    )
    cf_handle: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    last_synced_submission_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="cf_account")


class Submission(Base):
    """Tracks both Mode 1 (CF sync) and Mode 2 (Discord Judge) submissions."""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.discord_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    cf_submission_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    problem_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    contest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )  # 1 = CF Sync, 2 = In-Discord
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    execution_time: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    memory: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tests_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_suspicion_score: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="submissions")


class Problem(Base):
    """Cached Codeforces problem metadata and rank accessibility requirements."""

    __tablename__ = "problems"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "1700A"
    contest_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    index: Mapped[str] = mapped_column(String(8), nullable=False)  # e.g. "A", "B1"
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    div: Mapped[str | None] = mapped_column(String(32), nullable=True)  # e.g. "Div. 2"
    tags: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # JSON or comma-separated
    time_limit: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    memory_limit: Mapped[int] = mapped_column(Integer, default=256, nullable=False)
    min_rank_required: Mapped[str] = mapped_column(
        String(16), default="T8", nullable=False
    )
    cached_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


class Contest(Base):
    """Cached Codeforces contest catalog entries."""

    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    writers: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    div: Mapped[str | None] = mapped_column(String(32), nullable=True)
    min_rank_required: Mapped[str] = mapped_column(
        String(16), default="T8", nullable=False
    )
    phase: Mapped[str] = mapped_column(String(32), default="FINISHED", nullable=False)
    start_time: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RatingHistory(Base):
    """Audit log of all rating updates, contest performances, and problem solves."""

    __tablename__ = "rating_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.discord_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    old_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    new_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    performance: Mapped[float | None] = mapped_column(Float, nullable=True)
    contest_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str] = mapped_column(
        String(128), default="Problem Solve", nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="rating_history")


class RankHistory(Base):
    """Historical timeline of rank tier promotions and demotions."""

    __tablename__ = "rank_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.discord_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    old_rank: Mapped[str] = mapped_column(String(16), nullable=False)
    new_rank: Mapped[str] = mapped_column(String(16), nullable=False)
    old_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    new_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="rank_history")


class DuelMatch(Base):
    """Represents a 1:1 Ranked Duel Match between two players."""

    __tablename__ = "duel_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_code: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    player1_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), nullable=False
    )
    player2_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.discord_id", ondelete="CASCADE"), nullable=False
    )
    p1_lives: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    p2_lives: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    current_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    p1_rating_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    p2_rating_delta: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="IN_PROGRESS", nullable=False
    )  # IN_PROGRESS, FINISHED, CANCELLED
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class UserTokenTier(Base):
    """Quản lý hạn mức Token hàng ngày và Gói thành viên Hyper của người dùng."""

    __tablename__ = "user_token_tiers"

    discord_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    tier: Mapped[str] = mapped_column(
        String(32), default="Free", nullable=False
    )  # Free, Pro, Ultra, Elite
    daily_tokens: Mapped[int] = mapped_column(
        Integer, default=200, nullable=False
    )
    used_tokens_today: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    last_reset_date: Mapped[str] = mapped_column(
        String(10), default="", nullable=False
    )  # Định dạng YYYY-MM-DD theo giờ Việt Nam (UTC+7)
    total_generated: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )


class ExamJob(Base):
    """Lưu trữ lịch sử các phiên tạo đề thi, bài tập và hướng dẫn giải."""

    __tablename__ = "exam_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    discord_id: Mapped[int] = mapped_column(
        BigInteger, index=True, nullable=False
    )
    thread_id: Mapped[int] = mapped_column(
        BigInteger, index=True, nullable=False
    )
    subject: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    style: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    length_tier: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # Ngắn, Vừa, Dài, To
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # Lite, Flash, Pro, Max, Ultra
    output_format: Mapped[str] = mapped_column(
        String(32), default="Both", nullable=False
    )  # PDF, Word, Both
    token_cost: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING", nullable=False
    )  # PENDING, GENERATING, COMPLETED, FAILED, CLOSED
    exam_file_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    solution_file_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    database_msg_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    checkpoint_data: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    is_shuffled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

