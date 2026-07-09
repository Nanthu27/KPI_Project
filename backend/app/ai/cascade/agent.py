"""
Cascade AI Agent — Dynamic Version
-------------------------------------
ALL metric names, intervention names, and follow-up questions are derived
from LIVE page data and DB state. Nothing is hardcoded to Finance / DSO / RPA.

Key rules:
  1. Intent detection uses keywords only (no extra LLM call).
  2. Goal/trace parameter extraction reads real names from pageContext first.
  3. Follow-up questions are built from real metric names in the tool result.
  4. SYSTEM_PROMPT instructs the LLM to only use names that exist in the data.
"""
import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional, List, Dict, Any
from sqlalchemy.orm import Session

from .schemas import IntentType, CascadeChatRequest
from .prompts import (
    SYSTEM_PROMPT,
    format_insight_prompt,
    format_goal_prompt,
    format_knowledge_prompt,
    format_trace_prompt,
    format_advisor_prompt,
    format_whatif_prompt,
    format_page_context,
)
from ..tools.kpi_tools import (
    insight_tool,
    goal_tool,
    knowledge_tool,
    excel_trace_tool,
    decision_advisor_tool,
    whatif_tool,
)
from ..evidence.grounding import (
    collect_allowed_numbers,
    find_ungrounded_numbers,
    compute_confidence,
    evidence_list,
    evidence_footer,
)

logger = logging.getLogger(__name__)


# ── Intent Detection ─────────────────────────────────────────────────────────

INTENT_PATTERNS = {
    IntentType.INSIGHT: [
        r"\bwhy\b", r"\bwhat happened\b", r"\bchanged\b", r"\bimproved\b",
        r"\bdeclined\b", r"\bexplain.*result", r"\bwhy.*kpi\b",
        r"\binsight\b", r"\bcause\b", r"\breason\b", r"\bwhat caused\b",
        # "how can I improve X?", "what drives X?" — open-ended improvement
        # questions about a specific metric belong to the Insight agent
        # (live driver analysis), not Advisor (global strategy ranking).
        r"\bhow\s+(can|do|to)\b.{0,40}\bimprove\b",
        r"\bwhat\s+drives\b",
    ],
    IntentType.GOAL: [
        r"\bhow.*reach\b", r"\bhow.*achieve\b", r"\bhow.*reduce\b", r"\bhow.*improve\b",
        r"\bwhat.*set.*to\b", r"\btarget\b.*\d", r"\bbelow\s+\d", r"\babove\s+\d",
        r"\bgoal\b", r"\bget.*to\s+\d", r"\bneed.*to.*reach\b",
        r"\b(reach|achieve|hit)\b.*\bis\b\s*\d", r"\b(reduce|decrease|lower)\b.*\bis\b\s*\d",
    ],
    IntentType.TRACE: [
        r"\bformula\b", r"\btrace\b", r"\bpath\b", r"\bhierarchy\b",
        r"\bhow.*calculated\b", r"\bimpact factor\b", r"\bcascade\b",
        r"\bcalculate\b", r"\bcalculation\b", r"\bcomputed\b", r"\bcompute\b",
        r"\bflow\b", r"\bwhich.*drives\b", r"\bwhat.*drives\b",
    ],
    IntentType.ADVISOR: [
        r"\brecommend\b", r"\bbest.*strategy\b", r"\btop.*intervention\b",
        r"\badvise\b", r"\bsuggest.*plan\b", r"\bwhat should\b",
        r"\boptimal\b", r"\bwhich.*intervention\b", r"\bwhat.*combination\b",
        r"\bstrategy\b", r"\bwhich.*best\b",
    ],
    IntentType.KNOWLEDGE: [
        r"\bwhat is\b", r"\bwhat are\b", r"\bdefine\b", r"\bexplain\b",
        r"\bmeaning\b", r"\bmean\b", r"\bkpi\b", r"\bmetric\b",
    ],
}


def detect_intent(
    message: str,
    override: Optional[IntentType] = None,
    page_context=None,
) -> IntentType:
    """
    Resolve the intent for a user message.

    Order of precedence:
      1. Explicit UI override (chip click) - always wins.
      2. Advisor "apply" trigger phrases - deterministic, must never be
         reclassified by anything downstream.
      3. LLM-based classification (semantic, handles natural/incomplete/
         informal phrasing, uses live page context to disambiguate).
      4. Regex keyword fallback - ONLY used if the LLM call fails (e.g.
         rate-limited, network down, no API key). This keeps the system
         degrading gracefully instead of hard-failing, but the regex path
         is no longer the primary classifier - see _detect_intent_regex.
    """
    if override and override != IntentType.UNKNOWN:
        return override

    # Apply-mode trigger phrases ("apply it", "apply the top recommendation
    # to my sliders", "set the sliders", ...) are deterministic UI actions,
    # not open-ended questions. Checking this first guarantees these phrases
    # always continue the advisor flow regardless of how the classifier
    # (LLM or regex) would otherwise score them.
    if _is_advisor_apply_intent(message):
        return IntentType.ADVISOR

    # Deterministic pre-check for hypothetical forward-simulation questions
    # ("if I set X to 55 ... what is Revenue Growth?") — must come before
    # the goal-seeking check since both can mention numbers and "what", but
    # this class states VALUES and asks for a RESULT, while goal-seeking
    # states a RESULT and asks which values to change.
    if _is_whatif_intent(message):
        return IntentType.WHATIF

    # Deterministic pre-check for goal-seeking phrasing that mentions a
    # number/percent AND asks which intervention(s) to change. This class of
    # question ("the growth is 5%, what interventions do I change?") is easy
    # for a human to read as goal-seeking but doesn't contain any of the
    # obvious keywords ("target", "reach", "increase to") the classifier
    # prompt leans on, and it contains "what are" which reads superficially
    # like a Knowledge-style definition question. Catching it here removes
    # the dependency on the LLM getting every such phrasing right.
    if _is_goal_seeking_intent(message):
        return IntentType.GOAL

    # Broader net for plain target-stating phrasing that isn't specifically
    # "which intervention should I change" but is still unmistakably a goal
    # ("reach revenue growth is 85", "reduce revenue growth is 10%"). See
    # _is_goal_target_intent's docstring for why this doesn't just rely on
    # the LLM classifier below to get these right.
    if _is_goal_target_intent(message):
        return IntentType.GOAL

    try:
        llm_intent = _detect_intent_llm(message, page_context)
        if llm_intent is not None:
            return llm_intent
    except Exception as e:
        logger.warning(f"LLM intent classification failed, falling back to regex: {e}")

    return _detect_intent_regex(message)


_WHATIF_QUESTION_RE = r"\bwhat\s+(?:is|are|would|will|happens?\s+to)\b"
_WHATIF_SETTING_RE = (
    r"\b(set|sets|setting|increase[d]?|change[d]?|adjust(?:ed)?|move[d]?)\b.*"
    r"\b(to|at)\s*[\d.]+"
)
_WHATIF_ORDINAL_RE = r"\bfirst\s+(\d+|one|two|three|four|five)\b.*\b(option|intervention|slider)"


def _is_whatif_intent(message: str) -> bool:
    """True for hypothetical forward-simulation questions: the user states
    (or implies) specific intervention values and asks what a KPI/Business
    Outcome would become — as opposed to `_is_goal_seeking_intent` (asks
    WHICH interventions to change to hit a target) or a Knowledge question
    (asks for a definition). This class of question has nowhere correct to
    go without it: `insight_tool` only reads the currently SAVED state
    (not a hypothetical), and `knowledge_tool` has no live-calculation
    capability at all — so before this existed, a message like "what is
    BO?" immediately after describing hypothetical values fell through to
    the Knowledge Agent and correctly failed to find a definition for an
    undocumented abbreviation, instead of running the simulation the user
    was actually asking for.
    """
    m = (message or "").lower()
    if not re.search(_WHATIF_QUESTION_RE, m):
        return False
    if re.search(_WHATIF_SETTING_RE, m) or re.search(_WHATIF_ORDINAL_RE, m):
        return True
    # Bare "Name - N%, Name2 - N%, ..." listing with NO setting verb at all
    # ("TP Simulation- 11% QA Automation-11% ... now what is revenue
    # growth?") used to require "set"/"increase"/"change" etc. to be
    # recognized, so a plain list of stated values fell through entirely.
    # Two or more name/value pairs immediately followed by a "what is/are"
    # question is unambiguously this class of question regardless of verb.
    return len(re.findall(_WHATIF_NAME_VALUE_RE, message, re.I)) >= 2


_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

_WHATIF_NAME_VALUE_RE = r"([A-Za-z][A-Za-z0-9 /&]{1,40}?)\s*(?:to|at|=|:|-)\s*([\d.]+)\s*%?"


def _extract_prior_recommended_interventions(history) -> List[str]:
    """Scan recent assistant messages for a previously offered strategy
    like "...setting TP Gamification to 100%, Interaction Analytics to
    100%, QA Automation to 50%, and TP Simulation to 25%." and return the
    intervention names in the order they were listed. Used to resolve a
    pronoun-style follow-up ("the first 3 options") to real names instead
    of guessing which interventions the user means.
    """
    if not history:
        return []
    for msg in reversed(history):
        role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
        if role != "assistant" or not content:
            continue
        m = re.search(r"setting\s+(.+?)(?:\.|$)", content, re.I)
        if not m:
            continue
        parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", m.group(1))
        names = []
        for p in parts:
            name = re.sub(r"\s*to\s+[\d.]+\s*%?\s*$", "", p).strip().strip("*")
            if name:
                names.append(name)
        if names:
            return names
    return []


