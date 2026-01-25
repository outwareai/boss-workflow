-- Migration 003: Add Undo/Rollback History System
-- Created: 2026-01-25
-- Description: Full enterprise undo/redo system with multi-level support

-- ==================== CLEANUP ====================

-- Drop existing table if it exists (in case of previous failed migrations)
DROP TABLE IF EXISTS undo_history CASCADE;

-- ==================== UNDO HISTORY TABLE ====================

CREATE TABLE undo_history (
    id SERIAL PRIMARY KEY,

    -- User identification
    user_id VARCHAR(100) NOT NULL,

    -- Action details
    action_type VARCHAR(50) NOT NULL,  -- delete_task, change_status, reassign, etc.
    action_data JSONB NOT NULL,        -- Original action parameters

    -- Undo details
    undo_function VARCHAR(100) NOT NULL,  -- Function to call for undo
    undo_data JSONB NOT NULL,            -- Data needed for undo

    -- Metadata
    description TEXT,                    -- Human-readable description
    metadata JSONB,                      -- Additional context

    -- Status tracking
    is_undone BOOLEAN DEFAULT FALSE,

    -- Timestamps
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    undo_timestamp TIMESTAMP,

    -- Indexing
    CONSTRAINT idx_undo_history_user_timestamp_idx UNIQUE (user_id, timestamp)
);

-- ==================== INDEXES ====================

-- Primary lookup index (user + timestamp for history retrieval)
CREATE INDEX IF NOT EXISTS idx_undo_history_user ON undo_history(user_id);
CREATE INDEX IF NOT EXISTS idx_undo_history_timestamp ON undo_history(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_undo_history_user_time ON undo_history(user_id, timestamp DESC);

-- Status tracking
CREATE INDEX IF NOT EXISTS idx_undo_history_undone ON undo_history(is_undone) WHERE is_undone = FALSE;

-- Action type filtering
CREATE INDEX IF NOT EXISTS idx_undo_history_action_type ON undo_history(action_type);

-- Note: GIN indexes on JSONB columns can be added later if needed for query performance
-- They are omitted here to ensure migration compatibility across PostgreSQL versions

-- ==================== COMMENTS ====================

COMMENT ON TABLE undo_history IS 'Enterprise undo/redo history for reversible actions';
COMMENT ON COLUMN undo_history.user_id IS 'User who performed the action (Telegram/Discord ID)';
COMMENT ON COLUMN undo_history.action_type IS 'Type of action: delete_task, change_status, reassign, change_priority, change_deadline';
COMMENT ON COLUMN undo_history.action_data IS 'Original action parameters (for redo)';
COMMENT ON COLUMN undo_history.undo_function IS 'Function name to call for undo operation';
COMMENT ON COLUMN undo_history.undo_data IS 'Data needed to undo the action (old values)';
COMMENT ON COLUMN undo_history.description IS 'Human-readable description shown in history';
COMMENT ON COLUMN undo_history.is_undone IS 'Whether this action has been undone';
COMMENT ON COLUMN undo_history.timestamp IS 'When the action was performed';
COMMENT ON COLUMN undo_history.undo_timestamp IS 'When the action was undone (NULL if not undone)';

-- ==================== VALIDATION ====================

-- Ensure undo_timestamp is set only when is_undone is true
ALTER TABLE undo_history ADD CONSTRAINT chk_undo_timestamp
    CHECK ((is_undone = TRUE AND undo_timestamp IS NOT NULL) OR (is_undone = FALSE AND undo_timestamp IS NULL));
