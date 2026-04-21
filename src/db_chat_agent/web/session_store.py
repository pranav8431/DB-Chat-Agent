from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Lock
from typing import Any

from sqlalchemy.engine import Engine

from ..agent import DatabaseChatAgent
from ..config import Settings
from ..db import make_engine


@dataclass
class SessionRecord:
    session_id: str
    db_uri: str
    engine: Engine
    agent: DatabaseChatAgent
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionStore:
    def __init__(self):
        self._lock = Lock()
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, db_uri: str, settings: Settings) -> SessionRecord:
        engine = make_engine(db_uri)
        agent = DatabaseChatAgent(engine, settings)
        session = SessionRecord(
            session_id=token_urlsafe(16),
            db_uri=db_uri,
            engine=engine,
            agent=agent,
        )
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> SessionRecord:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(session_id)
            session = self._sessions[session_id]
            session.updated_at = datetime.now(timezone.utc).isoformat()
            return session

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "session_id": s.session_id,
                    "db_uri": s.db_uri,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in self._sessions.values()
            ]

    def delete(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            session.engine.dispose()


STORE = SessionStore()
