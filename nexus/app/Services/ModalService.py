"""
Slack modal definitions and submission routing for /nexus slash command.

Flow:
  /nexus <command>  →  open_modal()  →  Slack modal pops up
  User submits      →  handle_submission()  →  calls the right agent handler
"""
import json
import logging

logger = logging.getLogger(__name__)


# ── Block builders ─────────────────────────────────────────────────────────────

def _text(block_id, label, placeholder="", optional=False, multiline=False, hint=None):
    block = {
        "type": "input",
        "block_id": block_id,
        "optional": optional,
        "label": {"type": "plain_text", "text": label},
        "element": {
            "type": "plain_text_input",
            "action_id": "value",
            "multiline": multiline,
        },
    }
    if placeholder:
        block["element"]["placeholder"] = {"type": "plain_text", "text": placeholder}
    if hint:
        block["hint"] = {"type": "plain_text", "text": hint}
    return block


def _date(block_id, label, optional=True):
    return {
        "type": "input",
        "block_id": block_id,
        "optional": optional,
        "label": {"type": "plain_text", "text": label},
        "element": {
            "type": "datepicker",
            "action_id": "value",
            "placeholder": {"type": "plain_text", "text": "Pick a date"},
        },
    }


def _select(block_id, label, options):
    return {
        "type": "input",
        "block_id": block_id,
        "label": {"type": "plain_text", "text": label},
        "element": {
            "type": "static_select",
            "action_id": "value",
            "options": [
                {"text": {"type": "plain_text", "text": o}, "value": o}
                for o in options
            ],
        },
    }


# ── Modal definitions ──────────────────────────────────────────────────────────

