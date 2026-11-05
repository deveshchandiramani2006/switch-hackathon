import logging
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient
from app.Services.ApprovalsService import ApprovalRequest, check_approval_expirations
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
    room_id    = payload.get("room_id", client.room_id)
    tenant_id  = client.tenant_id

    if sender in ("BlogAgent", "NEXUS"):
        return
    if not text and not payload.get("is_mention"):
        return

    # Cross-agent brief from GeoSEOAgent
    if text.startswith("BRIEF:"):
        handle_brief(client, text, tenant_id=tenant_id)
        return

    # Scoped approval must include explicit draft ID: "approve #42" or "reject #42"
    if text.lower().startswith("approve #"):
        _handle_approve_cmd(client, text, sender, tenant_id)
        return
    if text.lower().startswith("reject #"):
        _handle_reject_cmd(client, text, sender, tenant_id)
        return

    if not is_mention:
        return

    clean = text.split(">", 1)[-1].strip() if text.startswith("<@") else text
    for p in ["@BlogAgent ", "@blogagent "]:
        if clean.lower().startswith(p):
            clean = clean[len(p):]
            break

    from app.Services import ConversationService
    if ConversationService.resume(tenant_id, room_id, sender, "BlogAgent", clean, client):
        return

    t = clean.lower().strip()
    from app.Services.UsageAnalyticsService import UsageAnalyticsService
    _cmd_key = t.split(":")[0].strip()[:50]
    UsageAnalyticsService.log(tenant_id, "BlogAgent", _cmd_key, sender)
    if t == "draft":
        # Bare "draft" with no topic → start wizard
        ConversationService.start(tenant_id, room_id, sender, "BlogAgent", "draft_post", client)
    elif t.startswith("draft:"):
        manual_draft(client, clean.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("queue"):
        show_queue(client, tenant_id)
    elif t.startswith("preview:"):
        preview_draft(client, clean.split(":", 1)[1].strip(), tenant_id)
    elif t.startswith("approve:"):
        # approve: change CTA to "Book a demo" — approve with edits (uses top draft for backwards compat)
        edit_instruction = clean.split(":", 1)[1].strip()
        approve_top_draft(client, sender, tenant_id, with_edits=edit_instruction)
    elif t.startswith("delegate to"):
        delegate_to = clean.replace("delegate to", "").strip().lstrip("@")
        client.post_message(f"Draft delegated to @{delegate_to} for review.")
    elif t.startswith("patterns"):
        _cmd_patterns(client, tenant_id)
    elif t.startswith("memory"):
        _cmd_memory(client, tenant_id)
    elif t.startswith("knowledge:"):
        _cmd_knowledge(client, clean.split(":", 1)[1].strip(), tenant_id)
    else:
        from app.Services.BlockBuilder import _section
        client.post_blocks([
            _section("*BlogAgent — Content Drafts*\n"
                     "• `draft: topic` or `draft` — guided form\n"
                     "• `queue`\n"
                     "• `preview: #42`\n"
                     "• `approve #42` or `approve #42 -- edit: change CTA`\n"
                     "• `reject #42 -- reason: too promotional`\n"
                     "• `delegate to @name`\n"
                     "• `patterns` / `memory` / `knowledge: topic`")
        ], fallback_text="BlogAgent commands")


# ---------------------------------------------------------------------------
# Scoped approval helpers
# ---------------------------------------------------------------------------

def _handle_approve_cmd(client, text: str, sender: str, tenant_id: str):
    """approve #42 or approve #42 -- edit: change CTA"""
    from app.Services.UserIdentityService import UserIdentityService
    if not UserIdentityService.has_role(tenant_id, sender, "manager"):
        UserIdentityService.deny(client, "approve invoices")
        return
    parts = text.strip().split("--", 1)
    id_part = parts[0].replace("approve", "").strip().lstrip("#")
    edit_instruction = None
    if len(parts) > 1:
        edit_part = parts[1].strip()
        if edit_part.lower().startswith("edit:"):
            edit_instruction = edit_part[5:].strip()
    try:
        draft_id = int(id_part)
    except ValueError:
        client.post_message("Usage: `approve #42` or `approve #42 -- edit: change CTA to X`")
        return
    approve_draft_by_id(client, draft_id, sender, tenant_id, with_edits=edit_instruction)


def _handle_reject_cmd(client, text: str, sender: str, tenant_id: str):
    """reject #42 or reject #42 -- reason: too long"""
    parts = text.strip().split("--", 1)
    id_part = parts[0].replace("reject", "").strip().lstrip("#")
    reason = "no reason given"
    if len(parts) > 1:
        reason_part = parts[1].strip()
        if reason_part.lower().startswith("reason:"):
            reason = reason_part[7:].strip()
        else:
            reason = reason_part
    try:
        draft_id = int(id_part)
    except ValueError:
        client.post_message("Usage: `reject #42` or `reject #42 -- reason: too promotional`")
        return
    reject_draft_by_id(client, draft_id, sender, tenant_id, reason=reason)


def approve_draft_by_id(client, draft_id: int, sender: str, tenant_id: str, with_edits=None):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, keyword, title, draft_content, meta_description FROM content_queue WHERE id=%s AND tenant_id=%s",
            (draft_id, tenant_id)
        )
        draft = cur.fetchone()
    if not draft:
        client.post_message(f"Draft #{draft_id} not found.")
        return

    # Mark as publishing to prevent double-approval
    with db_cursor() as cur:
        cur.execute(
            "UPDATE content_queue SET status='publishing' WHERE id=%s AND tenant_id=%s",
            (draft_id, tenant_id)
        )

    # Apply edits if requested
    if with_edits:
        client.post_message(f"Applying edit: _{with_edits}_...")
        from app.Services.FeatureGateService import FeatureGateService
        if not FeatureGateService.gate_llm(tenant_id, client):
            return
        new_body = llm.complete(
            f"Apply this edit to the blog post:\nEdit instruction: {with_edits}\n\nOriginal:\n{draft['draft_content']}\n\nReturn the full updated post body only."
        )
        with db_cursor() as cur:
            cur.execute(
                "UPDATE content_queue SET draft_content=%s WHERE id=%s",
                (new_body, draft_id)
            )
        # Reload
        with db_cursor() as cur:
            cur.execute(
                "SELECT id, keyword, title, draft_content, meta_description FROM content_queue WHERE id=%s",
                (draft_id,)
            )
            draft = cur.fetchone()

    # Publish
    url = publish_post(draft)
    if url:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE content_queue SET status='published', published_url=%s, published_at=NOW() WHERE id=%s",
                (url, draft_id)
            )
        client.post_message(f"✅ Published — {url}")
        client.safe_signal("GeoSEOAgent", f"POST_PUBLISHED: keyword={draft['keyword'].replace(' ', '_')} url={url}")
    else:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE content_queue SET status='draft_ready' WHERE id=%s",
                (draft_id,)
            )
        client.post_message("Publish failed. Draft returned to queue.")


