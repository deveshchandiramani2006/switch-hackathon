import logging
from shared.db import db_cursor
from shared.llm import LLMClient
from .publisher import publish_post

logger = logging.getLogger(__name__)
llm = LLMClient(agent="blog")

DRAFT_PROMPT = """Write a 600-word SEO-optimized blog post for the keyword: "{keyword}"
Geographic context: {geo}
Trend context: {reason}

Format:
Title: [compelling SEO title]
Meta: [155-character meta description]
---
[600-word body with H2 subheadings, natural keyword usage]

Write in a clear, helpful tone. No fluff."""


def handle_message(client, payload: dict):
    text       = payload.get("text", "").strip()
    sender     = payload.get("sender", "")
    is_mention = payload.get("is_mention", False)

    if not text or sender in ("BlogAgent", "NEXUS"):
        return

    # Cross-agent brief from GeoSEOAgent
    if text.startswith("BRIEF:"):
        handle_brief(client, text)
        return

    # Approve / reject without @mention
    if text.lower().strip() in ("approve", "yes"):
        approve_top_draft(client, sender)
        return
    if text.lower().strip() in ("reject", "no"):
        reject_top_draft(client, sender)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if ">" in text else text
    for p in ["@BlogAgent ", "@blogagent "]:
        if clean.lower().startswith(p):
            clean = clean[len(p):]
            break

    t = clean.lower().strip()
    if t.startswith("draft:"):
        manual_draft(client, clean.split(":", 1)[1].strip())
    elif t.startswith("queue"):
        show_queue(client)
    elif t.startswith("preview:"):
        preview_draft(client, clean.split(":", 1)[1].strip())
    else:
        client.post_message(
            "Commands:\n"
            "- `@BlogAgent draft: topic`\n"
            "- `@BlogAgent queue`\n"
            "- `@BlogAgent preview: #id`\n"
            "- Type `approve` or `reject` for top draft"
        )


def handle_brief(client, text: str):
    # Parse: "BRIEF: keyword=X volume=Y trend=Z queue_id=N reason=W"
    parts = {}
    for p in text.replace("BRIEF:", "").strip().split():
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k] = v
    keyword  = parts.get("keyword", "").replace("_", " ")
    volume   = parts.get("volume", "?")
    trend    = parts.get("trend", "0")
    queue_id = parts.get("queue_id")
    reason   = parts.get("reason", "content_opportunity").replace("_", " ")

    client.post_message(
        f"*Brief received:* {keyword}\n"
        f"Volume: {volume}/mo | Trend: +{trend}%\n"
        f"Generating draft..."
    )

    draft_text = llm.complete(
        DRAFT_PROMPT.format(keyword=keyword, geo="India", reason=reason)
    )

    # Parse title/meta from draft
    lines = draft_text.split("\n")
    title = next(
        (l.replace("Title:", "").strip() for l in lines if l.startswith("Title:")),
        keyword
    )
    meta = next(
        (l.replace("Meta:", "").strip() for l in lines if l.startswith("Meta:")),
        ""
    )
    sep  = draft_text.find("---")
    body = draft_text[sep + 3:].strip() if sep > -1 else draft_text

    with db_cursor() as cur:
        if queue_id:
            cur.execute(
                """
                UPDATE content_queue
                SET title=%s, meta_description=%s, draft_content=%s, status='draft_ready'
                WHERE id=%s RETURNING id
                """,
                (title, meta, body, queue_id)
            )
            row = cur.fetchone()
            q_id = row["id"] if row else queue_id
        else:
            cur.execute(
                """
                INSERT INTO content_queue (keyword, title, meta_description, draft_content, status, source)
                VALUES (%s, %s, %s, %s, 'draft_ready', 'manual') RETURNING id
                """,
                (keyword, title, meta, body)
            )
            q_id = cur.fetchone()["id"]

    preview = body[:300] + "..." if len(body) > 300 else body
    client.post_message(
        f"*Draft ready* (#{q_id})\n"
        f"*{title}*\n_{meta}_\n\n"
        f"{preview}\n\n"
        f"Reply `approve` to publish or `reject` to discard."
    )


def approve_top_draft(client, sender: str):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, keyword, title, draft_content, meta_description
            FROM content_queue WHERE status='draft_ready'
            ORDER BY created_at ASC LIMIT 1
            """
        )
        draft = cur.fetchone()
    if not draft:
        client.post_message("No drafts waiting for approval.")
        return

    # Mark as publishing to prevent double-approval
    with db_cursor() as cur:
        cur.execute(
            "UPDATE content_queue SET status='publishing' WHERE id=%s",
            (draft["id"],)
        )

    url = publish_post(draft)

    if url:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE content_queue SET status='published', published_url=%s, published_at=NOW() WHERE id=%s",
                (url, draft["id"])
            )
        client.post_message(f"Published -> {url}")
        signal = f"POST_PUBLISHED: keyword={draft['keyword'].replace(' ', '_')} url={url}"
        client.safe_signal("GeoSEOAgent", signal)
    else:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE content_queue SET status='draft_ready' WHERE id=%s",
                (draft["id"],)
            )
        client.post_message("Publish failed. Draft returned to queue. Check BLOG_API config.")


def reject_top_draft(client, sender: str):
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE content_queue SET status='rejected'
            WHERE id=(
                SELECT id FROM content_queue
                WHERE status='draft_ready'
                ORDER BY created_at ASC LIMIT 1
            )
            RETURNING id, keyword
            """
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Draft #{row['id']} ({row['keyword']}) rejected and removed from queue.")


def manual_draft(client, topic: str):
    handle_brief(
        client,
        f"BRIEF: keyword={topic.replace(' ', '_')} volume=0 trend=0 reason=manual_request"
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


def preview_draft(client, ref: str):
    q_id = ref.lstrip("#").strip()
    with db_cursor() as cur:
        cur.execute(
            "SELECT title, draft_content FROM content_queue WHERE id=%s",
            (q_id,)
        )
        row = cur.fetchone()
    if not row:
        client.post_message(f"Draft #{q_id} not found.")
        return
    preview = (row["draft_content"] or "")[:500] + "..."
    client.post_message(f"*{row['title']}*\n\n{preview}")
