import os
import sys
import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

SWITCH_URL = os.getenv("SWITCH_SERVER_URL", "http://localhost:8080")
DB_URL = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")

checks = []

# PostgreSQL
try:
    conn = psycopg2.connect(DB_URL)
    conn.close()
    checks.append(("PostgreSQL", "OK", ""))
except Exception as e:
    checks.append(("PostgreSQL", "FAIL", str(e)))

# Switch
try:
    resp = requests.get(f"{SWITCH_URL}/health", timeout=5)
    checks.append(("Switch", "OK", ""))
except Exception as e:
    checks.append(("Switch", "FAIL", f"Not reachable at {SWITCH_URL}"))

# Agent keys
for name, key in [
    ("SalesAgent", "SWITCH_API_KEY_SALES"),
    ("SupportAgent", "SWITCH_API_KEY_SUPPORT"),
    ("GeoSEOAgent", "SWITCH_API_KEY_GEOSEO"),
    ("BlogAgent", "SWITCH_API_KEY_BLOG"),
    ("InfraAgent", "SWITCH_API_KEY_INFRA"),
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
