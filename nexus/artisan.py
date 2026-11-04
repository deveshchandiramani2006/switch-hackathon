#!/usr/bin/env python3
"""
NEXUS Artisan — project CLI tool.

Usage:
  python artisan.py migrate        Run database migrations
  python artisan.py seed           Seed demo data
  python artisan.py agents:setup   Register agents with Switch
  python artisan.py health:check   System health check
  python artisan.py serve:api      Start management API (dev)
  python artisan.py serve:voice    Start voice server (dev)
"""
import sys
import os


def _migrate():
    from database.migrations.migrate import run_migrations
    run_migrations()


def _seed():
    from database.seeders.DemoSeeder import run_seeder
    run_seeder()


def _agents_setup():
    import requests
    from dotenv import load_dotenv, set_key

    load_dotenv()
    switch_url = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")
    reg_key    = os.getenv("SWITCH_REGISTRATION_KEY", "")

    if not reg_key:
        print("ERROR: SWITCH_REGISTRATION_KEY not set in .env")
        sys.exit(1)

    agents = [
        {"name": "SalesAgent",   "description": "CRM, pipeline, and escalation engine",                             "id_env": "SWITCH_AGENT_ID_SALES",   "key_env": "SWITCH_API_KEY_SALES",   "addressing": "anyone"},
        {"name": "SupportAgent", "description": "Bug triage, severity classification, SLA tracking",                "id_env": "SWITCH_AGENT_ID_SUPPORT", "key_env": "SWITCH_API_KEY_SUPPORT", "addressing": "anyone"},
        {"name": "GeoSEOAgent",  "description": "Geo keyword trends, content brief generation",                     "id_env": "SWITCH_AGENT_ID_GEOSEO",  "key_env": "SWITCH_API_KEY_GEOSEO",  "addressing": "owner_and_owner_agents"},
        {"name": "BlogAgent",    "description": "Blog draft generation, approval, and publishing",                  "id_env": "SWITCH_AGENT_ID_BLOG",    "key_env": "SWITCH_API_KEY_BLOG",    "addressing": "owner_and_owner_agents"},
        {"name": "InfraAgent",   "description": "Service health monitoring and on-call alerts",                     "id_env": "SWITCH_AGENT_ID_INFRA",   "key_env": "SWITCH_API_KEY_INFRA",   "addressing": "anyone"},
        {"name": "CSAgent",      "description": "Customer success, health scoring, renewal tracking",               "id_env": "SWITCH_AGENT_ID_CS",      "key_env": "SWITCH_API_KEY_CS",      "addressing": "owner_and_owner_agents"},
        {"name": "FinanceAgent", "description": "Invoice approvals, budget tracking, expense management",           "id_env": "SWITCH_AGENT_ID_FINANCE", "key_env": "SWITCH_API_KEY_FINANCE", "addressing": "owner_and_owner_agents"},
    ]

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    print("Registering agents with Switch...\n")

    for agent in agents:
        if os.getenv(agent["key_env"]):
            print(f"  {agent['name']} -- already registered, skipping")
            continue
        try:
            resp = requests.post(
                f"{switch_url}/agents",
                headers={"Authorization": f"Bearer {reg_key}", "Content-Type": "application/json"},
                json={
                    "name": agent["name"], "description": agent["description"],
                    "connector_type": "custom_client",
                    "integration_profile": {
                        "connection_model": "always_on", "message_exchange": True,
                        "pre_invocation_mediation": [], "post_invocation_mediation": [], "event_reporting": []
                    }
                },
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            agent_id, api_key = data["agent_id"], data["api_key"]

            requests.post(
                f"{switch_url}/agents/{agent_id}/ops/update_agent_detail",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"agent_id": agent_id, "addressing": agent["addressing"]},
                timeout=10
            )

            set_key(env_path, agent["id_env"],  agent_id)
            set_key(env_path, agent["key_env"], api_key)
            print(f"  {agent['name']} registered  (id={agent_id[:8]}...)")
        except Exception as e:
            print(f"  {agent['name']} FAILED: {e}")
            sys.exit(1)

    print("\nAll agents registered.")
    print("Next: add SWITCH_ROOM_ID_* values to .env, then run docker compose up -d")


def _health_check():
    import psycopg2
    import requests
    from dotenv import load_dotenv

    load_dotenv()
    switch_url = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")
    db_url     = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")

    checks = []

    try:
        conn = psycopg2.connect(db_url)
        conn.close()
        checks.append(("PostgreSQL", "OK", ""))
    except Exception as e:
        checks.append(("PostgreSQL", "FAIL", str(e)))

    try:
        requests.get(f"{switch_url}/health", timeout=5)
        checks.append(("Switch", "OK", ""))
    except Exception:
        checks.append(("Switch", "FAIL", f"Not reachable at {switch_url}"))

    for name, key in [
        ("SalesAgent",   "SWITCH_API_KEY_SALES"),
        ("SupportAgent", "SWITCH_API_KEY_SUPPORT"),
        ("GeoSEOAgent",  "SWITCH_API_KEY_GEOSEO"),
        ("BlogAgent",    "SWITCH_API_KEY_BLOG"),
        ("InfraAgent",   "SWITCH_API_KEY_INFRA"),
    ]:
        val = os.getenv(key, "")
        if val:
            checks.append((f"{name} key", "OK", ""))
        else:
            checks.append((f"{name} key", "FAIL", f"{key} not set in .env"))

    print("\nNEXUS Health Check")
    print("=" * 40)
    all_ok = True
    for name, status, note in checks:
        icon = "[OK]" if status == "OK" else "[FAIL]"
        print(f"  {icon} {name}" + (f" -- {note}" if note else ""))
        if status == "FAIL":
            all_ok = False

    print()
    if all_ok:
        print("All checks passed. Ready to run.\n")
        sys.exit(0)
    else:
        print("Some checks failed. Fix the above before running.\n")
        sys.exit(1)


def _serve_api():
    from bootstrap.api import create_app
    port = int(os.getenv("MANAGEMENT_API_PORT", "5000"))
    create_app().run(host="0.0.0.0", port=port, debug=False)


def _serve_voice():
    from bootstrap.voice import create_app
    port = int(os.getenv("VOICE_SERVER_PORT", "5001"))
    create_app().run(host="0.0.0.0", port=port, debug=False)


COMMANDS = {
    "migrate":       _migrate,
    "seed":          _seed,
    "agents:setup":  _agents_setup,
    "health:check":  _health_check,
    "serve:api":     _serve_api,
    "serve:voice":   _serve_voice,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print("Available commands:")
        for cmd in COMMANDS:
            print(f"  python artisan.py {cmd}")
        sys.exit(1)

    COMMANDS[sys.argv[1]]()
