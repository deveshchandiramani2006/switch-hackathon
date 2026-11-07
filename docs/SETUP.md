# NEXUS Setup Guide

Switch is the primary transport. Agents connect to Switch rooms via WebSocket, and Switch Console bridges those rooms to Slack. The Slack app itself is thin - it just receives slash commands and forwards them through Switch.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| [Switch Console](https://switchagents.ai) | Running locally or as a hosted instance |
| Python 3.11+ | `python --version` to confirm |
| PostgreSQL 16 | Via Docker Compose (included) or local install |
| Anthropic API key | `sk-ant-...` from [console.anthropic.com](https://console.anthropic.com) - OR set `LLM_MOCK_MODE=true` to skip |
| Ollama (optional) | Local LLM fallback - `ollama pull llama3.2` |

---

## 1. Clone and Configure

```bash
git clone https://github.com/deveshchandiramani2006/switch-hackathon
cd switch-hackathon
cp .env.example .env
```

Open `.env` and fill in the following:

```env
# Switch
SWITCH_REGISTRATION_KEY=            # from Switch Console → Settings → Registration Keys

# LLM (pick one)
ANTHROPIC_API_KEY=sk-ant-...        # Claude Sonnet 4.6
LLM_MOCK_MODE=false                 # set true to skip LLM entirely

# Database
DATABASE_URL=postgresql://nexus:nexus@localhost:5432/nexus
```

Leave `SWITCH_AGENT_ID_*` and `SWITCH_API_KEY_*` blank for now - you'll fill them in Step 3.

---

## 2. Install Dependencies and Start the Database

```bash
pip install -r requirements.txt
docker compose up postgres -d
python database/migrate_fresh.py
```

`migrate_fresh.py` drops and recreates all tables and loads seed data. Safe to re-run at any time.

---

## 3. Register Agents with Switch

```bash
python register_agents.py
```

This registers all 7 agents with Switch under the `SWITCH_REGISTRATION_KEY` you set above. On success it prints a block of env vars:

```
SWITCH_AGENT_ID_SALES=agent_01abc...
SWITCH_API_KEY_SALES=sk_live_...
SWITCH_AGENT_ID_FINANCE=agent_02def...
SWITCH_API_KEY_FINANCE=sk_live_...
... (one pair per agent)
```

Paste the entire block into your `.env` file. These credentials are how each agent authenticates to its Switch room.

Each agent is registered with a name, description, and `addressing_mode`:
- `anyone` - SalesAgent, FinanceAgent, GeoSEOAgent, InfraAgent
- `owner_and_owner_agents` - CSAgent, SupportAgent, BlogAgent

The addressing mode is enforced by Switch at the protocol level. You cannot override it in application code.

---

## 4. Create 7 Rooms in Switch Console and Bridge to Slack

Open Switch Console and create these 7 rooms:

| Room name | Agent | Slack channel |
|-----------|-------|---------------|
| `nexus-sales` | SalesAgent | `#nexus-sales` |
| `nexus-finance` | FinanceAgent | `#nexus-finance` |
| `nexus-cs` | CSAgent | `#nexus-cs` |
| `nexus-support` | SupportAgent | `#nexus-support` |
| `nexus-growth` | GeoSEOAgent | `#nexus-growth` |
| `nexus-content` | BlogAgent | `#nexus-content` |
| `nexus-devops` | InfraAgent | `#nexus-devops` |

For each room:
1. Switch Console → **Rooms** → **New Room**
2. Set the name as listed above
3. Under **Bridge** → select your Slack workspace
4. Copy the **Room ID** (looks like `room_01abc...`)

Add all 7 room IDs to `.env`:

```env
SWITCH_ROOM_ID_SALES=room_01...
SWITCH_ROOM_ID_FINANCE=room_02...
SWITCH_ROOM_ID_CS=room_03...
SWITCH_ROOM_ID_SUPPORT=room_04...
SWITCH_ROOM_ID_GROWTH=room_05...
SWITCH_ROOM_ID_CONTENT=room_06...
SWITCH_ROOM_ID_DEVOPS=room_07...
```

---

## 5. Run the Full Demo

```bash
make demo
```

This command:
1. Starts Postgres and runs migrations
2. Seeds demo data (leads, customers, invoices)
3. Launches all 7 agents with `LLM_MOCK_MODE=true` (no API key needed)

All 7 agents connect to Switch via WebSocket and appear as members in their respective rooms. Messages flow through Switch Console to Slack automatically.

---

## 6. Verify with `/nexus status`

In any Slack channel, run:

```
/nexus status
```

You should see a card listing all 7 agents with green online indicators, pulled live from `list_agents()`.

Then try a command in `#nexus-sales`:

```
/pipeline
```

SalesAgent should respond with the seeded pipeline within a few seconds.

---

## Running Individual Agents (without `make demo`)

```bash
# Start a single agent
python agents/sales_agent/main.py

# Start all agents manually
python run_agents.py
```

Each agent reads its `SWITCH_AGENT_ID_*` and `SWITCH_API_KEY_*` from the environment and connects to its Switch room.

---

## Secondary Setup - Slack Direct Mode (without Switch Console)

If you want to run against Slack Bolt directly - bypassing Switch Console - you can configure the Slack app manually. This is useful for local development without a Switch Console instance.

### Create a Slack App

1. Go to **https://api.slack.com/apps** → **Create New App** → **From scratch**
2. App Name: `NEXUS` - select your workspace → **Create App**

### Enable Socket Mode

1. Left sidebar → **Socket Mode** → toggle ON
2. Create App-Level Token: name `nexus-socket`, scope `connections:write` → **Generate**
3. Copy the token (starts `xapp-1-...`) - save as `SLACK_APP_TOKEN`

### Add Bot Scopes

Left sidebar → **OAuth & Permissions** → **Bot Token Scopes** - add:

| Scope | Why |
|-------|-----|
| `app_mentions:read` | Detect @mentions |
| `channels:history` | Read messages |
| `channels:read` | List channels |
| `chat:write` | Post messages |
| `users:read` | Get display names |
| `groups:history` | Read private channels |
| `commands` | Slash command responses |

### Subscribe to Events

1. Left sidebar → **Event Subscriptions** → toggle ON
2. Add bot events: `app_mention`, `message.channels`
3. **Save Changes**

### Register Slash Commands

Left sidebar → **Slash Commands** → **Create New Command** - register all 25 commands from the table in the main README. Set the Request URL to your ngrok or deployed URL.

### Install to Workspace

1. **OAuth & Permissions** → **Install to Workspace** → **Allow**
2. Copy the Bot User OAuth Token (starts `xoxb-...`) - save as `SLACK_BOT_TOKEN`

### Create 7 Channels and Get Channel IDs

Create channels: `nexus-sales`, `nexus-finance`, `nexus-cs`, `nexus-support`, `nexus-growth`, `nexus-content`, `nexus-devops`

For each channel: right-click → **View channel details** → scroll to **Channel ID** (starts `C0...`).

Add to `.env`:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-1-...
SLACK_CHANNEL_ID_SALES=C0...
SLACK_CHANNEL_ID_FINANCE=C0...
SLACK_CHANNEL_ID_CS=C0...
SLACK_CHANNEL_ID_SUPPORT=C0...
SLACK_CHANNEL_ID_GROWTH=C0...
SLACK_CHANNEL_ID_CONTENT=C0...
SLACK_CHANNEL_ID_DEVOPS=C0...
```

Then run: `python run_agents.py`

---

## Optional - Live SEO Data (SerpAPI)

Without this, GeoSEOAgent uses mock scores. Fine for demo.

1. Register at **https://serpapi.com** (free plan: 100 searches/month)
2. Copy your API key from the dashboard
3. Add to `.env`:
   ```env
   SERPAPI_KEY=your-key-here
   GEO_SEO_MOCK_MODE=false
   ```

---

## Troubleshooting

**`/nexus status` shows agents offline**
- Confirm `SWITCH_AGENT_ID_*` and `SWITCH_API_KEY_*` are set in `.env`
- Check agent logs: `docker compose logs sales_agent -f`
- Verify Switch Console is running and rooms are configured

**Agent container exits immediately**
```bash
docker compose logs <agent_name>
```
Common causes: missing env vars, Postgres not healthy (`docker compose ps`).

**Slash commands return "dispatch_failed"**
- Confirm Switch Console is running and bridged to the Slack workspace
- Confirm the room IDs in `.env` match what Switch Console shows

**"LLM daily limit reached"**
```bash
docker compose exec postgres psql -U nexus -c \
  "UPDATE tenants SET llm_calls_today=0 WHERE tenant_id='default';"
```

**Anthropic key rejected**
```bash
curl https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY"
# should return 400 (bad request), not 401 (unauthorized)
```

**Port conflict on 5000 or 5001**
```env
MANAGEMENT_API_PORT=5002
```
