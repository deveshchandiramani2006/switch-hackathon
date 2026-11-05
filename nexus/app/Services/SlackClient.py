import os
import logging
import threading
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Maps agent name → env var holding that agent's Slack channel ID
_AGENT_CHANNEL_ENV = {
    "SalesAgent":   "SLACK_CHANNEL_ID_SALES",
    "SupportAgent": "SLACK_CHANNEL_ID_SUPPORT",
    "CSAgent":      "SLACK_CHANNEL_ID_CS",
    "FinanceAgent": "SLACK_CHANNEL_ID_FINANCE",
    "GeoSEOAgent":  "SLACK_CHANNEL_ID_GROWTH",
    "BlogAgent":    "SLACK_CHANNEL_ID_CONTENT",
    "InfraAgent":   "SLACK_CHANNEL_ID_DEVOPS",
}


class SlackClient:
    """
    Drop-in replacement for SwitchClient — same public interface so all
    agent handlers work without modification.

    Requires:
        SLACK_BOT_TOKEN   xoxb-...   Bot User OAuth Token
        SLACK_APP_TOKEN   xapp-...   App-Level Token (connections:write scope)
        SLACK_CHANNEL_ID  C...       Channel this agent listens to
    """

    def __init__(self, agent_name: str, bot_token: str, app_token: str,
                 channel_id: str, tenant_id: str = "default"):
        self.agent_name  = agent_name
        self.bot_token   = bot_token
        self.app_token   = app_token
        self.channel_id  = channel_id
        self.room_id     = channel_id   # same attribute name as SwitchClient
        self.tenant_id   = tenant_id
        self._on_message_cb = None
        self._bot_user_id   = None
        self._app           = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_bot_user_id(self) -> str:
        if self._bot_user_id:
            return self._bot_user_id
        try:
            resp = self._app.client.auth_test()
            self._bot_user_id = resp["user_id"]
        except Exception as e:
            logger.error(f"auth_test failed: {e}")
            self._bot_user_id = ""
        return self._bot_user_id

    def _get_user_name(self, user_id: str) -> str:
        try:
            resp = self._app.client.users_info(user=user_id)
            profile = resp["user"]["profile"]
            return profile.get("display_name") or profile.get("real_name") or user_id
        except Exception:
            return user_id

    # ── Public interface (matches SwitchClient) ───────────────────────────────

    def post_message(self, text: str, room_id: str = None):
        channel = room_id or self.channel_id
        try:
            self._app.client.chat_postMessage(channel=channel, text=text)
        except Exception as e:
            logger.error(f"post_message failed: {e}")

    def post_blocks(self, blocks: list, fallback_text: str = "", room_id: str = None):
        """Post a Block Kit message. Falls back to plain text if blocks fail."""
        channel = room_id or self.channel_id
        try:
            self._app.client.chat_postMessage(
                channel=channel,
                text=fallback_text,
                blocks=blocks,
            )
        except Exception as e:
            logger.error(f"post_blocks failed: {e}")
            if fallback_text:
                self.post_message(fallback_text, room_id=room_id)

    def send_targeted_message(self, target_agent_id: str, message: str):
        # In Slack context target_agent_id is treated as a channel ID
        self.post_message(message, room_id=target_agent_id)

    def safe_signal(self, target_name: str, message: str):
        """Send a cross-agent signal to the target agent's Slack channel."""
        env_var = _AGENT_CHANNEL_ENV.get(target_name)
        channel = os.getenv(env_var, "") if env_var else ""
        if channel:
            self.post_message(message, room_id=channel)
            logger.info(f"Signal sent to {target_name} ({channel})")
        else:
            logger.info(f"{target_name} Slack channel not configured — skipping signal")

    def list_agents(self) -> list:
        # Not applicable for Slack; return empty so safe_signal falls through gracefully
        return []

    def record_heartbeat(self):
        try:
            from app.Services.DatabaseService import db_cursor
            with db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_heartbeats (tenant_id, agent_name, last_seen)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (tenant_id, agent_name) DO UPDATE SET last_seen = NOW()
                    """,
                    (self.tenant_id, self.agent_name)
                )
        except Exception as e:
            logger.warning(f"record_heartbeat failed: {e}")

    def read_context(self, room_id: str = None, limit: int = 10) -> list:
        channel = room_id or self.channel_id
        try:
            resp = self._app.client.conversations_history(channel=channel, limit=limit)
            return [
                {"sender": m.get("user", "unknown"), "text": m.get("text", "")}
                for m in resp.get("messages", [])
                if not m.get("bot_id")
            ]
        except Exception as e:
            logger.warning(f"read_context failed: {e}")
            return []

    def set_addressing(self, mode: str):
        pass  # no-op for Slack

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self, on_message_callback, addressing_mode: str = "anyone"):
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        self._on_message_cb = on_message_callback
        self._app = App(token=self.bot_token)

        # Resolve bot user ID up front so we can filter self-messages
        bot_user_id = self._get_bot_user_id()
        agent_name  = self.agent_name
        channel_id  = self.channel_id

        def _build_payload(event: dict, is_mention: bool) -> dict:
            user_id = event.get("user", "")
            sender  = self._get_user_name(user_id) if user_id else "unknown"
            text    = event.get("text", "")
            # Strip <@BOTID> prefix that Slack prepends on mentions
            if is_mention and bot_user_id:
                text = text.replace(f"<@{bot_user_id}>", "").strip()
            return {
                "text":       text,
                "sender":     sender,
                "room_id":    event.get("channel", channel_id),
                "is_mention": is_mention,
                "addressed":  True,
            }

        @self._app.event("app_mention")
        def on_mention(event, say):
            if event.get("channel") != channel_id:
                return
            payload = _build_payload(event, is_mention=True)
            if payload["sender"] == agent_name:
                return
            if self._on_message_cb:
                self._on_message_cb(self, payload)

        @self._app.action("nexus_cmd")
        def on_button_click(ack, body, action):
            ack()
            if body.get("channel", {}).get("id") != channel_id:
                return
            user_id = body.get("user", {}).get("id", "")
            sender  = self._get_user_name(user_id) if user_id else "unknown"
            cmd     = action.get("value", "").strip()
            if cmd and self._on_message_cb:
                payload = {
                    "text":       cmd,
                    "sender":     sender,
                    "room_id":    channel_id,
                    "is_mention": True,
                    "addressed":  True,
                }
                self._on_message_cb(self, payload)

        @self._app.event("message")
        def on_message(event, say):
            # Skip edits, deletes, bot posts, and messages in other channels
            if event.get("subtype") or event.get("bot_id"):
                return
            if event.get("channel") != channel_id:
                return
            # Skip if it's a mention — already handled by on_mention
            if bot_user_id and f"<@{bot_user_id}>" in event.get("text", ""):
                return
            payload = _build_payload(event, is_mention=False)
            if payload["sender"] == agent_name:
                return
            if self._on_message_cb:
                self._on_message_cb(self, payload)

        def _run():
            handler = SocketModeHandler(self._app, self.app_token)
            logger.info(f"{agent_name} connecting to Slack via Socket Mode...")
            handler.start()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        logger.info(f"{agent_name} Slack thread started")
