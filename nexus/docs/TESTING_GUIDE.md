# NEXUS Testing Guide

## How to Talk to Agents

- Mention `@nexus` in the channel — the agent responds
- Type `@nexus help` in any channel to see all available commands for that agent
- **Buttons on responses** — click them instead of typing follow-up commands
- All commands are case-insensitive

---

## Test Flow 1 — Sales Pipeline (start here)

**Channel:** `#nexus-sales`

### Step 1 — Add a lead
```
@nexus new lead: Rahul Sharma, CTO, Mumbai, SaaS, Rs500000
```
**Expected:** Card with lead details + `📋 Pipeline` and `💬 Follow Up` buttons

### Step 2 — View pipeline
```
@nexus pipeline
```
**Expected:** Each lead shown with `💬 Follow Up`, `🏆 Won`, `❌ Lost` buttons

### Step 3 — Follow up on a lead
```
@nexus follow up: Rahul Sharma
```
**Expected:** LLM-generated follow-up suggestion based on lead context

### Step 4 — Try the guided wizard (no parameters needed)
```
@nexus new lead
```
**Expected:** Agent asks for name, then role, city, industry, deal value — one field at a time

### Step 5 — Mark as won (triggers cross-agent flow)
```
@nexus won: Rahul Sharma
```
**Expected:**
- SalesAgent confirms win in `#nexus-sales`
- FinanceAgent auto-logs revenue in `#nexus-finance`
- CSAgent auto-onboards customer in `#nexus-cs`

### Step 6 — Check stale leads
```
@nexus stale leads
```
**Expected:** Any leads untouched for 7+ days

### Other commands
```
@nexus lead: Rahul Sharma        → view full lead detail
@nexus lost: Rahul Sharma -- reason: budget constraints
@nexus set commitment            → guided form for sales commitment
@nexus patterns                  → patterns the agent has learned
@nexus memory                    → recent decisions and events
@nexus knowledge: pricing        → search agent knowledge base
```

---

## Test Flow 2 — Finance (best to test after a won deal)

**Channel:** `#nexus-finance`

### Step 1 — Log an invoice
```
@nexus invoice: AWS, Rs75000, due: 2026-11-30, category: infrastructure
```
**Expected:** Invoice card with `✅ Approve` and `❌ Reject` buttons — no typing needed

### Step 2 — Approve via button
Click `✅ Approve` on the invoice card.
**Expected:** Status updates to approved

### Step 3 — List all invoices
```
@nexus invoices
```
**Expected:** Each pending invoice shows `✅ Approve` and `❌ Reject` buttons

### Step 4 — Log an expense
```
@nexus expense: Priya Kapoor, Rs3200, travel, 2026-11-05
```
Or use the guided wizard:
```
@nexus expense
```

### Step 5 — Reports
```
@nexus overdue               → overdue invoices
@nexus expenses pending      → expenses waiting approval
@nexus weekly report         → revenue, expenses, cash flow
@nexus forecast              → LLM financial forecast
@nexus budget: infrastructure → budget usage for a category
```

### Other commands
```
@nexus approve: invoice-001
@nexus reject: invoice-001, reason: duplicate
```

---

## Test Flow 3 — Support Bugs

**Channel:** `#nexus-support`

### Step 1 — Log a bug
```
@nexus bug: Checkout page crashes on payment step, severity: P1
```
**Expected:** Bug card with `📋 All Bugs` and `✅ Close` buttons

### Step 2 — View all bugs
```
@nexus status
```
**Expected:** All open bugs listed by priority

### Step 3 — Filter bugs
```
@nexus bugs: open P0
@nexus bugs: open P1
```

### Step 4 — Close a bug
Click `✅ Close` on the bug card, or type:
```
@nexus close: #1
```

> Note: Logging a P0 or P1 bug auto-fires a signal to CSAgent to flag the affected customer.

### Other commands
```
@nexus patterns       → recurring bug patterns detected
@nexus memory         → recent triage decisions
@nexus knowledge: auth → search bug knowledge base
```

---

## Test Flow 4 — Customer Success

**Channel:** `#nexus-cs`

> CSAgent gets customers automatically when SalesAgent marks a deal won. You can also add manually.

### Step 1 — Add a customer manually
```
@nexus add customer: TechCorp, Rs800000, renewal: 2027-01-15
```

### Step 2 — Health check
```
@nexus health: TechCorp
```
**Expected:** LLM-generated health score + risk assessment

### Step 3 — At-risk customers
```
@nexus at-risk
```

### Step 4 — Log NPS
```
@nexus nps: TechCorp, score: 8, note: great onboarding experience
```
Or guided:
```
@nexus nps
```

### Step 5 — Renewals
```
@nexus renewals          → renewals in next 30 days
@nexus renewals: 60      → renewals in next 60 days
```