def _resolve_whatif_overrides(message: str, request: CascadeChatRequest):
    """
    Resolve hypothetical intervention values from the message to REAL
    intervention names, never a guess:

      1. Explicit "NAME to VALUE" pairs matched against real names from
         live page_context.
      2. An ordinal back-reference ("the first 3 options/interventions")
         plus a bare list of numbers — resolved against the intervention
         names the assistant itself listed in its immediately preceding
         message (see `_extract_prior_recommended_interventions`).

    Returns (overrides: Dict[str, float], unresolved_count: int).
    unresolved_count > 0 with an empty `overrides` means the reference
    could not be confidently resolved — callers must ask a clarifying
    question rather than guess which interventions were meant.
    """
    names = _real_metric_names_from_context(request.page_context)
    real_iv_names = names["ivs"] or []

    overrides: Dict[str, float] = {}
    for m in re.finditer(_WHATIF_NAME_VALUE_RE, message, re.I):
        candidate = m.group(1).strip()
        value = float(m.group(2))
        match = next(
            (n for n in real_iv_names
             if n.lower() == candidate.lower()
             or n.lower() in candidate.lower()
             or candidate.lower() in n.lower()),
            None,
        )
        if match:
            overrides[match] = value

    if overrides:
        return overrides, 0

    bare_numbers = [float(x) for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", message)]
    ordinal_match = re.search(_WHATIF_ORDINAL_RE, message, re.I)
    generic_ref = re.search(r"\b(these|those|the)\s+intervention", message, re.I)
    if bare_numbers and (ordinal_match or generic_ref):
        n = len(bare_numbers)
        if ordinal_match and ordinal_match.group(1) in _WORD_NUMBERS:
            n = _WORD_NUMBERS[ordinal_match.group(1)]
            bare_numbers = bare_numbers[:n]
        prior_names = _extract_prior_recommended_interventions(request.history)
        chosen_names = prior_names[:n]
        if len(chosen_names) == n and n > 0:
            return dict(zip(chosen_names, bare_numbers)), 0
        return {}, n

    return {}, 0


_GOAL_SEEKING_PATTERNS = [
    r"\b(which|what)\b.*\b(intervention|slider)s?\b.*\b(change|set|adjust|modify)\b",
    r"\b(intervention|slider)s?\b.*\b(which|what)\b.*\b(change|set|adjust|modify)\b",
    r"\bwhat\s+value\b.*\b(intervention|slider)s?\b",
    r"\b(intervention|slider)s?\b.*\bshould\s+i\s+(change|set|adjust|modify)\b",
]


def _is_goal_seeking_intent(message: str) -> bool:
    """True if the message asks which intervention(s)/slider(s) to change
    AND references a concrete target number/percent — the hallmark of a
    goal-seeking question, even when phrased without words like "target" or
    "reach" that the LLM classifier's prompt is anchored on."""
    m = (message or "").lower()
    has_number = bool(re.search(r"\d", m))
    if not has_number:
        return False
    return any(re.search(p, m) for p in _GOAL_SEEKING_PATTERNS)


# Broader than _GOAL_SEEKING_PATTERNS: fires on plain target-stating
# phrasing ("reach revenue growth is 85", "reduce revenue growth is 10%",
# "decrease the revenue growth 5", "lower revenue growth by 5")
# even without an explicit "which intervention should I change" clause and
# without the word "target"/"goal" the plain keyword table (and the LLM
# classifier's few-shot examples) leaned on. This exists because relying on
# the LLM call to get every such phrasing right means a transient API
# failure — or just unusual/non-native phrasing — silently degrades all the
# way down to _detect_intent_regex, whose own GOAL patterns are just as
# narrow and defaults to KNOWLEDGE when nothing matches. A deterministic
# catch here means this whole class of question works even with the LLM
# classifier fully unavailable.
_GOAL_TARGET_PATTERNS = [
    r"\b(reach|achieve|hit)\b.{0,30}?\bis\b\s*[\d.]+",       # "reach X is 85"
    r"\b(reach|achieve|hit)\b\s*[\d.]+\s*%?",                # "achieve 85%", "reach 90"
    r"\b(reduce|decrease|lower|drop)\b.{0,30}?\bis\b\s*[\d.]+",  # "reduce X is 10%"
    r"\b(reduce|decrease|lower|drop|increase|raise|boost)\b.{0,30}?\bto\s*[\d.]+",
    r"\bshould\s+be\b\s*[\d.]+", r"\bbecomes?\b\s*[\d.]+",
    # "decrease/reduce/lower X 5" or "decrease/reduce/lower X by 5"
    # — a bare number immediately follows the metric name, no connector needed.
    # This is the "decrease the revenue growth 5?" case: the user states a
    # delta amount without saying "to" or "by", which neither the LLM
    # classifier examples nor the verb_with_by_re in _extract_goal_params
    # (which requires the number to appear after the metric, not right after
    # the verb) handled reliably.
    r"\b(decrease|reduce|lower|drop|cut)\w*\b.{0,40}?\b[\d.]+",
    r"\b(increase|raise|boost|grow(?!th))\w*\b.{0,40}?\b[\d.]+",
    # "X by N" — "revenue growth by 5", "improve NPS by 10"
    r"\bby\s+[\d.]+\b",
]


def _is_goal_target_intent(message: str) -> bool:
    m = (message or "").lower()
    if not re.search(r"\d", m):
        return False
    return any(re.search(p, m) for p in _GOAL_TARGET_PATTERNS)


def _detect_intent_regex(message: str) -> IntentType:
    """Deterministic keyword fallback. Used only when the LLM classifier is
    unavailable. Deliberately no longer the primary path, because plain
    keyword matching rejects any natural-language phrasing that doesn't
    contain one of a fixed set of trigger words (e.g. "Which metrics are
    improving?", "Undo the last recommendation") and used to silently dump
    all of those into the Knowledge Agent."""
    msg_lower = message.lower()
    scores = {intent: 0 for intent in INTENT_PATTERNS}
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, msg_lower):
                scores[intent] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else IntentType.KNOWLEDGE


_INTENT_CLASSIFIER_SYSTEM_PROMPT = """You classify a user's message into exactly ONE category for a KPI simulation platform. Respond with ONLY the category word, nothing else - no punctuation, no explanation.

Categories:
- insight: asking WHY a KPI/metric changed, what happened, summarizing changes, which KPI changed most/least, comparing before/after, or any live-state fact-finding question (e.g. "what are my active interventions", "which metrics are improving", "show only the KPIs that changed") since answering needs live simulation data, not a document definition. Also includes open-ended "how can I improve X?" questions about a SPECIFIC metric — these need live driver analysis, not a global strategy ranking.
- goal: asking to REACH/ACHIEVE/REDUCE/INCREASE a metric to a SPECIFIC NUMERIC target value, what slider values are needed for a target, "minimum change needed", "optimize while keeping X below Y", "what's the highest achievable value". A concrete number must be stated or clearly implied.
- whatif: the user STATES specific intervention/slider values (e.g. "TP Simulation to 55%, QA Automation to 75%") and asks what a KPI/Business Outcome would become as a RESULT of those values. The direction is opposite of "goal": here the user already knows the inputs and wants the computed output, not "which inputs do I need". Also use this for a bare list of "Name - N%" pairs followed by "what is X now?" even with no verb like "set"/"increase" at all.
- trace: asking to see the FORMULA, dependency chain, calculation path, or "which KPIs affect / are affected by" another metric, or how something is computed.
- advisor: asking for a RECOMMENDATION or RANKING across MULTIPLE strategies/interventions, comparing named strategies, best strategy overall, which intervention to change first when no specific metric target is given, applying a strategy to sliders, undoing/resetting an applied strategy. Use this only when the user wants a strategy comparison or ranking — NOT for "how can I improve specific metric X?".
- knowledge: asking for a DEFINITION or business/domain meaning of a term, or documentation, where the answer would come from a written document rather than the live simulation.

Do not be misled by surface phrasing like "what is"/"what are" into picking knowledge — check what the user actually wants. A message describing a KPI's current or desired value and asking which intervention(s) to change is goal-seeking, not a definition request, even when worded clumsily or without words like "target"/"reach". A message that instead STATES intervention values and asks what the resulting KPI value would be is whatif, not knowledge, even though it also contains "what is".

Examples:
"If I have decreased the revenue, the growth is 5%. What are the interventions I will change the value of?" -> goal
"reach revenue growth is 85" -> goal
"reduce revenue growth is 10%" -> goal
"decrease the revenue growth 5" -> goal
"decrease revenue growth by 5" -> goal
"lower revenue growth 5" -> goal
"reduce revenue growth 5?" -> goal
"increase revenue growth by 10" -> goal
"Reduce the revenue growth by 5?" -> goal
"reduce 5% in revenue growth" -> goal
"increase 5% in revenue growth" -> goal
"How to achieve 85% revenue growth?" -> goal
"achieve 90 NPS" -> goal
"TP Simulation- 11% QA Automation-11% TP Gamification-11% now what is revenue growth?" -> whatif
"If I set TP Simulation to 55%, what is Revenue Growth?" -> whatif
"What are my active interventions?" -> insight
"What is TP Simulation?" -> knowledge
"Which KPIs affect Revenue Growth?" -> trace
"What should I do to improve things?" -> advisor
"How do I get Revenue Growth even higher?" -> advisor
"How can I improve Revenue Growth?" -> insight
"How can I improve Cash Conversion Cycle?" -> insight
"How to optimize NPS?" -> insight
"What's the best strategy to improve CSAT?" -> advisor
"What's the best overall strategy?" -> advisor
"Recommend the best intervention strategy" -> advisor
"Which intervention should I prioritize?" -> advisor
"What's driving the change in Cash Conversion Cycle?" -> insight
"Why did NPS change?" -> insight

Respond with exactly one word: insight, goal, whatif, trace, advisor, or knowledge."""


