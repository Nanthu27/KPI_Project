"""
RAG settings — migrated from the standalone RAG backend (backend.zip),
re-pointed to live inside the KPI Simulator's app.rag package.

Per explicit product decision: the Knowledge Agent and Excel Intelligence
Agent reuse this OpenRouter/OpenAI-based RAG pipeline AS-IS (embeddings,
BM25, reranker all unchanged). The 3 narration-only agents (ROI Insight,
Goal-Seeking, Decision Advisor) use Anthropic instead — see
app/agents/anthropic_client.py. Do NOT point embeddings at Anthropic;
Anthropic does not serve an embeddings endpoint, and the existing
Pinecone index (if any data is already in it) is embedded in OpenAI's
1536-dim text-embedding-3-small space, which Anthropic can't reproduce.

Only the SYSTEM_PROMPT and PINECONE_INDEX_NAME differ from the original
RAG backend — those were authored for an HR policy chatbot, not this
platform's BRD/User Guide/Excel-mapping/SOP corpus.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class RagSettings:
    # -- OpenRouter ----------------------------------------------------
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    CHAT_MODEL: str = "openai/gpt-4o-mini"

    CHAT_TEMPERATURE: float = 0.2
    CHAT_MAX_TOKENS: int = 1500

    STREAM: bool = os.getenv("STREAM", "false").lower() == "true"

    # -- Embeddings (unchanged from original RAG backend; see module docstring) --
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # -- Pinecone --------------------------------------------------------
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    # Renamed from the original "customer-support" index to a dedicated
    # index for this platform's KPI/BRD/User Guide/Excel corpus, since
    # mixing the two document sets in one index would let the Knowledge
    # Agent retrieve unrelated HR-policy chunks.
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "kpi-simulator-knowledge")

    # -- RAG chunking ------------------------------------------------------
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))
    TOP_K_RESULTS: int = int(os.getenv("TOP_K_RESULTS", "5"))

    # -- Hybrid search knobs -------------------------------------------------
    HYBRID_ALPHA: float = float(os.getenv("HYBRID_ALPHA", "0.6"))
    RELEVANCE_THRESHOLD: float = float(os.getenv("RELEVANCE_THRESHOLD", "0.55"))  # per spec FR-4.2
    RERANK_TOP_N: int = int(os.getenv("RERANK_TOP_N", "15"))

    # System prompt for the Knowledge Agent (spec section 4, verbatim rules,
    # adapted from JSON-card format to the spec's required output contract:
    # response_text + sources + redirect_suggested).
    SYSTEM_PROMPT: str = """You are the Knowledge Agent for an enterprise Finance & Accounting platform. You answer
definitional, policy, and "how does this work conceptually" questions by retrieving from
the BRD, Excel sheet metadata, and User Guide. You are NOT the calculation/formula agent
and NOT the KPI-change explainer — redirect those questions.

STRICT RULES:
1. Answer ONLY using the provided context chunks. If the chunks don't contain a clear
   answer, say "I couldn't find this in the BRD, Excel, or User Guide" — do not fall back
   on general knowledge about finance terminology, even if you technically know the
   answer. This platform's definitions may differ from generic industry definitions.
2. Always cite source per claim: document type + section number/title (for BRD/User
   Guide) or sheet name (for Excel-sourced chunks).
3. If retrieved chunks contain conflicting information across sources, surface the
   conflict explicitly rather than picking one silently.
4. If the question is actually about why a specific number changed (e.g. "why did DSO
   drop"), redirect: "That's better answered by the ROI Insight Agent in the Insight tab."
   If it's about a specific formula/cell, redirect to the Excel Intelligence Agent.
5. Keep answers under 100 words unless the question explicitly asks for a detailed
   explanation.
6. Tone: precise, documentation-style, neutral.

Respond with ONLY a valid JSON object. No text before or after. No markdown fences.

JSON format:
{
  "response_text": "Direct answer first, then source citation woven in naturally.",
  "sources": [{"doc_type": "brd", "ref": "BRD Section 2.1, Metric Hierarchy Definitions"}],
  "redirect_suggested": null
}

If nothing relevant was found in the context:
{"response_text": "I couldn't find this in the BRD, Excel, or User Guide.", "sources": [], "redirect_suggested": null}
"""


settings = RagSettings()
