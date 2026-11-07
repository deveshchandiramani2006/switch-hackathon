"""
BillingService - Stripe-based subscription management.

Env vars:
  STRIPE_SECRET_KEY    - Stripe API key (sk_live_... or sk_test_...)
  STRIPE_WEBHOOK_SECRET - For verifying Stripe webhook signatures
  BILLING_MOCK_MODE    - Set to "true" to use mock checkout (default: false)

Price IDs (set these to your actual Stripe price IDs):
  STRIPE_PRICE_STARTER    - Monthly starter plan price ID
  STRIPE_PRICE_PRO        - Monthly pro plan price ID
  STRIPE_PRICE_ENTERPRISE - Monthly enterprise plan price ID
"""
import os
import logging
from app.Services.DatabaseService import db_cursor

logger = logging.getLogger(__name__)

STRIPE_KEY             = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
MOCK_MODE              = os.getenv("BILLING_MOCK_MODE", "false").lower() == "true"
BILLING_SUCCESS_URL    = os.getenv("BILLING_SUCCESS_URL", "https://nexus.ai/billing/success")
BILLING_CANCEL_URL     = os.getenv("BILLING_CANCEL_URL",  "https://nexus.ai/billing/cancel")

PLAN_PRICE_IDS = {
    "starter":    os.getenv("STRIPE_PRICE_STARTER",    "price_starter_placeholder"),
    "pro":        os.getenv("STRIPE_PRICE_PRO",         "price_pro_placeholder"),
    "enterprise": os.getenv("STRIPE_PRICE_ENTERPRISE",  "price_enterprise_placeholder"),
}

PLAN_FEATURES = {
    "free":       {"agents": 3,  "llm_per_day": 100,  "price_monthly": 0},
    "starter":    {"agents": 5,  "llm_per_day": 300,  "price_monthly": 49},
    "pro":        {"agents": 7,  "llm_per_day": 1000, "price_monthly": 149},
    "enterprise": {"agents": 7,  "llm_per_day": -1,   "price_monthly": 499},
}


class BillingService:

    @classmethod
    def create_checkout_session(cls, tenant_id: str, plan: str, customer_email: str = None) -> dict:
        """
        Create a Stripe Checkout session for a plan upgrade.
        Returns {"url": "...", "session_id": "..."} or {"error": "..."}.
        """
        if plan not in PLAN_PRICE_IDS:
            return {"error": f"Unknown plan: {plan}. Choose from: {list(PLAN_PRICE_IDS.keys())}"}

        if MOCK_MODE or not STRIPE_KEY:
            mock_url = f"{BILLING_SUCCESS_URL}?tenant_id={tenant_id}&plan={plan}&mock=1"
            logger.info(f"BillingService MOCK checkout for {tenant_id} plan={plan}")
            return {"url": mock_url, "session_id": f"mock_{tenant_id}_{plan}"}

        try:
            import stripe
            stripe.api_key = STRIPE_KEY

            session_kwargs = {
                "mode":               "subscription",
                "line_items":         [{"price": PLAN_PRICE_IDS[plan], "quantity": 1}],
                "success_url":        f"{BILLING_SUCCESS_URL}?session_id={{CHECKOUT_SESSION_ID}}&tenant_id={tenant_id}",
                "cancel_url":         BILLING_CANCEL_URL,
                "metadata":           {"tenant_id": tenant_id, "plan": plan},
                "subscription_data":  {"metadata": {"tenant_id": tenant_id, "plan": plan}},
            }
            if customer_email:
                session_kwargs["customer_email"] = customer_email

            session = stripe.checkout.Session.create(**session_kwargs)
            return {"url": session.url, "session_id": session.id}
        except Exception as e:
            logger.error(f"Stripe checkout failed: {e}")
            return {"error": str(e)}

    @classmethod
    def handle_webhook(cls, payload: bytes, sig_header: str) -> dict:
        """Process a Stripe webhook event. Returns {"status": "ok"} or {"error": "..."}."""
        if MOCK_MODE or not STRIPE_KEY:
            return {"status": "ok", "note": "mock mode"}

        try:
            import stripe
            stripe.api_key = STRIPE_KEY
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            return {"error": f"Webhook verification failed: {e}"}

        if event["type"] in ("checkout.session.completed", "invoice.payment_succeeded"):
            metadata  = event["data"]["object"].get("metadata", {})
            tenant_id = metadata.get("tenant_id")
            plan      = metadata.get("plan")
            if tenant_id and plan:
                cls.update_plan(tenant_id, plan)
                logger.info(f"Plan updated via webhook: {tenant_id} -> {plan}")

        elif event["type"] in ("customer.subscription.deleted", "invoice.payment_failed"):
            metadata  = event["data"]["object"].get("metadata", {})
            tenant_id = metadata.get("tenant_id")
            if tenant_id:
                cls.update_plan(tenant_id, "free")
                logger.info(f"Plan downgraded via webhook: {tenant_id} -> free")

        return {"status": "ok"}

    @classmethod
    def update_plan(cls, tenant_id: str, plan: str) -> bool:
        """Directly update a tenant's plan (used by webhook handler and admin API)."""
        if plan not in PLAN_FEATURES:
            return False
        try:
            with db_cursor() as cur:
                cur.execute(
                    "UPDATE tenants SET plan=%s, llm_calls_today=0 WHERE tenant_id=%s",
                    (plan, tenant_id)
                )
            logger.info(f"Plan updated: {tenant_id} -> {plan}")
            return True
        except Exception as e:
            logger.error(f"update_plan failed: {e}")
            return False

    @classmethod
    def get_plan_info(cls, tenant_id: str) -> dict:
        """Return plan details + upgrade options for a tenant."""
        try:
            with db_cursor() as cur:
                cur.execute(
                    "SELECT plan, llm_calls_today FROM tenants WHERE tenant_id=%s",
                    (tenant_id,)
                )
                row = cur.fetchone()
            current_plan = row["plan"] if row else "free"
        except Exception:
            current_plan = "free"

        current = PLAN_FEATURES.get(current_plan, PLAN_FEATURES["free"])
        upgrades = {
            k: v for k, v in PLAN_FEATURES.items()
            if v["price_monthly"] > current["price_monthly"]
        }
        return {
            "current_plan":   current_plan,
            "features":       current,
            "upgrade_options": upgrades,
        }
