"""
RAG Service — Hybrid BM25 + Vector Search
-------------------------------------------
IMPORTANT: BUILTIN_KPI_KNOWLEDGE is generic fallback documentation about KPI concepts
in general. It is labeled with metadata source="generic_fallback" so the LLM knows
not to use these Finance-specific names (DSO, RPA, etc.) when answering questions about
the user's actual metrics.

The LLM prompt (SYSTEM_PROMPT + format_knowledge_prompt) instructs Claude to ONLY answer
from pageContext (live data) when the user asks "why did X change?" — the knowledge tool
is only for definitional questions ("what is a KPI?", "how does the hierarchy work?").
"""
import hashlib
import math
import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RagDocument:
    content: str
    metadata: Dict[str, Any]
    score: float = 0.0


# ---------------------------------------------------------------------------
# Generic KPI concept documentation — NOT Finance-specific
# Labeled as generic_fallback so LLM knows not to use these names for user data
# ---------------------------------------------------------------------------
BUILTIN_KPI_KNOWLEDGE = [
    {
        "id": "kpi_hierarchy_concept",
        "content": (
            "The KPI Simulator uses a 4-level hierarchy: Intervention → L2 Metric → L1 Metric → Business Outcome. "
            "Impact flows downward: changing an Intervention slider causes L2 Metrics to change, which cascades "
            "into L1 Metrics, which then affects Business Outcomes. "
            "Each relationship has an Impact Factor (a decimal number) that determines how strongly one level affects another."
        ),
        "metadata": {"source": "generic_fallback", "category": "architecture", "name": "KPI Hierarchy"},
    },
    {
        "id": "formula_cascade",
        "content": (
            "KPI Cascade Calculation — how the simulator computes new values:\n"
            "Step 1 (Intervention → L2): change_fraction = (impact_factor × slider_pct) / 100 / 100\n"
            "  Note: slider stores integer percent (11 means 11%), so divide by 100 twice.\n"
            "Step 2 (L2 → L1): change_fraction = impact_factor × l2_total_change_fraction\n"
            "Step 3 (L1 → BO): change_fraction = impact_factor × l1_total_change_fraction\n"
            "New Value = Default Value × (1 + total_change_fraction)\n"
            "Improvement % = total_change_fraction × 100"
        ),
        "metadata": {"source": "generic_fallback", "category": "formula", "name": "Cascade Formula"},
    },
    {
        "id": "impact_factor_concept",
        "content": (
            "Impact Factor is a coefficient showing how strongly one KPI level affects the next. "
            "It is a decimal value (e.g. 0.7 means 70% pass-through, -0.35 means 35% inverse relationship). "
            "A negative impact factor means: when the upstream metric increases, the downstream metric decreases. "
            "Impact factors are configured in the Excel relationship sheet and stored in the database."
        ),
        "metadata": {"source": "generic_fallback", "category": "formula", "name": "Impact Factor"},
    },
    {
        "id": "what_is_intervention",
        "content": (
            "An Intervention in the KPI Simulator is a business or technology initiative whose adoption level "
            "is controlled by a slider (0-100%). Increasing the slider simulates increasing deployment of that "
            "initiative. The intervention connects to one or more L2 Metrics via impact factors, causing those "
            "metrics to change when the slider moves."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "Intervention"},
    },
    {
        "id": "what_is_l2",
        "content": (
            "L2 Metrics are the second level in the KPI hierarchy, directly impacted by Intervention sliders. "
            "They represent operational or process-level measurements. Each L2 Metric can receive contributions "
            "from multiple Interventions. L2 Metrics cascade their changes into L1 Metrics."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "L2 Metric"},
    },
    {
        "id": "what_is_l1",
        "content": (
            "L1 Metrics sit between L2 Metrics and Business Outcomes in the KPI hierarchy. "
            "They aggregate changes from multiple L2 Metrics using their respective impact factors. "
            "L1 Metrics cascade their total change into Business Outcomes."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "L1 Metric"},
    },
    {
        "id": "what_is_business_outcome",
        "content": (
            "Business Outcomes are the top-level results the organisation cares about in the KPI Simulator. "
            "They receive cascaded changes from L1 Metrics. Business Outcomes cannot cascade further — they "
            "are the final output of the simulation. Their improvement_percentage shows the total impact of "
            "all active interventions."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "Business Outcome"},
    },
    {
        "id": "slider_rules",
        "content": (
            "Slider Interaction Rules in the KPI Simulator:\n"
            "- Dragging an Intervention slider → recalculates all linked L2, then L1, then Business Outcomes\n"
            "- Dragging an L2 slider → recalculates linked L1 and Business Outcomes (does not update Intervention)\n"
            "- Dragging an L1 slider → recalculates linked Business Outcomes only\n"
            "- Dragging a Business Outcome slider → updates only that card (no downstream propagation)\n"
            "- Slider changes are NEVER saved to the database automatically. Only 'Save'/'Apply' actions persist."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "Slider Rules"},
    },
    {
        "id": "excel_upload",
        "content": (
            "The Excel upload feature lets administrators import metric configurations. "
            "The Excel file should contain sheets for: Business Outcomes, L1 Metrics, L2 Metrics, Interventions, "
            "and Relationship Mappings. The Relationship Mapping sheet defines Impact Factors between levels. "
            "After upload, the system validates the data, stores nodes, and builds the dependency graph."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "Excel Upload"},
    },
    {
        "id": "higher_is_better",
        "content": (
            "Each metric in the KPI Simulator has a 'Higher is Better' flag. "
            "If higher_is_better=True: an upward change (positive improvement_pct) is good (shown in green). "
            "If higher_is_better=False: a downward change (negative improvement_pct) is good — like reducing "
            "cycle time or reducing error rate. The color of the improvement arrow reflects this flag."
        ),
        "metadata": {"source": "generic_fallback", "category": "concept", "name": "Higher is Better"},
    },
]


