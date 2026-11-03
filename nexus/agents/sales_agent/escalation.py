import os
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from shared.db import db_cursor
from shared.llm import LLMClient
from shared.config import Config

logger = logging.getLogger(__name__)
llm = LLMClient(agent="sales")

LEVEL_TONES = {
    1: "Write a friendly, casual reminder to the sales rep. Use first name. Under 2 sentences.",
    2: "Write a direct message to a team lead. Professional. State the deal needs attention. 2-3 sentences.",
    3: "Write a concise message to a manager. Bottom-line first: deal name, value, days overdue.",
    4: "Write a 2-sentence CEO/founder escalation. State deal value and total time elapsed. No fluff.",
}


def check_and_escalate(client):
    chain = Config.get_escalation_chain("sales")
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

        client.post_message(f"{target} {msg}")

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
    scheduler.start()
    logger.info(f"Escalation scheduler running every {interval} min")
    return scheduler
