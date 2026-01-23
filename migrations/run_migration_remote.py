"""
Remote migration runner - to be executed on Railway
"""
import asyncio
import asyncpg
import os

async def run():
    database_url = os.getenv("DATABASE_URL")

    # Remove SQLAlchemy-specific parts from URL
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    # Find migration SQL file (works in both local and Railway environments)
    import pathlib
    script_dir = pathlib.Path(__file__).parent
    migration_path = script_dir / "001_add_composite_indexes.sql"

    if not migration_path.exists():
        # Try /app path for Railway
        migration_path = pathlib.Path("/app/migrations/001_add_composite_indexes.sql")

    # Read migration SQL
    with open(migration_path, "r", encoding="utf-8") as f:
        migration_sql = f.read()
    
    # Split into statements
    statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]
    
    # Connect to database
    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        print(f"\nExecuting {len(statements)} statements...\n")
        
        for i, statement in enumerate(statements, 1):
            if not statement or statement.startswith('--'):
                continue
            
            try:
                await conn.execute(statement)
                
                if 'idx_' in statement:
                    index_name = statement.split('idx_')[1].split()[0]
                    print(f"[{i}] ✅ Created index: idx_{index_name}")
                else:
                    print(f"[{i}] ✅ Executed statement")
            
            except Exception as e:
                if 'already exists' in str(e):
                    if 'idx_' in statement:
                        index_name = statement.split('idx_')[1].split()[0]
                        print(f"[{i}] ⚠️  Already exists: idx_{index_name}")
                    else:
                        print(f"[{i}] ⚠️  Already exists (skipped)")
                else:
                    print(f"[{i}] ❌ Error: {e}")
                    raise
        
        # Verify
        print("\n" + "="*60)
        indexes = await conn.fetch("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname IN ('idx_tasks_status_assignee', 'idx_tasks_status_deadline', 
                              'idx_time_entries_user_date', 'idx_attendance_date_user',
                              'idx_audit_timestamp_entity')
            ORDER BY indexname
        """)
        
        print(f"✅ MIGRATION COMPLETE - Found {len(indexes)} new indexes:")
        for idx in indexes:
            print(f"  • {idx['indexname']} on {idx['tablename']}")
        print("="*60)
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
