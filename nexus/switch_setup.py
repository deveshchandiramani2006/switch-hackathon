import os
import sys
import requests
from dotenv import load_dotenv, set_key

load_dotenv()

SWITCH_URL = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")
REG_KEY    = os.getenv("SWITCH_REGISTRATION_KEY", "")

AGENTS = [
    {
        "name": "SalesAgent",
        "description": "CRM, pipeline, and escalation engine",
        "id_env":   "SWITCH_AGENT_ID_SALES",
        "key_env":  "SWITCH_API_KEY_SALES",
        "addressing": "anyone",
    },
    {
        "name": "SupportAgent",
        "description": "Bug triage, severity classification, SLA tracking",
        "id_env":   "SWITCH_AGENT_ID_SUPPORT",
        "key_env":  "SWITCH_API_KEY_SUPPORT",
        "addressing": "anyone",
    },
    {
        "name": "GeoSEOAgent",
        "description": "Geo keyword trends, content brief generation",
        "id_env":   "SWITCH_AGENT_ID_GEOSEO",
        "key_env":  "SWITCH_API_KEY_GEOSEO",
        "addressing": "owner_and_owner_agents",
    },
    {
        "name": "BlogAgent",
        "description": "Blog draft generation, approval, and publishing",
        "id_env":   "SWITCH_AGENT_ID_BLOG",
        "key_env":  "SWITCH_API_KEY_BLOG",
        "addressing": "owner_and_owner_agents",
    },
    {
        "name": "InfraAgent",
        "description": "Service health monitoring and on-call alerts",
        "id_env":   "SWITCH_AGENT_ID_INFRA",
        "key_env":  "SWITCH_API_KEY_INFRA",
        "addressing": "anyone",
    },
]


def register_agent(agent: dict) -> tuple:
    payload = {
        "name": agent["name"],
        "description": agent["description"],
        "connector_type": "custom_client",
        "integration_profile": {
            "connection_model": "always_on",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": []
        }
    }
    resp = requests.post(
        f"{SWITCH_URL}/agents",
        headers={
            "Authorization": f"Bearer {REG_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=15
    )
    resp.raise_for_status()
    data = resp.json()
    return data["agent_id"], data["api_key"]


def set_addressing(agent_id: str, api_key: str, mode: str):
    requests.post(
        f"{SWITCH_URL}/agents/{agent_id}/ops/update_agent_detail",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"agent_id": agent_id, "addressing": mode},
        timeout=10
    )


if __name__ == "__main__":
    if not REG_KEY:
        print("ERROR: SWITCH_REGISTRATION_KEY not set in .env")
        sys.exit(1)

    print("Registering agents with Switch...\n")
    env_path = os.path.join(os.path.dirname(__file__), ".env")

    for agent in AGENTS:
        if os.getenv(agent["key_env"]):
            print(f"  {agent['name']} -- already registered, skipping")
            continue
        try:
            agent_id, api_key = register_agent(agent)
            set_key(env_path, agent["id_env"], agent_id)
            set_key(env_path, agent["key_env"], api_key)
            set_addressing(agent_id, api_key, agent["addressing"])
            print(f"  {agent['name']} registered  (id={agent_id[:8]}...)")
        except Exception as e:
            print(f"  {agent['name']} FAILED: {e}")
            sys.exit(1)

    print("\nAll agents registered.")
    print("Next: add SWITCH_ROOM_ID_* values to .env, then run docker compose up -d")
