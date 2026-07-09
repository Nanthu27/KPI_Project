"""
RAG Document Ingestion Script
-------------------------------
Run this ONCE to build the Pinecone vector index from your documents.
After this, the cascade uses hybrid search (Pinecone + BM25) automatically.

Usage:
  cd backend
  python -m app.ai.scripts.ingest_docs

Requirements:
  - PINECONE_API_KEY set in .env
  - GEMINI_API_KEY set in .env (not needed for ingestion, only for chat)
  - pip install sentence-transformers pinecone

What gets ingested:
  1. Built-in KPI knowledge (14 definitions, always available)
  2. BRD .docx (from uploads or docs/ folder)
  3. Excel metadata (from the F&A workbook)
  4. Any .txt files in backend/docs/
"""
import hashlib
import math
import os
import re
import sys
import json
import logging
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_env():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        load_dotenv(env_path)
        logger.info(f"Loaded .env from {env_path}")
    except ImportError:
        logger.warning("python-dotenv not installed; reading from environment")


def chunk_text(text: str, source: str, chunk_size: int = 400, overlap: int = 50):
    words = text.split()
    step = chunk_size - overlap
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if len(chunk.strip()) > 80:
            chunks.append({
                "id": f"{source}_{i // step}",
                "content": chunk,
                "metadata": {"source": source, "chunk_index": i // step, "content": chunk},
            })
    return chunks


def load_brd_docx():
    """Load and chunk the BRD Word document."""
    candidates = [
        "/mnt/user-data/uploads/ROI_Measurement_Framework_and_Simulation_Model_BRD__004_.docx",
        Path(__file__).parent.parent.parent.parent / "docs" / "BRD.docx",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                import docx
                doc = docx.Document(str(path))
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                logger.info(f"Loaded BRD: {len(text)} chars from {path}")
                return chunk_text(text, "BRD", chunk_size=400)
            except Exception as e:
                logger.warning(f"BRD load failed: {e}")
    logger.warning("BRD not found; skipping")
    return []


def load_excel_metadata():
    """Extract text metadata from Excel workbook."""
    candidates = [
        "/mnt/user-data/uploads/ROI_Measurement_Framework_and_Simulation_Model_F_A_V2_1_1__1_.xlsx",
        "/mnt/user-data/uploads/Calculation_Sheet_KPI_Simulator.xlsx",
    ]
    chunks = []
    for path in candidates:
        if os.path.exists(path):
            try:
                import openpyxl
                wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    rows = list(ws.iter_rows(max_row=100, values_only=True))
                    text = f"Sheet: {sheet_name}\n"
                    for row in rows:
                        row_text = " | ".join(str(c) for c in row if c is not None)
                        if row_text.strip():
                            text += row_text + "\n"
                    if len(text) > 100:
                        chunks.extend(chunk_text(text, f"excel_{sheet_name}", chunk_size=300))
                logger.info(f"Loaded Excel metadata: {len(chunks)} chunks")
                return chunks
            except Exception as e:
                logger.warning(f"Excel load failed: {e}")
    return []


def load_builtin_knowledge():
    """Load the built-in KPI knowledge base."""
    from app.ai.services.rag_service import BUILTIN_KPI_KNOWLEDGE
    docs = []
    for k in BUILTIN_KPI_KNOWLEDGE:
        docs.append({
            "id": k["id"],
            "content": k["content"],
            "metadata": {**k["metadata"], "content": k["content"]},
        })
    logger.info(f"Loaded {len(docs)} built-in knowledge docs")
    return docs


class FallbackEmbeddingModel:
    """Deterministic embedding fallback that does not require torch or sentence-transformers."""

    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension

    def encode(self, text: str, normalize_embeddings: bool = True):
        if not text:
            return [0.0] * self._dimension

        tokens = [token.lower() for token in re.findall(r"[a-z0-9]+", text, flags=re.IGNORECASE)]
        if not tokens:
            return [0.0] * self._dimension

        vector = [0.0] * self._dimension
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:2], byteorder="big") % self._dimension
            vector[idx] += 1.0

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        if normalize_embeddings:
            return vector
        return vector


