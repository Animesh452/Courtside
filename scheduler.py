"""
scheduler.py — Background reminder checker + email sender.

Uses Resend API (HTTPS) instead of SMTP to send emails.
SMTP is blocked on Render's free tier; Resend uses port 443 which is always open.

Resend free tier: 3,000 emails/month, send from onboarding@resend.dev
"""

import os
import resend
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_pending_reminders, mark_reminder_sent


def _format_reminder_time(utc_iso: str) -> str:
    """Format a UTC time for the email, using USER_TIMEZONE from .env."""
    tz_name = os.getenv("USER_TIMEZONE", "America/Phoenix")
    try:
        tz = ZoneInfo(tz_name)
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
        local_dt = dt.astimezone(tz)
        tz_abbr = local_dt.strftime("%Z")
        return local_dt.strftime(f"%I:%M %p {tz_abbr} on %A, %B %d, %Y").lstrip("0")
    except Exception:
        return utc_iso


def send_email(to_address: str, subject: str, body: str) -> bool:
    """
    Send an email via Resend API (HTTPS, no SMTP needed).
    Requires RESEND_API_KEY in .env.
    """
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        print("[Scheduler] RESEND_API_KEY not set — skipping email.")
        return False

    try:
        resend.api_key = api_key

        params: resend.Emails.SendParams = {
            "from": "Courtside <onboarding@resend.dev>",
            "to": [to_address],
            "subject": subject,
            "text": body,
        }

        result = resend.Emails.send(params)
        print(f"[Scheduler] Email sent via Resend: {subject} (id: {result.get('id', 'unknown')})")
        return True

    except Exception as e:
        print(f"[Scheduler] Failed to send email via Resend: {e}")
        return False


def check_reminders():
    """
    Check for due reminders and send email notifications.
    Wrapped in try/except so a failure never blocks the scheduler.
    """
    try:
        pending = get_pending_reminders()

        if not pending:
            return

        to_address = os.getenv("GMAIL_ADDRESS")
        if not to_address:
            print("[Scheduler] GMAIL_ADDRESS not set — skipping email.")
            return

        for reminder in pending:
            local_time = _format_reminder_time(reminder['remind_at'])
            subject = f"Courtside Reminder: {reminder['event']}"
            body = (
                f"Hey! This is your Courtside reminder.\n\n"
                f"Event: {reminder['event']}\n"
                f"Time: {local_time}\n\n"
                f"Enjoy the action!"
            )

            success = send_email(to_address, subject, body)

            if success:
                mark_reminder_sent(reminder["id"])
                print(f"[Scheduler] Reminder #{reminder['id']} sent and marked.")
            else:
                print(f"[Scheduler] Reminder #{reminder['id']} — email failed, will retry next cycle.")

    except Exception as e:
        print(f"[Scheduler] Error in check_reminders: {e}")


def start_scheduler():
    """
    Start the background scheduler.
    Runs check_reminders() every 60 seconds.
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_reminders,
        "interval",
        seconds=60,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )
    scheduler.start()
    print("[Scheduler] Background reminder checker started (checking every 60s).")
    return scheduler