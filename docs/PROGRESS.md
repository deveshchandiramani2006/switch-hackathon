# NEXUS Progress Log

## Day 1 - Nov 4, 2026

### Infrastructure
- [x] Project structure created (Laravel-inspired: app/, routes/, bootstrap/, database/, docker/)
- [x] Docker Compose with PostgreSQL + 7 agents + management API + voice server
- [x] PostgreSQL schema (25+ tables across 3 migration files)
- [x] `artisan.py` - CLI for migrations, agent registration, seeding, config migration

### Shared Services
- [x] `app/Services/SwitchClient.py` - WebSocket client with ping/pong, auto-reconnect, post_message, send_targeted_message, list_agents, safe_signal, record_heartbeat, read_context
- [x] `app/Services/LlmService.py` - Anthropic / OpenAI / Ollama backends + retry + circuit breaker
- [x] `app/Services/DatabaseService.py` - psycopg2 context manager
- [x] `config/app.py` - env-based config

### SalesAgent
- [x] Passive commitment detection via Claude
- [x] Commands: new lead, pipeline, follow up, format, won, lost, stale leads, lead card
- [x] Escalation scheduler with 4-level chain

### SupportAgent
- [x] Passive bug keyword detection
- [x] LLM severity classification (P0/P1/P2/P3)
- [x] Commands: bug, status, close, filtered list

### InfraAgent
- [x] 5-minute health check scheduler
- [x] On-call alerting with consecutive failure threshold
- [x] Commands: status, ping, add service

## Day 2 - Nov 5, 2026

### GeoSEOAgent
- [x] SerpAPI integration with mock fallback
- [x] Analysis cycle: trend detection + content gap detection
- [x] Cross-agent signaling to BlogAgent via Switch send_targeted_message
- [x] Commands: run now, trending, report, queue, track

### BlogAgent
- [x] BRIEF: signal handler
- [x] LLM draft generation (600-word SEO post)
- [x] Approval flow (approve/reject)
- [x] CMS publishing (custom/WordPress/Ghost adapters)
- [x] Cross-agent POST_PUBLISHED: signal to GeoSEOAgent
- [x] Commands: draft, queue, preview

### Demo Data
- [x] `database/seeders/DemoSeeder.py` - 3 leads, overdue commitment, keywords, monitored services (`python artisan.py seed`)

### Documentation
- [x] SETUP.md - full setup guide
- [x] ARCHITECTURE.md - system design, loop, escalation flow
- [x] AGENTS.md - command reference for all agents
- [x] README.md - quickstart

## Day 3 - Nov 6, 2026

### P0: Wire Dead Services (All Three Now Active)
- [x] `FeatureGateService.gate_llm()` wired into all LLM-calling handler functions across 5 agents (SupportAgent triage, CSAgent expansion/QBR, BlogAgent draft generation + edit approval)
- [x] `UserIdentityService.has_role()` enforced: FinanceAgent `approve`/`reject` require `manager+`; BlogAgent `approve #N` requires `manager+`
- [x] `UsageAnalyticsService.log()` called at top of `route_command` in all 7 agent handlers - every command is now logged to `usage_events`

### P0: LLM Reliability
- [x] `LlmService.complete()` - 3-attempt exponential backoff (1s, 2s) on primary provider before falling back; then configured fallback provider (2 attempts); then Ollama as last resort
- [x] Feature gate integrated directly into `complete()` via optional `tenant_id`/`client` params

### P1: SLA Breach Alerts
- [x] `SupportAgent` scheduler - `_check_sla_breaches()` runs every 30 min
- [x] Reads SLA thresholds from `TenantConfig` (p0_hours=2, p1_hours=8 defaults)
- [x] Posts in-channel alert for P0/P1 bugs exceeding SLA, marks `sla_breach_notified=TRUE` to prevent spam

### P1: Agent Liveness Monitoring
- [x] `SwitchClient.record_heartbeat()` - upserts into `agent_heartbeats` table
- [x] All 7 agent schedulers call `record_heartbeat()` every 5 min
- [x] `GET /api/v1/tenants/{id}/agents/status` - returns alive/stale/dead status per agent (stale > 10 min, dead > 30 min)

### P2: Audit Log
- [x] `audit_log` table in migration 003 - actor, action, target, before/after JSONB
- [x] Management API writes audit entries on: tenant delete, config update, role change, webhook secret rotation, GDPR purge
- [x] `GET /api/v1/tenants/{id}/audit-log?limit=50` - returns recent entries
- [x] Pass `X-Actor: <username>` header to attribute API calls to a human

### P2: GDPR Hard Delete
- [x] `DELETE /api/v1/tenants/{id}/purge` - wipes all data across 23 tables, then removes tenant row
- [x] Writes final audit entry before purging (preserved since audit_log is deleted last)
- [x] Soft delete (`DELETE /api/v1/tenants/{id}`) still available for recoverable removals

### Infrastructure
- [x] Migration `003_operations_hardening.sql` - `agent_heartbeats`, `audit_log`, `sla_breach_notified` column on bugs, `auto_resolved`/`resolved_text` on commitments

