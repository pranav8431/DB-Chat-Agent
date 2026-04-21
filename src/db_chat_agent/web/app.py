from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import Settings
from ..db import inspect_schema
from .session_store import STORE


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"


app = FastAPI(title="Gemma DB Intelligence", version="1.0.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectRequest(BaseModel):
    db_uri: str = Field(..., min_length=3)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class SessionResponse(BaseModel):
    session_id: str
    db_uri: str
    created_at: str
    updated_at: str


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_FILE.read_text(encoding="utf-8"))


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/sessions", response_model=SessionResponse)
def create_session(payload: ConnectRequest) -> SessionResponse:
    settings = Settings()
    session = None
    try:
        session = STORE.create(payload.db_uri, settings)
        # Force eager schema inspection to surface bad credentials/DB errors here.
        inspect_schema(session.engine)
        return SessionResponse(
            session_id=session.session_id,
            db_uri=session.db_uri,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
    except Exception as exc:
        if session is not None:
            STORE.delete(session.session_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sessions")
def list_sessions() -> dict[str, Any]:
    return {"sessions": STORE.list()}


@app.get("/api/sessions/{session_id}/schema")
def get_schema(session_id: str) -> dict[str, Any]:
    try:
        session = STORE.get(session_id)
        return session.agent.get_analysis()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/chat")
def chat(session_id: str, payload: ChatRequest) -> dict[str, Any]:
    try:
        session = STORE.get(session_id)
        result = session.agent.ask(payload.question)
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sessions/{session_id}/analyze")
def analyze(session_id: str) -> dict[str, Any]:
    try:
        session = STORE.get(session_id)
        return session.agent.get_analysis()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, str]:
    STORE.delete(session_id)
    return {"status": "deleted"}
