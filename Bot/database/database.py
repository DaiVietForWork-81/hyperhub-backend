"""Async Database connection, engine initialization, and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings
from utils.logger import get_logger

logger = get_logger("Database")


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""


# Async engine creation
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

# Async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency helper to yield an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initializes the database by creating all missing tables and performing lightweight migrations."""
    logger.info(
        f"Initializing database schema with connection: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrate SQLite columns if missing
        try:
            from sqlalchemy import text

            await conn.execute(
                text("ALTER TABLE users ADD COLUMN max_rating INTEGER DEFAULT 0")
            )
        except Exception:
            pass
        try:
            from sqlalchemy import text

            await conn.execute(
                text("ALTER TABLE users ADD COLUMN is_retired BOOLEAN DEFAULT 0")
            )
        except Exception:
            pass

        # Ranked 1:1 columns migration
        for col, col_type, default_val in [
            ("ranked_rating", "INTEGER", "0"),
            ("ranked_max_rating", "INTEGER", "0"),
            ("ranked_rank", "VARCHAR(16)", "'T8'"),
            ("ranked_wins", "INTEGER", "0"),
            ("ranked_losses", "INTEGER", "0"),
            ("ranked_draws", "INTEGER", "0"),
            ("ranked_streak", "INTEGER", "0"),
            ("ranked_max_streak", "INTEGER", "0"),
            ("last_duel_at", "TIMESTAMP", "NULL"),
            ("ai_violations", "INTEGER", "0"),
            ("banned_until", "TIMESTAMP", "NULL"),
            ("special_role", "VARCHAR(32)", "NULL"),
            ("special_fortune_count", "INTEGER", "0"),
            ("special_outclassed_count", "INTEGER", "0"),
            ("special_clutch_count", "INTEGER", "0"),
            ("is_doomed", "BOOLEAN", "0"),
        ]:
            try:
                from sqlalchemy import text

                await conn.execute(
                    text(
                        f"ALTER TABLE users ADD COLUMN {col} {col_type} DEFAULT {default_val}"
                    )
                )
            except Exception:
                pass

    logger.info("Database tables initialized successfully.")


async def close_db_engine() -> None:
    """Disposes and cleans up database connection pool."""
    logger.info("Closing database engine pool...")
    await engine.dispose()


import aiosqlite
from pathlib import Path


class Database:
    """HyperHub SQLite database manager for moderation, cooldowns, warns and config."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database chưa được khởi tạo, hãy gọi connect() trước")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA synchronous = NORMAL")
        await self._conn.execute("PRAGMA cache_size = -64000")  # 64MB RAM cache
        await self._conn.execute("PRAGMA temp_store = MEMORY")
        # Đăng ký hàm Unicode LOWER hỗ trợ tiếng Việt toàn diện trong SQLite queries
        await self._conn.create_function("lower", 1, lambda s: s.lower() if s is not None else None)
        await self._create_tables()
        await self._conn.commit()

    async def _create_tables(self) -> None:
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_change_text TEXT NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kick_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mute_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                duration INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ban_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                is_temporary INTEGER NOT NULL DEFAULT 0,
                duration INTEGER,
                start_time TEXT NOT NULL,
                end_time TEXT
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_unbans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS warn_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                moderator_id INTEGER NOT NULL,
                moderator_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mod_roles (
                role_id INTEGER PRIMARY KEY,
                added_by INTEGER NOT NULL,
                added_at TEXT NOT NULL
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                file_name TEXT,
                file_size_bytes INTEGER DEFAULT 0,
                file_type TEXT,
                estimated_level TEXT,
                question_count INTEGER DEFAULT 0,
                page_count INTEGER DEFAULT 0,
                author_id INTEGER NOT NULL,
                author_name TEXT,
                channel_id INTEGER,
                message_id INTEGER,
                jump_url TEXT,
                timestamp TEXT NOT NULL,
                file_hash TEXT,
                raw_text TEXT,
                notes TEXT
            )
            """
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_archive_subject ON documents_archive (subject)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_doc_archive_timestamp ON documents_archive (timestamp)"
        )
        try:
            await self._conn.execute("ALTER TABLE documents_archive ADD COLUMN file_hash TEXT")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE documents_archive ADD COLUMN raw_text TEXT")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE documents_archive ADD COLUMN notes TEXT")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE documents_archive ADD COLUMN source_drive_id TEXT")
        except Exception:
            pass
        for _col in ("verdict TEXT", "exam_track TEXT", "confidence REAL"):
            try:
                await self._conn.execute(f"ALTER TABLE documents_archive ADD COLUMN {_col}")
            except Exception:
                pass
        try:
            await self._conn.execute("ALTER TABLE documents_archive ADD COLUMN is_chunked INTEGER DEFAULT 0")
        except Exception:
            pass
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                part_no INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                cdn_url TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(doc_id, part_no)
            )
            """
        )
        try:
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks (doc_id)"
            )
        except Exception:
            pass
        try:
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_archive_hash ON documents_archive (file_hash)"
            )
        except Exception:
            pass
        try:
            await self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_archive_drive ON documents_archive (source_drive_id)"
            )
        except Exception:
            pass

        await self._conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title,
                file_name,
                subject,
                raw_text,
                content=documents_archive,
                content_rowid=id,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS doc_fts_insert AFTER INSERT ON documents_archive BEGIN
                INSERT INTO documents_fts(rowid, title, file_name, subject, raw_text)
                VALUES (new.id, new.title, new.file_name, new.subject, new.raw_text);
            END
            """
        )
        await self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS doc_fts_delete AFTER DELETE ON documents_archive BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, file_name, subject, raw_text)
                VALUES ('delete', old.id, old.title, old.file_name, old.subject, old.raw_text);
            END
            """
        )
        await self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS doc_fts_update AFTER UPDATE ON documents_archive BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, file_name, subject, raw_text)
                VALUES ('delete', old.id, old.title, old.file_name, old.subject, old.raw_text);
                INSERT INTO documents_fts(rowid, title, file_name, subject, raw_text)
                VALUES (new.id, new.title, new.file_name, new.subject, new.raw_text);
            END
            """
        )

        # Bảng lưu trữ vector embeddings ngữ nghĩa cho tài liệu
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_embeddings (
                doc_id INTEGER PRIMARY KEY,
                model_name TEXT NOT NULL,
                embedding BLOB NOT NULL,
                dim INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES documents_archive(id) ON DELETE CASCADE
            )
            """
        )
        await self._conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS doc_embed_delete AFTER DELETE ON documents_archive BEGIN
                DELETE FROM document_embeddings WHERE doc_id = old.id;
            END
            """
        )

        # Đảm bảo index FTS5 luôn đồng bộ với dữ liệu hiện có trong documents_archive
        try:
            await self._conn.execute("INSERT INTO documents_fts(documents_fts) VALUES('rebuild')")
        except Exception:
            pass

        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        # Bảng lưu tài khoản Discord đã liên kết web (KHÔNG lưu access token)
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS linked_accounts (
                discord_id INTEGER PRIMARY KEY,
                username TEXT,
                global_name TEXT,
                avatar_url TEXT,
                email TEXT,
                verified INTEGER DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                login_count INTEGER DEFAULT 1
            )
            """
        )

    async def execute(self, sql: str, *params) -> None:
        await self.connection.execute(sql, params)
        await self.connection.commit()

    async def fetchone(self, sql: str, *params) -> aiosqlite.Row | None:
        cursor = await self.connection.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, *params) -> list[aiosqlite.Row]:
        cursor = await self.connection.execute(sql, params)
        return await cursor.fetchall()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
