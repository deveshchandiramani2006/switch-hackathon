import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
-- ── Tenants ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    tenant_id   VARCHAR(100) NOT NULL UNIQUE,
    config_path VARCHAR(500),
    plan        VARCHAR(50) DEFAULT 'starter',
    status      VARCHAR(50) DEFAULT 'active',
    created_at  TIMESTAMP DEFAULT NOW()
);

INSERT INTO tenants (name, tenant_id, config_path, plan)
VALUES ('Default Tenant', 'default', 'company_config.yaml', 'enterprise')
ON CONFLICT (tenant_id) DO NOTHING;

-- ── Core tables (with tenant_id) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id              SERIAL PRIMARY KEY,
    tenant_id       VARCHAR(100) DEFAULT 'default',
    name            VARCHAR(255) NOT NULL,
    role            VARCHAR(255),
    company         VARCHAR(255),
    city            VARCHAR(100),
    industry        VARCHAR(100),
    deal_value      BIGINT DEFAULT 0,
    stage           VARCHAR(50) DEFAULT 'Prospect',
    rep_slack_user  VARCHAR(100),
    notes           TEXT,
    last_touched_at TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS commitments (
    id                       SERIAL PRIMARY KEY,
    tenant_id                VARCHAR(100) DEFAULT 'default',
    lead_id                  INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    lead_name                VARCHAR(255),
    commitment_text          TEXT NOT NULL,
    party                    VARCHAR(50) DEFAULT 'customer',
    deadline                 TIMESTAMP,
    detected_by              VARCHAR(50) DEFAULT 'passive',
    source_message           TEXT,
    status                   VARCHAR(50) DEFAULT 'pending',
    current_escalation_level INTEGER DEFAULT 0,
    last_escalated_at        TIMESTAMP,
    resolved_at              TIMESTAMP,
    created_at               TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS escalation_log (
    id                 SERIAL PRIMARY KEY,
    tenant_id          VARCHAR(100) DEFAULT 'default',
    commitment_id      INTEGER REFERENCES commitments(id),
    level              INTEGER NOT NULL,
    target_slack_user  VARCHAR(100),
    message_sent       TEXT,
    sent_at            TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_queue (
    id               SERIAL PRIMARY KEY,
    tenant_id        VARCHAR(100) DEFAULT 'default',
    source           VARCHAR(50) DEFAULT 'geo_seo',
    keyword          VARCHAR(255),
    volume           INTEGER,
    trend_pct        INTEGER,
    geo              VARCHAR(100),
    brief_notes      TEXT,
    title            VARCHAR(500),
    meta_description TEXT,
    draft_content    TEXT,
    status           VARCHAR(50) DEFAULT 'pending',
    published_url    VARCHAR(500),
    published_at     TIMESTAMP,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS keyword_tracking (
    id              SERIAL PRIMARY KEY,
    tenant_id       VARCHAR(100) DEFAULT 'default',
    keyword         VARCHAR(255) NOT NULL,
    country         VARCHAR(10) DEFAULT 'IN',
    current_rank    INTEGER,
    previous_rank   INTEGER,
    volume          INTEGER,
    published_url   VARCHAR(500),
    last_checked_at TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, keyword)
);

CREATE TABLE IF NOT EXISTS monitored_services (
    id                   SERIAL PRIMARY KEY,
    tenant_id            VARCHAR(100) DEFAULT 'default',
    name                 VARCHAR(255) NOT NULL,
    url                  VARCHAR(500) NOT NULL,
    status               VARCHAR(50) DEFAULT 'unknown',
    last_status_code     INTEGER,
    last_checked_at      TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    created_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS bugs (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) DEFAULT 'default',
    description TEXT NOT NULL,
    severity    VARCHAR(10) NOT NULL,
    status      VARCHAR(50) DEFAULT 'open',
    reported_by VARCHAR(100),
    assigned_to VARCHAR(100),
    source      VARCHAR(50) DEFAULT 'manual',
    customer    VARCHAR(255),
    resolved_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ── CS Agent ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id           SERIAL PRIMARY KEY,
    tenant_id    VARCHAR(100) DEFAULT 'default',
    name         VARCHAR(255) NOT NULL,
    arr          BIGINT DEFAULT 0,
    renewal_date DATE,
    health_score INTEGER DEFAULT 100,
    nps          INTEGER,
    assigned_csm VARCHAR(100),
    status       VARCHAR(50) DEFAULT 'active',
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customer_events (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) DEFAULT 'default',
    customer_id INTEGER REFERENCES customers(id) ON DELETE CASCADE,
    event_type  VARCHAR(100) NOT NULL,
    notes       TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ── Finance Agent ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invoices (
    id           SERIAL PRIMARY KEY,
    tenant_id    VARCHAR(100) DEFAULT 'default',
    vendor       VARCHAR(255) NOT NULL,
    amount       BIGINT NOT NULL,
    due_date     DATE,
    category     VARCHAR(100),
    status       VARCHAR(50) DEFAULT 'pending',
    submitted_by VARCHAR(100),
    approved_by  VARCHAR(100),
    approved_at  TIMESTAMP,
    notes        TEXT,
    created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) DEFAULT 'default',
    submitter   VARCHAR(100) NOT NULL,
    amount      BIGINT NOT NULL,
    category    VARCHAR(100),
    description TEXT,
    expense_date DATE,
    status      VARCHAR(50) DEFAULT 'pending',
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS budgets (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) DEFAULT 'default',
    name        VARCHAR(255) NOT NULL,
    period      VARCHAR(50),
    allocated   BIGINT DEFAULT 0,
    spent       BIGINT DEFAULT 0,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ── Agent Memory ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_memory (
    id         SERIAL PRIMARY KEY,
    tenant_id  VARCHAR(100) DEFAULT 'default',
    agent      VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    context    TEXT,
    outcome    TEXT,
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_patterns (
    id          SERIAL PRIMARY KEY,
    tenant_id   VARCHAR(100) DEFAULT 'default',
    agent       VARCHAR(100) NOT NULL,
    pattern_type VARCHAR(100),
    description TEXT NOT NULL,
    occurrences INTEGER DEFAULT 1,
    confidence  FLOAT DEFAULT 0.5,
    last_seen   TIMESTAMP DEFAULT NOW(),
    created_at  TIMESTAMP DEFAULT NOW()
);

-- ── Approval Workflow ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approval_requests (
    id                  SERIAL PRIMARY KEY,
    tenant_id           VARCHAR(100) DEFAULT 'default',
    agent               VARCHAR(100) NOT NULL,
    item_id             VARCHAR(100),
    item_type           VARCHAR(100),
    required_approvers  TEXT[],
    approvals_received  TEXT[] DEFAULT '{}',
    status              VARCHAR(50) DEFAULT 'pending',
    edit_instruction    TEXT,
    timeout_at          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ── Voice ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voice_transcriptions (
    id           SERIAL PRIMARY KEY,
    tenant_id    VARCHAR(100) DEFAULT 'default',
    agent        VARCHAR(100),
    audio_file   VARCHAR(500),
    transcript   TEXT,
    processed_by VARCHAR(100),
    created_at   TIMESTAMP DEFAULT NOW()
);

-- ── Migrations: add tenant_id to old tables if column missing ─────────────────
DO $$
BEGIN
    -- leads
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='leads' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE leads ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
    END IF;
    -- commitments
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='commitments' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE commitments ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
    END IF;
    -- escalation_log
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='escalation_log' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE escalation_log ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
    END IF;
    -- content_queue
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='content_queue' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE content_queue ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
    END IF;
    -- keyword_tracking: also need to handle unique constraint change
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='keyword_tracking' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE keyword_tracking ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
        -- Drop old unique constraint on keyword alone if it exists
        IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name='keyword_tracking' AND constraint_type='UNIQUE'
              AND constraint_name='keyword_tracking_keyword_key'
        ) THEN
            ALTER TABLE keyword_tracking DROP CONSTRAINT keyword_tracking_keyword_key;
            ALTER TABLE keyword_tracking ADD CONSTRAINT keyword_tracking_tenant_keyword_key
                UNIQUE (tenant_id, keyword);
        END IF;
    END IF;
    -- monitored_services
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='monitored_services' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE monitored_services ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
        IF EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name='monitored_services' AND constraint_type='UNIQUE'
              AND constraint_name='monitored_services_name_key'
        ) THEN
            ALTER TABLE monitored_services DROP CONSTRAINT monitored_services_name_key;
            ALTER TABLE monitored_services ADD CONSTRAINT monitored_services_tenant_name_key
                UNIQUE (tenant_id, name);
        END IF;
    END IF;
    -- bugs
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='bugs' AND column_name='tenant_id'
    ) THEN
        ALTER TABLE bugs ADD COLUMN tenant_id VARCHAR(100) DEFAULT 'default';
    END IF;
    -- bugs customer column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='bugs' AND column_name='customer'
    ) THEN
        ALTER TABLE bugs ADD COLUMN customer VARCHAR(255);
    END IF;
END
$$;
"""

if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(SCHEMA)
    conn.commit()
    cur.close()
    conn.close()
    print("PostgreSQL schema initialized (multi-tenant)")
