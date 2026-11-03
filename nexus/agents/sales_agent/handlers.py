import logging
from .commitment import detect_commitment
from .commands import (
    cmd_new_lead, cmd_pipeline, cmd_follow_up,
    cmd_format, cmd_won, cmd_lost,
    cmd_set_commitment, cmd_stale_leads, cmd_lead_card
)

logger = logging.getLogger(__name__)


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)

    if not text or sender in ("SalesAgent", "NEXUS"):
        return

    if is_mention:
        # Strip @SalesAgent prefix
        clean = text.split(">", 1)[-1].strip() if ">" in text else text
        for prefix in ["@SalesAgent ", "@salesagent "]:
            if clean.lower().startswith(prefix.lower()):
                clean = clean[len(prefix):]
                break
        route_command(client, clean, sender)
    else:
        detect_commitment(client, text, sender)


def route_command(client, text: str, sender: str):
    t = text.lower().strip()

    if t.startswith("new lead:"):
        cmd_new_lead(client, text, sender)
    elif t.startswith("pipeline"):
        cmd_pipeline(client, text, sender)
    elif t.startswith("follow up:"):
        cmd_follow_up(client, text, sender)
    elif t.startswith("format:"):
        cmd_format(client, text, sender)
    elif t.startswith("won:"):
        cmd_won(client, text, sender)
    elif t.startswith("lost:"):
        cmd_lost(client, text, sender)
    elif t.startswith("set commitment:"):
        cmd_set_commitment(client, text, sender)
    elif t.startswith("stale"):
        cmd_stale_leads(client, sender)
    elif t.startswith("lead:"):
        cmd_lead_card(client, text, sender)
    else:
        client.post_message(
            "Commands:\n"
            "- `@SalesAgent new lead: Name, Role, City, Industry, Value`\n"
            "- `@SalesAgent pipeline`\n"
            "- `@SalesAgent lead: Name`\n"
            "- `@SalesAgent follow up: Name`\n"
            "- `@SalesAgent format: [msg] as: executive`\n"
            "- `@SalesAgent won: Name` / `lost: Name -- reason: ...`\n"
            "- `@SalesAgent set commitment: Name will do X by Date`\n"
            "- `@SalesAgent stale leads`"
        )
