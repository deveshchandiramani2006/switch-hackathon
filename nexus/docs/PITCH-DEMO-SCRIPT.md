# NEXUS - Pitch Demo Script
## Flip the Switch Hackathon | Nov 4-7 2026

---

## The Setup (30 seconds)

"Every SaaS company runs 7 disconnected teams. Sales closes a deal - Customer Success
doesn't know. Support logs a P0 - no one tells the account team. Finance sees an
overdue invoice - Sales has no idea.

NEXUS is 7 AI agents, each owning one domain, coordinating in real time."

---

## Day 1: The Hard Way

Before Switch, here is what cross-agent coordination looked like:

```python
# SlackClient.safe_signal - hardcoded channel IDs, no agent awareness
_AGENT_CHANNEL_ENV = {
    "CSAgent":  "SLACK_CHANNEL_ID_CS",
    "Finance":  "SLACK_CHANNEL_ID_FINANCE",
}
def safe_signal(self, target_name, message):
    env_var = _AGENT_CHANNEL_ENV.get(target_name)
    channel = os.getenv(env_var, "")
    self.post_message(message, room_id=channel)   # broadcast to channel
```

Problems:
- 7 env vars to maintain, one per target agent
- Broadcasting to a channel - ANY agent reading that channel picks it up
- No way to know if the target agent is actually online
- Tight coupling: add a new agent, update every other agent's config

---

## Day 2: Switch Changes Everything

With SwitchClient, agents discover each other at runtime:

```python
# SwitchClient.safe_signal - dynamic discovery via Switch list_agents()
def safe_signal(self, target_name, message):
    agents = self.list_agents()                        # ask Switch who's online
    target = next((a for a in agents if a["name"] == target_name), None)
    if target:
        self.send_targeted_message(target["id"], message)  # direct, not broadcast
    else:
        logger.info(f"{target_name} not deployed - skipping signal")
```

What Switch enabled:
| Before Switch               | After Switch                              |
|-----------------------------|-------------------------------------------|
| Hardcoded channel IDs       | `list_agents()` - dynamic discovery       |
| Channel broadcast           | `send_targeted_message()` - direct P2P    |
| No presence awareness       | Signal only fires if agent is online      |
| HTTP polling for messages   | WebSocket with exponential backoff        |
| 7 config vars per coupling  | Zero config - Switch manages the mesh     |

---

## The 5 Demo Flows

### Legend

| Symbol | Channel       | Slash Command Prefix |
|--------|---------------|----------------------|
| S      | #sales        | /pipeline /new-lead  |
| C      | #cs           | /health /at-risk     |
| F      | #finance      | /invoices /invoice   |
| T      | #support      | /bug /bugs /resolve  |
| I      | #devops       | /services /ping      |
| B      | #content      | /draft /queue        |
| G      | #growth       | /geo /geo-run        |

---

### Flow 1: Deal Won - Cross-Agent Chain (45 seconds)

What to type:
```
/won Acme Corp
```

What happens behind the scenes:
```
SalesAgent: won Acme Corp
  → Switch safe_signal("CSAgent",  "DEAL_WON: customer=Acme Corp value=50000")
  → Switch safe_signal("FinanceAgent", "DEAL_WON: customer=Acme Corp")

CSAgent receives → auto-creates health record for Acme Corp
FinanceAgent receives → creates draft invoice for Acme Corp
```

Talking point: "One command in Sales triggers two agents via Switch. Zero human
coordination. Zero channel noise. The signals go directly agent-to-agent."

---

### Flow 2: P0 Bug - Support to CS Escalation (30 seconds)

What to type:
```
/bug payment gateway returning 500 on checkout
```

What happens:
```
SupportAgent: LLM classifies severity → P0
  → logs bug #ID to database
  → Switch safe_signal("CSAgent", "P1_BREACH: customer=Unknown issue=payment_gateway_500")

CSAgent: receives breach signal
  → auto-flags all customers with payment integrations as At Risk
```

Show: `/bugs` to see the bug with severity badge and Close button inline.

---

### Flow 3: Invoice Approval (20 seconds)

What to type:
```
/invoices
```

Shows all pending invoices in one compact message with Approve / Reject buttons.

Click Approve on one. The button fires directly:
```
FinanceAgent: approve: invoice-42
  → updates DB status to 'approved'
  → posts confirmation
```

Talking point: "No separate bot command to remember. The action is right there in the message."

---

### Flow 4: At-Risk Customers (20 seconds)

What to type (in #cs):
```
/at-risk
```

Shows a compact table: customer, health score, churn risk, MRR at stake.
Buttons inline: "Flag" to escalate to SalesAgent.

Click Flag:
```
CSAgent: Switch safe_signal("SalesAgent", "CHURN_RISK: customer=BetaCorp score=35")
SalesAgent: creates follow-up task automatically
```

---

### Flow 5: Infrastructure Monitoring (15 seconds)

What to type:
```
/services
```

Shows all monitored URLs with status badge. Ping button inline.

Add a new service:
```
/nexus-add-service
```

Opens a Slack modal: service name + URL fields. Submit creates the monitor instantly.

---

## Cross-Agent Signal Map

```
SalesAgent  --[DEAL_WON]------>  CSAgent        (creates health record)
SalesAgent  --[DEAL_WON]------>  FinanceAgent   (creates invoice)
SupportAgent --[P1_BREACH]---->  CSAgent        (flags at-risk accounts)
CSAgent     --[CHURN_RISK]---->  SalesAgent     (creates follow-up)
GeoSEOAgent --[GEO_ALERT]----->  SalesAgent     (geo-targeted lead signal)
GeoSEOAgent --[CONTENT_BRIEF]-> BlogAgent       (triggers draft)
```

All routed via Switch `send_targeted_message`. No channel IDs. No config changes
needed when adding a new agent - it registers with Switch and is immediately
discoverable by all others.

---

## What We Built

| Metric                  | Count |
|-------------------------|-------|
| AI agents               | 7     |
| Slash commands          | 25    |
| Cross-agent signal types| 6     |
| Modal forms             | 8     |
| DB tables               | 12+   |
| LLM providers supported | 7     |

Switch is the backbone. Slack is the interface. Postgres is the memory.

---

## The Closing Line

"Seven agents. One protocol. No hardcoded wiring.

Add a new agent: register it with Switch. Every other agent discovers it
automatically. The mesh self-assembles.

That is NEXUS."
