from flask import Blueprint
from app.Http.Middleware.auth import require_master_key, require_tenant_key
from app.Http.Controllers.ManagementController import (
    create_tenant, get_tenant, update_tenant, delete_tenant,
    get_pipeline, get_incidents,
    webhook_lead, webhook_bug, webhook_deploy,
    health_check,
)

api_bp = Blueprint("api", __name__)

# ── Tenant CRUD ───────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants",              view_func=require_master_key(create_tenant),  methods=["POST"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>",  view_func=require_master_key(get_tenant),     methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>",  view_func=require_master_key(update_tenant),  methods=["PATCH"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>",  view_func=require_master_key(delete_tenant),  methods=["DELETE"])

# ── Data API ──────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/pipeline",  view_func=require_master_key(get_pipeline),  methods=["GET"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/incidents", view_func=require_master_key(get_incidents), methods=["GET"])

# ── Webhook API ───────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/webhooks/lead",   view_func=require_tenant_key(webhook_lead),   methods=["POST"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/webhooks/bug",    view_func=require_tenant_key(webhook_bug),    methods=["POST"])
api_bp.add_url_rule("/api/v1/tenants/<tenant_id>/webhooks/deploy", view_func=require_tenant_key(webhook_deploy), methods=["POST"])

# ── Health ────────────────────────────────────────────────────────────────────
api_bp.add_url_rule("/api/v1/health", view_func=health_check, methods=["GET"])
