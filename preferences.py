"""
preferences.py — Persistent user preference store.

Uses ChromaDB with persistent storage to remember what the user cares about:
- Which sports they follow
- Teams they ask about
- Topics they're interested in

This data persists across server restarts and helps personalize responses.
The agent checks preferences before responding to add relevant context.
"""

import chromadb
from datetime import datetime, timezone


# Persistent ChromaDB client — survives server restarts
_client = chromadb.PersistentClient(path="./chroma_preferences")


def _get_collection():
    """Get or create the preferences collection."""
    return _client.get_or_create_collection(name="user_preferences")


def save_preference(category: str, value: str, detail: str = "") -> str:
    """
    Save a user preference.
    
    Args:
        category: Type of preference — "sport", "team", "fighter", "league", etc.
        value: The actual preference — "UFC", "Lakers", "Ilia Topuria", etc.
        detail: Optional extra context
    
    Returns:
        Confirmation message
    """
    collection = _get_collection()
    doc_id = f"{category}_{value}".lower().replace(" ", "_")
    timestamp = datetime.now(timezone.utc).isoformat()

    document = f"User follows {category}: {value}. {detail}".strip()

    # Upsert — update if exists, create if not
    collection.upsert(
        ids=[doc_id],
        documents=[document],
        metadatas=[{
            "category": category,
            "value": value,
            "detail": detail,
            "updated_at": timestamp,
        }],
    )

    return f"Noted: you follow {value} ({category})."


def get_preferences(query: str = "", top_k: int = 5) -> list[dict]:
    """
    Get user preferences, optionally filtered by relevance to a query.
    
    Args:
        query: If provided, returns preferences most relevant to this query
        top_k: Max number of preferences to return
    
    Returns:
        List of preference dicts
    """
    collection = _get_collection()

    if collection.count() == 0:
        return []

    if query:
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
        )
        prefs = []
        for i, doc in enumerate(results.get("documents", [[]])[0]):
            metadata = results.get("metadatas", [[]])[0][i]
            prefs.append({
                "document": doc,
                "category": metadata.get("category", ""),
                "value": metadata.get("value", ""),
            })
        return prefs
    else:
        # Return all preferences
        results = collection.get()
        prefs = []
        for i, doc in enumerate(results.get("documents", [])):
            metadata = results.get("metadatas", [])[i]
            prefs.append({
                "document": doc,
                "category": metadata.get("category", ""),
                "value": metadata.get("value", ""),
            })
        return prefs


def get_preference_context(query: str) -> str:
    """
    Get a formatted preference context string to inject into the system prompt.
    Makes it explicit how to use preferences for personalization.
    """
    prefs = get_preferences(query, top_k=3)

    if not prefs:
        return ""

    lines = ["USER PREFERENCES (from past interactions):"]
    for p in prefs:
        lines.append(f"- {p['document']}")
    lines.append(
        "\nWhen the user asks a vague question like 'any upcoming events?' or 'what's happening?', "
        "use their preferences to decide which sport(s) to look up. "
        "For example, if they follow UFC, fetch the UFC schedule."
    )

    return "\n".join(lines)


def list_all_preferences() -> str:
    """Return a formatted list of all stored preferences."""
    prefs = get_preferences()

    if not prefs:
        return "No preferences saved yet. As we chat, I'll learn what sports and teams you follow."

    lines = [f"I know you follow these ({len(prefs)} total):\n"]
    for p in prefs:
        lines.append(f"  • {p['value']} ({p['category']})")

    return "\n".join(lines)


def clear_preferences() -> str:
    """Clear all stored preferences."""
    global _client
    _client.delete_collection("user_preferences")
    return "All preferences have been cleared."