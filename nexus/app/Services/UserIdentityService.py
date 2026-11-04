"""
UserIdentityService — maps Switch sender usernames to tenant users with roles.

Roles: admin > manager > member > viewer
Auto-creates 'member' on first interaction (configurable per tenant).
"""
import logging
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

ROLE_HIERARCHY = {"admin": 4, "manager": 3, "member": 2, "viewer": 1}


class UserIdentityService:

    @classmethod
    def get_or_create(cls, tenant_id: str, username: str) -> dict:
        """Get user record, creating a 'member' if first seen."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT username, role FROM tenant_users WHERE tenant_id=%s AND username=%s",
                    (tenant_id, username)
                )
                user = cur.fetchone()
                if not user:
                    cur.execute(
                        "INSERT INTO tenant_users (tenant_id, username, role) VALUES (%s,%s,'member') "
                        "ON CONFLICT (tenant_id, username) DO UPDATE SET last_seen=NOW() "
                        "RETURNING username, role",
                        (tenant_id, username)
                    )
                    user = cur.fetchone()
                else:
                    cur.execute(
                        "UPDATE tenant_users SET last_seen=NOW() WHERE tenant_id=%s AND username=%s",
                        (tenant_id, username)
                    )
            return dict(user) if user else {"username": username, "role": "member"}
        except Exception as e:
            logger.warning(f"UserIdentityService.get_or_create failed: {e}")
            return {"username": username, "role": "member"}

    @classmethod
    def get_role(cls, tenant_id: str, username: str) -> str:
        user = cls.get_or_create(tenant_id, username)
        return user.get("role", "member")

    @classmethod
    def has_role(cls, tenant_id: str, username: str, required_role: str) -> bool:
        """True if user's role >= required_role in the hierarchy."""
        user_level     = ROLE_HIERARCHY.get(cls.get_role(tenant_id, username), 0)
        required_level = ROLE_HIERARCHY.get(required_role, 0)
        return user_level >= required_level

    @classmethod
    def set_role(cls, tenant_id: str, username: str, role: str) -> bool:
        if role not in ROLE_HIERARCHY:
            return False
        try:
            with db_cursor() as cur:
                cur.execute(
                    "INSERT INTO tenant_users (tenant_id, username, role) VALUES (%s,%s,%s) "
                    "ON CONFLICT (tenant_id, username) DO UPDATE SET role=%s",
                    (tenant_id, username, role, role)
                )
            return True
        except Exception as e:
            logger.error(f"UserIdentityService.set_role failed: {e}")
            return False

    @classmethod
    def deny(cls, client, action: str, required_role: str = "manager") -> None:
        client.post_message(
            f"❌ You need *{required_role}* or higher to {action}.\n"
            f"Ask your workspace admin to update your role."
        )
