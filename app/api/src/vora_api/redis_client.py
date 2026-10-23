from redis import Redis

from vora_api.settings import Settings


def redis_ok(settings: Settings) -> bool:
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        return bool(client.ping())
    except Exception:
        return False
    finally:
        client.close()
