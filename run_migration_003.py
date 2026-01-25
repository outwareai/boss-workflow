"""
Quick migration runner for 003_add_undo_history.sql
Uses existing database connection from the app.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.database.connection import get_database
from sqlalchemy import text


async def run_migration():
    """Run the migration SQL file using existing database connection."""
    # Read migration file
    migration_file = Path(__file__).parent / "migrations" / "003_add_undo_history.sql"

    if not migration_file.exists():
        print(f"ERROR: Migration file not found: {migration_file}")
        return False

    with open(migration_file, 'r') as f:
        sql = f.read()

    print(f"Running migration: 003_add_undo_history.sql")

    try:
        # Get database connection
        db = get_database()

        # Initialize database
        await db.initialize()

        async with db.session() as session:
            # Run migration in transaction
            await session.execute(text(sql))
            await session.commit()

            print("SUCCESS: Migration completed successfully")

            # Verify table was created
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'undo_history'
                )
            """))

            exists = result.scalar()

            if exists:
                print("SUCCESS: Verified undo_history table exists")

                # Check indexes
                indexes_result = await session.execute(text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = 'undo_history'
                """))

                indexes = indexes_result.fetchall()

                print(f"SUCCESS: Indexes created: {len(indexes)}")
                for idx in indexes:
                    print(f"   - {idx[0]}")
            else:
                print("ERROR: Table verification failed")
                return False

        return True

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)
