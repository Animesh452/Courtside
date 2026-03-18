import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq
from agent import run_agent
from database import init_db
from scheduler import start_scheduler

# Load environment variables from .env file
load_dotenv()

# Initialize the database (creates tables if they don't exist)
init_db()

# Start the background reminder scheduler
start_scheduler()

# Initialize the Groq client with your API key
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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


# GET / - serves the chat page
@app.get("/")
async def root():
    return FileResponse("static/index.html")