"""
Single-process launcher for all 7 NEXUS agents.

Transport architecture:
  Slack  → user-facing interaction (slash commands, modals, Block Kit)
  Switch → agent-to-agent signals  (DEAL_WON, P1_BREACH, GEO_SIGNAL, etc.)

Each agent gets a HybridClient. When SWITCH_AGENT_ID_*/SWITCH_API_KEY_*/SWITCH_ROOM_ID_*
env vars are set, inter-agent signals travel over Switch WebSockets. Otherwise the
system falls back to in-process routing so it runs without a Switch server.
"""
import os
import sys
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [NEXUS] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

bot_token  = os.getenv("SLACK_BOT_TOKEN", "")
app_token  = os.getenv("SLACK_APP_TOKEN", "")
tenant_id  = os.getenv("TENANT_ID", "default")

if not bot_token or not app_token:
    logger.error("SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in .env")
    sys.exit(1)

from app.Services.SlackClient import SlackClient
from app.Services.HybridClient import HybridClient


def _client(agent_name: str, channel_env: str, switch_prefix: str) -> HybridClient:
    channel_id = os.getenv(channel_env, "")
    if not channel_id:
        logger.warning(f"{agent_name}: {channel_env} not set - agent will not receive Slack messages")
    slack = SlackClient(agent_name, bot_token, app_token, channel_id, tenant_id)

    # Build SwitchClient when all three credentials are present
    agent_id  = os.getenv(f"SWITCH_AGENT_ID_{switch_prefix}", "")
    api_key   = os.getenv(f"SWITCH_API_KEY_{switch_prefix}", "")
    room_id   = os.getenv(f"SWITCH_ROOM_ID_{switch_prefix}", "")
    switch = None
    if agent_id and api_key and room_id:
        try:
            from app.Services.SwitchClient import SwitchClient
            switch = SwitchClient(agent_name, api_key, agent_id, room_id, tenant_id)
            logger.info(f"{agent_name}: Switch transport enabled (agent_id={agent_id[:8]}…)")
        except Exception as e:
            logger.warning(f"{agent_name}: Switch import failed ({e}) - using Slack fallback")
    else:
        missing = [v for v in [
            f"SWITCH_AGENT_ID_{switch_prefix}",
            f"SWITCH_API_KEY_{switch_prefix}",
            f"SWITCH_ROOM_ID_{switch_prefix}",
        ] if not os.getenv(v)]
        if missing:
            logger.info(f"{agent_name}: Switch not configured ({', '.join(missing)} missing) - using in-process fallback")

    return HybridClient(slack, switch)


# ── Build all clients ─────────────────────────────────────────────────────────
sales_client   = _client("SalesAgent",   "SLACK_CHANNEL_ID_SALES",    "SALES")
support_client = _client("SupportAgent", "SLACK_CHANNEL_ID_SUPPORT",  "SUPPORT")
cs_client      = _client("CSAgent",      "SLACK_CHANNEL_ID_CS",       "CS")
finance_client = _client("FinanceAgent", "SLACK_CHANNEL_ID_FINANCE",  "FINANCE")
geo_client     = _client("GeoSEOAgent",  "SLACK_CHANNEL_ID_GROWTH",   "GEOSEO")
blog_client    = _client("BlogAgent",    "SLACK_CHANNEL_ID_CONTENT",  "BLOG")
infra_client   = _client("InfraAgent",   "SLACK_CHANNEL_ID_DEVOPS",   "INFRA")

# ── Start schedulers ──────────────────────────────────────────────────────────
logger.info("Starting schedulers...")

from agents.sales_agent.escalation import start_escalation_scheduler
start_escalation_scheduler(sales_client)

from agents.support_agent.scheduler import start_support_scheduler
start_support_scheduler(support_client)

from agents.cs_agent.scheduler import start_cs_scheduler
start_cs_scheduler(cs_client)

from agents.finance_agent.scheduler import start_finance_scheduler
start_finance_scheduler(finance_client)

from agents.geo_seo_agent.scheduler import start_geo_scheduler
start_geo_scheduler(geo_client)

from agents.blog_agent.scheduler import start_blog_scheduler
start_blog_scheduler(blog_client)

from agents.infra_agent.monitor import start_monitor
start_monitor(infra_client)

# ── Connect all agents ────────────────────────────────────────────────────────
logger.info("Connecting all agents...")

from agents.sales_agent.handlers   import handle_message as sales_handle
from agents.support_agent.handlers import handle_message as support_handle
from agents.cs_agent.handlers      import handle_message as cs_handle
from agents.finance_agent.handlers import handle_message as finance_handle
from agents.geo_seo_agent.handlers import handle_message as geo_handle
from agents.blog_agent.handlers    import handle_message as blog_handle
from agents.infra_agent.handlers   import handle_message as infra_handle

sales_client.connect(sales_handle)
support_client.connect(support_handle)
cs_client.connect(cs_handle)
finance_client.connect(finance_handle)
geo_client.connect(geo_handle)
blog_client.connect(blog_handle)
infra_client.connect(infra_handle)

switch_active = sum(
    1 for c in [sales_client, support_client, cs_client, finance_client,
                geo_client, blog_client, infra_client]
    if c._switch is not None
)

logger.info(f"All 7 agents connected — {switch_active}/7 using Switch for signals.")
logger.info("Channels registered:")
for name, env in [
    ("SalesAgent",   "SLACK_CHANNEL_ID_SALES"),
    ("SupportAgent", "SLACK_CHANNEL_ID_SUPPORT"),
    ("CSAgent",      "SLACK_CHANNEL_ID_CS"),
    ("FinanceAgent", "SLACK_CHANNEL_ID_FINANCE"),
    ("GeoSEOAgent",  "SLACK_CHANNEL_ID_GROWTH"),
    ("BlogAgent",    "SLACK_CHANNEL_ID_CONTENT"),
    ("InfraAgent",   "SLACK_CHANNEL_ID_DEVOPS"),
]:
    ch = os.getenv(env, "(not set)")
    logger.info(f"  {name:14s} → {ch}")

try:
    while True:
        time.sleep(5)
except KeyboardInterrupt:
    logger.info("NEXUS stopped.")
