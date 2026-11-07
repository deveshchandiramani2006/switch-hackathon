"""
demo_slack_setup.py - Clear all bot messages from every channel, then post
polished demo cards showing the seeded data state.

Called automatically at the end of migrate_fresh.py.
Can also run standalone:
    cd nexus/
    python3 database/demo_slack_setup.py

Slack rule: each message can only have ONE instance of a given action_id.
So every card with buttons = its own separate post() call.
"""
import os
import time
import logging
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

CHANNELS = {
    "sales":   os.getenv("SLACK_CHANNEL_ID_SALES",   ""),
    "support": os.getenv("SLACK_CHANNEL_ID_SUPPORT", ""),
    "cs":      os.getenv("SLACK_CHANNEL_ID_CS",      ""),
    "finance": os.getenv("SLACK_CHANNEL_ID_FINANCE", ""),
    "growth":  os.getenv("SLACK_CHANNEL_ID_GROWTH",  ""),
    "content": os.getenv("SLACK_CHANNEL_ID_CONTENT", ""),
    "devops":  os.getenv("SLACK_CHANNEL_ID_DEVOPS",  ""),
}

# Thumbnail images - consistent picsum seeds (same seed = same photo every time)
IMGS = {
    "ai_sales": "https://picsum.photos/seed/ai-sales-india/800/400",
    "crm":      "https://picsum.photos/seed/crm-startups/800/400",
}


def _client():
    from slack_sdk import WebClient
    return WebClient(token=BOT_TOKEN)


# ── Clear channel ──────────────────────────────────────────────────────────────

