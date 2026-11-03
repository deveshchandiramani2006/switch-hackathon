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

from shared.switch_client import SwitchClient
from .handlers import handle_message
from .monitor import start_monitor


def main():
    agent_id = os.getenv("SWITCH_AGENT_ID", "")
    api_key  = os.getenv("SWITCH_API_KEY", "")
    room_id  = os.getenv("SWITCH_ROOM_ID", "")

    if not all([agent_id, api_key, room_id]):
        logger.error("SWITCH env vars not set.")
        sys.exit(1)

    client = SwitchClient("InfraAgent", api_key, agent_id, room_id)
    start_monitor(client)
    client.connect(handle_message, addressing_mode="anyone")

    logger.info("InfraAgent running.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("InfraAgent stopped.")


if __name__ == "__main__":
    main()
