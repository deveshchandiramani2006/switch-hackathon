import uuid
import logging
from flask import request, jsonify

from app.Http.Middleware.auth import get_tenant_api_key
from app.Models.Tenant import (
    tenant_exists, generate_tenant_config,
    save_tenant_config, load_tenant_config
)
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

AUDIT_TABLES = [
    "leads", "commitments", "escalation_log", "content_queue", "keyword_tracking",
    "monitored_services", "bugs", "customers", "customer_events", "invoices",
    "expenses", "budgets", "agent_memory", "agent_patterns", "approval_requests",
    "approval_sessions", "conversation_sessions", "usage_events", "onboarding_sessions",
    "voice_transcriptions", "tenant_users", "tenant_configs", "agent_heartbeats",
    "audit_log",
]


def _write_audit(tenant_id: str, actor: str, action: str,
                 target_type: str = None, target_id: str = None,
                 before_val: dict = None, after_val: dict = None):
    """Write an immutable audit entry. Swallows DB errors to never break the main path."""
    try:
        import json
        with db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log (tenant_id, actor, action, target_type, target_id, before_val, after_val)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    tenant_id, actor, action, target_type, str(target_id) if target_id else None,
                    json.dumps(before_val) if before_val else None,
                    json.dumps(after_val)  if after_val  else None,
                )
            )
    except Exception as e:
        logger.warning(f"audit log write failed: {e}")


def create_tenant():
    body   = request.get_json(force=True) or {}
    name   = body.get("name", "").strip()
    agents = body.get("agents", ["sales", "support", "infra"])
    llm    = body.get("llm", {})

    if not name:
        return jsonify({"error": "name is required"}), 400

    tenant_id = body.get("tenant_id") or str(uuid.uuid4())[:8]

    with db_cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE tenant_id=%s", (tenant_id,))
        if cur.fetchone():
            return jsonify({"error": f"tenant_id '{tenant_id}' already exists"}), 409

    config      = generate_tenant_config(tenant_id, name, agents, llm)
    config_path = save_tenant_config(tenant_id, config)

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, tenant_id, config_path, plan) VALUES (%s, %s, %s, %s) RETURNING id",
            (name, tenant_id, config_path, body.get("plan", "starter"))
        )
        db_id = cur.fetchone()["id"]

    logger.info(f"Tenant created: {tenant_id} ({name})")
    return jsonify({
        "tenant_id":              tenant_id,
        "db_id":                  db_id,
        "name":                   name,
        "status":                 "active",
        "config_path":            config_path,
        "api_key":                get_tenant_api_key(tenant_id),
        "agents_enabled":         agents,
        "agents_live_in_seconds": 30,
        "dashboard_url":          f"/dashboard/{tenant_id}"
    }), 201


def get_tenant(tenant_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, tenant_id, config_path, plan, status, created_at FROM tenants WHERE tenant_id=%s",
            (tenant_id,)
        )
        tenant = cur.fetchone()

    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    config = load_tenant_config(tenant["config_path"])
    return jsonify({
        "tenant_id":  tenant["tenant_id"],
        "name":       tenant["name"],
        "plan":       tenant["plan"],
        "status":     tenant["status"],
        "created_at": str(tenant["created_at"]),
        "config":     config,
        "api_key":    get_tenant_api_key(tenant_id),
    })


