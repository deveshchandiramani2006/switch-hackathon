# NEXUS — 7 AI Agents Coordinating via Switch

**Flip the Switch Hackathon | Track 01: Best Business Workflow**

Seven AI agents — one per business function — connected through Switch. When a deal closes in Sales, FinanceAgent logs revenue and CSAgent onboards the customer. When a P0 bug drops, SupportAgent finds CSAgent via `list_agents()` and fires a targeted signal before anyone types a message.

Remove Switch and none of the coordination works.

---

## Architecture

```
Your Slack workspace
        │
        │  (Switch Console bridges Slack ↔ Switch protocol)
        ▼
┌─────────────────────────────────────────────────────┐
│                  Switch Room Mesh                    │
│                                                      │
│  SalesAgent ──[DEAL_WON]──► FinanceAgent            │
│      │                                               │
│      └──────[DEAL_WON]──► CSAgent                   │
│                               ▲                      │
│  SupportAgent ─[P1_BREACH]────┘                     │
│                                                      │
│  GeoSEOAgent ─[CONTENT_BRIEF]─► BlogAgent           │
│                                                      │
│  InfraAgent  (monitors services, fires alerts)       │
└─────────────────────────────────────────────────────┘
        │
        │  WebSocket (SwitchClient — persistent connection)
        ▼
   7 Python agents, each in their own Switch room
```

Each agent connects via `SwitchClient` WebSocket. Cross-agent signals use `send_targeted_message()` — no hardcoded channel IDs, no broadcasting. Agents discover each other at runtime with `list_agents()`.

---

## What Switch Enables

| Without Switch | With Switch |
|----------------|-------------|
| Hardcoded Slack channel IDs per agent pair | `list_agents()` — dynamic discovery at runtime |
| Broadcast to channel (any reader picks it up) | `send_targeted_message()` — direct agent-to-agent |
| No presence awareness | Signal silently dropped if target is offline |
| HTTP polling or Slack Bolt | WebSocket with exponential-backoff reconnect |
| 7 env vars to wire one new agent | Zero config — register with Switch, discoverable immediately |

---

## The 7 Agents

| Agent | Switch Room | Responsibility |
|-------|-------------|----------------|
| SalesAgent | `nexus-sales` | Leads, pipeline, deal tracking, AI follow-ups |
| FinanceAgent | `nexus-finance` | Invoices, approvals, expense claims, revenue |
| CSAgent | `nexus-cs` | Health scores, renewals, at-risk alerts |
| SupportAgent | `nexus-support` | Bug triage, LLM severity classification (P0–P3) |
| GeoSEOAgent | `nexus-growth` | AI citability scoring, keyword tracking |
| BlogAgent | `nexus-content` | AI blog drafts, approval workflow, publishing |
| InfraAgent | `nexus-devops` | Service monitoring, live HTTP pings, failure alerts |

---

## Cross-Agent Signal Chains

```
/won Name  (in #sales)
  └─► SalesAgent fires DEAL_WON via Switch send_targeted_message
        ├─► FinanceAgent → logs revenue, creates invoice draft
        └─► CSAgent → creates health record, starts onboarding

/bug modal submit  (P0 or P1, in #support)
  └─► SupportAgent fires P1_BREACH via Switch send_targeted_message
        └─► CSAgent → flags affected accounts as At Risk

/geo keyword  (score < 7, in #growth)
  └─► GeoSEOAgent fires CONTENT_BRIEF via Switch send_targeted_message
        └─► BlogAgent → auto-drafts SEO post for the keyword
```

---

## Quickstart

