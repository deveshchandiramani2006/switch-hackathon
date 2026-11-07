"""
register_agents.py — Register all 7 NEXUS agents with Switch and auto-write .env.

Usage:
  1. Start Switch Console
  2. Set SWITCH_REGISTRATION_KEY in .env (copy from Switch Console → Settings)
  3. Run:  cd nexus && python3 register_agents.py

The script registers every agent, then automatically writes
SWITCH_AGENT_ID_* / SWITCH_API_KEY_* back into .env.
After that, copy SWITCH_ROOM_ID_* from Switch Console and restart run_agents.py.
"""
import os
import re
import sys
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

REGISTRATION_KEY = os.getenv("SWITCH_REGISTRATION_KEY", "")
SWITCH_URL       = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")
ENV_FILE         = os.path.join(os.path.dirname(__file__), ".env")

AGENTS = [
    {
        "name":        "sales-agent",   # Switch requires lowercase-hyphenated
        "display":     "SalesAgent",    # used in NEXUS agent code
        "description": "Manages sales pipeline and leads. Fires cross-agent signals on deal close: "
                       "send_targeted_message to FinanceAgent (revenue) and CSAgent (onboarding).",
        "prefix":      "SALES",
    },
    {
        "name":        "support-agent",
        "display":     "SupportAgent",
        "description": "Triages bugs with LLM severity classification (P0-P3). "
                       "Escalates P0/P1 bugs directly to CSAgent via Switch send_targeted_message.",
        "prefix":      "SUPPORT",
    },
    {
        "name":        "cs-agent",
        "display":     "CSAgent",
        "description": "Tracks customer health scores, renewals, and at-risk accounts. "
                       "Receives DEAL_WON and P1_BREACH signals from other agents.",
        "prefix":      "CS",
    },
    {
        "name":        "finance-agent",
        "display":     "FinanceAgent",
        "description": "Manages invoices, approvals, expense claims, and revenue tracking. "
                       "Receives DEAL_WON signals from SalesAgent.",
        "prefix":      "FINANCE",
    },
    {
        "name":        "geo-seo-agent",
        "display":     "GeoSEOAgent",
        "description": "Scores AI citability for keywords. Sends CONTENT_BRIEF signals "
                       "to BlogAgent via Switch when keyword scores below threshold.",
        "prefix":      "GEOSEO",
    },
    {
        "name":        "blog-agent",
        "display":     "BlogAgent",
        "description": "Generates AI blog drafts, manages approval workflow, publishes on approval. "
                       "Receives CONTENT_BRIEF signals from GeoSEOAgent.",
        "prefix":      "BLOG",
    },
    {
        "name":        "infra-agent",
        "display":     "InfraAgent",
        "description": "Monitors service health with live HTTP pings. "
                       "Fires alerts on consecutive failures.",
        "prefix":      "INFRA",
    },
]


def _patch_env(key: str, value: str):
    """Update a key=value line in .env in-place, or append if not found."""
    try:
        with open(ENV_FILE, "r") as f:
            content = f.read()
        pattern = rf"^({re.escape(key)}=).*$"
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
        else:
            content += f"\n{key}={value}"
        with open(ENV_FILE, "w") as f:
            f.write(content)
    except Exception as e:
        print(f"  WARNING: could not update .env ({e})")


def main():
    if not REGISTRATION_KEY:
        print("ERROR: SWITCH_REGISTRATION_KEY not set in .env")
        print()
        print("Steps to fix:")
        print("  1. Open Switch Console")
        print("  2. Go to Settings → Copy the Registration Key")
        print("  3. Add to .env:  SWITCH_REGISTRATION_KEY=<your-key>")
        print("  4. Re-run this script")
        sys.exit(1)

    # Quick connectivity check
    import requests
    try:
        requests.get(f"{SWITCH_URL}/health", timeout=3)
    except Exception:
        print(f"ERROR: Cannot reach Switch server at {SWITCH_URL}")
        print("Make sure Switch Console is running (it starts the local server).")
        sys.exit(1)

    from app.Services.SwitchClient import SwitchClient

    print(f"Registering 7 NEXUS agents with Switch at {SWITCH_URL}...\n")

    results = {}
    success = 0
    for agent in AGENTS:
        name    = agent["name"]     # Switch-registered name (lowercase-hyphenated)
        display = agent.get("display", name)
        prefix  = agent["prefix"]
        try:
            result   = SwitchClient.register(
                name=name,
                description=agent["description"],
                registration_key=REGISTRATION_KEY,
            )
            agent_id = result.get("agent_id") or result.get("id", "")
            api_key  = result.get("api_key") or result.get("key", "")

            if not agent_id or not api_key:
                raise ValueError(f"Unexpected response: {result}")

            results[prefix] = {"agent_id": agent_id, "api_key": api_key, "name": display}
            print(f"  ✓ {display}  ({name})")
            success += 1
        except Exception as e:
            print(f"  ✗ {display} — {e}")

    print()
    if success == 0:
        print("All registrations failed. Check SWITCH_SERVER_URL and SWITCH_REGISTRATION_KEY.")
        sys.exit(1)

    # Auto-write to .env
    print(f"Writing {success} agent credentials to .env...")
    for prefix, creds in results.items():
        _patch_env(f"SWITCH_AGENT_ID_{prefix}", creds["agent_id"])
        _patch_env(f"SWITCH_API_KEY_{prefix}", creds["api_key"])
        print(f"  {creds['name']:14s}  id={creds['agent_id'][:12]}…  key={creds['api_key'][:8]}…")

    print()
    print(f"Done — {success}/7 agents registered.")
    print()
    print("One step left: set room IDs from Switch Console.")
    print("In Switch Console, find each agent's room and copy its ID.")
    print("Then add to .env:")
    for agent in AGENTS:
        p = agent["prefix"]
        if p in results:
            print(f"  SWITCH_ROOM_ID_{p}=<room-id-from-console>")
    print()
    print("Then restart:  python3 run_agents.py")


if __name__ == "__main__":
    main()
