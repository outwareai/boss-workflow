import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def run_migration():
    # Load environment variables
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL not found in environment")
        return
    
    # Read migration SQL
    with open("migrations/001_add_composite_indexes.sql", "r") as f:
        migration_sql = f.read()
    
    # Connect to database
    print(f"Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        # Split SQL into individual statements (CREATE INDEX CONCURRENTLY must run separately)
        statements = [s.strip() for s in migration_sql.split(';') if s.strip() and not s.strip().startswith('--')]
        
        print(f"\nFound {len(statements)} SQL statements to execute\n")
        
        for i, statement in enumerate(statements, 1):
            # Skip empty or comment-only statements
            if not statement or statement.startswith('--'):
                continue
                
            # Extract index name for logging
            if 'CREATE INDEX' in statement:
                index_name = statement.split('idx_')[1].split()[0] if 'idx_' in statement else f'statement_{i}'
                print(f"[{i}/{len(statements)}] Creating index: idx_{index_name}...")
            else:
                print(f"[{i}/{len(statements)}] Executing statement...")
            
            try:
                # Execute statement
                await conn.execute(statement)
                print(f"  ✅ Success")
            except Exception as e:
                if 'already exists' in str(e):
                    print(f"  ⚠️  Already exists (skipping)")
                else:
                    print(f"  ❌ Error: {e}")
                    raise
        
        print("\n" + "="*60)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY")
        print("="*60)
        
        # Verify indexes
        print("\nVerifying indexes...")
        indexes = await conn.fetch("""
            SELECT schemaname, tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            ORDER BY tablename, indexname;
        """)
        
        print(f"\nFound {len(indexes)} indexes:")
        for idx in indexes:
            print(f"  • {idx['indexname']} on {idx['tablename']}")
        
    finally:
        await conn.close()
        print("\nDatabase connection closed.")

if __name__ == "__main__":
    asyncio.run(run_migration())
