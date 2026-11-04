"""
ConversationService — stateful guided-input wizard (modal) for multi-field commands.

When a user types a command without required args, the agent starts a conversation
session that prompts for each field one at a time, validates each answer, then
executes the original command with the collected data.

Usage in any agent handler:

    # At the top of handle_message, before command routing:
    if ConversationService.resume(tenant_id, room_id, sender, "AgentName", text, client):
        return  # wizard handled this message

    # To start a wizard (command called without args):
    ConversationService.start(tenant_id, room_id, sender, "AgentName", "new_lead", client)
    return
"""

import json
import logging
from datetime import datetime, timedelta
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 15

# ── Command schemas ────────────────────────────────────────────────────────────
# Each field: key, prompt, type (text|money|date|url|integer|choice), required,
#             skip_phrase (for optional fields), choices (for type=choice),
#             min/max (for type=integer)

SCHEMAS: dict = {
    # ── SalesAgent ─────────────────────────────────────────────────────────────
    "new_lead": {
        "title": "New Lead",
        "agent": "SalesAgent",
        "fields": [
            {"key": "name",       "prompt": "Lead's full name?",                                "type": "text",    "required": True},
            {"key": "role",       "prompt": "Their role or title?",                             "type": "text",    "required": True},
            {"key": "city",       "prompt": "City? (e.g. Bangalore, Mumbai)",                   "type": "text",    "required": True},
            {"key": "industry",   "prompt": "Industry? (e.g. SaaS, Fintech, Retail)",           "type": "text",    "required": True},
            {"key": "deal_value", "prompt": "Estimated deal value? (e.g. Rs50000, Rs5L) — or type `skip`", "type": "money", "required": False, "skip_phrase": "skip"},
        ],
    },
    "set_commitment": {
        "title": "Set Commitment",
        "agent": "SalesAgent",
        "fields": [
            {"key": "person",   "prompt": "Who made the commitment? (their name)",          "type": "text", "required": True},
            {"key": "action",   "prompt": "What exactly did they commit to?",               "type": "text", "required": True},
            {"key": "deadline", "prompt": "By when? (YYYY-MM-DD, 'today', 'next Friday')", "type": "date", "required": True},
        ],
    },
    "format_message": {
        "title": "Format Message",
        "agent": "SalesAgent",
        "fields": [
            {"key": "message", "prompt": "Paste the message to reformat:",                                           "type": "text",   "required": True},
            {"key": "style",   "prompt": "Format as: executive / casual / technical / formal / sales",             "type": "choice", "required": True,
             "choices": ["executive", "casual", "technical", "formal", "sales"]},
        ],
    },
    # ── CSAgent ────────────────────────────────────────────────────────────────
    "add_customer": {
        "title": "Add Customer",
        "agent": "CSAgent",
        "fields": [
            {"key": "name",         "prompt": "Customer / company name?",                              "type": "text",  "required": True},
            {"key": "arr",          "prompt": "Annual contract value? (e.g. Rs5L, Rs1Cr)",            "type": "money", "required": True},
            {"key": "renewal_date", "prompt": "Renewal date? (YYYY-MM-DD) — or type `skip`",          "type": "date",  "required": False, "skip_phrase": "skip"},
        ],
    },
    "log_nps": {
        "title": "Log NPS",
        "agent": "CSAgent",
        "fields": [
            {"key": "customer", "prompt": "Customer name?",                      "type": "text",    "required": True},
            {"key": "score",    "prompt": "NPS score? (0 – 10)",                 "type": "integer", "required": True,  "min": 0, "max": 10},
            {"key": "note",     "prompt": "Feedback note? — or type `skip`",     "type": "text",    "required": False, "skip_phrase": "skip"},
        ],
    },
    # ── FinanceAgent ───────────────────────────────────────────────────────────
    "add_invoice": {
        "title": "New Invoice",
        "agent": "FinanceAgent",
        "fields": [
            {"key": "vendor",   "prompt": "Vendor / supplier name?",                       "type": "text",  "required": True},
            {"key": "amount",   "prompt": "Invoice amount? (e.g. Rs50000, Rs2L)",         "type": "money", "required": True},
            {"key": "due_date", "prompt": "Due date? (YYYY-MM-DD) — or type `skip`",      "type": "date",  "required": False, "skip_phrase": "skip"},
            {"key": "category", "prompt": "Category? (software / travel / marketing) — or `skip`", "type": "text", "required": False, "skip_phrase": "skip"},
        ],
    },
    "add_expense": {
        "title": "Expense Claim",
        "agent": "FinanceAgent",
        "fields": [
            {"key": "submitter",    "prompt": "Who is submitting? (name or type 'me')",              "type": "text",  "required": True},
            {"key": "amount",       "prompt": "Amount? (e.g. Rs3200, Rs500)",                       "type": "money", "required": True},
            {"key": "category",     "prompt": "Category? (travel / meals / equipment / other)",     "type": "text",  "required": True},
            {"key": "expense_date", "prompt": "Date of expense? (YYYY-MM-DD) — or `today`",        "type": "date",  "required": False, "skip_phrase": "today"},
        ],
    },
    "reject_invoice": {
        "title": "Reject Invoice",
        "agent": "FinanceAgent",
        "fields": [
            {"key": "invoice_id", "prompt": "Invoice ID? (e.g. invoice-042 or just 42)", "type": "text", "required": True},
            {"key": "reason",     "prompt": "Reason for rejection?",                     "type": "text", "required": True},
        ],
    },
    # ── InfraAgent ────────────────────────────────────────────────────────────
    "add_service": {
        "title": "Monitor New Service",
        "agent": "InfraAgent",
        "fields": [
            {"key": "name", "prompt": "Service name? (e.g. api-server, payment-gateway)",          "type": "text", "required": True},
            {"key": "url",  "prompt": "Health check URL? (e.g. https://api.example.com/health)",   "type": "url",  "required": True},
        ],
    },
    # ── BlogAgent ─────────────────────────────────────────────────────────────
    "draft_post": {
        "title": "Draft Blog Post",
        "agent": "BlogAgent",
        "fields": [
            {"key": "topic", "prompt": "Topic or target keyword for the blog post?",                             "type": "text", "required": True},
            {"key": "geo",   "prompt": "Target geography? (e.g. Bangalore, India) — or `skip`",                 "type": "text", "required": False, "skip_phrase": "skip"},
            {"key": "tone",  "prompt": "Tone? (informative / persuasive / technical) — or `skip`",             "type": "text", "required": False, "skip_phrase": "skip"},
        ],
    },
}


