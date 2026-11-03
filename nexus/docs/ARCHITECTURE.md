# NEXUS Architecture

## Overview

NEXUS is a 5-agent AI coordination system built on Switch. Each agent maintains a persistent WebSocket connection to Switch, listens to its assigned room, and communicates with other agents via Switch's `send_targeted_message` API.

```
Switch Platform
├── Room: nexus-sales      ← SalesAgent (anyone)
├── Room: nexus-support    ← SupportAgent (anyone)
├── Room: nexus-growth     ← GeoSEOAgent (owner_and_owner_agents)
├── Room: nexus-content    ← BlogAgent (owner_and_owner_agents)
└── Room: nexus-devops     ← InfraAgent (anyone)
```

---

## Agent Details

### SalesAgent
- **Addressing:** `anyone` — reads every message in the sales room
- **Passive:** Scans all messages for commitments using Claude (LLM classification)
- **Commands:** `new lead`, `pipeline`, `follow up`, `format`, `won`, `lost`, `stale leads`, `lead card`
- **Scheduler:** Checks overdue commitments every N minutes, fires escalation messages

### SupportAgent
- **Addressing:** `anyone` — reads every message in the support room
- **Passive:** Detects bug keywords and auto-triages via LLM
- **Commands:** `bug`, `status`, `close`, `bugs` (filtered list)

### GeoSEOAgent
- **Addressing:** `owner_and_owner_agents` — only receives @mentions and cross-agent signals
- **Scheduler:** Runs keyword analysis cycle every 24h (configurable)
- **Cross-agent out:** Sends `BRIEF:` signals to BlogAgent via `send_targeted_message`
- **Cross-agent in:** Receives `POST_PUBLISHED:` from BlogAgent

### BlogAgent
- **Addressing:** `owner_and_owner_agents` — receives @mentions and GeoSEO briefs
- **Cross-agent in:** Receives `BRIEF:` signals from GeoSEOAgent
- **Cross-agent out:** Sends `POST_PUBLISHED:` to GeoSEOAgent after publishing
- **LLM:** Uses Ollama (Mistral) locally to generate drafts

### InfraAgent
- **Addressing:** `anyone` — receives @mentions in devops room
- **Scheduler:** Health checks every 5 minutes
- **Alert:** Posts to room + pings on-call when consecutive_failures >= threshold

---

## The GeoSEO → Blog Loop

```
GeoSEOAgent runs analysis
    │
    ├── Fetches keyword data (SerpAPI or mock)
    ├── Detects trending keywords or content gaps
    ├── Creates record in content_queue
    └── Sends BRIEF: signal to BlogAgent via Switch send_targeted_message
            │
            ▼
        BlogAgent receives brief
            ├── Generates 600-word draft via LLM
            ├── Stores in content_queue with status=draft_ready
            └── Posts preview to #nexus-content for approval
                    │
                    ▼
                Human types "approve"
                    │
                    ├── BlogAgent publishes to CMS
                    ├── Sends POST_PUBLISHED: back to GeoSEOAgent
                    └── GeoSEOAgent starts tracking rankings for the keyword
```

This loop only works because Switch provides:
1. Persistent WebSocket connections for both agents
2. `send_targeted_message` for direct cross-agent signaling
3. Room subscriptions so agents see the approval message

---

## Escalation Flow

```
SalesAgent passively detects: "Ankit said he'll send approval by Friday"
    │
    ▼
Claude classifies: commitment_found=true, deadline=Friday
    │
    ▼
Stored in commitments table with deadline
    │
    ▼ (escalation scheduler runs)
Deadline passes, status=pending
    │
    ├── Level 1 (wait_hours=24): @rep notified
    ├── Level 2 (wait_hours=24): @lead notified
    ├── Level 3 (wait_hours=24): @manager notified
    └── Level 4 (wait_hours=48): @founder notified
```

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `leads` | CRM — prospect tracking |
| `commitments` | Customer/rep promises with deadlines |
| `escalation_log` | Audit trail of all escalation messages sent |
| `content_queue` | SEO brief → draft → published lifecycle |
| `keyword_tracking` | Keyword rank tracking with history |
| `monitored_services` | URLs under infra surveillance |
| `bugs` | Support ticket tracking |

---

## LLM Strategy

| Agent | Provider | Model | Why |
|-------|----------|-------|-----|
| SalesAgent | Anthropic | claude-sonnet-4-6 | Commitment detection needs nuance |
| SupportAgent | Anthropic | claude-sonnet-4-6 | Severity classification accuracy |
| GeoSEOAgent | Anthropic | claude-sonnet-4-6 | Reserved for future analysis |
| BlogAgent | Ollama | Mistral | High-volume generation, cost sensitive |
| InfraAgent | Ollama | Phi-3 | Simple classification, fast response |

---

## Why Switch Is Central

Without Switch, the system degrades completely:
- Agents cannot receive messages (no WebSocket)
- Cross-agent signals (`BRIEF:`, `POST_PUBLISHED:`) cannot be delivered
- The GeoSEO→Blog loop breaks
- Escalation messages cannot be posted to rooms
- Room addressing modes (`anyone` vs `owner_and_owner_agents`) control passive scan vs targeted — this distinction is a Switch primitive

The system is architecturally dependent on Switch, not just integrated with it.
