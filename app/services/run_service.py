from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import AttemptOut, RunDetail, TaskRunOut
from app.db.models import TaskRun, WorkflowRun
from app.errors import ConflictError, NotFoundError
from app.services import workflow_service


def create_run(db: Session, workflow_id: str) -> WorkflowRun:
    workflow = workflow_service.get_workflow(db, workflow_id)

    if not workflow.nodes:
        raise ConflictError(
            "A workflow needs at least one node before it can run.", code="EMPTY_GRAPH"
        )

    validation = workflow_service.validate_workflow(db, workflow_id)
    if not validation.valid:
        raise ConflictError(
            "The saved graph is invalid, so it cannot run.",
            code="INVALID_GRAPH",
            details=[issue.model_dump() for issue in validation.errors],
        )

    # Freeze the graph exactly as it is now.
    snapshot = workflow_service.workflow_to_detail(workflow).model_dump(mode="json")
    snapshot["execution_order"] = validation.execution_order

    run = WorkflowRun(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        workflow_snapshot_json=snapshot,
        status="queued",
    )
    db.add(run)
    db.flush()  # gives the run an id before we create its tasks

    for node in sorted(workflow.nodes, key=lambda n: n.sort_order):
        db.add(
            TaskRun(
                run_id=run.id,
                node_id=node.id,
                node_name_snapshot=node.name,
                node_kind_snapshot=node.kind,
                status="pending",
            )
        )

    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: str) -> WorkflowRun:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("Run not found.")
    return run


def list_runs(db: Session, workflow_id: str, limit: int) -> list[WorkflowRun]:
    workflow_service.get_workflow(db, workflow_id)  # raises 404 if missing
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def run_to_detail(run: WorkflowRun) -> RunDetail:
    """Convert a database run into the API shape, with tasks in execution order."""
    order = {
        node_id: i
        for i, node_id in enumerate(run.workflow_snapshot_json.get("execution_order", []))
    }
    tasks = []
    for t in sorted(run.tasks, key=lambda t: order.get(t.node_id, len(order))):
        attempts = [
            AttemptOut(
                attempt_number=a.attempt_number,
                status=a.status,
                error_type=a.error_type,
                error_message=a.error_message,
                started_at=a.started_at,
                finished_at=a.finished_at,
            )
            for a in sorted(t.attempts, key=lambda a: a.attempt_number)
        ]
        tasks.append(
            TaskRunOut(
                id=t.id,
                node_id=t.node_id,
                node_name=t.node_name_snapshot,
                node_kind=t.node_kind_snapshot,
                status=t.status,
                attempt_count=t.attempt_count,
                output=t.output_json,
                error_message=t.error_message,
                started_at=t.started_at,
                finished_at=t.finished_at,
                attempts=attempts,
            )
        )
    return RunDetail(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version=run.workflow_version,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_summary=run.error_summary,
        tasks=tasks,
    )