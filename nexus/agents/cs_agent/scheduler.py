"""
CSAgent scheduler — daily digest, weekly report, at-risk sweep, proactive checks.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from .escalation import run_health_escalations
from app.Services.DatabaseService import db_cursor
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check

logger = logging.getLogger(__name__)


def _health_decay_check(client):
    """Gradually reduce health score for disengaged customers."""
    tenant_id = client.tenant_id
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                UPDATE customers
                SET health_score = GREATEST(health_score - 5, 10)
                WHERE tenant_id = %s
                  AND status = 'active'
                  AND id NOT IN (
                      SELECT DISTINCT customer_id FROM customer_events
                      WHERE tenant_id = %s
                        AND created_at > NOW() - INTERVAL '14 days'
                  )
                  AND health_score > 10
                """,
                (tenant_id, tenant_id)
            )
            decayed = cur.rowcount
        if decayed:
            logger.info(f"Health decay: {decayed} customers reduced (tenant={tenant_id})")
    except Exception as e:
        logger.error(f"Health decay check failed: {e}")


def start_cs_scheduler(client):
    scheduler = BackgroundScheduler()

    # Daily 9 AM health digest
    scheduler.add_job(
        lambda: post_morning_digest(client, "CSAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="cs_morning_digest"
    )

    # Weekly Monday report
    scheduler.add_job(
        lambda: _weekly_report(client),
        "cron",
        day_of_week="mon",
        hour=9,
        minute=30,
        id="cs_weekly_report"
    )

    # Daily at-risk sweep (run health escalations every 6h)
    scheduler.add_job(
        lambda: run_health_escalations(client, client.tenant_id),
        "interval",
        hours=6,
        id="cs_health_escalations"
    )

    # Proactive intelligence every 6h
    scheduler.add_job(
        lambda: run_proactive_check(client, "CSAgent", client.tenant_id),
        "interval",
        hours=6,
        id="cs_proactive"
    )

    scheduler.add_job(
        lambda: client.record_heartbeat(),
        "interval",
        minutes=5,
        id="cs_heartbeat"
    )

    scheduler.add_job(
        lambda: _health_decay_check(client),
        "cron",
        hour=2,
        minute=0,
        id="cs_health_decay"
    )

    scheduler.start()
    logger.info("CSAgent scheduler started")
    return scheduler


def _weekly_report(client):
    from agents.cs_agent.handlers import _cmd_weekly_report
    _cmd_weekly_report(client, client.tenant_id)
