"""
CSAgent message handler — routes commands and cross-agent signals.
Cross-agent in:
  - DEAL_WON from SalesAgent → auto-create customer
  - P1_BREACH from SupportAgent → flag at-risk
"""
import logging
from datetime import datetime, date
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient
from .health import calculate_health

logger = logging.getLogger(__name__)
llm = LLMClient(agent="cs")


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)
    room_id    = payload.get("room_id", client.room_id)
    tenant_id  = client.tenant_id

    if sender in ("CSAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return

    # Cross-agent signals (not @mentions)
    if text.startswith("DEAL_WON:"):
        _handle_deal_won(client, text)
        return
    if text.startswith("P1_BREACH:"):
        _handle_p1_breach(client, text)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if text.startswith("<@") else text
    for p in ["@CSAgent ", "@csagent "]:
        if clean.lower().startswith(p.lower()):
            clean = clean[len(p):]
            break

    from app.Services import ConversationService
    if ConversationService.resume(tenant_id, room_id, sender, "CSAgent", clean, client):
        return

    _route_command(client, clean, sender, tenant_id, room_id)


def _route_command(client, text: str, sender: str, tenant_id: str, room_id: str):
    t = text.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "CSAgent", _cmd_key, sender)

    if t == "add customer":
        from app.Services import ConversationService
        ConversationService.start(tenant_id, room_id, sender, "CSAgent", "add_customer", client)
    elif t.startswith("add customer:"):
        _cmd_add_customer(client, text, sender, tenant_id)
    elif t.startswith("health:"):
        _cmd_health(client, text.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("at-risk") or t.startswith("at risk"):
        _cmd_at_risk(client, tenant_id)
    elif t.startswith("renewals"):
        days = 30
        if ":" in t:
            try:
                days = int(t.split(":", 1)[1].strip())
            except ValueError:
                pass
        _cmd_renewals(client, days, tenant_id)
    elif t == "nps":
        from app.Services import ConversationService
        ConversationService.start(tenant_id, room_id, sender, "CSAgent", "log_nps", client)
    elif t.startswith("nps:"):
        _cmd_log_nps(client, text, sender, tenant_id)
    elif t.startswith("expansion:"):
        _cmd_expansion(client, text.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("qbr:"):
        _cmd_qbr(client, text.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("weekly report"):
        _cmd_weekly_report(client, tenant_id)
    elif t.startswith("patterns"):
        _cmd_patterns(client, tenant_id)
    elif t.startswith("memory"):
        _cmd_memory(client, tenant_id)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, text.split(":", 1)[1].strip(), tenant_id)
    else:
        from app.Services.BlockBuilder import _section
        client.post_blocks([
            _section("*CSAgent — customer success*\n"
                     "`add customer: Name, Rs500K, renewal: 2027-03-31`  `health: Name`  `at-risk`\n"
                     "`renewals` or `renewals: 60`  `nps: Name, score: 7, note: feedback`\n"
                     "`expansion: Name`  `qbr: Name`  `weekly report`")
        ], fallback_text="CSAgent commands")


# ── Commands ───────────────────────────────────────────────────────────────────

def _cmd_add_customer(client, text: str, sender: str, tenant_id: str):
    """Parse: 'add customer: Name, Rs500000, renewal: 2027-03-31'"""
    raw = text.split(":", 1)[1].strip()
    # Extract renewal date if present
    renewal_date = None
    if "renewal:" in raw.lower():
        idx = raw.lower().find("renewal:")
        renewal_str = raw[idx + 8:].strip().split(",")[0].strip()
        try:
            renewal_date = datetime.strptime(renewal_str, "%Y-%m-%d").date()
        except ValueError:
            renewal_date = None
        raw = raw[:idx].strip().rstrip(",")

    parts = [p.strip() for p in raw.split(",")]
    name  = parts[0] if parts else raw
    arr   = _parse_money(parts[1]) if len(parts) > 1 else 0

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO customers (tenant_id, name, arr, renewal_date, assigned_csm)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (tenant_id, name, arr, renewal_date, f"@{sender}")
        )
        cid = cur.fetchone()["id"]

    client.post_message(
        f"✅ *{name}* added — ARR: {_fmt_v(arr)} · renewal: {renewal_date or 'not set'}"
    )


def _cmd_health(client, name: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, arr, renewal_date, nps, assigned_csm, health_score "
            "FROM customers WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        cust = cur.fetchone()

    if not cust:
        client.post_message(f"Customer '{name}' not found.")
        return

    health = calculate_health(cust["id"], tenant_id)
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(health["level"], "⚫")
    renewal_str = str(cust["renewal_date"]) if cust["renewal_date"] else "not set"

    from app.Services.BlockBuilder import _section, _context
    signals = " · ".join(health["signals"]) if health["signals"] else "No signals"
    client.post_blocks([
        _section(f"{icon} *{cust['name']}* — Health {health['score']}/100"),
        _context(f"ARR: {_fmt_v(cust['arr'])}", f"NPS: {cust['nps'] or 'N/A'}", f"Renewal: {renewal_str}"),
        _section(f"_{signals}_"),
    ], fallback_text=f"{cust['name']} health: {health['score']}/100")


def _cmd_at_risk(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, health_score, arr, assigned_csm, renewal_date
            FROM customers
            WHERE tenant_id=%s AND health_score < 70 AND status='active'
            ORDER BY health_score ASC
            """,
            (tenant_id,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("🟢 All customers healthy — no at-risk accounts.")
        return

    lines = [f"*At-risk ({len(rows)})*\n"]
    for r in rows:
        emoji = "🔴" if r["health_score"] < 50 else "🟡"
        lines.append(
            f"{emoji} *{r['name']}* — score {r['health_score']} · {_fmt_v(r['arr'])}"
        )
    client.post_message("\n".join(lines))


def _cmd_renewals(client, days: int, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT name, arr, renewal_date, health_score, assigned_csm
            FROM customers
            WHERE tenant_id=%s AND status='active'
              AND renewal_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '%s days'
            ORDER BY renewal_date ASC
            """,
            (tenant_id, days)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message(f"No renewals in the next {days} days.")
        return

    lines = [f"*Renewals in {days} days ({len(rows)})*\n"]
    for r in rows:
        days_left = (r["renewal_date"] - date.today()).days
        emoji = "🟢" if r["health_score"] >= 70 else ("🟡" if r["health_score"] >= 50 else "🔴")
        lines.append(
            f"{emoji} *{r['name']}* — {_fmt_v(r['arr'])} · {days_left}d left"
        )
    client.post_message("\n".join(lines))


def _cmd_log_nps(client, text: str, sender: str, tenant_id: str):
    """Parse: 'nps: CustomerName, score: 7, note: feedback text'"""
    raw   = text.split(":", 1)[1].strip() if ":" in text else text
    parts = raw.split(",")
    name  = parts[0].strip()
    score = None
    note  = ""
    for p in parts[1:]:
        p = p.strip()
        if p.lower().startswith("score:"):
            try:
                score = int(p.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif p.lower().startswith("note:"):
            note = p.split(":", 1)[1].strip()

    if score is None:
        client.post_message("Usage: `@CSAgent nps: Name, score: 7, note: feedback`")
        return

    with db_cursor() as cur:
        cur.execute(
            "UPDATE customers SET nps=%s WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) RETURNING id, name",
            (score, tenant_id, f"%{name}%")
        )
        row = cur.fetchone()

    if not row:
        client.post_message(f"Customer '{name}' not found.")
        return

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO customer_events (tenant_id, customer_id, event_type, notes)
            VALUES (%s, %s, 'nps_logged', %s)
            """,
            (tenant_id, row["id"], f"NPS {score}: {note}")
        )

    label = "promoter" if score >= 9 else ("passive" if score >= 7 else "detractor")
    client.post_message(f"NPS logged for *{row['name']}*: {score}/10 ({label})\n_{note}_")


def _cmd_expansion(client, name: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, arr, health_score, nps FROM customers "
            "WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        cust = cur.fetchone()

    if not cust:
        client.post_message(f"Customer '{name}' not found.")
        return

    with db_cursor() as cur:
        cur.execute(
            "SELECT event_type, notes, created_at FROM customer_events "
            "WHERE tenant_id=%s AND customer_id=%s ORDER BY created_at DESC LIMIT 10",
            (tenant_id, cust["id"])
        )
        events = cur.fetchall()

    signals = []
    if cust["health_score"] >= 70:
        signals.append(f"Health score {cust['health_score']} — satisfied customer")
    if cust["nps"] and cust["nps"] >= 9:
        signals.append(f"NPS {cust['nps']} — promoter, likely to expand")
    if len(events) >= 5:
        signals.append(f"High engagement: {len(events)} recent events")

    prompt = (
        f"Customer: {cust['name']}\n"
        f"ARR: {_fmt_v(cust['arr'])}\n"
        f"Health score: {cust['health_score']}\n"
        f"NPS: {cust['nps']}\n"
        f"Recent events: {', '.join([e['event_type'] for e in events[:5]])}\n\n"
        f"Give 2-3 concrete expansion opportunities for this customer. Be specific. 3-4 bullet points."
    )
    from app.Services.FeatureGateService import FeatureGateService
    if not FeatureGateService.gate_llm(tenant_id, client):
        return
    suggestions = llm.complete(prompt)
    client.post_message(
        f"*Expansion signals for {cust['name']}:*\n"
        + ("\n".join([f"- {s}" for s in signals]) or "No strong signals yet")
        + f"\n\n*AI recommendations:*\n{suggestions}"
    )


def _cmd_qbr(client, name: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM customers WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        cust = cur.fetchone()

    if not cust:
        client.post_message(f"Customer '{name}' not found.")
        return

    health = calculate_health(cust["id"], tenant_id)
    prompt = (
        f"Generate a QBR (Quarterly Business Review) agenda for customer: {cust['name']}\n"
        f"ARR: {_fmt_v(cust['arr'])}\n"
        f"Health score: {health['score']}/100 ({health['level']})\n"
        f"NPS: {cust['nps'] or 'N/A'}\n"
        f"Renewal date: {cust['renewal_date'] or 'unknown'}\n"
        f"Key signals: {'; '.join(health['signals'])}\n\n"
        f"Create a 5-point QBR agenda with time estimates. Focus on value delivery and renewal. "
        f"Format as a numbered list."
    )
    from app.Services.FeatureGateService import FeatureGateService
    if not FeatureGateService.gate_llm(tenant_id, client):
        return
    agenda = llm.complete(prompt)
    client.post_message(f"*QBR Agenda for {cust['name']}:*\n\n{agenda}")


def _cmd_weekly_report(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND status='active'", (tenant_id,))
        total = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND health_score < 50", (tenant_id,))
        red = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND health_score BETWEEN 50 AND 69", (tenant_id,))
        yellow = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM customers WHERE tenant_id=%s AND renewal_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'",
            (tenant_id,)
        )
        renewals = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT name, arr FROM customers WHERE tenant_id=%s AND health_score < 50 ORDER BY arr DESC LIMIT 3",
            (tenant_id,)
        )
        top_red = cur.fetchall()

    green = total - red - yellow
    lines = [
        "*CS Weekly Report*\n",
        f"🟢 {green}  🟡 {yellow}  🔴 {red}  of {total} active customers",
        f"🔄 {renewals} renewals due in 30 days",
    ]
    if top_red:
        lines.append("\n*Top at-risk:*")
        for r in top_red:
            lines.append(f"🔴 {r['name']} — {_fmt_v(r['arr'])}")
    client.post_message("\n".join(lines))


def _cmd_patterns(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("CSAgent", tenant_id)
    patterns = mem.get_patterns(min_occurrences=2)
    if not patterns:
        client.post_message("No patterns detected yet. Keep using CSAgent and patterns will emerge.")
        return
    lines = ["*Patterns learned:*\n"]
    for p in patterns[:5]:
        lines.append(f"- {p['description']} (seen {p['occurrences']}x, confidence {p['confidence']:.0%})")
    client.post_message("\n".join(lines))


def _cmd_memory(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("CSAgent", tenant_id)
    events = mem.search_knowledge("")
    if not events:
        client.post_message("No memory events recorded yet.")
        return
    lines = ["*Recent memory:*\n"]
    for ev in events[:5]:
        lines.append(f"- [{ev['event_type']}] {str(ev['context'] or '')[:80]}")
    client.post_message("\n".join(lines))


def _cmd_knowledge(client, query: str, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("CSAgent", tenant_id)
    results = mem.search_knowledge(query)
    if not results:
        client.post_message(f"No memory found for '{query}'.")
        return
    lines = [f"*Knowledge search: '{query}'*\n"]
    for r in results[:5]:
        lines.append(f"- [{r['event_type']}] {str(r['outcome'] or r['context'] or '')[:100]}")
    client.post_message("\n".join(lines))


# ── Cross-agent signal handlers ────────────────────────────────────────────────

def _handle_deal_won(client, text: str):
    """DEAL_WON: customer=X arr=Y renewal_date=Z"""
    tenant_id = client.tenant_id
    parts = {}
    for p in text.replace("DEAL_WON:", "").strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v

    name         = parts.get("customer", "").replace("_", " ")
    arr          = _parse_money(parts.get("arr", "0"))
    renewal_str  = parts.get("renewal_date", "")

    renewal_date = None
    if renewal_str:
        try:
            renewal_date = datetime.strptime(renewal_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if not name:
        return

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO customers (tenant_id, name, arr, renewal_date, status)
            VALUES (%s, %s, %s, %s, 'active')
            ON CONFLICT DO NOTHING RETURNING id
            """,
            (tenant_id, name, arr, renewal_date)
        )
        row = cur.fetchone()

    if row:
        client.post_message(
            f"🏆 *{name}* onboarded — ARR: {_fmt_v(arr)} · renewal: {renewal_date or 'not set'}"
        )
        logger.info(f"CSAgent created customer from DEAL_WON: {name}")


def _handle_p1_breach(client, text: str):
    """P1_BREACH: customer=X issue=Y"""
    tenant_id = client.tenant_id
    parts = {}
    for p in text.replace("P1_BREACH:", "").strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v

    customer = parts.get("customer", "").replace("_", " ")
    issue    = parts.get("issue", "").replace("_", " ")

    if not customer:
        return

    with db_cursor() as cur:
        cur.execute(
            "SELECT id, assigned_csm FROM customers WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{customer}%")
        )
        cust = cur.fetchone()

    if cust:
        # Reduce health score
        with db_cursor() as cur:
            cur.execute(
                "UPDATE customers SET health_score = GREATEST(health_score - 20, 0) WHERE id=%s",
                (cust["id"],)
            )
            cur.execute(
                """
                INSERT INTO customer_events (tenant_id, customer_id, event_type, notes)
                VALUES (%s, %s, 'p1_breach', %s)
                """,
                (tenant_id, cust["id"], f"P1 breach: {issue}")
            )

        csm = cust["assigned_csm"] or "@cs_team"
        client.post_message(
            f"🚨 *P1 Breach* — {customer}\n_{issue}_\nHealth score reduced. {csm} follow up needed."
        )


# ── Modal data-variant functions ──────────────────────────────────────────────

def cmd_add_customer_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard completes."""
    from app.Services.ValidationService import validate_money, validate_date
    arr, _ = validate_money(data["arr"])
    renewal_date = None
    if data.get("renewal_date"):
        renewal_date, _ = validate_date(data["renewal_date"])

    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO customers (tenant_id, name, arr, renewal_date, assigned_csm) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (tenant_id, data["name"], arr, renewal_date, f"@{sender}")
        )
        cid = cur.fetchone()["id"]
    client.post_message(
        f"✅ *{data['name']}* added — ARR: {_fmt_v(arr)} · renewal: {renewal_date or 'not set'}"
    )


def cmd_log_nps_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard completes."""
    from app.Services.ValidationService import validate_integer
    score, _ = validate_integer(str(data["score"]), 0, 10)
    note = data.get("note") or ""

    with db_cursor() as cur:
        cur.execute(
            "UPDATE customers SET nps=%s WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) RETURNING id, name",
            (score, tenant_id, f"%{data['customer']}%")
        )
        row = cur.fetchone()
    if not row:
        client.post_message(f"Customer '{data['customer']}' not found.")
        return
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO customer_events (tenant_id, customer_id, event_type, notes) VALUES (%s,%s,'nps_logged',%s)",
            (tenant_id, row["id"], f"NPS {score}: {note}")
        )
    label = "promoter" if score >= 9 else ("passive" if score >= 7 else "detractor")
    client.post_message(f"NPS logged for *{row['name']}*: {score}/10 ({label})\n_{note}_")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_money(s: str) -> int:
    s = str(s).strip().replace("Rs", "").replace("INR", "").replace(",", "").upper().replace("₹", "")
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
