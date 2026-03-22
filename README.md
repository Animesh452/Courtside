# Courtside

**A personal AI sports assistant with agentic tool calling, on-demand RAG, and automated event reminders — deployed on Render.**

Courtside replaces the manual process of googling sports schedules, missing match results, and not knowing enough about a new sport — with a single conversational interface. Ask about upcoming UFC fights, F1 race weekends, NBA scores, or any sport. Set reminders and get email notifications. Ask deep questions about players or teams and get answers backed by retrieved context.

**Live demo:** [courtside-1uqy.onrender.com](https://courtside-1uqy.onrender.com)

---

## Architecture

```
Browser (HTML/JS) — sends user timezone automatically
    │
    ▼
FastAPI Backend ──► Agentic Tool Loop (Gemini 2.5 Flash decides which tool to call)
    │                    │
    │                    ├── Sports Data Tool (ESPN API → schedules, scores, cricket)
    │                    ├── Deep Search Tool (Wikipedia → chunk → keyword score → retrieve)
    │                    ├── Reminder Tool (PostgreSQL → APScheduler → Resend email)
    │                    ├── Preference Tool (PostgreSQL → personalization)
    │                    └── Direct Chat (LLM answers from knowledge)
    │
    ▼
APScheduler (background) ──► checks PostgreSQL every 60s ──► sends email via Resend API
```

Every message flows through the agentic loop. The LLM reads tool definitions and autonomously decides whether to fetch live data, search for context, set a reminder, or just answer directly. No hardcoded `if/else` routing.

---

## Features

**Live Sports Data** — Real-time schedules and scores from the ESPN unofficial API. Supports UFC, MMA, PFL, Bellator, F1, NFL, NBA, MLB, NHL, ATP Tennis, WTA Tennis, Premier League, La Liga, Serie A, Bundesliga, Ligue 1, MLS, Champions League, Europa League, Eredivisie, Liga MX, and cricket (including IPL and T20 World Cup).

**Agentic Tool Calling** — The LLM reads JSON tool schemas and decides which tool to invoke based on user intent. Built manually (no LangChain) to demonstrate understanding of the pattern.

**On-Demand RAG** — When a deep question is asked (player history, matchup background, rules of a sport), the system fetches Wikipedia content, chunks it into passages, scores chunks by keyword relevance, and uses the best chunks as LLM context. Data is discarded after each response — zero maintenance, no embedding model required.

**Event Reminders** — Set reminders via natural language ("remind me about UFC 327 on April 12 at 5pm"). Stored in PostgreSQL, checked every 60 seconds by APScheduler, delivered via Resend email API. Timezone-aware — the browser sends the user's timezone automatically and each reminder stores the timezone it was created in.

**Preference Store** — PostgreSQL table remembers which sports and teams you follow. Personalizes responses over time ("any upcoming events?" returns UFC schedule if it knows you follow UFC). Persists across server restarts.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| LLM | Gemini 2.5 Flash (Google) | Free tier with 250 RPD / 250k TPM, OpenAI-compatible format, strong tool calling |
| Backend | FastAPI (Python) | Lightweight, async-ready, easy to deploy |
| Frontend | Single HTML file | No build tools, no React — focus is on the backend and AI architecture |
| Database | PostgreSQL (Render) / SQLite (local) | Auto-detected via `DATABASE_URL` — PostgreSQL for production persistence, SQLite for local dev |
| Scheduler | APScheduler | Python-native background jobs, no external dependencies |
| Notifications | Resend API | HTTP-based email delivery — Render free tier blocks SMTP ports, Resend uses HTTPS |
| RAG | Wikipedia + keyword scoring | On-demand fetch, chunk, score, retrieve — no embedding model needed, zero cold-start overhead |
| Sports Data | ESPN Unofficial API | Free, no auth required, covers all major sports |
| Deployment | Render (free tier) | Auto-deploy from GitHub, free PostgreSQL add-on, UptimeRobot keepalive |

**Evolution of the stack:** The project started with Groq (Llama 3.1 8B), SQLite, Gmail SMTP, and ChromaDB embeddings. Each was replaced as deployment constraints surfaced — Groq hit rate limits, SMTP was blocked on Render, ChromaDB downloaded an 80MB embedding model on every cold start. Each swap was a one-file change thanks to the modular architecture.

---

## Setup

### Prerequisites

- Python 3.10+
- A Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/apikey))
- A Resend API key (free at [resend.com](https://resend.com)) — for email reminders
- A Gmail address — destination for reminder emails

### Install

```bash
git clone https://github.com/Animesh452/Courtside.git
cd Courtside
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Configure

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_gemini_api_key
RESEND_API_KEY=your_resend_api_key
GMAIL_ADDRESS=your.email@gmail.com
USER_TIMEZONE=America/Phoenix
```

`USER_TIMEZONE` is only used for email formatting. The chat UI detects timezone from the browser automatically.

Locally, the app uses SQLite (no setup needed). On Render, set `DATABASE_URL` to a PostgreSQL connection string and the app switches automatically.

### Run

```bash
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

---

## Project Structure

```
courtside/
├── main.py           # FastAPI app, startup (DB init + scheduler), Gemini client config
├── agent.py          # Agentic tool-calling loop, tool definitions, system prompt
├── sports.py         # ESPN API wrapper — schedules, scores, cricket
├── rag.py            # On-demand RAG — Wikipedia fetch, chunking, keyword scoring
├── reminders.py      # Reminder tool functions — create, list, delete
├── preferences.py    # Preference store — PostgreSQL/SQLite backed
├── database.py       # Auto-detects PostgreSQL vs SQLite, handles both schemas
├── scheduler.py      # APScheduler background job + Resend email sender
├── requirements.txt
├── render.yaml       # Render deployment config
├── Procfile          # Process definition for deployment
├── .env              # API keys and config (not committed)
├── .gitignore
└── static/
    └── index.html    # Chat UI — single file, vanilla JS, no build tools
```

---

## Key Design Decisions

These are the architectural decisions worth discussing in an interview.

### Why agentic tool calling instead of if/else routing?

Hardcoded routing like `if "schedule" in message` breaks as soon as language varies. The agentic approach lets the LLM understand intent naturally — you define tools with JSON schemas and descriptions, and the model picks which one to call. This is how production AI systems (OpenAI, Anthropic, etc.) handle tool use.

### Why build the tool-calling loop manually instead of using LangChain?

LangChain abstracts the loop, which means you can't explain what's happening. Building it manually — even though it's ~50 lines of Python — means every step is visible and explainable. In an interview, this signals understanding rather than framework dependency.

### Why on-demand RAG instead of a pre-scraped vector database?

Pre-scraping all sports data across all players, teams, and leagues isn't feasible — the data is enormous and goes stale constantly. On-demand RAG solves this cleanly: fetch at query time, chunk, score, retrieve, answer, discard. No maintenance burden, but still demonstrates the full RAG pattern.

### Why keyword scoring instead of embedding-based retrieval?

The original implementation used ChromaDB with the all-MiniLM-L6-v2 embedding model. On Render's ephemeral filesystem, this model (~80MB) was re-downloaded on every cold start, adding 30+ seconds to the first request. Keyword scoring achieves comparable retrieval quality for this use case with zero model dependencies and instant startup. The architecture still demonstrates the RAG pattern — only the scoring function changed.

### Why PostgreSQL instead of SQLite for production?

SQLite is a single file with zero setup — perfect for local development. But Render's free tier has an ephemeral filesystem that resets on every deploy. Reminders set for next month would be wiped. PostgreSQL on Render's free tier gives persistent storage. The `database.py` module auto-detects which to use via the `DATABASE_URL` environment variable — same code, different backend.

### Why Resend instead of Gmail SMTP?

Gmail SMTP was the original plan. Render's free tier blocks outbound traffic on ports 465 and 587 (common SMTP ports) to prevent spam. Resend uses HTTPS (port 443), which is never blocked. The switch was a single-file change in `scheduler.py`.

### Why Gemini 2.5 Flash instead of Groq?

Groq's free tier (Llama 3.1 70B) has a 100,000 token-per-day limit, which was hit during testing within a few conversations. Gemini 2.5 Flash offers 250 requests/day and 250,000 tokens/minute on the free tier, and uses the same OpenAI-compatible API format — the switch was a one-line config change. The model also has stronger tool-calling reliability.

### Why a single HTML file for the frontend?

The goal of this project is to demonstrate AI engineering — agentic systems, RAG, tool calling — not frontend development. A single HTML file with vanilla JS gets a working chat interface without introducing React, npm, or build tooling complexity.

---

## Deployment Notes

The app is deployed on Render's free tier. A few things to know:

- **Cold starts** — Free tier spins down after 15 minutes of inactivity. UptimeRobot pings the `/health` endpoint every 5 minutes to keep it alive.
- **PostgreSQL** — Render's free PostgreSQL add-on provides persistent storage for reminders and preferences.
- **Auto-deploy** — Every push to `main` triggers a redeploy automatically.
- **Environment variables** — `GEMINI_API_KEY`, `RESEND_API_KEY`, `GMAIL_ADDRESS`, `USER_TIMEZONE`, and `DATABASE_URL` are all set in Render's dashboard.

---

## Future Improvements

- **Soccer/Tennis fixture APIs** — ESPN's calendar for soccer and tennis leagues only returns matchday dates, not actual fixtures (e.g., "Premier League Matchday" instead of "Arsenal vs Chelsea"). Integrating football-data.org (free tier, 12 leagues) and a tennis API would provide proper fixture data.
- **User authentication** — Each user gets their own reminders and preferences.
- **Chat history persistence** — Currently resets on server restart. Would need a `chat_history` table in PostgreSQL.
- **Multi-user support** — OAuth, per-user database rows, session management.
- **Paid sports APIs** — ESPN's unofficial API is undocumented and can change without notice. SportsRadar or similar for production reliability.

---

## What I Learned

Building Courtside taught me more about AI engineering than any course or tutorial:

- **Agentic tool calling** is the pattern that separates chatbots from useful AI systems. The LLM deciding what to do — not hardcoded logic — is what makes it work.
- **Never let the LLM do math.** Timezone conversion, date calculation, anything numerical — compute it in Python and give the LLM pre-formatted text.
- **On-demand RAG** is more practical than maintaining a vector database for most use cases. Fetch, use, discard.
- **The gap between "it works on localhost" and "it works deployed" is real.** Ephemeral filesystems wiped my database. SMTP ports were blocked. An 80MB model re-downloaded on every cold start. Each problem required rethinking the architecture — not just the code.
- **Every production constraint led to a better design.** Switching from ChromaDB to keyword scoring eliminated a dependency. Moving from SMTP to Resend made email delivery more reliable. PostgreSQL over SQLite made reminders actually persistent. The deployed version is architecturally stronger than the original design.

---

## License

MIT