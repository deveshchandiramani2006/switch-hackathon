
-- ── 002_saas_foundation.sql ───────────────────────────────────────────────────
-- SaaS foundation: workspace mapping, webhook secrets, tenant users,
-- tenant configs, conversation sessions, approval sessions,
-- usage events, and onboarding sessions.

-- ── Extend tenants ────────────────────────────────────────────────────────────
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS workspace_id  VARCHAR(255);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS room_mappings JSONB DEFAULT '{}';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(64);
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS llm_calls_today  INTEGER DEFAULT 0;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS llm_calls_reset_at DATE DEFAULT CURRENT_DATE;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{}';

-- Backfill webhook_secret for existing tenants (requires pgcrypto)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'
    ) THEN
        UPDATE tenants
        SET webhook_secret = encode(gen_random_bytes(32), 'hex')
        WHERE webhook_secret IS NULL;
    ELSE
        UPDATE tenants
        SET webhook_secret = md5(random()::text || clock_timestamp()::text)
        WHERE webhook_secret IS NULL;
    END IF;
END
$$;

-- ── Tenant Users ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenant_users (
    id           SERIAL PRIMARY KEY,
    tenant_id    VARCHAR(100) NOT NULL,
    username     VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    role         VARCHAR(50)  DEFAULT 'member',  -- admin | manager | member | viewer
    invited_by   VARCHAR(255),
    last_seen    TIMESTAMP    DEFAULT NOW(),
    joined_at    TIMESTAMP    DEFAULT NOW(),
    UNIQUE (tenant_id, username)
);

-- ── Tenant Configs ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenant_configs (
    id               SERIAL PRIMARY KEY,
    tenant_id        VARCHAR(100) NOT NULL UNIQUE,
    escalation_chain JSONB DEFAULT '{}',
    integrations     JSONB DEFAULT '{}',
    thresholds       JSONB DEFAULT '{}',
    agent_flags      JSONB DEFAULT '{}',
    llm_config       JSONB DEFAULT '{}',
    geo_seo_config   JSONB DEFAULT '{}',
    updated_at       TIMESTAMP DEFAULT NOW(),
    created_at       TIMESTAMP DEFAULT NOW()
);

-- Seed default tenant config (migrated from company.yaml)
INSERT INTO tenant_configs (tenant_id, escalation_chain, thresholds, agent_flags)
VALUES (
    'default',
    '{"sales": {"levels": [], "deal_size_tiers": {}}, "support": {"levels": [], "sla": {"p0_hours": 2, "p1_hours": 8, "p2_hours": 48}}, "infra": {"levels": [], "failure_threshold": 2}, "cs": {"csm": "@cs_team", "cs_lead": "@cs_lead"}, "finance": {"approver": "@finance_lead"}}',
    '{"stale_lead_days": 7, "health_score_red": 50, "health_score_yellow": 70, "escalation_check_minutes": 60}',
    '{"sales_agent": true, "support_agent": true, "geo_seo_agent": true, "blog_agent": true, "infra_agent": true, "cs_agent": true, "finance_agent": true}'
)
ON CONFLICT (tenant_id) DO NOTHING;

-- ── Conversation Sessions (guided input wizard / modal) ───────────────────────
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id         SERIAL PRIMARY KEY,
    tenant_id  VARCHAR(100) NOT NULL,
    room_id    VARCHAR(255) NOT NULL,
    sender     VARCHAR(255) NOT NULL,
    agent      VARCHAR(100) NOT NULL,
    command    VARCHAR(100) NOT NULL,
    collected  JSONB        DEFAULT '{}',
    step       INTEGER      DEFAULT 0,
    status     VARCHAR(50)  DEFAULT 'active',  -- active | completed | cancelled
    expires_at TIMESTAMP    NOT NULL,
    created_at TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_sessions_active
    ON conversation_sessions (tenant_id, room_id, sender, agent, status);

-- ── Approval Sessions ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approval_sessions (
    id               SERIAL PRIMARY KEY,
    tenant_id        VARCHAR(100) NOT NULL,
    room_id          VARCHAR(255) NOT NULL,
    agent            VARCHAR(100) NOT NULL,
    item_type        VARCHAR(100) NOT NULL,  -- blog_draft | invoice
    item_id          INTEGER      NOT NULL,
    requester        VARCHAR(255) NOT NULL,
    status           VARCHAR(50)  DEFAULT 'pending',  -- pending | approved | rejected | expired
    approved_by      VARCHAR(255),
    rejected_by      VARCHAR(255),
    rejection_reason TEXT,
    expires_at       TIMESTAMP    NOT NULL,
    resolved_at      TIMESTAMP,
    created_at       TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approval_sessions_pending
    ON approval_sessions (tenant_id, room_id, item_type, item_id, status);

-- ── Usage Events ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usage_events (
    id         SERIAL  PRIMARY KEY,
    tenant_id  VARCHAR(100) NOT NULL,
    agent      VARCHAR(100) NOT NULL,
    command    VARCHAR(100) NOT NULL,
    username   VARCHAR(255),
    success    BOOLEAN      DEFAULT TRUE,
    error_msg  TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usage_events_tenant_ts
    ON usage_events (tenant_id, created_at DESC);

-- ── Onboarding Sessions ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS onboarding_sessions (
    id               SERIAL PRIMARY KEY,
    tenant_id        VARCHAR(100) NOT NULL UNIQUE,
    current_step     INTEGER      DEFAULT 0,
    steps_completed  JSONB        DEFAULT '[]',
    completed_at     TIMESTAMP,
    created_at       TIMESTAMP    DEFAULT NOW()
);
