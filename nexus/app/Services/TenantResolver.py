"""
TenantResolver - resolves tenant_id for every incoming Switch message.

Resolution order:
  1. TENANT_ID env var (fastest - used in isolated per-tenant Docker deployments)
  2. payload workspace_id → DB lookup
  3. payload room_id → DB room_mappings lookup
  4. Fall back to "default"

For isolated deployments (one container = one tenant), just set TENANT_ID in
the container's environment. For shared-infra multi-tenant, leave TENANT_ID
unset and populate workspace_id / room_mappings in the tenants table.
"""
import os
import logging
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

_ENV_TENANT: str = os.getenv("TENANT_ID", "default")


class TenantResolver:

    @classmethod
    def resolve(cls, payload: dict = None) -> str:
        if _ENV_TENANT != "default":
            return _ENV_TENANT

        if payload:
            workspace_id = payload.get("workspace_id") or payload.get("workspace")
            if workspace_id:
                tenant = cls._by_workspace(workspace_id)
                if tenant:
                    return tenant

            room_id = payload.get("room_id", "")
            if room_id:
                tenant = cls._by_room(room_id)
                if tenant:
                    return tenant

        return "default"

    @classmethod
    def _by_workspace(cls, workspace_id: str) -> str | None:
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT tenant_id FROM tenants WHERE workspace_id=%s AND status='active' LIMIT 1",
                    (workspace_id,)
                )
                row = cur.fetchone()
                return row["tenant_id"] if row else None
        except Exception as e:
            logger.warning(f"TenantResolver workspace lookup failed: {e}")
            return None

    @classmethod
    def _by_room(cls, room_id: str) -> str | None:
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT tenant_id FROM tenants WHERE room_mappings ? %s AND status='active' LIMIT 1",
                    (room_id,)
                )
                row = cur.fetchone()
                return row["tenant_id"] if row else None
        except Exception as e:
            logger.warning(f"TenantResolver room lookup failed: {e}")
            return None

    @classmethod
    def register_room(cls, tenant_id: str, room_id: str, room_name: str) -> None:
        """Associate a Switch room ID with a tenant (called during agent setup)."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    UPDATE tenants
                    SET room_mappings = room_mappings || jsonb_build_object(%s, %s)
                    WHERE tenant_id = %s
                    """,
                    (room_id, room_name, tenant_id)
                )
        except Exception as e:
            logger.error(f"TenantResolver.register_room failed: {e}")
