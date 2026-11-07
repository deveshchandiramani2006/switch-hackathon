"""
migrate_fresh.py - Drop every table, re-run all migrations, seed test data.

Usage:
    cd nexus/
    python3 database/migrate_fresh.py

This is safe to run repeatedly. Every run gives you a clean slate.
"""
import os
import glob
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")

# Tables in dependency order (children first so FK constraints don't block DROP)
DROP_ORDER = [
    "schema_migrations",
    "escalation_log",
    "commitments",
    "customer_events",
    "approval_sessions",
    "approval_requests",
    "usage_events",
    "conversation_sessions",
    "onboarding_sessions",
    "agent_memory",
    "agent_patterns",
    "agent_heartbeats",
    "audit_log",
    "voice_transcriptions",
    "geo_citations",
    "geo_recommendations",
    "content_queue",
    "keyword_tracking",
    "monitored_services",
    "bugs",
    "leads",
    "customers",
    "invoices",
    "expenses",
    "budgets",
    "tenant_users",
    "tenant_configs",
    "tenants",
]


def drop_all(cur):
    print("Dropping all tables...")
    for table in DROP_ORDER:
        cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        print(f"  dropped {table}")


def run_migrations(cur):
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)

    for sql_file in sql_files:
        filename = os.path.basename(sql_file)
        print(f"  applying {filename}...")
        with open(sql_file) as f:
            cur.execute(f.read())
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING",
            (filename,)
        )
        print(f"  ✓ {filename}")


