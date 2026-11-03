"""
Customer health score calculator.
Score = NPS(30%) + support_volume(25%) + renewal_proximity(20%) + engagement(25%)
"""
import logging
from datetime import datetime, timedelta
from shared.db import db_cursor

logger = logging.getLogger(__name__)


def calculate_health(customer_id: int, tenant_id: str = "default") -> dict:
    """
    Calculate health score for a customer.
    Returns: {"score": int, "level": "GREEN"|"YELLOW"|"RED", "signals": list}
    """
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM customers WHERE id=%s AND tenant_id=%s",
            (customer_id, tenant_id)
        )
        customer = cur.fetchone()

    if not customer:
        return {"score": 0, "level": "RED", "signals": ["Customer not found"]}

    signals = []
    score   = 0

    # ── NPS (30 points) ──────────────────────────────────────────────────────
    nps = customer.get("nps")
    if nps is not None:
        if nps >= 9:
            nps_score = 30
            signals.append(f"NPS {nps} — promoter")
        elif nps >= 7:
            nps_score = 20
            signals.append(f"NPS {nps} — passive")
        else:
            nps_score = 5
            signals.append(f"NPS {nps} — detractor")
    else:
        nps_score = 15  # neutral if no data
        signals.append("No NPS data")
    score += nps_score

    # ── Support volume (25 points) ───────────────────────────────────────────
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt, COUNT(CASE WHEN severity IN ('P0','P1') THEN 1 END) AS critical
            FROM bugs
            WHERE tenant_id=%s AND customer=%s AND status='open'
            """,
            (tenant_id, customer["name"])
        )
        bug_data = cur.fetchone()

    open_tickets = bug_data["cnt"] if bug_data else 0
    critical     = bug_data["critical"] if bug_data else 0

    if open_tickets == 0:
        support_score = 25
        signals.append("No open support tickets")
    elif open_tickets <= 2 and critical == 0:
        support_score = 18
        signals.append(f"{open_tickets} open tickets (low severity)")
    elif critical > 0:
        support_score = 5
        signals.append(f"{critical} critical (P0/P1) open tickets")
    else:
        support_score = 10
        signals.append(f"{open_tickets} open tickets")
    score += support_score

    # ── Renewal proximity (20 points) ────────────────────────────────────────
    renewal_date = customer.get("renewal_date")
    if renewal_date:
        days_to_renewal = (renewal_date - datetime.utcnow().date()).days
        if days_to_renewal > 90:
            renewal_score = 20
            signals.append(f"Renewal in {days_to_renewal}d — plenty of time")
        elif days_to_renewal > 30:
            renewal_score = 15
            signals.append(f"Renewal in {days_to_renewal}d — approaching")
        elif days_to_renewal > 0:
            renewal_score = 8
            signals.append(f"Renewal in {days_to_renewal}d — URGENT")
        else:
            renewal_score = 2
            signals.append(f"Renewal OVERDUE by {abs(days_to_renewal)}d")
    else:
        renewal_score = 10  # no renewal date = neutral
        signals.append("No renewal date set")
    score += renewal_score

    # ── Engagement (25 points) ───────────────────────────────────────────────
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM customer_events
            WHERE tenant_id=%s AND customer_id=%s
              AND created_at > NOW() - INTERVAL '30 days'
            """,
            (tenant_id, customer_id)
        )
        event_count = cur.fetchone()["cnt"]

    if event_count >= 5:
        eng_score = 25
        signals.append(f"High engagement: {event_count} events in 30 days")
    elif event_count >= 2:
        eng_score = 15
        signals.append(f"Moderate engagement: {event_count} events in 30 days")
    elif event_count == 1:
        eng_score = 8
        signals.append("Low engagement: 1 event in 30 days")
    else:
        eng_score = 2
        signals.append("No engagement in 30 days")
    score += eng_score

    # ── Determine level ───────────────────────────────────────────────────────
    if score >= 70:
        level = "GREEN"
    elif score >= 50:
        level = "YELLOW"
    else:
        level = "RED"

    # Update health_score in DB
    try:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE customers SET health_score=%s WHERE id=%s AND tenant_id=%s",
                (score, customer_id, tenant_id)
            )
    except Exception as e:
        logger.warning(f"Failed to update health_score: {e}")

    return {"score": score, "level": level, "signals": signals}
