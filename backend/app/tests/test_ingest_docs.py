import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.scripts import ingest_docs


def test_main_exits_cleanly_when_pinecone_key_is_missing(monkeypatch):
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.delenv("PINECONE_INDEX", raising=False)
    monkeypatch.setattr(ingest_docs, "load_env", lambda: None)
    monkeypatch.setattr(ingest_docs, "load_builtin_knowledge", lambda: [])
    monkeypatch.setattr(ingest_docs, "load_brd_docx", lambda: [])
    monkeypatch.setattr(ingest_docs, "load_excel_metadata", lambda: [])

    result = ingest_docs.main()

    assert result == 0


def test_ingest_to_pinecone_skips_when_sentence_transformers_is_unavailable(monkeypatch):
    import builtins
    import types

    monkeypatch.setattr(ingest_docs, "load_env", lambda: None)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("sentence_transformers"):
            raise OSError("simulated missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    class FakePineconeIndex:
        def describe_index_stats(self):
            return {"dimension": 384}

        def upsert(self, vectors):
            return None

    class FakePineconeClient:
        def __init__(self, api_key):
            self.api_key = api_key

        def list_indexes(self):
            return []

        def create_index(self, **kwargs):
            return None

        def Index(self, name):
            return FakePineconeIndex()

    pinecone_stub = types.ModuleType("pinecone")
    pinecone_stub.Pinecone = FakePineconeClient
    pinecone_stub.ServerlessSpec = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "pinecone", pinecone_stub)

    result = ingest_docs.ingest_to_pinecone([{"id": "1", "content": "hello", "metadata": {}}], "dummy-key", "dummy-index", "all-MiniLM-L6-v2")

    assert result is True