class BM25Retriever:
    def __init__(self, documents: List[Dict]):
        self._docs = documents
        self._bm25 = None
        if not documents:
            return
        try:
            from rank_bm25 import BM25Okapi
            tokenized = [d["content"].lower().split() for d in documents]
            self._bm25 = BM25Okapi(tokenized)
        except ImportError:
            logger.warning("rank-bm25 not installed. Run: pip install rank-bm25")

    @property
    def bm25(self):
        return self._bm25

    def search(self, query: str, k: int = 8) -> List[RagDocument]:
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [
            RagDocument(content=self._docs[i]["content"],
                        metadata=self._docs[i]["metadata"],
                        score=float(scores[i]))
            for i in top if scores[i] > 0
        ]


class LocalVectorRetriever:
    def __init__(self, documents: List[Dict], dimension: int = 384):
        self._docs = documents
        self._dim = dimension
        self._embeddings = [self._embed(d.get("content", "")) for d in documents]

    def _embed(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dim
        tokens = re.findall(r"[a-z0-9]+", text, flags=re.IGNORECASE)
        vec = [0.0] * self._dim
        for token in tokens:
            digest = hashlib.blake2b(token.lower().encode(), digest_size=8).digest()
            idx = int.from_bytes(digest[:2], "big") % self._dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm > 0 else vec

    def _cosine(self, a, b) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query: str, k: int = 8) -> List[RagDocument]:
        q = self._embed(query)
        scored = [(self._cosine(q, emb), doc) for doc, emb in zip(self._docs, self._embeddings)]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            RagDocument(content=doc.get("content", ""), metadata=doc.get("metadata", {}), score=s)
            for s, doc in scored[:k] if s > 0
        ]


