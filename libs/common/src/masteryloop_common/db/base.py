from collections.abc import AsyncGenerator, Generator

from masteryloop_common.config import get_settings
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

settings = get_settings()

# Asynchronous SQLAlchemy Engine & Session Factory (asyncpg)
async_engine = create_async_engine(
    settings.async_database_url,
    echo=settings.ENVIRONMENT == "development",
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Synchronous SQLAlchemy Engine & Session Factory (psycopg3 / migrations / scripts)
sync_engine = create_engine(
    settings.sync_database_url,
    echo=settings.ENVIRONMENT == "development",
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2.0 models."""


async def get_async_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI/Service dependency yielding an asynchronous database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Alias for dependency injection
get_db_session = get_async_db_session


def get_sync_db_session() -> Generator[Session, None, None]:
    """Yields a synchronous database session for scripts and batch tasks."""
    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
