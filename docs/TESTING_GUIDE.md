# NEXUS Testing Guide

All commands are Slack slash commands. There are no `@mention` commands - everything goes through the 25 registered slash commands.

Before running any test flows, confirm all agents are online:

```
/nexus status
```

You should see 7 green indicators. If any agent is offline, check [docs/SETUP.md](SETUP.md) troubleshooting.

---

## Test Flow 1 - Sales Pipeline

**Channel:** `#nexus-sales`

### Step 1 - Add a lead

Type `/new-lead` - a modal opens. Fill in:
- **Name**: Rahul Sharma
- **Role**: CTO
- **City**: Mumbai
- **Industry**: SaaS
- **Deal Value**: Rs500000

Click **Submit**.

**Expected:** Lead card in `#nexus-sales` with Follow Up and Won/Lost buttons.

### Step 2 - View the pipeline

```
/pipeline
```

**Expected:** All active leads sorted by deal value, each with Follow Up, Won, and Lost buttons.

### Step 3 - Generate a follow-up

```
/follow-up Rahul Sharma
```

**Expected:** LLM-generated follow-up message draft based on lead context (role, city, industry).

### Step 4 - Set a commitment

Type `/commitment` - modal opens. Set a commitment tied to Rahul Sharma with a due date.

### Step 5 - Mark as won (triggers cross-agent chain)

```
/won Rahul Sharma
```

**Expected - watch three channels simultaneously:**
- `#nexus-sales`: SalesAgent confirms the win
- `#nexus-finance`: FinanceAgent auto-logs a revenue invoice
- `#nexus-cs`: CSAgent auto-creates a customer record

This is Chain 1 - DEAL_WON over Switch `send_targeted_message`. SalesAgent calls `list_agents()` to discover FinanceAgent and CSAgent at runtime.

### Step 6 - Mark as lost

```
/lost Rahul Sharma
```

**Expected:** Lead status updates to Closed-Lost.

---

## Test Flow 2 - Finance

**Channel:** `#nexus-finance`

> Run after Test Flow 1 to see the auto-created invoice from Chain 1.

### Step 1 - Log an invoice

Type `/invoice` - modal opens. Fill in:
- **Vendor**: AWS
- **Amount**: Rs75000
- **Due Date**: 2026-11-30
- **Category**: infrastructure

**Expected:** Invoice card with Approve and Reject buttons.

### Step 2 - Approve via button

Click **Approve** on the invoice card.

**Expected:** Card updates to Approved status inline.

### Step 3 - Reject with reason

Type `/reject` - modal opens. Enter an invoice ID and rejection reason.

**Expected:** Card updates to Rejected with the reason shown.

### Step 4 - Log an expense

Type `/expense` - modal opens. Fill in submitter name, amount, category, and date.

**Expected:** Expense card with pending status.

---

## Test Flow 3 - Support Bugs

**Channel:** `#nexus-support`

### Step 1 - Log a P1 bug (triggers cross-agent chain)

Type `/bug` - modal opens. Fill in:
- **Description**: Checkout page crashes on payment step
- **Severity**: P1

Click **Submit**.

**Expected - watch two channels:**
- `#nexus-support`: Bug card filed with severity badge and Resolve button
- `#nexus-cs`: SupportAgent fires P1_BREACH to CSAgent → at-risk alert for affected accounts

This is Chain 2 - P1_BREACH over Switch `send_targeted_message`.

### Step 2 - Log a P0 bug

Type `/bug` again with severity P0. Same chain fires.

### Step 3 - View all bugs

```
/bugs
```

**Expected:** All open bugs listed by priority, each with a Resolve button.

### Step 4 - Resolve a bug

```
/resolve #1
```

Or click **Resolve** on the bug card.

**Expected:** Bug status updates to Resolved.

---

## Test Flow 4 - Customer Success

**Channel:** `#nexus-cs`

> CSAgent gets customers automatically from Chain 1 (DEAL_WON). You can also add manually.

### Step 1 - Add a customer manually

Type `/customer` - modal opens. Fill in company name, ARR, and renewal date.

### Step 2 - Health check

```
/health TechCorp
```

**Expected:** LLM-generated health score (0–100) + risk signals (NPS, ticket volume, renewal proximity).

### Step 3 - Expansion analysis

```
/expansion TechCorp
```

**Expected:** LLM-generated upsell and cross-sell recommendations.

### Step 4 - QBR prep

```
/qbr TechCorp
```

**Expected:** LLM-generated QBR agenda with talking points.

### Step 5 - Log an NPS score

Type `/nps` - modal opens. Enter customer name, score (0–10), and a note.

---

## Test Flow 5 - GEO Score and Content Brief

**Channels:** `#nexus-growth` then `#nexus-content`

### Step 1 - Run a GEO score (triggers cross-agent chain)

```
/geo invoicing software india
```

**Expected:**
- If score >= 7: Score card with current citability rating and improvement notes
- If score < 7: Score card PLUS BlogAgent receives a CONTENT_BRIEF signal in `#nexus-content` automatically

