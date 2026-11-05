import os
import sys
import time
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [InfraAgent] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, "/app")

from .handlers import handle_message
from .monitor import start_monitor


def _make_client(tenant_id: str):
    bot_token  = os.getenv("SLACK_BOT_TOKEN", "")
    app_token  = os.getenv("SLACK_APP_TOKEN", "")
    channel_id = os.getenv("SLACK_CHANNEL_ID") or os.getenv("SLACK_CHANNEL_ID_DEVOPS", "")

    if bot_token and app_token and channel_id:
        from app.Services.SlackClient import SlackClient
        logger.info("InfraAgent using Slack")
        return SlackClient("InfraAgent", bot_token, app_token, channel_id, tenant_id)

    agent_id = os.getenv("SWITCH_AGENT_ID", "")
    api_key  = os.getenv("SWITCH_API_KEY", "")
    room_id  = os.getenv("SWITCH_ROOM_ID", "")
    if agent_id and api_key and room_id:
        from app.Services.SwitchClient import SwitchClient
        logger.info("InfraAgent using Switch")
        return SwitchClient("InfraAgent", api_key, agent_id, room_id, tenant_id)

    logger.error("No messaging config found. Set SLACK_BOT_TOKEN/SLACK_APP_TOKEN/SLACK_CHANNEL_ID or SWITCH_* vars.")
    sys.exit(1)


def main():
    tenant_id = os.getenv("TENANT_ID", "default")
    client = _make_client(tenant_id)
    start_monitor(client)
    client.connect(handle_message, addressing_mode="anyone")

    logger.info("InfraAgent running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("InfraAgent stopped.")


if __name__ == "__main__":
    main()
