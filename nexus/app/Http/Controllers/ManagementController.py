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

    with db_cursor() as cur:
        cur.execute("UPDATE tenants SET status='deleted' WHERE tenant_id=%s", (tenant_id,))

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
