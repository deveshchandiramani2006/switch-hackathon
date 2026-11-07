"""
Block Kit helpers. Card anatomy: header -> fields/section -> divider -> actions.
Lists post each item as a separate card (one post_blocks call per row).
LLM output uses >blockquote style.
Unique action_id per button within any message.
No em dashes anywhere.
"""


# ── Primitives ────────────────────────────────────────────────────────────────

def _btn(label: str, cmd: str, action_id: str, style: str = None) -> dict:
    b = {
        "type": "button",
        "text": {"type": "plain_text", "text": label, "emoji": True},
        "action_id": action_id,
        "value": cmd,
    }
    if style:
        b["style"] = style
    return b


def _actions(*buttons) -> dict:
    return {"type": "actions", "elements": list(buttons)}


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _fields(*texts) -> dict:
    return {"type": "section", "fields": [{"type": "mrkdwn", "text": t} for t in texts]}


def _context(*texts) -> dict:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": t} for t in texts]}


def _divider() -> dict:
    return {"type": "divider"}


def _quote_llm(text: str) -> dict:
    """Render LLM-generated text as a Slack blockquote."""
    lines = text.strip().split("\n")
    quoted = "\n".join(f">{line}" if line.strip() else ">" for line in lines)
    return _section(quoted)


def _fmt_money(v) -> str:
    try:
        v = int(v)
    except Exception:
        return str(v)
    if v >= 10_000_000:
        return f"Rs {v/10_000_000:.1f}Cr"
    if v >= 100_000:
        return f"Rs {v/100_000:.1f}L"
    if v >= 1_000:
        return f"Rs {v/1_000:.0f}K"
    return f"Rs {v}"


# ── Sales ─────────────────────────────────────────────────────────────────────

def lead_added(name: str, role: str, value: str) -> list:
    return [
        _header("🎯 New Lead Added"),
        _fields(
            f"*Name*\n{name}",
            f"*Deal Value*\n{value}",
        ),
        _section(role),
        _divider(),
        _actions(
            _btn("💬 Draft Follow-up", f"follow up: {name}", "nexus_followup"),
            _btn("📋 Pipeline",        "pipeline",           "nexus_pipeline"),
        ),
    ]


def deal_won(name: str, value: str) -> list:
    return [
        _header("🏆 Deal Closed"),
        _fields(
            f"*Customer*\n{name}",
            f"*Value*\n{value}",
        ),
        _context("Notifying Finance and CS now..."),
    ]


def deal_lost(name: str, reason: str) -> list:
    return [
        _header("❌ Deal Lost"),
        _fields(
            f"*Lead*\n{name}",
            f"*Reason*\n{reason}",
        ),
    ]


def commitment_tracked(cid: int, text: str) -> list:
    return [
        _header("📌 Commitment Tracked"),
        _section(text),
        _context(f"Commitment #{cid}  ·  escalation enabled"),
    ]


def pipeline_card(name: str, stage: str, value: str, lead_id: int = 0) -> list:
    """Standalone card for each lead in a pipeline listing."""
    stage_emoji = {
        "Prospect": "🔵", "Qualified": "🟡", "Proposal": "🟠",
        "Negotiation": "🔸", "Closed-Won": "🏆", "Closed-Lost": "❌"
    }.get(stage, "⚫")
    sfx = f"_{lead_id}" if lead_id else f"_{name[:8].replace(' ', '')}"
    return [
        _header(f"{stage_emoji} {stage}"),
        _fields(
            f"*Name*\n{name}",
            f"*Value*\n{value}",
        ),
        _divider(),
        _actions(
            _btn("💬 Follow Up", f"follow up: {name}", f"nexus_followup{sfx}"),
            _btn("🏆 Won",       f"won: {name}",       f"nexus_won{sfx}",  style="primary"),
            _btn("❌ Lost",      f"lost: {name}",      f"nexus_lost{sfx}", style="danger"),
        ),
    ]


# ── Finance ───────────────────────────────────────────────────────────────────

