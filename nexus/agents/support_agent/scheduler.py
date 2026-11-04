"""
SupportAgent scheduler — digest, proactive checks, SLA breach alerts.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check

logger = logging.getLogger(__name__)


def _check_sla_breaches(client):
    """Alert on P0/P1 bugs that have exceeded their SLA without being closed."""
    tenant_id = client.tenant_id
    try:
        from app.Services.DatabaseService import db_cursor
        from app.Models.TenantConfig import TenantConfig
        cfg = TenantConfig.get(tenant_id)
        sla = cfg.get("escalation_chain", {}).get("support", {}).get("sla", {})
        p0_hours = sla.get("p0_hours", 2)
        p1_hours = sla.get("p1_hours", 8)

        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, severity, description, reported_by, created_at
                FROM bugs
                WHERE tenant_id = %s
                  AND status = 'open'
                  AND sla_breach_notified = FALSE
                  AND (
                      (severity = 'P0' AND created_at < NOW() - INTERVAL '1 hour' * %s)
                      OR
                      (severity = 'P1' AND created_at < NOW() - INTERVAL '1 hour' * %s)
                  )
                """,
                (tenant_id, p0_hours, p1_hours)
            )
            breached = cur.fetchall()

        for bug in breached:
            hours_open = (
                __import__("datetime").datetime.utcnow() - bug["created_at"].replace(tzinfo=None)
            ).total_seconds() / 3600
            sla_limit = p0_hours if bug["severity"] == "P0" else p1_hours
            client.post_message(
                f"*SLA BREACH* — Bug #{bug['id']} [{bug['severity']}]\n"
                f"{bug['description'][:100]}\n"
                f"Open for {hours_open:.1f}h (SLA: {sla_limit}h) | Reporter: {bug['reported_by']}"
            )
            with db_cursor() as cur:
                cur.execute(
                    "UPDATE bugs SET sla_breach_notified = TRUE WHERE id = %s",
                    (bug["id"],)
                )
        if breached:
            logger.info(f"SLA breach alerts sent for {len(breached)} bugs (tenant={tenant_id})")
    except Exception as e:
        logger.error(f"SLA breach check failed: {e}")


def start_support_scheduler(client):
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: post_morning_digest(client, "SupportAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="support_morning_digest"
    )
    scheduler.add_job(
        lambda: run_proactive_check(client, "SupportAgent", client.tenant_id),
        "interval",
        hours=6,
        id="support_proactive"
    )
    scheduler.add_job(
        lambda: _check_sla_breaches(client),
        "interval",
        minutes=30,
        id="support_sla_check"
    )
    scheduler.add_job(
        lambda: client.record_heartbeat(),
        "interval",
        minutes=5,
        id="support_heartbeat"
    )

    scheduler.start()
    logger.info("SupportAgent scheduler started")
    return scheduler
