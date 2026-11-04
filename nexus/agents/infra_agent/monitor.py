import os
import logging
import requests
import yaml
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from app.Services.DatabaseService import db_cursor
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check

logger = logging.getLogger(__name__)


def check_services(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, url, consecutive_failures FROM monitored_services"
        )
        services = cur.fetchall()

    try:
        with open("company_config.yaml") as f:
            cfg = yaml.safe_load(f)
        threshold = cfg.get("escalation_chains", {}).get("infra", {}).get("failure_threshold", 2)
        chain     = cfg.get("escalation_chains", {}).get("infra", {}).get("levels", [])
    except Exception:
        threshold = 2
        chain = []

    for svc in services:
        try:
            resp = requests.get(svc["url"], timeout=10)
            ok     = resp.status_code < 500
            status = "healthy" if ok else "degraded"
            fails  = 0 if ok else svc["consecutive_failures"] + 1
            code   = resp.status_code
        except Exception:
            ok     = False
            status = "down"
            fails  = svc["consecutive_failures"] + 1
            code   = None

        with db_cursor() as cur:
            cur.execute(
                """
                UPDATE monitored_services
                SET status=%s, last_status_code=%s,
                    consecutive_failures=%s, last_checked_at=%s
                WHERE id=%s
                """,
                (status, code, fails, datetime.utcnow(), svc["id"])
            )

        if not ok and fails >= threshold:
            oncall = chain[0]["slack_user"] if chain else "@oncall"
            client.post_message(
                f"[ALERT] {oncall} -- *{svc['name']}* DOWN\n"
                f"{fails} consecutive failures\n"
                f"URL: {svc['url']}\n"
                f"Status: {f'HTTP {code}' if code else 'unreachable'}"
            )
            logger.warning(f"Service {svc['name']} DOWN after {fails} failures")


def start_monitor(client):
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: check_services(client),
        "interval",
        minutes=5,
        id="infra_monitor"
    )
    # Daily 9 AM digest
    scheduler.add_job(
        lambda: post_morning_digest(client, "InfraAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="infra_morning_digest"
    )
    # Proactive checks every 6h
    scheduler.add_job(
        lambda: run_proactive_check(client, "InfraAgent", client.tenant_id),
        "interval",
        hours=6,
        id="infra_proactive"
    )

    scheduler.start()
    logger.info("Infra monitor running every 5 min")
    return scheduler
