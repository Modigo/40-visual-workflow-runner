from fastapi.testclient import TestClient

from app.main import app


def test_unknown_url_uses_error_envelope(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unexpected_error_returns_500_envelope():
    @app.get("/__test_boom")
    def boom():
        raise RuntimeError("secret internal detail")

    # By default the test client re-raises server errors. We want to see
    # what a real user would receive, so we turn that off.
    test_client = TestClient(app, raise_server_exceptions=False)
    response = test_client.get("/__test_boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in response.text