This is Chain 3 - CONTENT_BRIEF over Switch `send_targeted_message`.

### Step 2 - Track a keyword

Type `/track` - modal opens. Add `invoicing software india` to tracking.

### Step 3 - Check the content queue

Switch to `#nexus-content`:

```
/queue
```

**Expected:** If Chain 3 fired, you should see a pending draft for the keyword.

### Step 4 - Generate a manual draft

Type `/draft` - modal opens. Fill in topic and target geo.

**Expected:** Draft card with Approve and Reject buttons.

### Step 5 - Approve a draft

```
/approve 1
```

**Expected:** Draft status updates to Published inline. Card does not disappear - it updates in place.

---

## Test Flow 6 - Infra Monitoring

**Channels:** `#nexus-devops` then `#nexus-support`

### Step 1 - Register a service

Type `/service` - modal opens. Fill in:
- **Name**: google
- **URL**: https://google.com

### Step 2 - Ping a service

```
/ping https://google.com
```

**Expected:** Live HTTP response - status code and latency in milliseconds.

### Step 3 - Trigger Chain 4 (Service Down)

To test the automatic monitoring chain, register a service with a URL that returns errors or is unreachable. Wait for two consecutive background health check cycles.

**Expected - watch two channels:**
- `#nexus-devops`: InfraAgent posts a service-down alert
- `#nexus-support`: SupportAgent auto-files a P0 bug (InfraAgent fires SERVICE_DOWN via Switch)

This is Chain 4 - SERVICE_DOWN over Switch `send_targeted_message`. SupportAgent has `addressing_mode: owner_and_owner_agents` - only InfraAgent can file this P0, not a user.

---

## Verifying Switch Coordination

The five cross-agent chains only work because of Switch. Here is how to verify the transport is active and signals are flowing.

### Check all agents are online

```
/nexus status
```

This calls `list_agents()` live and shows online/offline status for all 7 agents. If any agent shows offline, the signal chains involving it will silently drop.

### Watch a signal fire in real time

1. Open `#nexus-sales` and `#nexus-finance` side by side
2. Run `/won Test Customer` in `#nexus-sales`
3. Watch `#nexus-finance` - FinanceAgent should respond within 2–3 seconds

The latency between the win confirmation in Sales and the invoice creation in Finance is the Switch round-trip time. No Slack automation, no Zapier, no cron job - it is a direct agent-to-agent signal.

### Verify addressing mode enforcement

Try this from a regular user account (not an agent):
1. Directly call CSAgent's Switch room as a user
2. Attempt to send a message formatted as `P1_BREACH`

**Expected:** Message rejected at the Switch protocol level. CSAgent has `addressing_mode: owner_and_owner_agents` - only registered agents can send it signals.

---

## Cross-Agent Chains - Full Reference

| Trigger | Channel | What you do | Fires | Watch in |
|---------|---------|-------------|-------|----------|
| Chain 1 | `#nexus-sales` | `/won Name` | DEAL_WON → FinanceAgent + CSAgent | `#nexus-finance` + `#nexus-cs` |
| Chain 2 | `#nexus-support` | `/bug` with P0 or P1 | P1_BREACH → CSAgent | `#nexus-cs` |
| Chain 3 | `#nexus-growth` | `/geo Keyword` (score < 7) | CONTENT_BRIEF → BlogAgent | `#nexus-content` |
| Chain 4 | `#nexus-devops` | 2 health check failures (automatic) | SERVICE_DOWN → SupportAgent | `#nexus-support` |
| Chain 5 | `#nexus-finance` | Invoice 30+ days overdue (nightly) | INVOICE_OVERDUE → SalesAgent | `#nexus-sales` |

All chains use `send_targeted_message()` with targets discovered at runtime via `list_agents()`.

---

## Troubleshooting

**Slash commands return "dispatch_failed"**
- Confirm Switch Console is running and bridged to the workspace
- Run `/nexus status` - if any agent shows offline, restart it: `docker compose up <agent_name> -d`

**Agent responds but cross-agent chain does not fire**
- Run `/nexus status` - confirm the target agent is online
- Check agent logs for the signal: `docker compose logs sales_agent -f | grep DEAL_WON`
- Verify `SWITCH_AGENT_ID_*` vars are set for the target agent

**Modal does not open**
- Confirm Interactivity is enabled: api.slack.com/apps → your app → **Interactivity & Shortcuts** → toggle ON

**LLM responses are slow or missing**
- Check `LLM_MOCK_MODE` in `.env` - set to `true` to use canned responses
- If using Ollama: `curl http://localhost:11434/api/tags` - confirm `llama3.2:latest` is listed
- Pull if missing: `ollama pull llama3.2`

**Database errors**
```bash
python database/migrate_fresh.py
```

**"LLM daily limit reached"**
```bash
docker compose exec postgres psql -U nexus -c \
  "UPDATE tenants SET llm_calls_today=0 WHERE tenant_id='default';"
```
