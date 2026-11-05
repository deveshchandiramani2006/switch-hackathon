import logging
from datetime import datetime
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient(agent="sales")


def cmd_new_lead(client, text: str, sender: str, tenant_id: str):
    """Parse: 'new lead: Priya Sharma, CTO, Mumbai, fintech, 2L'"""
    parts = text.split(":", 1)
    if len(parts) < 2:
        client.post_message("Usage: `@SalesAgent new lead: Name, Role, City, Industry, Value`")
        return
    raw = parts[1].strip()
    segments = [s.strip() for s in raw.split(",")]
    name     = segments[0] if len(segments) > 0 else raw
    role     = segments[1] if len(segments) > 1 else ""
    city     = segments[2] if len(segments) > 2 else ""
    industry = segments[3] if len(segments) > 3 else ""
    deal_str = segments[4] if len(segments) > 4 else "0"

    deal_value = parse_deal_value(deal_str)

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO leads (tenant_id, name, role, city, industry, deal_value, rep_slack_user)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (tenant_id, name, role, city, industry, deal_value, f"@{sender}")
        )
        lead_id = cur.fetchone()["id"]

    from app.Services.BlockBuilder import lead_added
    client.post_blocks(
        lead_added(name, f"{role} @ {city}", format_value(deal_value)),
        fallback_text=f"Lead added: {name}"
    )


def cmd_new_lead_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard collects all fields."""
    from app.Services.ValidationService import validate_money
    deal_str = data.get("deal_value") or "0"
    deal_value, _ = validate_money(deal_str)

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO leads (tenant_id, name, role, city, industry, deal_value, rep_slack_user)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (tenant_id, data["name"], data["role"], data["city"],
             data["industry"], deal_value, f"@{sender}")
        )
        lead_id = cur.fetchone()["id"]

    from app.Services.BlockBuilder import lead_added
    client.post_blocks(
        lead_added(data["name"], f"{data['role']} @ {data['city']}", format_value(deal_value)),
        fallback_text=f"Lead added: {data['name']}"
    )


def cmd_pipeline(client, text: str, sender: str, tenant_id: str):
    geo_filter = None
    if ":" in text:
        geo_filter = text.split(":", 1)[1].strip()

    with db_cursor() as cur:
        if geo_filter:
            cur.execute(
                """
                SELECT name, stage, deal_value, city, last_touched_at, rep_slack_user
                FROM leads WHERE tenant_id = %s AND stage NOT IN ('Closed-Won','Closed-Lost')
                AND LOWER(city) = LOWER(%s)
                ORDER BY deal_value DESC
                """,
                (tenant_id, geo_filter)
            )
        else:
            cur.execute(
                """
                SELECT name, stage, deal_value, city, last_touched_at, rep_slack_user
                FROM leads WHERE tenant_id = %s ORDER BY deal_value DESC LIMIT 20
                """,
                (tenant_id,)
            )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No leads in pipeline.")
        return

    from app.Services.BlockBuilder import pipeline_row, _section
    header = "*Pipeline*" + (f": {geo_filter}" if geo_filter else "")
    blocks = [_section(header)]
    for r in rows:
        days = (datetime.now() - r["last_touched_at"]).days if r["last_touched_at"] else "?"
        label = f"{format_value(r['deal_value'])} | {r['city']} | touched {days}d ago"
        blocks += pipeline_row(r["name"], r["stage"], label)
    client.post_blocks(blocks, fallback_text="Pipeline")


def cmd_follow_up(client, text: str, sender: str, tenant_id: str):
    name = text.split(":", 1)[1].strip() if ":" in text else ""
    if not name:
        client.post_message("Usage: `@SalesAgent follow up: Lead Name`")
        return
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM leads WHERE tenant_id = %s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        lead = cur.fetchone()
    if not lead:
        client.post_message(f"Lead '{name}' not found.")
        return
    draft = llm.complete(
        f"Write a short, professional follow-up message for {lead['name']} "
        f"({lead['role']} at {lead['company'] or lead['city']}, {lead['industry']} industry). "
        f"They are in {lead['stage']} stage. Deal value: {format_value(lead['deal_value'])}. "
        f"Keep it under 4 sentences. Friendly but professional tone."
    )
    client.post_message(
        f"💬 *Follow-up for {lead['name']}*\n\n{draft}"
    )


def cmd_format(client, text: str, sender: str, tenant_id: str):
    tone = "professional"
    if " as: " in text.lower():
        idx = text.lower().find(" as: ")
        tone = text[idx + 5:].split()[0].strip()
        msg_part = text.split(":", 1)[1][:idx - text.find(":") - 1].strip() if ":" in text else text
    else:
        msg_part = text.split(":", 1)[1].strip() if ":" in text else text

    tone_map = {
        "executive": "concise, professional, bottom-line first, no filler",
        "friendly":  "warm, conversational, first-name basis",
        "technical": "precise, detail-oriented, terminology-rich",
        "formal":    "formal, full names, passive voice",
        "sales":     "value-focused, outcome-oriented, creates mild urgency"
    }
    tone_desc = tone_map.get(tone.lower(), "professional and clear")
    formatted = llm.complete(
        f"Reformat this message in a {tone_desc} tone. Output only the reformatted message:\n\n{msg_part}"
    )
    client.post_message(f"*Formatted ({tone}):*\n\n{formatted}")


def cmd_format_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard collects message and style."""
    tone_map = {
        "executive": "concise, professional, bottom-line first, no filler",
        "casual":    "warm, conversational, first-name basis",
        "technical": "precise, detail-oriented, terminology-rich",
        "formal":    "formal, full names, passive voice",
        "sales":     "value-focused, outcome-oriented, creates mild urgency",
    }
    tone = data.get("style", "executive").lower()
    tone_desc = tone_map.get(tone, "professional and clear")
    formatted = llm.complete(
        f"Reformat this message in a {tone_desc} tone. Output only the reformatted message:\n\n{data['message']}"
    )
    client.post_message(f"*Formatted ({tone}):*\n\n{formatted}")


