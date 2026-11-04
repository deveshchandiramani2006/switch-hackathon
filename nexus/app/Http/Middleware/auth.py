import os
import hashlib
from functools import wraps
from flask import request, abort

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
