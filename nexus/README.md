<br>
<div align="center">

# NEXUS

**7 AI agents. 5 autonomous signal chains. 0 human coordination.**

[![CI](https://github.com/your-org/nexus/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/nexus/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Powered by Switch](https://img.shields.io/badge/transport-Switch-7c3aed)](https://switchagents.ai)

*Built for the Flip the Switch Hackathon - Track 01: Best Business Workflow*

</div>

---

> Sales closes a deal. Finance logs revenue. CS onboards the customer.  
> Nobody sent a message. Nobody made a call. The agents did it.

NEXUS puts one AI agent in every business channel - Sales, Finance, CS, Support, Growth, Content, DevOps. They handle commands from your team and coordinate with each other automatically over **Switch**, an agent messaging protocol. When something happens in one channel, the right agents in other channels know about it instantly.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Signal Chains](#signal-chains)
- [Quickstart](#quickstart)
- [The 7 Agents](#the-7-agents)
- [Slash Commands](#slash-commands)
- [What Switch Enables](#what-switch-enables)
- [Stack](#stack)
- [Roadmap](#roadmap)
- [Project Structure](#project-structure)

---

## How It Works

Every agent connects to Switch via a persistent WebSocket. When an event happens - a deal closes, a P0 bug drops, a service goes down - the agent that knows about it queries Switch for who is online, then sends a targeted signal directly to the right agent. No shared database. No API calls between agents. No hardcoded channel IDs.

```python
# Without Switch - hardcoded, blind, breaks when anything moves
channel = os.getenv("SLACK_CHANNEL_ID_CS")
slack.chat_postMessage(channel=channel, text="DEAL_WON: Rahul")
# ↑ broadcasts to the whole channel, any reader picks it up,
#   no way to know if CSAgent is even running

# With Switch - dynamic, targeted, presence-aware
agents  = client.list_agents()                          # who is online right now?
target  = next(a for a in agents if a["name"] == "CSAgent")
client.send_targeted_message(target["id"], "DEAL_WON: Rahul")
# ↑ goes directly to CSAgent, skipped gracefully if offline,
#   no config change needed when agents are added or moved
```

---

## Architecture

```
  ╔══════════════════════════════════════════════════════════════╗
  ║                     Your Slack Workspace                     ║
  ║   #sales  #finance  #cs  #support  #growth  #content  #devops║
  ╚══════════════════════════════╤═══════════════════════════════╝
                                 │
                     Switch Console (Slack bridge)
                                 │
  ╔══════════════════════════════▼═══════════════════════════════╗
  ║                      Switch Room Mesh                        ║
  ║                                                              ║
  ║  SalesAgent ─────── DEAL_WON ──────────► FinanceAgent       ║
  ║      │                                                       ║
  ║      └──────────── DEAL_WON ──────────► CSAgent ◄───────┐   ║
  ║                                                          │   ║
  ║  SupportAgent ──── P1_BREACH ────────────────────────── ┘   ║
  ║      ▲                                                       ║
  ║      └──────────── SERVICE_DOWN ──────── InfraAgent          ║
  ║                                                              ║
  ║  GeoSEOAgent ───── CONTENT_BRIEF ──────► BlogAgent           ║
  ║                                                              ║
  ║  FinanceAgent ───── INVOICE_OVERDUE ───► SalesAgent          ║
  ║                                                              ║
  ╚══════════════════════════════╤═══════════════════════════════╝
                                 │
                     WebSocket · SwitchClient
                     persistent · auto-reconnect
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
    SalesAgent            FinanceAgent             CSAgent
    SupportAgent          GeoSEOAgent             BlogAgent
                          InfraAgent
```

Each agent runs a persistent WebSocket connection. Cross-agent signals use `send_targeted_message()` - direct delivery, not channel broadcast. Agents discover each other at runtime with `list_agents()`.

---

## Signal Chains

Five workflows that run automatically - no human in the loop.

---

### ⚡ Chain 1 - Deal Won

```
  User types:  /won Rahul Sharma  (in #nexus-sales)
               │
               ▼
         SalesAgent
         list_agents() ──── discovers FinanceAgent, CSAgent online
               │
               ├── send_targeted_message ──► FinanceAgent
               │                             └─ 💰 Revenue logged in #nexus-finance
               │
               └── send_targeted_message ──► CSAgent
                                             └─ 🏆 Customer onboarded in #nexus-cs
```

**One command. Three channels updated. Zero messages sent by humans.**

---

### ⚡ Chain 2 - P0 Bug Breach

```
  User submits:  /bug modal  (P0 severity, in #nexus-support)
                 │
                 ▼
           SupportAgent  (LLM classifies severity)
                 │
                 └── send_targeted_message ──► CSAgent
                                               └─ 🚨 P1 Breach alert in #nexus-cs
```

**CS knows about the outage before the customer calls.**

---

### ⚡ Chain 3 - GEO Score Below Threshold

```
  User types:  /geo best CRM for Indian startups  (in #nexus-growth)
               │
               ▼
         GeoSEOAgent  (LLM scores AI citability: 3/10)
               │
               └── send_targeted_message ──► BlogAgent
                                             └─ ✍️ 600-word SEO draft queued in #nexus-content
```

**Gap identified in Growth. Post drafted in Content. No back-and-forth.**

---

### ⚡ Chain 4 - Service Down

```
  InfraAgent background monitor  (every 5 min)
  2 consecutive failures on checkout-api
               │
               ▼
         InfraAgent
               │
               └── send_targeted_message ──► SupportAgent
                                             └─ 🐛 P0 bug auto-filed in #nexus-support
```

**The bug filed itself. No PagerDuty. No YAML. No human paged.**

---

### ⚡ Chain 5 - Invoice Overdue *(scheduled, runs nightly)*

```
  APScheduler  02:00 daily
  FinanceAgent queries invoices 30+ days unpaid
               │
               ▼
         FinanceAgent
               │
               └── send_targeted_message ──► SalesAgent
                                             └─ ⚠️ Account flagged in #nexus-sales
```

**Reps wake up to flags. No finance-to-sales Slack thread. The agents coordinated overnight.**

---

## Quickstart

**Prerequisites:** [Switch Console](https://switchagents.ai) running · Python 3.11+ · PostgreSQL 16

```bash
# 1. Clone and configure
git clone https://github.com/your-org/nexus
cd nexus
cp .env.example .env
# → fill in SWITCH_REGISTRATION_KEY and ANTHROPIC_API_KEY

# 2. Register all 7 agents with Switch
python register_agents.py
# → prints SWITCH_AGENT_ID_* and SWITCH_API_KEY_* - paste into .env

# 3. Create 7 rooms in Switch Console, bridge to Slack workspace
#    nexus-sales · nexus-finance · nexus-cs · nexus-support
#    nexus-growth · nexus-content · nexus-devops
#    → paste each Room ID into .env as SWITCH_ROOM_ID_*

# 4. Launch everything
make demo
```

Then open Slack and type `/nexus status` in any channel.

```
🟢 online   SalesAgent     nexus-sales
🟢 online   FinanceAgent   nexus-finance
🟢 online   CSAgent        nexus-cs
🟢 online   SupportAgent   nexus-support
🟢 online   GeoSEOAgent    nexus-growth
🟢 online   BlogAgent      nexus-content
🟢 online   InfraAgent     nexus-devops
```

> **No Anthropic key?** `make demo` sets `LLM_MOCK_MODE=true` automatically.  
> All LLM calls return realistic responses. All 5 signal chains still fire.

See [docs/SETUP.md](docs/SETUP.md) for the complete setup guide.

---

## The 7 Agents

| Agent | Channel | Switch Room | What it handles |
|-------|---------|-------------|-----------------|
| **SalesAgent** | `#nexus-sales` | `nexus-sales` | Leads, pipeline, deal tracking, AI follow-ups |
| **FinanceAgent** | `#nexus-finance` | `nexus-finance` | Invoices, approvals, expense claims, revenue |
| **CSAgent** | `#nexus-cs` | `nexus-cs` | Health scores, renewals, at-risk alerts |
| **SupportAgent** | `#nexus-support` | `nexus-support` | Bug triage, LLM severity classification (P0–P3) |
| **GeoSEOAgent** | `#nexus-growth` | `nexus-growth` | AI citability scoring, keyword tracking |
| **BlogAgent** | `#nexus-content` | `nexus-content` | AI blog drafts, approval workflow, publishing |
| **InfraAgent** | `#nexus-devops` | `nexus-devops` | Service monitoring, live HTTP pings, failure alerts |

---

## Slash Commands

25 commands registered in Slack - the maximum Slack allows.  
Switch Console routes each command to the correct agent room.

`[M]` = opens a modal form &nbsp;&nbsp; `[T]` = responds inline, instantly

#### Sales - `#nexus-sales`

| Command | Type | What it does |
|---------|------|--------------|
| `/new-lead` | M | Log a lead - Name, Role, City, Industry, Deal Value |
| `/pipeline` | T | All active leads sorted by deal value |
| `/won Name` | T | Close deal - fires DEAL_WON to Finance + CS |
| `/lost Name` | T | Mark deal lost |
| `/follow-up Name` | T | LLM follow-up draft (reads room context via `read_context()`) |
| `/commitment` | M | Track a commitment - Lead, Text, Due Date |

#### Finance - `#nexus-finance`

| Command | Type | What it does |
|---------|------|--------------|
| `/invoice` | M | Create invoice - Vendor, Amount, Due Date, Category |
| `/approve ID` | T | Approve invoice instantly |
| `/reject` | M | Reject invoice - ID + Reason |
| `/expense` | M | Expense claim - Submitter, Amount, Category, Date |

#### Customer Success - `#nexus-cs`

| Command | Type | What it does |
|---------|------|--------------|
| `/health Name` | T | LLM health score + risk signals |
| `/expansion Name` | T | LLM upsell and cross-sell angles |
| `/qbr Name` | T | LLM-generated QBR agenda |
| `/customer` | M | Add customer - Company, ARR, Renewal Date |
| `/nps` | M | Log NPS - Customer, Score, Note |

#### Support - `#nexus-support`

| Command | Type | What it does |
|---------|------|--------------|
| `/bug` | M | Log bug - Description + Severity dropdown (P0–P3) |
| `/bugs` | T | All open bugs with inline Resolve buttons |
| `/resolve #ID` | T | Close a bug |

#### Growth - `#nexus-growth`

| Command | Type | What it does |
|---------|------|--------------|
| `/geo Keyword` | T | AI citability score + exact fixes |
| `/track` | M | Track a keyword |

#### Content - `#nexus-content`

| Command | Type | What it does |
|---------|------|--------------|
| `/draft` | M | AI blog draft - Topic + Target Geography |
| `/queue` | T | All drafts with Approve / Reject buttons |
| `/approve ID` | T | Publish post - card updates in place, buttons removed |

#### DevOps - `#nexus-devops`

| Command | Type | What it does |
|---------|------|--------------|
| `/service` | M | Register service for monitoring - Name, URL |
| `/ping URL` | T | Live HTTP check - status code + latency |

---

## What Switch Enables

| Without Switch | With Switch |
|----------------|-------------|
| Hardcoded channel ID per agent pair | `list_agents()` - discover agents at runtime |
| Broadcast to channel, any reader picks it up | `send_targeted_message()` - direct P2P delivery |
| N API calls to signal N agents | `fan_out()` - one `list_agents()` call, fires to all |
| No presence check | Signal silently dropped if target is offline |
| HTTP polling or webhook | WebSocket with exponential-backoff reconnect |
| No access control on who can signal an agent | `addressing_mode` enforced at protocol level |

#### Addressing Modes

Each agent's `addressing_mode` is set deliberately - enforced by Switch, not application code.

| Agent | Mode | Reason |
|-------|------|--------|
| SalesAgent | `anyone` | Reps trigger pipeline commands directly |
| FinanceAgent | `anyone` | Finance team approves invoices via slash commands |
| **CSAgent** | `owner_and_owner_agents` | At-risk alerts must come from agents - not users |
| **SupportAgent** | `owner_and_owner_agents` | Auto-filed bugs must come from InfraAgent - prevents spoofed P0s |
| GeoSEOAgent | `anyone` | Growth team runs keyword scans on demand |
| **BlogAgent** | `owner_and_owner_agents` | CONTENT_BRIEF must come from GeoSEOAgent |
| InfraAgent | `anyone` | Ping commands and monitor alerts both need access |

> `owner_and_owner_agents` - only the room owner or other registered agents can send this agent a message. Users in Slack cannot spoof automated signals.

---

## Stack

| Layer | Technology |
|-------|------------|
| Agent transport | Switch WebSocket (`SwitchClient`) |
| Cross-agent signals | `send_targeted_message()` + `list_agents()` |
| Slack bridge | Switch Console |
| Cloud LLM | Anthropic Claude Sonnet 4.6 |
| Local LLM fallback | Ollama · llama3.2 |
| Database | PostgreSQL 16 |
| Scheduling | APScheduler |
| UI | Slack Block Kit · 11 modal forms |
| Testing | pytest · 5 unit tests · GitHub Actions CI |
| Containers | Docker Compose · per-agent Dockerfiles |

---

## Roadmap

Five chains are live. Three more are planned.

| Chain | Signal | Route | What it unlocks |
|-------|--------|-------|-----------------|
| Churn risk → outreach | `CHURN_RISK` | CSAgent → SalesAgent | Rep flagged before renewal call, not after churn |
| Publish → re-score | `POST_PUBLISHED` | BlogAgent → GeoSEOAgent | Closes the GEO loop - confirms the gap is filled |
| Shared room context | `read_context()` across agents | Sales + CS + Finance | LLM sees cross-team history, not just own channel |

The shared room model is the larger architectural shift: Sales, CS, and Finance in one Switch room. Any agent calling `read_context()` pulls the last N messages from the shared room. That is not possible with Slack alone.

---

## Project Structure

```
nexus/
│
├── agents/                        # One directory per agent
│   ├── sales_agent/
│   │   ├── main.py                # Switch-first transport setup
│   │   ├── handlers.py            # Message routing + signal handling
│   │   ├── commands.py            # Business logic + LLM calls
│   │   └── Dockerfile
│   ├── finance_agent/
│   ├── cs_agent/
│   ├── support_agent/
│   ├── geo_seo_agent/
│   ├── blog_agent/
│   └── infra_agent/
│
├── app/Services/
│   ├── SwitchClient.py            # WebSocket · list_agents · send_targeted_message
│   ├── SlackClient.py             # Slack Bolt fallback · slash command routing
│   ├── ModalService.py            # 11 Slack modal definitions
│   ├── BlockBuilder.py            # Slack Block Kit helpers
│   └── LlmService.py              # Claude / Ollama router · LLM_MOCK_MODE
│
├── database/
│   ├── migrate_fresh.py           # Drop + recreate all tables + seed data
│   └── demo_slack_setup.py        # Post demo cards to all channels
│
├── tests/
│   └── Unit/
│       └── test_signal_chains.py  # 5 tests · fan-out · presence · payload
│
├── docs/
│   ├── AGENTS.md                  # Per-agent slash command reference
│   ├── SETUP.md                   # Full setup guide (Switch + Slack)
│   └── TESTING_GUIDE.md           # End-to-end test flows
│
├── .github/workflows/ci.yml       # pytest + Docker build matrix (7 images)
├── register_agents.py             # Register all 7 agents with Switch
├── run_agents.py                  # Launch all 7 agents
├── docker-compose.yml             # Postgres + all 7 agents
└── Makefile                       # make demo · make test · make help
```

---

<div align="center">

Built at the **Flip the Switch Hackathon** · Nov 4–7 2026 · Track 01: Best Business Workflow

</div>
