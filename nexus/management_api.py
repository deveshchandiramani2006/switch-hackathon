"""
NEXUS Management API — tenant provisioning, data API, webhook ingestion.
Run with: gunicorn -w 2 -b 0.0.0.0:5000 nexus.management_api:app
"""
import os
import uuid
import json
import yaml
import logging
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

app = Flask(__name__)
MASTER_KEY = os.getenv("NEXUS_MASTER_KEY", "")
CONFIG_DIR = os.getenv("NEXUS_CONFIG_DIR", "/app/tenant_configs")


# ── Auth ──────────────────────────────────────────────────────────────────────

def require_master_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not MASTER_KEY:
            abort(500, "NEXUS_MASTER_KEY not configured")
        if auth != f"Bearer {MASTER_KEY}":
            abort(401, "Unauthorized")
        return f(*args, **kwargs)
    return decorated


def get_tenant_api_key(tenant_id: str) -> str:
    """Generate a deterministic tenant API key from master key + tenant_id."""
    import hashlib
    return hashlib.sha256(f"{MASTER_KEY}:{tenant_id}".encode()).hexdigest()[:32]


def require_tenant_key(f):
    """Check tenant-specific API key (used for webhooks)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        tenant_id = kwargs.get("tenant_id", "")
        auth      = request.headers.get("X-Tenant-API-Key", "")
        expected  = get_tenant_api_key(tenant_id)
        if auth != expected:
            abort(401, "Invalid tenant API key")
        return f(*args, **kwargs)
    return decorated


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    from shared.db import db_cursor
    return db_cursor


def tenant_exists(tenant_id: str) -> bool:
    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE tenant_id=%s", (tenant_id,))
        return cur.fetchone() is not None


def generate_tenant_config(tenant_id: str, name: str, agents: list, llm_cfg: dict) -> dict:
    """Generate a company_config.yaml dict for a new tenant."""
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
    """Save tenant config to disk. Returns config path."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    path = os.path.join(CONFIG_DIR, f"{tenant_id}.yaml")
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    return path


# ── Tenant CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/v1/tenants", methods=["POST"])
@require_master_key
def create_tenant():
    """
    Body: {name, agents: [], llm: {provider, api_key, model}, ...}
    Returns: {tenant_id, status, dashboard_url, api_key}
    """
    body   = request.get_json(force=True) or {}
    name   = body.get("name", "").strip()
    agents = body.get("agents", ["sales", "support", "infra"])
    llm    = body.get("llm", {})

    if not name:
        return jsonify({"error": "name is required"}), 400

    tenant_id = body.get("tenant_id") or str(uuid.uuid4())[:8]

    from shared.db import db_cursor
    # Check uniqueness
    with db_cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE tenant_id=%s", (tenant_id,))
        if cur.fetchone():
            return jsonify({"error": f"tenant_id '{tenant_id}' already exists"}), 409

    # Generate config
    config      = generate_tenant_config(tenant_id, name, agents, llm)
    config_path = save_tenant_config(tenant_id, config)

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, tenant_id, config_path, plan) VALUES (%s, %s, %s, %s) RETURNING id",
            (name, tenant_id, config_path, body.get("plan", "starter"))
        )
        db_id = cur.fetchone()["id"]

    tenant_api_key = get_tenant_api_key(tenant_id)
    logger.info(f"Tenant created: {tenant_id} ({name})")

    return jsonify({
        "tenant_id":          tenant_id,
        "db_id":              db_id,
        "name":               name,
        "status":             "active",
        "config_path":        config_path,
        "api_key":            tenant_api_key,
        "agents_enabled":     agents,
        "agents_live_in_seconds": 30,
        "dashboard_url":      f"/dashboard/{tenant_id}"
    }), 201


@app.route("/api/v1/tenants/<tenant_id>", methods=["GET"])
@require_master_key
def get_tenant(tenant_id):
    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, tenant_id, config_path, plan, status, created_at FROM tenants WHERE tenant_id=%s",
            (tenant_id,)
        )
        tenant = cur.fetchone()

    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    # Load config file
    config = {}
    if tenant["config_path"] and os.path.exists(tenant["config_path"]):
        with open(tenant["config_path"]) as f:
            config = yaml.safe_load(f) or {}

    return jsonify({
        "tenant_id":   tenant["tenant_id"],
        "name":        tenant["name"],
        "plan":        tenant["plan"],
        "status":      tenant["status"],
        "created_at":  str(tenant["created_at"]),
        "config":      config,
        "api_key":     get_tenant_api_key(tenant_id),
    })


