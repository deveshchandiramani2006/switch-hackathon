"""
Proactive Intelligence - unprompted signals across all agents.
Called by each agent's scheduler every 6 hours (configurable).
"""
import os
import logging
from datetime import datetime
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

PROACTIVE_INTERVAL_HOURS = int(os.getenv("PROACTIVE_INTERVAL_HOURS", "6"))


def run_proactive_check(client, agent_name: str, tenant_id: str = "default"):
    """Agent-specific proactive intelligence."""
    try:
        if agent_name == "SalesAgent":
            _sales_proactive(client, tenant_id)
        elif agent_name == "SupportAgent":
            _support_proactive(client, tenant_id)
        elif agent_name == "GeoSEOAgent":
            _geoseo_proactive(client, tenant_id)
        elif agent_name == "BlogAgent":
            _blog_proactive(client, tenant_id)
        elif agent_name == "CSAgent":
            _cs_proactive(client, tenant_id)
        elif agent_name == "FinanceAgent":
            _finance_proactive(client, tenant_id)
    except Exception as e:
        logger.error(f"Proactive check failed for {agent_name}: {e}")


def _sales_proactive(client, tenant_id: str):
    silence_days = int(os.getenv("DEAL_SILENCE_ALERT_DAYS", "7"))

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, deal_value, last_touched_at
            FROM leads
            WHERE tenant_id=%s
              AND stage NOT IN ('Closed-Won', 'Closed-Lost')
              AND last_touched_at < NOW() - INTERVAL '%s days'
            ORDER BY deal_value DESC
            LIMIT 5
            """,
            (tenant_id, silence_days)
        )
        silent = cur.fetchall()

    if silent:
        lines = [f"*Proactive: {len(silent)} leads silent > {silence_days} days*"]
        for r in silent:
            days = (datetime.utcnow() - r["last_touched_at"]).days
            lines.append(f"- {r['name']} | {_fmt_v(r['deal_value'])} | {days}d silent")
        client.post_message("\n".join(lines))

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT notes, COUNT(*) AS cnt
            FROM leads
            WHERE tenant_id=%s AND stage='Closed-Lost'
              AND updated_at > NOW() - INTERVAL '7 days'
              AND notes IS NOT NULL
            GROUP BY notes HAVING COUNT(*) >= 3
            """,
            (tenant_id,)
        )
        loss_patterns = cur.fetchall()

    if loss_patterns:
        for p in loss_patterns:
            client.post_message(
                f"*Loss pattern detected:* {p['notes']} -- {p['cnt']} deals lost this week with same reason. "
                f"Want me to draft a win-back strategy?"
            )


def _support_proactive(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT description, COUNT(*) AS cnt
            FROM bugs
            WHERE tenant_id=%s AND status='open'
              AND created_at > NOW() - INTERVAL '24 hours'
            GROUP BY description HAVING COUNT(*) >= 3
            LIMIT 5
            """,
            (tenant_id,)
        )
        recurring = cur.fetchall()

    if recurring:
        for r in recurring:
            client.post_message(
                f"*Recurring error detected ({r['cnt']}x in 24h):* {r['description'][:120]}\n"
                f"This is a systematic issue - recommend root-cause investigation."
            )

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT customer, COUNT(*) AS recent_cnt
            FROM bugs
            WHERE tenant_id=%s AND customer IS NOT NULL
              AND created_at > NOW() - INTERVAL '7 days'
            GROUP BY customer
            HAVING COUNT(*) >= 3
            ORDER BY recent_cnt DESC
            LIMIT 3
            """,
            (tenant_id,)
        )
        spikes = cur.fetchall()

    if spikes:
        for s in spikes:
            client.post_message(
                f"*Customer bug spike:* {s['customer']} filed {s['recent_cnt']} bugs this week. "
                f"Consider proactive outreach - flag CSAgent."
            )


def _geoseo_proactive(client, tenant_id: str):
    rank_drop_threshold = int(os.getenv("RANK_DROP_THRESHOLD", "5"))
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT keyword, previous_rank, current_rank,
                   (current_rank - previous_rank) AS drop_positions
            FROM keyword_tracking
            WHERE tenant_id=%s
              AND previous_rank IS NOT NULL AND current_rank IS NOT NULL
              AND current_rank > previous_rank + %s
            ORDER BY drop_positions DESC
            LIMIT 5
            """,
            (tenant_id, rank_drop_threshold)
        )
        drops = cur.fetchall()

    if drops:
        lines = ["*Rank drops detected:*"]
        for r in drops:
            lines.append(f"- {r['keyword']}: #{r['previous_rank']} -> #{r['current_rank']} (-{r['drop_positions']})")
        lines.append("Consider refreshing content for these keywords.")
        client.post_message("\n".join(lines))

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT keyword, volume FROM keyword_tracking
            WHERE tenant_id=%s AND published_url IS NULL AND volume > 1000
            ORDER BY volume DESC LIMIT 3
            """,
            (tenant_id,)
        )
        gaps = cur.fetchall()

    if gaps:
        lines = ["*Content gaps (high volume, no post):*"]
        for g in gaps:
            lines.append(f"- {g['keyword']}: {g['volume']}/mo volume, no published post")
        client.post_message("\n".join(lines))


