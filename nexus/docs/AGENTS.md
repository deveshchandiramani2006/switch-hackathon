# NEXUS Agent Command Reference

All commands are issued in the agent's Switch room by @mentioning the agent.
Commands marked with ✦ open a **guided wizard** — the bot asks for each field one at a time.
Commands marked with ⚡ also accept inline syntax for power users.

Type `cancel` at any step in a wizard to abort.

---

## SalesAgent (#nexus-sales)

| Command | Wizard | Description |
|---------|--------|-------------|
| `@SalesAgent new lead` | ✦⚡ | Add a new prospect |
| `@SalesAgent new lead: Name, Role, City, Industry, Value` | ⚡ | Quick add (inline) |
| `@SalesAgent pipeline` | | Full pipeline sorted by deal value |
| `@SalesAgent pipeline: Bangalore` | | Pipeline filtered by city |
| `@SalesAgent lead: Name` | | Lead card with commitments |
| `@SalesAgent follow up: Name` | | Generate AI follow-up draft |
| `@SalesAgent format` | ✦⚡ | Reformat a message in chosen style |
| `@SalesAgent won: Name` | | Mark deal Closed-Won |
| `@SalesAgent lost: Name -- reason: ...` | | Mark deal Closed-Lost |
| `@SalesAgent set commitment` | ✦⚡ | Manually track a commitment |
| `@SalesAgent stale leads` | | Leads not touched in 7+ days |
| `@SalesAgent patterns` / `memory` / `knowledge: keyword` | | Agent memory |

**Passive:** Reads every message in room. Detects commitment language and auto-starts escalation clock.

**Cross-agent out:** `DEAL_WON:` → CSAgent + FinanceAgent on `won:` command.

---

## SupportAgent (#nexus-support)

| Command | Description |
|---------|-------------|
| `@SupportAgent bug: description` | File a bug (AI classifies P0–P3) |
| `@SupportAgent status` | All open bugs |
| `@SupportAgent bugs: open P1` | Filter by status + severity |
| `@SupportAgent close: #id` | Close a bug |
| `@SupportAgent patterns` / `memory` / `knowledge: keyword` | Agent memory |

**Passive:** Scans every message for bug keywords (crash, error, timeout…) and auto-triages.

**Cross-agent out:** P0/P1 bugs send `P1_BREACH:` to CSAgent.

---

## CSAgent (#nexus-cs)

| Command | Wizard | Description |
|---------|--------|-------------|
| `@CSAgent add customer` | ✦⚡ | Onboard a new customer |
| `@CSAgent add customer: Name, Rs5L, renewal: 2027-03-31` | ⚡ | Quick add |
| `@CSAgent health: CustomerName` | | Health score + signals |
| `@CSAgent at-risk` | | Customers with health score < 70 |
| `@CSAgent renewals` / `renewals: 60` | | Upcoming renewals |
| `@CSAgent nps` | ✦⚡ | Log NPS score |
| `@CSAgent nps: Name, score: 7, note: feedback` | ⚡ | Quick NPS |
| `@CSAgent expansion: CustomerName` | | AI expansion analysis |
| `@CSAgent qbr: CustomerName` | | Generate QBR agenda |
| `@CSAgent weekly report` | | CS weekly summary |

**Cross-agent in:** `DEAL_WON:` (SalesAgent) → auto-creates customer. `P1_BREACH:` (SupportAgent) → reduces health score.

---

## FinanceAgent (#nexus-finance)

| Command | Wizard | Description |
|---------|--------|-------------|
| `@FinanceAgent invoice` | ✦⚡ | Log invoice for approval |
| `@FinanceAgent invoice: Vendor, Rs50000, due: 2026-11-15, category: software` | ⚡ | Quick add |
| `@FinanceAgent invoices` | | List all invoices |
| `@FinanceAgent approve: invoice-042` | | Approve invoice (manager+) |
| `@FinanceAgent reject` | ✦⚡ | Reject invoice with reason |
| `@FinanceAgent reject: invoice-042, reason: duplicate` | ⚡ | Quick reject |
| `@FinanceAgent expense` | ✦⚡ | Submit expense claim |
| `@FinanceAgent expense: Name, Rs3200, travel, 2026-11-04` | ⚡ | Quick expense |
| `@FinanceAgent expenses pending` | | Pending expense claims |
| `@FinanceAgent budget: Q4 marketing` | | Budget burn rate |
| `@FinanceAgent overdue` | | Overdue invoices |
| `@FinanceAgent weekly report` / `forecast` | | Financial summary / 30-day forecast |

**Cross-agent in:** `DEAL_WON:` → auto-creates expected revenue invoice.

---

## GeoSEOAgent (#nexus-growth)

| Command | Description |
|---------|-------------|
| `@GeoSEOAgent run now` | Trigger immediate analysis cycle |
| `@GeoSEOAgent trending` | Tracked keywords + volumes |
| `@GeoSEOAgent report` | SEO summary |
| `@GeoSEOAgent queue` | Content queue status |
| `@GeoSEOAgent track: keyword` | Add keyword to tracking |

**Cross-agent out:** Trending keyword → signals SalesAgent (`GEO_SIGNAL:`) + BlogAgent (`BRIEF:`).

**Cross-agent in:** `POST_PUBLISHED:` from BlogAgent → starts ranking tracking.

---

## BlogAgent (#nexus-content)

| Command | Wizard | Description |
|---------|--------|-------------|
| `@BlogAgent draft` | ✦⚡ | Generate a blog draft |
| `@BlogAgent draft: topic` | ⚡ | Quick draft |
| `@BlogAgent queue` | | Content queue |
| `@BlogAgent preview: #id` | | Preview draft |
| `approve #42` | | Approve and publish draft #42 |
| `approve #42 -- edit: change CTA to X` | | Approve with inline edit |
| `reject #42` | | Reject draft |
| `reject #42 -- reason: too long` | | Reject with reason |

**Approval requires draft ID** — prevents accidental triggers. Approval expires after 24 hours.

**Cross-agent in:** `BRIEF:` from GeoSEOAgent → triggers draft generation.

**Cross-agent out:** `POST_PUBLISHED:` to GeoSEOAgent after publish.

---

## InfraAgent (#nexus-devops)

| Command | Wizard | Description |
|---------|--------|-------------|
| `@InfraAgent status` | | Health of all monitored services |
| `@InfraAgent ping: https://url` | | One-time health check |
| `@InfraAgent add` | ✦⚡ | Add service to monitoring |
| `@InfraAgent add: service-name -> https://url` | ⚡ | Quick add |

**Automatic monitoring:** Health checks every 5 min. N consecutive failures → alert + on-call ping.

---

## Validation Formats

| Field | Accepted Formats |
|-------|-----------------|
| Money | `Rs50000`, `Rs5L`, `Rs1Cr`, `50000` |
| Date | `YYYY-MM-DD`, `DD/MM/YYYY`, `today`, `tomorrow`, `next Friday` |
| URL | Must start with `https://` |
| NPS score | Integer 0–10 |
| Severity | `P0` (critical), `P1` (major), `P2` (degraded), `P3` (minor) |

---

## Role-Based Access

| Role | Key Permissions |
|------|----------------|
| admin | All commands, user management, config |
| manager | Approve invoices, close P0 bugs, all data |
| member | Create leads, log bugs, submit expenses |
| viewer | Read-only (pipeline, status) |

Set roles via API: `PATCH /api/v1/tenants/{id}/users/{username}/role`
