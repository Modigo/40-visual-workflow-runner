def make_node(node_id, name, x=0, y=0, sort_order=0):
    return {
        "id": node_id,
        "name": name,
        "kind": "emit_json",
        "config": {"value": {"value": 3}},
        "position": {"x": x, "y": y},
        "sort_order": sort_order,
        "max_retries": 0,
        "retry_delay_seconds": 1,
        "timeout_seconds": 10,
    }


def make_workflow(client, name="Demo"):
    return client.post("/api/v1/workflows", json={"name": name}).json()


def test_save_graph_and_read_it_back(client):
    wf = make_workflow(client)
    payload = {
        "expected_version": 1,
        "nodes": [make_node("a", "Source A", 80, 120), make_node("b", "Collect", 360, 120, 1)],
        "edges": [{"source_node_id": "a", "target_node_id": "b"}],
    }
    response = client.put(f"/api/v1/workflows/{wf['id']}/graph", json=payload)
    assert response.status_code == 200
    assert response.json()["version"] == 2

    loaded = client.get(f"/api/v1/workflows/{wf['id']}").json()
    assert loaded["version"] == 2
    assert [n["id"] for n in loaded["nodes"]] == ["a", "b"]
    assert loaded["nodes"][0]["position"] == {"x": 80.0, "y": 120.0}
    assert loaded["nodes"][0]["config"] == {"value": {"value": 3}}
    assert loaded["edges"] == [{"source_node_id": "a", "target_node_id": "b"}]


def test_saving_again_replaces_the_graph(client):
    wf = make_workflow(client)
    url = f"/api/v1/workflows/{wf['id']}/graph"
    client.put(url, json={"expected_version": 1, "nodes": [make_node("a", "A"), make_node("b", "B")], "edges": []})
    response = client.put(url, json={"expected_version": 2, "nodes": [make_node("c", "C")], "edges": []})
    assert response.status_code == 200
    assert [n["id"] for n in response.json()["nodes"]] == ["c"]


def test_stale_version_returns_409(client):
    wf = make_workflow(client)
    url = f"/api/v1/workflows/{wf['id']}/graph"
    client.put(url, json={"expected_version": 1, "nodes": [make_node("a", "A")], "edges": []})
    response = client.put(url, json={"expected_version": 1, "nodes": [], "edges": []})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_CONFLICT"


def test_edge_to_missing_node_returns_422(client):
    wf = make_workflow(client)
    response = client.put(
        f"/api/v1/workflows/{wf['id']}/graph",
        json={
            "expected_version": 1,
            "nodes": [make_node("a", "A")],
            "edges": [{"source_node_id": "a", "target_node_id": "ghost"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EDGE_UNKNOWN_NODE"


def test_duplicate_node_names_return_422(client):
    wf = make_workflow(client)
    response = client.put(
        f"/api/v1/workflows/{wf['id']}/graph",
        json={"expected_version": 1, "nodes": [make_node("a", "Same"), make_node("b", "Same")], "edges": []},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DUPLICATE_NODE_NAME"


def test_node_id_used_by_another_workflow_returns_409(client):
    first = make_workflow(client, "First")
    second = make_workflow(client, "Second")
    client.put(f"/api/v1/workflows/{first['id']}/graph", json={"expected_version": 1, "nodes": [make_node("a", "A")], "edges": []})
    response = client.put(f"/api/v1/workflows/{second['id']}/graph", json={"expected_version": 1, "nodes": [make_node("a", "A")], "edges": []})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NODE_ID_IN_USE"


def test_save_graph_on_missing_workflow_returns_404(client):
    response = client.put("/api/v1/workflows/nope/graph", json={"expected_version": 1, "nodes": [], "edges": []})
    assert response.status_code == 404