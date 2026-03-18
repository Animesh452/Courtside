"""
reminders.py — Reminder tool functions for the agent.

IMPORTANT: All timezone conversion happens HERE in Python.
The LLM is unreliable at timezone math. It passes either:
  - minutes_from_now (for relative times like "in 5 minutes")
  - local_datetime (for absolute times like "April 12 at 5pm")
Python converts everything to UTC for storage and to local time for display.
"""

import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from database import add_reminder, get_upcoming_reminders, delete_reminder


def _get_tz(tz_name: str) -> ZoneInfo:
    """Get a ZoneInfo object, falling back to UTC."""
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _to_local_str(utc_iso: str, tz_name: str) -> str:
    """Convert a UTC ISO datetime string to a friendly local time string."""
    tz = _get_tz(tz_name)
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        local_dt = dt.astimezone(tz)
        tz_abbr = local_dt.strftime("%Z")
        return local_dt.strftime(f"%I:%M %p {tz_abbr} on %A, %B %d, %Y").lstrip("0")
    except Exception:
        return utc_iso


def create_reminder(
    event: str,
    minutes_from_now: int = None,
    local_datetime: str = None,
    user_timezone: str = "UTC",
) -> str:
    """
    Create a new reminder. Python handles all time conversion.

    Args:
        event: What to remind about
        minutes_from_now: Minutes from now (for "in 5 minutes" style requests)
        local_datetime: Local datetime string "YYYY-MM-DD HH:MM" (for "April 12 at 5pm")
        user_timezone: User's timezone name (e.g. "America/Phoenix")
    """
    tz = _get_tz(user_timezone)
    now_utc = datetime.now(timezone.utc)

    # Option 1: Relative time — "in X minutes"
    if minutes_from_now is not None:
        try:
            minutes = int(minutes_from_now)
            if minutes <= 0:
                return json.dumps({
                    "success": False,
                    "error": "Minutes must be a positive number."
                })
            remind_at_utc = now_utc + timedelta(minutes=minutes)
        except (ValueError, TypeError):
            return json.dumps({
                "success": False,
                "error": f"Invalid minutes value: '{minutes_from_now}'."
            })

    # Option 2: Absolute local time — "2026-04-12 17:00"
    elif local_datetime is not None:
        try:
            # Parse the local datetime string
            local_dt = datetime.strptime(local_datetime.strip(), "%Y-%m-%d %H:%M")
            # Attach the user's timezone
            local_dt = local_dt.replace(tzinfo=tz)
            # Convert to UTC
            remind_at_utc = local_dt.astimezone(timezone.utc)

            if remind_at_utc <= now_utc:
                return json.dumps({
                    "success": False,
                    "error": "That time is in the past. Please set a future time."
                })
        except (ValueError, TypeError):
            return json.dumps({
                "success": False,
                "error": f"Invalid datetime format: '{local_datetime}'. Use 'YYYY-MM-DD HH:MM' format."
            })

    # Neither provided — error
    else:
        return json.dumps({
            "success": False,
            "error": "Please provide either minutes_from_now or local_datetime."
        })

    # Store in UTC
    remind_at_iso = remind_at_utc.isoformat()
    result = add_reminder(event, remind_at_iso)

    # Convert to local time for the confirmation
    local_time_str = _to_local_str(remind_at_iso, user_timezone)

    # Return plain text — the LLM will naturally echo this.
    # JSON responses get ignored by smaller models; plain text works reliably.
    return (
        f"DONE. Reminder #{result['id']} created.\n"
        f"Event: {event}\n"
        f"You will be reminded at: {local_time_str}\n"
        f"Tell the user: \"Got it! I've set a reminder for '{event}' at {local_time_str}.\""
    )


def list_reminders(user_timezone: str = "UTC") -> str:
    """List all upcoming (unsent) reminders with times in the user's timezone."""
    reminders = get_upcoming_reminders()

    if not reminders:
        return "You have no upcoming reminders."

    lines = [f"You have {len(reminders)} upcoming reminder(s):\n"]
    for r in reminders:
        local_time = _to_local_str(r["remind_at"], user_timezone)
        lines.append(f"  #{r['id']} — {r['event']} at {local_time}")

    return "\n".join(lines)


def remove_reminder(reminder_id: int) -> str:
    """Delete a reminder by ID."""
    deleted = delete_reminder(reminder_id)

    if deleted:
        return f"Reminder #{reminder_id} has been deleted."
    else:
        return f"No reminder found with ID #{reminder_id}."