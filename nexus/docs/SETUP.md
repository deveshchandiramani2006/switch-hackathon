# NEXUS Setup Guide

Complete, step-by-step instructions to get all 7 agents running from scratch.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker + Docker Compose v2 | Latest | `docker compose version` |
| Python | 3.11+ | For running artisan.py locally |
| Switch workspace | Local or hosted | See Step 1 |
| Anthropic API key | — | console.anthropic.com |

Optional (safe to skip for demo — mock modes available):
- SerpAPI key — for live SEO keyword data
- Blog CMS API — for real post publishing
- SMTP / SendGrid — for email escalation fallback
- Stripe keys — for billing integration

---

## Step 1 — Start Switch

### Option A: Local Docker
```bash
docker run -d -p 8080:8080 --name switch fliptheswitch/switch:latest
```

### Option B: Hosted Switch
Skip this step. Set `SWITCH_SERVER_URL` in `.env` to the hosted URL.

### Create 7 rooms in Switch Console

Open the Switch Console (`http://localhost:8080`) and create these rooms. Copy each room ID.

| Room name | Variable to set |
|-----------|----------------|
| `nexus-sales` | `SWITCH_ROOM_ID_SALES` |
| `nexus-support` | `SWITCH_ROOM_ID_SUPPORT` |
| `nexus-cs` | `SWITCH_ROOM_ID_CS` |
| `nexus-finance` | `SWITCH_ROOM_ID_FINANCE` |
| `nexus-growth` | `SWITCH_ROOM_ID_GROWTH` |
| `nexus-content` | `SWITCH_ROOM_ID_CONTENT` |
| `nexus-devops` | `SWITCH_ROOM_ID_DEVOPS` |

Also copy your **Registration Key** from Console → Settings.

---

## Step 2 — Configure `.env`

```bash
cd nexus/
cp .env.example .env
```

Fill in the entire `.env`. Full variable reference below.

### Required — always

```env
# Switch
SWITCH_SERVER_URL=http://localhost:8080
SWITCH_REGISTRATION_KEY=<from Switch Console → Settings>

# Room IDs (from Step 1)
SWITCH_ROOM_ID_SALES=<room_id>
SWITCH_ROOM_ID_SUPPORT=<room_id>
SWITCH_ROOM_ID_CS=<room_id>
SWITCH_ROOM_ID_FINANCE=<room_id>
SWITCH_ROOM_ID_GROWTH=<room_id>
SWITCH_ROOM_ID_CONTENT=<room_id>
SWITCH_ROOM_ID_DEVOPS=<room_id>

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# Management API — generate any strong random string
NEXUS_MASTER_KEY=your-secret-master-key-here

# Multi-tenancy — use "default" for single-tenant setup
TENANT_ID=default
```

### Required after agent registration (Step 4 writes these)

```env
# These are written automatically by: python artisan.py register-agents
SWITCH_AGENT_ID_SALES=
SWITCH_API_KEY_SALES=
SWITCH_AGENT_ID_SUPPORT=
SWITCH_API_KEY_SUPPORT=
SWITCH_AGENT_ID_CS=
SWITCH_API_KEY_CS=
SWITCH_AGENT_ID_FINANCE=
SWITCH_API_KEY_FINANCE=
SWITCH_AGENT_ID_GEOSEO=
SWITCH_API_KEY_GEOSEO=
SWITCH_AGENT_ID_BLOG=
SWITCH_API_KEY_BLOG=
SWITCH_AGENT_ID_INFRA=
SWITCH_API_KEY_INFRA=
```

### Optional — set to skip real integrations in demo

```env
# SEO — set mock mode to skip SerpAPI
SERPAPI_KEY=                     # leave blank OR:
GEO_SEO_MOCK_MODE=true           # uses mock data instead

# Blog publishing — set mock mode to skip real CMS
BLOG_API_ENDPOINT=               # leave blank OR:
BLOG_MOCK_MODE=true              # returns a fake URL (fine for demo)
BLOG_API_ADAPTER=custom          # custom | wordpress | ghost
BLOG_API_TOKEN=

# LLM provider overrides (optional — Anthropic is default for all agents)
LLM_MODEL=claude-sonnet-4-6
BLOG_LLM_PROVIDER=ollama         # use local Ollama for blog drafts
BLOG_LLM_MODEL=mistral
INFRA_LLM_PROVIDER=ollama
INFRA_LLM_MODEL=phi3

# Escalation timing (shorten for demo)
ESCALATION_CHECK_MINUTES=60      # set to 1 for demo

# SEO cycle frequency
GEO_SEO_INTERVAL_HOURS=24        # set to 1 for demo
```

