"""
BlogAgent scheduler — digest + proactive checks + approval expiration checks.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from shared.digest import post_morning_digest
from shared.proactive import run_proactive_check
from shared.approvals import check_approval_expirations

logger = logging.getLogger(__name__)

TENANT_ID = "default"


def start_blog_scheduler(client):
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: post_morning_digest(client, "BlogAgent", TENANT_ID),
        "cron",
        hour=9,
        minute=0,
        id="blog_morning_digest"
    )
    scheduler.add_job(
        lambda: run_proactive_check(client, "BlogAgent", TENANT_ID),
        "interval",
        hours=6,
        id="blog_proactive"
    )
    # Check approval expirations every hour
    scheduler.add_job(
        lambda: check_approval_expirations(client, "BlogAgent", TENANT_ID),
        "interval",
        hours=1,
        id="blog_approval_expirations"
    )

    scheduler.start()
    logger.info("BlogAgent scheduler started")
    return scheduler
