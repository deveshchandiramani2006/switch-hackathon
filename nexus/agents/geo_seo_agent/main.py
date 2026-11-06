import os
import sys
import time
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [GeoSEOAgent] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, "/app")

from .handlers import handle_message
from .scheduler import start_geo_scheduler


def _make_client(tenant_id: str):
    # Switch is the primary transport — agents connect to Switch rooms,
    # Switch Console bridges to Slack/Teams/Discord
    agent_id = os.getenv("SWITCH_AGENT_ID_GEOSEO", "")
    api_key  = os.getenv("SWITCH_API_KEY_GEOSEO", "")
    room_id  = os.getenv("SWITCH_ROOM_ID_GROWTH", "")
    if agent_id and api_key and room_id:
        from app.Services.SwitchClient import SwitchClient
        logger.info("GeoSEOAgent using Switch")
        return SwitchClient("GeoSEOAgent", api_key, agent_id, room_id, tenant_id)

    # Slack Bolt fallback — only used when Switch Console is not running
    bot_token  = os.getenv("SLACK_BOT_TOKEN", "")
    app_token  = os.getenv("SLACK_APP_TOKEN", "")
    channel_id = os.getenv("SLACK_CHANNEL_ID_GROWTH", "")
    if bot_token and app_token and channel_id:
        from app.Services.SlackClient import SlackClient
        logger.info("GeoSEOAgent using Slack (Switch not configured)")
        return SlackClient("GeoSEOAgent", bot_token, app_token, channel_id, tenant_id)

    logger.error("No transport configured. Set SWITCH_AGENT_ID_GEOSEO/SWITCH_API_KEY_GEOSEO/SWITCH_ROOM_ID_GROWTH or SLACK_* vars.")
    sys.exit(1)


def main():
    tenant_id = os.getenv("TENANT_ID", "default")
    client = _make_client(tenant_id)
    start_geo_scheduler(client)
    client.connect(handle_message, addressing_mode="owner_and_owner_agents")

    logger.info("GeoSEOAgent running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("GeoSEOAgent stopped.")


if __name__ == "__main__":
    main()
