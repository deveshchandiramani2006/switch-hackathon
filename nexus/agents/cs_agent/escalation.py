"""
CS Agent escalation — RED health customers notified to CSM, then CS Lead after 48h.
"""
import logging
from datetime import datetime, timedelta
from shared.db import db_cursor

logger = logging.getLogger(__name__)


def run_health_escalations(client, tenant_id: str = "default"):
    """
    - When health turns RED: DM assigned CSM
    - After 48h no action: escalate to CS Lead
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.name, c.health_score, c.assigned_csm,
                   MAX(ce.created_at) AS last_event
            FROM customers c
            LEFT JOIN customer_events ce
                ON ce.customer_id = c.id AND ce.tenant_id = c.tenant_id
                AND ce.event_type = 'health_alert'
            WHERE c.tenant_id=%s AND c.health_score < 50 AND c.status='active'
            GROUP BY c.id, c.name, c.health_score, c.assigned_csm
            """,
            (tenant_id,)
        )
        red_customers = cur.fetchall()

    now = datetime.utcnow()
    for cust in red_customers:
        last_alert = cust["last_event"]
        csm = cust["assigned_csm"] or "@cs_team"

        if last_alert is None:
            # First alert — notify CSM
            msg = (
                f"*Health Alert* — {cust['name']} is at risk\n"
                f"Health score: {cust['health_score']} (RED)\n"
                f"{csm} please take action."
            )
            client.post_message(msg)
            with db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO customer_events (tenant_id, customer_id, event_type, notes)
                    VALUES (%s, %s, 'health_alert', %s)
                    """,
                    (tenant_id, cust["id"], f"Health alert sent to {csm}")
                )
            logger.info(f"Health alert sent for {cust['name']} -> {csm}")

        elif (now - last_alert).total_seconds() > 48 * 3600:
            # 48h no action — escalate to CS Lead
            cs_lead = "@cs_lead"
            msg = (
                f"*ESCALATION* — {cust['name']} still at risk after 48h\n"
                f"Health score: {cust['health_score']} (RED)\n"
                f"Original CSM {csm} has not resolved. Escalating to {cs_lead}."
            )
            client.post_message(msg)
            with db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO customer_events (tenant_id, customer_id, event_type, notes)
                    VALUES (%s, %s, 'health_escalation', %s)
                    """,
                    (tenant_id, cust["id"], f"Escalated to {cs_lead}")
                )
            logger.info(f"Health escalation for {cust['name']} -> {cs_lead}")
