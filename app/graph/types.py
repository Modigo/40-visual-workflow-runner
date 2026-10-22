# app/graph/types.py
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class NodeDef:
    id: str
    name: str
    kind: str
    config: dict[str, Any]
    sort_order: int
    max_retries: int = 0
    retry_delay_seconds: int = 1
    timeout_seconds: int = 10

@dataclass(frozen=True)
class EdgeDef:
    source_node_id: str
    target_node_id: str

@dataclass(frozen=True)
class GraphDef:
    nodes: list[NodeDef]
    edges: list[EdgeDef]

@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    node_ids: list[str] = field(default_factory=list)
    edge: tuple[str, str] | None = None

@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: list[Issue]
    warnings: list[Issue]
    execution_order: list[str]   # empty when invalid