"""
FinanceAgent handler — invoice approvals, budget tracking, expense management.
Cross-agent in: DEAL_WON from SalesAgent → creates expected payment record.
"""
import logging
from datetime import datetime, date
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient(agent="finance")


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)
    room_id    = payload.get("room_id", client.room_id)
    tenant_id  = client.tenant_id

    if sender in ("FinanceAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return

    # Cross-agent signals
    if text.startswith("DEAL_WON:"):
        _handle_deal_won(client, text)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if text.startswith("<@") else text
    for p in ["@FinanceAgent ", "@financeagent "]:
        if clean.lower().startswith(p.lower()):
            clean = clean[len(p):]
            break

    from app.Services import ConversationService
    if ConversationService.resume(tenant_id, room_id, sender, "FinanceAgent", clean, client):
        return

    _route_command(client, clean, sender, tenant_id, room_id)


def _route_command(client, text: str, sender: str, tenant_id: str, room_id: str):
    t = text.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "FinanceAgent", _cmd_key, sender)

    if t == "invoice" or t == "invoice:":
        from app.Services import ConversationService
        ConversationService.start(tenant_id, room_id, sender, "FinanceAgent", "add_invoice", client)
    elif t.startswith("invoice:"):
        _cmd_invoice(client, text, sender, tenant_id)
    elif t.startswith("invoices"):
        _cmd_list_invoices(client, tenant_id)
    elif t.startswith("approve:"):
        _cmd_approve_invoice(client, text, sender, tenant_id)
    elif t == "reject":
        from app.Services import ConversationService
        ConversationService.start(tenant_id, room_id, sender, "FinanceAgent", "reject_invoice", client)
    elif t.startswith("reject:"):
        _cmd_reject_invoice(client, text, sender, tenant_id)
    elif t.startswith("budget:"):
        _cmd_budget_status(client, text.split(":", 1)[1].strip(), tenant_id)
    elif t == "expense":
        from app.Services import ConversationService
        ConversationService.start(tenant_id, room_id, sender, "FinanceAgent", "add_expense", client)
    elif t.startswith("expense:"):
        _cmd_expense(client, text, sender, tenant_id)
    elif t.startswith("expenses pending"):
        _cmd_expenses_pending(client, tenant_id)
    elif t.startswith("overdue"):
        _cmd_overdue(client, tenant_id)
    elif t.startswith("weekly report"):
        _cmd_weekly_report(client, tenant_id)
    elif t.startswith("forecast"):
        _cmd_forecast(client, tenant_id)
    elif t.startswith("patterns"):
        _cmd_patterns(client, tenant_id)
    elif t.startswith("memory"):
        _cmd_memory(client, tenant_id)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, text.split(":", 1)[1].strip(), tenant_id)
    else:
        from app.Services.BlockBuilder import _section
        client.post_blocks([
            _section("*FinanceAgent — Invoices & Expenses*\n"
                     "• `invoice: Vendor, Rs50K, due: 2026-11-15, category: software`\n"
                     "• `invoices`\n"
                     "• `approve: invoice-042`\n"
                     "• `reject: invoice-042, reason: duplicate`\n"
                     "• `budget: category name`\n"
                     "• `expense: Name, Rs3200, travel, 2026-11-04`\n"
                     "• `expenses pending`\n"
                     "• `overdue`\n"
                     "• `weekly report`\n"
                     "• `forecast`")
        ], fallback_text="FinanceAgent commands")


# ── Commands ───────────────────────────────────────────────────────────────────

def _cmd_invoice(client, text: str, sender: str, tenant_id: str):
    """Parse: 'invoice: Vendor, Rs50000, due: 2026-11-15, category: software'"""
    raw = text.split(":", 1)[1].strip()
    due_date = None
    category = ""

    if "due:" in raw.lower():
        idx = raw.lower().find("due:")
        due_str = raw[idx + 4:].strip().split(",")[0].strip()
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            due_date = None
        raw = raw[:idx].strip().rstrip(",")

    if "category:" in raw.lower():
        idx = raw.lower().find("category:")
        category = raw[idx + 9:].strip().split(",")[0].strip()
        raw = raw[:idx].strip().rstrip(",")

    parts  = [p.strip() for p in raw.split(",")]
    vendor = parts[0] if parts else raw
    amount = _parse_money(parts[1]) if len(parts) > 1 else 0

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO invoices (tenant_id, vendor, amount, due_date, category, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (tenant_id, vendor, amount, due_date, category, f"@{sender}")
        )
        inv_id = cur.fetchone()["id"]

    from app.Services.BlockBuilder import invoice_logged
    client.post_blocks(
        invoice_logged(f"{inv_id:03d}", vendor, _fmt_v(amount), str(due_date or "not set"), category),
        fallback_text=f"Invoice logged: {vendor} {_fmt_v(amount)}"
    )


