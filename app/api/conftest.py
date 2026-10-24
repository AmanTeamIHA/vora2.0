import os
from pathlib import Path

import pytest

_API_ROOT = Path(__file__).resolve().parent


@pytest.fixture(scope="session", autouse=True)
def api_working_directory() -> None:
    """API tests open alembic.ini from the working directory."""
    os.chdir(_API_ROOT)
