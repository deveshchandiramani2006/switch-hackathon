import logging
import requests as req
from shared.db import db_cursor

logger = logging.getLogger(__name__)


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)

    if not text or sender in ("InfraAgent", "NEXUS"):
        return
    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if ">" in text else text
    for p in ["@InfraAgent ", "@infraagent "]:
        if clean.lower().startswith(p):
            clean = clean[len(p):]
            break

    t = clean.lower().strip()
    if t.startswith("status"):
        show_status(client)
    elif t.startswith("ping:"):
        ping_service(client, clean.split(":", 1)[1].strip())
    elif t.startswith("add:"):
        add_service(client, clean.split(":", 1)[1].strip())
    elif t.startswith("jobs"):
        client.post_message(
            "Job monitoring: health checks run every 5 min.\n"
            "Use `@InfraAgent status` to see current state."
        )
    else:
        client.post_message(
            "Commands:\n"
            "- `@InfraAgent status`\n"
            "- `@InfraAgent ping: url`\n"
            "- `@InfraAgent add: name -> url`"
        )


def show_status(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT name, url, status, last_status_code, last_checked_at, consecutive_failures "
            "FROM monitored_services ORDER BY name"
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message(
            "No services monitored. Add one: `@InfraAgent add: service-name -> https://url`"
        )
        return
    lines = ["*Service Health*\n"]
    for r in rows:
        icon = "[UP]" if r["status"] == "healthy" else ("[WARN]" if r["status"] == "degraded" else "[DOWN]")
        checked = r["last_checked_at"].strftime("%H:%M") if r["last_checked_at"] else "never"
        lines.append(
            f"{icon} *{r['name']}* -- {r['status']} | "
            f"HTTP {r['last_status_code'] or '?'} | checked {checked}"
        )
    client.post_message("\n".join(lines))


def ping_service(client, url: str):
    try:
        resp = req.get(url, timeout=10)
        icon = "[OK]" if resp.status_code < 400 else "[FAIL]"
        client.post_message(
            f"{icon} {url} -- HTTP {resp.status_code} "
            f"({resp.elapsed.total_seconds()*1000:.0f}ms)"
        )
    except Exception as e:
        client.post_message(f"[DOWN] {url} -- unreachable: {e}")


def add_service(client, text: str):
    # Format: "service-name -> https://url"
    if "->" in text:
        parts = text.split("->", 1)
    elif ">" in text:
        parts = text.split(">", 1)
    else:
        client.post_message("Usage: `@InfraAgent add: service-name -> https://health-url`")
        return
    name = parts[0].strip()
    url  = parts[1].strip()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO monitored_services (name, url) VALUES (%s, %s) "
            "ON CONFLICT (name) DO NOTHING RETURNING id",
            (name, url)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Now monitoring *{name}*\n{url}")
    else:
        client.post_message(f"Already monitoring *{name}*")
