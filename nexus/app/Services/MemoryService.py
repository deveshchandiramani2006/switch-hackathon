"""
Agent Memory - event logging, pattern extraction, knowledge search.
All agents call AgentMemory(agent, tenant_id) to remember outcomes and extract patterns.
"""
import json
import logging
from collections import Counter
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)


class AgentMemory:
    def __init__(self, agent: str, tenant_id: str = "default"):
        self.agent = agent
        self.tenant_id = tenant_id

    def log_event(self, event_type: str, context: dict, outcome: str = None):
        """Record an event (command, escalation, etc.) for future pattern learning."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_memory (tenant_id, agent, event_type, context, outcome, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        self.tenant_id,
                        self.agent,
                        event_type,
                        json.dumps(context) if isinstance(context, dict) else str(context),
                        outcome,
                        json.dumps(context) if isinstance(context, dict) else "{}"
                    )
                )
        except Exception as e:
            logger.warning(f"AgentMemory.log_event failed: {e}")

    def get_patterns(self, min_occurrences: int = 3) -> list:
        """Return known patterns with enough occurrences to be significant."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    SELECT pattern_type, description, occurrences, confidence, last_seen
                    FROM agent_patterns
                    WHERE tenant_id = %s AND agent = %s AND occurrences >= %s
                    ORDER BY occurrences DESC, confidence DESC
                    LIMIT 10
                    """,
                    (self.tenant_id, self.agent, min_occurrences)
                )
                return cur.fetchall()
        except Exception as e:
            logger.warning(f"AgentMemory.get_patterns failed: {e}")
            return []

    def extract_patterns(self):
        """
        Group recent events by event_type and outcome, detect repetition.
        Called periodically by scheduler.
        """
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type, outcome, context
                    FROM agent_memory
                    WHERE tenant_id = %s AND agent = %s
                      AND created_at > NOW() - INTERVAL '30 days'
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (self.tenant_id, self.agent)
                )
                events = cur.fetchall()

            if not events:
                return

            pairs = Counter()
            for ev in events:
                key = (ev["event_type"], str(ev["outcome"] or ""))
                pairs[key] += 1

            with db_cursor() as cur:
                for (event_type, outcome), count in pairs.items():
                    if count < 2:
                        continue
                    description = f"{event_type}: {outcome[:100]}" if outcome else event_type
                    confidence = min(0.95, 0.5 + (count / 20))
                    cur.execute(
                        """
                        INSERT INTO agent_patterns
                            (tenant_id, agent, pattern_type, description, occurrences, confidence, last_seen)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING
                        """,
                        (self.tenant_id, self.agent, event_type, description, count, confidence)
                    )
                    cur.execute(
                        """
                        UPDATE agent_patterns
                        SET occurrences = %s, confidence = %s, last_seen = NOW()
                        WHERE tenant_id = %s AND agent = %s AND description = %s
                          AND occurrences < %s
                        """,
                        (count, confidence, self.tenant_id, self.agent, description, count)
                    )
        except Exception as e:
            logger.warning(f"AgentMemory.extract_patterns failed: {e}")

    def search_knowledge(self, query: str) -> list:
        """Simple keyword search in agent_memory context/outcome fields."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    """
                    SELECT event_type, context, outcome, created_at
                    FROM agent_memory
                    WHERE tenant_id = %s AND agent = %s
                      AND (context ILIKE %s OR outcome ILIKE %s OR event_type ILIKE %s)
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    (self.tenant_id, self.agent, f"%{query}%", f"%{query}%", f"%{query}%")
                )
                return cur.fetchall()
        except Exception as e:
            logger.warning(f"AgentMemory.search_knowledge failed: {e}")
            return []
