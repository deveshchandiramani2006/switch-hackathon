import logging
from .analysis import run_analysis_cycle
from shared.db import db_cursor

logger = logging.getLogger(__name__)


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)

    if not text or sender in ("GeoSEOAgent", "NEXUS"):
        return

    # Cross-agent signal from BlogAgent
    if text.startswith("POST_PUBLISHED:"):
        handle_post_published(client, text)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if ">" in text else text
    for p in ["@GeoSEOAgent ", "@geoseoagent "]:
        if clean.lower().startswith(p):
            clean = clean[len(p):]
            break

    t = clean.lower().strip()
    if "run now" in t:
        client.post_message("Running analysis cycle now...")
        run_analysis_cycle(client)
    elif t.startswith("trending"):
        show_trending(client)
    elif t.startswith("report"):
        show_report(client)
    elif t.startswith("queue"):
        show_queue(client)
    elif t.startswith("track:"):
        track_keyword(client, clean.split(":", 1)[1].strip())
    else:
        client.post_message(
            "Commands:\n"
            "- `@GeoSEOAgent run now`\n"
            "- `@GeoSEOAgent trending`\n"
            "- `@GeoSEOAgent report`\n"
            "- `@GeoSEOAgent queue`\n"
            "- `@GeoSEOAgent track: keyword`"
        )


def handle_post_published(client, text: str):
    # Format: "POST_PUBLISHED: keyword=X url=Y"
    parts = {}
    for p in text.replace("POST_PUBLISHED:", "").strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v
    keyword = parts.get("keyword", "").replace("_", " ")
    url     = parts.get("url", "")
    if keyword and url:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE keyword_tracking SET published_url=%s WHERE LOWER(keyword)=LOWER(%s)",
                (url, keyword)
            )
        client.post_message(f"Now tracking rankings for: *{keyword}*\nPublished URL: {url}")


def show_trending(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT keyword, volume, current_rank FROM keyword_tracking ORDER BY volume DESC LIMIT 10"
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message("No keywords tracked yet. Run `@GeoSEOAgent run now`")
        return
    lines = ["*Tracked keywords:*\n"]
    for r in rows:
        rank_str = f"rank #{r['current_rank']}" if r["current_rank"] else "not ranked"
        lines.append(f"- *{r['keyword']}* -- {r['volume'] or '?'}/mo -- {rank_str}")
    client.post_message("\n".join(lines))


def show_report(client):
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as total FROM keyword_tracking")
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT COUNT(*) as briefs FROM content_queue WHERE status NOT IN ('published','rejected')"
        )
        briefs = cur.fetchone()["briefs"]
    client.post_message(
        f"*SEO Report*\nTracked keywords: {total}\nContent queue: {briefs} briefs pending"
    )


def show_queue(client):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, keyword, status, created_at FROM content_queue ORDER BY created_at DESC LIMIT 10"
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message("Content queue is empty.")
        return
    lines = ["*Content queue:*\n"]
    for r in rows:
        lines.append(f"- #{r['id']} | {r['keyword']} | {r['status']}")
    client.post_message("\n".join(lines))


def track_keyword(client, keyword: str):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO keyword_tracking (keyword) VALUES (%s) ON CONFLICT (keyword) DO NOTHING RETURNING id",
            (keyword,)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Now tracking: *{keyword}*")
    else:
        client.post_message(f"Already tracking: *{keyword}*")
