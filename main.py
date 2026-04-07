import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Database helpers (raw sqlite3, no ORM)
# ---------------------------------------------------------------------------
DB_PATH = Path(__file__).parent / "explanations.db"


def init_db():
    """Create the explanations table if it doesn't exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS explanations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            explanation TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """Yield a connection wrapped in a context manager with auto-commit/close."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="ELI5 AI Explainer")


@app.on_event("startup")
def on_startup():
    init_db()


# Serve static files and the SPA entry point
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ExplainRequest(BaseModel):
    term: str


class ExplainResponse(BaseModel):
    term: str
    explanation: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "Ты добрый учитель. Объясни термин коротко и понятно для 5-летнего ребенка, "
    "обязательно используй простую бытовую аналогию. Максимум 3-4 предложения."
)


@app.post("/api/explain", response_model=ExplainResponse)
async def explain(req: ExplainRequest):
    term = req.term.strip()

    # 1. Ask LLM
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": term},
        ],
        temperature=0.7,
        max_tokens=300,
    )
    explanation = response.choices[0].message.content.strip()

    # 2. Save to SQLite
    with get_db() as conn:
        conn.execute(
            "INSERT INTO explanations (term, explanation) VALUES (?, ?)",
            (term, explanation),
        )

    return {"term": term, "explanation": explanation}


@app.get("/api/history")
async def history():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, term, explanation FROM explanations ORDER BY id DESC"
        ).fetchall()

    return [{"id": r["id"], "term": r["term"], "explanation": r["explanation"]} for r in rows]
