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


def _context(*texts) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": t} for t in texts]}


def _divider() -> dict:
    return {"type": "divider"}


# ── Finance ───────────────────────────────────────────────────────────────────

def invoice_logged(inv_id: str, vendor: str, amount: str, due: str, category: str) -> list:
    cat_str = f" · {category}" if category and category != "none" else ""
    return [
        _section(f"*{vendor}* — {amount}"),
        _context(f"Invoice #{inv_id}{cat_str}", f"Due: {due}", "Status: _pending_"),
        _actions(
            _btn("✅ Approve", f"approve: invoice-{inv_id}", style="primary"),
            _btn("❌ Reject",  f"reject: invoice-{inv_id}",  style="danger"),
        ),
    ]


def invoice_list(rows: list) -> list:
    if not rows:
        return [_section("No invoices found.")]

    blocks = [_section("*Invoices*"), _divider()]
    for r in rows:
        status = r.get("status", "pending")
        due    = str(r.get("due_date", "—"))
        amount = r.get("amount", "—")
        status_emoji = "⏳" if status == "pending" else ("✅" if status == "approved" else "❌")

        blocks.append(_section(f"{status_emoji} *{r['vendor']}* — {amount}"))
        blocks.append(_context(f"#{r['id']:03d}", f"Due: {due}", f"_{status}_"))

        if status == "pending":
            blocks.append(_actions(
                _btn("✅ Approve", f"approve: invoice-{r['id']:03d}", style="primary"),
                _btn("❌ Reject",  f"reject: invoice-{r['id']:03d}",  style="danger"),
            ))

    return blocks


# ── Blog ──────────────────────────────────────────────────────────────────────

def draft_created(draft_id: int, title: str, preview: str) -> list:
    return [
        _section(f"*{title}*"),
        _context(f"Draft #{draft_id}", f"_{preview[:180]}…_"),
        _actions(
            _btn("✅ Approve",  f"approve: #{draft_id}",  style="primary"),
            _btn("👁 Preview",  f"preview: #{draft_id}"),
            _btn("❌ Reject",   f"reject: #{draft_id}",   style="danger"),
        ),
    ]


def draft_queue(rows: list) -> list:
    if not rows:
        return [_section("Content queue is empty.")]

    blocks = [_section("*Content queue*"), _divider()]
    for r in rows:
        title = r.get("title") or r.get("keyword", "—")
        status = r.get("status", "")
        status_emoji = "✍️" if status in ("pending", "draft", "draft_ready") else ("✅" if status == "published" else "❌")
        blocks.append(_section(f"{status_emoji} *{title}*"))
        blocks.append(_context(f"#{r['id']}", f"_{status}_"))
        if r.get("status") in ("pending", "draft", "draft_ready"):
            blocks.append(_actions(
                _btn("✅ Approve", f"approve: #{r['id']}", style="primary"),
                _btn("👁 Preview", f"preview: #{r['id']}"),
                _btn("❌ Reject",  f"reject: #{r['id']}",  style="danger"),
            ))
    return blocks


# ── Sales ─────────────────────────────────────────────────────────────────────

def lead_added(name: str, role: str, value: str) -> list:
    return [
        _section(f"🎯 *{name}*"),
        _context(role, value),
        _actions(
            _btn("📋 Pipeline",  "pipeline"),
            _btn("💬 Follow Up", f"follow up: {name}"),
        ),
    ]


def pipeline_row(name: str, stage: str, value: str) -> list:
    stage_emoji = {
        "Prospect": "🔵", "Qualified": "🟡", "Proposal": "🟠",
        "Negotiation": "🔸", "Closed-Won": "🏆", "Closed-Lost": "❌"
    }.get(stage, "⚫")
    return [
        _section(f"{stage_emoji} *{name}* — {value}"),
        _context(f"Stage: {stage}"),
        _actions(
            _btn("💬 Follow Up", f"follow up: {name}"),
            _btn("🏆 Won",       f"won: {name}",  style="primary"),
            _btn("❌ Lost",      f"lost: {name}", style="danger"),
        ),
    ]


# ── Support ───────────────────────────────────────────────────────────────────

def bug_logged(bug_id: int, description: str, priority: str) -> list:
    sev_emoji = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}.get(priority, "⚫")
    return [
        _section(f"{sev_emoji} *{priority}* — {description}"),
        _context(f"Bug #{bug_id}"),
        _actions(
            _btn("📋 All Bugs",  "status"),
            _btn("✅ Close",     f"close: #{bug_id}", style="primary"),
        ),
    ]


# ── GEO ───────────────────────────────────────────────────────────────────────

def geo_score(keyword: str, score: int, reason: str) -> list:
    emoji = "🟢" if score >= 7 else "🟡" if score >= 4 else "🔴"
    blocks = [
        _section(f"{emoji} *{keyword}* — {score}/10"),
        _context(f"_{reason}_"),
    ]
    if score < 8:
        blocks.append(_actions(
            _btn("💡 Improve", f"geo tips: {keyword}"),
        ))
    return blocks


# ── Infra ─────────────────────────────────────────────────────────────────────

def service_status_row(name: str, url: str, status: str, failures: int) -> list:
    emoji = "🟢" if status == "up" else "🔴"
    fail_str = f" · {failures} failures" if failures else ""
    return [
        _section(f"{emoji} *{name}*"),
        _context(url, f"_{status}{fail_str}_"),
        _actions(
            _btn("🔁 Ping", f"ping: {url}"),
        ),
    ]