### Prerequisites
- [Switch Console](https://switchagents.ai) installed and running
- Python 3.11+
- PostgreSQL 16
- Anthropic API key (or Ollama for local LLM)

### 1. Clone and configure

```bash
git clone <repo>
cd nexus
cp .env.example .env
# Fill in: SWITCH_REGISTRATION_KEY, ANTHROPIC_API_KEY, DATABASE_URL
```

### 2. Start the database

```bash
docker compose up postgres -d
python database/migrate_fresh.py
```

### 3. Register agents with Switch

```bash
pip install -r requirements.txt
python register_agents.py
# Copy the printed SWITCH_AGENT_ID_* and SWITCH_API_KEY_* into .env
```

### 4. Create rooms in Switch Console

Open Switch Console → create 7 rooms, bridge to your Slack workspace:
`nexus-sales` `nexus-finance` `nexus-cs` `nexus-support` `nexus-growth` `nexus-content` `nexus-devops`

Copy each room ID into `.env` as `SWITCH_ROOM_ID_*`.

### 5. Launch all agents

```bash
python run_agents.py
```

All 7 agents connect to Switch via WebSocket. They appear as members in their Switch rooms, and messages flow through Switch Console to Slack.

---

## Slash Commands (25 total)

Registered in Slack. Switch Console routes them to the right agent room.

`[M]` = opens a modal form   `[T]` = inline, instant

| Channel | Command | Type | What it does |
|---------|---------|------|--------------|
| `#sales` | `/new-lead` | M | Log lead — Name, Role, City, Industry, Deal Value |
| `#sales` | `/pipeline` | T | All active leads, compact list |
| `#sales` | `/won Name` | T | Close deal — fires Switch signals to Finance + CS |
| `#sales` | `/lost Name` | T | Mark deal lost |
| `#sales` | `/follow-up Name` | T | LLM-generated follow-up draft |
| `#sales` | `/commitment` | M | Set commitment — Lead, Text, Due Date |
| `#finance` | `/invoice` | M | Create invoice — Vendor, Amount, Due Date, Category |
| `#finance` | `/approve ID` | T | Approve invoice instantly |
| `#finance` | `/reject` | M | Reject invoice — ID + Reason |
| `#finance` | `/expense` | M | Expense claim — Submitter, Amount, Category, Date |
| `#cs` | `/health Name` | T | LLM health score + risk signals |
| `#cs` | `/expansion Name` | T | LLM upsell and cross-sell angles |
| `#cs` | `/qbr Name` | T | LLM-generated QBR agenda |
| `#cs` | `/customer` | M | Add customer — Company, ARR, Renewal Date |
| `#cs` | `/nps` | M | Log NPS — Customer, Score, Note |
| `#support` | `/bug` | M | Log bug — Description + Severity dropdown (P0–P3) |
| `#support` | `/bugs` | T | All open bugs with Resolve buttons |
| `#support` | `/resolve #ID` | T | Close bug |
| `#growth` | `/geo Keyword` | T | AI citability score + exact fixes |
| `#growth` | `/track` | M | Track keyword |
| `#content` | `/draft` | M | AI blog draft — Topic, Geo |
| `#content` | `/queue` | T | All drafts with Approve / Reject buttons |
| `#content` | `/approve ID` | T | Publish post — card updates in place |
| `#devops` | `/service` | M | Register service — Name, URL |
| `#devops` | `/ping URL` | T | Live HTTP check — status code + latency |

---

## Stack

| Layer | Technology |
|-------|-----------|
| Agent transport | Switch WebSocket (`SwitchClient`) |
| Cross-agent signals | Switch `send_targeted_message` + `list_agents` |
| Slack bridge | Switch Console |
| Cloud LLM | Anthropic Claude Sonnet 4.6 |
| Local LLM | Ollama (llama3.2) |
| Database | PostgreSQL 16 |
| Scheduling | APScheduler |
| UI | Slack Block Kit + modal forms |

---

## Demo

Watch the 5-minute demo: **[VIDEO LINK]**

The demo shows:
1. Switch Console with all 7 agents online
2. `/new-lead` modal → lead card in Slack
3. `/won` → Finance and CS auto-update (Switch cross-agent chain live)
4. `/bug` P0 modal → CS breach alert fires automatically
5. `/invoice` modal → one-click approval
6. `/geo` → `/draft` → published post
7. `/service` modal → `/ping` → 500 shown

---

## Project Structure

```
nexus/
├── agents/
│   ├── sales_agent/      # SalesAgent — leads, pipeline, escalation
│   ├── finance_agent/    # FinanceAgent — invoices, revenue
│   ├── cs_agent/         # CSAgent — health scores, churn detection
│   ├── support_agent/    # SupportAgent — bug triage, severity
│   ├── geo_seo_agent/    # GeoSEOAgent — AI citability scoring
│   ├── blog_agent/       # BlogAgent — drafts, approval, publishing
│   └── infra_agent/      # InfraAgent — service monitoring
├── app/
│   └── Services/
│       ├── SwitchClient.py     # WebSocket client, list_agents, send_targeted_message
│       ├── SlackClient.py      # Slack Bolt fallback + slash command routing
│       ├── ModalService.py     # 20 Slack modal definitions
│       ├── BlockBuilder.py     # Slack Block Kit helpers
│       └── LlmService.py       # Multi-provider LLM router
├── database/
│   ├── migrate_fresh.py        # Drop + recreate all tables + seed data
│   └── demo_slack_setup.py     # Post polished demo cards to channels
├── register_agents.py          # Register all 7 agents with Switch
└── run_agents.py               # Launch all 7 agents
```
