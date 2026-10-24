import pytest

from vora_api.integration_crypto import IntegrationSecretError, open_secret, seal
from vora_api.settings import get_settings


def test_seal_hides_the_plaintext_and_round_trips() -> None:
    get_settings.cache_clear()
    secret = "sk-sarvam-test-9f3a"
    token = seal(secret, purpose="sarvam")
    assert secret not in token
    assert open_secret(token, purpose="sarvam") == secret
    with pytest.raises(IntegrationSecretError):
        open_secret(token, purpose="other")


def test_local_encryption_key_is_refused_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "local-dev-integration-key-not-for-production")
    get_settings.cache_clear()
    try:
        with pytest.raises(IntegrationSecretError):
            seal("sk-sarvam-test-9f3a", purpose="sarvam")
    finally:
        get_settings.cache_clear()


def test_a_real_key_works_when_app_env_is_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", "generated-in-secrets-manager")
    get_settings.cache_clear()
    try:
        token = seal("sk-sarvam-test-9f3a", purpose="sarvam")
        assert open_secret(token, purpose="sarvam") == "sk-sarvam-test-9f3a"
    finally:
        get_settings.cache_clear()
