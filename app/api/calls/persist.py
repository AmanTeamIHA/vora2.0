"""Write one lifecycle event as vora_app, with that event's tenant selected."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from contracts import (
    CallAnswered,
    CallCreated,
    CallEnded,
    CallRinging,
    LifecycleEvent,
    TurnCompleted,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vora_api.db import get_app_engine


class WaitingForCall(Exception):
    """The call row is not visible yet. The stream entry stays pending."""


@contextmanager
def tenant_session(tenant_id: UUID) -> Iterator[Session]:
    """One transaction as vora_app. RLS sees only this tenant."""
    session = Session(get_app_engine())
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def apply_event(session: Session, event: LifecycleEvent) -> None:
    try:
        if isinstance(event, CallCreated):
            _created(session, event)
        elif isinstance(event, CallRinging):
            _require_call(session, _RINGING, _scope(event))
        elif isinstance(event, CallAnswered):
            _require_call(session, _ANSWERED, _scope(event))
        elif isinstance(event, TurnCompleted):
            _turn(session, event)
        elif isinstance(event, CallEnded):
            _ended(session, event)
        else:
            raise RuntimeError(f"unhandled lifecycle event {type(event).__name__}")
    except IntegrityError as exc:
        if _missing_parent(exc):
            raise WaitingForCall(str(event.call_id)) from exc
        raise


def _scope(event: LifecycleEvent) -> dict[str, object]:
    return {
        "call_id": event.call_id,
        "tenant_id": event.tenant_id,
        "occurred_at": event.occurred_at,
    }


def _require_call(session: Session, statement: str, params: dict[str, object]) -> None:
    if session.execute(text(statement), params).first() is None:
        raise WaitingForCall(str(params["call_id"]))


def _created(session: Session, event: CallCreated) -> None:
    # A later status event may already have been applied if this delivery is a replay
    # after the row existed. Do not walk status backwards to "created".
    row = session.execute(
        text(
            """
            INSERT INTO calls (
                id, tenant_id, agent_id, agent_version_id, status, created_at
            ) VALUES (
                :call_id, :tenant_id, :agent_id, :agent_version_id, 'created', :occurred_at
            )
            ON CONFLICT (id) DO UPDATE SET
                agent_id = EXCLUDED.agent_id,
                agent_version_id = EXCLUDED.agent_version_id
            RETURNING id
            """
        ),
        {
            "call_id": event.call_id,
            "tenant_id": event.tenant_id,
            "agent_id": event.agent_id,
            "agent_version_id": event.agent_version_id,
            "occurred_at": event.occurred_at,
        },
    ).first()
    if row is None:
        raise WaitingForCall(str(event.call_id))


_RINGING = """
UPDATE calls
SET ringing_at = COALESCE(ringing_at, :occurred_at),
    status = CASE
        WHEN status IN ('answered', 'ended') THEN status
        ELSE 'ringing'
    END
WHERE id = :call_id AND tenant_id = :tenant_id
RETURNING id
"""

_ANSWERED = """
UPDATE calls
SET answered_at = COALESCE(answered_at, :occurred_at),
    status = CASE
        WHEN status = 'ended' THEN status
        ELSE 'answered'
    END
WHERE id = :call_id AND tenant_id = :tenant_id
RETURNING id
"""

_ENDED = """
UPDATE calls
SET ended_at = :occurred_at,
    end_reason = :end_reason,
    duration_ms = :duration_ms,
    status = 'ended'
WHERE id = :call_id AND tenant_id = :tenant_id
RETURNING id
"""

_TURN = """
INSERT INTO call_turns (
    tenant_id, call_id, turn_index, stt_ms, llm_ms, tts_ms, ttfw_ms, created_at
) VALUES (
    :tenant_id, :call_id, :turn_index, :stt_ms, :llm_ms, :tts_ms, :ttfw_ms, :occurred_at
)
ON CONFLICT ON CONSTRAINT call_turns_call_index DO NOTHING
"""

_RECORDING = """
INSERT INTO call_recordings (tenant_id, call_id, recording_key, created_at)
VALUES (:tenant_id, :call_id, :recording_key, :occurred_at)
ON CONFLICT ON CONSTRAINT call_recordings_key DO NOTHING
"""


def _turn(session: Session, event: TurnCompleted) -> None:
    session.execute(
        text(_TURN),
        {
            "tenant_id": event.tenant_id,
            "call_id": event.call_id,
            "turn_index": event.turn_index,
            "stt_ms": event.stt_ms,
            "llm_ms": event.llm_ms,
            "tts_ms": event.tts_ms,
            "ttfw_ms": event.ttfw_ms,
            "occurred_at": event.occurred_at,
        },
    )


def _ended(session: Session, event: CallEnded) -> None:
    _require_call(
        session,
        _ENDED,
        {
            **_scope(event),
            "end_reason": event.reason,
            "duration_ms": event.duration_ms,
        },
    )
    if event.recording_key:
        session.execute(
            text(_RECORDING),
            {
                "tenant_id": event.tenant_id,
                "call_id": event.call_id,
                "recording_key": event.recording_key,
                "occurred_at": event.occurred_at,
            },
        )


def _missing_parent(exc: IntegrityError) -> bool:
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate is None:
        sqlstate = getattr(orig, "pgcode", None)
    return sqlstate == "23503"