def _cmd_list_invoices(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, vendor, amount, due_date, status, category
            FROM invoices WHERE tenant_id=%s
            ORDER BY
                CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                due_date ASC NULLS LAST
            LIMIT 20
            """,
            (tenant_id,)
        )
        rows = cur.fetchall()

    from app.Services.BlockBuilder import invoice_list
    client.post_blocks(
        invoice_list([dict(r) for r in rows]),
        fallback_text="Invoices list"
    )


def _cmd_approve_invoice(client, text: str, sender: str, tenant_id: str):
    from app.Services.UserIdentityService import UserIdentityService
    if not UserIdentityService.has_role(tenant_id, sender, "manager"):
        UserIdentityService.deny(client, "approve invoices")
        return
    ref    = text.split(":", 1)[1].strip()
    inv_id = ref.replace("invoice-", "").strip()
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE invoices SET status='approved', approved_by=%s, approved_at=NOW()
            WHERE id=%s AND tenant_id=%s
            RETURNING id, vendor, amount
            """,
            (f"@{sender}", inv_id, tenant_id)
        )
        row = cur.fetchone()

    if row:
        client.post_message(
            f"✅ Invoice #{row['id']:03d} approved — *{row['vendor']}* {_fmt_v(row['amount'])}"
        )
    else:
        client.post_message(f"Invoice '{ref}' not found.")


def _cmd_reject_invoice(client, text: str, sender: str, tenant_id: str):
    from app.Services.UserIdentityService import UserIdentityService
    if not UserIdentityService.has_role(tenant_id, sender, "manager"):
        UserIdentityService.deny(client, "approve invoices")
        return
    raw    = text.split(":", 1)[1].strip()
    parts  = raw.split(",", 1)
    ref    = parts[0].strip()
    reason = parts[1].split(":", 1)[1].strip() if len(parts) > 1 and ":" in parts[1] else "no reason given"
    inv_id = ref.replace("invoice-", "").strip()

    with db_cursor() as cur:
        cur.execute(
            "UPDATE invoices SET status='rejected', notes=%s WHERE id=%s AND tenant_id=%s RETURNING id, vendor",
            (f"Rejected by @{sender}: {reason}", inv_id, tenant_id)
        )
        row = cur.fetchone()

    if row:
        client.post_message(f"Invoice-{row['id']:03d} (*{row['vendor']}*) rejected — reason: {reason}")
    else:
        client.post_message(f"Invoice '{ref}' not found.")


def _cmd_budget_status(client, name: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM budgets WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (tenant_id, f"%{name}%")
        )
        budget = cur.fetchone()

    if not budget:
        client.post_message(f"Budget '{name}' not found. Create one or check the name.")
        return

    pct  = round(budget["spent"] / budget["allocated"] * 100) if budget["allocated"] > 0 else 0
    rem  = budget["allocated"] - budget["spent"]
    emoji = "✅" if pct < 75 else ("⚠️" if pct < 90 else "🚨")
    from app.Services.BlockBuilder import _section, _context
    client.post_blocks([
        _section(f"{emoji} *{budget['name']}* — {pct}% burned"),
        _context(f"Spent: {_fmt_v(budget['spent'])}", f"Remaining: {_fmt_v(rem)}", f"of {_fmt_v(budget['allocated'])}"),
    ], fallback_text=f"Budget {budget['name']}: {pct}% burned")