### Other commands
```
@nexus expansion: TechCorp    → expansion opportunity analysis
@nexus qbr: TechCorp          → QBR prep notes
@nexus weekly report          → CS team summary
```

---

## Test Flow 5 — Blog Content

**Channel:** `#nexus-content`

### Step 1 — Generate a draft
```
@nexus draft: 5 reasons startups need invoicing software
```
**Expected:** Draft card with `✅ Approve`, `👁 Preview`, `❌ Reject` buttons

### Step 2 — Preview before approving
Click `👁 Preview` on the draft card.
**Expected:** Full draft text posted

### Step 3 — Approve
Click `✅ Approve` on the draft card.
Or approve with edits:
```
approve #1 -- edit: change CTA to start free trial
```

### Step 4 — Reject
Click `❌ Reject`, or:
```
reject #1 -- reason: too promotional
```

### Step 5 — Queue view
```
@nexus queue
```
**Expected:** Each pending draft shows `✅ Approve`, `👁 Preview`, `❌ Reject` buttons

### Step 6 — Guided wizard
```
@nexus draft
```
**Expected:** Agent asks for topic, tone, keywords one by one

### Other commands
```
@nexus delegate to @username    → delegate a draft for review
@nexus patterns                 → content formats that perform well
@nexus memory                   → recent drafts and decisions
@nexus knowledge: SEO           → search content knowledge base
```

---

## Test Flow 6 — GEO & SEO

**Channel:** `#nexus-growth`

### Step 1 — Track a keyword
```
@nexus track: invoicing software india
```

### Step 2 — GEO score (Generative Engine Optimization)
```
@nexus geo check: invoicing software india
```
**Expected:** Score card (1–10) with `💡 Get Improvement Tips` button if score < 8

### Step 3 — Get improvement tips
Click `💡 Get Improvement Tips`, or:
```
@nexus geo tips: invoicing software india
```
**Expected:** LLM recommendations to get cited in ChatGPT, Perplexity, Google AI Overviews

### Step 4 — Run GEO cycle for all keywords
```
@nexus geo run
```

### Step 5 — GEO report
```
@nexus geo report
```
**Expected:** Citation rates per keyword

### Step 6 — Traditional SEO
```
@nexus run now         → check Google rankings for all tracked keywords
@nexus trending        → top keywords by volume
@nexus report          → SEO summary — total keywords, content queue size
@nexus queue           → content briefs queued for BlogAgent
```

---

## Test Flow 7 — Infra Monitoring

**Channel:** `#nexus-devops`

### Step 1 — Add a service to monitor
```
@nexus add: google -> https://google.com
```
Or guided:
```
@nexus add
```

### Step 2 — View service health
```
@nexus status
```
**Expected:** Each service shown with `🔁 Ping Now` button

### Step 3 — Ping a service
Click `🔁 Ping Now`, or:
```
@nexus ping: https://google.com
```

### Other commands
```
@nexus jobs    → scheduled monitoring jobs
```

---

## Cross-Agent Flows (automatic — no manual trigger)

These fire automatically. Test them by running the trigger command and watching the other channels.

| Trigger in | What you do | Auto fires in |
|-----------|------------|---------------|
| `#nexus-sales` | `@nexus won: Lead Name` | FinanceAgent logs revenue in `#nexus-finance` |
| `#nexus-sales` | `@nexus won: Lead Name` | CSAgent onboards customer in `#nexus-cs` |
| `#nexus-support` | Log a P0 or P1 bug | CSAgent gets a P1_BREACH alert in `#nexus-cs` |
| `#nexus-growth` | GeoSEO finds trending keyword | BlogAgent gets a content brief in `#nexus-content` |
| `#nexus-growth` | GEO score < 7 for a keyword | BlogAgent gets a GEO optimization brief in `#nexus-content` |
| `#nexus-content` | Blog post published | GeoSEOAgent starts tracking the post's keyword rankings in `#nexus-growth` |

---

## Troubleshooting

**Bot doesn't respond at all:**
1. Check it's in the channel: `/invite @nexus`
2. Check events are subscribed: api.slack.com/apps → Event Subscriptions → `app_mention` + `message.channels`
3. Check agent is running: `ps aux | grep agent`
4. Check logs: `tail -f /tmp/geo_agent.log`

**Buttons don't work:**
- Make sure `interactivity` is enabled in Slack app settings → Interactivity & Shortcuts → toggle ON

**LLM responses are slow:**
- Ollama must be running: `curl http://localhost:11434/api/tags`
- Model must exist: should show `llama3.2:latest`
- Pull if missing: `ollama pull llama3.2`

**Database errors:**
```bash
python3 database/migrations/migrate.py
```
