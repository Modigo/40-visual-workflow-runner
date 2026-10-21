from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.errors import AppError

RunStatus = Literal["queued", "running", "succeeded", "failed"]
TaskStatus = Literal["pending", "running", "retrying", "succeeded", "failed", "skipped"]


# ---------- Graph pieces (used in requests and responses) ----------

class Position(BaseModel):
    x: float
    y: float


class NodeIn(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=80)
    kind: str
    config: dict = {}
    position: Position
    sort_order: int = 0
    max_retries: int = Field(default=0, ge=0, le=3)
    retry_delay_seconds: int = Field(default=1, ge=0, le=10)
    timeout_seconds: int = Field(default=10, ge=1, le=30)


class EdgeIn(BaseModel):
    source_node_id: str
    target_node_id: str


class NodeOut(NodeIn):
    """A node as returned by the API (same shape as the request)."""


class EdgeOut(EdgeIn):
    """An edge as returned by the API (same shape as the request)."""


class GraphSaveRequest(BaseModel):
    expected_version: int
    nodes: list[NodeIn]
    edges: list[EdgeIn]


# ---------- Workflows ----------

class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None = None
    version: int
    created_at: datetime
    updated_at: datetime
    is_archived: bool = False


class WorkflowDetail(WorkflowSummary):
    nodes: list[NodeOut] = []
    edges: list[EdgeOut] = []


# ---------- Validation ----------

class ValidationIssue(BaseModel):
    code: str
    message: str
    node_ids: list[str] = []
    edge_ids: list[str] = []


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    execution_order: list[str] = []


# ---------- Runs ----------

class RunCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    workflow_version: int
    status: RunStatus
    created_at: datetime


class AttemptOut(BaseModel):
    attempt_number: int
    status: str
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TaskRunOut(BaseModel):
    id: str
    node_id: str
    node_name: str
    node_kind: str
    status: TaskStatus
    attempt_count: int = 0
    output: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    attempts: list[AttemptOut] = []


class RunDetail(RunCreated):
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_summary: str | None = None
    tasks: list[TaskRunOut] = []


# ---------- Errors ----------

class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] = []


class ErrorEnvelope(BaseModel):
    error: ErrorBody

class InvalidGraphError(AppError):
    status_code = 422
    code = "INVALID_GRAPH"