def _detect_intent_llm(message: str, page_context=None) -> Optional[IntentType]:
    """
    Single fast LLM call that semantically classifies the message instead
    of matching fixed keyword patterns. This is what lets the agent handle
    natural, incomplete, or informally-phrased questions ("Which metrics
    are getting worse?", "Show only the KPIs that changed") instead of
    requiring the user to phrase things the way a regex expects.

    This is a one-word classification, not generation, so it stays cheap
    and low-latency relative to the main answer-generation call that
    follows it.
    """
    from ..config import get_ai_config
    cfg = get_ai_config()
    if not cfg.gemini_api_key:
        return None

    context_hint = ""
    if page_context:
        names = _real_metric_names_from_context(page_context)
        visible = ", ".join([*names["bos"][:3], *names["l1s"][:3], *names["l2s"][:3]])
        if visible:
            context_hint = f"\n\nMetrics visible on the current page: {visible}"

    cache_key = (message.strip().lower(), context_hint)
    cached = _INTENT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    _, client = _get_gemini_client()
    msgs = [
        {"role": "system", "content": _INTENT_CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user", "content": message + context_hint},
    ]
    resp = client.complete(msgs, max_tokens=5, temperature=0.0)
    raw = resp["choices"][0]["message"]["content"].strip().lower()
    raw = re.sub(r"[^a-z]", "", raw)

    mapping = {
        "insight": IntentType.INSIGHT,
        "goal": IntentType.GOAL,
        "whatif": IntentType.WHATIF,
        "trace": IntentType.TRACE,
        "advisor": IntentType.ADVISOR,
        "knowledge": IntentType.KNOWLEDGE,
    }
    result = mapping.get(raw)
    if result is not None:
        # Simple bounded cache — avoids unbounded growth over a long-running
        # server process while still saving a round-trip on repeated/retried
        # messages, which are common in a chat UI.
        if len(_INTENT_CACHE) > 500:
            _INTENT_CACHE.clear()
        _INTENT_CACHE[cache_key] = result
    return result


_INTENT_CACHE: dict = {}


_ADVISOR_APPLY_PATTERNS = [
    # Loose match: "apply" anywhere in the message followed eventually by
    # one of these words — NOT "apply" immediately adjacent to the word.
    # The original tight pattern (`apply\s+(it|this|...)`) never matched
    # "Apply the top recommendation to my sliders" (the panel's own button
    # text!) because of the "the top" in between, so clicking that button
    # silently fell through to the Knowledge intent instead of applying
    # anything.
    r"\bapply\b.*\b(it|this|recommendation|strateg\w*|sliders?)\b",
    r"\buse\s+this\s+strateg\w*\b",
    r"\bset\s+the\s+sliders?\b",
    r"\bgive\s+me\s+the\s+(exact\s+)?intervention\s+values?\b",
    r"\bwhat\s+values?\s+should\s+i\s+apply\b",
    r"\blist\s+the\s+exact\s+intervention\s+values?\b",
]


def _is_advisor_apply_intent(message: str) -> bool:
    """Detect the Advisor's Mode 2 (Apply) trigger phrases. See prompts.py
    format_advisor_prompt for the two-mode contract this feeds."""
    m = (message or "").lower()
    return any(re.search(p, m) for p in _ADVISOR_APPLY_PATTERNS)


# Open-ended improvement questions: "How can I improve X?", "optimize NPS",
# "what's the best way to increase Revenue Growth?" — no numeric target stated.
def _get_scope(request: CascadeChatRequest):
    """
    Resolve the (vertical, lob) scope for this request.

    Priority: explicit top-level request fields (what the schema declares)
    → page_context.filters (what the frontend actually sends today).

    This is the single choke point that feeds every tool call below. Before
    this existed, tools queried the database with no vertical/LOB filter at
    all, so responses could silently include another vertical's active
    sliders, KPI changes, or recommended strategy — the "wrong finance
    vertical intervention detail" bug.
    """
    vertical = request.vertical_horizontal
    lob = request.lob
    if request.page_context and request.page_context.filters:
        filters = request.page_context.filters
        vertical = vertical or filters.get("vertical") or filters.get("vertical_horizontal")
        lob = lob or filters.get("lob")
    return vertical, lob


def _real_metric_names_from_context(page_context) -> dict:
    """
    Extract real metric/intervention names from live pageContext.
    Returns a dict of all real names for use in follow-ups and parameter extraction.
    """
    if not page_context:
        return {"bos": [], "l1s": [], "l2s": [], "ivs": [], "active_ivs": []}
    return {
        "bos":  [m.get("name", "") for m in (page_context.business_outcomes or [])],
        "l1s":  [m.get("name", "") for m in (page_context.l1_metrics or [])],
        "l2s":  [m.get("name", "") for m in (page_context.l2_metrics or [])],
        "ivs":  [m.get("name", "") for m in (page_context.active_interventions or [])],
        "active_ivs": [m for m in (page_context.active_interventions or []) if m.get("percentage", 0) > 0],
    }


def _business_outcome_context(
    db: Session,
    metric_name: Optional[str],
    vertical: Optional[str],
    lob: Optional[str],
) -> Dict[str, Any]:
    """Look up the REAL slider bounds for `metric_name`, plus any other
    Business Outcomes that share (or partially match) that name.

    Two problems this fixes:
      1. The Goal clarification prompt used to suggest example target values
         from a hardcoded scale ("increase it to 105") regardless of the
         metric's actual slider range — nonsensical for a metric capped at,
         say, 60. Bounds returned here let the caller keep suggestions
         inside [min_value, max_value].
      2. When more than one Business Outcome card matches the name the user
         typed (e.g. the same KPI name reused across verticals/LOBs, or a
         partial match against several cards), the old code silently picked
         the first DB row via `.first()`. Callers can use `matches` to name
         every candidate explicitly and ask which card the user meant,
         instead of guessing.
    """
    from ...models import BusinessOutcome

    info: Dict[str, Any] = {"min_value": None, "max_value": None, "matches": []}
    if not metric_name:
        return info

    try:
        rows = db.query(BusinessOutcome).filter(BusinessOutcome.name == metric_name).all()
        if not rows:
            # No exact match — try a scoped partial match so we can still
            # surface bounds/duplicates for a loosely-typed metric name.
            rows = db.query(BusinessOutcome).filter(BusinessOutcome.name.ilike(f"%{metric_name}%")).all()

        # Bounds come from the row in the CURRENT vertical/lob scope when
        # possible, so a same-named card in a different scope never leaks
        # in as the suggested range for this one.
        scoped_rows = [
            r for r in rows
            if (not vertical or r.vertical_horizontal == vertical) and (not lob or r.lob == lob)
        ]
        primary_rows = scoped_rows or rows
        if primary_rows:
            bo = primary_rows[0]
            info["min_value"] = bo.min_value
            info["max_value"] = bo.max_value

        if len(rows) > 1:
            info["matches"] = [
                {
                    "name": r.name,
                    "vertical": r.vertical_horizontal,
                    "lob": r.lob,
                    "current_value": r.current_value,
                }
                for r in rows
            ]
    except Exception:
        pass

    return info


def _extract_goal_params(message: str, request: CascadeChatRequest):
    """
    Extract target metric name, value, direction, and optionally a list of
    allowed interventions from the user's message.
    
    Priority: explicit request fields → message regex → FIRST BO from live page data.
    Never falls back to 'DSO' or '25.0' — uses real names from the DB.

    Returns (metric, value, higher, ambiguous, current_value, allowed_interventions):
      - ambiguous=True means no target value could be confidently parsed from
        the message. Previously this silently defaulted to "current value
        +/- 10%" and presented a computed reachability answer as if the user
        had asked for that number — which is exactly the guessing behavior
        your own agent guardrails ("Goal Agent should NEVER guess") rule
        out. Callers must check `ambiguous` and ask a clarifying question
        instead of running the optimizer against a fabricated target.
      - allowed_interventions: list of intervention names parsed from the
        message, or None (meaning "search all interventions"). When the user
        says "only change TP Simulation, Interaction Analytics, and TP
        Gamification", the solver should only adjust those, pinning others at 0.
    """
    metric = request.target_metric
    value = request.target_value
    higher = request.higher_is_better or False

    if metric and value is not None:
        return metric, value, higher, False, None, None

    # Direction-aware value parsing. Order matters:
    #   1. An explicit "from X to Y" range — this is an ABSOLUTE target (Y),
    #      and must be checked before anything else. Without this, a phrasing
    #      like "reduces 5% revenue growth from 100% to 95%" matched the
    #      decrease-word regex against the nearest number after "reduce"
    #      (the "5" in "reduces 5%", a DELTA) instead of the real absolute
    #      target the user stated explicitly ("95"). That bug sent the
    #      optimizer chasing target=5 instead of target=95.
    #   2. An explicit "by N" delta ("increase Revenue Growth by only 3%",
    #      "reduce it by 10") — this is RELATIVE to whatever the metric's
    #      current value actually is (current +/- N), computed once we know
    #      current_value below. Without this, "increase by 5" fell through
    #      to the plain increase_re/generic_re path, which mis-parsed the
    #      "5" itself as the ABSOLUTE target — so if the metric was already
    #      at 100, the solver went hunting for a Revenue Growth of literally
    #      5, not the 105 the user meant. This also naturally handles any
    #      metric's real scale (100, 200, whatever current_value is), since
    #      the target is always current +/- N rather than a hardcoded ceiling.
    #   3. Decrease-direction words, then increase-direction words.
    #   4. Direction-agnostic connector/target words ("to", "at", "of", "is",
    #      "target", "reach", "achieve", "="). These do NOT imply a
    #      direction by themselves — "reach 95" said while a metric sits at
    #      100 usually means "get down to 95", not "increase to 95", but
    #      "reach 95" said at a current value of 80 means the opposite.
    #      Direction for these is decided below, once current_value is
    #      known, by simply comparing target vs current — never guessed
    #      from the word alone. Without this, "reach"/"achieve" were treated
    #      as unconditionally meaning "increase", so "goal reach 95% in
    #      revenue growth" while already at 100 got treated as "you're
    #      already there" instead of the decrease the user obviously meant
    #      (they'd just asked to reduce this same metric to this same 95
    #      the message before).
    range_re = r"from\s+(\d+(?:\.\d+)?)\s*%?\s*to\s+(\d+(?:\.\d+)?)\s*%?"
    # Genuine absolute thresholds — "keep DSO below 25%", "get NPS above 60".
    # These describe a hard line in the metric's own units/scale, so they
    # stay absolute even when followed by "%".
    # NOTE: capture group is (\d+(?:\.\d+)?) — requires at least one digit
    # before any decimal point, so a lone "." in the message (e.g. a sentence
    # ending "85% revenue growth.") can never be captured and crash float().
    threshold_decrease_re = r"\b(?:below|under|less than)\b\D{0,15}?(\d+(?:\.\d+)?)"
    threshold_increase_re = r"\b(?:above|over|more than)\b\D{0,15}?(\d+(?:\.\d+)?)"
    # Parsing rules for verb-driven phrases:
    #
    #   "reduce/increase BY N[%]"   → relative delta (always, by is explicit)
    #   "reduce/increase TO N[%]"   → absolute target (always, to is explicit)
    #   "reduce/increase N%"        → relative delta (% after bare number = change BY N%)
    #   "reduce/increase N"         → absolute target (bare number no % = reach N)
    #
    # Examples:
    #   "reduce 5% in revenue growth"   → delta -5%   of current → target = current * 0.95
    #   "increase 5% in revenue growth" → delta +5%   of current → target = current * 1.05
    #   "reduce revenue growth to 85"   → absolute target 85
    #   "increase revenue growth to 105"→ absolute target 105
    #   "reduce by 10"                  → delta -10 raw units
    #   "increase by 10%"               → delta +10% of current

    # True relative deltas: "by N" explicit, OR "VERB N%" (bare % with no "to")
    # `_FILLER` tolerates a filler word between the verb and the number/"to"/"by"
    # ("increase IT 105", "reduce THIS by 10") — without it, phrasing like
    # "increase it 105" matched none of the verb_* patterns below (the
    # pronoun broke the \s+ adjacency) and fell through to "ambiguous",
    # asking the same clarifying question again even though the user had
    # already answered it.
    _FILLER = r"(?:it\s+|this\s+|that\s+)?"
    verb_with_by_re = rf"\b(?:decrease|reduce|lower|drop|cut|increase|raise|boost|grow(?!th)|add)\w*\s+{_FILLER}by\s+(\d+(?:\.\d+)?)\s*(%?)"
    verb_bare_pct_re = rf"\b(?:decrease|reduce|lower|drop|cut|increase|raise|boost|grow(?!th)|add)\w*\s+{_FILLER}(\d+(?:\.\d+)?)\s*%(?!\s*\bto\b)"
    # Absolute targets: "VERB to N" or "VERB N" (no % after the number)
    verb_with_to_re = rf"\b(?:decrease|reduce|lower|drop|cut|increase|raise|boost|grow(?!th)|add)\w*\s+{_FILLER}to\s+(\d+(?:\.\d+)?)\s*%?"
    verb_bare_num_re = rf"\b(?:decrease|reduce|lower|drop|cut|increase|raise|boost|grow(?!th)|add)\w*\s+{_FILLER}(\d+(?:\.\d+)?)(?!\s*%)"
    neutral_target_re = r"(?:reach|achieve)\D{0,15}?(\d+(?:\.\d+)?)"
    generic_re = r"(?:\bto\b|\bat\b|\btarget(?:ing)?\b|\bis\b|\bof\b|=)\s*(\d+(?:\.\d+)?)\s*%?"
    # "by N" standalone — fires only when none of the verb patterns above matched.
    by_delta_re = r"\bby\s+(\d+(?:\.\d+)?)\s*(%?)"

    range_match = re.search(range_re, message, re.I)
    threshold_decrease_match = re.search(threshold_decrease_re, message, re.I)
    threshold_increase_match = re.search(threshold_increase_re, message, re.I)
    verb_with_by_match = re.search(verb_with_by_re, message, re.I)
    verb_bare_pct_match = re.search(verb_bare_pct_re, message, re.I)
    verb_with_to_match = re.search(verb_with_to_re, message, re.I)
    verb_bare_num_match = re.search(verb_bare_num_re, message, re.I)
    by_delta_match = re.search(by_delta_re, message, re.I)

    is_delta = False
    is_delta_pct = False
    delta_amount = None
    direction_is_explicit = False

    def _is_decrease(msg: str) -> bool:
        return bool(re.search(r"\b(decrease|reduce|lower|drop|cut)\w*\b", msg, re.I))

    if range_match:
        from_value = float(range_match.group(1))
        value = float(range_match.group(2))
        higher = value > from_value
        direction_is_explicit = True
    elif threshold_decrease_match:
        value = float(threshold_decrease_match.group(1))
        higher = False
        direction_is_explicit = True
    elif threshold_increase_match:
        value = float(threshold_increase_match.group(1))
        higher = True
        direction_is_explicit = True
    elif verb_with_by_match:
        # "increase/reduce BY N[%]" — explicit relative delta
        is_delta = True
        delta_amount = float(verb_with_by_match.group(1))
        is_delta_pct = verb_with_by_match.group(2) == "%"
        higher = not _is_decrease(message)
        direction_is_explicit = True
    elif verb_bare_pct_match:
        # "reduce 5%" / "increase 5%" — bare % means change BY N%
        is_delta = True
        delta_amount = float(verb_bare_pct_match.group(1))
        is_delta_pct = True
        higher = not _is_decrease(message)
        direction_is_explicit = True
    elif verb_with_to_match:
        # "reduce TO 85" / "increase TO 105" — explicit absolute target
        value = float(verb_with_to_match.group(1))
        higher = not _is_decrease(message)
        direction_is_explicit = True
    elif verb_bare_num_match:
        # "reduce 85" / "increase 105" (no %, no "to") — absolute target
        value = float(verb_bare_num_match.group(1))
        higher = not _is_decrease(message)
        direction_is_explicit = True
    elif by_delta_match:
        # "by N" with no direction verb — treat as relative delta.
        # Direction inferred from surrounding context words; falls back to
        # target-vs-current comparison below when context is silent.
        is_delta = True
        delta_amount = float(by_delta_match.group(1))
        is_delta_pct = by_delta_match.group(2) == "%"
        _msg_l = message.lower()
        if re.search(r"\b(decrease|reduce|lower|drop|cut|less|smaller|below)\w*\b", _msg_l):
            higher = False
            direction_is_explicit = True
        elif re.search(r"\b(increase|raise|boost|grow|more|higher|above)\w*\b", _msg_l):
            higher = True
            direction_is_explicit = True
        else:
            higher = False
            direction_is_explicit = False
    else:
        neutral_match = re.search(neutral_target_re, message, re.I)
        generic_match = neutral_match or re.search(generic_re, message, re.I)
        if generic_match:
            value = float(generic_match.group(1))
            higher = True  # direction corrected below via current_value comparison

    # Try to match a real metric name from pageContext
    names = _real_metric_names_from_context(request.page_context)
    msg_lower = message.lower()

    # Check BO names first
    for name in names["bos"]:
        if name.lower() in msg_lower or any(word in msg_lower for word in name.lower().split()[:2]):
            metric = name
            break

    # Fall back to first BO from live page
    if not metric and names["bos"]:
        metric = names["bos"][0]

    vertical, lob = _get_scope(request)

    # Last resort: query DB for first business outcome name IN THIS SCOPE.
    # Querying without the vertical/lob filter here would hand back a
    # random other vertical's first business outcome as the "target metric"
    # whenever the message/page_context didn't already name one.
    if not metric:
        try:
            from ...models import BusinessOutcome
            from ...database import SessionLocal
            db = SessionLocal()
            q = db.query(BusinessOutcome)
            if vertical:
                q = q.filter(BusinessOutcome.vertical_horizontal == vertical)
            if lob:
                q = q.filter(BusinessOutcome.lob == lob)
            bo = q.first()
            if bo:
                metric = bo.name
            db.close()
        except Exception:
            metric = "Business Outcome"

    current_value = None
    try:
        from ...models import BusinessOutcome
        from ...database import SessionLocal
        db = SessionLocal()
        q = db.query(BusinessOutcome).filter(BusinessOutcome.name == metric)
        if vertical:
            q = q.filter(BusinessOutcome.vertical_horizontal == vertical)
        if lob:
            q = q.filter(BusinessOutcome.lob == lob)
        bo = q.first()
        if bo:
            current_value = bo.current_value if bo.current_value is not None else bo.default_value
            if higher is False and value is None:
                pass  # direction known, value still missing — still ambiguous
        db.close()
    except Exception:
        current_value = None

    if is_delta:
        # "increase/reduce X by N" is only meaningful relative to whatever
        # X actually is right now — never a hardcoded scale. If we can't
        # read a real current_value, we cannot compute a real target, so
        # this stays ambiguous rather than guessing (e.g. assuming N alone
        # or assuming a 0-100 scale that may not match this metric at all).
        if current_value is not None:
            if is_delta_pct:
                # "reduce/increase X by N%" -> N% OF current_value, not N
                # raw units. ("reduce revenue growth 15%" while sitting at
                # 76.89 means ~65.4, not literally 76.89 - 15 = 61.89, and
                # certainly not a target of 15.)
                value = (
                    current_value * (1 + delta_amount / 100.0) if higher
                    else current_value * (1 - delta_amount / 100.0)
                )
            else:
                value = current_value + delta_amount if higher else current_value - delta_amount
        else:
            value = None
    elif not direction_is_explicit and value is not None and current_value is not None:
        # "reach 95" / "achieve 95" / "the target is 95" never said whether
        # that's an increase or a decrease — decide from the actual numbers
        # instead of assuming. If the stated target is below where the
        # metric already sits, the user means bring it DOWN to that number;
        # if it's above, they mean bring it UP. Only an exact match (target
        # == current) falls back to the increase-leaning default, since
        # there's nothing to infer direction from at all in that edge case.
        higher = value >= current_value

    # Parse any intervention names mentioned in the message — these become
    # the constraint list for the solver (only adjust these, pin others at 0).
    # E.g. "achieve 85% using only TP Simulation, Interaction Analytics, and
    # TP Gamification" → allowed = ["TP Simulation", "Interaction Analytics",
    # "TP Gamification"]. No match → None (search all interventions).
    allowed_interventions = None
    names_ctx = _real_metric_names_from_context(request.page_context)
    iv_names_all = names_ctx.get("ivs", [])
    if iv_names_all:
        msg_lower_iv = message.lower()
        matched = [
            iv for iv in iv_names_all
            if iv and iv.lower() in msg_lower_iv
        ]
        if matched:
            allowed_interventions = matched

    if value is None:
        # No target value could be parsed from the message at all. Ask,
        # don't guess — this is the fix for the "Revenue Growth of 110"
        # fabrication, where 110 was silently invented as current*1.10.
        return metric, None, higher, True, current_value, allowed_interventions

    return metric, value, higher, False, current_value, allowed_interventions


def _extract_trace_params(message: str, request: CascadeChatRequest):
    """
    Extract metric name for trace.
    Uses real names from pageContext, never hardcoded 'DSO'.
    """
    if request.trace_metric:
        return request.trace_metric, request.from_intervention, request.to_outcome

    names = _real_metric_names_from_context(request.page_context)
    msg_lower = message.lower()

    # Try to match a real metric name from the message
    all_names = names["bos"] + names["l1s"] + names["l2s"] + names["ivs"]
    for name in all_names:
        if name and (name.lower() in msg_lower or
                     any(word in msg_lower for word in name.lower().split()[:2] if len(word) > 3)):
            return name, None, None

    # Default to first BO from live page
    if names["bos"]:
        return names["bos"][0], None, None

    # Query DB, scoped to the current vertical/LOB
    try:
        from ...models import BusinessOutcome
        from ...database import SessionLocal
        vertical, lob = _get_scope(request)
        db = SessionLocal()
        q = db.query(BusinessOutcome)
        if vertical:
            q = q.filter(BusinessOutcome.vertical_horizontal == vertical)
        if lob:
            q = q.filter(BusinessOutcome.lob == lob)
        bo = q.first()
        name = bo.name if bo else "KPI"
        db.close()
        return name, None, None
    except Exception:
        return "KPI", None, None


def _generate_followups(intent: IntentType, tool_data: dict, page_context=None) -> List[str]:
    """
    Build follow-up suggestions using REAL names from tool_data and page_context.
    Never hardcodes 'DSO', 'RPA', 'ROI', etc.
    """
    names = _real_metric_names_from_context(page_context)
    first_bo = names["bos"][0] if names["bos"] else None
    first_iv = names["ivs"][0] if names["ivs"] else None
    first_l1 = names["l1s"][0] if names["l1s"] else None

    # Also read from tool_data for richer context
    changed_bos = tool_data.get("changed_business_outcomes", [])
    changed_bo_name = changed_bos[0]["name"] if changed_bos else first_bo
    solutions = tool_data.get("solutions", [])

    if intent == IntentType.INSIGHT:
        q = [
            f"How can I improve {changed_bo_name}?" if changed_bo_name else "How can I improve my results?",
            "Which intervention has the most impact?",
        ]
        if first_l1:
            q.append(f"Show me the formula path for {first_l1}")
        return q[:3]

    elif intent == IntentType.GOAL:
        q = ["What's the best overall strategy?"]
        if first_bo:
            q.append(f"Which interventions have the highest impact on {first_bo}?")
        q.append("Apply the top recommendation to my sliders")
        return q[:3]

    elif intent == IntentType.KNOWLEDGE:
        q = []
        if first_bo:
            q.append(f"How is {first_bo} calculated?")
        if first_iv:
            q.append(f"What does {first_iv} impact?")
        q.append("Show me the full formula path")
        return q[:3]

    elif intent == IntentType.TRACE:
        q = []
        if changed_bo_name:
            q.append(f"Why did {changed_bo_name} change?")
        if first_iv:
            q.append(f"How do I improve results using {first_iv}?")
        q.append("What is the impact factor for this relationship?")
        return q[:3]

    elif intent == IntentType.ADVISOR:
        q = []
        if first_bo:
            q.append(f"How do I reach a specific target for {first_bo}?")
        q.append("Why does this strategy work?")
        if first_iv:
            q.append(f"Show me the formula for {first_iv}")
        return q[:3]

    elif intent == IntentType.WHATIF:
        q = []
        if first_bo:
            q.append(f"How do I get {first_bo} even higher?")
        q.append("What's the best overall strategy?")
        if first_iv:
            q.append(f"What happens if I lower {first_iv} instead?")
        return q[:3]

    return [
        "Why did my KPIs change?",
        "What is the best strategy?",
        "Show me the formula path",
    ]


# ── LLM Client ───────────────────────────────────────────────────────────────

def _get_gemini_client():
    from ..config import get_ai_config
    cfg = get_ai_config()
    if not cfg.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to backend/.env\n"
            "Get a free key at https://aistudio.google.com/apikey"
        )
    import urllib.request

    class _GeminiHttp:
        def __init__(self, key, model, fallback_model=None):
            self.key = key
            self.model = model
            self.fallback_model = fallback_model
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

        @staticmethod
        def _to_gemini_payload(messages, max_tokens, temperature):
            """Gemini has no 'system'/'assistant' roles: system prompt text
            goes in a separate systemInstruction field, and assistant turns
            become role 'model'."""
            system_parts = []
            contents = []
            for m in messages:
                role = m["role"]
                text = m["content"]
                if role == "system":
                    system_parts.append(text)
                elif role == "assistant":
                    contents.append({"role": "model", "parts": [{"text": text}]})
                else:
                    contents.append({"role": "user", "parts": [{"text": text}]})
            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature,
                },
            }
            if system_parts:
                payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
            return payload

        @staticmethod
        def _extract_text(data):
            try:
                candidate = data["candidates"][0]
                return "".join(
                    p.get("text", "") for p in candidate["content"]["parts"]
                )
            except (KeyError, IndexError):
                finish = (data.get("candidates") or [{}])[0].get("finishReason", "UNKNOWN")
                raise RuntimeError(f"Gemini returned no content (finishReason={finish})")

        def _post(self, model, messages, max_tokens, temperature):
            payload = self._to_gemini_payload(messages, max_tokens, temperature)
            url = f"{self.base_url}/{model}:generateContent?key={self.key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            return self._extract_text(data)

        def complete(self, messages, max_tokens=1000, temperature=0.3):
            """
            Resilience strategy:
              - 429 (rate limited) on the primary model: back off briefly and
                retry twice, then switch to the fallback model for this call
                only (never permanently) so one busy model doesn't take down
                the whole turn.
              - 5xx (transient server error): short retry, no model switch.
              - Anything else (401/403/400): fail fast — retrying won't help
                an auth or request-shape problem, and we don't want to burn
                the fallback model's quota on a request that will never
                succeed.
            """
            import time
            import urllib.error

            attempts = [
                (self.model, 0),
                (self.model, 0.6),
            ]
            if self.fallback_model and self.fallback_model != self.model:
                attempts.append((self.fallback_model, 0))

            last_err = None
            for model, delay in attempts:
                if delay:
                    time.sleep(delay)
                try:
                    text = self._post(model, messages, max_tokens, temperature)
                    # Wrapped in an OpenAI-shaped envelope so call sites
                    # (resp["choices"][0]["message"]["content"]) don't change.
                    return {"choices": [{"message": {"content": text}}]}
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code in (429, 500, 502, 503, 504):
                        continue  # try next attempt (retry or fallback model)
                    raise  # 401/403/400 etc — no point retrying
            raise last_err

        def stream(self, messages, max_tokens=1000, temperature=0.3):
            """Yields text deltas via Gemini's SSE streaming endpoint."""
            import urllib.error

            payload = self._to_gemini_payload(messages, max_tokens, temperature)
            models_to_try = [self.model]
            if self.fallback_model and self.fallback_model != self.model:
                models_to_try.append(self.fallback_model)

            last_err = None
            for i, model in enumerate(models_to_try):
                url = (
                    f"{self.base_url}/{model}:streamGenerateContent"
                    f"?alt=sse&key={self.key}"
                )
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=60) as r:
                        for raw_line in r:
                            line = raw_line.decode("utf-8", errors="ignore").strip()
                            if not line.startswith("data:"):
                                continue
                            data_str = line[len("data:"):].strip()
                            if not data_str or data_str == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk["candidates"][0]["content"]["parts"][0]["text"]
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                            if delta:
                                yield delta
                    return
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code in (429, 500, 502, 503, 504) and i < len(models_to_try) - 1:
                        continue  # try fallback model
                    raise
            if last_err:
                raise last_err

    return cfg, _GeminiHttp(cfg.gemini_api_key, cfg.gemini_model, cfg.gemini_fallback_model)