def update_tenant(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body = request.get_json(force=True) or {}

    with db_cursor() as cur:
        cur.execute("SELECT config_path FROM tenants WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()

    config = load_tenant_config(row["config_path"])

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


def delete_tenant(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    actor = request.headers.get("X-Actor", "api")
    with db_cursor() as cur:
        cur.execute("UPDATE tenants SET status='deleted' WHERE tenant_id=%s", (tenant_id,))

    _write_audit(tenant_id, actor, "tenant_deleted", "tenant", tenant_id)
    logger.info(f"Tenant soft-deleted: {tenant_id}")
    return jsonify({"tenant_id": tenant_id, "status": "deleted"})


def get_pipeline(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

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
        "tenant_id":      tenant_id,
        "total_pipeline": total,
        "leads":          [dict(r) for r in leads]
    })


def get_incidents(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

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


def webhook_lead(tenant_id):
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

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO leads (tenant_id, name, role, city, industry, deal_value) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, name, role, city, industry, deal_val)
        )
        lead_id = cur.fetchone()["id"]

    logger.info(f"Webhook lead #{lead_id} for tenant {tenant_id}: {name}")
    return jsonify({"lead_id": lead_id, "status": "created"}), 201


def webhook_bug(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body        = request.get_json(force=True) or {}
    description = body.get("description", "").strip()
    severity    = body.get("severity", "P2").upper()
    source      = body.get("source", "webhook")
    customer    = body.get("customer", "")

    if not description:
        return jsonify({"error": "description is required"}), 400

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO bugs (tenant_id, description, severity, source, customer) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (tenant_id, description, severity, source, customer)
        )
        bug_id = cur.fetchone()["id"]

    logger.info(f"Webhook bug #{bug_id} for tenant {tenant_id}: {severity}")
    return jsonify({"bug_id": bug_id, "status": "created"}), 201


def webhook_deploy(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    body    = request.get_json(force=True) or {}
    service = body.get("service", "").strip()
    status  = body.get("status", "deployed")

    logger.info(f"Deploy event for tenant {tenant_id}: {service} -> {status}")
    return jsonify({"tenant_id": tenant_id, "service": service, "status": status}), 200


def health_check():
    return jsonify({"status": "ok", "version": "2.0.0"})


# ── Webhook secret ─────────────────────────────────────────────────────────────

def get_webhook_secret(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    with db_cursor() as cur:
        cur.execute("SELECT webhook_secret FROM tenants WHERE tenant_id=%s", (tenant_id,))
        row = cur.fetchone()
    if not row or not row["webhook_secret"]:
        return jsonify({"error": "Webhook secret not set"}), 404
    return jsonify({"tenant_id": tenant_id, "webhook_secret": row["webhook_secret"]})


def rotate_webhook_secret(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    import secrets
    new_secret = secrets.token_hex(32)
    with db_cursor() as cur:
        cur.execute("UPDATE tenants SET webhook_secret=%s WHERE tenant_id=%s", (new_secret, tenant_id))
    actor = request.headers.get("X-Actor", "api")
    _write_audit(tenant_id, actor, "secret_rotated", "tenant", tenant_id)
    logger.info(f"Webhook secret rotated for tenant {tenant_id}")
    return jsonify({"tenant_id": tenant_id, "webhook_secret": new_secret})


# ── Tenant config ─────────────────────────────────────────────────────────────

def get_tenant_config(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    from app.Models.TenantConfig import TenantConfig
    TenantConfig.ensure_exists(tenant_id)
    return jsonify({"tenant_id": tenant_id, "config": TenantConfig.get(tenant_id)})


def update_tenant_config(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    body = request.get_json(force=True) or {}
    allowed = {"escalation_chain", "integrations", "thresholds", "agent_flags", "llm_config", "geo_seo_config"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return jsonify({"error": f"No valid fields. Allowed: {', '.join(allowed)}"}), 400
    from app.Models.TenantConfig import TenantConfig
    old_cfg = TenantConfig.get(tenant_id)
    ok = TenantConfig.save(tenant_id, **updates)
    if not ok:
        return jsonify({"error": "Config update failed"}), 500
    actor = request.headers.get("X-Actor", "api")
    _write_audit(tenant_id, actor, "config_updated", "tenant", tenant_id,
                 before_val={k: old_cfg.get(k) for k in updates},
                 after_val=updates)
    return jsonify({"tenant_id": tenant_id, "status": "updated", "updated_fields": list(updates.keys())})


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_analytics(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    days = int(request.args.get("period", "7").replace("d", ""))
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    summary = UsageAnalyticsService.get_summary(tenant_id, days=days)
    return jsonify({"tenant_id": tenant_id, **summary})


# ── Onboarding ────────────────────────────────────────────────────────────────

def get_onboarding_status(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    from app.Services.OnboardingService import OnboardingService
    return jsonify(OnboardingService.get_status(tenant_id))


# ── User management ───────────────────────────────────────────────────────────

def list_users(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    with db_cursor() as cur:
        cur.execute(
            "SELECT username, display_name, role, joined_at, last_seen FROM tenant_users "
            "WHERE tenant_id=%s ORDER BY joined_at DESC",
            (tenant_id,)
        )
        users = cur.fetchall()
    return jsonify({"tenant_id": tenant_id, "users": [dict(u) for u in users]})


def set_user_role(tenant_id, username):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    body = request.get_json(force=True) or {}
    role = body.get("role", "").strip()
    from app.Services.ValidationService import validate_role
    role, err = validate_role(role)
    if err:
        return jsonify({"error": err}), 400
    from app.Services.UserIdentityService import UserIdentityService
    old_role = UserIdentityService.get_role(tenant_id, username)
    ok = UserIdentityService.set_role(tenant_id, username, role)
    if not ok:
        return jsonify({"error": "Failed to set role"}), 500
    actor = request.headers.get("X-Actor", "api")
    _write_audit(tenant_id, actor, "role_changed", "user", username,
                 before_val={"role": old_role}, after_val={"role": role})
    return jsonify({"tenant_id": tenant_id, "username": username, "role": role})


# ── Agent liveness ────────────────────────────────────────────────────────────

def get_agent_liveness(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT agent_name, last_seen,
                   EXTRACT(EPOCH FROM (NOW() - last_seen)) AS seconds_ago
            FROM agent_heartbeats
            WHERE tenant_id = %s
            ORDER BY agent_name
            """,
            (tenant_id,)
        )
        rows = cur.fetchall()

    agents = []
    for r in rows:
        seconds_ago = int(r["seconds_ago"] or 0)
        status = "alive" if seconds_ago < 600 else ("stale" if seconds_ago < 1800 else "dead")
        agents.append({
            "agent":       r["agent_name"],
            "last_seen":   str(r["last_seen"]),
            "seconds_ago": seconds_ago,
            "status":      status,
        })

    return jsonify({"tenant_id": tenant_id, "agents": agents})


# ── Audit log ─────────────────────────────────────────────────────────────────

def get_audit_log(tenant_id):
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404
    limit = min(int(request.args.get("limit", "50")), 200)
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT actor, action, target_type, target_id, before_val, after_val, created_at
            FROM audit_log
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, limit)
        )
        rows = cur.fetchall()
    return jsonify({"tenant_id": tenant_id, "entries": [dict(r) for r in rows]})


# ── GDPR hard delete ──────────────────────────────────────────────────────────

def purge_tenant(tenant_id):
    """Hard delete — wipes ALL data for the tenant then removes the tenant row."""
    if not tenant_exists(tenant_id):
        return jsonify({"error": "Tenant not found"}), 404

    actor = request.headers.get("X-Actor", "api")
    _write_audit(tenant_id, actor, "tenant_purged", "tenant", tenant_id)

    with db_cursor() as cur:
        for table in AUDIT_TABLES:
            try:
                cur.execute(f"DELETE FROM {table} WHERE tenant_id = %s", (tenant_id,))
            except Exception as e:
                logger.warning(f"purge_tenant: could not delete from {table}: {e}")
        cur.execute("DELETE FROM tenants WHERE tenant_id = %s", (tenant_id,))

    logger.info(f"Tenant hard-deleted (GDPR purge): {tenant_id}")
    return jsonify({"tenant_id": tenant_id, "status": "purged"})
