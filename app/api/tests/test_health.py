from fastapi.testclient import TestClient

from vora_api.main import app
from vora_api.settings import Settings


def test_healthz_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_dependency_failures(monkeypatch) -> None:
    monkeypatch.setattr("vora_api.main.postgres_ok", lambda _settings: False)
    monkeypatch.setattr("vora_api.main.redis_ok", lambda _settings: True)
    monkeypatch.setattr("vora_api.main.get_settings", lambda: Settings())

    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["redis"] is True


def test_readyz_ok_when_dependencies_respond(monkeypatch) -> None:
    monkeypatch.setattr("vora_api.main.postgres_ok", lambda _settings: True)
    monkeypatch.setattr("vora_api.main.redis_ok", lambda _settings: True)
    monkeypatch.setattr("vora_api.main.get_settings", lambda: Settings())

    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
