"""
Database connection and session management.

Provides async SQLAlchemy engine and session factory.
"""

import logging
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.pool import NullPool

from config import settings
from .models import Base

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize database connection and create tables."""
        if self._initialized:
            return True

        database_url = settings.database_url
        if not database_url:
            logger.warning("DATABASE_URL not configured")
            return False

        try:
            # Convert postgres:// to postgresql+asyncpg://
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif database_url.startswith("postgresql://"):
                database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            # Create async engine
            self.engine = create_async_engine(
                database_url,
                echo=settings.debug,
                poolclass=NullPool,  # Better for serverless/Railway
            )

            # Create session factory
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )

            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._initialized = True
            logger.info("Database initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False

    async def close(self):
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
            self._initialized = False
            logger.info("Database connection closed")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        if not self._initialized:
            await self.initialize()

        if not self.session_factory:
            raise RuntimeError("Database not initialized")

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise

    async def is_available(self) -> bool:
        """Check if database is available."""
        if not self._initialized:
            return await self.initialize()
        return self._initialized

    async def health_check(self) -> dict:
        """Perform health check on database."""
        from sqlalchemy import text

        try:
            if not self._initialized:
                await self.initialize()

            async with self.session() as session:
                result = await session.execute(text("SELECT 1"))
                result.scalar()

            return {
                "status": "healthy",
                "initialized": self._initialized,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }


# Singleton instance
_database: Optional[Database] = None


def get_database() -> Database:
    """Get the database singleton."""
    global _database
    if _database is None:
        _database = Database()
    return _database


async def init_database() -> bool:
    """Initialize the database."""
    db = get_database()
    return await db.initialize()


async def close_database():
    """Close the database connection."""
    global _database
    if _database:
        await _database.close()
        _database = None
