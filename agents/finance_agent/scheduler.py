"""
FinanceAgent scheduler: daily digest, 3-day invoice reminders, weekly report.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.Services.DigestService import post_morning_digest
from app.Services.ProactiveService import run_proactive_check

logger = logging.getLogger(__name__)


def start_finance_scheduler(client):
    scheduler = BackgroundScheduler()

    # Daily 9 AM digest
    scheduler.add_job(
        lambda: post_morning_digest(client, "FinanceAgent", client.tenant_id),
        "cron",
        hour=9,
        minute=0,
        id="finance_morning_digest"
    )

    # 3-days-before-due invoice reminders (run daily at noon)
    scheduler.add_job(
        lambda: _invoice_reminders(client),
        "cron",
        hour=12,
        minute=0,
        id="finance_invoice_reminders"
    )

    scheduler.add_job(
        lambda: _overdue_signal(client),
        "cron",
        hour=9,
        minute=15,
        id="finance_overdue_signal"
    )

    # Weekly Monday report
    scheduler.add_job(
        lambda: _weekly_report(client),
        "cron",
        day_of_week="mon",
        hour=9,
        minute=30,
        id="finance_weekly_report"
    )

    # Proactive intelligence every 6h
    scheduler.add_job(
        lambda: run_proactive_check(client, "FinanceAgent", client.tenant_id),
        "interval",
        hours=6,
        id="finance_proactive"
    )

    scheduler.add_job(
        lambda: client.record_heartbeat(),
        "interval",
        minutes=5,
        id="finance_heartbeat"
    )

    scheduler.start()
    logger.info("FinanceAgent scheduler started")
    return scheduler


def _invoice_reminders(client):
    from app.Services.DatabaseService import db_cursor
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, vendor, amount, due_date
                FROM invoices
                WHERE tenant_id=%s AND status='pending'
                  AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'
                ORDER BY due_date ASC
                """,
                (client.tenant_id,)
            )
            due_soon = cur.fetchall()

        if due_soon:
            from agents.finance_agent.handlers import _fmt_v
            lines = [f"*Invoice reminders: due in 3 days*"]
            for inv in due_soon:
                lines.append(f"- invoice-{inv['id']:03d} | {inv['vendor']}: {_fmt_v(inv['amount'])} due {inv['due_date']}")
            client.post_message("\n".join(lines))
    except Exception as e:
        logger.error(f"Invoice reminders failed: {e}")


def _weekly_report(client):
    from agents.finance_agent.handlers import _cmd_weekly_report
    _cmd_weekly_report(client, client.tenant_id)


def _overdue_signal(client):
    """Fire INVOICE_OVERDUE signal to SalesAgent for invoices 30+ days past due."""
    from app.Services.DatabaseService import db_cursor
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT vendor, amount, due_date,
                       CURRENT_DATE - due_date AS days_overdue
                FROM invoices
                WHERE tenant_id=%s AND status='pending'
                  AND due_date < CURRENT_DATE - INTERVAL '30 days'
                ORDER BY days_overdue DESC
                """,
                (client.tenant_id,)
            )
            overdue = cur.fetchall()

        for inv in overdue:
            client.safe_signal(
                "SalesAgent",
                f"INVOICE_OVERDUE: customer={inv['vendor']} "
                f"amount={inv['amount']} days={inv['days_overdue']}"
            )
            logger.info(f"Fired INVOICE_OVERDUE signal for {inv['vendor']}")
    except Exception as e:
        logger.error(f"_overdue_signal failed: {e}")
