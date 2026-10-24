import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.integration_crypto import IntegrationSecretError, open_secret, seal
from vora_api.models import PlatformSetting
from vora_api.settings import get_settings

router = APIRouter()
SARVAM = "sarvam"
_DEFAULTS = {
    "stt_model": "saaras:v4",
    "tts_model": "bulbul:v3",
    "llm_model": "sarvam-105b-conversations",
}
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,79}$")
_MODEL_FIELDS = ("stt_model", "tts_model", "llm_model")


class SarvamBody(BaseModel):
    api_key: str | None = None
    stt_model: str | None = None
    tts_model: str | None = None
    llm_model: str | None = None


def _model(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if _MODEL.fullmatch(cleaned) is None:
        raise HTTPException(status_code=422, detail=f"{name} is not a valid model id")
    return cleaned


def _stored_value(row: PlatformSetting | None) -> dict[str, object]:
    if row is None or not isinstance(row.value, dict):
        return {}
    return dict(row.value)


def _config(row: PlatformSetting | None) -> dict[str, str]:
    merged = dict(_DEFAULTS)
    for name in _MODEL_FIELDS:
        raw = _stored_value(row).get(name)
        if isinstance(raw, str) and raw.strip():
            merged[name] = raw.strip()
    return merged


def _public(row: PlatformSetting | None) -> dict[str, object]:
    saved = row is not None and bool(row.secret_ciphertext)
    last4 = "" if row is None or not row.secret_last4 else row.secret_last4
    env_fallback = (not saved) and bool(get_settings().sarvam_api_key.strip())
    return {
        "api_key_set": saved,
        "api_key_last4": last4,
        "env_fallback": env_fallback,
        **_config(row),
    }


def _stored_key(row: PlatformSetting | None) -> tuple[str, str]:
    if row is not None and row.secret_ciphertext:
        try:
            return open_secret(row.secret_ciphertext, purpose=SARVAM), "settings"
        except IntegrationSecretError as exc:
            raise HTTPException(
                status_code=500, detail="Could not read the saved Sarvam key"
            ) from exc
    env_key = get_settings().sarvam_api_key.strip()
    if env_key:
        return env_key, "env"
    return "", "missing"


@router.get("/admin/settings/integrations")
def get_integrations(_: AuthUser = Depends(require_writer)) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        return {"sarvam": _public(session.get(PlatformSetting, SARVAM))}


@router.put("/admin/settings/integrations/sarvam")
def update_sarvam(body: SarvamBody, actor: AuthUser = Depends(require_writer)) -> dict[str, object]:
    api_key = (body.api_key or "").strip()
    if body.api_key is not None and body.api_key.strip() and len(api_key) < 8:
        raise HTTPException(status_code=422, detail="Sarvam API key is too short")
    if len(api_key) > 500:
        raise HTTPException(status_code=422, detail="Sarvam API key is too long")
    models = {name: _model(name, getattr(body, name)) for name in _MODEL_FIELDS}
    ciphertext: str | None = None
    if api_key:
        try:
            ciphertext = seal(api_key, purpose=SARVAM)
        except IntegrationSecretError as exc:
            raise HTTPException(
                status_code=503, detail="Integration encryption is not configured"
            ) from exc
    with admin_transaction(
        action="update_sarvam_integration",
        actor_user_id=actor.id,
        detail="sarvam",
    ) as session:
        row = session.get(PlatformSetting, SARVAM)
        if row is None:
            row = PlatformSetting(key=SARVAM, value={})
            session.add(row)
        value = _stored_value(row)
        for name, cleaned in models.items():
            if cleaned is not None:
                value[name] = cleaned
        row.value = value
        if ciphertext is not None:
            row.secret_ciphertext = ciphertext
            row.secret_last4 = api_key[-4:]
        row.updated_at = datetime.now(UTC)
        session.flush()
        view = _public(row)
    return {"sarvam": view}


@router.get("/internal/integrations/sarvam")
def sarvam_for_worker() -> dict[str, str]:
    """Plaintext for the voice worker on the private network. Not for browsers."""
    with Session(get_admin_engine()) as session:
        row = session.get(PlatformSetting, SARVAM)
        key, source = _stored_key(row)
        config = _config(row)
    return {"api_key": key, "source": source, **config}
