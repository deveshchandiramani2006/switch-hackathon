import psycopg2
import psycopg2.extras
import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        os.getenv("DATABASE_URL", "postgresql://nexus:nexus_dev@localhost:5432/nexus"),
        cursor_factory=psycopg2.extras.RealDictCursor
    )


@contextmanager
def db_cursor():
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
