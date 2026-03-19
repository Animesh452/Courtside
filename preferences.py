"""
preferences.py — User preference store.

Now uses the same database as reminders (PostgreSQL on Render, SQLite locally).
ChromaDB is still used for on-demand RAG (ephemeral) but no longer for preferences.
This ensures preferences persist across Render redeploys.
"""

from database import add_preference, get_all_preferences


def save_preference(category: str, value: str, detail: str = "") -> str:
    """Save a user preference."""
    result = add_preference(category, value, detail)

    if result.get("exists"):
        return f"I already know you follow {value} ({category})."

    return f"Noted: you follow {value} ({category})."


def get_preference_context(query: str) -> str:
    """
    Get a formatted preference context string to inject into the system prompt.
    """
    prefs = get_all_preferences()

    if not prefs:
        return ""

    lines = ["USER PREFERENCES (from past interactions):"]
    for p in prefs:
        lines.append(f"- User follows {p['category']}: {p['value']}")
    lines.append(
        "\nWhen the user asks a vague question like 'any upcoming events?' or 'what's happening?', "
        "use their preferences to decide which sport(s) to look up. "
        "For example, if they follow UFC, fetch the UFC schedule."
    )

    return "\n".join(lines)


def list_all_preferences() -> str:
    """Return a formatted list of all stored preferences."""
    prefs = get_all_preferences()

    if not prefs:
        return "No preferences saved yet. As we chat, I'll learn what sports and teams you follow."

    lines = [f"I know you follow these ({len(prefs)} total):\n"]
    for p in prefs:
        lines.append(f"  • {p['value']} ({p['category']})")

    return "\n".join(lines)