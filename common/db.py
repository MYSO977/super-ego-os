import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager

DB_HOST = os.getenv("SUPEREGO_DB_HOST", "192.168.0.18")
DB_PORT = int(os.getenv("SUPEREGO_DB_PORT", "5432"))
DB_NAME = os.getenv("SUPEREGO_DB_NAME", "superego")
DB_USER = os.getenv("SUPEREGO_DB_USER", "postgres")
DB_PASS = os.getenv("SUPEREGO_DB_PASS", "newpassword123")

def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS,
        cursor_factory=psycopg2.extras.RealDictCursor
    )

@contextmanager
def db_cursor():
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur, conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def insert_raw_event(source, category, title, content, url=None):
    with db_cursor() as (cur, conn):
        cur.execute("""
            INSERT INTO raw_events (source, category, title, content, url)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (source, category, title, content, url))
        return cur.fetchone()["id"]

def log_push(channel, message_type, payload, success=True):
    with db_cursor() as (cur, conn):
        cur.execute("""
            INSERT INTO push_log (channel, message_type, payload, success)
            VALUES (%s, %s, %s, %s)
        """, (channel, message_type, str(payload), success))