# ── Public API ─────────────────────────────────────────────────────────────────

def start(tenant_id: str, room_id: str, sender: str, agent: str,
          command: str, client) -> bool:
    """
    Start a new conversation wizard for `command`.
    Posts the first field prompt to the room.
    Returns True if wizard started, False if command has no schema.
    """
    schema = SCHEMAS.get(command)
    if not schema:
        return False

    expires_at = datetime.utcnow() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    try:
        with db_cursor() as cur:
            # Cancel any existing active session for this user/room/agent
            cur.execute(
                """
                UPDATE conversation_sessions SET status='cancelled'
                WHERE tenant_id=%s AND room_id=%s AND sender=%s
                  AND agent=%s AND status='active'
                """,
                (tenant_id, room_id, sender, agent)
            )
            cur.execute(
                """
                INSERT INTO conversation_sessions
                    (tenant_id, room_id, sender, agent, command, collected, step, status, expires_at)
                VALUES (%s, %s, %s, %s, %s, '{}', 0, 'active', %s)
                """,
                (tenant_id, room_id, sender, agent, command, expires_at)
            )
    except Exception as e:
        logger.error(f"ConversationService.start failed: {e}")
        return False

    total  = len(schema["fields"])
    first  = schema["fields"][0]
    opt_hint = "" if first.get("required", True) else f" _(optional — type `{first.get('skip_phrase', 'skip')}` to skip)_"

    client.post_message(
        f"*{schema['title']}* — 1 of {total}\n"
        f"{first['prompt']}{opt_hint}\n"
        f"_(Type `cancel` at any time to abort)_"
    )
    return True


