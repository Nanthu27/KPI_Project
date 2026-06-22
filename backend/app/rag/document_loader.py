"""
services/document_loader.py
────────────────────────────
Loads documents from /data and splits into overlapping token chunks.

Supported:  .txt | .md | .pdf | .docx | .xlsx | .xls | .csv
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import tiktoken
from .rag_settings import settings


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class DocumentChunk:
    chunk_id:  str
    source:    str
    text:      str
    metadata:  dict = field(default_factory=dict)


# ── Tokenizer ─────────────────────────────────────────────────────────────────
#
# tiktoken's cl100k_base encoding downloads its BPE merge table from
# openaipublic.blob.core.windows.net on first use. Some deployment
# environments (this sandbox included) block egress to that host. Rather
# than make the whole RAG module fail to import in that case, fall back
# to a simple whitespace-based approximation (~1.3 tokens per word,
# which is a reasonable English-text approximation) so chunking still
# works — just with slightly less precise token-budget accounting. This
# only affects chunk-size bucketing, not retrieval quality or correctness.
try:
    _TOKENIZER = tiktoken.get_encoding("cl100k_base")
    _TIKTOKEN_AVAILABLE = True
except Exception:
    _TOKENIZER = None
    _TIKTOKEN_AVAILABLE = False


def _count_tokens(text: str) -> int:
    if _TIKTOKEN_AVAILABLE:
        return len(_TOKENIZER.encode(text))
    return int(len(text.split()) * 1.3) + 1


def _token_split(text: str, chunk_size: int, overlap: int) -> List[str]:
    if _TIKTOKEN_AVAILABLE:
        tokens = _TOKENIZER.encode(text)
        chunks: List[str] = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunks.append(_TOKENIZER.decode(tokens[start:end]))
            if end == len(tokens):
                break
            start += chunk_size - overlap
        return chunks

    # Fallback: word-based windowing (~1.3 tokens/word approximation)
    words = text.split()
    word_chunk_size = max(int(chunk_size / 1.3), 1)
    word_overlap = max(int(overlap / 1.3), 0)
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + word_chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += word_chunk_size - word_overlap
    return chunks


# ── File readers ──────────────────────────────────────────────────────────────

def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_md(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"#+\s",          "",    raw)
    raw = re.sub(r"\*{1,2}(.+?)\*{1,2}", r"\1", raw)
    raw = re.sub(r"`{1,3}[^`]*`{1,3}",   "",    raw)
    raw = re.sub(r"!\[.*?\]\(.*?\)",      "",    raw)
    raw = re.sub(r"\[(.+?)\]\(.*?\)",     r"\1", raw)
    raw = re.sub(r"-{3,}",                "",    raw)
    raw = re.sub(r"\n{3,}",              "\n\n", raw)
    return raw.strip()


def _read_pdf(path: Path) -> str:
    try:
        import PyPDF2
        parts: List[str] = []
        with path.open("rb") as fh:
            for page in PyPDF2.PdfReader(fh).pages:
                parts.append(page.extract_text() or "")
        return "\n\n".join(parts)
    except ImportError:
        raise RuntimeError("Run: pip install PyPDF2")


def _read_docx(path: Path) -> str:
    try:
        from docx import Document
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        raise RuntimeError("Run: pip install python-docx")


def _read_excel(path: Path) -> str:
    """
    Convert Excel (.xlsx / .xls) into clean text.

    Strategy per sheet:
      1. Row 0 is treated as a header row.
      2. Each data row is rendered as:
           Header1: value1 | Header2: value2 | ...
         so every row is self-contained and embeds well.
      3. Sheets are separated by a clear label.
     """
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("Run: pip install openpyxl")

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    parts: List[str] = []

    for sheet_name in wb.sheetnames:
        ws     = wb[sheet_name]
        rows   = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        # First non-empty row = headers
        headers = [str(h).strip() if h is not None else f"Col{i}"
                   for i, h in enumerate(rows[0])]

        sheet_lines = [f"[Sheet: {sheet_name}]"]

        for row in rows[1:]:
            # Skip entirely empty rows
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            pairs = []
            for h, cell in zip(headers, row):
                val = str(cell).strip() if cell is not None else ""
                if val and val.lower() not in ("none", "nan", "-"):
                    pairs.append(f"{h}: {val}")
            if pairs:
                sheet_lines.append(" | ".join(pairs))

        if len(sheet_lines) > 1:       # skip empty sheets
            parts.append("\n".join(sheet_lines))

    wb.close()
    return "\n\n".join(parts)


def _read_csv(path: Path) -> str:
    """
    Convert CSV/TSV → same row-as-sentence format as Excel.
    """
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError("Run: pip install pandas")

    sep = "\t" if path.suffix.lower() == ".tsv" else ","
    df  = pd.read_csv(str(path), sep=sep, dtype=str, keep_default_na=False)

    lines: List[str] = [f"[File: {path.name}]"]
    headers = list(df.columns)

    for _, row in df.iterrows():
        pairs = []
        for h in headers:
            val = str(row[h]).strip()
            if val and val.lower() not in ("none", "nan", ""):
                pairs.append(f"{h}: {val}")
        if pairs:
            lines.append(" | ".join(pairs))

    return "\n".join(lines)


# ── Reader dispatch ───────────────────────────────────────────────────────────

_READERS = {
    ".txt":  _read_txt,
    ".md":   _read_md,
    ".pdf":  _read_pdf,
    ".docx": _read_docx,
    ".xlsx": _read_excel,
    ".xls":  _read_excel,
    ".csv":  _read_csv,
    ".tsv":  _read_csv,
}


# Extensions considered "structured / tabular".
# For list-style or filter queries we load the whole file directly
# instead of relying on vector similarity (which may miss rows).
TABULAR_EXTS = {".xlsx", ".xls", ".csv", ".tsv"}


def load_tabular_full_text(
    data_dir: str | Path | None = None,
    filter_substr: str | None = None,
) -> str:
    """
    Read every tabular file in /data and return one big text blob.

    If `filter_substr` is given, only rows whose text (case-insensitive)
    contains that substring are kept (header line of each file/sheet
    is always preserved).
    """
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return ""

    needle = filter_substr.lower().strip() if filter_substr else None
    parts: List[str] = []

    for file_path in sorted(data_dir.iterdir()):
        suffix = file_path.suffix.lower()
        if suffix not in TABULAR_EXTS:
            continue
        try:
            text = _READERS[suffix](file_path)
        except Exception:
            continue
        if not text.strip():
            continue

        if needle:
            kept = []
            for line in text.splitlines():
                lower = line.lower()
                # Always keep sheet/file labels
                if (
                    line.startswith("[Sheet:")
                    or line.startswith("[File:")
                    or needle in lower
                ):
                    kept.append(line)
            text = "\n".join(kept)
            # if no real matches (only labels), skip this file
            if not any(
                ln for ln in text.splitlines()
                if ln and not ln.startswith("[")
            ):
                continue

        parts.append(f"=== FILE: {file_path.name} ===\n{text}")

    return "\n\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def load_chunks(
    data_dir:   str | Path | None = None,
    chunk_size: int = settings.CHUNK_SIZE,
    overlap:    int = settings.CHUNK_OVERLAP,
) -> List[DocumentChunk]:
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"

    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    all_chunks: List[DocumentChunk] = []

    for file_path in sorted(data_dir.iterdir()):
        suffix = file_path.suffix.lower()
        if suffix not in _READERS:
            continue

        print(f"  📄 Loading: {file_path.name}")
        try:
            full_text = _READERS[suffix](file_path)
        except Exception as exc:
            print(f"  ⚠️  Could not read {file_path.name}: {exc}")
            continue

        if not full_text.strip():
            print(f"  ⚠️  {file_path.name} is empty – skipping.")
            continue

        raw_chunks = _token_split(full_text, chunk_size, overlap)
        stem       = file_path.stem

        for idx, chunk_text in enumerate(raw_chunks):
            all_chunks.append(DocumentChunk(
                chunk_id  = f"{stem}_{idx}",
                source    = file_path.name,
                text      = chunk_text.strip(),
                metadata  = {
                    "source":      file_path.name,
                    "chunk_index": idx,
                    "token_count": _count_tokens(chunk_text),
                    "file_type":   suffix.lstrip("."),
                },
            ))

    print(f"  ✅ Total chunks created: {len(all_chunks)}")
    return all_chunks