from app.graph.ordering import topological_order


def keys(*ids):
    return {i: (idx, i) for idx, i in enumerate(ids)}


def test_chain():
    order, left = topological_order(keys("a", "b", "c"), [("a", "b"), ("b", "c")])
    assert order == ["a", "b", "c"] and left == []


def test_diamond():
    edges = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]
    order, left = topological_order(keys("a", "b", "c", "d"), edges)
    assert order == ["a", "b", "c", "d"] and left == []


def test_tie_break_uses_sort_order_then_id():
    sk = {"x": (0, "x"), "y": (0, "y"), "z": (-1, "z")}
    order, _ = topological_order(sk, [])
    assert order == ["z", "x", "y"]


def test_tie_break_ignores_input_order():
    sk = {"b": (1, "b"), "a": (1, "a")}
    assert topological_order(sk, [])[0] == ["a", "b"]


def test_dependency_beats_sort_order():
    sk = {"a": (5, "a"), "b": (0, "b")}
    order, _ = topological_order(sk, [("a", "b")])
    assert order == ["a", "b"]


def test_cycle_reports_leftover():
    order, left = topological_order(keys("a", "b"), [("a", "b"), ("b", "a")])
    assert order == [] and left == ["a", "b"]


def test_cycle_after_valid_prefix():
    edges = [("a", "b"), ("b", "c"), ("c", "b")]
    order, left = topological_order(keys("a", "b", "c"), edges)
    assert order == ["a"] and left == ["b", "c"]