class RagService:
    def __init__(self):
        from ..config import get_ai_config
        self.config = get_ai_config()
        self._documents: List[Dict] = list(BUILTIN_KPI_KNOWLEDGE)
        self._bm25: Optional[BM25Retriever] = None
        self._local_vec: Optional[LocalVectorRetriever] = None
        self._pinecone_index = None
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        if not self._documents:
            self._documents = list(BUILTIN_KPI_KNOWLEDGE)
        self._load_local_docs()
        if not self._documents:
            self._documents = list(BUILTIN_KPI_KNOWLEDGE)
        self._bm25 = BM25Retriever(self._documents)
        self._local_vec = LocalVectorRetriever(self._documents)
        self._try_pinecone()
        self._initialized = True
        logger.info(f"RAG ready: {len(self._documents)} docs, pinecone={'yes' if self._pinecone_index else 'no'}")

    def reset_for_reingest(self):
        self._documents = list(BUILTIN_KPI_KNOWLEDGE)
        self._bm25 = None
        self._local_vec = None
        self._pinecone_index = None
        self._initialized = False

    def _load_local_docs(self):
        docs_path = Path(self.config.docs_dir)
        if not docs_path.exists():
            return
        for fp in docs_path.glob("**/*"):
            if fp.suffix in {".txt", ".md"}:
                try:
                    text = fp.read_text(encoding="utf-8")
                    chunks = self._chunk(text, fp.name)
                    self._documents.extend(chunks)
                except Exception as e:
                    logger.warning(f"Failed to load {fp}: {e}")
            elif fp.suffix == ".json":
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        self._documents.extend(data)
                except Exception as e:
                    logger.warning(f"Failed to load {fp}: {e}")

    def _chunk(self, text, source, chunk_size=500, overlap=50) -> List[Dict]:
        words = text.split()
        step = chunk_size - overlap
        chunks = []
        for i in range(0, len(words), step):
            chunk = " ".join(words[i: i + chunk_size])
            if len(chunk.strip()) > 60:
                chunks.append({
                    "id": f"{source}_{i // step}",
                    "content": chunk,
                    "metadata": {"source": source, "chunk_index": i // step},
                })
        return chunks

    def _try_pinecone(self):
        if not self.config.pinecone_api_key:
            return
        try:
            from pinecone import Pinecone
            pc = Pinecone(api_key=self.config.pinecone_api_key)
            existing = [idx.name for idx in pc.list_indexes()]
            if self.config.pinecone_index_name in existing:
                self._pinecone_index = pc.Index(self.config.pinecone_index_name)
                logger.info(f"Pinecone connected: {self.config.pinecone_index_name}")
        except Exception as e:
            logger.warning(f"Pinecone unavailable: {e}")

    def _pinecone_search(self, query, k) -> List[RagDocument]:
        if not self._pinecone_index:
            return self._local_vec.search(query, k=k) if self._local_vec else []
        try:
            embedding = self._local_vec._embed(query) if self._local_vec else LocalVectorRetriever([])._embed(query)
            results = self._pinecone_index.query(vector=embedding, top_k=k, include_metadata=True)
            return [
                RagDocument(content=m["metadata"].get("content", ""),
                            metadata=m["metadata"], score=m["score"])
                for m in results.get("matches", [])
            ]
        except Exception as e:
            logger.warning(f"Pinecone search failed: {e}")
            return self._local_vec.search(query, k=k) if self._local_vec else []

    def _rrf(self, bm25_results, vec_results, k=60) -> List[RagDocument]:
        alpha = self.config.hybrid_alpha
        scores: Dict[str, float] = {}
        docs_map: Dict[str, RagDocument] = {}
        for rank, doc in enumerate(bm25_results):
            key = doc.content[:120]
            scores[key] = scores.get(key, 0) + (1 - alpha) / (rank + k)
            docs_map[key] = doc
        for rank, doc in enumerate(vec_results):
            key = doc.content[:120]
            scores[key] = scores.get(key, 0) + alpha / (rank + k)
            docs_map[key] = doc
        merged = sorted(scores, key=lambda x: scores[x], reverse=True)
        result = []
        for key in merged[: self.config.rag_top_k]:
            d = docs_map[key]
            d.score = scores[key]
            result.append(d)
        return result

    def search(self, query: str, allowed_terms: Optional[List[str]] = None) -> List[RagDocument]:
        """
        allowed_terms: real KPI/intervention/BO/L1/L2 names from the CURRENT
        page (vertical/LOB). Any retrieved chunk that is not tagged
        "generic_fallback" AND does not mention at least one of these real
        names is dropped before ranking.

        Why: BUILTIN_KPI_KNOWLEDGE is vertical-agnostic (safe, always kept).
        But files loaded from backend/docs/ (BRD.docx, kpi_formula_knowledge.txt)
        are Finance/O2C-specific -- DSO, RPA, Collection Efficiency Rate, etc.
        Nothing in those files is tagged with a vertical, so a query like
        "which interventions impact Revenue Growth?" on a Customer Support
        page matched them anyway on pure keyword/vector similarity and got
        cited back to the user as if they applied to TP Simulation / TP
        Gamification. This is the cross-vertical contamination bug reported:
        Knowledge Agent citing "Collection Efficiency Rate, DSO, IDP, RPA"
        while the page was Customer Support / Back Office.
        """
        self._ensure_initialized()
        bm25 = self._bm25.search(query, k=self.config.bm25_top_k) if self._bm25 else []
        vec = self._pinecone_search(query, k=self.config.rag_top_k)
        merged = self._rrf(bm25, vec) if (bm25 or vec) else []

        if not allowed_terms:
            return merged

        allowed_lower = {t.lower() for t in allowed_terms if t}
        filtered = []
        for doc in merged:
            if doc.metadata.get("source") == "generic_fallback":
                filtered.append(doc)
                continue
            content_lower = doc.content.lower()
            if any(term in content_lower for term in allowed_lower):
                filtered.append(doc)
            # else: silently dropped -- belongs to a different vertical's docs
        return filtered

    def format_context(self, results: List[RagDocument]) -> str:
        if not results:
            return "No specific documentation found for this query."
        parts = []
        for i, doc in enumerate(results, 1):
            src = doc.metadata.get("source", "docs")
            label = f"[Source {i}: {src}]"
            if src == "generic_fallback":
                label += " [Generic KPI concept — not specific to your simulator data]"
            parts.append(f"{label}\n{doc.content.strip()}")
        return "\n\n---\n\n".join(parts)


_rag_service: Optional[RagService] = None


def get_rag_service() -> RagService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagService()
    return _rag_service
