from flask import Blueprint
from app.Http.Middleware.auth import require_master_key, require_tenant_key, require_webhook_signature
from app.Http.Controllers.ManagementController import (
    # Tenant CRUD
    create_tenant, get_tenant, update_tenant, delete_tenant,
    # Data APIs
    get_pipeline, get_incidents,
    # Webhooks
    webhook_lead, webhook_bug, webhook_deploy,
    # Health
    health_check,
    # SaaS endpoints
    get_webhook_secret, rotate_webhook_secret,
    get_tenant_config, update_tenant_config,
    get_analytics,
    get_onboarding_status,
    set_user_role, list_users,
    # Operations hardening
    get_agent_liveness, get_audit_log, purge_tenant,
)

api_bp = Blueprint("api", __name__)

# ── Tenant CRUD ───────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants",             view_func=require_master_key(create_tenant), methods=["POST"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>", view_func=require_master_key(get_tenant),    methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>", view_func=require_master_key(update_tenant), methods=["PATCH"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>", view_func=require_master_key(delete_tenant), methods=["DELETE"])

# ── Data APIs ─────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/pipeline",  view_func=require_master_key(get_pipeline),  methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/incidents", view_func=require_master_key(get_incidents), methods=["GET"])

# ── Webhook ingestion (HMAC-signed) ───────────────────────────────────────────
api_bp.add_url_rule(
    "/api/v1/tenants/<tenant_id>/webhooks/lead",
    view_func=require_webhook_signature(require_tenant_key(webhook_lead)),
    methods=["POST"],
)
api_bp.add_url_rule(
    "/api/v1/tenants/<tenant_id>/webhooks/bug",
    view_func=require_webhook_signature(require_tenant_key(webhook_bug)),
    methods=["POST"],
)
api_bp.add_url_rule(
    "/api/v1/tenants/<tenant_id>/webhooks/deploy",
    view_func=require_webhook_signature(require_tenant_key(webhook_deploy)),
    methods=["POST"],
)

# ── Webhook secret management ─────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/webhook-secret",        view_func=require_master_key(get_webhook_secret),    methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/webhook-secret/rotate", view_func=require_master_key(rotate_webhook_secret), methods=["POST"])

# ── Tenant config ─────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/config", view_func=require_master_key(get_tenant_config),    methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/config", view_func=require_master_key(update_tenant_config), methods=["PATCH"])

# ── Analytics ─────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/analytics", view_func=require_master_key(get_analytics), methods=["GET"])

# ── Onboarding ────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/onboarding", view_func=require_master_key(get_onboarding_status), methods=["GET"])

# ── User management ───────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/users",                 view_func=require_master_key(list_users),    methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/users/<username>/role", view_func=require_master_key(set_user_role), methods=["PATCH"])

# ── Agent liveness ────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/agents/status", view_func=require_master_key(get_agent_liveness), methods=["GET"])

# ── Audit log ─────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/audit-log", view_func=require_master_key(get_audit_log), methods=["GET"])

# ── GDPR purge ────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/purge", view_func=require_master_key(purge_tenant), methods=["DELETE"])

# ── Health ────────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/health", view_func=health_check, methods=["GET"])
