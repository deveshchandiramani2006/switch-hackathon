# NEXUS Architecture

## Overview

NEXUS is a multi-agent AI operations platform built on Switch. Six agents serve as the AI backbone for Sales, Support, CS, Finance, Content, and DevOps — all coordinated through Switch's persistent WebSocket and cross-agent messaging primitives.

```
Switch Platform
├── Room: nexus-sales      ← SalesAgent   (anyone)
├── Room: nexus-support    ← SupportAgent (anyone)
├── Room: nexus-cs         ← CSAgent      (owner_and_owner_agents)
├── Room: nexus-finance    ← FinanceAgent (owner_and_owner_agents)
├── Room: nexus-growth     ← GeoSEOAgent  (owner_and_owner_agents)
├── Room: nexus-content    ← BlogAgent    (owner_and_owner_agents)
└── Room: nexus-devops     ← InfraAgent   (anyone)
```

---

## Multi-Tenancy Model

Each Docker container serves **one tenant** — tenant isolation by deployment, not by application logic.

```
TENANT_ID (env var)
    └─► SwitchClient.tenant_id
            └─► passed to every handler, DB query, scheduler
```

For shared-infra deployments (future), `TenantResolver` maps `workspace_id` or Switch `room_id` to a `tenant_id` via the `tenants.room_mappings` JSONB column.

**New tables (migration 002):**
| Table | Purpose |
|-------|---------|
| `tenant_users` | Per-tenant user registry with roles (admin/manager/member/viewer) |
| `tenant_configs` | Per-tenant config in JSONB — replaces single company.yaml |
| `conversation_sessions` | Active modal wizard state (expires in 15 min) |
| `approval_sessions` | Blog/invoice approval tracking with timeout and scoped approver |
| `usage_events` | Every command execution logged for analytics (90-day rolling) |
| `onboarding_sessions` | Setup wizard step tracking per tenant |

---

## Service Layer

```
app/Services/
├── SwitchClient.py         — WebSocket client (now carries tenant_id)
├── TenantResolver.py       — Resolves tenant from env var / workspace / room
├── ConversationService.py  — Stateful modal wizard for multi-field commands
├── ValidationService.py    — Field-level validators with helpful error messages
├── UserIdentityService.py  — Sender → TenantUser with role hierarchy
├── FeatureGateService.py   — Subscription tier enforcement + LLM usage tracking
├── UsageAnalyticsService.py — Command execution logging, 90-day analytics
├── OnboardingService.py    — 4-step setup wizard for new tenants
├── LlmService.py           — Anthropic / Ollama backends
├── DatabaseService.py      — psycopg2 context manager
├── MemoryService.py        — Agent event log + pattern extraction
├── ApprovalsService.py     — Approval request lifecycle
├── DigestService.py        — Morning digest generator
└── ProactiveService.py     — Unprompted intelligence signals

app/Models/
├── Tenant.py               — Tenant CRUD helpers
└── TenantConfig.py         — Per-tenant config (escalation, thresholds, flags)
```

---

## Modal / Guided Input (ConversationService)

Commands with ≥ 3 inputs trigger a guided in-channel wizard instead of requiring users to remember comma syntax.

**Flow:**
```
User: @SalesAgent new lead
Bot:  New Lead — 1 of 5
      Lead's full name?
User: Priya Sharma
Bot:  Step 2 of 5
      Their role or title?
...  (continues for all fields)
Bot:  Lead added (#12) — Priya Sharma — CTO @ Mumbai
```

State stored in `conversation_sessions` table (tenant, room, sender, agent, step, collected JSONB). Sessions expire after 15 minutes; user can type `cancel` at any step.

**Commands with modal wizards:**

| Agent | Trigger | Fields |
|-------|---------|--------|
| SalesAgent | `new lead` | name, role, city, industry, deal value |
| SalesAgent | `set commitment` | person, action, deadline |
| SalesAgent | `format` | message text, style |
| CSAgent | `add customer` | name, ARR, renewal date |
| CSAgent | `nps` | customer, score, note |
| FinanceAgent | `invoice` | vendor, amount, due date, category |
| FinanceAgent | `expense` | submitter, amount, category, date |
| FinanceAgent | `reject` | invoice ID, reason |
| InfraAgent | `add` | service name, health URL |
| BlogAgent | `draft` | topic, geo, tone |

Inline syntax still works for power users: `@SalesAgent new lead: Name, Role, City, Industry, Value`

---

## Approval Flow (Hardened)

BlogAgent requires explicit draft IDs in approvals — prevents accidental triggers from unrelated messages.

```
Bot:   Draft ready (#42)
       "Best AI Payroll Tools in Hyderabad 2026"
       Reply: approve #42   or   reject #42 -- reason: too long

User:  approve #42
Bot:   Published → https://blog.example.com/...

User:  approve #42 -- edit: change CTA to "Book a demo"
Bot:   Applying edit...
       Published → https://blog.example.com/...
```

---

## Escalation Flow

```
SalesAgent passively detects: "Ankit said he'll send approval by Friday"
    │
    ▼
Claude classifies: commitment_found=true, deadline=Friday
    │
    ▼
Stored in commitments table with deadline + tenant_id
    │
    ▼  (escalation scheduler — interval from TenantConfig.thresholds)
Deadline passes, status=pending
    │
    ├─ Level 1 (wait_hours configurable per tenant): @rep notified
    ├─ Level 2: @lead notified
    ├─ Level 3: @manager notified
    └─ Level 4: @founder notified

Escalation chain loaded from tenant_configs.escalation_chain (not YAML).
```

