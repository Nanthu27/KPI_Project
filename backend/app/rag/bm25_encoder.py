"""
services/bm25_encoder.py
─────────────────────────
Pure-Python multilingual BM25 implementation.

Features:
  • Multilingual tokenization — handles Latin, Devanagari, CJK,
    Tamil, Arabic etc. using Unicode character categories (no NLTK needed).
  • Synonym / concept expansion table so queries like
    "hospital" match "diagnostic center" and vice-versa (cross-concept retrieval).
  • Saved to disk as JSON after ingest; loaded back on startup.
  • No external ML dependencies — stdlib only.

BM25 Okapi formula:
  IDF(t) = log((N - df + 0.5) / (df + 0.5) + 1)
  TF_norm = freq * (K1 + 1) / (freq + K1 * (1 - B + B * |d| / avgdl))
  score(q,d) = Σ IDF(t) * TF_norm(t, d)
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── BM25 Hyperparameters ──────────────────────────────────────────────────────
K1: float = 1.5   # term-frequency saturation
B:  float = 0.75  # length normalisation

# ── Storage path ──────────────────────────────────────────────────────────────
_MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / ".bm25_model"

# ── Concept-synonym expansion table ──────────────────────────────────────────
# Maps any query token to a list of related tokens already present in the KB.
# Populated here for the Teleperformance use-case; expand as needed.
# The key IS NOT a hard-coded filter — it is used only to BOOST BM25 recall
# by adding synonymous tokens to the query sparse vector.
SYNONYM_MAP: Dict[str, List[str]] = {
    # medical-facility synonyms
    "hospital":         ["diagnostic", "center", "centre", "clinic", "health", "medical"],
    "clinic":           ["diagnostic", "center", "centre", "hospital", "health"],
    "medical":          ["diagnostic", "center", "centre", "hospital", "clinic", "health"],
    "healthcare":       ["diagnostic", "center", "centre", "hospital", "clinic"],
    # leave synonyms
    "vacation":         ["leave", "annual", "paid"],
    "holiday":          ["leave", "annual", "paid"],
    "congé":            ["leave", "annual", "paid"],           # French
    "छुट्टी":           ["leave", "annual"],                   # Hindi
    "விடுப்பு":         ["leave", "annual"],                   # Tamil
    # salary synonyms
    "salary":           ["pay", "compensation", "remuneration", "ctc"],
    "wage":             ["salary", "pay", "compensation"],
    "pay":              ["salary", "compensation"],
    "rémunération":     ["salary", "pay"],                      # French
    # work-time synonyms
    "office":           ["working", "hours", "attendance", "shift"],
    "timing":           ["working", "hours", "attendance", "shift"],
    # gratuity synonyms
    "retirement":       ["gratuity", "provident", "pf"],
    "severance":        ["gratuity"],
    "indemnité":        ["gratuity"],                           # French
    # recruitment synonyms
    "hiring":           ["recruitment", "onboarding", "joining"],
    "joining":          ["recruitment", "onboarding", "hiring"],
}


# ── Tokeniser ─────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """
    Language-agnostic tokeniser.
    • Lowercases.
    • Splits on whitespace and most punctuation.
    • Keeps digits (PIN codes, phone numbers).
    • Keeps sequences of non-Latin scripts intact (Tamil, Hindi, Arabic, CJK…).
    """
    text = text.lower()
    # Insert spaces around punctuation, but NOT around hyphens or dots in numbers
    text = re.sub(r"[^\w\s\-\.]", " ", text, flags=re.UNICODE)
    # Split digit-letter boundaries (e.g. "600001chennai" → "600001 chennai")
    text = re.sub(r"(\d)([^\d\s])", r"\1 \2", text)
    text = re.sub(r"([^\d\s])(\d)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = text.split()
    # Keep tokens with at least 2 characters OR single digits
    return [t for t in tokens if len(t) >= 2 or t.isdigit()]


def _expand_query_tokens(tokens: List[str]) -> List[str]:
    """Add synonym tokens to query for cross-concept retrieval."""
    expanded = list(tokens)
    for tok in tokens:
        for syn in SYNONYM_MAP.get(tok, []):
            if syn not in expanded:
                expanded.append(syn)
    return expanded


# ── BM25 Model ────────────────────────────────────────────────────────────────

class BM25Model:
    def __init__(
        self,
        vocab:     Dict[str, int],
        idf:       Dict[int, float],
        avgdl:     float,
        doc_count: int,
    ) -> None:
        self.vocab     = vocab
        self.idf       = idf
        self.avgdl     = avgdl
        self.doc_count = doc_count

    # ── Sparse vectors ────────────────────────────────────────────────────────

    def encode_query(self, query: str) -> Dict[int, float]:
        """
        Return {token_index: idf_score} for query tokens.
        Includes synonym expansion for cross-concept retrieval.
        """
        raw_tokens = _tokenize(query)
        tokens     = _expand_query_tokens(raw_tokens)
        sparse: Dict[int, float] = {}
        for token in tokens:
            idx = self.vocab.get(token)
            if idx is not None and idx in self.idf:
                sparse[idx] = sparse.get(idx, 0.0) + self.idf[idx]
        return sparse

    def encode_document(self, text: str, doc_len: int) -> Dict[int, float]:
        """Return {token_index: bm25_score} for a document chunk."""
        tokens = _tokenize(text)
        tf_map = Counter(tokens)
        sparse: Dict[int, float] = {}
        for token, freq in tf_map.items():
            idx = self.vocab.get(token)
            if idx is None or idx not in self.idf:
                continue
            idf = self.idf[idx]
            tf_norm = (freq * (K1 + 1)) / (
                freq + K1 * (1 - B + B * doc_len / max(self.avgdl, 1))
            )
            sparse[idx] = round(idf * tf_norm, 6)
        return sparse

    # ── Serialisation ─────────────────────────────────────────────────────────

    def save(self, path: Path = _MODEL_DIR) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "vocab.json").write_text(
            json.dumps(self.vocab, ensure_ascii=False), encoding="utf-8"
        )
        (path / "idf.json").write_text(
            json.dumps({str(k): v for k, v in self.idf.items()}), encoding="utf-8"
        )
        (path / "meta.json").write_text(
            json.dumps({"avgdl": self.avgdl, "doc_count": self.doc_count}),
            encoding="utf-8",
        )
        print(f"  💾 BM25 model saved ({len(self.vocab):,} tokens, avgdl={self.avgdl:.1f})")

    @classmethod
    def load(cls, path: Path = _MODEL_DIR) -> Optional["BM25Model"]:
        try:
            vocab   = json.loads((path / "vocab.json").read_text(encoding="utf-8"))
            idf_raw = json.loads((path / "idf.json").read_text(encoding="utf-8"))
            idf     = {int(k): v for k, v in idf_raw.items()}
            meta    = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            return cls(vocab=vocab, idf=idf, avgdl=meta["avgdl"], doc_count=meta["doc_count"])
        except Exception:
            return None


# ── Builder ───────────────────────────────────────────────────────────────────

def build_bm25_model(texts: List[str]) -> BM25Model:
    print(f"  📖 Building BM25 index over {len(texts)} chunks …")
    tokenized = [_tokenize(t) for t in texts]

    # Vocabulary: sorted for deterministic indices
    all_tokens: set[str] = set()
    for toks in tokenized:
        all_tokens.update(toks)
    vocab: Dict[str, int] = {tok: i for i, tok in enumerate(sorted(all_tokens))}

    # Document frequency
    df: Dict[int, int] = {}
    for toks in tokenized:
        for tok in set(toks):
            idx = vocab[tok]
            df[idx] = df.get(idx, 0) + 1

    N     = len(tokenized)
    avgdl = sum(len(t) for t in tokenized) / max(N, 1)

    idf: Dict[int, float] = {
        idx: round(math.log((N - freq + 0.5) / (freq + 0.5) + 1), 6)
        for idx, freq in df.items()
    }
    print(f"  ✅ Vocab: {len(vocab):,} tokens | avgdl: {avgdl:.1f}")
    return BM25Model(vocab=vocab, idf=idf, avgdl=avgdl, doc_count=N)


# ── Singleton ─────────────────────────────────────────────────────────────────

_model: Optional[BM25Model] = None


def get_bm25_model() -> Optional[BM25Model]:
    global _model
    if _model is None:
        _model = BM25Model.load()
    return _model


def set_bm25_model(model: BM25Model) -> None:
    global _model
    _model = model
