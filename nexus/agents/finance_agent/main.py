import os
import sys
import time
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [FinanceAgent] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, "/app")

from app.Services.SwitchClient import SwitchClient
from .handlers import handle_message
from .scheduler import start_finance_scheduler


def main():
    agent_id = os.getenv("SWITCH_AGENT_ID", "")
    api_key  = os.getenv("SWITCH_API_KEY", "")
    room_id  = os.getenv("SWITCH_ROOM_ID", "")

    if not all([agent_id, api_key, room_id]):
        logger.error("SWITCH_AGENT_ID, SWITCH_API_KEY, SWITCH_ROOM_ID must all be set.")
        sys.exit(1)

    client = SwitchClient(
        agent_name="FinanceAgent",
        api_key=api_key,
        agent_id=agent_id,
        room_id=room_id
    )

    start_finance_scheduler(client)
    client.connect(on_message_callback=handle_message, addressing_mode="owner_and_owner_agents")

    logger.info("FinanceAgent running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("FinanceAgent stopped.")


if __name__ == "__main__":
    main()