---

## The GeoSEO → Blog Loop

```
GeoSEOAgent runs analysis (scheduler, 24h)
    │
    ├── Fetches keyword data (SerpAPI or mock), filters by tenant_id
    ├── Detects trending keywords or content gaps
    ├── Creates record in content_queue
    └── Sends BRIEF: signal to BlogAgent via Switch send_targeted_message
            │
            ▼
        BlogAgent receives brief
            ├── Generates 600-word draft via LLM
            ├── Stores in content_queue with status=draft_ready
            └── Posts "Draft ready (#N)" with approve #N / reject #N syntax
                    │
                    ▼
                Human types: approve #42
                    │
                    ├── BlogAgent publishes to CMS
                    ├── Sends POST_PUBLISHED: back to GeoSEOAgent
                    └── GeoSEOAgent tracks rankings for the keyword
```

---

## API Reference

### Management API (port 5000)

All endpoints require `Authorization: Bearer <MASTER_KEY>` unless noted.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/tenants` | Create tenant |
| GET | `/api/v1/tenants/{id}` | Get tenant details |
| PATCH | `/api/v1/tenants/{id}` | Update tenant |
| DELETE | `/api/v1/tenants/{id}` | Soft-delete tenant |
| GET | `/api/v1/tenants/{id}/pipeline` | Sales pipeline data |
| GET | `/api/v1/tenants/{id}/incidents` | Open bugs/incidents |
| POST | `/api/v1/tenants/{id}/webhooks/lead` | Ingest lead (HMAC-signed) |
| POST | `/api/v1/tenants/{id}/webhooks/bug` | Ingest bug (HMAC-signed) |
| POST | `/api/v1/tenants/{id}/webhooks/deploy` | Ingest deploy event (HMAC-signed) |
| GET | `/api/v1/tenants/{id}/webhook-secret` | Get webhook HMAC secret |
| POST | `/api/v1/tenants/{id}/webhook-secret/rotate` | Rotate webhook secret |
| GET | `/api/v1/tenants/{id}/config` | Get tenant config |
| PATCH | `/api/v1/tenants/{id}/config` | Update tenant config |
| GET | `/api/v1/tenants/{id}/analytics?period=7d` | Usage analytics |
| GET | `/api/v1/tenants/{id}/onboarding` | Onboarding step status |
| GET | `/api/v1/tenants/{id}/users` | List tenant users |
| PATCH | `/api/v1/tenants/{id}/users/{username}/role` | Set user role |
| GET | `/api/v1/health` | Health check (no auth) |

**Webhook signing:**
```
X-Nexus-Signature: sha256=<hmac-sha256(webhook_secret, raw_body)>
```

---

## Subscription Tiers

| Tier | Agents | LLM calls/day |
|------|--------|---------------|
| free | 3 | 100 |
| starter | 5 | 300 |
| pro | 7 | 1 000 |
| enterprise | 7 | unlimited |

LLM calls tracked in `tenants.llm_calls_today`, reset daily at midnight.
Over-limit message links to upgrade page.

---

## Role-Based Access

| Role | Permissions |
|------|-------------|
| admin | All commands, user management, config changes |
| manager | Approve invoices, close P0 bugs, all data commands |
| member | Create leads, log bugs, submit expenses |
| viewer | Read-only (pipeline, status) |

Auto-created as `member` on first interaction. Elevated via API or by admin.

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `tenants` | Tenant registry |
| `tenant_users` | Per-tenant user roster + roles |
| `tenant_configs` | Escalation chains, thresholds, agent flags per tenant |
| `leads` | CRM — prospect tracking |
| `commitments` | Customer/rep promises with deadlines |
| `escalation_log` | Audit trail of all escalation messages |
| `content_queue` | SEO brief → draft → published lifecycle |
| `keyword_tracking` | Keyword rank tracking with history |
| `monitored_services` | URLs under infra surveillance |
| `bugs` | Support ticket tracking |
| `customers` | CS customer roster |
| `customer_events` | CS event log (NPS, P1 breaches, etc.) |
| `invoices` | Finance invoice tracking |
| `expenses` | Finance expense claims |
| `budgets` | Budget allocation and burn tracking |
| `agent_memory` | Agent event log for pattern learning |
| `agent_patterns` | Extracted behavioral patterns |
| `approval_requests` | Generic approval workflow |
| `approval_sessions` | Blog/invoice approvals with scoped approver + timeout |
| `conversation_sessions` | Active modal wizard state |
| `usage_events` | Command execution analytics (90-day rolling) |
| `onboarding_sessions` | New-tenant setup wizard progress |
| `voice_transcriptions` | Voice command transcripts |
| `schema_migrations` | Applied migration tracking |

---

## Why Switch Is Central

Without Switch, the system degrades completely:
- Agents cannot receive messages (no WebSocket)
- Cross-agent signals (`BRIEF:`, `POST_PUBLISHED:`, `DEAL_WON:`) cannot be delivered
- The GeoSEO→Blog loop breaks
- Escalation messages cannot be posted to rooms
- Room addressing modes (`anyone` vs `owner_and_owner_agents`) control passive scan vs targeted — a Switch primitive

The system is architecturally dependent on Switch, not just integrated with it.