def resume(tenant_id: str, room_id: str, sender: str, agent: str,
           text: str, client) -> bool:
    """
    Check for an active session and process `text` as the next field answer.
    Returns True if handled (caller should return early from handle_message).
    """
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, command, collected, step FROM conversation_sessions
                WHERE tenant_id=%s AND room_id=%s AND sender=%s AND agent=%s
                  AND status='active' AND expires_at > NOW()
                ORDER BY created_at DESC LIMIT 1
                """,
                (tenant_id, room_id, sender, agent)
            )
            session = cur.fetchone()
    except Exception as e:
        logger.error(f"ConversationService.resume DB error: {e}")
        return False

    if not session:
        return False

    text = text.strip()

    if text.lower() in ("cancel", "abort", "quit", "stop"):
        _cancel(session["id"])
        client.post_message("Cancelled. No changes were made.")
        return True

    schema = SCHEMAS.get(session["command"])
    if not schema:
        return False

    step      = session["step"]
    fields    = schema["fields"]
    collected = dict(session["collected"] or {})

    if step >= len(fields):
        _complete(session["id"], collected)
        return False

    field = fields[step]
    skip  = field.get("skip_phrase", "skip")

    # Optional field — accept skip
    if not field.get("required", True) and text.lower() in (skip.lower(), "skip"):
        collected[field["key"]] = None
    else:
        err = _validate_field(field, text)
        if err:
            client.post_message(f"❌ {err}\n\n{field['prompt']}")
            return True
        collected[field["key"]] = text

    next_step = step + 1

    if next_step >= len(fields):
        _complete(session["id"], collected)
        _execute(tenant_id, session["command"], collected, sender, client)
    else:
        _save(session["id"], next_step, collected)
        nf       = fields[next_step]
        num      = next_step + 1
        total    = len(fields)
        opt_hint = "" if nf.get("required", True) else f" _(optional — type `{nf.get('skip_phrase', 'skip')}` to skip)_"
        client.post_message(f"Step {num} of {total}\n{nf['prompt']}{opt_hint}")

    return True


# ── Internals ──────────────────────────────────────────────────────────────────

def _validate_field(field: dict, value: str) -> str | None:
    from app.Services.ValidationService import (
        validate_money, validate_date, validate_url, validate_integer
    )
    ftype = field.get("type", "text")
    if ftype == "money":
        _, err = validate_money(value)
        return err
    if ftype == "date":
        _, err = validate_date(value)
        return err
    if ftype == "url":
        _, err = validate_url(value)
        return err
    if ftype == "integer":
        _, err = validate_integer(value, field.get("min"), field.get("max"))
        return err
    if ftype == "choice":
        choices = field.get("choices", [])
        if value.lower() not in [c.lower() for c in choices]:
            return f"Must be one of: {', '.join(choices)}"
    return None


def _execute(tenant_id: str, command: str, data: dict, sender: str, client):
    """Lazy-import and call the data-variant command function."""
    try:
        if command == "new_lead":
            from agents.sales_agent.commands import cmd_new_lead_data
            cmd_new_lead_data(client, data, sender, tenant_id)

        elif command == "set_commitment":
            from agents.sales_agent.commands import cmd_set_commitment_data
            cmd_set_commitment_data(client, data, sender, tenant_id)

        elif command == "format_message":
            from agents.sales_agent.commands import cmd_format_data
            cmd_format_data(client, data, sender, tenant_id)

        elif command == "add_customer":
            from agents.cs_agent.handlers import cmd_add_customer_data
            cmd_add_customer_data(client, data, sender, tenant_id)

        elif command == "log_nps":
            from agents.cs_agent.handlers import cmd_log_nps_data
            cmd_log_nps_data(client, data, sender, tenant_id)

        elif command == "add_invoice":
            from agents.finance_agent.handlers import cmd_invoice_data
            cmd_invoice_data(client, data, sender, tenant_id)

        elif command == "add_expense":
            from agents.finance_agent.handlers import cmd_expense_data
            cmd_expense_data(client, data, sender, tenant_id)

        elif command == "reject_invoice":
            from agents.finance_agent.handlers import cmd_reject_invoice_data
            cmd_reject_invoice_data(client, data, sender, tenant_id)

        elif command == "add_service":
            from agents.infra_agent.handlers import cmd_add_service_data
            cmd_add_service_data(client, data, sender, tenant_id)

        elif command == "draft_post":
            from agents.blog_agent.handlers import cmd_draft_post_data
            cmd_draft_post_data(client, data, sender, tenant_id)

        else:
            client.post_message(f"❌ Unknown command '{command}'. Please try again.")

    except Exception as e:
        logger.error(f"ConversationService._execute [{command}] failed: {e}", exc_info=True)
        client.post_message("❌ Something went wrong. Please try the command again.")


def _save(session_id: int, step: int, collected: dict):
    try:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE conversation_sessions SET step=%s, collected=%s WHERE id=%s",
                (step, json.dumps(collected), session_id)
            )
    except Exception as e:
        logger.error(f"ConversationService._save failed: {e}")


def _complete(session_id: int, collected: dict):
    try:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE conversation_sessions SET status='completed', collected=%s WHERE id=%s",
                (json.dumps(collected), session_id)
            )
    except Exception as e:
        logger.error(f"ConversationService._complete failed: {e}")


def _cancel(session_id: int):
    try:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE conversation_sessions SET status='cancelled' WHERE id=%s",
                (session_id,)
            )
    except Exception as e:
        logger.error(f"ConversationService._cancel failed: {e}")