def reject_draft_by_id(client, draft_id: int, sender: str, tenant_id: str, reason: str = ""):
    with db_cursor() as cur:
        cur.execute(
            "UPDATE content_queue SET status='rejected', brief_notes=%s WHERE id=%s AND tenant_id=%s RETURNING id, keyword",
            (f"Rejected by @{sender}: {reason}", draft_id, tenant_id)
        )
        row = cur.fetchone()
    if row:
        client.post_message(f"Draft #{row['id']} ({row['keyword']}) rejected. Reason: {reason}")
    else:
        client.post_message(f"Draft #{draft_id} not found.")


# ---------------------------------------------------------------------------
# Modal wizard data handler
# ---------------------------------------------------------------------------

def cmd_draft_post_data(client, data: dict, sender: str, tenant_id: str):
    """Called by ConversationService after wizard completes."""
    geo   = data.get("geo") or "India"
    tone  = data.get("tone") or "informative"
    topic = data["topic"]
    handle_brief(
        client,
        f"BRIEF: keyword={topic.replace(' ', '_')} volume=0 trend=0 reason={tone} geo={geo.replace(' ', '_')}",
        tenant_id=tenant_id
    )


# ---------------------------------------------------------------------------
# Core handlers
# ---------------------------------------------------------------------------

def handle_brief(client, text: str, tenant_id: str = "default"):
    # Parse: "BRIEF: keyword=X volume=Y trend=Z queue_id=N reason=W geo=G"
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
    geo      = parts.get("geo", "India").replace("_", " ")

    client.post_message(f"✍️ Drafting *{keyword}*...")

    from app.Services.FeatureGateService import FeatureGateService
    if not FeatureGateService.gate_llm(tenant_id, client):
        return
    draft_text = llm.complete(
        DRAFT_PROMPT.format(keyword=keyword, geo=geo, reason=reason)
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
                WHERE id=%s AND tenant_id=%s RETURNING id
                """,
                (title, meta, body, queue_id, tenant_id)
            )
            row = cur.fetchone()
            q_id = row["id"] if row else queue_id
        else:
            cur.execute(
                """
                INSERT INTO content_queue (tenant_id, keyword, title, meta_description, draft_content, status, source)
                VALUES (%s, %s, %s, %s, %s, 'draft_ready', 'manual') RETURNING id
                """,
                (tenant_id, keyword, title, meta, body)
            )
            q_id = cur.fetchone()["id"]

    preview = body[:200] + "…" if len(body) > 200 else body
    from app.Services.BlockBuilder import draft_created
    client.post_blocks(
        draft_created(q_id, title, preview),
        fallback_text=f"Draft ready #{q_id}: {title}"
    )


def approve_top_draft(client, sender: str, tenant_id: str, with_edits: str = None):
    """Backwards-compatible: approve the oldest draft_ready item for this tenant."""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, keyword, title, draft_content, meta_description
            FROM content_queue WHERE status='draft_ready' AND tenant_id=%s
            ORDER BY created_at ASC LIMIT 1
            """,
            (tenant_id,)
        )
        draft = cur.fetchone()
    if not draft:
        client.post_message("No drafts waiting for approval.")
        return
    approve_draft_by_id(client, draft["id"], sender, tenant_id, with_edits=with_edits)