def cmd_won(client, text: str, sender: str, tenant_id: str):
    name = text.split(":", 1)[1].strip() if ":" in text else ""
    with db_cursor() as cur:
        cur.execute(
            "UPDATE leads SET stage = 'Closed-Won', updated_at = NOW() "
            "WHERE tenant_id = %s AND LOWER(name) LIKE LOWER(%s) RETURNING name, deal_value",
            (tenant_id, f"%{name}%")
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"🏆 Deal won: *{row['name']}* · {format_value(row['deal_value'])}")
        # Cross-agent signals: notify CSAgent and FinanceAgent
        won_name   = row["name"].replace(" ", "_")
        won_amount = row["deal_value"]
        client.safe_signal(
            "CSAgent",
            f"DEAL_WON: customer={won_name} arr={won_amount} renewal_date="
        )
        client.safe_signal(
            "FinanceAgent",
            f"DEAL_WON: customer={won_name} amount={won_amount}"
        )
    else:
        client.post_message(f"Lead '{name}' not found.")


def cmd_lost(client, text: str, sender: str, tenant_id: str):
    parts = text.split("--")
    name = parts[0].split(":", 1)[1].strip() if ":" in parts[0] else ""
    reason = parts[1].split(":", 1)[1].strip() if len(parts) > 1 and ":" in parts[1] else "unspecified"
    with db_cursor() as cur:
        cur.execute(
            "UPDATE leads SET stage = 'Closed-Lost', notes = %s, updated_at = NOW() "
            "WHERE tenant_id = %s AND LOWER(name) LIKE LOWER(%s)",
            (f"Lost: {reason}", tenant_id, f"%{name}%")
        )
    client.post_message(f"❌ Deal lost: *{name}* · {reason}")