def invoice_logged(inv_id: str, vendor: str, amount: str, due: str, category: str) -> list:
    cat = category if category and category.lower() not in ("", "none") else "uncategorized"
    return [
        _header("🧾 Invoice Received"),
        _fields(
            f"*Vendor*\n{vendor}",
            f"*Amount*\n{amount}",
            f"*Due Date*\n{due}",
            f"*Category*\n{cat}",
        ),
        _context(f"Invoice #{inv_id}  ·  pending approval"),
        _divider(),
        _actions(
            _btn("✅ Approve", f"approve: invoice-{inv_id}", "nexus_approve", style="primary"),
            _btn("❌ Reject",  f"reject: invoice-{inv_id}",  "nexus_reject",  style="danger"),
        ),
    ]


def invoice_status_card(r: dict) -> list:
    """Standalone card for each invoice in the invoices listing."""
    row_id = r["id"]
    status = r.get("status", "pending")
    due    = str(r.get("due_date", "not set"))
    amount = _fmt_money(r.get("amount", 0))
    status_emoji = "⏳" if status == "pending" else ("✅" if status == "approved" else "❌")
    blocks = [
        _header(f"🧾 Invoice #{row_id:03d}  {status_emoji}"),
        _fields(
            f"*Vendor*\n{r['vendor']}",
            f"*Amount*\n{amount}",
            f"*Due Date*\n{due}",
            f"*Status*\n_{status}_",
        ),
    ]
    if status == "pending":
        blocks += [
            _divider(),
            _actions(
                _btn("✅ Approve", f"approve: invoice-{row_id:03d}", f"nexus_approve_{row_id}", style="primary"),
                _btn("❌ Reject",  f"reject: invoice-{row_id:03d}",  f"nexus_reject_{row_id}",  style="danger"),
            ),
        ]
    return blocks


def revenue_logged(customer: str, amount: str, inv_id: str) -> list:
    return [
        _header("💰 Revenue Logged"),
        _fields(
            f"*Customer*\n{customer}",
            f"*Amount*\n{amount}",
        ),
        _context(f"Invoice #{inv_id}  ·  auto-created from deal close"),
    ]


# ── CS ────────────────────────────────────────────────────────────────────────

def customer_onboarded(name: str, arr: str, renewal: str) -> list:
    renewal_str = renewal if renewal and renewal not in ("None", "", "not set") else "not set"
    return [
        _header("🏆 New Customer Onboarded"),
        _fields(
            f"*Name*\n{name}",
            f"*ARR*\n{arr}",
            f"*Renewal*\n{renewal_str}",
            f"*Status*\nactive",
        ),
    ]


def p1_breach_alert(customer: str, issue: str, csm: str = "") -> list:
    csm_str = csm if csm else "@cs_team"
    return [
        _header("🚨 P1 Breach: Immediate Action Required"),
        _fields(
            f"*Customer*\n{customer}",
            f"*Assigned CSM*\n{csm_str}",
        ),
        _quote_llm(issue),
        _context("Health score reduced by 20 points"),
    ]


def p1_breach_unknown(issue: str) -> list:
    return [
        _header("🚨 P1 Breach Reported"),
        _quote_llm(issue),
        _context("@cs_team  ·  customer not identified, follow up needed"),
    ]


# ── Support ───────────────────────────────────────────────────────────────────

def bug_logged(bug_id: int, description: str, priority: str) -> list:
    """Card shown when a NEW bug is filed."""
    sev_emoji = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}.get(priority, "⚫")
    sev_label = {"P0": "Critical", "P1": "High", "P2": "Medium", "P3": "Low"}.get(priority, "")
    return [
        _header(f"{sev_emoji} Bug Filed: {priority} {sev_label}"),
        _section(description),
        _context(f"Bug #{bug_id}"),
        _divider(),
        _actions(
            _btn("✅ Close",    f"close: #{bug_id}", "nexus_close",  style="primary"),
            _btn("📋 All Bugs", "status",            "nexus_status"),
        ),
    ]


def bug_status_card(bug_id: int, description: str, priority: str) -> list:
    """Standalone card for each bug in the status listing."""
    sev_emoji = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}.get(priority, "⚫")
    sev_label = {"P0": "Critical", "P1": "High", "P2": "Medium", "P3": "Low"}.get(priority, "")
    return [
        _header(f"{sev_emoji} {priority} {sev_label}  ·  Bug #{bug_id}"),
        _section(description),
        _divider(),
        _actions(
            _btn("✅ Close", f"close: #{bug_id}", f"nexus_close_{bug_id}", style="primary"),
        ),
    ]


# ── Blog ──────────────────────────────────────────────────────────────────────

