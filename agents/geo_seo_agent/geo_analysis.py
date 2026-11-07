"""
GEO - Generative Engine Optimization engine.

Uses the OpenAI-compatible chat API to score content and generate
optimization recommendations. By default wired to local Ollama via
GEO_API_BASE / GEO_API_KEY env vars, but any OpenAI-compatible
endpoint (real OpenAI, Groq, Together, etc.) works as a drop-in.

Optional citation checks:
  - Brave Search API  (GEO_BRAVE_API_KEY)   - 2000 free queries/month
  - SerpAPI           (SERPAPI_KEY)          - checks Google AI Overview box
"""
import os
import json
import logging
import requests
from openai import OpenAI
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)


def _openai_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv("GEO_API_BASE", "http://localhost:11434/v1"),
        api_key=os.getenv("GEO_API_KEY", "ollama"),
    )


def _geo_model() -> str:
    return os.getenv("GEO_MODEL", "llama3.2:latest")


# ── Content scoring ────────────────────────────────────────────────────────────

def score_content_for_geo(keyword: str, content: str) -> dict:
    """
    Ask the LLM: would an AI engine cite this content when asked about keyword?
    Returns {"score": int, "reason": str, "gaps": [str]}.
    """
    client = _openai_client()
    prompt = f"""You are a Generative Engine Optimization (GEO) expert.
A user searches for: "{keyword}"

Here is a piece of content that might answer this query:
---
{content[:2000]}
---

Evaluate how likely an AI search engine (like ChatGPT, Perplexity, or Google AI Overviews) would cite this content in its answer.

Respond ONLY with valid JSON in this exact format:
{{
  "score": <integer 1-10>,
  "reason": "<one sentence why>",
  "gaps": ["<gap 1>", "<gap 2>", "<gap 3>"]
}}"""

    try:
        resp = client.chat.completions.create(
            model=_geo_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.lower().startswith("json"):
                raw = raw[4:]
        # Extract JSON object even if model adds surrounding text
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
        return json.loads(raw)
    except Exception as e:
        logger.error(f"GEO score error for '{keyword}': {e}")
        return {"score": 0, "reason": "Could not parse LLM response", "gaps": []}


def generate_geo_recommendations(keyword: str, score_result: dict) -> str:
    """Generate actionable rewrite recommendations to improve GEO citability."""
    client = _openai_client()
    gaps = "\n".join(f"- {g}" for g in score_result.get("gaps", []))
    prompt = f"""You are a GEO (Generative Engine Optimization) content strategist.

Keyword: "{keyword}"
Current AI-friendliness score: {score_result.get("score")}/10
Reason: {score_result.get("reason")}
Content gaps:
{gaps}

Give 3 specific, actionable recommendations to make this content more likely to be cited by AI search engines like ChatGPT, Perplexity, and Google AI Overviews.

Format as a numbered list. Be specific and practical. Max 2 sentences per recommendation."""

    try:
        resp = client.chat.completions.create(
            model=_geo_model(),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"GEO recommendations error: {e}")
        return f"Could not generate recommendations: {e}"


# ── Citation checks (optional, free tier APIs) ─────────────────────────────────

def check_brave_citation(keyword: str, target_domain: str) -> dict:
    """Check if target_domain appears in Brave Search AI summary citations."""
    api_key = os.getenv("GEO_BRAVE_API_KEY", "")
    if not api_key:
        return {"cited": False, "engine": "brave", "snippet": None, "skipped": True}
    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            params={"q": keyword, "summary": 1, "count": 5},
            timeout=10,
        )
        data = resp.json()
        summary = data.get("summarizer", {}) or {}
        snippet = summary.get("summary", [{}])[0].get("data", "") if summary.get("summary") else ""
        cited_urls = [e.get("url", "") for e in summary.get("results", [])]
        cited = any(target_domain in u for u in cited_urls)
        return {"cited": cited, "engine": "brave", "snippet": snippet[:500] if snippet else None}
    except Exception as e:
        logger.error(f"Brave citation check error: {e}")
        return {"cited": False, "engine": "brave", "snippet": None}