MODALS = {
    "modal_add_customer": {
        "title": "Add Customer",
        "agent": "CSAgent",
        "blocks": [
            _text("name",         "Company name",           "Acme Corp"),
            _text("arr",          "Annual contract value",  "Rs5L",    hint="e.g. Rs5L, Rs1Cr, Rs500K"),
            _date("renewal_date", "Renewal date"),
        ],
    },
    "modal_new_lead": {
        "title": "New Lead",
        "agent": "SalesAgent",
        "blocks": [
            _text("name",        "Full name",    "Priya Sharma"),
            _text("role",        "Role / title", "CTO"),
            _text("city",        "City",         "Mumbai"),
            _text("industry",    "Industry",     "Fintech"),
            _text("deal_value",  "Deal value",   "Rs2L", hint="e.g. Rs2L, Rs500K"),
        ],
    },
    "modal_log_nps": {
        "title": "Log NPS Score",
        "agent": "CSAgent",
        "blocks": [
            _text("customer", "Customer name",   "Acme Corp"),
            _text("score",    "NPS score (0-10)", "9"),
            _text("note",     "Feedback note",   "They loved onboarding", optional=True, multiline=True),
        ],
    },
    "modal_health_check": {
        "title": "Customer Health",
        "agent": "CSAgent",
        "blocks": [
            _text("name", "Customer name", "Acme Corp"),
        ],
    },
    "modal_expansion": {
        "title": "Expansion Opportunities",
        "agent": "CSAgent",
        "blocks": [
            _text("name", "Customer name", "Acme Corp"),
        ],
    },
    "modal_qbr": {
        "title": "QBR Agenda",
        "agent": "CSAgent",
        "blocks": [
            _text("name", "Customer name", "Acme Corp"),
        ],
    },
    "modal_add_invoice": {
        "title": "New Invoice",
        "agent": "FinanceAgent",
        "blocks": [
            _text("vendor",   "Vendor name", "AWS"),
            _text("amount",   "Amount",      "Rs50K", hint="e.g. Rs50K, Rs1L"),
            _date("due_date", "Due date"),
            _text("category", "Category",   "software", optional=True,
                  hint="software / travel / marketing / other"),
        ],
    },
    "modal_add_expense": {
        "title": "Expense Claim",
        "agent": "FinanceAgent",
        "blocks": [
            _text("submitter",    "Your name", "Devesh"),
            _text("amount",       "Amount",    "Rs3200", hint="e.g. Rs3200, Rs500"),
            _select("category",   "Category",  ["travel", "meals", "equipment", "marketing", "other"]),
            _date("expense_date", "Date of expense"),
        ],
    },
    "modal_add_service": {
        "title": "Monitor Service",
        "agent": "InfraAgent",
        "blocks": [
            _text("name", "Service name",     "api-server"),
            _text("url",  "Health check URL", "https://api.example.com/health"),
        ],
    },
    "modal_draft_post": {
        "title": "Draft Blog Post",
        "agent": "BlogAgent",
        "blocks": [
            _text("topic", "Topic / keyword",    "AI for SaaS startups"),
            _text("geo",   "Target geography",   "Bangalore, India", optional=True),
        ],
    },
    "modal_set_commitment": {
        "title": "Set Commitment",
        "agent": "SalesAgent",
        "blocks": [
            _text("lead",       "Lead name",   "Priya Sharma"),
            _text("commitment", "Commitment",  "Send proposal by Friday", multiline=True),
            _date("due_date",   "Due date",    optional=True),
        ],
    },
    "modal_log_bug": {
        "title": "Log Bug",
        "agent": "SupportAgent",
        "blocks": [
            _text("description", "Bug description", "Payment fails on checkout for Indian cards",
                  multiline=True),
            _select("severity", "Severity", ["P0: production down", "P1: major feature broken",
                                             "P2: degraded, workaround exists", "P3: minor / cosmetic"]),
        ],
    },
    "modal_reject_invoice": {
        "title": "Reject Invoice",
        "agent": "FinanceAgent",
        "blocks": [
            _text("invoice_id", "Invoice ID", "42"),
            _text("reason",     "Reason for rejection", "Duplicate invoice"),
        ],
    },
    "modal_lost_lead": {
        "title": "Close Lost Deal",
        "agent": "SalesAgent",
        "blocks": [
            _text("name",   "Lead name",      "Priya Sharma"),
            _text("reason", "Lost reason",    "Budget", hint="e.g. budget, timing, competitor, no response"),
        ],
    },
    "modal_won_lead": {
        "title": "Mark Deal Won",
        "agent": "SalesAgent",
        "blocks": [
            _text("name", "Lead name", "Priya Sharma"),
        ],
    },
    "modal_followup": {
        "title": "Draft Follow-Up",
        "agent": "SalesAgent",
        "blocks": [
            _text("name", "Lead name", "Priya Sharma"),
        ],
    },
    "modal_approve_invoice": {
        "title": "Approve Invoice",
        "agent": "FinanceAgent",
        "blocks": [
            _text("invoice_id", "Invoice ID", "42"),
        ],
    },
    "modal_close_bug": {
        "title": "Close Bug",
        "agent": "SupportAgent",
        "blocks": [
            _text("bug_id", "Bug ID", "42", hint="e.g. 42 or #42"),
        ],
    },
    "modal_track_keyword": {
        "title": "Track Keyword",
        "agent": "GeoSEOAgent",
        "blocks": [
            _text("keyword", "Keyword or phrase", "best CRM for Indian startups"),
        ],
    },
}

# Maps /nexus-* slash command → modal callback_id
SLASH_ROUTE = {
    "/nexus-customer":   "modal_add_customer",
    "/nexus-lead":       "modal_new_lead",
    "/new-lead":         "modal_new_lead",
    "/nexus-lost":       "modal_lost_lead",
    "/nexus-commitment": "modal_set_commitment",
    "/nexus-nps":        "modal_log_nps",
    "/nexus-health":     "modal_health_check",
    "/nexus-expansion":  "modal_expansion",
    "/nexus-qbr":        "modal_qbr",
    "/nexus-invoice":    "modal_add_invoice",
    "/nexus-expense":    "modal_add_expense",
    "/nexus-reject":     "modal_reject_invoice",
    "/nexus-bug":        "modal_log_bug",
    "/nexus-service":    "modal_add_service",
    "/nexus-draft":      "modal_draft_post",
    "/nexus-won":        "modal_won_lead",
    "/nexus-followup":   "modal_followup",
    "/nexus-approve":    "modal_approve_invoice",
    "/nexus-close":      "modal_close_bug",
    "/nexus-track":      "modal_track_keyword",
}

