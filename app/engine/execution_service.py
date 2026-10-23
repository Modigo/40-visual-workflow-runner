
"""Execute a queued workflow and persist its progress."""

from datetime import datetime, timezone
from typing import Any

from app.db.repositories import RunRepository, SqlRunRepository
from app.engine.runner import run_one_task


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _output_as_dict(output: Any) -> dict | None:
    """Keep persisted outputs compatible with the API output schema."""
    if output is None:
        return None
    if isinstance(output, dict):
        return output
    return {"value": output}


def execute_run(
    run_id: str,
    repository: RunRepository | None = None,
) -> bool:
    """Execute one queued run.

    Returns True when the run finishes successfully, or False on failure.
    The repository is injectable so this function can be tested independently.
    """
    repo = repository or SqlRunRepository()
    plan = repo.get_run_plan(run_id)

    if plan is None:
        raise ValueError(f"Run not found: {run_id}")

    # Prevent two workers from starting the same queued run.
    if not repo.mark_run_running(run_id):
        return False

    outputs: dict[str, Any] = {}

    for index, task in enumerate(plan.tasks):
        repo.mark_task_running(task.task_run_id)

        parent_outputs = {
            parent_id: outputs[parent_id]
            for parent_id in task.parent_node_ids
            if parent_id in outputs
        }

        # Translate repository fields into the format expected by runner.py.
        config = dict(task.config)
        config["retries"] = task.max_retries

        # Support the validator's configuration name as well as the
        # runner's original name for the controlled demo failure task.
        if (
            "fail_first_n_attempts" in config
            and "fail_times" not in config
        ):
            config["fail_times"] = config["fail_first_n_attempts"]

        node = {
            "id": task.node_id,
            "name": task.name,
            "type": task.kind,
            "config": config,
        }

        succeeded = False
        last_error = None

        for attempt_number in range(1, task.max_retries + 2):
            started_at = _now()

            try:
                # The delay task is the only built-in task that waits.
                # Reject a delay exceeding its configured task timeout.
                if task.kind == "delay":
                    seconds = config.get("seconds", 1)
                    if (
                        isinstance(seconds, (int, float))
                        and not isinstance(seconds, bool)
                        and seconds > task.timeout_seconds
                    ):
                        raise TimeoutError(
                            "Delay exceeds the task timeout."
                        )

                output = run_one_task(
                    node,
                    parent_outputs,
                    attempt_number,
                )
                finished_at = _now()

                repo.record_attempt(
                    task.task_run_id,
                    attempt_number,
                    "succeeded",
                    started_at=started_at,
                    finished_at=finished_at,
                )
                repo.finish_task(
                    task.task_run_id,
                    "succeeded",
                    output=_output_as_dict(output),
                )

                outputs[task.node_id] = output
                succeeded = True
                break

            except Exception as exc:
                finished_at = _now()
                last_error = f"{type(exc).__name__}: {exc}"

                repo.record_attempt(
                    task.task_run_id,
                    attempt_number,
                    "failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    started_at=started_at,
                    finished_at=finished_at,
                )

                if attempt_number <= task.max_retries:
                    repo.mark_task_retrying(task.task_run_id)

                    if task.retry_delay_seconds:
                        import time
                        time.sleep(task.retry_delay_seconds)

        if not succeeded:
            repo.finish_task(
                task.task_run_id,
                "failed",
                error_message=last_error,
            )
            repo.skip_pending_tasks(run_id)
            repo.finish_run(
                run_id,
                "failed",
                error_summary=(
                    f"Task {task.name!r} failed: {last_error}"
                ),
            )
            return False

    repo.finish_run(run_id, "succeeded")
    return True
