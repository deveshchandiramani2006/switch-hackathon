import logging
from .commitment import detect_commitment, detect_resolution
from .commands import (
    cmd_new_lead, cmd_pipeline, cmd_follow_up,
    cmd_format, cmd_won, cmd_lost,
    cmd_set_commitment, cmd_stale_leads, cmd_lead_card
)

logger = logging.getLogger(__name__)


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    room_id    = payload.get("room_id", client.room_id)
    is_mention = payload.get("is_mention", False)
    tenant_id  = client.tenant_id

    if sender in ("SalesAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return

    # Cross-agent signal from GeoSEOAgent
    if text.startswith("GEO_SIGNAL:"):
        _handle_geo_signal(client, text, tenant_id)
        return

    if is_mention:
        clean = text.split(">", 1)[-1].strip() if ">" in text else text
        for prefix in ["@SalesAgent ", "@salesagent "]:
            if clean.lower().startswith(prefix.lower()):
                clean = clean[len(prefix):]
                break
        # Resume active modal session first
        from app.Services import ConversationService
        if ConversationService.resume(tenant_id, room_id, sender, "SalesAgent", clean, client):
            return
        route_command(client, clean, sender, tenant_id, room_id)
    else:
        from app.Services import ConversationService
        if ConversationService.resume(tenant_id, room_id, sender, "SalesAgent", text, client):
            return
        detect_commitment(client, text, sender, tenant_id)
        detect_resolution(client, text, sender, tenant_id)


def route_command(client, text: str, sender: str, tenant_id: str, room_id: str):
    t = text.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "SalesAgent", _cmd_key, sender)
    from app.Services import ConversationService

    if t in ("new lead", "new lead:"):
        ConversationService.start(tenant_id, room_id, sender, "SalesAgent", "new_lead", client)
    elif t.startswith("new lead:") and len(t) > len("new lead:"):
        cmd_new_lead(client, text, sender, tenant_id)
    elif t.startswith("pipeline"):
        cmd_pipeline(client, text, sender, tenant_id)
    elif t.startswith("follow up:"):
        cmd_follow_up(client, text, sender, tenant_id)
    elif t in ("format", "format:"):
        ConversationService.start(tenant_id, room_id, sender, "SalesAgent", "format_message", client)
    elif t.startswith("format:") and len(t) > len("format:"):
        cmd_format(client, text, sender, tenant_id)
    elif t.startswith("won:"):
        cmd_won(client, text, sender, tenant_id)
    elif t.startswith("lost:"):
        cmd_lost(client, text, sender, tenant_id)
    elif t in ("set commitment", "set commitment:"):
        ConversationService.start(tenant_id, room_id, sender, "SalesAgent", "set_commitment", client)
    elif t.startswith("set commitment:") and len(t) > len("set commitment:"):
        cmd_set_commitment(client, text, sender, tenant_id)
    elif t.startswith("stale"):
        cmd_stale_leads(client, sender, tenant_id)
    elif t.startswith("lead:"):
        cmd_lead_card(client, text, sender, tenant_id)
    elif t.startswith("patterns"):
        _cmd_patterns(client, tenant_id)
    elif t.startswith("memory"):
        _cmd_memory(client, tenant_id)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, text.split(":", 1)[1].strip(), tenant_id)
    else:
        client.post_message(
            "Commands:\n"
            "- `@SalesAgent new lead` — guided form\n"
            "- `@SalesAgent new lead: Name, Role, City, Industry, Value` — quick add\n"
            "- `@SalesAgent pipeline`\n"
            "- `@SalesAgent lead: Name`\n"
            "- `@SalesAgent follow up: Name`\n"
            "- `@SalesAgent format` — guided form\n"
            "- `@SalesAgent won: Name` / `lost: Name -- reason: ...`\n"
            "- `@SalesAgent set commitment` — guided form\n"
            "- `@SalesAgent stale leads`\n"
            "- `@SalesAgent patterns` / `memory` / `knowledge: keyword`"
        )


def _handle_geo_signal(client, text: str, tenant_id: str):
    """GEO_SIGNAL: keyword=X geo=Y volume=Z trend=T"""
    from app.Services.DatabaseService import db_cursor
    parts = {}
    for p in text.replace("GEO_SIGNAL:", "").strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v

    keyword = parts.get("keyword", "").replace("_", " ")
    geo     = parts.get("geo", "").replace("_", " ")
    volume  = parts.get("volume", "?")
    trend   = parts.get("trend", "0")

    # Count leads in that geo area filtered by tenant
    lead_count = 0
    if geo:
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM leads "
                    "WHERE tenant_id = %s AND LOWER(city) LIKE LOWER(%s) "
                    "AND stage NOT IN ('Closed-Won','Closed-Lost')",
                    (tenant_id, f"%{geo}%")
                )
                lead_count = cur.fetchone()["cnt"]
        except Exception:
            pass

    client.post_message(
        f"*Geo opportunity:* {keyword} trending +{trend}% in {geo}.\n"
        f"Volume: {volume}/mo | {lead_count} leads in that area.\n"
        f"Want me to draft geo-targeted outreach? Reply `@SalesAgent follow up: <lead name>`"
    )


def _cmd_patterns(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("SalesAgent")
    patterns = mem.get_patterns(min_occurrences=2)
    if not patterns:
        client.post_message("No patterns detected yet.")
        return
    lines = ["*SalesAgent learned patterns:*\n"]
    for p in patterns[:5]:
        lines.append(f"- {p['description']} (seen {p['occurrences']}x, confidence {p['confidence']:.0%})")
    client.post_message("\n".join(lines))


def _cmd_memory(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("SalesAgent")
    events = mem.search_knowledge("")
    if not events:
        client.post_message("No memory events recorded yet.")
        return
    lines = ["*SalesAgent recent memory:*\n"]
    for ev in events[:5]:
        lines.append(f"- [{ev['event_type']}] {str(ev['context'] or '')[:80]}")
    client.post_message("\n".join(lines))


def _cmd_knowledge(client, query: str, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("SalesAgent")
    results = mem.search_knowledge(query)
    if not results:
        client.post_message(f"No memory found for '{query}'.")
        return
    lines = [f"*Knowledge search: '{query}'*\n"]
    for r in results[:5]:
        lines.append(f"- [{r['event_type']}] {str(r['outcome'] or r['context'] or '')[:100]}")
    client.post_message("\n".join(lines))