def cmd_set_commitment(client, text: str, sender: str, tenant_id: str):
    raw = text.split(":", 1)[1].strip() if ":" in text else text
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO commitments (tenant_id, lead_name, commitment_text, detected_by, source_message, party)
            VALUES (%s, %s, %s, 'manual', %s, 'customer') RETURNING id
            """,
            (tenant_id, None, raw, text)
        )
        cid = cur.fetchone()["id"]
    client.post_message(f"📌 Commitment tracked (#{cid}) · {raw}")


def cmd_set_commitment_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard collects all fields."""
    from app.Services.ValidationService import validate_date
    deadline, _ = validate_date(data["deadline"])
    text_summary = f"{data['person']} will {data['action']} by {deadline}"

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO commitments (tenant_id, lead_name, commitment_text, deadline, detected_by, source_message, party)
            VALUES (%s, %s, %s, %s, 'manual', %s, 'customer') RETURNING id
            """,
            (tenant_id, data["person"], text_summary, deadline, text_summary)
        )
        cid = cur.fetchone()["id"]
    client.post_message(f"📌 Commitment tracked (#{cid}) · {text_summary}")


def cmd_stale_leads(client, sender: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, stage, deal_value, last_touched_at
            FROM leads
            WHERE tenant_id = %s AND last_touched_at < NOW() - INTERVAL '7 days'
            ORDER BY deal_value DESC
            """,
            (tenant_id,)
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message("✅ No stale leads.")
        return
    lines = [f"*Stale leads ({len(rows)} · untouched 7+ days)*\n"]
    for r in rows:
        days = (datetime.now() - r["last_touched_at"]).days
        lines.append(f"🕰️ *{r['name']}* · {r['stage']} · {format_value(r['deal_value'])} · {days}d ago")
    client.post_message("\n".join(lines))


def cmd_lead_card(client, text: str, sender: str, tenant_id: str):
    name = text.split(":", 1)[1].strip() if ":" in text else ""
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM leads WHERE tenant_id = %s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        lead = cur.fetchone()
        commits = []
        if lead:
            cur.execute(
                "SELECT * FROM commitments WHERE tenant_id = %s AND LOWER(lead_name) LIKE LOWER(%s) "
                "ORDER BY created_at DESC LIMIT 3",
                (tenant_id, f"%{name}%")
            )
            commits = cur.fetchall()
    if not lead:
        client.post_message(f"Lead '{name}' not found.")
        return
    stage_emoji = {
        "Prospect": "🔵", "Qualified": "🟡", "Proposal": "🟠",
        "Negotiation": "🔸", "Closed-Won": "🏆", "Closed-Lost": "❌"
    }.get(lead["stage"], "⚫")
    lines = [
        f"{stage_emoji} *{lead['name']}* · {lead['role']} · {lead['city']}",
        f"_{lead['industry']}_ · {format_value(lead['deal_value'])} · stage: {lead['stage']}",
    ]
    if commits:
        lines.append("\n*Commitments:*")
        for c in commits:
            lines.append(f"📌 {c['commitment_text']} _{c['status']}_")
    client.post_message("\n".join(lines))


# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_deal_value(s: str) -> int:
    s = s.strip().replace("Rs", "").replace("INR", "").replace(",", "").upper()
    # Remove rupee sign if present (non-ASCII)
    s = s.replace("₹", "")
    if s.endswith("CR"):
        return int(float(s[:-2]) * 10000000)
    if s.endswith("L"):
        return int(float(s[:-1]) * 100000)
    if s.endswith("K"):
        return int(float(s[:-1]) * 1000)
    try:
        return int(float(s))
    except Exception:
        return 0


def format_value(v: int) -> str:
    if v >= 10000000:
        return f"Rs {v/10000000:.1f}Cr"
    if v >= 100000:
        return f"Rs {v/100000:.1f}L"
    if v >= 1000:
        return f"Rs {v/1000:.0f}K"
    return f"Rs {v}"
