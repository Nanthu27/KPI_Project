import io
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import excel_service, simulation_service
from ..schemas import schemas as sc

router = APIRouter(tags=["Excel Upload"])


@router.post("/upload-excel", response_model=sc.ExcelUploadResult)
async def upload_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx / .xlsm files are supported")

    contents = await file.read()
    try:
        bo, l1, l2, iv, warnings = excel_service.import_workbook(db, io.BytesIO(contents))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    simulation_service.recalculate(db)

    return sc.ExcelUploadResult(
        business_outcomes_created=bo,
        l1_metrics_created=l1,
        l2_metrics_created=l2,
        interventions_created=iv,
        warnings=warnings,
    )