### Optional — email fallback for escalations

```env
# Option A: Raw SMTP
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=you@gmail.com
EMAIL_PASS=your-app-password
EMAIL_FROM=noreply@yourdomain.com

# Option B: SendGrid (takes priority over SMTP)
SENDGRID_API_KEY=SG.xxx
```

### Optional — billing (Stripe)

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_xxx
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_ENTERPRISE=price_xxx
BILLING_SUCCESS_URL=https://yourdomain.com/billing/success
BILLING_CANCEL_URL=https://yourdomain.com/billing/cancel
BILLING_MOCK_MODE=true           # set false in production
```

### Optional — voice server

```env
WHISPER_MODEL=base               # tiny | base | small | medium
VOICE_SERVER_PORT=5001
```

---

## Step 3 — Start PostgreSQL

```bash
docker compose up postgres -d
# Wait until healthy
docker compose ps
# postgres should show "(healthy)"
```

---

## Step 4 — Initialize Database + Register Agents

```bash
pip install -r requirements.txt
```

**Run migrations** (creates all tables):
```bash
python artisan.py migrate
```

This runs all three migrations in order:
- `001_initial_schema.sql` — core tables
- `002_saas_foundation.sql` — multi-tenancy, usage analytics, approvals
- `003_operations_hardening.sql` — agent heartbeats, audit log, SLA columns

**Register all 7 agents** with Switch (writes IDs/keys directly to `.env`):
```bash
python artisan.py register-agents
```

You should see output like:
```
Registered SalesAgent   → agent_id: abc123  key: written to .env
Registered SupportAgent → agent_id: def456  key: written to .env
...
```

**Ensure default tenant config** exists:
```bash
python artisan.py ensure-tenant-config
```

---

## Step 5 — Seed Demo Data

```bash
python artisan.py seed
```

Seeds:
- 3 leads: Priya Sharma (CTO, Mumbai), Ankit Mehta (VP Sales, Bangalore), Meera Nair (Founder, Chennai)
- 1 overdue commitment from Ankit (deadline 3 days ago — triggers escalation immediately on start)
- 3 SEO keywords: "AI payroll India", "HR automation Bangalore", "startup HRMS"
- 3 monitored services: api.example.com, app.example.com, dashboard.example.com

---

## Step 6 — Build and Launch All Services

```bash
docker compose up -d --build
```

This starts:
- PostgreSQL
- 7 agent containers (sales, support, cs, finance, geo_seo, blog, infra)
- Management API (port 5000)
- Voice server (port 5001)

Check all containers are running:
```bash
docker compose ps
```

All should show `Up`. Tail logs if any exit:
```bash
docker compose logs <service_name> -f
# e.g. docker compose logs sales_agent -f
```

### For local LLM (optional)

```bash
docker compose --profile local-llm up -d
# Then pull models:
docker exec -it nexus-ollama-1 ollama pull mistral
docker exec -it nexus-ollama-1 ollama pull phi3
```

---

## Step 7 — Verify Everything Works

### Check agent liveness
```bash
curl -H "Authorization: Bearer $NEXUS_MASTER_KEY" \
  http://localhost:5000/api/v1/tenants/default/agents/status
```

All 7 agents should show `"status": "alive"` within 5 minutes of startup.

### Check management API health
```bash
curl http://localhost:5000/api/v1/health
# → {"status": "ok", "version": "2.0.0"}
```

### Smoke test in Switch rooms

**Sales room (`nexus-sales`):**
```
just spoke to Priya, she said she'll send the PO by Friday
```
→ SalesAgent detects commitment, posts tracking card with deadline

```
@SalesAgent pipeline
```
→ Shows all 3 seeded leads sorted by deal value

**Support room (`nexus-support`):**
```
@SupportAgent bug: login page crashes on mobile Safari, users can't sign in
```
→ SupportAgent classifies P0/P1, posts severity card, fires P1_BREACH to CSAgent

**Growth room (`nexus-growth`):**
```
@GeoSEOAgent run now
```
→ Runs SEO analysis, sends `BRIEF:` signal to BlogAgent

**Content room (`nexus-content`):**
```
@BlogAgent queue
```
→ Shows pending drafts from GeoSEO briefs

```
approve #1
```
→ Publishes draft #1 (requires `manager` role — see role setup below)

**DevOps room (`nexus-devops`):**
```
@InfraAgent status
```
→ Shows health of 3 seeded monitored services

---

## Step 8 — Set User Roles (Optional)

By default every user is `member`. Promote a user to allow invoice approvals and blog publishing:

```bash
curl -X PATCH \
  -H "Authorization: Bearer $NEXUS_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role": "manager"}' \
  http://localhost:5000/api/v1/tenants/default/users/<your_switch_username>/role
