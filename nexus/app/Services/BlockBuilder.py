"""
Block Kit helpers. Only used where buttons genuinely improve UX.
All buttons use action_id="nexus_cmd" and put the command in value —
SlackClient routes button clicks back through the same handler as text.
"""


def _btn(label: str, cmd: str, style: str = None) -> dict:
    b = {
        "type": "button",
        "text": {"type": "plain_text", "text": label, "emoji": True},
        "action_id": "nexus_cmd",
        "value": cmd,
    }
    if style:
        b["style"] = style
    return b


def _actions(*buttons) -> dict:
    return {"type": "actions", "elements": list(buttons)}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _divider() -> dict:
    return {"type": "divider"}


# ── Finance ───────────────────────────────────────────────────────────────────

def invoice_logged(inv_id: str, vendor: str, amount: str, due: str, category: str) -> list:
    return [
        _section(
            f"*Invoice logged* (invoice-{inv_id})\n"
            f"*{vendor}* | {amount} | due: {due} | category: {category or 'none'}\n"
            f"Status: pending"
        ),
        _actions(
            _btn("✅ Approve", f"approve: invoice-{inv_id}", style="primary"),
            _btn("❌ Reject",  f"reject: invoice-{inv_id}",  style="danger"),
        ),
    ]


def invoice_list(rows: list) -> list:
    """rows: list of dicts with id, vendor, amount, status, due_date"""
    if not rows:
        return [_section("No invoices found.")]

    blocks = [_section("*Invoices:*")]
    for r in rows:
        status = r.get("status", "pending")
        due    = str(r.get("due_date", "—"))
        amount = r.get("amount", "—")
        line   = f"*invoice-{r['id']:03d}* | {r['vendor']} | {amount} | due {due} | _{status}_"

        if status == "pending":
            blocks.append(_section(line))
            blocks.append(_actions(
                _btn("✅ Approve", f"approve: invoice-{r['id']:03d}", style="primary"),
                _btn("❌ Reject",  f"reject: invoice-{r['id']:03d}",  style="danger"),
            ))
        else:
            blocks.append(_section(line))

    return blocks


# ── Blog ──────────────────────────────────────────────────────────────────────

def draft_created(draft_id: int, title: str, preview: str) -> list:
    return [
        _section(f"*Draft ready* — #{draft_id}\n*{title}*\n>{preview[:200]}…"),
        _actions(
            _btn("✅ Approve",          f"approve: #{draft_id}",  style="primary"),
            _btn("👁 Preview",           f"preview: #{draft_id}"),
            _btn("❌ Reject",            f"reject: #{draft_id}",   style="danger"),
        ),
    ]


def draft_queue(rows: list) -> list:
    if not rows:
        return [_section("Content queue is empty.")]

    blocks = [_section("*Content queue:*")]
    for r in rows:
        blocks.append(_section(f"*#{r['id']}* | {r.get('title') or r.get('keyword', '—')} | _{r['status']}_"))
        if r.get("status") in ("pending", "draft"):
            blocks.append(_actions(
                _btn("✅ Approve", f"approve: #{r['id']}", style="primary"),
                _btn("👁 Preview", f"preview: #{r['id']}"),
                _btn("❌ Reject",  f"reject: #{r['id']}",  style="danger"),
            ))
    return blocks


# ── Sales ─────────────────────────────────────────────────────────────────────

def lead_added(name: str, role: str, value: str) -> list:
    return [
        _section(f"*Lead added* — {name}\n{role} | {value}"),
        _actions(
            _btn("📋 Pipeline",    "pipeline"),
            _btn("💬 Follow Up",   f"follow up: {name}"),
        ),
    ]


def pipeline_row(name: str, stage: str, value: str) -> list:
    return [
        _section(f"*{name}* | {stage} | {value}"),
        _actions(
            _btn("💬 Follow Up", f"follow up: {name}"),
            _btn("🏆 Won",       f"won: {name}",  style="primary"),
            _btn("❌ Lost",      f"lost: {name}", style="danger"),
        ),
    ]


# ── Support ───────────────────────────────────────────────────────────────────

def bug_logged(bug_id: int, description: str, priority: str) -> list:
    return [
        _section(f"*Bug logged* — #{bug_id} `{priority}`\n{description}"),
        _actions(
            _btn("📋 All Bugs",  "status"),
            _btn("✅ Close",     f"close: #{bug_id}", style="primary"),
        ),
    ]


# ── GEO ───────────────────────────────────────────────────────────────────────

def geo_score(keyword: str, score: int, reason: str) -> list:
    emoji = "🟢" if score >= 7 else "🟡" if score >= 4 else "🔴"
    blocks = [
        _section(
            f"*GEO score for \"{keyword}\"* {emoji}\n"
            f"Score: *{score}/10*\n_{reason}_"
        ),
    ]
    if score < 8:
        blocks.append(_actions(
            _btn("💡 Get Improvement Tips", f"geo tips: {keyword}"),
        ))
    return blocks


# ── Infra ─────────────────────────────────────────────────────────────────────

def service_status_row(name: str, url: str, status: str, failures: int) -> list:
    emoji  = "🟢" if status == "up" else "🔴"
    label  = f"{emoji} *{name}* | {url} | {status}"
    if failures:
        label += f" | {failures} consecutive failures"
    return [
        _section(label),
        _actions(
            _btn("🔁 Ping Now", f"ping: {url}"),
        ),
    ]
