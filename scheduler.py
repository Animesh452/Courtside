"""
scheduler.py — Background reminder checker + email sender.

Uses APScheduler to run a job every 60 seconds that:
1. Queries SQLite for reminders that are due (remind_at <= now, sent = 0)
2. Sends an email for each one via Gmail SMTP
3. Marks each reminder as sent

This runs independently of the chat flow — it doesn't need the user
to be active in the browser for reminders to fire.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_pending_reminders, mark_reminder_sent


def _format_reminder_time(utc_iso: str) -> str:
    """Format a UTC time for the email, using USER_TIMEZONE from .env as fallback."""
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
    Send an email via Gmail SMTP.
    Requires GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env.
    """
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        print("[Scheduler] Gmail credentials not set — skipping email.")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = gmail_address
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(gmail_address, gmail_password)
            server.send_message(msg)

        print(f"[Scheduler] Email sent: {subject}")
        return True

    except Exception as e:
        print(f"[Scheduler] Failed to send email: {e}")
        return False


def check_reminders():
    """
    Check for due reminders and send email notifications.
    This function runs on a schedule (every 60 seconds).
    Wrapped in try/except so a failure never blocks the scheduler.
    """
    try:
        pending = get_pending_reminders()

        if not pending:
            return

        gmail_address = os.getenv("GMAIL_ADDRESS")

        for reminder in pending:
            local_time = _format_reminder_time(reminder['remind_at'])
            subject = f"Courtside Reminder: {reminder['event']}"
            body = (
                f"Hey! This is your Courtside reminder.\n\n"
                f"Event: {reminder['event']}\n"
                f"Time: {local_time}\n\n"
                f"Enjoy the action!"
            )

            success = send_email(gmail_address, subject, body)

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
    - max_instances=1: only one check runs at a time
    - coalesce=True: if multiple runs were missed, only run once
    - misfire_grace_time=120: allow jobs that are up to 2 min late to still run
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