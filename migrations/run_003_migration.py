"""
Migration script for 003_add_undo_history.sql

Adds the undo/redo history table with full enterprise support.
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings


async def run_migration():
    """Run the migration SQL file."""
    # Read migration file
    migration_file = Path(__file__).parent / "003_add_undo_history.sql"

    if not migration_file.exists():
        print(f"ERROR: Migration file not found: {migration_file}")
        return False

    with open(migration_file, 'r') as f:
        sql = f.read()

    print(f"Running migration: 003_add_undo_history.sql")
    print(f"   Database: {settings.database_url}")

    try:
        # Connect to database
        conn = await asyncpg.connect(settings.database_url)

        # Run migration in transaction
        async with conn.transaction():
            await conn.execute(sql)

        print("SUCCESS: Migration completed successfully")

        # Verify table was created
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'undo_history'
            )
        """)

        if result:
            print("SUCCESS: Verified undo_history table exists")

            # Check indexes
            indexes = await conn.fetch("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'undo_history'
            """)

            print(f"SUCCESS: Indexes created: {len(indexes)}")
            for idx in indexes:
                print(f"   - {idx['indexname']}")
        else:
            print("ERROR: Table verification failed")
            return False

        await conn.close()
        return True

    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)