## Day 3 (Continued) - Operations Hardening Round 2

### P0: Config + Integration Fixes
- [x] InfraAgent monitor reads threshold and on-call chain from `TenantConfig`, not `company_config.yaml` - last YAML holdout eliminated
- [x] `publisher.py` - no longer returns the API endpoint URL as a fake published URL; logs error and returns `None` if response has no `url`/`link`/`permalink` key

### P1: Circuit Breaker
- [x] `LlmService._dispatch()` wrapped with `_CircuitBreaker` (5-failure threshold, 120s recovery). CLOSED → OPEN → HALF_OPEN state machine, per-provider, in-memory singleton
- [x] Combined with existing retry (3 attempts + backoff): retry handles transient errors, circuit breaker handles sustained outages

### P1: Room Context for LLM
- [x] `SwitchClient.read_context(room_id, limit)` - fetches recent room messages via Switch REST API
- [x] `commitment.py` - loads last 5 room messages as context block before passing message to LLM, improving commitment detection accuracy in multi-turn threads

### P1: Commitment Auto-Resolve
- [x] `detect_resolution(client, message, user, tenant_id)` - LLM classifies passive "done" language (sent, submitted, shared, completed)
- [x] On match: finds most recent pending commitment for that user, marks `status=kept`, `auto_resolved=TRUE`, posts in-channel confirmation
- [x] Wired into `sales_agent/handlers.py` passive scan alongside `detect_commitment`

### P2: CS Health Score Decay
- [x] `_health_decay_check` in `cs_agent/scheduler.py` - runs daily at 02:00
- [x] Reduces `health_score` by 5 (floor 10) for active customers with no `customer_events` in last 14 days
- [x] Prevents stale customers from forever holding an inflated score

### P2: Email Fallback for Escalations
- [x] `app/Services/EmailService.py` - SMTP + SendGrid transports, graceful no-op when unconfigured
- [x] `sales_agent/escalation.py` - sends email for escalation Level 3+ if `email` key present in level config

### P2: Management API Rate Limiting
- [x] `auth.py` - `require_master_key_with_rate_limit`: token bucket, 120 req/min per API key, returns 429 JSON on breach

### P3: Billing Integration
- [x] `app/Services/BillingService.py` - Stripe checkout session creation, webhook handler (payment → plan update, failure → downgrade to free), mock mode via `BILLING_MOCK_MODE=true`
- [x] `GET /api/v1/tenants/{id}/billing` - plan info + upgrade options
- [x] `POST /api/v1/tenants/{id}/billing/checkout` - create Stripe checkout session
- [x] `PATCH /api/v1/tenants/{id}/billing/plan` - admin override (audit-logged)
- [x] `POST /api/v1/billing/webhook` - Stripe webhook (unauthenticated, Stripe-signed)

### P3: Cross-Agent Entity Search
- [x] `GET /api/v1/tenants/{id}/search?q=Acme` - single query across leads, customers, bugs, invoices, content_queue; returns unified JSON result

### P3: Voice Integration (Whisper)
- [x] `VoiceService.py` - Whisper transcription (lazy-load model), keyword-based agent routing, DB logging to `voice_transcriptions`
- [x] `VoiceController.py` - `/health`, `/transcribe`, `/voice-command` endpoints
- [x] `/voice-command` posts transcribed message directly to Switch room via `_post_to_switch` (uses `SWITCH_AGENT_ID_VOICE` / `SWITCH_API_KEY_VOICE`)
- [x] Auto-detects target agent from transcript keywords; falls back gracefully if voice credentials not set
- [x] Voice server runs as separate Docker service on port 5001 (`docker/Dockerfile.voice`)

### Documentation
- [x] `docs/SETUP.md` - full rewrite: artisan.py workflow, all env vars, Switch room setup, troubleshooting, demo mode shortcuts
- [x] `.env.example` - updated with all current vars (Stripe, SMTP, SendGrid, voice agent, TENANT_ID, billing mock flags)

## Day 2 (Continued) - SaaS Foundation

### P0: Multi-Tenancy
- [x] `SwitchClient` carries `tenant_id` (from `TENANT_ID` env var per container)
- [x] All 6 agent `main.py` files read `TENANT_ID` and pass to `SwitchClient`
- [x] All agent handlers use `client.tenant_id` - no more `TENANT_ID = "default"`
- [x] All schedulers use `client.tenant_id`
- [x] `TenantResolver` service for future shared-infra multi-tenant deployments
- [x] Migration 002: adds `workspace_id`, `room_mappings`, `webhook_secret`, LLM usage columns to tenants

### P0: Modal UX (ConversationService)
- [x] `ConversationService` - stateful wizard backed by `conversation_sessions` table
- [x] 10 commands across 6 agents converted to guided forms
- [x] Each field validates with `ValidationService` - helpful errors, not silent failures
- [x] `cancel` exits at any step; sessions expire in 15 minutes
- [x] Inline syntax still works for power users (backward compatible)
- [x] DATA-VARIANT functions (`cmd_new_lead_data`, etc.) wired into ConversationService executor

