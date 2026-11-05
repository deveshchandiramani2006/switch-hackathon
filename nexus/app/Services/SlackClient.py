import os
import re
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

# ── Module-level singletons ───────────────────────────────────────────────────
# All SlackClient instances in this process share ONE Bolt app and ONE socket
# connection. Slack distributes events across connections round-robin when
# multiple SocketModeHandlers share the same App-Level Token, so running 7
# separate connections means 6/7 events land on the wrong agent.

_lock             = threading.Lock()
_shared_app       = None   # single slack_bolt.App
_socket_started   = False  # True once SocketModeHandler thread is running
_bot_user_id      = None   # resolved once, shared
_channel_registry = {}     # channel_id → (SlackClient, callback)


def _get_or_create_app(bot_token: str):
    global _shared_app
    with _lock:
        if _shared_app is None:
            from slack_bolt import App
            _shared_app = App(token=bot_token)
            _register_global_handlers(_shared_app)
            logger.info("Shared Bolt app created")
        return _shared_app


def _register_global_handlers(app):
    """Register event handlers on the shared app exactly once."""

    @app.event("app_mention")
    def on_mention(event, say):
        channel = event.get("channel", "")
        entry   = _channel_registry.get(channel)
        if not entry:
            return
        client, cb = entry
        if event.get("user") == _bot_user_id:
            return
        payload = _build_payload(client, event, is_mention=True)
        if payload["sender"] == client.agent_name:
            return
        cb(client, payload)

    @app.action("nexus_cmd")
    def on_button_click(ack, body, action):
        ack()
        channel = body.get("channel", {}).get("id", "")
        entry   = _channel_registry.get(channel)
        if not entry:
            return
        client, cb = entry
        user_id = body.get("user", {}).get("id", "")
        sender  = client._get_user_name(user_id) if user_id else "unknown"
        cmd     = action.get("value", "").strip()
        if cmd:
            payload = {
                "text":       cmd,
                "sender":     sender,
                "room_id":    channel,
                "is_mention": True,
                "addressed":  True,
            }
            cb(client, payload)

    @app.event("message")
    def on_message(event, say):
        if event.get("subtype") or event.get("bot_id"):
            return
        channel = event.get("channel", "")
        entry   = _channel_registry.get(channel)
        if not entry:
            return
        client, cb = entry
        # Skip if it's a mention — already handled by on_mention
        if _bot_user_id and f"<@{_bot_user_id}>" in event.get("text", ""):
            return
        payload = _build_payload(client, event, is_mention=False)
        if payload["sender"] == client.agent_name:
            return
        cb(client, payload)

    @app.command("/nexus")
    def on_nexus_command(ack, command, client):
        ack()
        channel_id = command.get("channel_id", "")
        entry      = _channel_registry.get(channel_id)
        tenant_id  = entry[0].tenant_id if entry else "default"
        from app.Services.ModalService import open_modal
        open_modal(
            trigger_id=command["trigger_id"],
            text=command.get("text", "").strip().lower(),
            channel_id=channel_id,
            tenant_id=tenant_id,
            user_id=command.get("user_id", ""),
            client=client,
        )

    @app.view(re.compile(r"^modal_"))
    def on_view_submission(ack, body, client, view):
        ack()
        from app.Services.ModalService import handle_submission
        handle_submission(
            callback_id=view["callback_id"],
            state_values=view["state"]["values"],
            metadata_str=view.get("private_metadata", ""),
            user_id=body["user"]["id"],
            app_client=client,
        )


def _build_payload(client, event: dict, is_mention: bool) -> dict:
    user_id = event.get("user", "")
    sender  = client._get_user_name(user_id) if user_id else "unknown"
    text    = event.get("text", "")
    if is_mention and _bot_user_id:
        text = text.replace(f"<@{_bot_user_id}>", "").strip()
    return {
        "text":       text,
        "sender":     sender,
        "room_id":    event.get("channel", client.channel_id),
        "is_mention": is_mention,
        "addressed":  True,
    }


class SlackClient:
    """
    Drop-in replacement for SwitchClient — same public interface so all
    agent handlers work without modification.

    All instances in the same process share one Bolt app and one Socket Mode
    connection so Slack always routes events to the right agent.

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
        self.room_id     = channel_id
        self.tenant_id   = tenant_id
        self._app        = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_user_name(self, user_id: str) -> str:
        if not self._app:
            return user_id
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
        self.post_message(message, room_id=target_agent_id)

    def safe_signal(self, target_name: str, message: str):
        env_var = _AGENT_CHANNEL_ENV.get(target_name)
        channel = os.getenv(env_var, "") if env_var else ""
        if channel:
            self.post_message(message, room_id=channel)
            logger.info(f"Signal sent to {target_name} ({channel})")
        else:
            logger.info(f"{target_name} Slack channel not configured — skipping signal")

    def list_agents(self) -> list:
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
        pass

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self, on_message_callback, addressing_mode: str = "anyone"):
        global _socket_started, _bot_user_id

        self._app = _get_or_create_app(self.bot_token)

        # Resolve bot user ID once for the whole process
        with _lock:
            if _bot_user_id is None:
                try:
                    resp = self._app.client.auth_test()
                    _bot_user_id = resp["user_id"]
                    logger.info(f"Bot user ID: {_bot_user_id}")
                except Exception as e:
                    logger.error(f"auth_test failed: {e}")
                    _bot_user_id = ""

        # Register this agent's channel
        _channel_registry[self.channel_id] = (self, on_message_callback)
        logger.info(f"{self.agent_name} registered for channel {self.channel_id}")

        # Start the socket handler only once (first agent to connect starts it)
        with _lock:
            if not _socket_started:
                _socket_started = True
                app_token = self.app_token

                def _run():
                    from slack_bolt.adapter.socket_mode import SocketModeHandler
                    logger.info("Starting shared Socket Mode connection...")
                    handler = SocketModeHandler(self._app, app_token)
                    handler.start()

                t = threading.Thread(target=_run, daemon=True)
                t.start()
                logger.info("Socket Mode thread launched")
