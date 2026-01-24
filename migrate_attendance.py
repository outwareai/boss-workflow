"""
Migration script to add missing columns to attendance_records table.
Run this once to fix the database schema.
"""

import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Convert postgres:// to postgresql+asyncpg://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


async def migrate():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        return

    engine = create_async_engine(DATABASE_URL, echo=True)

    # Columns to add with their definitions
    columns_to_add = [
        ("is_boss_reported", "BOOLEAN DEFAULT FALSE"),
        ("reported_by", "VARCHAR(100)"),
        ("reported_by_id", "VARCHAR(50)"),
        ("reason", "TEXT"),
        ("affected_date", "DATE"),
        ("duration_minutes", "INTEGER"),
        ("notification_sent", "BOOLEAN DEFAULT FALSE"),
    ]

    async with engine.begin() as conn:
        for column_name, column_def in columns_to_add:
            try:
                # SECURITY FIX: Check if column exists using parameterized query
                result = await conn.execute(text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = :table
                    AND column_name = :column
                """), {"table": "attendance_records", "column": column_name})
                exists = result.fetchone()

                if not exists:
                    print(f"Adding column: {column_name}")

                    # SECURITY FIX: Validate identifier before DDL
                    # Only allow alphanumeric and underscores (prevents SQL injection)
                    if not column_name.replace('_', '').isalnum():
                        raise ValueError(f"Invalid column name: {column_name}")

                    # Safe to use in DDL after validation
                    # Note: column_def is internally controlled, not user input
                    await conn.execute(text(f"""
                        ALTER TABLE attendance_records
                        ADD COLUMN {column_name} {column_def}
                    """))
                    print(f"  ✓ Added {column_name}")
                else:
                    print(f"  - Column {column_name} already exists")

            except Exception as e:
                print(f"  ! Error with {column_name}: {e}")

        # Create index if not exists
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_attendance_boss_reported
                ON attendance_records (is_boss_reported)
            """))
            print("  ✓ Index created/verified")
        except Exception as e:
            print(f"  ! Index error: {e}")

    await engine.dispose()
    print("\nMigration complete!")


if __name__ == "__main__":
    asyncio.run(migrate())
