"""
SupportAgent scheduler — digest + proactive checks.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from shared.digest import post_morning_digest
from shared.proactive import run_proactive_check

logger = logging.getLogger(__name__)

TENANT_ID = "default"


def start_support_scheduler(client):
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: post_morning_digest(client, "SupportAgent", TENANT_ID),
        "cron",
        hour=9,
        minute=0,
        id="support_morning_digest"
    )
    scheduler.add_job(
        lambda: run_proactive_check(client, "SupportAgent", TENANT_ID),
        "interval",
        hours=6,
        id="support_proactive"
    )

    scheduler.start()
    logger.info("SupportAgent scheduler started")
    return scheduler
