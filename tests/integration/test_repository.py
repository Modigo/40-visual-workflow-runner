import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.schemas import EdgeIn, GraphSaveRequest, NodeIn, Position
from app.db import models  # noqa: F401
from app.db.repositories import SqlRunRepository
from app.db.session import Base
from app.services import run_service, workflow_service


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def make_node(node_id, name, order):
    return NodeIn(
        id=node_id, name=name, kind="emit_json", config={"value": 1},
        position=Position(x=0, y=0), sort_order=order,
    )


@pytest.fixture()
def queued_run_id(session_factory):
    with session_factory() as db:
        wf = workflow_service.create_workflow(db, "Demo", None)
        workflow_service.save_graph(
            db, wf.id,
            GraphSaveRequest(
                expected_version=1,
                nodes=[make_node("a", "A", 0), make_node("b", "B", 1)],
                edges=[EdgeIn(source_node_id="a", target_node_id="b")],
            ),
        )
        return run_service.create_run(db, wf.id).id


def read_detail(session_factory, run_id):
    with session_factory() as db:
        return run_service.run_to_detail(run_service.get_run(db, run_id))


def test_plan_is_in_order_with_parents(session_factory, queued_run_id):
    plan = SqlRunRepository(session_factory).get_run_plan(queued_run_id)
    assert [t.name for t in plan.tasks] == ["A", "B"]
    assert plan.tasks[0].parent_node_ids == []
    assert plan.tasks[1].parent_node_ids == ["a"]


def test_missing_run_has_no_plan(session_factory):
    assert SqlRunRepository(session_factory).get_run_plan("nope") is None


def test_run_can_only_be_started_once(session_factory, queued_run_id):
    repo = SqlRunRepository(session_factory)
    assert repo.mark_run_running(queued_run_id) is True
    assert repo.mark_run_running(queued_run_id) is False


def test_attempts_and_results_are_saved(session_factory, queued_run_id):
    repo = SqlRunRepository(session_factory)
    first = repo.get_run_plan(queued_run_id).tasks[0]
    repo.mark_run_running(queued_run_id)
    repo.mark_task_running(first.task_run_id)
    repo.record_attempt(first.task_run_id, 1, "failed", "TestError", "boom")
    repo.mark_task_retrying(first.task_run_id)
    repo.record_attempt(first.task_run_id, 2, "succeeded")
    repo.finish_task(first.task_run_id, "succeeded", output={"value": 1})

    task = read_detail(session_factory, queued_run_id).tasks[0]
    assert task.status == "succeeded"
    assert task.attempt_count == 2
    assert [a.status for a in task.attempts] == ["failed", "succeeded"]
    assert task.output == {"value": 1}


def test_failure_skips_remaining_tasks(session_factory, queued_run_id):
    repo = SqlRunRepository(session_factory)
    first = repo.get_run_plan(queued_run_id).tasks[0]
    repo.mark_run_running(queued_run_id)
    repo.mark_task_running(first.task_run_id)
    repo.finish_task(first.task_run_id, "failed", error_message="x")
    assert repo.skip_pending_tasks(queued_run_id) == 1
    repo.finish_run(queued_run_id, "failed", "Task 'A' failed")

    detail = read_detail(session_factory, queued_run_id)
    assert detail.status == "failed"
    assert detail.error_summary == "Task 'A' failed"
    assert [t.status for t in detail.tasks] == ["failed", "skipped"]


def test_interrupted_runs_are_marked_failed(session_factory, queued_run_id):
    repo = SqlRunRepository(session_factory)
    first = repo.get_run_plan(queued_run_id).tasks[0]
    repo.mark_run_running(queued_run_id)
    repo.mark_task_running(first.task_run_id)

    assert repo.recover_interrupted_runs() == [queued_run_id]

    detail = read_detail(session_factory, queued_run_id)
    assert detail.status == "failed"
    assert detail.error_summary.startswith("INTERRUPTED")
    assert [t.status for t in detail.tasks] == ["failed", "skipped"]