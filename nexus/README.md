# NEXUS — AI Business Command Center

Five AI agents living inside Switch, coordinating over WebSocket. Sales escalation, bug triage, SEO content loop, infra monitoring — all in one workspace.

**Hackathon:** Flip the Switch (Nov 4-7, 2026) | Track 01: Best Business Workflow

---

## Quickstart

### 1. Prerequisites
- Docker + Docker Compose
- Python 3.11+
- Switch workspace (local Docker or hosted)
- Anthropic API key

### 2. Configure
```bash
cp .env.example .env
# Edit .env -- fill in Anthropic key, Switch registration key
```

### 3. Start PostgreSQL
```bash
docker compose up postgres -d
```

### 4. Register agents + init DB
```bash
pip install -r requirements.txt
python db_init.py
python switch_setup.py
# Then add SWITCH_ROOM_ID_* values to .env from Switch Console
```

### 5. Launch everything
```bash
make start
# or for demo mode (5-min escalations, 1-hour SEO):
make demo-mode
```

### 6. Seed demo data
```bash
make seed
```

### 7. Verify
```bash
python health_check.py
```

---

## Demo Commands

**#nexus-sales (no @mention needed):**
```
just spoke to Priya, she'll get back to us by Friday
```
SalesAgent detects the commitment and posts a tracking card.

```
@SalesAgent pipeline
@SalesAgent format: hey priya following up as: executive
```

**#nexus-growth:**
```
@GeoSEOAgent run now
```
Runs keyword analysis, sends briefs to BlogAgent.

**#nexus-content (after brief arrives):**
```
approve
```
BlogAgent publishes the draft and notifies GeoSEOAgent.

**#nexus-support:**
```
the payments API is returning 500 errors and crashing
```
SupportAgent auto-triages and classifies severity.

**#nexus-devops:**
```
@InfraAgent status
@InfraAgent add: payments-api -> https://api.example.com/health
```

---

## Architecture

```
Switch Platform
├── nexus-sales    ← SalesAgent  (addressing: anyone)
├── nexus-support  ← SupportAgent (addressing: anyone)
├── nexus-growth   ← GeoSEOAgent  (addressing: owner_and_owner_agents)
├── nexus-content  ← BlogAgent    (addressing: owner_and_owner_agents)
└── nexus-devops   ← InfraAgent   (addressing: anyone)
```

Cross-agent communication uses Switch `send_targeted_message`:
- GeoSEOAgent -> BlogAgent: `BRIEF: keyword=X volume=Y ...`
- BlogAgent -> GeoSEOAgent: `POST_PUBLISHED: keyword=X url=Y`

See `docs/ARCHITECTURE.md` for the full design.

---

## Why Switch Is Central

Remove Switch and the product stops working:
- Agents have no message transport (WebSocket)
- Cross-agent signals cannot be delivered
- The GeoSEO->Blog content loop breaks
- Escalation messages cannot reach rooms
- Addressing modes (`anyone` vs `owner_and_owner_agents`) control passive scan vs targeted — this is a Switch primitive

---

## Stack

| Layer | Technology |
|-------|-----------|
| Agent transport | Switch WebSocket |
| Cloud LLM | Anthropic Claude Sonnet |
| Local LLM | Ollama (Mistral, Phi-3) |
| Database | PostgreSQL 16 |
| Scheduling | APScheduler |
| SEO data | SerpAPI (or mock) |
| Blog publishing | Custom/WordPress/Ghost API |

---

## Tracks

- **Track 01** — Best Business Workflow ($2,000)
- **Track 03** — Core Contributions to Switch ($100 x contributions)
- **Code with Wispr** — Voice integration ($500)
