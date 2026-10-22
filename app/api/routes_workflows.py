from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import (
    GraphSaveRequest, ValidationResponse, WorkflowCreate, WorkflowDetail, WorkflowSummary,
)
from app.db.session import get_db
from app.services import workflow_service

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    GraphSaveRequest, RunCreated, ValidationResponse,
    WorkflowCreate, WorkflowDetail, WorkflowSummary,
)
from app.db.session import get_db
from app.services import run_service, workflow_service

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowSummary, status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db)):
    return workflow_service.create_workflow(db, body.name, body.description)


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(db: Session = Depends(get_db)):
    return workflow_service.list_workflows(db)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    workflow = workflow_service.get_workflow(db, workflow_id)
    return workflow_service.workflow_to_detail(workflow)

@router.put("/{workflow_id}/graph", response_model=WorkflowDetail)
def save_graph(workflow_id: str, body: GraphSaveRequest, db: Session = Depends(get_db)):
    workflow = workflow_service.save_graph(db, workflow_id, body)
    return workflow_service.workflow_to_detail(workflow)

@router.post("/{workflow_id}/validate", response_model=ValidationResponse)
def validate_workflow(workflow_id: str, db: Session = Depends(get_db)):
    return workflow_service.validate_workflow(db, workflow_id)

@router.post("/{workflow_id}/runs", response_model=RunCreated, status_code=202)
def create_run(workflow_id: str, db: Session = Depends(get_db)):
    return run_service.create_run(db, workflow_id)


@router.get("/{workflow_id}/runs", response_model=list[RunCreated])
def list_runs(
    workflow_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return run_service.list_runs(db, workflow_id, limit)