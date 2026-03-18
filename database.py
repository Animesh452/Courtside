"""
database.py — SQLite database for Courtside.

Stores reminders in a single file (courtside.db).
No setup required — SQLite creates the file automatically on first run.

Schema:
    reminders:
        id          INTEGER PRIMARY KEY
        event       TEXT        — what the reminder is about
        remind_at   TEXT        — ISO datetime of when to send the reminder
        created_at  TEXT        — ISO datetime of when the reminder was created
        sent        INTEGER     — 0 = not sent, 1 = sent
"""

import sqlite3
from datetime import datetime, timezone

DB_PATH = "courtside.db"


def get_connection():
    """Get a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # access columns by name
    return conn


def init_db():
    """Create the reminders table if it doesn't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event       TEXT NOT NULL,
            remind_at   TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            sent        INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def add_reminder(event: str, remind_at: str) -> dict:
    """
    Add a new reminder to the database.
    
    Args:
        event: Description of what to remind about (e.g. "UFC 327: Prochazka vs Ulberg")
        remind_at: ISO format datetime string of when to send the reminder
    
    Returns:
        dict with the created reminder details
    """
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO reminders (event, remind_at, created_at, sent) VALUES (?, ?, ?, 0)",
        (event, remind_at, created_at),
    )
    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": reminder_id,
        "event": event,
        "remind_at": remind_at,
        "created_at": created_at,
        "sent": False,
    }


def get_pending_reminders() -> list:
    """Get all reminders that are due and haven't been sent yet."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reminders WHERE sent = 0 AND remind_at <= ?",
        (now,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_reminder_sent(reminder_id: int):
    """Mark a reminder as sent so it doesn't fire again."""
    conn = get_connection()
    conn.execute(
        "UPDATE reminders SET sent = 1 WHERE id = ?",
        (reminder_id,),
    )
    conn.commit()
    conn.close()


def get_all_reminders() -> list:
    """Get all reminders (for listing to the user)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reminders ORDER BY remind_at ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_upcoming_reminders() -> list:
    """Get only future, unsent reminders."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reminders WHERE sent = 0 AND remind_at > ? ORDER BY remind_at ASC",
        (now,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder by ID. Returns True if a row was deleted."""
    conn = get_connection()
    cursor = conn.execute(
        "DELETE FROM reminders WHERE id = ?",
        (reminder_id,),
    )
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted