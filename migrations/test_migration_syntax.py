"""
Test migration SQL syntax without executing.

Q3 2026: Validates migration files for syntax errors.
"""
import sys
from pathlib import Path


def validate_sql_syntax(sql_content: str) -> tuple[bool, list[str]]:
    """
    Validate SQL syntax for common issues.
    
    Returns:
        (is_valid, errors)
    """
    errors = []
    lines = sql_content.split('\n')
    
    # Check for common syntax issues
    for i, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip comments and empty lines
        if not line or line.startswith('--'):
            continue
        
        # Check for missing semicolons at end of CREATE statements
        if line.upper().startswith('CREATE INDEX'):
            # Find the end of this statement
            statement = line
            j = i
            while j < len(lines) and ';' not in lines[j-1]:
                j += 1
                if j <= len(lines):
                    statement += ' ' + lines[j-1].strip()
            
            if not statement.strip().endswith(';'):
                errors.append(f"Line {i}: CREATE INDEX statement missing semicolon")
        
        # Check for proper CONCURRENTLY usage
        if 'CREATE INDEX' in line.upper() and 'CONCURRENTLY' not in line.upper():
            errors.append(f"Line {i}: Missing CONCURRENTLY flag (causes table locks)")
        
        # Check for IF NOT EXISTS
        if 'CREATE INDEX' in line.upper() and 'IF NOT EXISTS' not in line.upper():
            errors.append(f"Line {i}: Missing IF NOT EXISTS (fails on re-run)")
    
    return len(errors) == 0, errors


def count_statements(sql_content: str) -> dict:
    """Count different types of statements."""
    # Count by lines since statements can span multiple lines
    lines = sql_content.split('\n')
    
    counts = {
        'create_index': 0,
        'create_index_gin': 0,
        'create_index_partial': 0,
    }
    
    for line in lines:
        if 'CREATE INDEX' in line.upper():
            counts['create_index'] += 1
            
        if 'USING gin' in line:
            counts['create_index_gin'] += 1
        
        if 'CREATE INDEX' in line.upper() and 'WHERE' in line.upper():
            counts['create_index_partial'] += 1
    
    return counts


def main():
    # Find migration file
    script_dir = Path(__file__).parent
    migration_path = script_dir / "002_add_performance_indexes.sql"
    
    if not migration_path.exists():
        print(f"Migration file not found: {migration_path}")
        sys.exit(1)
    
    # Read migration
    print(f"Reading: {migration_path}\n")
    with open(migration_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Validate syntax
    print("Validating SQL syntax...")
    is_valid, errors = validate_sql_syntax(sql_content)
    
    if not is_valid:
        print(f"\nVALIDATION FAILED - {len(errors)} errors found:\n")
        for error in errors:
            print(f"  • {error}")
        print()
        sys.exit(1)
    
    print("Syntax validation passed\n")
    
    # Count statements
    counts = count_statements(sql_content)
    
    print("=" * 60)
    print("MIGRATION STATISTICS")
    print("=" * 60)
    print(f"CREATE INDEX statements: {counts['create_index']}")
    print(f"Full-text search (GIN) indexes: {counts['create_index_gin']}")
    print(f"Partial indexes (with WHERE): {counts['create_index_partial']}")
    print("=" * 60)
    print()
    
    # Extract index names
    print("INDEX BREAKDOWN BY TABLE:")
    print("-" * 60)
    
    by_table = {}
    for line in sql_content.split('\n'):
        if 'CREATE INDEX CONCURRENTLY IF NOT EXISTS' in line:
            parts = line.split()
            try:
                exists_idx = parts.index('EXISTS')
                index_name = parts[exists_idx + 1]
                
                # Extract table name (after ON keyword)
                on_idx = parts.index('ON')
                table_name = parts[on_idx + 1].split('(')[0]
                
                if table_name not in by_table:
                    by_table[table_name] = []
                by_table[table_name].append(index_name)
            except (ValueError, IndexError):
                continue
    
    for table, indexes in sorted(by_table.items()):
        print(f"\n{table}: {len(indexes)} indexes")
        for idx in sorted(indexes):
            print(f"  • {idx}")
    
    print("\n" + "=" * 60)
    print("MIGRATION FILE IS READY")
    print("=" * 60)
    print("\nTo apply this migration:")
    print("  python migrations/run_002_migration.py")


if __name__ == "__main__":
    main()