def manual_draft(client, topic: str, tenant_id: str):
    handle_brief(
        client,
        f"BRIEF: keyword={topic.replace(' ', '_')} volume=0 trend=0 reason=manual_request",
        tenant_id=tenant_id
    )


def show_queue(client, tenant_id: str):
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, keyword, status, created_at FROM content_queue WHERE tenant_id=%s ORDER BY created_at DESC LIMIT 10",
            (tenant_id,)
        )
        rows = cur.fetchall()
    from app.Services.BlockBuilder import draft_queue
    client.post_blocks(
        draft_queue([dict(r) for r in rows]),
        fallback_text="Content queue"
    )


def preview_draft(client, ref: str, tenant_id: str):
    q_id = ref.lstrip("#").strip()
    with db_cursor() as cur:
        cur.execute(
            "SELECT title, draft_content FROM content_queue WHERE id=%s AND tenant_id=%s",
            (q_id, tenant_id)
        )
        row = cur.fetchone()
    if not row:
        client.post_message(f"Draft #{q_id} not found.")
        return
    preview = (row["draft_content"] or "")[:500] + "..."
    client.post_message(f"*{row['title']}*\n\n{preview}")


def _cmd_patterns(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("BlogAgent")
    patterns = mem.get_patterns(min_occurrences=2)
    if not patterns:
        client.post_message("No patterns detected yet.")
        return
    lines = ["*Patterns learned:*\n"]
    for p in patterns[:5]:
        lines.append(f"- {p['description']} (seen {p['occurrences']}x)")
    client.post_message("\n".join(lines))


def _cmd_memory(client, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("BlogAgent")
    events = mem.search_knowledge("")
    if not events:
        client.post_message("No memory events recorded yet.")
        return
    lines = ["*Recent memory:*\n"]
    for ev in events[:5]:
        lines.append(f"- [{ev['event_type']}] {str(ev['context'] or '')[:80]}")
    client.post_message("\n".join(lines))


def _cmd_knowledge(client, query: str, tenant_id: str):
    from app.Services.MemoryService import AgentMemory
    mem = AgentMemory("BlogAgent")
    results = mem.search_knowledge(query)
    if not results:
        client.post_message(f"No memory found for '{query}'.")
        return
    lines = [f"*Knowledge search: '{query}'*\n"]
    for r in results[:5]:
        lines.append(f"- [{r['event_type']}] {str(r['outcome'] or r['context'] or '')[:100]}")
    client.post_message("\n".join(lines))
