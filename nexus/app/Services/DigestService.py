"""
Daily 9 AM Digest — each agent posts a morning summary to its room.
Called by each agent's scheduler at 9 AM.
"""
import logging
from datetime import datetime
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)


def post_morning_digest(client, agent_name: str, tenant_id: str = "default"):
    """Post agent-specific morning digest to the agent's room."""
    try:
        if agent_name == "SalesAgent":
            _sales_digest(client, tenant_id)
        elif agent_name == "SupportAgent":
            _support_digest(client, tenant_id)
        elif agent_name == "GeoSEOAgent":
            _geoseo_digest(client, tenant_id)
        elif agent_name == "BlogAgent":
            _blog_digest(client, tenant_id)
        elif agent_name == "InfraAgent":
            _infra_digest(client, tenant_id)
        elif agent_name == "CSAgent":
            _cs_digest(client, tenant_id)
        elif agent_name == "FinanceAgent":
            _finance_digest(client, tenant_id)
    except Exception as e:
        logger.error(f"Morning digest failed for {agent_name}: {e}")


def _sales_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM leads WHERE tenant_id=%s AND stage NOT IN ('Closed-Won','Closed-Lost')",
            (tenant_id,)
        )
        total_leads = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COALESCE(SUM(deal_value),0) AS total FROM leads WHERE tenant_id=%s AND stage NOT IN ('Closed-Won','Closed-Lost')",
            (tenant_id,)
        )
        pipeline = cur.fetchone()["total"]

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM leads WHERE tenant_id=%s AND last_touched_at < NOW() - INTERVAL '7 days' AND stage NOT IN ('Closed-Won','Closed-Lost')",
            (tenant_id,)
        )
        stale = cur.fetchone()["cnt"]

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM commitments WHERE tenant_id=%s AND status='pending' AND deadline::date = CURRENT_DATE",
            (tenant_id,)
        )
        due_today = cur.fetchone()["cnt"]

    pipeline_str = _format_value(pipeline)
    stale_flag   = f" | {stale} stale" if stale > 0 else ""
    due_flag     = f" | {due_today} commitments due today" if due_today > 0 else ""
    client.post_message(
        f"*SalesAgent Morning Digest*\n"
        f"{total_leads} leads | {pipeline_str} pipeline{stale_flag}{due_flag}"
    )


def _support_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM bugs WHERE tenant_id=%s AND status='open'",
            (tenant_id,)
        )
        open_bugs = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT severity, COUNT(*) AS cnt FROM bugs WHERE tenant_id=%s AND status='open' GROUP BY severity",
            (tenant_id,)
        )
        by_sev = {r["severity"]: r["cnt"] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))/3600) AS avg_h
            FROM bugs WHERE tenant_id=%s AND resolved_at IS NOT NULL
              AND created_at > NOW() - INTERVAL '7 days'
            """,
            (tenant_id,)
        )
        avg_row = cur.fetchone()
        avg_h = round(avg_row["avg_h"], 1) if avg_row and avg_row["avg_h"] else "N/A"

    p0 = by_sev.get("P0", 0)
    p1 = by_sev.get("P1", 0)
    client.post_message(
        f"*SupportAgent Morning Digest*\n"
        f"{open_bugs} open bugs | P0: {p0} | P1: {p1} | avg resolution: {avg_h}h"
    )


def _geoseo_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM content_queue WHERE tenant_id=%s AND status='pending' AND created_at > NOW() - INTERVAL '1 day'",
            (tenant_id,)
        )
        new_briefs = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM content_queue WHERE tenant_id=%s AND status='draft_ready'",
            (tenant_id,)
        )
        awaiting = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT keyword, current_rank FROM keyword_tracking WHERE tenant_id=%s ORDER BY current_rank NULLS LAST LIMIT 1",
            (tenant_id,)
        )
        top_kw_row = cur.fetchone()

    top_kw = f" | top keyword: #{top_kw_row['current_rank']} {top_kw_row['keyword']}" if top_kw_row else ""
    client.post_message(
        f"*GeoSEOAgent Morning Digest*\n"
        f"Last night: {new_briefs} briefs queued | {awaiting} drafts waiting approval{top_kw}"
    )


def _blog_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM content_queue WHERE tenant_id=%s AND status='draft_ready'",
            (tenant_id,)
        )
        drafts = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM content_queue WHERE tenant_id=%s AND status='published' AND published_at > NOW() - INTERVAL '7 days'",
            (tenant_id,)
        )
        published_wk = cur.fetchone()["cnt"]

    client.post_message(
        f"*BlogAgent Morning Digest*\n"
        f"{drafts} drafts awaiting approval | {published_wk} published this week"
    )


def _infra_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM monitored_services WHERE tenant_id=%s",
            (tenant_id,)
        )
        total_svcs = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM monitored_services WHERE tenant_id=%s AND status='healthy'",
            (tenant_id,)
        )
        healthy = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM monitored_services WHERE tenant_id=%s AND status='down'",
            (tenant_id,)
        )
        down = cur.fetchone()["cnt"]

    down_flag = f" | {down} DOWN" if down > 0 else ""
    client.post_message(
        f"*InfraAgent Morning Digest*\n"
        f"{healthy}/{total_svcs} services healthy{down_flag}"
    )


def _cs_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND status='active'",
            (tenant_id,)
        )
        total = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND health_score < 50",
            (tenant_id,)
        )
        red = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND health_score BETWEEN 50 AND 69",
            (tenant_id,)
        )
        yellow = cur.fetchone()["cnt"]
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM customers
            WHERE tenant_id=%s AND renewal_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
            """,
            (tenant_id,)
        )
        renewals_soon = cur.fetchone()["cnt"]

    at_risk_flag = f" | {red} RED, {yellow} YELLOW at-risk" if (red + yellow) > 0 else ""
    renewal_flag = f" | {renewals_soon} renewals in 30d" if renewals_soon > 0 else ""
    client.post_message(
        f"*CSAgent Morning Digest*\n"
        f"{total} active customers{at_risk_flag}{renewal_flag}"
    )


def _finance_digest(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id=%s AND status='pending'",
            (tenant_id,)
        )
        pending_inv = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id=%s AND status='pending' AND due_date < CURRENT_DATE",
            (tenant_id,)
        )
        overdue = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT SUM(allocated) AS alloc, SUM(spent) AS sp FROM budgets WHERE tenant_id=%s",
            (tenant_id,)
        )
        brow = cur.fetchone()
        alloc = brow["alloc"] or 0
        sp    = brow["sp"] or 0
        burn_pct = round(sp / alloc * 100) if alloc > 0 else 0

    overdue_flag = f" | {overdue} overdue" if overdue > 0 else ""
    client.post_message(
        f"*FinanceAgent Morning Digest*\n"
        f"{pending_inv} invoices pending{overdue_flag} | budget burn: {burn_pct}%"
    )


def _format_value(v: int) -> str:
    if v >= 10000000:
        return f"Rs {v/10000000:.1f}Cr"
    if v >= 100000:
        return f"Rs {v/100000:.1f}L"
    if v >= 1000:
        return f"Rs {v/1000:.0f}K"
    return f"Rs {v}"
