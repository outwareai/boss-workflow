-- Migration 003: Planning and Project Memory System
-- Created: 2026-01-25
-- Purpose: Add comprehensive planning system with AI-powered project memory

-- ==================== ENUMS ====================

-- Planning session states
CREATE TYPE planning_state AS ENUM (
    'initiated',
    'gathering_info',
    'ai_analyzing',
    'reviewing_breakdown',
    'refining',
    'finalizing',
    'completed',
    'cancelled'
);

-- Project complexity levels
CREATE TYPE project_complexity AS ENUM (
    'simple',
    'moderate',
    'complex',
    'very_complex'
);

-- ==================== TABLE 1: PLANNING SESSIONS ====================

CREATE TABLE planning_sessions (
    -- Primary identifiers
    session_id VARCHAR(50) PRIMARY KEY,
    conversation_id VARCHAR(50) REFERENCES conversations(conversation_id),
    user_id VARCHAR(50) NOT NULL,

    -- Session metadata
    state planning_state NOT NULL DEFAULT 'initiated',
    project_name VARCHAR(200),
    project_description TEXT,
    detected_project_id VARCHAR(50),
    detection_confidence FLOAT CHECK (detection_confidence >= 0 AND detection_confidence <= 1),

    -- AI analysis results
    complexity project_complexity,
    estimated_duration_hours FLOAT,
    suggested_team_members JSONB,
    applied_template_id VARCHAR(50),

    -- Planning data
    raw_input TEXT NOT NULL,
    clarifying_questions JSONB,
    ai_breakdown JSONB,
    user_edits JSONB,

    -- Finalization
    finalized_at TIMESTAMP,
    created_project_id VARCHAR(50),
    created_task_ids JSONB,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for planning_sessions
CREATE INDEX idx_planning_user_state ON planning_sessions(user_id, state);
CREATE INDEX idx_planning_created ON planning_sessions(created_at);
CREATE INDEX idx_planning_project ON planning_sessions(detected_project_id);
CREATE INDEX idx_planning_activity ON planning_sessions(last_activity_at);

-- ==================== TABLE 2: TASK DRAFTS ====================

CREATE TABLE task_drafts (
    -- Primary identifiers
    draft_id VARCHAR(50) PRIMARY KEY,
    session_id VARCHAR(50) NOT NULL REFERENCES planning_sessions(session_id) ON DELETE CASCADE,

    -- Task details
    title VARCHAR(500) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    priority VARCHAR(20),

    -- Assignment
    assigned_to VARCHAR(100),
    estimated_hours FLOAT,
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),

    -- Dependencies
    depends_on JSONB,
    blocking JSONB,

    -- AI metadata
    ai_generated BOOLEAN DEFAULT TRUE,
    ai_reasoning TEXT,
    user_modified BOOLEAN DEFAULT FALSE,

    -- Order
    sequence_order INTEGER NOT NULL,

    -- Finalization
    created_task_id VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for task_drafts
CREATE INDEX idx_draft_session ON task_drafts(session_id);
CREATE INDEX idx_draft_order ON task_drafts(session_id, sequence_order);
CREATE INDEX idx_draft_created_task ON task_drafts(created_task_id);

-- ==================== TABLE 3: PROJECT MEMORY ====================

CREATE TABLE project_memory (
    -- Primary identifier
    memory_id VARCHAR(50) PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL,

    -- Pattern extraction (AI-powered)
    common_challenges JSONB,
    success_patterns JSONB,
    team_insights JSONB,
    estimated_vs_actual JSONB,
    bottleneck_patterns JSONB,
    recommended_templates JSONB,

    -- Learning metadata
    pattern_confidence FLOAT CHECK (pattern_confidence >= 0 AND pattern_confidence <= 1),
    last_analyzed_at TIMESTAMP,
    analysis_version VARCHAR(20),

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for project_memory
CREATE INDEX idx_memory_project ON project_memory(project_id);
CREATE INDEX idx_memory_analyzed ON project_memory(last_analyzed_at);
CREATE INDEX idx_memory_confidence ON project_memory(pattern_confidence);

-- ==================== TABLE 4: PROJECT DECISIONS ====================

CREATE TABLE project_decisions (
    -- Primary identifier
    decision_id VARCHAR(50) PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL,
    planning_session_id VARCHAR(50) REFERENCES planning_sessions(session_id),

    -- Decision details
    decision_type VARCHAR(50) NOT NULL,
    decision_text TEXT NOT NULL,
    reasoning TEXT,
    alternatives_considered JSONB,

    -- Context
    made_by VARCHAR(100) NOT NULL,
    context JSONB,

    -- Impact tracking
    impact_assessment TEXT,
    outcome TEXT,

    -- Timestamps
    decided_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMP
);

-- Indexes for project_decisions
CREATE INDEX idx_decision_project ON project_decisions(project_id);
CREATE INDEX idx_decision_type ON project_decisions(decision_type);
CREATE INDEX idx_decision_date ON project_decisions(decided_at);
CREATE INDEX idx_decision_session ON project_decisions(planning_session_id);

-- ==================== TABLE 5: KEY DISCUSSIONS ====================

CREATE TABLE key_discussions (
    -- Primary identifier
    discussion_id VARCHAR(50) PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL,
    planning_session_id VARCHAR(50) REFERENCES planning_sessions(session_id),

    -- Discussion content
    topic VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    key_points JSONB,

    -- Messages
    message_ids JSONB,
    participant_ids JSONB,

    -- AI extraction
    extracted_decisions JSONB,
    extracted_action_items JSONB,

    -- Importance
    importance_score FLOAT CHECK (importance_score >= 0 AND importance_score <= 1),
    tags JSONB,

    -- Timestamps
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),
    summarized_at TIMESTAMP
);

-- Indexes for key_discussions
CREATE INDEX idx_discussion_project ON key_discussions(project_id);
CREATE INDEX idx_discussion_importance ON key_discussions(importance_score);
CREATE INDEX idx_discussion_date ON key_discussions(occurred_at);
CREATE INDEX idx_discussion_session ON key_discussions(planning_session_id);

-- ==================== TABLE 6: PLANNING TEMPLATES ====================

CREATE TABLE planning_templates (
    -- Primary identifier
    template_id VARCHAR(50) PRIMARY KEY,

    -- Template metadata
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category VARCHAR(100),

    -- Template structure
    task_template JSONB NOT NULL,
    clarifying_questions JSONB,
    team_suggestions JSONB,

    -- Learning metadata
    source VARCHAR(50) NOT NULL,
    source_project_ids JSONB,
    usage_count INTEGER DEFAULT 0,
    success_rate FLOAT CHECK (success_rate >= 0 AND success_rate <= 1),

    -- Versioning
    version VARCHAR(20) NOT NULL DEFAULT '1.0',
    active BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for planning_templates
CREATE INDEX idx_template_category ON planning_templates(category);
CREATE INDEX idx_template_active ON planning_templates(active);
CREATE INDEX idx_template_usage ON planning_templates(usage_count DESC);
CREATE INDEX idx_template_success ON planning_templates(success_rate DESC);

-- ==================== TRIGGERS ====================

-- Update updated_at timestamp on planning_sessions
CREATE OR REPLACE FUNCTION update_planning_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER planning_session_updated
    BEFORE UPDATE ON planning_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_planning_session_timestamp();

-- Update updated_at timestamp on task_drafts
CREATE TRIGGER task_draft_updated
    BEFORE UPDATE ON task_drafts
    FOR EACH ROW
    EXECUTE FUNCTION update_planning_session_timestamp();

-- Update updated_at timestamp on project_memory
CREATE TRIGGER project_memory_updated
    BEFORE UPDATE ON project_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_planning_session_timestamp();

-- Update updated_at timestamp on planning_templates
CREATE TRIGGER planning_template_updated
    BEFORE UPDATE ON planning_templates
    FOR EACH ROW
    EXECUTE FUNCTION update_planning_session_timestamp();

-- ==================== COMMENTS ====================

COMMENT ON TABLE planning_sessions IS 'Tracks multi-turn planning conversations with AI-powered task breakdown';
COMMENT ON TABLE task_drafts IS 'Task drafts within planning sessions, convertible to real tasks';
COMMENT ON TABLE project_memory IS 'AI-extracted patterns and learnings from completed projects';
COMMENT ON TABLE project_decisions IS 'Key decisions made during project planning and execution';
COMMENT ON TABLE key_discussions IS 'Important discussions extracted and summarized by AI';
COMMENT ON TABLE planning_templates IS 'Reusable planning templates for common project types';

COMMENT ON COLUMN planning_sessions.detection_confidence IS 'AI confidence score (0-1) for project recognition';
COMMENT ON COLUMN planning_sessions.ai_breakdown IS 'Full AI-generated task breakdown with dependencies';
COMMENT ON COLUMN task_drafts.ai_reasoning IS 'Explanation of why AI suggested this task breakdown';
COMMENT ON COLUMN project_memory.pattern_confidence IS 'Confidence in extracted patterns (0-1)';
COMMENT ON COLUMN key_discussions.importance_score IS 'AI-determined importance (0-1)';

-- ==================== SEED DATA: INITIAL TEMPLATES ====================

-- Template 1: Mobile App Development
INSERT INTO planning_templates (
    template_id, name, description, category, task_template,
    clarifying_questions, team_suggestions, source, version
) VALUES (
    'TPL-20260125-001',
    'Mobile App Development',
    'Comprehensive template for building mobile applications (iOS/Android)',
    'mobile_dev',
    '[
        {"title": "Setup project structure and dependencies", "category": "infrastructure", "estimated_hours": 4},
        {"title": "Design UI/UX mockups and user flows", "category": "design", "estimated_hours": 16},
        {"title": "Implement authentication system", "category": "backend", "estimated_hours": 12},
        {"title": "Build main app screens and navigation", "category": "frontend", "estimated_hours": 24},
        {"title": "Integrate backend API", "category": "backend", "estimated_hours": 16},
        {"title": "Add push notifications", "category": "infrastructure", "estimated_hours": 8},
        {"title": "Implement offline mode and data sync", "category": "backend", "estimated_hours": 12},
        {"title": "Write unit and integration tests", "category": "testing", "estimated_hours": 16},
        {"title": "App store submission and deployment", "category": "deployment", "estimated_hours": 8}
    ]'::jsonb,
    '["Which platforms? (iOS only, Android only, or both?)", "Authentication method? (Email/password, social login, biometric?)", "Offline functionality needed?", "Push notifications required?", "Third-party integrations? (payment, analytics, etc.)"]'::jsonb,
    '{"Mobile Developer": 1, "UI/UX Designer": 1, "Backend Developer": 1, "QA Tester": 1}'::jsonb,
    'manual',
    '1.0'
);

-- Template 2: Web Application
INSERT INTO planning_templates (
    template_id, name, description, category, task_template,
    clarifying_questions, team_suggestions, source, version
) VALUES (
    'TPL-20260125-002',
    'Web Application Development',
    'Full-stack web application with modern frontend and backend',
    'web_dev',
    '[
        {"title": "Setup development environment and repository", "category": "infrastructure", "estimated_hours": 2},
        {"title": "Design database schema and relationships", "category": "backend", "estimated_hours": 8},
        {"title": "Create API endpoints and business logic", "category": "backend", "estimated_hours": 24},
        {"title": "Implement user authentication and authorization", "category": "backend", "estimated_hours": 12},
        {"title": "Build responsive UI components", "category": "frontend", "estimated_hours": 20},
        {"title": "Integrate frontend with API", "category": "frontend", "estimated_hours": 16},
        {"title": "Add form validation and error handling", "category": "frontend", "estimated_hours": 8},
        {"title": "Write automated tests (unit, integration, E2E)", "category": "testing", "estimated_hours": 16},
        {"title": "Setup CI/CD pipeline", "category": "deployment", "estimated_hours": 8},
        {"title": "Deploy to production environment", "category": "deployment", "estimated_hours": 4}
    ]'::jsonb,
    '["Frontend framework preference? (React, Vue, Angular?)", "Backend technology? (Node.js, Python, Ruby?)", "Database type? (PostgreSQL, MongoDB, MySQL?)", "User roles and permissions needed?", "Real-time features required?"]'::jsonb,
    '{"Frontend Developer": 1, "Backend Developer": 1, "DevOps Engineer": 1, "QA Tester": 1}'::jsonb,
    'manual',
    '1.0'
);