### P1: Tenant-Aware Config
- [x] `TenantConfig` model - escalation chains, thresholds, agent flags in `tenant_configs` JSONB table
- [x] Escalation engine reads from DB per tenant (not global YAML)
- [x] `artisan.py migrate-config` - migrate legacy company.yaml → DB
- [x] `artisan.py ensure-tenant-config` - create default row if missing
- [x] Migration runner updated: tracks applied files in `schema_migrations` table, idempotent re-runs

### P1: Input Validation
- [x] `ValidationService` - `validate_money`, `validate_date`, `validate_url`, `validate_integer`, `validate_severity`, `validate_role`
- [x] All modal wizard fields validated with helpful error messages
- [x] Date parser handles relative formats: today, tomorrow, next Friday

### P1: Approval Flow Hardening
- [x] BlogAgent: bare "approve"/"reject" removed
- [x] New syntax: `approve #42` / `reject #42 -- reason: ...`
- [x] `approve #42 -- edit: change CTA to X` for approve-with-edits
- [x] `approve_draft_by_id` / `reject_draft_by_id` with tenant_id scoping
- [x] `approval_sessions` table for structured approval tracking

### P2: User Identity + Roles
- [x] `UserIdentityService` - sender → TenantUser with role (admin/manager/member/viewer)
- [x] Role hierarchy: admin > manager > member > viewer
- [x] Auto-creates `member` on first interaction
- [x] `set_user_role` API endpoint: `PATCH /api/v1/tenants/{id}/users/{username}/role`
- [x] `list_users` endpoint

### P2: Webhook Security
- [x] `webhook_secret` auto-generated per tenant on create
- [x] `require_webhook_signature` middleware: verifies `X-Nexus-Signature: sha256=<hmac>` 
- [x] All 3 webhook endpoints now require HMAC signature
- [x] `GET /api/v1/tenants/{id}/webhook-secret` to retrieve
- [x] `POST /api/v1/tenants/{id}/webhook-secret/rotate` to rotate

### P3: Subscription Tiers
- [x] `FeatureGateService` - free (100/day), starter (300/day), pro (1000/day), enterprise (unlimited)
- [x] Daily LLM call counter with auto-reset
- [x] `gate_llm()` posts upgrade message when limit hit

### P3: Onboarding Flow
- [x] `OnboardingService` - 4-step wizard (welcome → company name → escalation contact → first command)
- [x] `onboarding_sessions` table tracks step completion
- [x] `GET /api/v1/tenants/{id}/onboarding` returns step status

### P3: Usage Analytics
- [x] `UsageAnalyticsService` - logs every command (tenant, agent, command, user, success, latency_ms)
- [x] `GET /api/v1/tenants/{id}/analytics?period=7d` returns aggregated summary
- [x] `cleanup_old_events` for 90-day rolling retention

### New API Endpoints
- [x] `GET/PATCH /api/v1/tenants/{id}/config`
- [x] `GET/POST /api/v1/tenants/{id}/webhook-secret[/rotate]`
- [x] `GET /api/v1/tenants/{id}/analytics`
- [x] `GET /api/v1/tenants/{id}/onboarding`
- [x] `GET /api/v1/tenants/{id}/users`
- [x] `PATCH /api/v1/tenants/{id}/users/{username}/role`

### Documentation
- [x] ARCHITECTURE.md - updated with multi-tenancy model, services, API reference, tiers, roles
- [x] AGENTS.md - full command reference with wizard indicators (✦⚡), role gates, validation formats
- [x] PROGRESS.md - this file

---

## Demo Checklist
- [ ] Switch server running
- [ ] All 7 agents connected (check logs), each with TENANT_ID env var set
- [ ] Demo data seeded (`python artisan.py seed`)
- [ ] Multi-tenancy: `TENANT_ID` env var verified per container
- [ ] Sales: `@SalesAgent new lead` → wizard starts (5 prompts)
- [ ] Sales: passive commitment detection
- [ ] Sales: escalation fires (ESCALATION_CHECK_MINUTES=1 for demo)
- [ ] CS: `@CSAgent add customer` → wizard
- [ ] Finance: `@FinanceAgent invoice` → wizard
- [ ] Finance: `@FinanceAgent approve: invoice-001` as non-manager → role denied
- [ ] Growth: `@GeoSEOAgent run now` → briefs to blog
- [ ] Content: `approve #N` → publish (manager role required)
- [ ] DevOps: `@InfraAgent add` → wizard, then status
- [ ] Webhook: test with HMAC signature
- [ ] Analytics: `GET /api/v1/tenants/default/analytics` → shows real command counts
- [ ] Liveness: `GET /api/v1/tenants/default/agents/status` → all 7 alive
- [ ] Audit log: `GET /api/v1/tenants/default/audit-log`
- [ ] LLM gate: set plan=free in DB, trigger 101st LLM call → upgrade message appears
- [ ] SLA: file a P0 bug, wait 2h (or set p0_hours=0 for demo) → breach alert fires
