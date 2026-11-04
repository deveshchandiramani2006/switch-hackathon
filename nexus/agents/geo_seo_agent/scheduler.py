import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from .analysis import run_analysis_cycle
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check

logger = logging.getLogger(__name__)


def start_geo_scheduler(client):
    hours = int(os.getenv("GEO_SEO_INTERVAL_HOURS", "24"))
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: run_analysis_cycle(client, client.tenant_id),
        "interval",
        hours=hours,
        id="geo_seo_cycle"
    )
    # Daily 9 AM digest
    scheduler.add_job(
        lambda: post_morning_digest(client, "GeoSEOAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="geoseo_morning_digest"
    )
    # Proactive checks every 6h
    scheduler.add_job(
        lambda: run_proactive_check(client, "GeoSEOAgent", client.tenant_id),
        "interval",
        hours=6,
        id="geoseo_proactive"
    )

    scheduler.start()
    logger.info(f"GeoSEO scheduler running every {hours}h")
    return scheduler
