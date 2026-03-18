"""
agent.py — The agentic tool-calling loop.

Instead of hardcoded if/else routing, this module:
1. Defines tools with JSON schemas (so the LLM knows what's available)
2. Sends the user's message to the LLM with the tool definitions
3. If the LLM decides to call a tool, we execute it and return the result
4. The LLM then writes a natural response using the tool result

This is the same pattern used in production AI systems (OpenAI function calling,
Anthropic tool use, etc). Building it manually means you understand every step.
"""

import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from groq import Groq
from sports import (
    get_sports_data,
    get_schedule,
    get_scoreboard,
    get_cricket_data,
    format_schedule_for_llm,
    format_scoreboard_for_llm,
    format_cricket_for_llm,
    SUPPORTED_SPORTS,
)
from reminders import create_reminder, list_reminders, remove_reminder
from rag import on_demand_rag
from preferences import save_preference, list_all_preferences, get_preference_context

# Model to use for tool calling
# llama-3.1-8b-instant is more reliable for tool call formatting on Groq
# Switch to "llama-3.3-70b-versatile" for better reasoning if it works for you
MODEL = "llama-3.1-8b-instant"

# ──────────────────────────────────────────────
# Tool definitions (JSON schemas for the LLM)
# ──────────────────────────────────────────────
# These tell the LLM what tools exist, what they do, and what parameters they take.
# The LLM reads these descriptions and decides which tool to call based on the user's message.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_sports_schedule",
            "description": (
                "Get the upcoming schedule of events for a sport. Use this when the user "
                "asks about upcoming games, fights, races, fixtures, or schedules. "
                "Supported sports: UFC/MMA, F1, NFL, NBA, MLB, NHL, Premier League, "
                "La Liga, MLS, Serie A, Bundesliga."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": (
                            "The sport to look up. Use one of these exact keys: "
                            "ufc, mma, f1, nfl, nba, mlb, nhl, premier league, epl, "
                            "la liga, mls, serie a, bundesliga"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many upcoming events to return (default 10, max 50)",
                    },
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sports_scores",
            "description": (
                "Get current/recent scores and results for a sport. Use this when the user "
                "asks about live scores, recent results, who won, or what's happening now. "
                "Supported sports: UFC/MMA, F1, NFL, NBA, MLB, NHL, Premier League, "
                "La Liga, MLS, Serie A, Bundesliga."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sport": {
                        "type": "string",
                        "description": (
                            "The sport to look up. Use one of these exact keys: "
                            "ufc, mma, f1, nfl, nba, mlb, nhl, premier league, epl, "
                            "la liga, mls, serie a, bundesliga"
                        ),
                    },
                },
                "required": ["sport"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cricket_scores",
            "description": (
                "Get live and recent cricket match data. Use this for any cricket-related "
                "question — IPL, T20 World Cup, Test matches, ODIs, or any cricket league. "
                "This returns all currently active cricket matches across all leagues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": (
                            "Optional filter for a specific tournament. "
                            "Examples: 'ipl', 't20 world cup', 'test', 'odi'. "
                            "Leave empty to get all current cricket matches."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Set a reminder for a sports event. Use this when the user says things like "
                "'remind me about the UFC fight on Saturday', 'set a reminder for the NBA game', "
                "or 'don't let me forget the F1 race'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "Description of the event to remind about (e.g. 'UFC 327: Prochazka vs Ulberg')",
                    },
                    "minutes_from_now": {
                        "type": "integer",
                        "description": (
                            "How many minutes from NOW to send the reminder. "
                            "Use this for relative times: 'in 5 minutes' = 5, "
                            "'in an hour' = 60, 'in 2 hours' = 120. "
                            "If BOTH minutes_from_now and local_datetime are provided, "
                            "minutes_from_now takes priority."
                        ),
                    },
                    "local_datetime": {
                        "type": "string",
                        "description": (
                            "The date and time to send the reminder, in the USER'S LOCAL timezone. "
                            "Format: 'YYYY-MM-DD HH:MM' (24-hour). "
                            "Examples: '2026-04-12 17:00' for April 12 at 5pm local time, "
                            "'2026-03-21 14:30' for March 21 at 2:30pm local time. "
                            "Use this for absolute times like 'April 12 at 5pm', 'Saturday at noon'. "
                            "Do NOT convert to UTC — pass the time exactly as the user means it "
                            "in their local timezone."
                        ),
                    },
                },
                "required": ["event"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_reminders",
            "description": (
                "List all upcoming reminders the user has set. Use this when the user "
                "asks 'what reminders do I have', 'show my reminders', or 'any upcoming reminders'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": (
                "Delete a reminder by its ID. Use this when the user says "
                "'cancel reminder #3', 'delete that reminder', or 'remove reminder 5'. "
                "You need the reminder ID — if you don't have it, list reminders first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "integer",
                        "description": "The ID of the reminder to delete",
                    },
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deep_search",
            "description": (
                "Search for detailed information about a sports topic using Wikipedia. "
                "Use this when the user asks a deep question that needs more context than "
                "your general knowledge provides — like fighter history, career stats, "
                "matchup background, team history, coaching changes, or any topic where "
                "you want more detailed and accurate information. "
                "Examples: 'tell me about Ilia Topuria', 'history of the Lakers-Celtics rivalry', "
                "'what happened in the 2005 Champions League final'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — be specific. 'Ilia Topuria MMA career' is better than just 'Topuria'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_user_preference",
            "description": (
                "Save a user's sports preference when they mention following a sport, team, "
                "fighter, or league. Call this when the user says things like 'I follow UFC', "
                "'I'm a Lakers fan', 'I love F1', 'I watch Premier League'. "
                "Also call this when you notice patterns — if they keep asking about UFC, "
                "save that preference."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Type of preference: 'sport', 'team', 'fighter', 'league', or 'driver'",
                    },
                    "value": {
                        "type": "string",
                        "description": "The actual preference value, e.g. 'UFC', 'Lakers', 'Max Verstappen'",
                    },
                },
                "required": ["category", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_user_preferences",
            "description": (
                "List what the user follows and is interested in. Use this when they ask "
                "'what do you know about me', 'what sports do I follow', or 'my preferences'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# System prompt — built dynamically so it includes the user's current time
def _format_utc_offset(dt: datetime) -> str:
    """Format a datetime's UTC offset as a readable string like '-7 hours'."""
    offset = dt.utcoffset()
    if offset is None:
        return "+0 hours"
    total_seconds = int(offset.total_seconds())
    hours = total_seconds // 3600
    sign = "+" if hours >= 0 else ""
    return f"{sign}{hours} hours"


def build_system_prompt(user_tz_name: str = "UTC", user_message: str = "") -> str:
    """Build the system prompt with current time, timezone, and user preferences."""
    try:
        user_tz = ZoneInfo(user_tz_name)
    except Exception:
        user_tz = timezone.utc
        user_tz_name = "UTC"

    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(user_tz)
    tz_abbr = now_local.strftime('%Z')  # e.g. "MST", "EST", "PST"

    # Get relevant user preferences
    pref_context = get_preference_context(user_message) if user_message else ""
    pref_block = f"\n{pref_context}\n" if pref_context else ""

    return f"""You are Courtside, a personal AI sports assistant.
You help users with sports questions, schedules, scores, rules, and player info.
You are friendly, knowledgeable, and concise.
Keep responses conversational and to the point.

CURRENT TIME CONTEXT:
- The user's timezone is {user_tz_name} ({tz_abbr}).
- The user's current local time is {now_local.strftime('%A, %B %d, %Y at %I:%M %p')} {tz_abbr}.
- When displaying times to the user, ALWAYS use "{tz_abbr}" not "{user_tz_name}".
  Example: "5:00 PM {tz_abbr}" NOT "5:00 PM {user_tz_name}".
- Use this to resolve relative dates like "this Saturday" or "next Friday".
{pref_block}
AVAILABLE TOOLS:
- Upcoming events, schedules, or fixtures → use get_sports_schedule
- Current scores, results, or live games → use get_sports_scores  
- Any cricket question (IPL, T20, Tests, etc) → use get_cricket_scores
- User wants to be reminded about an event → use set_reminder
- User wants to see their reminders → use list_my_reminders
- User wants to cancel a reminder → use delete_reminder
- Deep question about a player, team, or event history → use deep_search
- User mentions they follow a sport/team/fighter → use save_user_preference
- User asks what you know about them → use list_user_preferences

WHEN TO USE deep_search:
- When the user asks about a specific person, team history, rivalry, or event you're unsure about
- When accuracy matters more than speed (player stats, career records, historical facts)
- When the user asks for specific data you don't have, like fight records, match history, 
  career stats, or recent results for a specific player — USE deep_search, don't say "I don't have access"
- If you just used deep_search for a person and the user asks a follow-up about the same person 
  (like "what about his last 5 fights"), search again with a more specific query
- Do NOT use deep_search for simple questions you can answer from general knowledge

REMINDER RULES:
- For relative times like "in 5 minutes", "in an hour" → pass minutes_from_now to set_reminder.
- For absolute times like "April 12 at 5pm", "Saturday at noon" → pass local_datetime 
  in "YYYY-MM-DD HH:MM" format using the user's LOCAL time. Do NOT convert to UTC.
- The tool response includes pre-formatted local times. Use those exactly as given.
- NEVER output raw JSON to the user. Always write a natural confirmation message.
- If the user asks for a reminder about a specific event (like "remind me about the Adesanya fight")
  but does NOT specify when to be reminded, you MUST ask them when they want the reminder.
  Do NOT set the reminder for the current time. Say something like:
  "When would you like to be reminded? I can remind you a day before, a few hours before, etc."

MULTI-ACTION REQUESTS:
- If the user asks for multiple reminders in one message, set them ONE AT A TIME.
- NEVER skip or ignore any part of the user's request.
- NEVER claim you deleted or removed something unless you actually called the delete tool.
- NEVER invent actions you didn't take.

PREFERENCE RULES:
- When a user says "I follow UFC" or "I'm a Lakers fan", save it with save_user_preference.
- Don't save preferences for every sport they ask about — only when they express fandom or interest.

CRITICAL RULES:
1. When you receive data from a tool, use ONLY that data for scores/events/schedules.
2. NEVER make up scores, events, fight cards, dates, or results.
3. NEVER invent or guess player stats, records, or career details you're unsure about.
4. If a tool returns no data or an error, tell the user clearly.
5. You CAN share general sports knowledge (rules, history, well-known facts) without tools.
   But clearly distinguish between live data and general knowledge.
6. NEVER output raw JSON, tool call arguments, or internal data structures to the user."""


# ──────────────────────────────────────────────
# Tool execution
# ──────────────────────────────────────────────

def execute_tool(tool_name: str, arguments: dict, user_timezone: str = "UTC") -> str:
    """
    Run a tool and return the result as a string.
    This is where tool calls from the LLM get translated into actual function calls.
    """
    if tool_name == "get_sports_schedule":
        sport = arguments.get("sport", "").lower().strip()
        limit = arguments.get("limit", 10)
        limit = min(max(limit, 1), 50)  # clamp between 1 and 50

        if sport not in SUPPORTED_SPORTS:
            return f"Sport '{sport}' is not supported. Supported: UFC, F1, NFL, NBA, MLB, NHL, Premier League, La Liga, MLS, Serie A, Bundesliga, Cricket."

        if SUPPORTED_SPORTS[sport]["sport"] == "cricket":
            data = get_cricket_data()
            return format_cricket_for_llm(data, sport)

        data = get_schedule(sport, limit=limit)
        return format_schedule_for_llm(data)

    elif tool_name == "get_sports_scores":
        sport = arguments.get("sport", "").lower().strip()

        if sport not in SUPPORTED_SPORTS:
            return f"Sport '{sport}' is not supported. Supported: UFC, F1, NFL, NBA, MLB, NHL, Premier League, La Liga, MLS, Serie A, Bundesliga, Cricket."

        if SUPPORTED_SPORTS[sport]["sport"] == "cricket":
            data = get_cricket_data()
            return format_cricket_for_llm(data, sport)

        data = get_scoreboard(sport)
        return format_scoreboard_for_llm(data)

    elif tool_name == "get_cricket_scores":
        data = get_cricket_data()
        filter_key = arguments.get("filter", "")
        return format_cricket_for_llm(data, filter_key or "cricket")

    elif tool_name == "set_reminder":
        event = arguments.get("event", "Unknown event")
        minutes_from_now = arguments.get("minutes_from_now")
        local_datetime = arguments.get("local_datetime")
        return create_reminder(
            event=event,
            minutes_from_now=minutes_from_now,
            local_datetime=local_datetime,
            user_timezone=user_timezone,
        )

    elif tool_name == "list_my_reminders":
        return list_reminders(user_timezone)

    elif tool_name == "delete_reminder":
        reminder_id = arguments.get("reminder_id", 0)
        return remove_reminder(reminder_id)

    elif tool_name == "deep_search":
        query = arguments.get("query", "")
        if not query:
            return "Please provide a search query."
        return on_demand_rag(query)

    elif tool_name == "save_user_preference":
        category = arguments.get("category", "sport")
        value = arguments.get("value", "")
        if not value:
            return "Please provide a preference value."
        return save_preference(category, value)

    elif tool_name == "list_user_preferences":
        return list_all_preferences()

    else:
        return f"Unknown tool: {tool_name}"


# ──────────────────────────────────────────────
# The agentic loop
# ──────────────────────────────────────────────

def _call_llm_with_tools(client, model, messages, system_prompt, tools, temperature=0.5):
    """Make an LLM call with tools, handling the Groq tool_use_failed error."""
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        tools=tools,
        tool_choice="auto",
        temperature=temperature,
        max_tokens=1024,
    )


def _call_llm(client, model, messages, system_prompt, temperature=0.7):
    """Make an LLM call without tools (for final responses)."""
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        temperature=temperature,
        max_tokens=1024,
    )


def run_agent(client: Groq, user_message: str, chat_history: list, user_timezone: str = "UTC") -> str:
    """
    The core agentic loop:
    1. Send the message + tools to the LLM
    2. If the LLM wants to call a tool, execute it
    3. Send the tool result back to the LLM
    4. Return the final response

    Includes retry logic: if the primary model fails on tool calling,
    retries with lower temperature, then falls back to the smaller model.
    """
    # Add the user message to history
    chat_history.append({"role": "user", "content": user_message})

    # Build system prompt fresh each call (includes current time + user's timezone)
    system_prompt = build_system_prompt(user_timezone, user_message)

    # Step 1: Send message to LLM with tool definitions
    # Try primary model, retry with lower temp, then fallback model
    response = None
    temps_to_try = [0.5, 0.2, 0.1]  # progressively more deterministic

    for temp in temps_to_try:
        try:
            response = _call_llm_with_tools(
                client, MODEL, chat_history, system_prompt, TOOLS, temp
            )
            break  # success — exit retry loop
        except Exception as e:
            error_str = str(e)
            if "tool_use_failed" in error_str:
                print(f"[Agent] Tool call failed at temp={temp}, retrying...")
                continue
            else:
                # Non-tool error — don't retry, just raise
                raise e

    if response is None:
        # All retries failed — respond without tools
        chat_history.append({"role": "assistant", "content": "I had trouble using my tools. Let me try to answer directly."})
        response = _call_llm(client, MODEL, chat_history, system_prompt)
        reply = response.choices[0].message.content
        chat_history.append({"role": "assistant", "content": reply})
        return reply

    assistant_message = response.choices[0].message

    # Step 2: Check if the LLM wants to call a tool
    if assistant_message.tool_calls:
        # Add the assistant's tool call message to history
        chat_history.append({
            "role": "assistant",
            "content": assistant_message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in assistant_message.tool_calls
            ],
        })

        # Step 3: Execute each tool call and collect results
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                arguments = {}

            # Run the tool
            tool_result = execute_tool(tool_name, arguments, user_timezone)

            # Add the tool result to history
            chat_history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

        # Step 4: Send the tool results back to the LLM for a final response
        final_response = _call_llm(
            client, MODEL, chat_history, system_prompt
        )

        reply = final_response.choices[0].message.content

    else:
        # No tool call — the LLM responded directly (general chat)
        reply = assistant_message.content

    # Add the final reply to history
    chat_history.append({"role": "assistant", "content": reply})

    return reply