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
                SELECT id, name, stage, deal_value, city, last_touched_at, rep_slack_user
                FROM leads WHERE tenant_id = %s AND stage NOT IN ('Closed-Won','Closed-Lost')
                AND LOWER(city) = LOWER(%s)
                ORDER BY deal_value DESC
                """,
                (tenant_id, geo_filter)
            )
        else:
            cur.execute(
                """
                SELECT id, name, stage, deal_value, city, last_touched_at, rep_slack_user
                FROM leads WHERE tenant_id = %s ORDER BY deal_value DESC LIMIT 20
                """,
                (tenant_id,)
            )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No leads in pipeline.")
        return

    stage_emoji = {"Prospect": "🔵", "Qualified": "🟡", "Proposal": "🟠", "Negotiation": "🔸", "Closed-Won": "🏆", "Closed-Lost": "❌"}
    lines = []
    for r in rows:
        emoji = stage_emoji.get(r["stage"], "⚫")
        days = (datetime.now() - r["last_touched_at"]).days if r["last_touched_at"] else "?"
        lines.append(f"{emoji} *{r['name']}*  {r.get('role') or r.get('city', '')} · {format_value(r['deal_value'])} · {days}d ago")

    from app.Services.BlockBuilder import _header, _section, _context, _divider
    blocks = [_header(f"📋 Pipeline ({len(rows)} lead{'s' if len(rows) != 1 else ''})")]
    blocks.append(_divider())
    blocks += [_section("\n".join(lines)), _context("_follow up: Name  ·  won: Name  ·  lost: Name_")]
    client.post_blocks(blocks, fallback_text=f"Pipeline ({len(rows)} leads)")


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
    # Read recent room context from Switch to personalize the follow-up
    context_msgs = client.read_context(limit=5)
    context_str = ""
    if context_msgs:
        recent = [m.get("text", "") for m in context_msgs if m.get("text")][:3]
        if recent:
            context_str = "\n\nRecent room context:\n" + "\n".join(f"- {m}" for m in recent)

    draft = llm.complete(
        f"Write a short, professional follow-up message for {lead['name']} "
        f"({lead['role']} at {lead['company'] or lead['city']}, {lead['industry']} industry). "
        f"They are in {lead['stage']} stage. Deal value: {format_value(lead['deal_value'])}. "
        f"Keep it under 4 sentences. Friendly but professional tone."
        f"{context_str}"
    )
    from app.Services.BlockBuilder import _header, _quote_llm
    client.post_blocks([
        _header(f"💬 Follow-up for {lead['name']}"),
        _quote_llm(draft),
    ], fallback_text=f"Follow-up for {lead['name']}")


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


_DEAL_WON_TARGETS = {
    "CSAgent":      lambda name, amount: f"DEAL_WON: customer={name} arr={amount}",
    "FinanceAgent": lambda name, amount: f"DEAL_WON: customer={name} amount={amount}",
}


def _broadcast_deal_won(client, won_name: str, won_amount):
    """Dynamic fan-out via Switch: one list_agents() call, signal all subscribed agents."""
    agents = client.list_agents()
    online = {a["name"]: a["id"] for a in agents}
    for target_name, signal_fn in _DEAL_WON_TARGETS.items():
        if target_name in online:
            client.send_targeted_message(online[target_name], signal_fn(won_name, won_amount))
            logger.info("DEAL_WON fired to %s (online)", target_name)
        else:
            logger.info("DEAL_WON skipped %s (offline)", target_name)


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
        from app.Services.BlockBuilder import deal_won
        client.post_blocks(
            deal_won(row["name"], format_value(row["deal_value"])),
            fallback_text=f"Deal won: {row['name']} · {format_value(row['deal_value'])}"
        )
        _broadcast_deal_won(client, row["name"].replace(" ", "_"), row["deal_value"])
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
    from app.Services.BlockBuilder import deal_lost
    client.post_blocks(deal_lost(name, reason), fallback_text=f"Deal lost: {name}")


def cmd_lost_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ModalService after modal submission."""
    name   = data["name"]
    reason = data.get("reason", "unspecified")
    with db_cursor() as cur:
        cur.execute(
            "UPDATE leads SET stage='Closed-Lost', notes=%s, updated_at=NOW() "
            "WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s)",
            (f"Lost: {reason}", tenant_id, f"%{name}%")
        )
    from app.Services.BlockBuilder import deal_lost
    client.post_blocks(deal_lost(name, reason), fallback_text=f"Deal lost: {name}")


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
    from app.Services.BlockBuilder import commitment_tracked
    client.post_blocks(commitment_tracked(cid, raw), fallback_text=f"Commitment #{cid} tracked")


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
    from app.Services.BlockBuilder import commitment_tracked
    client.post_blocks(commitment_tracked(cid, text_summary), fallback_text=f"Commitment #{cid} tracked")