def clear_channel(wc, channel_id: str, channel_name: str):
    deleted = 0
    cursor  = None
    while True:
        kwargs = {"channel": channel_id, "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        resp = wc.conversations_history(**kwargs)
        for msg in resp.get("messages", []):
            if msg.get("bot_id") or msg.get("subtype") == "bot_message":
                try:
                    wc.chat_delete(channel=channel_id, ts=msg["ts"])
                    deleted += 1
                    time.sleep(0.3)
                except Exception as e:
                    if "cant_delete_message" not in str(e):
                        logger.warning(f"delete failed: {e}")
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    print(f"    cleared {deleted} bot messages")


# ── Block helpers ─────────────────────────────────────────────────────────────

def _s(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

def _ctx(*texts):
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": t} for t in texts]}

def _div():
    return {"type": "divider"}

def _hdr(text):
    return {"type": "header", "text": {"type": "plain_text", "text": text, "emoji": True}}

def _img(url, alt):
    return {"type": "image", "image_url": url, "alt_text": alt}

_btn_counter = 0

def _btn(label, cmd, style=None):
    global _btn_counter
    _btn_counter += 1
    b = {"type": "button",
         "text": {"type": "plain_text", "text": label, "emoji": True},
         "action_id": f"nexus_{_btn_counter:04d}", "value": cmd}
    if style:
        b["style"] = style
    return b

def _actions(*btns):
    return {"type": "actions", "elements": list(btns)}

def post(wc, channel, blocks, text=""):
    """Post one message. Each message must have at most one _actions block."""
    try:
        wc.chat_postMessage(channel=channel, text=text or " ", blocks=blocks)
    except Exception as e:
        print(f"    WARNING post failed: {e}")
    time.sleep(0.5)


# ── Channel setups ─────────────────────────────────────────────────────────────

def setup_sales(wc, ch):
    today = date.today()

    post(wc, ch, [
        _hdr("🌅 Sales Dashboard - Today's Snapshot"),
        _ctx(f"*{today.strftime('%A, %b %d %Y')}*  ·  5 active leads  ·  2 overdue commitments"),
    ])

    post(wc, ch, [_hdr("📊 Pipeline")])

    post(wc, ch, [
        _div(),
        _s("🔸 *Priya Sharma*  ·  CTO, FinancePro  ·  Rs 5.0L"),
        _ctx("Stage: *Negotiation*", "Mumbai · Fintech", "Last touched: today"),
        _actions(_btn("💬 Follow Up", "follow up: Priya Sharma"),
                 _btn("🏆 Won", "won: Priya Sharma", "primary"),
                 _btn("❌ Lost", "lost: Priya Sharma", "danger")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟠 *Sunita Patel*  ·  CEO, RetailEdge  ·  Rs 7.5L"),
        _ctx("Stage: *Demo*", "Delhi · Retail", "Last touched: today"),
        _actions(_btn("💬 Follow Up", "follow up: Sunita Patel"),
                 _btn("🏆 Won", "won: Sunita Patel", "primary"),
                 _btn("❌ Lost", "lost: Sunita Patel", "danger")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟠 *Rahul Verma*  ·  Head Eng, CloudBase  ·  Rs 3.0L"),
        _ctx("Stage: *Proposal*", "Pune · Cloud", "Last touched: today"),
        _actions(_btn("💬 Follow Up", "follow up: Rahul Verma"),
                 _btn("🏆 Won", "won: Rahul Verma", "primary")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟡 *Meera Singh*  ·  Founder, HRstack  ·  Rs 10.0L"),
        _ctx("Stage: *Prospect*", "Bangalore · HR-Tech", "Last touched: today"),
        _actions(_btn("💬 Follow Up", "follow up: Meera Singh"),
                 _btn("🏆 Won", "won: Meera Singh", "primary")),
    ])

    post(wc, ch, [
        _div(),
        _s("⚠️ *Ankit Mehta*  ·  VP Ops, PayCo  ·  Rs 2.0L"),
        _ctx("Stage: *Qualified*", "Hyderabad · Fintech", "🕰️ _Stale - 10 days untouched_"),
        _actions(_btn("💬 Follow Up", "follow up: Ankit Mehta"),
                 _btn("🏆 Won", "won: Ankit Mehta", "primary")),
    ])

    post(wc, ch, [_hdr("⏰ Overdue Commitments")])

    post(wc, ch, [
        _div(),
        _s("🚨 *Ankit Mehta* - Send internal sign-off"),
        _ctx("Deadline: 3 days ago", "Escalation Level 1 → @ravi notified"),
    ])

    post(wc, ch, [
        _div(),
        _s("🔴 *Priya Sharma* - Share legal review doc"),
        _ctx("Deadline: yesterday", "Escalation Level 1 → @ravi notified"),
        _ctx("_Escalation runs every minute. Email fires at Level 3 → Mailtrap inbox_"),
    ])


def setup_cs(wc, ch):
    today   = date.today()
    renew10 = (today + timedelta(days=10)).strftime("%b %d")
    renew15 = (today + timedelta(days=15)).strftime("%b %d")
    renew30 = (today + timedelta(days=30)).strftime("%b %d")

    post(wc, ch, [
        _hdr("👥 Customer Success Dashboard"),
        _ctx(f"*{today.strftime('%A, %b %d %Y')}*  ·  5 customers  ·  2 at risk  ·  2 renewals this month"),
    ])

    post(wc, ch, [_hdr("🚨 Health Alerts - Action Required")])

    post(wc, ch, [
        _div(),
        _s("🔴 *TechStack* - Health score: 35/100"),
        _ctx("ARR: Rs 2.0L", "NPS: 5", "CSM: @ravi", "Renewal: in 90 days"),
        _actions(_btn("🩺 Health Check", "health: TechStack"),
                 _btn("📈 Expansion", "expansion: TechStack")),
    ])

    post(wc, ch, [
        _div(),
        _s("🔴 *CloudBase* - Health score: 48/100"),
        _ctx("ARR: Rs 7.5L", "NPS: 4", f"⚠️ Renewal: *{renew10}* - only 10 days away!"),
        _actions(_btn("🩺 Health Check", "health: CloudBase"),
                 _btn("📋 QBR Agenda", "qbr: CloudBase")),
    ])

    post(wc, ch, [_hdr("🗓️ Upcoming Renewals")])

    post(wc, ch, [
        _div(),
        _s(f"⚠️ *RetailEdge* - Renewal {renew15}  ·  Rs 3.0L"),
        _ctx("Health: 🟡 60/100", "NPS: 7"),
        _actions(_btn("📋 QBR Agenda", "qbr: RetailEdge"),
                 _btn("📈 Expansion", "expansion: RetailEdge")),
    ])

    post(wc, ch, [
        _div(),
        _s(f"📅 *Acme Corp* - Renewal {renew30}  ·  Rs 5.0L"),
        _ctx("Health: 🟢 85/100", "NPS: 9"),
        _actions(_btn("📈 Expansion", "expansion: Acme Corp"),
                 _btn("📋 QBR Agenda", "qbr: Acme Corp")),
    ])

    post(wc, ch, [
        _div(),
        _s("✅ *PayCo*  ·  Rs 10.0L  ·  Health: 🟢 72/100"),
        _ctx("NPS: 8", "Renewal: in 60 days"),
    ])


def setup_support(wc, ch):
    post(wc, ch, [
        _hdr("🐛 Bug Tracker - Open Issues"),
        _ctx("4 total  ·  1 P0  ·  1 P1  ·  1 P2"),
    ])

    post(wc, ch, [
        _div(),
        _s("🚨 *P0* - Bug #1\nPayment gateway returns 500 on UPI transactions - all Indian cards failing"),
        _ctx("Reported by: @amit", "_open_  ·  Source: manual"),
        _actions(_btn("✅ Close Bug", "close: #1", "primary"),
                 _btn("📋 All Bugs", "status")),
    ])

    post(wc, ch, [
        _div(),
        _s("🔴 *P1* - Bug #2\nCSV export truncates rows beyond 1000 entries"),
        _ctx("Reported by: @ravi", "_open_"),
        _actions(_btn("✅ Close Bug", "close: #2", "primary")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟡 *P2* - Bug #3\nDashboard charts render blank on Firefox 120"),
        _ctx("Reported by: @amit", "_open_"),
        _actions(_btn("✅ Close Bug", "close: #3", "primary")),
    ])

    post(wc, ch, [
        _ctx("💡 `/nexus-bug` to log a new bug  ·  or `@SupportAgent bug: <description>`"),
    ])


def setup_finance(wc, ch):
    today   = date.today()
    due5    = (today + timedelta(days=5)).strftime("%b %d")
    due10   = (today + timedelta(days=10)).strftime("%b %d")
    due20   = (today + timedelta(days=20)).strftime("%b %d")
    overdue = (today - timedelta(days=2)).strftime("%b %d")

    post(wc, ch, [
        _hdr("💰 Finance Dashboard"),
        _ctx(f"*{today.strftime('%A, %b %d %Y')}*  ·  4 invoices pending  ·  3 expense claims  ·  1 overdue"),
    ])

    post(wc, ch, [_hdr("🧾 Invoices - Pending Approval")])

    post(wc, ch, [
        _div(),
        _s(f"⚠️ *Google Ads* - Rs 80K  ·  Overdue since {overdue}"),
        _ctx("Invoice #3", "Category: marketing"),
        _actions(_btn("✅ Approve", "approve: invoice-3", "primary"),
                 _btn("❌ Reject",  "reject: invoice-3",  "danger")),
    ])

    post(wc, ch, [
        _div(),
        _s("⏳ *AWS* - Rs 1.5L"),
        _ctx("Invoice #1", "Category: infrastructure", f"Due: {due5}"),
        _actions(_btn("✅ Approve", "approve: invoice-1", "primary"),
                 _btn("❌ Reject",  "reject: invoice-1",  "danger")),
    ])

    post(wc, ch, [
        _div(),
        _s("⏳ *HubSpot* - Rs 50K"),
        _ctx("Invoice #4", "Category: software", f"Due: {due20}"),
        _actions(_btn("✅ Approve", "approve: invoice-4", "primary"),
                 _btn("❌ Reject",  "reject: invoice-4",  "danger")),
    ])

    post(wc, ch, [
        _div(),
        _s("⏳ *Zoom* - Rs 20K"),
        _ctx("Invoice #2", "Category: software", f"Due: {due10}"),
        _actions(_btn("✅ Approve", "approve: invoice-2", "primary"),
                 _btn("❌ Reject",  "reject: invoice-2",  "danger")),
    ])

    post(wc, ch, [
        _hdr("📊 Budget Burn"),
        _div(),
        _s("🚨 *Marketing*  ·  93% burned\n🟡 *Engineering*  ·  45% burned\n✅ *Operations*  ·  40% burned"),
        _ctx("Marketing: Rs 4.65L of Rs 5L  ·  _Warning: approaching limit_"),
    ])

    post(wc, ch, [
        _hdr("🧾 Expense Claims - Pending"),
        _s("⏳ *Ravi* - Rs 8,500 · Travel\n⏳ *Devesh* - Rs 3,200 · Equipment\n⏳ *Amit* - Rs 1,500 · Meals"),
        _ctx("3 claims pending  ·  Total: Rs 13,200"),
        _actions(_btn("📋 All Expenses", "expenses"),
                 _btn("📊 Budget: Engineering", "budget: Engineering")),
    ])


def setup_content(wc, ch):
    post(wc, ch, [
        _hdr("✍️ Content Queue - Drafts Ready for Approval"),
        _ctx("2 drafts waiting  ·  Auto-generated by GeoSEO analysis  ·  Approve to publish"),
    ])

    post(wc, ch, [
        _img(IMGS["ai_sales"], "AI Tools for Sales Teams India"),
        _s("*5 AI Tools Transforming Sales Teams in India (2026)*"),
        _ctx("Draft #1", "Keyword: _AI tools for sales team India_",
             "GEO score: 4/10 → content optimized", "Volume: 8,200/mo"),
        _s("_Indian sales teams are adopting AI at record speed. From automated follow-ups to deal "
           "intelligence and pipeline forecasting, the right AI stack can cut sales cycles by 40%. "
           "In this guide we cover the five tools making the biggest difference for B2B SaaS teams "
           "across Mumbai, Bangalore, and Delhi in 2026..._"),
        _actions(_btn("✅ Approve & Publish", "approve #1", "primary"),
                 _btn("👁 Preview",           "preview: #1"),
                 _btn("❌ Reject",             "reject #1", "danger")),
    ])

    post(wc, ch, [
        _img(IMGS["crm"], "Best CRM for Indian Startups"),
        _s("*Best CRM Software for Indian Startups: Complete Guide 2026*"),
        _ctx("Draft #2", "Keyword: _best CRM for Indian startups_",
             "GEO score: 3/10 → content optimized", "Volume: 12,400/mo"),
        _s("_Choosing the right CRM is one of the highest-leverage decisions an Indian startup can make. "
           "With deal cycles averaging 45 days and reps juggling WhatsApp, email, and Slack, you need "
           "a CRM that fits the way Indian teams actually work. We evaluated 12 tools on price, "
           "localisation, and AI features..._"),
        _actions(_btn("✅ Approve & Publish", "approve #2", "primary"),
                 _btn("👁 Preview",           "preview: #2"),
                 _btn("❌ Reject",             "reject #2", "danger")),
    ])


def setup_growth(wc, ch):
    post(wc, ch, [
        _hdr("📈 GEO/SEO Dashboard"),
        _ctx("4 keywords tracked  ·  GEO cycle ran  ·  2 content briefs sent to #content"),
    ])

    post(wc, ch, [_hdr("🔍 Keyword GEO Scores")])

    post(wc, ch, [
        _div(),
        _s("🔴 *best CRM for Indian startups*  ·  3/10"),
        _ctx("Volume: 12,400/mo · Country: IN",
             "Gaps: lacks examples, no structured data, missing FAQ schema"),
        _actions(_btn("💡 Improve", "geo tips: best CRM for Indian startups")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟡 *AI tools for sales team India*  ·  4/10"),
        _ctx("Volume: 8,200/mo · Country: IN",
             "Gaps: needs comparison table, missing author credentials"),
        _actions(_btn("💡 Improve", "geo tips: AI tools for sales team India")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟡 *automated invoicing software India*  ·  5/10"),
        _ctx("Volume: 6,700/mo · Country: IN"),
        _actions(_btn("💡 Improve", "geo tips: automated invoicing software India")),
    ])

    post(wc, ch, [
        _div(),
        _s("🟢 *customer success software SaaS India*  ·  7/10"),
        _ctx("Volume: 4,100/mo · Country: IN", "✅ Above threshold - no action needed"),
    ])

    post(wc, ch, [
        _s("💡 *2 content briefs auto-sent to #content* - blog drafts ready for your approval"),
        _ctx("Next GEO cycle: in 12 hours  ·  Next SEO rank check: in 24 hours"),
        _actions(_btn("🔄 Run GEO Now", "geo run"),
                 _btn("📊 Full Report", "geo report")),
    ])


def setup_devops(wc, ch):
    post(wc, ch, [
        _hdr("🖥️ Infrastructure Monitor"),
        _ctx("4 services monitored  ·  All healthy  ·  Checks every 60 seconds"),
    ])

    services = [
        ("API Gateway",      "https://httpbin.org/status/200"),
        ("Database",         "https://httpbin.org/status/200"),
        ("payments-service", "https://httpbin.org/status/200"),
        ("auth-service",     "https://httpbin.org/status/200"),
    ]
    for name, url in services:
        post(wc, ch, [
            _div(),
            _s(f"🟢 *{name}*  ·  200 OK"),
            _ctx(url, "_healthy_  ·  0 consecutive failures"),
            _actions(_btn("🔁 Ping", f"check: {name}")),
        ])

    post(wc, ch, [
        _ctx("💡 Add a failing service: `/nexus-service` → name + `https://httpbin.org/status/500`"),
    ])


# ── Main ──────────────────────────────────────────────────────────────────────

SETUP_FNS = {
    "sales":   setup_sales,
    "cs":      setup_cs,
    "support": setup_support,
    "finance": setup_finance,
    "content": setup_content,
    "growth":  setup_growth,
    "devops":  setup_devops,
}


def run():
    if not BOT_TOKEN:
        print("  SLACK_BOT_TOKEN not set - skipping Slack setup")
        return

    try:
        from slack_sdk import WebClient
    except ImportError:
        print("  slack_sdk not installed - skipping Slack setup")
        return

    wc = _client()
    print("\nSetting up Slack channels...")

    for name, channel_id in CHANNELS.items():
        if not channel_id:
            print(f"  #{name}: channel ID not set - skipping")
            continue
        print(f"  #{name}:")
        clear_channel(wc, channel_id, name)
        SETUP_FNS[name](wc, channel_id)
        print(f"    demo cards posted ✓")

    print("\n✅  Slack setup complete - all channels ready for demo.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run()
