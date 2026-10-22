from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import RunDetail
from app.db.session import get_db
from app.services import run_service

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = run_service.get_run(db, run_id)
    return run_service.run_to_detail(run)