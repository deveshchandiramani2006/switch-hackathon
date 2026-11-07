"""
FeatureGateService - subscription tier enforcement and LLM usage tracking.

Tiers:
  free       - 3 agents max, 100 LLM calls/day
  pro        - all agents, 1 000 LLM calls/day
  enterprise - all agents, unlimited LLM calls, custom escalation
"""
import logging
from datetime import date
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

TIER_LIMITS = {
    "free":       {"agents": 3,  "llm_per_day": 100},
    "starter":    {"agents": 5,  "llm_per_day": 300},
    "pro":        {"agents": 7,  "llm_per_day": 1000},
    "enterprise": {"agents": -1, "llm_per_day": -1},   # -1 = unlimited
}

UPGRADE_URL = "https://nexus.ai/upgrade"


class FeatureGateService:

    @classmethod
    def can_use_llm(cls, tenant_id: str) -> bool:
        """Check whether the tenant can make another LLM call. Resets daily."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT plan, llm_calls_today, llm_calls_reset_at FROM tenants WHERE tenant_id=%s",
                    (tenant_id,)
                )
                row = cur.fetchone()
            if not row:
                return True

            plan  = row["plan"] or "free"
            limit = TIER_LIMITS.get(plan, TIER_LIMITS["free"])["llm_per_day"]
            if limit == -1:
                return True

            # Reset counter if it's a new day
            if row["llm_calls_reset_at"] and row["llm_calls_reset_at"] < date.today():
                with db_cursor() as cur:
                    cur.execute(
                        "UPDATE tenants SET llm_calls_today=0, llm_calls_reset_at=%s WHERE tenant_id=%s",
                        (date.today(), tenant_id)
                    )
                return True

            return (row["llm_calls_today"] or 0) < limit
        except Exception as e:
            logger.warning(f"FeatureGateService.can_use_llm failed: {e}")
            return True  # Fail open - don't break on DB issues

    @classmethod
    def track_llm_call(cls, tenant_id: str) -> None:
        """Increment the daily LLM call counter."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "UPDATE tenants SET llm_calls_today = COALESCE(llm_calls_today, 0) + 1 WHERE tenant_id=%s",
                    (tenant_id,)
                )
        except Exception as e:
            logger.warning(f"FeatureGateService.track_llm_call failed: {e}")

    @classmethod
    def gate_llm(cls, tenant_id: str, client) -> bool:
        """
        Combined check + track. Post upgrade message if limit hit.
        Returns True if allowed (caller should proceed), False if blocked.
        """
        if not cls.can_use_llm(tenant_id):
            plan  = cls._get_plan(tenant_id)
            limit = TIER_LIMITS.get(plan, TIER_LIMITS["free"])["llm_per_day"]
            client.post_message(
                f"⚠️ You've used all {limit} AI calls for today (plan: *{plan}*).\n"
                f"Upgrade at {UPGRADE_URL} for more capacity."
            )
            return False
        cls.track_llm_call(tenant_id)
        return True

    @classmethod
    def _get_plan(cls, tenant_id: str) -> str:
        try:
            with db_cursor() as cur:
                cur.execute("SELECT plan FROM tenants WHERE tenant_id=%s", (tenant_id,))
                row = cur.fetchone()
            return (row["plan"] or "free") if row else "free"
        except Exception:
            return "free"
