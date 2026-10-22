
from app.engine.runner import run_workflow, run_task_with_retries


def make_node(node_id, task_type, config=None):
    return {
        "id": node_id,
        "type": task_type,
        "config": config or {},
    }


def test_task_succeeds_without_retry():
    node = make_node("a", "emit_json", {"value": {"message": "hello"}})

    result = run_task_with_retries(node, {})

    assert result["status"] == "Success"
    assert result["output"] == {"message": "hello"}
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["status"] == "Success"


def test_task_retries_then_succeeds():
    node = make_node("a", "demo_fail", {"fail_times": 1, "retries": 1})

    result = run_task_with_retries(node, {})

    assert result["status"] == "Success"
    assert len(result["attempts"]) == 2
    assert result["attempts"][0]["status"] == "Failed"
    assert result["attempts"][0]["error"] is not None
    assert result["attempts"][1]["status"] == "Success"


def test_task_fails_after_all_retries():
    node = make_node("a", "demo_fail", {"fail_times": 3, "retries": 2})

    result = run_task_with_retries(node, {})

    assert result["status"] == "Failed"
    assert len(result["attempts"]) == 3
    assert all(a["status"] == "Failed" for a in result["attempts"])
    assert result["output"] is None
    assert result["error"] is not None


def test_child_receives_parent_output():
    nodes = [
        make_node("source", "emit_json", {"value": {"number": 42}}),
        make_node("child", "combine_inputs"),
    ]
    edges = [("source", "child")]

    result = run_workflow(nodes, edges, ["source", "child"])

    assert result["status"] == "Success"
    assert result["outputs"]["source"] == {"number": 42}
    assert result["outputs"]["child"] == {
        "inputs": {"source": {"number": 42}}
    }


def test_later_tasks_are_skipped_after_permanent_failure():
    nodes = [
        make_node("first", "demo_fail", {"fail_times": 1, "retries": 0}),
        make_node("second", "emit_json", {"value": "should not run"}),
        make_node("third", "combine_inputs"),
    ]

    result = run_workflow(nodes, [], ["first", "second", "third"])

    assert result["status"] == "Failed"
    assert result["tasks"]["first"]["status"] == "Failed"
    assert result["tasks"]["second"]["status"] == "Skipped"
    assert result["tasks"]["third"]["status"] == "Skipped"
    assert result["tasks"]["second"]["attempts"] == []
    assert "first" in result["tasks"]["second"]["error"]


def test_invalid_retry_count_is_rejected():
    node = make_node("a", "emit_json", {"value": "hello", "retries": -1})

    result = run_task_with_retries(node, {})

    assert result["status"] == "Failed"
    assert result["attempts"] == []
    assert "retries" in result["error"]
