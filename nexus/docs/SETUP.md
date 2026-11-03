# NEXUS Setup Guide

## Prerequisites

- Docker + Docker Compose v2
- Python 3.11+
- A Switch workspace (local Docker or hosted)
- Anthropic API key
- (Optional) SerpAPI key for live SEO data
- (Optional) Blog CMS with an API endpoint

---

## 1. Switch Console Setup

### Option A — Run Switch locally via Docker
```bash
docker run -d -p 8080:8080 switch/server:latest
```

### Option B — Use hosted Switch
Set `SWITCH_SERVER_URL` in .env to the hosted URL.

### Create rooms in Switch Console
Create 5 rooms and copy their IDs:
- Sales room → `SWITCH_ROOM_ID_SALES`
- Support room → `SWITCH_ROOM_ID_SUPPORT`
- Growth/SEO room → `SWITCH_ROOM_ID_GROWTH`
- Content room → `SWITCH_ROOM_ID_CONTENT`
- DevOps room → `SWITCH_ROOM_ID_DEVOPS`

---

## 2. Environment Configuration

```bash
cd nexus/
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Where to get it |
|----------|----------------|
| `SWITCH_REGISTRATION_KEY` | Switch Console → Settings → Registration Key |
| `SWITCH_ROOM_ID_*` | Switch Console → Rooms |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `SERPAPI_KEY` | serpapi.com (optional — set `GEO_SEO_MOCK_MODE=true` to skip) |
| `BLOG_API_ENDPOINT` | Your CMS API endpoint (optional — set `BLOG_MOCK_MODE=true` to skip) |

---

## 3. Start PostgreSQL

```bash
docker compose up postgres -d
# Wait for healthy status
docker compose ps
```

---

## 4. Initialize Database + Register Agents

```bash
pip install -r requirements.txt
python db_init.py
python switch_setup.py
```

`switch_setup.py` will:
1. Register all 5 agents with Switch
2. Write their `SWITCH_AGENT_ID_*` and `SWITCH_API_KEY_*` values directly to your `.env`
3. Set addressing modes

After this, add your `SWITCH_ROOM_ID_*` values to `.env` (from Switch Console).

---

## 5. Launch All Agents

```bash
docker compose up -d
```

Or for demo mode (5-minute escalation checks, 1-hour SEO cycles):
```bash
make demo-mode
```

---

## 6. Seed Demo Data

```bash
python scripts/seed_demo_data.py
```

This seeds:
- 3 leads (Priya, Ankit, Meera)
- 1 overdue commitment from Ankit (3 days past deadline — triggers escalation immediately)
- 3 SEO keywords
- 3 monitored services

---

## 7. Health Check

```bash
python health_check.py
```

---

## 8. Verify It Works

**Sales room:**
```
just spoke to Priya, she'll get back by Friday
```
→ SalesAgent detects commitment and posts a tracking card

```
@SalesAgent pipeline
```
→ Shows all leads

**Growth room:**
```
@GeoSEOAgent run now
```
→ Runs SEO analysis, sends briefs to BlogAgent

**Content room:**
```
approve
```
→ BlogAgent publishes the top draft

**DevOps room:**
```
@InfraAgent status
```
→ Shows service health

---

## Troubleshooting

**Agent won't connect:**
- Check `SWITCH_AGENT_ID` and `SWITCH_API_KEY` are set correctly in `.env`
- Check Switch server is reachable: `curl http://localhost:8080/health`

**Commitment detection not working:**
- Check `ANTHROPIC_API_KEY` is valid
- Check logs: `docker compose logs sales_agent -f`

**GeoSEO returns mock data:**
- Either `GEO_SEO_MOCK_MODE=true` or `SERPAPI_KEY` is not set
- This is fine for demo — set mock mode explicitly: `GEO_SEO_MOCK_MODE=true`
