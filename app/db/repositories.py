from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy import select, update

from app.db.models import TaskAttempt, TaskRun, WorkflowRun, utcnow
from app.db.session import SessionLocal


# ---------- Plain data handed to the engine (no database objects) ----------

@dataclass
class TaskPlan:
    task_run_id: str
    node_id: str
    name: str
    kind: str
    config: dict
    max_retries: int
    retry_delay_seconds: int
    timeout_seconds: int
    parent_node_ids: list[str] = field(default_factory=list)


@dataclass
class RunPlan:
    run_id: str
    workflow_id: str
    tasks: list[TaskPlan]  # already in execution order


# ---------- The interface the engine codes against ----------

class RunRepository(Protocol):
    def get_run_plan(self, run_id: str) -> RunPlan | None: ...
    def mark_run_running(self, run_id: str) -> bool: ...
    def mark_task_running(self, task_run_id: str) -> None: ...
    def mark_task_retrying(self, task_run_id: str) -> None: ...
    def record_attempt(
        self,
        task_run_id: str,
        attempt_number: int,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None: ...
    def finish_task(
        self,
        task_run_id: str,
        status: str,
        output: dict | None = None,
        error_message: str | None = None,
    ) -> None: ...
    def skip_pending_tasks(self, run_id: str) -> int: ...
    def finish_run(self, run_id: str, status: str, error_summary: str | None = None) -> None: ...
    def recover_interrupted_runs(self) -> list[str]: ...


# ---------- The real implementation, backed by the database ----------

class SqlRunRepository:
    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    @contextmanager
    def _session(self):
        """One short-lived session per call: open, do the work, save, close."""
        db = self._session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_run_plan(self, run_id: str) -> RunPlan | None:
        with self._session() as db:
            run = db.get(WorkflowRun, run_id)
            if run is None:
                return None

            snapshot = run.workflow_snapshot_json
            nodes = {n["id"]: n for n in snapshot.get("nodes", [])}
            parents: dict[str, list[str]] = {node_id: [] for node_id in nodes}
            for e in snapshot.get("edges", []):
                parents.setdefault(e["target_node_id"], []).append(e["source_node_id"])

            order = snapshot.get("execution_order") or [
                n["id"] for n in sorted(nodes.values(), key=lambda n: n["sort_order"])
            ]
            task_ids = {t.node_id: t.id for t in run.tasks}

            tasks = [
                TaskPlan(
                    task_run_id=task_ids[node_id],
                    node_id=node_id,
                    name=nodes[node_id]["name"],
                    kind=nodes[node_id]["kind"],
                    config=nodes[node_id]["config"],
                    max_retries=nodes[node_id]["max_retries"],
                    retry_delay_seconds=nodes[node_id]["retry_delay_seconds"],
                    timeout_seconds=nodes[node_id]["timeout_seconds"],
                    parent_node_ids=parents[node_id],
                )
                for node_id in order
            ]
            return RunPlan(run_id=run.id, workflow_id=run.workflow_id, tasks=tasks)

    def mark_run_running(self, run_id: str) -> bool:
        """queued -> running. Returns False if the run was not queued, so the
        same run can never be started twice."""
        with self._session() as db:
            result = db.execute(
                update(WorkflowRun)
                .where(WorkflowRun.id == run_id, WorkflowRun.status == "queued")
                .values(status="running", started_at=utcnow())
            )
            return result.rowcount == 1

    def mark_task_running(self, task_run_id: str) -> None:
        with self._session() as db:
            task = db.get(TaskRun, task_run_id)
            task.status = "running"
            if task.started_at is None:
                task.started_at = utcnow()

    def mark_task_retrying(self, task_run_id: str) -> None:
        with self._session() as db:
            db.get(TaskRun, task_run_id).status = "retrying"

    def record_attempt(
        self,
        task_run_id: str,
        attempt_number: int,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        with self._session() as db:
            db.add(
                TaskAttempt(
                    task_run_id=task_run_id,
                    attempt_number=attempt_number,
                    status=status,
                    error_type=error_type,
                    error_message=error_message,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
            task = db.get(TaskRun, task_run_id)
            task.attempt_count = max(task.attempt_count, attempt_number)

    def finish_task(
        self,
        task_run_id: str,
        status: str,
        output: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._session() as db:
            task = db.get(TaskRun, task_run_id)
            task.status = status
            task.output_json = output
            task.error_message = error_message
            task.finished_at = utcnow()

    def skip_pending_tasks(self, run_id: str) -> int:
        with self._session() as db:
            result = db.execute(
                update(TaskRun)
                .where(TaskRun.run_id == run_id, TaskRun.status == "pending")
                .values(status="skipped")
            )
            return result.rowcount

    def finish_run(self, run_id: str, status: str, error_summary: str | None = None) -> None:
        with self._session() as db:
            run = db.get(WorkflowRun, run_id)
            run.status = status
            run.error_summary = error_summary
            run.finished_at = utcnow()

    def recover_interrupted_runs(self) -> list[str]:
        """Call once at startup. A run still marked 'running' was cut off by a
        restart, so mark it failed with an INTERRUPTED summary (PRD section 9.4)."""
        with self._session() as db:
            stale = list(db.scalars(select(WorkflowRun).where(WorkflowRun.status == "running")))
            for run in stale:
                run.status = "failed"
                run.finished_at = utcnow()
                run.error_summary = "INTERRUPTED: the server stopped while this run was in progress."
                for task in run.tasks:
                    if task.status in ("running", "retrying"):
                        task.status = "failed"
                        task.error_message = "Interrupted by a server restart."
                        task.finished_at = utcnow()
                    elif task.status == "pending":
                        task.status = "skipped"
            return [run.id for run in stale]