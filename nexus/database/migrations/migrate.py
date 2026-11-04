import os
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def run_migrations():
    db_url = os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus")

    migrations_dir = os.path.dirname(__file__)
    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))

    conn = psycopg2.connect(db_url)
    cur  = conn.cursor()

    # Ensure migrations tracking table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename   VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()

    for sql_file in sql_files:
        filename = os.path.basename(sql_file)
        cur.execute("SELECT filename FROM schema_migrations WHERE filename=%s", (filename,))
        if cur.fetchone():
            print(f"  skipping {filename} (already applied)")
            continue

        print(f"  applying {filename}...")
        with open(sql_file) as f:
            cur.execute(f.read())
        cur.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s)",
            (filename,)
        )
        conn.commit()
        print(f"  ✓ {filename}")

    cur.close()
    conn.close()
    print("All migrations complete.")


if __name__ == "__main__":
    run_migrations()