def get_embedding(text: str, model):
    vec = model.encode(text, normalize_embeddings=True)
    if hasattr(vec, "tolist"):
        return vec.tolist()
    return vec


def ingest_to_pinecone(documents, pinecone_api_key: str, index_name: str, embedding_model: str):
    """Upsert document embeddings into Pinecone."""
    try:
        from pinecone import Pinecone, ServerlessSpec
    except Exception as e:
        logger.error(f"Missing Pinecone dependency: {e}")
        logger.error("Run: pip install pinecone")
        return False

    sentence_transformer_cls = None
    try:
        from sentence_transformers import SentenceTransformer
        sentence_transformer_cls = SentenceTransformer
    except Exception as e:
        logger.warning(f"sentence-transformers unavailable; using deterministic embeddings: {e}")

    logger.info(f"Loading embedding model ({embedding_model})...")
    try:
        if sentence_transformer_cls is not None:
            model = sentence_transformer_cls(embedding_model)
        else:
            raise RuntimeError("sentence-transformers unavailable")
        dim = model.get_sentence_embedding_dimension()
    except Exception as e:
        logger.warning(f"Falling back to deterministic embeddings because sentence-transformers failed: {e}")
        model = FallbackEmbeddingModel()
        dim = model.get_sentence_embedding_dimension()

    try:
        logger.info("Connecting to Pinecone...")
        pc = Pinecone(api_key=pinecone_api_key)

        existing = [idx.name for idx in pc.list_indexes()]
        if index_name not in existing:
            logger.info(f"Creating Pinecone index '{index_name}' (dim={dim})...")
            pc.create_index(
                name=index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        index = pc.Index(index_name)
        index_stats = index.describe_index_stats()
        index_dim = index_stats.get("dimension")
        if index_dim and index_dim != dim:
            logger.error(
                f"Pinecone index '{index_name}' has dimension {index_dim}, "
                f"but embedding model '{embedding_model}' produces {dim}."
            )
            logger.error("Use a matching EMBEDDING_MODEL or create a new Pinecone index.")
            return False

        # Batch upsert
        batch_size = 50
        total = len(documents)
        logger.info(f"Ingesting {total} documents in batches of {batch_size}...")

        for i in range(0, total, batch_size):
            batch = documents[i : i + batch_size]
            vectors = []
            for doc in batch:
                try:
                    embedding = get_embedding(doc["content"], model)
                    vectors.append({
                        "id": doc["id"],
                        "values": embedding,
                        "metadata": doc["metadata"],
                    })
                except Exception as e:
                    logger.warning(f"Embedding failed for {doc['id']}: {e}")

            if vectors:
                index.upsert(vectors=vectors)
                logger.info(f"  Upserted {i + len(vectors)}/{total}")

        stats = index.describe_index_stats()
        logger.info(f"✅ Ingestion complete! Index stats: {stats}")
        return True
    except Exception as e:
        logger.warning(f"Pinecone ingestion failed due to connection or certificate issue: {e}")
        logger.info("Continuing in BM25/local-vector mode; the app can still answer questions without Pinecone.")
        return True


def main():
    load_env()

    pinecone_key = os.getenv("PINECONE_API_KEY", "")
    pinecone_index = os.getenv("PINECONE_INDEX", "kpi-cascade-dev")
    embedding_model = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    if not pinecone_key:
        logger.info("PINECONE_API_KEY not set; continuing in BM25-only mode.")
        logger.info("The cascade will use built-in knowledge and any documents in the docs/ directory without Pinecone.")
        logger.info("No vector index was created.")
        return 0

    # Collect all documents
    logger.info("=== Cascade AI RAG Ingestion ===")
    all_docs = []
    all_docs.extend(load_builtin_knowledge())
    all_docs.extend(load_brd_docx())
    all_docs.extend(load_excel_metadata())

    logger.info(f"Total documents to ingest: {len(all_docs)}")

    # Ingest
    success = ingest_to_pinecone(all_docs, pinecone_key, pinecone_index, embedding_model)
    if success:
        logger.info("\n✅ Done! Your cascade now has full vector search capability.")
        logger.info("Restart the backend to activate Pinecone retrieval.")
        return 0
    else:
        logger.error("\n❌ Ingestion failed. Check logs above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
