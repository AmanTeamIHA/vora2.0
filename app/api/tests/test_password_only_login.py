import pytest
from fastapi.testclient import TestClient

from vora_api.main import app
from vora_api.settings import Settings, get_settings


def test_password_only_login_is_local_and_dev_only() -> None:
    assert Settings(app_env="local").password_only_login is True
    assert Settings(app_env="dev").password_only_login is True
    assert Settings(app_env="DEV").password_only_login is True
    assert Settings(app_env="prod").password_only_login is False
    assert Settings(app_env="production").password_only_login is False
    assert Settings(app_env="staging").password_only_login is False


@pytest.mark.parametrize("app_env", ["prod", "production"])
def test_production_config_refuses_password_only_login(
    monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        response = client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "owner-password"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Password-only sign-in is refused in production"
        assert response.cookies.get("vora_access") is None
    finally:
        get_settings.cache_clear()
