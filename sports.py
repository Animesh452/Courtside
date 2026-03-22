"""
sports.py — Fetches live sports data from the ESPN unofficial API.

Standard ESPN endpoint:
    https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard

Cricket ESPN endpoint (different pattern):
    https://site.api.espn.com/apis/personalized/v2/scoreboard/header?sport=cricket&region=in

No API key required for any endpoint.
"""

import re
import requests
from datetime import datetime, timezone

# ESPN base URL for standard sports
BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"

# ESPN cricket endpoint (uses a different pattern)
CRICKET_URL = "https://site.api.espn.com/apis/personalized/v2/scoreboard/header"

# Map of supported sports to their ESPN sport/league path
SUPPORTED_SPORTS = {
    # MMA
    "ufc": {"sport": "mma", "league": "ufc", "display": "UFC"},
    "mma": {"sport": "mma", "league": "ufc", "display": "UFC"},
    "pfl": {"sport": "mma", "league": "pfl", "display": "PFL"},
    "bellator": {"sport": "mma", "league": "bellator", "display": "Bellator"},
    # Motorsport
    "f1": {"sport": "racing", "league": "f1", "display": "Formula 1"},
    "formula 1": {"sport": "racing", "league": "f1", "display": "Formula 1"},
    # US sports
    "nfl": {"sport": "football", "league": "nfl", "display": "NFL"},
    "nba": {"sport": "basketball", "league": "nba", "display": "NBA"},
    "mlb": {"sport": "baseball", "league": "mlb", "display": "MLB"},
    "nhl": {"sport": "hockey", "league": "nhl", "display": "NHL"},
    # Tennis
    "tennis": {"sport": "tennis", "league": "atp", "display": "Tennis (ATP)"},
    "atp": {"sport": "tennis", "league": "atp", "display": "Tennis (ATP)"},
    "wta": {"sport": "tennis", "league": "wta", "display": "Tennis (WTA)"},
    # Soccer
    "premier league": {"sport": "soccer", "league": "eng.1", "display": "Premier League"},
    "epl": {"sport": "soccer", "league": "eng.1", "display": "Premier League"},
    "la liga": {"sport": "soccer", "league": "esp.1", "display": "La Liga"},
    "mls": {"sport": "soccer", "league": "usa.1", "display": "MLS"},
    "serie a": {"sport": "soccer", "league": "ita.1", "display": "Serie A"},
    "bundesliga": {"sport": "soccer", "league": "ger.1", "display": "Bundesliga"},
    "ligue 1": {"sport": "soccer", "league": "fra.1", "display": "Ligue 1"},
    "champions league": {"sport": "soccer", "league": "uefa.champions", "display": "Champions League"},
    "ucl": {"sport": "soccer", "league": "uefa.champions", "display": "Champions League"},
    "europa league": {"sport": "soccer", "league": "uefa.europa", "display": "Europa League"},
    "eredivisie": {"sport": "soccer", "league": "ned.1", "display": "Eredivisie"},
    "liga mx": {"sport": "soccer", "league": "mex.1", "display": "Liga MX"},
    # Cricket — handled separately via CRICKET_URL
    "cricket": {"sport": "cricket", "league": "cricket", "display": "Cricket"},
    "ipl": {"sport": "cricket", "league": "cricket", "display": "Cricket (IPL)"},
    "t20": {"sport": "cricket", "league": "cricket", "display": "Cricket (T20)"},
    "t20 world cup": {"sport": "cricket", "league": "cricket", "display": "Cricket (T20 World Cup)"},
}

# Keywords that suggest the user wants a schedule/upcoming events list
SCHEDULE_KEYWORDS = [
    "schedule", "upcoming", "next", "coming up", "calendar", "when is",
    "when are", "events", "fights", "races", "fixtures", "list",
]

# Keywords that suggest the user wants scores/results
SCORE_KEYWORDS = [
    "score", "result", "who won", "final", "live", "happening",
    "going on", "current", "today", "last night", "yesterday",
]


# ──────────────────────────────────────────────
# Standard sports (everything except cricket)
# ──────────────────────────────────────────────

