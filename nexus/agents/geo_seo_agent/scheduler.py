import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from .analysis import run_analysis_cycle

logger = logging.getLogger(__name__)


def start_geo_scheduler(client):
    hours = int(os.getenv("GEO_SEO_INTERVAL_HOURS", "24"))
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: run_analysis_cycle(client),
        "interval",
        hours=hours,
        id="geo_seo_cycle"
    )
    scheduler.start()
    logger.info(f"GeoSEO scheduler running every {hours}h")
    return scheduler
