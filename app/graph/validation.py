from __future__ import annotations

import json

from app.graph.ordering import topological_order
from app.graph.types import GraphDef, Issue, NodeDef, ValidationResult

MAX_NODES = 30
MAX_EDGES = 60
MAX_NAME_LEN = 80
MAX_CONFIG_BYTES = 32 * 1024
BASE_KINDS = {"emit_json", "combine_inputs", "delay"}


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------- limits ----------

def _check_limits(graph: GraphDef) -> list[Issue]:
    issues = []
    if len(graph.nodes) == 0:
        issues.append(Issue("GRAPH_EMPTY", "The workflow needs at least one node to run."))
    if len(graph.nodes) > MAX_NODES:
        issues.append(Issue(
            "TOO_MANY_NODES",
            f"A workflow can have at most {MAX_NODES} nodes; this one has {len(graph.nodes)}.",
        ))
    if len(graph.edges) > MAX_EDGES:
        issues.append(Issue(
            "TOO_MANY_EDGES",
            f"A workflow can have at most {MAX_EDGES} connections; this one has {len(graph.edges)}.",
        ))
    return issues


# ---------- nodes ----------

def _check_config(node: NodeDef) -> list[Issue]:
    ref = [node.id]
    cfg = node.config
    if not isinstance(cfg, dict):
        return [Issue("CONFIG_INVALID", f"Node '{node.name}': config must be a JSON object.", ref)]
    try:
        size = len(json.dumps(cfg).encode("utf-8"))
    except (TypeError, ValueError):
        return [Issue("CONFIG_INVALID", f"Node '{node.name}': config must be valid JSON.", ref)]
    if size > MAX_CONFIG_BYTES:
        return [Issue(
            "CONFIG_TOO_LARGE",
            f"Node '{node.name}': config is larger than {MAX_CONFIG_BYTES // 1024} KB.",
            ref,
        )]

    if node.kind == "emit_json" and "value" not in cfg:
        return [Issue("CONFIG_INVALID", f"Node '{node.name}': emit_json needs a \"value\" in its config.", ref)]

    if node.kind == "delay":
        s = cfg.get("seconds")
        if not _is_number(s) or not 0 <= s <= 5:
            return [Issue("CONFIG_INVALID", f"Node '{node.name}': delay needs \"seconds\" between 0 and 5.", ref)]

    if node.kind == "demo_fail":
        n = cfg.get("fail_first_n_attempts")
        if not _is_int(n) or n < 0 or "value" not in cfg:
            return [Issue(
                "CONFIG_INVALID",
                f"Node '{node.name}': demo_fail needs \"fail_first_n_attempts\" (0 or more) and a \"value\".",
                ref,
            )]
    return []


def _check_node(node: NodeDef, allow_demo_node: bool) -> list[Issue]:
    issues = []
    ref = [node.id]

    if not isinstance(node.id, str) or not node.id:
        issues.append(Issue("NODE_ID_INVALID", "Every node needs a non-empty id.", ref))

    if not isinstance(node.name, str) or not 1 <= len(node.name) <= MAX_NAME_LEN:
        issues.append(Issue("NODE_NAME_INVALID", f"Node '{node.id}' needs a name of 1-{MAX_NAME_LEN} characters.", ref))

    allowed = BASE_KINDS | ({"demo_fail"} if allow_demo_node else set())
    kind_ok = node.kind in allowed
    if not kind_ok:
        issues.append(Issue(
            "UNSUPPORTED_KIND",
            f"Node '{node.name}' has unsupported type '{node.kind}'. Use one of: {', '.join(sorted(allowed))}.",
            ref,
        ))

    if not _is_int(node.max_retries) or not 0 <= node.max_retries <= 3:
        issues.append(Issue("RETRY_OUT_OF_RANGE", f"Node '{node.name}': retries must be 0 to 3.", ref))
    if not _is_int(node.retry_delay_seconds) or not 0 <= node.retry_delay_seconds <= 10:
        issues.append(Issue("RETRY_DELAY_OUT_OF_RANGE", f"Node '{node.name}': retry delay must be 0 to 10 seconds.", ref))
    if not _is_int(node.timeout_seconds) or not 1 <= node.timeout_seconds <= 30:
        issues.append(Issue("TIMEOUT_OUT_OF_RANGE", f"Node '{node.name}': timeout must be 1 to 30 seconds.", ref))

    if kind_ok:
        issues.extend(_check_config(node))
    return issues


def _check_nodes(graph: GraphDef, allow_demo_node: bool) -> list[Issue]:
    issues = []
    seen_ids: set[str] = set()
    seen_names: dict[str, str] = {}
    for node in graph.nodes:
        if node.id in seen_ids:
            issues.append(Issue("DUPLICATE_NODE_ID", f"Node id '{node.id}' is used more than once.", [node.id]))
        seen_ids.add(node.id)

        if node.name in seen_names:
            issues.append(Issue(
                "DUPLICATE_NODE_NAME",
                f"The name '{node.name}' is used by more than one node. Names must be unique.",
                [seen_names[node.name], node.id],
            ))
        else:
            seen_names[node.name] = node.id

        issues.extend(_check_node(node, allow_demo_node))
    return issues


# ---------- edges ----------

def _check_edges(graph: GraphDef, node_ids: set[str]) -> tuple[list[Issue], list[tuple[str, str]]]:
    issues = []
    good: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for e in graph.edges:
        pair = (e.source_node_id, e.target_node_id)

        if pair[0] == pair[1]:
            issues.append(Issue("EDGE_SELF", f"Node '{pair[0]}' cannot depend on itself.", [pair[0]], [pair]))
            continue

        missing = [n for n in pair if n not in node_ids]
        if missing:
            issues.append(Issue(
                "EDGE_MISSING_ENDPOINT",
                f"Connection {pair[0]} -> {pair[1]} points to a node that does not exist: {', '.join(missing)}.",
                missing,
                [pair],
            ))
            continue

        if pair in seen:
            issues.append(Issue("EDGE_DUPLICATE", f"The connection {pair[0]} -> {pair[1]} appears more than once.", list(pair), [pair]))
            continue

        seen.add(pair)
        good.append(pair)
    return issues, good


# ---------- public entry point ----------

def validate_graph(graph: GraphDef, *, allow_demo_node: bool = False) -> ValidationResult:
    errors: list[Issue] = []
    errors.extend(_check_limits(graph))
    errors.extend(_check_nodes(graph, allow_demo_node))

    node_ids = {n.id for n in graph.nodes}
    edge_issues, good_edges = _check_edges(graph, node_ids)
    errors.extend(edge_issues)

    # Ordering only makes sense if node ids are unique; other problems
    # have already been excluded from good_edges.
    has_dup_ids = len(node_ids) != len(graph.nodes)
    order: list[str] = []
    if graph.nodes and not has_dup_ids:
        sort_keys = {n.id: (n.sort_order, n.id) for n in graph.nodes}
        order, leftover = topological_order(sort_keys, good_edges)
        if leftover:
            errors.append(Issue(
                "GRAPH_CYCLE",
                "The workflow contains a dependency cycle. Check the connections between: "
                + ", ".join(leftover) + ".",
                leftover,
            ))

    valid = not errors
    return ValidationResult(
        valid=valid,
        errors=errors,
        warnings=[],
        execution_order=order if valid else [],
    )