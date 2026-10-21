def test_create_and_get_workflow(client):
    response = client.post("/api/v1/workflows", json={"name": "Demo", "description": "x"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Demo"
    assert body["version"] == 1

    response = client.get(f"/api/v1/workflows/{body['id']}")
    assert response.status_code == 200
    assert response.json()["nodes"] == []
    assert response.json()["edges"] == []


def test_list_workflows(client):
    client.post("/api/v1/workflows", json={"name": "One"})
    client.post("/api/v1/workflows", json={"name": "Two"})
    response = client.get("/api/v1/workflows")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_missing_workflow_returns_404(client):
    response = client.get("/api/v1/workflows/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_create_workflow_rejects_empty_name(client):
    response = client.post("/api/v1/workflows", json={"name": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"