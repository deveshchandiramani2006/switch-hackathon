import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def run_migrations():
    db_url   = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")
    sql_path = os.path.join(os.path.dirname(__file__), "001_initial_schema.sql")

    with open(sql_path) as f:
        schema = f.read()

    conn = psycopg2.connect(db_url)
    cur  = conn.cursor()
    cur.execute(schema)
    conn.commit()
    cur.close()
    conn.close()
    print("Migrations complete (multi-tenant schema applied).")


if __name__ == "__main__":
    run_migrations()