def fetch_espn_data(sport_key: str) -> dict:
    """Fetch the full scoreboard response from ESPN for a standard sport."""
    config = SUPPORTED_SPORTS[sport_key.lower().strip()]
    url = f"{BASE_URL}/{config['sport']}/{config['league']}/scoreboard"
    headers = {"User-Agent": "Courtside/1.0 (Sports Assistant)"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        print(f"[Sports] ESPN fetch failed for {sport_key}: {e}")
        return {"success": False, "error": f"Failed to fetch data: {str(e)}"}

    return {"success": True, "data": data, "config": config}


def get_schedule(sport_key: str, limit: int = 20, user_tz_name: str = "UTC") -> dict:
    """Get upcoming events from the calendar field."""
    result = fetch_espn_data(sport_key)
    if not result["success"]:
        return result

    data = result["data"]
    config = result["config"]

    calendar = []
    leagues = data.get("leagues", [])
    if leagues:
        raw_calendar = leagues[0].get("calendar", [])
        sport_display = config["display"]

        for entry in raw_calendar:
            if isinstance(entry, dict):
                # Named event (UFC, F1, PFL style) — has label and startDate
                calendar.append({
                    "name": entry.get("label", "TBD"),
                    "date": _format_date(entry.get("startDate", ""), user_tz_name),
                    "raw_date": entry.get("startDate", ""),
                })
            elif isinstance(entry, str):
                # Date-only entry (soccer, tennis style) — use sport name as label
                calendar.append({
                    "name": f"{sport_display} Matchday",
                    "date": _format_date(entry, user_tz_name),
                    "raw_date": entry,
                })

    # Also check the events array for today's actual matches with names
    # These have real matchup info like "Arsenal vs Chelsea"
    today_events = data.get("events", [])
    if today_events and not any(isinstance(e, dict) and e.get("label") for e in (leagues[0].get("calendar", []) if leagues else [])):
        # Prepend today's named events at the top
        for event in today_events:
            name = event.get("name", event.get("shortName", ""))
            if name:
                calendar.insert(0, {
                    "name": name,
                    "date": _format_date(event.get("date", ""), user_tz_name),
                    "raw_date": event.get("date", ""),
                })

    # Filter to only future events
    now = datetime.now(timezone.utc)
    upcoming = []
    for event in calendar:
        try:
            event_dt = datetime.fromisoformat(
                event["raw_date"].replace("Z", "+00:00")
            )
            if event_dt > now:
                upcoming.append(event)
        except (ValueError, TypeError):
            upcoming.append(event)

    upcoming = upcoming[:limit]

    if not upcoming:
        return {
            "success": True, "sport": config["display"],
            "message": f"No upcoming {config['display']} events found in the schedule.",
            "events": [],
        }

    return {
        "success": True, "sport": config["display"],
        "event_count": len(upcoming), "total_scheduled": len(calendar),
        "events": upcoming,
    }


def get_scoreboard(sport_key: str, user_tz_name: str = "UTC") -> dict:
    """Get detailed event data for current/nearest events."""
    result = fetch_espn_data(sport_key)
    if not result["success"]:
        return result

    data = result["data"]
    config = result["config"]
    events = data.get("events", [])

    if not events:
        return {
            "success": True, "sport": config["display"],
            "message": f"No current {config['display']} events found right now.",
            "events": [],
        }

    parsed_events = []
    for event in events:
        parsed = {
            "name": event.get("name", "Unknown Event"),
            "short_name": event.get("shortName", ""),
            "date": _format_date(event.get("date", ""), user_tz_name),
            "status": _get_status(event),
            "venue": _get_venue(event),
            "competitors": _get_competitors(event),
        }
        parsed_events.append(parsed)

    return {
        "success": True, "sport": config["display"],
        "event_count": len(parsed_events), "events": parsed_events,
    }


# ──────────────────────────────────────────────
# Cricket (uses a different ESPN endpoint)
# ──────────────────────────────────────────────

def get_cricket_data() -> dict:
    """
    Fetch cricket scores from ESPN's personalized scoreboard header.
    This returns all currently active cricket series and their matches.
    """
    try:
        response = requests.get(
            CRICKET_URL,
            params={"sport": "cricket", "region": "in", "tz": "Asia/Calcutta"},
            headers={"User-Agent": "Courtside/1.0 (Sports Assistant)"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return {"success": False, "error": f"Failed to fetch cricket data: {str(e)}"}

    sports = data.get("sports", [])
    if not sports:
        return {"success": True, "sport": "Cricket", "message": "No cricket data found.", "events": []}

    cricket_sport = sports[0]
    leagues = cricket_sport.get("leagues", [])

    parsed_events = []
    for league in leagues:
        league_name = league.get("name", "Unknown League")
        events = league.get("events", [])

        for event in events:
            status_info = event.get("fullStatus", {})
            status_type = status_info.get("type", {})
            competitors = event.get("competitors", [])

            comp_list = []
            for comp in competitors:
                comp_list.append({
                    "name": comp.get("displayName", "Unknown"),
                    "score": comp.get("score", ""),
                    "winner": comp.get("winner", False),
                })

            parsed_events.append({
                "league": league_name,
                "name": event.get("name", "Unknown Match"),
                "description": event.get("description", ""),
                "location": event.get("location", ""),
                "date": _format_date(event.get("date", "")),
                "status": status_type.get("description", "Unknown"),
                "summary": status_info.get("longSummary", status_info.get("summary", "")),
                "competitors": comp_list,
            })

    if not parsed_events:
        return {"success": True, "sport": "Cricket", "message": "No current cricket matches found.", "events": []}

    return {
        "success": True, "sport": "Cricket",
        "event_count": len(parsed_events), "events": parsed_events,
    }


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _format_date(date_str: str, user_tz_name: str = "UTC") -> str:
    """Convert an ESPN ISO date to a friendly local time string."""
    if not date_str:
        return "Date TBD"
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

        # Convert to user's timezone
        try:
            user_tz = ZoneInfo(user_tz_name)
        except Exception:
            user_tz = timezone.utc
            user_tz_name = "UTC"

        local_dt = dt.astimezone(user_tz)
        tz_abbr = local_dt.strftime("%Z")
        return local_dt.strftime(f"%B %d, %Y at %I:%M %p {tz_abbr}").lstrip("0")
    except (ValueError, TypeError):
        return date_str


def _get_status(event: dict) -> str:
    try:
        return event["status"]["type"]["description"]
    except (KeyError, TypeError):
        return "Unknown"


def _get_venue(event: dict) -> str:
    try:
        competitions = event.get("competitions", [])
        if competitions:
            venue = competitions[0].get("venue", {})
            city = venue.get("address", {}).get("city", "")
            name = venue.get("fullName", venue.get("name", ""))
            if city:
                return f"{name}, {city}"
            return name
    except (KeyError, TypeError, IndexError):
        pass
    return "Venue TBD"


def _get_competitors(event: dict) -> list:
    competitors = []
    try:
        competitions = event.get("competitions", [])
        if competitions:
            for comp in competitions[0].get("competitors", []):
                team = comp.get("team", {})
                name = team.get("displayName") or team.get("name", "")
                if not name:
                    athlete = comp.get("athlete", {})
                    name = athlete.get("displayName", athlete.get("fullName", "Unknown"))
                competitors.append({
                    "name": name,
                    "score": comp.get("score", ""),
                    "winner": comp.get("winner", False),
                })
    except (KeyError, TypeError, IndexError):
        pass
    return competitors


# ──────────────────────────────────────────────
# Detection + routing
# ──────────────────────────────────────────────

def detect_sport(message: str) -> str | None:
    """Check if a user message mentions a supported sport."""
    message_lower = message.lower()
    for key in sorted(SUPPORTED_SPORTS.keys(), key=len, reverse=True):
        if key in message_lower:
            return key
    return None


def is_schedule_question(message: str) -> bool:
    message_lower = message.lower()
    return any(kw in message_lower for kw in SCHEDULE_KEYWORDS)


def is_score_question(message: str) -> bool:
    message_lower = message.lower()
    return any(kw in message_lower for kw in SCORE_KEYWORDS)


def _is_cricket(sport_key: str) -> bool:
    return SUPPORTED_SPORTS.get(sport_key, {}).get("sport") == "cricket"


def _extract_number(message: str, default: int = 20) -> int:
    """Extract a number from the user's message for use as a limit."""
    match = re.search(r'\b(\d{1,2})\b', message)
    if match:
        num = int(match.group(1))
        # Clamp to reasonable range
        return max(1, min(num, 50))
    return default


def get_sports_data(message: str, sport_key: str) -> str:
    """
    Main entry point. Routes to the right fetcher based on sport and question type.
    """
    # Cricket uses a completely different endpoint
    if _is_cricket(sport_key):
        data = get_cricket_data()
        return format_cricket_for_llm(data, sport_key)

    # Standard sports — decide between schedule and scores
    if is_schedule_question(message):
        limit = _extract_number(message, default=20)
        data = get_schedule(sport_key, limit=limit)
        return format_schedule_for_llm(data)
    elif is_score_question(message):
        data = get_scoreboard(sport_key)
        return format_scoreboard_for_llm(data)
    else:
        limit = _extract_number(message, default=10)
        schedule_data = get_schedule(sport_key, limit=limit)
        scoreboard_data = get_scoreboard(sport_key)
        schedule_text = format_schedule_for_llm(schedule_data)
        scoreboard_text = format_scoreboard_for_llm(scoreboard_data)
        return f"{scoreboard_text}\n\n{schedule_text}"


# ──────────────────────────────────────────────
# Formatters (text blocks for the LLM)
# ──────────────────────────────────────────────

def format_schedule_for_llm(data: dict) -> str:
    if not data["success"]:
        return f"Error fetching schedule: {data.get('error', 'Unknown error')}"
    if not data.get("events"):
        return data.get("message", "No upcoming events found.")

    lines = [f"=== {data['sport']} — Upcoming Schedule ===\n"]

    for i, event in enumerate(data["events"], 1):
        lines.append(f"{i}. {event['name']}")
        lines.append(f"   Date: {event['date']}")
        lines.append("")

    lines.append("DISPLAY INSTRUCTION: List ALL events above to the user with their names and dates. Do not summarize or skip any.")

    return "\n".join(lines)


def format_scoreboard_for_llm(data: dict) -> str:
    if not data["success"]:
        return f"Error fetching scores: {data.get('error', 'Unknown error')}"
    if not data.get("events"):
        return data.get("message", "No current events found.")

    lines = [f"=== {data['sport']} — Current/Recent Events ===\n"]

    for i, event in enumerate(data["events"], 1):
        lines.append(f"{i}. {event['name']}")
        lines.append(f"   Date: {event['date']}")
        lines.append(f"   Status: {event['status']}")
        lines.append(f"   Venue: {event['venue']}")
        if event["competitors"]:
            for comp in event["competitors"]:
                score_str = f" — {comp['score']}" if comp["score"] else ""
                winner_str = " ✓" if comp.get("winner") else ""
                lines.append(f"   • {comp['name']}{score_str}{winner_str}")
        lines.append("")

    lines.append("DISPLAY INSTRUCTION: List ALL events above to the user with full details. Do not summarize or skip any.")

    return "\n".join(lines)


def format_cricket_for_llm(data: dict, sport_key: str) -> str:
    if not data["success"]:
        return f"Error fetching cricket data: {data.get('error', 'Unknown error')}"
    if not data.get("events"):
        return data.get("message", "No cricket matches found.")

    # If user asked specifically about IPL or T20 World Cup, filter results
    filter_term = None
    if sport_key == "ipl":
        filter_term = "ipl"
    elif sport_key in ("t20", "t20 world cup"):
        filter_term = "t20 world cup"

    events = data["events"]
    if filter_term:
        filtered = [e for e in events if filter_term in e.get("league", "").lower()]
        if filtered:
            events = filtered

    lines = [f"=== Cricket — Current Matches ===\n"]

    for i, event in enumerate(events, 1):
        lines.append(f"{i}. [{event['league']}] {event['name']}")
        if event.get("description"):
            lines.append(f"   {event['description']}")
        if event.get("location"):
            lines.append(f"   Location: {event['location']}")
        lines.append(f"   Date: {event['date']}")
        lines.append(f"   Status: {event['status']}")
        if event.get("summary"):
            lines.append(f"   Summary: {event['summary']}")
        if event["competitors"]:
            for comp in event["competitors"]:
                score_str = f" — {comp['score']}" if comp["score"] else ""
                winner_str = " ✓" if comp.get("winner") else ""
                lines.append(f"   • {comp['name']}{score_str}{winner_str}")
        lines.append("")

    return "\n".join(lines)