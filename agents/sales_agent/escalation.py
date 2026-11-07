import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient
from config.app import Config
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check

logger = logging.getLogger(__name__)
llm = LLMClient(agent="sales")

LEVEL_TONES = {
    1: "Write a friendly, casual reminder to the sales rep. Use first name. Under 2 sentences.",
    2: "Write a direct message to a team lead. Professional. State the deal needs attention. 2-3 sentences.",
    3: "Write a concise message to a manager. Bottom-line first: deal name, value, days overdue.",
    4: "Write a 2-sentence CEO/founder escalation. State deal value and total time elapsed. No fluff.",
}


def check_and_escalate(client):
    from app.Models.TenantConfig import TenantConfig
    chain = TenantConfig.get_escalation_chain(client.tenant_id, "sales")
    levels = chain.get("levels", [])
    if not levels:
        return

    now = datetime.utcnow()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, lead_name, commitment_text, deadline,
                   current_escalation_level, last_escalated_at
            FROM commitments
            WHERE status = 'pending'
              AND deadline IS NOT NULL
              AND deadline < %s
            """,
            (now,)
        )
        overdue = cur.fetchall()

    for c in overdue:
        current = c["current_escalation_level"]
        if current >= len(levels):
            continue

        wait_hours = levels[current].get("wait_hours", 24)
        if c["last_escalated_at"]:
            elapsed = (now - c["last_escalated_at"]).total_seconds() / 3600
            if elapsed < wait_hours:
                continue

        new_level = current + 1
        target    = levels[current]["slack_user"]
        tone      = LEVEL_TONES.get(new_level, LEVEL_TONES[3])
        days_over = (now - c["deadline"]).days if c["deadline"] else "unknown"

        msg = llm.complete(
            f"{tone}\n\n"
            f"Lead: {c['lead_name'] or 'Unknown'}\n"
            f"Commitment: {c['commitment_text']}\n"
            f"Deadline: {c['deadline']}\n"
            f"Days overdue: {days_over}\n"
            f"Target: {target}\n\n"
            f"Write only the Slack message text."
        )

        level_idx = current  # 0-based index into levels
        client.post_message(f"{target} {msg}")

        # Email for Level 3+
        if level_idx >= 2:
            email = levels[level_idx].get("email", "")
            if email:
                from app.Services.EmailService import EmailService
                deal_value = levels[level_idx].get("deal_value", "")
                EmailService.send_escalation(
                    to=email,
                    level=new_level,
                    lead_name=c["lead_name"] or "Unknown",
                    deal_value=deal_value or "N/A",
                    days_overdue=days_over if isinstance(days_over, int) else 0,
                    commitment_text=c["commitment_text"] or "",
                    llm_message=msg,
                )

        with db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO escalation_log (commitment_id, level, target_slack_user, message_sent)
                VALUES (%s, %s, %s, %s)
                """,
                (c["id"], new_level, target, msg)
            )
            cur.execute(
                """
                UPDATE commitments SET current_escalation_level=%s, last_escalated_at=%s
                WHERE id=%s
                """,
                (new_level, now, c["id"])
            )

        logger.info(f"Commitment #{c['id']} escalated to level {new_level} -> {target}")


def start_escalation_scheduler(client):
    interval = int(os.getenv("ESCALATION_CHECK_MINUTES", "60"))
    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: check_and_escalate(client),
        "interval",
        minutes=interval,
        id="escalation_check"
    )
    # Daily 9 AM digest
    scheduler.add_job(
        lambda: post_morning_digest(client, "SalesAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="sales_morning_digest"
    )
    # Proactive checks every 6h
    scheduler.add_job(
        lambda: run_proactive_check(client, "SalesAgent", client.tenant_id),
        "interval",
        hours=6,
        id="sales_proactive"
    )

    scheduler.add_job(
        lambda: client.record_heartbeat(),
        "interval",
        minutes=5,
        id="sales_heartbeat"
    )

    scheduler.start()
    logger.info(f"Escalation scheduler running every {interval} min")
    return scheduler
