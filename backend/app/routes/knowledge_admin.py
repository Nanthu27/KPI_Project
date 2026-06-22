"""
Admin/maintenance routes for the Knowledge Agent's document corpus
(spec FR-4.1: "re-index all documents on every new BRD/Excel/User Guide
upload"). These are deliberately separate from the existing
/upload-excel route (KPI data import) since BRD/User Guide ingestion is
a distinct, occasional admin action, not part of the regular KPI CRUD
flow.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from ..database import get_db

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Agent Admin"])


@router.post("/reindex/brd")
def reindex_brd():
    from ..rag.ingest import ingest_brd_docx
    try:
        count = ingest_brd_docx()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Ingestion failed (is PINECONE_API_KEY / OPENROUTER_API_KEY configured?): {exc}") from exc
    return {"ok": True, "chunks_ingested": count}


@router.post("/reindex/excel")
def reindex_excel(db: Session = Depends(get_db)):
    from ..rag.ingest import ingest_excel_rows
    from ..services.trace_engine import TraceEngine
    try:
        TraceEngine.reload()  # re-parse the workbook in case it was just re-uploaded
        count = ingest_excel_rows(db)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Ingestion failed: {exc}") from exc
    return {"ok": True, "chunks_ingested": count}


@router.post("/reindex/user-guide")
def reindex_user_guide():
    from ..rag.ingest import ingest_user_guide_text
    from .user_guide_content import USER_GUIDE_TEXT
    try:
        count = ingest_user_guide_text(USER_GUIDE_TEXT)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Ingestion failed: {exc}") from exc
    return {"ok": True, "chunks_ingested": count}