def draft_created(draft_id: int, title: str, preview: str, image_url: str = "") -> list:
    snippet = preview[:220] + "…" if len(preview) > 220 else preview
    blocks = []
    if image_url:
        blocks.append({"type": "image", "image_url": image_url, "alt_text": title})
    blocks += [
        _header("✍️ Blog Draft Ready"),
        _section(f"*{title}*"),
        _quote_llm(snippet),
        _context(f"Draft #{draft_id}  ·  ready for review"),
        _divider(),
        _actions(
            _btn("✅ Approve", f"approve #{draft_id}", "nexus_approve", style="primary"),
            _btn("👁 Preview", f"preview: #{draft_id}", "nexus_preview"),
            _btn("❌ Reject",  f"reject #{draft_id}",  "nexus_reject",  style="danger"),
        ),
    ]
    return blocks


def draft_published(draft_id: int, title: str, url: str) -> list:
    return [
        _header("✅ Post Published"),
        _section(f"*{title}*"),
        _context(f"Draft #{draft_id}  ·  {url}"),
    ]


def draft_rejected(draft_id: int, title: str, reason: str = "") -> list:
    return [
        _header("❌ Draft Rejected"),
        _section(f"*{title}*"),
        _context(f"Draft #{draft_id}  ·  {reason or 'no reason given'}"),
    ]


def draft_queue_card(r: dict) -> list:
    """Standalone card for each draft in the content queue listing."""
    row_id = r["id"]
    title  = r.get("title") or r.get("keyword", "Untitled")
    status = r.get("status", "")
    status_emoji = "✍️" if status in ("pending", "draft", "draft_ready") else ("✅" if status == "published" else "❌")
    blocks = [
        _header(f"{status_emoji} Draft #{row_id}"),
        _section(f"*{title}*"),
        _context(f"_{status}_"),
    ]
    if status in ("pending", "draft", "draft_ready"):
        blocks += [
            _divider(),
            _actions(
                _btn("✅ Approve", f"approve #{row_id}", f"nexus_approve_{row_id}", style="primary"),
                _btn("👁 Preview", f"preview: #{row_id}", f"nexus_preview_{row_id}"),
                _btn("❌ Reject",  f"reject #{row_id}",  f"nexus_reject_{row_id}",  style="danger"),
            ),
        ]
    return blocks


# ── GEO ───────────────────────────────────────────────────────────────────────

def geo_score(keyword: str, score: int, reason: str) -> list:
    emoji = "🟢" if score >= 7 else "🟡" if score >= 4 else "🔴"
    label = "High" if score >= 7 else "Medium" if score >= 4 else "Low"
    blocks = [
        _header("📊 GEO Score"),
        _fields(
            f"*Keyword*\n{keyword}",
            f"*Score*\n{emoji} {score}/10  ({label} citability)",
        ),
        _quote_llm(reason),
    ]
    if score < 8:
        blocks += [
            _divider(),
            _actions(
                _btn("💡 Get Improvement Tips", f"geo tips: {keyword}", "nexus_geo_tips"),
            ),
        ]
    return blocks


# ── Infra ─────────────────────────────────────────────────────────────────────

def service_status_card(name: str, url: str, status: str, failures: int) -> list:
    """Standalone card for each service in the status listing."""
    up        = status in ("up", "healthy")
    emoji     = "🟢" if up else "🔴"
    fail_str  = f"\n{failures} consecutive failures" if failures else ""
    safe_name = name[:12].replace(" ", "_").replace("-", "_")
    return [
        _header(f"{emoji} {name}"),
        _fields(
            f"*URL*\n{url}",
            f"*Status*\n_{status}{fail_str}_",
        ),
        _divider(),
        _actions(
            _btn("🔁 Ping", f"ping: {url}", f"nexus_ping_{safe_name}"),
        ),
    ]


def ping_result(url: str, status_code: int, latency_ms: float) -> list:
    emoji = "✅" if status_code < 400 else "⚠️" if status_code < 500 else "🔴"
    label = "OK" if status_code < 400 else "Warning" if status_code < 500 else "Down"
    return [
        _header(f"{emoji} Ping Result"),
        _fields(
            f"*Status*\nHTTP {status_code}  ({label})",
            f"*Latency*\n{latency_ms:.0f}ms",
        ),
        _context(url),
    ]
