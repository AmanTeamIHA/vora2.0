import os

import pytest

from vora_api.db import postgres_ok
from vora_api.redis_client import redis_ok
from vora_api.settings import get_settings


@pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres and redis")
def test_postgres_and_redis_answer() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert postgres_ok(settings) is True
    assert redis_ok(settings) is True
