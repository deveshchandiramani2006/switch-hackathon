# NEXUS Setup Guide

Follow every step in order. At the end, run `bash run.sh` and the script handles the rest.

> **Slack or Switch?**
> Agents support both. Set `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` + channel IDs → runs in Slack.
> Set Switch vars → runs in Switch. If both are set, Slack takes priority.

---

## Step 1 — Create a Slack workspace (skip if you already have one)

1. Go to **https://slack.com/get-started**
2. Click **Create a new workspace**
3. Enter your email address → click **Continue**
4. Enter the confirmation code sent to your email
5. Enter your company/team name (e.g. `NEXUS Demo`) → click **Next**
6. Skip adding teammates for now → click **Skip this step**
7. Your workspace is ready — you'll land in Slack

---

## Step 2 — Create a Slack app

1. Go to **https://api.slack.com/apps**
2. Click the **Create New App** button (top right)
3. Choose **From scratch**
4. In the popup:
   - **App Name**: `NEXUS`
   - **Pick a workspace**: select the workspace you just created
   - Click **Create App**

---

## Step 3 — Enable Socket Mode and get App Token

Socket Mode lets the bot receive events without exposing a public URL.

1. In the left sidebar, click **Socket Mode**
2. Toggle **Enable Socket Mode** to ON
3. A popup appears asking you to create an App-Level Token:
   - **Token Name**: `nexus-socket`
   - Click **Add Scope** → select `connections:write`
   - Click **Generate**
