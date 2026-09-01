"""SQLAlchemy 2.x asynchronous database engine and session infrastructure."""

from collections.abc import AsyncGenerator
from typing import Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


def normalize_database_url(url: str) -> str:
    """Ensure database URL has the asyncpg scheme for PostgreSQL."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def build_engine(database_url: str) -> AsyncEngine:
    """Construct an AsyncEngine with appropriate pooling parameters based on dialect."""
    normalized_url = normalize_database_url(database_url)
    engine_kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
    }
    if "sqlite" in normalized_url:
        engine_kwargs["poolclass"] = StaticPool
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["pool_size"] = settings.db_pool_size
        engine_kwargs["max_overflow"] = settings.db_max_overflow
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 300

    return create_async_engine(normalized_url, **engine_kwargs)


# Asynchronous database engine
engine: AsyncEngine = build_engine(settings.database_url)

# Async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for obtaining an isolated async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_connection() -> tuple[bool, str]:
    """Test database connectivity with a lightweight ping."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "Database connection successful"
    except Exception as exc:
        return False, f"Database connection failed: {exc!s}"


async def init_database_tables() -> None:
    """Idempotently create all database tables defined on Base metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database_engine() -> None:
    """Cleanly dispose database connection pool on application shutdown."""
    await engine.dispose()
