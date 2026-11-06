import logging
import requests as req
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)
    room_id    = payload.get("room_id", client.room_id)
    tenant_id  = client.tenant_id

    if sender in ("InfraAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return
    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if text.startswith("<@") else text
    for p in ["@InfraAgent ", "@infraagent "]:
        if clean.lower().startswith(p):
            clean = clean[len(p):]
            break

    from app.Services import ConversationService
    if ConversationService.resume(tenant_id, room_id, sender, "InfraAgent", clean, client):
        return

    route_command(client, clean, sender, tenant_id, room_id)


def route_command(client, text: str, sender: str, tenant_id: str, room_id: str):
    t = text.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "InfraAgent", _cmd_key, sender)
    if t.startswith("status"):
        show_status(client, tenant_id)
    elif t.startswith("ping:"):
        ping_service(client, text.split(":", 1)[1].strip())
    elif t.startswith("check:"):
        check_service_by_name(client, text.split(":", 1)[1].strip(), tenant_id)
    elif t == "add":
        # Bare "add" with no args → start wizard
        from app.Services import ConversationService
        ConversationService.start(tenant_id, room_id, sender, "InfraAgent", "add_service", client)
    elif t.startswith("add:"):
        add_service(client, text.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("jobs"):
        client.post_message(
            "Job monitoring: health checks run every 5 min.\n"
            "Use `@InfraAgent status` to see current state."
        )
    else:
        from app.Services.BlockBuilder import _section
        client.post_blocks([
            _section("*InfraAgent: Service Monitoring*\n"
                     "1. `status`\n"
                     "2. `ping: https://url`\n"
                     "3. `add: name -> https://url`\n"
                     "4. `add` (guided form)\n"
                     "5. `jobs`")
        ], fallback_text="InfraAgent commands")


def show_status(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT name, url, status, last_status_code, last_checked_at, consecutive_failures "
            "FROM monitored_services WHERE tenant_id=%s ORDER BY name",
            (tenant_id,)
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message(
            "No services monitored. Add one: `@InfraAgent add: service-name -> https://url`"
        )
        return
    from app.Services.BlockBuilder import _header, _section, _actions, _btn, _divider
    blocks = [_header(f"📡 Service Monitoring ({len(rows)} service{'s' if len(rows) != 1 else ''})")]
    blocks.append(_divider())
    for r in rows:
        status = r["status"] or "unknown"
        up = status in ("up", "healthy")
        emoji = "🟢" if up else "🔴"
        fail_str = f" · {r['consecutive_failures']} failures" if r.get("consecutive_failures") else ""
        safe_name = r["name"][:12].replace(" ", "_").replace("-", "_")
        blocks.append(_section(f"{emoji} *{r['name']}*  `{r['url']}`  _{status}{fail_str}_"))
        blocks.append(_actions(_btn("🔁 Ping", f"ping: {r['url']}", f"nexus_ping_{safe_name}")))
    client.post_blocks(blocks, fallback_text="Services")


def ping_service(client, url: str):
    try:
        resp = req.get(url, timeout=10)
        from app.Services.BlockBuilder import ping_result
        client.post_blocks(
            ping_result(url, resp.status_code, resp.elapsed.total_seconds() * 1000),
            fallback_text=f"HTTP {resp.status_code}"
        )
    except Exception as e:
        from app.Services.BlockBuilder import _header, _section
        client.post_blocks([_header("🔴 Unreachable"), _section(f"`{url}`\n_{e}_")], fallback_text=f"{url} unreachable")


def check_service_by_name(client, name: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT name, url FROM monitored_services WHERE tenant_id=%s AND LOWER(name)=LOWER(%s)",
            (tenant_id, name.strip())
        )
        row = cur.fetchone()
    if not row:
        client.post_message(f"Service '{name}' not found.")
        return
    ping_service(client, row["url"])


def add_service(client, text: str, tenant_id: str):
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
            "INSERT INTO monitored_services (tenant_id, name, url) VALUES (%s, %s, %s) "
            "ON CONFLICT (tenant_id, name) DO NOTHING RETURNING id",
            (tenant_id, name, url)
        )
        row = cur.fetchone()
    from app.Services.BlockBuilder import _header, _fields
    if row:
        client.post_blocks([
            _header("📡 Service Added"),
            _fields(f"*Name*\n{name}", f"*URL*\n{url}"),
        ], fallback_text=f"Now monitoring {name}")
    else:
        client.post_blocks([
            _header("📡 Already Monitoring"),
            _fields(f"*Name*\n{name}", f"*URL*\n{url}"),
        ], fallback_text=f"Already monitoring {name}")


def cmd_add_service_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard completes."""
    from app.Services.ValidationService import validate_url
    url, err = validate_url(data["url"])
    if err:
        client.post_message(f"[X] {err}")
        return
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO monitored_services (tenant_id, name, url) VALUES (%s,%s,%s) "
            "ON CONFLICT (tenant_id, name) DO NOTHING RETURNING id",
            (tenant_id, data["name"], url)
        )
        row = cur.fetchone()
    from app.Services.BlockBuilder import _header, _fields
    if row:
        client.post_blocks([
            _header("📡 Service Added"),
            _fields(f"*Name*\n{data['name']}", f"*URL*\n{url}"),
        ], fallback_text=f"Now monitoring {data['name']}")
    else:
        client.post_blocks([
            _header("📡 Already Monitoring"),
            _fields(f"*Name*\n{data['name']}", f"*URL*\n{url}"),
        ], fallback_text=f"Already monitoring {data['name']}")
