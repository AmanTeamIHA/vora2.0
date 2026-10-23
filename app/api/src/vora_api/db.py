from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase

from vora_api.settings import Settings


class Base(DeclarativeBase):
    """Shared metadata. Tables arrive in later migrations."""


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
