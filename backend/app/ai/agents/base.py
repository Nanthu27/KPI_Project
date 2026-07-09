"""
Agent node infrastructure
--------------------------
Every LangGraph node in this project is a plain function:

    def some_agent(state: ConversationState) -> dict: ...

`@node(name)` wraps that function so every node gets, for free:
  - start/finish/duration timing pushed to state["node_trace"]     (Step 11)
  - up to MAX_RETRIES re-invocations if the wrapped tool call raises
    or returns a dict containing an "error" key                    (Step 7)
  - errors / missing_information bubbled into shared state instead
    of raising, so one failing agent never crashes the whole graph
"""
from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict

from ..graph.state import ConversationState

logger = logging.getLogger("cascade.graph")

MAX_RETRIES = 2


def _merge_log(state: ConversationState, entry: Dict[str, Any]) -> Dict[str, Any]:
    trace = list(state.get("node_trace") or [])
    trace.append(entry)
    return {"node_trace": trace}


def node(name: str) -> Callable:
    """Decorator that adds logging + bounded retry semantics to a node fn."""

    def decorator(fn: Callable[[ConversationState], Dict[str, Any]]):
        @wraps(fn)
        def wrapper(state: ConversationState) -> Dict[str, Any]:
            retries = dict(state.get("retries") or {})
            attempt = 0
            started = time.time()
            last_error: str | None = None
            result: Dict[str, Any] = {}

            while attempt <= MAX_RETRIES:
                try:
                    result = fn(state) or {}
                    tool_data = (result.get("tool_outputs") or {}).get(name, {})
                    if isinstance(tool_data, dict) and tool_data.get("error"):
                        raise RuntimeError(tool_data["error"])
                    break
                except Exception as exc:  # noqa: BLE001 - agents must never crash the graph
                    last_error = str(exc)
                    attempt += 1
                    if attempt <= MAX_RETRIES:
                        logger.warning("Node '%s' failed (attempt %d/%d): %s",
                                        name, attempt, MAX_RETRIES, last_error)
                    else:
                        logger.error("Node '%s' exhausted retries: %s", name, last_error)

            finished = time.time()
            retries[name] = attempt
            log_entry = {
                "node": name,
                "started_at": started,
                "finished_at": finished,
                "duration_ms": round((finished - started) * 1000, 2),
                "status": "error" if last_error else ("retried" if attempt else "ok"),
                "detail": last_error or "",
            }

            updates: Dict[str, Any] = dict(result)
            updates["retries"] = retries
            updates.update(_merge_log(state, log_entry))

            if last_error:
                errors = list(state.get("errors") or [])
                errors.append(f"{name}: {last_error}")
                updates["errors"] = errors
                missing = list(state.get("missing_information") or [])
                missing.append(name)
                updates["missing_information"] = missing

            return updates

        wrapper.__node_name__ = name
        return wrapper

    return decorator
