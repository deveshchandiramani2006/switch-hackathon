# NEXUS Agent Command Reference

All commands are Slack slash commands registered via Switch Console.
Commands marked with `[M]` open a modal form - no inline syntax required.
Commands marked with `[T]` respond inline and immediately.

Run `/nexus status` in any channel to confirm all 7 agents are online.

---

## SalesAgent (`#nexus-sales`)

| Command | Type | Description |
|---------|------|-------------|
| `/new-lead` | M | Add a new prospect - Name, Role, City, Industry, Deal Value |
| `/pipeline` | T | All active leads sorted by deal value |
| `/won Name` | T | Mark deal Closed-Won - fires DEAL_WON to Finance + CS |
| `/lost Name` | T | Mark deal Closed-Lost |
| `/follow-up Name` | T | LLM-generated follow-up draft based on lead context |
| `/commitment` | M | Track a sales commitment - Lead, Text, Due Date |

**Cross-agent out:**
- `DEAL_WON` → FinanceAgent + CSAgent on `/won Name`
- `INVOICE_OVERDUE` received from FinanceAgent → flags vendor in pipeline

---

## FinanceAgent (`#nexus-finance`)

| Command | Type | Description |
|---------|------|-------------|
| `/invoice` | M | Log invoice - Vendor, Amount, Due Date, Category |
| `/approve ID` | T | Approve invoice instantly |
| `/reject` | M | Reject invoice - Invoice ID + Reason |
| `/expense` | M | Submit expense claim - Submitter, Amount, Category, Date |

**Cross-agent in:**
- `DEAL_WON` from SalesAgent → auto-creates expected revenue invoice

**Cross-agent out:**
- `INVOICE_OVERDUE` → SalesAgent (nightly scheduler, 30+ day overdue invoices)

---

## CSAgent (`#nexus-cs`)

| Command | Type | Description |
|---------|------|-------------|
| `/customer` | M | Add customer - Company, ARR, Renewal Date |
| `/health Name` | T | LLM health score + risk signals for a customer |
| `/expansion Name` | T | LLM upsell and cross-sell angles |
| `/qbr Name` | T | LLM-generated QBR agenda |
| `/nps` | M | Log NPS score - Customer, Score (0–10), Note |

**Cross-agent in:**
- `DEAL_WON` from SalesAgent → auto-creates customer record, starts onboarding
- `P1_BREACH` from SupportAgent → marks affected accounts At Risk

> CSAgent has `addressing_mode: owner_and_owner_agents`. Only registered agents (SalesAgent, SupportAgent) can send it signals - users cannot trigger automated alerts directly.

---

## SupportAgent (`#nexus-support`)

| Command | Type | Description |
|---------|------|-------------|
| `/bug` | M | Log bug - Description + Severity dropdown (P0, P1, P2, P3) |
| `/bugs` | T | All open bugs with Resolve buttons |
| `/resolve #ID` | T | Close a bug |

**Cross-agent out:**
- `P1_BREACH` → CSAgent on P0 or P1 bug submission

**Cross-agent in:**
- `SERVICE_DOWN` from InfraAgent → auto-files a P0 bug

> SupportAgent has `addressing_mode: owner_and_owner_agents`. Automated P0 bugs can only be filed by InfraAgent - not by arbitrary users.

---

## GeoSEOAgent (`#nexus-growth`)

| Command | Type | Description |
|---------|------|-------------|
| `/geo Keyword` | T | AI citability score (1–10) + exact improvement recommendations |
| `/track` | M | Add a keyword to tracking |

**Cross-agent out:**
- `CONTENT_BRIEF` → BlogAgent when `/geo` returns a score below 7

---

## BlogAgent (`#nexus-content`)

| Command | Type | Description |
|---------|------|-------------|
| `/draft` | M | Generate AI blog draft - Topic, Target Geo |
| `/queue` | T | All drafts with Approve / Reject buttons |
| `/approve ID` | T | Publish post - card updates in-place |

**Cross-agent in:**
- `CONTENT_BRIEF` from GeoSEOAgent → triggers draft generation automatically

> BlogAgent has `addressing_mode: owner_and_owner_agents`. Drafts triggered by keyword briefs must come from GeoSEOAgent - users cannot inject content briefs directly.

---

## InfraAgent (`#nexus-devops`)

| Command | Type | Description |
|---------|------|-------------|
| `/service` | M | Register a service - Name, URL |
| `/ping URL` | T | Live HTTP check - returns status code + latency |

**Background monitoring:**
Health checks run automatically. Two consecutive failures trigger a `SERVICE_DOWN` signal to SupportAgent, which auto-files a P0 bug.

**Cross-agent out:**
- `SERVICE_DOWN` → SupportAgent on 2 consecutive health check failures

---

## Validation Formats

| Field | Accepted Formats |
|-------|-----------------|
| Money | `Rs50000`, `Rs5L`, `Rs1Cr`, `50000` |
| Date | `YYYY-MM-DD`, `DD/MM/YYYY`, `today`, `tomorrow`, `next Friday` |
| URL | Must start with `https://` |
| NPS score | Integer 0–10 |
| Severity | `P0` (critical), `P1` (major), `P2` (degraded), `P3` (minor) |
