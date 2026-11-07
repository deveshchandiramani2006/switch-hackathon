import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


def run_seeder():
    conn = psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus"))
    cur  = conn.cursor()

    leads = [
        ("Priya Sharma", "CTO",      "FinancePro", "Mumbai",    "fintech", 200000, "Negotiation", "@ravi"),
        ("Ankit Mehta",  "VP Ops",   "PayCo",      "Hyderabad", "fintech", 150000, "Demo",        "@ravi"),
        ("Meera Singh",  "Founder",  "HRstack",    "Bangalore", "hr-tech", 350000, "Prospect",    "@ravi"),
    ]
    for lead in leads:
        try:
            cur.execute(
                """
                INSERT INTO leads (name, role, company, city, industry, deal_value, stage, rep_slack_user)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                lead
            )
            conn.commit()
        except Exception:
            conn.rollback()
            print(f"  Skipped duplicate lead: {lead[0]}")

    three_days_ago = datetime.utcnow() - timedelta(days=3)
    try:
        cur.execute(
            """
            INSERT INTO commitments (lead_name, commitment_text, party, deadline, detected_by, source_message)
            VALUES ('Ankit Mehta', 'Ankit will send internal approval', 'customer', %s, 'manual',
                    'Ankit said he would send approval EOD Friday')
            """,
            (three_days_ago,)
        )
        conn.commit()
        print("  Overdue commitment seeded (triggers escalation)")
    except Exception as e:
        conn.rollback()
        print(f"  Commitment skipped: {e}")

    keywords = [
        ("AI invoicing tools India", "IN", 12400),
        ("payroll software startup",  "IN",  8200),
        ("HR automation SaaS",        "IN",  6700),
    ]
    for kw in keywords:
        try:
            cur.execute(
                "INSERT INTO keyword_tracking (keyword, country, volume) VALUES (%s, %s, %s)", kw
            )
            conn.commit()
        except Exception:
            conn.rollback()

    services = [
        ("API Gateway",       "https://httpbin.org/status/200", "healthy"),
        ("Database",          "https://httpbin.org/status/200", "healthy"),
        ("payments-service",  "https://httpbin.org/status/200", "healthy"),
    ]
    for svc in services:
        try:
            cur.execute(
                "INSERT INTO monitored_services (name, url, status) VALUES (%s, %s, %s)", svc
            )
            conn.commit()
        except Exception:
            conn.rollback()

    cur.close()
    conn.close()
    print("Demo data seeded.")
    print("  Ankit's commitment is 3 days overdue - escalation fires on next check.")


if __name__ == "__main__":
    run_seeder()