```

Role permissions:
| Role | Can do |
|------|--------|
| `admin` | Everything — user management, config |
| `manager` | Approve invoices, approve blog drafts, close P0 bugs |
| `member` | Create leads, file bugs, submit expenses |
| `viewer` | Read-only (pipeline, status) |

---

## Full `.env.example` Template

```env
# ── Switch ───────────────────────────────────────────────────────────────────
SWITCH_SERVER_URL=http://localhost:8080
SWITCH_REGISTRATION_KEY=

SWITCH_ROOM_ID_SALES=
SWITCH_ROOM_ID_SUPPORT=
SWITCH_ROOM_ID_CS=
SWITCH_ROOM_ID_FINANCE=
SWITCH_ROOM_ID_GROWTH=
SWITCH_ROOM_ID_CONTENT=
SWITCH_ROOM_ID_DEVOPS=

# Written by artisan.py register-agents — do not fill manually
SWITCH_AGENT_ID_SALES=
SWITCH_API_KEY_SALES=
SWITCH_AGENT_ID_SUPPORT=
SWITCH_API_KEY_SUPPORT=
SWITCH_AGENT_ID_CS=
SWITCH_API_KEY_CS=
SWITCH_AGENT_ID_FINANCE=
SWITCH_API_KEY_FINANCE=
SWITCH_AGENT_ID_GEOSEO=
SWITCH_API_KEY_GEOSEO=
SWITCH_AGENT_ID_BLOG=
SWITCH_API_KEY_BLOG=
SWITCH_AGENT_ID_INFRA=
SWITCH_API_KEY_INFRA=

# ── LLM ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=
LLM_MODEL=claude-sonnet-4-6

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://nexus:nexus_dev@localhost:5432/nexus

# ── Management API ────────────────────────────────────────────────────────────
NEXUS_MASTER_KEY=

# ── Multi-tenancy ─────────────────────────────────────────────────────────────
TENANT_ID=default

# ── SEO ──────────────────────────────────────────────────────────────────────
SERPAPI_KEY=
GEO_SEO_MOCK_MODE=true
GEO_SEO_INTERVAL_HOURS=24

# ── Blog CMS ──────────────────────────────────────────────────────────────────
BLOG_API_ENDPOINT=
BLOG_API_TOKEN=
BLOG_API_ADAPTER=custom
BLOG_MOCK_MODE=true
BLOG_LLM_PROVIDER=anthropic
BLOG_LLM_MODEL=claude-sonnet-4-6

# ── Escalation ────────────────────────────────────────────────────────────────
ESCALATION_CHECK_MINUTES=60

# ── Voice ─────────────────────────────────────────────────────────────────────
WHISPER_MODEL=base
VOICE_SERVER_PORT=5001

# ── Management API port ───────────────────────────────────────────────────────
MANAGEMENT_API_PORT=5000

# ── Email (optional) ─────────────────────────────────────────────────────────
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_USER=
EMAIL_PASS=
EMAIL_FROM=noreply@nexus.ai
SENDGRID_API_KEY=

# ── Billing / Stripe (optional) ───────────────────────────────────────────────
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_STARTER=
STRIPE_PRICE_PRO=
STRIPE_PRICE_ENTERPRISE=
BILLING_SUCCESS_URL=https://nexus.ai/billing/success
BILLING_CANCEL_URL=https://nexus.ai/billing/cancel
BILLING_MOCK_MODE=true
```

---

## Artisan Commands Reference

```bash
# Database
python artisan.py migrate                    # run all pending SQL migrations
python artisan.py ensure-tenant-config       # create default tenant config row

# Agents
python artisan.py register-agents            # register all 7 agents with Switch, write keys to .env

