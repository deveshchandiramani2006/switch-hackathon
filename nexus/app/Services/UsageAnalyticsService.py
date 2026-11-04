"""
UsageAnalyticsService — logs every agent command execution.

Schema: usage_events(tenant_id, agent, command, username, success, error_msg, latency_ms)
Retention: 90-day rolling window (clean up via artisan cleanup-usage command).
"""
import time
import logging
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)


class UsageAnalyticsService:

    @classmethod
    def log(cls, tenant_id: str, agent: str, command: str,
            username: str = None, success: bool = True,
            error_msg: str = None, latency_ms: int = None) -> None:
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usage_events
                        (tenant_id, agent, command, username, success, error_msg, latency_ms)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, agent, command, username, success, error_msg, latency_ms)
                )
        except Exception as e:
            logger.warning(f"UsageAnalyticsService.log failed: {e}")

    @classmethod
    def get_summary(cls, tenant_id: str, days: int = 7) -> dict:
        """Return command usage summary for the last N days."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    SELECT agent, command, COUNT(*) AS calls,
                           SUM(CASE WHEN success THEN 1 ELSE 0 END) AS successes,
                           AVG(latency_ms) AS avg_latency_ms
                    FROM usage_events
                    WHERE tenant_id=%s
                      AND created_at > NOW() - INTERVAL '%s days'
                    GROUP BY agent, command
                    ORDER BY calls DESC
                    LIMIT 50
                    """,
                    (tenant_id, days)
                )
                rows = cur.fetchall()
                cur.execute(
                    "SELECT COUNT(DISTINCT username) AS active_users FROM usage_events "
                    "WHERE tenant_id=%s AND created_at > NOW() - INTERVAL '%s days'",
                    (tenant_id, days)
                )
                users_row = cur.fetchone()
            return {
                "period_days":   days,
                "commands":      [dict(r) for r in rows],
                "active_users":  users_row["active_users"] if users_row else 0,
                "total_calls":   sum(r["calls"] for r in rows),
            }
        except Exception as e:
            logger.error(f"UsageAnalyticsService.get_summary failed: {e}")
            return {"period_days": days, "commands": [], "active_users": 0, "total_calls": 0}

    @classmethod
    def cleanup_old_events(cls, retention_days: int = 90) -> int:
        """Delete events older than retention_days. Returns rows deleted."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "DELETE FROM usage_events WHERE created_at < NOW() - INTERVAL '%s days'",
                    (retention_days,)
                )
                return cur.rowcount
        except Exception as e:
            logger.error(f"UsageAnalyticsService.cleanup failed: {e}")
            return 0


def timed_command(tenant_id: str, agent: str, command: str, username: str):
    """Context manager to time and log a command execution."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        start = time.monotonic()
        success = True
        error_msg = None
        try:
            yield
        except Exception as e:
            success = False
            error_msg = str(e)[:255]
            raise
        finally:
            latency = int((time.monotonic() - start) * 1000)
            UsageAnalyticsService.log(
                tenant_id, agent, command, username,
                success=success, error_msg=error_msg, latency_ms=latency
            )

    return _ctx()
