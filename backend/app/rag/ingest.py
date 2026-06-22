"""
Ingestion pipeline for the Knowledge Agent's document corpus (spec
section 4.1). Reads the BRD docx, chunks it section-aware (split on
heading boundaries from the docx's own Heading 1/2/3 styles — never
mid-sentence), tags each chunk with the required metadata, embeds, and
upserts into Pinecone via the migrated vector_store module.

Run standalone:
    python -m app.rag.ingest

Per FR-4.1 ("re-index all documents on every new BRD/Excel/User Guide
upload"), this script is idempotent (re-running it re-upserts chunks
with the same deterministic chunk_id, so old + new ingestion runs don't
duplicate vectors) and should be re-run any time a new BRD/User
Guide/SOP file is uploaded — wired into the existing /upload-excel flow
is a separate, future step; for now this is invoked manually or via
ingest_brd_docx() called from a route.
"""
from __future__ import annotations

import hashlib
import os
from typing import List, Optional

from docx import Document as DocxDocument

from .document_loader import DocumentChunk, _count_tokens
from .vector_store import ensure_index, upsert_chunks
from .rag_settings import settings

DEFAULT_BRD_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "data", "source_documents", "ROI_Measurement_Framework_BRD.docx",
)


def _chunk_id(doc_type: str, section_number: str, part: int) -> str:
    raw = f"{doc_type}:{section_number}:{part}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _split_into_token_windows(text: str, max_tokens: int = None, overlap: int = None) -> List[str]:
    """
    Splits a section's full text into ~300-500 token windows (spec
    section 4.1) without cutting mid-sentence: splits on sentence
    boundaries first, then packs sentences into windows under the token
    budget, only spilling into a new window between sentences.
    """
    max_tokens = max_tokens or settings.CHUNK_SIZE // 2  # spec wants 300-500, not the RAG backend's default 1200
    max_tokens = min(max_tokens, 500)

    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    windows: List[str] = []
    current: List[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_with_period = sentence if sentence.endswith(".") else sentence + "."
        sentence_tokens = _count_tokens(sentence_with_period)
        if current_tokens + sentence_tokens > max_tokens and current:
            windows.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(sentence_with_period)
        current_tokens += sentence_tokens

    if current:
        windows.append(" ".join(current))

    return windows if windows else [text]


def parse_brd_sections(docx_path: str) -> List[dict]:
    """
    Walks the BRD's paragraphs, grouping body text under the most recent
    Heading 1/2/3 paragraph, and returns one dict per section:
    {section_number, section_title, text}.

    Section numbers are parsed from the heading text itself (e.g. "6.3
    Simulation Logic & Calculations" -> section_number "6.3") since the
    BRD numbers its own headings; sections without a leading number
    (e.g. a sub-heading continuation) inherit "(continued)" framing but
    keep their own title for citation purposes.
    """
    doc = DocxDocument(docx_path)
    sections: List[dict] = []
    current = None

    for para in doc.paragraphs:
        style = para.style.name if para.style else ""
        text = para.text.strip()

        if style.startswith("Heading"):
            if not text:
                continue  # skip empty heading paragraphs (artifacts in the source doc)
            if current and current["text"].strip():
                sections.append(current)
            number, title = _split_heading(text)
            current = {"section_number": number, "section_title": title, "text": ""}
        elif current is not None and text:
            current["text"] += text + "\n"

    if current and current["text"].strip():
        sections.append(current)

    return sections


def _split_heading(heading_text: str):
    parts = heading_text.strip().split(" ", 1)
    if parts and parts[0].replace(".", "").isdigit():
        number = parts[0]
        title = parts[1].strip() if len(parts) > 1 else ""
        return number, title
    return "", heading_text.strip()


def ingest_brd_docx(docx_path: Optional[str] = None) -> int:
    """
    Ingests the BRD into Pinecone. Returns the number of chunks upserted.
    """
    path = docx_path or DEFAULT_BRD_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"BRD document not found at {path}")

    ensure_index()
    sections = parse_brd_sections(path)

    chunks: List[DocumentChunk] = []
    for section in sections:
        windows = _split_into_token_windows(section["text"])
        for part, window_text in enumerate(windows):
            chunk_id = _chunk_id("brd", section["section_number"] or section["section_title"], part)
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                source=os.path.basename(path),
                text=window_text,
                metadata={
                    "doc_type": "brd",
                    "section_number": section["section_number"],
                    "section_title": section["section_title"],
                    "page_number": None,  # python-docx doesn't expose page numbers directly
                },
            ))

    if chunks:
        upsert_chunks(chunks)
    return len(chunks)


def ingest_user_guide_text(guide_text: str, source_label: str = "User Guide") -> int:
    """
    Ingests free-text User Guide content (e.g. the popover copy already
    shown in the product UI) using the same section-aware strategy: the
    guide_text is expected to use "### Heading" markdown-style markers
    for sections; everything else is treated as one section's body.
    """
    ensure_index()
    sections: List[dict] = []
    current = {"section_number": "", "section_title": "Overview", "text": ""}

    for line in guide_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("###") or stripped.startswith("##") or stripped.startswith("#"):
            if current["text"].strip():
                sections.append(current)
            title = stripped.lstrip("#").strip()
            current = {"section_number": "", "section_title": title, "text": ""}
        else:
            current["text"] += line + "\n"

    if current["text"].strip():
        sections.append(current)

    chunks: List[DocumentChunk] = []
    for section in sections:
        windows = _split_into_token_windows(section["text"])
        for part, window_text in enumerate(windows):
            chunk_id = _chunk_id("user_guide", section["section_title"], part)
            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                source=source_label,
                text=window_text,
                metadata={
                    "doc_type": "user_guide",
                    "section_number": "",
                    "section_title": section["section_title"],
                    "page_number": None,
                },
            ))

    if chunks:
        upsert_chunks(chunks)
    return len(chunks)


def ingest_excel_rows(db_session) -> int:
    """
    Row-level ingestion of the Excel impact matrix (spec section 4.1:
    "one chunk per intervention/L2/L1 mapping row, NOT a flattened table
    dump"). Reuses TraceEngine's already-parsed edge index so this and
    the Excel Intelligence Agent's calculation_trace never drift out of
    sync after a re-upload (per the spec's explicit warning).
    """
    from ..services.trace_engine import TraceEngine

    ensure_index()
    engine = TraceEngine()
    edges = engine.index.get("edges", [])
    source_file = engine.index.get("source_file") or "FA_V2.1.xlsx"

    chunks: List[DocumentChunk] = []
    for i, edge in enumerate(edges):
        text = (
            f"{edge['from']} impacts {edge['to']} via formula '{edge['formula']}' "
            f"(sheet: {edge['sheet']}, row: {edge['row']})."
        )
        if edge.get("weight") is not None:
            text += f" Weight/impact factor: {edge['weight']}."

        chunk_id = _chunk_id("excel", f"{edge['sheet']}_{edge['row']}", i)
        chunks.append(DocumentChunk(
            chunk_id=chunk_id,
            source=source_file,
            text=text,
            metadata={
                "doc_type": "excel",
                "sheet_name": edge["sheet"],
                "row_number": edge["row"],
                "entity_names": f"{edge['from']}, {edge['to']}",
            },
        ))

    if chunks:
        upsert_chunks(chunks)
    return len(chunks)


if __name__ == "__main__":
    count = ingest_brd_docx()
    print(f"Ingested {count} BRD chunks.")