# Data
python artisan.py seed                       # seed demo leads, keywords, services

# Config migration (from legacy YAML)
python artisan.py migrate-config \
  --tenant-id default \
  --yaml-path company_config.yaml

# Maintenance
python artisan.py cleanup-usage              # delete usage_events older than 90 days
```

---

## Management API Quick Reference

All endpoints require `Authorization: Bearer $NEXUS_MASTER_KEY` unless noted.

```bash
# Health (no auth)
curl http://localhost:5000/api/v1/health

# Tenant
curl -H "Authorization: Bearer $KEY" http://localhost:5000/api/v1/tenants/default

# Agent liveness (alive / stale / dead)
curl -H "Authorization: Bearer $KEY" http://localhost:5000/api/v1/tenants/default/agents/status

# Usage analytics
curl -H "Authorization: Bearer $KEY" "http://localhost:5000/api/v1/tenants/default/analytics?period=7d"

# Audit log
curl -H "Authorization: Bearer $KEY" http://localhost:5000/api/v1/tenants/default/audit-log

# Cross-agent search
curl -H "Authorization: Bearer $KEY" "http://localhost:5000/api/v1/tenants/default/search?q=Acme"

# Users
curl -H "Authorization: Bearer $KEY" http://localhost:5000/api/v1/tenants/default/users

# Set role
curl -X PATCH \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"role":"manager"}' \
  http://localhost:5000/api/v1/tenants/default/users/<username>/role

# Webhook secret
curl -H "Authorization: Bearer $KEY" http://localhost:5000/api/v1/tenants/default/webhook-secret

# Billing
curl -H "Authorization: Bearer $KEY" http://localhost:5000/api/v1/tenants/default/billing
curl -X POST \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan":"pro","email":"you@company.com"}' \
  http://localhost:5000/api/v1/tenants/default/billing/checkout
```

---

## Troubleshooting

### Agent container exits immediately
```bash
docker compose logs <agent_name>
```
Most common causes:
- `SWITCH_AGENT_ID` / `SWITCH_API_KEY` not in `.env` → run `python artisan.py register-agents`
- `DATABASE_URL` wrong → check postgres is healthy: `docker compose ps`
- Switch server not reachable → `curl http://localhost:8080/health`

### "LLM daily limit reached"
Your tenant is on the `free` plan (100 LLM calls/day). Either:
- Reset: `UPDATE tenants SET llm_calls_today=0 WHERE tenant_id='default';` in psql
- Upgrade plan: `curl -X PATCH ... /api/v1/tenants/default/billing/plan -d '{"plan":"pro"}'`

### Commitment detection not working
- Verify `ANTHROPIC_API_KEY` is valid: `curl https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY"` should return a 400, not 401
- Check logs: `docker compose logs sales_agent -f`
- Passive detection requires messages without `@SalesAgent` — just type naturally in the Sales room

### GeoSEO returns mock data
Expected if `GEO_SEO_MOCK_MODE=true` or `SERPAPI_KEY` is blank. Mock mode is fine for demo.

### Blog publish returns "Publish failed"
Set `BLOG_MOCK_MODE=true` in `.env` to use mock publishing. The agent will post a fake URL and the GeoSEO loop will complete normally.

### approve #N says "insufficient role"
The user needs `manager` or higher. See Step 8 — set role via management API.

### Agent shows "stale" or "dead" in liveness check
Heartbeats are sent every 5 minutes via the scheduler. The agent is running but may not have sent its first heartbeat yet. Wait 5 minutes, then recheck. If still dead: `docker compose logs <agent> -f`.

### Port conflict (5000 / 5001)
```env
MANAGEMENT_API_PORT=5002
VOICE_SERVER_PORT=5003
```

---

## Demo Mode (Faster Timers)

For demos, shorten escalation and SEO cycle intervals:

```env
ESCALATION_CHECK_MINUTES=1
GEO_SEO_INTERVAL_HOURS=1
```

Then restart:
```bash
docker compose up -d
```

The SLA breach alert (SupportAgent) uses thresholds from `tenant_configs`. To trigger it in demo:
```sql
-- In psql: set P0 SLA to 0 hours so any P0 bug immediately breaches
UPDATE tenant_configs
SET escalation_chain = jsonb_set(
    escalation_chain,
    '{support,sla,p0_hours}',
    '0'
)
WHERE tenant_id = 'default';
```
