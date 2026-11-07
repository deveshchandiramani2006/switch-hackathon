"""
Unit tests for Switch signal chain logic.

Verifies that DEAL_WON uses dynamic fan-out via list_agents() - one discovery
call, signals fired only to online agents.
"""
import sys
import os
from unittest.mock import MagicMock

# Mock external dependencies before importing the module under test
for _mod in [
    "app", "app.Services", "app.Services.DatabaseService",
    "app.Services.LlmService", "app.Services.BlockBuilder",
    "app.Services.ValidationService",
]:
    sys.modules[_mod] = MagicMock()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from agents.sales_agent.commands import _broadcast_deal_won, _DEAL_WON_TARGETS


class _MockSwitchClient:
    """Minimal Switch client mock for unit testing signal chains."""

    def __init__(self, online_agents: list):
        self.agent_name = "SalesAgent"
        self.room_id    = "test-room"
        self.tenant_id  = "default"
        self._online    = online_agents
        self.targeted   = {}   # agent_name → signal text received

    def list_agents(self):
        return [{"name": n, "id": f"id-{n}"} for n in self._online]

    def send_targeted_message(self, target_id: str, message: str):
        name = target_id.replace("id-", "")
        self.targeted[name] = message

    def post_message(self, text: str, room_id: str = None):
        pass

    def post_blocks(self, blocks, fallback_text="", room_id=None):
        pass

    def read_context(self, limit=10):
        return []


def test_deal_won_fires_to_all_subscribed_agents():
    """DEAL_WON fans out to every agent in _DEAL_WON_TARGETS that is online."""
    client = _MockSwitchClient(online_agents=["CSAgent", "FinanceAgent", "InfraAgent"])
    _broadcast_deal_won(client, "Vikram_Nair", 800000)

    for target in _DEAL_WON_TARGETS:
        assert target in client.targeted, f"DEAL_WON must fire to {target}"
        assert client.targeted[target].startswith("DEAL_WON:"), \
            f"Signal to {target} must start with DEAL_WON:"

    assert "InfraAgent" not in client.targeted, \
        "InfraAgent is not a DEAL_WON subscriber"


def test_deal_won_skips_offline_agents():
    """Agents not returned by list_agents() must not receive the signal."""
    client = _MockSwitchClient(online_agents=["CSAgent"])  # FinanceAgent offline
    _broadcast_deal_won(client, "Priya_Shah", 500000)

    assert "CSAgent" in client.targeted
    assert "FinanceAgent" not in client.targeted, \
        "Offline agent must be skipped - no phantom signals"


def test_deal_won_no_agents_online():
    """Fan-out must not raise when list_agents() returns empty."""
    client = _MockSwitchClient(online_agents=[])
    _broadcast_deal_won(client, "Test_Lead", 100000)
    assert client.targeted == {}


def test_deal_won_signal_contains_customer_name():
    """Signal payload must include the customer name."""
    client = _MockSwitchClient(online_agents=["CSAgent", "FinanceAgent"])
    _broadcast_deal_won(client, "Acme_Corp", 1200000)

    for signal in client.targeted.values():
        assert "Acme_Corp" in signal, "Customer name must appear in signal payload"


def test_deal_won_uses_single_list_agents_call(monkeypatch):
    """Dynamic fan-out must call list_agents() exactly once, not once per target."""
    call_count = 0
    original_list = _MockSwitchClient.list_agents

    def counting_list_agents(self):
        nonlocal call_count
        call_count += 1
        return original_list(self)

    monkeypatch.setattr(_MockSwitchClient, "list_agents", counting_list_agents)
    client = _MockSwitchClient(online_agents=["CSAgent", "FinanceAgent"])
    _broadcast_deal_won(client, "Ravi_Kumar", 300000)

    assert call_count == 1, \
        f"list_agents() called {call_count} times - must be called once for fan-out efficiency"
