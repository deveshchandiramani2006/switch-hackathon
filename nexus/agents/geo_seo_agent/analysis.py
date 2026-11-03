import os
import logging
import requests
import yaml
from shared.db import db_cursor

logger = logging.getLogger(__name__)


def fetch_serpapi(keyword: str) -> dict:
    if os.getenv("GEO_SEO_MOCK_MODE", "false").lower() == "true":
        return _mock_data(keyword)
    key = os.getenv("SERPAPI_KEY", "")
    if not key:
        return _mock_data(keyword)
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": keyword,
                "api_key": key,
                "gl": os.getenv("SEO_COUNTRY", "IN").lower(),
                "hl": os.getenv("SEO_LANGUAGE", "en"),
                "num": 10
            },
            timeout=15
        )
        data = resp.json()
        rank = None
        site = ""
        endpoint = os.getenv("BLOG_API_ENDPOINT", "")
        if endpoint and "/" in endpoint:
            parts = endpoint.split("/")
            site = parts[2] if len(parts) > 2 else ""
        for i, r in enumerate(data.get("organic_results", []), 1):
            if site and site in r.get("link", ""):
                rank = i
                break
        return {
            "keyword": keyword,
            "rank": rank,
            "volume": data.get("search_information", {}).get("total_results", 0),
            "trend_pct": 0
        }
    except Exception as e:
        logger.error(f"SerpAPI error: {e}")
        return _mock_data(keyword)


def _mock_data(keyword: str) -> dict:
    import random
    return {
        "keyword": keyword,
        "rank": random.randint(5, 50),
        "volume": random.randint(1000, 20000),
        "trend_pct": random.randint(50, 400)
    }


def run_analysis_cycle(client):
    try:
        with open("company_config.yaml") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        cfg = {}

    geo_cfg = cfg.get("geo_seo", {})
    threshold_pct  = geo_cfg.get("analysis", {}).get("trend_threshold_pct", 200)
    max_briefs     = geo_cfg.get("content_queue", {}).get("max_briefs_per_run", 3)
    init_keywords  = geo_cfg.get("initial_keywords", [])

    with db_cursor() as cur:
        cur.execute("SELECT keyword FROM keyword_tracking")
        tracked = [r["keyword"] for r in cur.fetchall()]

    all_keywords = list(set(tracked + init_keywords))
    briefs_sent  = 0
    summaries    = []

    for kw in all_keywords:
        if briefs_sent >= max_briefs:
            break
        data = fetch_serpapi(kw)
        with db_cursor() as cur:
            cur.execute(
                """
                INSERT INTO keyword_tracking (keyword, volume, current_rank)
                VALUES (%s, %s, %s)
                ON CONFLICT (keyword) DO UPDATE
                  SET previous_rank    = keyword_tracking.current_rank,
                      current_rank     = EXCLUDED.current_rank,
                      volume           = EXCLUDED.volume,
                      last_checked_at  = NOW()
                """,
                (kw, data["volume"], data["rank"])
            )

        should_brief = False
        reason = ""
        if data.get("trend_pct", 0) >= threshold_pct:
            should_brief = True
            reason = f"trending +{data['trend_pct']}%"
        elif data["volume"] >= 1000 and not data["rank"]:
            should_brief = True
            reason = "content gap -- no ranking yet"

        if should_brief:
            with db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO content_queue (keyword, volume, trend_pct, brief_notes, source)
                    VALUES (%s, %s, %s, %s, 'geo_seo') RETURNING id
                    """,
                    (kw, data["volume"], data.get("trend_pct", 0), reason)
                )
                q_id = cur.fetchone()["id"]

            signal = (
                f"BRIEF: keyword={kw.replace(' ', '_')} "
                f"volume={data['volume']} trend={data.get('trend_pct', 0)} "
                f"queue_id={q_id} reason={reason.replace(' ', '_')}"
            )
            client.safe_signal("BlogAgent", signal)
            summaries.append(f"- *{kw}* -- {reason}")
            briefs_sent += 1

    if summaries:
        client.post_message(
            "*GeoSEO cycle complete*\nBriefs sent to BlogAgent:\n" + "\n".join(summaries)
        )
    else:
        client.post_message(
            f"GeoSEO cycle complete -- {len(all_keywords)} keywords checked, no new briefs needed."
        )
