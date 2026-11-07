"""
OnboardingService - step-by-step setup wizard for new tenants.

Steps:
  0: Welcome + verify connection
  1: Set company name
  2: Configure first escalation contact
  3: Send a test command
  4: Health check pass
"""
import logging
import json
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

STEPS = [
    {
        "id": 0,
        "name": "welcome",
        "title": "Welcome to NEXUS",
        "message": (
            "*Welcome to NEXUS!* 👋\n\n"
            "I'm your AI operations hub. I'll guide you through a quick setup.\n\n"
            "*Step 1 of 4:* What is your company name?\n"
            "_(Reply with your company name to continue)_"
        ),
    },
    {
        "id": 1,
        "name": "company_name",
        "title": "Company Name",
        "message": (
            "*Step 2 of 4:* Set your escalation contact\n\n"
            "Who should receive escalation alerts? (e.g. @ceo or @founder)\n"
            "_(Reply with their @username)_"
        ),
    },
    {
        "id": 2,
        "name": "escalation_contact",
        "title": "Escalation Contact",
        "message": (
            "*Step 3 of 4:* Test a command\n\n"
            "Try your first command - type:\n"
            "`@SalesAgent pipeline`\n\n"
            "_(Once you send it, I'll confirm setup is working)_"
        ),
    },
    {
        "id": 3,
        "name": "first_command",
        "title": "First Command",
        "message": (
            "*Setup complete!* ✅\n\n"
            "NEXUS is ready. Here's a quick reference:\n"
            "- Sales: `@SalesAgent new lead`\n"
            "- Support: `@SupportAgent bug: description`\n"
            "- Finance: `@FinanceAgent invoice`\n"
            "- Content: `@BlogAgent draft`\n"
            "- DevOps: `@InfraAgent status`\n\n"
            "Type `help` in any room to see all commands."
        ),
    },
]


class OnboardingService:

    @classmethod
    def get_status(cls, tenant_id: str) -> dict:
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT current_step, steps_completed, completed_at FROM onboarding_sessions WHERE tenant_id=%s",
                    (tenant_id,)
                )
                row = cur.fetchone()
            if not row:
                return {"tenant_id": tenant_id, "current_step": 0, "steps_completed": [], "completed": False}
            return {
                "tenant_id":       tenant_id,
                "current_step":    row["current_step"],
                "steps_completed": row["steps_completed"] or [],
                "completed":       row["completed_at"] is not None,
            }
        except Exception as e:
            logger.error(f"OnboardingService.get_status failed: {e}")
            return {"tenant_id": tenant_id, "current_step": 0, "steps_completed": [], "completed": False}

    @classmethod
    def start_wizard(cls, client, tenant_id: str) -> None:
        """Post the first onboarding message and create a session."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "INSERT INTO onboarding_sessions (tenant_id, current_step, steps_completed) "
                    "VALUES (%s, 0, '[]') ON CONFLICT (tenant_id) DO NOTHING",
                    (tenant_id,)
                )
        except Exception as e:
            logger.error(f"OnboardingService.start_wizard failed: {e}")
            return
        client.post_message(STEPS[0]["message"])

    @classmethod
    def complete_step(cls, tenant_id: str, step_name: str) -> None:
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT current_step, steps_completed FROM onboarding_sessions WHERE tenant_id=%s",
                    (tenant_id,)
                )
                row = cur.fetchone()
            if not row:
                return
            completed = list(row["steps_completed"] or [])
            if step_name not in completed:
                completed.append(step_name)
            next_step = row["current_step"] + 1
            done = next_step >= len(STEPS)
            with db_cursor() as cur:
                cur.execute(
                    "UPDATE onboarding_sessions SET current_step=%s, steps_completed=%s"
                    + (", completed_at=NOW()" if done else "")
                    + " WHERE tenant_id=%s",
                    (next_step, json.dumps(completed), tenant_id)
                )
        except Exception as e:
            logger.error(f"OnboardingService.complete_step failed: {e}")
