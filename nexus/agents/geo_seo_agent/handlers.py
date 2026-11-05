import logging
from .analysis import run_analysis_cycle
from .geo_analysis import run_geo_cycle, score_content_for_geo, generate_geo_recommendations
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)
    room_id    = payload.get("room_id", client.room_id)
    tenant_id  = client.tenant_id

    if sender in ("GeoSEOAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return

    # Cross-agent signal from BlogAgent
    if text.startswith("POST_PUBLISHED:"):
        handle_post_published(client, text, tenant_id)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if text.startswith("<@") else text
    for p in ["@GeoSEOAgent ", "@geoseoagent "]:
        if clean.lower().startswith(p):
            clean = clean[len(p):]
            break

    from app.Services import ConversationService
    if ConversationService.resume(tenant_id, room_id, sender, "GeoSEOAgent", clean, client):
        return

    t = clean.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "GeoSEOAgent", _cmd_key, sender)
    if "run now" in t:
        client.post_message("Running analysis cycle now...")
        run_analysis_cycle(client, tenant_id)
    elif "geo run" in t:
        client.post_message("Running GEO cycle now...")
        run_geo_cycle(client, tenant_id)
    elif t.startswith("geo report"):
        show_geo_report(client, tenant_id)
    elif t.startswith("geo check:"):
        kw = clean.split(":", 1)[1].strip()
        client.post_message(f"Checking GEO score for: *{kw}*...")
        geo_check_single(client, kw, tenant_id)
    elif t.startswith("geo tips:"):
        kw = clean.split(":", 1)[1].strip()
        client.post_message(f"Generating GEO tips for: *{kw}*...")
        geo_tips_single(client, kw, tenant_id)
    elif t.startswith("trending"):
        show_trending(client, tenant_id)
    elif t.startswith("report"):
        show_report(client, tenant_id)
    elif t.startswith("queue"):
        show_queue(client, tenant_id)
    elif t.startswith("track:"):
        track_keyword(client, clean.split(":", 1)[1].strip(), tenant_id)
    else:
        client.post_message(
            "*SEO Commands:*\n"
            "- `@GeoSEOAgent run now` — run keyword rank check\n"
            "- `@GeoSEOAgent trending` — top keywords by volume\n"
            "- `@GeoSEOAgent report` — SEO summary\n"
            "- `@GeoSEOAgent queue` — content queue\n"
            "- `@GeoSEOAgent track: keyword` — add keyword\n\n"
            "*GEO Commands (Generative Engine Optimization):*\n"
            "- `@GeoSEOAgent geo run` — check AI citability for all keywords\n"
            "- `@GeoSEOAgent geo report` — citation rates per keyword\n"
            "- `@GeoSEOAgent geo check: keyword` — score one keyword now\n"
            "- `@GeoSEOAgent geo tips: keyword` — get AI rewrite recommendations"
        )


def handle_post_published(client, text: str, tenant_id: str):
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
                "UPDATE keyword_tracking SET published_url=%s WHERE LOWER(keyword)=LOWER(%s) AND tenant_id=%s",
                (url, keyword, tenant_id)
            )
        client.post_message(f"Now tracking rankings for: *{keyword}*\nPublished URL: {url}")


def show_trending(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT keyword, volume, current_rank FROM keyword_tracking WHERE tenant_id=%s ORDER BY volume DESC LIMIT 10",
            (tenant_id,)
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


def show_report(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as total FROM keyword_tracking WHERE tenant_id=%s", (tenant_id,))
        total = cur.fetchone()["total"]
        cur.execute(
            "SELECT COUNT(*) as briefs FROM content_queue WHERE status NOT IN ('published','rejected') AND tenant_id=%s",
            (tenant_id,)
        )
        briefs = cur.fetchone()["briefs"]
    client.post_message(
        f"*SEO Report*\nTracked keywords: {total}\nContent queue: {briefs} briefs pending"
    )


def show_queue(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, keyword, status, created_at FROM content_queue WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10",
            (tenant_id,)
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message("Content queue is empty.")
        return
    lines = ["*Content queue:*\n"]
    for r in rows:
        lines.append(f"- #{r['id']} | {r['keyword']} | {r['status']}")
    client.post_message("\n".join(lines))


def track_keyword(client, keyword: str, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO keyword_tracking (tenant_id, keyword) VALUES (%s, %s) ON CONFLICT (tenant_id, keyword) DO NOTHING RETURNING id",
            (tenant_id, keyword)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Now tracking: *{keyword}*")
    else:
        client.post_message(f"Already tracking: *{keyword}*")


# ── GEO handlers ──────────────────────────────────────────────────────────────

def show_geo_report(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT keyword,
                   ROUND(AVG(ai_score), 1)                          AS avg_score,
                   COUNT(*)                                          AS checks,
                   SUM(CASE WHEN cited THEN 1 ELSE 0 END)           AS cited_count
            FROM geo_citations
            WHERE tenant_id=%s
            GROUP BY keyword
            ORDER BY avg_score DESC NULLS LAST
            LIMIT 10
            """,
            (tenant_id,)
        )
        rows = cur.fetchall()
    if not rows:
        client.post_message("No GEO data yet. Run `@GeoSEOAgent geo run` first.")
        return
    lines = ["*GEO Report — AI citability scores:*\n"]
    for r in rows:
        cited_str = f"{r['cited_count']}/{r['checks']} cited"
        lines.append(f"- *{r['keyword']}* — score {r['avg_score']}/10 — {cited_str}")
    client.post_message("\n".join(lines))


def geo_check_single(client, keyword: str, tenant_id: str):
    import os
    placeholder = (
        f"This page covers everything about {keyword}. "
        f"Published on {os.getenv('GEO_TARGET_DOMAIN', 'your domain')}."
    )
    result = score_content_for_geo(keyword, placeholder)
    score  = result.get("score", 0)
    reason = result.get("reason", "")
    gaps   = result.get("gaps", [])

    from app.Services.BlockBuilder import geo_score
    blocks = geo_score(keyword, score, reason)
    if gaps:
        from app.Services.BlockBuilder import _section
        blocks.append(_section("*Gaps:*\n" + "\n".join(f"• {g}" for g in gaps)))
    client.post_blocks(blocks, fallback_text=f"GEO score for '{keyword}': {score}/10")


def geo_tips_single(client, keyword: str, tenant_id: str):
    import os
    placeholder = (
        f"This page covers everything about {keyword}. "
        f"Published on {os.getenv('GEO_TARGET_DOMAIN', 'your domain')}."
    )
    score_result = score_content_for_geo(keyword, placeholder)
    recs = generate_geo_recommendations(keyword, score_result)
    client.post_message(
        f"*GEO tips for \"{keyword}\" (score {score_result.get('score', '?')}/10):*\n{recs}"
    )
