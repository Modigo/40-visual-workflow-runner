
from app.db.repositories import RunPlan, TaskPlan
from app.engine.execution_service import execute_run


class FakeRepository:
    """In-memory repository for testing execution without a database."""

    def __init__(self, tasks):
        self.plan = RunPlan(
            run_id="run-1",
            workflow_id="workflow-1",
            tasks=tasks,
        )
        self.run_status = "queued"
        self.task_statuses = {
            task.task_run_id: "pending" for task in tasks
        }
        self.attempts = {task.task_run_id: [] for task in tasks}
        self.outputs = {}
        self.errors = {}
        self.finished_status = None
        self.error_summary = None
        self.skipped_count = 0

    def get_run_plan(self, run_id):
        return self.plan if run_id == self.plan.run_id else None

    def mark_run_running(self, run_id):
        if run_id != self.plan.run_id or self.run_status != "queued":
            return False
        self.run_status = "running"
        return True

    def mark_task_running(self, task_run_id):
        self.task_statuses[task_run_id] = "running"

    def mark_task_retrying(self, task_run_id):
        self.task_statuses[task_run_id] = "retrying"

    def record_attempt(
        self,
        task_run_id,
        attempt_number,
        status,
        error_type=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    ):
        self.attempts[task_run_id].append({
            "attempt_number": attempt_number,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
        })

    def finish_task(
        self,
        task_run_id,
        status,
        output=None,
        error_message=None,
    ):
        self.task_statuses[task_run_id] = status
        self.outputs[task_run_id] = output
        self.errors[task_run_id] = error_message

    def skip_pending_tasks(self, run_id):
        count = 0
        for task in self.plan.tasks:
            if self.task_statuses[task.task_run_id] == "pending":
                self.task_statuses[task.task_run_id] = "skipped"
                count += 1
        self.skipped_count = count
        return count

    def finish_run(self, run_id, status, error_summary=None):
        self.run_status = status
        self.finished_status = status
        self.error_summary = error_summary

    def recover_interrupted_runs(self):
        return []


def make_task(
    node_id,
    kind,
    config=None,
    max_retries=0,
    parents=None,
):
    return TaskPlan(
        task_run_id=f"task-{node_id}",
        node_id=node_id,
        name=node_id,
        kind=kind,
        config=config or {},
        max_retries=max_retries,
        retry_delay_seconds=0,
        timeout_seconds=5,
        parent_node_ids=parents or [],
    )


def test_execute_run_saves_successful_task_output():
    repo = FakeRepository([
        make_task("source", "emit_json", {"value": {"message": "hello"}})
    ])

    assert execute_run("run-1", repo) is True
    assert repo.run_status == "succeeded"
    assert repo.task_statuses["task-source"] == "succeeded"
    assert repo.outputs["task-source"] == {"message": "hello"}
    assert len(repo.attempts["task-source"]) == 1


def test_execute_run_passes_parent_output_to_child():
    repo = FakeRepository([
        make_task("source", "emit_json", {"value": {"number": 42}}),
        make_task("child", "combine_inputs", parents=["source"]),
    ])

    assert execute_run("run-1", repo) is True
    assert repo.outputs["task-child"] == {
        "inputs": {"source": {"number": 42}}
    }


def test_execute_run_retries_then_succeeds():
    repo = FakeRepository([
        make_task(
            "flaky",
            "demo_fail",
            {"fail_times": 1},
            max_retries=1,
        )
    ])

    assert execute_run("run-1", repo) is True
    assert repo.task_statuses["task-flaky"] == "succeeded"
    assert [a["status"] for a in repo.attempts["task-flaky"]] == [
        "failed",
        "succeeded",
    ]


def test_execute_run_skips_remaining_tasks_after_failure():
    repo = FakeRepository([
        make_task("first", "demo_fail", {"fail_times": 1}),
        make_task("second", "emit_json", {"value": "not run"}),
    ])

    assert execute_run("run-1", repo) is False
    assert repo.run_status == "failed"
    assert repo.task_statuses["task-first"] == "failed"
    assert repo.task_statuses["task-second"] == "skipped"
    assert repo.skipped_count == 1


def test_execute_run_does_not_start_a_run_twice():
    repo = FakeRepository([
        make_task("source", "emit_json", {"value": "hello"})
    ])
    repo.run_status = "running"

    assert execute_run("run-1", repo) is False
    assert repo.attempts["task-source"] == []
