import json
import logging
from app.Services.DatabaseService import db_cursor
from app.Services.LlmService import LLMClient

logger = logging.getLogger(__name__)
llm = LLMClient(agent="sales")

PROMPT = '''You are analyzing a Slack message from a sales team channel.

Determine if this message contains a commitment -- a customer promising to do something, or a sales rep committing to follow up.

Message: "{message}"
Sent by: {user}

Reply with JSON only. No explanation, no markdown.

If NO commitment:
{{"commitment_found": false}}

If commitment found:
{{
  "commitment_found": true,
  "lead_name": "customer or lead name, or null",
  "party": "customer or rep",
  "commitment_text": "what they committed to in one sentence",
  "deadline_description": "when (e.g. 'by Friday', 'in 2 days')",
  "deadline_iso": "YYYY-MM-DD estimate or null"
}}

Examples that ARE commitments:
- "Priya said she'll revert by Friday" -> customer
- "just spoke to Ankit, he'll send approval by EOD" -> customer
- "I'll follow up with Ravi tomorrow" -> rep
- "client will share PO by Thursday" -> customer

NOT commitments:
- "how's the Priya deal going?" -> question
- "Priya sounds interested" -> observation
- "great call today" -> general comment
'''


def detect_commitment(client, message: str, user: str, tenant_id: str):
    if len(message.strip()) < 8:
        return

    # Load recent room context to help LLM understand the full thread
    context_lines = []
    try:
        recent = client.read_context(limit=5)
        context_lines = [f"[{m.get('sender','?')}]: {m.get('text','')}" for m in recent if m.get("text")]
    except Exception:
        pass
    context_block = "\nRecent conversation:\n" + "\n".join(context_lines) if context_lines else ""

    try:
        raw = llm.complete(PROMPT.format(message=message, user=user) + context_block, json_mode=True)
        data = json.loads(raw)
    except Exception as e:
        logger.debug(f"Commitment detection skipped: {e}")
        return

    if not data.get("commitment_found"):
        return

    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO commitments
              (tenant_id, lead_name, commitment_text, party, deadline, detected_by, source_message)
            VALUES (%s, %s, %s, %s, %s::date, 'passive', %s)
            RETURNING id
            """,
            (
                tenant_id,
                data.get("lead_name"),
                data["commitment_text"],
                data["party"],
                data.get("deadline_iso"),
                message
            )
        )
        cid = cur.fetchone()["id"]

    lead_line = f"Lead: {data['lead_name']}\n" if data.get("lead_name") else ""
    card = (
        f"Commitment tracked (#{cid})\n"
        f"{lead_line}"
        f"Party: {data['party'].title()} | "
        f"Deadline: {data.get('deadline_description', 'unspecified')}\n"
        f"_{data['commitment_text']}_\n"
        f"Rep: @{user} | Auto-escalates if no update by deadline"
    )
    client.post_message(card)
    logger.info(f"Commitment #{cid} tracked from passive detection")


RESOLVE_PROMPT = '''You are analyzing a Slack message in a sales channel.

Does this message indicate that a previously made commitment has been completed or fulfilled?

Message: "{message}"
Sent by: {user}

Look for completion signals like: "just sent", "done", "submitted", "shared the doc", "sent the PO", "approval sent", "completed", "done with that", "just did", "already sent".

Reply with JSON only:
{{"resolved": false}} if no clear completion signal.
{{"resolved": true, "completion_summary": "one line describing what was done"}} if completed.
'''


def detect_resolution(client, message: str, user: str, tenant_id: str):
    """Passively detect when a commitment is fulfilled and mark it resolved."""
    if len(message.strip()) < 8:
        return
    try:
        raw = llm.complete(RESOLVE_PROMPT.format(message=message, user=user), json_mode=True)
        data = json.loads(raw)
    except Exception as e:
        logger.debug(f"Resolution detection skipped: {e}")
        return

    if not data.get("resolved"):
        return

    # Find the most recent open commitment by this user for this tenant
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT id, commitment_text, lead_name
                FROM commitments
                WHERE tenant_id = %s
                  AND status = 'pending'
                  AND auto_resolved = FALSE
                  AND (detected_by = %s OR lead_name IS NOT NULL)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tenant_id, f"@{user}")
            )
            commitment = cur.fetchone()

        if not commitment:
            return

        summary = data.get("completion_summary", "marked complete")
        with db_cursor() as cur:
            cur.execute(
                """
                UPDATE commitments
                SET status = 'kept', auto_resolved = TRUE, resolved_text = %s
                WHERE id = %s
                """,
                (f"Auto-resolved: {summary} (by @{user})", commitment["id"])
            )

        client.post_message(
            f"Commitment #{commitment['id']} auto-resolved\n"
            f"_{commitment['commitment_text']}_\n"
            f"Resolved by @{user}: {summary}"
        )
        logger.info(f"Commitment #{commitment['id']} auto-resolved by @{user}")
    except Exception as e:
        logger.warning(f"Commitment resolution update failed: {e}")
