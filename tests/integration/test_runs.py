def make_node(node_id, name, sort_order=0):
    return {
        "id": node_id, "name": name, "kind": "emit_json",
        "config": {"value": {"value": 3}},
        "position": {"x": 0, "y": 0},
        "sort_order": sort_order,
        "max_retries": 0, "retry_delay_seconds": 1, "timeout_seconds": 10,
    }


def make_saved_workflow(client):
    wf = client.post("/api/v1/workflows", json={"name": "Demo"}).json()
    client.put(
        f"/api/v1/workflows/{wf['id']}/graph",
        json={
            "expected_version": 1,
            "nodes": [make_node("a", "A", 0), make_node("b", "B", 1)],
            "edges": [{"source_node_id": "a", "target_node_id": "b"}],
        },
    )
    return wf  # the saved workflow is now at version 2


def test_create_run_returns_202_and_queued(client):
    wf = make_saved_workflow(client)
    response = client.post(f"/api/v1/workflows/{wf['id']}/runs")
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["workflow_version"] == 2


def test_get_run_shows_pending_tasks_in_order(client):
    wf = make_saved_workflow(client)
    run = client.post(f"/api/v1/workflows/{wf['id']}/runs").json()
    detail = client.get(f"/api/v1/runs/{run['id']}").json()
    assert [t["node_name"] for t in detail["tasks"]] == ["A", "B"]
    assert all(t["status"] == "pending" for t in detail["tasks"])
    assert all(t["attempts"] == [] for t in detail["tasks"])


def test_empty_workflow_cannot_run(client):
    wf = client.post("/api/v1/workflows", json={"name": "Empty"}).json()
    response = client.post(f"/api/v1/workflows/{wf['id']}/runs")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMPTY_GRAPH"


def test_run_snapshot_survives_later_edits(client):
    wf = make_saved_workflow(client)
    run = client.post(f"/api/v1/workflows/{wf['id']}/runs").json()
    client.put(
        f"/api/v1/workflows/{wf['id']}/graph",
        json={"expected_version": 2, "nodes": [make_node("a", "Renamed")], "edges": []},
    )
    detail = client.get(f"/api/v1/runs/{run['id']}").json()
    assert [t["node_name"] for t in detail["tasks"]] == ["A", "B"]


def test_list_runs_newest_first_and_respects_limit(client):
    wf = make_saved_workflow(client)
    first = client.post(f"/api/v1/workflows/{wf['id']}/runs").json()
    second = client.post(f"/api/v1/workflows/{wf['id']}/runs").json()
    runs = client.get(f"/api/v1/workflows/{wf['id']}/runs").json()
    assert [r["id"] for r in runs] == [second["id"], first["id"]]
    limited = client.get(f"/api/v1/workflows/{wf['id']}/runs?limit=1").json()
    assert len(limited) == 1


def test_get_missing_run_returns_404(client):
    response = client.get("/api/v1/runs/nope")
    assert response.status_code == 404


def test_list_runs_for_missing_workflow_returns_404(client):
    response = client.get("/api/v1/workflows/nope/runs")
    assert response.status_code == 404