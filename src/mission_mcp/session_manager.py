"""In-memory session store for mission profiles."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MissionSession:
    """Holds the state of a single mission analysis session."""

    session_id: str
    vehicle: dict[str, Any] = field(default_factory=dict)
    segments: list[dict[str, Any]] = field(default_factory=list)
    results: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    # Aviary-specific state
    backend: str = "nseg"  # "nseg" or "aviary"
    mission_config: dict[str, Any] = field(default_factory=dict)
    aircraft_params: dict[str, Any] = field(default_factory=dict)
    aviary_prob: Any = None
    aviary_converged: bool = False
    trajectory: dict[str, Any] | None = None


class SessionManager:
    """Thread-safe (GIL-sufficient) mission session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, MissionSession] = {}

    def create(self, **meta: Any) -> MissionSession:
        sid = str(uuid.uuid4())
        session = MissionSession(session_id=sid, meta=meta)
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> MissionSession:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"No mission session with id '{session_id}'") from None

    def close(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_ids(self) -> list[str]:
        return list(self._sessions.keys())


session_manager = SessionManager()
