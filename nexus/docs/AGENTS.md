# NEXUS Agent Reference

## SalesAgent

### Purpose
Live in `#nexus-sales`. Passively monitors every message for customer commitments. Provides CRM commands for the sales team.

### Addressing Mode
`anyone` — reads all messages in the room.

### Passive Behavior
Every message (not from an agent) is sent to Claude for commitment detection. Claude returns JSON indicating whether a commitment was found, who made it, what they committed to, and by when.

### Commands (prefix with `@SalesAgent`)

| Command | Description |
|---------|-------------|
| `new lead: Name, Role, City, Industry, Value` | Add a lead to CRM |
| `pipeline` | Show all leads by deal value |
| `pipeline: Bangalore` | Filter pipeline by city |
| `lead: Name` | Show full lead card with commitments |
| `follow up: Name` | Generate AI follow-up draft |
| `format: [msg] as: executive` | Reformat message in a tone |
| `won: Name` | Mark deal won |
| `lost: Name -- reason: X` | Mark deal lost with reason |
| `set commitment: X will do Y by Z` | Manual commitment entry |
| `stale leads` | Show leads not touched in 7+ days |

### Escalation
Runs every `ESCALATION_CHECK_MINUTES` (default 60). For each overdue commitment:
1. Waits `wait_hours` from previous escalation
2. Generates an AI message in the appropriate tone for the escalation level
3. Posts `@target message` to the room
4. Logs to `escalation_log` table

---

## SupportAgent

### Purpose
Lives in `#nexus-support`. Passively triages bug reports, tracks severity, and maintains an open bug list.

### Addressing Mode
`anyone` — reads all messages.

### Passive Behavior
Scans for keywords: crash, error, bug, broken, down, fail, 500, timeout. If detected and message is 20+ chars, auto-triages via LLM.

### Commands (prefix with `@SupportAgent`)

| Command | Description |
|---------|-------------|
| `bug: description` | File and triage a bug |
| `status` | Show all open bugs |
| `close: #id` | Close a bug |
| `bugs: open P0` | Filter bugs by status/severity |

### Severity Classification
Claude classifies every bug as P0/P1/P2/P3:
- **P0** — Production down, data loss, security breach
- **P1** — Major feature broken, blocks users
- **P2** — Degraded experience, workaround exists
- **P3** — Minor, cosmetic

---

## GeoSEOAgent

### Purpose
Lives in `#nexus-growth`. Runs keyword analysis cycles, detects trending topics and content gaps, dispatches content briefs to BlogAgent.

### Addressing Mode
`owner_and_owner_agents` — receives @mentions and cross-agent signals only.

### Scheduled Behavior
Every `GEO_SEO_INTERVAL_HOURS` (default 24), runs analysis cycle:
1. Fetches data for all tracked + initial keywords from SerpAPI (or mock)
2. For trending keywords (>200% trend) or content gaps: creates brief in `content_queue`
3. Sends `BRIEF:` signal to BlogAgent via Switch `send_targeted_message`

### Commands (prefix with `@GeoSEOAgent`)

| Command | Description |
|---------|-------------|
| `run now` | Trigger analysis cycle immediately |
| `trending` | Show tracked keywords and rankings |
| `report` | Summary stats |
| `queue` | Show content queue |
| `track: keyword` | Add keyword to tracking list |

### Cross-Agent Protocol
- **Out:** `BRIEF: keyword=X volume=Y trend=Z queue_id=N reason=W`
- **In:** `POST_PUBLISHED: keyword=X url=Y`

---

## BlogAgent

### Purpose
Lives in `#nexus-content`. Receives SEO briefs, generates drafts via LLM, posts for approval, publishes to CMS.

### Addressing Mode
`owner_and_owner_agents` — receives @mentions and GeoSEO signals.

### Workflow
1. Receives `BRIEF:` signal from GeoSEOAgent
2. Generates 600-word SEO blog post via Ollama/Mistral
3. Posts draft preview to room for human approval
4. On `approve`: publishes to CMS, signals GeoSEOAgent
5. On `reject`: removes from queue

### Commands (prefix with `@BlogAgent`)

| Command | Description |
|---------|-------------|
| `draft: topic` | Manual draft request |
| `queue` | Show content queue |
| `preview: #id` | Preview a specific draft |

### Direct Commands (no @mention needed)
| Message | Action |
|---------|--------|
| `approve` | Approve and publish top draft |
| `reject` | Reject top draft |

### Blog API Adapters
Set `BLOG_API_ADAPTER` to: `custom` (default), `wordpress`, or `ghost`.
Set `BLOG_MOCK_MODE=true` to skip actual publishing (returns mock URL).

---

## InfraAgent

### Purpose
Lives in `#nexus-devops`. Monitors service health every 5 minutes, alerts on-call when services go down.

### Addressing Mode
`anyone` — receives all messages but only responds to @mentions.

### Scheduled Behavior
Every 5 minutes:
1. HTTP GET each monitored service URL
2. If response >= 500 or unreachable: increment `consecutive_failures`
3. If `consecutive_failures >= failure_threshold` (default 2): post alert to room tagging on-call

### Commands (prefix with `@InfraAgent`)

| Command | Description |
|---------|-------------|
| `status` | Show all monitored services |
| `ping: url` | One-time health check |
| `add: name -> url` | Add service to monitoring |
| `jobs` | Show scheduler info |
