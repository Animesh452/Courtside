# Courtside

**A personal AI sports assistant with agentic tool calling, on-demand RAG, and automated event reminders.**

Courtside replaces the manual process of googling sports schedules, missing match results, and not knowing enough about a new sport — with a single conversational interface. Ask about upcoming UFC fights, F1 race weekends, NBA scores, or any sport. Set reminders and get email notifications. Ask deep questions about players or teams and get answers backed by retrieved context.

**Live demo:** [your-render-url.onrender.com](https://your-render-url.onrender.com)

---

## Architecture

```
Browser (HTML/JS)
    │
    ▼
FastAPI Backend ──► Agentic Tool Loop (LLM decides which tool to call)
    │                    │
    │                    ├── Sports Data Tool (ESPN API → schedules, scores)
    │                    ├── Deep Search Tool (Wikipedia → chunk → embed → retrieve)
    │                    ├── Reminder Tool (SQLite → APScheduler → Gmail SMTP)
    │                    ├── Preference Tool (ChromaDB → personalization)
    │                    └── Direct Chat (LLM answers from knowledge)
    │
    ▼
APScheduler (background) ──► checks SQLite every 60s ──► sends email reminders
```

Every message flows through the agentic loop. The LLM reads tool definitions and autonomously decides whether to fetch live data, search for context, set a reminder, or just answer directly. No hardcoded `if/else` routing.

---

## Features

**Live Sports Data** — Real-time schedules and scores from the ESPN unofficial API. Supports UFC, F1, NFL, NBA, MLB, NHL, Premier League, La Liga, Serie A, Bundesliga, MLS, and cricket.

**Agentic Tool Calling** — The LLM reads JSON tool schemas and decides which tool to invoke based on user intent. Built manually (no LangChain) to demonstrate understanding of the pattern.

**On-Demand RAG** — When a deep question is asked (player history, matchup background), the system fetches Wikipedia content, chunks it, embeds it with ChromaDB's built-in model (all-MiniLM-L6-v2), retrieves the most relevant chunks, and uses them as LLM context. Data is discarded after each response — zero maintenance.

**Event Reminders** — Set reminders via natural language ("remind me about UFC 327 on April 12 at 5pm"). Stored in SQLite, checked every 60 seconds by APScheduler, delivered via Gmail SMTP. Timezone-aware — the browser sends the user's timezone automatically.

**Preference Store** — Persistent ChromaDB collection remembers which sports and teams you follow. Personalizes responses over time ("any upcoming events?" returns UFC schedule if it knows you follow UFC).

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| LLM | Groq API (Llama 3.1 8B) | Free tier, fast inference, OpenAI-compatible format |
| Backend | FastAPI (Python) | Lightweight, async-ready, easy to deploy |
| Frontend | Single HTML file | No build tools, no React — focus is on the backend |
| Database | SQLite | Zero setup, single file, trivially replaceable with PostgreSQL |
| Vector Store | ChromaDB | Built-in embeddings (runs locally), persistent + ephemeral modes |
| Scheduler | APScheduler | Python-native background jobs, no external dependencies |
| Notifications | Gmail SMTP | Free, reliable, configured with app password |
| Sports Data | ESPN Unofficial API | Free, no auth required, covers all major sports |
| Deployment | Render | Free tier, supports Python web apps |

---

## Setup

### Prerequisites

- Python 3.10+
- A Groq API key (free at [console.groq.com](https://console.groq.com))
- A Gmail account with an app password (for reminders)

### Install

```bash
git clone https://github.com/your-username/courtside.git
cd courtside
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key
GMAIL_ADDRESS=your.email@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
USER_TIMEZONE=America/Phoenix
```

`USER_TIMEZONE` is only used for email formatting. The chat UI detects timezone from the browser automatically.

### Run

```bash
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

---

## Project Structure

```
courtside/
├── main.py           # FastAPI app, routes, startup (DB init + scheduler)
├── agent.py          # Agentic tool-calling loop, tool definitions, system prompt
├── sports.py         # ESPN API wrapper — schedules, scores, cricket
├── rag.py            # On-demand RAG pipeline — fetch, chunk, embed, retrieve
├── reminders.py      # Reminder tool functions — create, list, delete
├── preferences.py    # Persistent preference store via ChromaDB
├── database.py       # SQLite setup and reminder CRUD
├── scheduler.py      # APScheduler background job + Gmail emailer
├── requirements.txt
├── .env              # API keys and config (not committed)
├── .gitignore
└── static/
    └── index.html    # Chat UI — single file, no build tools
```

---

## Key Design Decisions

These are the architectural decisions worth discussing in an interview.

### Why agentic tool calling instead of if/else routing?

Hardcoded routing like `if "schedule" in message` breaks as soon as language varies. The agentic approach lets the LLM understand intent naturally — you define tools with JSON schemas and descriptions, and the model picks which one to call. This is how production AI systems (OpenAI, Anthropic, etc.) handle tool use.

### Why build the tool-calling loop manually instead of using LangChain?

LangChain abstracts the loop, which means you can't explain what's happening. Building it manually — even though it's ~50 lines of Python — means every step is visible and explainable. In an interview, this signals understanding rather than framework dependency.

### Why on-demand RAG instead of a pre-scraped vector database?

Pre-scraping all sports data across all players, teams, and leagues isn't feasible — the data is enormous and goes stale constantly. On-demand RAG solves this cleanly: fetch at query time, embed temporarily, retrieve, answer, discard. No maintenance burden, but still demonstrates the full RAG pattern (fetch → chunk → embed → retrieve → answer).

### Why SQLite instead of PostgreSQL?

SQLite is a single file with zero setup. For a personal tool with one user, it's the right call. The entire database layer lives in one file (`database.py`) and is trivially replaceable with PostgreSQL — all that changes is the connection string and a few SQL dialect differences.

### Why ChromaDB for preferences but not for RAG?

Preferences need persistence (survive server restarts) → ChromaDB with `PersistentClient`. RAG data is ephemeral by design (fetched, used, discarded) → ChromaDB with `EphemeralClient`. Same library, two different modes, each chosen for the right reason.

### Why Groq over other LLM providers?

Groq's free tier is generous and extremely fast (LPU inference). The API is OpenAI-compatible, so switching to Claude, GPT-4, or any other provider is a one-line config change. Development speed matters more than model quality during iteration.

### Why a single HTML file for the frontend?

The goal of this project is to demonstrate AI engineering — agentic systems, RAG, tool calling — not frontend development. A single HTML file with vanilla JS gets a working chat interface without introducing React, npm, or build tooling complexity.

---

## Production Improvements

Things I'd change for a multi-user production deployment:

- **PostgreSQL instead of SQLite** — persistent storage that survives Render's ephemeral filesystem. Reminders and preferences would both live here.
- **User authentication** — each user gets their own reminders and preferences.
- **SendGrid/Resend instead of Gmail SMTP** — proper transactional email service with delivery guarantees.
- **Store timezone per reminder** — so reminder emails format correctly even if the user changes location.
- **Paid sports API** — ESPN's unofficial API is undocumented and can change without notice. SportsRadar or similar for production reliability.
- **Claude or GPT-4 for the LLM** — better reasoning, more reliable tool calling, higher quality responses.

---

## What I Learned

Building Courtside taught me more about AI engineering than any course or tutorial:

- **Agentic tool calling** is the pattern that separates chatbots from useful AI systems. The LLM deciding what to do — not hardcoded logic — is what makes it work.
- **Never let the LLM do math.** Timezone conversion, date calculation, anything numerical — compute it in Python and give the LLM pre-formatted text.
- **On-demand RAG** is more practical than maintaining a vector database for most use cases. Fetch, use, discard.
- **Smaller models need more hand-holding** in prompts. The 8b model requires explicit instructions and examples; vague guidance gets ignored.
- **The gap between "it works on localhost" and "it works deployed" is real** — ephemeral filesystems, environment variables, and CORS are all things you only learn by deploying.

---

## License

MIT