@app.route("/api/v1/tenants/<tenant_id>", methods=["PATCH"])
@require_master_key
def update_tenant(tenant_id):
    """Update LLM config, escalation chain, enable/disable agents."""
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body = request.get_json(force=True) or {}
    from shared.db import db_cursor

    # Load existing config
    with db_cursor() as cur:
        cur.execute("SELECT config_path, name FROM tenants WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()

    config = {}
    if row["config_path"] and os.path.exists(row["config_path"]):
        with open(row["config_path"]) as f:
            config = yaml.safe_load(f) or {}

    # Apply patches
    if "llm" in body:
        config.setdefault("llm", {})
        config["llm"].update(body["llm"])

    if "agents" in body:
        for agent, enabled in body["agents"].items():
            config.setdefault("agents", {})[agent] = {"enabled": bool(enabled)}

    if "escalation_chains" in body:
        config.setdefault("escalation_chains", {}).update(body["escalation_chains"])

    config_path = save_tenant_config(tenant_id, config)
    with db_cursor() as cur:
        cur.execute("UPDATE tenants SET config_path=%s WHERE tenant_id=%s", (config_path, tenant_id))

    return jsonify({"tenant_id": tenant_id, "status": "updated"})


@app.route("/api/v1/tenants/<tenant_id>", methods=["DELETE"])
@require_master_key
def delete_tenant(tenant_id):
    """Soft-delete tenant."""
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute("UPDATE tenants SET status='deleted' WHERE tenant_id=%s", (tenant_id,))

    logger.info(f"Tenant soft-deleted: {tenant_id}")
    return jsonify({"tenant_id": tenant_id, "status": "deleted"})


# ── Data API ──────────────────────────────────────────────────────────────────

@app.route("/api/v1/tenants/<tenant_id>/pipeline", methods=["GET"])
@require_master_key
def get_pipeline(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, role, city, industry, deal_value, stage, rep_slack_user, last_touched_at
            FROM leads WHERE tenant_id=%s AND stage NOT IN ('Closed-Won','Closed-Lost')
            ORDER BY deal_value DESC LIMIT 50
            """,
            (tenant_id,)
        )
        leads = cur.fetchall()
        cur.execute(
            "SELECT SUM(deal_value) AS total FROM leads WHERE tenant_id=%s AND stage NOT IN ('Closed-Won','Closed-Lost')",
            (tenant_id,)
        )
        total = cur.fetchone()["total"] or 0

    return jsonify({
        "tenant_id": tenant_id,
        "total_pipeline": total,
        "leads": [dict(r) for r in leads]
    })


@app.route("/api/v1/tenants/<tenant_id>/incidents", methods=["GET"])
@require_master_key
def get_incidents(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, severity, description, status, reported_by, created_at FROM bugs "
            "WHERE tenant_id=%s AND status='open' ORDER BY severity, created_at DESC LIMIT 50",
            (tenant_id,)
        )
        bugs = cur.fetchall()

    return jsonify({
        "tenant_id": tenant_id,
        "incidents": [dict(r) for r in bugs]
    })


# ── Webhook API ───────────────────────────────────────────────────────────────

@app.route("/api/v1/tenants/<tenant_id>/webhooks/lead", methods=["POST"])
def webhook_lead(tenant_id):
    """Ingest a new lead via webhook (no master key — tenant API key)."""
    auth     = request.headers.get("X-Tenant-API-Key", "")
    expected = get_tenant_api_key(tenant_id)
    if not MASTER_KEY or auth != expected:
        abort(401, "Invalid tenant API key")

    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body     = request.get_json(force=True) or {}
    name     = body.get("name", "").strip()
    role     = body.get("role", "")
    city     = body.get("city", "")
    industry = body.get("industry", "")
    deal_val = int(body.get("deal_value", 0))

    if not name:
        return jsonify({"error": "name is required"}), 400

    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO leads (tenant_id, name, role, city, industry, deal_value) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, name, role, city, industry, deal_val)
        )
        lead_id = cur.fetchone()["id"]

    logger.info(f"Webhook lead #{lead_id} for tenant {tenant_id}: {name}")
    return jsonify({"lead_id": lead_id, "status": "created"}), 201


@app.route("/api/v1/tenants/<tenant_id>/webhooks/bug", methods=["POST"])
def webhook_bug(tenant_id):
    """Ingest a bug report via webhook."""
    auth     = request.headers.get("X-Tenant-API-Key", "")
    expected = get_tenant_api_key(tenant_id)
    if not MASTER_KEY or auth != expected:
        abort(401, "Invalid tenant API key")

    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body        = request.get_json(force=True) or {}
    description = body.get("description", "").strip()
    severity    = body.get("severity", "P2").upper()
    source      = body.get("source", "webhook")
    customer    = body.get("customer", "")

    if not description:
        return jsonify({"error": "description is required"}), 400

    from shared.db import db_cursor
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO bugs (tenant_id, description, severity, source, customer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, description, severity, source, customer)
        )
        bug_id = cur.fetchone()["id"]

    logger.info(f"Webhook bug #{bug_id} for tenant {tenant_id}: {severity}")
    return jsonify({"bug_id": bug_id, "status": "created"}), 201


@app.route("/api/v1/tenants/<tenant_id>/webhooks/deploy", methods=["POST"])
def webhook_deploy(tenant_id):
    """Log a deploy event and update monitored_services last_checked."""
    auth     = request.headers.get("X-Tenant-API-Key", "")
    expected = get_tenant_api_key(tenant_id)
    if not MASTER_KEY or auth != expected:
        abort(401, "Invalid tenant API key")

    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body    = request.get_json(force=True) or {}
    service = body.get("service", "").strip()
    status  = body.get("status", "deployed")

    logger.info(f"Deploy event for tenant {tenant_id}: {service} -> {status}")
    return jsonify({"tenant_id": tenant_id, "service": service, "status": status}), 200


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/api/v1/health")
def health():
    return jsonify({"status": "ok", "version": "2.0.0"})


if __name__ == "__main__":
    port = int(os.getenv("MANAGEMENT_API_PORT", "5000"))
    logger.info(f"Management API starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
