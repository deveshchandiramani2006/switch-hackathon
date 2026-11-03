import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              SERIAL PRIMARY KEY,
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
    commitment_id      INTEGER REFERENCES commitments(id),
    level              INTEGER NOT NULL,
    target_slack_user  VARCHAR(100),
    message_sent       TEXT,
    sent_at            TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_queue (
    id               SERIAL PRIMARY KEY,
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
    keyword         VARCHAR(255) NOT NULL UNIQUE,
    country         VARCHAR(10) DEFAULT 'IN',
    current_rank    INTEGER,
    previous_rank   INTEGER,
    volume          INTEGER,
    published_url   VARCHAR(500),
    last_checked_at TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monitored_services (
    id                   SERIAL PRIMARY KEY,
    name                 VARCHAR(255) NOT NULL UNIQUE,
    url                  VARCHAR(500) NOT NULL,
    status               VARCHAR(50) DEFAULT 'unknown',
    last_status_code     INTEGER,
    last_checked_at      TIMESTAMP,
    consecutive_failures INTEGER DEFAULT 0,
    created_at           TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bugs (
    id          SERIAL PRIMARY KEY,
    description TEXT NOT NULL,
    severity    VARCHAR(10) NOT NULL,
    status      VARCHAR(50) DEFAULT 'open',
    reported_by VARCHAR(100),
    assigned_to VARCHAR(100),
    source      VARCHAR(50) DEFAULT 'manual',
    resolved_at TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW()
);
"""

if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(SCHEMA)
    conn.commit()
    cur.close()
    conn.close()
    print("PostgreSQL schema initialized")
