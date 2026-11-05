import json
import logging
import requests as req
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient(agent="support")

BUG_KEYWORDS = [
    "crash", "crashing", "broken", "error", "exception", "fail", "failing",
    "bug", "down", "not working", "500", "timeout"
]

SEVERITY_PROMPT = """Classify the severity of this bug report:
P0 = production down / data loss / security breach
P1 = major feature broken, blocks users
P2 = degraded experience, workaround exists
P3 = minor issue, cosmetic

Report: "{report}"

Reply with JSON only: {{"severity": "P0"|"P1"|"P2"|"P3", "summary": "one line summary", "suggested_owner": null}}"""


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)
    room_id    = payload.get("room_id", client.room_id)
    tenant_id  = client.tenant_id

    if sender in ("SupportAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return

    if is_mention:
        clean = text.split(">", 1)[-1].strip() if text.startswith("<@") else text
        for p in ["@SupportAgent ", "@supportagent "]:
            if clean.lower().startswith(p):
                clean = clean[len(p):]
                break

        from app.Services import ConversationService
        if ConversationService.resume(tenant_id, room_id, sender, "SupportAgent", clean, client):
            return

        route_command(client, clean, sender, tenant_id, room_id)
    else:
        # Passive scan for bug language
        if any(kw in text.lower() for kw in BUG_KEYWORDS):
            from app.Services import ConversationService
            if ConversationService.resume(tenant_id, room_id, sender, "SupportAgent", text, client):
                return
            passive_triage(client, text, sender, tenant_id)


def route_command(client, text: str, sender: str, tenant_id: str, room_id: str):
    t = text.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "SupportAgent", _cmd_key, sender)
    if t.startswith("bug:"):
        triage_bug(client, text.split(":", 1)[1].strip(), sender, tenant_id)
    elif t.startswith("status"):
        show_status(client, tenant_id)
    elif t.startswith("close:"):
        close_bug(client, t.split(":", 1)[1].strip(), sender, tenant_id)
    elif t.startswith("bugs:"):
        filter_bugs(client, t.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("patterns"):
        _cmd_patterns(client, tenant_id)
    elif t.startswith("memory"):
        _cmd_memory(client, tenant_id)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, t.split(":", 1)[1].strip(), tenant_id)
    else:
        from app.Services.BlockBuilder import _section
        client.post_blocks([
            _section("*SupportAgent: Bug Triage*\n"
                     "1. `bug: description, severity: P1`\n"
                     "2. `status`\n"
                     "3. `close: #42`\n"
                     "4. `bugs: open P0`\n"
                     "5. `patterns` / `memory` / `knowledge: topic`")
        ], fallback_text="SupportAgent commands")


def _cmd_patterns(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("SupportAgent")
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
    mem = AgentMemory("SupportAgent")
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
    mem = AgentMemory("SupportAgent")
    results = mem.search_knowledge(query)
    if not results:
        client.post_message(f"No memory found for '{query}'.")
        return
    lines = [f"*Knowledge search: '{query}'*\n"]
    for r in results[:5]:
        lines.append(f"- [{r['event_type']}] {str(r['outcome'] or r['context'] or '')[:100]}")
    client.post_message("\n".join(lines))


def triage_bug(client, description: str, sender: str, tenant_id: str):
    from app.Services.FeatureGateService import FeatureGateService
    if not FeatureGateService.gate_llm(tenant_id, client):
        return
    try:
        result = llm.complete(SEVERITY_PROMPT.format(report=description), json_mode=True)
        data = json.loads(result)
    except Exception:
        data = {"severity": "P2", "summary": description[:100]}

    sev = data.get("severity", "P2")
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO bugs (tenant_id, description, severity, reported_by, source) "
            "VALUES (%s, %s, %s, %s, 'manual') RETURNING id",
            (tenant_id, description, sev, f"@{sender}")
        )
        bug_id = cur.fetchone()["id"]

    from app.Services.BlockBuilder import bug_logged
    client.post_blocks(
        bug_logged(bug_id, data.get("summary", description), sev),
        fallback_text=f"Bug #{bug_id} logged ({sev})"
    )

    # Fire P1_BREACH signal to CSAgent for P0/P1 bugs
    if sev in ("P0", "P1"):
        issue_text = data.get("summary", description[:60]).replace(" ", "_")
        client.safe_signal(
            "CSAgent",
            f"P1_BREACH: customer=Unknown issue={issue_text}"
        )


def passive_triage(client, text: str, sender: str, tenant_id: str):
    if len(text) < 20:
        return
    triage_bug(client, text, sender, tenant_id)


def show_status(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, severity, description, status, created_at "
            "FROM bugs WHERE status='open' AND tenant_id=%s ORDER BY severity, created_at LIMIT 20",
            (tenant_id,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("✅ No open bugs.")
        return

    sev_emoji = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}
    lines = [f"*Open bugs ({len(rows)})*\n"]
    for r in rows:
        emoji = sev_emoji.get(r["severity"], "⚫")
        lines.append(f"{emoji} `#{r['id']}` *{r['severity']}* {r['description'][:60]}")
    client.post_message("\n".join(lines))


def close_bug(client, ref: str, sender: str, tenant_id: str):
    bug_id = ref.lstrip("#").strip()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE bugs SET status='closed', resolved_at=NOW() WHERE id=%s AND tenant_id=%s RETURNING id",
            (bug_id, tenant_id)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"✅ Bug #{bug_id} closed")
    else:
        client.post_message(f"Bug #{bug_id} not found.")


def filter_bugs(client, filter_str: str, tenant_id: str):
    parts = filter_str.strip().split()
    status = "open"
    sev = None
    for p in parts:
        if p in ("open", "closed"):
            status = p
        if p in ("P0", "P1", "P2", "P3", "p0", "p1", "p2", "p3"):
            sev = p.upper()

    with db_cursor() as cur:
        if sev:
            cur.execute(
                "SELECT id, severity, description FROM bugs "
                "WHERE status=%s AND severity=%s AND tenant_id=%s ORDER BY created_at DESC LIMIT 15",
                (status, sev, tenant_id)
            )
        else:
            cur.execute(
                "SELECT id, severity, description FROM bugs "
                "WHERE status=%s AND tenant_id=%s ORDER BY severity, created_at DESC LIMIT 15",
                (status, tenant_id)
            )
        rows = cur.fetchall()

    if not rows:
        client.post_message(f"No {status} bugs{' at ' + sev if sev else ''}.")
        return

    sev_emoji = {"P0": "🚨", "P1": "🔴", "P2": "🟡", "P3": "🔵"}
    label = f"{status.title()} bugs" + (f" ({sev})" if sev else "")
    lines = [f"*{label} ({len(rows)})*\n"]
    for r in rows:
        emoji = sev_emoji.get(r["severity"], "⚫")
        lines.append(f"{emoji} `#{r['id']}` *{r['severity']}* {r['description'][:70]}")
    client.post_message("\n".join(lines))
