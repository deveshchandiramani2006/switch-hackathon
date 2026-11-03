import os
import uuid
import json
import time
import logging
import threading
import requests
import websocket
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SWITCH_URL = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")


class SwitchClient:
    def __init__(self, agent_name: str, api_key: str, agent_id: str, room_id: str):
        self.agent_name = agent_name
        self.api_key = api_key
        self.agent_id = agent_id
        self.room_id = room_id
        self.conn_id = str(uuid.uuid4())
        self.ws = None
        self.cursor = 0
        self._on_message_cb = None
        self._reconnect_delay = 1

    @staticmethod
    def register(name: str, description: str, registration_key: str) -> dict:
        """Register a new agent with Switch. Returns {agent_id, api_key}."""
        resp = requests.post(
            f"{SWITCH_URL}/agents",
            headers={
                "Authorization": f"Bearer {registration_key}",
                "Content-Type": "application/json"
            },
            json={
                "name": name,
                "description": description,
                "connector_type": "custom_client",
                "integration_profile": {
                    "connection_model": "always_on",
                    "message_exchange": True,
                    "pre_invocation_mediation": [],
                    "post_invocation_mediation": [],
                    "event_reporting": []
                }
            }
        )
        resp.raise_for_status()
        return resp.json()

    def set_addressing(self, mode: str):
        """Set addressing mode: owner_only | owner_and_owner_agents | anyone"""
        try:
            requests.post(
                f"{SWITCH_URL}/agents/{self.agent_id}/ops/update_agent_detail",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"agent_id": self.agent_id, "addressing": mode},
                timeout=10
            )
            logger.info(f"{self.agent_name} addressing set to: {mode}")
        except Exception as e:
            logger.error(f"set_addressing failed: {e}")

    def post_message(self, text: str, room_id: str = None):
        """Post a message to a Switch room."""
        try:
            requests.post(
                f"{SWITCH_URL}/agents/{self.agent_id}/ops/post_message",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Switch-Connection-Id": self.conn_id
                },
                json={"room_id": room_id or self.room_id, "text": text},
                timeout=10
            )
        except Exception as e:
            logger.error(f"post_message failed: {e}")

    def send_targeted_message(self, target_agent_id: str, message: str):
        """Send a direct message to another agent."""
        try:
            requests.post(
                f"{SWITCH_URL}/agents/{self.agent_id}/ops/send_targeted_message",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Switch-Connection-Id": self.conn_id
                },
                json={"target_agent_id": target_agent_id, "message": message},
                timeout=10
            )
        except Exception as e:
            logger.error(f"send_targeted_message failed: {e}")

    def list_agents(self) -> list:
        """List all registered agents."""
        try:
            resp = requests.get(
                f"{SWITCH_URL}/agents/{self.agent_id}/ops/list_agents",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "X-Switch-Connection-Id": self.conn_id
                },
                timeout=10
            )
            return resp.json().get("agents", [])
        except Exception as e:
            logger.error(f"list_agents failed: {e}")
            return []

    def safe_signal(self, target_name: str, message: str):
        """Send targeted message only if target agent is deployed."""
        agents = self.list_agents()
        target = next((a for a in agents if a.get("name") == target_name), None)
        if target:
            self.send_targeted_message(target["id"], message)
            logger.info(f"Signal sent to {target_name}")
        else:
            logger.info(f"{target_name} not deployed — skipping signal")

    def connect(self, on_message_callback, addressing_mode: str = "owner_and_owner_agents"):
        """Start WebSocket connection with auto-reconnect."""
        self._on_message_cb = on_message_callback
        self.set_addressing(addressing_mode)
        self._start_ws()

    def _start_ws(self):
        ws_url = f"{SWITCH_URL.replace('http', 'ws')}/agents/{self.agent_id}/connection/ws"

        def on_message(ws, raw):
            try:
                msg = json.loads(raw)
                # Handle ping
                if msg.get("type") == "ping":
                    ws.send(json.dumps({"type": "pong", "cursor": self.cursor}))
                    return
                # Update cursor
                if "cursor" in msg:
                    self.cursor = msg["cursor"]
                # Only process addressed messages
                payload = msg.get("payload", {})
                if payload.get("addressed") and self._on_message_cb:
                    self._on_message_cb(self, payload)
            except Exception as e:
                logger.error(f"on_message error: {e}")

        def on_error(ws, error):
            logger.error(f"{self.agent_name} WebSocket error: {error}")

        def on_close(ws, code, msg):
            logger.warning(
                f"{self.agent_name} WebSocket closed: {code}. "
                f"Reconnecting in {self._reconnect_delay}s..."
            )
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 60)
            self._start_ws()

        def on_open(ws):
            self._reconnect_delay = 1
            logger.info(f"{self.agent_name} connected to Switch")

        self.ws = websocket.WebSocketApp(
            ws_url,
            header={
                "Authorization": f"Bearer {self.api_key}",
                "X-Switch-Connection-Id": self.conn_id,
                "X-Switch-Claim-Rooms": self.room_id
            },
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        t = threading.Thread(target=self.ws.run_forever, daemon=True)
        t.start()
        logger.info(f"{self.agent_name} WebSocket thread started")
