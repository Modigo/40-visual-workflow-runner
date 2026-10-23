
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import RunDetail
from app.db.session import get_db
from app.db.repositories import SqlRunRepository
from app.engine.execution_service import execute_run
from app.services import run_service

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = run_service.get_run(db, run_id)
    return run_service.run_to_detail(run)


@router.post("/{run_id}/execute")
def execute_queued_run(run_id: str):
    repository = SqlRunRepository()

    try:
        succeeded = execute_run(run_id, repository)
    except ValueError as exc:
        if str(exc).startswith("Run not found:"):
            raise HTTPException(status_code=404, detail="Run not found.") from exc
        raise

    if not succeeded:
        # This can mean the run was already started or was not queued.
        raise HTTPException(
            status_code=409,
            detail="Run was not queued or has already been started.",
        )

    return {"run_id": run_id, "status": "succeeded"}
