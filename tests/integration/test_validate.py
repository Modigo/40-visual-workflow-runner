def test_validate_existing_workflow(client):
    wf = client.post("/api/v1/workflows", json={"name": "Demo"}).json()
    node = {
        "id": "a", "name": "A", "kind": "emit_json",
        "config": {}, "position": {"x": 0, "y": 0},
    }
    client.put(
        f"/api/v1/workflows/{wf['id']}/graph",
        json={"expected_version": 1, "nodes": [node], "edges": []},
    )
    response = client.post(f"/api/v1/workflows/{wf['id']}/validate")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["execution_order"] == ["a"]


def test_validate_missing_workflow_returns_404(client):
    response = client.post("/api/v1/workflows/nope/validate")
    assert response.status_code == 404