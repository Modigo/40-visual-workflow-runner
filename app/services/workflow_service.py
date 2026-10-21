from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    EdgeOut, GraphSaveRequest, NodeOut, Position, WorkflowDetail, WorkflowSummary,
)
from app.db.models import Edge, Node, Workflow
from app.errors import ConflictError, InvalidGraphError, NotFoundError


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

def _check_storable(request: GraphSaveRequest) -> None:
    """Reject graphs the database cannot store. (Cycles are NOT checked here;
    that is the validator's job, so users can save a half-finished drawing.)"""
    node_ids = [n.id for n in request.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise InvalidGraphError("Two nodes share the same id.", code="DUPLICATE_NODE_ID")

    names = [n.name for n in request.nodes]
    if len(names) != len(set(names)):
        raise InvalidGraphError("Two nodes share the same name.", code="DUPLICATE_NODE_NAME")

    known = set(node_ids)
    seen_edges = set()
    for e in request.edges:
        if e.source_node_id not in known or e.target_node_id not in known:
            raise InvalidGraphError(
                "An edge points to a node that does not exist.",
                code="EDGE_UNKNOWN_NODE",
                details=[{"source_node_id": e.source_node_id, "target_node_id": e.target_node_id}],
            )
        if e.source_node_id == e.target_node_id:
            raise InvalidGraphError(
                "A node cannot depend on itself.",
                code="SELF_EDGE",
                details=[{"node_id": e.source_node_id}],
            )
        pair = (e.source_node_id, e.target_node_id)
        if pair in seen_edges:
            raise InvalidGraphError("The same edge appears twice.", code="DUPLICATE_EDGE")
        seen_edges.add(pair)


def _check_node_ids_free(db: Session, workflow_id: str, request: GraphSaveRequest) -> None:
    """Node ids are unique across all workflows, so refuse ids another workflow owns."""
    ids = [n.id for n in request.nodes]
    if not ids:
        return
    stmt = select(Node.id).where(Node.id.in_(ids), Node.workflow_id != workflow_id)
    taken = list(db.scalars(stmt))
    if taken:
        raise ConflictError(
            "A node id is already used by another workflow. Use a new unique id (a UUID).",
            code="NODE_ID_IN_USE",
            details=[{"node_id": node_id} for node_id in taken],
        )


def save_graph(db: Session, workflow_id: str, request: GraphSaveRequest) -> Workflow:
    workflow = get_workflow(db, workflow_id)

    if workflow.version != request.expected_version:
        raise ConflictError(
            "The workflow was changed by someone else. Reload it and try again.",
            code="VERSION_CONFLICT",
            details=[
                {
                    "expected_version": request.expected_version,
                    "current_version": workflow.version,
                }
            ],
        )

    _check_storable(request)
    _check_node_ids_free(db, workflow_id, request)

    # Replace the whole graph: edges first (they point at nodes), then nodes.
    db.execute(delete(Edge).where(Edge.workflow_id == workflow_id))
    db.execute(delete(Node).where(Node.workflow_id == workflow_id))

    for n in request.nodes:
        db.add(
            Node(
                id=n.id,
                workflow_id=workflow_id,
                name=n.name,
                kind=n.kind,
                config_json=n.config,
                position_x=n.position.x,
                position_y=n.position.y,
                sort_order=n.sort_order,
                max_retries=n.max_retries,
                retry_delay_seconds=n.retry_delay_seconds,
                timeout_seconds=n.timeout_seconds,
            )
        )
    db.flush()  # make sure nodes exist before edges point at them

    for e in request.edges:
        db.add(
            Edge(
                workflow_id=workflow_id,
                source_node_id=e.source_node_id,
                target_node_id=e.target_node_id,
            )
        )

    workflow.version = workflow.version + 1
    db.commit()
    db.refresh(workflow)
    return workflow