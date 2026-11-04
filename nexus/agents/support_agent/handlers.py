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

    if not text or sender in ("SupportAgent", "NEXUS"):
        return

    if is_mention:
        clean = text.split(">", 1)[-1].strip() if ">" in text else text
        for p in ["@SupportAgent ", "@supportagent "]:
            if clean.lower().startswith(p):
                clean = clean[len(p):]
                break
        route_command(client, clean, sender)
    else:
        # Passive scan for bug language
        if any(kw in text.lower() for kw in BUG_KEYWORDS):
            passive_triage(client, text, sender)


def route_command(client, text: str, sender: str):
    t = text.lower().strip()
    if t.startswith("bug:"):
        triage_bug(client, text.split(":", 1)[1].strip(), sender)
    elif t.startswith("status"):
        show_status(client)
    elif t.startswith("close:"):
        close_bug(client, t.split(":", 1)[1].strip(), sender)
    elif t.startswith("bugs:"):
        filter_bugs(client, t.split(":", 1)[1].strip())
    elif t.startswith("patterns"):
        _cmd_patterns(client)
    elif t.startswith("memory"):
        _cmd_memory(client)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, t.split(":", 1)[1].strip())
    else:
        client.post_message(
            "Commands:\n"
            "- `@SupportAgent bug: description`\n"
            "- `@SupportAgent status`\n"
            "- `@SupportAgent close: #bug-id`\n"
            "- `@SupportAgent bugs: open P0`\n"
            "- `@SupportAgent patterns` / `memory` / `knowledge: keyword`"
        )


def _cmd_patterns(client):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("SupportAgent")
    patterns = mem.get_patterns(min_occurrences=2)
    if not patterns:
        client.post_message("No patterns detected yet.")
        return
    lines = ["*SupportAgent learned patterns:*\n"]
    for p in patterns[:5]:
        lines.append(f"- {p['description']} (seen {p['occurrences']}x)")
    client.post_message("\n".join(lines))


def _cmd_memory(client):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("SupportAgent")
    events = mem.search_knowledge("")
    if not events:
        client.post_message("No memory events recorded yet.")
        return
    lines = ["*SupportAgent recent memory:*\n"]
    for ev in events[:5]:
        lines.append(f"- [{ev['event_type']}] {str(ev['context'] or '')[:80]}")
    client.post_message("\n".join(lines))


def _cmd_knowledge(client, query: str):
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


def triage_bug(client, description: str, sender: str):
    try:
        result = llm.complete(SEVERITY_PROMPT.format(report=description), json_mode=True)
        data = json.loads(result)
    except Exception:
        data = {"severity": "P2", "summary": description[:100]}

    sev = data.get("severity", "P2")
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO bugs (description, severity, reported_by, source) "
            "VALUES (%s, %s, %s, 'manual') RETURNING id",
            (description, sev, f"@{sender}")
        )
        bug_id = cur.fetchone()["id"]

    emoji = {"P0": "[P0-CRITICAL]", "P1": "[P1]", "P2": "[P2]", "P3": "[P3]"}.get(sev, "[P2]")
    client.post_message(
        f"{emoji} *Bug #{bug_id} -- {sev}*\n"
        f"{data.get('summary', description)}\n"
        f"Reported by: @{sender}"
    )

    # Fire P1_BREACH signal to CSAgent for P0/P1 bugs
    if sev in ("P0", "P1"):
        issue_text = data.get("summary", description[:60]).replace(" ", "_")
        client.safe_signal(
            "CSAgent",
            f"P1_BREACH: customer=Unknown issue={issue_text}"
        )


def passive_triage(client, text: str, sender: str):
    if len(text) < 20:
        return
    triage_bug(client, text, sender)


def show_status(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, severity, description, status, created_at "
            "FROM bugs WHERE status='open' ORDER BY severity, created_at LIMIT 20"
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("No open bugs.")
        return

    lines = ["*Open bugs:*\n"]
    for r in rows:
        lines.append(f"- #{r['id']} [{r['severity']}] {r['description'][:60]}...")
    client.post_message("\n".join(lines))


def close_bug(client, ref: str, sender: str):
    bug_id = ref.lstrip("#").strip()
    with db_cursor() as cur:
        cur.execute(
            "UPDATE bugs SET status='closed', resolved_at=NOW() WHERE id=%s RETURNING id",
            (bug_id,)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Bug #{bug_id} closed by @{sender}")
    else:
        client.post_message(f"Bug #{bug_id} not found.")


def filter_bugs(client, filter_str: str):
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
                "WHERE status=%s AND severity=%s ORDER BY created_at DESC LIMIT 15",
                (status, sev)
            )
        else:
            cur.execute(
                "SELECT id, severity, description FROM bugs "
                "WHERE status=%s ORDER BY severity, created_at DESC LIMIT 15",
                (status,)
            )
        rows = cur.fetchall()

    if not rows:
        client.post_message(f"No {status} bugs{' at ' + sev if sev else ''}.")
        return

    lines = [f"*{status.title()} bugs{' -- ' + sev if sev else ''}:*\n"]
    for r in rows:
        lines.append(f"- #{r['id']} [{r['severity']}] {r['description'][:70]}")
    client.post_message("\n".join(lines))
