import json
import logging
from shared.db import db_cursor
from shared.llm import LLMClient

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


def detect_commitment(client, message: str, user: str):
    if len(message.strip()) < 8:
        return
    try:
        raw = llm.complete(PROMPT.format(message=message, user=user), json_mode=True)
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
              (lead_name, commitment_text, party, deadline, detected_by, source_message)
            VALUES (%s, %s, %s, %s::date, 'passive', %s)
            RETURNING id
            """,
            (
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
