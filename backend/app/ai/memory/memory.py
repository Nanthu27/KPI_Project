"""
Conversation Memory
--------------------
Lightweight, in-process memory store keyed by `session_id`, so the graph
can persist context ACROSS turns (Step 8): conversation history, last-seen
KPIs, business domain, selected interventions, and simulation history.

This is intentionally NOT a database table — it is a fast, ephemeral
cache that survives for the life of the backend process. If durability
across restarts is required later, swap `_STORE` for a Redis/DB-backed
implementation without changing the public API below.
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOCK = threading.RLock()  # reentrant: get() is called from within other locked methods
_STORE: Dict[str, "SessionMemory"] = {}

_MAX_HISTORY_TURNS = 20
_SESSION_TTL_SECONDS = 60 * 60 * 6  # 6 hours


@dataclass
class SessionMemory:
    session_id: str
    history: List[Dict[str, str]] = field(default_factory=list)
    last_kpis: List[Dict[str, Any]] = field(default_factory=list)
    business_domain: Optional[str] = None
    selected_interventions: List[Dict[str, Any]] = field(default_factory=list)
    simulation_history: List[Dict[str, Any]] = field(default_factory=list)
    excel_references: List[str] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "history": self.history[-_MAX_HISTORY_TURNS:],
            "last_kpis": self.last_kpis,
            "business_domain": self.business_domain,
            "selected_interventions": self.selected_interventions,
            "simulation_history": self.simulation_history[-10:],
            "excel_references": self.excel_references,
        }


class ConversationMemory:
    """Thread-safe accessor over the process-wide session store."""

    @staticmethod
    def get(session_id: str) -> SessionMemory:
        with _LOCK:
            _evict_expired()
            mem = _STORE.get(session_id)
            if mem is None:
                mem = SessionMemory(session_id=session_id)
                _STORE[session_id] = mem
            return mem

    @staticmethod
    def append_turn(session_id: str, role: str, content: str) -> None:
        with _LOCK:
            mem = ConversationMemory.get(session_id)
            mem.history.append({"role": role, "content": content})
            mem.history = mem.history[-_MAX_HISTORY_TURNS:]
            mem.updated_at = time.time()

    @staticmethod
    def update(session_id: str, **fields: Any) -> SessionMemory:
        with _LOCK:
            mem = ConversationMemory.get(session_id)
            for key, value in fields.items():
                if hasattr(mem, key):
                    setattr(mem, key, value)
            mem.updated_at = time.time()
            return mem

    @staticmethod
    def record_simulation(session_id: str, snapshot: Dict[str, Any]) -> None:
        with _LOCK:
            mem = ConversationMemory.get(session_id)
            mem.simulation_history.append({**snapshot, "at": time.time()})
            mem.simulation_history = mem.simulation_history[-10:]
            mem.updated_at = time.time()

    @staticmethod
    def clear(session_id: str) -> None:
        with _LOCK:
            _STORE.pop(session_id, None)


def _evict_expired() -> None:
    now = time.time()
    expired = [sid for sid, mem in _STORE.items() if now - mem.updated_at > _SESSION_TTL_SECONDS]
    for sid in expired:
        _STORE.pop(sid, None)
