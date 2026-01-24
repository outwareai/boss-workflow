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

            # Create async engine with optimized connection pooling
            # For production workloads (10 persistent + 20 burst connections)
            self.engine = create_async_engine(
                database_url,
                echo=settings.debug,
                pool_size=10,              # 10 persistent connections
                max_overflow=20,           # +20 burst connections (30 total)
                pool_pre_ping=True,        # Validate before use (prevent stale)
                pool_recycle=3600,         # Recycle every hour (DB restarts)
                pool_timeout=30,           # 30s wait for connection
                connect_args={
                    "server_settings": {
                        "application_name": "boss-workflow",
                        "jit": "off"       # Disable JIT for faster simple queries
                    }
                },
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

            # Run migrations for new columns on existing tables
            await self._run_migrations()

            self._initialized = True
            logger.info("Database initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False

    async def _run_migrations(self):
        """Run schema migrations for new columns on existing tables."""
        from sqlalchemy import text

        # Define columns to add to existing tables
        # Format: (table_name, column_name, column_definition)
        migrations = [
            # attendance_records table - new columns
            ("attendance_records", "is_boss_reported", "BOOLEAN DEFAULT FALSE"),
            ("attendance_records", "reported_by", "VARCHAR(100)"),
            ("attendance_records", "reported_by_id", "VARCHAR(50)"),
            ("attendance_records", "reason", "TEXT"),
            ("attendance_records", "affected_date", "DATE"),
            ("attendance_records", "duration_minutes", "INTEGER"),
            ("attendance_records", "notification_sent", "BOOLEAN DEFAULT FALSE"),
        ]

        async with self.engine.begin() as conn:
            for table_name, column_name, column_def in migrations:
                try:
                    # SECURITY FIX: Check if column exists using parameterized query
                    result = await conn.execute(text("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = :table
                        AND column_name = :column
                    """), {"table": table_name, "column": column_name})
                    exists = result.fetchone()

                    if not exists:
                        logger.info(f"Migration: Adding column {table_name}.{column_name}")

                        # SECURITY FIX: Validate identifiers before DDL
                        # Only allow alphanumeric and underscores (prevents SQL injection)
                        if not table_name.replace('_', '').isalnum():
                            raise ValueError(f"Invalid table name: {table_name}")
                        if not column_name.replace('_', '').isalnum():
                            raise ValueError(f"Invalid column name: {column_name}")

                        # Safe to use in DDL after validation
                        # Note: column_def is internally controlled, not user input
                        await conn.execute(text(f"""
                            ALTER TABLE {table_name}
                            ADD COLUMN {column_name} {column_def}
                        """))
                        logger.info(f"  ✓ Added {column_name}")
                except Exception as e:
                    logger.warning(f"Migration error for {table_name}.{column_name}: {e}")

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
