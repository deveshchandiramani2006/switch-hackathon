"""
Enhanced multi-person approval workflow with edit requests, delegation, and expiry.
"""
import os
import logging
from datetime import datetime, timedelta
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_HOURS = int(os.getenv("APPROVAL_TIMEOUT_HOURS", "48"))


class ApprovalRequest:
    def __init__(
        self,
        agent: str,
        item_id: str,
        item_type: str,
        required_approvers: list,
        tenant_id: str = "default",
        timeout_hours: int = None
    ):
        self.agent = agent
        self.item_id = str(item_id)
        self.item_type = item_type
        self.required_approvers = required_approvers
        self.tenant_id = tenant_id
        self.timeout_hours = timeout_hours or DEFAULT_TIMEOUT_HOURS
        self.db_id = self._store()

    def _store(self) -> int:
        timeout_at = datetime.utcnow() + timedelta(hours=self.timeout_hours)
        with db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO approval_requests
                    (tenant_id, agent, item_id, item_type,
                     required_approvers, approvals_received, status, timeout_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                RETURNING id
                """,
                (
                    self.tenant_id, self.agent, self.item_id, self.item_type,
                    self.required_approvers, [],
                    timeout_at
                )
            )
            return cur.fetchone()["id"]

    def record_approval(self, approver: str, with_edits: str = None) -> dict:
        """
        Record one approval.
        Returns {"complete": bool, "pending": list, "edit_requested": str|None}
        """
        with db_cursor() as cur:
            cur.execute(
                "SELECT required_approvers, approvals_received, status FROM approval_requests WHERE id=%s",
                (self.db_id,)
            )
            row = cur.fetchone()
            if not row or row["status"] != "pending":
                return {"complete": False, "pending": [], "edit_requested": None}

            approvals = list(row["approvals_received"] or [])
            if approver not in approvals:
                approvals.append(approver)

            required = row["required_approvers"] or []
            pending  = [r for r in required if r not in approvals]
            complete = len(pending) == 0

            if with_edits:
                cur.execute(
                    "UPDATE approval_requests SET approvals_received=%s, edit_instruction=%s WHERE id=%s",
                    (approvals, with_edits, self.db_id)
                )
            elif complete:
                cur.execute(
                    "UPDATE approval_requests SET approvals_received=%s, status='approved' WHERE id=%s",
                    (approvals, self.db_id)
                )
            else:
                cur.execute(
                    "UPDATE approval_requests SET approvals_received=%s WHERE id=%s",
                    (approvals, self.db_id)
                )

        return {
            "complete": complete,
            "pending": pending,
            "edit_requested": with_edits
        }

    def reject(self, approver: str, reason: str):
        with db_cursor() as cur:
            cur.execute(
                "UPDATE approval_requests SET status='rejected', edit_instruction=%s WHERE id=%s",
                (f"Rejected by {approver}: {reason}", self.db_id)
            )

    def is_expired(self) -> bool:
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT timeout_at, status FROM approval_requests WHERE id=%s",
                    (self.db_id,)
                )
                row = cur.fetchone()
            if not row or row["status"] != "pending":
                return False
            return datetime.utcnow() > row["timeout_at"]
        except Exception:
            return False

    @staticmethod
    def get_pending(agent: str, tenant_id: str = "default") -> list:
        """Return all pending approval requests for an agent."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    SELECT id, item_id, item_type, required_approvers,
                           approvals_received, timeout_at, created_at
                    FROM approval_requests
                    WHERE agent=%s AND tenant_id=%s AND status='pending'
                    ORDER BY created_at ASC
                    """,
                    (agent, tenant_id)
                )
                return cur.fetchall()
        except Exception as e:
            logger.warning(f"ApprovalRequest.get_pending failed: {e}")
            return []

    @staticmethod
    def load(db_id: int) -> "ApprovalRequest | None":
        """Load an existing approval request from DB (without re-inserting)."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    SELECT agent, item_id, item_type, required_approvers,
                           approvals_received, status, tenant_id, timeout_at
                    FROM approval_requests WHERE id=%s
                    """,
                    (db_id,)
                )
                row = cur.fetchone()
            if not row:
                return None
            obj = object.__new__(ApprovalRequest)
            obj.agent = row["agent"]
            obj.item_id = row["item_id"]
            obj.item_type = row["item_type"]
            obj.required_approvers = row["required_approvers"] or []
            obj.tenant_id = row["tenant_id"]
            obj.timeout_hours = DEFAULT_TIMEOUT_HOURS
            obj.db_id = db_id
            return obj
        except Exception as e:
            logger.warning(f"ApprovalRequest.load failed: {e}")
            return None


def check_approval_expirations(client, agent_name: str, tenant_id: str = "default"):
    """
    Called by scheduler every hour.
    For expired pending approvals: escalate by posting a reminder.
    """
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, item_id, item_type, required_approvers, approvals_received
                FROM approval_requests
                WHERE agent=%s AND tenant_id=%s AND status='pending' AND timeout_at < NOW()
                """,
                (agent_name, tenant_id)
            )
            expired = cur.fetchall()

        for req in expired:
            received   = req["approvals_received"] or []
            required   = req["required_approvers"] or []
            pending_ap = [r for r in required if r not in received]
            msg = (
                f"*Approval timed out* - {req['item_type']} #{req['item_id']}\n"
                f"Still waiting on: {', '.join(pending_ap) if pending_ap else 'all approvers'}\n"
                f"Action needed - re-queuing for review."
            )
            client.post_message(msg)

            with db_cursor() as cur:
                cur.execute(
                    "UPDATE approval_requests SET status='expired' WHERE id=%s",
                    (req["id"],)
                )

    except Exception as e:
        logger.error(f"check_approval_expirations failed: {e}")