HELP_TEXT = (
    "*NEXUS slash commands (type any to open a form):*\n"
    "1. `/nexus-customer` add customer\n"
    "2. `/nexus-lead` new sales lead\n"
    "3. `/nexus-lost` close lost deal\n"
    "4. `/nexus-commitment` set commitment\n"
    "5. `/nexus-nps` log NPS score\n"
    "6. `/nexus-health` customer health\n"
    "7. `/nexus-expansion` expansion opportunities\n"
    "8. `/nexus-qbr` QBR agenda\n"
    "9. `/nexus-invoice` new invoice\n"
    "10. `/nexus-expense` expense claim\n"
    "11. `/nexus-reject` reject invoice\n"
    "12. `/nexus-bug` log bug\n"
    "13. `/nexus-service` monitor service\n"
    "14. `/nexus-draft` draft blog post\n"
    "15. `/nexus-won` mark deal won\n"
    "16. `/nexus-followup` draft follow-up message\n"
    "17. `/nexus-approve` approve invoice\n"
    "18. `/nexus-close` close bug\n"
    "19. `/nexus-track` track SEO keyword"
)


# ── Open modal ─────────────────────────────────────────────────────────────────

_TEXT_ROUTE = {
    "add customer": "modal_add_customer",    "customer":       "modal_add_customer",
    "new lead":     "modal_new_lead",         "lead":           "modal_new_lead",
    "lost":         "modal_lost_lead",         "lost lead":      "modal_lost_lead",
    "nps":          "modal_log_nps",
    "health":       "modal_health_check",
    "expansion":    "modal_expansion",
    "qbr":          "modal_qbr",
    "invoice":      "modal_add_invoice",
    "expense":      "modal_add_expense",
    "reject":       "modal_reject_invoice",   "reject invoice": "modal_reject_invoice",
    "bug":          "modal_log_bug",           "log bug":        "modal_log_bug",
    "add service":  "modal_add_service",       "monitor":        "modal_add_service",
    "draft":        "modal_draft_post",        "draft post":     "modal_draft_post",
    "commitment":   "modal_set_commitment",    "set commitment": "modal_set_commitment",
    "won":          "modal_won_lead",           "mark won":       "modal_won_lead",
    "followup":     "modal_followup",           "follow up":      "modal_followup",
    "approve":      "modal_approve_invoice",    "approve invoice": "modal_approve_invoice",
    "close":        "modal_close_bug",          "close bug":      "modal_close_bug",
    "track":        "modal_track_keyword",      "track keyword":  "modal_track_keyword",
}


def open_modal(trigger_id: str, channel_id: str, tenant_id: str,
               user_id: str, client, command: str = "", text: str = ""):
    callback_id = SLASH_ROUTE.get(command) or _TEXT_ROUTE.get(text.strip().lower())
    if not callback_id:
        client.chat_postEphemeral(channel=channel_id, user=user_id, text=HELP_TEXT)
        return

    metadata = json.dumps({"channel_id": channel_id, "tenant_id": tenant_id, "user_id": user_id})
    defn = MODALS[callback_id]
    view = {
        "type": "modal",
        "callback_id": callback_id,
        "private_metadata": metadata,
        "title":  {"type": "plain_text", "text": defn["title"]},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close":  {"type": "plain_text", "text": "Cancel"},
        "blocks": defn["blocks"],
    }
    try:
        client.views_open(trigger_id=trigger_id, view=view)
    except Exception as e:
        logger.error(f"views_open failed for {callback_id}: {e}")
        client.chat_postEphemeral(channel=channel_id, user=user_id,
                                  text=f"Could not open form: {e}")