-- Template 3: REST API Development
INSERT INTO planning_templates (
    template_id, name, description, category, task_template,
    clarifying_questions, team_suggestions, source, version
) VALUES (
    'TPL-20260125-003',
    'REST API Development',
    'RESTful API with authentication, documentation, and testing',
    'api_dev',
    '[
        {"title": "Design API structure and endpoints", "category": "design", "estimated_hours": 6},
        {"title": "Setup project with framework and dependencies", "category": "infrastructure", "estimated_hours": 3},
        {"title": "Implement database models and migrations", "category": "backend", "estimated_hours": 8},
        {"title": "Create CRUD endpoints for core resources", "category": "backend", "estimated_hours": 16},
        {"title": "Add authentication and authorization middleware", "category": "backend", "estimated_hours": 10},
        {"title": "Implement rate limiting and security headers", "category": "backend", "estimated_hours": 6},
        {"title": "Write comprehensive API documentation", "category": "docs", "estimated_hours": 8},
        {"title": "Add input validation and error handling", "category": "backend", "estimated_hours": 8},
        {"title": "Write unit and integration tests", "category": "testing", "estimated_hours": 12},
        {"title": "Setup monitoring and logging", "category": "infrastructure", "estimated_hours": 6},
        {"title": "Deploy API with documentation", "category": "deployment", "estimated_hours": 4}
    ]'::jsonb,
    '["API versioning strategy?", "Authentication method? (JWT, OAuth, API keys?)", "Expected request volume and performance requirements?", "Third-party integrations needed?", "Deployment platform?"]'::jsonb,
    '{"Backend Developer": 2, "DevOps Engineer": 1}'::jsonb,
    'manual',
    '1.0'
);