def _blog_proactive(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT keyword, title, published_at
            FROM content_queue
            WHERE tenant_id=%s AND status='published'
              AND published_at < NOW() - INTERVAL '80 days'
            ORDER BY published_at ASC
            LIMIT 3
            """,
            (tenant_id,)
        )
        stale_posts = cur.fetchall()

    if stale_posts:
        lines = ["*Posts approaching 90-day refresh window:*"]
        for p in stale_posts:
            days = (datetime.utcnow() - p["published_at"]).days
            lines.append(f"- {p['keyword']}: published {days}d ago - consider refreshing")
        client.post_message("\n".join(lines))

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, keyword, title, created_at
            FROM content_queue
            WHERE tenant_id=%s AND status='draft_ready'
              AND created_at < NOW() - INTERVAL '48 hours'
            ORDER BY created_at ASC
            LIMIT 5
            """,
            (tenant_id,)
        )
        stale_drafts = cur.fetchall()

    if stale_drafts:
        lines = [f"*{len(stale_drafts)} draft(s) awaiting approval > 48h:*"]
        for d in stale_drafts:
            lines.append(f"- #{d['id']} {d['keyword']} - reply `approve` or `reject`")
        client.post_message("\n".join(lines))


def _cs_proactive(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT c.name, c.health_score, c.assigned_csm
            FROM customers c
            WHERE c.tenant_id=%s AND c.health_score < 50 AND c.status='active'
            ORDER BY c.health_score ASC
            LIMIT 5
            """,
            (tenant_id,)
        )
        red_customers = cur.fetchall()

    if red_customers:
        lines = ["*At-risk customers (health RED):*"]
        for c in red_customers:
            csm = c["assigned_csm"] or "unassigned"
            lines.append(f"- {c['name']}: score {c['health_score']} | CSM: {csm}")
        client.post_message("\n".join(lines))

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, arr, renewal_date, health_score
            FROM customers
            WHERE tenant_id=%s AND health_score >= 80 AND status='active'
              AND renewal_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '45 days'
            ORDER BY arr DESC
            LIMIT 3
            """,
            (tenant_id,)
        )
        expansion = cur.fetchall()

    if expansion:
        lines = ["*Expansion opportunities (healthy + renewing soon):*"]
        for c in expansion:
            days = (c["renewal_date"] - datetime.utcnow().date()).days
            lines.append(f"- {c['name']}: ARR {_fmt_v(c['arr'])} | renews in {days}d | score {c['health_score']}")
        client.post_message("\n".join(lines))


def _finance_proactive(client, tenant_id: str):
    budget_warn_pct = int(os.getenv("BUDGET_WARN_PCT", "75"))

    with db_cursor() as cur:
        cur.execute(
            "SELECT name, allocated, spent, period FROM budgets WHERE tenant_id=%s AND allocated > 0",
            (tenant_id,)
        )
        budgets = cur.fetchall()

    warnings = []
    for b in budgets:
        pct = round(b["spent"] / b["allocated"] * 100) if b["allocated"] > 0 else 0
        if pct >= budget_warn_pct:
            warnings.append(f"- {b['name']}: {pct}% burned ({_fmt_v(b['spent'])} of {_fmt_v(b['allocated'])})")

    if warnings:
        client.post_message("*Budget alert - high burn rate:*\n" + "\n".join(warnings))

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT vendor, amount, due_date
            FROM invoices
            WHERE tenant_id=%s AND status='pending'
              AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '3 days'
            ORDER BY due_date ASC
            """,
            (tenant_id,)
        )
        due_soon = cur.fetchall()

    if due_soon:
        lines = ["*Invoices due in 3 days:*"]
        for inv in due_soon:
            lines.append(f"- {inv['vendor']}: {_fmt_v(inv['amount'])} due {inv['due_date']}")
        client.post_message("\n".join(lines))


def _fmt_v(v) -> str:
    try:
        v = int(v)
    except Exception:
        return str(v)
    if v >= 10000000:
        return f"Rs {v/10000000:.1f}Cr"
    if v >= 100000:
        return f"Rs {v/100000:.1f}L"
    if v >= 1000:
        return f"Rs {v/1000:.0f}K"
    return f"Rs {v}"
