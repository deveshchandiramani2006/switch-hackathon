"""
demo_slack_setup.py - Clear ALL messages from every channel, then post ONLY
the pre-seeded blog drafts in #nexus-content.

Everything else (sales, CS, support, finance, growth, devops) starts empty —
agents populate those channels live during the demo.

Escalation cards appear automatically via the escalation engine (1-min cycle).
"""
import os
import time
import logging
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

IMGS = {
    "ai_sales": "https://picsum.photos/seed/ai-sales-india/800/400",
    "crm":      "https://picsum.photos/seed/crm-startups/800/400",
}


def _client():
    from slack_sdk import WebClient
    return WebClient(token=BOT_TOKEN)


def clear_channel(wc, channel_id: str, channel_name: str):
    deleted = 0
    cursor = None
    while True:
        kwargs = {"channel": channel_id, "limit": 200}
        if cursor:
            kwargs["cursor"] = cursor
        resp = wc.conversations_history(**kwargs)
        for msg in resp.get("messages", []):
            try:
                wc.chat_delete(channel=channel_id, ts=msg["ts"])
                deleted += 1
                time.sleep(0.1)
            except Exception:
                pass
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    print(f"    cleared {deleted} messages")


def _s(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

def _ctx(*texts):
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": t} for t in texts]}

def _div():
    return {"type": "divider"}

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
    try:
        wc.chat_postMessage(channel=channel, text=text or " ", blocks=blocks)
    except Exception as e:
        print(f"    WARNING post failed: {e}")
    time.sleep(0.5)


def setup_content(wc, ch):
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
    print("\nClearing all Slack channels...")

    for name, channel_id in CHANNELS.items():
        if not channel_id:
            print(f"  #{name}: channel ID not set - skipping")
            continue
        print(f"  #nexus-{name}:")
        clear_channel(wc, channel_id, name)

    print("\nSeeding #nexus-content with blog drafts...")
    ch = CHANNELS.get("content", "")
    if ch:
        setup_content(wc, ch)
        print("  blog drafts posted ✓")

    print("\n✅  Slack setup complete — all channels cleared, blog drafts in #nexus-content.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    run()
