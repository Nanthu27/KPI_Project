"""
Cascade AI Configuration
------------------------
All settings for the AI layer. Copy backend/.env.example → backend/.env and fill in keys.

LLM:   Google Gemini (free tier available)  →  https://aistudio.google.com/apikey
         Recommended models:
           gemini-2.5-flash        ← balanced quality + speed (default)
           gemini-2.5-flash-lite   ← fastest, lower quality (used as fallback)

Vector DB: Pinecone (free tier: 1 index, 100k vectors)  →  https://app.pinecone.io
            OPTIONAL — BM25 works without it.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    # Load from backend/.env (two directories up from this file)
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass


@dataclass
class AIConfig:
    # ── Google Gemini LLM ────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash-lite"

    # ── Pinecone Vector DB (optional) ────────────────────────────────────
    pinecone_api_key: str = ""
    pinecone_index_name: str = "kpi-cascade-dev"
    pinecone_environment: str = "gcp-starter"

    # ── RAG Settings ─────────────────────────────────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"   # local, no API key needed
    rag_top_k: int = 5
    bm25_top_k: int = 10
    hybrid_alpha: float = 0.6    # 0.0 = pure BM25, 1.0 = pure vector

    # ── Streaming ────────────────────────────────────────────────────────
    stream_enabled: bool = True

    # ── Document paths (for RAG ingestion) ───────────────────────────────
    docs_dir: str = str(Path(__file__).resolve().parents[2] / "docs")

    @classmethod
    def from_env(cls) -> "AIConfig":
        return cls(
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            gemini_fallback_model=os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite"),
            pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
            pinecone_index_name=os.getenv("PINECONE_INDEX", "kpi-cascade-dev"),
            pinecone_environment=os.getenv("PINECONE_ENV", "gcp-starter"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
            rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
            bm25_top_k=int(os.getenv("BM25_TOP_K", "10")),
            hybrid_alpha=float(os.getenv("HYBRID_ALPHA", "0.6")),
            stream_enabled=os.getenv("STREAM_ENABLED", "true").lower() == "true",
        )


_config: Optional[AIConfig] = None


def get_ai_config() -> AIConfig:
    global _config
    if _config is None:
        _config = AIConfig.from_env()
    return _config
