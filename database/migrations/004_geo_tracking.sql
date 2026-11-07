
-- ── 004_geo_tracking.sql ───────────────────────────────────────────────────────
-- GEO (Generative Engine Optimization) citation tracking and scoring.

CREATE TABLE IF NOT EXISTS geo_citations (
    id              SERIAL PRIMARY KEY,
    tenant_id       VARCHAR(100) NOT NULL,
    keyword         VARCHAR(500) NOT NULL,
    engine          VARCHAR(100) NOT NULL,  -- openai | brave | google_sge
    cited           BOOLEAN      NOT NULL DEFAULT FALSE,
    citation_url    TEXT,
    snippet         TEXT,
    ai_score        INTEGER,                -- 1-10 AI-friendliness score
    checked_at      TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geo_citations_lookup
    ON geo_citations (tenant_id, keyword, engine, checked_at DESC);

CREATE TABLE IF NOT EXISTS geo_recommendations (
    id              SERIAL PRIMARY KEY,
    tenant_id       VARCHAR(100) NOT NULL,
    keyword         VARCHAR(500) NOT NULL,
    recommendation  TEXT         NOT NULL,
    created_at      TIMESTAMP    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_geo_recommendations_lookup
    ON geo_recommendations (tenant_id, keyword, created_at DESC);
