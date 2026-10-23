import itertools

from app.graph.types import EdgeDef, GraphDef, NodeDef
from app.graph.validation import validate_graph

DEFAULT_CONFIG = {
    "emit_json": {"value": 1},
    "combine_inputs": {},
    "delay": {"seconds": 1},
    "demo_fail": {"fail_first_n_attempts": 1, "value": 1},
}


def node(id, name=None, kind="emit_json", config=None, sort_order=0, **kw):
    return NodeDef(
        id=id,
        name=name if name is not None else id,  # Fixes the empty string override
        kind=kind,
        config=DEFAULT_CONFIG[kind] if config is None else config,
        sort_order=sort_order,
        **kw,
    )


def graph(nodes, edges=()):
    return GraphDef(list(nodes), [EdgeDef(s, t) for s, t in edges])


def codes(result):
    return [e.code for e in result.errors]


# ----- basic shapes -----

def test_empty_graph():
    r = validate_graph(graph([]))
    assert not r.valid and "GRAPH_EMPTY" in codes(r) and r.execution_order == []


def test_single_node():
    r = validate_graph(graph([node("a")]))
    assert r.valid and r.execution_order == ["a"] and r.errors == []


def test_valid_chain():
    r = validate_graph(graph([node("a"), node("b"), node("c")], [("a", "b"), ("b", "c")]))
    assert r.valid and r.execution_order == ["a", "b", "c"]


# ----- limits -----

def test_30_nodes_ok_31_rejected():
    ok = validate_graph(graph([node(f"n{i:02}") for i in range(30)]))
    assert ok.valid
    bad = validate_graph(graph([node(f"n{i:02}") for i in range(31)]))
    assert "TOO_MANY_NODES" in codes(bad)


def test_60_edges_ok_61_rejected():
    nodes = [node(f"n{i:02}", sort_order=i) for i in range(30)]
    pairs = list(itertools.combinations([n.id for n in nodes], 2))
    assert validate_graph(graph(nodes, pairs[:60])).valid
    assert "TOO_MANY_EDGES" in codes(validate_graph(graph(nodes, pairs[:61])))


# ----- node checks -----

def test_duplicate_node_id():
    r = validate_graph(graph([node("a", name="A1"), node("a", name="A2")]))
    assert "DUPLICATE_NODE_ID" in codes(r)


def test_duplicate_node_name():
    r = validate_graph(graph([node("a", name="Same"), node("b", name="Same")]))
    assert "DUPLICATE_NODE_NAME" in codes(r)


def test_name_length_limits():
    assert "NODE_NAME_INVALID" in codes(validate_graph(graph([node("a", name="")])))
    assert "NODE_NAME_INVALID" in codes(validate_graph(graph([node("a", name="x" * 81)])))
    assert validate_graph(graph([node("a", name="x" * 80)])).valid


def test_unsupported_kind():
    n = NodeDef(id="a", name="a", kind="run_shell", config={}, sort_order=0)  # Added missing sort_order
    assert "UNSUPPORTED_KIND" in codes(validate_graph(graph([n])))


def test_demo_fail_only_when_enabled():
    g = graph([node("a", kind="demo_fail")])
    assert "UNSUPPORTED_KIND" in codes(validate_graph(g))
    assert validate_graph(g, allow_demo_node=True).valid


def test_retry_and_timeout_ranges():
    assert "RETRY_OUT_OF_RANGE" in codes(validate_graph(graph([node("a", max_retries=4)])))
    assert "RETRY_DELAY_OUT_OF_RANGE" in codes(validate_graph(graph([node("a", retry_delay_seconds=11)])))
    assert "TIMEOUT_OUT_OF_RANGE" in codes(validate_graph(graph([node("a", timeout_seconds=0)])))
    assert "TIMEOUT_OUT_OF_RANGE" in codes(validate_graph(graph([node("a", timeout_seconds=31)])))
    assert validate_graph(graph([node("a", max_retries=3, retry_delay_seconds=10, timeout_seconds=30)])).valid


def test_emit_json_requires_value():
    r = validate_graph(graph([node("a", config={})]))
    assert "CONFIG_INVALID" in codes(r)


def test_delay_seconds_range():
    assert validate_graph(graph([node("a", kind="delay", config={"seconds": 5})])).valid
    r = validate_graph(graph([node("a", kind="delay", config={"seconds": 6})]))
    assert "CONFIG_INVALID" in codes(r)


def test_config_too_large():
    r = validate_graph(graph([node("a", config={"value": "x" * 40_000})]))
    assert "CONFIG_TOO_LARGE" in codes(r)


# ----- edge checks -----

def test_self_edge():
    r = validate_graph(graph([node("a")], [("a", "a")]))
    assert "EDGE_SELF" in codes(r) and "GRAPH_CYCLE" not in codes(r)


def test_duplicate_edge():
    r = validate_graph(graph([node("a"), node("b")], [("a", "b"), ("a", "b")]))
    assert "EDGE_DUPLICATE" in codes(r)


def test_missing_endpoint():
    r = validate_graph(graph([node("a")], [("a", "ghost")]))
    assert "EDGE_MISSING_ENDPOINT" in codes(r)
    assert r.errors[0].node_ids == ["ghost"]


# ----- cycles and ordering -----

def test_two_node_cycle():
    r = validate_graph(graph([node("a"), node("b")], [("a", "b"), ("b", "a")]))
    assert "GRAPH_CYCLE" in codes(r) and r.execution_order == []


def test_longer_cycle_reports_involved_nodes():
    g = graph([node("a"), node("b"), node("c"), node("d")],
              [("a", "b"), ("b", "c"), ("c", "b"), ("c", "d")])
    cycle = next(e for e in validate_graph(g).errors if e.code == "GRAPH_CYCLE")
    assert "b" in cycle.node_ids and "c" in cycle.node_ids


def test_diamond():
    g = graph([node("a"), node("b"), node("c"), node("d")],
              [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert validate_graph(g).execution_order == ["a", "b", "c", "d"]


def test_tie_break_sort_order_then_id():
    g = graph([node("x", sort_order=1), node("y", sort_order=0), node("a", sort_order=1)])
    assert validate_graph(g).execution_order == ["y", "a", "x"]


def test_isolated_nodes_allowed():
    g = graph([node("a"), node("b"), node("c")], [("a", "b")])
    r = validate_graph(g)
    assert r.valid and set(r.execution_order) == {"a", "b", "c"}


def test_order_is_deterministic():
    g = graph([node(f"n{i}", sort_order=i % 3) for i in range(10)], [("n0", "n5"), ("n2", "n7")])
    first = validate_graph(g).execution_order
    assert all(validate_graph(g).execution_order == first for _ in range(100))


def test_multiple_errors_reported_together():
    g = graph([node("a", max_retries=9), node("b", config={})], [("a", "ghost")])
    assert {"RETRY_OUT_OF_RANGE", "CONFIG_INVALID", "EDGE_MISSING_ENDPOINT"} <= set(codes(validate_graph(g)))