def seed_data(cur):
    print("\nSeeding test data...")

    # ── Tenant users (role-based access for modal testing) ────────────────────
    tenant_users = [
        ("default", "devesh",  "Devesh",      "admin"),
        ("default", "ravi",    "Ravi",         "manager"),
        ("default", "priya_s", "Priya (Sales)", "member"),
        ("default", "amit",    "Amit",          "member"),
    ]
    for u in tenant_users:
        cur.execute(
            "INSERT INTO tenant_users (tenant_id, username, display_name, role) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id, username) DO NOTHING",
            u
        )

    # ── Tenant config - escalation chain with Mailtrap email ─────────────────
    import json
    escalation_chain = {
        "sales": {
            "levels": [
                {"slack_user": "@ravi",   "wait_hours": 0},
                {"slack_user": "@devesh", "wait_hours": 0},
                {"slack_user": "@devesh", "email": "tools@onestopengineering.in", "deal_value": "Rs 12.5L", "wait_hours": 0},
            ],
            "deal_size_tiers": {}
        },
        "support": {
            "levels": [
                {"slack_user": "@ravi",   "wait_hours": 1},
                {"slack_user": "@devesh", "email": "tools@onestopengineering.in", "wait_hours": 2},
            ],
            "sla": {"p0_hours": 2, "p1_hours": 8, "p2_hours": 48}
        },
        "infra": {
            "levels": [
                {"slack_user": "@devesh", "email": "tools@onestopengineering.in", "wait_hours": 1},
            ],
            "failure_threshold": 2
        },
        "cs": {"csm": "@ravi", "cs_lead": "@devesh"},
        "finance": {"approver": "@ravi"}
    }
    thresholds = {
        "stale_lead_days": 7,
        "health_score_red": 50,
        "health_score_yellow": 70,
        "escalation_check_minutes": 1,  # 1 min for demo - sees escalation fast
        "infra_failure_threshold": 2,
    }
    cur.execute(
        """
        UPDATE tenant_configs
        SET escalation_chain=%s, thresholds=%s, updated_at=NOW()
        WHERE tenant_id='default'
        """,
        (json.dumps(escalation_chain), json.dumps(thresholds))
    )
    print("  tenant_configs updated with Mailtrap escalation chain")

    # ── Leads (all stages, one stale) ─────────────────────────────────────────
    from datetime import datetime, timedelta, date
    stale_date = datetime.utcnow() - timedelta(days=10)

    leads = [
        # (name, role, company, city, industry, deal_value, stage, rep)
        ("Priya Sharma",  "CTO",      "FinancePro",  "Mumbai",    "fintech",  500000,  "Negotiation", "@ravi"),
        ("Ankit Mehta",   "VP Ops",   "PayCo",       "Hyderabad", "fintech",  200000,  "Qualified",   "@ravi"),
        ("Meera Singh",   "Founder",  "HRstack",     "Bangalore", "hr-tech", 1000000,  "Prospect",    "@amit"),
        ("Rahul Verma",   "Head Eng", "CloudBase",   "Pune",      "cloud",    300000,  "Proposal",    "@ravi"),
        ("Sunita Patel",  "CEO",      "RetailEdge",  "Delhi",     "retail",   750000,  "Demo",        "@amit"),
    ]
    for l in leads:
        cur.execute(
            """
            INSERT INTO leads (name, role, company, city, industry, deal_value, stage,
                               rep_slack_user, tenant_id, last_touched_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'default',%s)
            """,
            (*l, stale_date if l[0] == "Ankit Mehta" else datetime.utcnow())
        )
    print("  5 leads seeded (Ankit Mehta is stale 10d)")

    # ── Commitments - 2 overdue (triggers escalation + email) ────────────────
    overdue_3d = datetime.utcnow() - timedelta(days=3)
    overdue_1d = datetime.utcnow() - timedelta(days=1)

    cur.execute(
        """
        INSERT INTO commitments
            (tenant_id, lead_name, commitment_text, party, deadline, detected_by, source_message)
        VALUES
            ('default','Ankit Mehta','Ankit will send internal sign-off',
             'customer', %s, 'manual', 'Said he will send approval EOD Friday'),
            ('default','Priya Sharma','Priya will share legal review doc',
             'customer', %s, 'manual', 'Mentioned legal review in call')
        """,
        (overdue_3d, overdue_1d)
    )
    print("  2 overdue commitments seeded (escalation will fire immediately)")

    # ── Customers (healthy, yellow, RED - RED triggers CS health alert) ───────
    customers = [
        # (name, arr, renewal_date, health_score, nps, assigned_csm)
        ("Acme Corp",   500000,  date.today() + timedelta(days=30),  85, 9, "@ravi"),
        ("TechStack",   200000,  date.today() + timedelta(days=90),  35, 5, "@ravi"),   # RED
        ("PayCo",      1000000,  date.today() + timedelta(days=60),  72, 8, "@amit"),
        ("RetailEdge",  300000,  date.today() + timedelta(days=15),  60, 7, "@ravi"),   # renewal soon
        ("CloudBase",   750000,  date.today() + timedelta(days=10),  48, 4, "@amit"),   # RED + renewal in 10d
    ]
    for c in customers:
        cur.execute(
            """
            INSERT INTO customers (tenant_id, name, arr, renewal_date, health_score, nps, assigned_csm)
            VALUES ('default',%s,%s,%s,%s,%s,%s)
            """,
            c
        )
    print("  5 customers seeded (TechStack & CloudBase are RED, CloudBase renews in 10d)")

    # ── Bugs (P0 open, P1 open, P2 open, P3 closed) ───────────────────────────
    bugs = [
        ("Payment gateway returns 500 on UPI transactions - all Indian cards failing",
         "P0", "open",  "@amit"),
        ("CSV export truncates rows beyond 1000 entries",
         "P1", "open",  "@ravi"),
        ("Dashboard charts render blank on Firefox 120",
         "P2", "open",  "@amit"),
        ("Tooltip text overflows on mobile viewport",
         "P3", "closed","@ravi"),
    ]
    for b in bugs:
        cur.execute(
            """
            INSERT INTO bugs (tenant_id, description, severity, status, reported_by, source)
            VALUES ('default',%s,%s,%s,%s,'manual')
            """,
            b
        )
    print("  4 bugs seeded (P0 UPI crash open, P1 open)")

    # ── Invoices (pending - approve/reject via /nexus-approve or /nexus-reject) ─
    invoices = [
        ("AWS",        150000, date.today() + timedelta(days=5),  "infrastructure"),
        ("Zoom",        20000, date.today() + timedelta(days=10), "software"),
        ("Google Ads",  80000, date.today() - timedelta(days=2),  "marketing"),   # overdue!
        ("HubSpot",     50000, date.today() + timedelta(days=20), "software"),
    ]
    for inv in invoices:
        cur.execute(
            """
            INSERT INTO invoices (tenant_id, vendor, amount, due_date, category, submitted_by)
            VALUES ('default',%s,%s,%s,%s,'@ravi')
            """,
            inv
        )
    print("  4 invoices seeded (Google Ads is overdue, all pending approval)")

    # ── Expenses (pending) ─────────────────────────────────────────────────────
    expenses = [
        ("Ravi",   8500,  "travel",    date.today() - timedelta(days=3)),
        ("Devesh", 3200,  "equipment", date.today() - timedelta(days=1)),
        ("Amit",   1500,  "meals",     date.today()),
    ]
    for e in expenses:
        cur.execute(
            """
            INSERT INTO expenses (tenant_id, submitter, amount, category, expense_date, status)
            VALUES ('default',%s,%s,%s,%s,'pending')
            """,
            e
        )
    print("  3 expense claims seeded (all pending)")

    # ── Budgets ────────────────────────────────────────────────────────────────
    budgets = [
        ("Engineering", "Q4-2026", 1000000, 450000),
        ("Marketing",   "Q4-2026",  500000, 465000),  # 93% burned - alert!
        ("Operations",  "Q4-2026",  300000, 120000),
    ]
    for b in budgets:
        cur.execute(
            """
            INSERT INTO budgets (tenant_id, name, period, allocated, spent)
            VALUES ('default',%s,%s,%s,%s)
            """,
            b
        )
    print("  3 budgets seeded (Marketing at 93% - will trigger warning)")

    # ── Keywords (SEO/GEO tracking) ───────────────────────────────────────────
    keywords = [
        ("best CRM for Indian startups",        "IN", 12400),
        ("AI tools for sales team India",        "IN",  8200),
        ("automated invoicing software India",   "IN",  6700),
        ("customer success software SaaS India", "IN",  4100),
    ]
    for kw in keywords:
        cur.execute(
            "INSERT INTO keyword_tracking (tenant_id, keyword, country, volume) "
            "VALUES ('default',%s,%s,%s) ON CONFLICT (tenant_id, keyword) DO NOTHING",
            kw
        )
    print("  4 keywords tracked for GEO/SEO")

    # ── Monitored services ─────────────────────────────────────────────────────
    services = [
        ("API Gateway",      "https://httpbin.org/status/200"),
        ("Database",         "https://httpbin.org/status/200"),
        ("payments-service", "https://httpbin.org/status/200"),
        ("auth-service",     "https://httpbin.org/status/200"),
    ]
    for svc in services:
        cur.execute(
            "INSERT INTO monitored_services (tenant_id, name, url, status) "
            "VALUES ('default',%s,%s,'healthy') ON CONFLICT (tenant_id, name) DO NOTHING",
            svc
        )
    print("  4 services seeded for Infra monitoring")

    # ── Blog drafts (pre-written, no LLM needed) ───────────────────────────────
    drafts = [
        (
            "best CRM for Indian startups",
            "Best CRM Software for Indian Startups: Complete Guide 2026",
            "Choosing the right CRM is one of the highest-leverage decisions an Indian startup can make. With deal cycles averaging 45 days and reps juggling WhatsApp, email, and Slack, you need a CRM that fits the way Indian teams actually work.",
            """Choosing the right CRM is one of the highest-leverage decisions an Indian startup can make. With deal cycles averaging 45 days and reps juggling WhatsApp, email, and Slack, you need a CRM that fits the way Indian teams actually work. We evaluated 12 tools on price, localisation, and AI features.

## Why Indian Startups Need a Different CRM

Most CRMs were built for US enterprise sales motions - long email threads, structured demo flows, and procurement committees. Indian B2B sales is different: deals close over WhatsApp, decision-makers want calls not demos, and pricing sensitivity is higher.

## Top 5 CRMs for Indian Startups in 2026

**1. NEXUS AI CRM** - purpose-built for Indian teams with WhatsApp integration, INR pricing, and an AI agent that handles follow-ups automatically.

**2. Zoho CRM** - the most popular choice for SMBs, strong localisation, affordable pricing starting at Rs 800/user/month.

**3. Leadsquared** - built in Bangalore, strong in field sales and education verticals, good for teams with high-volume inbound.

**4. Freshsales** - Freshworks' CRM is polished and affordable, good API support for integrations.

**5. HubSpot Free** - good for early-stage startups, limitations kick in at scale.

## What to Look For

- INR pricing (avoid USD billing surprises)
- WhatsApp integration
- AI-powered follow-up suggestions
- Mobile-first design for field sales reps
- Indian payment gateway integrations

## Verdict

For most Indian seed-to-Series A startups, NEXUS or Leadsquared will give the best ROI. Enterprise teams should evaluate Zoho Enterprise or Salesforce with heavy customisation.""",
        ),
        (
            "AI tools for sales team India",
            "5 AI Tools Transforming Sales Teams in India (2026)",
            "Indian sales teams are adopting AI at record speed. From automated follow-ups to deal intelligence and pipeline forecasting, the right AI stack can cut sales cycles by 40%.",
            """Indian sales teams are adopting AI at record speed. From automated follow-ups to deal intelligence and pipeline forecasting, the right AI stack can cut sales cycles by 40%. In this guide we cover the five tools making the biggest difference for B2B SaaS teams across Mumbai, Bangalore, and Delhi in 2026.

## The State of AI in Indian Sales

67% of Indian B2B sales leaders say AI tools are now a competitive necessity, up from 23% in 2024 (IDC India, 2026). Yet most teams are still using basic automation - the real gains come from AI that understands context.

## 5 AI Tools Worth Investing In

**1. NEXUS SalesAgent** - an AI agent that lives in your Slack, tracks commitments, drafts follow-ups, and escalates overdue deals automatically. Zero context-switching.

**2. Gong.io India** - conversation intelligence for sales calls. Transcribes, scores, and surfaces deal risks. Now available with Hindi language support.

**3. Clay** - AI-powered lead enrichment. Build targeted prospect lists with verified Indian contact data at Rs 15/contact.

**4. Lavender** - AI email coach. Analyses your emails in real time and suggests improvements. Reduces ghosting by 31%.

**5. Clari** - revenue forecasting AI. Predicts deal close probability with 89% accuracy. Available on AWS India region.

## How to Get Started

Don't try to adopt all five at once. Start with one tool that solves your biggest bottleneck - usually follow-up consistency or pipeline visibility - prove ROI, then expand.

## The Bottom Line

AI doesn't replace great sales reps. It removes the administrative drag so they can spend more time actually selling. Indian teams that get this right are seeing 2-3x pipeline velocity improvements.""",
        ),
    ]

    for kw, title, meta, body in drafts:
        cur.execute(
            """
            INSERT INTO content_queue
                (tenant_id, keyword, title, meta_description, draft_content, status, source)
            VALUES ('default', %s, %s, %s, %s, 'draft_ready', 'geo_seo')
            """,
            (kw, title, meta, body)
        )
    print("  2 blog drafts seeded with pre-written content")

    print("\nSeed complete.")


def main():
    print(f"Connecting to: {DB_URL.split('@')[1] if '@' in DB_URL else DB_URL}\n")
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        drop_all(cur)
        conn.commit()
        print()

        print("Running migrations...")
        run_migrations(cur)
        conn.commit()

        seed_data(cur)
        conn.commit()

        import importlib.util, os as _os
        _spec = importlib.util.spec_from_file_location(
            "demo_slack_setup",
            _os.path.join(_os.path.dirname(__file__), "demo_slack_setup.py")
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _mod.run()

        print("\n✅  migrate_fresh complete - clean slate with full test data.")
        print("    Run agents: python3 run_agents.py")

    except Exception as e:
        conn.rollback()
        print(f"\n❌  Error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