def _cmd_expense(client, text: str, sender: str, tenant_id: str):
    """Parse: 'expense: Name, Rs3200, travel, 2026-11-04'"""
    raw   = text.split(":", 1)[1].strip()
    parts = [p.strip() for p in raw.split(",")]
    submitter   = parts[0] if parts else sender
    amount      = _parse_money(parts[1]) if len(parts) > 1 else 0
    category    = parts[2] if len(parts) > 2 else ""
    expense_date = None
    if len(parts) > 3:
        try:
            expense_date = datetime.strptime(parts[3].strip(), "%Y-%m-%d").date()
        except ValueError:
            expense_date = date.today()

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO expenses (tenant_id, submitter, amount, category, expense_date, status)
            VALUES (%s, %s, %s, %s, %s, 'pending') RETURNING id
            """,
            (tenant_id, submitter, amount, category, expense_date or date.today())
        )
        exp_id = cur.fetchone()["id"]

    client.post_message(
        f"⏳ Expense #{exp_id} logged — *{submitter}* {_fmt_v(amount)} · {category}"
    )


def _cmd_expenses_pending(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, submitter, amount, category, expense_date FROM expenses "
            "WHERE tenant_id=%s AND status='pending' ORDER BY created_at ASC",
            (tenant_id,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No pending expense claims.")
        return

    total = sum(r["amount"] for r in rows)
    lines = [f"*Pending expenses — {len(rows)} claims · {_fmt_v(total)} total*\n"]
    for r in rows:
        lines.append(f"⏳ *{r['submitter']}* — {_fmt_v(r['amount'])} · {r['category']}")
    client.post_message("\n".join(lines))


def _cmd_overdue(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, vendor, amount, due_date FROM invoices "
            "WHERE tenant_id=%s AND status='pending' AND due_date < CURRENT_DATE "
            "ORDER BY due_date ASC",
            (tenant_id,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No overdue invoices.")
        return

    lines = [f"*Overdue invoices ({len(rows)})*\n"]
    for r in rows:
        days_over = (date.today() - r["due_date"]).days
        lines.append(f"🚨 *{r['vendor']}* — {_fmt_v(r['amount'])} · {days_over}d overdue")
    client.post_message("\n".join(lines))


def _cmd_weekly_report(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt, SUM(amount) AS total FROM invoices WHERE tenant_id=%s AND status='pending'", (tenant_id,))
        inv_row = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id=%s AND status='pending' AND due_date < CURRENT_DATE", (tenant_id,))
        overdue_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt, SUM(amount) AS total FROM expenses WHERE tenant_id=%s AND status='pending'", (tenant_id,))
        exp_row = cur.fetchone()
        cur.execute("SELECT SUM(allocated) AS alloc, SUM(spent) AS sp FROM budgets WHERE tenant_id=%s", (tenant_id,))
        brow = cur.fetchone()
        alloc = brow["alloc"] or 0
        spent = brow["sp"] or 0
        burn  = round(spent / alloc * 100) if alloc > 0 else 0

    client.post_message(
        f"*Finance Weekly*\n"
        f"⏳ {inv_row['cnt']} pending invoices · {_fmt_v(inv_row['total'] or 0)}\n"
        f"🚨 {overdue_cnt} overdue\n"
        f"💸 {exp_row['cnt']} expense claims · {_fmt_v(exp_row['total'] or 0)}\n"
        f"📊 Budget: {burn}% burned ({_fmt_v(spent)} of {_fmt_v(alloc)})"
    )


def _cmd_forecast(client, tenant_id: str):
    with db_cursor() as cur:
        # Approved invoices = outflows
        cur.execute(
            "SELECT SUM(amount) AS total FROM invoices WHERE tenant_id=%s AND status='approved' AND created_at > NOW() - INTERVAL '30 days'",
            (tenant_id,)
        )
        outflow = cur.fetchone()["total"] or 0

        # Expenses paid out
        cur.execute(
            "SELECT SUM(amount) AS total FROM expenses WHERE tenant_id=%s AND created_at > NOW() - INTERVAL '30 days'",
            (tenant_id,)
        )
        exp_total = cur.fetchone()["total"] or 0

        # Pending outflow
        cur.execute(
            "SELECT SUM(amount) AS total FROM invoices WHERE tenant_id=%s AND status='pending'",
            (tenant_id,)
        )
        pending_outflow = cur.fetchone()["total"] or 0

        # Budget remaining
        cur.execute("SELECT SUM(allocated) AS alloc, SUM(spent) AS sp FROM budgets WHERE tenant_id=%s", (tenant_id,))
        brow = cur.fetchone()
        alloc = brow["alloc"] or 0
        spent = brow["sp"] or 0

    burn_rate = outflow + exp_total  # last 30 days spend
    client.post_message(
        f"*Finance Forecast*\n"
        f"📉 30d spend: {_fmt_v(burn_rate)} · run rate: {_fmt_v(burn_rate)}/mo\n"
        f"⏳ Pending payables: {_fmt_v(pending_outflow)}\n"
        f"💰 Budget remaining: {_fmt_v(alloc - spent)} of {_fmt_v(alloc)}"
    )


def _cmd_patterns(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("FinanceAgent", tenant_id)
    patterns = mem.get_patterns(min_occurrences=2)
    if not patterns:
        client.post_message("No patterns detected yet.")
        return
    lines = ["*Patterns learned:*\n"]
    for p in patterns[:5]:
        lines.append(f"- {p['description']} (seen {p['occurrences']}x)")
    client.post_message("\n".join(lines))


def _cmd_memory(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("FinanceAgent", tenant_id)
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
    mem = AgentMemory("FinanceAgent", tenant_id)
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
    """DEAL_WON: customer=X amount=Y"""
    tenant_id = client.tenant_id
    parts = {}
    for p in text.replace("DEAL_WON:", "").strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v

    customer = parts.get("customer", "").replace("_", " ")
    amount   = _parse_money(parts.get("amount", "0"))

    if not customer or amount == 0:
        return

    # Create an expected payment invoice
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO invoices (tenant_id, vendor, amount, category, status, notes)
            VALUES (%s, %s, %s, 'revenue', 'approved', %s) RETURNING id
            """,
            (tenant_id, customer, amount, f"Auto-created from SalesAgent DEAL_WON")
        )
        inv_id = cur.fetchone()["id"]

    client.post_message(
        f"💰 *{customer}* — {_fmt_v(amount)} revenue logged (invoice #{inv_id:03d})"
    )
    logger.info(f"FinanceAgent logged revenue from DEAL_WON: {customer} {amount}")


