"""Workflow execution engine for the Visual Workflow Runner.

Person 4 responsibility:
- Execute supported task types in dependency order.
- Pass parent task outputs to dependent tasks.
- Retry failed tasks within their configured retry limit.
- Record each attempt, output, error, and task status.
- Mark tasks after a permanent failure as Skipped.

This module expects the graph to be validated and execution_order to be
provided by the graph module (Person 3).
"""

from __future__ import annotations

import time
from typing import Any

Node = dict[str, Any]
Edge = tuple[str, str]


def emit_json(node: Node, parent_outputs: dict[str, Any]) -> Any:
    """Return the JSON-compatible value configured for this task."""
    return node.get("config", {}).get("value")


def combine_inputs(node: Node, parent_outputs: dict[str, Any]) -> dict[str, Any]:
    """Return all parent task outputs, keyed by parent node ID."""
    return {"inputs": parent_outputs}


def delay(node: Node, parent_outputs: dict[str, Any]) -> dict[str, Any]:
    """Wait for the configured duration (maximum five seconds)."""
    seconds = node.get("config", {}).get("seconds", 1)

    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ValueError("Delay seconds must be a number.")
    if not 0 <= seconds <= 5:
        raise ValueError("Delay must be between 0 and 5 seconds.")

    time.sleep(seconds)
    return {"delayed_seconds": seconds}


def demo_fail(
    node: Node,
    parent_outputs: dict[str, Any],
    attempt_number: int,
) -> dict[str, Any]:
    """Controlled task for testing retries; it never runs user-written code.

    Configuration:
        fail_times: number of initial attempts that should fail.
    """
    fail_times = node.get("config", {}).get("fail_times", 1)

    if isinstance(fail_times, bool) or not isinstance(fail_times, int):
        raise ValueError("fail_times must be an integer.")
    if fail_times < 0:
        raise ValueError("fail_times cannot be negative.")

    if attempt_number <= fail_times:
        raise RuntimeError("Demo task failed on purpose.")

    return {"message": "Demo task succeeded"}


def run_one_task(
    node: Node,
    parent_outputs: dict[str, Any],
    attempt_number: int = 1,
) -> Any:
    """Run one supported task implementation."""
    task_type = node.get("type")

    if task_type == "emit_json":
        return emit_json(node, parent_outputs)
    if task_type == "combine_inputs":
        return combine_inputs(node, parent_outputs)
    if task_type == "delay":
        return delay(node, parent_outputs)
    if task_type == "demo_fail":
        return demo_fail(node, parent_outputs, attempt_number)

    raise ValueError(f"Unsupported task type: {task_type!r}")


def get_outputs_from_parent_nodes(
    node_id: str,
    edges: list[Edge],
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """Collect outputs from completed parent nodes of ``node_id``."""
    parent_outputs: dict[str, Any] = {}
    for source, target in edges:
        if target == node_id and source in outputs:
            parent_outputs[source] = outputs[source]
    return parent_outputs


def run_task_with_retries(
    node: Node,
    parent_outputs: dict[str, Any],
) -> dict[str, Any]:
    """Run a task, retrying failures up to config['retries'] additional times.

    Returns a task record containing status, output/error, and attempt history.
    """
    config = node.get("config", {})
    retries = config.get("retries", 0)
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        return {
            "status": "Failed",
            "output": None,
            "error": "retries must be a non-negative integer.",
            "attempts": [],
        }

    attempts: list[dict[str, Any]] = []
    total_attempts = retries + 1

    for attempt_number in range(1, total_attempts + 1):
        try:
            output = run_one_task(node, parent_outputs, attempt_number)
            attempts.append({
                "attempt": attempt_number,
                "status": "Success",
                "output": output,
                "error": None,
            })
            return {
                "status": "Success",
                "output": output,
                "error": None,
                "attempts": attempts,
            }
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            attempts.append({
                "attempt": attempt_number,
                "status": "Failed",
                "output": None,
                "error": error_message,
            })

    last_error = attempts[-1]["error"] if attempts else "Task failed without an attempt."
    return {
        "status": "Failed",
        "output": None,
        "error": last_error,
        "attempts": attempts,
    }


def run_workflow(
    nodes: list[Node],
    edges: list[Edge],
    execution_order: list[str],
) -> dict[str, Any]:
    """Execute workflow nodes in the supplied order and return run details.

    If a task permanently fails, tasks later in execution_order are marked
    Skipped. The graph should be validated before this function is called.
    """
    nodes_by_id: dict[str, Node] = {}
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("Every node must have a non-empty string 'id'.")
        if node_id in nodes_by_id:
            raise ValueError(f"Duplicate node ID: {node_id!r}")
        nodes_by_id[node_id] = node

    outputs: dict[str, Any] = {}
    task_results: dict[str, dict[str, Any]] = {}

    for index, node_id in enumerate(execution_order):
        node = nodes_by_id.get(node_id)
        if node is None:
            raise ValueError(f"Execution order references unknown node ID: {node_id!r}")

        parent_outputs = get_outputs_from_parent_nodes(node_id, edges, outputs)
        task_result = run_task_with_retries(node, parent_outputs)
        task_results[node_id] = task_result

        if task_result["status"] == "Success":
            outputs[node_id] = task_result["output"]
            continue

        # A permanent failure stops the workflow. Mark all remaining nodes skipped.
        for skipped_id in execution_order[index + 1:]:
            task_results[skipped_id] = {
                "status": "Skipped",
                "output": None,
                "error": f"Skipped because task {node_id!r} failed.",
                "attempts": [],
            }

        return {
            "status": "Failed",
            "outputs": outputs,
            "tasks": task_results,
        }

    return {
        "status": "Success",
        "outputs": outputs,
        "tasks": task_results,
    }
