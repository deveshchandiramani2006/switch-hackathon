import os
import yaml
from app.Services.DatabaseService import db_cursor
from app.Http.Middleware.auth import get_tenant_api_key

CONFIG_DIR = os.getenv("NEXUS_CONFIG_DIR", "/app/tenant_configs")


def tenant_exists(tenant_id: str) -> bool:
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE tenant_id=%s", (tenant_id,))
        return cur.fetchone() is not None


def generate_tenant_config(tenant_id: str, name: str, agents: list, llm_cfg: dict) -> dict:
    all_agents = ["sales_agent", "support_agent", "geo_seo_agent", "blog_agent",
                  "infra_agent", "cs_agent", "finance_agent"]
    agent_flags = {a: {"enabled": a.replace("_agent", "") in agents or a in agents}
                   for a in all_agents}

    provider = llm_cfg.get("provider", "anthropic")
    model    = llm_cfg.get("model", "claude-sonnet-4-6")

    return {
        "company": {"name": name, "timezone": "Asia/Kolkata", "locale": "en"},
        "tenant":  {"id": tenant_id},
        "agents":  agent_flags,
        "llm": {
            "agents": {
                "default":        {"provider": provider, "model": model},
                "sales_agent":    {"provider": provider, "model": model},
                "support_agent":  {"provider": provider, "model": model},
                "geo_seo_agent":  {"provider": provider, "model": model},
                "blog_agent":     {"provider": "ollama", "model": "mistral"},
                "infra_agent":    {"provider": "ollama", "model": "phi3"},
                "cs_agent":       {"provider": provider, "model": model},
                "finance_agent":  {"provider": provider, "model": model},
            }
        },
        "escalation_chains": {
            "sales":   {"levels": [], "deal_size_tiers": {}},
            "support": {"levels": [], "sla": {"p0_hours": 2, "p1_hours": 8, "p2_hours": 48}},
            "infra":   {"levels": [], "failure_threshold": 2},
            "cs":      {"csm": "@cs_team", "cs_lead": "@cs_lead"},
            "finance": {"approver": "@finance_lead"},
        },
        "geo_seo": {
            "analysis": {"trend_threshold_pct": 200, "rank_drop_threshold": 5},
            "content_queue": {"max_briefs_per_run": 3},
            "initial_keywords": [],
        }
    }


def save_tenant_config(tenant_id: str, config: dict) -> str:
    """Write tenant config to disk. Returns config path."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = os.path.join(CONFIG_DIR, f"{tenant_id}.yaml")
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    return path


def load_tenant_config(config_path: str) -> dict:
    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}
