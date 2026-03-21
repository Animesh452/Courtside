import os
from dotenv import load_dotenv

# Load environment variables FIRST — before any module reads them
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from openai import OpenAI
from agent import run_agent
from database import init_db
from scheduler import start_scheduler

# Initialize the database (creates tables if they don't exist)
init_db()

# Start the background reminder scheduler
start_scheduler()

# Initialize the Gemini client via OpenAI-compatible API
client = OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

# Initialize the FastAPI app
app = FastAPI()

# Store conversation history in memory (resets when server restarts)
chat_history = []


# Define the shape of incoming chat messages
class ChatRequest(BaseModel):
    message: str
    timezone: str = "UTC"  # Browser sends this automatically


# POST /chat - receives a message, passes it to the agent, returns the reply
@app.post("/chat")
async def chat(request: ChatRequest):
    reply = run_agent(client, request.message, chat_history, request.timezone)
    return {"reply": reply}


# Serve the static folder (where index.html lives)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Health check endpoint for UptimeRobot and monitoring
@app.get("/health")
@app.head("/health")
async def health():
    return {"status": "ok"}


# GET / - serves the chat page
@app.get("/")
@app.head("/")
async def root():
    return FileResponse("static/index.html")