# ── Extract value from modal state ─────────────────────────────────────────────

def _val(state_values: dict, block_id: str) -> str:
    el = state_values.get(block_id, {}).get("value", {})
    if not el:
        return ""
    t = el.get("type", "")
    if t == "datepicker":
        return el.get("selected_date") or ""
    if t == "static_select":
        sel = el.get("selected_option") or {}
        return sel.get("value") or ""
    return el.get("value") or ""


# ── Proxy client for posting results ──────────────────────────────────────────

class _ProxyClient:
    """Minimal SlackClient-compatible wrapper backed by the shared Bolt client."""

    def __init__(self, app_client, channel_id: str, tenant_id: str, agent_name: str = "NEXUS"):
        self._app        = app_client
        self.channel_id  = channel_id
        self.room_id     = channel_id
        self.tenant_id   = tenant_id
        self.agent_name  = agent_name

    def post_message(self, text: str, room_id: str = None):
        self._app.chat_postMessage(channel=room_id or self.channel_id, text=text)

    def post_blocks(self, blocks, fallback_text: str = "", room_id: str = None):
        self._app.chat_postMessage(
            channel=room_id or self.channel_id,
            blocks=blocks, text=fallback_text,
        )

    def safe_signal(self, target_name: str, message: str):
        from app.Services.SlackClient import _channel_registry
        for _, (sc, _) in _channel_registry.items():
            if sc.agent_name == target_name:
                try:
                    sc.post_message(message)
                except Exception:
                    pass
                return


# ── Handle submission ──────────────────────────────────────────────────────────

