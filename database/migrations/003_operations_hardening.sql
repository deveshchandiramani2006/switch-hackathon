
-- ── 003_operations_hardening.sql ──────────────────────────────────────────────
-- Agent heartbeats (liveness), audit log (config/role/key changes), SLA tracking column.

-- ── Agent Heartbeats ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_heartbeats (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) NOT NULL,
    agent_name  VARCHAR(100) NOT NULL,
    last_seen   TIMESTAMP    DEFAULT NOW(),
    UNIQUE (tenant_id, agent_name)
);

CREATE INDEX IF NOT EXISTS idx_agent_heartbeats_lookup
    ON agent_heartbeats (tenant_id, last_seen DESC);

-- ── Audit Log ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) NOT NULL,
    actor       VARCHAR(255) NOT NULL,  -- username or "system"
    action      VARCHAR(100) NOT NULL,  -- config_updated | role_changed | secret_rotated | tenant_deleted | tenant_purged
    target_type VARCHAR(100),           -- tenant | user | agent
    target_id   VARCHAR(255),           -- the entity affected
    before_val  JSONB,
    after_val   JSONB,
    ip_addr     VARCHAR(50),
    created_at  TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_ts
    ON audit_log (tenant_id, created_at DESC);

-- ── SLA tracking on bugs ──────────────────────────────────────────────────────
ALTER TABLE bugs ADD COLUMN IF NOT EXISTS sla_breach_notified BOOLEAN DEFAULT FALSE;
ALTER TABLE bugs ADD COLUMN IF NOT EXISTS resolved_by         VARCHAR(255);

-- ── Commitments: allow passive auto-resolve ───────────────────────────────────
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS auto_resolved BOOLEAN DEFAULT FALSE;
ALTER TABLE commitments ADD COLUMN IF NOT EXISTS resolved_text TEXT;