def cmd_won_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ModalService after modal submission."""
    name = data.get("name", "").strip()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE leads SET stage = 'Closed-Won', updated_at = NOW() "
            "WHERE tenant_id = %s AND LOWER(name) LIKE LOWER(%s) RETURNING name, deal_value",
            (tenant_id, f"%{name}%")
        )
        row = cur.fetchone()
    if row:
        from app.Services.BlockBuilder import deal_won
        client.post_blocks(
            deal_won(row["name"], format_value(row["deal_value"])),
            fallback_text=f"Deal won: {row['name']} {format_value(row['deal_value'])}"
        )
        _broadcast_deal_won(client, row["name"].replace(" ", "_"), row["deal_value"])
    else:
        client.post_message(f"Lead '{name}' not found.")


def cmd_follow_up_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ModalService after modal submission."""
    name = data.get("name", "").strip()
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM leads WHERE tenant_id = %s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        lead = cur.fetchone()
    if not lead:
        client.post_message(f"Lead '{name}' not found.")
        return
    # Read recent room context from Switch to personalize the follow-up
    context_msgs = client.read_context(limit=5)
    context_str = ""
    if context_msgs:
        recent = [m.get("text", "") for m in context_msgs if m.get("text")][:3]
        if recent:
            context_str = "\n\nRecent room context:\n" + "\n".join(f"- {m}" for m in recent)

    draft = llm.complete(
        f"Write a short, professional follow-up message for {lead['name']} "
        f"({lead['role']} at {lead.get('company') or lead['city']}, {lead['industry']} industry). "
        f"They are in {lead['stage']} stage. Deal value: {format_value(lead['deal_value'])}. "
        f"Keep it under 4 sentences. Friendly but professional tone."
        f"{context_str}"
    )
    from app.Services.BlockBuilder import _header, _quote_llm
    client.post_blocks([
        _header(f"💬 Follow-up for {lead['name']}"),
        _quote_llm(draft),
    ], fallback_text=f"Follow-up for {lead['name']}")


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
    stage_emoji = {"Prospect": "🔵", "Qualified": "🟡", "Proposal": "🟠", "Negotiation": "🔸"}
    lines = []
    for r in rows:
        emoji = stage_emoji.get(r["stage"], "⚫")
        days = (datetime.now() - r["last_touched_at"]).days
        lines.append(f"{emoji} *{r['name']}*  {format_value(r['deal_value'])} · {r['stage']} · {days}d ago")

    from app.Services.BlockBuilder import _header, _section, _context, _divider
    blocks = [_header(f"🕰️ Stale Leads ({len(rows)} untouched 7+ days)")]
    blocks.append(_divider())
    blocks += [_section("\n".join(lines)), _context("_follow up: Name  ·  won: Name  ·  lost: Name_")]
    client.post_blocks(blocks, fallback_text=f"Stale leads ({len(rows)})")


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


def cmd_geo_outreach(client, text: str, sender: str, tenant_id: str):
    """Button handler: draft geo-targeted outreach for all active leads."""
    parts = {}
    for p in text.split(":", 1)[-1].strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v

    keyword = parts.get("keyword", "").replace("_", " ")
    geo     = parts.get("geo", "").replace("_", " ")

    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM leads WHERE tenant_id = %s AND LOWER(city) LIKE LOWER(%s) "
            "AND stage NOT IN ('Closed-Won','Closed-Lost') ORDER BY deal_value DESC LIMIT 5",
            (tenant_id, f"%{geo}%")
        )
        leads = cur.fetchall()
        if not leads:
            cur.execute(
                "SELECT * FROM leads WHERE tenant_id = %s "
                "AND stage NOT IN ('Closed-Won','Closed-Lost') ORDER BY deal_value DESC LIMIT 5",
                (tenant_id,)
            )
            leads = cur.fetchall()

    if not leads:
        client.post_message("No active leads to target for geo outreach.")
        return

    client.post_message(
        f"Drafting geo-targeted outreach for {len(leads)} lead(s) based on *{keyword}* trending in {geo}..."
    )

    from app.Services.BlockBuilder import _header, _quote_llm
    for lead in leads:
        draft = llm.complete(
            f"Write a short, personalized outreach message for {lead['name']} "
            f"({lead['role']} at {lead.get('company') or lead['city']}, {lead['industry']} industry, "
            f"{lead['stage']} stage). "
            f"Context: The search term '{keyword}' is trending in {geo} right now. "
            f"Reference this trend subtly to make the message timely. "
            f"Keep it under 4 sentences. Friendly but professional tone."
        )
        client.post_blocks([
            _header(f"💬 Geo Outreach: {lead['name']}"),
            _quote_llm(draft),
        ], fallback_text=f"Geo outreach for {lead['name']}")


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
