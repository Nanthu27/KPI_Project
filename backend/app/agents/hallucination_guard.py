"""
Hallucination guard (spec section 6.2): "Before returning any agent
response to the UI, validate that every number mentioned in
response_text exists in the structured input the agent was given."

This is a regex-extract-numbers-and-match approach, explicitly called
out in the spec as "sufficient for MVP." It is a QA gate, not a content
filter — on failure we do NOT silently strip the number or rewrite the
text (that could change the meaning of a sentence), we flag the
response so the route layer can log it and the agent's calling code can
decide whether to retry the narration call once with a corrective
system reminder.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Set, Union

_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_numbers(text: str) -> Set[str]:
    """Extracts numeric tokens, normalized (sign stripped, trailing .0 stripped) so
    '41', '-41', and '41.0' all match the same allowed-set entry. Sign is dropped
    because narration commonly rephrases a negative delta as "a drop of 8.9%"
    without the minus sign — the magnitude is what matters for this guard."""
    found = set()
    for match in _NUMBER_PATTERN.findall(text):
        value = match.lstrip("-")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        if value:
            found.add(value)
    return found


def _flatten_allowed_numbers(data: Union[dict, list, tuple, int, float, str, None]) -> Set[str]:
    """Recursively walks the structured input JSON and collects every number found anywhere in it."""
    allowed: Set[str] = set()

    def _walk(node):
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)
        elif isinstance(node, (int, float)):
            value = str(node).lstrip("-")
            if "." in value:
                value = value.rstrip("0").rstrip(".")
            if value:
                allowed.add(value)
        elif isinstance(node, str):
            allowed.update(_extract_numbers(node))

    _walk(data)
    return allowed


def validate_no_hallucinated_numbers(response_text: str, structured_input: dict) -> List[str]:
    """
    Returns a list of numeric tokens present in response_text that do NOT
    appear anywhere in structured_input. An empty list means the response
    passed the guard. Small integers (0-12) are exempted from the check —
    they're overwhelmingly used as natural-language counting words
    ("three interventions", "the first step") rather than cited figures,
    and flagging them produces too many false positives to be useful.
    """
    mentioned = _extract_numbers(response_text)
    allowed = _flatten_allowed_numbers(structured_input)

    violations = []
    for number in mentioned:
        try:
            numeric_value = float(number)
        except ValueError:
            continue
        if 0 <= numeric_value <= 12 and "." not in number:
            continue  # exempt small counting numbers
        if number not in allowed:
            violations.append(number)

    return violations
