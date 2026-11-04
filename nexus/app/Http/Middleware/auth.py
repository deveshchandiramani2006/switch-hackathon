import os
import hmac
import hashlib
from functools import wraps
from flask import request, abort, jsonify

MASTER_KEY = os.getenv("NEXUS_MASTER_KEY", "")


def get_tenant_api_key(tenant_id: str) -> str:
    """Generate a deterministic tenant API key from master key + tenant_id."""
    return hashlib.sha256(f"{MASTER_KEY}:{tenant_id}".encode()).hexdigest()[:32]


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


def require_tenant_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        tenant_id = kwargs.get("tenant_id", "")
        auth = request.headers.get("X-Tenant-API-Key", "")
        if not MASTER_KEY:
            abort(500, "NEXUS_MASTER_KEY not configured")
        expected = get_tenant_api_key(tenant_id)
        if auth != expected:
            abort(401, "Invalid tenant API key")
        return f(*args, **kwargs)
    return decorated


def verify_webhook_signature(request, tenant_id: str) -> bool:
    """
    Verify X-Nexus-Signature: sha256=<hmac> header against tenant's webhook_secret.
    Returns True if valid, False if invalid or secret not found.
    """
    signature_header = request.headers.get("X-Nexus-Signature", "")
    if not signature_header.startswith("sha256="):
        return False

    received_sig = signature_header[7:]  # strip "sha256="

    try:
        from app.Services.DatabaseService import db_cursor
        with db_cursor() as cur:
            cur.execute(
                "SELECT webhook_secret FROM tenants WHERE tenant_id=%s AND status='active'",
                (tenant_id,)
            )
            row = cur.fetchone()
        if not row or not row["webhook_secret"]:
            return False

        secret  = row["webhook_secret"].encode()
        payload = request.get_data()
        expected_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received_sig, expected_sig)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"verify_webhook_signature failed: {e}")
        return False


def require_webhook_signature(f):
    """Decorator: reject webhook requests with invalid HMAC signature."""
    @wraps(f)
    def decorated(*args, **kwargs):
        tenant_id = kwargs.get("tenant_id", "")
        if not verify_webhook_signature(request, tenant_id):
            return jsonify({"error": "Invalid webhook signature"}), 401
        return f(*args, **kwargs)
    return decorated
