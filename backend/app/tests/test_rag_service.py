"""
Regression test for a real bug found while smoke-testing the deployed
Cascade: calling POST /api/cascade/ingest in an environment with no
docs/ directory (the default state of this project — no docs/ folder
exists anywhere) wiped RagService._documents to [] and never restored
the built-in KPI knowledge base, causing BM25Okapi to divide by zero on
an empty corpus. Worse, the exception was swallowed by the background
task's try/except, but _ensure_initialized() still set
self._initialized = True before the crash unwound, so EVERY subsequent
/chat call hit the same already-broken (bm25=None) state until the
process restarted.

Fixed by:
  1. RagService.reset_for_reingest() restores the built-in knowledge
     base before clearing _initialized, instead of the route directly
     setting self._documents = [].
  2. _ensure_initialized() falls back to the built-in knowledge if
     _load_documents() leaves self._documents empty, and only sets
     self._initialized = True if a usable BM25 index actually exists.
  3. BM25Retriever itself guards against an empty document list.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.services.rag_service import RagService, BM25Retriever, BUILTIN_KPI_KNOWLEDGE


def test_bm25_retriever_handles_empty_corpus_without_crashing():
    retriever = BM25Retriever([])
    assert retriever.bm25 is None
    assert retriever.search("anything") == []


def test_ensure_initialized_falls_back_to_builtin_knowledge_when_docs_dir_missing():
    rag = RagService()
    # Simulate the exact bug trigger: no docs/ directory exists in this
    # deployment, so _load_documents() is a no-op and must not be allowed
    # to leave self._documents empty.
    rag.config.docs_dir = "/path/does/not/exist"
    rag._ensure_initialized()

    assert rag._documents, "RagService must never end up with zero documents after initialization"
    assert rag._bm25 is not None
    assert rag._bm25.bm25 is not None
    assert rag._initialized is True


def test_reset_for_reingest_restores_builtin_knowledge_before_reinitializing():
    rag = RagService()
    rag.config.docs_dir = "/path/does/not/exist"
    rag._ensure_initialized()
    assert len(rag._documents) == len(BUILTIN_KPI_KNOWLEDGE)

    # This is what the old buggy code effectively did manually (rag._documents = []);
    # reset_for_reingest() must not leave the service in that broken state.
    rag.reset_for_reingest()
    assert rag._documents == list(BUILTIN_KPI_KNOWLEDGE)
    assert rag._initialized is False

    # And re-initializing after a reset must succeed cleanly, not crash.
    rag._ensure_initialized()
    assert rag._bm25 is not None
    assert rag._bm25.bm25 is not None
    assert rag._initialized is True


def test_chat_still_works_after_a_failed_ingest_with_no_docs_dir(monkeypatch):
    """
    End-to-end regression: simulates the exact sequence that broke
    production — an /ingest call in an environment with no docs/ folder —
    and verifies a subsequent search still returns real results instead
    of silently returning nothing (the symptom before this fix; the raw
    crash would have surfaced as a 500/error field upstream).
    """
    rag = RagService()
    rag.config.docs_dir = "/path/does/not/exist"

    # First "ingest" attempt (mirrors the route's _run_ingestion()).
    rag.reset_for_reingest()
    rag._ensure_initialized()

    results = rag._bm25.search("DSO Days Sales Outstanding")
    assert len(results) > 0, "BM25 search must return real results after an ingest cycle with no docs/ directory"
