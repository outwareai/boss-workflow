"""
Verify database indexes after migration.

Q3 2026: Validates that all expected indexes were created successfully.
"""
import asyncio
import asyncpg
import os
import sys


EXPECTED_INDEXES = {
    'tasks': [
        'idx_tasks_status',
        'idx_tasks_assignee',
        'idx_tasks_priority',
        'idx_tasks_deadline',
        'idx_tasks_project_id',
        'idx_tasks_created_at',
        'idx_tasks_assignee_priority',
        'idx_tasks_project_status',
        'idx_tasks_parent_task',
        'idx_tasks_title_search',
        'idx_tasks_description_search',
        'idx_tasks_content_search',
    ],
    'subtasks': [
        'idx_subtasks_parent_id',
        'idx_subtasks_status',
        'idx_subtasks_parent_status',
    ],
    'task_dependencies': [
        'idx_dependencies_task_id',
        'idx_dependencies_depends_on',
        'idx_dependencies_type',
        'idx_dependencies_task_type',
    ],
    'audit_logs': [
        'idx_audit_entity_type',
        'idx_audit_entity_id',
        'idx_audit_user_id',
        'idx_audit_action',
        'idx_audit_timestamp',
        'idx_audit_task_id',
        'idx_audit_entity_action',
    ],
    'conversations': [
        'idx_conversations_user_id',
        'idx_conversations_stage',
        'idx_conversations_active',
        'idx_conversations_created',
    ],
    'messages': [
        'idx_messages_conversation_id',
        'idx_messages_timestamp',
        'idx_messages_conv_timestamp',
    ],
    'ai_memory': [
        'idx_ai_memory_user_id',
    ],
    'projects': [
        'idx_projects_status',
        'idx_projects_owner',
        'idx_projects_name',
    ],
    'recurring_tasks': [
        'idx_recurring_next_run',
        'idx_recurring_active',
    ],
    'time_entries': [
        'idx_time_task_id',
        'idx_time_user_id',
        'idx_time_running',
        'idx_time_started',
    ],
    'active_timers': [
        'idx_active_timer_user',
    ],
    'attendance_records': [
        'idx_attendance_user_id',
        'idx_attendance_type',
        'idx_attendance_time',
        'idx_attendance_channel',
        'idx_attendance_synced',
        'idx_attendance_boss_reported',
        'idx_attendance_date_user_type',
    ],
    'webhook_events': [
        'idx_webhook_source',
        'idx_webhook_processed',
        'idx_webhook_received',
    ],
    'oauth_tokens': [
        'idx_oauth_email',
        'idx_oauth_service',
    ],
    'staff_task_contexts': [
        'idx_staff_ctx_task',
        'idx_staff_ctx_staff',
        'idx_staff_ctx_channel',
        'idx_staff_ctx_thread',
        'idx_staff_ctx_status',
        'idx_staff_ctx_activity',
    ],
    'staff_context_messages': [
        'idx_staff_msg_ctx',
        'idx_staff_msg_time',
    ],
    'staff_escalations': [
        'idx_staff_esc_ctx',
        'idx_staff_esc_responded',
        'idx_staff_esc_telegram',
    ],
    'discord_thread_task_links': [
        'idx_thread_link_thread',
        'idx_thread_link_task',
        'idx_thread_link_channel',
    ],
    'team_members': [
        'idx_team_name',
        'idx_team_telegram',
        'idx_team_discord',
        'idx_team_active',
    ],
}


async def verify_indexes():
    """Verify all expected indexes exist."""
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    # Remove SQLAlchemy-specific parts
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)
    
    try:
        # Get all existing indexes
        existing = await conn.fetch("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE 'idx_%'
            ORDER BY tablename, indexname
        """)
        
        # Convert to dict
        existing_by_table = {}
        for row in existing:
            table = row['tablename']
            if table not in existing_by_table:
                existing_by_table[table] = []
            existing_by_table[table].append(row['indexname'])
        
        # Verify each table
        print("\n" + "=" * 80)
        print("INDEX VERIFICATION REPORT")
        print("=" * 80)
        print()
        
        total_expected = 0
        total_found = 0
        total_missing = 0
        missing_indexes = []
        
        for table, expected_indexes in sorted(EXPECTED_INDEXES.items()):
            existing_indexes = existing_by_table.get(table, [])
            
            found = [idx for idx in expected_indexes if idx in existing_indexes]
            missing = [idx for idx in expected_indexes if idx not in existing_indexes]
            
            total_expected += len(expected_indexes)
            total_found += len(found)
            total_missing += len(missing)
            
            status = "OK" if not missing else "INCOMPLETE"
            symbol = "✓" if not missing else "✗"
            
            print(f"{symbol} {table}: {len(found)}/{len(expected_indexes)} indexes")
            
            if missing:
                for idx in missing:
                    print(f"    MISSING: {idx}")
                    missing_indexes.append((table, idx))
        
        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Tables checked: {len(EXPECTED_INDEXES)}")
        print(f"Expected indexes: {total_expected}")
        print(f"Found indexes: {total_found}")
        print(f"Missing indexes: {total_missing}")
        print()
        
        if total_missing == 0:
            print("STATUS: ALL INDEXES VERIFIED")
            print()
            
            # Check for full-text search indexes
            fts = await conn.fetch("""
                SELECT tablename, indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND indexdef LIKE '%to_tsvector%'
                ORDER BY indexname
            """)
            
            if fts:
                print("Full-Text Search Indexes:")
                for row in fts:
                    print(f"  ✓ {row['indexname']} on {row['tablename']}")
            
            print()
            print("=" * 80)
            print("DEPLOYMENT SUCCESS")
            print("=" * 80)
            return True
        else:
            print("STATUS: INCOMPLETE - Missing indexes detected")
            print()
            print("Missing Indexes:")
            for table, idx in missing_indexes:
                print(f"  • {table}.{idx}")
            print()
            print("=" * 80)
            print("DEPLOYMENT INCOMPLETE")
            print("=" * 80)
            return False
    
    finally:
        await conn.close()


if __name__ == "__main__":
    try:
        success = asyncio.run(verify_indexes())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
