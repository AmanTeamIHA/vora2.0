from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session

from vora_api.settings import Settings, get_settings
from vora_api.tenant_context import current_tenant_id


class Base(DeclarativeBase):
    """Shared metadata for Alembic and the request session."""


def postgres_ok(settings: Settings) -> bool:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def _engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_app_engine() -> Engine:
    return _engine(get_settings().app_database_url)


@lru_cache
def get_admin_engine() -> Engine:
    return _engine(get_settings().admin_database_url)


def get_session() -> Iterator[Session]:
    """Request session as vora_app. RLS uses app.tenant_id for this transaction only."""
    session = Session(get_app_engine())
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": current_tenant_id.get()},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def admin_transaction(
    *,
    action: str,
    actor_user_id: UUID | None = None,
    tenant_id: UUID | None = None,
) -> Iterator[Session]:
    """vora_admin bypasses RLS. The audit row commits with the work, or not at all."""
    from vora_api.models import AuditLog

    session = Session(get_admin_engine())
    try:
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_user_id=actor_user_id,
                action=action,
            )
        )
        session.flush()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
