"""
FinanceAgent handler — invoice approvals, budget tracking, expense management.
Cross-agent in: DEAL_WON from SalesAgent → creates expected payment record.
"""
import logging
from datetime import datetime, date
from shared.db import db_cursor
from shared.llm import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient(agent="finance")

TENANT_ID = "default"


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)

    if not text or sender in ("FinanceAgent", "NEXUS"):
        return

    # Cross-agent signals
    if text.startswith("DEAL_WON:"):
        _handle_deal_won(client, text)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if ">" in text else text
    for p in ["@FinanceAgent ", "@financeagent "]:
        if clean.lower().startswith(p.lower()):
            clean = clean[len(p):]
            break

    _route_command(client, clean, sender)


def _route_command(client, text: str, sender: str):
    t = text.lower().strip()

    if t.startswith("invoice:"):
        _cmd_invoice(client, text, sender)
    elif t.startswith("invoices"):
        _cmd_list_invoices(client)
    elif t.startswith("approve:"):
        _cmd_approve_invoice(client, text, sender)
    elif t.startswith("reject:"):
        _cmd_reject_invoice(client, text, sender)
    elif t.startswith("budget:"):
        _cmd_budget_status(client, text.split(":", 1)[1].strip())
    elif t.startswith("expense:"):
        _cmd_expense(client, text, sender)
    elif t.startswith("expenses pending"):
        _cmd_expenses_pending(client)
    elif t.startswith("overdue"):
        _cmd_overdue(client)
    elif t.startswith("weekly report"):
        _cmd_weekly_report(client)
    elif t.startswith("forecast"):
        _cmd_forecast(client)
    elif t.startswith("patterns"):
        _cmd_patterns(client)
    elif t.startswith("memory"):
        _cmd_memory(client)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, text.split(":", 1)[1].strip())
    else:
        client.post_message(
            "FinanceAgent commands:\n"
            "- `@FinanceAgent invoice: Vendor, Rs50000, due: 2026-11-15, category: software`\n"
            "- `@FinanceAgent invoices`\n"
            "- `@FinanceAgent approve: invoice-042`\n"
            "- `@FinanceAgent reject: invoice-042, reason: duplicate`\n"
            "- `@FinanceAgent budget: Q4 marketing`\n"
            "- `@FinanceAgent expense: Name, Rs3200, travel, 2026-11-04`\n"
            "- `@FinanceAgent expenses pending`\n"
            "- `@FinanceAgent overdue`\n"
            "- `@FinanceAgent weekly report`\n"
            "- `@FinanceAgent forecast`"
        )


# ── Commands ───────────────────────────────────────────────────────────────────

def _cmd_invoice(client, text: str, sender: str):
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
            (TENANT_ID, vendor, amount, due_date, category, f"@{sender}")
        )
        inv_id = cur.fetchone()["id"]

    client.post_message(
        f"Invoice logged (invoice-{inv_id:03d})\n"
        f"*{vendor}* | {_fmt_v(amount)} | due: {due_date or 'not set'} | category: {category or 'none'}\n"
        f"Status: pending — reply `@FinanceAgent approve: invoice-{inv_id:03d}` to approve"
    )


