"""
register_agents.py - Register all 7 NEXUS agents with Switch.

Run this once after Switch Console is running:
    cd nexus/
    python register_agents.py

Prints agent IDs and API keys. Copy them into your .env file,
then set SWITCH_ROOM_ID_* from Switch Console.
"""
import os
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

REGISTRATION_KEY = os.getenv("SWITCH_REGISTRATION_KEY", "")
SWITCH_URL       = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")

AGENTS = [
    {
        "name":        "SalesAgent",
        "description": "Manages sales pipeline and leads. Fires cross-agent signals on deal close: "
                       "send_targeted_message to FinanceAgent (revenue) and CSAgent (onboarding).",
        "prefix":      "SALES",
    },
    {
        "name":        "SupportAgent",
        "description": "Triages bugs with LLM severity classification (P0-P3). "
                       "Escalates P0/P1 bugs directly to CSAgent via Switch send_targeted_message.",
        "prefix":      "SUPPORT",
    },
    {
        "name":        "CSAgent",
        "description": "Tracks customer health scores, renewals, and at-risk accounts. "
                       "Receives DEAL_WON and P1_BREACH signals from other agents.",
        "prefix":      "CS",
    },
    {
        "name":        "FinanceAgent",
        "description": "Manages invoices, approvals, expense claims, and revenue tracking. "
                       "Receives DEAL_WON signals from SalesAgent.",
        "prefix":      "FINANCE",
    },
    {
        "name":        "GeoSEOAgent",
        "description": "Scores AI citability for keywords. Sends CONTENT_BRIEF signals "
                       "to BlogAgent via Switch when keyword scores below threshold.",
        "prefix":      "GEOSEO",
    },
    {
        "name":        "BlogAgent",
        "description": "Generates AI blog drafts, manages approval workflow, publishes on approval. "
                       "Receives CONTENT_BRIEF signals from GeoSEOAgent.",
        "prefix":      "BLOG",
    },
    {
        "name":        "InfraAgent",
        "description": "Monitors service health with live HTTP pings. "
                       "Fires alerts on consecutive failures.",
        "prefix":      "INFRA",
    },
]


def main():
    if not REGISTRATION_KEY:
        print("ERROR: SWITCH_REGISTRATION_KEY not set in .env")
        print("Get your registration key from Switch Console.")
        sys.exit(1)

    from app.Services.SwitchClient import SwitchClient

    print(f"Registering 7 NEXUS agents with Switch at {SWITCH_URL}...\n")
    print("=" * 60)
    print("Add these lines to your .env:\n")

    success = 0
    for agent in AGENTS:
        try:
            result = SwitchClient.register(
                name=agent["name"],
                description=agent["description"],
                registration_key=REGISTRATION_KEY,
            )
            prefix    = agent["prefix"]
            agent_id  = result.get("agent_id") or result.get("id", "")
            api_key   = result.get("api_key") or result.get("key", "")

            print(f"# {agent['name']}")
            print(f"SWITCH_AGENT_ID_{prefix}={agent_id}")
            print(f"SWITCH_API_KEY_{prefix}={api_key}")
            print()
            success += 1
        except Exception as e:
            print(f"# {agent['name']} - FAILED: {e}")
            print()

    print("=" * 60)
    print(f"Registered {success}/7 agents.")
    if success == 7:
        print("\nNext: set SWITCH_ROOM_ID_* from Switch Console, then run:")
        print("  python run_agents.py")
    else:
        print("\nSome registrations failed. Check SWITCH_SERVER_URL and SWITCH_REGISTRATION_KEY.")


if __name__ == "__main__":
    main()
