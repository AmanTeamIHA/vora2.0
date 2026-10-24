from uuid import UUID

# Global Redis Stream. Every lifecycle event is also appended here.
CALLS_EVENTS_STREAM = "calls:events"


def tenant_calls_stream(tenant_id: UUID) -> str:
    """Per-tenant Redis Stream key. Format: `calls:events:{tenant_id}`."""
    return f"{CALLS_EVENTS_STREAM}:{tenant_id}"