def check_google_ai_overview(keyword: str, target_domain: str) -> dict:
    """Check if target_domain appears in Google AI Overview via SerpAPI."""
    api_key = os.getenv("SERPAPI_KEY", "")
    if not api_key or os.getenv("GEO_SEO_MOCK_MODE", "false").lower() == "true":
        return {"cited": False, "engine": "google_sge", "snippet": None, "skipped": not api_key}
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={
                "q": keyword,
                "api_key": api_key,
                "gl": os.getenv("SEO_COUNTRY", "IN").lower(),
                "hl": os.getenv("SEO_LANGUAGE", "en"),
            },
            timeout=15,
        )
        data = resp.json()
        ai_overview = data.get("ai_overview", {}) or {}
        text = ai_overview.get("text", "") or ""
        sources = [s.get("link", "") for s in ai_overview.get("sources", [])]
        cited = any(target_domain in s for s in sources)
        return {"cited": cited, "engine": "google_sge", "snippet": text[:500] if text else None}
    except Exception as e:
        logger.error(f"Google SGE check error: {e}")
        return {"cited": False, "engine": "google_sge", "snippet": None}


# ── Main GEO cycle ─────────────────────────────────────────────────────────────

def run_geo_cycle(client, tenant_id: str = "default"):
    target_domain = os.getenv("GEO_TARGET_DOMAIN", "")
    if not target_domain:
        client.post_message(
            "GEO: `GEO_TARGET_DOMAIN` not set in .env - cannot check citations. "
            "Set it to your domain (e.g. `yourdomain.com`) and re-run."
        )
        return

    with db_cursor() as cur:
        cur.execute(
            "SELECT keyword FROM keyword_tracking WHERE tenant_id=%s LIMIT 10",
            (tenant_id,)
        )
        rows = cur.fetchall()

    if not rows:
        client.post_message("GEO: No keywords tracked yet. Add some with `@GeoSEOAgent track: keyword`")
        return

    summaries = []
    for row in rows:
        kw = row["keyword"]

        # Score content using local LLM (OpenAI-compatible call → Ollama)
        placeholder_content = (
            f"This page covers everything about {kw}. "
            f"It is published on {target_domain}."
        )
        score_result = score_content_for_geo(kw, placeholder_content)
        score = score_result.get("score", 0)

        # Optional citation checks
        brave  = check_brave_citation(kw, target_domain)
        google = check_google_ai_overview(kw, target_domain)

        with db_cursor() as cur:
            for check in [brave, google]:
                if check.get("skipped"):
                    continue
                cur.execute(
                    """
                    INSERT INTO geo_citations
                        (tenant_id, keyword, engine, cited, snippet, ai_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (tenant_id, kw, check["engine"], check["cited"],
                     check.get("snippet"), score)
                )

        # Generate recommendations if score is low
        if score < 7:
            recs = generate_geo_recommendations(kw, score_result)
            with db_cursor() as cur:
                cur.execute(
                    "INSERT INTO geo_recommendations (tenant_id, keyword, recommendation) VALUES (%s, %s, %s)",
                    (tenant_id, kw, recs)
                )
            client.safe_signal(
                "BlogAgent",
                f"GEO_OPTIMIZE: keyword={kw.replace(' ', '_')} score={score} domain={target_domain}"
            )

        cited_engines = [
            c["engine"] for c in [brave, google]
            if c.get("cited") and not c.get("skipped")
        ]
        cited_str = ", ".join(cited_engines) if cited_engines else "none"
        summaries.append(f"• *{kw}* · AI score {score}/10 · cited by: {cited_str}")

    client.post_message(
        "*GEO cycle complete*\n" + "\n".join(summaries)
    )