-- Template 4: Infrastructure Setup
INSERT INTO planning_templates (
    template_id, name, description, category, task_template,
    clarifying_questions, team_suggestions, source, version
) VALUES (
    'TPL-20260125-004',
    'Infrastructure & DevOps',
    'Cloud infrastructure setup with monitoring and security',
    'infrastructure',
    '[
        {"title": "Design infrastructure architecture", "category": "design", "estimated_hours": 8},
        {"title": "Setup cloud provider accounts and billing", "category": "infrastructure", "estimated_hours": 2},
        {"title": "Configure VPC, networking, and security groups", "category": "infrastructure", "estimated_hours": 8},
        {"title": "Setup database instances with backups", "category": "infrastructure", "estimated_hours": 6},
        {"title": "Configure load balancers and auto-scaling", "category": "infrastructure", "estimated_hours": 8},
        {"title": "Implement CI/CD pipelines", "category": "infrastructure", "estimated_hours": 12},
        {"title": "Setup monitoring and alerting (Prometheus, Grafana)", "category": "infrastructure", "estimated_hours": 10},
        {"title": "Configure centralized logging", "category": "infrastructure", "estimated_hours": 6},
        {"title": "Implement backup and disaster recovery", "category": "infrastructure", "estimated_hours": 8},
        {"title": "Security hardening and compliance", "category": "infrastructure", "estimated_hours": 12},
        {"title": "Documentation and runbooks", "category": "docs", "estimated_hours": 8}
    ]'::jsonb,
    '["Cloud provider? (AWS, GCP, Azure?)", "Expected traffic and scaling needs?", "Compliance requirements? (GDPR, HIPAA, SOC2?)", "Budget constraints?", "Disaster recovery RTO/RPO targets?"]'::jsonb,
    '{"DevOps Engineer": 2, "Security Engineer": 1, "Backend Developer": 1}'::jsonb,
    'manual',
    '1.0'
);

-- ==================== VERIFICATION ====================

-- Verify tables created
DO $$
DECLARE
    table_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_name IN (
        'planning_sessions',
        'task_drafts',
        'project_memory',
        'project_decisions',
        'key_discussions',
        'planning_templates'
    );

    IF table_count = 6 THEN
        RAISE NOTICE '✓ All 6 planning tables created successfully';
    ELSE
        RAISE EXCEPTION 'Only % tables created, expected 6', table_count;
    END IF;
END $$;

-- Verify indexes created
DO $$
DECLARE
    index_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'public'
    AND tablename IN (
        'planning_sessions',
        'task_drafts',
        'project_memory',
        'project_decisions',
        'key_discussions',
        'planning_templates'
    );

    RAISE NOTICE '✓ Created % indexes for planning tables', index_count;
END $$;

-- Verify seed templates
SELECT
    COUNT(*) as template_count,
    STRING_AGG(name, ', ') as templates
FROM planning_templates;
