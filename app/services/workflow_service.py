from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import EdgeOut, NodeOut, Position, WorkflowDetail, WorkflowSummary
from app.db.models import Workflow
from app.errors import NotFoundError


def create_workflow(db: Session, name: str, description: str | None) -> Workflow:
    workflow = Workflow(name=name, description=description)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


def list_workflows(db: Session) -> list[Workflow]:
    stmt = (
        select(Workflow)
        .where(Workflow.is_archived.is_(False))
        .order_by(Workflow.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_workflow(db: Session, workflow_id: str) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow not found.")
    return workflow


def workflow_to_detail(workflow: Workflow) -> WorkflowDetail:
    """Convert a database workflow into the API shape (config_json becomes config, and so on)."""
    nodes = [
        NodeOut(
            id=n.id,
            name=n.name,
            kind=n.kind,
            config=n.config_json,
            position=Position(x=n.position_x, y=n.position_y),
            sort_order=n.sort_order,
            max_retries=n.max_retries,
            retry_delay_seconds=n.retry_delay_seconds,
            timeout_seconds=n.timeout_seconds,
        )
        for n in sorted(workflow.nodes, key=lambda n: n.sort_order)
    ]
    edges = [
        EdgeOut(source_node_id=e.source_node_id, target_node_id=e.target_node_id)
        for e in workflow.edges
    ]
    summary = WorkflowSummary.model_validate(workflow)
    return WorkflowDetail(**summary.model_dump(), nodes=nodes, edges=edges)