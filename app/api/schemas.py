from pydantic import BaseModel, Field


class Position(BaseModel):
    x: float
    y: float


class NodeIn(BaseModel):
    id: str
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


class GraphSaveRequest(BaseModel):
    expected_version: int
    nodes: list[NodeIn]
    edges: list[EdgeIn]