def _cmd_list_invoices(client):
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
            (TENANT_ID,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No invoices found.")
        return

    lines = ["*Invoices:*\n"]
    for r in rows:
        icon = "[PENDING]" if r["status"] == "pending" else ("[OK]" if r["status"] == "approved" else "[X]")
        lines.append(
            f"{icon} invoice-{r['id']:03d} | *{r['vendor']}* | {_fmt_v(r['amount'])} "
            f"| due: {r['due_date'] or 'N/A'} | {r['category'] or 'misc'}"
        )
    client.post_message("\n".join(lines))


def _cmd_approve_invoice(client, text: str, sender: str):
    ref    = text.split(":", 1)[1].strip()
    inv_id = ref.replace("invoice-", "").strip()
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE invoices SET status='approved', approved_by=%s, approved_at=NOW()
            WHERE id=%s AND tenant_id=%s
            RETURNING id, vendor, amount
            """,
            (f"@{sender}", inv_id, TENANT_ID)
        )
        row = cur.fetchone()

    if row:
        client.post_message(
            f"Invoice-{row['id']:03d} approved\n"
            f"*{row['vendor']}* {_fmt_v(row['amount'])} approved by @{sender}"
        )
    else:
        client.post_message(f"Invoice '{ref}' not found.")


def _cmd_reject_invoice(client, text: str, sender: str):
    raw    = text.split(":", 1)[1].strip()
    parts  = raw.split(",", 1)
    ref    = parts[0].strip()
    reason = parts[1].split(":", 1)[1].strip() if len(parts) > 1 and ":" in parts[1] else "no reason given"
    inv_id = ref.replace("invoice-", "").strip()

    with db_cursor() as cur:
        cur.execute(
            "UPDATE invoices SET status='rejected', notes=%s WHERE id=%s AND tenant_id=%s RETURNING id, vendor",
            (f"Rejected by @{sender}: {reason}", inv_id, TENANT_ID)
        )
        row = cur.fetchone()

    if row:
        client.post_message(f"Invoice-{row['id']:03d} (*{row['vendor']}*) rejected — reason: {reason}")
    else:
        client.post_message(f"Invoice '{ref}' not found.")


def _cmd_budget_status(client, name: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM budgets WHERE tenant_id=%s AND LOWER(name) LIKE LOWER(%s) LIMIT 1",
            (TENANT_ID, f"%{name}%")
        )
        budget = cur.fetchone()

    if not budget:
        client.post_message(f"Budget '{name}' not found. Create one or check the name.")
        return

    pct  = round(budget["spent"] / budget["allocated"] * 100) if budget["allocated"] > 0 else 0
    rem  = budget["allocated"] - budget["spent"]
    icon = "[OK]" if pct < 75 else ("[WARN]" if pct < 90 else "[CRITICAL]")
    client.post_message(
        f"*Budget: {budget['name']}* {icon}\n"
        f"Period: {budget['period'] or 'N/A'}\n"
        f"Allocated: {_fmt_v(budget['allocated'])} | Spent: {_fmt_v(budget['spent'])} | Remaining: {_fmt_v(rem)}\n"
        f"Burn: {pct}%"
    )


def _cmd_expense(client, text: str, sender: str):
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
            (TENANT_ID, submitter, amount, category, expense_date or date.today())
        )
        exp_id = cur.fetchone()["id"]

    client.post_message(
        f"Expense claim #{exp_id} logged\n"
        f"{submitter} | {_fmt_v(amount)} | {category} | {expense_date or date.today()}\n"
        f"Status: pending approval"
    )


def _cmd_expenses_pending(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, submitter, amount, category, expense_date FROM expenses "
            "WHERE tenant_id=%s AND status='pending' ORDER BY created_at ASC",
            (TENANT_ID,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No pending expense claims.")
        return

    total = sum(r["amount"] for r in rows)
    lines = [f"*Pending expense claims ({len(rows)} | total: {_fmt_v(total)}):*\n"]
    for r in rows:
        lines.append(f"- #{r['id']} | {r['submitter']} | {_fmt_v(r['amount'])} | {r['category']} | {r['expense_date']}")
    client.post_message("\n".join(lines))


def _cmd_overdue(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, vendor, amount, due_date FROM invoices "
            "WHERE tenant_id=%s AND status='pending' AND due_date < CURRENT_DATE "
            "ORDER BY due_date ASC",
            (TENANT_ID,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No overdue invoices.")
        return

    lines = [f"*Overdue invoices ({len(rows)}):*\n"]
    for r in rows:
        days_over = (date.today() - r["due_date"]).days
        lines.append(f"- invoice-{r['id']:03d} | *{r['vendor']}* | {_fmt_v(r['amount'])} | {days_over}d overdue")
    client.post_message("\n".join(lines))


def _cmd_weekly_report(client):
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt, SUM(amount) AS total FROM invoices WHERE tenant_id=%s AND status='pending'", (TENANT_ID,))
        inv_row = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS cnt FROM invoices WHERE tenant_id=%s AND status='pending' AND due_date < CURRENT_DATE", (TENANT_ID,))
        overdue_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) AS cnt, SUM(amount) AS total FROM expenses WHERE tenant_id=%s AND status='pending'", (TENANT_ID,))
        exp_row = cur.fetchone()
        cur.execute("SELECT SUM(allocated) AS alloc, SUM(spent) AS sp FROM budgets WHERE tenant_id=%s", (TENANT_ID,))
        brow = cur.fetchone()
        alloc = brow["alloc"] or 0
        spent = brow["sp"] or 0
        burn  = round(spent / alloc * 100) if alloc > 0 else 0

    client.post_message(
        f"*FinanceAgent Weekly Report*\n"
        f"Pending invoices: {inv_row['cnt']} | total: {_fmt_v(inv_row['total'] or 0)}\n"
        f"Overdue invoices: {overdue_cnt}\n"
        f"Pending expense claims: {exp_row['cnt']} | total: {_fmt_v(exp_row['total'] or 0)}\n"
        f"Budget burn: {burn}% ({_fmt_v(spent)} of {_fmt_v(alloc)})"
    )


def _cmd_forecast(client):
    with db_cursor() as cur:
        # Approved invoices = outflows
        cur.execute(
            "SELECT SUM(amount) AS total FROM invoices WHERE tenant_id=%s AND status='approved' AND created_at > NOW() - INTERVAL '30 days'",
            (TENANT_ID,)
        )
        outflow = cur.fetchone()["total"] or 0

        # Expenses paid out
        cur.execute(
            "SELECT SUM(amount) AS total FROM expenses WHERE tenant_id=%s AND created_at > NOW() - INTERVAL '30 days'",
            (TENANT_ID,)
        )
        exp_total = cur.fetchone()["total"] or 0

        # Pending outflow
        cur.execute(
            "SELECT SUM(amount) AS total FROM invoices WHERE tenant_id=%s AND status='pending'",
            (TENANT_ID,)
        )
        pending_outflow = cur.fetchone()["total"] or 0

        # Budget remaining
        cur.execute("SELECT SUM(allocated) AS alloc, SUM(spent) AS sp FROM budgets WHERE tenant_id=%s", (TENANT_ID,))
        brow = cur.fetchone()
        alloc = brow["alloc"] or 0
        spent = brow["sp"] or 0

    burn_rate = outflow + exp_total  # last 30 days spend
    client.post_message(
        f"*FinanceAgent Forecast*\n"
        f"Last 30d spend: {_fmt_v(burn_rate)} (invoices: {_fmt_v(outflow)} + expenses: {_fmt_v(exp_total)})\n"
        f"Pending payables: {_fmt_v(pending_outflow)}\n"
        f"Budget remaining: {_fmt_v(alloc - spent)} of {_fmt_v(alloc)} allocated\n"
        f"Projected monthly run rate: {_fmt_v(burn_rate)}"
    )


def _cmd_patterns(client):
    from shared.memory import AgentMemory
    mem = AgentMemory("FinanceAgent", TENANT_ID)
    patterns = mem.get_patterns(min_occurrences=2)
    if not patterns:
        client.post_message("No patterns detected yet.")
        return
    lines = ["*FinanceAgent learned patterns:*\n"]
    for p in patterns[:5]:
        lines.append(f"- {p['description']} (seen {p['occurrences']}x)")
    client.post_message("\n".join(lines))


def _cmd_memory(client):
    from shared.memory import AgentMemory
    mem = AgentMemory("FinanceAgent", TENANT_ID)
    events = mem.search_knowledge("")
    if not events:
        client.post_message("No memory events recorded yet.")
        return
    lines = ["*FinanceAgent recent memory:*\n"]
    for ev in events[:5]:
        lines.append(f"- [{ev['event_type']}] {str(ev['context'] or '')[:80]}")
    client.post_message("\n".join(lines))


def _cmd_knowledge(client, query: str):
    from shared.memory import AgentMemory
    mem = AgentMemory("FinanceAgent", TENANT_ID)
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
            (TENANT_ID, customer, amount, f"Auto-created from SalesAgent DEAL_WON")
        )
        inv_id = cur.fetchone()["id"]

    client.post_message(
        f"*Revenue logged* from SalesAgent deal win\n"
        f"Customer: *{customer}* | Amount: {_fmt_v(amount)} | invoice-{inv_id:03d}"
    )
    logger.info(f"FinanceAgent logged revenue from DEAL_WON: {customer} {amount}")


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
