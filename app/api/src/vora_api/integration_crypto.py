"""Encrypt integration secrets before they touch Postgres.

The Sarvam API key is an app setting. INTEGRATION_ENCRYPTION_KEY is the only
secret that stays outside the database, and the local default is refused
once APP_ENV leaves local or test.
"""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vora_api.settings import get_settings

_LOCAL_KEY = "local-dev-integration-key-not-for-production"
_LOCAL_ENVS = frozenset({"local", "test"})


class IntegrationSecretError(Exception):
    """The encryption key is missing, or the stored ciphertext cannot be opened."""


def _key_bytes() -> bytes:
    settings = get_settings()
    raw = settings.integration_encryption_key.strip()
    if not raw or (raw == _LOCAL_KEY and settings.app_env not in _LOCAL_ENVS):
        raise IntegrationSecretError("Integration encryption key is not configured")
    return hashlib.sha256(raw.encode()).digest()


def seal(plaintext: str, *, purpose: str) -> str:
    if not plaintext:
        raise IntegrationSecretError("Nothing to seal")
    nonce = os.urandom(12)
    token = AESGCM(_key_bytes()).encrypt(nonce, plaintext.encode(), purpose.encode())
    return base64.urlsafe_b64encode(nonce + token).decode()


def open_secret(token: str, *, purpose: str) -> str:
    key = _key_bytes()
    try:
        blob = base64.urlsafe_b64decode(token.encode())
        if len(blob) < 13:
            raise ValueError("short")
        plaintext = AESGCM(key).decrypt(blob[:12], blob[12:], purpose.encode())
    except (InvalidTag, ValueError) as exc:
        raise IntegrationSecretError("Could not read the saved secret") from exc
    return plaintext.decode()