4. Copy the token shown — it starts with `xapp-1-...`
5. Save it as **`SLACK_APP_TOKEN`** (you'll paste this into `.env` later)
6. Click **Done**

---

## Step 4 — Add bot scopes

1. In the left sidebar, click **OAuth & Permissions**
2. Scroll down to the **Scopes** section
3. Under **Bot Token Scopes**, click **Add an OAuth Scope**
4. Add each of these scopes one by one:

| Scope | Why it's needed |
|-------|----------------|
| `app_mentions:read` | Detect when someone @mentions the bot |
| `channels:history` | Read messages in public channels |
| `channels:read` | List channels |
| `chat:write` | Post messages |
| `users:read` | Get user display names |
| `groups:history` | Read messages in private channels |

---

## Step 5 — Subscribe to events

1. In the left sidebar, click **Event Subscriptions**
2. Toggle **Enable Events** to ON
3. Scroll down to **Subscribe to bot events**
4. Click **Add Bot User Event** and add:
   - `app_mention` — fires when someone types `@NEXUS`
   - `message.channels` — fires for every message in channels the bot is in
5. Click **Save Changes** (bottom right)

---

## Step 6 — Install the app to your workspace

1. In the left sidebar, click **OAuth & Permissions**
2. Scroll to the top — click **Install to Workspace**
3. Click **Allow** on the permissions screen
4. You'll be redirected back — copy the **Bot User OAuth Token**
   - It starts with `xoxb-...`
5. Save it as **`SLACK_BOT_TOKEN`**

---

## Step 7 — Create 7 Slack channels

1. In Slack (left sidebar), click the **+** button next to **Channels**
2. Click **Create a channel**
3. Create these 7 channels one by one (set them to **Public**):

| Channel name | Agent that uses it |
|-------------|-------------------|
| `nexus-sales` | SalesAgent |
| `nexus-support` | SupportAgent |
| `nexus-cs` | CSAgent (Customer Success) |
| `nexus-finance` | FinanceAgent |
| `nexus-growth` | GeoSEOAgent |
| `nexus-content` | BlogAgent |
| `nexus-devops` | InfraAgent |

---

## Step 8 — Invite the bot to every channel

For **each** of the 7 channels:
1. Click the channel name in the sidebar to open it
2. Type `/invite @NEXUS` in the message box
3. Press **Enter**
4. You should see `NEXUS was added to #nexus-sales` (or whichever channel)

Repeat for all 7 channels.

---

## Step 9 — Copy the Channel ID for each channel

Slack uses IDs (not names) to route messages. You need the ID for each channel.

For **each** of the 7 channels:
1. Right-click the channel name in the sidebar
2. Click **View channel details**
3. Scroll to the very bottom of the popup
4. You'll see **Channel ID** — it looks like `C06ABC1234`
5. Copy it

Save all 7 IDs — you'll paste them into `.env` in the next step.

---

## Step 10 — Get an Anthropic API key

1. Go to **https://console.anthropic.com**
2. Click **Sign Up** (or log in if you have an account)
3. Verify your email if prompted
4. In the left sidebar, click **API Keys**
5. Click **Create Key**
6. Give it a name (e.g. `nexus-hackathon`)
7. Click **Create Key**
8. Copy the key — it looks like `sk-ant-api03-...`
9. Save it — **you cannot view it again** after closing this popup

---

## Step 11 — Fill in `.env`

1. In your terminal, go to the nexus folder:
   ```bash
   cd nexus/
   ```
2. Copy the example file:
   ```bash
   cp .env.example .env
   ```
3. Open `.env` in any text editor and fill in these values:

```env
# ── Slack ──────────────────────────────────────────────
SLACK_BOT_TOKEN=xoxb-...        ← from Step 6
SLACK_APP_TOKEN=xapp-...        ← from Step 3

SLACK_CHANNEL_ID_SALES=         ← Channel ID for nexus-sales    (from Step 9)
SLACK_CHANNEL_ID_SUPPORT=       ← Channel ID for nexus-support
SLACK_CHANNEL_ID_CS=            ← Channel ID for nexus-cs
SLACK_CHANNEL_ID_FINANCE=       ← Channel ID for nexus-finance
SLACK_CHANNEL_ID_GROWTH=        ← Channel ID for nexus-growth
SLACK_CHANNEL_ID_CONTENT=       ← Channel ID for nexus-content
SLACK_CHANNEL_ID_DEVOPS=        ← Channel ID for nexus-devops

# ── Anthropic ──────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...    ← from Step 10
```

Leave everything else as-is. Save the file.

---

## Step 12 — Run the setup script

```bash
bash run.sh
```

The script will:
- Install Python dependencies
- Start PostgreSQL
- Run database migrations
- Ensure tenant config exists
- Ask if you want demo data seeded (say `y`)
- Build and start all 7 agent containers

**All 7 agents will now connect to your Slack workspace via Socket Mode.**

Test it — go to `#nexus-sales` in Slack and type:
```
@NEXUS pipeline
```
You should get a response from SalesAgent within a few seconds.

---
---

## Optional A — SerpAPI (live SEO keyword rankings)

Without this, GeoSEO agent uses mock data. Fine for demo.

1. Go to **https://serpapi.com**
2. Click **Register** (top right)
3. Fill in your name, email, and password → click **Register**
4. Verify your email
5. After logging in, you're on the **Dashboard** — your **API Key** is shown at the top
6. Copy it
7. Open `.env` and set:
   ```env
   SERPAPI_KEY=your-key-here
   GEO_SEO_MOCK_MODE=false
   ```
8. Save `.env` and restart: `docker compose up -d`

> Free plan: 100 searches/month.

---

## Optional B — Mailtrap (email notifications — free)

Mailtrap catches all emails in a test inbox so nothing goes to real users. Free forever, no card required.

1. Go to **https://mailtrap.io/register/signup**
2. Sign up with your email (or Google/GitHub)
3. Verify your email address
4. After logging in, you land on the **Email Testing** dashboard
5. Click **My Inbox** under Email Testing → Inboxes
6. Click the inbox named **My First Project** (or create a new one)
7. On the inbox page, click the **SMTP/POP3** tab
8. Under **Integrations**, select **Nodemailer** from the dropdown — this shows the raw SMTP credentials
9. You'll see:
   - **Host**: `sandbox.smtp.mailtrap.io`
   - **Port**: `2525`
   - **Username**: a random string
   - **Password**: a random string
10. Open `.env` and set:
    ```env
    SMTP_HOST=sandbox.smtp.mailtrap.io
    SMTP_PORT=2525
    SMTP_USER=your-mailtrap-username
    SMTP_PASSWORD=your-mailtrap-password
    EMAIL_FROM=nexus@demo.com
    ```
11. Save `.env`

> All emails sent by NEXUS will now appear in your Mailtrap inbox at **https://mailtrap.io** — no real emails are sent.

---


## Troubleshooting

**Bot doesn't respond in Slack**
- Check `message.channels` and `app_mention` events are enabled → **https://api.slack.com/apps** → your app → **Event Subscriptions**
- Check Socket Mode is ON → **Socket Mode** in sidebar
- Make sure bot was invited to the channel: type `/invite @NEXUS` in the channel
- Check agent logs: `docker compose logs sales_agent -f`

**Agent container exits immediately**
```bash
docker compose logs <agent_name>
```
Common causes:
- `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` / `SLACK_CHANNEL_ID_*` missing → check `.env`
- Postgres not healthy → `docker compose ps`

**"LLM daily limit reached"**
```bash
docker compose exec postgres psql -U nexus -c \
  "UPDATE tenants SET llm_calls_today=0 WHERE tenant_id='default';"
```

**Anthropic key rejected**
```bash
curl https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY"
# should return 400 (bad request), not 401 (unauthorized)
```

**"approve #N — insufficient role"**
```bash
curl -X PATCH \
  -H "Authorization: Bearer $NEXUS_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"role":"manager"}' \
  http://localhost:5000/api/v1/tenants/default/users/<your_slack_username>/role
```

**Port conflict on 5000 or 5001**
```env
MANAGEMENT_API_PORT=5002
VOICE_SERVER_PORT=5003
```
