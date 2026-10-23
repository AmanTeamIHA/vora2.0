from fastapi.testclient import TestClient

from vora_api.main import app
from vora_api.settings import get_settings


def test_public_api_prefix_reaches_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_internal_secret_blocks_a_public_caller(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "s3cret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            missing = client.get("/internal/dids/+919800000000")
            prefixed = client.get("/api/internal/dids/+919800000000")
            present = client.get(
                "/internal/dids/+919800000000",
                headers={"x-vora-internal": "s3cret"},
            )
        assert missing.status_code == 401
        assert missing.json()["detail"] == "Internal auth failed"
        assert prefixed.status_code == 401
        assert prefixed.json()["detail"] == "Internal auth failed"
        assert present.status_code == 401
        assert present.json()["detail"] == "Sign in required"
    finally:
        monkeypatch.delenv("INTERNAL_AUTH_SECRET", raising=False)
        get_settings.cache_clear()
