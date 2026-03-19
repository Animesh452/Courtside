"""
database.py — Database layer for Courtside.

Auto-detects which database to use:
    - If DATABASE_URL env var exists → PostgreSQL (for Render deployment)
    - Otherwise → SQLite (for local development)

Stores both reminders and preferences in the same database.
All functions use parameterized queries to prevent SQL injection.
"""

import os
import sqlite3
from datetime import datetime, timezone

# ──────────────────────────────────────────────
# Connection helpers
# ──────────────────────────────────────────────

def _get_database_url():
    """Get DATABASE_URL lazily so dotenv has time to load."""
    return os.getenv("DATABASE_URL")


def _is_postgres() -> bool:
    return _get_database_url() is not None


def get_connection():
    """Get a database connection (PostgreSQL or SQLite)."""
    if _is_postgres():
        import psycopg2
        url = _get_database_url().replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(url)
        conn.autocommit = False
        return conn
    else:
        conn = sqlite3.connect("courtside.db")
        conn.row_factory = sqlite3.Row
        return conn


def _dict_rows(cursor, rows) -> list:
    """Convert rows to list of dicts (works for both SQLite and PostgreSQL)."""
    if _is_postgres():
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    else:
        return [dict(row) for row in rows]


def _placeholder() -> str:
    """Return the correct placeholder for the database type."""
    return "%s" if _is_postgres() else "?"


# ──────────────────────────────────────────────
# Schema initialization
# ──────────────────────────────────────────────

def init_db():
    """Create tables if they don't exist."""
    p = _placeholder()
    conn = get_connection()
    cur = conn.cursor()

    # Use TEXT for SQLite, VARCHAR for PostgreSQL (TEXT works for both actually)
    if _is_postgres():
        serial = "SERIAL PRIMARY KEY"
        int_default = "INTEGER DEFAULT 0"
    else:
        serial = "INTEGER PRIMARY KEY AUTOINCREMENT"
        int_default = "INTEGER DEFAULT 0"

    # Reminders table
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS reminders (
            id              {serial},
            event           TEXT NOT NULL,
            remind_at       TEXT NOT NULL,
            user_timezone   TEXT DEFAULT 'UTC',
            created_at      TEXT NOT NULL,
            sent            {int_default}
        )
    """)

    # Preferences table (replaces ChromaDB for persistence)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS preferences (
            id              {serial},
            category        TEXT NOT NULL,
            value           TEXT NOT NULL,
            detail          TEXT DEFAULT '',
            created_at      TEXT NOT NULL
        )
    """)

    conn.commit()

    # SQLite migration — add user_timezone if missing
    if not _is_postgres():
        try:
            cur.execute("SELECT user_timezone FROM reminders LIMIT 1")
        except sqlite3.OperationalError:
            cur.execute("ALTER TABLE reminders ADD COLUMN user_timezone TEXT DEFAULT 'UTC'")
            conn.commit()
            print("[Database] Migrated: added user_timezone column.")

    cur.close()
    conn.close()
    db_type = "PostgreSQL" if _is_postgres() else "SQLite"
    print(f"[Database] Initialized ({db_type}).")


# ──────────────────────────────────────────────
# Reminders CRUD
# ──────────────────────────────────────────────

def add_reminder(event: str, remind_at: str, user_timezone: str = "UTC") -> dict:
    """Add a new reminder."""
    p = _placeholder()
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()

    if _is_postgres():
        cur.execute(
            f"INSERT INTO reminders (event, remind_at, user_timezone, created_at, sent) "
            f"VALUES ({p}, {p}, {p}, {p}, 0) RETURNING id",
            (event, remind_at, user_timezone, created_at),
        )
        reminder_id = cur.fetchone()[0]
    else:
        cur.execute(
            f"INSERT INTO reminders (event, remind_at, user_timezone, created_at, sent) "
            f"VALUES ({p}, {p}, {p}, {p}, 0)",
            (event, remind_at, user_timezone, created_at),
        )
        reminder_id = cur.lastrowid

    conn.commit()
    cur.close()
    conn.close()

    return {
        "id": reminder_id,
        "event": event,
        "remind_at": remind_at,
        "user_timezone": user_timezone,
        "created_at": created_at,
        "sent": False,
    }


def get_pending_reminders() -> list:
    """Get all reminders that are due and haven't been sent yet."""
    p = _placeholder()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM reminders WHERE sent = 0 AND remind_at <= {p}",
        (now,),
    )
    rows = cur.fetchall()
    result = _dict_rows(cur, rows)
    cur.close()
    conn.close()
    return result


def mark_reminder_sent(reminder_id: int):
    """Mark a reminder as sent."""
    p = _placeholder()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"UPDATE reminders SET sent = 1 WHERE id = {p}", (reminder_id,))
    conn.commit()
    cur.close()
    conn.close()


def get_upcoming_reminders() -> list:
    """Get only future, unsent reminders."""
    p = _placeholder()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM reminders WHERE sent = 0 AND remind_at > {p} ORDER BY remind_at ASC",
        (now,),
    )
    rows = cur.fetchall()
    result = _dict_rows(cur, rows)
    cur.close()
    conn.close()
    return result


def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder by ID."""
    p = _placeholder()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM reminders WHERE id = {p}", (reminder_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted


# ──────────────────────────────────────────────
# Preferences CRUD
# ──────────────────────────────────────────────

def add_preference(category: str, value: str, detail: str = "") -> dict:
    """Add or update a user preference."""
    p = _placeholder()
    conn = get_connection()
    cur = conn.cursor()

    # Check if this preference already exists
    cur.execute(
        f"SELECT id FROM preferences WHERE category = {p} AND value = {p}",
        (category, value),
    )
    existing = cur.fetchone()

    if existing:
        # Already exists — no need to duplicate
        cur.close()
        conn.close()
        return {"id": existing[0], "category": category, "value": value, "exists": True}

    created_at = datetime.now(timezone.utc).isoformat()

    if _is_postgres():
        cur.execute(
            f"INSERT INTO preferences (category, value, detail, created_at) "
            f"VALUES ({p}, {p}, {p}, {p}) RETURNING id",
            (category, value, detail, created_at),
        )
        pref_id = cur.fetchone()[0]
    else:
        cur.execute(
            f"INSERT INTO preferences (category, value, detail, created_at) "
            f"VALUES ({p}, {p}, {p}, {p})",
            (category, value, detail, created_at),
        )
        pref_id = cur.lastrowid

    conn.commit()
    cur.close()
    conn.close()

    return {"id": pref_id, "category": category, "value": value, "exists": False}


def get_all_preferences() -> list:
    """Get all stored preferences."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM preferences ORDER BY created_at ASC")
    rows = cur.fetchall()
    result = _dict_rows(cur, rows)
    cur.close()
    conn.close()
    return result


def delete_preference(pref_id: int) -> bool:
    """Delete a preference by ID."""
    p = _placeholder()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM preferences WHERE id = {p}", (pref_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    cur.close()
    conn.close()
    return deleted