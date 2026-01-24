"""
Remote migration runner for 002_add_performance_indexes.sql

Q3 2026: Comprehensive performance indexes migration.
Run this on Railway to apply all performance indexes.

Usage:
  python migrations/run_002_migration.py
"""
import asyncio
import asyncpg
import os
import sys
from pathlib import Path


async def run():
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    # Remove SQLAlchemy-specific parts from URL
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    # Find migration SQL file (works in both local and Railway environments)
    script_dir = Path(__file__).parent
    migration_path = script_dir / "002_add_performance_indexes.sql"

    if not migration_path.exists():
        # Try /app path for Railway
        migration_path = Path("/app/migrations/002_add_performance_indexes.sql")
    
    if not migration_path.exists():
        print(f"❌ ERROR: Migration file not found at {migration_path}")
        sys.exit(1)

    # Read migration SQL
    print(f"📖 Reading migration from: {migration_path}")
    with open(migration_path, "r", encoding="utf-8") as f:
        migration_sql = f.read()
    
    # Split into statements (filter out comments and empty lines)
    statements = [
        s.strip() 
        for s in migration_sql.split(';') 
        if s.strip() and not s.strip().startswith('--')
    ]
    
    print(f"📊 Found {len(statements)} SQL statements to execute\n")
    
    # Connect to database
    print("🔌 Connecting to database...")
    try:
        conn = await asyncpg.connect(database_url)
        print("✅ Connected successfully\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)
    
    try:
        print("=" * 80)
        print("EXECUTING MIGRATION: 002_add_performance_indexes.sql")
        print("=" * 80)
        print()
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for i, statement in enumerate(statements, 1):
            if not statement or statement.startswith('--'):
                continue
            
            try:
                await conn.execute(statement)
                
                # Extract index name for pretty output
                if 'CREATE INDEX' in statement:
                    parts = statement.split()
                    idx_pos = parts.index('idx_tasks_status') if 'idx_tasks_status' in statement else -1
                    
                    # Find index name (after IF NOT EXISTS)
                    index_name = "unknown"
                    for j, part in enumerate(parts):
                        if part == 'EXISTS' and j + 1 < len(parts):
                            index_name = parts[j + 1]
                            break
                    
                    print(f"[{i:3d}] ✅ Created index: {index_name}")
                    success_count += 1
                else:
                    print(f"[{i:3d}] ✅ Executed statement")
                    success_count += 1
            
            except Exception as e:
                error_msg = str(e)
                if 'already exists' in error_msg:
                    # Extract index name
                    index_name = "unknown"
                    if 'relation "' in error_msg:
                        index_name = error_msg.split('relation "')[1].split('"')[0]
                    
                    print(f"[{i:3d}] ⚠️  Already exists: {index_name}")
                    skip_count += 1
                else:
                    print(f"[{i:3d}] ❌ Error: {e}")
                    error_count += 1
                    # Don't raise - continue with other indexes
        
        print()
        print("=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"✅ Success: {success_count}")
        print(f"⚠️  Skipped: {skip_count}")
        print(f"❌ Errors:  {error_count}")
        print()
        
        # Verify indexes
        print("🔍 Verifying indexes...")
        print()
        
        # Count all indexes starting with idx_
        total_indexes = await conn.fetchval("""
            SELECT COUNT(*)
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
        """)
        
        print(f"📊 Total performance indexes in database: {total_indexes}")
        print()
        
        # Show newly created indexes (from this migration)
        new_indexes = await conn.fetch("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            AND indexname NOT IN (
                'idx_tasks_status_assignee',
                'idx_tasks_status_deadline',
                'idx_time_entries_user_date',
                'idx_attendance_date_user',
                'idx_audit_timestamp_entity'
            )
            ORDER BY tablename, indexname
        """)
        
        if new_indexes:
            print(f"✅ VERIFIED: {len(new_indexes)} new indexes from this migration:")
            print()
            
            # Group by table
            by_table = {}
            for idx in new_indexes:
                table = idx['tablename']
                if table not in by_table:
                    by_table[table] = []
                by_table[table].append(idx['indexname'])
            
            for table, indexes in sorted(by_table.items()):
                print(f"  📋 {table}:")
                for idx_name in sorted(indexes):
                    print(f"      • {idx_name}")
                print()
        
        # Show full-text search indexes
        fts_indexes = await conn.fetch("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexdef LIKE '%to_tsvector%'
            ORDER BY indexname
        """)
        
        if fts_indexes:
            print("🔍 Full-Text Search Indexes:")
            for idx in fts_indexes:
                print(f"  • {idx['indexname']} on {idx['tablename']}")
            print()
        
        print("=" * 80)
        if error_count == 0:
            print("✅ MIGRATION COMPLETE - All indexes created successfully")
        else:
            print(f"⚠️  MIGRATION COMPLETE - {error_count} errors occurred")
        print("=" * 80)
    
    finally:
        await conn.close()
        print("\n🔌 Database connection closed")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