# ── Modal data-variant functions ──────────────────────────────────────────────

def cmd_invoice_data(client, data: dict, sender: str, tenant_id: str):
    from app.Services.ValidationService import validate_money, validate_date
    amount, _ = validate_money(data["amount"])
    due_date = None
    if data.get("due_date"):
        due_date, _ = validate_date(data["due_date"])
    category = data.get("category") or ""
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO invoices (tenant_id, vendor, amount, due_date, category, submitted_by) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (tenant_id, data["vendor"], amount, due_date, category, f"@{sender}")
        )
        inv_id = cur.fetchone()["id"]
    from app.Services.BlockBuilder import invoice_logged
    client.post_blocks(
        invoice_logged(f"{inv_id:03d}", data["vendor"], _fmt_v(amount), str(due_date or "not set"), category),
        fallback_text=f"Invoice logged: {data['vendor']} {_fmt_v(amount)}"
    )


def cmd_expense_data(client, data: dict, sender: str, tenant_id: str):
    from app.Services.ValidationService import validate_money, validate_date
    from datetime import date
    amount, _ = validate_money(data["amount"])
    submitter = data["submitter"]
    if submitter.lower() == "me":
        submitter = sender
    expense_date = date.today()
    if data.get("expense_date"):
        parsed, _ = validate_date(data["expense_date"])
        if parsed:
            expense_date = parsed
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO expenses (tenant_id, submitter, amount, category, expense_date, status) VALUES (%s,%s,%s,%s,%s,'pending') RETURNING id",
            (tenant_id, submitter, amount, data["category"], expense_date)
        )
        exp_id = cur.fetchone()["id"]
    client.post_message(
        f"⏳ Expense #{exp_id} logged — *{submitter}* {_fmt_v(amount)} · {data['category']}"
    )


def cmd_reject_invoice_data(client, data: dict, sender: str, tenant_id: str):
    inv_id = str(data["invoice_id"]).replace("invoice-", "").strip()
    reason = data["reason"]
    with db_cursor() as cur:
        cur.execute(
            "UPDATE invoices SET status='rejected', notes=%s WHERE id=%s AND tenant_id=%s RETURNING id, vendor",
            (f"Rejected by @{sender}: {reason}", inv_id, tenant_id)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Invoice-{row['id']:03d} (*{row['vendor']}*) rejected — reason: {reason}")
    else:
        client.post_message(f"Invoice '{data['invoice_id']}' not found.")


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
