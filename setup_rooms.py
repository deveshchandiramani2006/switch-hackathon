"""
setup_rooms.py — Create Switch rooms for all 7 NEXUS agents and write IDs to .env.

Run after register_agents.py:
  python3 setup_rooms.py
"""
import os, re, sys, time, threading, uuid
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()

import requests
import websocket

url      = os.getenv("SWITCH_SERVER_URL", "http://localhost:8000")
ENV_FILE = os.path.join(os.path.dirname(__file__), ".env")

AGENTS = [
    ("SalesAgent",   "SALES",   "nexus-sales",   "sales-agent"),
    ("SupportAgent", "SUPPORT", "nexus-support", "support-agent"),
    ("CSAgent",      "CS",      "nexus-cs",      "cs-agent"),
    ("FinanceAgent", "FINANCE", "nexus-finance",  "finance-agent"),
    ("GeoSEOAgent",  "GEOSEO",  "nexus-growth",  "geo-seo-agent"),
    ("BlogAgent",    "BLOG",    "nexus-content",  "blog-agent"),
    ("InfraAgent",   "INFRA",   "nexus-devops",  "infra-agent"),
]


def patch_env(key: str, value: str):
    with open(ENV_FILE) as f:
        content = f.read()
    pattern = rf"^({re.escape(key)}=).*$"
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, rf"\g<1>{value}", content, flags=re.MULTILINE)
    else:
        content += f"\n{key}={value}"
    with open(ENV_FILE, "w") as f:
        f.write(content)


def create_room(agent_name: str, prefix: str, room_name: str, switch_name: str):
    agent_id = os.getenv(f"SWITCH_AGENT_ID_{prefix}", "")
    api_key  = os.getenv(f"SWITCH_API_KEY_{prefix}", "")
    if not agent_id or not api_key:
        print(f"  SKIP {agent_name} — no credentials in .env")
        return

    conn_id    = str(uuid.uuid4())
    ws_url     = (
        f"{url.replace('http', 'ws')}/agents/{agent_id}/connection/ws"
        f"?connection_id={conn_id}&scope=all&filter=addressed"
    )
    # Wait for the server's first message which confirms the connection is
    # fully open and HTTP ops with this conn_id are accepted.
    server_msg = threading.Event()

    def _on_msg(_ws, _raw):
        import json as _json
        try:
            msg = _json.loads(_raw)
            if msg.get("event") == "ping":
                _ws.send(_json.dumps({"type": "pong"}))
            server_msg.set()
        except Exception:
            server_msg.set()

    ws = websocket.WebSocketApp(
        ws_url,
        header={"Authorization": f"Bearer {api_key}"},
        on_message=_on_msg,
        on_error=lambda _ws, _e: server_msg.set(),
    )
    t = threading.Thread(target=ws.run_forever, daemon=True)
    t.start()

    if not server_msg.wait(timeout=8):
        print(f"  ✗ {agent_name} — no server message within 8s")
        ws.close()
        return
    time.sleep(1.0)  # Let the connection stabilise

    try:
        resp = requests.post(
            f"{url}/agents/{agent_id}/ops/create_room",
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Switch-Connection-Id": conn_id,
                "Content-Type": "application/json",
            },
            json={
                "name":        room_name,
                "description": f"NEXUS {agent_name} room",
                "agent_names": [switch_name],
            },
            timeout=10,
        )
    finally:
        ws.close()

    if resp.ok:
        data    = resp.json()
        result  = data.get("result", data)
        room_id = result.get("id") or result.get("room_id", "")
        if room_id:
            patch_env(f"SWITCH_ROOM_ID_{prefix}", room_id)
            print(f"  ✓ {agent_name:14s} → {room_name}  ({room_id[:14]}…)")
        else:
            print(f"  ? {agent_name} — unexpected response: {data}")
    else:
        print(f"  ✗ {agent_name} — {resp.status_code}: {resp.text[:200]}")


def main():
    try:
        requests.get(f"{url}/health", timeout=3)
    except Exception:
        print(f"ERROR: Switch server not reachable at {url}")
        sys.exit(1)

    print(f"Creating 7 rooms in Switch at {url}...\n")
    for agent_name, prefix, room_name, switch_name in AGENTS:
        create_room(agent_name, prefix, room_name, switch_name)

    print("\nRoom IDs written to .env.")
    print("Next: python3 run_agents.py")


if __name__ == "__main__":
    main()
