"""
HybridClient — dual-transport client for NEXUS agents.

Slack   → user-facing output  (post_message, post_blocks, update_message)
Switch  → agent-to-agent signals (safe_signal, send_targeted_message, list_agents)

When Switch credentials are absent, falls back to SlackClient in-process routing
so the system still works without a running Switch server.
"""
import logging

logger = logging.getLogger(__name__)


class HybridClient:
    def __init__(self, slack_client, switch_client=None):
        self._slack  = slack_client
        self._switch = switch_client

        # Expose the same attributes agent handlers read directly
        self.agent_name = slack_client.agent_name
        self.channel_id = slack_client.channel_id
        self.room_id    = slack_client.channel_id
        self.tenant_id  = slack_client.tenant_id

    # ── Slack UI ─────────────────────────────────────────────────────────────

    def post_message(self, text: str, room_id: str = None):
        self._slack.post_message(text, room_id)

    def post_blocks(self, blocks: list, fallback_text: str = "", room_id: str = None):
        self._slack.post_blocks(blocks, fallback_text, room_id)

    def update_message(self, ts: str, blocks: list, fallback_text: str = "", room_id: str = None):
        self._slack.update_message(ts, blocks, fallback_text, room_id)

    def read_context(self, room_id: str = None, limit: int = 10) -> list:
        return self._slack.read_context(room_id, limit)

    # ── Agent signals → Switch (with Slack in-process fallback) ──────────────

    def safe_signal(self, target_name: str, message: str):
        if self._switch:
            logger.info(f"{self.agent_name} → Switch safe_signal → {target_name}")
            self._switch.safe_signal(target_name, message)
        else:
            self._slack.safe_signal(target_name, message)

    def send_targeted_message(self, target_agent_id: str, message: str):
        if self._switch:
            logger.info(f"{self.agent_name} → Switch send_targeted_message → {target_agent_id}")
            self._switch.send_targeted_message(target_agent_id, message)
        else:
            self._slack.send_targeted_message(target_agent_id, message)

    def list_agents(self) -> list:
        if self._switch:
            return self._switch.list_agents()
        return self._slack.list_agents()

    def record_heartbeat(self):
        if self._switch:
            self._switch.record_heartbeat()
        else:
            self._slack.record_heartbeat()

    def _get_user_name(self, user_id: str) -> str:
        return self._slack._get_user_name(user_id)

    def set_addressing(self, mode: str):
        pass

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self, on_message_callback, addressing_mode: str = "anyone"):
        # Register with Slack (starts Socket Mode on first call)
        self._slack.connect(on_message_callback, addressing_mode)

        # Override _channel_registry so ALL Slack-routed events (slash commands,
        # button clicks, mentions) pass *this* HybridClient to the handler —
        # ensuring safe_signal/send_targeted_message go via Switch.
        from app.Services.SlackClient import _channel_registry
        _channel_registry[self.channel_id] = (self, on_message_callback)
        logger.info(f"{self.agent_name} registered in channel_registry as HybridClient")

        if self._switch:
            # Relay incoming Switch targeted messages to the agent handler.
            # Pass `self` (HybridClient) so agent responses go to Slack, not Switch.
            hybrid = self

            def _switch_relay(_, payload):
                try:
                    on_message_callback(hybrid, payload)
                except Exception as e:
                    logger.error(f"{hybrid.agent_name} switch_relay error: {e}")

            self._switch.connect(_switch_relay, addressing_mode)
            logger.info(f"{self.agent_name} Switch WebSocket started — signals via Switch")
        else:
            logger.info(f"{self.agent_name} no Switch credentials — signals via in-process routing")
