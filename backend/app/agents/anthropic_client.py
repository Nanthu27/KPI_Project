"""
Thin Anthropic client wrapper for the 3 narration-only agents that use
Anthropic per product decision (ROI Insight, Goal-Seeking, Decision
Advisor). Knowledge Agent and Excel Intelligence Agent stay on the
existing OpenRouter/OpenAI pipeline (app/rag/) since they reuse that
RAG stack as-is.

Every call here is a NARRATION call only — the input JSON it receives
already contains every number it's allowed to mention (see each agent's
system prompt). This client does not perform retries/streaming/back-off
beyond what the SDK does by default; add those if this goes to
production traffic.
"""
from __future__ import annotations

import os
import json
from typing import Optional

import anthropic

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 1024

_client: Optional[anthropic.Anthropic] = None


class AnthropicNotConfiguredError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY is missing — callers should surface a clean 503, not a stack trace."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if not ANTHROPIC_API_KEY:
        raise AnthropicNotConfiguredError(
            "ANTHROPIC_API_KEY is not set. Narration agents (ROI Insight, Goal-Seeking, "
            "Decision Advisor) cannot run without it. See .env.example."
        )
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def call_anthropic_json(system_prompt: str, user_payload: dict, max_tokens: int = MAX_TOKENS) -> dict:
    """
    Sends a system prompt + a structured JSON payload as the user turn,
    expects a JSON object back (per each agent's OUTPUT FORMAT contract),
    and parses it defensively (the model occasionally wraps JSON in
    markdown fences despite instructions not to).
    """
    client = _get_client()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(user_payload, default=str)}],
    )
    raw_text = "".join(block.text for block in response.content if hasattr(block, "text"))
    return _parse_json_response(raw_text)


def call_anthropic_text(system_prompt: str, user_message: str, max_tokens: int = MAX_TOKENS) -> str:
    """Plain-text variant for agents that don't need structured JSON back (currently unused, kept for completeness)."""
    client = _get_client()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if hasattr(block, "text"))


def _parse_json_response(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last-resort: find the first { ... last } span and try again.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        # Give callers a usable fallback rather than raising mid-request.
        return {"response_text": raw_text.strip(), "_parse_error": True}
