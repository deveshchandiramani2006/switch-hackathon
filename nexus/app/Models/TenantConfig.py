"""
TenantConfig - per-tenant configuration stored in DB (tenant_configs table).

Replaces the single company.yaml file with per-tenant JSONB config in Postgres.
Each tenant has its own escalation chains, integrations, thresholds, and agent flags.
"""
import logging
import yaml
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

DEFAULTS = {
    "escalation_chain": {
        "sales":   {"levels": [], "deal_size_tiers": {}},
        "support": {"levels": [], "sla": {"p0_hours": 2, "p1_hours": 8, "p2_hours": 48}},
        "infra":   {"levels": [], "failure_threshold": 2},
        "cs":      {"csm": "@cs_team", "cs_lead": "@cs_lead"},
        "finance": {"approver": "@finance_lead"},
    },
    "thresholds": {
        "stale_lead_days":           7,
        "health_score_red":          50,
        "health_score_yellow":       70,
        "escalation_check_minutes":  60,
        "infra_failure_threshold":   2,
    },
    "agent_flags": {
        "sales_agent":    True,
        "support_agent":  True,
        "geo_seo_agent":  True,
        "blog_agent":     True,
        "infra_agent":    True,
        "cs_agent":       True,
        "finance_agent":  True,
    },
    "integrations": {
        "blog_api_url":  "",
        "serp_api_key":  "",
        "slack_webhook": "",
    },
    "geo_seo_config": {
        "trend_threshold_pct":  200,
        "rank_drop_threshold":  5,
        "max_briefs_per_run":   3,
        "initial_keywords":     [],
    },
}


class TenantConfig:

    @classmethod
    def get(cls, tenant_id: str) -> dict:
        """Load config from DB, falling back to defaults for missing keys."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT escalation_chain, integrations, thresholds, agent_flags, llm_config, geo_seo_config "
                    "FROM tenant_configs WHERE tenant_id=%s",
                    (tenant_id,)
                )
                row = cur.fetchone()
        except Exception as e:
            logger.warning(f"TenantConfig.get failed for {tenant_id}: {e}")
            return DEFAULTS.copy()

        if not row:
            return DEFAULTS.copy()

        return {
            "escalation_chain": row["escalation_chain"] or DEFAULTS["escalation_chain"],
            "integrations":     row["integrations"]     or DEFAULTS["integrations"],
            "thresholds":       row["thresholds"]        or DEFAULTS["thresholds"],
            "agent_flags":      row["agent_flags"]       or DEFAULTS["agent_flags"],
            "llm_config":       row["llm_config"]        or {},
            "geo_seo_config":   row["geo_seo_config"]    or DEFAULTS["geo_seo_config"],
        }

    @classmethod
    def get_escalation_chain(cls, tenant_id: str, chain_name: str) -> dict:
        """Convenience: get a single escalation chain (e.g. 'sales', 'support')."""
        cfg = cls.get(tenant_id)
        return cfg.get("escalation_chain", {}).get(chain_name, {})

    @classmethod
    def get_threshold(cls, tenant_id: str, key: str, default=None):
        """Convenience: get a single threshold value."""
        cfg = cls.get(tenant_id)
        return cfg.get("thresholds", {}).get(key, default)

    @classmethod
    def save(cls, tenant_id: str, **sections) -> bool:
        """
        Upsert config sections. Pass keyword args matching column names:
          escalation_chain, integrations, thresholds, agent_flags, llm_config, geo_seo_config
        """
        import json
        allowed = {"escalation_chain", "integrations", "thresholds",
                   "agent_flags", "llm_config", "geo_seo_config"}
        updates = {k: v for k, v in sections.items() if k in allowed}
        if not updates:
            return False

        set_clauses = ", ".join(f"{k} = %s" for k in updates)
        set_clauses += ", updated_at = NOW()"
        values = [json.dumps(v) for v in updates.values()]
        values.append(tenant_id)

        try:
            with db_cursor() as cur:
                result = cur.execute(
                    f"UPDATE tenant_configs SET {set_clauses} WHERE tenant_id=%s",
                    values
                )
                if cur.rowcount == 0:
                    # Row doesn't exist - insert with defaults first
                    import json as _json
                    cur.execute(
                        "INSERT INTO tenant_configs (tenant_id) VALUES (%s) ON CONFLICT (tenant_id) DO NOTHING",
                        (tenant_id,)
                    )
                    cur.execute(
                        f"UPDATE tenant_configs SET {set_clauses} WHERE tenant_id=%s",
                        values
                    )
            return True
        except Exception as e:
            logger.error(f"TenantConfig.save failed for {tenant_id}: {e}")
            return False

    @classmethod
    def from_yaml(cls, tenant_id: str, yaml_path: str) -> bool:
        """Migrate a legacy company.yaml into the DB for the given tenant."""
        try:
            with open(yaml_path) as f:
                raw = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.error(f"TenantConfig.from_yaml: file not found: {yaml_path}")
            return False

        escalation_chain = raw.get("escalation_chains", DEFAULTS["escalation_chain"])
        geo_seo_config   = raw.get("geo_seo", {}).get("analysis", DEFAULTS["geo_seo_config"])
        agent_flags      = {
            k: v.get("enabled", True)
            for k, v in raw.get("agents", {}).items()
        }
        llm_config = raw.get("llm", {})

        return cls.save(
            tenant_id,
            escalation_chain=escalation_chain,
            geo_seo_config=geo_seo_config,
            agent_flags=agent_flags,
            llm_config=llm_config,
        )

    @classmethod
    def ensure_exists(cls, tenant_id: str) -> None:
        """Create default config row if missing."""
        import json
        try:
            with db_cursor() as cur:
                cur.execute(
                    "INSERT INTO tenant_configs (tenant_id, escalation_chain, thresholds, agent_flags) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (tenant_id) DO NOTHING",
                    (
                        tenant_id,
                        json.dumps(DEFAULTS["escalation_chain"]),
                        json.dumps(DEFAULTS["thresholds"]),
                        json.dumps(DEFAULTS["agent_flags"]),
                    )
                )
        except Exception as e:
            logger.error(f"TenantConfig.ensure_exists failed: {e}")