def handle_submission(callback_id: str, state_values: dict,
                      metadata_str: str, user_id: str, app_client):
    try:
        meta = json.loads(metadata_str) if metadata_str else {}
    except Exception:
        meta = {}

    channel_id = meta.get("channel_id", "")
    tenant_id  = meta.get("tenant_id", "default")

    # Prefer the registered SlackClient for the channel; fall back to agent's
    # own channel; finally fall back to ProxyClient posting to command channel.
    from app.Services.SlackClient import _channel_registry
    entry = _channel_registry.get(channel_id)
    if entry:
        client = entry[0]
    else:
        agent_name = MODALS.get(callback_id, {}).get("agent", "NEXUS")
        client = None
        for _, (sc, _) in _channel_registry.items():
            if sc.agent_name == agent_name:
                client = sc
                break
        if not client:
            client = _ProxyClient(app_client, channel_id, tenant_id)

    v = lambda bid: _val(state_values, bid)

    try:
        if callback_id == "modal_add_customer":
            from agents.cs_agent.handlers import cmd_add_customer_data
            cmd_add_customer_data(client,
                {"name": v("name"), "arr": v("arr"), "renewal_date": v("renewal_date")},
                user_id, tenant_id)

        elif callback_id == "modal_new_lead":
            from agents.sales_agent.commands import cmd_new_lead_data
            cmd_new_lead_data(client,
                {"name": v("name"), "role": v("role"), "city": v("city"),
                 "industry": v("industry"), "deal_value": v("deal_value")},
                user_id, tenant_id)

        elif callback_id == "modal_log_nps":
            from agents.cs_agent.handlers import cmd_log_nps_data
            cmd_log_nps_data(client,
                {"customer": v("customer"), "score": v("score"), "note": v("note")},
                user_id, tenant_id)

        elif callback_id == "modal_health_check":
            from agents.cs_agent.handlers import cmd_health_check_data
            cmd_health_check_data(client, {"name": v("name")}, user_id, tenant_id)

        elif callback_id == "modal_expansion":
            from agents.cs_agent.handlers import cmd_expansion_data
            cmd_expansion_data(client, {"name": v("name")}, user_id, tenant_id)

        elif callback_id == "modal_qbr":
            from agents.cs_agent.handlers import cmd_qbr_data
            cmd_qbr_data(client, {"name": v("name")}, user_id, tenant_id)

        elif callback_id == "modal_add_invoice":
            from agents.finance_agent.handlers import cmd_invoice_data
            cmd_invoice_data(client,
                {"vendor": v("vendor"), "amount": v("amount"),
                 "due_date": v("due_date"), "category": v("category")},
                user_id, tenant_id)

        elif callback_id == "modal_add_expense":
            from agents.finance_agent.handlers import cmd_expense_data
            cmd_expense_data(client,
                {"submitter": v("submitter"), "amount": v("amount"),
                 "category": v("category"), "expense_date": v("expense_date")},
                user_id, tenant_id)

        elif callback_id == "modal_add_service":
            from agents.infra_agent.handlers import cmd_add_service_data
            cmd_add_service_data(client,
                {"name": v("name"), "url": v("url")},
                user_id, tenant_id)

        elif callback_id == "modal_draft_post":
            from agents.blog_agent.handlers import cmd_draft_post_data
            cmd_draft_post_data(client,
                {"topic": v("topic"), "geo": v("geo")},
                user_id, tenant_id)

        elif callback_id == "modal_set_commitment":
            from agents.sales_agent.commands import cmd_set_commitment_data
            cmd_set_commitment_data(client,
                {"lead": v("lead"), "commitment": v("commitment"), "due_date": v("due_date")},
                user_id, tenant_id)

        elif callback_id == "modal_log_bug":
            from agents.support_agent.handlers import cmd_log_bug_data
            sev_raw = v("severity")
            sev = sev_raw.split(":")[0].split(" ")[0] if sev_raw else "P2"  # "P0: production down" → "P0"
            cmd_log_bug_data(client,
                {"description": v("description"), "severity": sev},
                user_id, tenant_id)

        elif callback_id == "modal_reject_invoice":
            from agents.finance_agent.handlers import cmd_reject_invoice_data
            cmd_reject_invoice_data(client,
                {"invoice_id": v("invoice_id"), "reason": v("reason")},
                user_id, tenant_id)

        elif callback_id == "modal_lost_lead":
            from agents.sales_agent.commands import cmd_lost_data
            cmd_lost_data(client,
                {"name": v("name"), "reason": v("reason")},
                user_id, tenant_id)

        elif callback_id == "modal_won_lead":
            from agents.sales_agent.commands import cmd_won_data
            cmd_won_data(client, {"name": v("name")}, user_id, tenant_id)

        elif callback_id == "modal_followup":
            from agents.sales_agent.commands import cmd_follow_up_data
            cmd_follow_up_data(client, {"name": v("name")}, user_id, tenant_id)

        elif callback_id == "modal_approve_invoice":
            from agents.finance_agent.handlers import cmd_approve_invoice_data
            cmd_approve_invoice_data(client, {"invoice_id": v("invoice_id")}, user_id, tenant_id)

        elif callback_id == "modal_close_bug":
            from agents.support_agent.handlers import cmd_close_bug_data
            cmd_close_bug_data(client, {"bug_id": v("bug_id")}, user_id, tenant_id)

        elif callback_id == "modal_track_keyword":
            from agents.geo_seo_agent.handlers import cmd_track_keyword_data
            cmd_track_keyword_data(client, {"keyword": v("keyword")}, user_id, tenant_id)

        else:
            logger.warning(f"handle_submission: unknown callback_id={callback_id}")

    except Exception as e:
        logger.error(f"handle_submission [{callback_id}] failed: {e}", exc_info=True)
        try:
            client.post_message(f"Something went wrong processing the form: {e}")
        except Exception:
            pass
