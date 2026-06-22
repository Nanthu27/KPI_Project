"""
services/vector_store.py  — HYBRID SEARCH (Dense + BM25 Sparse)
────────────────────────────────────────────────────────────────
Every vector stored in Pinecone now carries TWO components:
  • values        — 1536-d dense embedding (semantic understanding)
  • sparse_values — BM25 token scores     (keyword / exact-match recall)

At query time, Pinecone combines them:
  final_score = α × dense_score + (1-α) × sparse_score

Alpha (α) blending:
  α = 1.0 → pure semantic (cross-lingual, synonym-aware)
  α = 0.0 → pure keyword  (abbreviations, IDs, exact names)
  α = 0.6 → default balanced (recommended starting point)

IMPORTANT: Pinecone hybrid search REQUIRES metric="dotproduct".
  If your existing index uses "cosine", ensure_index() will
  detect this and print a warning — you must delete the index
  manually in the Pinecone console and re-run ingest.py once.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from pinecone import Pinecone, ServerlessSpec

from .rag_settings import settings
from .document_loader import DocumentChunk
from .embedder import embed_query, embed_texts
from .bm25_encoder import (
    BM25Model,
    build_bm25_model,
    get_bm25_model,
    set_bm25_model,
)

# Default dense/sparse blend
_DEFAULT_ALPHA: float = 0.6

_pc:    Pinecone | None = None
_index                  = None


def _get_pinecone() -> Pinecone:
    global _pc
    if _pc is None:
        if not settings.PINECONE_API_KEY:
            raise RuntimeError("PINECONE_API_KEY is not set in .env")
        _pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    return _pc


def _get_index():
    global _index
    if _index is None:
        _index = _get_pinecone().Index(settings.PINECONE_INDEX_NAME)
    return _index


# ── Index management ──────────────────────────────────────────────────────────

def ensure_index() -> None:
    """
    Create the Pinecone index (dotproduct metric, required for hybrid search).
    If an existing index uses cosine, prints a migration warning.
    """
    pc       = _get_pinecone()
    existing = {idx.name: idx for idx in pc.list_indexes()}

    if settings.PINECONE_INDEX_NAME in existing:
        idx  = existing[settings.PINECONE_INDEX_NAME]
        metric = getattr(idx, "metric", "unknown")
        if metric != "dotproduct":
            print(
                f"\n  ⚠️  WARNING: Index '{settings.PINECONE_INDEX_NAME}' uses metric='{metric}'.\n"
                f"     Hybrid search requires 'dotproduct'.\n"
                f"     To fix: delete the index in Pinecone console, then re-run ingest.py.\n"
                f"     For now, falling back to dense-only search.\n"
            )
        else:
            print(f"  ✅ Pinecone index '{settings.PINECONE_INDEX_NAME}' ready (dotproduct).")
        return

    print(f"  Creating Pinecone index '{settings.PINECONE_INDEX_NAME}' (dotproduct) …")
    pc.create_index(
        name      = settings.PINECONE_INDEX_NAME,
        dimension = settings.EMBEDDING_DIM,
        metric    = "dotproduct",
        spec      = ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    for _ in range(30):
        desc = pc.describe_index(settings.PINECONE_INDEX_NAME)
        if desc.status.get("ready"):
            print("  ✅ Index ready.")
            return
        print("  ⏳ Waiting …")
        time.sleep(5)
    raise TimeoutError("Index not ready within 150 s.")


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_chunks(chunks: List[DocumentChunk], batch_size: int = 50) -> None:
    """
    Embed all chunks (dense) and compute BM25 sparse vectors,
    then upsert both into Pinecone.
    """
    index  = _get_index()
    texts  = [c.text for c in chunks]

    # Build + save BM25 model from the ingest corpus
    bm25 = build_bm25_model(texts)
    bm25.save()
    set_bm25_model(bm25)

    print(f"  🔢 Embedding {len(texts)} chunks (dense) …")
    dense_vecs = embed_texts(texts)

    records: List[dict] = []
    for chunk, dense in zip(chunks, dense_vecs):
        doc_len     = len(chunk.text.split())
        sparse_dict = bm25.encode_document(chunk.text, doc_len)

        if sparse_dict:
            indices = list(sparse_dict.keys())
            values  = [sparse_dict[i] for i in indices]
        else:
            indices, values = [0], [0.0]

        records.append({
            "id":     chunk.chunk_id,
            "values": dense,
            "sparse_values": {"indices": indices, "values": values},
            "metadata": {**chunk.metadata, "text": chunk.text},
        })

    print(f"  📤 Upserting {len(records)} hybrid vectors …")
    for i in range(0, len(records), batch_size):
        batch = records[i: i + batch_size]
        index.upsert(vectors=batch)
        print(f"      {min(i + batch_size, len(records))}/{len(records)} uploaded")

    print("  ✅ Hybrid upsert complete.")


# ── Query ─────────────────────────────────────────────────────────────────────

def query_similar(
    query:  str,
    top_k:  int   = settings.TOP_K_RESULTS,
    alpha:  float = _DEFAULT_ALPHA,
) -> List[dict]:
    """
    Hybrid Vector + BM25 retrieval.

    Semantic understanding example:
      query "automobile repair" → retrieves "car maintenance" via dense vector.

    Exact-match example:
      query "Chennai diagnostic center" → BM25 boosts exact token matches.

    Cross-lingual example:
      query "congé annuel" (French) → dense embedding bridges to English "annual leave".

    Cross-concept example (synonym expansion):
      query "hospitals city wise" → BM25 synonym table adds "diagnostic", "center"
      tokens so tabular rows about diagnostic centers are recalled.
    """
    index    = _get_index()
    bm25     = get_bm25_model()
    dense_v  = embed_query(query)

    sparse_q: Optional[dict] = None
    if bm25 is not None:
        sd = bm25.encode_query(query)  # includes synonym expansion
        if sd:
            sparse_q = {
                "indices": list(sd.keys()),
                "values":  [sd[i] for i in sd.keys()],
            }

    kwargs: dict = {
        "vector":           dense_v,
        "top_k":            top_k,
        "include_metadata": True,
    }
    if sparse_q:
        kwargs["sparse_vector"] = sparse_q
        kwargs["alpha"]         = alpha

    response = index.query(**kwargs)

    return [
        {
            "id":       m.id,
            "score":    round(m.score, 4),
            "text":     (m.metadata or {}).get("text", ""),
            "source":   (m.metadata or {}).get("source", "unknown"),
            "metadata": {k: v for k, v in (m.metadata or {}).items() if k != "text"},
        }
        for m in response.matches
    ]


# ── Utility ───────────────────────────────────────────────────────────────────

def get_index_stats() -> dict:
    return _get_index().describe_index_stats()