def _build_messages(system, user_message, history):
    msgs = [{"role": "system", "content": system}]
    for h in history[-6:]:
        msgs.append({"role": h.role, "content": h.content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


def _call_llm(system, user_message, history) -> str:
    cfg, client = _get_gemini_client()
    msgs = _build_messages(system, user_message, history)
    try:
        resp = client.complete(msgs)
        return resp["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Gemini call failed: {e}")
        raise


class LLMUnavailable(Exception):
    """Raised when the LLM call fails after retries. Carries enough detail
    for the caller to give a specific, honest message instead of a generic
    one — a 429 (rate limit / quota) is a completely different situation
    from a bad API key or no internet access, and telling a user to go
    check their API key when the real problem is "wait 30 seconds and
    retry" just sends them on a pointless goose chase.
    """
    def __init__(self, detail: str, is_rate_limit: bool):
        self.detail = detail
        self.is_rate_limit = is_rate_limit
        super().__init__(detail)


async def _stream_llm(system, user_message, history) -> AsyncGenerator[str, None]:
    cfg, client = _get_gemini_client()
    msgs = _build_messages(system, user_message, history)

    # 429s are frequently transient on the free tier (a per-minute quota
    # that resets shortly), so it's worth a couple of short waits before
    # giving up — much cheaper than making the user manually retry, and
    # _get_gemini_client() already tries a fallback model first, so this
    # only kicks in if BOTH models are rate-limited.
    backoffs = [1.5, 3.0]
    last_err: Optional[Exception] = None

    for attempt in range(len(backoffs) + 1):
        try:
            got_any = False
            for delta in client.stream(msgs, max_tokens=1000, temperature=0.3):
                got_any = True
                yield delta

            if not got_any:
                resp = client.complete(msgs)
                yield resp["choices"][0]["message"]["content"]
            return

        except Exception as e:
            last_err = e
            is_rate_limit = "429" in str(e) or "Too Many Requests" in str(e)
            logger.error(f"LLM stream error (attempt {attempt + 1}): {e}", exc_info=True)
            if is_rate_limit and attempt < len(backoffs):
                await asyncio.sleep(backoffs[attempt])
                continue
            raise LLMUnavailable(str(e)[:160], is_rate_limit) from e

    if last_err:
        raise LLMUnavailable(str(last_err)[:160], "429" in str(last_err))


def _deterministic_reply_fallback(intent: IntentType, tool_data: dict) -> Optional[str]:
    """Plain-template reply built directly from tool_data, with no LLM
    involved at all — used when Gemini is unreachable (most commonly:
    rate-limited) so the user still gets the real, already-computed numbers
    instead of only an error message. The Goal Engine / What-If simulator
    already did all the actual work before the LLM was ever called; the LLM
    normally just narrates it more naturally. Covers GOAL and WHATIF, the
    two most-exercised tool-backed intents; returns None for anything else
    (Insight/Trace/Knowledge/Advisor), where the caller shows a plain error
    instead of guessing at a template.
    """
    if intent == IntentType.GOAL:
        solutions = tool_data.get("solutions") or []
        if not solutions:
            return None
        top = solutions[0]
        metric = tool_data.get("target_metric", "the metric")
        target = tool_data.get("target_value")
        achieved = top.get("achieved_value")
        gap = top.get("gap_pct")
        ivs = top.get("interventions") or []
        iv_txt = ", ".join(f"**{iv['name']}** at {iv['value']:.0f}%" for iv in ivs) if ivs else "no interventions"
        if gap is not None and gap < 5:
            return (
                f"Target **{metric} = {target}** is reachable. Set {iv_txt} to hit "
                f"**{achieved}** (within {gap}% of target).\n\n"
                "Open the recommendation above and tap Apply to move your sliders to this plan."
            )
        limiting_factors = tool_data.get("limiting_factors") or []
        lf_txt = (
            "; ".join(f"**{lf['name']}** is already at its {lf['at']}" for lf in limiting_factors)
            if limiting_factors
            else "the combination as a whole has already been pushed as far as the model allows"
        )
        return (
            f"**{metric}** measures a live simulated KPI on this page.\n\n"
            f"A target of **{target}** is NOT reachable with the current interventions. The "
            f"Goal Engine already searched the full range of every intervention and found the "
            f"minimum/maximum achievable **{metric}** is **{achieved}**"
            f"{f' (gap: {gap}%)' if gap is not None else ''} — {target} sits outside the "
            f"feasible solution space with the levers currently available.\n\n"
            f"**Limiting factors:** {lf_txt}. These are constraints imposed by the prediction "
            f"model, not something left untried.\n\n"
            f"**Closest achievable result:** requested {target}, best achievable {achieved}"
            f"{f', gap {gap}%' if gap is not None else ''}.\n\n"
            f"**Recommended action:** set {iv_txt} — this is the best available outcome given "
            "current constraints.\n\n"
            "Open the recommendation above and tap Apply to move your sliders to this plan."
        )

    if intent == IntentType.WHATIF:
        applied = tool_data.get("applied_overrides") or {}
        bos = tool_data.get("business_outcomes") or []
        l1s = tool_data.get("l1_metrics") or []
        unresolved = tool_data.get("unresolved_names") or []
        if not applied:
            return None
        applied_txt = ", ".join(f"{name} = {val}%" for name, val in applied.items())
        lines = [f"With {applied_txt}, the simulated results are:"]
        for bo in bos:
            lines.append(
                f"- **{bo['name']}**: {bo['current_value']} {bo.get('unit') or ''} "
                f"(was {bo['default_value']}, {bo['improvement_percentage']:+.1f}%)"
            )
        for l1 in l1s:
            lines.append(f"- **{l1['name']}**: {l1['current_value']} {l1.get('unit') or ''}")
        if unresolved:
            lines.append(f"\n(Couldn't match: {', '.join(unresolved)})")
        lines.append("\n_This is a temporary simulation — your saved sliders are unchanged._")
        return "\n".join(lines)

    return None


def _llm_unavailable_message(err: "LLMUnavailable") -> str:
    if err.is_rate_limit:
        return (
            "⚠️ Gemini is rate-limiting this app right now (**HTTP 429 — quota exceeded**). "
            "This is a usage-quota limit on your API key, not a bug in the app — the free tier "
            "allows a fairly small number of requests per minute. Wait a minute and try again, "
            "or check your quota/plan at https://ai.google.dev/gemini-api/docs/rate-limits."
        )
    return (
        f"⚠️ Cannot reach the AI service: {err.detail}\n\n"
        "**To fix:** Check that `GEMINI_API_KEY` is set in `backend/.env` "
        "and your server has internet access to `generativelanguage.googleapis.com`."
    )


# ── Tool Dispatch ─────────────────────────────────────────────────────────────

def _goal_clarification_reply(tool_data: Dict[str, Any]) -> str:
    """Builds the "what target value?" clarifying question for GOAL intents.

    Replaces two bugs that used to live inline at each call site:
      1. A hardcoded "increase it to 105 / reduce it below 25" example that
         ignored the metric's actual slider range — nonsensical once the
         metric's max_value is, say, 60. Examples are now derived from the
         metric's real [min_value, max_value] (falling back to a percentage
         of current_value when bounds aren't available) and clamped inside
         that range.
      2. Silently answering about whichever Business Outcome row happened
         to be `.first()`-ed out of the DB when several cards share (or
         partially match) the same name. When _business_outcome_context()
         found more than one match, every candidate is named explicitly so
         the user can say which card they meant instead of getting an
         answer for the wrong one.
    """
    metric = tool_data.get("metric", "this metric")
    current = tool_data.get("current_value")
    min_v = tool_data.get("min_value")
    max_v = tool_data.get("max_value")
    matches = tool_data.get("matches") or []

    current_txt = f" It's currently at **{current}**." if current is not None else ""

    if current is not None:
        span = (max_v - min_v) if (min_v is not None and max_v is not None and max_v > min_v) else None
        step = max(span * 0.15, 1) if span else max(abs(current) * 0.1, 1)
        up_example = current + step
        down_example = current - step
        if max_v is not None:
            up_example = min(up_example, max_v)
        if min_v is not None:
            down_example = max(down_example, min_v)
        example_txt = (
            f' For example: "increase it to {round(up_example, 1)}" '
            f'or "reduce it below {round(down_example, 1)}".'
        )
    else:
        example_txt = ' For example: "increase it to X" or "reduce it below Y".'

    disambiguation_txt = ""
    if len(matches) > 1:
        listed = "; ".join(
            f"{m['name']} ({m.get('vertical') or 'Unscoped'} / {m.get('lob') or 'Unscoped'}, "
            f"currently {m.get('current_value')})"
            for m in matches
        )
        disambiguation_txt = (
            f" I also found **{len(matches)}** Business Outcome cards matching \"{metric}\": "
            f"{listed}. Let me know which one you mean if that's not the right one."
        )

    return (
        "I want to make sure I optimize for the right number before running the solver. "
        f"What target value would you like for **{metric}**?{current_txt}"
        f"{example_txt}{disambiguation_txt}"
    )


def _dispatch(db: Session, request: CascadeChatRequest, intent: IntentType):
    """Run the correct tool and build the LLM user prompt.

    Every tool call below is scoped to the current vertical/LOB via
    `_get_scope(request)`. This is the fix for the cross-vertical data leak:
    previously none of these calls passed vertical/lob at all, so each tool
    queried its underlying table unfiltered, across every vertical in the DB.
    """
    page_ctx_block = format_page_context(request.page_context)
    vertical, lob = _get_scope(request)

    if intent == IntentType.INSIGHT:
        tool_data = insight_tool(db, request.message, vertical=vertical, lob=lob)
        prompt = page_ctx_block + format_insight_prompt(tool_data, request.message)

    elif intent == IntentType.GOAL:
        metric, value, higher, ambiguous, current_value, allowed_interventions = _extract_goal_params(request.message, request)
        if ambiguous:
            # Don't run the optimizer against a fabricated target. Surface
            # enough for run_cascade/stream_cascade to ask a real
            # clarifying question instead (see needs_clarification bypass).
            bo_ctx = _business_outcome_context(db, metric, vertical, lob)
            tool_data = {
                "tool": "goal",
                "needs_clarification": True,
                "metric": metric,
                "current_value": current_value,
                "min_value": bo_ctx["min_value"],
                "max_value": bo_ctx["max_value"],
                "matches": bo_ctx["matches"],
            }
            prompt = ""
        else:
            tool_data = goal_tool(db, metric, value, higher, vertical=vertical, lob=lob,
                                  allowed_interventions=allowed_interventions)
            prompt = page_ctx_block + format_goal_prompt(tool_data, request.message)

    elif intent == IntentType.TRACE:
        metric, from_iv, to_bo = _extract_trace_params(request.message, request)
        tool_data = excel_trace_tool(db, metric, from_iv, to_bo, vertical=vertical, lob=lob)
        prompt = page_ctx_block + format_trace_prompt(tool_data, request.message)

    elif intent == IntentType.ADVISOR:
        apply_intent = _is_advisor_apply_intent(request.message)
        tool_data = decision_advisor_tool(
            db, request.target_outcome, vertical=vertical, lob=lob, apply_intent=apply_intent
        )
        prompt = page_ctx_block + format_advisor_prompt(tool_data, request.message)

    elif intent == IntentType.WHATIF:
        # This branch was previously MISSING entirely: detect_intent() could
        # already return IntentType.WHATIF (via _is_whatif_intent), and
        # _resolve_whatif_overrides/whatif_tool already existed, but nothing
        # ever called them here — so a WHATIF-classified message fell
        # through to the `else` (Knowledge) branch below, ran knowledge_tool
        # against a RAG index that only knows business concepts, and (for
        # something like "what is BO?" after stating hypothetical slider
        # values) correctly reported no definition found for "BO" — because
        # the question was never a definition question in the first place.
        overrides, unresolved_count = _resolve_whatif_overrides(request.message, request)
        if not overrides:
            tool_data = {
                "tool": "whatif",
                "needs_clarification": True,
                "unresolved_count": unresolved_count,
            }
            prompt = ""
        else:
            tool_data = whatif_tool(db, overrides, unresolved_count=unresolved_count, vertical=vertical, lob=lob)
            prompt = page_ctx_block + format_whatif_prompt(tool_data, request.message)

    else:
        # Scope RAG retrieval to names that actually exist on THIS page, so
        # a Finance BRD chunk (DSO, RPA, Collection Efficiency Rate...) can
        # never be cited back to a Customer Support / TP Simulation page.
        names = _real_metric_names_from_context(request.page_context)
        allowed_terms = list({
            *names["bos"], *names["l1s"], *names["l2s"], *names["ivs"],
        })
        tool_data = knowledge_tool(request.message, allowed_terms=allowed_terms)
        prompt = page_ctx_block + format_knowledge_prompt(tool_data, request.message)

    return tool_data, prompt


import contextlib


@contextlib.contextmanager
def _synced_to_live_page_state(db: Session, request: CascadeChatRequest, vertical, lob):
    """
    Make the DB briefly reflect exactly what the user sees on screen, run the
    tool, then put the DB back exactly as it was.

    Why this exists: dragging a slider on the KPI board is a purely
    client-side simulation ("drag-tick: local cascade only, no API" — see
    frontend/src/store/kpiStore.js). Nothing is written to the database
    until the user explicitly clicks Save/Update. That means every AI tool
    (insight_tool, goal_tool, decision_advisor_tool, trace) was reading the
    DB's last-SAVED intervention percentages, while `request.page_context`
    carried the true on-screen (possibly unsaved, possibly higher/lower)
    percentages — two different numbers for "the current state" landing in
    the same prompt. That's exactly the contradiction reported: "Active
    Interventions: None" (from the stale DB read) next to "TP Simulation...
    at 11% each" (from the live page_context block) in the same answer.

    This context manager closes that gap without changing the "nothing is
    saved unless you click Save" contract: it writes the live percentages
    into the DB, recalculates the cascade, lets the tool run against that
    now-accurate snapshot, and restores the original saved values (with
    another recalculate) in a `finally` block no matter what happens.
    """
    from ...models import Intervention
    from ...services import simulation_service

    page_ctx = request.page_context
    if not page_ctx or page_ctx.active_interventions is None:
        # No live data supplied — nothing to sync, just run as-is.
        yield
        return

    def _scope(q):
        if vertical:
            q = q.filter(Intervention.vertical_horizontal == vertical)
        if lob:
            q = q.filter(Intervention.lob == lob)
        return q

    scoped_ivs = _scope(db.query(Intervention)).all()
    original = {iv.id: iv.percentage for iv in scoped_ivs}
    live_by_name = {iv["name"]: iv.get("percentage", 0) for iv in page_ctx.active_interventions}

    try:
        for iv in scoped_ivs:
            # Anything not present in the live list is 0% on screen right now
            # (the frontend only sends interventions with percentage > 0).
            live_value = live_by_name.get(iv.name, 0)
            if live_value != iv.percentage:
                db.query(Intervention).filter(Intervention.id == iv.id).update(
                    {Intervention.percentage: live_value}
                )
        db.commit()
        simulation_service.recalculate(db)
        yield
    finally:
        for iv_id, pct in original.items():
            db.query(Intervention).filter(Intervention.id == iv_id).update(
                {Intervention.percentage: pct}
            )
        db.commit()
        simulation_service.recalculate(db)


# ── Evidence Sources per Intent ─────────────────────────────────────────────

def _sources_used(intent: IntentType, tool_data: dict) -> List[str]:
    """Which real, verifiable data sources actually backed this answer.
    Deterministic — derived from what the tool actually returned, not from
    what the LLM claims to have used."""
    if tool_data.get("error"):
        return []

    if intent == IntentType.INSIGHT:
        sources = ["live_simulation"]
        if tool_data.get("verified_chains"):
            sources.append("formula_trace")
        return sources
    if intent == IntentType.GOAL:
        return ["live_simulation", "goal_engine"]
    if intent == IntentType.TRACE:
        return ["formula_trace", "workbook"]
    if intent == IntentType.ADVISOR:
        return ["live_simulation", "decision_engine"]
    if intent == IntentType.WHATIF:
        return [] if tool_data.get("needs_clarification") else ["live_simulation", "calculation_engine"]
    if intent == IntentType.KNOWLEDGE:
        return [] if tool_data.get("not_found") else ["knowledge_base"]
    return []


def _finalize_reply(intent: IntentType, tool_data: dict, reply: str) -> tuple[str, List[str], float]:
    """Run the post-hoc grounding check and attach a deterministic evidence
    footer. Returns (reply_with_footer, evidence_labels, confidence)."""
    sources = _sources_used(intent, tool_data)
    allowed = collect_allowed_numbers(tool_data)
    ungrounded = find_ungrounded_numbers(reply, allowed) if allowed else []

    confidence = compute_confidence(
        has_error=bool(tool_data.get("error")),
        ungrounded_count=len(ungrounded),
        sources_used=sources,
    )
    reply_with_footer = reply + evidence_footer(sources, confidence, ungrounded)
    return reply_with_footer, evidence_list(sources), confidence




def run_cascade(db: Session, request: CascadeChatRequest) -> dict:
    """Synchronous cascade call. Returns full response dict."""
    intent = detect_intent(request.message, request.intent_override, request.page_context)
    vertical, lob = _get_scope(request)
    with _synced_to_live_page_state(db, request, vertical, lob):
        tool_data, user_prompt = _dispatch(db, request, intent)

    # Knowledge questions with nothing retrieved never reach the LLM at
    # all — this is what fixes "the Knowledge Agent explained from live
    # data instead of admitting it didn't know". There is nothing for the
    # model to blend in if it's never asked.
    if intent == IntentType.KNOWLEDGE and tool_data.get("not_found"):
        reply = (
            f"No definition was found in the current knowledge base for **\"{request.message}\"**. "
            "This term may not be documented yet, or it may only exist as a live simulation value "
            "rather than a formal definition — try asking \"why did X change\" instead for that."
        )
        reply, evidence, confidence = _finalize_reply(intent, tool_data, reply)
        return {
            "reply": reply,
            "intent": intent,
            "tool_result": {"tool_used": tool_data.get("tool", intent.value), "data": tool_data},
            "suggested_followups": _generate_followups(intent, tool_data, request.page_context),
            "evidence": evidence,
            "confidence": confidence,
        }

    # Goal questions with no parseable target value never reach the LLM or
    # the optimizer either — this is what fixes the "Revenue Growth of 110"
    # fabrication, where no number could be parsed from the message so the
    # code used to silently guess current_value*1.10 and present it as the
    # user's target. Ask instead of guessing.
    if intent == IntentType.GOAL and tool_data.get("needs_clarification"):
        reply = _goal_clarification_reply(tool_data)
        return {
            "reply": reply,
            "intent": intent,
            "tool_result": {"tool_used": "goal", "data": tool_data},
            "suggested_followups": [],
            "evidence": [],
            "confidence": None,
        }

    # What-if questions whose intervention names couldn't be confidently
    # resolved never reach the LLM either — same "ask, don't guess" rule as
    # GOAL above. Guessing which real intervention "the first 3 options"
    # refers to (or inventing a plausible-sounding name) is exactly the
    # fabrication pattern the rest of this file already guards against.
    if intent == IntentType.WHATIF and tool_data.get("needs_clarification"):
        available = tool_data.get("available_interventions") or []
        listed = ", ".join(available[:8]) if available else "the interventions shown on this page"
        reply = (
            "I couldn't confidently match those to real intervention names on this page. "
            f"Could you name them directly? For example: {listed}."
        )
        return {
            "reply": reply,
            "intent": intent,
            "tool_result": {"tool_used": "whatif", "data": tool_data},
            "suggested_followups": [],
            "evidence": [],
            "confidence": None,
        }

    try:
        reply = _call_llm(SYSTEM_PROMPT, user_prompt, request.history)
    except Exception as e:
        is_rate_limit = "429" in str(e) or "Too Many Requests" in str(e)
        fallback = _deterministic_reply_fallback(intent, tool_data)
        if fallback:
            note = (
                "\n\n_(Gemini is rate-limited right now, so this reply is templated directly "
                "from the calculation engine's numbers instead of AI-narrated.)_"
                if is_rate_limit else
                "\n\n_(AI narration is unavailable, so this reply is templated directly from "
                "the calculation engine.)_"
            )
            reply = fallback + note
        elif is_rate_limit:
            reply = (
                "⚠️ Gemini is rate-limiting this app right now (**HTTP 429 — quota exceeded**). "
                "This is a usage-quota limit on your API key, not a bug — wait a minute and "
                "try again, or check your quota/plan at "
                "https://ai.google.dev/gemini-api/docs/rate-limits."
            )
        else:
            reply = (
                f"⚠️ AI unavailable: {e}\n\n"
                "Add `GEMINI_API_KEY` to `backend/.env`. "
                "Free key at https://aistudio.google.com/apikey"
            )
        return {
            "reply": reply,
            "intent": intent,
            "tool_result": {"tool_used": tool_data.get("tool", intent.value), "data": tool_data},
            "suggested_followups": _generate_followups(intent, tool_data, request.page_context),
            "evidence": [],
            "confidence": 0.0,
        }

    reply, evidence, confidence = _finalize_reply(intent, tool_data, reply)

    return {
        "reply": reply,
        "intent": intent,
        "tool_result": {"tool_used": tool_data.get("tool", intent.value), "data": tool_data},
        "suggested_followups": _generate_followups(intent, tool_data, request.page_context),
        "evidence": evidence,
        "confidence": confidence,
        "card_data": _recommendation_card_data(intent, tool_data),
    }


def _recommendation_card_data(intent: IntentType, tool_data: dict) -> Optional[dict]:
    """Structured data for the frontend's sticky Recommendation Card —
    built directly from the same deterministic tool_data the prompt
    formatters use, never from parsing the LLM's prose. Returns None for
    intents that don't produce an actionable plan (Insight/Knowledge/Trace),
    or when the tool found nothing to recommend.

    Only GOAL and ADVISOR (recommend mode — not apply-confirmation) produce
    a card. WHATIF is a one-off hypothetical, not a standing plan, so it
    doesn't get a persistent card either.
    """
    if intent == IntentType.GOAL:
        solutions = tool_data.get("solutions") or []
        if not solutions:
            return None
        top = solutions[0]
        return {
            "kind": "goal",
            "title": f"Reach {tool_data.get('target_metric', 'target')} = {tool_data.get('target_value')}",
            "achieved_label": tool_data.get("target_metric", "Result"),
            "achieved_value": top.get("achieved_value"),
            "confidence": top.get("confidence"),
            "gap_pct": top.get("gap_pct"),
            "interventions": top.get("interventions", []),
        }

    if intent == IntentType.ADVISOR and tool_data.get("mode") != "apply":
        strategies = tool_data.get("strategies") or []
        if not strategies:
            return None
        top = strategies[0]
        bos = top.get("business_outcomes", [])
        return {
            "kind": "advisor",
            "title": top.get("name", "Recommended Strategy"),
            "achieved_label": bos[0]["name"] if bos else "Business Outcome",
            "achieved_value": bos[0]["improvement_pct"] if bos else top.get("avg_bo_improvement"),
            "confidence": top.get("confidence"),
            "gap_pct": None,
            "interventions": [
                {"name": iv["name"], "value": iv["pct"]} for iv in top.get("interventions", [])
            ],
        }

    return None


async def stream_cascade(db: Session, request: CascadeChatRequest) -> AsyncGenerator[str, None]:
    """Async streaming cascade. Yields SSE-formatted text chunks."""
    intent = detect_intent(request.message, request.intent_override, request.page_context)
    vertical, lob = _get_scope(request)
    with _synced_to_live_page_state(db, request, vertical, lob):
        tool_data, user_prompt = _dispatch(db, request, intent)

    sources = _sources_used(intent, tool_data)
    followups = _generate_followups(intent, tool_data, request.page_context)

    # First event: metadata (intent badge + dynamic follow-ups)
    meta = json.dumps({
        "intent": intent.value,
        "tool": tool_data.get("tool", intent.value),
        "followups": followups,
        # Deterministic action payload (e.g. Advisor apply-mode slider
        # values) computed directly from the simulation engine. The
        # frontend should act on this instead of regex-parsing the chat
        # reply text, which is unreliable once the reply's wording changes.
        "mode": tool_data.get("mode"),
        "apply_action": tool_data.get("apply_action"),
        # Structured plan data for the frontend's sticky Recommendation
        # Card — see _recommendation_card_data(). None for intents that
        # don't produce an actionable plan.
        "card_data": _recommendation_card_data(intent, tool_data),
        # Deterministic, computed before any LLM text exists — the UI can
        # render the evidence checklist immediately.
        "evidence": evidence_list(sources),
    })
    yield f"data: {meta}\n\n"

    # Knowledge questions with nothing retrieved never reach the LLM — see
    # run_cascade() for the full rationale.
    if intent == IntentType.KNOWLEDGE and tool_data.get("not_found"):
        reply = (
            f"No definition was found in the current knowledge base for **\"{request.message}\"**. "
            "This term may not be documented yet, or it may only exist as a live simulation value "
            "rather than a formal definition — try asking \"why did X change\" instead for that."
        )
        yield f"data: {json.dumps({'chunk': reply})}\n\n"
        confidence = compute_confidence(has_error=False, ungrounded_count=0, sources_used=sources)
        yield f"data: {json.dumps({'confidence': confidence, 'ungrounded': []})}\n\n"
        yield "data: [DONE]\n\n"
        return

    # See run_cascade() for the full rationale — same bypass, streaming form.
    if intent == IntentType.GOAL and tool_data.get("needs_clarification"):
        reply = _goal_clarification_reply(tool_data)
        yield f"data: {json.dumps({'chunk': reply})}\n\n"
        yield f"data: {json.dumps({'confidence': None, 'ungrounded': []})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if intent == IntentType.WHATIF and tool_data.get("needs_clarification"):
        available = tool_data.get("available_interventions") or []
        listed = ", ".join(available[:8]) if available else "the interventions shown on this page"
        reply = (
            "I couldn't confidently match those to real intervention names on this page. "
            f"Could you name them directly? For example: {listed}."
        )
        yield f"data: {json.dumps({'chunk': reply})}\n\n"
        yield f"data: {json.dumps({'confidence': None, 'ungrounded': []})}\n\n"
        yield "data: [DONE]\n\n"
        return

    full_text_parts: List[str] = []
    try:
        async for chunk in _stream_llm(SYSTEM_PROMPT, user_prompt, request.history):
            full_text_parts.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    except LLMUnavailable as e:
        fallback = _deterministic_reply_fallback(intent, tool_data)
        if fallback:
            note = (
                "\n\n_(Gemini is rate-limited right now, so this reply is templated directly "
                "from the calculation engine's numbers instead of AI-narrated — the numbers "
                "themselves are unaffected. Try again shortly for normal AI responses.)_"
                if e.is_rate_limit else
                "\n\n_(AI narration is unavailable, so this reply is templated directly from "
                "the calculation engine — the numbers themselves are unaffected.)_"
            )
            reply = fallback + note
        else:
            reply = _llm_unavailable_message(e)
        full_text_parts.append(reply)
        yield f"data: {json.dumps({'chunk': reply})}\n\n"

    # Post-stream grounding check — runs once on the full accumulated
    # reply, since numbers can span chunk boundaries mid-stream. Emitted
    # as its own event so the UI can show a confidence/warning badge
    # without having to re-parse the whole conversation.
    full_reply = "".join(full_text_parts)
    allowed = collect_allowed_numbers(tool_data)
    ungrounded = find_ungrounded_numbers(full_reply, allowed) if allowed else []
    confidence = compute_confidence(
        has_error=bool(tool_data.get("error")),
        ungrounded_count=len(ungrounded),
        sources_used=sources,
    )
    yield f"data: {json.dumps({'confidence': confidence, 'ungrounded': ungrounded})}\n\n"

    yield "data: [DONE]\n\n"