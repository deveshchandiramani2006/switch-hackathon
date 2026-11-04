"""
BlogAgent scheduler — digest + proactive checks + approval expiration checks.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check
from app.Services.ApprovalsService import check_approval_expirations

logger = logging.getLogger(__name__)


def start_blog_scheduler(client):
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: post_morning_digest(client, "BlogAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="blog_morning_digest"
    )
    scheduler.add_job(
        lambda: run_proactive_check(client, "BlogAgent", client.tenant_id),
        "interval",
        hours=6,
        id="blog_proactive"
    )
    # Check approval expirations every hour
    scheduler.add_job(
        lambda: check_approval_expirations(client, "BlogAgent", client.tenant_id),
        "interval",
        hours=1,
        id="blog_approval_expirations"
    )

    scheduler.add_job(
        lambda: client.record_heartbeat(),
        "interval",
        minutes=5,
        id="blog_heartbeat"
    )

    scheduler.start()
    logger.info("BlogAgent scheduler started")
    return scheduler
